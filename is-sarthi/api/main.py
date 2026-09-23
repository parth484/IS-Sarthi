"""IS Sarthi recommendation API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.services import recommender, retrieval
from pipeline.db.stores import graph, postgres, vectors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IS Sarthi API",
    description=(
        "Recommends applicable Indian Standards for procurement specifications, "
        "with allied standards, currency status and certification requirements."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ schemas

class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=8000,
                       description="Product description or technical specification")
    top_k: Optional[int] = Field(None, ge=1, le=10)
    include_withdrawn: bool = Field(
        False, description="Include withdrawn standards, e.g. when auditing an old tender"
    )


class ValidateRequest(BaseModel):
    spec_text: str = Field(..., min_length=10, max_length=100_000)


class FeedbackRequest(BaseModel):
    recommendation_id: Optional[str] = None
    is_number: str
    verdict: str = Field(..., pattern="^(accept|reject)$")
    comment: Optional[str] = None


# ------------------------------------------------------------------ lifecycle

@app.on_event("startup")
def startup() -> None:
    count = retrieval.build_sparse_index()
    logger.info(
        "Startup complete: %d vectors, %d sparse docs, postgres=%s, neo4j=%s",
        vectors.count(), count, postgres.available, graph.available,
    )


# ------------------------------------------------------------------ routes

@app.post("/api/v1/recommend")
def recommend(request: RecommendRequest) -> dict:
    """FR-201..FR-205 -- the core recommendation endpoint."""
    try:
        return recommender.recommend(
            request.query,
            top_k=request.top_k,
            include_withdrawn=request.include_withdrawn,
        )
    except Exception as exc:
        logger.exception("Recommendation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/recommend/document")
async def recommend_document(file: UploadFile = File(...)) -> dict:
    """
    FR-103 -- accept a tender document and recommend per extracted line item.

    Uploaded content is processed in memory and never persisted: tender text is
    routinely pre-publication and commercially sensitive.
    """
    content = await file.read()
    text = _extract_text(content, file.filename or "")
    if not text.strip():
        raise HTTPException(status_code=422, detail="No extractable text in document.")

    segments = _segment_spec(text)
    results = [
        {"segment": segment[:200], **recommender.recommend(segment, top_k=3)}
        for segment in segments[:10]
    ]
    return {"filename": file.filename, "segments_found": len(segments), "results": results}


@app.post("/api/v1/validate-spec")
def validate_spec(request: ValidateRequest) -> dict:
    """FR-404 -- flag outdated, withdrawn or incomplete citations in a draft."""
    return recommender.validate_spec(request.spec_text)


@app.get("/api/v1/standards/{is_number:path}")
def get_standard(is_number: str) -> dict:
    record = postgres.get_standard(is_number)
    if not record:
        raise HTTPException(status_code=404, detail=f"{is_number} not in corpus")
    record["allied_standards"] = graph.allied_standards(is_number)
    return record


@app.get("/api/v1/standards/{is_number:path}/graph")
def standard_graph(is_number: str) -> dict:
    """Nodes and edges for the dependency-graph visualization."""
    return graph.neighbourhood(is_number)


@app.post("/api/v1/feedback")
def submit_feedback(request: FeedbackRequest) -> dict:
    """
    FR-604. Beyond product analytics, this table is the training substrate for
    replacing the hand-weighted confidence formula and the heuristic reference
    classifier with fitted models.
    """
    with postgres.cursor() as cur:
        if cur is None:
            return {"stored": False, "reason": "datastore unavailable"}
        cur.execute(
            """INSERT INTO feedback (recommendation_id, is_number, verdict, comment)
               VALUES (%s,%s,%s,%s)""",
            (request.recommendation_id, request.is_number, request.verdict, request.comment),
        )
    return {"stored": True}


@app.get("/api/v1/changes")
def changes(since: Optional[str] = Query(None)) -> dict:
    """FR-705 -- corpus changelog."""
    since = since or (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    return {"since": since, "changes": postgres.changes_since(since)}


@app.get("/api/v1/coverage")
def coverage() -> dict:
    """Powers the UI's honest coverage badge."""
    return {"divisions": postgres.coverage(), "indexed_vectors": vectors.count()}


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "vectors": vectors.count(),
        "postgres": postgres.available,
        "neo4j": graph.available,
    }


@app.get("/health/pipeline")
def pipeline_health() -> dict:
    with postgres.cursor(commit=False) as cur:
        if cur is None:
            return {"healthy": False, "reason": "postgres unavailable"}
        cur.execute("SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 5")
        runs = [dict(row) for row in cur.fetchall()]
    return {"recent_runs": runs, "healthy": all(r.get("healthy") for r in runs) if runs else None}


# ------------------------------------------------------------------ helpers

def _extract_text(content: bytes, filename: str) -> str:
    import io

    name = filename.lower()
    if name.endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages[:40])
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    return content.decode("utf-8", errors="ignore")


def _segment_spec(text: str) -> list[str]:
    """
    Split a tender into per-line-item specifications.

    Tenders are structured as numbered item lists far more often than as prose,
    so numbered-clause boundaries segment them better than sentence splitting
    would -- and each item needs its own standards, which is the whole point of
    segmenting rather than embedding the document as one blob.
    """
    import re

    parts = re.split(r"\n\s*(?:\d+[\.\)]\s+|[a-z][\.\)]\s+|Item\s+\d+)", text)
    segments = [
        re.sub(r"\s+", " ", part).strip()
        for part in parts
        if len(part.strip()) > 60
    ]
    return segments or [re.sub(r"\s+", " ", text).strip()[:2000]]
