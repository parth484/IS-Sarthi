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
from pipeline.classify import ROLE_LABELS
from pipeline.scrapers.doc_extractor import extract_document_text
from pipeline.scrapers.pdf_extractor import extract_text_from_pdf
from pipeline.utils.multilingual import normalize_query_for_retrieval
from pipeline.procurement.service import ProcurementService
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
procurement_service = ProcurementService(corpus)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def generate_tender_clause(rec: dict) -> str:
    """
    Generate legally compliant, enforceable tender specification clause.
    Incorporates distinct certification scheme requirements (ISI/QCO, CRS, Hallmarking)
    and allied standards categorized across the role taxonomy (Test method, Safety,
    Installation, Related product, Terminology).
    """
    is_num = rec.get("is_number", "IS XXXX")
    latest = rec.get("latest_version") or is_num
    title = rec.get("title", "")
    cert = rec.get("certification") or {}

    clause_idx = 1
    clause = [
        f"{clause_idx}. Standard Conformity: The supplied materials/equipment shall strictly conform to {latest} "
        f"('{title}'), including all up-to-date amendments issued by the Bureau of Indian Standards (BIS)."
    ]

    # Granular Certification Scheme Handling
    if cert.get("mandatory") or cert.get("scheme"):
        scheme = str(cert.get("scheme") or "ISI").strip().upper()
        product = cert.get("product") or "this item"
        clause_idx += 1

        if scheme == "CRS":
            clause.append(
                f"{clause_idx}. Mandatory Compulsory Registration (CRS): The product ('{product}') must be registered "
                f"under the BIS Compulsory Registration Scheme (CRS) pursuant to Scheme-II of BIS (Conformity Assessment) "
                f"Regulations, 2018. Bidders must furnish a valid BIS Registration number (R-number) and affix the standard "
                f"words 'Self Declaration - Conforming to {is_num}' on packaging. Unregistered products shall be summarily rejected."
            )
        elif scheme == "HALLMARKING":
            clause.append(
                f"{clause_idx}. Mandatory BIS Hallmarking: All articles ('{product}') must bear mandatory BIS Hallmarking "
                f"with a 6-digit alphanumeric Hallmarking Unique Identification (HUID) and fineness grade in accordance with "
                f"the Bureau of Indian Standards (Hallmarking) Regulations. Bids offering non-hallmarked articles shall be rejected."
            )
        else:  # Standard ISI / QCO
            scheme_label = cert.get("scheme_label") or "BIS Product Certification (ISI mark)"
            clause.append(
                f"{clause_idx}. Mandatory Certification ({scheme_label}): The product must bear the valid Standard ISI Mark "
                f"under Scheme-I of BIS (Conformity Assessment) Regulations, 2018, as mandated by the applicable Gazette "
                f"Quality Control Order (QCO). Bidders must hold an active CM/L BIS license on bid submission date. "
                f"Uncertified bids shall be summarily rejected."
            )

    # Allied Standards by Taxonomy Role
    allied = rec.get("allied") or rec.get("allied_standards", {}).get("by_role", {})
    if allied:
        # 1. Test methods
        test_methods = [
            item["is_number"]
            for item in allied.get("Test method", allied.get("test_method", []))
        ]
        if test_methods:
            clause_idx += 1
            clause.append(
                f"{clause_idx}. Acceptance & Routine Testing: Acceptance testing, lot sampling, and routine quality verification "
                f"at vendor premises shall strictly comply with test procedures prescribed in {', '.join(test_methods[:4])}."
            )

        # 2. Safety
        safety = [
            item["is_number"]
            for item in allied.get("Safety", allied.get("safety", []))
        ]
        if safety:
            clause_idx += 1
            clause.append(
                f"{clause_idx}. Operational Safety & Environmental Protection: Equipment design, insulation barriers, and operational "
                f"safety mechanisms shall strictly adhere to {', '.join(safety[:3])}."
            )

        # 3. Installation & Erection
        installation = [
            item["is_number"]
            for item in allied.get("Installation", allied.get("installation", []))
        ]
        if installation:
            clause_idx += 1
            clause.append(
                f"{clause_idx}. Installation & Code of Practice: Field erection, mounting, laying, earthing, and commissioning "
                f"practices shall strictly follow {', '.join(installation[:3])}."
            )

        # 4. Related Products & Raw Materials
        related_products = [
            item["is_number"]
            for item in allied.get("Related product", allied.get("related_product", []))
        ]
        if related_products:
            clause_idx += 1
            clause.append(
                f"{clause_idx}. Normative Raw Materials & Feedstocks: Sub-components, conductors, and raw materials used in manufacture "
                f"shall conform to {', '.join(related_products[:3])}."
            )

        # 5. Terminology & Definitions
        terminology = [
            item["is_number"]
            for item in allied.get("Terminology", allied.get("terminology", []))
        ]
        if terminology:
            clause_idx += 1
            clause.append(
                f"{clause_idx}. Terminology & Standards Nomenclature: Technical definitions, ratings, and engineering nomenclature "
                f"shall be interpreted in accordance with {', '.join(terminology[:3])}."
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
            role = ROLE_LABELS.get(ref.get("ref_type"), "Related product")
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
    # Multilingual query normalization (Hindi, Marathi, Telugu, Tamil, English)
    normalized_q, detected_lang, orig_q = normalize_query_for_retrieval(req.query.strip())

    result = corpus.recommend(normalized_q, top_k=req.top_k)
    recs = result.get("recommendations", [])
    
    if req.division and req.division != "All Divisions":
        recs = [r for r in recs if corpus.by_number.get(r["is_number"], {}).get("division") == req.division]
        result["recommendations"] = recs

    # Add pre-computed tender clauses to each recommendation
    for r in recs:
        r["tender_clause"] = generate_tender_clause(r)

    # Preserve original user query for UI display while exposing normalized retrieval representation
    result["query"] = orig_q
    result["normalized_query"] = normalized_q
    result["detected_language"] = detected_lang

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


@app.post("/api/extract-document")
async def extract_document_endpoint(file: UploadFile = File(...)):
    """Extract readable text from an uploaded specification document (.pdf, .docx, .txt)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing from upload.")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported document format '{ext}'. Accepted formats: .pdf, .docx, .txt.",
        )

    content = await file.read()
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"The uploaded document '{file.filename}' is empty (0 bytes).",
        )

    try:
        text = extract_document_text(content, file.filename)
        return {
            "text": text,
            "filename": file.filename,
            "character_count": len(text),
            "format": ext.lstrip("."),
        }
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error("Document extraction error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to process document: {str(exc)}",
        )


@app.post("/api/extract-pdf")
async def extract_pdf_document(file: UploadFile = File(...)):
    """Backward compatibility endpoint for PDF extraction."""
    return await extract_document_endpoint(file)


# -----------------------------------------------------------------------------
# Procurement Portal Integration Endpoints
# -----------------------------------------------------------------------------
class ProcurementIngestRequest(BaseModel):
    tender_id_or_data: Any = Field(..., description="Tender ID (e.g. GEM/2026/B/892104) or full tender specification object")
    portal: Optional[str] = Field("gem", description="Procurement portal connector ('gem' or 'generic')")
    top_k: int = Field(5, ge=1, le=15)
    division: Optional[str] = None


@app.get("/api/procurement/sample-tenders")
def get_sample_procurement_tenders():
    """Return sample verified GeM public procurement tenders for testing."""
    return procurement_service.get_sample_tenders()


@app.post("/api/procurement/ingest")
def ingest_procurement_tender(req: ProcurementIngestRequest):
    """
    Ingest a procurement tender, normalize specification, and pass into the
    existing BIS recommendation engine.
    """
    try:
        res = procurement_service.ingest_and_recommend(
            tender_input=req.tender_id_or_data,
            connector_type=req.portal or "gem",
            top_k=req.top_k,
            division=req.division,
        )
        # Add pre-computed tender clauses to recommendations
        for r in res.get("recommendations", []):
            if not r.get("tender_clause"):
                r["tender_clause"] = generate_tender_clause(r)
        return res
    except Exception as exc:
        logger.error("Procurement ingestion failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to ingest procurement tender: {exc}")

