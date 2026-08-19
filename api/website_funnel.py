# -*- coding: utf-8 -*-

"""Vercel Python function: /api/website_funnel

Website Funnel dashboard (HTML) and month JSON (?format=json).
A lead is a completed form submit. Reads ≤31 web_funnel_daily_v1 docs.
Never streams ghl_* collections.

Optional ?rollup=1 writes yesterday (or ?date=YYYY-MM-DD) then returns
the dashboard/JSON. Prefer /api/web_funnel_rollup for the write path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


def _load_metric():
    path = API_DIR / "metrics" / "website_funnel.py"
    spec = importlib.util.spec_from_file_location("hs_website_funnel_metric", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load website_funnel metric from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metric = _load_metric()


def render_html(year: int, month: int) -> str:
    return metric.render_html(
        year,
        month,
        nav_css=dashboard_nav_css(),
        nav_html=render_dashboard_nav("website_funnel"),
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = (qs.get("format", [""])[0] or "").lower() == "json"
            do_rollup = (qs.get("rollup", [""])[0] or "").strip() in {"1", "true", "yes"}
            now = datetime.now(ZoneInfo("America/New_York"))
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            date = (qs.get("date", [""])[0] or "").strip() or None

            if do_rollup:
                db = metric.get_db()
                rollup = metric.rollup_day(db, date)
                if want_json:
                    body = json.dumps(rollup).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if want_json:
                db = metric.get_db()
                payload = metric.compute_month(db, year=year, month=month)
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(year, month).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
