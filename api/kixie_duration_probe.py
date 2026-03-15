# -*- coding: utf-8 -*-

"""Vercel Python function: /api/kixie_duration_probe

Purpose:
- Inspect recent kixie_calls docs and report the observed type/shape of the `duration` field.
- Helps confirm whether `duration` is stored as an int seconds, string, or nested object.

Returns:
- counts by python type name
- if object/dict: top-level keys frequency
- a few sample values (redacted / truncated)

Params:
- limit (optional, default 200, max 1000)

Collections:
- kixie_calls
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

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


def clip(v: Any, n: int = 180) -> Any:
    try:
        s = json.dumps(v)
    except Exception:
        s = str(v)
    if len(s) > n:
        s = s[: n - 3] + "..."
    return s


def parse_int(qs, k: str, default: int) -> int:
    try:
        return int(qs.get(k, [str(default)])[0])
    except Exception:
        return default


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            limit = max(10, min(1000, parse_int(qs, "limit", 200)))

            db = get_db()
            col = db.collection("kixie_calls")

            docs = list(col.order_by("receivedAt", direction=firestore.Query.DESCENDING).limit(limit).stream())

            type_counts: dict[str, int] = {}
            key_counts: dict[str, int] = {}
            samples: list[dict[str, Any]] = []

            for snap in docs:
                d = snap.to_dict() or {}
                dur = d.get("duration")
                tname = type(dur).__name__
                type_counts[tname] = type_counts.get(tname, 0) + 1

                if isinstance(dur, dict):
                    for k in dur.keys():
                        key_counts[str(k)] = key_counts.get(str(k), 0) + 1

                if len(samples) < 8:
                    samples.append(
                        {
                            "id": snap.id,
                            "receivedAt": d.get("receivedAt"),
                            "duration_type": tname,
                            "duration": clip(dur),
                        }
                    )

            payload = {
                "collection": "kixie_calls",
                "limit": limit,
                "duration_type_counts": dict(sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))),
                "duration_object_key_counts": dict(sorted(key_counts.items(), key=lambda x: (-x[1], x[0]))),
                "samples": samples,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            }

            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
