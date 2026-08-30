# -*- coding: utf-8 -*-

"""Vercel Python function: /api/web_funnel_named_fills_ingest

Standing ingest of leads@ WNY calculator notifies into
web_funnel_named_fills_v1. Filesystem function; not on warm_cache cron.

GET: optional date=YYYY-MM-DD (default yesterday America/New_York).
Uses Gmail when GMAIL_ACCESS_TOKEN or refresh trio is set. If Gmail is
not configured, HTTP 200 {ready: false, reason: gmail_not_configured}.

POST: JSON {"messages": [{"plaintext": "...", "received_at": "..."}]}
for QA without Gmail env. Cap 50. Idempotent merge-write.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _load_module(name: str, path: Path):
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_ingest():
    path = Path(__file__).resolve().parent / "metrics" / "funnel_named_fills_ingest.py"
    return _load_module("hs_funnel_named_fills_ingest", path)


def _load_funnel():
    path = Path(__file__).resolve().parent / "metrics" / "website_funnel.py"
    return _load_module("hs_website_funnel_named_fills_ingest", path)


ingest = _load_ingest()
funnel = _load_funnel()
COLLECTION = "web_funnel_named_fills_v1"


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Request line only. Do not log bodies (PII).
        return

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            date = (qs.get("date", [""])[0] or "").strip() or funnel.yesterday_ny_date()
            if not funnel.parse_date_ymd(date):
                self._send_json(400, {"error": "Invalid date; expected YYYY-MM-DD"})
                return
            if not ingest.gmail_configured():
                self._send_json(
                    200,
                    {
                        "ready": False,
                        "reason": "gmail_not_configured",
                        "collection": COLLECTION,
                        "date": date,
                    },
                )
                return
            db = funnel.get_db()
            result = ingest.ingest_leads_at(db, date_ymd=date)
            payload = {
                "ready": True,
                "collection": COLLECTION,
                "date": date,
                "attempted": result.get("attempted", True),
                "wrote": result.get("wrote", 0),
                "skipped": result.get("skipped", 0),
                "ids": result.get("ids") or [],
                "reason": result.get("reason"),
            }
            self._send_json(200, payload)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                body = json.loads(raw.decode("utf-8") or "null")
            except Exception:
                self._send_json(400, {"error": "invalid_json"})
                return
            if not isinstance(body, dict):
                self._send_json(400, {"error": "invalid_body"})
                return
            messages = body.get("messages")
            if messages is None:
                messages = []
            if not isinstance(messages, list):
                self._send_json(400, {"error": "invalid_messages"})
                return
            messages = messages[:50]
            db = funnel.get_db()
            result = ingest.ingest_leads_at(db, messages=messages)
            self._send_json(
                200,
                {
                    "wrote": result.get("wrote", 0),
                    "skipped": result.get("skipped", 0),
                    "ids": result.get("ids") or [],
                    "collection": COLLECTION,
                    "attempted": result.get("attempted", True),
                    "reason": result.get("reason"),
                },
            )
        except Exception as e:
            self._send_json(500, {"error": str(e)})
