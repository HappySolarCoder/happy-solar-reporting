# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/demo_rate

Metric: Demo Rate
Definition: Percentage of Opportunities Ran whose disposition ("What happened with Appointment?") is "Sit".

Numerator: count of opportunities with dispositionValue == "Sit".
Denominator: count of opportunities with dispositionValue in {"Sit", "No Sit"}.

Time filter:
- Uses derived Firestore field: ghl_opportunities_v2.dispositionDate (Timestamp)
  (populated by Cloud Run ghl-firestore-sync-v2)
- Month windows computed in America/New_York.

Filters (optional query params):
- pipeline=<pipeline name>   (e.g., buffalo)
- setter=<setter last name>  (contact custom field Eq4NLTSkJ56KTxbxypuE)
- lead_source=<lead gen source> (contact custom field hd5QqHEOVSsPom5bJ32P; normalized)

Output:
- HTML (default) for QA debugging (includes matching rows table)
- JSON via ?format=json
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
class MetricContract:
    metric_name: str = "Demo Rate"
    unit: str = "percentage"

    opp_collection: str = "ghl_opportunities_v2"
    contact_collection: str = "ghl_contacts_v2"
    pipeline_collection: str = "ghl_pipelines_v2"

    timezone: str = "America/New_York"  # MANDATORY

    # Derived fields we write into ghl_opportunities_v2
    disposition_value_field: str = "dispositionValue"  # Sit / No Sit / null

    # Stable occurred timestamp used for ran/demo month windows
    appointment_occurred_at_field: str = "appointmentOccurredAt"  # Firestore Timestamp/datetime

    # Pipeline scope
    included_pipeline_names: tuple[str, ...] = ("buffalo", "rochester", "virtual", "syracuse")
    excluded_pipeline_names: tuple[str, ...] = ("inbound/lead locker",)  # do not exclude sweeper/rehash

    # Breakdown fields
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


def normalize_lead_source(v: Any) -> str:
    """Normalize lead gen source to canonical casing.

    Business update: "Virtual" is now treated as "Phones".
    """

    if v is None:
        return "none"
    s = str(v).strip()
    if not s:
        return "none"

    low = s.lower()
    if low in ("crm ui", "hand", "manual"):
        return "none"

    if low in ("doors", "door", "d2d"):
        return "Doors"

    # New canonical
    if low in ("phones", "phone", "ph", "call", "calls"):
        return "Phones"

    # Legacy mapping
    if low in ("virtual", "virt"):
        return "Phones"

    if low in ("3pl", "3p", "threepl"):
        return "3PL"

    # fallback to raw casing
    return s


def contact_custom_field(contact: dict, cf_id: str) -> Any:
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def pipeline_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in db.collection(MetricContract.pipeline_collection).stream():
        d = doc.to_dict() or {}
        pid = str(d.get("id") or doc.id)
        nm = str(d.get("name") or "")
        if pid and nm:
            out[pid] = nm
    return out


def contact_lookup(db: firestore.Client, contact_id: str) -> dict | None:
    """Fetch contact by doc id; fallback to query where('id','==',contact_id)."""
    if not contact_id:
        return None

    snap = db.collection(MetricContract.contact_collection).document(str(contact_id)).get()
    if snap.exists:
        return snap.to_dict() or {}

    # fallback join (doc_id may not match)
    q = db.collection(MetricContract.contact_collection).where("id", "==", str(contact_id)).limit(1)
    docs = list(q.stream())
    if docs:
        return docs[0].to_dict() or {}
    return None


def parse_int(qs: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(qs.get(key, [str(default)])[0])
    except Exception:
        return default


def html_page(payload: dict) -> str:
    # Dark QA page (matches other QA endpoints)
    rows = payload.get("rows") or []

    def esc(x: Any) -> str:
        return (
            str(x)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    table_rows = "".join(
        f"<tr><td>{esc(r.get('opportunityId'))}</td><td>{esc(r.get('pipeline'))}</td><td>{esc(r.get('disposition'))}</td><td>{esc(r.get('appointmentOccurredAt'))}</td><td>{esc(r.get('setter'))}</td><td>{esc(r.get('lead_source'))}</td></tr>"
        for r in rows[:500]
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QA — Demo Rate</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system; margin: 0; background:#0b1220; color:#e5e7eb; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .title {{ font-size: 20px; font-weight: 900; }}
    .sub {{ color:#9ca3af; margin-top:4px; }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap: 12px; margin-top: 14px; }}
    .card {{ grid-column: span 4; background:#0f172a; border:1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 14px; }}
    .label {{ color:#9ca3af; font-size: 12px; font-weight: 800; }}
    .kpi {{ font-size: 34px; font-weight: 950; margin-top: 6px; }}
    .meta {{ color:#9ca3af; font-size: 12px; margin-top: 6px; }}
    .wide {{ grid-column: span 12; }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,0.06); padding: 8px 10px; font-size: 12px; text-align:left; }}
    th {{ color:#a7f3d0; font-weight: 900; }}
    a {{ color:#34d399; }}
    code {{ background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">QA — Demo Rate</div>
    <div class="sub">{esc(payload.get('metric_name'))} • window {esc(payload.get('window_start_local'))} → {esc(payload.get('window_end_local'))} ({esc(payload.get('timezone'))})</div>

    <div class="grid">
      <div class="card">
        <div class="label">Demo Rate</div>
        <div class="kpi">{esc(payload.get('result'))}%</div>
        <div class="meta">Sit {esc(payload.get('sit_count'))} / Ran {esc(payload.get('ran_count'))}</div>
      </div>
      <div class="card">
        <div class="label">Filters</div>
        <div class="meta"><code>pipeline</code>: {esc(payload.get('filters', {}).get('pipeline') or '—')}</div>
        <div class="meta"><code>setter</code>: {esc(payload.get('filters', {}).get('setter') or '—')}</div>
        <div class="meta"><code>lead_source</code>: {esc(payload.get('filters', {}).get('lead_source') or '—')}</div>
      </div>
      <div class="card">
        <div class="label">JSON</div>
        <div class="meta"><a href="?format=json&year={esc(payload.get('year'))}&month={esc(payload.get('month'))}">?format=json</a></div>
      </div>

      <div class="card wide">
        <div class="label">Matching opportunities (first 500)</div>
        <div class="meta">Row count: {len(rows)} (table capped at 500)</div>
        <div style="overflow:auto; margin-top:10px">
          <table>
            <thead>
              <tr>
                <th>opportunityId</th>
                <th>pipeline</th>
                <th>disposition</th>
                <th>appointmentOccurredAt</th>
                <th>setter</th>
                <th>lead_source</th>
              </tr>
            </thead>
            <tbody>
              {table_rows}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""


def build_payload(db: firestore.Client, year: int, month: int, filters: dict[str, str | None], start: str | None = None, end: str | None = None) -> dict:
    c = MetricContract()
    if start and end:
        start_local, end_local, start_str, end_str = date_range_window(start, end, c.timezone)
    else:
        start_local, end_local, start_str, end_str = month_window(year, month, c.timezone)

    pipelines = pipeline_name_lookup(db)

    # Firestore query: only scan opportunities in the month window (big speedup)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    # Guardrail (business rule): appointmentOccurredAt should not be in the future.
    now_utc = datetime.now(timezone.utc)
    if end_utc > now_utc:
        end_utc = now_utc

    opp_query = (
        db.collection(c.opp_collection)
        .where(c.appointment_occurred_at_field, ">=", start_utc)
        .where(c.appointment_occurred_at_field, "<", end_utc)
    )

    matching = []
    ran = 0
    sit = 0

    # breakdowns
    ran_by_setter: dict[str, int] = {}
    sit_by_setter: dict[str, int] = {}
    by_pipeline: dict[str, int] = {}
    by_lead: dict[str, int] = {}

    for snap in opp_query.stream():
        opp = snap.to_dict() or {}

        pid = str(opp.get("pipelineId") or "")
        pname = (pipelines.get(pid) or "").strip()
        pname_low = pname.lower()

        if not pname_low:
            continue

        if pname_low in c.excluded_pipeline_names:
            continue

        if pname_low not in c.included_pipeline_names:
            continue

        dispo = opp.get(c.disposition_value_field)
        if dispo not in ("Sit", "No Sit"):
            continue

        dispo_dt = as_dt(opp.get(c.appointment_occurred_at_field))
        if not dispo_dt:
            continue

        # Convert to local timezone for month window comparisons
        try:
            from zoneinfo import ZoneInfo

            local_dt = dispo_dt.astimezone(ZoneInfo(c.timezone)) if dispo_dt.tzinfo else dispo_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(c.timezone))
        except Exception:
            continue

        if not (start_local <= local_dt < end_local):
            continue

        # join contact for setter + lead source filters/breakdowns
        contact = contact_lookup(db, str(opp.get("contactId") or "")) or {}
        setter = contact_custom_field(contact, c.setter_last_name_contact_cf_id)
        setter_s = str(setter).strip() if setter not in (None, "") else "none"

        lead = normalize_lead_source(contact_custom_field(contact, c.lead_gen_source_contact_cf_id))

        # Apply optional filters
        if filters.get("pipeline") and pname_low != str(filters["pipeline"]).strip().lower():
            continue
        if filters.get("setter") and setter_s.lower() != str(filters["setter"]).strip().lower():
            continue
        if filters.get("lead_source") and lead.lower() != str(filters["lead_source"]).strip().lower():
            continue

        ran += 1
        if dispo == "Sit":
            sit += 1

        ran_by_setter[setter_s] = ran_by_setter.get(setter_s, 0) + 1
        if dispo == "Sit":
            sit_by_setter[setter_s] = sit_by_setter.get(setter_s, 0) + 1
        by_pipeline[pname] = by_pipeline.get(pname, 0) + 1
        by_lead[lead] = by_lead.get(lead, 0) + 1

        matching.append(
            {
                "opportunityId": str(opp.get("id") or snap.id),
                "pipeline": pname,
                "disposition": dispo,
                "appointmentOccurredAt": local_dt.isoformat(),
                "setter": setter_s,
                "lead_source": lead,
            }
        )

    pct = round((sit / ran) * 100, 1) if ran else 0.0

    return {
        "metric_name": c.metric_name,
        "unit": c.unit,
        "timezone": c.timezone,
        "year": year,
        "month": month,
        "window_start_local": start_str,
        "window_end_local": end_str,
        "filters": filters,
        "ran_count": ran,
        "sit_count": sit,
        "result": pct,
        "breakdowns": {
            "ran_by_setter_last_name": ran_by_setter,
            "sit_by_setter_last_name": sit_by_setter,
            "demo_rate_by_setter_last_name": ran_by_setter,  # legacy: was misnamed; kept for backward-compat

            "demo_rate_by_pipeline": by_pipeline,
            "demo_rate_by_lead_gen_source": by_lead,
        },
        "rows": matching,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        now = datetime.utcnow()

        year = parse_int(qs, "year", now.year)
        month = parse_int(qs, "month", now.month)
        fmt = (qs.get("format", [""])[0] or "").lower()

        start = (qs.get("start", [None])[0] or None)
        end = (qs.get("end", [None])[0] or None)

        filters = {
            "pipeline": (qs.get("pipeline", [None])[0] or None),
            "setter": (qs.get("setter", [None])[0] or None),
            "lead_source": (qs.get("lead_source", [None])[0] or None),
        }

        try:
            db = get_db()
            payload = build_payload(db, year, month, filters, start, end)

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
