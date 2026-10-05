# -*- coding: utf-8 -*-
"""Versioned terminology. Seed records stay DRAFT until an admin revision approves them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).resolve().parent / "seeds" / "terminology.json"
USABLE_STATUSES = frozenset({"APPROVED"})


class SeedPolicyError(RuntimeError):
    pass


def load_seed() -> list[dict[str, Any]]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]
    for entry in entries:
        status = entry["governance"]["status"]
        if status != "DRAFT":
            raise SeedPolicyError(f"{entry['term_id']} seed status must be DRAFT, found {status}")
        if entry["governance"].get("approved_by") or entry["governance"].get("approved_at"):
            raise SeedPolicyError(f"{entry['term_id']} seed must not carry approval")
    return entries


def _excerpt_present(entry: dict[str, Any], root: Path) -> bool:
    for evidence in entry.get("evidence") or []:
        path = root / evidence["path"]
        excerpt = evidence.get("excerpt") or ""
        if not excerpt:
            return False
        if not path.is_file() or excerpt not in path.read_text(encoding="utf-8"):
            return False
    return True


def apply_revisions(entries: list[dict[str, Any]], revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = {entry["term_id"]: json.loads(json.dumps(entry)) for entry in entries}
    ordered = sorted(revisions, key=lambda item: item.get("approved_at") or item.get("created_at") or "")
    for revision in ordered:
        if revision.get("kind") not in {None, "term"}:
            continue
        term_id = revision.get("term_id")
        if term_id not in current:
            continue
        snapshot = revision.get("definition_snapshot")
        if isinstance(snapshot, dict):
            merged = json.loads(json.dumps(snapshot))
            merged["term_id"] = term_id
            current[term_id] = merged
        governance = current[term_id].setdefault("governance", {})
        if revision.get("status"):
            governance["status"] = revision["status"]
        governance["version"] = revision.get("version", governance.get("version"))
        governance["approved_by"] = revision.get("approved_by")
        governance["approved_at"] = revision.get("approved_at")
        governance["revision_id"] = revision.get("revision_id")
    return list(current.values())


def effective_entries(entries: list[dict[str, Any]], *, root: Path | None = None) -> list[dict[str, Any]]:
    base = root or Path(__file__).resolve().parents[2]
    output = []
    for entry in entries:
        copied = json.loads(json.dumps(entry))
        governance = copied.setdefault("governance", {})
        if not _excerpt_present(copied, base):
            governance["source_changed"] = True
            if governance.get("status") == "APPROVED":
                governance["status"] = "REVIEW_DUE"
        else:
            governance["source_changed"] = False
        output.append(copied)
    return output


def lookup(entries: list[dict[str, Any]], term_id: str | None) -> dict[str, Any] | None:
    if not term_id:
        return None
    wanted = term_id.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    for entry in entries:
        names = [entry["term_id"], entry.get("display_name", "")]
        names.extend(entry.get("aliases") or [])
        for name in names:
            token = str(name).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
            if token == wanted:
                return entry
    return None


def is_official(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    governance = entry.get("governance") or {}
    return governance.get("status") in USABLE_STATUSES and bool(governance.get("approved_by")) and bool(
        governance.get("approved_at")
    )
