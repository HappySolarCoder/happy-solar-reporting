# -*- coding: utf-8 -*-

"""Vercel Python function: /api/kixie_status

Purpose:
- Verify whether Kixie call data is present in Firestore and how recently it has been updated.

Reads:
- Firestore collection: kixie_calls

Returns JSON:
- count (best-effort)
- latest_timestamp + which field was used
- age_minutes

Env (same as other metrics endpoints):
- FIREBASE_SERVICE_ACCOUNT_JSON
- GCP_PROJECT_ID
- FIRESTORE_DATABASE_ID
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

from google.cloud import firestore
from google.oauth2 import service_account


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


def coerce_dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            db = get_db()
            col = db.collection("kixie_calls")

            fields = ["receivedAt", "callDate", "callEndDate", "createdAt", "updatedAt"]
            latest_dt = None
            latest_field = None
            latest_doc = None

            for f in fields:
                try:
                    docs = list(col.order_by(f, direction=firestore.Query.DESCENDING).limit(1).stream())
                    if not docs:
                        continue
                    d = docs[0]
                    data = d.to_dict() or {}
                    dt = coerce_dt(data.get(f))
                    if dt:
                        latest_dt = dt
                        latest_field = f
                        latest_doc = {"id": d.id, "agent": data.get("agent"), "outcome": data.get("outcome")}
                        break
                except Exception:
                    continue

            # Count aggregation (best-effort; not critical)
            count = None
            try:
                count = col.count().get()[0][0].value
            except Exception:
                count = None

            age_minutes = None
            latest_utc = None
            if latest_dt:
                latest_utc = latest_dt.astimezone(timezone.utc).isoformat()
                age_minutes = round((datetime.now(timezone.utc) - latest_dt.astimezone(timezone.utc)).total_seconds() / 60.0, 1)

            payload = {
                "collection": "kixie_calls",
                "count": count,
                "latest_field": latest_field,
                "latest_utc": latest_utc,
                "age_minutes": age_minutes,
                "latest_doc": latest_doc,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            }

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
