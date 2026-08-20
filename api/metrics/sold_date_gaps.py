# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sold_date_gaps

Read-only QA: contacts currently in the 8 Sold / Sale Cancelled stages
whose Sold Date custom field (P9oBjgbZjJdeE0OkBj9T) is missing or blank.

Purpose: catch the next White-style wipe before month sales move.
Does not write or restore any Sold Date values.

Grain: distinct contactId.
Query: pipelineStageId IN the same 8 stage IDs compute_sales uses, then
get_all those contacts only. No full opp/contact stream.

Params:
- year, month (defaults to current UTC year/month; accepted for QA URLs)
- format=json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sales import SalesMetricContract, get_db

SOLD_DATE_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def contact_display_name(contact: dict | None) -> str:
    if not isinstance(contact, dict):
        return ""
    parts = [compact_str(contact.get("firstName")), compact_str(contact.get("lastName"))]
    name = " ".join(p for p in parts if p)
    if name:
        return name
    return compact_str(contact.get("name") or contact.get("displayName"))


def sold_date_raw(contact: dict | None, field_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == field_id:
            return cf.get("value")
    return None


def sold_date_yyyy_mm_dd(raw: Any) -> str | None:
    """Date-only. Do not timezone-shift a ...Z wrapper (same rule as compute_sales)."""
    if isinstance(raw, str) and len(raw.strip()) >= 10:
        return raw.strip()[:10]
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


def load_pipelines_by_ids(db: firestore.Client, pipeline_ids) -> tuple[dict[str, str], dict[str, str]]:
    """Bounded pipeline name + stage name lookups. No collection stream."""
    names: dict[str, str] = {}
    stages: dict[str, str] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in pipeline_ids:
        pid = compact_str(raw)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        needed.append(pid)

    def _remember(d: dict, snap_id: str) -> None:
        pid = compact_str(d.get("id") or snap_id)
        nm = d.get("name")
        if pid and nm:
            names[pid] = str(nm)
        for st in (d.get("stages") or []):
            if not isinstance(st, dict):
                continue
            sid = compact_str(st.get("id"))
            sname = compact_str(st.get("name"))
            if sid and sname and sid not in stages:
                stages[sid] = sname

    refs = [db.collection("ghl_pipelines_v2").document(pid) for pid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            _remember(snap.to_dict() or {}, snap.id)
    for pid in needed:
        if pid in names:
            continue
        misses = list(
            db.collection("ghl_pipelines_v2").where("id", "==", pid).limit(1).stream()
        )
        if misses:
            _remember(misses[0].to_dict() or {}, pid)
    return names, stages


def compute_sold_date_gaps(
    db: firestore.Client,
    contract: SalesMetricContract,
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    stage_ids = list(contract.stage_ids)
    stage_set = set(contract.stage_ids)
    sold_field_id = contract.sold_date_custom_field_id or SOLD_DATE_FIELD_ID

    # Same 8-stage `in` query as compute_sales. Firestore `in` max 10.
    opp_snaps = list(
        db.collection(contract.collection)
        .where(contract.stage_field, "in", stage_ids)
        .stream()
    )

    needed_contact_ids: list[str] = []
    needed_pipeline_ids: list[str] = []
    for snap in opp_snaps:
        opp = snap.to_dict() or {}
        if opp.get(contract.stage_field) not in stage_set:
            continue
        cid = compact_str(opp.get("contactId"))
        if cid:
            needed_contact_ids.append(cid)
        pid = compact_str(opp.get("pipelineId"))
        if pid:
            needed_pipeline_ids.append(pid)

    contacts_map = load_contacts_by_ids(db, needed_contact_ids)
    pipe_names, stage_names = load_pipelines_by_ids(db, needed_pipeline_ids)

    gaps_by_contact: dict[str, dict[str, Any]] = {}
    seen_contacts: set[str] = set()
    sold_stage_contacts = 0
    missing_contact = 0

    for snap in opp_snaps:
        opp = snap.to_dict() or {}
        stage_id = opp.get(contract.stage_field)
        if stage_id not in stage_set:
            continue
        contact_id = compact_str(opp.get("contactId"))
        if not contact_id or contact_id in seen_contacts:
            continue
        seen_contacts.add(contact_id)

        contact = contacts_map.get(contact_id)
        if not contact:
            missing_contact += 1
            continue

        sold_stage_contacts += 1
        raw = sold_date_raw(contact, sold_field_id)
        if sold_date_yyyy_mm_dd(raw):
            continue

        opp_id = compact_str(opp.get(contract.opportunity_id_field) or snap.id)
        assigned = compact_str(opp.get("assignedTo")) or None
        pipeline_id = compact_str(opp.get("pipelineId"))
        gaps_by_contact[contact_id] = {
            "contactId": contact_id,
            "name": contact_display_name(contact),
            "opportunityId": opp_id,
            "pipeline": pipe_names.get(pipeline_id) or pipeline_id or None,
            "stage": stage_names.get(compact_str(stage_id)) or compact_str(stage_id) or None,
            "pipelineStageId": compact_str(stage_id) or None,
            "assignedTo": assigned,
        }

    rows = sorted(
        gaps_by_contact.values(),
        key=lambda r: (compact_str(r.get("name")).lower(), compact_str(r.get("contactId"))),
    )

    return {
        "metric": "Sold Date Gaps",
        "unit": "count",
        "year": year,
        "month": month,
        "timezone": "America/New_York",
        "result": len(rows),
        "count_method": (
            "COUNT_DISTINCT(ghl_opportunities_v2.contactId) where pipelineStageId in "
            "compute_sales stage_ids and ghl_contacts_v2.customFields[P9oBjgbZjJdeE0OkBj9T] "
            "is missing/blank (date-only, no timezone shift)"
        ),
        "read_only": True,
        "debug": {
            "opportunities_scanned": len(opp_snaps),
            "sold_stage_contacts_joined": sold_stage_contacts,
            "contacts_missing": missing_contact,
            "gaps": len(rows),
        },
        "contract": {
            "base_collection": contract.collection,
            "stage_field": f"{contract.collection}.{contract.stage_field}",
            "included_stage_ids": list(contract.stage_ids),
            "contact_join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
            "sold_date_field": f"ghl_contacts_v2.customFields[{sold_field_id}] (ISO date-only)",
            "grain": "distinct contactId",
            "writes": "none — does not write or restore Sold Date",
        },
        "rows": rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    tr = []
    for r in rows:
        tr.append(
            "<tr>"
            f"<td><code>{r.get('contactId') or ''}</code></td>"
            f"<td>{r.get('name') or ''}</td>"
            f"<td><code>{r.get('opportunityId') or ''}</code></td>"
            f"<td>{r.get('pipeline') or ''}</td>"
            f"<td>{r.get('stage') or ''}</td>"
            f"<td><code>{r.get('assignedTo') or ''}</code></td>"
            "</tr>"
        )
    rows_html = "\n".join(tr) if tr else "<tr><td colspan='6' style='padding:8px'>No gaps</td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>QA — Sold Date Gaps</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:#0b0f14;color:#e8eef6;}}
.wrap{{padding:18px;max-width:1180px;margin:0 auto;}}
.card{{background:#121a24;border:1px solid #1f2a38;border-radius:12px;padding:16px;margin-top:12px;}}
.label{{color:#9db0c7;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}}
.kpi{{font-size:44px;font-weight:900;}}
code{{background:#0e1520;padding:2px 6px;border-radius:6px;}}
th,td{{border-bottom:1px solid #1f2a38;padding:8px;font-size:12px;}}
th{{color:#9db0c7;text-align:left;}}
a{{color:#6ee7b7;}}
</style></head>
<body><div class="wrap">
<div class="card" style="background:linear-gradient(135deg,#00C853 0%,#1b5e20 100%);border:none;">
  <div style="font-weight:900;font-size:18px">QA — Sold Date Gaps</div>
  <div style="opacity:.9">Contacts in Sold / Sale Cancelled with blank Sold Date (P9oBjgbZjJdeE0OkBj9T). Read-only.</div>
</div>
<div class="card"><div class="label">Gaps</div><div class="kpi">{payload['result']}</div>
<div style="color:#9db0c7">{payload['count_method']}</div>
<div style="margin-top:8px">JSON: <a href="?format=json">?format=json</a></div>
</div>
<div class="card"><div class="label">Contract</div>
<pre style="white-space:pre-wrap;color:#9db0c7">{json.dumps(payload['contract'], indent=2)}</pre>
</div>
<div class="card"><div class="label">Gap contacts</div>
<table style="width:100%; border-collapse: collapse; margin-top: 10px;">
<thead><tr>
<th>contactId</th><th>name</th><th>opportunityId</th><th>pipeline</th><th>stage</th><th>assignedTo</th>
</tr></thead>
<tbody>
{rows_html}
</tbody></table>
</div>
</div></body></html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = qs.get("format", [""])[0].lower() == "json"

            now = datetime.utcnow()
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])

            contract = SalesMetricContract()
            db = get_db()
            payload = compute_sold_date_gaps(db, contract, year=year, month=month)

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


Handler = handler
