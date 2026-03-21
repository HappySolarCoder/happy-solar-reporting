# -*- coding: utf-8 -*-

"""/api/metrics/company_trends

Monthly trends for company dashboard:
- sales per month
- opp2prelim per month (sales / opps_ran)
- opps_created per month

Default start: 2025-08 (GHL start), through requested/current month.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300


def _base_url(h: BaseHTTPRequestHandler) -> str:
    proto = h.headers.get("x-forwarded-proto") or "https"
    host = h.headers.get("x-forwarded-host") or h.headers.get("host") or "database-migration-chi.vercel.app"
    return f"{proto}://{host}"


def _fetch_json(url: str, timeout: int = 25) -> dict | None:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # nosec - internal URL
        return json.loads(resp.read().decode("utf-8"))


def _months(start_y: int, start_m: int, end_y: int, end_m: int) -> list[tuple[int, int]]:
    out = []
    y, m = start_y, start_m
    while (y < end_y) or (y == end_y and m <= end_m):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.utcnow()
            end_y = int((qs.get("year", [str(now.year)])[0] or now.year))
            end_m = int((qs.get("month", [str(now.month)])[0] or now.month))
            start_y = int((qs.get("start_year", ["2025"])[0] or "2025"))
            start_m = int((qs.get("start_month", ["8"])[0] or "8"))

            key = f"{start_y}-{start_m}:{end_y}-{end_m}"
            hit = _CACHE.get(key)
            t = time.time()
            if hit and (t - hit[0]) < _TTL:
                payload = dict(hit[1])
                payload["cache"] = {"hit": True, "ttl": _TTL}
                b = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=300")
                self.end_headers()
                self.wfile.write(b)
                return

            base = _base_url(self)
            months = _months(start_y, start_m, end_y, end_m)

            def one(ym: tuple[int, int]) -> dict:
                y, m = ym
                q = urlencode({"format": "json", "year": y, "month": m})
                sales = _fetch_json(f"{base}/api/metrics/sales?{q}") or {}
                created = _fetch_json(f"{base}/api/metrics/opportunities_created?{q}&pipeline_scope=all") or {}
                ran = _fetch_json(f"{base}/api/metrics/opportunities_ran?{q}") or {}
                s = float(sales.get("result") or 0)
                c = float(created.get("result") or 0)
                r = float(ran.get("result") or 0)
                opp2 = (s / r * 100.0) if r > 0 else 0.0
                return {
                    "month": f"{y}-{str(m).zfill(2)}",
                    "sales": s,
                    "opps_created": c,
                    "opp2prelim": round(opp2, 1),
                }

            with ThreadPoolExecutor(max_workers=6) as ex:
                rows = list(ex.map(one, months))

            payload = {
                "metric": "company_trends",
                "cache": {"hit": False, "ttl": _TTL},
                "rows": rows,
                "start": f"{start_y}-{str(start_m).zfill(2)}",
                "end": f"{end_y}-{str(end_m).zfill(2)}",
            }
            _CACHE[key] = (t, payload)

            b = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(b)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
