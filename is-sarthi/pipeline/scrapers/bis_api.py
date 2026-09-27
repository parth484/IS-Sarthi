"""
Official BIS Know Your Standard backend API client.

Connects to the verified official Bureau of Indian Standards endpoints:
- searchKnowStandards (review-service): keyword and standard number search
- getWebsiteDepartments (sdo-service): technical departments directory
- getWebsitePSTechDepartmentWise (review-service): paginated published standards catalogue

Includes polite rate limiting, bounded retries with exponential backoff,
robust error handling, typed exceptions, and safe logging.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_BIS_ENDPOINT = (
    "https://standardsadmin.bis.gov.in/review-service//searchKnowStandards"
)
DEFAULT_DEPARTMENTS_ENDPOINT = (
    "https://standardsmodule.bis.gov.in/sdo-service/getWebsiteDepartments"
)
DEFAULT_CATALOGUE_ENDPOINT = (
    "https://standardsadmin.bis.gov.in/review-service/getWebsitePSTechDepartmentWise"
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BISError(Exception):
    """Base exception for BIS scraper/client errors."""


class BISRequestError(BISError):
    """Raised on network failure, HTTP status error, or request timeout."""


class BISAPIError(BISError):
    """Raised when the BIS API returns non-success or malformed JSON."""


@dataclass
class BISSearchResult:
    """Structured result returned by the BIS API search endpoint."""

    status: str
    status_code: int
    msg: str
    total_records: int
    records: list[dict[str, Any]]
    search_text: str


@dataclass
class BISCatalogueResult:
    """Structured result returned by the BIS paginated catalogue endpoint."""

    status: str
    status_code: int
    msg: str
    total_records: int
    records: list[dict[str, Any]]
    offset: int
    limit: int
    department: Optional[str] = None


class BISApiClient:
    """
    Polite, safe API client for official BIS endpoints.

    Ensures rate limits are strictly enforced between requests and logs
    only safe operational metadata without exposing request headers or credentials.
    Supports bounded retries with exponential backoff for transient network issues.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_BIS_ENDPOINT,
        departments_endpoint: str = DEFAULT_DEPARTMENTS_ENDPOINT,
        catalogue_endpoint: str = DEFAULT_CATALOGUE_ENDPOINT,
        timeout: int = 30,
        rate_limit_delay: float = 1.5,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        session: Optional[requests.Session] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.endpoint = endpoint
        self.departments_endpoint = departments_endpoint
        self.catalogue_endpoint = catalogue_endpoint
        self.timeout = timeout
        self.rate_limit_delay = max(0.0, rate_limit_delay)
        self.max_retries = max(1, max_retries)
        self.retry_backoff = max(1.0, retry_backoff)
        self.session = session or requests.Session()
        self.headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://standards.bis.gov.in",
            "Referer": "https://standards.bis.gov.in/",
        }
        self._last_request_time: float = 0.0

    def _wait_for_rate_limit(self) -> None:
        """Enforce configured delay between sequential API requests."""
        if self.rate_limit_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if self._last_request_time > 0 and elapsed < self.rate_limit_delay:
            sleep_sec = self.rate_limit_delay - elapsed
            logger.debug("Rate-limiting: sleeping for %.2f seconds", sleep_sec)
            time.sleep(sleep_sec)

    def _post_with_retries(
        self,
        url: str,
        payload: dict[str, Any],
        description: str = "request",
    ) -> requests.Response:
        """
        Execute POST request with rate limiting and bounded exponential backoff retries.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                self._last_request_time = time.monotonic()

                # Success
                if response.status_code == 200:
                    return response

                # Retryable HTTP status codes (rate limit 429, gateway/server 500/502/503/504)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    backoff = self.retry_backoff ** (attempt - 1)
                    logger.warning(
                        "Transient HTTP %d on %s (attempt %d/%d). Retrying in %.1fs...",
                        response.status_code,
                        description,
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue

                raise BISRequestError(
                    f"BIS API HTTP error: status code {response.status_code} for {description}"
                )

            except requests.exceptions.Timeout as exc:
                last_error = exc
                self._last_request_time = time.monotonic()
                if attempt < self.max_retries:
                    backoff = self.retry_backoff ** (attempt - 1)
                    logger.warning(
                        "Timeout on %s (attempt %d/%d). Retrying in %.1fs...",
                        description,
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise BISRequestError(
                    f"Request timed out after {self.timeout}s for {description} (after {self.max_retries} attempts)"
                ) from exc

            except requests.exceptions.RequestException as exc:
                last_error = exc
                self._last_request_time = time.monotonic()
                if attempt < self.max_retries:
                    backoff = self.retry_backoff ** (attempt - 1)
                    logger.warning(
                        "Network error on %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        description,
                        attempt,
                        self.max_retries,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise BISRequestError(
                    f"Network error querying BIS endpoint for {description}: {exc}"
                ) from exc

        raise BISRequestError(f"Request failed for {description}: {last_error}")

    def search(self, search_text: str) -> BISSearchResult:
        """
        Query the BIS Know Your Standard API with a search query.

        Args:
            search_text: Keyword or standard identifier to search for.

        Returns:
            BISSearchResult containing parsed metadata and list of records.

        Raises:
            BISRequestError: If network error or non-200 HTTP code.
            BISAPIError: If invalid JSON or API status is not SUCCESS.
        """
        if not search_text or not isinstance(search_text, str):
            raise ValueError("search_text must be a non-empty string.")

        clean_text = search_text.strip()
        payload = {
            "searchText": clean_text,
            "token": None,
            "refreshToken": None,
            "clientId": None,
            "clientSecret": None,
            "sub": None,
        }

        logger.info("Sending BIS search request for search_text=%r", clean_text)
        response = self._post_with_retries(
            self.endpoint,
            payload,
            description=f"search query {clean_text!r}",
        )

        try:
            data = response.json()
        except Exception as exc:
            raise BISAPIError(
                f"Failed to parse JSON response from BIS endpoint: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise BISAPIError(
                f"Expected JSON object from BIS API, got {type(data).__name__}"
            )

        api_status = data.get("status")
        if api_status != "SUCCESS":
            msg = data.get("msg") or data.get("message") or "Non-success status"
            raise BISAPIError(
                f"BIS API returned status '{api_status}': {msg} (query: {clean_text!r})"
            )

        raw_records = data.get("data")
        if raw_records is None:
            records = []
        elif isinstance(raw_records, list):
            records = raw_records
        else:
            raise BISAPIError(
                f"Unexpected type for 'data' array in BIS response: {type(raw_records).__name__}"
            )

        total_records_val = data.get("totalRecords", len(records))
        try:
            total_records = int(total_records_val)
        except (ValueError, TypeError):
            total_records = len(records)

        return BISSearchResult(
            status=str(api_status),
            status_code=response.status_code,
            msg=str(data.get("msg", "")),
            total_records=total_records,
            records=records,
            search_text=clean_text,
        )

    def get_website_departments(self) -> list[dict[str, Any]]:
        """
        Retrieve official BIS technical departments from the public sdo-service.

        Returns:
            List of department dictionaries containing:
            - departmentId: Numeric ID (e.g. 63)
            - deptName: Full name (e.g. "CIVIL ENGINEERING DEPARTMENT")
            - deptAliasName: Short code (e.g. "CED")
            - preparedName: Formatted name (e.g. "CIVIL ENGINEERING DEPARTMENT (CED)")
            - encryptedDepartmentId: Cipher token required for department-filtered queries

        Raises:
            BISRequestError: On network or HTTP error.
            BISAPIError: If response is malformed or non-SUCCESS.
        """
        logger.info("Fetching official BIS technical departments")
        response = self._post_with_retries(
            self.departments_endpoint,
            {},
            description="departments list",
        )

        try:
            data = response.json()
        except Exception as exc:
            raise BISAPIError(
                f"Failed to parse JSON response from BIS departments endpoint: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise BISAPIError(
                f"Expected JSON object from BIS departments, got {type(data).__name__}"
            )

        api_status = data.get("status")
        if api_status != "SUCCESS":
            msg = data.get("msg") or data.get("message") or "Non-success status"
            raise BISAPIError(f"BIS departments returned status '{api_status}': {msg}")

        depts = data.get("data")
        if depts is None:
            return []
        if not isinstance(depts, list):
            raise BISAPIError(
                f"Expected list in departments data, got {type(depts).__name__}"
            )

        return depts

    def get_website_ps_tech_department_wise(
        self,
        offset: int = 0,
        limit: int = 100,
        enc_department_id: Optional[str] = None,
        all_departments: bool = False,
    ) -> BISCatalogueResult:
        """
        Retrieve published standards from the official paginated catalogue endpoint.

        Supports true offset and limit pagination without the 500-record query ceiling.

        Args:
            offset: Record offset (0-indexed).
            limit: Maximum records to return in this page (e.g. 100).
            enc_department_id: Encrypted department token (from get_website_departments).
            all_departments: Set True to page across all 17 departments globally.

        Returns:
            BISCatalogueResult with parsed standards, total count, offset, and limit.

        Raises:
            BISRequestError: On network or HTTP error.
            BISAPIError: If response is malformed or non-SUCCESS.
        """
        if offset < 0:
            raise ValueError("offset must be non-negative.")
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        if enc_department_id:
            payload: dict[str, Any] = {
                "encDepartmentId": enc_department_id,
                "typeSelected": 1,
                "offset": offset,
                "limit": limit,
                "techCommitteeId": 0,
            }
        else:
            payload = {
                "allDepartments": True,
                "totalRow": 1,
                "offset": offset,
                "limit": limit,
                "techCommitteeId": 0,
            }

        logger.info(
            "Querying BIS catalogue: offset=%d, limit=%d, dept_filter=%s",
            offset,
            limit,
            bool(enc_department_id),
        )
        response = self._post_with_retries(
            self.catalogue_endpoint,
            payload,
            description=f"catalogue (offset={offset}, limit={limit})",
        )

        try:
            data = response.json()
        except Exception as exc:
            raise BISAPIError(
                f"Failed to parse JSON response from BIS catalogue endpoint: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise BISAPIError(
                f"Expected JSON object from BIS catalogue, got {type(data).__name__}"
            )

        api_status = data.get("status")
        if api_status != "SUCCESS":
            msg = data.get("msg") or data.get("message") or "Non-success status"
            raise BISAPIError(f"BIS catalogue returned status '{api_status}': {msg}")

        raw_records = data.get("data")
        if raw_records is None:
            records = []
        elif isinstance(raw_records, list):
            records = raw_records
        else:
            raise BISAPIError(
                f"Unexpected type for 'data' in BIS catalogue response: {type(raw_records).__name__}"
            )

        total_records_val = data.get("totalRecord", len(records))
        try:
            total_records = int(total_records_val)
        except (ValueError, TypeError):
            total_records = len(records)

        return BISCatalogueResult(
            status=str(api_status),
            status_code=response.status_code,
            msg=str(data.get("msg", "")),
            total_records=total_records,
            records=records,
            offset=offset,
            limit=limit,
        )
