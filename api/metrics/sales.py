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
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.oauth2 import service_account
from google.cloud import firestore


@dataclass(frozen=True)
class SalesMetricContract:
    metric_name: str = "Sales"
    unit: str = "count"

    # DB mapping
    collection: str = "ghl_contacts"
    sold_date_field: str = "dateSold"  # epoch millis
    stage_field: str = "pipelineStageId"
    opportunity_id_field: str = "opportunityId"

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


def compute_sales(db: firestore.Client, contract: SalesMetricContract, *, year: int, month: int, tz: str) -> dict[str, Any]:
    start_ms, end_ms, start_iso, end_iso = month_window_ms(year, month, tz)

    q = (
        db.collection(contract.collection)
        .where(contract.sold_date_field, ">=", start_ms)
        .where(contract.sold_date_field, "<", end_ms)
    )

    stage_set = set(contract.stage_ids)
    contrib_rows: list[dict[str, Any]] = []
    unique_keys: set[str] = set()

    scanned = 0
    matched_stage = 0

    for doc in q.stream():
        scanned += 1
        d = doc.to_dict() or {}
        stage_id = d.get(contract.stage_field)
        if stage_id not in stage_set:
            continue
        matched_stage += 1

        opp_id = d.get(contract.opportunity_id_field)
        # Choose COUNT DISTINCT of opportunityId when present, else fall back to doc_id.
        # This prevents double-counting if the same opportunity shows up multiple times.
        key = str(opp_id) if opp_id else f"doc:{doc.id}"
        unique_keys.add(key)

        # Keep a small sample for QA (PII-minimal)
        if len(contrib_rows) < 25:
            contrib_rows.append(
                {
                    "doc_id": doc.id,
                    "opportunityId": opp_id,
                    "pipelineStageId": stage_id,
                    "dateSold": d.get(contract.sold_date_field),
                    "team": d.get("team"),
                    "pipelineId": d.get("pipelineId"),
                    "stageName": d.get("stageName"),
                    "assignedTo": d.get("assignedTo"),
                    "setter": d.get("setter"),
                    "leadSource": d.get("leadSource"),
                }
            )

    result = {
        "metric": contract.metric_name,
        "unit": contract.unit,
        "year": year,
        "month": month,
        "timezone": tz,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "result": len(unique_keys),
        "count_method": "COUNT_DISTINCT(opportunityId) with fallback to doc_id",
        "debug": {
            "docs_scanned_in_date_range": scanned,
            "docs_matched_stage": matched_stage,
            "distinct_keys": len(unique_keys),
        },
        "contract": {
            "collection": contract.collection,
            "date_field": f"{contract.collection}.{contract.sold_date_field}",
            "stage_field": f"{contract.collection}.{contract.stage_field}",
            "opportunity_id_field": f"{contract.collection}.{contract.opportunity_id_field}",
            "included_stage_ids": list(contract.stage_ids),
        },
        "sample_rows": contrib_rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return result


def render_html(payload: dict[str, Any]) -> str:
    # Keep it dead simple for mobile QA.
    rows_html = "".join(
        f"<tr><td><code>{r.get('opportunityId') or ''}</code></td><td><code>{r.get('pipelineStageId') or ''}</code></td><td>{r.get('team') or ''}</td><td>{r.get('dateSold') or ''}</td></tr>"
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
      <div style=\"margin-top:8px\">Collection: <code>{payload['contract']['collection']}</code></div>
      <div>Date field: <code>{payload['contract']['date_field']}</code></div>
      <div>Stage field: <code>{payload['contract']['stage_field']}</code></div>
      <div>Opportunity id field: <code>{payload['contract']['opportunity_id_field']}</code></div>
      <div style=\"margin-top:8px\">Included stage IDs: <code>{len(payload['contract']['included_stage_ids'])}</code></div>
      <div style=\"margin-top:8px\">Debug: scanned <code>{payload['debug']['docs_scanned_in_date_range']}</code> docs in date range; matched stage <code>{payload['debug']['docs_matched_stage']}</code></div>
      <div style=\"margin-top:8px\">JSON: <a href=\"?format=json\">?format=json</a></div>
    </div>

    <div class=\"card\">
      <div class=\"label\">Sample contributing rows (first 25)</div>
      <table>
        <thead>
          <tr><th>opportunityId</th><th>pipelineStageId</th><th>team</th><th>dateSold</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="4">No rows in this window.</td></tr>'}
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
            tz = qs.get("tz", ["America/New_York"])[0]

            contract = SalesMetricContract()
            db = get_db()
            payload = compute_sales(db, contract, year=year, month=month, tz=tz)

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
