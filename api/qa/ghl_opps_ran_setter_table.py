# -*- coding: utf-8 -*-

"""Vercel Python function: /api/qa/ghl_opps_ran_setter_table

QA: list the exact opportunities that feed the FMS "GHL — Demo Rate by Setter" table.

Business logic source: GHLMetrics.md
- Time filter field: ghl_opportunities_v2.appointmentOccurredAt
- Ran qualification: dispositionValue in (Sit, No Sit)
- Setter: ghl_contacts_v2.customFields[Eq4NLTSkJ56KTxbxypuE] via contactId join
- Pipeline scope: included buffalo/rochester/virtual/syracuse; excluded rehash/sweeper/inbound/lead locker

Params:
- year, month (default current UTC)
- start=YYYY-MM-DD, end=YYYY-MM-DD (optional; date-only inclusive; America/New_York)
- format=json (optional)

Output:
- HTML table (default)
- JSON payload for debugging
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


@dataclass(frozen=True)
class Contract:
    timezone: str = "America/New_York"

    opps: str = "ghl_opportunities_v2"
    contacts: str = "ghl_contacts_v2"
    pipelines: str = "ghl_pipelines_v2"

    time_field: str = "appointmentOccurredAt"  # Timestamp
    disposition_field: str = "dispositionValue"  # derived field

    setter_cf_id: str = "Eq4NLTSkJ56KTxbxypuE"

    included_pipeline_names: tuple[str, ...] = ("buffalo", "rochester", "virtual", "syracuse")
    excluded_pipeline_names: tuple[str, ...] = ("rehash", "sweeper", "inbound/lead locker")


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
        y, m, d = [int(x) for x in t.split("-")]
        return y, m, d
    except Exception:
        return None


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
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
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def pipeline_name_lookup(db: firestore.Client, c: Contract) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in db.collection(c.pipelines).stream():
        d = doc.to_dict() or {}
        pid = str(d.get("id") or doc.id)
        name = d.get("name")
        if pid and name:
            out[pid] = str(name)
    return out


def contact_lookup(db: firestore.Client, c: Contract, contact_id: str) -> dict | None:
    if not contact_id:
        return None

    snap = db.collection(c.contacts).document(contact_id).get()
    if snap.exists:
        return snap.to_dict() or {}

    # fallback by id field
    snaps = list(db.collection(c.contacts).where("id", "==", contact_id).limit(1).stream())
    return (snaps[0].to_dict() or {}) if snaps else None


def contact_custom_field(contact: dict | None, cf_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def html_escape(x: Any) -> str:
    return (
        str(x)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compute(db: firestore.Client, c: Contract, *, year: int, month: int, start: str | None, end: str | None) -> dict[str, Any]:
    if start and end:
        start_local, end_local, start_iso, end_iso = date_range_window(start, end, c.timezone)
    else:
        start_local, end_local, start_iso, end_iso = month_window(year, month, c.timezone)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    pipe_names = pipeline_name_lookup(db, c)
    included = {x.lower() for x in c.included_pipeline_names}
    excluded = {x.lower() for x in c.excluded_pipeline_names}

    # Range query (fast)
    q = (
        db.collection(c.opps)
        .where(c.time_field, ">=", start_utc)
        .where(c.time_field, "<", end_utc)
    )

    rows: list[dict[str, Any]] = []
    ran_by_setter: dict[str, int] = {}
    sit_by_setter: dict[str, int] = {}

    scanned = 0
    for snap in q.stream():
        scanned += 1
        opp = snap.to_dict() or {}

        dispo = opp.get(c.disposition_field)
        if dispo not in ("Sit", "No Sit"):
            continue

        pid = str(opp.get("pipelineId") or "")
        pname = (pipe_names.get(pid) or "").strip()
        pname_low = pname.lower()

        if not pname_low:
            continue
        if pname_low in excluded:
            continue
        if pname_low not in included:
            continue

        cid = str(opp.get("contactId") or "")
        contact = contact_lookup(db, c, cid)
        setter = contact_custom_field(contact, c.setter_cf_id)
        setter_s = str(setter).strip() if setter not in (None, "") else "none"

        ran_by_setter[setter_s] = ran_by_setter.get(setter_s, 0) + 1
        if dispo == "Sit":
            sit_by_setter[setter_s] = sit_by_setter.get(setter_s, 0) + 1

        occ = opp.get(c.time_field)
        occ_iso = occ.isoformat() if hasattr(occ, "isoformat") else str(occ)

        rows.append(
            {
                "opportunityId": str(opp.get("id") or snap.id),
                "contactId": cid,
                "setterLastName": setter_s,
                "pipeline": pname,
                "dispositionValue": dispo,
                "appointmentOccurredAt": occ_iso,
            }
        )

    # Compute demo% by setter
    demo_pct_by_setter: dict[str, float] = {}
    for setter, ran in ran_by_setter.items():
        sit = sit_by_setter.get(setter, 0)
        demo_pct_by_setter[setter] = round((sit / ran) * 100, 1) if ran else 0.0

    # Sort rows by occurred time (string iso sorts ok)
    rows_sorted = sorted(rows, key=lambda r: (r.get("appointmentOccurredAt") or ""), reverse=True)

    return {
        "metric": "QA — GHL Opps Ran by Setter (feeds FMS table)",
        "timezone": c.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "filters": {
            "time_field": f"{c.opps}.{c.time_field}",
            "disposition_value": ["Sit", "No Sit"],
            "pipelines_included": list(c.included_pipeline_names),
            "pipelines_excluded": list(c.excluded_pipeline_names),
            "setter_field": f"{c.contacts}.customFields[{c.setter_cf_id}]",
        },
        "debug": {
            "opps_scanned": scanned,
            "rows_counted": len(rows_sorted),
        },
        "breakdowns": {
            "ran_by_setter_last_name": ran_by_setter,
            "sit_by_setter_last_name": sit_by_setter,
            "demo_pct_by_setter_last_name": demo_pct_by_setter,
        },
        "rows": rows_sorted,
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []

    # Build rows HTML
    trs = []
    for r in rows:
        trs.append(
            "<tr>"
            f"<td>{html_escape(r.get('setterLastName'))}</td>"
            f"<td>{html_escape(r.get('pipeline'))}</td>"
            f"<td>{html_escape(r.get('dispositionValue'))}</td>"
            f"<td><code>{html_escape(r.get('appointmentOccurredAt'))}</code></td>"
            f"<td><code>{html_escape(r.get('opportunityId'))}</code></td>"
            f"<td><code>{html_escape(r.get('contactId'))}</code></td>"
            "</tr>"
        )

    table_html = "\n".join(trs) if trs else "<tr><td colspan='6' style='padding:12px'>No rows</td></tr>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QA — GHL Opps Ran by Setter (FMS)</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system; margin: 0; background:#0b1220; color:#e5e7eb; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .title {{ font-size: 18px; font-weight: 950; }}
    .sub {{ color:#9ca3af; margin-top:4px; font-size: 12px; }}
    .card {{ background:#0f172a; border:1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 14px; margin-top: 12px; }}
    code {{ background:#0b1020; padding:2px 6px; border-radius: 8px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,0.06); padding: 8px 10px; font-size: 12px; text-align:left; }}
    th {{ color:#9ca3af; font-weight: 900; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">QA — GHL Opps Ran by Setter (feeds FMS table)</div>
    <div class="sub">Window: {html_escape(payload.get('window_start_local'))} → {html_escape(payload.get('window_end_local'))} ({html_escape(payload.get('timezone'))})</div>

    <div class="card">
      <div class="sub">JSON: <a style="color:#93c5fd" href="?format=json">?format=json</a></div>
      <div class="sub">Counted rows: <b>{html_escape(payload.get('debug',{}).get('rows_counted'))}</b> • Scanned: {html_escape(payload.get('debug',{}).get('opps_scanned'))}</div>
    </div>

    <div class="card">
      <div style="font-weight:900">Rows (each counted opportunity)</div>
      <table>
        <thead>
          <tr>
            <th>Setter</th>
            <th>Pipeline</th>
            <th>Disposition</th>
            <th>appointmentOccurredAt</th>
            <th>opportunityId</th>
            <th>contactId</th>
          </tr>
        </thead>
        <tbody>
          {table_html}
        </tbody>
      </table>
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
        start = (qs.get("start", [""])[0] or "").strip() or None
        end = (qs.get("end", [""])[0] or "").strip() or None
        fmt = (qs.get("format", [""])[0] or "").lower()

        try:
            db = get_db()
            payload = compute(db, Contract(), year=year, month=month, start=start, end=end)

            if fmt == "json":
                body = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(payload).encode("utf-8")
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
