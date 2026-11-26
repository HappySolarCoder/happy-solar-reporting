# -*- coding: utf-8 -*-

"""POST /api/empower_portal_ingest

Weekday box routine posts the NYHEP EmPower+ snapshot. The shared secret is
NYHEP_INGEST_SECRET, sent as Authorization: Bearer or X-Webhook-Secret.
GET never writes. Re-posting one snapshot replaces that history row and
replaces the stage-history rows for that same snapshot. Stage history is
the difference in status, step, and step status versus the previous check.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any


API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from metrics.empower_portal_metrics import (
    build_portal_view,
    contains_forbidden_keys,
    derive_stage_events,
    merge_stage_history,
    prior_snapshot_id,
)


ENV_NAME = "NYHEP_INGEST_SECRET"
LATEST_COLLECTION = "nyhep_empower_portal"
LATEST_DOC_ID = "latest"
SNAPSHOT_COLLECTION = "nyhep_empower_portal_snapshots"
MAX_BODY_BYTES = 900_000
_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_PROJECT_FIELDS = (
    "id",
    "customer",
    "city",
    "county",
    "enrolled",
    "status",
    "step",
    "stepStatus",
    "onTodo",
    "due",
    "initialProcess",
    "tier",
    "installer",
)
_CHANGE_FIELDS = ("id", "customer", "change")
_STAGE_FIELDS = ("id", "customer", "snapshot", "checkedAt", "change", "from", "to")
_STAGE_CHANGES = {"added", "removed", "step", "status", "step status"}


def header_value(headers, name: str) -> str:
    if headers is None:
        return ""
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return "" if value is None else str(value)
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name)
    return "" if value is None else str(value)


def write_json(req: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    req.send_response(status)
    req.send_header("Content-Type", "application/json; charset=utf-8")
    req.send_header("Cache-Control", "no-store")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def ingest_secret() -> str:
    return str(os.environ.get(ENV_NAME) or "").strip()


def secret_matches(headers, secret: str) -> bool:
    """True when Bearer or X-Webhook-Secret matches. The secret is not echoed."""
    if not secret:
        return False
    candidates: list[str] = []
    auth = header_value(headers, "Authorization")
    if auth.lower().startswith("bearer "):
        candidates.append(auth.split(" ", 1)[1].strip())
    hook = header_value(headers, "X-Webhook-Secret").strip()
    if hook:
        candidates.append(hook)
    for presented in candidates:
        try:
            if hmac.compare_digest(presented.encode("utf-8"), secret.encode("utf-8")):
                return True
        except Exception:
            continue
    return False


def read_body(req: BaseHTTPRequestHandler) -> bytes:
    raw_length = header_value(req.headers, "Content-Length") or "0"
    try:
        length = int(raw_length)
    except ValueError:
        raise ValueError("size")
    if length < 0 or length > MAX_BODY_BYTES:
        raise ValueError("size")
    if length == 0:
        return b""
    return req.rfile.read(length)


def _clean_text(value: object, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _clean_project(row: dict) -> dict:
    cleaned = {field: row.get(field) for field in _PROJECT_FIELDS if field in row}
    if "id" in cleaned:
        cleaned["id"] = _clean_text(cleaned.get("id"), 80)
    if "customer" in cleaned:
        cleaned["customer"] = _clean_text(cleaned.get("customer"), 200)
    return cleaned


def _clean_change(row: dict) -> dict:
    return {
        "id": _clean_text(row.get("id"), 80),
        "customer": _clean_text(row.get("customer"), 200),
        "change": _clean_text(row.get("change"), 500),
    }


def _clean_changes(changes: object) -> list[dict]:
    if not isinstance(changes, list):
        return []
    return [_clean_change(row) for row in changes if isinstance(row, dict)]


def _history_changes(changes: object):
    if isinstance(changes, bool):
        return []
    if isinstance(changes, list):
        return _clean_changes(changes)
    if isinstance(changes, (int, float)):
        return int(changes)
    return []


def _clean_history_entry(row: dict) -> dict | None:
    snapshot = _clean_text(row.get("snapshot"), 80)
    if not snapshot:
        return None
    entry: dict[str, Any] = {
        "snapshot": snapshot,
        "checkedAt": _clean_text(row.get("checkedAt"), 200),
    }
    for key in ("open", "closed", "cancelled", "total"):
        if key in row and isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool):
            entry[key] = int(row[key])
    if "changes" in row:
        entry["changes"] = _history_changes(row.get("changes"))
    return entry


def validate_payload(payload: object) -> dict | None:
    """Return a cleaned snapshot, or None when the body is not usable."""
    if not isinstance(payload, dict):
        return None
    snapshot = _clean_text(payload.get("snapshot"), 80)
    checked_at = _clean_text(payload.get("checkedAt"), 200)
    projects = payload.get("projects")
    if not snapshot or _SNAPSHOT_ID.match(snapshot) is None:
        return None
    if not checked_at or not isinstance(projects, list):
        return None
    if any(not isinstance(row, dict) for row in projects):
        return None
    changes = payload.get("changes", [])
    history = payload.get("history", [])
    if not isinstance(changes, list) or not isinstance(history, list):
        return None
    if any(not isinstance(row, dict) for row in changes):
        return None
    if any(not isinstance(row, dict) for row in history):
        return None
    return {
        "snapshot": snapshot,
        "checkedAt": checked_at,
        "projects": [_clean_project(row) for row in projects],
        "changes": _clean_changes(changes),
        "history": [entry for row in history if (entry := _clean_history_entry(row))],
    }


def _computed_history_entry(cleaned: dict) -> dict:
    view = build_portal_view(cleaned)
    metrics = view["metrics"]
    return {
        "snapshot": cleaned["snapshot"],
        "checkedAt": cleaned["checkedAt"],
        "open": metrics["open"],
        "closed": metrics["closed"],
        "cancelled": metrics["cancelled"],
        "total": metrics["total"],
        "changes": cleaned["changes"],
    }


def merge_history(existing: object, incoming: object, current: dict) -> list[dict]:
    """Upsert history by snapshot id. The same id replaces; it does not append."""
    items: list[dict] = []
    index: dict[str, int] = {}

    def upsert(entry: dict) -> None:
        snapshot_id = str(entry.get("snapshot") or "").strip()
        if not snapshot_id:
            return
        stored = dict(entry)
        stored["snapshot"] = snapshot_id
        if snapshot_id in index:
            items[index[snapshot_id]] = stored
        else:
            index[snapshot_id] = len(items)
            items.append(stored)

    if isinstance(existing, list):
        for entry in existing:
            if isinstance(entry, dict):
                cleaned = _clean_history_entry(entry)
                if cleaned:
                    upsert(cleaned)
    incoming_ids: set[str] = set()
    if isinstance(incoming, list):
        for entry in incoming:
            if isinstance(entry, dict):
                cleaned = _clean_history_entry(entry)
                if cleaned:
                    incoming_ids.add(cleaned["snapshot"])
                    upsert(cleaned)
    if current["snapshot"] not in incoming_ids:
        upsert(current)
    return items


def _clean_stage_event(row: dict) -> dict | None:
    event = {field: _clean_text(row.get(field), 500) for field in _STAGE_FIELDS}
    if not event["id"] or not event["snapshot"]:
        return None
    if event["change"] not in _STAGE_CHANGES:
        return None
    return event


def _clean_stage_history(events: object) -> list[dict]:
    if not isinstance(events, list):
        return []
    cleaned = []
    for row in events:
        if not isinstance(row, dict):
            continue
        event = _clean_stage_event(row)
        if event:
            cleaned.append(event)
    return cleaned


def _existing_latest(db) -> dict:
    try:
        snap = db.collection(LATEST_COLLECTION).document(LATEST_DOC_ID).get()
    except Exception:
        return {}
    if not getattr(snap, "exists", False):
        return {}
    data = snap.to_dict() or {}
    return data if isinstance(data, dict) else {}


def _snapshot_projects(db, snapshot_id: str) -> list:
    if not snapshot_id:
        return []
    try:
        snap = db.collection(SNAPSHOT_COLLECTION).document(snapshot_id).get()
    except Exception:
        return []
    if not getattr(snap, "exists", False):
        return []
    data = snap.to_dict() or {}
    projects = data.get("projects") if isinstance(data, dict) else None
    return projects if isinstance(projects, list) else []


def upsert_snapshot(db, cleaned: dict, *, now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    updated_at = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = _existing_latest(db)
    current = _computed_history_entry(cleaned)
    history = merge_history(
        existing.get("history") if existing else [],
        cleaned["history"],
        current,
    )
    prior_id = prior_snapshot_id(history, cleaned["snapshot"])
    stage_events = derive_stage_events(
        _snapshot_projects(db, prior_id),
        cleaned["projects"],
        cleaned["snapshot"],
        cleaned["checkedAt"],
    )
    stage_history = merge_stage_history(
        _clean_stage_history(existing.get("stageHistory")),
        cleaned["snapshot"],
        stage_events,
    )
    latest = {
        "snapshot": cleaned["snapshot"],
        "checkedAt": cleaned["checkedAt"],
        "projects": cleaned["projects"],
        "changes": cleaned["changes"],
        "history": history,
        "stageHistory": stage_history,
        "updatedAt": updated_at,
    }
    snapshot_doc = {
        "snapshot": cleaned["snapshot"],
        "checkedAt": cleaned["checkedAt"],
        "projects": cleaned["projects"],
        "changes": cleaned["changes"],
        "open": current["open"],
        "closed": current["closed"],
        "cancelled": current["cancelled"],
        "total": current["total"],
        "stageChanges": stage_events,
        "updatedAt": updated_at,
    }
    db.collection(LATEST_COLLECTION).document(LATEST_DOC_ID).set(latest)
    db.collection(SNAPSHOT_COLLECTION).document(cleaned["snapshot"]).set(snapshot_doc)
    return {
        "ok": True,
        "snapshot": cleaned["snapshot"],
        "historyCount": len(history),
        "updatedAt": updated_at,
    }


def load_latest(db) -> dict | None:
    snap = db.collection(LATEST_COLLECTION).document(LATEST_DOC_ID).get()
    if not getattr(snap, "exists", False):
        return None
    data = snap.to_dict() or {}
    return data if isinstance(data, dict) else None


def get_db():
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [
            key
            for key in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(key)
        ]
        raise RuntimeError("missing warehouse env: " + ", ".join(missing))
    from google.cloud import firestore
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def _forbidden(payload: dict) -> bool:
    return contains_forbidden_keys(payload.get("projects")) or contains_forbidden_keys(
        payload.get("changes")
    ) or contains_forbidden_keys(
        [item.get("changes") for item in payload.get("history") or [] if isinstance(item, dict)]
    )


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        write_json(
            self,
            200,
            {"ok": True, "route": "/api/empower_portal_ingest", "method": "POST"},
        )

    def do_POST(self) -> None:
        secret = ingest_secret()
        if not secret:
            write_json(
                self,
                500,
                {"ok": False, "error": "missing_env", "missing": [ENV_NAME]},
            )
            return
        if not secret_matches(self.headers, secret):
            write_json(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            raw = read_body(self)
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            write_json(self, 400, {"ok": False, "error": "invalid_body"})
            return
        if not isinstance(payload, dict):
            write_json(self, 400, {"ok": False, "error": "invalid_body"})
            return
        if _forbidden(payload):
            write_json(self, 400, {"ok": False, "error": "forbidden_fields"})
            return
        cleaned = validate_payload(payload)
        if cleaned is None:
            write_json(self, 400, {"ok": False, "error": "invalid_body"})
            return
        try:
            result = upsert_snapshot(get_db(), cleaned)
        except Exception:
            write_json(self, 500, {"ok": False, "error": "warehouse_unavailable"})
            return
        write_json(self, 200, result)


Handler = handler
