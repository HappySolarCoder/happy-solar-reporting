# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/kixie_calls_summary

Metric: Kixie Calls / Connections / Connection Rate

Definition:
- Calls = count of kixie_calls records in date window
- Connections = calls with `duration` > 60 seconds
- Connection rate = connections / calls * 100

Time filter:
- Uses kixie_calls.receivedAt (ISO string) as the canonical time filter.
- Window computed in America/New_York date-only range.

Breakdowns:
- by_agent (agent display name)
- by_day (NY date)

Params:
- start=YYYY-MM-DD&end=YYYY-MM-DD (inclusive end)
- format=json

Collections:
- kixie_calls
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        y, m, d = [int(x) for x in t.split("-")]
        return y, m, d
    except Exception:
        return None


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")

    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    return start_local, end_local


def coerce_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    if isinstance(v, dict) and ("seconds" in v or "_seconds" in v):
        try:
            sec = int(v.get("seconds") or v.get("_seconds") or 0)
            ns = int(v.get("nanos") or v.get("_nanoseconds") or 0)
            return datetime.fromtimestamp(sec + ns / 1e9, tz=timezone.utc)
        except Exception:
            return None
    return None


def is_connection(doc: dict) -> bool:
    """Connection definition (per Evan): duration > 60 seconds."""

    try:
        dur = int(doc.get("duration") or 0)
    except Exception:
        dur = 0

    return dur > 60


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)

        start = (qs.get("start", [""])[0] or "").strip() or None
        end = (qs.get("end", [""])[0] or "").strip() or None

        try:
            if not (start and end):
                raise ValueError("start and end are required (YYYY-MM-DD)")

            tz = "America/New_York"
            start_local, end_local = date_range_window(start, end, tz)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            db = get_db()
            col = db.collection("kixie_calls")

            # receivedAt is stored as ISO string in this dataset, so we cannot do range queries.
            # We stream a bounded sample and filter in code.
            docs = list(col.order_by("receivedAt", direction=firestore.Query.DESCENDING).limit(5000).stream())

            from zoneinfo import ZoneInfo
            ny = ZoneInfo(tz)

            total_calls = 0
            total_connections = 0

            by_agent_calls: dict[str, int] = {}
            by_agent_connections: dict[str, int] = {}

            by_day_calls: dict[str, int] = {}
            by_day_connections: dict[str, int] = {}

            scanned = 0

            for snap in docs:
                scanned += 1
                d = snap.to_dict() or {}
                dt = coerce_dt(d.get("receivedAt"))
                if not dt:
                    continue
                dt_utc = dt.astimezone(timezone.utc)
                if dt_utc < start_utc or dt_utc >= end_utc:
                    continue

                total_calls += 1

                agent = str(d.get("agent") or d.get("agentName") or (str(d.get("fname") or "") + " " + str(d.get("lname") or "")).strip() or "—").strip() or "—"
                day_ny = dt_utc.astimezone(ny).date().isoformat()

                by_agent_calls[agent] = by_agent_calls.get(agent, 0) + 1
                by_day_calls[day_ny] = by_day_calls.get(day_ny, 0) + 1

                if is_connection(d):
                    total_connections += 1
                    by_agent_connections[agent] = by_agent_connections.get(agent, 0) + 1
                    by_day_connections[day_ny] = by_day_connections.get(day_ny, 0) + 1

            # Series across the requested days (NY)
            series = []
            cur = start_local
            while cur < end_local:
                day = cur.date().isoformat()
                c = int(by_day_calls.get(day, 0))
                conn = int(by_day_connections.get(day, 0))
                rate = (conn / c * 100) if c > 0 else None
                series.append({"day": day, "calls": c, "connections": conn, "connection_rate": rate})
                cur = cur + timedelta(days=1)

            by_agent = []
            for agent in sorted(set(by_agent_calls.keys()) | set(by_agent_connections.keys())):
                c = int(by_agent_calls.get(agent, 0))
                conn = int(by_agent_connections.get(agent, 0))
                rate = (conn / c * 100) if c > 0 else None
                by_agent.append({"agent": agent, "calls": c, "connections": conn, "connection_rate": rate})
            by_agent.sort(key=lambda x: (-x["calls"], x["agent"]))

            payload = {
                "metric": "Kixie Calls",
                "unit": "count",
                "timezone": tz,
                "start": start,
                "end": end,
                "calls": total_calls,
                "connections": total_connections,
                "connection_rate": (total_connections / total_calls * 100) if total_calls > 0 else None,
                "by_agent": by_agent,
                "by_day": series,
                "debug": {"scanned_limit": 5000, "docs_streamed": scanned},
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
