# -*- coding: utf-8 -*-
"""Approved-document search. Drafts are invisible to the copilot."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).resolve().parent / "seeds" / "knowledge.json"


class SeedPolicyError(RuntimeError):
    pass


def apply_revisions(documents: list[dict[str, Any]], revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay admin document revisions. Seed files stay DRAFT on disk."""
    current = {document["document_id"]: json.loads(json.dumps(document)) for document in documents}
    ordered = sorted(revisions, key=lambda item: item.get("approved_at") or item.get("created_at") or "")
    for revision in ordered:
        if revision.get("kind") != "document":
            continue
        document_id = revision.get("document_id")
        if document_id not in current:
            continue
        snapshot = revision.get("document_snapshot")
        if isinstance(snapshot, dict):
            merged = json.loads(json.dumps(snapshot))
            merged["document_id"] = document_id
            current[document_id] = merged
        if revision.get("status"):
            current[document_id]["approval_status"] = revision["status"]
        if revision.get("approved_by"):
            current[document_id]["approved_by"] = revision["approved_by"]
        if revision.get("approved_at"):
            current[document_id]["approved_at"] = revision["approved_at"]
        if revision.get("version"):
            current[document_id]["version"] = revision["version"]
    return list(current.values())


def load_seed() -> dict[str, Any]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for document in payload["documents"]:
        if document["approval_status"] != "DRAFT":
            raise SeedPolicyError(f"{document['document_id']} seed must be DRAFT")
    return payload


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}


def _approved(document: dict[str, Any], now: datetime) -> bool:
    if document.get("approval_status") != "APPROVED":
        return False
    if not document.get("approved_by") or not document.get("approved_at"):
        return False
    effective_to = document.get("effective_to")
    if effective_to:
        try:
            if now.date().isoformat() > effective_to:
                return False
        except Exception:
            return False
    return True


def search(documents: list[dict[str, Any]], query: str, *, now: datetime, limit: int = 4) -> list[dict[str, Any]]:
    wanted = _tokens(query)
    scored = []
    for document in documents:
        if not _approved(document, now):
            continue
        haystack = _tokens(f"{document.get('title', '')} {document.get('content', '')}")
        if not wanted:
            continue
        overlap = wanted & haystack
        if not overlap:
            continue
        scored.append((len(overlap), document))
    scored.sort(key=lambda item: (-item[0], item[1]["document_id"]))
    results = []
    for _score, document in scored[:limit]:
        results.append(
            {
                "document_id": document["document_id"],
                "title": document["title"],
                "collection": document["collection"],
                "source_uri": document["source_uri"],
                "source_revision": document.get("source_revision"),
                "approval_status": document["approval_status"],
                "version": document.get("version"),
                "excerpt": (document.get("content") or "")[:1200],
            }
        )
    return results
