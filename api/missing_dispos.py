# -*- coding: utf-8 -*-

"""Vercel Python function: /api/missing_dispos

Missing Dispos Dashboard

Definition:
- List GHL opportunities where:
  - Opportunity is still in pipeline stage named "New Appointment"
  - The scheduled appointment datetime (contact field) is in the past (<= now)
  - And the scheduled appointment datetime is within the selected window

Purpose:
- Identify appointments that have passed but are still sitting in "New Appointment" (missing disposition / stage move).

Ordering:
- Scheduled appointment ASC (oldest first)

Time windows:
- Default: last 14 days (America/New_York)
- Optional: start/end date-only range (inclusive end) applied to scheduled appointment datetime

Collections:
- ghl_opportunities_v2
- ghl_contacts_v2 (scheduled appointment datetime)
- ghl_pipelines_v2 (resolve stage name / pipeline)
- ghl_users_v2 (resolve owner)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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


def parse_int(qs: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(qs.get(key, [str(default)])[0])
    except Exception:
        return default


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    try:
        y, m, d = [int(x) for x in t.split("-")]
        return y, m, d
    except Exception:
        return None


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_local, end_local


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime]:
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


def last_n_days_window(*, days: int, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    # date-only window: start at midnight N days ago, end at next midnight after today
    end_local = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    start_local = end_local - timedelta(days=days)
    return start_local, end_local


def parse_appt_dt_local(s: Any, tz_name: str) -> datetime | None:
    """Parse GHL 'Appointment Date and Time' contact field.

    Expected example: 'Wednesday, March 11, 2026 6:00 PM'
    """

    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None

    try:
        # Allow a few minor variations in spacing
        dt_naive = datetime.strptime(txt, "%A, %B %d, %Y %I:%M %p")
    except Exception:
        return None

    return dt_naive.replace(tzinfo=ZoneInfo(tz_name))


def pipelines_stage_lookup(db: firestore.Client) -> dict[str, str]:
    """Map stageId -> stageName by reading ghl_pipelines_v2.stages[]."""
    out: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        d = snap.to_dict() or {}
        stages = d.get("stages") or []
        if not isinstance(stages, list):
            continue
        for st in stages:
            if not isinstance(st, dict):
                continue
            sid = st.get("id")
            name = st.get("name")
            if sid and name and str(sid) not in out:
                out[str(sid)] = str(name)
    return out


def pipeline_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        d = snap.to_dict() or {}
        pid = str(d.get("id") or snap.id)
        nm = str(d.get("name") or "")
        if pid and nm:
            out[pid] = nm
    return out


def users_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_users_v2").stream():
        d = snap.to_dict() or {}
        uid = str(d.get("id") or snap.id)
        nm = str(d.get("name") or uid)
        out[uid] = nm
    return out


def html_escape(x: Any) -> str:
    return (
        str(x)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_page(*, rows_html: str, count: int, subtitle: str) -> str:
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Missing Dispos</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;
      --pink: #ec4899;
      --pink2: #f472b6;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background: var(--bg); color: var(--text); }
    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar {
      position: relative;
      display:flex; align-items:flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap;
      padding: 18px 20px; border-radius: 14px; background: var(--card);
      border: 1px solid var(--border); box-shadow: var(--shadow);
    }

    .adminSettings {
      position: absolute;
      top: 16px;
      right: 18px;
    }

    .title { font-size: 22px; font-weight: 950; color: #1a2b4a; letter-spacing: -0.02em; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px; width: 200px; border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

    .nav { margin-top: 12px; display:flex; gap: 10px; flex-wrap: wrap; }
    .navbtn {
      display:inline-flex; align-items:center; padding: 9px 12px;
      border-radius: 12px; border: 1px solid var(--border);
      background: #fff; color: #1f2937; font-size: 13px; font-weight: 800; text-decoration:none;
    }

    .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow); margin-top: 14px; }

    table { width:100%; border-collapse: collapse; margin-top: 8px; }
    th { text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); color: var(--muted); font-size: 12px; font-weight: 950; }
    td { font-size: 12px; }
    code { background:#f1f5f9; padding:2px 6px; border-radius: 8px; }

    .filters { display:flex; gap: 10px; flex-wrap: wrap; align-items:flex-end; margin-top: 10px; }
    .filters label { font-size: 12px; font-weight: 900; color: var(--muted); }
    .filters input { border:1px solid var(--border); border-radius: 10px; padding: 8px 10px; font-weight: 900; }
    .btn { background: var(--pink); border: 1px solid var(--pink); color:#fff; border-radius: 10px; padding: 8px 10px; font-size: 13px; font-weight: 950; cursor:pointer; }
    .btn.secondary { background:#fff; border: 1px solid var(--border); color:#334155; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Missing Dispos</div>
        <div class="subtitle">__SUBTITLE__</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn" href="/api/fma_dashboard">FMS dashboard</a>
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
          <a class="navbtn" href="/api/missing_dispos">Missing Dispos</a>
        </div>
      </div>
      <div style="min-width:320px">
        <a class="navbtn adminSettings" href="/api/settings">Admin Settings</a>
        <div style="color: var(--muted); font-size: 12px; font-weight: 900;">Custom Range (Scheduled Appointment)</div>
        <div class="filters">
          <div>
            <label>Start</label><br />
            <input id="startDate" type="date" />
          </div>
          <div>
            <label>End</label><br />
            <input id="endDate" type="date" />
          </div>
          <button class="btn" id="apply">Apply</button>
          <button class="btn secondary" id="clear">Clear</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div style="display:flex; align-items:flex-end; justify-content: space-between; gap: 10px; flex-wrap:wrap">
        <div>
          <div style="color: var(--muted); font-size: 12px; font-weight: 900;">Opportunities</div>
          <div style="font-size: 34px; font-weight: 950;">__COUNT__</div>
        </div>
        <div style="color: var(--muted2); font-size: 12px; font-weight: 900;">Stage = New Appointment, scheduled appointment <= now</div>
      </div>

      <div style="margin-top:10px; overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Owner</th>
              <th>Pipeline</th>
              <th>Stage</th>
              <th>appointmentOccurredAt</th>
              <th style="text-align:right">Days Since</th>
              <th>opportunityId</th>
            </tr>
          </thead>
          <tbody>
            __ROWS__
          </tbody>
        </table>
      </div>
    </div>
  </div>

<script>
  const url = new URL(window.location.href);
  const start = url.searchParams.get('start') || '';
  const end = url.searchParams.get('end') || '';
  document.getElementById('startDate').value = start;
  document.getElementById('endDate').value = end;

  document.getElementById('apply').addEventListener('click', () => {
    const s = document.getElementById('startDate').value;
    const e = document.getElementById('endDate').value;
    if (s && e) {
      url.searchParams.set('start', s);
      url.searchParams.set('end', e);
      window.location.href = url.toString();
    }
  });

  document.getElementById('clear').addEventListener('click', () => {
    url.searchParams.delete('start');
    url.searchParams.delete('end');
    window.location.href = url.toString();
  });
</script>
</body>
</html>
"""

    return (
        html.replace("__ROWS__", rows_html)
        .replace("__COUNT__", str(count))
        .replace("__SUBTITLE__", html_escape(subtitle))
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)

        tz = "America/New_York"
        now_utc = datetime.now(timezone.utc)
        now = datetime.utcnow()

        year = parse_int(qs, "year", now.year)
        month = parse_int(qs, "month", now.month)
        start = (qs.get("start", [""])[0] or "").strip() or None
        end = (qs.get("end", [""])[0] or "").strip() or None

        try:
            if start and end:
                start_local, end_local = date_range_window(start, end, tz)
                subtitle_window = f"Custom range: {start} → {end} (date-only)"
            else:
                # Default: last 14 days (date-only) in business timezone
                start_local, end_local = last_n_days_window(days=14, tz_name=tz)
                subtitle_window = "Default: last 14 days (date-only)"

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            db = get_db()
            stage_lookup = pipelines_stage_lookup(db)
            pipelines = pipeline_name_lookup(db)
            users = users_lookup(db)

            # Build set of stageIds whose stage name is "New Appointment"
            new_appt_stage_ids = {sid for sid, nm in stage_lookup.items() if str(nm).strip().lower() == 'new appointment'}

            # Contact lookup cache (NOTE: doc_id may not equal GHL contact id)
            contact_cache: dict[str, dict | None] = {}

            def get_contact(contact_id: str) -> dict | None:
                if not contact_id:
                    return None
                if contact_id in contact_cache:
                    return contact_cache[contact_id]

                snap = db.collection('ghl_contacts_v2').document(str(contact_id)).get()
                if snap.exists:
                    contact_cache[contact_id] = snap.to_dict() or {}
                    return contact_cache[contact_id]

                snaps = list(db.collection('ghl_contacts_v2').where('id', '==', str(contact_id)).limit(1).stream())
                contact_cache[contact_id] = (snaps[0].to_dict() or {}) if snaps else None
                return contact_cache[contact_id]

            # Scheduled appointment custom field id on contact
            APPT_CF_ID = 'e3udzXVTyqrMqICpyqjF'

            def contact_appt_dt_local(contact: dict | None) -> datetime | None:
                if not isinstance(contact, dict):
                    return None
                for cf in (contact.get('customFields') or []):
                    if isinstance(cf, dict) and cf.get('id') == APPT_CF_ID:
                        return parse_appt_dt_local(cf.get('value'), tz)
                return None

            # Query only opportunities in New Appointment stages (small-ish set). If there are >30 ids,
            # fall back to streaming and filtering.
            opp_col = db.collection('ghl_opportunities_v2')
            stage_ids_list = sorted(list(new_appt_stage_ids))

            if 0 < len(stage_ids_list) <= 30:
                q = opp_col.where('pipelineStageId', 'in', stage_ids_list)
            else:
                q = opp_col

            rows = []

            for snap in q.stream():
                opp = snap.to_dict() or {}

                stage_id = str(opp.get('pipelineStageId') or '')
                stage_name = stage_lookup.get(stage_id, '')
                if str(stage_name).strip().lower() != 'new appointment':
                    continue

                cid = str(opp.get('contactId') or '')
                contact = get_contact(cid)
                appt_local = contact_appt_dt_local(contact)
                if not appt_local:
                    continue

                appt_utc = appt_local.astimezone(timezone.utc)

                # Must have passed
                if appt_utc > now_utc:
                    continue

                # Window filter (scheduled appointment)
                if not (start_utc <= appt_utc < end_utc):
                    continue

                assigned_to = str(opp.get('assignedTo') or '')
                owner_name = users.get(assigned_to, assigned_to)

                pid = str(opp.get('pipelineId') or '')
                pname = pipelines.get(pid, pid)

                days_since = int((now_utc - appt_utc).total_seconds() // 86400)

                rows.append({
                    'owner': owner_name,
                    'pipeline': pname,
                    'stage': stage_name,
                    'appt_utc': appt_utc,
                    'days_since': days_since,
                    'opportunity_id': str(opp.get('id') or snap.id),
                })

            rows.sort(key=lambda r: r['appt_utc'])

            trs = []
            rows_count = 0
            for r in rows:
                trs.append(
                    "<tr>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; font-weight:900'>{html_escape(r['owner'])}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0;'>{html_escape(r['pipeline'])}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0;'>{html_escape(r['stage'])}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; font-variant-numeric:tabular-nums;'><code>{html_escape(r['appt_utc'].isoformat())}</code></td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0; text-align:right; font-variant-numeric:tabular-nums;'>{r['days_since']}</td>"
                    f"<td style='padding:10px 8px; border-bottom:1px solid #e8ecf0;'><code>{html_escape(r['opportunity_id'])}</code></td>"
                    "</tr>"
                )
                rows_count += 1

            rows_html = "\n".join(trs) if trs else "<tr><td colspan='6' style='padding:12px 8px; color:#9ca3af'>No rows</td></tr>"

            body = render_page(
                rows_html=rows_html,
                count=rows_count,
                subtitle=f"Scheduled appointment passed but still in stage 'New Appointment' (oldest first). {subtitle_window}",
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
