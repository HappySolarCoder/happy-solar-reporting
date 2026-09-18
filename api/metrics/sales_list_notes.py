# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sales_list_notes

Upsert dashboard overlays for the Sales List board. Persists to Firestore
named DB happy-solar, collection sales_list_notes_v1, keyed by contactId.

Accepts note, email, and/or phone. Omitted fields are left unchanged.
Does not write back to GHL. Empty values are stored as empty strings.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sales import get_db
from sales_list import (
    NOTES_COLLECTION,
    compact_text,
    load_overlays_by_contact_ids,
    upsert_sales_list_overlay,
)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    payload = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _overlay_payload(contact_id: str, overlay: dict[str, str] | None) -> dict[str, Any]:
    stored = overlay or {}
    return {
        "ok": True,
        "collection": NOTES_COLLECTION,
        "ghl_writeback": False,
        "contactId": contact_id,
        "note": stored.get("note", ""),
        "email": stored.get("email", ""),
        "phone": stored.get("phone", ""),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            contact_id = compact_text(qs.get("contactId", [""])[0])
            if not contact_id:
                raise ValueError("contactId is required")
            overlays = load_overlays_by_contact_ids(get_db(), [contact_id])
            _write_json(self, 200, _overlay_payload(contact_id, overlays.get(contact_id)))
        except Exception as e:
            _write_json(self, 400, {"ok": False, "error": str(e)})

    def do_POST(self):
        self._upsert()

    def do_PATCH(self):
        self._upsert()

    def _upsert(self):
        try:
            payload = _read_json(self)
            kwargs: dict[str, Any] = {"contact_id": payload.get("contactId")}
            if "note" in payload:
                kwargs["note"] = payload.get("note")
            if "email" in payload:
                kwargs["email"] = payload.get("email")
            if "phone" in payload:
                kwargs["phone"] = payload.get("phone")
            saved = upsert_sales_list_overlay(get_db(), **kwargs)
            _write_json(
                self,
                200,
                {
                    "ok": True,
                    "collection": NOTES_COLLECTION,
                    "ghl_writeback": False,
                    **saved,
                },
            )
        except Exception as e:
            _write_json(self, 400, {"ok": False, "error": str(e)})
