# -*- coding: utf-8 -*-

"""Vercel Python function: /api/raydar/stats

Summary stats for Raydar data.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        raise RuntimeError("Missing required env vars")
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            db = get_db()
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        leads_count = sum(1 for _ in db.collection("raydar_leads_v1").stream())
        users_count = sum(1 for _ in db.collection("raydar_users_v1").stream())
        dispositions_count = sum(1 for _ in db.collection("raydar_dispositions_v1").stream())

        # Get last sync info
        sync_doc = db.collection("raydar_sync_v1").document("last_run").get()
        last_sync = sync_doc.to_dict() if sync_doc.exists else None

        response = {
            "leads": leads_count,
            "users": users_count,
            "dispositions": dispositions_count,
            "lastSync": last_sync
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response, default=str).encode())
