#!/usr/bin/env python3
"""
Manually trigger a pipeline sync.

    python scripts/trigger_sync.py --mode delta
    python scripts/trigger_sync.py --mode full --divisions ETD CED
    python scripts/trigger_sync.py --mode gazette
    python scripts/trigger_sync.py --mode health
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True,
                        choices=["full", "delta", "gazette", "crs", "health"])
    parser.add_argument("--divisions", nargs="*", help="Limit a full sync")
    parser.add_argument("--sync", action="store_true",
                        help="Run inline instead of queueing (no Celery worker needed)")
    args = parser.parse_args()

    from pipeline.tasks import sync

    task = {
        "full": sync.full_sync,
        "delta": sync.delta_sync,
        "gazette": sync.check_gazette_updates,
        "crs": sync.refresh_crs_list,
        "health": sync.pipeline_health_check,
    }[args.mode]

    kwargs = {"divisions": args.divisions} if args.mode == "full" and args.divisions else {}

    if args.sync:
        print(task.run(**kwargs))
    else:
        result = task.delay(**kwargs)
        print(f"Queued {args.mode} sync — task id {result.id}")
        print("Monitor with: celery -A pipeline.celery_app flower")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
