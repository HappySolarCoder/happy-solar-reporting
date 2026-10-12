# -*- coding: utf-8 -*-
"""Serve the five dashboard pages for the Playwright date test.

HTML is the real page. Other /api responses are a small JSON stub so date
changes can run without Firestore.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
sys.path.insert(0, str(API))

HOST = "127.0.0.1"
PORT = 8765

STUB = {
    "result": 0,
    "ran_count": 0,
    "sit_count": 0,
    "calls": 0,
    "connections": 0,
    "rows": [],
    "days": [],
    "notes": [],
    "kpis": {},
    "secondary": {},
    "by_page": {},
    "chart": {},
    "overall": {},
    "performance_kpis": {},
    "breakdowns": {},
    "tables": {"by_agent": [], "by_owner": []},
    "top_knockers": [],
    "users": {},
    "available": False,
    "window_start_local": "2026-09-01T00:00:00-04:00",
    "window_end_local": "2026-09-30T23:59:59-04:00",
    "timezone": "America/New_York",
    "data": {
        "sales": {"result": 0, "breakdowns": {}},
        "created": {"result": 0, "breakdowns": {}},
        "ran": {"result": 0, "breakdowns": {}},
        "demo": {"result": 0, "ran_count": 0, "sit_count": 0, "breakdowns": {}},
    },
}


def _page(name: str):
    """Load api/<name>.py even after a metrics module of the same name is imported."""
    import importlib.util

    mod_name = f"hs_e2e_page_{name}"
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(mod_name, API / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _html_for(path: str, query: str) -> bytes | None:
    qs = parse_qs(query)
    now = datetime.now(ZoneInfo("America/New_York"))
    if path == "/api/daily_update":
        return _page("daily_update").HTML.encode("utf-8")
    if path == "/api/morning_brief":
        page = _page("morning_brief")
        from dashboard_nav import dashboard_nav_css, render_dashboard_nav

        html = page.HTML.replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css()).replace(
            "__DASHBOARD_NAV_HTML__", render_dashboard_nav("morning_brief")
        )
        return html.encode("utf-8")
    if path == "/api/website_traffic":
        return _page("website_traffic").render_html().encode("utf-8")
    if path == "/api/inbound_cac":
        year = int((qs.get("year") or [str(now.year)])[0])
        month_raw = (qs.get("month") or [str(now.month)])[0]
        month = None if str(month_raw).lower() == "ytd" else int(month_raw)
        return _page("inbound_cac").render_html(year, month).encode("utf-8")
    if path == "/api/company_overview":
        year = int((qs.get("year") or [str(now.year)])[0])
        month = int((qs.get("month") or [str(now.month)])[0])
        return _page("company_overview").render_html(year, month).encode("utf-8")
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        fmt = (parse_qs(parsed.query).get("format") or [""])[0].lower()
        if path == "/health":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return
        try:
            if fmt != "json" and path.startswith("/api/"):
                body = _html_for(path, parsed.query)
                if body is not None:
                    self._send(200, body, "text/html; charset=utf-8")
                    return
            self._send(200, json.dumps(STUB).encode("utf-8"), "application/json")
        except Exception as exc:
            self._send(500, ("ERROR: " + str(exc)).encode("utf-8"), "text/plain; charset=utf-8")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"dashboard e2e server http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
