# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/raydar_user_roles

Returns Raydar user role classification to support dashboard filtering:
- fma (Setter/FMA)
- selfgen (Closer/Self Gen)
- manager

Classification is inferred from common permission/role/title fields in raydar_users_v1.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any

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


def flatten_tokens(v: Any) -> list[str]:
    out: list[str] = []
    if v is None:
        return out
    if isinstance(v, str):
        t = v.strip()
        if t:
            out.append(t)
        return out
    if isinstance(v, (list, tuple)):
        for x in v:
            out.extend(flatten_tokens(x))
        return out
    if isinstance(v, dict):
        # Include BOTH keys and values so permission maps like
        # {"Setter (FMA)": true, "Closer": false} are classifiable.
        for k, x in v.items():
            out.extend(flatten_tokens(k))
            out.extend(flatten_tokens(x))
        return out
    return out


def classify(tokens: list[str]) -> list[str]:
    low = " | ".join(t.lower() for t in tokens)
    cats: list[str] = []

    # Requested mapping:
    # Setter => FMA
    # Closer => Self Gen
    if "setter" in low:
        cats.append("fma")
    if "closer" in low or "self gen" in low or "selfgen" in low:
        cats.append("selfgen")
    if "manager" in low:
        cats.append("manager")
    return sorted(set(cats))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            db = get_db()
            users = {}
            sampled_fields = [
                "permissions",
                "permission",
                "role",
                "roles",
                "accountPermissions",
                "userPermissions",
                "permissionSet",
                "title",
                "jobTitle",
                "groups",
            ]

            for snap in db.collection("raydar_users_v1").stream():
                d = snap.to_dict() or {}
                tokens: list[str] = []
                for f in sampled_fields:
                    if f in d:
                        tokens.extend(flatten_tokens(d.get(f)))

                cats = classify(tokens)
                name = str(d.get("name") or d.get("displayName") or d.get("fullName") or snap.id)

                keys = {str(snap.id).strip()}
                if d.get("id"):
                    keys.add(str(d.get("id")).strip())
                if d.get("userId"):
                    keys.add(str(d.get("userId")).strip())

                payload = {"name": name, "categories": cats}
                for k in keys:
                    if k:
                        users[k] = payload

            body = json.dumps({"users": users}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=600")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
