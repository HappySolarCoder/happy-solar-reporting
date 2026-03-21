# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/company_snapshot

Aggregated payload for company_overview to reduce client fan-out and improve perceived load.
Caches payloads in-process for a short TTL.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import Request, urlopen

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 90


def _base_url(handler: BaseHTTPRequestHandler) -> str:
    proto = handler.headers.get("x-forwarded-proto") or "https"
    host = handler.headers.get("x-forwarded-host") or handler.headers.get("host") or "database-migration-chi.vercel.app"
    return f"{proto}://{host}"


def _fetch_json(url: str, timeout: int = 25) -> dict | None:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # nosec - controlled internal URL
        body = resp.read()
        return json.loads(body.decode("utf-8"))


def _clean_qs(qs: dict[str, list[str]]) -> str:
    out = {}
    for k in ("year", "month", "start", "end"):
        v = (qs.get(k, [""])[0] or "").strip()
        if v:
            out[k] = v
    return urlencode(out)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            q = _clean_qs(qs)
            cache_key = q or "default"

            now = time.time()
            hit = _CACHE.get(cache_key)
            if hit and (now - hit[0]) < _TTL_SECONDS:
                payload = dict(hit[1])
                payload["cache"] = {"hit": True, "ttl": _TTL_SECONDS}
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
                self.end_headers()
                self.wfile.write(body)
                return

            base = _base_url(self)
            suffix = f"&{q}" if q else ""

            urls = {
                "sales": f"{base}/api/metrics/sales?format=json{suffix}",
                "created": f"{base}/api/metrics/opportunities_created?format=json&pipeline_scope=all{suffix}",
                "ran": f"{base}/api/metrics/opportunities_ran?format=json{suffix}",
                "demo": f"{base}/api/metrics/demo_rate?format=json{suffix}",
            }

            out = {}
            with ThreadPoolExecutor(max_workers=4) as ex:
                futs = {k: ex.submit(_fetch_json, u) for k, u in urls.items()}
                for k, f in futs.items():
                    try:
                        out[k] = f.result()
                    except Exception as e:
                        out[k] = {"error": str(e)}

            payload = {
                "metric": "company_snapshot",
                "query": q,
                "cache": {"hit": False, "ttl": _TTL_SECONDS},
                "data": out,
                "generated_at": int(now),
            }
            _CACHE[cache_key] = (now, payload)

            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
