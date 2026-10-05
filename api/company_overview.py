# -*- coding: utf-8 -*-

"""Vercel Python function: /api/company_overview

Operations Control company overview. Counts still come from the existing
sales, opportunities created, opportunities ran, and demo rate metrics.
The page fetches /api/metrics/company_snapshot.

Observed card contract, still cited by the Goose dictionary. Phones stays
inside the company total and is not its own funnel. Sweeper is the Sweeper
and Rehash pipelines.
const p = r > 0 ? (s / r) * 100 : null;
result: ran > 0 ? (sit / ran) * 100 : null,
const PHONES_KEYS = ['Phones', 'Virtual'];
const SELF_GEN_KEYS = ['Self Gen', 'self gen', 'selfgen', 'SelfGen'];
sumByAliases(salesByLead, ['Doors'])
const INBOUND_KEYS = ['Inbound'];
const THREE_PL_KEYS = ['3PL'];
const createdUrl = `/api/metrics/opportunities_created?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}&pipeline_scope=all`;
"""

from __future__ import annotations

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
from ops_overview import render_body


def render_html(year: int, month: int) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("company_overview")
    body = render_body(nav_html)
    html = f"""<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Company Overview</title>
  <style>
    {nav_css}
  </style>
</head>
<body class="oc-root" data-oc-native-filters="1" data-year="{year}" data-month="{month}">
{body}
</body>
</html>"""
    panel = _copilot_panel()
    if not panel:
        return html
    return html.replace("</body>", panel + "\n</body>")


def _copilot_panel() -> str:
    """Goose markup only when COPILOT_ENABLED is true. Flag-off HTML is unchanged."""
    try:
        from copilot.config import config_from_env

        enabled = config_from_env().enabled
    except Exception:
        return ""
    if not enabled:
        return ""
    try:
        from copilot.ui import render_panel

        return render_panel()
    except Exception:
        return ""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo("America/New_York"))
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])

            body = render_html(year, month).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
