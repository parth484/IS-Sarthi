"""
Content-hash change detection.

This is what turns a daily full crawl from unaffordable into routine. A crawl
touches every record but only records whose *meaningful* fields changed enter
the processing chain.

Two hashes are kept rather than one, because the expensive downstream work is
not uniform. Re-embedding costs orders of magnitude more than a Postgres
UPDATE, so scope text gets its own hash: a status change updates the row and
the graph without touching the GPU.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ChangeType(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    METADATA = "metadata"          # title/year/status/amendments moved
    REFERENCES = "references"      # normative reference set moved -> graph rebuild
    SCOPE = "scope"                # scope text moved -> re-embed
    CERTIFICATION = "certification"
    WITHDRAWN = "withdrawn"        # treated specially: user-facing warning


@dataclass
class ChangeResult:
    change_type: ChangeType
    content_hash: str
    scope_hash: str
    changed_fields: list[str]
    previous: Optional[dict] = None

    @property
    def needs_processing(self) -> bool:
        return self.change_type != ChangeType.UNCHANGED

    @property
    def needs_reembedding(self) -> bool:
        return self.change_type in (ChangeType.NEW, ChangeType.SCOPE)

    @property
    def needs_graph_update(self) -> bool:
        return self.change_type in (
            ChangeType.NEW,
            ChangeType.REFERENCES,
            ChangeType.WITHDRAWN,
        )


class ChangeDetector:
    CONTENT_FIELDS = ("title", "year", "status", "division", "amendments",
                      "normative_references", "certification", "supersedes")

    @staticmethod
    def _hash(payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    def content_hash(self, record: dict) -> str:
        payload = {}
        for key in self.CONTENT_FIELDS:
            value = record.get(key)
            # Reference and amendment ordering is an artefact of extraction,
            # not a meaningful change -- sort so a reshuffled list does not
            # trigger a spurious graph rebuild.
            if isinstance(value, list):
                value = sorted(value, key=lambda item: json.dumps(item, sort_keys=True, default=str))
            payload[key] = value
        return self._hash(payload)

    def scope_hash(self, record: dict) -> str:
        scope = (record.get("scope") or "").strip()
        title = (record.get("title") or "").strip()
        # Title participates because it is part of the embedded text.
        return self._hash({"title": title, "scope": scope})

    def compare(self, record: dict, stored: Optional[dict]) -> ChangeResult:
        new_content = self.content_hash(record)
        new_scope = self.scope_hash(record)

        if stored is None:
            return ChangeResult(ChangeType.NEW, new_content, new_scope, ["*"])

        if stored.get("content_hash") == new_content and stored.get("scope_hash") == new_scope:
            return ChangeResult(
                ChangeType.UNCHANGED, new_content, new_scope, [], previous=stored
            )

        changed = [
            field
            for field in self.CONTENT_FIELDS
            if self._normalized(record.get(field)) != self._normalized(stored.get(field))
        ]
        if stored.get("scope_hash") != new_scope:
            changed.append("scope")

        # Ordering matters: a withdrawal is the most user-consequential change
        # and must not be masked by a co-occurring title edit.
        if record.get("status") in ("withdrawn", "superseded") and stored.get(
            "status"
        ) not in ("withdrawn", "superseded"):
            change_type = ChangeType.WITHDRAWN
        elif "scope" in changed:
            change_type = ChangeType.SCOPE
        elif "normative_references" in changed:
            change_type = ChangeType.REFERENCES
        elif "certification" in changed:
            change_type = ChangeType.CERTIFICATION
        else:
            change_type = ChangeType.METADATA

        return ChangeResult(change_type, new_content, new_scope, changed, previous=stored)

    @staticmethod
    def _normalized(value: Any) -> Any:
        if isinstance(value, list):
            return sorted(json.dumps(item, sort_keys=True, default=str) for item in value)
        if isinstance(value, str):
            return value.strip()
        return value


detector = ChangeDetector()
