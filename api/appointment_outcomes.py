# -*- coding: utf-8 -*-

"""Vercel Python function: /api/appointment_outcomes

Appointment Outcomes dashboard
- List of appointments that have been dispositioned
- Filters: Setter Last Name + date range
- Default: yesterday
- Date filtering field: appointment date/time (appointmentStartTime)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

TZ = ZoneInfo("America/New_York")
SETTER_LAST_NAME_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"
DISPOSITION_NOTES_FIELD_ID = "cCcnzoIp8YgW2Pr0sB5E"  # GHL custom field: Disposition Notes
OWNER_NAME_OVERRIDES = {
    "0fhsjcmlntce0cpjyfhj": "William Breen",
}


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        return firestore.Client(project="gemini-assistant-bot", credentials=creds, database="happy-solar")
    return firestore.Client(project="gemini-assistant-bot", database="happy-solar")


def parse_ymd(s: str) -> datetime | None:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d")
    except Exception:
        return None


def parse_firestore_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            if v.endswith("Z"):
                return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def normalize_disposition(v) -> str:
    if v is None:
        return ""
    text = str(v).strip()
    if not text:
        return ""
    n = text.lower().replace("_", " ").replace("-", " ")
    while "  " in n:
        n = n.replace("  ", " ")
    if n == "nosit":
        n = "no sit"
    if n == "sit":
        return "Sit"
    if n == "no sit":
        return "No Sit"
    return text


def get_custom_field_value(custom_fields, field_id: str) -> str:
    if not isinstance(custom_fields, list):
        return ""
    for cf in custom_fields:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("id") or "").strip() != field_id:
            continue
        for key in ("fieldValueString", "value", "field_value", "fieldValue"):
            val = cf.get(key)
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    return ""


def pipeline_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        d = snap.to_dict() or {}
        pid = str(d.get("id") or snap.id)
        out[pid] = str(d.get("name") or pid)
    return out


def pipeline_stage_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        d = snap.to_dict() or {}
        stages = d.get("stages") or []
        if not isinstance(stages, list):
            continue
        for st in stages:
            if not isinstance(st, dict):
                continue
            sid = str(st.get("id") or "").strip()
            sname = str(st.get("name") or "").strip()
            if sid and sname and sid not in out:
                out[sid] = sname
    return out


def user_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_users_v2").stream():
        d = snap.to_dict() or {}
        uid = str(d.get("id") or snap.id)
        name = str(d.get("name") or d.get("firstName") or uid)
        out[uid] = name
    return out


def contact_setter_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_contacts_v2").stream():
        d = snap.to_dict() or {}
        cid = str(d.get("id") or snap.id)
        setter_last = get_custom_field_value(d.get("customFields") or [], SETTER_LAST_NAME_FIELD_ID)
        out[cid] = setter_last
    return out


def format_local(dt_utc: datetime | None) -> str:
    if not dt_utc:
        return ""
    return dt_utc.astimezone(TZ).strftime("%Y-%m-%d %I:%M %p")


def render_page(*, start_date: str, end_date: str, selected_setter: str, setter_options: list[str], rows_html: str, subtitle_window: str) -> str:
    options_html = ['<option value="">All setters</option>']
    for s in setter_options:
        sel = " selected" if s == selected_setter else ""
        options_html.append(f'<option value="{escape(s)}"{sel}>{escape(s)}</option>')

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar - Appointment Outcomes</title>
  <style>
    :root {{
      --bg: #f5f7fa; --card: #ffffff; --border: #e8ecf0;
      --text: #111827; --muted: #6b7280;
      --pink: #ec4899; --pink2: #f472b6;
    }}
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }}
    .wrap {{ padding: 22px; max-width: 1240px; margin: 0 auto; }}
    .topbar {{ position:relative; display:flex; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:2px solid var(--border); }}
    .title {{ font-size:22px; font-weight:950; color:#1a2b4a; letter-spacing:-0.02em; }}
    .subtitle {{ margin-top:4px; color:var(--muted); font-size:13px; }}
    .pinkline {{ height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }}
    .brandCenter {{ position:absolute; left:50%; top:12px; transform:translateX(-50%); pointer-events:none; }}
    .brandCenter img {{ height:56px; width:auto; }}
    .nav {{ margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; justify-content:center; width:100%; }}
    .navbtn {{ display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }}
    .navbtn.active {{ background:rgba(236,72,153,0.10); border-color:rgba(236,72,153,0.45); color:#b80b66; }}
    .adminSettings {{ position:absolute; top:16px; right:18px; }}

    .panel {{ margin-top:14px; background:var(--card); border:1px solid var(--border); border-radius:14px; padding:14px; }}
    .filters {{ display:flex; flex-wrap:wrap; align-items:end; gap:10px; }}
    .filters label {{ font-size:12px; color:#6b7280; font-weight:700; }}
    .input, .select {{ height:36px; border:1px solid #d8dee6; border-radius:10px; padding:0 10px; font-size:13px; background:#fff; color:#0f172a; }}
    .btn {{ height:36px; border-radius:10px; padding:0 12px; border:1px solid #d8dee6; background:#fff; color:#0f172a; font-size:12px; font-weight:800; cursor:pointer; }}
    .btn.primary {{ border-color:rgba(236,72,153,0.45); background:rgba(236,72,153,0.10); color:#b80b66; }}

    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:9px 10px; border-bottom:1px solid var(--border); font-size:13px; }}
    th {{ text-align:left; color:#334155; font-size:12px; text-transform:uppercase; letter-spacing:.03em; background:#f8fafc; }}
    td.right {{ text-align:right; }}
    .empty {{ color:#94a3b8; padding:20px 10px; }}

    @media (max-width: 900px) {{
      .brandCenter {{ display:none; }}
      .adminSettings {{ position:static; }}
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Appointment Outcomes</div>
        <div class=\"subtitle\">Dispositioned appointments list ({escape(subtitle_window)})</div>
        <div class=\"pinkline\"></div>
      </div>

      <div class=\"brandCenter\"><img src=\"https://assets.zyrosite.com/cdn-cgi/image/format=auto,w=180,fit=crop,q=95/Aq2VyN6Nz4fD9PjZ/happy-solar-logo-m2W4o75D7Ks9NQj0.png\" alt=\"Happy Solar\" /></div>

      <div class=\"adminSettings\">
        <a class=\"navbtn\" href=\"/api/settings\">Admin Settings</a>
      </div>

      <div class=\"nav\">
        <a class=\"navbtn\" href=\"/api/company_overview\">Company Overview</a>
        <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales Dashboard</a>
        <a class=\"navbtn\" href=\"/api/fma_dashboard\">FMA Dashboard</a>
        <a class=\"navbtn\" href=\"/api/missing_dispos\">Missing Dispos</a>
        <a class=\"navbtn active\" href=\"/api/appointment_outcomes\">Appointment Outcomes</a>
        <a class=\"navbtn\" href=\"/api/virtual_team_dashboard\">Virtual Team</a>
      </div>
    </div>

    <div class=\"panel\">
      <form class=\"filters\" method=\"get\" action=\"/api/appointment_outcomes\">
        <div>
          <label for=\"setter_last_name\">Setter Last Name</label><br />
          <select class=\"select\" id=\"setter_last_name\" name=\"setter_last_name\">{''.join(options_html)}</select>
        </div>
        <div>
          <label for=\"start_date\">Start Date</label><br />
          <input class=\"input\" id=\"start_date\" name=\"start_date\" type=\"date\" value=\"{escape(start_date)}\" />
        </div>
        <div>
          <label for=\"end_date\">End Date</label><br />
          <input class=\"input\" id=\"end_date\" name=\"end_date\" type=\"date\" value=\"{escape(end_date)}\" />
        </div>
        <button class=\"btn primary\" type=\"submit\">Apply</button>
        <button class=\"btn\" type=\"button\" id=\"yesterdayBtn\">Yesterday</button>
      </form>
    </div>

    <div class=\"panel\" style=\"padding:0; overflow:hidden;\">
      <table>
        <thead>
          <tr>
            <th>Appointment Date & Time</th>
            <th>Setter Last Name</th>
            <th>Disposition</th>
            <th>Disposition Notes</th>
            <th>Contact</th>
            <th>Owner</th>
            <th>Pipeline</th>
            <th>Pipeline Stage</th>
            <th class=\"right\">Opportunity ID</th>
          </tr>
        </thead>
        <tbody>
          {rows_html if rows_html else '<tr><td class="empty" colspan="9">No dispositioned appointments in this window.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    const yBtn = document.getElementById('yesterdayBtn');
    if (yBtn) {{
      yBtn.addEventListener('click', () => {{
        const now = new Date();
        now.setDate(now.getDate() - 1);
        const iso = now.toISOString().slice(0,10);
        document.getElementById('start_date').value = iso;
        document.getElementById('end_date').value = iso;
      }});
    }}
  </script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs((self.path.split("?", 1)[1] if "?" in self.path else ""), keep_blank_values=True)

        today_local = datetime.now(TZ).date()
        yday = today_local - timedelta(days=1)

        start_raw = (qs.get("start_date", [""])[0] or "").strip()
        end_raw = (qs.get("end_date", [""])[0] or "").strip()

        start_dt = parse_ymd(start_raw) or datetime(yday.year, yday.month, yday.day)
        end_dt = parse_ymd(end_raw) or datetime(yday.year, yday.month, yday.day)
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        start_local = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, tzinfo=TZ)
        end_local = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, 999999, tzinfo=TZ)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        selected_setter = (qs.get("setter_last_name", [""])[0] or "").strip()

        rows_html = ""
        setter_options: list[str] = []

        try:
            db = get_db()
            pipelines = pipeline_name_lookup(db)
            stage_names = pipeline_stage_name_lookup(db)
            users = user_name_lookup(db)
            setter_by_contact = contact_setter_lookup(db)

            opp_rows: list[dict] = []
            try:
                q = (
                    db.collection("ghl_opportunities_v2")
                    .where("appointmentStartTime", ">=", start_utc)
                    .where("appointmentStartTime", "<=", end_utc)
                )
                docs = q.stream()
            except Exception:
                docs = db.collection("ghl_opportunities_v2").stream()

            for s in docs:
                d = s.to_dict() or {}
                dt_utc = parse_firestore_ts(d.get("appointmentStartTime"))
                if not dt_utc:
                    continue
                if dt_utc < start_utc or dt_utc > end_utc:
                    continue

                dispo = normalize_disposition(d.get("dispositionValue"))
                if not dispo:
                    continue

                contact_id = str(d.get("contactId") or "").strip()
                setter_last = setter_by_contact.get(contact_id, "")

                disposition_notes = str(
                    d.get("dispositionNotes")
                    or d.get("dispositionNote")
                    or d.get("notes")
                    or get_custom_field_value(d.get("customFields") or [], DISPOSITION_NOTES_FIELD_ID)
                    or ""
                ).strip()
                if selected_setter and setter_last.lower().strip() != selected_setter.lower().strip():
                    continue

                pid = str(d.get("pipelineId") or "").strip()
                pipeline_name = pipelines.get(pid, pid)
                stage_id = str(d.get("pipelineStageId") or d.get("pipelineStageUId") or "").strip()
                stage_name = stage_names.get(stage_id, stage_id)
                if pipeline_name.strip().lower() == "inbound/lead locker":
                    continue

                owner_id = str(d.get("assignedTo") or "").strip()
                owner_name = users.get(owner_id, "")
                if not owner_name:
                    owner_name = OWNER_NAME_OVERRIDES.get(owner_id.lower(), "")
                if not owner_name:
                    for k in ("assignedToName", "assignedToUserName", "assignedUserName", "ownerName"):
                        v = d.get(k)
                        if v and str(v).strip():
                            owner_name = str(v).strip()
                            break
                if not owner_name:
                    au = d.get("assignedToUser")
                    if isinstance(au, dict):
                        v = au.get("name")
                        if v and str(v).strip():
                            owner_name = str(v).strip()
                if not owner_name:
                    owner_name = owner_id

                contact_name = ""
                c = d.get("contact")
                if isinstance(c, dict):
                    contact_name = str(c.get("name") or "").strip()

                opp_id = str(d.get("id") or s.id)

                opp_rows.append(
                    {
                        "dt_utc": dt_utc,
                        "setter": setter_last,
                        "dispo": dispo,
                        "disposition_notes": disposition_notes,
                        "contact": contact_name,
                        "owner": owner_name,
                        "pipeline": pipeline_name,
                        "pipeline_stage": stage_name,
                        "opp_id": opp_id,
                    }
                )

            opp_rows.sort(key=lambda r: r["dt_utc"], reverse=True)

            opts = sorted({(r.get("setter") or "").strip() for r in opp_rows if (r.get("setter") or "").strip()})
            setter_options = opts

            body = []
            for r in opp_rows:
                body.append(
                    "<tr>"
                    f"<td>{escape(format_local(r.get('dt_utc')))}</td>"
                    f"<td>{escape((r.get('setter') or ''))}</td>"
                    f"<td>{escape((r.get('dispo') or ''))}</td>"
                    f"<td>{escape((r.get('disposition_notes') or ''))}</td>"
                    f"<td>{escape((r.get('contact') or ''))}</td>"
                    f"<td>{escape((r.get('owner') or ''))}</td>"
                    f"<td>{escape((r.get('pipeline') or ''))}</td>"
                    f"<td>{escape((r.get('pipeline_stage') or ''))}</td>"
                    f"<td class='right'>{escape((r.get('opp_id') or ''))}</td>"
                    "</tr>"
                )
            rows_html = "\n".join(body)

        except Exception as e:
            rows_html = f"<tr><td class='empty' colspan='9'>Error: {escape(str(e))}</td></tr>"

        subtitle_window = f"{start_local.strftime('%Y-%m-%d')} to {end_local.strftime('%Y-%m-%d')}"
        html = render_page(
            start_date=start_local.strftime("%Y-%m-%d"),
            end_date=end_local.strftime("%Y-%m-%d"),
            selected_setter=selected_setter,
            setter_options=setter_options,
            rows_html=rows_html,
            subtitle_window=subtitle_window,
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
