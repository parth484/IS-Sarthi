"""Unit tests for the correctness-critical pipeline components."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.change_detector import ChangeType, detector
from pipeline.classify import RefType, classify_reference
from pipeline.utils.normalize import (
    extract_all_is_references,
    normalize_is_number,
    split_number_and_year,
)


class TestNormalization:
    """IS-number canonicalization: every downstream join depends on this."""

    @pytest.mark.parametrize("raw,expected", [
        ("IS 1554 (Part 1) : 1988", "IS 1554-1"),
        ("IS:1554-1", "IS 1554-1"),
        ("IS 1554 Part 1", "IS 1554-1"),
        ("IS1554", "IS 1554"),
        ("IS 732:2019", "IS 732"),
        ("IS 10810-7", "IS 10810-7"),
        ("IS 8130 (Part 2)", "IS 8130-2"),
        ("no standard here", None),
    ])
    def test_canonical_forms(self, raw, expected):
        assert normalize_is_number(raw) == expected

    def test_year_not_mistaken_for_part(self):
        """The subtle one: 'IS 1554-1988' is a year, not Part 1988."""
        number, year = split_number_and_year("IS 1554-1988")
        assert number == "IS 1554"
        assert year == 1988

    def test_extract_multiple_preserves_order(self):
        refs = extract_all_is_references(
            "Conforms to IS 694:2010 and IS 8130 (Part 2), tested per IS 10810-7."
        )
        assert refs == ["IS 694", "IS 8130-2", "IS 10810-7"]

    def test_extract_deduplicates(self):
        assert extract_all_is_references("IS 456 and IS 456:2000") == ["IS 456"]


class TestClassification:
    @pytest.mark.parametrize("title,expected", [
        ("Methods of test for cables Part 7", RefType.TEST_METHOD),
        ("Glossary of terms relating to cables", RefType.TERMINOLOGY),
        ("Code of practice for electrical wiring installations", RefType.INSTALLATION),
        ("Safety requirements for LV switchgear", RefType.SAFETY),
        ("Methods of sampling hydraulic cement", RefType.SAMPLING),
        ("PVC insulated cables Part 1", RefType.RELATED_PRODUCT),
    ])
    def test_title_rules(self, title, expected):
        assert classify_reference(title=title) == expected

    def test_rule_precedence(self):
        """'Methods of test for safety of X' is a test method, not a safety standard."""
        assert classify_reference(
            title="Methods of test for safety of household appliances"
        ) == RefType.TEST_METHOD

    def test_context_fallback(self):
        assert classify_reference(
            title=None, citing_context="shall be tested in accordance with"
        ) == RefType.TEST_METHOD


class TestChangeDetection:
    @pytest.fixture
    def record(self):
        return {
            "title": "XLPE Cables",
            "year": 2020,
            "status": "current",
            "normative_references": ["IS 8130", "IS 10810-7"],
            "scope": "Covers XLPE insulated cables.",
        }

    @pytest.fixture
    def stored(self, record):
        return {
            "content_hash": detector.content_hash(record),
            "scope_hash": detector.scope_hash(record),
            **record,
        }

    def test_identical_is_unchanged(self, record, stored):
        assert detector.compare(record, stored).change_type == ChangeType.UNCHANGED

    def test_reordered_references_do_not_trigger_rebuild(self, record, stored):
        """Extraction order is an artefact; it must not cause spurious work."""
        shuffled = dict(record, normative_references=["IS 10810-7", "IS 8130"])
        assert detector.compare(shuffled, stored).change_type == ChangeType.UNCHANGED

    def test_scope_change_triggers_reembedding(self, record, stored):
        changed = dict(record, scope="Covers XLPE cables up to 1100V.")
        result = detector.compare(changed, stored)
        assert result.change_type == ChangeType.SCOPE
        assert result.needs_reembedding

    def test_metadata_change_skips_reembedding(self, record, stored):
        """Gating embedding on scope is what makes daily syncs affordable."""
        changed = dict(record, year=2021)
        result = detector.compare(changed, stored)
        assert result.change_type == ChangeType.METADATA
        assert not result.needs_reembedding

    def test_withdrawal_outranks_other_changes(self, record, stored):
        """Withdrawal is the most user-consequential change and must not be masked."""
        changed = dict(record, status="withdrawn", title="XLPE Cables Revised")
        assert detector.compare(changed, stored).change_type == ChangeType.WITHDRAWN

    def test_new_record(self, record):
        result = detector.compare(record, None)
        assert result.change_type == ChangeType.NEW
        assert result.needs_reembedding and result.needs_graph_update


class TestSeedCorpus:
    @pytest.fixture
    def corpus(self):
        path = Path(__file__).resolve().parents[1] / "data" / "seed" / "standards.json"
        with open(path) as handle:
            return json.load(handle)

    def test_numbers_are_canonical(self, corpus):
        for record in corpus:
            assert normalize_is_number(record["is_number"]) == record["is_number"]

    def test_no_duplicates(self, corpus):
        numbers = [r["is_number"] for r in corpus]
        assert len(numbers) == len(set(numbers))

    def test_every_record_has_scope(self, corpus):
        """Scope is the embedded field; a record without it cannot be retrieved."""
        for record in corpus:
            assert record.get("scope"), f"{record['is_number']} has no scope"

    def test_no_self_references(self, corpus):
        for record in corpus:
            assert record["is_number"] not in record.get("normative_references", [])

    def test_superseded_records_name_successor(self, corpus):
        for record in corpus:
            if record.get("status") == "superseded":
                assert record.get("superseded_by")


class TestEvalSet:
    def test_expected_standards_exist_in_corpus(self):
        base = Path(__file__).resolve().parents[1] / "data" / "seed"
        with open(base / "standards.json") as handle:
            corpus = {r["is_number"] for r in json.load(handle)}
        with open(base / "eval_queries.json") as handle:
            cases = json.load(handle)

        for case in cases:
            for is_number in case["expected"]:
                assert is_number in corpus, (
                    f"eval expects {is_number} which is not in the seed corpus"
                )
