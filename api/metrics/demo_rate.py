# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/demo_rate

Metric: Demo Rate
Definition: Percentage of Opportunities Ran whose disposition ("What happened with Appointment?") is "Sit".

Numerator: count of opportunities with dispositionValue == "Sit".
Denominator: count of opportunities with dispositionValue in {"Sit", "No Sit"}.

Time filter:
- First-write-wins Sit/No Sit timestamp: earlier of
  ghl_opportunities_v2.appointmentOccurredAt and
  ghl_opportunities_v2.dispositionDate (both written by ghl-firestore-sync-v2
  from GYGpLKBPfMpiBqyU2ogQ Sit / No Sit). A later follow-up start time must
  not move the sit. Follow-up is not a second sit.
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
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sit_timestamp import frozen_sit_timestamp


def normalize_person_display(value: Any, *, empty: str) -> str:
    s = " ".join(str(value or "").strip().split())
    if not s:
        return empty
    low = s.lower()
    if low in {"none", "null", "n/a"}:
        return "none"
    if low in {"unassigned", "unknown"}:
        return "unassigned"
    return s


def pick_better_person_display(current: str | None, candidate: str) -> str:
    if not current or current == candidate:
        return candidate

    def score(v: str) -> tuple[int, int, int]:
        return (
            0 if v == v.lower() else 1,
            sum(1 for idx, ch in enumerate(v) if idx > 0 and ch.isupper()),
            -len(v),
        )

    return candidate if score(candidate) > score(current) else current


def add_casefold_count(
    counts: dict[str, int],
    labels: dict[str, str],
    raw_value: Any,
    *,
    empty: str,
    delta: int = 1,
) -> str:
    display = normalize_person_display(raw_value, empty=empty)
    key = display.casefold()
    labels[key] = pick_better_person_display(labels.get(key), display)
    counts[key] = counts.get(key, 0) + delta
    return labels[key]


def finalize_casefold_counts(counts: dict[str, int], labels: dict[str, str]) -> dict[str, int]:
    return {
        labels[key]: value
        for key, value in sorted(counts.items(), key=lambda kv: (-kv[1], labels.get(kv[0], kv[0])))
        if value > 0
    }


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
    # GHL custom field "What happened with Appointment?" — source of dispositionValue
    what_happened_custom_field_id: str = "GYGpLKBPfMpiBqyU2ogQ"

    # Stable occurred timestamp used for ran/demo month windows
    appointment_occurred_at_field: str = "appointmentOccurredAt"  # Firestore Timestamp/datetime
    # First Sit/No Sit write time (preserved by sync). Used to freeze a sit that
    # was later rewritten onto a follow-up appointmentStartTime.
    disposition_date_field: str = "dispositionDate"

    # Pipeline scope
    included_pipeline_names: tuple[str, ...] = ("buffalo", "rochester", "virtual", "syracuse", "rehash", "sweeper")
    excluded_pipeline_names: tuple[str, ...] = ("inbound/lead locker",)  # do not exclude sweeper/rehash

    # Breakdown fields
    setter_last_name_contact_cf_id: str = "Eq4NLTSkJ56KTxbxypuE"
    setter_last_name_opportunity_cf_id: str = "Eq4NLTSkJ56KTxbxypuE"
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


def to_local_iso(dt: datetime | None, tz_name: str) -> str | None:
    if not dt:
        return None
    from zoneinfo import ZoneInfo

    aware = dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))
    return aware.astimezone(ZoneInfo(tz_name)).isoformat()


def load_demo_rate_snaps(
    db: firestore.Client,
    c: MetricContract,
    start_utc: datetime,
    end_utc: datetime,
) -> list:
    """Union of appointmentOccurredAt and dispositionDate window scans.

    Needed when a follow-up rewrites appointmentOccurredAt out of the original
    sit day/month. Do not full-stream the collection if a query fails.
    """
    by_id: dict[str, Any] = {}
    for snap in (
        db.collection(c.opp_collection)
        .where(c.appointment_occurred_at_field, ">=", start_utc)
        .where(c.appointment_occurred_at_field, "<", end_utc)
        .stream()
    ):
        by_id[snap.id] = snap
    try:
        for snap in (
            db.collection(c.opp_collection)
            .where(c.disposition_date_field, ">=", start_utc)
            .where(c.disposition_date_field, "<", end_utc)
            .stream()
        ):
            by_id.setdefault(snap.id, snap)
    except Exception:
        pass
    return list(by_id.values())


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


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def pipeline_id_keys(raw: Any) -> list[str]:
    """Lookup keys for a pipelineId. compact_str and raw str() can differ (whitespace)."""
    keys: list[str] = []
    seen: set[str] = set()
    raw_s = "" if raw is None else str(raw)
    for candidate in (compact_str(raw), raw_s.strip(), raw_s):
        if candidate and candidate not in seen:
            seen.add(candidate)
            keys.append(candidate)
    return keys


def remember_pipeline_name(m: dict[str, str], name: Any, *raw_ids: Any) -> None:
    if not name:
        return
    name_s = str(name)
    for raw in raw_ids:
        for key in pipeline_id_keys(raw):
            m[key] = name_s


def resolve_pipeline_name(pipe_names: dict[str, str], raw_id: Any, *, fallback: str = "unknown") -> str:
    for key in pipeline_id_keys(raw_id):
        hit = pipe_names.get(key)
        if hit:
            return hit
    return compact_str(raw_id) or str(raw_id or "") or fallback


def contact_custom_field(contact: dict, cf_id: str) -> Any:
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def load_contacts_by_ids(db: firestore.Client, contact_ids) -> dict[str, dict]:
    """Bounded ghl_contacts_v2 get_all for contactIds on the already-fetched opp set."""
    contacts_map: dict[str, dict] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        cid = compact_str(raw)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        needed.append(cid)
    refs = [db.collection("ghl_contacts_v2").document(cid) for cid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            cid = compact_str(d.get("id") or snap.id)
            if cid:
                contacts_map[cid] = d
            if snap.id:
                contacts_map[compact_str(snap.id)] = d
    for cid in needed:
        if cid in contacts_map:
            continue
        misses = list(
            db.collection("ghl_contacts_v2").where("id", "==", cid).limit(1).stream()
        )
        if misses:
            contacts_map[cid] = misses[0].to_dict() or {}
    return contacts_map


def pipeline_name_lookup(db: firestore.Client, pipeline_ids) -> dict[str, str]:
    """Bounded ghl_pipelines_v2 get_all for pipelineIds on the already-fetched opp set."""
    out: dict[str, str] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in pipeline_ids:
        for pid in pipeline_id_keys(raw):
            if pid in seen:
                continue
            seen.add(pid)
            needed.append(pid)
    refs = [db.collection("ghl_pipelines_v2").document(pid) for pid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            remember_pipeline_name(out, d.get("name"), d.get("id"), snap.id)
    for pid in needed:
        if any(key in out for key in pipeline_id_keys(pid)):
            name = next(out[key] for key in pipeline_id_keys(pid) if key in out)
            remember_pipeline_name(out, name, pid)
            continue
        misses = list(
            db.collection("ghl_pipelines_v2").where("id", "==", pid).limit(1).stream()
        )
        if misses:
            d = misses[0].to_dict() or {}
            remember_pipeline_name(out, d.get("name"), d.get("id"), misses[0].id, pid)
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
        f"<tr><td>{esc(r.get('opportunityId'))}</td><td>{esc(r.get('pipeline'))}</td><td>{esc(r.get('disposition'))}</td><td>{esc(r.get('frozenAppointmentOccurredAt'))}</td><td>{esc(r.get('appointmentOccurredAt'))}</td><td>{esc(r.get('dispositionDate'))}</td><td>{esc(r.get('contactFirstName'))}</td><td>{esc(r.get('contactLastName'))}</td><td>{esc(r.get('setter'))}</td><td>{esc(r.get('lead_source'))}</td></tr>"
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
                <th>frozen sit timestamp</th>
                <th>appointmentOccurredAt (raw)</th>
                <th>dispositionDate</th>
                <th>contactFirstName</th>
                <th>contactLastName</th>
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

    # Firestore query: only scan opportunities in the month window (big speedup)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)

    # Do not cap the warehouse scan at "now". A follow-up can rewrite
    # appointmentOccurredAt into the future (Joanne Miechowski
    # OF48x1PrhxehlJS3ReMc: occurred 2026-08-26T18:00:00Z / Aug 26 2:00 PM ET
    # while the sit belongs on Aug 20). The frozen timestamp is still capped below.
    # Do not fall back to a full collection stream if a query fails.
    opp_snaps = load_demo_rate_snaps(db, c, start_utc, end_utc)

    needed_contact_ids: list[str] = []
    needed_pipeline_ids: list[str] = []
    for snap in opp_snaps:
        opp = snap.to_dict() or {}
        cid = compact_str(opp.get("contactId"))
        if cid:
            needed_contact_ids.append(cid)
        pid_raw = opp.get("pipelineId")
        if pipeline_id_keys(pid_raw):
            needed_pipeline_ids.extend(pipeline_id_keys(pid_raw))

    pipelines = pipeline_name_lookup(db, needed_pipeline_ids)
    contacts_map = load_contacts_by_ids(db, needed_contact_ids)

    matching = []
    ran = 0
    sit = 0

    # breakdowns
    ran_by_setter: dict[str, int] = {}
    sit_by_setter: dict[str, int] = {}
    setter_labels: dict[str, str] = {}
    by_pipeline: dict[str, int] = {}
    by_lead: dict[str, int] = {}
    sit_by_lead: dict[str, int] = {}

    for snap in opp_snaps:
        opp = snap.to_dict() or {}

        pname = resolve_pipeline_name(pipelines, opp.get("pipelineId"), fallback="").strip()
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

        frozen_dt = frozen_sit_timestamp(
            opp.get(c.appointment_occurred_at_field),
            opp.get(c.disposition_date_field),
        )
        if not frozen_dt:
            continue
        if frozen_dt > now_utc:
            continue

        # Convert to local timezone for month window comparisons
        try:
            from zoneinfo import ZoneInfo

            local_dt = frozen_dt.astimezone(ZoneInfo(c.timezone))
        except Exception:
            continue

        if not (start_local <= local_dt < end_local):
            continue

        # join contact for setter + lead source filters/breakdowns
        contact = contacts_map.get(str(opp.get("contactId") or "").strip()) or {}
        setter_opp = opportunity_custom_field(opp, c.setter_last_name_opportunity_cf_id)
        setter_contact = contact_custom_field(contact, c.setter_last_name_contact_cf_id)
        setter = setter_opp if setter_opp not in (None, "") else setter_contact
        setter_s = normalize_person_display(setter, empty="none")

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

        setter_s = add_casefold_count(ran_by_setter, setter_labels, setter_s, empty="none")
        if dispo == "Sit":
            add_casefold_count(sit_by_setter, setter_labels, setter_s, empty="none")
        by_pipeline[pname] = by_pipeline.get(pname, 0) + 1
        by_lead[lead] = by_lead.get(lead, 0) + 1
        if dispo == "Sit":
            sit_by_lead[lead] = sit_by_lead.get(lead, 0) + 1

        matching.append(
            {
                "opportunityId": str(opp.get("id") or snap.id),
                "pipeline": pname,
                "disposition": dispo,
                "frozenAppointmentOccurredAt": local_dt.isoformat(),
                "appointmentOccurredAt": to_local_iso(
                    as_dt(opp.get(c.appointment_occurred_at_field)), c.timezone
                ),
                "dispositionDate": to_local_iso(
                    as_dt(opp.get(c.disposition_date_field)), c.timezone
                ),
                "contactFirstName": contact.get("firstName"),
                "contactLastName": contact.get("lastName"),
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
        "count_method": (
            "Sit / Ran. Demos = Sit. Window = first-write-wins "
            "min(appointmentOccurredAt, dispositionDate). "
            "GYGpLKBPfMpiBqyU2ogQ / dispositionValue Sit|No Sit. "
            "Follow-up is not a second sit."
        ),
        "breakdowns": {
            "ran_by_setter_last_name": finalize_casefold_counts(ran_by_setter, setter_labels),
            "sit_by_setter_last_name": finalize_casefold_counts(sit_by_setter, setter_labels),
            "demo_rate_by_setter_last_name": finalize_casefold_counts(ran_by_setter, setter_labels),  # legacy: was misnamed; kept for backward-compat

            "demo_rate_by_pipeline": by_pipeline,
            "ran_by_lead_gen_source": by_lead,
            "sit_by_lead_gen_source": sit_by_lead,
            "demo_rate_by_lead_gen_source": {k: (round((sit_by_lead.get(k,0)/v)*100,1) if v else 0.0) for k,v in by_lead.items()},
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
                self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
                self.end_headers()
                self.wfile.write(body)
                return

            body = html_page(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)


def opportunity_custom_field(opportunity: dict | None, custom_field_id: str) -> Any:
    if not opportunity:
        return None
    for cf in (opportunity.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == custom_field_id:
            return cf.get("value") or cf.get("fieldValueString")
    return None
