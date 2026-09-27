"""
Unit tests for BIS API client and ingestion pipeline.

Mocks all external HTTP calls so no real BIS network requests are made during tests.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.scrapers.bis_api import (
    BISApiClient,
    BISAPIError,
    BISCatalogueResult,
    BISRequestError,
    BISSearchResult,
)
from pipeline.scrapers.bis_ingest import (
    create_backup,
    get_dedup_key,
    ingest_all_departments,
    ingest_bis_department,
    ingest_bis_standards,
    load_existing_dataset,
    load_ingestion_state,
    normalize_bis_record,
    save_dataset_atomic,
    save_ingestion_state,
)


@pytest.fixture
def mock_session():
    return MagicMock(spec=requests.Session)


@pytest.fixture
def sample_bis_search_payload():
    return {
        "status": "SUCCESS",
        "statusCode": 200,
        "msg": "Standards fetched successfully.",
        "totalRecords": 2,
        "data": [
            {
                "standardId": 30080,
                "standardNumber": "IS 10080:2026",
                "standardName": "Vibration Machine for casting standard cement mortar cubes",
                "standardNameInHindi": "मानक सीमेंट मोर्टार क्यूब्स",
                "departmentId": 74,
                "committeeId": 313,
                "publishedOn": "2026-01-15",
                "validUpto": "2031-01-14",
                "withdrawStatus": 0,
                "withdrawOn": None,
                "isStatus": 2,
                "matched_standard": "IS 10080:2026",
            },
            {
                "standardId": 30086,
                "standardNumber": "IS 10086:2021",
                "standardName": "Moulds for Use in Tests of Cement, Concrete and Pozzolana",
                "standardNameInHindi": "",
                "departmentId": 74,
                "committeeId": 313,
                "publishedOn": "2021-03-10",
                "validUpto": "2026-03-09",
                "withdrawStatus": 0,
                "withdrawOn": None,
                "isStatus": 2,
                "matched_standard": "IS 10086:2021",
            },
        ],
    }


@pytest.fixture
def sample_departments_payload():
    return {
        "status": "SUCCESS",
        "statusCode": 200,
        "msg": "Technical departments fetched successfully.",
        "data": [
            {
                "departmentId": 63,
                "deptName": "CIVIL ENGINEERING DEPARTMENT",
                "deptAliasName": "CED",
                "preparedName": "CIVIL ENGINEERING DEPARTMENT (CED)",
                "encryptedDepartmentId": "ENC_CED_12345",
            },
            {
                "departmentId": 65,
                "deptName": "ELECTROTECHNICAL DEPARTMENT",
                "deptAliasName": "ETD",
                "preparedName": "ELECTROTECHNICAL DEPARTMENT (ETD)",
                "encryptedDepartmentId": "ENC_ETD_67890",
            },
        ],
    }


@pytest.fixture
def sample_catalogue_payload():
    return {
        "status": "SUCCESS",
        "statusCode": 200,
        "msg": "Standards fetched successfully.",
        "totalRecord": 940,
        "data": [
            {
                "slNo": 1,
                "standardId": 19609,
                "standardNumber": "IS 19609:2026",
                "standardTitle": "uPVC Profiles Framed Doors, Windows and sliders - Specification",
                "publishedOn": "2026-02-10",
                "reviewOn": "2031-02-09",
                "isStatus": 2,
                "noOfRevision": 0,
                "typeOfStandardName": "Product Specification",
                "equivalenceTypeName": "None",
                "documents": [],
            },
            {
                "slNo": 2,
                "standardId": 10080,
                "standardNumber": "IS 10080:2026",
                "standardName": "Vibration Machine for casting standard cement mortar cubes",
                "publishedOn": "2026-01-15",
                "reviewOn": "2031-01-14",
                "isStatus": 2,
                "noOfRevision": 1,
                "typeOfStandardName": "Methods of Tests",
                "equivalenceTypeName": "Identical",
                "documents": [],
            },
        ],
    }


class TestBISApiClientSearch:
    """Tests for BISApiClient searchKnowStandards endpoint."""

    def test_successful_api_response_parsing(self, mock_session, sample_bis_search_payload):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_bis_search_payload
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        res = client.search("cement")

        assert isinstance(res, BISSearchResult)
        assert res.status == "SUCCESS"
        assert res.status_code == 200
        assert res.total_records == 2
        assert len(res.records) == 2
        assert res.records[0]["standardNumber"] == "IS 10080:2026"

        mock_session.post.assert_called_once()
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["searchText"] == "cement"
        assert kwargs["json"]["token"] is None
        assert kwargs["headers"]["Content-Type"] == "application/json"

    def test_failed_http_response_exhaustion(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_session.post.return_value = mock_resp

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=2, retry_backoff=1.0
        )
        with pytest.raises(BISRequestError) as exc_info:
            client.search("steel")

        assert "502" in str(exc_info.value)
        assert mock_session.post.call_count == 2

    def test_network_timeout_exhaustion(self, mock_session):
        mock_session.post.side_effect = requests.exceptions.Timeout("Connection timed out")

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=2, retry_backoff=1.0
        )
        with pytest.raises(BISRequestError) as exc_info:
            client.search("steel")

        assert "timed out" in str(exc_info.value)
        assert mock_session.post.call_count == 2

    def test_invalid_json(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        with pytest.raises(BISAPIError) as exc_info:
            client.search("plastic")

        assert "Failed to parse JSON" in str(exc_info.value)

    def test_bis_api_error_status(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "FAILURE",
            "statusCode": 400,
            "msg": "Invalid search parameters",
            "data": None,
        }
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        with pytest.raises(BISAPIError) as exc_info:
            client.search("invalid")

        assert "FAILURE" in str(exc_info.value)
        assert "Invalid search parameters" in str(exc_info.value)

    def test_missing_data_field_handled_cleanly(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "SUCCESS",
            "statusCode": 200,
            "msg": "No standards found",
            "totalRecords": 0,
        }
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        res = client.search("nonexistent")

        assert res.status == "SUCCESS"
        assert res.records == []
        assert res.total_records == 0

    def test_empty_search_text_validation(self):
        client = BISApiClient(rate_limit_delay=0.0)
        with pytest.raises(ValueError):
            client.search("")


class TestBISApiClientDepartmentAndCatalogue:
    """Tests for departments directory and paginated catalogue endpoints."""

    def test_department_endpoint_success(self, mock_session, sample_departments_payload):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_departments_payload
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        depts = client.get_website_departments()

        assert len(depts) == 2
        assert depts[0]["deptAliasName"] == "CED"
        assert depts[0]["encryptedDepartmentId"] == "ENC_CED_12345"

        mock_session.post.assert_called_once()
        url, kwargs = mock_session.post.call_args
        assert "sdo-service/getWebsiteDepartments" in url[0]
        assert kwargs["json"] == {}

    def test_department_endpoint_http_error(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_session.post.return_value = mock_resp

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=1, retry_backoff=1.0
        )
        with pytest.raises(BISRequestError) as exc_info:
            client.get_website_departments()
        assert "500" in str(exc_info.value)

    def test_department_endpoint_invalid_json(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        with pytest.raises(BISAPIError):
            client.get_website_departments()

    def test_catalogue_endpoint_success_with_department(
        self, mock_session, sample_catalogue_payload
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_catalogue_payload
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        res = client.get_website_ps_tech_department_wise(
            offset=0, limit=100, enc_department_id="ENC_CED_12345"
        )

        assert isinstance(res, BISCatalogueResult)
        assert res.status == "SUCCESS"
        assert res.status_code == 200
        assert res.total_records == 940
        assert len(res.records) == 2
        assert res.offset == 0
        assert res.limit == 100

        mock_session.post.assert_called_once()
        url, kwargs = mock_session.post.call_args
        assert "getWebsitePSTechDepartmentWise" in url[0]
        payload = kwargs["json"]
        assert payload["encDepartmentId"] == "ENC_CED_12345"
        assert payload["typeSelected"] == 1
        assert payload["offset"] == 0
        assert payload["limit"] == 100

    def test_catalogue_endpoint_all_departments(self, mock_session, sample_catalogue_payload):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_catalogue_payload
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        res = client.get_website_ps_tech_department_wise(
            offset=100, limit=50, all_departments=True
        )

        assert res.total_records == 940
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["allDepartments"] is True
        assert kwargs["json"]["totalRow"] == 1
        assert kwargs["json"]["offset"] == 100
        assert kwargs["json"]["limit"] == 50

    def test_catalogue_endpoint_http_error(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_session.post.return_value = mock_resp

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=1, retry_backoff=1.0
        )
        with pytest.raises(BISRequestError) as exc_info:
            client.get_website_ps_tech_department_wise(offset=0, limit=100)
        assert "503" in str(exc_info.value)

    def test_catalogue_endpoint_invalid_json(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("error", "doc", 0)
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        with pytest.raises(BISAPIError):
            client.get_website_ps_tech_department_wise(offset=0, limit=100)

    def test_catalogue_endpoint_empty_page(self, mock_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "SUCCESS",
            "statusCode": 200,
            "msg": "No records found",
            "totalRecord": 0,
            "data": [],
        }
        mock_session.post.return_value = mock_resp

        client = BISApiClient(session=mock_session, rate_limit_delay=0.0)
        res = client.get_website_ps_tech_department_wise(offset=0, limit=100)

        assert res.records == []
        assert res.total_records == 0


class TestRetryAndFailureHandling:
    """Tests for bounded retries with exponential backoff on transient errors."""

    def test_retry_on_transient_503_then_success(self, mock_session, sample_departments_payload):
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = sample_departments_payload

        # Fail once with 503, then succeed on 2nd attempt
        mock_session.post.side_effect = [resp_503, resp_200]

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=3, retry_backoff=1.0
        )
        depts = client.get_website_departments()

        assert len(depts) == 2
        assert mock_session.post.call_count == 2

    def test_retry_on_transient_timeout_then_success(
        self, mock_session, sample_catalogue_payload
    ):
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = sample_catalogue_payload

        # Timeout on 1st attempt, succeed on 2nd attempt
        mock_session.post.side_effect = [
            requests.exceptions.Timeout("Server busy"),
            resp_200,
        ]

        client = BISApiClient(
            session=mock_session, rate_limit_delay=0.0, max_retries=3, retry_backoff=1.0
        )
        res = client.get_website_ps_tech_department_wise(offset=0, limit=100)

        assert res.total_records == 940
        assert mock_session.post.call_count == 2


class TestBISNormalization:
    """Tests for field extraction and normalization from raw records."""

    def test_normalize_record_complete_fields(self):
        raw = {
            "standardId": 12345,
            "standardNumber": "  IS 456:2000  ",
            "standardName": " Plain and Reinforced Concrete - Code of Practice ",
            "standardNameInHindi": " सादा और प्रबलित कंक्रीट ",
            "departmentId": 10,
            "committeeId": 20,
            "publishedOn": "2000-10-15",
            "validUpto": "2025-10-14",
            "withdrawStatus": 0,
            "withdrawOn": None,
            "isStatus": 2,
            "matched_standard": "IS 456",
        }
        normalized = normalize_bis_record(raw, query="concrete")

        assert normalized["is_number"] == "IS 456:2000"
        assert normalized["title"] == "Plain and Reinforced Concrete - Code of Practice"
        assert normalized["title_hindi"] == "सादा और प्रबलित कंक्रीट"
        assert normalized["standard_id"] == 12345
        assert normalized["department_id"] == 10
        assert normalized["committee_id"] == 20
        assert normalized["published_on"] == "2000-10-15"
        assert normalized["valid_upto"] == "2025-10-14"
        assert normalized["withdraw_status"] == 0
        assert normalized["withdrawn"] is False
        assert normalized["is_status"] == 2
        assert normalized["matched_standard"] == "IS 456"
        assert normalized["matched_queries"] == ["concrete"]
        assert "BIS Published Standards Catalogue" in normalized["source"]

    def test_normalize_catalogue_record_with_dept_info(self):
        raw = {
            "slNo": 1,
            "standardId": 19609,
            "standardNumber": "IS 19609:2026",
            "standardTitle": "uPVC Profiles Framed Doors, Windows",
            "publishedOn": "2026-02-10",
            "reviewOn": "2031-02-09",
            "isStatus": 2,
            "noOfRevision": 1,
            "typeOfStandardName": "Product Specification",
            "equivalenceTypeName": "Identical",
        }
        dept_info = {
            "departmentId": 63,
            "deptName": "CIVIL ENGINEERING DEPARTMENT",
            "deptAliasName": "CED",
        }
        normalized = normalize_bis_record(raw, dept_info=dept_info)

        assert normalized["is_number"] == "IS 19609:2026"
        assert normalized["title"] == "uPVC Profiles Framed Doors, Windows"
        assert normalized["department_id"] == 63
        assert normalized["department_alias"] == "CED"
        assert normalized["department_name"] == "CIVIL ENGINEERING DEPARTMENT"
        assert normalized["published_on"] == "2026-02-10"
        assert normalized["valid_upto"] == "2031-02-09"
        assert normalized["revision_count"] == 1
        assert normalized["aspect"] == "Product Specification"
        assert normalized["degree_of_equivalence"] == "Identical"
        assert normalized["matched_queries"] == ["CED"]


class TestStateCheckpointAndResumability:
    """Tests for state checkpointing, backups, atomic writes, and resume capability."""

    def test_checkpoint_save_and_load(self, tmp_path):
        state_file = tmp_path / "test_state.json"
        initial_state = load_ingestion_state(state_file)
        assert initial_state["completed_departments"] == []

        initial_state["completed_departments"].append("CED")
        initial_state["current_offset"] = 200
        save_ingestion_state(state_file, initial_state)

        loaded_state = load_ingestion_state(state_file)
        assert loaded_state["completed_departments"] == ["CED"]
        assert loaded_state["current_offset"] == 200

    def test_backup_creation_and_atomic_save(self, tmp_path):
        out_file = tmp_path / "standards.json"
        data_map = {"NUM:IS 1": {"is_number": "IS 1", "title": "Test 1"}}
        meta = {"unique_standards": 1}

        save_dataset_atomic(out_file, data_map, meta)
        assert out_file.exists()

        backup = create_backup(out_file)
        assert backup is not None
        assert backup.exists()
        assert backup.name == "standards.json.bak"

    def test_ingest_all_departments_resumes_from_checkpoint(self, tmp_path):
        mock_client = MagicMock(spec=BISApiClient)
        mock_client.get_website_departments.return_value = [
            {"deptAliasName": "CED", "deptName": "Civil", "encryptedDepartmentId": "ENC_CED"},
            {"deptAliasName": "ETD", "deptName": "Electro", "encryptedDepartmentId": "ENC_ETD"},
        ]

        # ETD returns 1 page
        mock_client.get_website_ps_tech_department_wise.return_value = BISCatalogueResult(
            status="SUCCESS",
            status_code=200,
            msg="ok",
            total_records=1,
            records=[{"standardNumber": "IS 2000", "standardName": "Cable Std"}],
            offset=0,
            limit=100,
        )

        out_file = tmp_path / "standards.json"
        state_file = tmp_path / "ingestion_state.json"

        # Pre-seed state: CED is already completed
        pre_state = {
            "version": 1,
            "completed_departments": ["CED"],
            "failed_departments": {},
            "current_offset": 0,
            "department_code": None,
            "stats": {"raw_records_collected": 100, "new_unique_standards": 90, "duplicates_merged": 10},
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(pre_state, f)

        res = ingest_all_departments(
            client=mock_client,
            limit=100,
            resume=True,
            output_path=out_file,
            state_path=state_file,
        )

        # CED was skipped; ETD was processed
        assert mock_client.get_website_ps_tech_department_wise.call_count == 1
        _, kwargs = mock_client.get_website_ps_tech_department_wise.call_args
        assert kwargs["enc_department_id"] == "ENC_ETD"
        assert "CED" in res["metadata"]["departments_ingested"] or "ETD" in res["metadata"]["departments_ingested"]

    def test_failed_department_recorded_and_continues_to_next(self, tmp_path):
        mock_client = MagicMock(spec=BISApiClient)
        mock_client.get_website_departments.return_value = [
            {"deptAliasName": "CED", "deptName": "Civil", "encryptedDepartmentId": "ENC_CED"},
            {"deptAliasName": "ETD", "deptName": "Electro", "encryptedDepartmentId": "ENC_ETD"},
        ]

        # CED fails with BISRequestError, ETD succeeds
        res_etd = BISCatalogueResult(
            status="SUCCESS",
            status_code=200,
            msg="ok",
            total_records=1,
            records=[{"standardNumber": "IS 3000", "standardName": "Switchgear"}],
            offset=0,
            limit=100,
        )
        mock_client.get_website_ps_tech_department_wise.side_effect = [
            BISRequestError("Network dropped for CED"),
            res_etd,
        ]

        out_file = tmp_path / "standards.json"
        state_file = tmp_path / "ingestion_state.json"

        res = ingest_all_departments(
            client=mock_client,
            limit=100,
            resume=False,
            output_path=out_file,
            state_path=state_file,
        )

        # CED recorded in failed_departments, ETD succeeded
        assert "CED" in res["run_stats"]["departments_failed"]
        assert res["run_stats"]["departments_completed"] == 1
        assert len(res["standards"]) == 1
        assert res["standards"][0]["is_number"] == "IS 3000"


class TestBISDepartmentIngestionWorkflow:
    """Tests for department-wise pagination, deduplication, and dataset preservation."""

    def test_ingest_department_pagination_and_max_pages(self, tmp_path):
        mock_client = MagicMock(spec=BISApiClient)
        mock_client.get_website_departments.return_value = [
            {
                "departmentId": 63,
                "deptAliasName": "CED",
                "deptName": "CIVIL ENGINEERING DEPARTMENT",
                "encryptedDepartmentId": "ENC_CED",
            }
        ]

        # Return page 1 of 2
        mock_client.get_website_ps_tech_department_wise.return_value = BISCatalogueResult(
            status="SUCCESS",
            status_code=200,
            msg="ok",
            total_records=250,
            records=[
                {"standardNumber": f"IS {i}", "standardName": f"Std {i}"}
                for i in range(1, 101)
            ],
            offset=0,
            limit=100,
        )

        out_file = tmp_path / "bis_standards.json"
        state_file = tmp_path / "state.json"
        res = ingest_bis_department(
            department_code="CED",
            client=mock_client,
            limit=100,
            max_pages=1,
            output_path=out_file,
            state_path=state_file,
        )

        assert mock_client.get_website_ps_tech_department_wise.call_count == 1
        assert res["run_stats"]["raw_collected"] == 100
        assert res["run_stats"]["new_unique"] == 100
        assert res["metadata"]["departments_ingested"] == ["CED"]

    def test_preserves_existing_bis_records_and_merges_duplicates(self, tmp_path):
        out_file = tmp_path / "bis_standards.json"
        state_file = tmp_path / "state.json"

        # Pre-populate dataset with 2 standards
        initial_data = {
            "metadata": {
                "source": "BIS Know Your Standard",
                "search_terms": ["cement"],
                "departments_ingested": [],
                "total_records_collected": 2,
                "unique_standards": 2,
            },
            "standards": [
                {
                    "is_number": "IS 10080:2026",
                    "title": "Vibration Machine",
                    "standard_id": 30080,
                    "matched_queries": ["cement"],
                    "aspect": None,
                },
                {
                    "is_number": "IS 9999",
                    "title": "Unrelated Existing Standard",
                    "standard_id": 9999,
                    "matched_queries": ["cement"],
                    "aspect": None,
                },
            ],
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        mock_client = MagicMock(spec=BISApiClient)
        mock_client.get_website_departments.return_value = [
            {
                "departmentId": 63,
                "deptAliasName": "CED",
                "deptName": "CIVIL ENGINEERING",
                "encryptedDepartmentId": "ENC_CED",
            }
        ]

        # Catalogue returns IS 10080 (duplicate with richer aspect) and IS 19609 (brand new)
        mock_client.get_website_ps_tech_department_wise.return_value = BISCatalogueResult(
            status="SUCCESS",
            status_code=200,
            msg="ok",
            total_records=2,
            records=[
                {
                    "standardNumber": "IS 10080:2026",
                    "standardName": "Vibration Machine for Cement Mortar",
                    "standardId": 30080,
                    "typeOfStandardName": "Methods of Tests",
                },
                {
                    "standardNumber": "IS 19609:2026",
                    "standardName": "uPVC Profiles",
                    "standardId": 19609,
                    "typeOfStandardName": "Product Specification",
                },
            ],
            offset=0,
            limit=100,
        )

        res = ingest_bis_department(
            department_code="CED",
            client=mock_client,
            limit=100,
            output_path=out_file,
            state_path=state_file,
        )

        # 1 new unique added + 2 previously existing = 3 unique standards
        assert res["run_stats"]["new_unique"] == 1
        assert res["run_stats"]["duplicates_merged"] == 1
        assert res["metadata"]["unique_standards"] == 3

        # Verify IS 9999 is still preserved
        std_map = {s["is_number"]: s for s in res["standards"]}
        assert "IS 9999" in std_map

        # Verify IS 10080 has merged matched_queries ("cement" AND "CED") and updated aspect
        is_10080 = std_map["IS 10080:2026"]
        assert "cement" in is_10080["matched_queries"]
        assert "CED" in is_10080["matched_queries"]
        assert is_10080["aspect"] == "Methods of Tests"

    def test_invalid_department_code_raises_error(self):
        mock_client = MagicMock(spec=BISApiClient)
        mock_client.get_website_departments.return_value = [
            {"deptAliasName": "CED", "deptName": "Civil Engineering"},
            {"deptAliasName": "ETD", "deptName": "Electrotechnical"},
        ]

        with pytest.raises(ValueError) as exc_info:
            ingest_bis_department(department_code="INVALID_XYZ", client=mock_client)

        assert "INVALID_XYZ" in str(exc_info.value)
        assert "CED" in str(exc_info.value)
