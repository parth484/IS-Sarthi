"""
Polite HTTP client for public-source extraction.

BIS is a public body running modest infrastructure. Crawling it aggressively is
both discourteous and self-defeating -- it is the fastest way to get blocked and
lose the data source entirely. Every request therefore passes through a token
bucket, honours robots.txt, backs off exponentially with jitter, and trips a
circuit breaker rather than retrying into a wall.
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
import urllib.robotparser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from pipeline.config import settings

logger = logging.getLogger(__name__)


class TokenBucket:
    """Thread-safe rate limiter, one bucket per host."""

    def __init__(self, rate_per_second: float, capacity: float = 3.0):
        self.rate = rate_per_second
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self.capacity, self._tokens + (now - self._last) * self.rate
            )
            self._last = now
            if self._tokens < 1:
                sleep_for = (1 - self._tokens) / self.rate
                time.sleep(sleep_for)
                self._tokens = 0
                self._last = time.monotonic()
            else:
                self._tokens -= 1


class CircuitBreaker:
    """Disable a source after repeated failures instead of hammering it."""

    def __init__(self, threshold: int):
        self.threshold = threshold
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_success(self, host: str) -> None:
        with self._lock:
            self._failures[host] = 0

    def record_failure(self, host: str) -> None:
        with self._lock:
            self._failures[host] = self._failures.get(host, 0) + 1

    def is_open(self, host: str) -> bool:
        return self._failures.get(host, 0) >= self.threshold


class PoliteClient:
    def __init__(self, delay: Optional[float] = None):
        self.delay = delay or settings.crawl_delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )
        self._buckets: dict[str, TokenBucket] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._breaker = CircuitBreaker(settings.circuit_breaker_threshold)
        self._lock = threading.Lock()

    # --- politeness helpers -------------------------------------------------

    def _bucket(self, host: str) -> TokenBucket:
        with self._lock:
            if host not in self._buckets:
                self._buckets[host] = TokenBucket(rate_per_second=1.0 / self.delay)
            return self._buckets[host]

    def _robots_allow(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(f"{urlparse(url).scheme}://{host}/robots.txt")
            try:
                parser.read()
            except Exception:
                # A missing or unreadable robots.txt is not permission to ignore
                # it, but it is also not a prohibition. Default to allowing and
                # rely on the rate limiter to stay courteous.
                logger.warning("Could not read robots.txt for %s", host)
            self._robots[host] = parser
        try:
            return self._robots[host].can_fetch(settings.user_agent, url)
        except Exception:
            return True

    # --- snapshotting -------------------------------------------------------

    @staticmethod
    def _snapshot(url: str, content: bytes) -> None:
        """
        Persist raw responses so a parser bug can be fixed and replayed without
        re-crawling. This is what makes selector changes cheap.
        """
        directory = Path(settings.raw_snapshot_dir)
        directory.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(url.encode()).hexdigest()[:20]
        (directory / f"{name}.html").write_bytes(content)

    # --- main entry point ---------------------------------------------------

    def get(
        self,
        url: str,
        params: Optional[dict] = None,
        snapshot: bool = True,
        **kwargs,
    ) -> Optional[requests.Response]:
        host = urlparse(url).netloc

        if self._breaker.is_open(host):
            logger.error("Circuit breaker open for %s -- skipping %s", host, url)
            return None

        if not self._robots_allow(url):
            logger.warning("robots.txt disallows %s -- skipping", url)
            return None

        self._bucket(host).acquire()

        for attempt in range(settings.max_retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=settings.request_timeout,
                    **kwargs,
                )
                if response.status_code in (429, 503):
                    # Honour Retry-After when the server supplies it.
                    wait = float(response.headers.get("Retry-After", 2**attempt))
                    wait += random.uniform(0, 1)
                    logger.warning("Throttled by %s, waiting %.1fs", host, wait)
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                self._breaker.record_success(host)
                if snapshot:
                    self._snapshot(url, response.content)
                return response

            except requests.RequestException as exc:
                wait = (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "Request failed (%s/%s) for %s: %s",
                    attempt + 1,
                    settings.max_retries,
                    url,
                    exc,
                )
                if attempt < settings.max_retries - 1:
                    time.sleep(wait)

        self._breaker.record_failure(host)
        return None

    def post(self, url: str, data: Optional[dict] = None, **kwargs):
        host = urlparse(url).netloc
        if self._breaker.is_open(host):
            return None
        self._bucket(host).acquire()
        try:
            response = self.session.post(
                url, data=data, timeout=settings.request_timeout, **kwargs
            )
            response.raise_for_status()
            self._breaker.record_success(host)
            return response
        except requests.RequestException as exc:
            logger.warning("POST failed for %s: %s", url, exc)
            self._breaker.record_failure(host)
            return None


client = PoliteClient()
