# -*- coding: utf-8 -*-

"""Vercel Python function: /api/buffalo_overrides

Buffalo Overrides Dashboard.

Shows every sold opportunity from the Buffalo pipeline with:
  Sales Rep, Setter Last Name, System Size, PPW Sold, Finance Product, Sold Date

Date filter: sold date, defaults to current month (America/New_York).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
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


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON","GCP_PROJECT_ID","FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def cf_value(custom_fields: list[dict] | None, field_id: str) -> str | None:
    for cf in custom_fields or []:
        if isinstance(cf, dict) and str(cf.get("id") or "") == field_id:
            v = cf.get("value")
            if v not in (None, ""):
                return str(v).strip()
    return None


def h(s: Any) -> str:
    t = "" if s is None else str(s)
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("&#39;","&apos;")


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
    .filters input[type=month] { border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:800; background:#fff; }
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
    tr:last-child td { border-bottom:none; }
    tr:hover td { background:#fafafa; }
    .wrap2 { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:var(--shadow); margin-top:14px; }
    @media (max-width:780px) { .wrap { padding:12px; } .topbar { padding:12px; gap:10px; } .title { font-size:20px; } .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; -webkit-overflow-scrolling:touch; } .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; } }
"""


def th_col(key, label, sort_col, sort_dir):
    cls = "sorted" if sort_col == key else ""
    icon = " ▲" if sort_dir == "asc" and sort_col == key else (" ▼" if sort_col == key else "")
    return '<th class="' + cls + '" data-col="' + h(key) + '">' + h(label) + icon + '</th>'


def render_page(rows, totals, count, year, month, month_str, sort_col, sort_dir):
    month_name = datetime(year, month, 1).strftime("%B %Y")

    rows_html = ""
    for r in rows:
        rows_html += (
            "<tr>"
            "<td>" + h(r.get("sales_rep","—")) + "</td>"
            "<td>" + h(r.get("setter","—")) + "</td>"
            "<td style='text-align:right; font-variant-numeric:tabular-nums;'>" + h(r.get("system_size","—")) + "</td>"
            "<td style='text-align:right; font-variant-numeric:tabular-nums;'>" + h(r.get("ppw_sold","—")) + "</td>"
            "<td>" + h(r.get("finance_type","—")) + "</td>"
            "<td>" + h(r.get("sold_date","—")) + "</td>"
            "</tr>"
        )

    if not rows_html:
        rows_html = '<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding:24px;">No Buffalo sales found for this period</td></tr>'

    headers = (
        th_col("sales_rep","Sales Rep",sort_col,sort_dir) +
        th_col("setter","Setter",sort_col,sort_dir) +
        th_col("system_size","System Size (kW)",sort_col,sort_dir) +
        th_col("ppw_sold","PPW Sold ($)",sort_col,sort_dir) +
        th_col("finance_type","Finance Product",sort_col,sort_dir) +
        th_col("sold_date","Sold Date",sort_col,sort_dir)
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
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company Overview</a>
          <a class="navbtn" href="/api/settings">Admin</a>
          <a class="navbtn active" href="/api/buffalo_overrides">Buffalo Overrides</a>
          <a class="navbtn" href="/api/fma_dashboard">FMA Dashboard</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales Dashboard</a>
        </div>
      </div>
      <form method="GET" class="filters" style="margin:0;">
        <label>Month
          <input type="month" name="month" value="""" + month_str + """" />
        </label>
        <button class="btn pink" type="submit">Go</button>
        <a class="btn" href="/api/buffalo_overrides">Reset</a>
      </form>
    </div>

    <div class="kpi-row">
      <div class="kpi"><div class="label">Total Buffalo Sales</div><div class="value">""" + str(count) + """</div></div>
      <div class="kpi"><div class="label">Period</div><div class="value" style="font-size:18px;">""" + h(month_name) + """</div></div>
      <div class="kpi"><div class="label">Avg System Size (kW)</div><div class="value" style="font-size:22px;">""" + h(totals.get("avg_size","—")) + """</div></div>
      <div class="kpi"><div class="label">Avg PPW Sold ($)</div><div class="value" style="font-size:22px;">""" + h(totals.get("avg_ppw","—")) + """</div></div>
    </div>

    <div class="wrap2">
      <table id="salesTable">
        <thead>
          <tr>""" + headers + """</tr>
        </thead>
        <tbody>
          """ + rows_html + """
        </tbody>
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
    })();
  </script>
</body>
</html>"""


def build_data(db, year, month, sort_col="sold_date", sort_dir="desc"):
    tz = ZoneInfo("America/New_York")
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)

    # Preload contacts
    contacts_map: dict[str, dict] = {}
    for snap in db.collection("ghl_contacts_v2").stream():
        d = snap.to_dict() or {}
        cid = str(d.get("id") or snap.id).strip()
        if cid:
            contacts_map[cid] = d

    # Preload users
    user_cache: dict[str, str] = {}
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
    debug_counts = {"stage_skip": 0, "no_contact": 0, "no_date": 0, "wrong_month": 0, "added": 0}
    for snap in db.collection("ghl_opportunities_v2").stream():
        opp = snap.to_dict() or {}
        stage_id = str(opp.get("pipelineStageId") or "")
        if stage_id not in BUFFALO_SOLD_STAGE_IDS:
            debug_counts["stage_skip"] += 1
            continue

        contact = contacts_map.get(str(opp.get("contactId") or "").strip()) or {}
        if not contact:
            debug_counts["no_contact"] += 1

        sold_date = cf_value(contact.get("customFields"), SOLD_DATE_CF_ID) if contact else None
        if not sold_date:
            debug_counts["no_date"] += 1
            continue
        try:
            sd = datetime.strptime(sold_date[:10], "%Y-%m-%d").replace(tzinfo=tz)
            if not (start <= sd < end):
                debug_counts["wrong_month"] += 1
                continue
        except Exception:
            continue

        debug_counts["added"] += 1
        owner_id = str(opp.get("assignedTo") or "").strip()
        setter = cf_value(contact.get("customFields"), SETTER_CF_ID) or "—"
        system_size = contact.get("system_size")
        ppw_sold = contact.get("ppw_sold")
        finance_type = contact.get("finance_type")

        rows.append({
            "sales_rep": user_cache.get(owner_id) or owner_id or "—",
            "setter": setter,
            "system_size": system_size if system_size not in (None, "") else "—",
            "ppw_sold": ppw_sold if ppw_sold not in (None, "") else "—",
            "finance_type": finance_type if finance_type not in (None, "") else "—",
            "sold_date": sold_date[:10],
        })

    # Sort
    rev = sort_dir == "desc"
    def sort_key(r):
        v = r.get(sort_col, "")
        try:
            return float(v)
        except Exception:
            return str(v).lower()
    rows.sort(key=sort_key, reverse=rev)

    # Totals
    sizes = [float(r["system_size"]) for r in rows if r["system_size"] not in ("—", None, "")]
    ppws = [float(r["ppw_sold"].replace("$","")) for r in rows if r["ppw_sold"] not in ("—", None, "") and r["ppw_sold"] is not None]
    totals = {
        "avg_size": f"{sum(sizes)/len(sizes):.1f}" if sizes else "—",
        "avg_ppw": f"${sum(ppws)/len(ppws):.2f}" if ppws else "—",
    }

    return rows, totals, debug_counts


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
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
            if sort_col not in ("sales_rep","setter","system_size","ppw_sold","finance_type","sold_date"):
                sort_col = "sold_date"
            if sort_dir not in ("asc","desc"):
                sort_dir = "desc"

            db = get_db()

            # Debug mode: show detailed diagnostics
            if qs.get("debug", [""])[0].strip() == "1":
                stage_ids = BUFFALO_SOLD_STAGE_IDS
                sold_date_cf = SOLD_DATE_CF_ID
                tz = ZoneInfo("America/New_York")
                if m == 12:
                    end = datetime(y+1, 1, 1, 0, 0, 0, tzinfo=tz)
                else:
                    end = datetime(y, m+1, 1, 0, 0, 0, tzinfo=tz)
                start_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=tz)
                
                # Preload contacts
                contacts_map = {}
                for snap in db.collection("ghl_contacts_v2").stream():
                    d = snap.to_dict() or {}
                    cid = str(d.get("id") or snap.id).strip()
                    if cid:
                        contacts_map[cid] = d
                
                found = 0
                null_date = 0
                wrong_month = 0
                no_contact = 0
                sample = []
                for si, s in enumerate(db.collection("ghl_opportunities_v2").stream()):
                    opp = s.to_dict() or {}
                    if str(opp.get("pipelineStageId") or "") not in stage_ids: continue
                    cid = str(opp.get("contactId") or "").strip()
                    contact = contacts_map.get(cid)
                    if not contact:
                        no_contact += 1
                        continue
                    sold = None
                    for cf in (contact.get("customFields") or []):
                        if str(cf.get("id") or "") == sold_date_cf:
                            sold = str(cf.get("value") or "")[:10]
                    if sold is None:
                        null_date += 1
                        continue
                    try:
                        sd = datetime.strptime(sold, "%Y-%m-%d").replace(tzinfo=tz)
                        if not (start_dt <= sd < end):
                            wrong_month += 1
                            continue
                    except:
                        continue
                    found += 1
                    if len(sample) < 5:
                        opp_cfs = opp.get("customFields") or []
                        opp_top_keys = [k for k in opp.keys() if k not in ("id","contactId","customFields")]
                        sample.append({
                            "opp_id": s.id, "contact_id": cid,
                            "sold_date": sold,
                            "contact_system_size": contact.get("system_size"),
                            "opp_top_keys": opp_top_keys,
                            "opp_cfs": [{"id": cf.get("id"), "name": cf.get("fieldName"), "val": str(cf.get("value","") or "")[:50]} for cf in opp_cfs[:10]]
                        })
                
                body = json.dumps({
                    "debug": True,
                    "month": f"{y}-{m:02d}",
                    "window_start": start_dt.isoformat(),
                    "window_end": end.isoformat(),
                    "opps_matching_stage": found,
                    "null_date": null_date,
                    "wrong_month": wrong_month,
                    "no_contact_found": no_contact,
                    "sample": sample
                }, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            rows, totals, dbg = build_data(db, y, m, sort_col, sort_dir)
            if qs.get('debug2', [''])[0].strip() == '1':
                body = json.dumps({'dbg': dbg, 'len_rows': len(rows)}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            rows, totals, _
            month_str = f"{y}-{m:02d}"

            body = render_page(rows, totals, len(rows), y, m, month_str, sort_col, sort_dir).encode("utf-8")

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
