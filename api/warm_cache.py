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
from urllib.parse import parse_qs, urlparse, urlencode

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

        qs = parse_qs(urlparse(self.path).query)

        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        now_ny = datetime.now(ny)

        # Optional query params:
        # - year/month
        # - start/end
        # - include_daily=1 (adds raydar/kixie daily warm)
        year = (qs.get("year", [str(now_ny.year)])[0] or str(now_ny.year)).strip()
        month = (qs.get("month", [str(now_ny.month)])[0] or str(now_ny.month)).strip()
        start = (qs.get("start", [""])[0] or "").strip()
        end = (qs.get("end", [""])[0] or "").strip()
        include_daily = (qs.get("include_daily", [""])[0] or "").strip() in {"1", "true", "yes"}

        params = {"format": "json"}
        if start and end:
            params["start"] = start
            params["end"] = end
        else:
            params["year"] = str(year)
            params["month"] = str(month)

        q = urlencode(params)

        urls = [
            f"{base}/api/metrics/sales?{q}",
            f"{base}/api/metrics/opportunities_created?{q}&pipeline_scope=all",
            f"{base}/api/metrics/opportunities_ran?{q}",
            f"{base}/api/metrics/demo_rate?{q}",
            f"{base}/api/metrics/company_snapshot?{q}",
        ]

        if include_daily and start and end:
            urls.extend([
                f"{base}/api/metrics/raydar_doors_knocked?{q}",
                f"{base}/api/metrics/kixie_calls_summary?{q}",
            ])

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
            "window": {"year": year, "month": month, "start": start or None, "end": end or None},
            "results": results,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "note": "Use for hourly baseline warm + non-blocking on-open warm.",
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
