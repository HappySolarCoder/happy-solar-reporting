# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/scheduling_manager_performance

Metric: Scheduling Manager Performance

Definition:
- Base cohort = distinct opportunities created in the selected window where a
  scheduling manager value is present.
- Breakdown dimension = scheduling manager.
- Demo'd = created-cohort opportunities whose final appointment disposition is
  currently "Sit".
- Demo % = demo'd / created within the same created-opportunity cohort.

Time filter:
- Uses ghl_opportunities_v2.createdAt
- Window computed in America/New_York

Pipeline scope:
- Default matches canonical opportunities-created scope:
  Buffalo, Rochester, Syracuse, Virtual
- Excludes Inbound/Lead Locker

Scheduling manager resolution order:
1. ghl_opportunities_v2.customFields[3z1GIGutL4JMLpdbtHN1]
2. ghl_contacts_v2.schedulingManager
3. ghl_contacts_v2.customFields[6QmaNZha745jNHnh3U86]
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


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def parse_iso_dt(value: Any) -> datetime | None:
    text = compact_str(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def contact_custom_field(contact: dict[str, Any] | None, cf_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


def opportunity_custom_field(opportunity: dict[str, Any] | None, cf_id: str) -> Any:
    if not isinstance(opportunity, dict):
        return None
    for cf in (opportunity.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value") or cf.get("fieldValueString")
    return None


def normalize_manager(value: Any) -> str:
    text = compact_str(value)
    if not text:
        return ""
    low = text.lower()
    if low in {"none", "null", "n/a", "na", "unknown", "unassigned", "no answer"}:
        return ""
    return text


def normalize_disposition(value: Any) -> str:
    text = compact_str(value)
    if not text:
        return ""
    low = text.lower().replace("-", " ").replace("_", " ")
    while "  " in low:
        low = low.replace("  ", " ")
    if low == "sit":
        return "Sit"
    if low == "no sit" or low == "nosit":
        return "No Sit"
    return text


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value or not isinstance(value, str):
        return None
    try:
        y, m, d = [int(x) for x in value.strip().split("-")]
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
    return start_local, end_local, start_local.date().isoformat(), (end_local - timedelta(days=1)).date().isoformat()


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo

    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
    tz = ZoneInfo(tz_name)
    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    return start_local, end_local, start_local.date().isoformat(), (end_local - timedelta(days=1)).date().isoformat()


@dataclass(frozen=True)
class MetricContract:
    metric_name: str = "Scheduling Manager Performance"
    timezone: str = "America/New_York"
    opp_collection: str = "ghl_opportunities_v2"
    contact_collection: str = "ghl_contacts_v2"
    pipeline_collection: str = "ghl_pipelines_v2"
    created_at_field: str = "createdAt"
    disposition_value_field: str = "dispositionValue"
    scheduling_manager_contact_field: str = "schedulingManager"
    scheduling_manager_contact_cf_id: str = "6QmaNZha745jNHnh3U86"
    scheduling_manager_opp_cf_id: str = "3z1GIGutL4JMLpdbtHN1"
    included_pipeline_names: tuple[str, ...] = ("buffalo", "rochester", "syracuse", "virtual")
    excluded_pipeline_names: tuple[str, ...] = ("inbound/lead locker",)


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [
            key
            for key in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(key)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def pipeline_name_lookup(db: firestore.Client, collection: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in db.collection(collection).stream():
        data = doc.to_dict() or {}
        pid = compact_str(data.get("id") or doc.id)
        name = compact_str(data.get("name"))
        if pid and name:
            out[pid] = name
    return out


def finalize_breakdown(store: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for manager, data in store.items():
        created = int(data.get("created", 0) or 0)
        demoed = int(data.get("demoed", 0) or 0)
        demo_pct = round((demoed / created) * 100, 1) if created else 0.0
        rows.append(
            {
                "manager": manager,
                "created": created,
                "demoed": demoed,
                "demo_percentage": demo_pct,
            }
        )
    rows.sort(key=lambda row: (-row["created"], -row["demoed"], row["manager"].lower()))
    return rows


def build_payload(
    db: firestore.Client,
    *,
    year: int,
    month: int,
    start: str | None = None,
    end: str | None = None,
    pipeline_scope: str | None = None,
) -> dict[str, Any]:
    contract = MetricContract()
    if start and end:
        start_local, end_local, window_start, window_end = date_range_window(start, end, contract.timezone)
    else:
        start_local, end_local, window_start, window_end = month_window(year, month, contract.timezone)

    pipe_names = pipeline_name_lookup(db, contract.pipeline_collection)
    pipeline_scope_norm = compact_str(pipeline_scope or "core").lower()
    included = {name.lower() for name in contract.included_pipeline_names}
    excluded = {name.lower() for name in contract.excluded_pipeline_names}

    contacts_map: dict[str, dict[str, Any]] = {}
    for doc in db.collection(contract.contact_collection).stream():
        data = doc.to_dict() or {}
        cid = compact_str(data.get("id") or doc.id)
        if cid:
            contacts_map[cid] = data

    scanned = 0
    in_window = 0
    in_scope = 0
    with_manager = 0
    demoed_total = 0
    breakdown_store: dict[str, dict[str, Any]] = {}
    sample_rows: list[dict[str, Any]] = []

    for doc in db.collection(contract.opp_collection).stream():
        scanned += 1
        opp = doc.to_dict() or {}
        created_dt = parse_iso_dt(opp.get(contract.created_at_field))
        if not created_dt:
            continue
        created_local = created_dt.astimezone(start_local.tzinfo)
        if not (start_local <= created_local < end_local):
            continue
        in_window += 1

        pipeline_id = compact_str(opp.get("pipelineId"))
        pipeline_name = compact_str(pipe_names.get(pipeline_id) or pipeline_id or "unknown")
        pipeline_low = pipeline_name.lower()
        if pipeline_low in excluded:
            continue
        if pipeline_scope_norm != "all" and pipeline_low not in included:
            continue
        in_scope += 1

        contact = contacts_map.get(compact_str(opp.get("contactId"))) or {}
        manager = normalize_manager(
            opportunity_custom_field(opp, contract.scheduling_manager_opp_cf_id)
            or contact.get(contract.scheduling_manager_contact_field)
            or contact_custom_field(contact, contract.scheduling_manager_contact_cf_id)
        )
        if not manager:
            continue
        with_manager += 1

        disposition = normalize_disposition(opp.get(contract.disposition_value_field))
        demoed = disposition == "Sit"
        if demoed:
            demoed_total += 1

        bucket = breakdown_store.setdefault(manager, {"created": 0, "demoed": 0})
        bucket["created"] += 1
        if demoed:
            bucket["demoed"] += 1

        if len(sample_rows) < 500:
            sample_rows.append(
                {
                    "opportunityId": compact_str(opp.get("id") or doc.id),
                    "createdAt": opp.get(contract.created_at_field),
                    "pipeline": pipeline_name,
                    "schedulingManager": manager,
                    "disposition": disposition or "—",
                    "contactName": compact_str(
                        (opp.get("contact") or {}).get("name")
                        or contact.get("contactName")
                        or " ".join(part for part in [compact_str(contact.get("firstName")), compact_str(contact.get("lastName"))] if part)
                    ),
                }
            )

    rows = finalize_breakdown(breakdown_store)
    total_demo_pct = round((demoed_total / with_manager) * 100, 1) if with_manager else 0.0

    return {
        "metric_name": contract.metric_name,
        "timezone": contract.timezone,
        "year": year,
        "month": month,
        "window_start_local": window_start,
        "window_end_local": window_end,
        "result": {
            "created_with_scheduling_manager": with_manager,
            "demoed_from_created_cohort": demoed_total,
            "demo_percentage": total_demo_pct,
        },
        "breakdowns": {
            "by_scheduling_manager": rows,
            "created_by_scheduling_manager": {row["manager"]: row["created"] for row in rows},
            "demoed_by_scheduling_manager": {row["manager"]: row["demoed"] for row in rows},
            "demo_percentage_by_scheduling_manager": {row["manager"]: row["demo_percentage"] for row in rows},
        },
        "contract": {
            "base_collection": contract.opp_collection,
            "time_field": f"{contract.opp_collection}.{contract.created_at_field}",
            "time_rule": "Opportunity createdAt converted to America/New_York and filtered inside selected window.",
            "demo_rule": f'{contract.opp_collection}.{contract.disposition_value_field} == "Sit"',
            "pipeline_field": f"{contract.opp_collection}.pipelineId -> {contract.pipeline_collection}.name",
            "included_pipeline_names": list(contract.included_pipeline_names),
            "excluded_pipeline_names": list(contract.excluded_pipeline_names),
            "scheduling_manager_resolution": [
                f"{contract.opp_collection}.customFields[{contract.scheduling_manager_opp_cf_id}]",
                f"{contract.contact_collection}.{contract.scheduling_manager_contact_field}",
                f"{contract.contact_collection}.customFields[{contract.scheduling_manager_contact_cf_id}]",
            ],
            "pipeline_scope": pipeline_scope_norm,
        },
        "debug": {
            "opportunities_scanned": scanned,
            "opportunities_in_window": in_window,
            "opportunities_in_pipeline_scope": in_scope,
            "opportunities_with_manager": with_manager,
            "sample_rows_returned": len(sample_rows),
        },
        "rows": sample_rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    totals = payload.get("result") or {}
    rows = payload.get("rows") or []
    lines = []
    for row in rows:
        lines.append(
            "<tr>"
            f"<td><code>{row.get('opportunityId','')}</code></td>"
            f"<td>{row.get('contactName','')}</td>"
            f"<td>{row.get('pipeline','')}</td>"
            f"<td>{row.get('schedulingManager','')}</td>"
            f"<td>{row.get('disposition','')}</td>"
            f"<td><code>{row.get('createdAt','')}</code></td>"
            "</tr>"
        )
    rows_html = "\n".join(lines) if lines else "<tr><td colspan='6' style='padding:8px'>No rows</td></tr>"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QA — Scheduling Manager Performance</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:#0b1220; color:#e5e7eb; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .card {{ background:#0f172a; border:1px solid rgba(255,255,255,0.06); border-radius:14px; padding:14px; margin-top:12px; }}
    .hero {{ background:linear-gradient(135deg,#ec4899 0%,#f97316 100%); border:none; }}
    .label {{ color:#94a3b8; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.05em; }}
    .kpi {{ font-size:38px; font-weight:950; margin-top:6px; }}
    .grid {{ display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; margin-top:12px; }}
    table {{ width:100%; border-collapse: collapse; margin-top:10px; }}
    th, td {{ border-bottom:1px solid rgba(255,255,255,0.06); padding:8px 10px; font-size:12px; text-align:left; }}
    th {{ color:#a7f3d0; font-weight:900; }}
    code {{ background: rgba(255,255,255,0.06); padding:2px 6px; border-radius:8px; }}
    pre {{ white-space: pre-wrap; color:#cbd5e1; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card hero">
      <div style="font-size:20px; font-weight:950;">QA — Scheduling Manager Performance</div>
      <div style="margin-top:4px; opacity:.92;">Window: {payload['window_start_local']} → {payload['window_end_local']} ({payload['timezone']})</div>
    </div>
    <div class="grid">
      <div class="card"><div class="label">Created With Manager</div><div class="kpi">{totals.get('created_with_scheduling_manager', 0)}</div></div>
      <div class="card"><div class="label">Demo'd</div><div class="kpi">{totals.get('demoed_from_created_cohort', 0)}</div></div>
      <div class="card"><div class="label">Demo %</div><div class="kpi">{totals.get('demo_percentage', 0)}%</div></div>
    </div>
    <div class="card">
      <div class="label">Contract</div>
      <pre>{json.dumps(payload.get('contract') or {}, indent=2)}</pre>
    </div>
    <div class="card">
      <div class="label">Matching opportunities (first 500)</div>
      <table>
        <thead>
          <tr><th>Opportunity</th><th>Contact</th><th>Pipeline</th><th>Scheduling Manager</th><th>Disposition</th><th>Created At</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.utcnow()
            year = int((qs.get("year", [str(now.year)])[0] or now.year))
            month = int((qs.get("month", [str(now.month)])[0] or now.month))
            start = compact_str(qs.get("start", [""])[0]) or None
            end = compact_str(qs.get("end", [""])[0]) or None
            pipeline_scope = compact_str(qs.get("pipeline_scope", [""])[0]) or None
            want_json = compact_str(qs.get("format", [""])[0]).lower() == "json"

            payload = build_payload(
                get_db(),
                year=year,
                month=month,
                start=start,
                end=end,
                pipeline_scope=pipeline_scope,
            )
            body = json.dumps(payload, indent=2).encode("utf-8") if want_json else render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8" if want_json else "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = ("ERROR: " + str(exc)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
