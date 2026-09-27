"""
BIS standards ingestion pipeline.

Supports two official ingestion modes:
1. Full / Department Catalogue Ingestion (review-service getWebsitePSTechDepartmentWise)
   - Multi-department traversal (--all)
   - Specific department (--department CED)
   - Full resumability and checkpointing (--resume, data/bis/ingestion_state.json)
   - Atomic dataset writes and automatic backups
2. Keyword Search Ingestion (review-service searchKnowStandards)

Extracts, normalizes, deduplicates by standardNumber, and safely merges records
into data/bis/standards.json without modifying data/seed/standards.json.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Optional

# Ensure project root is in sys.path when invoked directly
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pipeline.scrapers.bis_api import (
    BISApiClient,
    BISCatalogueResult,
    BISRequestError,
    BISSearchResult,
)

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_TERMS = [
    "cement",
    "steel",
    "electrical",
    "transformer",
    "cable",
    "plastic",
    "textile",
    "food",
    "construction",
    "automobile",
]

DEFAULT_OUTPUT_PATH = _PROJECT_ROOT / "data" / "bis" / "standards.json"
DEFAULT_STATE_PATH = _PROJECT_ROOT / "data" / "bis" / "ingestion_state.json"
DEFAULT_SEED_PATH = _PROJECT_ROOT / "data" / "seed" / "standards.json"


def normalize_bis_record(
    raw: dict[str, Any],
    query: Optional[str] = None,
    dept_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Extract and normalize standard fields from a raw BIS record (search or catalogue).

    Only actual values present in the BIS response are captured.
    Missing or empty values remain None or appropriate empty types.
    """
    raw_std_no = raw.get("standardNumber")
    is_number = str(raw_std_no).strip() if raw_std_no and str(raw_std_no).strip() else None

    raw_title = raw.get("standardTitle") or raw.get("standardName")
    title = str(raw_title).strip() if raw_title and str(raw_title).strip() else ""

    raw_hi = raw.get("standardNameInHindi")
    title_hindi = str(raw_hi).strip() if raw_hi and str(raw_hi).strip() else None

    standard_id = raw.get("standardId")
    department_id = dept_info.get("departmentId") if dept_info else raw.get("departmentId")
    department_alias = dept_info.get("deptAliasName") if dept_info else raw.get("deptAliasName")
    department_name = dept_info.get("deptName") if dept_info else raw.get("deptName")
    committee_id = raw.get("committeeId")
    published_on = raw.get("publishedOn")

    # Handle validity/review date casing & variants
    valid_upto = (
        raw.get("reviewOn")
        or (raw.get("validUpto") if "validUpto" in raw else raw.get("validupto"))
    )

    revision_count = raw.get("noOfRevision")
    aspect = raw.get("typeOfStandardName")
    degree_of_equivalence = raw.get("equivalenceTypeName")

    withdraw_status = raw.get("withdrawStatus")
    withdraw_on = raw.get("withdrawOn")

    withdrawn = False
    if withdraw_status not in (None, 0, "0"):
        withdrawn = True
    elif withdraw_on is not None:
        withdrawn = True
    elif raw.get("withdrawn") is True:
        withdrawn = True

    is_status = raw.get("isStatus")
    matched_standard = raw.get("matched_standard") or is_number

    matched_queries: list[str] = []
    if query:
        matched_queries.append(query)
    elif department_alias:
        matched_queries.append(department_alias)

    return {
        "is_number": is_number,
        "title": title,
        "title_hindi": title_hindi,
        "standard_id": standard_id,
        "department_id": department_id,
        "department_alias": department_alias,
        "department_name": department_name,
        "committee_id": committee_id,
        "published_on": published_on,
        "valid_upto": valid_upto,
        "revision_count": revision_count,
        "aspect": aspect,
        "degree_of_equivalence": degree_of_equivalence,
        "withdraw_status": withdraw_status,
        "withdrawn": withdrawn,
        "is_status": is_status,
        "matched_standard": matched_standard,
        "matched_queries": matched_queries,
        "source": "BIS Know Your Standard / BIS Published Standards Catalogue",
        "source_url": None,
    }


def get_dedup_key(record: dict[str, Any]) -> str:
    """
    Determine primary deduplication key for a standard.
    Prefers normalized is_number, falls back to standard_id or title.
    """
    is_num = record.get("is_number")
    if is_num:
        return f"NUM:{is_num.strip().upper()}"
    std_id = record.get("standard_id")
    if std_id is not None:
        return f"ID:{std_id}"
    title = record.get("title", "")
    return f"TITLE:{title.strip().upper()}"


def create_backup(target_path: Path) -> Optional[Path]:
    """
    Create a backup of the existing target file before modifying it.
    """
    if not target_path.exists():
        return None
    backup_path = target_path.with_name(target_path.name + ".bak")
    try:
        shutil.copy2(target_path, backup_path)
        logger.info("Backup created at %s", backup_path)
        return backup_path
    except Exception as exc:
        logger.warning("Could not create backup of %s: %s", target_path, exc)
        return None


def load_existing_dataset(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    Load existing standards from disk to safely merge and prevent accidental data loss.
    """
    if not path.exists():
        return {}, {
            "source": "BIS Know Your Standard / BIS Published Standards Catalogue",
            "search_terms": [],
            "departments_ingested": [],
            "total_records_collected": 0,
            "unique_standards": 0,
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            meta = data.get("metadata", {})
            standards_list = data.get("standards", [])
            standards_map = {get_dedup_key(s): s for s in standards_list}
            return standards_map, meta
    except Exception as exc:
        logger.warning("Could not read existing dataset at %s: %s", path, exc)
        return {}, {}


def save_dataset_atomic(
    output_path: Path,
    unique_standards: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    """
    Safely persist the merged dataset to JSON using an atomic write pattern.
    Writes to a temporary file first, then atomically replaces the target file.
    """
    target_file = Path(output_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_file.with_name(target_file.name + ".tmp")

    metadata["unique_standards"] = len(unique_standards)
    metadata["ingested_at"] = datetime.now(timezone.utc).isoformat()

    dataset = {
        "metadata": metadata,
        "standards": list(unique_standards.values()),
    }

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    os.replace(temp_file, target_file)


def load_ingestion_state(path: Path) -> dict[str, Any]:
    """
    Load checkpoint state from disk if available, otherwise return default initial state.
    """
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
                return state
        except Exception as exc:
            logger.warning("Failed to parse ingestion state from %s: %s", path, exc)

    return {
        "version": 1,
        "department_currently_processing": None,
        "department_code": None,
        "current_offset": 0,
        "page_size": 100,
        "total_records_reported": 0,
        "records_processed_in_department": 0,
        "completed_departments": [],
        "failed_departments": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "last_successful_request": None,
        "stats": {
            "raw_records_collected": 0,
            "new_unique_standards": 0,
            "duplicates_merged": 0,
        },
    }


def save_ingestion_state(path: Path, state: dict[str, Any]) -> None:
    """
    Persist checkpoint state atomically.
    """
    target_file = Path(path)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_file.with_name(target_file.name + ".tmp")

    state["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    os.replace(temp_file, target_file)


def ingest_bis_department(
    department_code: str,
    client: Optional[BISApiClient] = None,
    limit: int = 100,
    max_pages: Optional[int] = None,
    resume: bool = False,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    """
    Ingest standards for an official BIS Technical Department using paginated catalogue API.
    """
    api_client = client or BISApiClient()
    code_upper = department_code.strip().upper()

    print("\n==================================================")
    print("BIS Department Ingestion Started")
    print(f"Target Department: {code_upper}")
    print(f"Batch Limit: {limit}")
    print(f"Max Pages: {max_pages or 'All'}")
    print(f"Resume: {'ENABLED' if resume else 'DISABLED'}")
    print("==================================================")

    # 1. Fetch official departments directory
    try:
        depts = api_client.get_website_departments()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch BIS technical departments: {exc}") from exc

    dept = next(
        (
            d
            for d in depts
            if d.get("deptAliasName", "").strip().upper() == code_upper
            or d.get("deptName", "").strip().upper() == code_upper
        ),
        None,
    )

    if not dept:
        valid_aliases = [d.get("deptAliasName") for d in depts if d.get("deptAliasName")]
        raise ValueError(
            f"Department '{department_code}' not found. Valid department codes: {valid_aliases}"
        )

    dept_alias = dept.get("deptAliasName", code_upper)
    dept_name = dept.get("deptName", dept_alias)
    enc_id = dept.get("encryptedDepartmentId")
    if not enc_id:
        raise ValueError(f"No encryptedDepartmentId found for department {dept_alias}")

    print(f"Found Department: {dept_alias} - {dept_name}")
    print(f"Department ID: {dept.get('departmentId')}")

    # 2. Backup and load existing dataset
    create_backup(Path(output_path))
    unique_standards, meta = load_existing_dataset(Path(output_path))
    initial_unique_count = len(unique_standards)
    print(f"Existing unique standards in dataset: {initial_unique_count}")

    # 3. Load or initialize state
    state = load_ingestion_state(Path(state_path))
    offset = 0
    if resume and state.get("department_code") == dept_alias and state.get("current_offset", 0) > 0:
        offset = state["current_offset"]
        print(f"Resuming department {dept_alias} at offset {offset}")

    state["department_currently_processing"] = dept_name
    state["department_code"] = dept_alias
    state["encrypted_department_id"] = enc_id
    state["page_size"] = limit

    page = 1
    total_raw_collected = 0
    new_unique_count = 0
    duplicates_merged = 0

    while True:
        print(f"\n--- Requesting Page {page} (offset={offset}, limit={limit}) ---")
        try:
            catalogue_res: BISCatalogueResult = (
                api_client.get_website_ps_tech_department_wise(
                    offset=offset,
                    limit=limit,
                    enc_department_id=enc_id,
                )
            )
        except Exception as exc:
            print(f"Error requesting page {page}: {exc}")
            state["failed_departments"][dept_alias] = str(exc)
            save_ingestion_state(Path(state_path), state)
            break

        batch_records = catalogue_res.records
        raw_batch_len = len(batch_records)
        total_raw_collected += raw_batch_len
        total_dept_standards = catalogue_res.total_records

        state["total_records_reported"] = total_dept_standards
        state["last_successful_request"] = datetime.now(timezone.utc).isoformat()

        print(f"HTTP Status: {catalogue_res.status_code}")
        print(f"Records Returned in Page: {raw_batch_len}")
        print(f"Total Department Standards Reported: {total_dept_standards}")

        batch_new_unique = 0
        batch_duplicates = 0

        for raw_item in batch_records:
            normalized = normalize_bis_record(raw_item, query=None, dept_info=dept)
            key = get_dedup_key(normalized)

            if key not in unique_standards:
                unique_standards[key] = normalized
                new_unique_count += 1
                batch_new_unique += 1
            else:
                existing = unique_standards[key]
                duplicates_merged += 1
                batch_duplicates += 1

                # Merge matched_queries
                if dept_alias not in existing.get("matched_queries", []):
                    existing.setdefault("matched_queries", []).append(dept_alias)

                # Merge non-null catalogue attributes
                for field_name, val in normalized.items():
                    if val is not None and (
                        existing.get(field_name) is None
                        or field_name
                        in (
                            "aspect",
                            "revision_count",
                            "department_alias",
                            "department_name",
                            "department_id",
                            "valid_upto",
                        )
                    ):
                        existing[field_name] = val

        print(f"New unique in this page: {batch_new_unique}")
        print(f"Duplicates merged in this page: {batch_duplicates}")
        print(f"Total unique standards so far: {len(unique_standards)}")

        # Update and save checkpoint and dataset atomically
        state["current_offset"] = offset + raw_batch_len
        state["records_processed_in_department"] = offset + raw_batch_len
        save_ingestion_state(Path(state_path), state)
        meta["total_records_collected"] = (
            meta.get("total_records_collected", 0) + raw_batch_len
        )
        save_dataset_atomic(Path(output_path), unique_standards, meta)

        # Termination checks
        if raw_batch_len == 0 or raw_batch_len < limit:
            print("Reached final page (fewer records than limit returned).")
            break

        if offset + raw_batch_len >= total_dept_standards:
            print("Reached total reported department count.")
            break

        if max_pages and page >= max_pages:
            print(f"Reached max pages limit ({max_pages}). Stopping safely.")
            break

        offset += raw_batch_len
        page += 1

    # Update metadata
    departments_ingested = set(meta.get("departments_ingested", []))
    departments_ingested.add(dept_alias)
    meta["departments_ingested"] = sorted(departments_ingested)
    save_dataset_atomic(Path(output_path), unique_standards, meta)

    if not max_pages or page >= (max_pages or 1):
        if dept_alias not in state["completed_departments"]:
            state["completed_departments"].append(dept_alias)
        state["department_currently_processing"] = None
        state["current_offset"] = 0
        save_ingestion_state(Path(state_path), state)

    save_dataset_atomic(Path(output_path), unique_standards, meta)

    print("\n==================================================")
    print("Department Ingestion Run Summary:")
    print(f"Department: {dept_alias} ({dept_name})")
    print(f"Pages processed: {page}")
    print(f"Raw records collected in this run: {total_raw_collected}")
    print(f"New unique standards added: {new_unique_count}")
    print(f"Duplicates merged: {duplicates_merged}")
    print(f"Previous unique standards preserved: {initial_unique_count}")
    print(f"Total unique standards in dataset now: {len(unique_standards)}")
    print(f"Saved to: {output_path}")
    print(f"Checkpoint: {state_path}")
    print("==================================================")

    return {
        "metadata": meta,
        "standards": list(unique_standards.values()),
        "run_stats": {
            "department": dept_alias,
            "raw_collected": total_raw_collected,
            "new_unique": new_unique_count,
            "duplicates_merged": duplicates_merged,
            "total_unique": len(unique_standards),
        },
    }


def ingest_all_departments(
    client: Optional[BISApiClient] = None,
    limit: int = 100,
    max_pages_per_dept: Optional[int] = None,
    resume: bool = False,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    """
    Ingest all official BIS technical departments sequentially using paginated catalogue API.

    Resumable via state_path checkpoint. Saves progress after each page and department.
    """
    api_client = client or BISApiClient()
    output_target = Path(output_path)
    state_target = Path(state_path)

    # 1. Backup existing standards
    create_backup(output_target)

    # 2. Load existing dataset
    unique_standards, meta = load_existing_dataset(output_target)
    initial_unique_count = len(unique_standards)

    # 3. Load or initialize checkpoint state
    state = load_ingestion_state(state_target) if resume else {
        "version": 1,
        "department_currently_processing": None,
        "department_code": None,
        "current_offset": 0,
        "page_size": limit,
        "total_records_reported": 0,
        "records_processed_in_department": 0,
        "completed_departments": [],
        "failed_departments": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "last_successful_request": None,
        "stats": {
            "raw_records_collected": 0,
            "new_unique_standards": 0,
            "duplicates_merged": 0,
        },
    }

    # 4. Fetch official departments directory
    try:
        departments = api_client.get_website_departments()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch BIS technical departments: {exc}") from exc

    total_depts = len(departments)
    completed_set = set(state.get("completed_departments", []))

    print("\n========================================")
    print("BIS FULL CATALOGUE INGESTION")
    print("========================================")
    print(f"Departments discovered: {total_depts}")
    print(f"Already completed: {len(completed_set)}")
    print(f"Existing unique standards in dataset: {initial_unique_count}")
    print(f"Batch limit per request: {limit}")
    print(f"Resume mode: {'ENABLED' if resume else 'DISABLED'}")
    print("========================================\n")

    total_raw_collected_run = 0
    total_new_standards_run = 0
    total_duplicates_merged_run = 0

    for idx, dept in enumerate(departments, 1):
        dept_alias = dept.get("deptAliasName", f"DEPT_{idx}")
        dept_name = dept.get("deptName", dept_alias)
        enc_id = dept.get("encryptedDepartmentId")

        if not enc_id:
            print(f"[{idx}/{total_depts}] {dept_alias}: Missing encryptedDepartmentId. Skipping.")
            continue

        # Check if already completed in resume mode
        if resume and dept_alias in completed_set:
            print(f"[{idx}/{total_depts}] {dept_alias} ({dept_name}): Already completed. Skipping.")
            continue

        print(f"\n[{idx}/{total_depts}] {dept_alias} - {dept_name}")

        # Check in-progress offset if resuming this specific department
        offset = 0
        if resume and state.get("department_code") == dept_alias and state.get("current_offset", 0) > 0:
            offset = state["current_offset"]
            print(f"  Resuming {dept_alias} from offset {offset}")

        state["department_currently_processing"] = dept_name
        state["department_code"] = dept_alias
        state["encrypted_department_id"] = enc_id
        state["current_offset"] = offset
        save_ingestion_state(state_target, state)

        dept_raw = 0
        dept_new = 0
        dept_dups = 0
        dept_failed = False
        page = 1

        while True:
            try:
                catalogue_res: BISCatalogueResult = (
                    api_client.get_website_ps_tech_department_wise(
                        offset=offset,
                        limit=limit,
                        enc_department_id=enc_id,
                    )
                )
            except Exception as exc:
                print(f"  [!] Failed fetching {dept_alias} at offset {offset}: {exc}")
                state["failed_departments"][dept_alias] = str(exc)
                state["last_updated_at"] = datetime.now(timezone.utc).isoformat()
                save_ingestion_state(state_target, state)
                dept_failed = True
                break

            records = catalogue_res.records
            raw_len = len(records)
            dept_raw += raw_len
            total_raw_collected_run += raw_len
            total_reported = catalogue_res.total_records

            state["total_records_reported"] = total_reported
            state["last_successful_request"] = datetime.now(timezone.utc).isoformat()

            page_new = 0
            page_dups = 0

            for raw_item in records:
                normalized = normalize_bis_record(raw_item, query=None, dept_info=dept)
                key = get_dedup_key(normalized)

                if key not in unique_standards:
                    unique_standards[key] = normalized
                    dept_new += 1
                    total_new_standards_run += 1
                    page_new += 1
                else:
                    existing = unique_standards[key]
                    dept_dups += 1
                    total_duplicates_merged_run += 1
                    page_dups += 1

                    if dept_alias not in existing.get("matched_queries", []):
                        existing.setdefault("matched_queries", []).append(dept_alias)

                    for field_name, val in normalized.items():
                        if val is not None and (
                            existing.get(field_name) is None
                            or field_name
                            in (
                                "aspect",
                                "revision_count",
                                "department_alias",
                                "department_name",
                                "department_id",
                                "valid_upto",
                            )
                        ):
                            existing[field_name] = val

            print(
                f"  Fetching offset {offset:5d} / {total_reported:5d} -> {raw_len:3d} records "
                f"(New: {page_new:3d}, Merged: {page_dups:3d} | Total unique: {len(unique_standards)})"
            )

            # Update checkpoint
            offset += raw_len
            state["current_offset"] = offset
            state["records_processed_in_department"] = offset
            state["stats"]["raw_records_collected"] = (
                state["stats"].get("raw_records_collected", 0) + raw_len
            )
            state["stats"]["new_unique_standards"] = (
                state["stats"].get("new_unique_standards", 0) + page_new
            )
            state["stats"]["duplicates_merged"] = (
                state["stats"].get("duplicates_merged", 0) + page_dups
            )
            save_ingestion_state(state_target, state)
            meta["total_records_collected"] = (
                meta.get("total_records_collected", 0) + raw_len
            )
            save_dataset_atomic(output_target, unique_standards, meta)

            # Check termination
            if raw_len == 0 or raw_len < limit:
                break
            if offset >= total_reported:
                break
            if max_pages_per_dept and page >= max_pages_per_dept:
                break

            page += 1

        if not dept_failed:
            if dept_alias not in state["completed_departments"]:
                state["completed_departments"].append(dept_alias)
                completed_set.add(dept_alias)
            if dept_alias in state["failed_departments"]:
                del state["failed_departments"][dept_alias]

            state["department_currently_processing"] = None
            state["current_offset"] = 0
            save_ingestion_state(state_target, state)

            # Update dataset metadata and save atomically after each department
            deps_in_meta = set(meta.get("departments_ingested", []))
            deps_in_meta.add(dept_alias)
            meta["departments_ingested"] = sorted(deps_in_meta)
            save_dataset_atomic(output_target, unique_standards, meta)

            print(f"  --> {dept_alias} completed! New: {dept_new}, Duplicates: {dept_dups}")

    # Final summary
    failed_list = list(state.get("failed_departments", {}).keys())
    completed_count = len(state.get("completed_departments", []))

    # Verify seed standards are untouched
    seed_preserved = False
    if DEFAULT_SEED_PATH.exists():
        try:
            with open(DEFAULT_SEED_PATH, "r", encoding="utf-8") as f_seed:
                seeds = json.load(f_seed)
                seed_preserved = len(seeds) == 57
        except Exception:
            seed_preserved = False

    print("\n========================================")
    print("FINAL SUMMARY")
    print("========================================")
    print(f"Departments completed: {completed_count}/{total_depts}")
    if failed_list:
        print(f"Departments failed: {failed_list}")
    else:
        print("Departments failed: None")
    print(f"Raw records fetched in this run: {total_raw_collected_run}")
    print(f"Total unique standards in dataset: {len(unique_standards)}")
    print(f"New standards added: {total_new_standards_run}")
    print(f"Duplicates merged: {total_duplicates_merged_run}")
    print("Existing BIS records preserved: YES")
    print(f"Seed records preserved (57 standards): {'YES' if seed_preserved else 'NO'}")
    print(f"\nOutput:\n{output_target}")
    print(f"\nCheckpoint:\n{state_target}")
    print("========================================\n")

    return {
        "metadata": meta,
        "standards": list(unique_standards.values()),
        "run_stats": {
            "departments_completed": completed_count,
            "departments_failed": failed_list,
            "raw_collected": total_raw_collected_run,
            "new_unique": total_new_standards_run,
            "duplicates_merged": total_duplicates_merged_run,
            "total_unique": len(unique_standards),
            "seed_preserved": seed_preserved,
        },
    }


def ingest_bis_standards(
    search_terms: list[str],
    client: Optional[BISApiClient] = None,
    limit: Optional[int] = None,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """
    Run keyword search ingestion across search terms, safely merging with existing records.
    """
    api_client = client or BISApiClient()
    active_terms = search_terms[:limit] if limit and limit > 0 else search_terms

    create_backup(Path(output_path))
    unique_standards, meta = load_existing_dataset(Path(output_path))
    initial_unique = len(unique_standards)
    existing_terms = set(meta.get("search_terms", []))

    print("BIS ingestion started")
    print(f"Existing unique standards in dataset: {initial_unique}")
    total_raw_records = 0

    for term in active_terms:
        print(f"\nSearch: {term}")
        try:
            result: BISSearchResult = api_client.search(term)
        except Exception as exc:
            print(f"Error querying term {term!r}: {exc}")
            continue

        raw_count = len(result.records)
        total_raw_records += raw_count
        new_unique_in_search = 0

        for raw_item in result.records:
            normalized = normalize_bis_record(raw_item, query=term)
            key = get_dedup_key(normalized)

            if key not in unique_standards:
                unique_standards[key] = normalized
                new_unique_in_search += 1
            else:
                existing = unique_standards[key]
                if term not in existing.get("matched_queries", []):
                    existing.setdefault("matched_queries", []).append(term)
                for field_name, val in normalized.items():
                    if existing.get(field_name) is None and val is not None:
                        existing[field_name] = val

        existing_terms.add(term)
        print(f"HTTP: {result.status_code}")
        print(f"Results: {raw_count}")
        print(f"New unique: {new_unique_in_search}")
        print(f"Total unique so far: {len(unique_standards)}")

    meta["search_terms"] = sorted(existing_terms)
    meta["total_records_collected"] = (
        meta.get("total_records_collected", 0) + total_raw_records
    )

    save_dataset_atomic(Path(output_path), unique_standards, meta)

    print(f"\nFinal:")
    print(f"Raw records collected in run: {total_raw_records}")
    print(f"Total unique standards in dataset: {len(unique_standards)}")
    print(f"\nSaved to:\n{output_path}")

    return {
        "metadata": meta,
        "standards": list(unique_standards.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest standards from official BIS API")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all official BIS technical departments sequentially",
    )
    parser.add_argument(
        "--department",
        type=str,
        default=None,
        help="Official BIS department code to ingest via catalogue endpoint (e.g. --department CED)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume ingestion from state checkpoint",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum pages to ingest per department (e.g. --max-pages 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Records per page in department mode or search term limit (default: 100)",
    )
    parser.add_argument(
        "--terms",
        type=str,
        default=None,
        help="Comma-separated search terms for keyword mode (e.g. --terms cement,steel)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Output JSON file path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=str(DEFAULT_STATE_PATH),
        help=f"Checkpoint state file path (default: {DEFAULT_STATE_PATH})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between successive API requests (default: 1.5)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per request on failure (default: 3)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    client = BISApiClient(
        rate_limit_delay=args.delay,
        max_retries=args.max_retries,
    )

    if args.all:
        ingest_all_departments(
            client=client,
            limit=args.limit,
            max_pages_per_dept=args.max_pages,
            resume=args.resume,
            output_path=Path(args.output),
            state_path=Path(args.state_file),
        )
    elif args.department:
        ingest_bis_department(
            department_code=args.department,
            client=client,
            limit=args.limit,
            max_pages=args.max_pages,
            resume=args.resume,
            output_path=Path(args.output),
            state_path=Path(args.state_file),
        )
    else:
        terms = (
            [t.strip() for t in args.terms.split(",") if t.strip()]
            if args.terms
            else DEFAULT_SEARCH_TERMS
        )
        ingest_bis_standards(
            search_terms=terms,
            client=client,
            limit=args.limit if args.terms or (not args.department and not args.all) else None,
            output_path=Path(args.output),
        )
