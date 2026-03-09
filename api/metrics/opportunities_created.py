# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/opportunities_created

Metric: Opportunities Created
Definition: Opportunities created (front half of the funnel).
Calculation: count distinct opportunities created in included pipelines (Buffalo, Syracuse, Rochester, Virtual),
excluding specific pipelines (Rehash, Sweeper, Inbound/Lead Locker).
Time filter: based on opportunity createdAt (EST month window).

This endpoint supports the two requested “cards” via breakdowns:
- created_by_setter_last_name
- created_by_lead_gen_source

Params:
- year, month (defaults to current UTC year/month)
- format=json

Data sources (v2):
- ghl_opportunities_v2 (grain)
- ghl_pipelines_v2 (pipeline name)
- ghl_users_v2 (owner name)
- ghl_contacts_v2 (setter + lead source)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


@dataclass(frozen=True)
class MetricContract:
    metric_name: str = "Opportunities Created"
    unit: str = "count"

    # collections
    opp_collection: str = "ghl_opportunities_v2"
    contact_collection: str = "ghl_contacts_v2"
    pipeline_collection: str = "ghl_pipelines_v2"
    users_collection: str = "ghl_users_v2"

    # time
    timezone: str = "America/New_York"
    created_at_field: str = "createdAt"  # ISO string

    # pipeline scoping
    included_pipeline_names: tuple[str, ...] = ("buffalo", "syracuse", "rochester", "virtual")
    excluded_pipeline_names: tuple[str, ...] = ("rehash", "sweeper", "inbound/lead locker")

    # breakdown fields (already used in Sales)
    setter_last_name_contact_cf_id: str = "Eq4NLTSkJ56KTxbxypuE"
    lead_gen_source_contact_cf_id: str = "hd5QqHEOVSsPom5bJ32P"


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


def parse_date_ymd(s: str | None) -> tuple[int,int,int] | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        y, m, d = [int(x) for x in t.split('-')]
        return y, m, d
    except Exception:
        return None


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError('Invalid start/end date; expected YYYY-MM-DD')
    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()



def parse_iso_dt(s: str) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def contact_custom_field(contact: dict | None, cf_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def pipeline_name_lookup(db: firestore.Client, c: MetricContract) -> dict[str, str]:
    m: dict[str, str] = {}
    for doc in db.collection(c.pipeline_collection).stream():
        d = doc.to_dict() or {}
        pid = str(d.get("id") or doc.id)
        name = d.get("name")
        if pid and name:
            m[pid] = name
    return m


def user_name_lookup(db: firestore.Client, c: MetricContract) -> dict[str, str]:
    m: dict[str, str] = {}
    for doc in db.collection(c.users_collection).stream():
        u = doc.to_dict() or {}
        uid = str(u.get("id") or doc.id)
        name = u.get("name")
        if not name:
            fn = u.get("firstName") or ""
            ln = u.get("lastName") or ""
            name = (fn + " " + ln).strip() or None
        if uid and name:
            m[uid] = name
    return m


def normalize_channel(v: Any) -> str:
    if v is None:
        return "none"
    if isinstance(v, str):
        norm = v.strip()
        if norm.lower() in {"crm ui", "hand", "", "none", "null", "n/a"}:
            return "none"
        return norm
    return str(v)


def compute(db: firestore.Client, c: MetricContract, *, year: int, month: int, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    if start and end:
        start_local, end_local, start_iso, end_iso = date_range_window(start, end, c.timezone)
    else:
        start_local, end_local, start_iso, end_iso = month_window(year, month, c.timezone)

    pipe_names = pipeline_name_lookup(db, c)
    user_names = user_name_lookup(db, c)

    included = {x.strip().lower() for x in c.included_pipeline_names}
    excluded = {x.strip().lower() for x in c.excluded_pipeline_names}

    # cache contacts
    contact_cache: dict[str, dict | None] = {}

    def get_contact(cid: str) -> dict | None:
        if cid in contact_cache:
            return contact_cache[cid]
        snap = db.collection(c.contact_collection).document(cid).get()
        if snap.exists:
            contact_cache[cid] = snap.to_dict() or {}
            return contact_cache[cid]
        snaps = list(db.collection(c.contact_collection).where('id','==',cid).limit(1).stream())
        contact_cache[cid] = (snaps[0].to_dict() or {}) if snaps else None
        return contact_cache[cid]

    scanned = 0
    in_time = 0
    in_pipeline = 0

    matching_rows: dict[str, dict[str, Any]] = {}

    by_pipeline: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    by_setter: dict[str, int] = {}
    by_lead: dict[str, int] = {}

    for doc in db.collection(c.opp_collection).stream():
        scanned += 1
        opp = doc.to_dict() or {}
        opp_id = str(opp.get("id") or doc.id)

        created = parse_iso_dt(opp.get(c.created_at_field))
        if not created:
            continue
        created_local = created.astimezone(start_local.tzinfo)
        if not (start_local <= created_local < end_local):
            continue
        in_time += 1

        # pipeline include/exclude by resolved pipeline name
        pid = str(opp.get("pipelineId") or "")
        pname = pipe_names.get(pid) or pid or "unknown"
        pname_norm = pname.strip().lower() if isinstance(pname, str) else str(pname).strip().lower()

        if pname_norm in excluded:
            continue
        if included and pname_norm not in included:
            continue
        in_pipeline += 1

        # owner
        owner_id = str(opp.get("assignedTo") or "")
        oname = user_names.get(owner_id) or owner_id or "unassigned"

        # join to contact
        cid = str(opp.get("contactId") or "")
        contact = get_contact(cid) if cid else None
        setter = contact_custom_field(contact, c.setter_last_name_contact_cf_id)
        lead = contact_custom_field(contact, c.lead_gen_source_contact_cf_id)

        lead_norm = normalize_channel(lead)

        # record once, keyed so result always matches list
        matching_rows[opp_id] = {
            "opportunityId": opp_id,
            "pipeline": pname,
            "owner": oname,
            "contactId": cid,
            "contactLastName": (contact.get("lastName") if isinstance(contact, dict) else None),
            "createdAt": opp.get(c.created_at_field),
            "setterLastName": setter,
            "leadGenSource": lead_norm,
        }

        by_pipeline[pname] = by_pipeline.get(pname, 0) + 1
        by_owner[oname] = by_owner.get(oname, 0) + 1
        if setter:
            key = str(setter).strip()
            by_setter[key] = by_setter.get(key, 0) + 1
        by_lead[lead_norm] = by_lead.get(lead_norm, 0) + 1

    return {
        "metric": c.metric_name,
        "unit": c.unit,
        "year": year,
        "month": month,
        "timezone": c.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "result": len(matching_rows),
        "count_method": (
            "COUNT_DISTINCT(ghl_opportunities_v2.id) where createdAt in window (America/New_York) "
            "and pipeline in {Buffalo,Syracuse,Rochester,Virtual} excluding {Rehash,Sweeper,Inbound/Lead Locker}"
        ),
        "debug": {
            "opps_scanned": scanned,
            "opps_in_time_window": in_time,
            "opps_in_time_and_pipeline_scope": in_pipeline,
            "rows_listed": len(matching_rows),
        },
        "contract": {
            "base_collection": c.opp_collection,
            "time_field": f"{c.opp_collection}.{c.created_at_field}",
            "time_handling": "Parse ISO -> convert to America/New_York -> compare to month window",
            "pipeline_field": f"{c.opp_collection}.pipelineId -> {c.pipeline_collection}.name",
            "included_pipeline_names": list(c.included_pipeline_names),
            "excluded_pipeline_names": list(c.excluded_pipeline_names),
            "owner_field": f"{c.opp_collection}.assignedTo -> {c.users_collection}.name",
            "setter_field": f"{c.contact_collection}.customFields[{c.setter_last_name_contact_cf_id}]",
            "lead_gen_source_field": f"{c.contact_collection}.customFields[{c.lead_gen_source_contact_cf_id}] (normalized to none)",
        },
        "breakdowns": {
            "created_by_pipeline": {k: v for k, v in sorted(by_pipeline.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "created_by_owner": {k: v for k, v in sorted(by_owner.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "created_by_setter_last_name": {k: v for k, v in sorted(by_setter.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "created_by_lead_gen_source": {k: v for k, v in sorted(by_lead.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
        },
        "sample_rows": sorted(list(matching_rows.values()), key=lambda r: (r.get("createdAt") or "")),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = payload.get("sample_rows", [])

    tr = []
    for r in rows:
        tr.append(
            "<tr>"
            f"<td><code>{r.get('opportunityId','')}</code></td>"
            f"<td>{(r.get('contactLastName') or '')}</td>"
            f"<td>{(r.get('pipeline') or '')}</td>"
            f"<td>{(r.get('owner') or '')}</td>"
            f"<td><code>{(r.get('createdAt') or '')}</code></td>"
            f"<td>{(r.get('setterLastName') or '')}</td>"
            f"<td>{(r.get('leadGenSource') or '')}</td>"
            "</tr>"
        )

    rows_html = "\n".join(tr) if tr else "<tr><td colspan='7' style='padding:8px'>No rows</td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>QA — Opportunities Created</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#0b0f14;color:#e8eef6;}}
.wrap{{padding:18px;max-width:1180px;margin:0 auto;}}
.card{{background:#121a24;border:1px solid #1f2a38;border-radius:12px;padding:16px;margin-top:12px;}}
.label{{color:#9db0c7;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}}
.kpi{{font-size:44px;font-weight:900;}}
code{{background:#0e1520;padding:2px 6px;border-radius:6px;}}
th,td{{border-bottom:1px solid #1f2a38;padding:8px;font-size:12px;}}
th{{color:#9db0c7;text-align:left;}}
</style></head>
<body><div class="wrap">
<div class="card" style="background:linear-gradient(135deg,#00C853 0%,#1b5e20 100%);border:none;">
  <div style="font-weight:900;font-size:18px">QA — Opportunities Created</div>
  <div style="opacity:.9">Window: {payload['window_start_local']} → {payload['window_end_local']} ({payload['timezone']})</div>
</div>
<div class="card"><div class="label">Result</div><div class="kpi">{payload['result']}</div>
<div style="color:#9db0c7">{payload['count_method']}</div>
<div style="margin-top:8px">JSON: <a style="color:#6ee7b7" href="?format=json">?format=json</a></div>
</div>
<div class="card"><div class="label">Contract</div>
<pre style="white-space:pre-wrap;color:#9db0c7">{json.dumps(payload['contract'], indent=2)}</pre>
</div>
<div class="card"><div class="label">Matching opportunities (all)</div>
<table style="width:100%; border-collapse: collapse; margin-top: 10px;">
<thead><tr>
<th>opportunityId</th><th>contact last</th><th>pipeline</th><th>owner</th><th>createdAt</th><th>setter</th><th>lead source</th>
</tr></thead>
<tbody>
{rows_html}
</tbody></table>
</div>
</div></body></html>"""


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

            c = MetricContract()
            db = get_db()
            payload = compute(db, c, year=year, month=month, start=start, end=end)

            if want_json:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
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
