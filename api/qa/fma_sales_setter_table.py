# -*- coding: utf-8 -*-

"""Vercel Python function: /api/qa/fma_sales_setter_table

QA endpoint for the FMA "Sales" column shown in the
"GHL — Demo Rate by Setter" table.

Returns ALL counted sales rows for the requested window with:
- setterLastName
- dateSold (YYYY-MM-DD)
- rep
- customerLastName

Optional filters:
- start=YYYY-MM-DD&end=YYYY-MM-DD (date-only, end inclusive; America/New_York)
- or year=YYYY&month=M
- lead_source=<Doors|Phones|3PL|none|...>
- format=json (default is HTML)
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
class Contract:
    timezone: str = "America/New_York"

    opps: str = "ghl_opportunities_v2"
    contacts: str = "ghl_contacts_v2"
    users: str = "ghl_users_v2"

    sold_date_contact_cf_id: str = "P9oBjgbZjJdeE0OkBj9T"
    setter_contact_cf_id: str = "Eq4NLTSkJ56KTxbxypuE"
    lead_source_contact_cf_id: str = "hd5QqHEOVSsPom5bJ32P"

    stage_field: str = "pipelineStageId"
    opp_id_field: str = "id"

    # Sold + Sale Cancelled (Buffalo, Syracuse, Rochester, Virtual)
    stage_ids: tuple[str, ...] = (
        "7981f111-73f2-4593-9662-6b95d99bf51a",
        "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
        "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
        "34a1882f-7959-4d22-878d-91fe35a42907",
        "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
        "9bd71abf-7285-47bb-8800-a255e7b90630",
        "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
        "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
    )


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


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[str, str, str, str]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")

    sy, sm, sd = sp
    ey, em, ed = ep

    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_excl = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

    return start_local.date().isoformat(), end_excl.date().isoformat(), start_local.isoformat(), end_excl.isoformat()


def month_window(year: int, month: int, tz_name: str) -> tuple[str, str, str, str]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)

    return start_local.date().isoformat(), end_local.date().isoformat(), start_local.isoformat(), end_local.isoformat()


def contact_custom_field(contact: dict | None, cf_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def normalize_lead_source(v: Any) -> str:
    if v is None:
        return "none"
    s = str(v).strip()
    if s.lower() in {"", "none", "null", "n/a", "crm ui", "hand"}:
        return "none"
    return s


def user_name(users_col: firestore.CollectionReference, cache: dict[str, str], uid: str | None) -> str:
    if not uid:
        return "unassigned"
    k = str(uid)
    if k in cache:
        return cache[k]
    snaps = list(users_col.where("id", "==", k).limit(1).stream())
    if not snaps:
        cache[k] = k
        return k
    d = snaps[0].to_dict() or {}
    nm = d.get("name")
    if not nm:
        nm = ((d.get("firstName") or "") + " " + (d.get("lastName") or "")).strip() or k
    cache[k] = str(nm)
    return cache[k]


def html_escape(x: Any) -> str:
    return (
        str(x)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compute(db: firestore.Client, c: Contract, *, year: int, month: int, start: str | None, end: str | None, lead_source: str | None) -> dict[str, Any]:
    if start and end:
        start_date_str, end_date_str, start_iso, end_iso = date_range_window(start, end, c.timezone)
    else:
        start_date_str, end_date_str, start_iso, end_iso = month_window(year, month, c.timezone)

    stage_set = set(c.stage_ids)
    contacts_col = db.collection(c.contacts)
    users_col = db.collection(c.users)

    contact_cache: dict[str, dict | bool] = {}
    user_cache: dict[str, str] = {}

    rows: list[dict[str, Any]] = []
    sales_by_setter: dict[str, int] = {}

    scanned = 0
    matched_stage = 0
    matched_date = 0

    for opp_snap in db.collection(c.opps).stream():
        scanned += 1
        opp = opp_snap.to_dict() or {}

        stage_id = opp.get(c.stage_field)
        if stage_id not in stage_set:
            continue
        matched_stage += 1

        contact_id = str(opp.get("contactId") or "")
        if not contact_id:
            continue

        contact = contact_cache.get(contact_id)
        if contact is None:
            snaps = list(contacts_col.where("id", "==", contact_id).limit(1).stream())
            if not snaps:
                contact_cache[contact_id] = False
                continue
            contact = snaps[0].to_dict() or {}
            contact_cache[contact_id] = contact
        if contact is False:
            continue

        sold_raw = contact_custom_field(contact, c.sold_date_contact_cf_id)
        sold_date = sold_raw[:10] if isinstance(sold_raw, str) and len(sold_raw) >= 10 else None
        if not sold_date:
            continue

        # Date-only compare (locked business rule)
        if not (start_date_str <= sold_date < end_date_str):
            continue
        matched_date += 1

        ls = normalize_lead_source(contact_custom_field(contact, c.lead_source_contact_cf_id))
        if lead_source and ls.lower() != str(lead_source).strip().lower():
            continue

        setter = contact_custom_field(contact, c.setter_contact_cf_id)
        setter_bucket = str(setter).strip() if setter not in (None, "") else "none"

        rep = user_name(users_col, user_cache, opp.get("assignedTo"))
        customer_last = str(contact.get("lastName") or "")
        opp_id = str(opp.get(c.opp_id_field) or opp_snap.id)

        rows.append(
            {
                "opportunityId": opp_id,
                "setterLastName": setter_bucket,
                "dateSold": sold_date,
                "rep": rep,
                "customerLastName": customer_last,
            }
        )
        sales_by_setter[setter_bucket] = sales_by_setter.get(setter_bucket, 0) + 1

    rows.sort(key=lambda r: (r.get("dateSold") or "", r.get("setterLastName") or "", r.get("customerLastName") or ""), reverse=True)

    return {
        "metric": "QA — FMA Sales Column Rows",
        "timezone": c.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "filters": {
            "sold_date_field": f"{c.contacts}.customFields[{c.sold_date_contact_cf_id}]",
            "setter_field": f"{c.contacts}.customFields[{c.setter_contact_cf_id}]",
            "lead_source_field": f"{c.contacts}.customFields[{c.lead_source_contact_cf_id}]",
            "lead_source": lead_source,
            "included_stage_ids": list(c.stage_ids),
        },
        "debug": {
            "opps_scanned": scanned,
            "opps_matched_stage": matched_stage,
            "opps_matched_stage_and_sold_date": matched_date,
            "rows_counted": len(rows),
        },
        "breakdowns": {
            "sales_by_setter_last_name": dict(sorted(sales_by_setter.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
        "rows": rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    body_rows = "".join(
        "<tr>"
        f"<td><code>{html_escape(r.get('setterLastName'))}</code></td>"
        f"<td>{html_escape(r.get('dateSold'))}</td>"
        f"<td>{html_escape(r.get('rep'))}</td>"
        f"<td>{html_escape(r.get('customerLastName'))}</td>"
        f"<td><code>{html_escape(r.get('opportunityId'))}</code></td>"
        "</tr>"
        for r in rows
    )

    if not body_rows:
        body_rows = '<tr><td colspan="5">No rows in this window.</td></tr>'

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>QA — FMA Sales Column Rows</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:#0b0f14; color:#e8eef6; }}
    .wrap {{ padding: 18px; max-width: 1200px; margin: 0 auto; }}
    .card {{ background:#121a24; border:1px solid #1f2a38; border-radius:12px; padding:16px; margin-top:12px; }}
    .kpi {{ font-size:44px; font-weight:900; }}
    .label {{ color:#9db0c7; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    code {{ background:#0e1520; padding:2px 6px; border-radius:6px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom:1px solid #1f2a38; padding:8px; text-align:left; font-size: 13px; }}
    th {{ color:#9db0c7; font-weight:700; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h2 style=\"margin:0 0 6px 0\">QA — FMA Sales Column Rows</h2>
    <div style=\"opacity:.9\">Window: {html_escape(payload.get('window_start_local'))} → {html_escape(payload.get('window_end_local'))} ({html_escape(payload.get('timezone'))})</div>

    <div class=\"card\">
      <div class=\"label\">Counted Sales Rows</div>
      <div class=\"kpi\">{len(rows)}</div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Rows</div>
      <table>
        <thead>
          <tr><th>Setter Last Name</th><th>Date Sold</th><th>Rep</th><th>Customer Last Name</th><th>Opportunity ID</th></tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
    </div>

    <div style=\"margin-top:12px; color:#9db0c7; font-size:12px\">Generated at {html_escape(payload.get('generated_at'))}</div>
  </div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = qs.get("format", [""])[0].lower() == "json"

            now = datetime.utcnow()
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            start = (qs.get("start", [""])[0] or "").strip() or None
            end = (qs.get("end", [""])[0] or "").strip() or None
            lead_source = (qs.get("lead_source", [""])[0] or "").strip() or None

            db = get_db()
            c = Contract()
            payload = compute(db, c, year=year, month=month, start=start, end=end, lead_source=lead_source)

            if want_json:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
            self.end_headers()
            self.wfile.write(body)
