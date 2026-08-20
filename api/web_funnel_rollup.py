# -*- coding: utf-8 -*-

"""Vercel Python function: /api/web_funnel_rollup

Write/merge one web_funnel_daily_v1 doc for a given America/New_York date
(default yesterday). Scoreboard: sessions → start → completed form.
Completed-form counts only. Does not read CRM contact or opportunity
collections. Not on warm_cache. Not hourly.

8:00 America/New_York routine: hit this write for yesterday first,
then GET /api/website_funnel_yesterday. The yesterday read does not
auto-rollup.

Params:
- date=YYYY-MM-DD (optional)
"""

from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _load_metric():
    path = Path(__file__).resolve().parent / "metrics" / "website_funnel.py"
    spec = importlib.util.spec_from_file_location("hs_website_funnel_rollup_metric", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load website_funnel metric from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metric = _load_metric()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            date = (qs.get("date", [""])[0] or "").strip() or None
            db = metric.get_db()
            payload = metric.rollup_day(db, date)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
