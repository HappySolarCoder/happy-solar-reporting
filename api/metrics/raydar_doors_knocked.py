# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/raydar_doors_knocked

Metric: Raydar — Dispositioned Leads (Doors Knocked)

Business rule (canonical):
- Include a lead if raydar_leads_v1.dispositionedAt is non-null.
- Time filter field: raydar_leads_v1.dispositionedAt (Firestore Timestamp)
- Reporting windows computed in America/New_York.

Params:
- start=YYYY-MM-DD (optional; date-only, America/New_York)
- end=YYYY-MM-DD (optional; date-only, inclusive, America/New_York)
- period (optional) today|yesterday|7d|thiswk|lastwk|thismo|lastmo|all
- year (int) default current UTC year (used if no start/end/period)
- month (int) 1-12 default current UTC month (used if no start/end/period)
- format=json (optional)

Output:
- HTML QA page by default
- JSON if ?format=json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


@dataclass(frozen=True)
class MetricContract:
    metric_name: str = "Raydar — Doors Knocked"
    unit: str = "count"

    timezone: str = "America/New_York"  # MANDATORY

    leads_collection: str = "raydar_leads_v1"
    users_collection: str = "raydar_users_v1"

    time_field: str = "dispositionedAt"  # Firestore Timestamp


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


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)

    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def period_window(period: str, tz_name: str) -> tuple[datetime, datetime, str, str, str]:
    """Return (start_local, end_local, start_iso, end_iso, label).

    Period values (Raydar-style): today, yesterday, 7d, thiswk, lastwk, thismo, lastmo, all
    All boundaries computed in America/New_York.
    """

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    p = (period or "").strip().lower()

    # Helpers
    def start_of_day(d: datetime) -> datetime:
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)

    if p == "today":
        start = start_of_day(now)
        end = now
        label = "Today"
    elif p == "yesterday":
        y = now - timedelta(days=1)
        start = start_of_day(y)
        end = start_of_day(now)
        label = "Yesterday"
    elif p in ("7d", "7days", "7_days", "7 days"):
        start = now - timedelta(days=7)
        end = now
        label = "7 Days"
    elif p == "thiswk":
        # Week starts Monday
        start = start_of_day(now) - timedelta(days=now.weekday())
        end = now
        label = "This Wk"
    elif p == "lastwk":
        this_start = start_of_day(now) - timedelta(days=now.weekday())
        start = this_start - timedelta(days=7)
        end = this_start
        label = "Last Wk"
    elif p == "thismo":
        start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=tz)
        end = now
        label = "This Mo"
    elif p == "lastmo":
        if now.month == 1:
            y, m = now.year - 1, 12
        else:
            y, m = now.year, now.month - 1
        start = datetime(y, m, 1, 0, 0, 0, tzinfo=tz)
        # end is start of this month
        end = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=tz)
        label = "Last Mo"
    elif p == "all":
        start = datetime(1970, 1, 1, 0, 0, 0, tzinfo=tz)
        end = now
        label = "All"
    else:
        raise ValueError(f"Unsupported period: {period}")

    return start, end, start.isoformat(), end.isoformat(), label


def parse_int(qs: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(qs.get(key, [str(default)])[0])
    except Exception:
        return default


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        parts = t.split('-')
        if len(parts) != 3:
            return None
        y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
        if y < 2000 or m < 1 or m > 12 or d < 1 or d > 31:
            return None
        return y, m, d
    except Exception:
        return None


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str, str]:
    """Date-only range in tz, end date inclusive (full day).

    Returns (start_local, end_local_exclusive, start_iso, end_iso, label).
    """

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError('Invalid start/end date; expected YYYY-MM-DD')

    sy, sm, sd = sp
    ey, em, ed = ep

    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local_inclusive = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz)
    end_local_exclusive = end_local_inclusive + timedelta(days=1)

    label = f"{start_ymd} → {end_ymd}"
    return start_local, end_local_exclusive, start_local.isoformat(), end_local_exclusive.isoformat(), label



def user_name_map(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection(MetricContract.users_collection).stream():
        d = snap.to_dict() or {}
        out[str(snap.id)] = str(d.get("name") or snap.id)
    return out


def build_payload(db: firestore.Client, year: int, month: int, period: str | None = None, start: str | None = None, end: str | None = None) -> dict:
    from zoneinfo import ZoneInfo

    if start and end:
        start_local, end_local, start_iso, end_iso, period_label = date_range_window(start, end, MetricContract.timezone)
        period = None
    elif period:
        start_local, end_local, start_iso, end_iso, period_label = period_window(period, MetricContract.timezone)
    else:
        start_local, end_local, start_iso, end_iso = month_window(year, month, MetricContract.timezone)
        period_label = "Month"

    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    # Query: dispositionedAt in window (nulls excluded implicitly by >=)
    q = (
        db.collection(MetricContract.leads_collection)
        .where(MetricContract.time_field, ">=", start_utc)
        .where(MetricContract.time_field, "<", end_utc)
        .order_by(MetricContract.time_field)
    )

    # Breakdown: knocks by user (claimedBy / assignedTo)
    # Note: Firestore doesn't support group-by server-side; stream the filtered docs.
    by_claimed: dict[str, int] = {}
    by_assigned: dict[str, int] = {}

    streamed = 0
    for snap in q.stream():
        streamed += 1
        d = snap.to_dict() or {}
        cb = d.get('claimedBy')
        at = d.get('assignedTo')
        if cb not in (None, ''):
            k = str(cb)
            by_claimed[k] = by_claimed.get(k, 0) + 1
        if at not in (None, ''):
            k = str(at)
            by_assigned[k] = by_assigned.get(k, 0) + 1

    # Count
    result = streamed
    count_method = 'stream_len'

    # Sample rows (first 25)
    docs = list(q.limit(25).stream())
    users = user_name_map(db)

    sample_rows: list[dict[str, Any]] = []
    for snap in docs:
        d = snap.to_dict() or {}
        ts = d.get(MetricContract.time_field)
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else None
        claimed_by = d.get("claimedBy")
        assigned_to = d.get("assignedTo")
        sample_rows.append(
            {
                "leadId": snap.id,
                "dispositionedAt": ts_iso,
                "claimedBy": claimed_by,
                "claimedByName": users.get(str(claimed_by), claimed_by),
                "assignedTo": assigned_to,
                "assignedToName": users.get(str(assigned_to), assigned_to),
                "city": d.get("city"),
                "state": d.get("state"),
                "zip": d.get("zip"),
                "status": d.get("status"),
            }
        )

    return {
        "metric": MetricContract.metric_name,
        "unit": MetricContract.unit,
        "year": year,
        "month": month,
        "period": period or None,
        "start": start or None,
        "end": end or None,
        "period_label": period_label,
        "timezone": MetricContract.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "result": int(result),
        "count_method": count_method,
        "contract": {
            "collection": MetricContract.leads_collection,
            "time_field": f"{MetricContract.leads_collection}.{MetricContract.time_field} (Timestamp)",
            "inclusion": "dispositionedAt is non-null (enforced by >= start)",
        },
        "breakdowns": {
            "knocks_by_claimed_by": by_claimed,
            "knocks_by_assigned_to": by_assigned,
        },
        "top_knockers": [
            {
                "userId": uid,
                "name": users.get(uid, uid),
                "knocks": cnt,
            }
            for uid, cnt in sorted(by_claimed.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        ],
        "sample_rows": sample_rows,
    }


def html_page(payload: dict) -> str:
    def esc(x: Any) -> str:
        return (
            str(x)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    rows = payload.get("sample_rows") or []
    table_rows = "".join(
        f"<tr><td>{esc(r.get('leadId'))}</td><td>{esc(r.get('dispositionedAt'))}</td><td>{esc(r.get('claimedByName'))}</td><td>{esc(r.get('assignedToName'))}</td><td>{esc(r.get('city'))}</td><td>{esc(r.get('state'))}</td><td>{esc(r.get('zip'))}</td></tr>"
        for r in rows
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>QA — Raydar Doors Knocked</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system; margin: 0; background:#0b1220; color:#e5e7eb; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .title {{ font-size: 20px; font-weight: 950; }}
    .sub {{ color:#9ca3af; margin-top:4px; }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap: 12px; margin-top: 14px; }}
    .card {{ grid-column: span 4; background:#0f172a; border:1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 14px; }}
    .wide {{ grid-column: span 12; }}
    .label {{ color:#9ca3af; font-size: 12px; font-weight: 900; }}
    .kpi {{ font-size: 42px; font-weight: 950; margin-top: 6px; }}
    .meta {{ color:#9ca3af; font-size: 12px; margin-top: 6px; }}
    code {{ background:#0b1020; padding:2px 6px; border-radius: 8px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,0.06); padding: 8px 10px; font-size: 12px; text-align:left; }}
    th {{ color:#9ca3af; font-weight: 900; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"title\">QA — Raydar Doors Knocked</div>
    <div class=\"sub\">Window: {esc(payload.get('window_start_local'))} → {esc(payload.get('window_end_local'))} ({esc(payload.get('timezone'))})</div>

    <div class=\"grid\">
      <div class=\"card\">
        <div class=\"label\">Result</div>
        <div class=\"kpi\">{esc(payload.get('result'))}</div>
        <div class=\"meta\">COUNT where <code>raydar_leads_v1.dispositionedAt</code> in window</div>
        <div class=\"meta\"><a style=\"color:#93c5fd\" href=\"?format=json&year={esc(payload.get('year'))}&month={esc(payload.get('month'))}\">?format=json</a></div>
      </div>

      <div class=\"card\">
        <div class=\"label\">Count method</div>
        <div class=\"kpi\" style=\"font-size:18px\">{esc(payload.get('count_method'))}</div>
        <div class=\"meta\">Uses Firestore count aggregation when available</div>
      </div>

      <div class=\"card\">
        <div class=\"label\">Contract</div>
        <div class=\"meta\"><code>{esc((payload.get('contract') or {}).get('collection'))}</code></div>
        <div class=\"meta\"><code>{esc((payload.get('contract') or {}).get('time_field'))}</code></div>
      </div>

      <div class=\"card wide\">
        <div class=\"label\">Sample rows (first 25)</div>
        <table>
          <thead>
            <tr>
              <th>leadId</th>
              <th>dispositionedAt</th>
              <th>claimedBy</th>
              <th>assignedTo</th>
              <th>city</th>
              <th>state</th>
              <th>zip</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        now = datetime.utcnow()

        year = parse_int(qs, "year", now.year)
        month = parse_int(qs, "month", now.month)
        period = (qs.get("period", [""])[0] or "").strip() or None
        start = (qs.get("start", [""])[0] or "").strip() or None
        end = (qs.get("end", [""])[0] or "").strip() or None
        fmt = (qs.get("format", [""])[0] or "").lower()

        try:
            db = get_db()
            payload = build_payload(db, year, month, period, start, end)

            if fmt == "json":
                body = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = html_page(payload).encode("utf-8")
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
