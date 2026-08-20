# -*- coding: utf-8 -*-

"""Vercel Python function: /api/website_funnel_yesterday

Charles 8:00 America/New_York routine — calculator / wny snapshot.

Reads one web_funnel_daily_v1/{YYYY-MM-DD} doc for yesterday in
America/New_York (00:00–23:59 calendar day). No collection stream.
Does not auto-rollup. Prefer GET /api/web_funnel_rollup first.

Lead = estimate_submit only. Monthly Website Funnel still counts
/contact-me wix_form_submit.

If the daily doc is missing or ga4 is not_configured/failed:
HTTP 200, ready=false, all metrics null. Counts are never invented.

Params:
- date=YYYY-MM-DD or date=yesterday (optional; default yesterday NY)
"""

from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _load_metric():
    path = Path(__file__).resolve().parent / "metrics" / "website_funnel.py"
    spec = importlib.util.spec_from_file_location("hs_website_funnel_yesterday_metric", path)
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
            payload = metric.compute_day_snapshot(db, date)
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
