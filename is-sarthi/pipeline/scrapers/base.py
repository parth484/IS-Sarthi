"""Shared scraper machinery: selector loading with fallbacks, extraction stats."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

_SELECTOR_FILE = Path(__file__).parent / "selectors.yaml"


def load_selectors() -> dict[str, Any]:
    with open(_SELECTOR_FILE) as handle:
        return yaml.safe_load(handle)


@dataclass
class ExtractionStats:
    """
    Per-run extraction telemetry.

    The important field is `selector_misses`. A scraper that silently returns
    zero rows because the DOM changed looks identical to a scraper that
    correctly found nothing new -- unless misses are counted. The hourly health
    check alerts on this, which is how selector drift gets caught in hours
    rather than at the next demo.
    """

    source: str
    pages_fetched: int = 0
    records_found: int = 0
    records_changed: int = 0
    selector_misses: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def miss(self, selector_name: str) -> None:
        self.selector_misses[selector_name] = (
            self.selector_misses.get(selector_name, 0) + 1
        )

    @property
    def healthy(self) -> bool:
        if self.pages_fetched == 0:
            return False
        return self.records_found > 0 and not self.errors

    def summary(self) -> dict:
        return {
            "source": self.source,
            "pages_fetched": self.pages_fetched,
            "records_found": self.records_found,
            "records_changed": self.records_changed,
            "selector_misses": self.selector_misses,
            "error_count": len(self.errors),
            "healthy": self.healthy,
        }


class BaseScraper:
    """Selector resolution with ordered fallbacks."""

    source_name: str = "base"

    def __init__(self):
        self.selectors = load_selectors()
        self.stats = ExtractionStats(source=self.source_name)

    def select_all(
        self, soup: BeautifulSoup | Tag, spec: Any, name: str = "unnamed"
    ) -> list[Tag]:
        """
        Try each candidate selector in order; return the first non-empty result.

        Returning the first that matches (rather than the union) keeps results
        deterministic when two layouts coexist on the same page.
        """
        candidates = self._candidates(spec)
        for selector in candidates:
            try:
                found = soup.select(selector)
            except Exception as exc:
                logger.debug("Bad selector %r: %s", selector, exc)
                continue
            if found:
                return found
        self.stats.miss(name)
        return []

    def select_one(
        self, soup: BeautifulSoup | Tag, spec: Any, name: str = "unnamed"
    ) -> Optional[Tag]:
        found = self.select_all(soup, spec, name)
        return found[0] if found else None

    @staticmethod
    def _candidates(spec: Any) -> list[str]:
        if isinstance(spec, dict):
            return spec.get("candidates", [])
        if isinstance(spec, str):
            return [spec]
        if isinstance(spec, list):
            return spec
        return []

    @staticmethod
    def text_of(node: Optional[Tag]) -> Optional[str]:
        return node.get_text(strip=True) if node else None
