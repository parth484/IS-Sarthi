"""
Structured extraction from IS standard PDFs.

IS documents follow a rigid house style -- Foreword, 1 Scope, 2 References,
3 Terminology -- which makes section-boundary regexes far more reliable here
than they would be on arbitrary documents. Scope is the highest-value field:
it is what gets embedded, so extraction quality here sets the ceiling on
retrieval quality for the whole system.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pipeline.utils.normalize import (
    extract_all_is_references,
    split_number_and_year,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedStandard:
    file: str
    is_number: Optional[str] = None
    year: Optional[int] = None
    title: Optional[str] = None
    scope: Optional[str] = None
    normative_references: list[str] = field(default_factory=list)
    supersedes: Optional[str] = None
    amendments: list[dict] = field(default_factory=list)
    division: Optional[str] = None
    extraction_quality: float = 0.0

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "is_number": self.is_number,
            "year": self.year,
            "title": self.title,
            "scope": self.scope,
            "normative_references": self.normative_references,
            "supersedes": self.supersedes,
            "amendments": self.amendments,
            "division": self.division,
            "extraction_quality": self.extraction_quality,
        }


class ISPDFExtractor:
    SECTION_SCOPE = re.compile(
        r"(?:^|\n)\s*1[\.\s]+SCOPE\s*\n(?P<body>.*?)"
        r"(?=\n\s*2[\.\s]+|\n\s*NORMATIVE|\n\s*REFERENCES)",
        re.DOTALL | re.IGNORECASE,
    )
    SECTION_REFS = re.compile(
        r"(?:^|\n)\s*(?:2[\.\s]+)?(?:NORMATIVE\s+)?REFERENCES?\s*\n(?P<body>.*?)"
        r"(?=\n\s*3[\.\s]+|\n\s*TERMINOLOGY|\n\s*DEFINITIONS)",
        re.DOTALL | re.IGNORECASE,
    )
    SUPERSEDES = re.compile(
        r"supersed(?:es|ing)\s+(IS\s*:?\s*\d+[^\n\.]{0,60})", re.IGNORECASE
    )
    AMENDMENT = re.compile(
        r"Amendment\s*(?:No\.?)?\s*(\d+)\s*[:\-–]?\s*"
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)?\s*(?:19|20)\d{2})?",
        re.IGNORECASE,
    )
    DIVISION = re.compile(r"\b([A-Z]{2,4})\s*\d{1,2}\b")

    def extract(self, pdf_path: str | Path) -> ExtractedStandard:
        import pdfplumber

        path = Path(pdf_path)
        result = ExtractedStandard(file=str(path))

        try:
            with pdfplumber.open(path) as pdf:
                # The header block and the references section are what matter;
                # reading every page of a 200-page standard wastes time for no
                # gain, so cap it.
                pages = pdf.pages[:25]
                text = "\n".join((page.extract_text() or "") for page in pages)
        except Exception as exc:
            logger.error("Failed to open %s: %s", path, exc)
            return result

        text = self._clean(text)

        result.is_number, result.year = split_number_and_year(text[:1500])
        result.title = self._title(text)
        result.scope = self._scope(text)
        result.normative_references = self._references(text, result.is_number)
        result.supersedes = self._supersedes(text)
        result.amendments = self._amendments(text)
        result.extraction_quality = self._score(result)
        return result

    # --- field extractors ---------------------------------------------------

    @staticmethod
    def _clean(text: str) -> str:
        # Strip running headers/footers and lone page numbers, which otherwise
        # end up embedded in the middle of scope text.
        text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)
        text = re.sub(r"\n\s*(?:Bureau of Indian Standards|IS\s*\d+\s*:\s*\d{4})\s*\n", "\n", text)
        return text

    @staticmethod
    def _title(text: str) -> Optional[str]:
        # Title sits immediately after the IS designator in the header block,
        # conventionally in title case across one or two lines.
        match = re.search(
            r"IS\s*:?\s*\d+[^\n]{0,40}\n+\s*(?P<title>[A-Z][^\n]{10,160})", text[:2000]
        )
        if match:
            return re.sub(r"\s+", " ", match.group("title")).strip(" -—")
        return None

    def _scope(self, text: str) -> Optional[str]:
        match = self.SECTION_SCOPE.search(text)
        if not match:
            return None
        body = re.sub(r"\s+", " ", match.group("body")).strip()
        return body[:3000] if len(body) > 30 else None

    def _references(self, text: str, self_number: Optional[str]) -> list[str]:
        match = self.SECTION_REFS.search(text)
        source = match.group("body") if match else text
        refs = extract_all_is_references(source)
        # A standard citing itself is an artefact of header text bleeding into
        # the section; it would create a self-loop in the graph.
        return [r for r in refs if r != self_number]

    def _supersedes(self, text: str) -> Optional[str]:
        match = self.SUPERSEDES.search(text)
        if not match:
            return None
        from pipeline.utils.normalize import normalize_is_number

        return normalize_is_number(match.group(1))

    def _amendments(self, text: str) -> list[dict]:
        seen: dict[str, dict] = {}
        for match in self.AMENDMENT.finditer(text):
            number = match.group(1)
            if number not in seen:
                seen[number] = {
                    "number": number,
                    "date": (match.group(2) or "").strip() or None,
                }
        return list(seen.values())

    @staticmethod
    def _score(result: ExtractedStandard) -> float:
        """
        Extraction confidence, surfaced in the admin view.

        Records scoring low are flagged for manual review rather than silently
        entering the corpus, because a standard with a mangled scope will
        retrieve badly and there is no way to detect that from the query side.
        """
        weights = {
            "is_number": 0.30,
            "title": 0.25,
            "scope": 0.30,
            "normative_references": 0.15,
        }
        score = 0.0
        if result.is_number:
            score += weights["is_number"]
        if result.title and len(result.title) > 10:
            score += weights["title"]
        if result.scope and len(result.scope) > 100:
            score += weights["scope"]
        elif result.scope:
            score += weights["scope"] * 0.5
        if result.normative_references:
            score += weights["normative_references"]
        return round(score, 3)


def batch_extract(directory: str | Path) -> list[dict]:
    extractor = ISPDFExtractor()
    results: list[dict] = []
    for pdf_file in sorted(Path(directory).glob("*.pdf")):
        extracted = extractor.extract(pdf_file)
        results.append(extracted.as_dict())
        logger.info(
            "%s -> %s (quality %.2f, %d refs)",
            pdf_file.name,
            extracted.is_number,
            extracted.extraction_quality,
            len(extracted.normative_references),
        )
    return results
