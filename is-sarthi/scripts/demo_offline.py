#!/usr/bin/env python3
"""
Zero-infrastructure demo of the full recommendation flow.

Runs the same four-stage logic as the production path -- hybrid retrieval, RRF
fusion, graph expansion, certification lookup, justification -- but substitutes
TF-IDF for the transformer embeddings and an in-memory dict for the three
datastores. Requires only numpy and scikit-learn.

This exists for two reasons. Operationally, a demo that depends on Docker,
three databases and a 450MB model download is a demo that fails on stage.
Architecturally, it proves the orchestration logic is independent of the
retrieval backend -- swapping TF-IDF for e5 changes one function.

    python scripts/demo_offline.py
    python scripts/demo_offline.py --query "3 core armoured copper cable"
    python scripts/demo_offline.py --validate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

from pipeline.classify import ROLE_LABELS, classify_all  # noqa: E402
from pipeline.utils.normalize import extract_all_is_references  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "standards.json"

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREEN, AMBER, RED, BLUE, SAFFRON = (
    "\033[92m", "\033[93m", "\033[91m", "\033[94m", "\033[38;5;214m",
)


class OfflineCorpus:
    def __init__(self, records: list[dict]):
        self.records = records
        self.by_number = {r["is_number"]: r for r in records}

        titles = {r["is_number"]: r.get("title", "") for r in records}
        self.graph: dict[str, list[dict]] = {
            r["is_number"]: classify_all(r.get("normative_references", []),
                                         title_lookup=titles)
            for r in records
        }

        # Dense arm stand-in: character n-grams capture morphological overlap
        # ("armour"/"armoured"/"armouring") the way subword embeddings would.
        self.dense_vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1
        )
        # Sparse arm: word-level, mirroring BM25's exact-term behaviour.
        self.sparse_vec = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
        )

        documents = [f"{r.get('title','')}. {r.get('scope','')}" for r in records]
        self.dense_matrix = self.dense_vec.fit_transform(documents)
        self.sparse_matrix = self.sparse_vec.fit_transform(documents)
        self.ids = [r["is_number"] for r in records]

    # --- retrieval ------------------------------------------------------

    def _rank(self, matrix, vectorizer, query: str, top_k: int) -> list[tuple[str, float]]:
        vector = vectorizer.transform([query])
        scores = (matrix @ vector.T).toarray().ravel()
        order = np.argsort(-scores)[:top_k]
        return [(self.ids[i], float(scores[i])) for i in order if scores[i] > 0]

    def retrieve(self, query: str, top_k: int = 5, rrf_k: int = 60) -> list[dict]:
        dense = self._rank(self.dense_matrix, self.dense_vec, query, 25)
        sparse = self._rank(self.sparse_matrix, self.sparse_vec, query, 25)

        fused: dict[str, dict] = {}
        for rank, (is_number, score) in enumerate(dense, start=1):
            fused[is_number] = {"is_number": is_number, "dense_rank": rank,
                                "dense": score, "sparse_rank": None, "sparse": 0.0}
        for rank, (is_number, score) in enumerate(sparse, start=1):
            entry = fused.setdefault(
                is_number,
                {"is_number": is_number, "dense_rank": None, "dense": 0.0,
                 "sparse_rank": None, "sparse": 0.0},
            )
            entry["sparse_rank"], entry["sparse"] = rank, score

        for entry in fused.values():
            score = 0.0
            if entry["dense_rank"]:
                score += 1 / (rrf_k + entry["dense_rank"])
            if entry["sparse_rank"]:
                score += 1 / (rrf_k + entry["sparse_rank"])
            entry["fused"] = score

        ranked = sorted(fused.values(), key=lambda e: e["fused"], reverse=True)[:top_k]
        self._confidence(ranked)
        return ranked

    @staticmethod
    def _confidence(ranked: list[dict]) -> None:
        """
        Three-signal blend: absolute match quality, cross-arm agreement, margin.

        The *absolute* similarity has to dominate. An earlier version weighted
        the fused score relative to the top hit, which is degenerate: RRF
        scores cluster tightly by construction, so every result scored near the
        leader and a wholly irrelevant standard came back "Medium". Relative
        position tells you the ordering, not whether anything matched at all --
        only the raw similarity does.
        """
        if not ranked:
            return

        top_absolute = max(e["dense"] for e in ranked) or 1e-9
        runner_up = ranked[1]["dense"] if len(ranked) > 1 else 0.0

        for index, entry in enumerate(ranked):
            # Absolute match quality, scaled so typical good TF-IDF cosines
            # (~0.35-0.5 on this corpus) land in the High band.
            quality = min(1.0, entry["dense"] / 0.45)
            agreement = 1.0 if (entry["dense_rank"] and entry["sparse_rank"]) else 0.0
            margin = (
                max(0.0, (top_absolute - runner_up) / top_absolute) if index == 0 else 0.0
            )
            entry["confidence"] = round(
                min(1.0, 0.65 * quality + 0.15 * agreement + 0.20 * margin), 3
            )

    # --- enrichment -----------------------------------------------------

    def allied(self, is_number: str, query: str, depth: int = 2) -> dict[str, list[dict]]:
        """Breadth-first traversal to `depth`, ranked by hop plus query relevance."""
        seen: dict[str, dict] = {}
        frontier = [(is_number, 0)]

        while frontier:
            current, hop = frontier.pop(0)
            if hop >= depth:
                continue
            for ref in self.graph.get(current, []):
                target = ref["is_number"]
                if target == is_number or target in seen:
                    continue
                record = self.by_number.get(target, {})
                seen[target] = {
                    "is_number": target,
                    "title": record.get("title") or ref.get("title"),
                    "status": record.get("status", "unknown"),
                    "ref_type": ref["ref_type"],
                    "role": ROLE_LABELS.get(ref["ref_type"], "Related product"),
                    "hop": hop + 1,
                }
                frontier.append((target, hop + 1))

        if seen:
            # Relevance blending: keeps ubiquitous terminology standards from
            # crowding out the test method that actually matters for this spec.
            query_vector = self.dense_vec.transform([query])
            for item in seen.values():
                text = f"{item['title'] or ''} {self.by_number.get(item['is_number'],{}).get('scope','')}"
                similarity = float(
                    (self.dense_vec.transform([text]) @ query_vector.T).toarray().ravel()[0]
                )
                item["relevance"] = round(0.6 * (1 / item["hop"]) + 0.4 * similarity, 3)

        by_role: dict[str, list[dict]] = {}
        for item in sorted(seen.values(), key=lambda i: -i.get("relevance", 0)):
            role_label = ROLE_LABELS.get(item["ref_type"], "Related product")
            by_role.setdefault(role_label, []).append(item)
        return by_role

    def justify(self, query: str, record: dict) -> str:
        """Template justification -- identical fallback path to production."""
        terms = set(re.findall(r"[a-z]{4,}", query.lower()))
        text = f"{record.get('title','')} {record.get('scope','')}".lower()
        overlap = sorted(t for t in terms if t in text)[:4]
        if overlap:
            return (f"Scope covers {', '.join(overlap)} as described in the "
                    f"specification.")
        return "Closest semantic match; review the scope before citing."

    # --- public ---------------------------------------------------------

    def recommend(self, query: str, top_k: int = 3) -> dict:
        ranked = self.retrieve(query, top_k=top_k)
        if not ranked or ranked[0]["confidence"] < 0.35:
            return {"query": query, "state": "low_confidence",
                    "message": "No confident match. Add material, rating or application detail.",
                    "recommendations": []}

        recommendations = []
        for entry in ranked:
            record = self.by_number[entry["is_number"]]
            certification = record.get("certification") or {}
            amendments = record.get("amendments") or []
            version = f"{record['is_number']}:{record.get('year','')}"
            if amendments:
                version += f" (Amdt {amendments[-1]['number']}, {amendments[-1].get('date','')})"

            recommendations.append({
                "is_number": record["is_number"],
                "title": record.get("title"),
                "status": record.get("status"),
                "superseded_by": record.get("superseded_by"),
                "latest_version": version,
                "confidence": entry["confidence"],
                "band": ("High" if entry["confidence"] >= 0.75
                         else "Medium" if entry["confidence"] >= 0.5 else "Low"),
                "justification": self.justify(query, record),
                "certification": certification or None,
                "amendments": amendments,
                "allied": self.allied(record["is_number"], query),
                "signals": {"dense_rank": entry["dense_rank"],
                            "sparse_rank": entry["sparse_rank"]},
            })
        return {"query": query, "state": "ok", "recommendations": recommendations}

    def validate(self, spec_text: str) -> dict:
        cited = extract_all_is_references(spec_text)
        issues, suggestions = [], []

        for is_number in cited:
            record = self.by_number.get(is_number)
            if not record:
                issues.append({"is_number": is_number, "severity": "info",
                               "issue": "Not found in corpus",
                               "action": "Verify on the BIS portal."})
                continue

            if record.get("status") in ("withdrawn", "superseded"):
                successor = record.get("superseded_by")
                issues.append({
                    "is_number": is_number, "severity": "high",
                    "issue": f"Standard is {record['status']}",
                    "action": f"Replace with {successor}" if successor
                              else "Check BIS for the successor.",
                })

            certification = record.get("certification") or {}
            if certification.get("mandatory"):
                issues.append({
                    "is_number": is_number, "severity": "medium",
                    "issue": f"{certification['scheme']} certification is mandatory",
                    "action": "State the certification requirement in the tender.",
                })

            for ref in self.graph.get(is_number, []):
                if ref["is_number"] not in cited and not any(
                    s["is_number"] == ref["is_number"] for s in suggestions
                ):
                    suggestions.append({
                        "is_number": ref["is_number"],
                        "title": self.by_number.get(ref["is_number"], {}).get("title"),
                        "role": ROLE_LABELS.get(ref["ref_type"], "Related"),
                        "referenced_by": is_number,
                    })

        order = {"high": 0, "medium": 1, "info": 2}
        issues.sort(key=lambda i: order.get(i["severity"], 3))
        return {"cited": cited, "issues": issues, "suggested_additions": suggestions[:10]}


# ----------------------------------------------------------------- rendering

def render(result: dict) -> None:
    print(f"\n{BOLD}Query:{RESET} {result['query']}")

    if result["state"] != "ok":
        print(f"{AMBER}  {result['message']}{RESET}")
        return

    for index, rec in enumerate(result["recommendations"], start=1):
        colour = {"High": GREEN, "Medium": AMBER, "Low": RED}[rec["band"]]
        status_mark = ""
        if rec["status"] in ("withdrawn", "superseded"):
            status_mark = (f"  {RED}[{rec['status'].upper()}"
                           + (f" -> {rec['superseded_by']}" if rec["superseded_by"] else "")
                           + f"]{RESET}")

        print(f"\n{BOLD}{index}. {rec['is_number']}{RESET} — {rec['title'][:70]}{status_mark}")
        print(f"   {colour}Confidence: {rec['band']} ({rec['confidence']}){RESET}"
              f"   {DIM}dense#{rec['signals']['dense_rank']} "
              f"sparse#{rec['signals']['sparse_rank']}{RESET}")
        print(f"   Version: {rec['latest_version']}")
        print(f"   {rec['justification']}")

        if rec["certification"]:
            cert = rec["certification"]
            print(f"   {SAFFRON}● {cert.get('scheme_label', cert.get('scheme'))} "
                  f"— MANDATORY{RESET}")

        if rec["allied"]:
            print(f"   {BLUE}Allied standards:{RESET}")
            for role, items in rec["allied"].items():
                names = ", ".join(f"{i['is_number']}" for i in items[:4])
                print(f"     {DIM}{role:18}{RESET} {names}")


def render_validation(result: dict) -> None:
    print(f"\n{BOLD}Specification validation{RESET}")
    print(f"Cited standards: {', '.join(result['cited']) or 'none'}\n")

    if result["issues"]:
        print(f"{BOLD}Issues{RESET}")
        for issue in result["issues"]:
            colour = {"high": RED, "medium": AMBER, "info": DIM}[issue["severity"]]
            print(f"  {colour}[{issue['severity'].upper():6}]{RESET} "
                  f"{issue['is_number']}: {issue['issue']}")
            print(f"           {DIM}→ {issue['action']}{RESET}")

    if result["suggested_additions"]:
        print(f"\n{BOLD}Consider also citing{RESET}")
        for item in result["suggested_additions"]:
            print(f"  {item['is_number']:14} {DIM}{item['role']:18}{RESET} "
                  f"{(item['title'] or '')[:50]}")


DEMO_QUERIES = [
    "3 core armoured copper cable for underground LV power distribution up to 1100V",
    "43 grade ordinary portland cement for RCC foundation work",
    "LED street light fittings for municipal road lighting",
    "gold jewellery procurement for government gifting",
    "TMT steel reinforcement bars Fe 500 grade for bridge construction",
    "solar photovoltaic panels for rooftop installation on government building",
]

DEMO_SPEC = """
Supply of PVC insulated heavy duty cables conforming to IS 1554 (Part 1).
Cement shall conform to IS 8112:2013 for 43 grade OPC.
Reinforcement bars shall conform to IS 1786.
All work shall follow IS 456 for concrete.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Run a single query")
    parser.add_argument("--validate", action="store_true",
                        help="Run the spec-validator demo")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    args = parser.parse_args()

    with open(SEED) as handle:
        records = json.load(handle)
    corpus = OfflineCorpus(records)

    print(f"{BOLD}IS Sarthi — offline demo{RESET}")
    print(f"{DIM}Corpus: {len(records)} standards across "
          f"{len({r['division'] for r in records})} BIS divisions{RESET}")

    if args.validate:
        result = corpus.validate(DEMO_SPEC)
        print(json.dumps(result, indent=2)) if args.json else render_validation(result)
        return 0

    queries = [args.query] if args.query else DEMO_QUERIES
    for query in queries:
        result = corpus.recommend(query)
        print(json.dumps(result, indent=2)) if args.json else render(result)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
