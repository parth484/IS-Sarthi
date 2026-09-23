#!/usr/bin/env python3
"""
Bootstrap the corpus from the seed dataset.

Runs the full processing chain synchronously so the demo can be stood up
without Celery, Redis or a network connection. Every store degrades
gracefully, so this completes even with nothing but Python installed.

    python scripts/bootstrap.py
    python scripts/bootstrap.py --no-embed     # skip model download
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.change_detector import detector  # noqa: E402
from pipeline.classify import classify_all  # noqa: E402
from pipeline.db.stores import graph, postgres, vectors  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bootstrap")

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed" / "standards.json"


def load_seed() -> list[dict]:
    with open(SEED_PATH) as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embedding generation (no model download)")
    args = parser.parse_args()

    records = load_seed()
    logger.info("Loaded %d seed standards", len(records))

    # Title lookup is built first so reference classification has evidence for
    # every reference that points inside the seed corpus.
    title_lookup = {r["is_number"]: r.get("title", "") for r in records}

    embedder = None
    if not args.no_embed:
        try:
            from pipeline.tasks.process import build_embedding_text, get_embedder

            embedder = get_embedder()
            logger.info("Embedding model loaded")
        except Exception as exc:
            logger.warning("Embedding unavailable (%s); continuing without vectors", exc)

    stored = graphed = embedded = 0

    for record in records:
        classified = classify_all(
            record.get("normative_references", []), title_lookup=title_lookup
        )
        record["classified_references"] = classified

        change = detector.compare(record, postgres.get_standard(record["is_number"]))

        try:
            graph.upsert_standard(record, classified)
            graphed += 1
        except Exception as exc:
            logger.debug("Graph upsert failed for %s: %s", record["is_number"], exc)

        if embedder is not None:
            try:
                from pipeline.tasks.process import build_embedding_text

                text = build_embedding_text(record)
                embedding = embedder.encode(text, normalize_embeddings=True).tolist()
                certification = record.get("certification") or {}
                vectors.upsert(
                    record["is_number"],
                    embedding,
                    text,
                    {
                        "is_number": record["is_number"],
                        "title": record.get("title", ""),
                        "year": record.get("year") or 0,
                        "status": record.get("status", "current"),
                        "division": record.get("division") or "",
                        "certification_scheme": certification.get("scheme", "none"),
                    },
                )
                embedded += 1
            except Exception as exc:
                logger.debug("Embedding failed for %s: %s", record["is_number"], exc)

        try:
            postgres.upsert_standard(record, change)
            stored += 1
        except Exception as exc:
            logger.debug("Postgres upsert failed for %s: %s", record["is_number"], exc)

    logger.info(
        "Bootstrap complete -- postgres:%d graph:%d vectors:%d", stored, graphed, embedded
    )

    if embedded:
        from api.services import retrieval

        count = retrieval.build_sparse_index()
        logger.info("Sparse index built over %d documents", count)

    if not stored and not embedded:
        logger.warning(
            "No backing stores were reachable. Start them with "
            "`cd deploy && docker compose up -d`, or run the offline demo: "
            "`python scripts/demo_offline.py`"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
