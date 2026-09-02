# -*- coding: utf-8 -*-

"""Vercel Python function: /api

Simple QA dashboard. Uses Firestore counts to verify connectivity.

Env vars (set in Vercel):
- FIREBASE_SERVICE_ACCOUNT_JSON (stringified JSON)
- GCP_PROJECT_ID (e.g. gemini-assistant-bot)
- FIRESTORE_DATABASE_ID (e.g. happy-solar)

Routes:
- GET /api            -> HTML dashboard
- GET /api?format=json -> JSON stats

Also restores omitted /api/* handlers. Live chi (PR 17 / ec530bd)
shipped ~50 Python functions and 404'd the rest (Website Funnel,
inbound CAC, Essential Sales, bot KPI). Filesystem functions still
win; vercel.json rewrites only the missing paths here. Dispatch
reuses the existing handler modules — no new funnel/CAC contract.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from google.oauth2 import service_account
from google.cloud import firestore

API_DIR = Path(__file__).resolve().parent


def dispatch_route(path: str, query_string: str | None = None) -> str | None:
    """Return api-relative module path (no .py) for an omitted /api/* request.

    Reads `hs=` from the URL, then from an extra query string (Vercel
    QUERY_STRING), then from `/api/<route>` path prefix.
    """
    parsed = urlparse(path)
    merged = parsed.query or ""
    extra = (query_string or "").strip()
    if extra and extra != merged:
        merged = f"{merged}&{extra}" if merged else extra
    qs = parse_qs(merged)
    route = (qs.get("hs", [""])[0] or "").strip()
    if not route:
        prefix = parsed.path.rstrip("/")
        if prefix.startswith("/api/") and prefix != "/api":
            route = prefix[len("/api/") :]
    if not route or route in {"index"}:
        return None
    return route


def dispatch_file(route: str) -> Path | None:
    if not route or ".." in route or route.startswith("/") or route.startswith("\\"):
        return None
    candidate = (API_DIR / f"{route}.py").resolve()
    try:
        candidate.relative_to(API_DIR)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def handler_path_for_delegate(path: str, route: str) -> str:
    parsed = urlparse(path)
    pairs = [
        (key, value)
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        if key != "hs"
        for value in values
    ]
    query = urlencode(pairs)
    dest = f"/api/{route}"
    return dest + (f"?{query}" if query else "")


_MODULE_CACHE: dict[str, object] = {}


def _load_api_module(module_path: Path):
    key = str(module_path)
    cached = _MODULE_CACHE.get(key)
    if cached is not None:
        return cached
    name = "hs_restore_" + "_".join(module_path.with_suffix("").relative_to(API_DIR).parts)
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[key] = module
    return module


def _handler_class(module):
    cls = getattr(module, "handler", None) or getattr(module, "Handler", None)
    if inspect.isclass(cls) and issubclass(cls, BaseHTTPRequestHandler):
        return cls
    return None


def delegate_to_api_module(request_handler: BaseHTTPRequestHandler, route: str) -> bool:
    module_path = dispatch_file(route)
    if module_path is None:
        return False
    module = _load_api_module(module_path)
    cls = _handler_class(module)
    if cls is None:
        return False
    inst = cls.__new__(cls)
    for attr in (
        "request",
        "client_address",
        "server",
        "rfile",
        "wfile",
        "headers",
        "command",
        "request_version",
        "close_connection",
    ):
        if hasattr(request_handler, attr):
            setattr(inst, attr, getattr(request_handler, attr))
    inst.path = handler_path_for_delegate(request_handler.path, route)
    inst.requestline = getattr(
        request_handler, "requestline", f"GET {inst.path} HTTP/1.1"
    )
    inst.client_address = getattr(request_handler, "client_address", ("", 0))
    inst.do_GET()
    return True


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")

    if not (creds_json and project_id and database_id):
        missing = [
            k
            for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(k)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def safe_count(db: firestore.Client, collection: str) -> int:
    try:
        # Aggregation query - count() returns a list of results
        result = db.collection(collection).count().get()
        if isinstance(result, list) and len(result) > 0:
            # First element is the aggregate result
            return result[0][0].value
        elif hasattr(result, 'value'):
            return result.value
        return -1
    except Exception as e:
        print(f"count_failed collection={collection} err={e}")
        return -1


def build_stats(db: firestore.Client) -> dict:
    return {
        "contacts": safe_count(db, "ghl_contacts"),
        "opportunities": safe_count(db, "ghl_opportunities"),
        "pipelines": safe_count(db, "ghl_pipelines"),
        "users": safe_count(db, "ghl_users"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def build_html(stats: dict) -> str:
    def fmt(v):
        return "—" if v == -1 else f"{v:,}" if isinstance(v, int) else str(v)

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — QA Dashboard</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin: 0; background: #0b0f14; color: #e8eef6; }}
    .wrap {{ padding: 20px; max-width: 980px; margin: 0 auto; }}
    .header {{ padding: 18px 20px; border-radius: 12px; background: linear-gradient(135deg,#00C853 0%,#1b5e20 100%); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 14px; margin-top: 16px; }}
    .card {{ background: #121a24; border: 1px solid #1f2a38; border-radius: 12px; padding: 16px; }}
    .label {{ color: #9db0c7; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }}
    .value {{ font-size: 34px; font-weight: 800; margin-top: 6px; }}
    .meta {{ margin-top: 16px; color: #9db0c7; font-size: 13px; }}
    a {{ color: #6ee7b7; }}
    code {{ background: #0e1520; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"header\">
      <div style=\"font-weight:800;font-size:20px\">Happy Solar — QA Dashboard</div>
      <div style=\"opacity:.9\">Firestore connectivity check (reads only)</div>
    </div>

    <div class=\"grid\">
      <div class=\"card\"><div class=\"label\">Total Contacts</div><div class=\"value\">{fmt(stats['contacts'])}</div></div>
      <div class=\"card\"><div class=\"label\">Opportunities</div><div class=\"value\">{fmt(stats['opportunities'])}</div></div>
      <div class=\"card\"><div class=\"label\">Pipelines</div><div class=\"value\">{fmt(stats['pipelines'])}</div></div>
      <div class=\"card\"><div class=\"label\">Users</div><div class=\"value\">{fmt(stats['users'])}</div></div>
    </div>

    <div class=\"card\" style=\"margin-top:14px\">
      <div class=\"label\">Generated At (UTC)</div>
      <div class=\"meta\">{stats['generated_at']}</div>
      <div class=\"meta\">JSON: <a href=\"/api?format=json\">/api?format=json</a></div>
    </div>
  </div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            route = dispatch_route(self.path, os.environ.get("QUERY_STRING"))
            if route:
                if delegate_to_api_module(self, route):
                    return
                body = b"The page could not be found\n"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            qs = parse_qs(urlparse(self.path).query)
            want_json = qs.get("format", [""])[0].lower() == "json"

            db = get_db()
            stats = build_stats(db)

            if want_json:
                body = json.dumps(stats).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = build_html(stats).encode("utf-8")
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


handler = Handler
