# -*- coding: utf-8 -*-

"""Vercel Python function: /api/buffalo_overrides

Buffalo Overrides Dashboard.

Shows every sold opportunity from the Buffalo pipeline with:
  Sales Rep, Setter Last Name, System Size, PPW Sold, Finance Product, Override, Sold Date

Date filter: sold date month (America/New_York).
Override persistence: stored per month in Firestore collection `buffalo_overrides_monthly`.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account


BUFFALO_SOLD_STAGE_IDS = {
    "7981f111-73f2-4593-9662-6b95d99bf51a",
    "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
}

SOLD_DATE_CF_ID = "P9oBjgbZjJdeE0OkBj9T"
SETTER_CF_ID = "Eq4NLTSkJ56KTxbxypuE"
LEAD_GEN_SOURCE_CF_ID = "hd5QqHEOVSsPom5bJ32P"
DEFAULT_OVERRIDE_RATE = 0.05
DASHBOARD_PASSWORD = "Buffalo123$"
AUTH_COOKIE_NAME = "buffalo_auth"
AUTH_COOKIE_VALUE = "ok"


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def clamp_override(v: Any, fallback: float = DEFAULT_OVERRIDE_RATE) -> float:
    try:
        x = round(float(v), 2)
    except Exception:
        x = fallback
    if x < 0.01:
        x = 0.01
    if x > 0.10:
        x = 0.10
    return round(x, 2)


def parse_num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-", "-."):
        return None
    try:
        return float(s)
    except Exception:
        return None


def cf_value(custom_fields: list[dict] | None, field_id: str) -> str | None:
    for cf in custom_fields or []:
        if isinstance(cf, dict) and str(cf.get("id") or "") == field_id:
            v = cf.get("value")
            if v not in (None, ""):
                return str(v).strip()
    return None


def h(s: Any) -> str:
    t = "" if s is None else str(s)
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("&#39;", "&apos;")


def contact_name(contact: dict[str, Any]) -> str:
    fn = str(contact.get("firstName") or "").strip()
    ln = str(contact.get("lastName") or "").strip()
    nm = str(contact.get("name") or "").strip()
    full = (fn + " " + ln).strip()
    return full or nm or "—"


def is_authenticated(cookie_header: str | None) -> bool:
    if not cookie_header:
        return False
    c = SimpleCookie()
    c.load(cookie_header)
    morsel = c.get(AUTH_COOKIE_NAME)
    if not morsel:
        return False
    return str(morsel.value) == AUTH_COOKIE_VALUE


def render_login_page(error: str = "") -> str:
    err = f"<div style='color:#b91c1c;font-size:13px;font-weight:800;margin-top:8px;'>{h(error)}</div>" if error else ""
    return """<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Buffalo Overrides - Login</title>
  <style>
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f7fa; }
    .card { max-width:420px; margin:10vh auto; background:#fff; border:1px solid #e8ecf0; border-radius:14px; padding:20px; box-shadow:0 1px 3px rgba(17,24,39,.08); }
    .title { font-size:22px; font-weight:950; color:#1a2b4a; }
    .sub { margin-top:4px; color:#6b7280; font-size:13px; }
    .pinkline { height:3px; width:180px; border-radius:999px; background:linear-gradient(90deg,#ec4899 0%,#f472b6 45%,rgba(244,114,182,0) 100%); margin-top:10px; }
    label { display:block; margin-top:14px; font-size:12px; color:#6b7280; font-weight:900; }
    input { width:100%; margin-top:4px; border:1px solid #e8ecf0; border-radius:10px; padding:10px 12px; font-size:14px; }
    button { margin-top:12px; width:100%; border:1px solid #ec4899; background:#ec4899; color:#fff; border-radius:10px; padding:10px 12px; font-size:14px; font-weight:900; cursor:pointer; }
  </style>
</head>
<body>
  <div class='card'>
    <div class='title'>Buffalo Overrides</div>
    <div class='sub'>Password required</div>
    <div class='pinkline'></div>
    <form method='POST'>
      <input type='hidden' name='action' value='login' />
      <label>Password
        <input type='password' name='password' autocomplete='current-password' required />
      </label>
      <button type='submit'>Unlock Dashboard</button>
      """ + err + """
    </form>
  </div>
</body>
</html>"""


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def load_month_settings(db: firestore.Client, mkey: str) -> tuple[float, dict[str, float]]:
    snap = db.collection("buffalo_overrides_monthly").document(mkey).get()
    if not snap.exists:
        return DEFAULT_OVERRIDE_RATE, {}
    d = snap.to_dict() or {}
    default_override = clamp_override(d.get("default_override", DEFAULT_OVERRIDE_RATE), DEFAULT_OVERRIDE_RATE)
    raw = d.get("row_overrides") or {}
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            kk = str(k or "").strip()
            if not kk:
                continue
            out[kk] = clamp_override(v, default_override)
    return default_override, out


def save_month_default(db: firestore.Client, mkey: str, value: float) -> None:
    ref = db.collection("buffalo_overrides_monthly").document(mkey)
    ref.set(
        {
            "month": mkey,
            "default_override": clamp_override(value),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def save_row_overrides(db: firestore.Client, mkey: str, updates: dict[str, Any]) -> int:
    ref = db.collection("buffalo_overrides_monthly").document(mkey)
    snap = ref.get()
    cur = (snap.to_dict() or {}).get("row_overrides") if snap.exists else {}
    merged = dict(cur or {}) if isinstance(cur, dict) else {}

    n = 0
    for k, v in (updates or {}).items():
        kk = str(k or "").strip()
        if not kk:
            continue
        merged[kk] = clamp_override(v)
        n += 1

    ref.set(
        {
            "month": mkey,
            "default_override": (snap.to_dict() or {}).get("default_override", DEFAULT_OVERRIDE_RATE) if snap.exists else DEFAULT_OVERRIDE_RATE,
            "row_overrides": merged,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return n


CSS = """
    :root { --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --pink:#ec4899; --pink2:#f472b6; --shadow:0 1px 3px rgba(17,24,39,.06); }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1200px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:var(--shadow); }
    .title { font-size:22px; font-weight:950; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; }
    .pinkline { height:3px; width:240px; border-radius:999px; background:linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }
    .nav { margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; }
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(236,72,153,.10); border-color:rgba(236,72,153,.45); color:#b80b66; }
    .filters { display:flex; align-items:flex-end; gap:8px; flex-wrap:wrap; margin-top:14px; }
    .filters label { display:block; font-size:12px; color:var(--muted); font-weight:900; margin-bottom:4px; }
    .filters input[type=month], .filters input[type=number] { border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:800; background:#fff; }
    .btn { display:inline-flex; align-items:center; padding:8px 12px; border-radius:10px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:12px; font-weight:900; cursor:pointer; text-decoration:none; }
    .btn.pink { background:var(--pink); border-color:var(--pink); color:#fff; }
    .kpi-row { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; margin-top:14px; }
    .kpi { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:var(--shadow); }
    .kpi .label { font-size:12px; color:var(--muted); font-weight:900; }
    .kpi .value { font-size:30px; font-weight:950; margin-top:4px; }
    table { width:100%; border-collapse:collapse; margin-top:14px; background:var(--card); border-radius:14px; overflow:hidden; box-shadow:var(--shadow); }
    th, td { padding:11px 14px; text-align:left; font-size:13px; border-bottom:1px solid var(--border); }
    th { background:#f8fafc; color:var(--muted); font-weight:900; cursor:pointer; user-select:none; }
    th:hover { background:#f1f5f9; }
    th.sorted { color:var(--pink); }
    td { color:#0f172a; font-weight:800; }
    .contact-link { color:#0f172a; font-weight:900; text-decoration:none; }
    .contact-link:hover { color:var(--pink); text-decoration:underline; }
    tr:last-child td { border-bottom:none; }
    tr:hover td { background:#fafafa; }
    .wrap2 { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:var(--shadow); margin-top:14px; }
    .ovr { width:86px; border:1px solid var(--border); border-radius:8px; padding:6px 8px; font-size:13px; font-weight:800; }
    .toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }
    .status { font-size:12px; color:#64748b; font-weight:800; min-height:18px; }
    @media (max-width:780px) { .wrap { padding:12px; } .topbar { padding:12px; gap:10px; } .title { font-size:20px; } .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; -webkit-overflow-scrolling:touch; } .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; } }
"""


def th_col(key, label, sort_col, sort_dir):
    cls = "sorted" if sort_col == key else ""
    icon = " ▲" if sort_dir == "asc" and sort_col == key else (" ▼" if sort_col == key else "")
    return '<th class="' + cls + '" data-col="' + h(key) + '">' + h(label) + icon + '</th>'


def render_page(rows, totals, count, year, month, month_str, sort_col, sort_dir, default_override):
    month_name = datetime(year, month, 1).strftime("%B %Y")

    rows_html = ""
    for r in rows:
        opp_id = h(r.get("opp_id", ""))
        ov = f"{clamp_override(r.get('override', default_override), default_override):.2f}"
        contact_url = r.get("contact_url", "")
        contact_label = h(r.get("contact_name", "—"))
        contact_cell = (
            "<a class='contact-link' target='_blank' rel='noopener noreferrer' href='" + h(contact_url) + "'>" + contact_label + "</a>"
            if contact_url
            else contact_label
        )
        rows_html += (
            "<tr>"
            "<td>" + contact_cell + "</td>"
            "<td>" + h(r.get("sales_rep", "—")) + "</td>"
            "<td>" + h(r.get("setter", "—")) + "</td>"
            "<td>" + h(r.get("lead_source", "—")) + "</td>"
            "<td style='text-align:right; font-variant-numeric:tabular-nums;'>" + h(r.get("system_size", "—")) + "</td>"
            "<td style='text-align:right; font-variant-numeric:tabular-nums;'><input class='ovr' data-oppid='" + opp_id + "' data-size='" + h(r.get("system_size_num", "")) + "' type='number' min='0.01' max='0.10' step='0.01' value='" + ov + "' /></td>"
            "<td class='comm' data-oppid='" + opp_id + "' style='text-align:right; font-variant-numeric:tabular-nums;'>" + h(r.get("override_commission", "—")) + "</td>"
            "<td>" + h(r.get("sold_date", "—")) + "</td>"
            "</tr>"
        )

    if not rows_html:
        rows_html = '<tr><td colspan="8" style="text-align:center; color:#94a3b8; padding:24px;">No Buffalo sales found for this period</td></tr>'

    headers = (
        th_col("contact_name", "Contact Name", sort_col, sort_dir)
        + th_col("sales_rep", "Sales Rep", sort_col, sort_dir)
        + th_col("setter", "Setter", sort_col, sort_dir)
        + th_col("lead_source", "Lead Gen Source", sort_col, sort_dir)
        + th_col("system_size", "System Size (kW)", sort_col, sort_dir)
        + th_col("override", "Override", sort_col, sort_dir)
        + th_col("override_commission_num", "Override Commission ($)", sort_col, sort_dir)
        + th_col("sold_date", "Sold Date", sort_col, sort_dir)
    )

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Buffalo Overrides</title>
  <style>""" + CSS + """</style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Buffalo Overrides</div>
        <div class="subtitle">All sold opportunities from the Buffalo pipeline</div>
        <div class="pinkline"></div>
      </div>
      <form method="GET" class="filters" style="margin:0;">
        <label>Month
          <input type="month" name="month" value=""" + h(month_str) + """ />
        </label>
        <button class="btn pink" type="submit">Go</button>
        <a class="btn" href="/api/buffalo_overrides">Reset</a>
      </form>
    </div>

    <div class="kpi-row">
      <div class="kpi"><div class="label">Total Buffalo Sales</div><div class="value">""" + str(count) + """</div></div>
      <div class="kpi"><div class="label">Viewing Month</div><div class="value" style="font-size:18px;">""" + h(month_name) + """</div></div>
      <div class="kpi"><div class="label">Avg System Size (kW)</div><div class="value" style="font-size:22px;">""" + h(totals.get("avg_size", "—")) + """</div></div>
      <div class="kpi"><div class="label">Total Override Commission ($)</div><div id="kpiOverrideTotal" class="value" style="font-size:22px;">""" + h(totals.get("total_override_commission", "—")) + """</div></div>
    </div>

    <div class="wrap2">
      <div class="toolbar">
        <label style="font-size:12px; color:#6b7280; font-weight:900;">Default Override
          <input id="defaultOverride" type="number" min="0.01" max="0.10" step="0.01" value=""" + h(f"{default_override:.2f}") + """ class="ovr" />
        </label>
        <button class="btn" id="saveDefaultBtn" type="button">Save Default</button>
        <button class="btn" id="setAllBtn" type="button">Set All Rows To Value</button>
        <label style="font-size:12px; color:#6b7280; font-weight:900;">Lead Gen Source
          <select id="bulkLeadSource" class="ovr" style="width:150px;">
            <option value="">All Sources</option>
            <option value="Doors">Doors</option>
            <option value="Phones">Phones</option>
            <option value="3PL">3PL</option>
            <option value="Self Gen">Self Gen</option>
            <option value="none">none</option>
          </select>
        </label>
        <button class="btn" id="setBySourceBtn" type="button">Set Rows By Source</button>
        <button class="btn pink" id="saveRowsBtn" type="button">Save Row Edits</button>
        <span class="status" id="statusMsg"></span>
      </div>

      <table id="salesTable">
        <thead><tr>""" + headers + """</tr></thead>
        <tbody>""" + rows_html + """</tbody>
      </table>
    </div>
  </div>

  <a href="/api/settings#secret-lab" title="Secret Lab" style="position:fixed;right:12px;bottom:10px;z-index:9999;width:34px;height:34px;display:flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid #d1d5db;background:rgba(255,255,255,.38);color:#475569;text-decoration:none;font-size:16px;backdrop-filter:blur(2px);opacity:.35;">🧪</a>

  <script>
    (function() {
      var sc = '""" + h(sort_col) + """';
      var el = document.querySelector('[data-col="' + sc + '"]');
      if (el) el.classList.add('sorted');
      document.querySelectorAll('th[data-col]').forEach(function(th) {
        th.addEventListener('click', function() {
          var col = th.getAttribute('data-col');
          var params = new URLSearchParams(window.location.search);
          var cur = params.get('sort') || '';
          var dir = (cur === col) ? (params.get('dir') === 'asc' ? 'desc' : 'asc') : 'desc';
          params.set('sort', col);
          params.set('dir', dir);
          window.location.search = params.toString();
        });
      });

      var month = '""" + month_str + """';
      var statusEl = document.getElementById('statusMsg');
      function setStatus(msg, bad) {
        if (!statusEl) return;
        statusEl.textContent = msg || '';
        statusEl.style.color = bad ? '#b91c1c' : '#64748b';
      }
      function v(x) {
        var n = Number(x);
        if (!isFinite(n)) n = 0.05;
        if (n < 0.01) n = 0.01;
        if (n > 0.10) n = 0.10;
        return n.toFixed(2);
      }
      async function post(payload) {
        var r = await fetch('/api/buffalo_overrides', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        var j = await r.json();
        if (!r.ok || !j.ok) throw new Error((j && j.error) || ('HTTP ' + r.status));
        return j;
      }

      function recalcCommissions() {
        var total = 0;
        document.querySelectorAll('.ovr[data-oppid]').forEach(function(inp){
          var id = inp.getAttribute('data-oppid') || '';
          var size = Number(inp.getAttribute('data-size') || 0);
          var rate = Number(v(inp.value));
          var commRaw = isFinite(size) ? (size * rate) : 0;
          var comm = Number(commRaw.toFixed(2));
          total += comm;
          var cell = document.querySelector('.comm[data-oppid="' + id + '"]');
          if (cell) cell.textContent = '$' + comm.toFixed(2);
        });
        var kpi = document.getElementById('kpiOverrideTotal');
        if (kpi) kpi.textContent = '$' + total.toFixed(2);
      }

      var saveDefaultBtn = document.getElementById('saveDefaultBtn');
      var setAllBtn = document.getElementById('setAllBtn');
      var setBySourceBtn = document.getElementById('setBySourceBtn');
      var sourceEl = document.getElementById('bulkLeadSource');
      var saveRowsBtn = document.getElementById('saveRowsBtn');
      var defaultEl = document.getElementById('defaultOverride');

      if (saveDefaultBtn) saveDefaultBtn.addEventListener('click', async function() {
        try {
          setStatus('Saving default...');
          var x = v(defaultEl && defaultEl.value);
          if (defaultEl) defaultEl.value = x;
          await post({ action:'save_default', month:month, value:x });
          setStatus('Default override saved.');
        } catch (e) {
          setStatus('Save default failed: ' + e.message, true);
        }
      });

      if (setAllBtn) setAllBtn.addEventListener('click', function() {
        var x = v(defaultEl && defaultEl.value);
        if (defaultEl) defaultEl.value = x;
        document.querySelectorAll('.ovr[data-oppid]').forEach(function(inp){ inp.value = x; });
        recalcCommissions();
        setStatus('All visible rows set to ' + x + '. Click Save Row Edits.');
      });

      if (setBySourceBtn) setBySourceBtn.addEventListener('click', function() {
        var x = v(defaultEl && defaultEl.value);
        if (defaultEl) defaultEl.value = x;
        var wanted = String((sourceEl && sourceEl.value) || '').trim().toLowerCase();
        var touched = 0;
        document.querySelectorAll('#salesTable tbody tr').forEach(function(tr){
          var tdSource = tr.children && tr.children[3] ? String(tr.children[3].textContent || '').trim().toLowerCase() : '';
          if (!wanted || tdSource === wanted) {
            var inp = tr.querySelector('.ovr[data-oppid]');
            if (inp) {
              inp.value = x;
              touched += 1;
            }
          }
        });
        recalcCommissions();
        setStatus('Set ' + touched + ' row(s) to ' + x + (wanted ? (' for source ' + wanted) : '') + '. Click Save Row Edits.');
      });

      document.querySelectorAll('.ovr[data-oppid]').forEach(function(inp){
        inp.addEventListener('input', recalcCommissions);
      });
      recalcCommissions();

      if (saveRowsBtn) saveRowsBtn.addEventListener('click', async function() {
        try {
          setStatus('Saving row edits...');
          var payload = {};
          document.querySelectorAll('.ovr[data-oppid]').forEach(function(inp){
            var id = inp.getAttribute('data-oppid') || '';
            if (!id) return;
            payload[id] = v(inp.value);
          });
          var res = await post({ action:'save_rows', month:month, overrides:payload });
          setStatus('Saved ' + (res.updated || 0) + ' row override(s).');
        } catch (e) {
          setStatus('Save rows failed: ' + e.message, true);
        }
      });
    })();
  </script>
</body>
</html>"""


def build_data(db, year, month, default_override, row_overrides, sort_col="sold_date", sort_dir="desc"):
    tz = ZoneInfo("America/New_York")
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)

    contacts_map = {}
    for snap in db.collection("ghl_contacts_v2").stream():
        d = snap.to_dict() or {}
        cid = str(d.get("id") or snap.id).strip()
        if cid:
            contacts_map[cid] = d

    user_cache = {}
    for snap in db.collection("ghl_users_v2").stream():
        d = snap.to_dict() or {}
        uid = str(d.get("id") or snap.id).strip()
        name = d.get("name")
        if not name:
            fn = d.get("firstName") or ""
            ln = d.get("lastName") or ""
            name = (fn + " " + ln).strip() or None
        if uid and name:
            user_cache[uid] = name

    rows = []
    for snap in db.collection("ghl_opportunities_v2").stream():
        opp = snap.to_dict() or {}
        stage_id = str(opp.get("pipelineStageId") or "")
        if stage_id not in BUFFALO_SOLD_STAGE_IDS:
            continue

        opp_id = str(opp.get("id") or snap.id or "").strip()
        if not opp_id:
            continue

        contact_id = str(opp.get("contactId") or "").strip()
        contact = contacts_map.get(contact_id) or {}
        sold_date = cf_value(contact.get("customFields"), SOLD_DATE_CF_ID)
        if not sold_date:
            continue
        try:
            sd = datetime.strptime(sold_date[:10], "%Y-%m-%d").replace(tzinfo=tz)
            if not (start <= sd < end):
                continue
        except Exception:
            continue

        owner_id = str(opp.get("assignedTo") or "").strip()
        setter = cf_value(contact.get("customFields"), SETTER_CF_ID) or "—"
        loc_id = str(opp.get("locationId") or os.environ.get("GHL_LOCATION_ID") or "").strip()
        contact_url = f"https://app.gohighlevel.com/v2/location/{loc_id}/contacts/detail/{contact_id}" if (loc_id and contact_id) else ""
        lead_source = cf_value(contact.get("customFields"), LEAD_GEN_SOURCE_CF_ID) or contact.get("leadSource") or "—"
        system_size = contact.get("system_size") or "—"
        ppw_sold = contact.get("ppw_sold") or "—"
        sales_rep = user_cache.get(owner_id) or owner_id or "—"
        if str(sales_rep).strip().lower() == "brooke simpson":
            continue
        override_rate = clamp_override(row_overrides.get(opp_id, default_override), default_override)
        size_num = parse_num(system_size)
        comm_num = (size_num or 0.0) * override_rate

        rows.append(
            {
                "opp_id": opp_id,
                "contact_name": contact_name(contact),
                "contact_url": contact_url,
                "sales_rep": sales_rep,
                "setter": setter,
                "lead_source": lead_source,
                "system_size": system_size,
                "system_size_num": f"{size_num:.4f}" if size_num is not None else "",
                "override": f"{override_rate:.2f}",
                "override_commission_num": round(comm_num, 2),
                "override_commission": f"${comm_num:.2f}",
                "sold_date": sold_date[:10],
            }
        )

    rev = sort_dir == "desc"

    def sort_key(r):
        v = r.get(sort_col, "")
        try:
            return float(v)
        except Exception:
            return str(v).lower()

    rows.sort(key=sort_key, reverse=rev)

    size_vals = []
    total_override_commission = 0.0
    for r in rows:
        try:
            size_vals.append(float(str(r.get("system_size", "")).strip()))
        except Exception:
            pass
        try:
            total_override_commission += float(r.get("override_commission_num") or 0)
        except Exception:
            pass

    totals = {
        "avg_size": f"{(sum(size_vals) / len(size_vals)):.2f}" if size_vals else "—",
        "total_override_commission": f"${total_override_commission:.2f}",
    }

    return rows, totals


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not is_authenticated(self.headers.get("Cookie")):
                body = render_login_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            tz = ZoneInfo("America/New_York")
            now = datetime.now(tz)
            qs = parse_qs(urlparse(self.path).query)

            month_raw = qs.get("month", [""])[0].strip()
            if month_raw and "-" in month_raw:
                try:
                    y = int(month_raw.split("-")[0])
                    m = int(month_raw.split("-")[1])
                except Exception:
                    y, m = now.year, now.month
            else:
                y, m = now.year, now.month

            sort_col = qs.get("sort", ["sold_date"])[0].strip() or "sold_date"
            sort_dir = qs.get("dir", ["desc"])[0].strip() or "desc"
            if sort_col not in ("contact_name", "sales_rep", "setter", "lead_source", "system_size", "override", "override_commission_num", "sold_date"):
                sort_col = "sold_date"
            if sort_dir not in ("asc", "desc"):
                sort_dir = "desc"

            db = get_db()
            mkey = month_key(y, m)
            default_override, row_overrides = load_month_settings(db, mkey)

            rows, totals = build_data(db, y, m, default_override, row_overrides, sort_col, sort_dir)
            month_str = f"{y}-{m:02d}"
            body = render_page(rows, totals, len(rows), y, m, month_str, sort_col, sort_dir, default_override).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception:
            import traceback

            err = traceback.format_exc()
            body = ("<html><body><h1>Error</h1><pre>" + h(str(err)) + "\n\n" + h(err) + "</pre></body></html>").encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            ctype = (self.headers.get("Content-Type") or "").lower()

            if "application/x-www-form-urlencoded" in ctype:
                form = parse_qs(raw.decode("utf-8", errors="ignore"))
                action = (form.get("action", [""])[0] or "").strip()
                if action == "login":
                    pw = (form.get("password", [""])[0] or "")
                    if pw == DASHBOARD_PASSWORD:
                        self.send_response(302)
                        self.send_header("Set-Cookie", f"{AUTH_COOKIE_NAME}={AUTH_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax")
                        self.send_header("Location", "/api/buffalo_overrides")
                        self.end_headers()
                        return
                    body = render_login_page("Invalid password").encode("utf-8")
                    self.send_response(401)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            if not is_authenticated(self.headers.get("Cookie")):
                body = json.dumps({"ok": False, "error": "Unauthorized"}).encode("utf-8")
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            payload = json.loads(raw.decode("utf-8") or "{}")
            action = str(payload.get("action") or "").strip()
            mkey = str(payload.get("month") or "").strip()
            if not mkey or len(mkey) != 7 or "-" not in mkey:
                raise ValueError("Invalid month (expected YYYY-MM)")

            db = get_db()

            if action == "save_default":
                value = clamp_override(payload.get("value", DEFAULT_OVERRIDE_RATE), DEFAULT_OVERRIDE_RATE)
                save_month_default(db, mkey, value)
                out = {"ok": True, "action": action, "month": mkey, "value": f"{value:.2f}"}

            elif action == "save_rows":
                updates = payload.get("overrides") or {}
                if not isinstance(updates, dict):
                    raise ValueError("overrides must be an object")
                n = save_row_overrides(db, mkey, updates)
                out = {"ok": True, "action": action, "month": mkey, "updated": n}

            else:
                raise ValueError("Unsupported action")

            body = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
