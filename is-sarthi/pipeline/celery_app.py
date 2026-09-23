"""
Celery application: queues, routing, retry policy, and the beat schedule that
makes the corpus self-updating.
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from pipeline.config import settings

app = Celery(
    "is_sarthi",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["pipeline.tasks.sync", "pipeline.tasks.process"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,              # redeliver if a worker dies mid-task
    worker_prefetch_multiplier=1,     # long tasks: do not hoard the queue
    task_reject_on_worker_lost=True,
    result_expires=60 * 60 * 24 * 7,
)

# Three queues because the work has three very different resource profiles.
# Without separation, a GPU-bound embedding backlog would block the IO-bound
# crawler and the nightly sync would never finish.
app.conf.task_queues = (
    Queue("scrape"),    # network-bound, rate-limited
    Queue("process"),   # CPU-light parsing and DB writes
    Queue("embed"),     # CPU/GPU-heavy
)
app.conf.task_default_queue = "process"
app.conf.task_routes = {
    "pipeline.tasks.sync.scrape_*": {"queue": "scrape"},
    "pipeline.tasks.sync.*_sync": {"queue": "scrape"},
    "pipeline.tasks.sync.check_*": {"queue": "scrape"},
    "pipeline.tasks.sync.refresh_*": {"queue": "scrape"},
    "pipeline.tasks.process.regenerate_embedding": {"queue": "embed"},
    "pipeline.tasks.process.*": {"queue": "process"},
}

app.conf.beat_schedule = {
    "weekly-full-sync": {
        "task": "pipeline.tasks.sync.full_sync",
        "schedule": crontab(hour=settings.full_sync_hour, minute=0, day_of_week=0),
    },
    "daily-delta-sync": {
        "task": "pipeline.tasks.sync.delta_sync",
        "schedule": crontab(hour=settings.delta_sync_hour, minute=0),
    },
    "daily-gazette-check": {
        "task": "pipeline.tasks.sync.check_gazette_updates",
        "schedule": crontab(hour=settings.gazette_hour, minute=0),
    },
    "weekly-crs-refresh": {
        "task": "pipeline.tasks.sync.refresh_crs_list",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),
    },
    "hourly-health-check": {
        "task": "pipeline.tasks.sync.pipeline_health_check",
        "schedule": crontab(minute=15),
    },
}
