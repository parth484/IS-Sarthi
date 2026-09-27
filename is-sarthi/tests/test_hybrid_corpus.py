"""
Test Suite for Hybrid Corpus Architecture (Tier 1 Enriched Seed + Tier 2 BIS Catalogue).

Verifies the 9 mandatory hybrid-corpus requirements:
1. IS-number normalization on actual seed & BIS numbers
2. Canonical seed/BIS matching (verifying 22+ canonical overlaps)
3. Tier-1 precedence for rich fields (scope, references, certification, amendments never overwritten)
4. Tier-2 catalogue retrieval without fake scope
5. Mixed Tier-1/Tier-2 search results with visible tier indicators
6. Withdrawn status handling
7. Missing optional fields resilience
8. Duplicate prevention
9. Preservation of all 57 seed records
10. API endpoint integration (/api/standards/{is_number}, /graph, /validate, /recommend)
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.index import app, corpus, get_hybrid_corpus
from pipeline.db.unified_corpus import (
    DEFAULT_BIS_PATH,
    DEFAULT_SEED_PATH,
    HybridCorpus,
    UnifiedCorpusAdapter,
    UnifiedCorpusRecord,
)
from pipeline.utils.normalize import (
    canonical_is_key,
    extract_all_is_references,
    get_standard_family,
    is_equivalent_designation,
    normalize_is_number,
    split_number_and_year,
)

client = TestClient(app)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seed_data() -> list[dict]:
    with open(DEFAULT_SEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def bis_data() -> list[dict]:
    with open(DEFAULT_BIS_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("standards", [])


@pytest.fixture(scope="module")
def hybrid_adapter(seed_data: list[dict], bis_data: list[dict]) -> UnifiedCorpusAdapter:
    return UnifiedCorpusAdapter(seed_data, bis_data)


# -----------------------------------------------------------------------------
# 1. IS-Number Normalization Tests
# -----------------------------------------------------------------------------
def test_is_number_normalization_on_actual_seeds_and_bis():
    """Verify normalization against complex real-world standard designations."""
    # Seed forms
    assert normalize_is_number("IS 1554-1") == "IS 1554-1"
    assert normalize_is_number("IS 1554 (Part 1):1988") == "IS 1554-1"
    assert normalize_is_number("IS 10322 (Part 5/Sec 1):2012") == "IS 10322-5-1"
    assert normalize_is_number("IS 10322-5-1") == "IS 10322-5-1"
    assert normalize_is_number("IS 269:2015") == "IS 269"

    # Multi-prefix adoptions
    assert normalize_is_number("IS/ISO 9001:2015") == "IS/ISO 9001"
    assert normalize_is_number("IS/IEC 60079 (Part 1):2014") == "IS/IEC 60079-1"
    assert normalize_is_number("SP 34:1987") == "SP 34"
    assert normalize_is_number("IS/QC 260400:2000") == "IS/QC 260400"

    # Equivalence checks
    assert is_equivalent_designation("IS 1554-1", "IS 1554 (Part 1):1988") is True
    assert is_equivalent_designation("IS 269", "IS 269:2015") is True
    assert is_equivalent_designation("IS 1554-1", "IS 1554-2") is False

    # Family checks
    assert get_standard_family("IS 1554-1") == "IS 1554"
    assert get_standard_family("IS 1554 (Part 1):1988") == "IS 1554"
    assert get_standard_family("IS 10322-5-1") == "IS 10322"

    # Split year checks
    canon, year = split_number_and_year("IS 1554 (Part 1):1988")
    assert canon == "IS 1554-1"
    assert year == 1988


# -----------------------------------------------------------------------------
# 2. Canonical Seed/BIS Matching Tests
# -----------------------------------------------------------------------------
def test_canonical_seed_bis_matching(hybrid_adapter: UnifiedCorpusAdapter):
    """Verify that canonical keys reliably discover overlapping standards across tiers."""
    # Audit proved at least 22 canonical overlaps (actually 24)
    assert hybrid_adapter.canonical_overlap_count >= 22

    # High-profile overlapping standards must be reconciled
    critical_overlaps = ["IS 269", "IS 456", "IS 1786", "IS 3043", "IS 2062"]
    for key in critical_overlaps:
        rec = hybrid_adapter.canonical_map.get(key)
        assert rec is not None, f"Overlap {key} missing from canonical map"
        assert rec["tier"] == "enriched"
        # Must retain seed attributes
        assert len(rec.get("scope", "")) > 0


# -----------------------------------------------------------------------------
# 3. Tier-1 Precedence for Rich Fields Tests
# -----------------------------------------------------------------------------
def test_tier1_precedence_for_rich_fields(
    hybrid_adapter: UnifiedCorpusAdapter, seed_data: list[dict]
):
    """Verify Tier 1 rich fields are never overwritten or degraded by Tier 2."""
    seed_dict = {s["is_number"]: s for s in seed_data}

    for s_num in ["IS 269", "IS 1786", "IS 456"]:
        rec = hybrid_adapter.get_by_number(s_num)
        assert rec is not None
        assert rec["tier"] == "enriched"
        assert rec["is_enriched"] is True

        orig_seed = seed_dict[s_num]
        # Scope must be byte-for-byte identical to seed
        assert rec["scope"] == orig_seed["scope"]
        # Normative references preserved
        assert rec["normative_references"] == orig_seed.get("normative_references", [])
        # Certification scheme preserved
        if orig_seed.get("certification"):
            assert rec["certification"] == orig_seed["certification"]

        # Amendments preserved
        assert rec["amendments"] == orig_seed.get("amendments", [])

        # Non-rich catalogue metadata should enrich the record
        assert "alternate_designations" in rec


# -----------------------------------------------------------------------------
# 4. Tier-2 Catalogue Retrieval Without Fake Scope Tests
# -----------------------------------------------------------------------------
def test_tier2_catalogue_retrieval_without_fake_scope(
    hybrid_adapter: UnifiedCorpusAdapter,
):
    """Verify Tier 2 catalogue records contain genuine metadata and zero fabricated scope."""
    # 'IS 9973:1981' is in BIS catalogue (scooter helmet visors) but not in 57 seeds
    rec = hybrid_adapter.get_by_number("IS 9973:1981")
    assert rec is not None
    assert rec["tier"] == "catalogue"
    assert rec["is_enriched"] is False

    # Strict non-fabrication guarantees
    assert rec["scope"] == ""  # Zero fake scope
    assert rec["normative_references"] == []  # Zero fake citations
    assert rec["certification"] is None  # Zero fake certification

    # Genuine catalogue metadata present
    assert rec["department"] == "CED" or rec.get("department_name") == "CIVIL ENGINEERING DEPARTMENT"
    assert "visor" in rec["title"].lower()


# -----------------------------------------------------------------------------
# 5. Mixed Tier-1/Tier-2 Search Results with Visible Tier Tests
# -----------------------------------------------------------------------------
def test_mixed_search_results_with_visible_tier():
    """Verify retrieval returns mixed results with explicit tier tags."""
    hc = get_hybrid_corpus()
    res = hc.recommend("cement", top_k=5)
    assert res["state"] == "ok"
    recs = res["recommendations"]
    assert len(recs) > 0

    # Must contain tier field and boolean flag
    tiers = {r["tier"] for r in recs}
    assert "enriched" in tiers or "catalogue" in tiers

    for r in recs:
        assert "tier" in r
        assert r["tier"] in ("enriched", "catalogue")
        assert "is_enriched" in r
        assert r["is_enriched"] == (r["tier"] == "enriched")
        assert "justification" in r
        # Non-enriched catalogue standards should state catalogue source
        if r["tier"] == "catalogue":
            assert "catalogue" in r["justification"].lower() or "bis" in r["justification"].lower()


# -----------------------------------------------------------------------------
# 6. Withdrawn Status Handling Tests
# -----------------------------------------------------------------------------
def test_withdrawn_status_handling(hybrid_adapter: UnifiedCorpusAdapter):
    """Verify withdrawn standards in BIS catalogue have accurate status and warnings."""
    # Find a standard whose canonical record is marked withdrawn
    withdrawn_records = [
        r for r in hybrid_adapter.records
        if r.get("status") == "withdrawn"
        and hybrid_adapter.canonical_map.get(r.get("canonical_key", "")).get("status") == "withdrawn"
    ]
    assert len(withdrawn_records) > 0, "No withdrawn standards found in hybrid corpus"

    sample_withdrawn = withdrawn_records[0]
    is_num = sample_withdrawn["canonical_key"]

    # Test validator response
    hc = get_hybrid_corpus()
    val = hc.validate(f"The contractor shall adhere to standard {is_num} for construction.")
    assert val["standards_checked"] >= 1

    # Must generate a high severity issue for withdrawn standard
    issues = [i for i in val["issues"] if i["is_number"] == is_num]
    assert len(issues) > 0
    assert any(i["severity"] == "high" for i in issues)
    assert any("withdrawn" in i["issue"].lower() for i in issues)



# -----------------------------------------------------------------------------
# 7. Missing Optional Fields Resilience Tests
# -----------------------------------------------------------------------------
def test_missing_optional_fields_resilience():
    """Verify UnifiedCorpusAdapter gracefully handles incomplete or malformed BIS entries."""
    sparse_bis_records = [
        {
            "is_number": "IS 99991:2020",
            "title": "Minimal Standard",
            # Missing published_on, valid_upto, department, aspect, etc.
        },
        {
            "is_number": "IS 99992",
            "title": "Another Minimal Standard",
            "department_alias": None,
            "withdrawn": None,
        },
    ]

    adapter = UnifiedCorpusAdapter(seed_records=[], bis_records=sparse_bis_records)
    assert adapter.total_count == 2
    rec1 = adapter.get_by_number("IS 99991")
    assert rec1 is not None
    assert rec1["title"] == "Minimal Standard"
    assert rec1["status"] == "current"
    assert rec1["tier"] == "catalogue"


# -----------------------------------------------------------------------------
# 8. Duplicate Prevention Tests
# -----------------------------------------------------------------------------
def test_duplicate_prevention(
    hybrid_adapter: UnifiedCorpusAdapter, seed_data: list[dict], bis_data: list[dict]
):
    """Verify unified corpus contains no duplicate standard entries."""
    expected_total = len(seed_data) + len(bis_data) - hybrid_adapter.canonical_overlap_count
    assert hybrid_adapter.total_count == expected_total

    # Verify all records have unique is_number in adapter.records
    numbers = [r["is_number"] for r in hybrid_adapter.records]
    assert len(numbers) == len(set(numbers))


# -----------------------------------------------------------------------------
# 9. Preservation of All 57 Seed Records Tests
# -----------------------------------------------------------------------------
def test_preservation_of_all_57_seed_records(
    hybrid_adapter: UnifiedCorpusAdapter, seed_data: list[dict]
):
    """Verify that every single seed record is preserved in the hybrid corpus."""
    assert len(seed_data) == 57
    assert len(corpus.records) == 57

    for s in seed_data:
        num = s["is_number"]
        rec = hybrid_adapter.get_by_number(num)
        assert rec is not None, f"Seed standard {num} not found in hybrid adapter"
        assert rec["tier"] == "enriched"
        assert rec["is_enriched"] is True
        assert rec["title"] == s["title"]
        assert rec["scope"] == s["scope"]


# -----------------------------------------------------------------------------
# 10. API Endpoints Hybrid Integration Tests
# -----------------------------------------------------------------------------
def test_api_hybrid_detail_and_graph():
    """Verify /api/standards/{is_number} and graph endpoints for both tiers."""
    # Tier 1 lookup
    res_t1 = client.get("/api/standards/IS%201554-1")
    assert res_t1.status_code == 200
    d1 = res_t1.json()
    assert d1["tier"] == "enriched"
    assert d1["is_enriched"] is True
    assert "tender_clause" in d1
    assert "allied_by_role" in d1

    # Tier 1 graph
    res_g1 = client.get("/api/standards/IS%201554-1/graph")
    assert res_g1.status_code == 200
    g1 = res_g1.json()
    assert len(g1["nodes"]) > 1
    assert len(g1["edges"]) > 0

    # Tier 2 lookup (Scooter helmet visor)
    res_t2 = client.get("/api/standards/IS%209973")
    assert res_t2.status_code == 200
    d2 = res_t2.json()
    assert d2["tier"] == "catalogue"
    assert d2["is_enriched"] is False
    assert "Standard Conformity" in d2["tender_clause"]
    assert d2["allied_by_role"] == {}

    # Tier 2 graph
    res_g2 = client.get("/api/standards/IS%209973/graph")
    assert res_g2.status_code == 200
    g2 = res_g2.json()
    assert len(g2["nodes"]) == 1
    assert len(g2["edges"]) == 0

    # Non-existent standard
    res_404 = client.get("/api/standards/IS%20999999")
    assert res_404.status_code == 404


def test_slash_and_complex_identifiers_routing():
    """Verify standards with slashes, colons, parentheses, and amendments resolve cleanly."""
    from urllib.parse import quote

    test_standards = [
        ("IS/ISO 21927 (Part 1):2008", "catalogue"),
        ("IS 10000 (Part 10):1980", "catalogue"),
        ("IS 7098-1:1988 (Amdt 1, 1996)", "enriched"),
        ("IS 8042:1989", "catalogue"),
        ("IS 694", "enriched"),
    ]

    for is_num, expected_tier in test_standards:
        # 1. Test via query parameter
        res_q = client.get("/api/standards/detail", params={"is_number": is_num})
        assert res_q.status_code == 200, f"Failed query lookup for {is_num}"
        d_q = res_q.json()
        assert d_q["tier"] == expected_tier

        # 2. Test via path parameter
        enc = quote(is_num, safe="")
        res_p = client.get(f"/api/standards/{enc}")
        assert res_p.status_code == 200, f"Failed path lookup for {is_num}"
        d_p = res_p.json()
        assert d_p["tier"] == expected_tier

        # 3. Test graph endpoint
        res_g = client.get("/api/standards/graph", params={"is_number": is_num})
        assert res_g.status_code == 200
        assert res_g.json()["target"] is not None

