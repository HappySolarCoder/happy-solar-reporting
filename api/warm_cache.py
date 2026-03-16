# -*- coding: utf-8 -*-

"""Vercel Cron endpoint: /api/warm_cache

Purpose:
- Warm the edge/CDN cache for the most-used dashboard metric queries (primarily "this month").
- Runs every 5 minutes via vercel.json cron.

Notes:
- Uses absolute URLs to the production domain.
- Best-effort: failures are recorded in the response payload; does not raise unless everything fails.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

import urllib.request


def http_get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(256)
        return {
            "url": url,
            "status": resp.status,
            "cache": resp.headers.get("x-vercel-cache"),
            "age": resp.headers.get("age"),
            "cache_control": resp.headers.get("cache-control"),
            "sample": body.decode("utf-8", errors="ignore"),
        }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # allow override domain for testing
        base = os.environ.get("WARM_CACHE_BASE_URL") or "https://database-migration-chi.vercel.app"

        # Warm: this month views (dashboards typically request year/month)
        # Keep list small to avoid long cron runs.
        # Compute current business month in America/New_York
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        now_ny = datetime.now(ny)
        y = now_ny.year
        m = now_ny.month

        urls = [
            f"{base}/api/metrics/sales?format=json&year={y}&month={m}",
            f"{base}/api/metrics/opportunities_created?format=json&year={y}&month={m}&pipeline_scope=all",
            f"{base}/api/metrics/opportunities_ran?format=json&year={y}&month={m}",
            f"{base}/api/metrics/demo_rate?format=json&year={y}&month={m}",
        ]

        results = []
        ok = 0
        for u in urls:
            try:
                r = http_get(u)
                results.append(r)
                if 200 <= int(r.get("status") or 0) < 300:
                    ok += 1
            except Exception as e:
                results.append({"url": u, "error": str(e)})

        payload = {
            "base": base,
            "ok": ok,
            "total": len(urls),
            "results": results,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "note": "If ok==0, cron is not effectively warming cache.",
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
