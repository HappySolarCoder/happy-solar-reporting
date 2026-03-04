# -*- coding: utf-8 -*-

"""Vercel Python function: /api/raydar/leads

Query Raydar leads from happy-solar Firestore.

Collections:
- raydar_leads_v1 (source: Raydar Firestore)
- raydar_users_v1 (for joining to get user names)
- raydar_dispositions_v1 (for joining to get disposition names)

Params (optional):
- limit (default 50, max 200)
- offset (default 0)
- status (filter by lead status)
- dispositionId (filter by disposition)
- claimedBy (filter by Raydar user ID)
- assignedTo (filter by Raydar user ID)
- format=json (default)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


def get_db() -> firestore.Client:
    """Get Firestore client for happy-solar DB."""
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
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        limit = int(qs.get("limit", ["50"])[0])
        offset = int(qs.get("offset", ["0"])[0])
        status_filter = qs.get("status", [None])[0]
        disposition_filter = qs.get("dispositionId", [None])[0]
        claimed_by = qs.get("claimedBy", [None])[0]
        assigned_to = qs.get("assignedTo", [None])[0]

        try:
            db = get_db()
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Firestore connection failed: {str(e)}"}).encode())
            return

        # Build query
        coll = db.collection("raydar_leads_v1")
        if status_filter:
            coll = coll.where("status", "==", status_filter)
        if disposition_filter:
            coll = coll.where("dispositionId", "==", disposition_filter)
        if claimed_by:
            coll = coll.where("claimedBy", "==", claimed_by)
        if assigned_to:
            coll = coll.where("assignedTo", "==", assigned_to)

        # Get total (approximation via count)
        # For now just return data; client can count
        
        # Execute query with limit/offset
        docs = list(coll.limit(limit).offset(offset).stream())
        leads = []
        for doc in docs:
            d = doc.to_dict()
            # Convert any Timestamp to ISO string
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            d["id"] = doc.id
            leads.append(d)

        # Get users map for joining
        users = {}
        for u in db.collection("raydar_users_v1").stream():
            ud = u.to_dict()
            users[u.id] = ud.get("name", "Unknown")

        # Get dispositions map
        dispositions = {}
        for dp in db.collection("raydar_dispositions_v1").stream():
            dpd = dp.to_dict()
            dispositions[dp.id] = dpd.get("name", "Unknown")

        # Enrich leads with user/disposition names
        for lead in leads:
            cb = lead.get("claimedBy")
            lead["claimedByName"] = users.get(cb, cb)
            at = lead.get("assignedTo")
            lead["assignedToName"] = users.get(at, at)
            di = lead.get("dispositionId")
            lead["dispositionName"] = dispositions.get(di, di)

        response = {
            "leads": leads,
            "meta": {
                "limit": limit,
                "offset": offset,
                "count": len(leads)
            }
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response, default=str).encode())
