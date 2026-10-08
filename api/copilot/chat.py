# -*- coding: utf-8 -*-
"""POST /api/copilot/chat"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from copilot.chat_service import handle_chat
from copilot.config import config_from_env
from copilot.firestore_store import open_store
from copilot.gemini_client import GeminiClient
from copilot.messages import REQUEST_UNREADABLE
from copilot.metrics_port import LiveMetrics


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    if length > 20000:
        raise ValueError("body too large")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("body must be an object")
    return data


def _send(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            data = _read_json(self)
        except Exception:
            _send(self, 400, {"ok": False, "code": "bad_request", "answer": REQUEST_UNREADABLE})
            return
        result = handle_chat(
            message=str(data.get("message") or ""),
            filters=data.get("filters") if isinstance(data.get("filters"), dict) else {},
            conversation_id=data.get("conversation_id"),
            request_id=data.get("request_id"),
            headers=self.headers,
            now=datetime.now(timezone.utc),
            config=config_from_env(),
            store=open_store(),
            settings_password=None,
            metrics=LiveMetrics(),
            model=GeminiClient(),
            body_identity={"user_id": data.get("user_id"), "role": data.get("role")},
        )
        _send(self, result["status"], result["body"])

    def log_message(self, fmt: str, *args) -> None:
        return
