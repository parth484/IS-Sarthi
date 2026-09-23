"""
Recommendation orchestration -- the layer that turns retrieval results into
the resolved compliance surface described in the PRD.

Sequence: retrieve -> enrich from Postgres -> expand the citation graph ->
attach certification -> generate justifications -> assemble.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from api.services import reasoning, retrieval
from pipeline.classify import ROLE_LABELS
from pipeline.config import settings
from pipeline.db.stores import graph, postgres
from pipeline.utils.normalize import extract_all_is_references

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    """
    Script-range detection.

    Deliberately not a statistical language identifier: those are unreliable on
    the short, technical, code-switched text typical of procurement queries
    ("2 core copper cable ka standard"). Script ranges are crude but they do
    not produce confident wrong answers, and the only thing this feeds is the
    output language of the justification.
    """
    ranges = {
        "hi": (0x0900, 0x097F),  # Devanagari -- also Marathi
        "bn": (0x0980, 0x09FF),
        "ta": (0x0B80, 0x0BFF),
        "te": (0x0C00, 0x0C7F),
        "kn": (0x0C80, 0x0CFF),
        "ml": (0x0D00, 0x0D7F),
        "gu": (0x0A80, 0x0AFF),
        "pa": (0x0A00, 0x0A7F),
        "or": (0x0B00, 0x0B7F),
    }
    for char in text:
        code = ord(char)
        for language, (low, high) in ranges.items():
            if low <= code <= high:
                return language
    return "en"


def _enrich(candidate: retrieval.Candidate) -> dict:
    """Merge the vector-store hit with the Postgres system of record."""
    stored = postgres.get_standard(candidate.is_number) or {}
    return {
        "is_number": candidate.is_number,
        "title": stored.get("title") or candidate.title,
        "year": stored.get("year") or candidate.metadata.get("year"),
        "status": stored.get("status") or candidate.metadata.get("status", "current"),
        "division": stored.get("division") or candidate.metadata.get("division"),
        "scope": stored.get("scope") or candidate.document,
        "amendments": stored.get("amendments") or [],
        "superseded_by": stored.get("superseded_by"),
        "certification": stored.get("certification") or {},
        "source_url": stored.get("source_url"),
        "corpus_version": stored.get("corpus_version", 0),
        "confidence": candidate.confidence,
        "confidence_band": retrieval.confidence_band(candidate.confidence),
        "_scores": {
            "dense": round(candidate.dense_score, 4),
            "sparse": round(candidate.sparse_score, 4),
            "fused": round(candidate.fused_score, 6),
            "rerank": round(candidate.rerank_score, 4),
        },
    }


def _allied(is_number: str, query: str) -> dict:
    """
    Expand the citation graph and rank allied standards.

    Pure adjacency is the wrong ranking here. Terminology standards are cited by
    almost every product standard in their division, so hop distance alone
    floats them to the top of every result -- and they are rarely what the
    official needs. Blending in semantic relevance to the actual query pushes
    the test-method or safety standard that matters for *this* spec above the
    glossary that matters for all of them.
    """
    allied = graph.allied_standards(is_number, depth=settings.graph_depth)
    if not allied:
        return {"by_role": {}, "total": 0}

    try:
        query_embedding = retrieval.get_embedder().encode(
            f"query: {query}", normalize_embeddings=True
        )
        import numpy as np

        texts = [f"passage: {item.get('title') or item['is_number']}" for item in allied]
        embeddings = retrieval.get_embedder().encode(texts, normalize_embeddings=True)
        similarities = np.dot(embeddings, query_embedding)
    except Exception:
        similarities = [0.0] * len(allied)

    for item, similarity in zip(allied, similarities):
        hop = item.get("hop", 1) or 1
        item["relevance"] = round(0.6 * (1.0 / hop) + 0.4 * float(similarity), 4)

    allied.sort(key=lambda item: item["relevance"], reverse=True)

    by_role: dict[str, list[dict]] = {}
    for item in allied:
        role = item.get("ref_type") or "related_product"
        by_role.setdefault(ROLE_LABELS.get(role, "Related product"), []).append(
            {
                "is_number": item["is_number"],
                "title": item.get("title"),
                "status": item.get("status", "current"),
                "hop": item.get("hop", 1),
                "relevance": item["relevance"],
            }
        )

    return {"by_role": by_role, "total": len(allied)}


def _certification(record: dict) -> Optional[dict]:
    certification = record.get("certification") or {}
    if not certification:
        return None
    return {
        "scheme": certification.get("scheme"),
        "label": certification.get("scheme_label") or certification.get("scheme"),
        "mandatory": certification.get("mandatory", True),
        "effective_date": certification.get("effective_date"),
        "gazette_url": certification.get("gazette_url"),
        "product": certification.get("product"),
    }


def recommend(
    query: str,
    top_k: Optional[int] = None,
    include_withdrawn: bool = False,
) -> dict:
    started = time.perf_counter()
    language = _detect_language(query)

    candidates = retrieval.retrieve(query, top_k=top_k, include_withdrawn=include_withdrawn)
    retrieval_ms = int((time.perf_counter() - started) * 1000)

    if not candidates:
        return {
            "query": query,
            "language": language,
            "state": "no_results",
            "message": "No standards in the current corpus matched this specification.",
            "recommendations": [],
            "timing_ms": {"retrieval": retrieval_ms, "total": retrieval_ms},
        }

    enriched = [_enrich(candidate) for candidate in candidates]

    # FR-204: a confident wrong answer is worse than an honest uncertain one.
    top_confidence = enriched[0]["confidence"]
    if top_confidence < settings.min_confidence:
        return {
            "query": query,
            "language": language,
            "state": "low_confidence",
            "message": (
                "No confident match. Consider adding technical detail such as "
                "material, rating, dimensions or intended application."
            ),
            "recommendations": [
                {k: v for k, v in item.items() if not k.startswith("_")}
                for item in enriched[:3]
            ],
            "timing_ms": {"retrieval": retrieval_ms,
                          "total": int((time.perf_counter() - started) * 1000)},
        }

    reasoning_output = reasoning.generate_justifications(query, enriched, language)
    justification_map = {
        item["is_number"]: item for item in reasoning_output.get("justifications", [])
    }

    recommendations = []
    for record in enriched:
        justification = justification_map.get(record["is_number"], {})
        recommendations.append(
            {
                "is_number": record["is_number"],
                "title": record["title"],
                "year": record["year"],
                "status": record["status"],
                "superseded_by": record["superseded_by"],
                "division": record["division"],
                "confidence": record["confidence"],
                "confidence_band": record["confidence_band"],
                "justification": justification.get("justification"),
                "key_attributes": justification.get("key_attributes", []),
                "amendments": record["amendments"],
                "latest_version": _latest_version(record),
                "certification": _certification(record),
                "allied_standards": _allied(record["is_number"], query),
                "scope_excerpt": (record["scope"] or "")[:400],
                "source_url": record["source_url"],
                "corpus_version": record["corpus_version"],
            }
        )

    total_ms = int((time.perf_counter() - started) * 1000)
    return {
        "query": query,
        "language": language,
        "state": "ok",
        "recommendations": recommendations,
        "caveat": reasoning_output.get("caveat"),
        "timing_ms": {"retrieval": retrieval_ms, "total": total_ms},
    }


def _latest_version(record: dict) -> str:
    """Human-readable currency string for FR-401."""
    base = f"{record['is_number']}"
    if record.get("year"):
        base += f":{record['year']}"
    amendments = record.get("amendments") or []
    if amendments:
        latest = amendments[-1]
        base += f" (Amendment {latest.get('number')}"
        if latest.get("date"):
            base += f", {latest['date']}"
        base += ")"
    return base


def validate_spec(spec_text: str) -> dict:
    """
    FR-404 -- scan an existing specification for citation problems.

    This is the lowest-friction entry point in the product: it asks nothing of
    the user except a document they already have, and it surfaces exactly the
    failure the problem statement names (outdated versions, withdrawn
    standards) without requiring them to formulate a query at all.
    """
    cited = extract_all_is_references(spec_text)
    if not cited:
        return {"cited": [], "issues": [], "message": "No IS references found in this text."}

    issues, verified = [], []
    for is_number in cited:
        record = postgres.get_standard(is_number)
        if not record:
            issues.append(
                {
                    "is_number": is_number,
                    "severity": "info",
                    "issue": "Not found in the current corpus",
                    "action": "Verify this designation on the BIS portal.",
                }
            )
            continue

        entry = {
            "is_number": is_number,
            "title": record.get("title"),
            "status": record.get("status"),
            "year": record.get("year"),
        }
        verified.append(entry)

        if record.get("status") in ("withdrawn", "superseded"):
            issues.append(
                {
                    "is_number": is_number,
                    "severity": "high",
                    "issue": f"This standard is {record['status']}",
                    "action": (
                        f"Replace with {record['superseded_by']}"
                        if record.get("superseded_by")
                        else "Check the BIS portal for the current successor."
                    ),
                }
            )
        elif record.get("status") == "under_revision":
            issues.append(
                {
                    "is_number": is_number,
                    "severity": "medium",
                    "issue": "This standard is under revision",
                    "action": "Confirm the applicable edition before publishing the tender.",
                }
            )

        certification = record.get("certification") or {}
        if certification.get("mandatory"):
            issues.append(
                {
                    "is_number": is_number,
                    "severity": "medium",
                    "issue": f"{certification.get('scheme')} certification is mandatory",
                    "action": "State the certification requirement explicitly in the tender.",
                }
            )

    # Allied standards cited by nothing in the spec -- the omission the problem
    # statement identifies as a root cause of disputes.
    suggested = []
    for is_number in cited:
        for item in graph.allied_standards(is_number, depth=1)[:5]:
            if item["is_number"] not in cited and item["is_number"] not in {
                s["is_number"] for s in suggested
            }:
                suggested.append(
                    {
                        "is_number": item["is_number"],
                        "title": item.get("title"),
                        "role": ROLE_LABELS.get(item.get("ref_type"), "Related"),
                        "referenced_by": is_number,
                    }
                )

    severity_order = {"high": 0, "medium": 1, "info": 2}
    issues.sort(key=lambda i: severity_order.get(i["severity"], 3))

    return {
        "cited": verified,
        "issues": issues,
        "suggested_additions": suggested[:15],
        "summary": {
            "total_cited": len(cited),
            "high_severity": sum(1 for i in issues if i["severity"] == "high"),
            "suggestions": len(suggested),
        },
    }
