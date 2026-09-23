"""
BIS standards portal scraper.

Extracts the freely published metadata layer: standard number, title, year,
status, division, normative references and amendment history. Full clause text
is licensed and is deliberately not fetched -- the retrieval design targets
scope text precisely so that the system is useful without a BIS licence.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.scrapers.base import BaseScraper
from pipeline.utils.http import client
from pipeline.utils.normalize import (
    extract_all_is_references,
    normalize_is_number,
    split_number_and_year,
)

logger = logging.getLogger(__name__)

# The 14 BIS technical division codes. Crawling by division rather than by
# alphabetical page gives natural work partitioning and lets a partial corpus
# still be coherent -- "we have all of Electrotechnical" is a defensible
# coverage claim in a way that "we have the first 4,000 standards" is not.
BIS_DIVISIONS = {
    "CED": "Civil Engineering",
    "CHD": "Chemical",
    "ELD": "Electronics and Information Technology",
    "ETD": "Electrotechnical",
    "FAD": "Food and Agriculture",
    "LITD": "Electronics and IT",
    "MED": "Mechanical Engineering",
    "MTD": "Metallurgical Engineering",
    "PCD": "Petroleum, Coal and Related Products",
    "PGD": "Production and General Engineering",
    "SSD": "Service Sector",
    "TED": "Transport Engineering",
    "TXD": "Textile",
    "WRD": "Water Resources",
}


class BISPortalScraper(BaseScraper):
    source_name = "bis_portal"

    def __init__(self):
        super().__init__()
        self.cfg = self.selectors["bis_portal"]
        self.base = self.cfg["base_url"]

    # --- listing ------------------------------------------------------------

    def search_by_division(
        self, division: str, max_pages: int = 50
    ) -> list[dict]:
        """Page through one division's standard listing."""
        results: list[dict] = []
        for page in range(1, max_pages + 1):
            url = urljoin(self.base, self.cfg["search_path"])
            response = client.get(
                url, params={"division": division, "page": page, "per_page": 100}
            )
            if response is None:
                break

            self.stats.pages_fetched += 1
            page_rows = list(self._parse_listing(response.text, division))
            if not page_rows:
                break  # no more pages

            results.extend(page_rows)
            self.stats.records_found += len(page_rows)

        return results

    def recently_published(self) -> list[dict]:
        """
        The 'recently published' view drives the daily delta sync.

        This is what makes daily freshness affordable: instead of re-crawling
        20,000 standards to find the six that changed, ask the site which ones
        changed.
        """
        url = urljoin(self.base, self.cfg["recently_published_path"])
        response = client.get(url)
        if response is None:
            return []
        self.stats.pages_fetched += 1
        rows = list(self._parse_listing(response.text, division=None))
        self.stats.records_found += len(rows)
        return rows

    def _parse_listing(
        self, html: str, division: Optional[str]
    ) -> Iterator[dict]:
        soup = BeautifulSoup(html, "lxml")
        rows = self.select_all(soup, self.cfg["results_row"], "results_row")
        cols_cfg = self.cfg["columns"]

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(cols_cfg.values()):
                continue

            raw_number = cells[cols_cfg["is_number"]].get_text(strip=True)
            is_number, year = split_number_and_year(raw_number)
            if not is_number:
                continue

            link = cells[cols_cfg["is_number"]].find("a")
            detail_url = urljoin(self.base, link["href"]) if link and link.get("href") else None

            yield {
                "is_number": is_number,
                "raw_designation": raw_number,
                "title": cells[cols_cfg["title"]].get_text(strip=True),
                "year": year
                or self._safe_int(cells[cols_cfg["year"]].get_text(strip=True)),
                "status": self._normalize_status(
                    cells[cols_cfg["status"]].get_text(strip=True)
                ),
                "division": division,
                "source_url": detail_url,
            }

    # --- detail -------------------------------------------------------------

    def get_standard_detail(self, url: str) -> dict:
        """Fetch one standard's page: scope, normative references, amendments."""
        response = client.get(url)
        if response is None:
            return {}

        self.stats.pages_fetched += 1
        soup = BeautifulSoup(response.text, "lxml")
        detail_cfg = self.cfg["detail"]
        record: dict = {"source_url": url}

        title_node = self.select_one(soup, detail_cfg["title"], "detail.title")
        if title_node:
            record["title"] = title_node.get_text(strip=True)

        # Metadata is presented as a two-column table on most detail pages.
        meta_table = self.select_one(
            soup, detail_cfg["metadata_table"], "detail.metadata_table"
        )
        if meta_table:
            for row in meta_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) == 2:
                    key = (
                        cells[0]
                        .get_text(strip=True)
                        .lower()
                        .replace(" ", "_")
                        .rstrip(":")
                    )
                    record[f"meta_{key}"] = cells[1].get_text(strip=True)

        record["normative_references"] = self._extract_references(soup, detail_cfg)
        record["amendments"] = self._extract_amendments(soup, detail_cfg)
        record["scope"] = self._extract_scope(soup)

        return record

    def _extract_references(self, soup: BeautifulSoup, detail_cfg: dict) -> list[str]:
        section = self.select_one(
            soup, detail_cfg["normative_references"], "detail.normative_references"
        )
        if section is None:
            # Fall back to scanning the whole page. Noisier, but a missed
            # reference silently degrades the graph, which is the feature this
            # whole system is built around -- so over-collect and let the
            # classifier downweight.
            return extract_all_is_references(soup.get_text(" "))

        refs: list[str] = []
        for link in section.find_all("a"):
            key = normalize_is_number(link.get_text(strip=True))
            if key and key not in refs:
                refs.append(key)

        if not refs:
            refs = extract_all_is_references(section.get_text(" "))
        return refs

    def _extract_amendments(self, soup: BeautifulSoup, detail_cfg: dict) -> list[dict]:
        section = self.select_one(soup, detail_cfg["amendments"], "detail.amendments")
        if section is None:
            return []

        import re

        amendments: list[dict] = []
        pattern = re.compile(
            r"Amendment\s*(?:No\.?)?\s*(\d+)\s*[:\-–]?\s*"
            r"((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)?\s*(?:19|20)\d{2})?",
            re.IGNORECASE,
        )
        for match in pattern.finditer(section.get_text(" ")):
            amendments.append(
                {"number": match.group(1), "date": (match.group(2) or "").strip() or None}
            )
        return amendments

    @staticmethod
    def _extract_scope(soup: BeautifulSoup) -> Optional[str]:
        """
        Scope is section 1 of every IS standard. Where the portal exposes an
        abstract, that is used; otherwise the scope heading is located in the
        page text.
        """
        import re

        for selector in ("div.abstract", "div.scope", "div.field--name-body"):
            node = soup.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if len(text) > 40:
                    return text[:3000]

        text = soup.get_text("\n")
        match = re.search(
            r"1[\.\s]+SCOPE\s*\n(.*?)(?=\n\s*2[\.\s]|\nNORMATIVE|\nREFERENCES)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()[:3000]
        return None

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _safe_int(value: str) -> Optional[int]:
        import re

        match = re.search(r"(19|20)\d{2}", value or "")
        return int(match.group(0)) if match else None

    @staticmethod
    def _normalize_status(raw: str) -> str:
        lowered = (raw or "").lower()
        if "withdraw" in lowered:
            return "withdrawn"
        if "supersed" in lowered:
            return "superseded"
        if "revision" in lowered:
            return "under_revision"
        return "current"
