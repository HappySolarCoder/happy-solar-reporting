# -*- coding: utf-8 -*-

"""Vercel Python function: /api/data_cleanup

Admin Data Cleanup dashboard.

Shows contacts where:
- Appointment Date/Time is present (contact custom field e3udzXVTyqrMqICpyqjF)
- AND one of:
  - Setter Last Name is empty/missing (contact custom field Eq4NLTSkJ56KTxbxypuE)
  - Setter Last Name is a team label (Rochester, Buffalo, Syracuse, Virtual)
  - Contact is missing assigned owner
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


APPT_CF_ID = "e3udzXVTyqrMqICpyqjF"
SETTER_CF_ID = "Eq4NLTSkJ56KTxbxypuE"
TEAM_LABELS = {"rochester", "buffalo", "syracuse", "virtual"}
DEFAULT_LOCATION_ID = os.environ.get("GHL_LOCATION_ID") or "MMKRDviKggXzlcHQTnvZ"


def _unauthorized(h: BaseHTTPRequestHandler):
    h.send_response(401)
    h.send_header('WWW-Authenticate', 'Basic realm="Happy Solar Settings"')
    h.send_header('Content-Type', 'text/plain; charset=utf-8')
    h.end_headers()
    h.wfile.write(b'Unauthorized')


def _check_auth(h: BaseHTTPRequestHandler) -> bool:
    pw = os.environ.get('SETTINGS_PASSWORD')
    if not pw:
        return False

    auth = h.headers.get('Authorization') or ''
    if not auth.startswith('Basic '):
        return False
    try:
        raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
        user, pwd = raw.split(':', 1)
        return pwd == pw
    except Exception:
        return False


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

    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def html_escape(s: Any) -> str:
    t = "" if s is None else str(s)
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def cf_value(custom_fields: list[dict] | None, field_id: str) -> str | None:
    for cf in custom_fields or []:
        if isinstance(cf, dict) and str(cf.get("id") or "") == field_id:
            v = cf.get("value")
            if v in (None, ""):
                v = cf.get("fieldValueString")
            if v in (None, ""):
                return None
            return str(v).strip()
    return None


def parse_appt_local(txt: str | None, tz_name: str = "America/New_York") -> datetime | None:
    if not txt:
        return None
    s = str(txt).strip()
    if not s:
        return None
    try:
        dt_naive = datetime.strptime(s, "%A, %B %d, %Y %I:%M %p")
        return dt_naive.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        return None


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s or not isinstance(s, str):
        return None
    try:
        y, m, d = [int(x) for x in s.strip().split("-")]
        return y, m, d
    except Exception:
        return None


def render(rows_html: str, count: int, empty_count: int, team_count: int, assigned_count: int, start_date: str, end_date: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Data Cleanup</title>
  <style>
    :root {{
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --pink:#ec4899; --pink2:#f472b6;
      --shadow:0 1px 3px rgba(17,24,39,0.06);
    }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }}
    .wrap {{ padding:22px; max-width:1240px; margin:0 auto; }}
    .topbar {{ display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:var(--shadow); }}
    .topbar > div {{ min-width: 0; }}
    .title {{ font-size:22px; font-weight:950; color:#1a2b4a; letter-spacing:-0.02em; }}
    .subtitle {{ margin-top:4px; color:var(--muted); font-size:13px; }}
    .pinkline {{ height:3px; width:240px; border-radius:999px; background:linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }}
    .nav {{ margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; }}
    .navbtn {{ display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }}
    .navbtn.active {{ background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color:#b80b66; }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap:14px; margin-top:14px; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:var(--shadow); }}
    .span-3 {{ grid-column: span 3; }} .span-12 {{ grid-column: span 12; }}
    @media (max-width:980px) {{ .span-3 {{ grid-column: span 12; }} }}
    @media (max-width:820px) {{
      .wrap {{ padding:12px; }}
      .topbar {{ padding:12px; gap:10px; }}
      .title {{ font-size:20px; }}
      .nav {{ display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; -webkit-overflow-scrolling:touch; }}
      .navbtn {{ white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; }}
      .filters {{ width:100%; display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:8px; }}
      .filters input[type=date], .filters .btn {{ width:100%; }}
      th, td {{ font-size:11px; }}
    }}
    .label {{ color:var(--muted); font-size:12px; font-weight:900; }}
    .kpi {{ margin-top:4px; font-size:34px; font-weight:950; }}
    .filters {{ display:flex; align-items:flex-end; gap:8px; flex-wrap:wrap; }}
    .filters label {{ display:block; font-size:12px; color:var(--muted); font-weight:900; margin-bottom:4px; }}
    .filters input[type=date] {{ border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:800; background:#fff; }}
    .btn {{ display:inline-flex; align-items:center; padding:8px 12px; border-radius:10px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:12px; font-weight:900; text-decoration:none; cursor:pointer; }}
    table {{ width:100%; border-collapse: collapse; margin-top:10px; }}
    th, td {{ border-bottom:1px solid var(--border); padding:9px 8px; text-align:left; font-size:12px; }}
    th {{ color:var(--muted); font-weight:950; }}
    td {{ color:#0f172a; font-weight:800; }}
    code {{ background:#f1f5f9; padding:2px 6px; border-radius:8px; }}
    a {{ color:#0f766e; text-decoration:none; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Data Cleanup</div>
        <div class=\"subtitle\">Appointment exists + (Setter Last Name empty/team label OR contact missing Assigned Owner)</div>
        <div class=\"pinkline\"></div>
        <div class=\"nav\">
          <a class=\"navbtn\" href=\"/api/company_overview\">Company Overview</a>
          <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales Dashboard</a>
          <a class=\"navbtn\" href=\"/api/missing_dispos\">Missing Dispos</a>
          <a class=\"navbtn\" href=\"/api/settings\">Settings</a>
          <a class=\"navbtn active\" href=\"/api/data_cleanup\">Data Cleanup</a>
        </div>
      </div>
      <div style=\"min-width:320px\">
        <div class=\"label\">Appointment Date Filter</div>
        <form method=\"GET\" class=\"filters\" style=\"margin-top:8px\">
          <div>
            <label>Start</label>
            <input type=\"date\" name=\"start\" value=\"{html_escape(start_date)}\" />
          </div>
          <div>
            <label>End</label>
            <input type=\"date\" name=\"end\" value=\"{html_escape(end_date)}\" />
          </div>
          <button class=\"btn\" type=\"submit\">Apply</button>
          <a class=\"btn\" href=\"/api/data_cleanup\">Reset</a>
        </form>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-3\"><div class=\"label\">Contacts in Cleanup</div><div class=\"kpi\">{count}</div></div>
      <div class=\"card span-3\"><div class=\"label\">Missing Setter Last Name</div><div class=\"kpi\">{empty_count}</div></div>
      <div class=\"card span-3\"><div class=\"label\">Setter = Team Label</div><div class=\"kpi\">{team_count}</div></div>
      <div class=\"card span-3\"><div class=\"label\">Missing Assigned Owner</div><div class=\"kpi\">{assigned_count}</div></div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-12\">
        <table>
          <thead>
            <tr>
              <th>Issue</th>
              <th>Contact</th>
              <th>Setter Last Name</th>
              <th>Appointment Date</th>
              <th>Open in GHL</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _check_auth(self):
            return _unauthorized(self)

        try:
            tz = ZoneInfo("America/New_York")
            now_local = datetime.now(tz)
            qs = parse_qs(urlparse(self.path).query)
            start_q = (qs.get("start", [""])[0] or "").strip()
            end_q = (qs.get("end", [""])[0] or "").strip()

            if not (start_q and end_q):
                # Default: current month (relative)
                start_q = f"{now_local.year:04d}-{now_local.month:02d}-01"
                if now_local.month == 12:
                    end_dt = datetime(now_local.year + 1, 1, 1, tzinfo=tz)
                else:
                    end_dt = datetime(now_local.year, now_local.month + 1, 1, tzinfo=tz)
                end_dt = end_dt.replace(day=1)
                # inclusive end date for UI
                end_q = (end_dt - timedelta(days=1)).strftime("%Y-%m-%d")

            sp = parse_date_ymd(start_q)
            ep = parse_date_ymd(end_q)
            if not (sp and ep):
                raise ValueError("Invalid start/end date; expected YYYY-MM-DD")

            start_local = datetime(sp[0], sp[1], sp[2], 0, 0, 0, tzinfo=tz)
            end_local_excl = datetime(ep[0], ep[1], ep[2], 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            db = get_db()
            rows = []

            for snap in db.collection("ghl_contacts_v2").stream():
                c = snap.to_dict() or {}
                contact_id = str(c.get("id") or snap.id)
                location_id = str(c.get("locationId") or DEFAULT_LOCATION_ID or "")

                appt_raw = cf_value(c.get("customFields") or [], APPT_CF_ID)
                if not appt_raw:
                    continue

                setter_raw = cf_value(c.get("customFields") or [], SETTER_CF_ID)
                setter_norm = (setter_raw or "").strip().lower()

                assigned_owner = (
                    str(c.get("assignedTo") or "").strip()
                    or str(c.get("ownerId") or "").strip()
                    or str(c.get("assignedUserId") or "").strip()
                )

                issue = None
                if not setter_norm:
                    issue = "missing_setter_last_name"
                elif setter_norm in TEAM_LABELS:
                    issue = "setter_is_team_label"
                elif not assigned_owner:
                    issue = "missing_assigned_owner"
                else:
                    continue

                contact_name = (
                    str(c.get("contactName") or "").strip()
                    or (f"{str(c.get('firstName') or '').strip()} {str(c.get('lastName') or '').strip()}".strip())
                    or "—"
                )

                contact_url = None
                if location_id and contact_id:
                    contact_url = f"https://app.gohighlevel.com/v2/location/{location_id}/contacts/detail/{contact_id}"

                appt_local = parse_appt_local(appt_raw)
                if not appt_local:
                    continue

                if not (start_local <= appt_local < end_local_excl):
                    continue

                appt_sort = appt_local.isoformat()

                rows.append({
                    "issue": issue,
                    "contact_name": contact_name,
                    "contact_id": contact_id,
                    "contact_url": contact_url,
                    "setter": setter_raw or "",
                    "assigned_owner": assigned_owner,
                    "appt": appt_raw,
                    "appt_sort": appt_sort,
                })

            rows.sort(key=lambda r: (r["issue"], r["appt_sort"], r["contact_name"].lower()))

            empty_count = sum(1 for r in rows if r["issue"] == "missing_setter_last_name")
            team_count = sum(1 for r in rows if r["issue"] == "setter_is_team_label")
            assigned_count = sum(1 for r in rows if r["issue"] == "missing_assigned_owner")

            if rows:
                row_html = []
                for r in rows:
                    contact_cell = html_escape(r["contact_name"])
                    if r.get("contact_url"):
                        contact_cell = f"<a href='{html_escape(r['contact_url'])}' target='_blank' rel='noreferrer'>{contact_cell}</a>"
                    open_cell = "—"
                    if r.get("contact_url"):
                        open_cell = f"<a href='{html_escape(r['contact_url'])}' target='_blank' rel='noreferrer'>Open Contact</a>"

                    row_html.append(
                        "<tr>"
                        f"<td><code>{html_escape(r['issue'])}</code></td>"
                        f"<td>{contact_cell}</td>"
                        f"<td>{html_escape(r['setter'] or '—')}</td>"
                        f"<td>{html_escape(r['appt'])}</td>"
                        f"<td>{open_cell}</td>"
                        "</tr>"
                    )
                rows_html = "\n".join(row_html)
            else:
                rows_html = "<tr><td colspan='5' style='color:#9ca3af'>No rows</td></tr>"

            body = render(rows_html, len(rows), empty_count, team_count, assigned_count, start_q, end_q).encode("utf-8")
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
