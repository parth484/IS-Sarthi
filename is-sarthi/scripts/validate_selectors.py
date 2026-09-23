#!/usr/bin/env python3
"""
Validate scrapers against the live DOM.

Run this before any production crawl, and after any report of a drop in
extraction rate. It fetches one sample page per source and reports which
configured selectors actually resolve.

The failure this prevents is the expensive one: a scraper that returns zero
rows because the markup changed looks exactly like a scraper that correctly
found nothing new. Without this check, that difference surfaces at the worst
possible moment.

    python scripts/validate_selectors.py
    python scripts/validate_selectors.py --source bis_portal
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup  # noqa: E402

from pipeline.scrapers.base import load_selectors  # noqa: E402
from pipeline.utils.http import client  # noqa: E402

GREEN, RED, AMBER, DIM, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"


def probe(soup: BeautifulSoup, name: str, spec) -> tuple[bool, str]:
    candidates = spec.get("candidates", []) if isinstance(spec, dict) else [spec]
    for selector in candidates:
        try:
            found = soup.select(selector)
        except Exception:
            continue
        if found:
            return True, f"{selector} → {len(found)} nodes"
    return False, f"none of {len(candidates)} candidates matched"


def validate_source(key: str, config: dict) -> bool:
    print(f"\n{key}")
    base = config.get("base_url")
    path = (
        config.get("search_path")
        or config.get("landing_path")
        or config.get("recently_published_path")
        or "/"
    )
    url = urljoin(base, path)
    print(f"{DIM}  {url}{RESET}")

    response = client.get(url, snapshot=False)
    if response is None:
        print(f"  {RED}✕ unreachable{RESET} — network blocked, site down, or robots.txt disallow")
        return False

    soup = BeautifulSoup(response.text, "lxml")
    all_ok = True

    for name, spec in config.items():
        if not isinstance(spec, dict) or "candidates" not in spec:
            if isinstance(spec, dict):
                for sub_name, sub_spec in spec.items():
                    if isinstance(sub_spec, dict) and "candidates" in sub_spec:
                        ok, detail = probe(soup, f"{name}.{sub_name}", sub_spec)
                        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✕{RESET}"
                        print(f"  {mark} {name}.{sub_name}: {detail}")
                        all_ok &= ok
            continue

        ok, detail = probe(soup, name, spec)
        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✕{RESET}"
        print(f"  {mark} {name}: {detail}")
        all_ok &= ok

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Validate only this source")
    args = parser.parse_args()

    selectors = load_selectors()
    targets = {args.source: selectors[args.source]} if args.source else selectors

    print("Selector validation")
    print(f"{DIM}Probing live pages. Failures here mean the DOM has drifted; "
          f"fix pipeline/scrapers/selectors.yaml, not the code.{RESET}")

    results = {key: validate_source(key, config) for key, config in targets.items()}

    print("\nSummary")
    for key, ok in results.items():
        print(f"  {GREEN + 'PASS' if ok else RED + 'FAIL'}{RESET}  {key}")

    if not all(results.values()):
        print(f"\n{AMBER}Some selectors did not resolve. This is expected on first "
              f"run: the shipped selectors are a starting point, not verified "
              f"against the live site. Update selectors.yaml and re-run.{RESET}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
