"""
Processing chain. Each link is an independently retryable Celery task, so a
transient Neo4j blip re-runs one step rather than the whole crawl.

Chain:
  clean_and_validate -> classify_references -> update_graph
                     -> regenerate_embedding -> update_postgres
"""
from __future__ import annotations

import logging
from typing import Optional

from pipeline.celery_app import app
from pipeline.change_detector import ChangeResult, ChangeType, detector
from pipeline.classify import classify_all
from pipeline.db.stores import graph, postgres, vectors
from pipeline.utils.normalize import normalize_is_number

logger = logging.getLogger(__name__)

_embedder = None


def get_embedder():
    """Lazily loaded and process-global -- the model is ~450MB and reloading it
    per task would dominate runtime."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        from pipeline.config import settings

        _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


def build_embedding_text(record: dict) -> str:
    """
    Title alone is too terse to discriminate between sibling standards; scope
    alone often omits the product name entirely. Combining them is what makes
    a query phrased in procurement language reach a standard written in
    committee language.

    The "passage:" prefix is required by the e5 model family, which is trained
    asymmetrically -- queries get "query:", documents get "passage:". Omitting
    it measurably degrades retrieval.
    """
    title = (record.get("title") or "").strip()
    scope = (record.get("scope") or "").strip()
    return f"passage: {title}. {scope}".strip()


# ------------------------------------------------------------------ tasks

@app.task(bind=True, max_retries=2, name="pipeline.tasks.process.clean_and_validate")
def clean_and_validate(self, record: dict) -> Optional[dict]:
    """Canonicalize identifiers and drop records that cannot be keyed."""
    try:
        canonical = normalize_is_number(record.get("is_number"))
        if not canonical:
            logger.warning("Dropping record with unparseable IS number: %r",
                           record.get("is_number"))
            return None
        record["is_number"] = canonical

        refs = []
        for ref in record.get("normative_references", []):
            key = normalize_is_number(ref if isinstance(ref, str) else ref.get("is_number"))
            if key and key != canonical and key not in refs:
                refs.append(key)
        record["normative_references"] = refs

        if record.get("supersedes"):
            record["supersedes"] = normalize_is_number(record["supersedes"])

        record.setdefault("status", "current")
        record.setdefault("sources", [])
        return record
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@app.task(name="pipeline.tasks.process.classify_references")
def classify_references(record: Optional[dict]) -> Optional[dict]:
    if not record:
        return None

    # Pull titles for referenced standards already in the corpus, so
    # classification has evidence even for references not yet crawled.
    title_lookup: dict[str, str] = {}
    for ref in record.get("normative_references", []):
        stored = postgres.get_standard(ref)
        if stored and stored.get("title"):
            title_lookup[ref] = stored["title"]

    record["classified_references"] = classify_all(
        record.get("normative_references", []), title_lookup=title_lookup
    )
    return record


@app.task(bind=True, max_retries=3, name="pipeline.tasks.process.update_graph")
def update_graph(self, record: Optional[dict]) -> Optional[dict]:
    if not record:
        return None
    try:
        graph.upsert_standard(record, record.get("classified_references", []))
        return record
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@app.task(bind=True, max_retries=2, name="pipeline.tasks.process.regenerate_embedding")
def regenerate_embedding(self, record: Optional[dict],
                         force: bool = False) -> Optional[dict]:
    """Re-embed only when the scope text actually moved -- this is the
    expensive step and gating it is most of why daily syncs are affordable."""
    if not record:
        return None

    if not record.get("scope") and not record.get("title"):
        return record

    try:
        text = build_embedding_text(record)
        embedding = get_embedder().encode(text, normalize_embeddings=True).tolist()

        certification = record.get("certification") or {}
        vectors.upsert(
            is_number=record["is_number"],
            embedding=embedding,
            text=text,
            metadata={
                "is_number": record["is_number"],
                "title": record.get("title") or "",
                "year": record.get("year") or 0,
                "status": record.get("status", "current"),
                "division": record.get("division") or "",
                "certification_scheme": certification.get("scheme", "none"),
            },
        )
        return record
    except Exception as exc:
        raise self.retry(exc=exc, countdown=45)


@app.task(bind=True, max_retries=3, name="pipeline.tasks.process.update_postgres")
def update_postgres(self, record: Optional[dict],
                    change_payload: Optional[dict] = None) -> Optional[dict]:
    if not record:
        return None
    try:
        change = ChangeResult(
            change_type=ChangeType(change_payload["change_type"])
            if change_payload else ChangeType.NEW,
            content_hash=change_payload["content_hash"] if change_payload
            else detector.content_hash(record),
            scope_hash=change_payload["scope_hash"] if change_payload
            else detector.scope_hash(record),
            changed_fields=change_payload.get("changed_fields", []) if change_payload else ["*"],
        )
        postgres.upsert_standard(record, change)
        logger.info("Stored %s (%s)", record["is_number"], change.change_type.value)
        return record
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@app.task(name="pipeline.tasks.process.process_record")
def process_record(record: dict, change_payload: Optional[dict] = None) -> Optional[dict]:
    """
    Synchronous end-to-end processing of one record.

    Used by the bootstrap script and by tests, where the Celery chain's
    asynchrony adds complexity without benefit. Production crawls use the
    chained form so each step retries independently.
    """
    record = clean_and_validate.run(record)
    if not record:
        return None
    record = classify_references.run(record)
    update_graph.run(record)

    needs_embed = (
        change_payload is None
        or change_payload.get("change_type") in (ChangeType.NEW.value, ChangeType.SCOPE.value)
    )
    if needs_embed:
        regenerate_embedding.run(record)

    return update_postgres.run(record, change_payload)
