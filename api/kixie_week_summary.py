# -*- coding: utf-8 -*-

"""Vercel Python function: /api/kixie_week_summary

Purpose:
- Quick verification that Kixie calls are present Mon–Fri for the current week.
- Returns call counts per day (UTC and America/New_York) for last N days.

Params:
- days (optional int) default 10

Reads:
- Firestore collection: kixie_calls
- Timestamp field preference: receivedAt (falls back to callDate/callEndDate if needed)

Security:
- Returns aggregated counts only (no PII)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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
    # Firestore Timestamp often comes through as datetime (or DatetimeWithNanoseconds)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    # Some exports store as ISO string
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None

    # Some payloads store {seconds, nanos}
    if isinstance(v, dict) and ("seconds" in v or "_seconds" in v):
        try:
            sec = int(v.get("seconds") or v.get("_seconds") or 0)
            ns = int(v.get("nanos") or v.get("_nanoseconds") or 0)
            return datetime.fromtimestamp(sec + ns / 1e9, tz=timezone.utc)
        except Exception:
            return None

    # numeric epoch seconds
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except Exception:
            return None

    return None


def parse_int(qs, key: str, default: int) -> int:
    try:
        return int(qs.get(key, [str(default)])[0])
    except Exception:
        return default


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            days = max(3, min(31, parse_int(qs, "days", 10)))

            db = get_db()
            col = db.collection("kixie_calls")

            # Prefer receivedAt
            field = "receivedAt"
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=days)

            docs = []
            last_error = None
            try:
                docs = list(
                    col.where(field, ">=", start)
                    .order_by(field, direction=firestore.Query.ASCENDING)
                    .limit(5000)
                    .stream()
                )
            except Exception as e:
                last_error = str(e)

            if not docs:
                # Fallback: just take last 5000 docs by receivedAt
                try:
                    docs = list(col.order_by(field, direction=firestore.Query.DESCENDING).limit(5000).stream())
                except Exception as e:
                    last_error = str(e)
                    docs = []

            if not docs:
                # Last resort: stream a small sample without ordering and try to infer timestamp field
                sample = list(col.limit(200).stream())
                docs = sample
                last_error = last_error or "no_docs_from_ordered_queries"

            # Timezone for business view
            from zoneinfo import ZoneInfo
            ny = ZoneInfo("America/New_York")

            by_day_utc: dict[str, int] = {}
            by_day_ny: dict[str, int] = {}
            latest_dt = None
            sample_receivedAt_type = None

            for d in docs:
                data = d.to_dict() or {}
                if sample_receivedAt_type is None and field in data:
                    sample_receivedAt_type = type(data.get(field)).__name__
                dt = coerce_dt(data.get(field))
                if not dt:
                    continue

                if (latest_dt is None) or (dt > latest_dt):
                    latest_dt = dt

                day_utc = dt.astimezone(timezone.utc).date().isoformat()
                by_day_utc[day_utc] = by_day_utc.get(day_utc, 0) + 1

                day_ny = dt.astimezone(ny).date().isoformat()
                by_day_ny[day_ny] = by_day_ny.get(day_ny, 0) + 1

            # Build ordered series for last N days
            series_utc = []
            series_ny = []
            for i in range(days - 1, -1, -1):
                day = (now - timedelta(days=i)).date().isoformat()
                series_utc.append({"day": day, "count": by_day_utc.get(day, 0)})

            # NY series anchored to NY date
            now_ny = now.astimezone(ny)
            for i in range(days - 1, -1, -1):
                day = (now_ny - timedelta(days=i)).date().isoformat()
                series_ny.append({"day": day, "count": by_day_ny.get(day, 0)})

            payload = {
                "collection": "kixie_calls",
                "timestamp_field": field,
                "sample_receivedAt_type": sample_receivedAt_type,
                "days": days,
                "latest_utc": (latest_dt.astimezone(timezone.utc).isoformat() if latest_dt else None),
                "series_utc": series_utc,
                "series_ny": series_ny,
                "generated_at_utc": now.isoformat(),
                "debug": {
                    "docs_scanned": len(docs),
                    "last_error": last_error,
                },
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
