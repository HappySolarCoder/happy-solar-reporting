# -*- coding: utf-8 -*-

"""Vercel Python function: /api/qa_top_appts

QA page for "Top Performers — Appointments" (Opportunities Created by Setter Last Name).

Outputs the underlying opportunity rows that feed the setter-last-name counts.

Columns:
- Contact Last Name
- Setter Last Name (contact custom field)
- Pipeline (resolved name)
- Opportunity CreatedAt

Filters:
- start=YYYY-MM-DD&end=YYYY-MM-DD (date-only, inclusive end) in America/New_York
- Defaults to current month window (America/New_York)

Notes:
- Pipeline inclusion/exclusion follows Opportunities Created metric contract.
- This is a QA aid (no auth), returns HTML.
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


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


def esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s:
        return None
    try:
        y, m, d = [int(x) for x in s.strip().split("-")]
        return y, m, d
    except Exception:
        return None


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_local, end_local


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime]:
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
    return start_local, end_local


def coerce_dt(v: Any) -> datetime | None:
    # Firestore Timestamp often comes as datetime
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    # ISO string
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None

    # {seconds,nanos}
    if isinstance(v, dict) and ("seconds" in v or "_seconds" in v):
        try:
            sec = int(v.get("seconds") or v.get("_seconds") or 0)
            ns = int(v.get("nanos") or v.get("_nanoseconds") or 0)
            return datetime.fromtimestamp(sec + ns / 1e9, tz=timezone.utc)
        except Exception:
            return None

    # epoch seconds / ms
    if isinstance(v, (int, float)):
        try:
            x = float(v)
            # heuristically treat > 1e12 as ms
            if x > 1e12:
                x = x / 1000.0
            return datetime.fromtimestamp(x, tz=timezone.utc)
        except Exception:
            return None

    return None


def contact_custom_field(contact: dict | None, cf_id: str):
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == cf_id:
            return cf.get("value")
    return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            tz = "America/New_York"

            now = datetime.now(timezone.utc)
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            start = (qs.get("start", [""])[0] or "").strip() or None
            end = (qs.get("end", [""])[0] or "").strip() or None

            if start and end:
                start_local, end_local = date_range_window(start, end, tz)
                window_label = f"Custom: {start} → {end}"
            else:
                start_local, end_local = month_window(year, month, tz)
                window_label = f"Month: {year}-{str(month).zfill(2)}"

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            db = get_db()

            # pipeline name lookup
            pipes: dict[str, str] = {}
            for snap in db.collection("ghl_pipelines_v2").stream():
                d = snap.to_dict() or {}
                pid = str(d.get("id") or snap.id)
                nm = str(d.get("name") or "").strip()
                if pid:
                    pipes[pid] = nm

            included = {"buffalo", "syracuse", "rochester", "virtual"}
            excluded = {"inbound/lead locker"}

            contact_cache: dict[str, dict | None] = {}

            def get_contact(contact_id: str) -> dict | None:
                if not contact_id:
                    return None
                if contact_id in contact_cache:
                    return contact_cache[contact_id]

                snap = db.collection("ghl_contacts_v2").document(str(contact_id)).get()
                if snap.exists:
                    contact_cache[contact_id] = snap.to_dict() or {}
                    return contact_cache[contact_id]

                docs = list(db.collection("ghl_contacts_v2").where("id", "==", str(contact_id)).limit(1).stream())
                contact_cache[contact_id] = (docs[0].to_dict() or {}) if docs else None
                return contact_cache[contact_id]

            SETTER_CF = "Eq4NLTSkJ56KTxbxypuE"

            # Query by createdAt if possible
            col = db.collection("ghl_opportunities_v2")
            docs = []
            last_error = None
            try:
                docs = list(
                    col.where("createdAt", ">=", start_utc)
                    .where("createdAt", "<", end_utc)
                    .order_by("createdAt")
                    .limit(3000)
                    .stream()
                )
            except Exception as e:
                last_error = str(e)

            # If typed range query fails (createdAt stored as string/mixed), fall back to bounded stream
            if not docs:
                try:
                    docs = list(col.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(6000).stream())
                except Exception as e2:
                    last_error = (last_error or "") + " | " + str(e2)
                    docs = []

            if not docs:
                # Last resort: stream without ordering (bounded) and filter in code.
                last_error = (last_error or "") + " | fallback_stream"
                docs = []
                i = 0
                for snap in col.stream():
                    docs.append(snap)
                    i += 1
                    if i >= 8000:
                        break

            rows = []
            scanned = 0

            for snap in docs:
                scanned += 1
                opp = snap.to_dict() or {}

                created_dt = coerce_dt(opp.get("createdAt"))
                if not created_dt:
                    continue
                created_utc = created_dt.astimezone(timezone.utc)

                if created_utc < start_utc or created_utc >= end_utc:
                    continue

                pid = str(opp.get("pipelineId") or "")
                pname = str(pipes.get(pid) or "").strip().lower()
                if pname:
                    if pname in excluded:
                        continue
                    if pname not in included:
                        continue

                cid = str(opp.get("contactId") or "")
                contact = get_contact(cid)

                contact_last = (contact.get("lastName") if isinstance(contact, dict) else None) or ""
                setter_last = contact_custom_field(contact, SETTER_CF) or ""

                rows.append(
                    {
                        "contact_last": str(contact_last).strip(),
                        "setter_last": str(setter_last).strip(),
                        "pipeline": str(pipes.get(pid) or pid),
                        "createdAt": created_utc.isoformat(),
                        "opportunity_id": str(opp.get("id") or snap.id),
                    }
                )

            # sort by createdAt
            rows.sort(key=lambda r: r["createdAt"])

            trs = []
            for r in rows:
                trs.append(
                    "<tr>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; font-weight:900'>{esc(r['contact_last'] or '—')}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; font-weight:900'>{esc(r['setter_last'] or 'none')}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0;'>{esc(r['pipeline'] or '—')}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; font-variant-numeric:tabular-nums;'><code>{esc(r['createdAt'])}</code></td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0;'><code>{esc(r['opportunity_id'])}</code></td>"
                    "</tr>"
                )

            body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QA — Appointments (Opps Created)</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f7fa; color:#0f172a; margin:0; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
    .card {{ background:#fff; border:1px solid #e8ecf0; border-radius: 14px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(17,24,39,0.06); }}
    .title {{ font-size: 20px; font-weight: 950; }}
    .meta {{ margin-top: 6px; color:#6b7280; font-size: 12px; font-weight: 900; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 12px; }}
    th {{ text-align:left; padding:10px 8px; border-bottom:1px solid #e8ecf0; color:#6b7280; font-size:12px; font-weight:950; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="title">QA — Opportunities Created (Appointments) rows</div>
      <div class="meta">Window: {esc(window_label)} • Count: <b>{len(rows)}</b> • Scanned: {scanned} • Debug: {esc(last_error or 'ok')}</div>
      <div class="meta">This table is the raw row set feeding "created_by_setter_last_name" (setter last name is from contact custom field).</div>
      <div style="margin-top:10px; overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Contact Last Name</th>
              <th>Setter Last Name</th>
              <th>Pipeline</th>
              <th>CreatedAt (UTC)</th>
              <th>Opportunity ID</th>
            </tr>
          </thead>
          <tbody>
            {''.join(trs) if trs else "<tr><td colspan='5' style='padding:12px 8px; color:#9ca3af'>No rows</td></tr>"}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</body>
</html>"""

            out = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        except Exception as e:
            payload = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
