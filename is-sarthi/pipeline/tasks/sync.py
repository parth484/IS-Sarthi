"""
Sync orchestration -- the scheduled jobs that keep the corpus current.

Design intent: `full_sync` guarantees eventual completeness, `delta_sync`
guarantees daily freshness, and `check_gazette_updates` guarantees compliance
currency. All three are cheap because change detection gates the expensive
downstream work.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery import chain, group

from pipeline.celery_app import app
from pipeline.change_detector import detector
from pipeline.db.stores import postgres
from pipeline.scrapers.bis_portal import BIS_DIVISIONS, BISPortalScraper
from pipeline.scrapers.certification import CRSScraper, GazetteScraper

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, name="pipeline.tasks.sync.scrape_standard")
def scrape_standard(self, listing: dict) -> dict:
    """
    Fetch one standard's detail page, decide whether anything changed, and
    dispatch downstream work only if it did.
    """
    from pipeline.tasks.process import (
        classify_references,
        clean_and_validate,
        regenerate_embedding,
        update_graph,
        update_postgres,
    )

    is_number = listing.get("is_number")
    try:
        scraper = BISPortalScraper()
        record = dict(listing)

        if listing.get("source_url"):
            record.update(scraper.get_standard_detail(listing["source_url"]))
            record["is_number"] = is_number  # detail page must not override the key
        record.setdefault("sources", []).append("bis_portal")

        stored = postgres.get_standard(is_number)
        change = detector.compare(record, stored)

        if not change.needs_processing:
            postgres.touch_last_seen(is_number)
            return {"is_number": is_number, "status": "unchanged"}

        payload = {
            "change_type": change.change_type.value,
            "content_hash": change.content_hash,
            "scope_hash": change.scope_hash,
            "changed_fields": change.changed_fields,
        }

        # The chain is assembled conditionally: skipping the embedding link
        # entirely for a metadata-only change is what keeps the embed queue
        # from becoming the bottleneck during a full sync.
        steps = [clean_and_validate.s(record), classify_references.s()]
        if change.needs_graph_update:
            steps.append(update_graph.s())
        if change.needs_reembedding:
            steps.append(regenerate_embedding.s())
        steps.append(update_postgres.s(change_payload=payload))

        chain(*steps).apply_async()

        return {
            "is_number": is_number,
            "status": change.change_type.value,
            "fields": change.changed_fields,
        }

    except Exception as exc:
        logger.warning("scrape_standard failed for %s: %s", is_number, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)


@app.task(name="pipeline.tasks.sync.full_sync")
def full_sync(divisions: list[str] | None = None) -> dict:
    """Weekly: crawl every division. Guarantees completeness over time."""
    scraper = BISPortalScraper()
    targets = divisions or list(BIS_DIVISIONS.keys())

    queued = 0
    for index, division in enumerate(targets):
        listings = scraper.search_by_division(division)
        if not listings:
            logger.warning("No listings for division %s -- check selectors", division)
            continue

        # Stagger across the whole run rather than firing thousands of requests
        # into the rate limiter at once; this keeps queue depth predictable and
        # the crawl visibly polite.
        group(
            scrape_standard.signature((listing,), countdown=position * 2)
            for position, listing in enumerate(listings)
        ).apply_async()
        queued += len(listings)
        logger.info("Queued %d standards from %s", len(listings), division)

    postgres.record_sync_run("full", scraper.stats.summary())
    return {"queued": queued, "divisions": len(targets),
            "stats": scraper.stats.summary()}


@app.task(name="pipeline.tasks.sync.delta_sync")
def delta_sync() -> dict:
    """
    Daily: only what BIS says is recently published.

    This is the job that delivers the 24-hour freshness NFR. Asking the site
    what changed is orders of magnitude cheaper than re-deriving it.
    """
    scraper = BISPortalScraper()
    listings = scraper.recently_published()

    if listings:
        group(
            scrape_standard.signature((listing,), countdown=position * 2)
            for position, listing in enumerate(listings)
        ).apply_async()

    postgres.record_sync_run("delta", scraper.stats.summary())
    return {"queued": len(listings), "stats": scraper.stats.summary()}


@app.task(name="pipeline.tasks.sync.refresh_crs_list")
def refresh_crs_list() -> dict:
    """Weekly: re-read the CRS mandatory product list."""
    from pipeline.tasks.process import process_record

    scraper = CRSScraper()
    lookup = scraper.fetch()

    updated = 0
    for is_number, certification in lookup.items():
        stored = postgres.get_standard(is_number)
        record = dict(stored) if stored else {"is_number": is_number}
        record["certification"] = certification
        record.setdefault("sources", []).append("crs")

        change = detector.compare(record, stored)
        if change.needs_processing:
            process_record(
                record,
                {
                    "change_type": change.change_type.value,
                    "content_hash": change.content_hash,
                    "scope_hash": change.scope_hash,
                    "changed_fields": change.changed_fields,
                },
            )
            updated += 1

    postgres.record_sync_run("crs", scraper.stats.summary())
    return {"crs_entries": len(lookup), "updated": updated}


@app.task(name="pipeline.tasks.sync.check_gazette_updates")
def check_gazette_updates() -> dict:
    """
    Daily: watch for Quality Control Orders.

    A QCO is what makes a standard's certification mandatory. Without this
    feed the system would report yesterday's compliance regime with full
    confidence, which is worse than reporting nothing.
    """
    scraper = GazetteScraper()
    notifications = scraper.recent_notifications()

    processed = 0
    for notification in notifications:
        if notification.get("url"):
            process_gazette_notification.delay(notification["url"],
                                               notification.get("title", ""))
            processed += 1

    postgres.record_sync_run("gazette", scraper.stats.summary())
    return {"notifications": len(notifications), "queued": processed}


@app.task(bind=True, max_retries=2,
          name="pipeline.tasks.sync.process_gazette_notification")
def process_gazette_notification(self, url: str, title: str = "") -> dict:
    from pipeline.tasks.process import process_record

    scraper = GazetteScraper()
    parsed = scraper.parse_notification(url)
    if not parsed or not parsed.get("is_references"):
        return {"url": url, "affected": 0}

    affected = 0
    for is_number in parsed["is_references"]:
        stored = postgres.get_standard(is_number)
        record = dict(stored) if stored else {"is_number": is_number}
        record["certification"] = {
            "scheme": parsed["scheme"],
            "mandatory": True,
            "gazette_url": url,
            "gazette_title": title[:300],
            "effective_date": parsed.get("effective_date"),
        }
        record.setdefault("sources", []).append("gazette")

        change = detector.compare(record, stored)
        if change.needs_processing:
            process_record(record, {
                "change_type": change.change_type.value,
                "content_hash": change.content_hash,
                "scope_hash": change.scope_hash,
                "changed_fields": change.changed_fields,
            })
            affected += 1

    return {"url": url, "affected": affected, "scheme": parsed["scheme"]}


@app.task(name="pipeline.tasks.sync.pipeline_health_check")
def pipeline_health_check() -> dict:
    """
    Hourly: detect silent failure.

    The failure mode this exists to catch is a scraper that returns zero rows
    because the DOM changed. That looks identical to a correct 'nothing new'
    result unless selector misses are tracked -- so this is the difference
    between catching drift in an hour and discovering it on stage.
    """
    issues: list[str] = []

    with postgres.cursor(commit=False) as cur:
        if cur is None:
            return {"healthy": False, "issues": ["postgres unavailable"]}

        cur.execute(
            """SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 10"""
        )
        recent = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """SELECT MAX(last_seen) AS newest FROM is_standards"""
        )
        row = cur.fetchone()
        newest = row["newest"] if row else None

    if newest:
        staleness = datetime.now(timezone.utc) - newest
        if staleness > timedelta(hours=36):
            issues.append(f"corpus stale: last sync {staleness.total_seconds()/3600:.0f}h ago")

    for run in recent:
        if run.get("healthy") is False:
            issues.append(f"unhealthy run: {run['mode']}/{run['source']}")
        misses = run.get("selector_misses") or {}
        if misses:
            issues.append(f"selector misses in {run['source']}: {list(misses)}")

    healthy = not issues
    if not healthy:
        logger.error("Pipeline health issues: %s", issues)

    return {"healthy": healthy, "issues": issues, "recent_runs": len(recent)}
