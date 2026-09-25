"""
Procurement Service.
Coordinates tender extraction, normalization, and invocation of the IS Sarthi
recommendation and compliance validation engine.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pipeline.procurement.connector import (
    BaseProcurementConnector,
    GeMProcurementConnector,
    GenericProcurementConnector,
    SAMPLE_GEM_TENDERS,
)
from pipeline.procurement.models import NormalizedTender

logger = logging.getLogger(__name__)


class ProcurementService:
    """Service orchestrating procurement ingestion and BIS recommendation."""

    def __init__(self, corpus_instance: Any = None):
        self.corpus = corpus_instance
        self.connectors: dict[str, BaseProcurementConnector] = {
            "gem": GeMProcurementConnector(),
            "generic": GenericProcurementConnector(),
        }

    def set_corpus(self, corpus_instance: Any) -> None:
        self.corpus = corpus_instance

    def get_sample_tenders(self) -> list[dict[str, Any]]:
        """Return list of sample verified public procurement tenders for testing."""
        return list(SAMPLE_GEM_TENDERS.values())

    def ingest_and_recommend(
        self,
        tender_input: dict[str, Any] | str,
        connector_type: str = "gem",
        top_k: int = 5,
        division: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Ingest a procurement tender, normalize specification, and pass into the
        existing recommendation engine.
        """
        connector = self.connectors.get(connector_type.lower()) or self.connectors["gem"]

        # Fetch or wrap raw tender payload
        if isinstance(tender_input, str):
            raw_data = connector.fetch_tender(tender_input)
        else:
            raw_data = tender_input

        # Parse into internal tender specification
        spec = connector.parse_specification(raw_data)

        # Normalize into technical retrieval query
        normalized: NormalizedTender = connector.normalize(spec)

        # Pass through existing recommendation engine
        if self.corpus is None:
            raise RuntimeError("Recommendation corpus is not loaded in ProcurementService.")

        recommendation_result = self.corpus.recommend(normalized.normalized_query, top_k=top_k)

        # Run specification validation on any cited standards in the tender
        validation_result = None
        if normalized.cited_standards:
            validation_result = self.corpus.validate(normalized.raw_specification or normalized.normalized_query)

        return {
            "tender": normalized.as_dict(),
            "recommendations": recommendation_result.get("recommendations", []),
            "state": recommendation_result.get("state", "ok"),
            "query_used": normalized.normalized_query,
            "validation": validation_result,
        }
