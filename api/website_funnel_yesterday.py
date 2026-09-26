# -*- coding: utf-8 -*-

"""Vercel Python function: /api/website_funnel_yesterday

Charles 8:00 America/New_York routine — calculator snapshot.
site is wny.happyslr.com before 2026-09-10 ET and
www.happyslr.com/estimate on and after that date.

Reads one web_funnel_daily_v1/{YYYY-MM-DD} doc for yesterday in
America/New_York (00:00–23:59 calendar day). No collection stream.
If that daily is missing or ga4 is not "ok", auto-calls the same
in-process rollup_day as GET /api/web_funnel_rollup?date={date},
then re-reads. Prefer hitting rollup first at 8am; this is the
safety net. auto_rollup / auto_rollup_reason / auto_rollup_wrote
report whether this request wrote.

Lead = estimate_submit only. Monthly Website Funnel still counts
/contact-me wix_form_submit.

If the daily doc is still missing or ga4 is not_configured/failed
after that attempt: HTTP 200, ready=false, all metrics null.
Counts are never invented.

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
    patch_path = Path(__file__).resolve().parent / "metrics" / "funnel_test_address.py"
    pspec = importlib.util.spec_from_file_location("hs_funnel_test_address", patch_path)
    if pspec is None or pspec.loader is None:
        return module
    patch = importlib.util.module_from_spec(pspec)
    pspec.loader.exec_module(patch)
    return patch.install(module)


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
