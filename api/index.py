# -*- coding: utf-8 -*-

"""Vercel Python function: /api

Implements a simple QA-friendly dashboard view that works on phone/desktop.
Uses Firestore counts to verify credentials + connectivity.

Env vars (set in Vercel):
- FIREBASE_SERVICE_ACCOUNT_JSON (stringified JSON)
- GCP_PROJECT_ID (e.g. gemini-assistant-bot)
- FIRESTORE_DATABASE_ID (e.g. happy-solar)

Routes:
- GET /api            -> HTML dashboard
- GET /api?format=json -> JSON stats
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


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
        # Aggregation query (fast)
        return db.collection(collection).count().get()[0].value
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

    <div class=\"meta\">If any value is <code>—</code>, the Firestore aggregation count call failed (permissions/index/runtime). We can still query with fallbacks once metric endpoints are added.</div>
  </div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
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
