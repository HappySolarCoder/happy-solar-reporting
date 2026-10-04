# -*- coding: utf-8 -*-
"""POST /api/copilot/feedback — stores a review item for an authenticated admin."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from copilot.admin_actions import save_feedback
from copilot.auth import identity_from_headers
from copilot.firestore_store import open_store
from copilot.messages import SIGN_IN_REQUIRED
from copilot.store import LedgerUnavailable


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length and length < 20000 else b""
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}
        identity = identity_from_headers(self.headers)
        if identity is None:
            body = {"ok": False, "answer": SIGN_IN_REQUIRED}
            status = 401
        else:
            try:
                item = save_feedback(
                    open_store(),
                    actor=identity.actor_id,
                    message=str(data.get("message") or ""),
                    now=datetime.now(timezone.utc),
                )
                body = {"ok": True, "answer": "Saved for review.", "feedback_id": item["feedback_id"]}
                status = 200
            except LedgerUnavailable:
                body = {"ok": False, "answer": "Feedback could not be saved because the ledger is unavailable."}
                status = 503
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return
