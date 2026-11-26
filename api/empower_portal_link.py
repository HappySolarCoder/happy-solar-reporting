# -*- coding: utf-8 -*-

"""POST /api/empower_portal_link

Manager, coach, or settings admin confirms, rejects, or manually binds a
NYHEP enrollment to a GHL opportunity. Closers stay unauthorized.
"""

from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

from metrics.empower_ids import LINKS_COLLECTION
from metrics.empower_linker import apply_link_action, guarded_set


PHOENIX = ZoneInfo("America/Phoenix")


def _header(headers, name: str) -> str:
    if headers is None:
        return ""
    getter = headers.get if hasattr(headers, "get") else None
    if getter is None:
        return ""
    value = getter(name)
    if value is None and name != name.lower():
        value = getter(name.lower())
    return "" if value is None else str(value)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length_raw = _header(handler.headers, "Content-Length") or "0"
    length = int(length_raw)
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("invalid_body")
    return payload


def _write(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        from empower_portal import view_identity
        from empower_portal_ingest import get_db

        identity = view_identity(self.headers)
        if identity is None:
            _write(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            body = _read_json(self)
        except Exception:
            _write(self, 400, {"ok": False, "error": "invalid_body"})
            return
        enrollment_id = str(body.get("enrollmentId") or body.get("enrollment_id") or "").strip()
        opp_id = str(body.get("oppId") or body.get("opp_id") or "").strip()
        action = str(body.get("action") or "").strip()
        if not enrollment_id or not action:
            _write(self, 400, {"ok": False, "error": "invalid_body"})
            return
        try:
            db = get_db()
            snap = db.collection(LINKS_COLLECTION).document(enrollment_id).get()
            existing = snap.to_dict() if getattr(snap, "exists", False) else {}
            updated = apply_link_action(
                existing if isinstance(existing, dict) else {},
                action,
                enrollment_id,
                opp_id,
                identity.actor_id,
                now=datetime.now(PHOENIX).isoformat(),
            )
            if updated is None:
                _write(self, 400, {"ok": False, "error": "invalid_body"})
                return
            guarded_set(db, LINKS_COLLECTION, enrollment_id, updated)
        except Exception:
            _write(self, 500, {"ok": False, "error": "warehouse_unavailable"})
            return
        _write(
            self,
            200,
            {
                "ok": True,
                "enrollmentId": enrollment_id,
                "status": updated.get("status"),
                "confidence": updated.get("confidence"),
                "oppId": updated.get("opp_id"),
            },
        )


Handler = handler
