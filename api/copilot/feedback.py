# -*- coding: utf-8 -*-
"""POST /api/copilot/feedback — stores a review item for a signed-in employee or admin."""

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
from copilot.auth import identity_for_chat, identity_from_headers, unauthorized_answer
from copilot.config import config_from_env
from copilot.firestore_store import open_store
from copilot.messages import PAUSED
from copilot.store import LedgerUnavailable


def _write(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(payload)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not config_from_env().enabled:
            _write(
                self,
                200,
                {
                    "ok": False,
                    "code": "copilot_disabled",
                    "answer": PAUSED,
                    "dashboard_unaffected": True,
                },
            )
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length and length < 20000 else b""
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}
        identity = identity_from_headers(self.headers)
        if identity is None:
            # Bloom bearer is the employee path. It does not grant admin, and a
            # missing or invalid token stays anonymous and is refused.
            identity = identity_for_chat(
                self.headers,
                settings_password=None,
                allowed_roles=config_from_env().allowed_roles,
                now=datetime.now(timezone.utc),
            )
        if identity is None:
            body = {
                "ok": False,
                "answer": unauthorized_answer(
                    self.headers,
                    settings_password=None,
                    allowed_roles=config_from_env().allowed_roles,
                    now=datetime.now(timezone.utc),
                ),
            }
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
        _write(self, status, body)

    def log_message(self, fmt: str, *args) -> None:
        return
