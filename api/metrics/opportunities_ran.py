# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/opportunities_ran

Metric: Opportunities Ran
Definition: Opportunities/Appointments that have been completed (dispositioned).
Logic: Opportunity is considered 'ran' if custom field "What happened with Appointment?" is non-empty.
Time filter: based on opportunity appointmentOccurredAt (EST month window).

Params:
- year, month (default current UTC year/month)
- format=json

Data sources (v2):
- ghl_opportunities_v2 (grain)
- ghl_pipelines_v2 (pipeline name)
- ghl_users_v2 (owner name)
- ghl_contacts_v2 (for lead source + setter breakdowns)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


@dataclass(frozen=True)
class MetricContract:
    metric_name: str = "Opportunities Ran"
    unit: str = "count"

    # collections
    opp_collection: str = "ghl_opportunities_v2"
    contact_collection: str = "ghl_contacts_v2"
    pipeline_collection: str = "ghl_pipelines_v2"
    users_collection: str = "ghl_users_v2"

    # time
    timezone: str = "America/New_York"  # MANDATORY

    # Stable occurred timestamp (backfilled from CSV; future logic can set at disposition time)
    appointment_occurred_at_field: str = "appointmentOccurredAt"  # Firestore Timestamp/datetime

    # Disposition field: "What happened with Appointment?"
    # Identified from live v2 opportunity customFields sample: id=GYGpLKBPfMpiBqyU2ogQ value='No Sit'
    what_happened_custom_field_id: str = "GYGpLKBPfMpiBqyU2ogQ"

    # Exclusions
    excluded_pipeline_names: tuple[str, ...] = ("sweeper", "rehash")

    # breakdown fields (reuse contact custom fields we already identified)
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


def parse_iso_dt(s: str) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def as_dt(v: Any) -> datetime | None:
    """Coerce Firestore Timestamp/datetime/ISO string to datetime."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def cf_value(cf: dict) -> Any:
    # Opportunities use fieldValueString/fieldValueNumber/...; contacts use value.
    if not isinstance(cf, dict):
        return None
    if cf.get("value") not in (None, ""):
        return cf.get("value")
    for k in ("fieldValueString", "fieldValueNumber", "fieldValueBoolean"):
        if k in cf and cf.get(k) not in (None, ""):
            return cf.get(k)
    return None


def contact_custom_field(contact: dict, cf_id: str) -> Any:
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def pipeline_name_lookup(db: firestore.Client) -> dict[str, str]:
    m = {}
    for doc in db.collection("ghl_pipelines_v2").stream():
        d = doc.to_dict() or {}
        pid = str(d.get("id") or doc.id)
        name = d.get("name")
        if pid and name:
            m[pid] = name
    return m


def user_name_lookup(db: firestore.Client) -> dict[str, str]:
    m = {}
    for doc in db.collection("ghl_users_v2").stream():
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


def compute(db: firestore.Client, c: MetricContract, *, year: int, month: int) -> dict[str, Any]:
    start_local, end_local, start_iso, end_iso = month_window(year, month, c.timezone)

    # lookup maps (small; ok for QA)
    pipe_names = pipeline_name_lookup(db)
    user_names = user_name_lookup(db)

    # cache contacts
    contact_cache: dict[str, dict | None] = {}

    def get_contact(cid: str) -> dict | None:
        if cid in contact_cache:
            return contact_cache[cid]
        snap = db.collection(c.contact_collection).document(cid).get()
        if snap.exists:
            contact_cache[cid] = snap.to_dict() or {}
            return contact_cache[cid]
        # fallback
        snaps = list(db.collection(c.contact_collection).where('id','==',cid).limit(1).stream())
        contact_cache[cid] = (snaps[0].to_dict() or {}) if snaps else None
        return contact_cache[cid]

    scanned = 0
    matched_dispo = 0
    matched_time = 0

    distinct_opp_ids: set[str] = set()

    by_pipeline: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    by_setter: dict[str, int] = {}
    by_lead: dict[str, int] = {}

    matching_rows: dict[str, dict[str, Any]] = {}

    # Firestore query: only scan opportunities in the time window (big speedup)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    opp_query = (
        db.collection(c.opp_collection)
        .where(c.appointment_occurred_at_field, ">=", start_utc)
        .where(c.appointment_occurred_at_field, "<", end_utc)
    )

    for doc in opp_query.stream():
        scanned += 1
        opp = doc.to_dict() or {}
        opp_id = str(opp.get("id") or doc.id)

        # disposition check (use derived field for speed)
        dispo_val = opp.get("dispositionValue")
        if dispo_val not in ("Sit", "No Sit"):
            continue
        matched_dispo += 1

        # time window check already handled by Firestore query, but keep counters consistent
        matched_time += 1

        # distinct count
        # pipeline (and exclusions)
        pid = str(opp.get("pipelineId") or "")
        pname = pipe_names.get(pid) or pid or "unknown"
        if isinstance(pname, str) and pname.strip().lower() in set(c.excluded_pipeline_names):
            continue

        # distinct count (after exclusions)
        distinct_opp_ids.add(opp_id)

        by_pipeline[pname] = by_pipeline.get(pname, 0) + 1

        # owner
        owner_id = str(opp.get("assignedTo") or "")
        oname = user_names.get(owner_id) or owner_id or "unassigned"
        by_owner[oname] = by_owner.get(oname, 0) + 1

        # join to contact for setter + lead source
        cid = str(opp.get("contactId") or "")
        contact = get_contact(cid) if cid else None

        setter = contact_custom_field(contact, c.setter_last_name_contact_cf_id) if contact else None
        if setter:
            by_setter[str(setter).strip()] = by_setter.get(str(setter).strip(), 0) + 1

        lead = contact_custom_field(contact, c.lead_gen_source_contact_cf_id) if contact else None
        if isinstance(lead, str):
            norm = lead.strip()
            lead = "none" if norm.lower() in {"crm ui", "hand", "", "none", "null", "n/a"} else norm
        if lead is None:
            lead = "none"
        by_lead[str(lead)] = by_lead.get(str(lead), 0) + 1

        # Capture matching row keyed by opportunityId so result and list cannot diverge
        last_name = (contact.get("lastName") if isinstance(contact, dict) else None)
        matching_rows[opp_id] = {
            "opportunityId": opp_id,
            "contactId": cid,
            "contactLastName": last_name,
            "pipeline": pname,
            "owner": oname,
            "appointmentOccurredAt": opp.get(c.appointment_occurred_at_field),
            "whatHappened": dispo_val,
        }

    return {
        "metric": c.metric_name,
        "unit": c.unit,
        "year": year,
        "month": month,
        "timezone": c.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "result": len(matching_rows),
        "count_method": f"COUNT_DISTINCT({c.opp_collection}.id) where {c.opp_collection}.customFields[{c.what_happened_custom_field_id}] is not empty and appointmentOccurredAt in window",
        "debug": {
            "opps_scanned": scanned,  # scanned within time window query
            "opps_with_disposition": matched_dispo,
            "opps_with_disposition_and_in_window": matched_time,
            "rows_listed": len(matching_rows),
        },
        "contract": {
            "base_collection": c.opp_collection,
            "disposition_field": f"{c.opp_collection}.customFields[{c.what_happened_custom_field_id}] (What happened with Appointment?)",
            "time_field": f"{c.opp_collection}.{c.appointment_occurred_at_field} (Timestamp)",
            "time_handling": "Convert Timestamp -> America/New_York -> compare to month window (appointmentOccurredAt)",
            "excluded_pipelines": list(c.excluded_pipeline_names),
            "setter_field": f"{c.contact_collection}.customFields[{c.setter_last_name_contact_cf_id}]",
            "lead_gen_source_field": f"{c.contact_collection}.customFields[{c.lead_gen_source_contact_cf_id}] (normalized to none)",
        },
        "breakdowns": {
            "ran_by_pipeline": {k: v for k, v in sorted(by_pipeline.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "ran_by_owner": {k: v for k, v in sorted(by_owner.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "ran_by_setter_last_name": {k: v for k, v in sorted(by_setter.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "ran_by_lead_gen_source": {k: v for k, v in sorted(by_lead.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
        },
        "sample_rows": list(matching_rows.values()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = payload.get("sample_rows", [])

    # Sort by appointmentOccurredAt for readability
    rows = sorted(rows, key=lambda r: (str(r.get("appointmentOccurredAt") or "")))

    tr = []
    for r in rows:
        tr.append(
            "<tr>"
            f"<td><code>{r.get('opportunityId','')}</code></td>"
            f"<td>{(r.get('contactLastName') or '')}</td>"
            f"<td><code>{(r.get('whatHappened') or '')}</code></td>"
            f"<td><code>{(r.get('appointmentOccurredAt') or '')}</code></td>"
            "</tr>"
        )

    rows_html = "\n".join(tr) if tr else "<tr><td colspan='4' style='padding:8px'>No rows</td></tr>"

    table_html = f"""
    <table style=\"width:100%; border-collapse: collapse; margin-top: 10px;\">
      <thead>
        <tr>
          <th style=\"text-align:left; border-bottom:1px solid #1f2a38; padding:8px; color:#9db0c7\">opportunityId</th>
          <th style=\"text-align:left; border-bottom:1px solid #1f2a38; padding:8px; color:#9db0c7\">contact last name</th>
          <th style=\"text-align:left; border-bottom:1px solid #1f2a38; padding:8px; color:#9db0c7\">what happened</th>
          <th style=\"text-align:left; border-bottom:1px solid #1f2a38; padding:8px; color:#9db0c7\">appointmentOccurredAt</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """

    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"/><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
<title>QA — Opportunities Ran</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#0b0f14;color:#e8eef6;}}
.wrap{{padding:18px;max-width:1100px;margin:0 auto;}}
.card{{background:#121a24;border:1px solid #1f2a38;border-radius:12px;padding:16px;margin-top:12px;}}
.label{{color:#9db0c7;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}}
.kpi{{font-size:44px;font-weight:900;}}
code{{background:#0e1520;padding:2px 6px;border-radius:6px;}}
</style></head>
<body><div class=\"wrap\">
<div class=\"card\" style=\"background:linear-gradient(135deg,#00C853 0%,#1b5e20 100%);border:none;\">
  <div style=\"font-weight:900;font-size:18px\">QA — Opportunities Ran</div>
  <div style=\"opacity:.9\">Window: {payload['window_start_local']} → {payload['window_end_local']} ({payload['timezone']})</div>
</div>
<div class=\"card\"><div class=\"label\">Result</div><div class=\"kpi\">{payload['result']}</div>
<div style=\"color:#9db0c7\">{payload['count_method']}</div>
<div style=\"margin-top:8px\">JSON: <a style=\"color:#6ee7b7\" href=\"?format=json\">?format=json</a></div>
</div>
<div class=\"card\"><div class=\"label\">Contract</div>
<pre style=\"white-space:pre-wrap;color:#9db0c7\">{json.dumps(payload['contract'], indent=2)}</pre>
</div>

<div class=\"card\"><div class=\"label\">Matching opportunities (all)</div>
<div style=\"color:#9db0c7\">opportunityId + contact last name + disposition + appointmentOccurredAt</div>
{table_html}
</div>

</div></body></html>"""



def json_safe(x):
    """Recursively convert datetime/Timestamp objects to ISO strings for JSON."""
    from datetime import datetime, timezone

    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, dict):
        return {k: json_safe(v) for k, v in x.items()}
    if isinstance(x, list):
        return [json_safe(v) for v in x]
    if isinstance(x, tuple):
        return [json_safe(v) for v in x]
    return x


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = qs.get("format", [""])[0].lower() == "json"

            now = datetime.utcnow()
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])

            c = MetricContract()
            db = get_db()
            payload = compute(db, c, year=year, month=month)

            if want_json:
                body = json.dumps(json_safe(payload)).encode("utf-8")
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
