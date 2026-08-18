# -*- coding: utf-8 -*-

"""Vercel Python function: /api/essential_sales

This-month sales table using the Yadmada Job Tracker Essential tab columns.
Data: /api/metrics/essential_sales (locked Sales grain from sales.py).
"""

from __future__ import annotations

import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


def render_html(year: int, month: int) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("essential_sales")
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Essential Sales</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#00C853; --blue:#2196F3;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1600px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }
    .title { font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:820px; }
    .accentline { height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,var(--green) 0%, var(--blue) 55%, rgba(33,150,243,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(0,200,83,.10); border-color:rgba(0,200,83,.45); color:#0a7a34; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f2f5; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--green); border-color:var(--green); color:#fff; font-weight:900; cursor:pointer; }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); }
    .span-3 { grid-column:span 3; } .span-12 { grid-column:span 12; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:42px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .tableWrap { overflow:auto; max-height:70vh; border:1px solid var(--border); border-radius:12px; }
    table { width:100%; border-collapse:collapse; min-width:1400px; }
    th, td { border-bottom:1px solid var(--border); padding:9px 10px; text-align:left; font-size:13px; vertical-align:top; }
    th { color:#64748b; font-weight:900; background:#fafbfc; position:sticky; top:0; z-index:1; white-space:nowrap; }
    td.notes { max-width:280px; white-space:pre-wrap; word-break:break-word; }
    .jsonlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    @media (max-width:980px) { .span-3,.span-12 { grid-column:span 12; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:34px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Essential Sales</div>
        <div class="subtitle">This-month sales using the Yadmada Job Tracker Essential tab columns. Grain matches the locked Sales metric (distinct contact, Sold / Sale Cancelled). Installer is not filtered.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter"><div class="filter-label">Month</div><select id="month"></select></div>
        <button id="apply">Apply</button>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Sales</div>
        <div class="kpi" id="result">—</div>
        <div class="meta" id="windowMeta">Locked Sales grain</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Rows</div>
        <div class="kpi" id="rowCount">—</div>
        <div class="meta">Must equal Sales result</div>
      </div>
      <div class="card span-12">
        <div class="card-title">Essential tab</div>
        <div class="meta" style="margin-bottom:10px">Columns A–O. <a class="jsonlink" id="jsonLink" href="#">JSON</a></div>
        <div class="tableWrap"><table id="salesTable"></table></div>
      </div>
    </div>
  </div>
  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
<script>
var defaultYear = __YEAR__;
var defaultMonth = __MONTH__;
var yearSel = document.getElementById('year');
var monthSel = document.getElementById('month');
function setOptions(sel, options, value) {
  sel.innerHTML = '';
  options.forEach(function(opt) {
    var o = document.createElement('option');
    o.value = String(opt.value);
    o.textContent = opt.label;
    if (String(opt.value) === String(value)) o.selected = true;
    sel.appendChild(o);
  });
}
var years = [];
for (var y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
var months = [];
for (var i = 0; i < 12; i++) months.push({value: i + 1, label: new Date(2000, i, 1).toLocaleString('en-US', {month: 'long'})});
setOptions(yearSel, years, defaultYear);
setOptions(monthSel, months, defaultMonth);
function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function query() {
  return new URLSearchParams({ year: yearSel.value, month: monthSel.value }).toString();
}
function renderTable(el, columns, rows) {
  var html = '<thead><tr>';
  columns.forEach(function(c) { html += '<th>' + esc(c.label) + '</th>'; });
  html += '</tr></thead><tbody>';
  if (!rows || !rows.length) {
    html += '<tr><td colspan="' + columns.length + '">No sales in this window.</td></tr>';
  } else {
    rows.forEach(function(r) {
      html += '<tr>';
      columns.forEach(function(c) {
        var cls = c.key === 'notes' ? ' class="notes"' : '';
        html += '<td' + cls + '>' + esc(r[c.key]) + '</td>';
      });
      html += '</tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}
async function load() {
  var q = query();
  document.getElementById('jsonLink').href = '/api/metrics/essential_sales?' + q;
  var res = await fetch('/api/metrics/essential_sales?' + q);
  var data = await res.json();
  if (!res.ok) {
    document.getElementById('result').textContent = 'Error';
    document.getElementById('rowCount').textContent = '—';
    document.getElementById('windowMeta').textContent = data.error || 'Failed to load';
    return;
  }
  document.getElementById('result').textContent = String(data.result == null ? '—' : data.result);
  document.getElementById('rowCount').textContent = String((data.rows || []).length);
  var start = String(data.window_start_local || '').slice(0, 10);
  var end = String(data.window_end_local || '').slice(0, 10);
  document.getElementById('windowMeta').textContent = start + ' to ' + end + ' (' + (data.timezone || '') + ')';
  renderTable(document.getElementById('salesTable'), data.columns || [], data.rows || []);
}
document.getElementById('apply').addEventListener('click', load);
load();
</script>
</body>
</html>
"""
    return (
        html.replace("__YEAR__", str(year))
        .replace("__MONTH__", str(month))
        .replace("__DASHBOARD_NAV_CSS__", nav_css)
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo("America/New_York"))
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            body = render_html(year, month).encode("utf-8")
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
