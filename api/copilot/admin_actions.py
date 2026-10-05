# -*- coding: utf-8 -*-
"""Admin dictionary actions. Chat cannot call these."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from copilot import dictionary as dictionary_mod
from copilot import knowledge as knowledge_mod
from copilot.store import LedgerUnavailable


def _entries(store) -> list[dict[str, Any]]:
    try:
        revisions = store.list_revisions("term")
    except LedgerUnavailable:
        revisions = []
    return dictionary_mod.effective_entries(dictionary_mod.apply_revisions(dictionary_mod.load_seed(), revisions))


def _documents(store) -> list[dict[str, Any]]:
    try:
        revisions = store.list_revisions("document")
    except LedgerUnavailable:
        revisions = []
    return knowledge_mod.apply_revisions(knowledge_mod.load_seed()["documents"], revisions)


def snapshot(store, *, config, now: datetime) -> dict[str, Any]:
    entries = _entries(store)
    documents = _documents(store)
    ledger = None
    ledger_error = None
    month_key = None
    if config.billing_timezone:
        from copilot.periods import TimezoneUnconfirmed, billing_month_key, next_month_start

        try:
            month_key = billing_month_key(config.billing_timezone, now)
            reset = next_month_start(config.billing_timezone, now)
            ledger = store.month_view(month_key)
            ledger["month_key"] = month_key
            ledger["reset_date"] = reset
            ledger["cap_micro"] = config.model_cap_micro()
            ledger["remaining_micro"] = config.model_cap_micro() - ledger["spent"] - ledger["reserved"]
            spent = ledger["spent"]
            ledger["warnings"] = []
            if spent >= 12_000_000:
                ledger["warnings"].append("Model spend is at or above USD 12.")
            elif spent >= 10_000_000:
                ledger["warnings"].append("Model spend is at or above USD 10.")
        except (TimezoneUnconfirmed, LedgerUnavailable) as exc:
            ledger_error = str(exc)
    else:
        ledger_error = "COPILOT_BILLING_TIMEZONE is unset"
    review_due = []
    for entry in entries:
        governance = entry["governance"]
        if governance.get("status") in {"REVIEW_DUE", "DRAFT"}:
            review_due.append(entry["term_id"])
    return {
        "terms": entries,
        "documents": documents,
        "review_due": review_due,
        "ledger": ledger,
        "ledger_error": ledger_error,
        "paused": bool(getattr(store, "paused", False)),
        "enabled": config.enabled,
        "feedback": list(getattr(store, "feedback", [])),
        "suggestions": list(getattr(store, "suggestions", [])),
        "audit_count": len(getattr(store, "audit", [])),
    }


def approve_term(store, *, term_id: str, actor: str, now: datetime) -> dict[str, Any]:
    current = {entry["term_id"]: entry for entry in _entries(store)}
    entry = current.get(term_id)
    if entry is None:
        raise ValueError("unknown term")
    if entry["governance"].get("source_changed"):
        raise ValueError("source evidence changed; review the draft before approval")
    snapshot_body = dict(entry)
    snapshot_body["governance"] = dict(entry["governance"])
    snapshot_body["governance"]["status"] = "APPROVED"
    snapshot_body["governance"]["approved_by"] = actor
    snapshot_body["governance"]["approved_at"] = now.isoformat()
    snapshot_body["governance"]["version"] = int(entry["governance"].get("version") or 1) + 1
    revision = {
        "revision_id": "rev_" + uuid.uuid4().hex[:16],
        "kind": "term",
        "term_id": term_id,
        "status": "APPROVED",
        "version": snapshot_body["governance"]["version"],
        "approved_by": actor,
        "approved_at": now.isoformat(),
        "created_at": now.isoformat(),
        "actor": actor,
        "definition_snapshot": snapshot_body,
    }
    return store.add_revision(revision)


def save_definition(store, *, term_id: str, actor: str, definition: str, now: datetime) -> dict[str, Any]:
    """Save a draft revision. Chat still refuses the term until a later approval."""
    text = " ".join((definition or "").split())
    if not text or len(text) > 2000:
        raise ValueError("definition text is required")
    current = {entry["term_id"]: entry for entry in _entries(store)}
    entry = current.get(term_id)
    if entry is None:
        raise ValueError("unknown term")
    snapshot_body = dict(entry)
    snapshot_body["definition"] = text
    snapshot_body["governance"] = dict(entry["governance"])
    snapshot_body["governance"]["status"] = "DRAFT"
    snapshot_body["governance"]["approved_by"] = None
    snapshot_body["governance"]["approved_at"] = None
    snapshot_body["governance"]["version"] = int(entry["governance"].get("version") or 1) + 1
    revision = {
        "revision_id": "rev_" + uuid.uuid4().hex[:16],
        "kind": "term",
        "term_id": term_id,
        "status": "DRAFT",
        "version": snapshot_body["governance"]["version"],
        "approved_by": None,
        "approved_at": None,
        "created_at": now.isoformat(),
        "actor": actor,
        "definition_snapshot": snapshot_body,
    }
    return store.add_revision(revision)


def deprecate_term(store, *, term_id: str, actor: str, now: datetime) -> dict[str, Any]:
    current = {entry["term_id"]: entry for entry in _entries(store)}
    entry = current.get(term_id)
    if entry is None:
        raise ValueError("unknown term")
    snapshot_body = dict(entry)
    snapshot_body["governance"] = dict(entry["governance"])
    snapshot_body["governance"]["status"] = "DEPRECATED"
    snapshot_body["governance"]["approved_by"] = None
    snapshot_body["governance"]["approved_at"] = None
    snapshot_body["governance"]["version"] = int(entry["governance"].get("version") or 1) + 1
    revision = {
        "revision_id": "rev_" + uuid.uuid4().hex[:16],
        "kind": "term",
        "term_id": term_id,
        "status": "DEPRECATED",
        "version": snapshot_body["governance"]["version"],
        "approved_by": None,
        "approved_at": None,
        "created_at": now.isoformat(),
        "actor": actor,
        "definition_snapshot": snapshot_body,
    }
    return store.add_revision(revision)


def approve_document(store, *, document_id: str, actor: str, now: datetime) -> dict[str, Any]:
    current = {document["document_id"]: document for document in _documents(store)}
    document = current.get(document_id)
    if document is None:
        raise ValueError("unknown document")
    snapshot_body = dict(document)
    snapshot_body["approval_status"] = "APPROVED"
    snapshot_body["approved_by"] = actor
    snapshot_body["approved_at"] = now.isoformat()
    snapshot_body["version"] = int(document.get("version") or 1) + 1
    snapshot_body["last_verified_at"] = now.date().isoformat()
    revision = {
        "revision_id": "rev_" + uuid.uuid4().hex[:16],
        "kind": "document",
        "document_id": document_id,
        "status": "APPROVED",
        "version": snapshot_body["version"],
        "approved_by": actor,
        "approved_at": now.isoformat(),
        "created_at": now.isoformat(),
        "actor": actor,
        "document_snapshot": snapshot_body,
    }
    return store.add_revision(revision)


def deprecate_document(store, *, document_id: str, actor: str, now: datetime) -> dict[str, Any]:
    current = {document["document_id"]: document for document in _documents(store)}
    document = current.get(document_id)
    if document is None:
        raise ValueError("unknown document")
    snapshot_body = dict(document)
    snapshot_body["approval_status"] = "DEPRECATED"
    snapshot_body["approved_by"] = None
    snapshot_body["approved_at"] = None
    snapshot_body["version"] = int(document.get("version") or 1) + 1
    revision = {
        "revision_id": "rev_" + uuid.uuid4().hex[:16],
        "kind": "document",
        "document_id": document_id,
        "status": "DEPRECATED",
        "version": snapshot_body["version"],
        "approved_by": None,
        "approved_at": None,
        "created_at": now.isoformat(),
        "actor": actor,
        "document_snapshot": snapshot_body,
    }
    return store.add_revision(revision)


def suggest_term(store, *, actor: str, message: str, now: datetime) -> dict[str, Any]:
    return store.add_suggestion(
        {
            "suggestion_id": "sug_" + uuid.uuid4().hex[:12],
            "actor": actor,
            "message": message[:2000],
            "created_at": now.isoformat(),
            "status": "DRAFT",
        }
    )


def save_feedback(store, *, actor: str, message: str, now: datetime) -> dict[str, Any]:
    return store.add_feedback(
        {
            "feedback_id": "fb_" + uuid.uuid4().hex[:12],
            "actor": actor,
            "message": message[:2000],
            "created_at": now.isoformat(),
            "status": "REVIEW",
        }
    )


def review_due_date(kind: str, now: datetime) -> str:
    days = 30 if kind in {"goal", "process"} else 90
    return (now + timedelta(days=days)).date().isoformat()
