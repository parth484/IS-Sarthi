"""
Data models for procurement portal specifications and normalized tenders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TenderSpecification:
    """Standard internal representation of an ingested procurement tender."""
    tender_id: str
    title: str
    portal: str = "GeM"  # GeM, CPPP, Custom
    organization: str = "Government Department / PSU"
    reference_number: str = ""
    closing_date: Optional[str] = None
    category: str = "General Procurement"
    raw_specification: str = ""
    line_items: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tender_id": self.tender_id,
            "title": self.title,
            "portal": self.portal,
            "organization": self.organization,
            "reference_number": self.reference_number,
            "closing_date": self.closing_date,
            "category": self.category,
            "raw_specification": self.raw_specification,
            "line_items": self.line_items,
            "metadata": self.metadata,
        }


@dataclass
class NormalizedTender:
    """Normalized tender specification prepared for the BIS recommendation engine."""
    tender_id: str
    title: str
    portal: str
    organization: str
    normalized_query: str
    technical_parameters: dict[str, Any] = field(default_factory=dict)
    cited_standards: list[str] = field(default_factory=list)
    raw_specification: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tender_id": self.tender_id,
            "title": self.title,
            "portal": self.portal,
            "organization": self.organization,
            "normalized_query": self.normalized_query,
            "technical_parameters": self.technical_parameters,
            "cited_standards": self.cited_standards,
            "raw_specification": self.raw_specification,
        }
