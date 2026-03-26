# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sales

QA endpoint for Sales metric.

Sales definition (canonical):
- Count of opportunities in Sold OR Sale Cancelled stage IDs (8 IDs)
- Time filter is based on Contact Sold Date: ghl_contacts.dateSold (epoch millis)
- Scope: Buffalo, Rochester, Virtual, Syracuse (enforced implicitly by stage IDs)

Query notes:
- To avoid requiring composite indexes during QA, we query by dateSold range server-side,
  then apply stage filter client-side.

Params:
- year (int)  e.g. 2026
- month (int) 1-12
- tz (optional) default America/New_York
- format=json (optional) returns JSON, else HTML
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
import re
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


@dataclass(frozen=True)
class SalesMetricContract:
    metric_name: str = "Sales"
    unit: str = "count"

    # DB mapping
    collection: str = "ghl_opportunities_v2"
    # Canonical sold date lives in a Contact custom field (ISO string) in v2 payload
    sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"  # Sold Date (ISO)

    # TODO: fill these in once we identify the exact custom field IDs in GHL
    setter_last_name_custom_field_id: str = "Eq4NLTSkJ56KTxbxypuE"  # Setter Last Name (primary)
    setter_last_name_fallback_custom_field_id: str = "Xhy6k4xfHRJ6s5IbfA5x"  # Setter Last Name (fallback)
    lead_gen_source_custom_field_id: str = "hd5QqHEOVSsPom5bJ32P"  # Lead Gen Source
    sold_date_field: str = "dateSold"  # legacy field name (not used in v2)
    stage_field: str = "pipelineStageId"
    opportunity_id_field: str = "id"  # opportunity id in ghl_opportunities

    # Stage IDs (Sold + Sale Cancelled)
    stage_ids: tuple[str, ...] = (
        # Buffalo
        "7981f111-73f2-4593-9662-6b95d99bf51a",  # Sold
        "adf3106e-d371-47ff-ab9e-6f7f33ecf415",  # Sale Cancelled
        # Syracuse
        "0aea9f94-1205-4623-ad3d-6e1b08ae8791",  # Sold
        "34a1882f-7959-4d22-878d-91fe35a42907",  # Sale Cancelled
        # Rochester
        "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",  # Sold
        "9bd71abf-7285-47bb-8800-a255e7b90630",  # Sale Cancelled
        # Virtual
        "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",  # Sold
        "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",  # Sale Cancelled
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


def month_window_ms(year: int, month: int, tz_name: str) -> tuple[int, int, str, str]:
    # We compute boundaries in the requested timezone, then convert to epoch millis.
    # Using zoneinfo keeps DST correct.
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        next_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        next_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)

    start_ms = int(start_local.timestamp() * 1000)
    end_ms = int(next_local.timestamp() * 1000)
    return start_ms, end_ms, start_local.isoformat(), next_local.isoformat()


def parse_date_ymd(s: str | None) -> tuple[int,int,int] | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        y, m, d = [int(x) for x in t.split('-')]
        return y, m, d
    except Exception:
        return None


def date_range_window_ms(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[int, int, str, str]:
    """Date-only window, end inclusive; returns epoch ms boundaries [start, end_exclusive)."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError('Invalid start/end date; expected YYYY-MM-DD')
    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz)
    end_exclusive = end_local + timedelta(days=1)
    start_ms = int(start_local.timestamp() * 1000)
    end_ms = int(end_exclusive.timestamp() * 1000)
    return start_ms, end_ms, start_local.isoformat(), end_exclusive.isoformat()



def compute_sales(db: firestore.Client, contract: SalesMetricContract, *, year: int, month: int, tz: str, start: str | None = None, end: str | None = None, lead_source: str | None = None, dedupe_by: str | None = None) -> dict[str, Any]:
    if start and end:
        start_ms, end_ms, start_iso, end_iso = date_range_window_ms(start, end, tz)
    else:
        start_ms, end_ms, start_iso, end_iso = month_window_ms(year, month, tz)

    # Parse local window boundaries for date-only comparisons
    start_local = datetime.fromisoformat(start_iso)
    end_local = datetime.fromisoformat(end_iso)

    # Base query: opportunities in Sold/Sale Cancelled stages (opportunity grain)
    # NOTE: Firestore may require a composite index for (pipelineStageId IN ...).
    # To keep QA reliable without indexes, we stream opportunities and filter stage client-side.
    stage_set = set(contract.stage_ids)

    opp_q = db.collection(contract.collection)

    contrib_rows: list[dict[str, Any]] = []
    unique_result_ids: set[str] = set()
    pipeline_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    setter_counts: dict[str, int] = {}
    lead_source_counts: dict[str, int] = {}

    scanned = 0
    matched_stage = 0
    matched_date = 0

    # We'll join to ghl_contacts to get canonical sold date.
    contacts_col = db.collection("ghl_contacts_v2")
    pipelines_col = db.collection("ghl_pipelines_v2")
    users_col = db.collection("ghl_users_v2")
    pipeline_name_cache = {}
    user_name_cache = {}

    def user_name_from_id(user_id: str | None) -> str | None:
        if not user_id:
            return None
        uid = str(user_id)
        if uid in user_name_cache:
            return user_name_cache[uid]
        snaps = list(users_col.where('id', '==', uid).limit(1).stream())
        if not snaps:
            user_name_cache[uid] = None
            return None
        u = snaps[0].to_dict() or {}
        name = u.get('name')
        if not name:
            fn = u.get('firstName') or ''
            ln = u.get('lastName') or ''
            name = (fn + ' ' + ln).strip() or None
        user_name_cache[uid] = name
        return name

    def pipeline_name_from_id(pipeline_id: str | None) -> str | None:
        if not pipeline_id:
            return None
        pid = str(pipeline_id)
        if pid in pipeline_name_cache:
            return pipeline_name_cache[pid]
        snaps = list(pipelines_col.where('id', '==', pid).limit(1).stream())
        if not snaps:
            pipeline_name_cache[pid] = None
            return None
        name = (snaps[0].to_dict() or {}).get('name')
        pipeline_name_cache[pid] = name
        return name


    # Simple streaming approach for QA (optimize later with indexes/batching)
    for opp_doc in opp_q.stream():
        scanned += 1
        opp = opp_doc.to_dict() or {}

        stage_id = opp.get(contract.stage_field)
        if stage_id not in stage_set:
            continue
        matched_stage += 1

        contact_id = opp.get("contactId")
        if not contact_id:
            continue        # Fetch contact sold date (canonical field lives on contact)
        # IMPORTANT: ghl_contacts Firestore doc_id is NOT the same as GHL contact id.
        # So we must query by field `ghl_contacts.id == contactId`.
        if 'contact_cache' not in locals():
            contact_cache = {}

        cache_key = str(contact_id)
        contact = contact_cache.get(cache_key)
        if contact is None:
            snaps = list(contacts_col.where('id', '==', cache_key).limit(1).stream())
            if not snaps:
                contact_cache[cache_key] = False
                continue
            contact = snaps[0].to_dict() or {}
            contact_cache[cache_key] = contact
        if contact is False:
            continue

        # Extract Sold Date from customFields (ISO string)
        date_sold = None
        for cf in (contact.get("customFields") or []):
            if isinstance(cf, dict) and cf.get("id") == contract.sold_date_custom_field_id:
                date_sold = cf.get("value")
                break        # Interpret Sold Date as a DATE-ONLY field in EST.
        # GHL UI shows a calendar date (e.g., "Mar 1st 2026"). The API wraps it as an ISO timestamp
        # like 2026-03-01T00:00:00.000Z. We must NOT shift that into Feb 28 when converting timezones.
        sold_date_str = None
        if isinstance(date_sold, str) and len(date_sold) >= 10:
            sold_date_str = date_sold[:10]  # YYYY-MM-DD

        if not sold_date_str:
            continue

        # Compare by local date month window (EST)
        # Window boundaries are start_local/end_local; we compare on YYYY-MM-DD.
        # Convert boundaries to YYYY-MM-DD strings.
        start_date_str = start_local.date().isoformat()
        end_date_str = end_local.date().isoformat()

        if not (start_date_str <= sold_date_str < end_date_str):
            continue
        matched_date += 1

        # For display/debug, store dateSold as the YYYY-MM-DD string.
        date_sold_ms = sold_date_str

        # Breakdown by Lead Gen Source (custom field on contact, fallback to attributionSource)
        lead_src = None
        if contract.lead_gen_source_custom_field_id:
            for cf in (contact.get("customFields") or []):
                if isinstance(cf, dict) and cf.get("id") == contract.lead_gen_source_custom_field_id:
                    lead_src = cf.get("value")
                    break
        if not lead_src:
            attr = contact.get("attributionSource") or {}
            if isinstance(attr, dict):
                lead_src = attr.get("sessionSource") or attr.get("medium")

        # Normalize buckets (treat CRM UI / Hand / blank as none)
        if lead_src is None:
            lead_src = "none"
        if isinstance(lead_src, str):
            norm = lead_src.strip()
            if norm.lower() in {"crm ui", "hand", "", "none", "null", "n/a"}:
                lead_src = "none"
            else:
                lead_src = norm

        # Optional lead source filter (normalized comparison)
        if lead_source is not None and str(lead_source).strip() != "":
            want = str(lead_source).strip()
            if str(lead_src).strip().lower() != want.lower():
                continue

        opp_id = opp.get(contract.opportunity_id_field) or opp_doc.id
        dedupe_mode = str(dedupe_by or "opportunity").strip().lower()
        if dedupe_mode == "contact":
            result_key = str(contact_id or "").strip() or str(opp_id)
        else:
            result_key = str(opp_id)

        # For optional contact-level dedupe (used by Daily Dashboard),
        # count only the first matching record for each result_key.
        if result_key in unique_result_ids:
            continue
        unique_result_ids.add(result_key)

        # Breakdown by pipeline (human name)
        pname = pipeline_name_from_id(opp.get("pipelineId")) or str(opp.get("pipelineId") or "unknown")
        pipeline_counts[pname] = pipeline_counts.get(pname, 0) + 1

        # Breakdown by opportunity owner (assignedTo)
        owner_id = opp.get("assignedTo")
        oname = user_name_from_id(owner_id) or str(owner_id or "unassigned")
        owner_counts[oname] = owner_counts.get(oname, 0) + 1

        # Breakdown by Setter Last Name (custom field on contact)
        # Primary field can sometimes contain team/channel labels (e.g., Rochester/Buffalo).
        # In that case, fallback to secondary setter field to avoid mis-attribution.
        setter_name_primary = None
        setter_name_fallback = None
        if contract.setter_last_name_custom_field_id or contract.setter_last_name_fallback_custom_field_id:
            for cf in (contact.get("customFields") or []):
                if not isinstance(cf, dict):
                    continue
                cid = str(cf.get("id") or "")
                val = cf.get("value")
                if val in (None, ""):
                    val = cf.get("fieldValueString")
                if cid == contract.setter_last_name_custom_field_id:
                    setter_name_primary = val
                if cid == contract.setter_last_name_fallback_custom_field_id:
                    setter_name_fallback = val

        primary_s = str(setter_name_primary).strip() if setter_name_primary not in (None, "") else ""
        fallback_s = str(setter_name_fallback).strip() if setter_name_fallback not in (None, "") else ""

        invalid_primary_values = {
            "rochester", "buffalo", "virtual", "syracuse", "doors", "phones", "3pl", "none"
        }

        setter_name = primary_s
        if (not setter_name) or (setter_name.strip().lower() in invalid_primary_values and fallback_s):
            setter_name = fallback_s or setter_name

        setter_bucket = setter_name if setter_name else "none"
        setter_counts[setter_bucket] = setter_counts.get(setter_bucket, 0) + 1

        if lead_src:
            lead_source_counts[str(lead_src)] = lead_source_counts.get(str(lead_src), 0) + 1

        if len(contrib_rows) < 50:
            contrib_rows.append(
                {
                    "opportunityId": opp_id,
                    "pipelineStageId": stage_id,
                    "pipelineId": opp.get("pipelineId"),
                    "status": opp.get("status"),
                    "contactId": contact_id,
                    "soldDateRaw": date_sold,
                    "dateSold": date_sold_ms,
                    "pipelineName": pipeline_name_from_id(opp.get("pipelineId")),
                    "stageName_contact": contact.get("stageName"),
                    "assignedTo_contact": contact.get("assignedTo"),
                    "setter_contact": contact.get("setter"),
                    "leadSource_contact": contact.get("leadSource"),
                    "lastName_contact": contact.get("lastName"),
                    "customFieldsPreview": [
                        {"id": cf.get("id"), "value": cf.get("value")}
                        for cf in (contact.get("customFields") or [])
                        if isinstance(cf, dict) and cf.get("value") not in (None, "")
                    ][:12],
                }
            )

    payload = {
        "metric": contract.metric_name,
        "unit": contract.unit,
        "year": year,
        "month": month,
        "timezone": tz,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "result": len(unique_result_ids),
        "count_method": "COUNT_DISTINCT(key) where key=opportunityId (default) or contactId (dedupe_by=contact), stage in sold stages, and joined ghl_contacts_v2 Sold Date in window",
        "debug": {
            "opportunities_scanned": scanned,
            "opportunities_matched_stage": matched_stage,
            "opportunities_matched_stage_and_date": matched_date,
            "distinct_result_ids": len(unique_result_ids),
            "dedupe_by": (str(dedupe_by or "opportunity").strip().lower() or "opportunity"),
            "join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
        },
        "contract": {
            "base_collection": contract.collection,
            "stage_field": f"{contract.collection}.{contract.stage_field}",
            "opportunity_id_field": f"{contract.collection}.{contract.opportunity_id_field}",
            "contact_join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
            "sold_date_field": f"ghl_contacts_v2.customFields[{contract.sold_date_custom_field_id}] (ISO)",
            "included_stage_ids": list(contract.stage_ids),
        },
        "filters": {
            "lead_source": lead_source,
            "dedupe_by": (str(dedupe_by or "opportunity").strip().lower() or "opportunity"),
        },
        "breakdowns": {
            "sales_by_pipeline": {k: v for k, v in sorted(pipeline_counts.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "sales_by_owner": {k: v for k, v in sorted(owner_counts.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "sales_by_setter_last_name": {k: v for k, v in sorted(setter_counts.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0},
            "sales_by_lead_gen_source": {k: v for k, v in sorted(lead_source_counts.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0}
        },
        "sample_rows": contrib_rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return payload


def render_html(payload: dict[str, Any]) -> str:
    # Keep it dead simple for mobile QA.
    rows_html = "".join(
        f"<tr><td><code>{r.get('opportunityId') or ''}</code></td><td><code>{r.get('contactId') or ''}</code></td><td><code>{r.get('pipelineStageId') or ''}</code></td><td>{r.get('pipelineName') or ''}</td><td>{r.get('lastName_contact') or ''}</td><td>{r.get('dateSold') or ''}</td></tr>"
        for r in payload.get("sample_rows", [])
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>QA — Sales</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:#0b0f14; color:#e8eef6; }}
    .wrap {{ padding: 18px; max-width: 980px; margin: 0 auto; }}
    .card {{ background:#121a24; border:1px solid #1f2a38; border-radius:12px; padding:16px; margin-top:12px; }}
    .kpi {{ font-size:44px; font-weight:900; }}
    .label {{ color:#9db0c7; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    code {{ background:#0e1520; padding:2px 6px; border-radius:6px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom:1px solid #1f2a38; padding:8px; text-align:left; font-size: 13px; }}
    th {{ color:#9db0c7; font-weight:700; }}
    a {{ color:#6ee7b7; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\" style=\"background:linear-gradient(135deg,#00C853 0%,#1b5e20 100%); border:none;\">
      <div style=\"font-weight:900; font-size:18px\">QA — Sales</div>
      <div style=\"opacity:.9\">Window: {payload['window_start_local']} → {payload['window_end_local']} ({payload['timezone']})</div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Result</div>
      <div class=\"kpi\">{payload['result']}</div>
      <div style=\"color:#9db0c7\">Method: {payload['count_method']}</div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Contract (How it is formed from DB)</div>
      <div style=\"margin-top:8px\">Base collection: <code>{payload['contract']['base_collection']}</code></div>
      <div>Sold date field: <code>{payload['contract']['sold_date_field']}</code></div>
      <div>Stage field: <code>{payload['contract']['stage_field']}</code></div><div>Contact join: <code>{payload['contract']['contact_join']}</code></div>
      <div>Opportunity id field: <code>{payload['contract']['opportunity_id_field']}</code></div>
      <div style=\"margin-top:8px\">Included stage IDs: <code>{len(payload['contract']['included_stage_ids'])}</code></div>
      <div style=\"margin-top:8px\">Debug: opps scanned <code>{payload['debug']['opportunities_scanned']}</code>; matched stage <code>{payload['debug']['opportunities_matched_stage']}</code>; matched stage+date <code>{payload['debug']['opportunities_matched_stage_and_date']}</code></div>
      <div style=\"margin-top:8px\">JSON: <a href=\"?format=json\">?format=json</a></div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Sample contributing rows (first 25)</div>
      <table>
        <thead>
          <tr><th>opportunityId</th><th>contactId</th><th>pipelineStageId</th><th>pipeline</th><th>lastName</th><th>dateSold</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="6">No rows in this window.</td></tr>'}
        </tbody>
      </table>
    </div>

    <div style=\"margin-top:12px; color:#9db0c7; font-size:12px\">Generated at {payload['generated_at']}</div>
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
            dedupe_by = (qs.get("dedupe_by", [""])[0] or "").strip() or None

            # MANDATORY: all reporting uses EST (America/New_York). Ignore any incoming tz param.
            tz = "America/New_York"

            contract = SalesMetricContract()
            db = get_db()
            payload = compute_sales(db, contract, year=year, month=month, tz=tz, start=start, end=end, lead_source=lead_source, dedupe_by=dedupe_by)

            if want_json:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)