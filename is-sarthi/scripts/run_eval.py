#!/usr/bin/env python3
"""
Retrieval evaluation harness.

The point of this file is that retrieval changes get measured rather than
asserted. "We improved the matching" is not a claim anyone should accept, from
us or from a competing team, without Recall@k attached to it.

    python scripts/run_eval.py
    python scripts/run_eval.py --online     # evaluate the full production stack
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EVAL_SET = Path(__file__).resolve().parents[1] / "data" / "seed" / "eval_queries.json"
SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "standards.json"


def recall_at_k(predicted: list[str], expected: list[str], k: int) -> float:
    top = set(predicted[:k])
    return len(top & set(expected)) / len(expected) if expected else 0.0


def hit_at_k(predicted: list[str], expected: list[str], k: int) -> int:
    return int(bool(set(predicted[:k]) & set(expected)))


def mean_reciprocal_rank(predicted: list[str], expected: list[str]) -> float:
    for index, is_number in enumerate(predicted, start=1):
        if is_number in expected:
            return 1.0 / index
    return 0.0


def evaluate(engine, cases: list[dict], allied_check: bool = True) -> dict:
    metrics = {"hit@1": [], "hit@3": [], "hit@5": [],
               "recall@3": [], "recall@5": [], "mrr": [], "allied_recall": []}
    failures = []

    for case in cases:
        result = engine(case["query"])
        predicted = [r["is_number"] for r in result.get("recommendations", [])]
        expected = case["expected"]

        metrics["hit@1"].append(hit_at_k(predicted, expected, 1))
        metrics["hit@3"].append(hit_at_k(predicted, expected, 3))
        metrics["hit@5"].append(hit_at_k(predicted, expected, 5))
        metrics["recall@3"].append(recall_at_k(predicted, expected, 3))
        metrics["recall@5"].append(recall_at_k(predicted, expected, 5))
        metrics["mrr"].append(mean_reciprocal_rank(predicted, expected))

        if allied_check and case.get("expected_allied"):
            surfaced = set()
            for rec in result.get("recommendations", []):
                allied = rec.get("allied") or {}
                for items in allied.values():
                    surfaced.update(item["is_number"] for item in items)
            expected_allied = set(case["expected_allied"])
            metrics["allied_recall"].append(
                len(surfaced & expected_allied) / len(expected_allied)
            )

        if not hit_at_k(predicted, expected, 3):
            failures.append(
                {"query": case["query"], "expected": expected, "got": predicted[:3]}
            )

    summary = {
        name: round(sum(values) / len(values), 4) if values else None
        for name, values in metrics.items()
    }
    return {"n": len(cases), "metrics": summary, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true",
                        help="Evaluate the production retrieval stack")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with open(EVAL_SET) as handle:
        cases = json.load(handle)

    if args.online:
        from api.services.recommender import recommend

        engine = lambda q: recommend(q, top_k=5)  # noqa: E731
        label = "production stack (e5 + BM25 + cross-encoder)"
    else:
        from scripts.demo_offline import OfflineCorpus

        with open(SEED) as handle:
            corpus = OfflineCorpus(json.load(handle))
        engine = lambda q: corpus.recommend(q, top_k=5)  # noqa: E731
        label = "offline engine (TF-IDF baseline)"

    report = evaluate(engine, cases)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"\nIS Sarthi retrieval evaluation — {label}")
    print(f"Queries: {report['n']}\n")
    for name, value in report["metrics"].items():
        if value is not None:
            bar = "█" * int(value * 30)
            print(f"  {name:14} {value:>6.1%}  {bar}")

    if report["failures"]:
        print(f"\nMisses ({len(report['failures'])}):")
        for failure in report["failures"][:8]:
            print(f"  · {failure['query'][:60]}")
            print(f"      expected {failure['expected']}, got {failure['got']}")

    print(
        "\nRead these numbers with the corpus size in mind. Against 57 seed\n"
        "standards there are few near-misses available, so scores are\n"
        "substantially inflated relative to what the full BIS catalogue\n"
        "(~20,000 standards, many with overlapping scopes) will produce.\n"
        "Treat this as a regression harness -- it catches retrieval changes\n"
        "that make things worse -- not as a quality claim. The offline arm is\n"
        "a TF-IDF floor for the production stack to beat, nothing more."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
