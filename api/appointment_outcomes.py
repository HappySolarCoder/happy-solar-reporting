# -*- coding: utf-8 -*-

"""Vercel Python function: /api/appointment_outcomes

Appointment Outcomes dashboard
- List of appointments that have been dispositioned
- Filters: view + Setter Last Name + Sales Rep + date range
- Default: yesterday
- Date filtering field: appointment date/time (appointmentStartTime)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from google.cloud import firestore
from google.oauth2 import service_account
from dashboard_nav import dashboard_nav_css, render_dashboard_nav

TZ = ZoneInfo("America/New_York")
SETTER_LAST_NAME_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"
DISPOSITION_NOTES_FIELD_ID = "cCcnzoIp8YgW2Pr0sB5E"  # GHL custom field: Disposition Notes
OWNER_NAME_OVERRIDES = {
    "0fhsjcmlntce0cpjyfhj": "William Breen",
}


def compact_str(value) -> str:
    return " ".join(str(value or "").strip().split())


def looks_like_identifier(value) -> bool:
    text = compact_str(value)
    if not text or " " in text or len(text) < 12:
        return False
    return all(ch.isalnum() or ch in {"-", "_"} for ch in text)


def best_person_name(record, *, fallback: str = "") -> str:
    if not isinstance(record, dict):
        return fallback
    candidates = [
        record.get("name"),
        record.get("displayName"),
        record.get("fullName"),
        " ".join(part for part in (compact_str(record.get("firstName")), compact_str(record.get("lastName"))) if part),
        record.get("firstName"),
        record.get("lastName"),
        record.get("userName"),
    ]
    for candidate in candidates:
        text = compact_str(candidate)
        if text and not looks_like_identifier(text):
            return text
    return fallback


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
        name = best_person_name(d)
        for key in {compact_str(d.get("id")), compact_str(d.get("userId")), compact_str(snap.id)}:
            if key and name:
                out[key] = name
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


def view_copy(view: str) -> tuple[str, str]:
    normalized = (view or "outcomes").strip().lower()
    if normalized == "upcoming":
        return ("Upcoming Appointments", "Upcoming appointments list")
    if normalized == "all":
        return ("Appointment Outcomes + Upcoming", "Dispositioned and upcoming appointments")
    return ("Appointment Outcomes", "Dispositioned appointments list")


def render_page(
    *,
    selected_view: str,
    start_date: str,
    end_date: str,
    selected_setter: str,
    setter_options: list[str],
    selected_owner: str,
    owner_options: list[str],
    rows_html: str,
    subtitle_window: str,
    empty_state: str,
) -> str:
    normalized_view = (selected_view or "outcomes").strip().lower()
    view_options = [
        ("outcomes", "Outcomes Only"),
        ("upcoming", "Upcoming Only"),
        ("all", "Outcomes + Upcoming"),
    ]
    options_html = ['<option value="">All setters</option>']
    for s in setter_options:
        sel = " selected" if s == selected_setter else ""
        options_html.append(f'<option value="{escape(s)}"{sel}>{escape(s)}</option>')

    owner_options_html = ['<option value="">All sales reps</option>']
    for owner in owner_options:
        sel = " selected" if owner == selected_owner else ""
        owner_options_html.append(f'<option value="{escape(owner)}"{sel}>{escape(owner)}</option>')

    title_text, subtitle_prefix = view_copy(normalized_view)
    view_options_html = []
    for value, label in view_options:
        sel = " selected" if value == normalized_view else ""
        view_options_html.append(f'<option value="{escape(value)}"{sel}>{escape(label)}</option>')

    nav_html = render_dashboard_nav("appointment_outcomes")
    return (
        f"""<!doctype html>
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
    .topbarMain {{ min-width:0; flex:1 1 420px; }}
    .title {{ font-size:22px; font-weight:950; color:#1a2b4a; letter-spacing:-0.02em; }}
    .subtitle {{ margin-top:4px; color:var(--muted); font-size:13px; }}
    .pinkline {{ height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }}
    .brandCenter {{ position:absolute; left:50%; top:12px; transform:translateX(-50%); pointer-events:none; }}
    .brandCenter img {{ height:56px; width:auto; }}
__DASHBOARD_NAV_CSS__
    .navbtn {{ display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }}
    .navbtn.active {{ background:rgba(236,72,153,0.10); border-color:rgba(236,72,153,0.45); color:#b80b66; }}
    .adminSettings {{ position:absolute; top:16px; right:18px; }}
    .dashboardSwitch {{ margin-top:12px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
    .dashboardSwitch label {{ font-size:12px; font-weight:900; color:var(--muted); text-transform:uppercase; letter-spacing:0.04em; }}
    .dashboardSwitch select {{ min-width:240px; border:1px solid var(--border); border-radius:12px; background:#fff; color:#1f2937; padding:10px 12px; font-size:13px; font-weight:800; box-shadow:0 1px 3px rgba(17,24,39,0.06); }}

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
      .topbarMain {{ flex-basis:100%; width:100%; }}
      .dashboardSwitch {{ width:100%; align-items:stretch; gap:6px; }}
      .dashboardSwitch label {{ width:100%; }}
      .dashboardSwitch select {{ width:100%; min-width:0; }}
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div class=\"topbarMain\">
        <div class=\"title\">{escape(title_text)}</div>
        <div class=\"subtitle\">{escape(subtitle_prefix)} ({escape(subtitle_window)})</div>
        <div class=\"pinkline\"></div>
__DASHBOARD_NAV_HTML__
        <div class=\"dashboardSwitch\">
          <label for=\"fmaViewSelect\">FMA View</label>
          <select id=\"fmaViewSelect\" onchange=\"if (this.value) window.location.href = this.value;\">
            <option value=\"/api/fma_dashboard\">FMA Dashboard</option>
            <option value=\"/api/appointment_outcomes\" selected>Appointment Outcomes</option>
            <option value=\"/api/fma_commissions\">Commission Tracker</option>
          </select>
        </div>
      </div>

      <div class=\"brandCenter\"><img src=\"https://assets.zyrosite.com/cdn-cgi/image/format=auto,w=180,fit=crop,q=95/Aq2VyN6Nz4fD9PjZ/happy-solar-logo-m2W4o75D7Ks9NQj0.png\" alt=\"Happy Solar\" /></div>

      <div class=\"adminSettings\">
        <a class=\"navbtn\" href=\"/api/settings\">Admin Settings</a>
      </div>

    </div>

    <div class=\"panel\">
      <form class=\"filters\" method=\"get\" action=\"/api/appointment_outcomes\">
        <div>
          <label for=\"view\">View</label><br />
          <select class=\"select\" id=\"view\" name=\"view\">{''.join(view_options_html)}</select>
        </div>
        <div>
          <label for=\"setter_last_name\">Setter Last Name</label><br />
          <select class=\"select\" id=\"setter_last_name\" name=\"setter_last_name\">{''.join(options_html)}</select>
        </div>
        <div>
          <label for=\"owner_name\">Sales Rep (Owner)</label><br />
          <select class=\"select\" id=\"owner_name\" name=\"owner_name\">{''.join(owner_options_html)}</select>
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
        <button class=\"btn\" type=\"button\" id=\"next7Btn\">Next 7 Days</button>
      </form>
    </div>

    <div class=\"panel\" style=\"padding:0; overflow:hidden;\">
      <table>
        <thead>
          <tr>
            <th>Appointment Date & Time</th>
            <th>Setter Last Name</th>
            <th>Outcome / Status</th>
            <th>Disposition Notes</th>
            <th>Contact</th>
            <th>Owner</th>
            <th>Pipeline</th>
            <th>Pipeline Stage</th>
            <th class=\"right\">Opportunity ID</th>
          </tr>
        </thead>
        <tbody>
          {rows_html if rows_html else f'<tr><td class="empty" colspan="9">{escape(empty_state)}</td></tr>'}
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
    const nBtn = document.getElementById('next7Btn');
    if (nBtn) {{
      nBtn.addEventListener('click', () => {{
        const now = new Date();
        const end = new Date(now);
        end.setDate(end.getDate() + 7);
        document.getElementById('start_date').value = now.toISOString().slice(0,10);
        document.getElementById('end_date').value = end.toISOString().slice(0,10);
        const view = document.getElementById('view');
        if (view) view.value = 'upcoming';
      }});
    }}
  </script>
</body>
</html>
"""
        .replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css())
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs((self.path.split("?", 1)[1] if "?" in self.path else ""), keep_blank_values=True)

        today_local = datetime.now(TZ).date()
        yday = today_local - timedelta(days=1)
        now_utc = datetime.now(timezone.utc)

        start_raw = (qs.get("start_date", [""])[0] or "").strip()
        end_raw = (qs.get("end_date", [""])[0] or "").strip()
        selected_view = (qs.get("view", ["outcomes"])[0] or "outcomes").strip().lower()
        if selected_view not in {"outcomes", "upcoming", "all"}:
            selected_view = "outcomes"

        default_start = datetime(yday.year, yday.month, yday.day)
        default_end = datetime(yday.year, yday.month, yday.day)
        if selected_view == "upcoming":
            default_start = datetime(today_local.year, today_local.month, today_local.day)
            default_end = default_start + timedelta(days=7)

        start_dt = parse_ymd(start_raw) or default_start
        end_dt = parse_ymd(end_raw) or default_end
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        start_local = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, tzinfo=TZ)
        end_local = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, 999999, tzinfo=TZ)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        selected_setter = (qs.get("setter_last_name", [""])[0] or "").strip()
        selected_owner = (qs.get("owner_name", [""])[0] or "").strip()

        rows_html = ""
        setter_options: list[str] = []
        owner_options: list[str] = []

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
                is_upcoming = dt_utc >= now_utc
                if selected_view == "outcomes" and not dispo:
                    continue
                if selected_view == "upcoming" and not is_upcoming:
                    continue
                if selected_view == "all" and not dispo and not is_upcoming:
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
                            text = compact_str(v)
                            if not looks_like_identifier(text):
                                owner_name = text
                                break
                if not owner_name:
                    au = d.get("assignedToUser")
                    if isinstance(au, dict):
                        owner_name = best_person_name(au)
                if not owner_name:
                    owner_name = f"Unknown User ({owner_id[-6:]})" if owner_id else "unassigned"

                contact_name = ""
                c = d.get("contact")
                if isinstance(c, dict):
                    contact_name = str(c.get("name") or "").strip()

                opp_id = str(d.get("id") or s.id)

                opp_rows.append(
                    {
                        "dt_utc": dt_utc,
                        "setter": setter_last,
                        "status": dispo or ("Upcoming" if is_upcoming else ""),
                        "disposition_notes": disposition_notes,
                        "contact": contact_name,
                        "owner": owner_name,
                        "pipeline": pipeline_name,
                        "pipeline_stage": stage_name,
                        "opp_id": opp_id,
                    }
                )

            opp_rows.sort(
                key=lambda r: r["dt_utc"],
                reverse=(selected_view == "outcomes"),
            )

            setter_options = sorted({(r.get("setter") or "").strip() for r in opp_rows if (r.get("setter") or "").strip()})
            owner_options = sorted({(r.get("owner") or "").strip() for r in opp_rows if (r.get("owner") or "").strip()})

            body = []
            for r in opp_rows:
                row_setter = (r.get("setter") or "").strip()
                row_owner = (r.get("owner") or "").strip()
                if selected_setter and row_setter.lower() != selected_setter.lower():
                    continue
                if selected_owner and row_owner.lower() != selected_owner.lower():
                    continue
                body.append(
                    "<tr>"
                    f"<td>{escape(format_local(r.get('dt_utc')))}</td>"
                    f"<td>{escape((r.get('setter') or ''))}</td>"
                    f"<td>{escape((r.get('status') or ''))}</td>"
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
        empty_state = {
            "upcoming": "No upcoming appointments in this window.",
            "all": "No dispositioned or upcoming appointments in this window.",
        }.get(selected_view, "No dispositioned appointments in this window.")
        html = render_page(
            selected_view=selected_view,
            start_date=start_local.strftime("%Y-%m-%d"),
            end_date=end_local.strftime("%Y-%m-%d"),
            selected_setter=selected_setter,
            setter_options=setter_options,
            selected_owner=selected_owner,
            owner_options=owner_options,
            rows_html=rows_html,
            subtitle_window=subtitle_window,
            empty_state=empty_state,
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
