# -*- coding: utf-8 -*-
"""GET /api/copilot/status — no model call."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from copilot.config import config_from_env
from copilot.firestore_store import open_store
from copilot.launch import launch_checks


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = config_from_env()
        body = launch_checks(config, open_store(), today=datetime.now(timezone.utc).date())
        body["dashboard_unaffected"] = True
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return
