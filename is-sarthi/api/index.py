"""
Vercel Serverless FastAPI API for IS Sarthi.
Exposes recommendations, specification validation, dependency graph, catalog analytics,
and multilingual speech services.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.demo_offline import OfflineCorpus
from pipeline.utils.normalize import extract_all_is_references, normalize_is_number
from ui import speech_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("is_sarthi_api")

app = FastAPI(
    title="IS Sarthi API",
    description="Indian Standards Recommendation, Compliance & Allied Graph API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Corpus
def _load_corpus() -> OfflineCorpus:
    seed_paths = [
        BASE_DIR / "data" / "seed" / "standards.json",
        Path("data/seed/standards.json"),
        Path(__file__).resolve().parent / "data" / "standards.json",
    ]
    for p in seed_paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                records = json.load(f)
            logger.info("Loaded %d standards from %s", len(records), p)
            return OfflineCorpus(records)
    raise FileNotFoundError("Could not locate standards.json in data/seed/")

corpus = _load_corpus()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def generate_tender_clause(rec: dict) -> str:
    """Generate legally compliant tender specification clause."""
    is_num = rec.get("is_number", "IS XXXX")
    latest = rec.get("latest_version") or is_num
    title = rec.get("title", "")
    cert = rec.get("certification") or {}

    clause = [
        f"1. Standard Conformity: The supplied materials/equipment shall strictly conform to {latest} "
        f"('{title}'), including all up-to-date amendments issued by the Bureau of Indian Standards (BIS)."
    ]

    if cert.get("mandatory") or cert.get("scheme"):
        scheme = cert.get("scheme_label") or cert.get("scheme", "ISI")
        clause.append(
            f"2. Mandatory Certification: The product must bear the valid {scheme} mark as mandated by the "
            f"appropriate Quality Control Order (QCO) published in the Gazette of India. Uncertified bids shall be summarily rejected."
        )

    allied = rec.get("allied") or rec.get("allied_standards", {}).get("by_role", {})
    if allied:
        test_methods = [
            item["is_number"]
            for item in allied.get("Test method", allied.get("test_method", []))
        ]
        if test_methods:
            clause.append(
                f"3. Acceptance & Routine Tests: Acceptance testing at vendor works shall strictly follow testing procedures "
                f"prescribed in {', '.join(test_methods[:4])}."
            )

        conductors = [
            item["is_number"]
            for item in allied.get("Related product", allied.get("related_product", []))
        ]
        if conductors:
            clause.append(
                f"4. Normative Raw Materials: Raw materials and components shall satisfy {', '.join(conductors[:3])}."
            )

    return "\n\n".join(clause)


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=8000)
    top_k: int = Field(5, ge=1, le=15)
    division: Optional[str] = None


class ValidateRequest(BaseModel):
    spec_text: str = Field(..., min_length=3, max_length=100000)


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=3000)
    language_code: str = Field("hi-IN", pattern="^(en-IN|hi-IN|mr-IN|te-IN|ta-IN)$")


class FeedbackRequest(BaseModel):
    is_number: str
    verdict: str = Field(..., pattern="^(relevant|irrelevant)$")
    query: Optional[str] = None


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "standards_indexed": len(corpus.records),
        "voice_enabled": speech_service.is_voice_enabled(),
    }


@app.get("/api/standards")
def get_standards(division: Optional[str] = None, search: Optional[str] = None):
    results = corpus.records
    if division and division != "All":
        results = [r for r in results if r.get("division") == division]
    if search and search.strip():
        kw = search.strip().lower()
        results = [
            r for r in results
            if kw in r["is_number"].lower() or kw in r.get("title", "").lower() or kw in r.get("scope", "").lower()
        ]

    summary = [
        {
            "is_number": r["is_number"],
            "title": r.get("title", ""),
            "division": r.get("division", "ETD"),
            "year": r.get("year"),
            "status": r.get("status", "current"),
            "mandatory_qco": bool((r.get("certification") or {}).get("mandatory")),
            "certification": r.get("certification"),
        }
        for r in results
    ]
    return {"total": len(summary), "standards": summary}


@app.get("/api/standards/{is_number}")
def get_standard_detail(is_number: str):
    canonical = normalize_is_number(is_number) or is_number
    record = corpus.by_number.get(canonical)
    if not record:
        raise HTTPException(status_code=404, detail=f"Standard '{is_number}' not found.")
    
    # Enrich with tender clause & graph references
    enriched = dict(record)
    enriched["tender_clause"] = generate_tender_clause(record)
    enriched["allied_by_role"] = corpus.allied(canonical, query=record.get("title", ""))
    return enriched


@app.get("/api/standards/{is_number}/graph")
def get_standard_graph(is_number: str, depth: int = 1):
    canonical = normalize_is_number(is_number) or is_number
    record = corpus.by_number.get(canonical)
    if not record:
        raise HTTPException(status_code=404, detail=f"Standard '{is_number}' not found.")

    nodes = []
    edges = []
    visited = {canonical}

    nodes.append({
        "id": canonical,
        "label": canonical,
        "title": record.get("title", ""),
        "status": record.get("status", "current"),
        "division": record.get("division", "ETD"),
        "is_target": True,
    })

    frontier = [(canonical, 0)]
    while frontier:
        current, hop = frontier.pop(0)
        if hop >= depth:
            continue

        for ref in corpus.graph.get(current, []):
            child = ref["is_number"]
            role = ref.get("ref_type", "reference")
            edges.append({
                "source": current,
                "target": child,
                "role": role,
            })

            if child not in visited:
                child_rec = corpus.by_number.get(child, {})
                nodes.append({
                    "id": child,
                    "label": child,
                    "title": child_rec.get("title") or ref.get("title", ""),
                    "status": child_rec.get("status", "current"),
                    "division": child_rec.get("division", "ETD"),
                    "is_target": False,
                })
                visited.add(child)
                frontier.append((child, hop + 1))

    return {"target": canonical, "nodes": nodes, "edges": edges}


@app.post("/api/recommend")
def recommend_standards(req: RecommendRequest):
    result = corpus.recommend(req.query.strip(), top_k=req.top_k)
    recs = result.get("recommendations", [])
    
    if req.division and req.division != "All Divisions":
        recs = [r for r in recs if corpus.by_number.get(r["is_number"], {}).get("division") == req.division]
        result["recommendations"] = recs

    # Add pre-computed tender clauses to each recommendation
    for r in recs:
        r["tender_clause"] = generate_tender_clause(r)

    return result


@app.post("/api/validate")
def validate_specification(req: ValidateRequest):
    return corpus.validate(req.spec_text.strip())


@app.post("/api/speech/transcribe")
async def transcribe_audio_file(
    file: UploadFile = File(...),
    language_code: str = Form("auto"),
):
    if not speech_service.is_voice_enabled():
        raise HTTPException(status_code=503, detail="Voice service is not configured (SARVAM_API_KEY missing).")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    lang_arg = "unknown" if language_code == "auto" else language_code
    transcript, detected = speech_service.transcribe_audio(content, language_code=lang_arg)
    return {
        "transcript": transcript,
        "detected_language": detected,
    }


@app.post("/api/speech/synthesize")
def synthesize_speech_narration(req: SynthesizeRequest):
    if not speech_service.is_voice_enabled():
        raise HTTPException(status_code=503, detail="Voice service is not configured (SARVAM_API_KEY missing).")

    text_to_narrate = req.text.strip()
    if req.language_code != "en-IN":
        try:
            text_to_narrate = speech_service.translate_text(
                req.text, target_language_code=req.language_code, source_language_code="en-IN"
            )
        except Exception as err:
            logger.warning("Translation error: %s, falling back to original", err)

    audio_bytes = speech_service.synthesize_speech(text_to_narrate, language_code=req.language_code)
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    return {
        "text": text_to_narrate,
        "language_code": req.language_code,
        "audio_base64": f"data:audio/wav;base64,{audio_base64}",
    }


@app.post("/api/feedback")
def record_feedback(req: FeedbackRequest):
    logger.info("Feedback for %s: %s (query: %s)", req.is_number, req.verdict, req.query)
    return {"success": True, "message": "Feedback recorded."}
