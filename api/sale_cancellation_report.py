# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


def render_html(year: int, month: int) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("sale_cancellation_report")
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Sale Cancellation Report</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --pink:#ec4899; --pink2:#f472b6; --green:#10b981; --red:#ef4444; --amber:#f59e0b; --slate:#334155;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1240px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }
    .title { font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:780px; }
    .pinkline { height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(236,72,153,.10); border-color:rgba(236,72,153,.45); color:#b80b66; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f2f5; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button, input[type=date] { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--pink); border-color:var(--pink); color:#fff; font-weight:900; cursor:pointer; }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); min-height:120px; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:42px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-6 { grid-column:span 6; } .span-8 { grid-column:span 8; } .span-12 { grid-column:span 12; }
    .bars { margin-top:12px; display:flex; flex-direction:column; gap:10px; }
    .barrow { display:grid; grid-template-columns:180px 1fr 80px; gap:10px; align-items:center; }
    .barlabel { font-size:12px; font-weight:800; color:#334155; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bartrack { width:100%; height:12px; border-radius:999px; background:#eef2f7; overflow:hidden; }
    .barfill { height:100%; border-radius:999px; }
    .barvalue { text-align:right; font-size:12px; font-weight:900; color:#475569; }
    .trend { margin-top:12px; display:flex; align-items:flex-end; gap:10px; min-height:260px; overflow-x:auto; padding-bottom:8px; }
    .trendcol { width:42px; min-width:42px; display:flex; flex-direction:column; align-items:center; gap:6px; }
    .stack { width:100%; height:180px; display:flex; flex-direction:column; justify-content:flex-end; gap:4px; }
    .seg { width:100%; border-radius:8px 8px 3px 3px; }
    .gross { background:#fbcfe8; } .cancelled { background:var(--red); } .net { background:var(--green); }
    .trendlabel { font-size:11px; color:#64748b; transform:rotate(-30deg); transform-origin:center top; white-space:nowrap; }
    table { width:100%; border-collapse:collapse; margin-top:12px; }
    th, td { border-bottom:1px solid var(--border); padding:10px 8px; text-align:left; font-size:13px; vertical-align:top; }
    th { color:#64748b; font-weight:900; background:#fafbfc; position:sticky; top:0; }
    .tableWrap { overflow:auto; max-height:420px; border:1px solid var(--border); border-radius:12px; }
    .note { font-size:12px; color:#64748b; line-height:1.45; }
    .danger { color:#b91c1c; }
    @media (max-width:980px) { .span-3,.span-4,.span-6,.span-8,.span-12 { grid-column:span 12; } .barrow { grid-template-columns:120px 1fr 64px; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; } .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; } .kpi { font-size:34px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Sale Cancellation Report</div>
        <div class="subtitle">Cancelled sales dashboard by rep, pipeline, setter, and lead source. Cancellation rate uses Sale Cancelled opportunities divided by all sold-date opportunities in the selected window.</div>
        <div class="pinkline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter"><div class="filter-label">Month</div><select id="month"></select></div>
        <button id="apply">Apply</button>
        <div class="filter"><div class="filter-label">Start</div><input id="startDate" type="date" /></div>
        <div class="filter"><div class="filter-label">End</div><input id="endDate" type="date" /></div>
        <button id="clearRange" style="background:#fff;color:#1f2937;border-color:var(--border);font-weight:900">Clear</button>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3"><div class="card-title">Sold-Date Opportunities</div><div class="kpi" id="soldDateTotal">—</div><div class="meta">All included-pipeline opps with sold date</div></div>
      <div class="card span-3"><div class="card-title">Cancelled Sales</div><div class="kpi danger" id="cancelledSales">—</div><div class="meta">Current stage is Sale Cancelled</div></div>
      <div class="card span-3"><div class="card-title">Not Cancelled</div><div class="kpi" id="notCancelledSales">—</div><div class="meta">Sold-date opps not currently cancelled</div></div>
      <div class="card span-3"><div class="card-title">Cancellation Rate</div><div class="kpi" id="cancelRate">—</div><div class="meta" id="windowMeta">—</div></div>

      <div class="card span-8"><div class="card-title">Sold-Date vs Cancelled vs Not Cancelled Trend</div><div id="trend" class="trend"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">Metric Semantics</div><div class="note" id="semantics">Loading…</div></div>

      <div class="card span-6"><div class="card-title">Cancellations by Sales Rep</div><div id="ownerBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-6"><div class="card-title">Cancellation % by Sales Rep</div><div id="ownerRateBars" class="bars"><div class="meta">Loading…</div></div></div>

      <div class="card span-4"><div class="card-title">By Pipeline</div><div id="pipelineBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">By Setter</div><div id="setterBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">By Lead Source</div><div id="sourceBars" class="bars"><div class="meta">Loading…</div></div></div>

      <div class="card span-12"><div class="card-title">Rep Table</div><div class="tableWrap"><table id="ownerTable"></table></div></div>
      <div class="card span-12"><div class="card-title">Cancelled Detail</div><div class="tableWrap"><table id="detailTable"></table></div></div>
    </div>
  </div>
  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
<script>
var defaultYear = __YEAR__;
var defaultMonth = __MONTH__;
var yearSel = document.getElementById('year');
var monthSel = document.getElementById('month');
var startDate = document.getElementById('startDate');
var endDate = document.getElementById('endDate');
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
function fmtNum(v) { return new Intl.NumberFormat('en-US').format(Number(v || 0)); }
function fmtPct(v) { return Number(v || 0).toFixed(1) + '%'; }
function renderBars(el, rows, valueKey, color, isPct) {
  if (!rows || !rows.length) { el.innerHTML = '<div class="meta">No data.</div>'; return; }
  var max = 1;
  rows.forEach(function(r) { max = Math.max(max, Number(r[valueKey] || 0)); });
  var html = '';
  rows.slice(0, 12).forEach(function(r) {
    var val = Number(r[valueKey] || 0);
    var width = Math.max((val / max) * 100, val > 0 ? 3 : 0);
    html += '<div class="barrow"><div class="barlabel" title="' + r.label + '">' + r.label + '</div><div class="bartrack"><div class="barfill" style="width:' + width + '%; background:' + color + ';"></div></div><div class="barvalue">' + (isPct ? fmtPct(val) : fmtNum(val)) + '</div></div>';
  });
  el.innerHTML = html;
}
function renderTrend(el, rows) {
  if (!rows || !rows.length) { el.innerHTML = '<div class="meta">No trend data.</div>'; return; }
  var max = 1;
  rows.forEach(function(r) { max = Math.max(max, Number(r.sold_date_total || 0)); });
  var html = '';
  rows.slice(-24).forEach(function(r) {
    var grossH = Math.round((Number(r.sold_date_total || 0) / max) * 160);
    var cancelledH = Math.round((Number(r.cancelled || 0) / max) * 160);
    var netH = Math.round((Number(r.not_cancelled || 0) / max) * 160);
    html += '<div class="trendcol"><div class="stack"><div class="seg gross" style="height:' + grossH + 'px"></div><div class="seg cancelled" style="height:' + cancelledH + 'px"></div><div class="seg net" style="height:' + netH + 'px"></div></div><div class="trendlabel">' + String(r.date || '').slice(5) + '</div></div>';
  });
  el.innerHTML = html;
}
function renderTable(el, headers, rows, kind) {
  var html = '<thead><tr>';
  headers.forEach(function(h) { html += '<th>' + h + '</th>'; });
  html += '</tr></thead><tbody>';
  if (!rows || !rows.length) {
    html += '<tr><td colspan="' + headers.length + '">No rows.</td></tr>';
  } else if (kind === 'owner') {
    rows.forEach(function(r) {
      html += '<tr><td>' + r.label + '</td><td>' + fmtNum(r.sold_date_total) + '</td><td>' + fmtNum(r.cancelled) + '</td><td>' + fmtPct(r.cancellation_rate) + '</td><td>' + fmtNum(r.not_cancelled) + '</td></tr>';
    });
  } else {
    rows.forEach(function(r) {
      html += '<tr><td>' + (r.contactName || '') + '</td><td>' + (r.owner || '') + '</td><td>' + (r.setter || '') + '</td><td>' + (r.pipeline || '') + '</td><td>' + (r.leadSource || '') + '</td><td>' + (r.soldDate || '') + '</td><td>' + (r.lastStageChangeAt || r.updatedAt || '') + '</td></tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}
function query() {
  var params = new URLSearchParams({ format: 'json', year: yearSel.value, month: monthSel.value });
  if (startDate.value && endDate.value) { params.set('start', startDate.value); params.set('end', endDate.value); }
  return params.toString();
}
async function load() {
  var res = await fetch('/api/metrics/sales_cancellations?' + query());
  var data = await res.json();
  document.getElementById('soldDateTotal').textContent = fmtNum(data.kpis.sold_date_total);
  document.getElementById('cancelledSales').textContent = fmtNum(data.kpis.cancelled_sales);
  document.getElementById('notCancelledSales').textContent = fmtNum(data.kpis.not_cancelled_sales);
  document.getElementById('cancelRate').textContent = fmtPct(data.kpis.cancellation_rate);
  document.getElementById('windowMeta').textContent = data.window_start_local.slice(0, 10) + ' to ' + data.window_end_local.slice(0, 10);
  document.getElementById('semantics').textContent = data.window_semantics;
  renderTrend(document.getElementById('trend'), data.trend);
  renderBars(document.getElementById('ownerBars'), data.tables.by_owner, 'cancelled', 'var(--red)', false);
  renderBars(document.getElementById('ownerRateBars'), data.tables.by_owner, 'cancellation_rate', 'var(--pink)', true);
  renderBars(document.getElementById('pipelineBars'), data.tables.by_pipeline, 'cancelled', 'var(--amber)', false);
  renderBars(document.getElementById('setterBars'), data.tables.by_setter, 'cancelled', 'var(--pink2)', false);
  renderBars(document.getElementById('sourceBars'), data.tables.by_lead_source, 'cancelled', 'var(--slate)', false);
  renderTable(document.getElementById('ownerTable'), ['Sales Rep', 'Sold-Date Total', 'Cancelled', 'Cancellation %', 'Not Cancelled'], data.tables.by_owner, 'owner');
  renderTable(document.getElementById('detailTable'), ['Contact', 'Rep', 'Setter', 'Pipeline', 'Lead Source', 'Sold Date', 'Last Stage Change'], data.tables.cancelled_detail, 'detail');
}
document.getElementById('apply').addEventListener('click', load);
document.getElementById('clearRange').addEventListener('click', function() { startDate.value = ''; endDate.value = ''; load(); });
load();
</script>
</body>
</html>
"""
    return html.replace("__YEAR__", str(year)).replace("__MONTH__", str(month)).replace("__DASHBOARD_NAV_CSS__", nav_css).replace("__DASHBOARD_NAV_HTML__", nav_html)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render_html(datetime.utcnow().year, datetime.utcnow().month).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
