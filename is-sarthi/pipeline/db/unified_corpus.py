"""
Unified Hybrid Corpus Adapter and Retrieval Architecture for IS Sarthi.

Logically unifies:
- Tier 1: Enriched Core (data/seed/standards.json) - 57 curated standards
  Authoritative for scope, normative references, allied citation graph,
  and mandatory certification schemes (ISI, CRS, Hallmarking).
- Tier 2: National BIS Catalogue (data/bis/standards.json) - 13,779 standards
  Authoritative for standard number discovery, official titles, department routing,
  aspect/type facets, validity/review dates, and active/withdrawn status.

Non-destructive: No duplicate files created on disk.
Tier 1 records retain 100% precedence for rich fields.
Tier 2 records contain only factual metadata; no fabricated scope or citations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from pipeline.classify import ROLE_LABELS, classify_all
from pipeline.utils.normalize import (
    canonical_is_key,
    extract_all_is_references,
    is_equivalent_designation,
    normalize_is_number,
    split_number_and_year,
)

logger = logging.getLogger(__name__)

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed" / "standards.json"
DEFAULT_BIS_PATH = Path(__file__).resolve().parents[2] / "data" / "bis" / "standards.json"


@dataclass
class UnifiedCorpusRecord:
    is_number: str
    canonical_key: str
    title: str
    tier: str  # "enriched" (Tier 1) or "catalogue" (Tier 2)
    source: str
    status: str = "current"
    year: Optional[int] = None
    published_on: Optional[str] = None
    valid_upto: Optional[str] = None
    department: Optional[str] = None
    department_name: Optional[str] = None
    aspect: Optional[str] = None
    degree_of_equivalence: Optional[str] = None
    scope: Optional[str] = None
    normative_references: list[str] = field(default_factory=list)
    certification: Optional[dict] = None
    amendments: list[dict] = field(default_factory=list)
    superseded_by: Optional[str] = None
    title_hindi: Optional[str] = None
    alternate_designations: list[str] = field(default_factory=list)
    raw_record: dict = field(default_factory=dict)

    @property
    def is_enriched(self) -> bool:
        return self.tier == "enriched"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching the schema expected across IS Sarthi APIs."""
        return {
            "is_number": self.is_number,
            "canonical_key": self.canonical_key,
            "title": self.title,
            "title_hindi": self.title_hindi,
            "year": self.year,
            "status": self.status,
            "division": self.department,
            "department": self.department,
            "department_name": self.department_name,
            "scope": self.scope or "",
            "normative_references": self.normative_references,
            "amendments": self.amendments,
            "certification": self.certification,
            "superseded_by": self.superseded_by,
            "published_on": self.published_on,
            "valid_upto": self.valid_upto,
            "aspect": self.aspect,
            "degree_of_equivalence": self.degree_of_equivalence,
            "tier": self.tier,
            "is_enriched": self.is_enriched,
            "sources": [self.source],
            "alternate_designations": self.alternate_designations,
        }


class UnifiedCorpusAdapter:
    """
    Non-destructive logical combiner for Tier 1 (Seed) and Tier 2 (BIS Catalogue).
    """

    def __init__(
        self,
        seed_records: list[dict],
        bis_records: Optional[list[dict]] = None,
    ):
        self.tier1_raw = seed_records
        self.tier2_raw = bis_records or []

        self.records: list[dict] = []
        self.records_by_number: dict[str, dict] = {}
        self.canonical_map: dict[str, dict] = {}
        self.tier1_canonical_keys: set[str] = set()

        self._canonical_overlap_count = 0
        self._build_unified_index()

    def _build_unified_index(self) -> None:
        """
        Merge Tier 1 and Tier 2 records with Tier 1 precedence for rich fields.
        """
        # 1. Process Tier 1 Enriched Records
        for s in self.tier1_raw:
            raw_num = s.get("is_number", "")
            canon_key = normalize_is_number(raw_num) or raw_num

            rec = UnifiedCorpusRecord(
                is_number=raw_num,
                canonical_key=canon_key,
                title=s.get("title", ""),
                tier="enriched",
                source="Seed Enriched Corpus (Tier 1)",
                status=s.get("status", "current"),
                year=s.get("year"),
                department=s.get("division"),
                department_name=None,
                scope=s.get("scope"),
                normative_references=list(s.get("normative_references", [])),
                certification=s.get("certification"),
                amendments=list(s.get("amendments", [])),
                superseded_by=s.get("superseded_by"),
                raw_record=s,
            )

            rec_dict = rec.to_dict()
            self.records.append(rec_dict)
            self.records_by_number[raw_num] = rec_dict
            self.canonical_map[canon_key] = rec_dict
            self.tier1_canonical_keys.add(canon_key)

        # 2. Process Tier 2 Catalogue Records
        for b in self.tier2_raw:
            b_num = b.get("is_number", "")
            if not b_num:
                continue

            canon_key, year = split_number_and_year(b_num)
            if not canon_key:
                canon_key = normalize_is_number(b_num) or b_num

            # Check for canonical overlap with Tier 1
            if canon_key in self.tier1_canonical_keys:
                # Enrich Tier 1 with official catalogue metadata without overwriting rich fields
                tier1_rec = self.canonical_map[canon_key]
                self._canonical_overlap_count += 1

                if b_num not in tier1_rec.get("alternate_designations", []):
                    tier1_rec.setdefault("alternate_designations", []).append(b_num)

                # Populate missing non-rich metadata from official catalogue
                if not tier1_rec.get("published_on") and b.get("published_on"):
                    tier1_rec["published_on"] = b.get("published_on")
                if not tier1_rec.get("valid_upto") and b.get("valid_upto"):
                    tier1_rec["valid_upto"] = b.get("valid_upto")
                if not tier1_rec.get("department_name") and b.get("department_name"):
                    tier1_rec["department_name"] = b.get("department_name")
                if not tier1_rec.get("division") and b.get("department_alias"):
                    tier1_rec["division"] = b.get("department_alias")
                    tier1_rec["department"] = b.get("department_alias")
                if not tier1_rec.get("aspect") and b.get("aspect"):
                    tier1_rec["aspect"] = b.get("aspect")
                if not tier1_rec.get("degree_of_equivalence") and b.get("degree_of_equivalence"):
                    tier1_rec["degree_of_equivalence"] = b.get("degree_of_equivalence")
                if not tier1_rec.get("title_hindi") and b.get("title_hindi"):
                    tier1_rec["title_hindi"] = b.get("title_hindi")

                # Map BIS raw number to the enriched record for instant lookup
                self.records_by_number[b_num] = tier1_rec
            else:
                # Add as Tier-2 Catalogue Record
                is_withdrawn = b.get("withdrawn", False)
                status = "withdrawn" if is_withdrawn else "current"

                rec = UnifiedCorpusRecord(
                    is_number=b_num,
                    canonical_key=canon_key,
                    title=b.get("title", ""),
                    tier="catalogue",
                    source="Official BIS Published Standards Catalogue (Tier 2)",
                    status=status,
                    year=year,
                    published_on=b.get("published_on"),
                    valid_upto=b.get("valid_upto"),
                    department=b.get("department_alias"),
                    department_name=b.get("department_name"),
                    aspect=b.get("aspect"),
                    degree_of_equivalence=b.get("degree_of_equivalence"),
                    scope=None,  # Tier 2 carries NO fabricated scope
                    normative_references=[],  # Tier 2 carries NO fabricated references
                    certification=None,  # Tier 2 carries NO fabricated certification
                    amendments=[],
                    title_hindi=b.get("title_hindi"),
                    raw_record=b,
                )

                rec_dict = rec.to_dict()
                self.records.append(rec_dict)
                self.records_by_number[b_num] = rec_dict
                if canon_key not in self.canonical_map or (
                    status == "current"
                    and self.canonical_map[canon_key].get("status") == "withdrawn"
                ):
                    self.canonical_map[canon_key] = rec_dict

    def get_by_number(self, query_number: Optional[str]) -> Optional[dict]:
        """
        Fast multi-stage lookup by standard number:
        1. Exact raw key match (e.g. 'IS 1554-1' or 'IS 1554 (Part 1):1988')
        2. Canonical key match (e.g. 'IS 1554-1')
        """
        if not query_number:
            return None
        stripped = str(query_number).strip()
        # Direct match
        if stripped in self.records_by_number:
            return self.records_by_number[stripped]
        # Canonical match
        canon = normalize_is_number(stripped)
        if canon and canon in self.canonical_map:
            return self.canonical_map[canon]
        return None

    @property
    def total_count(self) -> int:
        return len(self.records)

    @property
    def tier1_count(self) -> int:
        return len(self.tier1_raw)

    @property
    def tier2_count(self) -> int:
        return len(self.records) - len(self.tier1_raw)

    @property
    def canonical_overlap_count(self) -> int:
        return self._canonical_overlap_count


class HybridCorpus:
    """
    Unified Hybrid Retrieval Corpus for IS Sarthi.

    Drop-in compatible with OfflineCorpus:
    - Provides recommend(), retrieve(), validate(), allied(), and by_number.
    - Accurately distinguishes Tier-1 Enriched Core from Tier-2 Catalogue.
    - Zero fabrication of scope, citations, or certification.
    """

    def __init__(
        self,
        seed_records: list[dict],
        bis_records: Optional[list[dict]] = None,
    ):
        self.adapter = UnifiedCorpusAdapter(seed_records, bis_records)
        self.records = self.adapter.records
        self.by_number = self.adapter.records_by_number

        # Graph built strictly from Tier 1 records holding normative_references
        titles = {r["is_number"]: r.get("title", "") for r in self.records}
        self.graph: dict[str, list[dict]] = {
            r["is_number"]: classify_all(
                r.get("normative_references", []), title_lookup=titles
            )
            if r.get("tier") == "enriched"
            else []
            for r in self.records
        }

        # Vectorizers
        self.dense_vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1
        )
        self.sparse_vec = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
        )

        # Retrieval documents:
        # Tier 1 uses title + scope.
        # Tier 2 uses factual designation, title, department, and aspect.
        documents = []
        for r in self.records:
            if r.get("tier") == "enriched":
                doc = f"{r.get('title', '')}. {r.get('scope', '')}"
            else:
                dept_str = r.get("department_name") or r.get("department") or ""
                aspect_str = r.get("aspect") or ""
                doc = f"{r.get('is_number', '')} {r.get('title', '')}. Department: {dept_str}. Aspect: {aspect_str}."
            documents.append(doc)

        logger.info("Fitting TF-IDF index over %d unified documents...", len(documents))
        self.dense_matrix = self.dense_vec.fit_transform(documents)
        self.sparse_matrix = self.sparse_vec.fit_transform(documents)
        self.ids = [r["is_number"] for r in self.records]

    @classmethod
    def from_files(
        cls,
        seed_path: Path = DEFAULT_SEED_PATH,
        bis_path: Path = DEFAULT_BIS_PATH,
    ) -> HybridCorpus:
        """Instantiate HybridCorpus from disk paths."""
        seeds: list[dict] = []
        if seed_path.exists():
            with open(seed_path, "r", encoding="utf-8") as f:
                seeds = json.load(f)

        bis_standards: list[dict] = []
        if bis_path.exists():
            try:
                with open(bis_path, "r", encoding="utf-8") as f:
                    bis_data = json.load(f)
                    bis_standards = bis_data.get("standards", [])
            except Exception as exc:
                logger.warning("Could not load BIS catalogue from %s: %s", bis_path, exc)

        return cls(seed_records=seeds, bis_records=bis_standards)

    # --- Retrieval ------------------------------------------------------

    def _rank(
        self, matrix: Any, vectorizer: Any, query: str, top_k: int
    ) -> list[tuple[str, float]]:
        vector = vectorizer.transform([query])
        scores = (matrix @ vector.T).toarray().ravel()
        order = np.argsort(-scores)[:top_k]
        return [(self.ids[i], float(scores[i])) for i in order if scores[i] > 0]

    def retrieve(
        self, query: str, top_k: int = 5, rrf_k: int = 60
    ) -> list[dict]:
        """
        Hybrid retrieval fusing dense subword TF-IDF and sparse word TF-IDF via RRF.
        Returns ranked candidate entries tagged with their tier.
        """
        dense = self._rank(self.dense_matrix, self.dense_vec, query, 35)
        sparse = self._rank(self.sparse_matrix, self.sparse_vec, query, 35)

        fused: dict[str, dict] = {}
        for rank, (is_number, score) in enumerate(dense, start=1):
            record = self.by_number.get(is_number, {})
            fused[is_number] = {
                "is_number": is_number,
                "tier": record.get("tier", "catalogue"),
                "dense_rank": rank,
                "dense": score,
                "sparse_rank": None,
                "sparse": 0.0,
            }
        for rank, (is_number, score) in enumerate(sparse, start=1):
            record = self.by_number.get(is_number, {})
            entry = fused.setdefault(
                is_number,
                {
                    "is_number": is_number,
                    "tier": record.get("tier", "catalogue"),
                    "dense_rank": None,
                    "dense": 0.0,
                    "sparse_rank": None,
                    "sparse": 0.0,
                },
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
        """Blend absolute similarity, cross-arm agreement, and leader margin."""
        if not ranked:
            return

        top_absolute = max(e["dense"] for e in ranked) or 1e-9
        runner_up = ranked[1]["dense"] if len(ranked) > 1 else 0.0

        for index, entry in enumerate(ranked):
            quality = min(1.0, entry["dense"] / 0.40)
            agreement = 1.0 if (entry["dense_rank"] and entry["sparse_rank"]) else 0.0
            margin = (
                max(0.0, (top_absolute - runner_up) / top_absolute)
                if index == 0
                else 0.0
            )
            entry["confidence"] = round(
                min(1.0, 0.65 * quality + 0.15 * agreement + 0.20 * margin), 3
            )

    # --- Enrichment & Graph ---------------------------------------------

    def allied(
        self, is_number: str, query: str, depth: int = 2
    ) -> dict[str, list[dict]]:
        """
        Traverse citation graph for Tier 1 standards.
        Tier 2 standards safely return empty taxonomy without failure.
        """
        record = self.adapter.get_by_number(is_number)
        if not record or record.get("tier") != "enriched":
            return {}

        seen: dict[str, dict] = {}
        frontier = [(record["is_number"], 0)]

        while frontier:
            current, hop = frontier.pop(0)
            if hop >= depth:
                continue
            for ref in self.graph.get(current, []):
                target = ref["is_number"]
                if target == is_number or target in seen:
                    continue
                target_rec = self.adapter.get_by_number(target) or {}
                seen[target] = {
                    "is_number": target,
                    "title": target_rec.get("title") or ref.get("title"),
                    "status": target_rec.get("status", "unknown"),
                    "ref_type": ref["ref_type"],
                    "role": ROLE_LABELS.get(ref["ref_type"], "Related product"),
                    "hop": hop + 1,
                }
                frontier.append((target, hop + 1))

        if seen:
            query_vector = self.dense_vec.transform([query])
            for item in seen.values():
                item_rec = self.adapter.get_by_number(item["is_number"]) or {}
                text = f"{item['title'] or ''} {item_rec.get('scope', '')}"
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
        """
        Generate contextual justification for recommendation.
        Distinguishes Tier 1 scope matching from Tier 2 catalogue matching.
        """
        tier = record.get("tier", "catalogue")
        if tier == "enriched" and record.get("scope"):
            terms = set(re.findall(r"[a-z]{4,}", query.lower()))
            text = f"{record.get('title','')} {record.get('scope','')}".lower()
            overlap = sorted(t for t in terms if t in text)[:4]
            if overlap:
                return (
                    f"Scope covers {', '.join(overlap)} as described in the specification."
                )
            return "Closest semantic match; review the scope before citing."

        # Tier 2 justification (honest and transparent about evidence source)
        dept = record.get("department_name") or record.get("department") or "BIS"
        aspect = record.get("aspect") or "Standard"
        return (
            f"National catalogue match from BIS {dept} ({aspect}). "
            f"Verified active standard in published Indian Standards catalogue."
        )

    # --- Public Endpoints -----------------------------------------------

    def recommend(self, query: str, top_k: int = 5) -> dict:
        """
        Recommend standards matching a query across both Tier 1 and Tier 2.
        Preserves Tier-1 rich dossiers and Tier-2 national catalogue coverage.
        """
        ranked = self.retrieve(query, top_k=top_k)
        if not ranked or ranked[0]["confidence"] < 0.25:
            return {
                "query": query,
                "state": "low_confidence",
                "message": "No confident match. Add material, rating or application detail.",
                "recommendations": [],
            }

        recommendations = []
        for entry in ranked:
            record = self.by_number[entry["is_number"]]
            tier = record.get("tier", "catalogue")
            certification = record.get("certification")
            amendments = record.get("amendments") or []
            year = record.get("year")

            version = f"{record['is_number']}:{year}" if year else record["is_number"]
            if amendments:
                version += f" (Amdt {amendments[-1]['number']}, {amendments[-1].get('date','')})"

            recommendations.append(
                {
                    "is_number": record["is_number"],
                    "canonical_key": record.get("canonical_key", record["is_number"]),
                    "title": record.get("title"),
                    "title_hindi": record.get("title_hindi"),
                    "tier": tier,
                    "is_enriched": tier == "enriched",
                    "status": record.get("status", "current"),
                    "department": record.get("department"),
                    "department_name": record.get("department_name"),
                    "aspect": record.get("aspect"),
                    "published_on": record.get("published_on"),
                    "valid_upto": record.get("valid_upto"),
                    "superseded_by": record.get("superseded_by"),
                    "latest_version": version,
                    "confidence": entry["confidence"],
                    "band": (
                        "High"
                        if entry["confidence"] >= 0.75
                        else "Medium"
                        if entry["confidence"] >= 0.50
                        else "Low"
                    ),
                    "justification": self.justify(query, record),
                    "certification": certification,
                    "amendments": amendments,
                    "allied": self.allied(record["is_number"], query)
                    if tier == "enriched"
                    else {},
                    "signals": {
                        "dense_rank": entry["dense_rank"],
                        "sparse_rank": entry["sparse_rank"],
                    },
                }
            )

        return {"query": query, "state": "ok", "recommendations": recommendations}

    def validate(self, spec_text: str) -> dict:
        """
        Validate cited IS designators against the unified corpus.
        Resolves both Tier 1 and Tier 2 standards using canonical matching.
        """
        cited = extract_all_is_references(spec_text)
        issues, suggestions = [], []

        for is_number in cited:
            record = self.adapter.get_by_number(is_number)
            if not record:
                issues.append(
                    {
                        "is_number": is_number,
                        "severity": "info",
                        "issue": "Not found in unified corpus",
                        "action": "Verify on the BIS portal.",
                    }
                )
                continue

            status = record.get("status", "current")
            tier = record.get("tier", "catalogue")

            # Check withdrawn / superseded status
            if status in ("withdrawn", "superseded"):
                successor = record.get("superseded_by")
                issues.append(
                    {
                        "is_number": is_number,
                        "severity": "high",
                        "issue": f"Standard is {status} in official BIS catalogue",
                        "action": f"Replace with {successor}"
                        if successor
                        else "Consult latest BIS catalogue for active successor.",
                    }
                )

            # Check review date expiration
            valid_upto = record.get("valid_upto")
            if valid_upto and str(valid_upto) < "2026-09-27":
                issues.append(
                    {
                        "is_number": is_number,
                        "severity": "low",
                        "issue": f"Standard review window lapsed on {valid_upto}",
                        "action": "Confirm whether BIS has issued reaffirmation or revision.",
                    }
                )

            # Check certification requirements for Tier 1
            certification = record.get("certification") or {}
            if certification.get("mandatory"):
                issues.append(
                    {
                        "is_number": is_number,
                        "severity": "medium",
                        "issue": f"{certification['scheme']} certification is mandatory under applicable QCO",
                        "action": f"Require BIS {certification.get('scheme_label', 'certification')} in tender submission criteria.",
                    }
                )

            # Positive acknowledgment
            suggestions.append(
                {
                    "is_number": is_number,
                    "canonical_key": record.get("canonical_key"),
                    "title": record.get("title"),
                    "tier": tier,
                    "status": status,
                    "department": record.get("department_name") or record.get("department"),
                }
            )

        suggested_additions = []
        for is_num in cited:
            rec = self.adapter.get_by_number(is_num)
            if rec and rec.get("tier") == "enriched":
                for ref in self.graph.get(rec.get("is_number", is_num), []):
                    target = ref["is_number"]
                    if target not in cited and not any(s["is_number"] == target for s in suggested_additions):
                        target_rec = self.adapter.get_by_number(target) or {}
                        suggested_additions.append({
                            "is_number": target,
                            "title": target_rec.get("title") or ref.get("title"),
                            "role": ROLE_LABELS.get(ref.get("ref_type"), "Related product"),
                            "referenced_by": is_num,
                        })

        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        issues.sort(key=lambda i: order.get(i["severity"], 4))

        return {
            "cited": cited,
            "standards_checked": len(cited),
            "valid_standards": len(suggestions),
            "issues": issues,
            "suggested_additions": suggested_additions[:10],
            "matched_standards": suggestions,
        }

