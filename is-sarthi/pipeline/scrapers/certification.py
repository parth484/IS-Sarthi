"""
Certification-regime extraction: CRS product list and e-Gazette notifications.

This is the component that most directly addresses a gap nothing in the current
workflow covers. Whether a product requires ISI marking, CRS registration or
Hallmarking is set by Quality Control Orders gazetted independently of the
standards themselves. An official searching the standards portal will never see
them. Linking the two is a substantial part of IS Sarthi's value.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.scrapers.base import BaseScraper
from pipeline.utils.http import client
from pipeline.utils.normalize import extract_all_is_references

logger = logging.getLogger(__name__)

HALLMARKING_IS_NUMBERS = {
    # Hallmarking of precious metals is governed by a small, stable set.
    "IS 1417": "Gold and gold alloys, jewellery/artefacts -- fineness and marking",
    "IS 1418": "Assaying of gold in gold bullion, jewellery and artefacts",
    "IS 2112": "Hallmarking of gold jewellery and artefacts",
    "IS 15766": "Hallmarking of silver jewellery and artefacts",
}


class CRSScraper(BaseScraper):
    """
    Extracts the Compulsory Registration Scheme product list.

    The list is published as a spreadsheet whose filename changes on every
    revision, so the download URL is discovered from the landing page rather
    than hardcoded -- a hardcoded URL is the single most common reason this
    kind of ingestion silently rots.
    """

    source_name = "crs"

    def __init__(self):
        super().__init__()
        self.cfg = self.selectors["crs"]
        self.base = self.cfg["base_url"]

    def discover_list_url(self) -> Optional[str]:
        landing = urljoin(self.base, self.cfg["landing_path"])
        response = client.get(landing)
        if response is None:
            return None

        self.stats.pages_fetched += 1
        soup = BeautifulSoup(response.text, "lxml")
        pattern = re.compile(self.cfg["file_link_pattern"], re.IGNORECASE)
        hints = [h.lower() for h in self.cfg["link_text_hints"]]

        for link in soup.find_all("a", href=True):
            href = link["href"]
            label = link.get_text(" ", strip=True).lower()
            if pattern.search(href) and any(hint in label or hint in href.lower() for hint in hints):
                return urljoin(self.base, href)

        self.stats.miss("crs.file_link")
        return None

    def fetch(self) -> dict[str, dict]:
        """Return {is_number: certification_record}."""
        url = self.discover_list_url()
        if not url:
            logger.warning("CRS list URL not discoverable; skipping this run")
            return {}

        response = client.get(url, snapshot=False)
        if response is None:
            return {}

        if url.lower().endswith(".pdf"):
            rows = self._parse_pdf(response.content)
        else:
            rows = self._parse_spreadsheet(response.content)

        lookup: dict[str, dict] = {}
        for product_name, standard_text in rows:
            for is_number in extract_all_is_references(standard_text):
                lookup[is_number] = {
                    "scheme": "CRS",
                    "scheme_label": "BIS Compulsory Registration Scheme",
                    "product": product_name,
                    "mandatory": True,
                    "source_url": url,
                }

        self.stats.records_found = len(lookup)
        return lookup

    @staticmethod
    def _parse_spreadsheet(content: bytes) -> list[tuple[str, str]]:
        import pandas as pd

        frame = pd.read_excel(io.BytesIO(content))
        frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]

        product_col = next(
            (c for c in frame.columns if "product" in c or "item" in c), frame.columns[0]
        )
        standard_col = next(
            (c for c in frame.columns if "standard" in c or "is_no" in c or "indian" in c),
            frame.columns[-1],
        )
        return [
            (str(row[product_col]), str(row[standard_col]))
            for _, row in frame.iterrows()
        ]

    @staticmethod
    def _parse_pdf(content: bytes) -> list[tuple[str, str]]:
        import pdfplumber

        rows: list[tuple[str, str]] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    for row in table:
                        cells = [c or "" for c in row]
                        joined = " ".join(cells)
                        if "IS" in joined:
                            rows.append((cells[1] if len(cells) > 1 else "", joined))
        return rows


class GazetteScraper(BaseScraper):
    """
    Monitors e-Gazette for Quality Control Orders affecting the certification
    regime. A QCO is what converts a voluntary standard into a mandatory one,
    so this feed is the difference between a system that is current on
    compliance and one that is a year behind.
    """

    source_name = "gazette"

    def __init__(self):
        super().__init__()
        self.cfg = self.selectors["gazette"]
        self.base = self.cfg["base_url"]

    def recent_notifications(self) -> list[dict]:
        url = urljoin(self.base, self.cfg["search_path"])
        response = client.get(url, params={"Ministry": self.cfg["ministry_filter"]})
        if response is None:
            return []

        self.stats.pages_fetched += 1
        soup = BeautifulSoup(response.text, "lxml")
        rows = self.select_all(soup, self.cfg["notification_row"], "notification_row")
        hints = [h.lower() for h in self.cfg["keyword_hints"]]

        notifications: list[dict] = []
        for row in rows:
            text = row.get_text(" ", strip=True)
            if not any(hint in text.lower() for hint in hints):
                continue
            link = row.find("a", href=True)
            notifications.append(
                {
                    "title": text[:300],
                    "url": urljoin(self.base, link["href"]) if link else None,
                    "is_references": extract_all_is_references(text),
                }
            )

        self.stats.records_found = len(notifications)
        return notifications

    def parse_notification(self, url: str) -> dict:
        """Pull IS references and effective date out of a gazette PDF."""
        response = client.get(url, snapshot=False)
        if response is None:
            return {}

        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages[:10])
        except Exception as exc:
            logger.warning("Could not parse gazette PDF %s: %s", url, exc)
            return {}

        effective = re.search(
            r"come into force on(?: the)?\s+(.{0,40}?\d{4})", text, re.IGNORECASE
        )
        scheme = "BIS Product Certification (ISI)"
        if re.search(r"compulsory registration", text, re.IGNORECASE):
            scheme = "CRS"
        elif re.search(r"hallmark", text, re.IGNORECASE):
            scheme = "Hallmarking"

        return {
            "url": url,
            "is_references": extract_all_is_references(text),
            "effective_date": effective.group(1).strip() if effective else None,
            "scheme": scheme,
        }
