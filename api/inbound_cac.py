# -*- coding: utf-8 -*-

"""Vercel Python function: /api/inbound_cac

Leadership Inbound CAC / TAC dashboard for Lead Locker and Solar Reviews.
Not listed on the main dashboard Lead Generation nav.
Setter unit cost is $500 per sale. TAC = lead CAC + $500.
Data: /api/metrics/inbound_cac (JSON). Default timeframe is YTD.
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


def parse_page_params(qs: dict[str, list[str]], now: datetime) -> tuple[int, int | None]:
    year = int((qs.get("year") or [str(now.year)])[0])
    month_raw = " ".join(str((qs.get("month") or [""])[0] or "").strip().split()).casefold()
    if month_raw in ("", "ytd"):
        return year, None
    return year, int(month_raw)


def render_html(year: int, month: int | None = None) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("inbound_cac")
    default_month = "ytd" if month is None else str(month)
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Inbound CAC</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#00C853; --blue:#2196F3;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1100px; margin:0 auto; }
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
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-12 { grid-column:span 12; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:42px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .tableWrap { overflow:auto; border:1px solid var(--border); border-radius:12px; }
    table { width:100%; border-collapse:collapse; min-width:960px; }
    th, td { border-bottom:1px solid var(--border); padding:11px 12px; text-align:left; font-size:14px; }
    th { color:#64748b; font-weight:900; background:#fafbfc; white-space:nowrap; }
    td.num { text-align:right; font-variant-numeric:tabular-nums; }
    th.num { text-align:right; }
    .jsonlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    .legend { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin:10px 0 6px; font-size:12px; font-weight:800; color:#334155; }
    .swatch { display:inline-block; width:10px; height:10px; border-radius:999px; margin-right:6px; vertical-align:middle; }
    .chartBox { width:100%; min-height:240px; }
    .chartBox svg { width:100%; height:240px; display:block; }
    .chartEmpty { color:var(--muted); font-size:13px; font-weight:700; padding:18px 0; }
    @media (max-width:980px) { .span-3,.span-4,.span-12 { grid-column:span 12; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:34px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Inbound CAC</div>
        <div class="subtitle">Leadership page (direct URL — not on the main Lead Generation nav). Lead CAC uses Lead Locker ($45/lead) and Solar Reviews ($70/lead) on Inbound/Lead Locker. Setter cost is $500 per sale. TAC = lead CAC + $500 (or (lead spend + setter spend) / sales). Default view is YTD (calendar year America/New_York). Sales use locked Sold / Sale Cancelled stages and Contact Sold Date in the same window. Months with no sales are chart gaps, not $0.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter"><div class="filter-label">Timeframe</div><select id="month"></select></div>
        <button id="apply">Apply</button>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Lead Locker CAC</div>
        <div class="kpi" id="leadLockerCac">—</div>
        <div class="meta" id="leadLockerMeta">$45 per lead</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Solar Reviews CAC</div>
        <div class="kpi" id="solarReviewsCac">—</div>
        <div class="meta" id="solarReviewsMeta">$70 per lead</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Overall CAC</div>
        <div class="kpi" id="overallCac">—</div>
        <div class="meta" id="overallMeta">total spend / total sales</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Window</div>
        <div class="kpi" id="windowKpi" style="font-size:22px;padding-top:10px">—</div>
        <div class="meta" id="windowMeta">America/New_York</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Lead Locker TAC</div>
        <div class="kpi" id="leadLockerTac">—</div>
        <div class="meta" id="leadLockerTacMeta">lead CAC + $500 setter</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Solar Reviews TAC</div>
        <div class="kpi" id="solarReviewsTac">—</div>
        <div class="meta" id="solarReviewsTacMeta">lead CAC + $500 setter</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Overall TAC</div>
        <div class="kpi" id="overallTac">—</div>
        <div class="meta" id="overallTacMeta">(lead spend + setter spend) / sales</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Setter unit</div>
        <div class="kpi" id="setterUnitKpi">$500</div>
        <div class="meta" id="setterUnitMeta">$500 per sale (constant)</div>
      </div>
      <div class="card span-12">
        <div class="card-title">YTD totals</div>
        <div class="meta" style="margin-bottom:10px">Lead Locker, Solar Reviews, and overall. Refunded-stage opps are excluded from lead spend. Setter is $500 per sale. Lead CAC and TAC are blank when sales=0. <a class="jsonlink" id="jsonLink" href="#">JSON</a></div>
        <div class="tableWrap"><table id="cacTable"></table></div>
      </div>
      <div class="card span-12">
        <div class="card-title">Performance KPIs</div>
        <div class="meta" style="margin-bottom:10px">Same window as the CAC totals. Opportunities created is the four-pipeline Opportunities Created count (Buffalo, Rochester, Syracuse, Virtual). Opp to prelim = sales ÷ opportunities created. Demo rate = sits ÷ opportunities created (Evan’s formula for this table — not Bot KPI Sit/(Sit+No Sit)). Rates are blank when opportunities created is 0.</div>
        <div class="tableWrap"><table id="kpiTable"></table></div>
        <div class="meta" id="kpiJoinGap" style="margin-top:10px"></div>
      </div>
      <div class="card span-12">
        <div class="card-title">Month-by-month CAC and TAC</div>
        <div class="meta">YTD months in America/New_York. Months with sales=0 are gaps, never plotted as 0.</div>
        <div class="legend">
          <span><span class="swatch" style="background:#2196F3"></span>Lead Locker CAC</span>
          <span><span class="swatch" style="background:#00C853"></span>Solar Reviews CAC</span>
          <span><span class="swatch" style="background:#1565C0"></span>Lead Locker TAC</span>
          <span><span class="swatch" style="background:#2E7D32"></span>Solar Reviews TAC</span>
        </div>
        <div class="chartBox" id="cacChart"></div>
      </div>
    </div>
  </div>
  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
<script>
var defaultYear = __YEAR__;
var defaultMonth = '__MONTH__';
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
var months = [{value: 'ytd', label: 'YTD'}];
for (var i = 0; i < 12; i++) months.push({value: i + 1, label: new Date(2000, i, 1).toLocaleString('en-US', {month: 'long'})});
setOptions(yearSel, years, defaultYear);
setOptions(monthSel, months, defaultMonth);
function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function fmtMoney(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 2});
}
function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return (Number(v) * 100).toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%';
}
function query() {
  var params = { format: 'json', year: yearSel.value };
  if (monthSel.value && monthSel.value !== 'ytd') params.month = monthSel.value;
  return new URLSearchParams(params).toString();
}
function rowBySource(rows, name) {
  rows = rows || [];
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].source === name) return rows[i];
  }
  return null;
}
function renderTable(el, rows, overall) {
  var html = '<thead><tr>';
  html += '<th>Source</th>';
  html += '<th class="num">Lead unit</th>';
  html += '<th class="num">Opps</th>';
  html += '<th class="num">Refunded excluded</th>';
  html += '<th class="num">Lead spend</th>';
  html += '<th class="num">Sales</th>';
  html += '<th class="num">Lead CAC</th>';
  html += '<th class="num">Setter unit</th>';
  html += '<th class="num">Setter spend</th>';
  html += '<th class="num">TAC</th>';
  html += '</tr></thead><tbody>';
  var all = (rows || []).slice();
  if (overall) all.push(overall);
  if (!all.length) {
    html += '<tr><td colspan="10">No inbound rows in this window.</td></tr>';
  } else {
    all.forEach(function(r) {
      html += '<tr>';
      html += '<td>' + esc(r.source) + '</td>';
      html += '<td class="num">' + (r.unit_cost == null ? '—' : fmtMoney(r.unit_cost)) + '</td>';
      html += '<td class="num">' + esc(r.opp_count) + '</td>';
      html += '<td class="num">' + esc(r.refunded_excluded_count) + '</td>';
      html += '<td class="num">' + fmtMoney(r.spend) + '</td>';
      html += '<td class="num">' + esc(r.sales) + '</td>';
      html += '<td class="num">' + fmtMoney(r.cac) + '</td>';
      html += '<td class="num">' + (r.setter_unit_cost == null ? '—' : fmtMoney(r.setter_unit_cost)) + '</td>';
      html += '<td class="num">' + fmtMoney(r.setter_spend) + '</td>';
      html += '<td class="num">' + fmtMoney(r.tac) + '</td>';
      html += '</tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}
function renderKpiTable(el, kpis) {
  kpis = kpis || {};
  var html = '<thead><tr>';
  html += '<th>KPI</th>';
  html += '<th class="num">Value</th>';
  html += '<th>Formula</th>';
  html += '</tr></thead><tbody>';
  html += '<tr><td>Opportunities created</td><td class="num">' + esc(kpis.opportunities_created == null ? '—' : kpis.opportunities_created) + '</td><td>Four-pipeline Opportunities Created (createdAt)</td></tr>';
  html += '<tr><td>Opp to prelim</td><td class="num">' + fmtPct(kpis.opp_to_prelim) + '</td><td>sales ÷ opportunities created</td></tr>';
  html += '<tr><td>Demo rate</td><td class="num">' + fmtPct(kpis.demo_rate) + '</td><td>sits ÷ opportunities created</td></tr>';
  html += '</tbody>';
  el.innerHTML = html;
  var gap = document.getElementById('kpiJoinGap');
  if (gap) gap.textContent = kpis.join_gap_short || '';
}
function drawCacChart(chart) {
  var el = document.getElementById('cacChart');
  if (!el) return;
  chart = chart || {};
  var labels = chart.labels || [];
  var locker = chart.lead_locker_cac || [];
  var reviews = chart.solar_reviews_cac || [];
  var lockerTac = chart.lead_locker_tac || [];
  var reviewsTac = chart.solar_reviews_tac || [];
  var rows = labels.map(function(label, i) {
    return {
      date: label,
      lead_locker_cac: (locker[i] === undefined ? null : locker[i]),
      solar_reviews_cac: (reviews[i] === undefined ? null : reviews[i]),
      lead_locker_tac: (lockerTac[i] === undefined ? null : lockerTac[i]),
      solar_reviews_tac: (reviewsTac[i] === undefined ? null : reviewsTac[i])
    };
  });
  var series = [
    {key: 'lead_locker_cac', label: 'Lead Locker CAC', color: '#2196F3', dash: ''},
    {key: 'solar_reviews_cac', label: 'Solar Reviews CAC', color: '#00C853', dash: ''},
    {key: 'lead_locker_tac', label: 'Lead Locker TAC', color: '#1565C0', dash: '6 4'},
    {key: 'solar_reviews_tac', label: 'Solar Reviews TAC', color: '#2E7D32', dash: '6 4'}
  ];
  var hasPoint = false;
  var values = series.map(function(s) {
    return rows.map(function(row) {
      var v = row[s.key];
      if (v === null || v === undefined || v === '') return null;
      hasPoint = true;
      return Number(v);
    });
  });
  if (!hasPoint) {
    el.innerHTML = '<div class="chartEmpty">No monthly CAC or TAC yet. Months with sales=0 stay blank (not $0).</div>';
    return;
  }
  var W = Math.max(320, el.clientWidth || 760);
  var H = 240;
  var m = {l: 48, r: 14, t: 16, b: 32};
  var iw = W - m.l - m.r;
  var ih = H - m.t - m.b;
  var n = rows.length || 1;
  var max = 0;
  values.forEach(function(vals) {
    vals.forEach(function(v) {
      if (v == null) return;
      if (v > max) max = v;
    });
  });
  max = Math.max(max, 1);
  function x(i) {
    return m.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  }
  function y(v) {
    return m.t + ih - (v / max) * ih;
  }
  var grid = '';
  for (var g = 0; g <= 4; g++) {
    var gv = (max / 4) * g;
    var gy = y(gv);
    grid += '<line x1="' + m.l + '" y1="' + gy.toFixed(1) + '" x2="' + (W - m.r) + '" y2="' + gy.toFixed(1) + '" stroke="#eef2f7" />';
    grid += '<text x="' + (m.l - 6) + '" y="' + (gy + 3).toFixed(1) + '" text-anchor="end" font-size="10" fill="#94a3b8">$' + Math.round(gv) + '</text>';
  }
  var xlabels = '';
  for (var i = 0; i < n; i++) {
    xlabels += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle" font-size="10" fill="#64748b">' + esc(labels[i] || '') + '</text>';
  }
  var paths = '';
  series.forEach(function(s, si) {
    var d = '';
    var drawing = false;
    var dots = '';
    values[si].forEach(function(v, i) {
      if (v == null) {
        drawing = false;
        return;
      }
      var px = x(i).toFixed(1);
      var py = y(v).toFixed(1);
      d += (drawing ? ' L' : 'M') + px + ' ' + py;
      drawing = true;
      dots += '<circle cx="' + px + '" cy="' + py + '" r="3" fill="' + s.color + '"><title>' + esc(labels[i] || '') + ' — ' + s.label + ' ' + fmtMoney(v) + '</title></circle>';
    });
    if (d) {
      var dashAttr = s.dash ? ' stroke-dasharray="' + s.dash + '"' : '';
      paths += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="2.5"' + dashAttr + ' />' + dots;
    }
  });
  el.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="240" role="img" aria-label="Inbound CAC monthly chart">' + grid + paths + xlabels + '</svg>';
}
async function load() {
  var q = query();
  document.getElementById('jsonLink').href = '/api/metrics/inbound_cac?' + q;
  var res = await fetch('/api/metrics/inbound_cac?' + q);
  var data = await res.json();
  if (!res.ok) {
    document.getElementById('leadLockerCac').textContent = 'Error';
    document.getElementById('solarReviewsCac').textContent = '—';
    document.getElementById('overallCac').textContent = '—';
    document.getElementById('leadLockerTac').textContent = '—';
    document.getElementById('solarReviewsTac').textContent = '—';
    document.getElementById('overallTac').textContent = '—';
    document.getElementById('windowKpi').textContent = '—';
    document.getElementById('windowMeta').textContent = data.error || 'Failed to load';
    return;
  }
  var locker = rowBySource(data.rows, 'Lead Locker');
  var reviews = rowBySource(data.rows, 'Solar Reviews');
  var overall = data.overall || {};
  var setterUnit = (overall.setter_unit_cost != null) ? overall.setter_unit_cost : (data.contract && data.contract.setter_unit_cost);
  document.getElementById('leadLockerCac').textContent = locker ? fmtMoney(locker.cac) : '—';
  document.getElementById('leadLockerMeta').textContent = locker
    ? (fmtMoney(locker.spend) + ' lead spend · ' + locker.sales + ' sales')
    : '$45 per lead';
  document.getElementById('solarReviewsCac').textContent = reviews ? fmtMoney(reviews.cac) : '—';
  document.getElementById('solarReviewsMeta').textContent = reviews
    ? (fmtMoney(reviews.spend) + ' lead spend · ' + reviews.sales + ' sales')
    : '$70 per lead';
  document.getElementById('overallCac').textContent = fmtMoney(overall.cac);
  document.getElementById('overallMeta').textContent = (fmtMoney(overall.spend) + ' lead spend · ' + (overall.sales == null ? '—' : overall.sales) + ' sales');
  document.getElementById('leadLockerTac').textContent = locker ? fmtMoney(locker.tac) : '—';
  document.getElementById('leadLockerTacMeta').textContent = locker
    ? (fmtMoney(locker.setter_spend) + ' setter · TAC = CAC + $500')
    : 'lead CAC + $500 setter';
  document.getElementById('solarReviewsTac').textContent = reviews ? fmtMoney(reviews.tac) : '—';
  document.getElementById('solarReviewsTacMeta').textContent = reviews
    ? (fmtMoney(reviews.setter_spend) + ' setter · TAC = CAC + $500')
    : 'lead CAC + $500 setter';
  document.getElementById('overallTac').textContent = fmtMoney(overall.tac);
  document.getElementById('overallTacMeta').textContent = (fmtMoney(overall.setter_spend) + ' setter spend · ' + (overall.sales == null ? '—' : overall.sales) + ' sales');
  document.getElementById('setterUnitKpi').textContent = fmtMoney(setterUnit != null ? setterUnit : 500);
  document.getElementById('setterUnitMeta').textContent = (overall.setter_spend == null ? '$500 per sale (constant)' : (fmtMoney(overall.setter_spend) + ' setter spend YTD'));
  var start = String(data.window_start_local || '').slice(0, 10);
  var end = String(data.window_end_local || '').slice(0, 10);
  var frame = data.timeframe === 'ytd' ? 'YTD' : 'Month';
  document.getElementById('windowKpi').textContent = frame + ' · ' + start + ' → ' + end;
  document.getElementById('windowMeta').textContent = data.timezone || 'America/New_York';
  renderTable(document.getElementById('cacTable'), data.rows || [], overall);
  renderKpiTable(document.getElementById('kpiTable'), data.performance_kpis || {});
  drawCacChart(data.chart || {});
}
document.getElementById('apply').addEventListener('click', load);
load();
</script>
</body>
</html>
"""
    return (
        html.replace("__YEAR__", str(year))
        .replace("__MONTH__", default_month)
        .replace("__DASHBOARD_NAV_CSS__", nav_css)
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo("America/New_York"))
            year, month = parse_page_params(qs, now)
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
