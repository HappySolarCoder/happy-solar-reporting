# -*- coding: utf-8 -*-

"""Vercel Python function: /api/sales_list

Sales List dashboard: Essential / Momentum / 3rd Roc / All on the locked
Sales grain. Dashboard notes, email, and phone persist in Firestore
sales_list_notes_v1. Data: /api/metrics/sales_list. Overlay write:
POST /api/metrics/sales_list_notes.
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


def render_html(
    timeframe: str = "all",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    installer: str = "all",
    salesperson: str = "",
) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("sales_list")
    now = datetime.now(ZoneInfo("America/New_York"))
    year = int(year) if year else now.year
    month = int(month) if month else now.month
    quarter = int(quarter) if quarter else ((month - 1) // 3) + 1
    timeframe = (timeframe or "all").strip().lower()
    if timeframe not in {"all", "month", "quarter"}:
        timeframe = "all"
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Sales List</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#00C853; --blue:#2196F3;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1700px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }
    .title { font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:900px; }
    .accentline { height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,var(--green) 0%, var(--blue) 55%, rgba(33,150,243,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(0,200,83,.10); border-color:rgba(0,200,83,.45); color:#0a7a34; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f2f5; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button, textarea, input[type="search"], input.dash-field { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--green); border-color:var(--green); color:#fff; font-weight:900; cursor:pointer; }
    button.tab { background:#fff; color:#1f2937; border-color:var(--border); font-weight:800; }
    button.tab.active { background:rgba(0,200,83,.10); border-color:rgba(0,200,83,.45); color:#0a7a34; }
    .tabs { display:flex; gap:8px; flex-wrap:wrap; }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); }
    .span-3 { grid-column:span 3; } .span-12 { grid-column:span 12; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:42px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .tableWrap { overflow:auto; max-height:70vh; border:1px solid var(--border); border-radius:12px; }
    table { width:100%; border-collapse:collapse; min-width:1600px; }
    th, td { border-bottom:1px solid var(--border); padding:9px 10px; text-align:left; font-size:13px; vertical-align:top; }
    th { color:#64748b; font-weight:900; background:#fafbfc; position:sticky; top:0; z-index:1; white-space:nowrap; }
    td.notes { max-width:260px; white-space:pre-wrap; word-break:break-word; }
    td.dashboard-note { min-width:220px; }
    td.dash-edit { min-width:170px; }
    textarea.dash-note { width:100%; min-height:64px; resize:vertical; font-family:inherit; }
    input.dash-field { width:100%; padding:7px 8px; box-sizing:border-box; }
    .note-status { display:block; margin-top:4px; font-size:11px; color:var(--muted2); min-height:14px; }
    .note-status.ok { color:#0a7a34; }
    .note-status.err { color:#b91c1c; }
    .table-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
    .searchbox { min-width:260px; width:min(420px, 100%); }
    button.sortbtn { background:#fff; color:#1f2937; border-color:var(--border); font-weight:800; }
    th.sortable { cursor:pointer; user-select:none; }
    th.sortable:hover { color:#0a7a34; }
    th.sortable .sort-ind { color:#0a7a34; font-weight:900; }
    a.clientlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    a.clientlink:hover { text-decoration:underline; }
    .jsonlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    @media (max-width:980px) { .span-3,.span-12 { grid-column:span 12; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:34px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Sales List</div>
        <div class="subtitle">Live GHL sales board for Essential, Momentum, and 3rd Roc. Defaults to all-time sales and All installers. Grain matches locked Sales / Essential Sales (distinct contact, Sold / Sale Cancelled). Dashboard notes, email, and phone save to Firestore only — GHL appointment notes stay read-only.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Installer</div>
          <div class="tabs" id="installerTabs">
            <button type="button" class="tab" data-installer="all">All</button>
            <button type="button" class="tab" data-installer="essential">Essential</button>
            <button type="button" class="tab" data-installer="momentum">Momentum</button>
            <button type="button" class="tab" data-installer="3rd_roc">3rd Roc</button>
          </div>
        </div>
        <div class="filter"><div class="filter-label">Timeframe</div>
          <div class="tabs" id="timeframeTabs">
            <button type="button" class="tab" data-timeframe="all">All time</button>
            <button type="button" class="tab" data-timeframe="month">Month</button>
            <button type="button" class="tab" data-timeframe="quarter">Quarter</button>
          </div>
        </div>
        <div class="filter"><div class="filter-label">Salesperson</div><select id="salesperson"></select></div>
        <div class="filter" id="yearFilter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter" id="monthFilter"><div class="filter-label">Month</div><select id="month"></select></div>
        <div class="filter" id="quarterFilter"><div class="filter-label">Quarter</div><select id="quarter"></select></div>
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
        <div class="meta" id="rowMeta">Filtered row count</div>
      </div>
      <div class="card span-12">
        <div class="card-title">Sales list</div>
        <div class="table-toolbar">
          <div class="meta">Essential-tab columns plus editable email, phone, and Dashboard notes. <a class="jsonlink" id="jsonLink" href="#">JSON</a></div>
          <div class="filters">
            <div class="filter"><div class="filter-label">Search</div>
              <input type="search" id="searchBox" class="searchbox" placeholder="Name, address, email, phone…" autocomplete="off" />
            </div>
            <div class="filter"><div class="filter-label">Date sold</div>
              <button type="button" class="sortbtn" id="sortBtn" aria-pressed="false">Oldest first</button>
            </div>
          </div>
        </div>
        <div class="tableWrap"><table id="salesTable"></table></div>
      </div>
    </div>
  </div>
  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
<script>
var defaultYear = __YEAR__;
var defaultMonth = __MONTH__;
var defaultQuarter = __QUARTER__;
var defaultTimeframe = "__TIMEFRAME__";
var defaultInstaller = "__INSTALLER__";
var defaultSalesperson = "__SALESPERSON__";
var yearSel = document.getElementById('year');
var monthSel = document.getElementById('month');
var quarterSel = document.getElementById('quarter');
var salespersonSel = document.getElementById('salesperson');
var installer = defaultInstaller || 'all';
var timeframe = defaultTimeframe || 'all';
var allRows = [];
var allColumns = [];
var grainResult = '—';
var tabRowCount = 0;
var searchQuery = '';
var sortDesc = false;
var searchTimer = null;
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
setOptions(quarterSel, [
  {value: 1, label: 'Q1'},
  {value: 2, label: 'Q2'},
  {value: 3, label: 'Q3'},
  {value: 4, label: 'Q4'}
], defaultQuarter);
setOptions(salespersonSel, [{value: '', label: 'All'}], defaultSalesperson);
function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function markTabs() {
  document.querySelectorAll('#installerTabs .tab').forEach(function(btn) {
    btn.classList.toggle('active', btn.getAttribute('data-installer') === installer);
  });
  document.querySelectorAll('#timeframeTabs .tab').forEach(function(btn) {
    btn.classList.toggle('active', btn.getAttribute('data-timeframe') === timeframe);
  });
  var showYear = timeframe === 'month' || timeframe === 'quarter';
  document.getElementById('yearFilter').style.display = showYear ? '' : 'none';
  document.getElementById('monthFilter').style.display = timeframe === 'month' ? '' : 'none';
  document.getElementById('quarterFilter').style.display = timeframe === 'quarter' ? '' : 'none';
}
function query() {
  var params = new URLSearchParams({
    timeframe: timeframe,
    installer: installer
  });
  if (timeframe === 'month') {
    params.set('year', yearSel.value);
    params.set('month', monthSel.value);
  } else if (timeframe === 'quarter') {
    params.set('year', yearSel.value);
    params.set('quarter', quarterSel.value);
  }
  if (salespersonSel.value) params.set('salesperson', salespersonSel.value);
  return params.toString();
}
function viewQuery() {
  var params = new URLSearchParams(query());
  if (searchQuery) params.set('q', searchQuery);
  params.set('order', sortDesc ? 'desc' : 'asc');
  return params.toString();
}
function digitsOnly(v) {
  return String(v == null ? '' : v).replace(/\D/g, '');
}
function ghlContactHref(row) {
  var url = String((row && row.ghlContactUrl) || '');
  if (/^https:\/\/app\.gohighlevel\.com\/v2\/location\/[A-Za-z0-9_-]+\/contacts\/detail\/[A-Za-z0-9_-]+$/.test(url)) {
    return url;
  }
  return '';
}
function identityBlob(row) {
  return [
    row.client, row.address, row.email, row.phone,
    row.salesperson, row.installer, row.contactId,
    row.notes, row.dashboardNote
  ].join(' ').toLowerCase();
}
function rowMatchesSearch(row, q) {
  q = String(q || '').trim().toLowerCase();
  if (!q) return true;
  if (identityBlob(row).indexOf(q) !== -1) return true;
  var qd = digitsOnly(q);
  return qd.length >= 4 && digitsOnly(row.phone).indexOf(qd) !== -1;
}
function visibleRows() {
  var rows = allRows.filter(function(r) { return rowMatchesSearch(r, searchQuery); });
  rows.sort(function(a, b) {
    var da = String(a.submissionDate || '');
    var db = String(b.submissionDate || '');
    if (da !== db) return sortDesc ? db.localeCompare(da) : da.localeCompare(db);
    var ca = String(a.client || '').toLowerCase();
    var cb = String(b.client || '').toLowerCase();
    if (ca !== cb) return ca.localeCompare(cb);
    return String(a.contactId || '').localeCompare(String(b.contactId || ''));
  });
  return rows;
}
function markSort() {
  var btn = document.getElementById('sortBtn');
  btn.textContent = sortDesc ? 'Newest first' : 'Oldest first';
  btn.setAttribute('aria-pressed', sortDesc ? 'true' : 'false');
}
function renderVisible() {
  var rows = visibleRows();
  renderTable(document.getElementById('salesTable'), allColumns, rows);
  document.getElementById('rowCount').textContent = String(rows.length);
  var suffix = searchQuery ? (' · search "' + searchQuery + '"') : '';
  document.getElementById('rowMeta').textContent = 'Locked grain ' + String(grainResult) + ' · filtered ' + String(tabRowCount) + ' · showing ' + String(rows.length) + suffix;
  document.getElementById('jsonLink').href = '/api/metrics/sales_list?' + viewQuery();
  markSort();
}
function renderTable(el, columns, rows) {
  var html = '<thead><tr>';
  columns.forEach(function(c) {
    if (c.key === 'submissionDate') {
      html += '<th class="sortable" data-sort="submissionDate" title="Sort by date sold">' + esc(c.label) + ' <span class="sort-ind">' + (sortDesc ? '▼' : '▲') + '</span></th>';
    } else {
      html += '<th>' + esc(c.label) + '</th>';
    }
  });
  html += '</tr></thead><tbody>';
  if (!rows || !rows.length) {
    html += '<tr><td colspan="' + columns.length + '">No sales in this window.</td></tr>';
  } else {
    rows.forEach(function(r) {
      html += '<tr data-contact="' + esc(r.contactId || '') + '">';
      columns.forEach(function(c) {
        var cid = String(r.contactId || '');
        if (c.key === 'dashboardNote') {
          html += '<td class="dashboard-note">';
          if (cid) {
            html += '<textarea class="dash-note" data-contact="' + esc(cid) + '" data-field="note" data-original="' + esc(r.dashboardNote) + '" aria-label="Dashboard notes">' + esc(r.dashboardNote) + '</textarea>';
            html += '<span class="note-status" data-status-for="note:' + esc(cid) + '"></span>';
          }
          html += '</td>';
        } else if (c.key === 'client') {
          var href = ghlContactHref(r);
          html += '<td>';
          if (href) {
            html += '<a class="clientlink" href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(r.client) + '</a>';
          } else {
            html += esc(r.client);
          }
          html += '</td>';
        } else if (c.key === 'email' || c.key === 'phone') {
          html += '<td class="dash-edit">';
          if (cid) {
            html += '<input class="dash-field" data-contact="' + esc(cid) + '" data-field="' + esc(c.key) + '" data-original="' + esc(r[c.key]) + '" aria-label="' + esc(c.label) + '" value="' + esc(r[c.key]) + '" />';
            html += '<span class="note-status" data-status-for="' + esc(c.key) + ':' + esc(cid) + '"></span>';
          } else {
            html += esc(r[c.key]);
          }
          html += '</td>';
        } else {
          var cls = (c.key === 'notes') ? ' class="notes"' : '';
          html += '<td' + cls + '>' + esc(r[c.key]) + '</td>';
        }
      });
      html += '</tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
  var dateHead = el.querySelector('th.sortable');
  if (dateHead) {
    dateHead.addEventListener('click', function() {
      sortDesc = !sortDesc;
      renderVisible();
    });
  }
  el.querySelectorAll('textarea.dash-note, input.dash-field').forEach(function(field) {
    field.addEventListener('blur', function() { saveField(field); });
    field.addEventListener('keydown', function(ev) {
      if (ev.key === 'Enter' && field.tagName === 'INPUT') {
        ev.preventDefault();
        field.blur();
      }
      if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
        ev.preventDefault();
        field.blur();
      }
    });
  });
}
function setFieldStatus(contactId, field, text, kind) {
  var el = document.querySelector('[data-status-for="' + field + ':' + contactId + '"]');
  if (!el) return;
  el.textContent = text;
  el.className = 'note-status' + (kind ? ' ' + kind : '');
}
function rememberField(contactId, field, value) {
  allRows.forEach(function(row) {
    if (String(row.contactId || '') !== String(contactId)) return;
    if (field === 'note') row.dashboardNote = value;
    else row[field] = value;
  });
}
async function saveField(el) {
  var contactId = el.getAttribute('data-contact') || '';
  var field = el.getAttribute('data-field') || '';
  if (!contactId || !field) return;
  var next = el.value;
  if (next === (el.getAttribute('data-original') || '')) return;
  var body = { contactId: contactId };
  body[field] = next;
  setFieldStatus(contactId, field, 'Saving…', '');
  var res = await fetch('/api/metrics/sales_list_notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  var data = {};
  try { data = await res.json(); } catch (_err) { data = {}; }
  if (!res.ok || data.ok === false) {
    setFieldStatus(contactId, field, data.error || 'Save failed', 'err');
    return;
  }
  rememberField(contactId, field, next);
  el.setAttribute('data-original', next);
  setFieldStatus(contactId, field, 'Saved', 'ok');
}
async function saveNote(area) {
  if (!area.getAttribute('data-field')) area.setAttribute('data-field', 'note');
  return saveField(area);
}
async function load() {
  document.getElementById('jsonLink').href = '/api/metrics/sales_list?' + viewQuery();
  var res = await fetch('/api/metrics/sales_list?' + query());
  var data = await res.json();
  if (!res.ok) {
    document.getElementById('result').textContent = 'Error';
    document.getElementById('rowCount').textContent = '—';
    document.getElementById('windowMeta').textContent = data.error || 'Failed to load';
    return;
  }
  grainResult = data.result == null ? '—' : data.result;
  allRows = data.rows || [];
  allColumns = data.columns || [];
  tabRowCount = data.sales_count != null ? data.sales_count : allRows.length;
  document.getElementById('result').textContent = String(grainResult);
  var start = String(data.window_start_local || '').slice(0, 10);
  var end = String(data.window_end_local || '').slice(0, 10);
  var locked = data.debug && data.debug.sales_result != null ? data.debug.sales_result : data.result;
  grainResult = locked == null ? grainResult : locked;
  var frame = data.timeframe === 'all' ? 'All time' : (data.timeframe === 'quarter' ? 'Quarter' : (data.timeframe === 'month' ? 'Month' : (data.timeframe || '')));
  document.getElementById('windowMeta').textContent = (frame ? frame + ' · ' : '') + start + ' to ' + end + ' (' + (data.timezone || '') + ')';
  var people = [{value: '', label: 'All'}].concat((data.salespeople || []).map(function(name) {
    return {value: name, label: name};
  }));
  var keep = salespersonSel.value || defaultSalesperson;
  setOptions(salespersonSel, people, keep);
  defaultSalesperson = keep;
  renderVisible();
}
document.getElementById('apply').addEventListener('click', load);
document.getElementById('sortBtn').addEventListener('click', function() {
  sortDesc = !sortDesc;
  document.getElementById('jsonLink').href = '/api/metrics/sales_list?' + viewQuery();
  renderVisible();
});
document.getElementById('searchBox').addEventListener('input', function(ev) {
  searchQuery = ev.target.value || '';
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(function() {
    document.getElementById('jsonLink').href = '/api/metrics/sales_list?' + viewQuery();
    renderVisible();
  }, 120);
});
document.querySelectorAll('#installerTabs .tab').forEach(function(btn) {
  btn.addEventListener('click', function() {
    installer = btn.getAttribute('data-installer') || 'all';
    markTabs();
    load();
  });
});
document.querySelectorAll('#timeframeTabs .tab').forEach(function(btn) {
  btn.addEventListener('click', function() {
    timeframe = btn.getAttribute('data-timeframe') || 'all';
    markTabs();
    load();
  });
});
markTabs();
load();
</script>
</body>
</html>
"""
    return (
        html.replace("__YEAR__", str(year))
        .replace("__MONTH__", str(month))
        .replace("__QUARTER__", str(quarter))
        .replace("__TIMEFRAME__", timeframe.replace('"', ""))
        .replace("__INSTALLER__", installer.replace('"', ""))
        .replace("__SALESPERSON__", salesperson.replace('"', "").replace("<", ""))
        .replace("__DASHBOARD_NAV_CSS__", nav_css)
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo("America/New_York"))
            timeframe = (qs.get("timeframe", ["all"])[0] or "all").strip() or "all"
            year_raw = (qs.get("year", [""])[0] or "").strip()
            month_raw = (qs.get("month", [""])[0] or "").strip()
            quarter_raw = (qs.get("quarter", [""])[0] or "").strip()
            year = int(year_raw) if year_raw else now.year
            month = int(month_raw) if month_raw else now.month
            quarter = int(quarter_raw) if quarter_raw.isdigit() else None
            installer = (qs.get("installer", ["all"])[0] or "all").strip() or "all"
            salesperson = (qs.get("salesperson", [""])[0] or "").strip()
            body = render_html(timeframe, year, month, quarter, installer, salesperson).encode("utf-8")
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
