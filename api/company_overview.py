# -*- coding: utf-8 -*-

"""Vercel Python function: /api/company_overview

Company Overview (first page of production dashboard)
- Total Sales
- Sales per Team (Pipeline)
- Sales per Owner (Sales Rep)
- Sales per Channel (Lead Gen Source)
- Opportunities Created by Setter (vertical bar chart)
- Opportunities Created by Lead Gen Source (vertical bar chart)

Data sources:
- /api/metrics/sales (v2)
- /api/metrics/opportunities_created (v2)

UI intent (Customer Insights production style):
- White cards on light gray background
- Vibrant chart colors
- 3-column grid behavior
- Pink gradient accent line

NOTE: The canonical style reference file
`Memories/Beane/Dashboard Designs/Customer Insights Dashboard UI Example.md`
was not found at the expected vault path at time of implementation, so this is a
best-effort implementation based on the described rules.
"""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def render_html(year: int, month: int) -> str:
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Company Overview</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;

      /* Customer Insights vibe */
      --green: #00C853;
      --green2: #2EE07A;
      --blue: #2196F3;
      --blue2: #64B5F6;

      --purple: #8b5cf6;
      --cyan: #06b6d4;
      --amber: #f59e0b;
      --green: #10b981;
    }

    body {
      font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      margin:0;
      background: var(--bg);
      color: var(--text);
    }

    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar {
      position: relative;
      display:flex;
      align-items:flex-start;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
      padding: 18px 20px;
      border-radius: 14px;
      background: var(--card);
      border: 1px solid var(--border);
      box-shadow: 0 1px 3px rgba(17,24,39,0.05);
    }

    .title {
      font-size: 22px;
      font-weight: 900;
      color: #1a2b4a;
      letter-spacing: -0.02em;
    }

    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px;
      width: 180px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--green) 0%, var(--blue) 55%, rgba(100,181,246,0) 100%);
      margin-top: 10px;
    }

    .nav {
      margin-top: 12px;
      display:flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .navbtn {
      display:inline-flex;
      align-items:center;
      padding: 9px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      color: #1f2937;
      font-size: 13px;
      font-weight: 800;
      text-decoration:none;
    }

    .navbtn:hover {
      border-color: rgba(0,200,83,0.45);
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }

    .navbtn.active {
      background: rgba(0,200,83,0.10);
      border-color: rgba(0,200,83,0.45);
      color: #0a7a34;
    }

    .adminSettings {
      position: absolute;
      top: 16px;
      right: 18px;
    }

    .filters { display:flex; align-items:center; gap: 10px; flex-wrap: wrap; }
    .filter { display:flex; align-items:center; gap: 8px; }

    /* Period pills (shared dashboard behavior) */
    .pillbar { margin-top: 12px; display:flex; gap: 10px; flex-wrap: wrap; }
    .pill {
      display:inline-flex;
      align-items:center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      color: #334155;
      font-size: 12px;
      font-weight: 950;
      cursor: pointer;
      user-select: none;
    }
    .pill:hover { border-color: rgba(0,200,83,0.45); box-shadow: 0 1px 2px rgba(17,24,39,0.06); }
    .pill.active { background: rgba(0,200,83,0.10); border-color: rgba(0,200,83,0.45); color: #0a7a34; }
    .filter-label {
      font-size: 12px;
      color: var(--muted);
      background:#f0f2f5;
      padding: 9px 10px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }

    select, button, input[type=date] {
      background: var(--card);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 13px;
    }

    button {
      background: var(--green);
      border-color: var(--green);
      color: #fff;
      font-weight: 900;
      cursor:pointer;
    }

    .grid {
      display:grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      margin-top: 14px;
      align-content: start;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px 18px;
      box-shadow: 0 1px 3px rgba(17,24,39,0.06);
      min-height: 120px;
    }

    /* Demo rate row: 5 cards on one line */
    .demoRow {
      grid-column: span 12;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 14px;
    }
    .demoCard { padding: 14px 14px; min-height: 104px; }
    .demoCard .kpi { font-size: 38px; }
    @media (max-width: 1180px) {
      .demoRow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .demoRow { grid-template-columns: 1fr; }
    }

    .card-header { display:flex; align-items:flex-start; justify-content: space-between; gap: 10px; }

    .gear {
      display:inline-flex;
      align-items:center;
      justify-content:center;
      width: 30px;
      height: 30px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #fff;
      color: var(--muted);
      text-decoration:none;
      font-size: 16px;
      line-height: 1;
    }

    .gear:hover {
      border-color: rgba(0,200,83,0.45);
      color: #0a7a34;
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }
    .card-title { font-size: 13px; font-weight: 800; color: var(--muted); }

    .kpi { font-size: 46px; font-weight: 950; margin-top: 8px; letter-spacing: -0.02em; }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }

    @media (max-width: 980px) {
      .span-3, .span-4, .span-6, .span-8, .span-12 { grid-column: span 12; }
    }

    /* Horizontal bars */
    .barlist { margin-top: 10px; }
    .barrow { display:flex; align-items:center; gap: 10px; margin: 10px 0; }
    .barlabel { width: 180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size: 13px; color: var(--text); }
    .barwrap { flex: 1; background: #f0f2f5; border: 1px solid var(--border); border-radius: 999px; height: 14px; overflow:hidden; }
    .barfill { height: 100%; }
    .barval { width: 54px; text-align:right; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 13px; }

    /* Vertical bars */
    .vchart { margin-top: 10px; }
    .vwrap {
      display:flex;
      align-items:stretch;
      justify-content:center;
      gap: 10px;
      height: 260px;
      padding: 12px 12px;
      background:#fafbfc;
      border:1px solid var(--border);
      border-radius:12px;
      overflow-x:auto;
    }
    .vcol {
      width: 86px;
      flex: 0 0 86px;
      height: 100%;
      display:flex;
      flex-direction:column;
      align-items:center;
      gap: 8px;
    }
    .vval { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; text-align:center; width:100%; }
    .vbarArea {
      width: 100%;
      flex: 1;
      display:flex;
      align-items:stretch;
      justify-content:center;
    }

    .vbarStack {
      width: 100%;
      height: 100%;
      display:flex;
      flex-direction:column;
      justify-content:flex-end;
      align-items:stretch;
      gap: 6px;
    }
    .vbar {
      width: 100%;
      border-radius: 14px 14px 6px 6px;
    }
    .vlabel {
      font-size: 11px;
      color: var(--muted);
      text-align:center;
      width: 100%;
      overflow:hidden;
      text-overflow:ellipsis;
      white-space:nowrap;
    }

    a { color: var(--green); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .skeleton { color: var(--muted2); font-size: 13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Company Overview</div>
        <div class="subtitle">Happy Solar — Sales + created opportunities</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn active" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn" href="/api/fma_dashboard">FMA dashboard</a>
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
          <a class="navbtn" href="/api/missing_dispos">Missing Dispos</a>
        </div>
      </div>

      <div class="filters">
        <a class="navbtn adminSettings" href="/api/settings">Admin Settings</a>
        <div class="filter">
          <div class="filter-label">Year</div>
          <select id="year"></select>
        </div>
        <div class="filter">
          <div class="filter-label">Month</div>
          <select id="month"></select>
        </div>
        <button id="apply">Apply</button>
        <div class="filter">
          <div class="filter-label">Start</div>
          <input id="startDate" type="date" />
        </div>
        <div class="filter">
          <div class="filter-label">End</div>
          <input id="endDate" type="date" />
        </div>
        <button id="clearRange" style="background:#fff;color:#1f2937;border-color:var(--border);font-weight:900">Clear</button>
        <div class="meta" id="rangeMeta" style="margin-left:auto"></div>
      </div>

      <div class="pillbar" id="periodTabs">
        <div class="pill" data-period="thismo">This Month</div>
        <div class="pill" data-period="lastmo">Last Month</div>
        <div class="pill" data-period="thiswk">This Week</div>
        <div class="pill" data-period="yesterday">Yesterday</div>
        <div class="pill" data-period="2w">Last 2 Weeks</div>
        <div class="pill" data-period="custom">Custom</div>
      </div>
    </div>

    <div class="grid">
      <!-- Top KPI row -->
      <div class="card span-4">
        <div class="card-header">
          <div class="card-title">Total Sales</div>
          <div class="meta"><a class="gear" href="/api/dashboard" title="Debug / settings">⚙</a></div>
        </div>
        <div class="kpi" id="totalSales">—</div>
        <div class="meta" id="salesMeta">—</div>
      </div>

      <div class="card span-4">
        <div class="card-header">
          <div class="card-title">Total Opportunities Created</div>
          <div class="meta"><a class="gear" href="/api/dashboard" title="Debug / settings">⚙</a></div>
        </div>
        <div class="kpi" id="totalCreated">—</div>
        <div class="meta" id="createdMeta">—</div>
      </div>

      <div class="card span-4">
        <div class="card-header">
          <div class="card-title">Opp2Prelim %</div>
          <div class="meta">Total Sales / Total Opps Ran</div>
        </div>
        <div class="kpi" id="opp2prelim">—</div>
        <div class="meta" id="opp2prelimMeta">—</div>
      </div>

      <!-- Demo Rate KPI row -->
      <div class="demoRow">
        <div class="card demoCard">
          <div class="card-header">
            <div class="card-title">Demo Rate (Company)</div>
            <div class="meta"><a class="gear" href="/api/metrics/demo_rate" title="QA debug">⚙</a></div>
          </div>
          <div class="kpi" id="demoRateCompany">—</div>
          <div class="meta" id="demoRateCompanyCounts">Demos: — • Ran: —</div>
        </div>

        <div class="card demoCard">
          <div class="card-header">
            <div class="card-title">Demo Rate — Doors</div>
            <div class="meta"><a class="gear" href="/api/metrics/demo_rate" title="QA debug">⚙</a></div>
          </div>
          <div class="kpi" id="demoRateDoors">—</div>
          <div class="meta" id="demoRateDoorsCounts">Demos: — • Ran: —</div>
        </div>

        <div class="card demoCard">
          <div class="card-header">
            <div class="card-title">Demo Rate — Self Gen</div>
            <div class="meta"><a class="gear" href="/api/metrics/demo_rate" title="QA debug">⚙</a></div>
          </div>
          <div class="kpi" id="demoRateSelfGen">—</div>
          <div class="meta" id="demoRateSelfGenCounts">Demos: — • Ran: —</div>
        </div>

        <div class="card demoCard">
          <div class="card-header">
            <div class="card-title">Demo Rate — Phones</div>
            <div class="meta"><a class="gear" href="/api/metrics/demo_rate" title="QA debug">⚙</a></div>
          </div>
          <div class="kpi" id="demoRateVirtual">—</div>
          <div class="meta" id="demoRateVirtualCounts">Demos: — • Ran: —</div>
        </div>

        <div class="card demoCard">
          <div class="card-header">
            <div class="card-title">Demo Rate — 3PL</div>
            <div class="meta"><a class="gear" href="/api/metrics/demo_rate" title="QA debug">⚙</a></div>
          </div>
          <div class="kpi" id="demoRate3pl">—</div>
          <div class="meta" id="demoRate3plCounts">Demos: — • Ran: —</div>
        </div>
      </div>

      <!-- Row 2: Sales per Team full width -->
      <div class="card span-12">
        <div class="card-header">
          <div class="card-title">Sales per Team (Pipeline)</div>
          <div class="meta">Vertical bars</div>
        </div>
        <div class="vchart" id="salesByPipelineV"><div class="skeleton">Loading…</div></div>
      </div>

      <!-- Row 3: vertical sales by lead gen source + vertical created by lead gen source -->
      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Sales per Lead Gen Source</div>
          <div class="meta">Vertical bars</div>
        </div>
        <div class="vchart" id="salesByChannelV"><div class="skeleton">Loading…</div></div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Opportunities Created by Lead Gen Source</div>
          <div class="meta">Vertical bars</div>
        </div>
        <div class="vchart" id="createdByLead"><div class="skeleton">Loading…</div></div>
      </div>
    </div>
  </div>

<script>
  const defaultYear = __YEAR__;
  const defaultMonth = __MONTH__;

  const palette = [
    'var(--green)',
    'var(--blue)',
    'var(--purple)',
    'var(--cyan)',
    'var(--amber)',
    'var(--green)'
  ];

  function setOptions(sel, options, value) {
    sel.innerHTML = '';
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = String(opt.value);
      o.textContent = opt.label;
      if (String(opt.value) === String(value)) o.selected = true;
      sel.appendChild(o);
    }
  }

  const yearSel = document.getElementById('year');
  const monthSel = document.getElementById('month');

  const years = [];
  for (let y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
  const months = Array.from({length:12}, (_,i)=>({value:i+1, label: new Date(2000,i,1).toLocaleString('en-US',{month:'long'})}));

  setOptions(yearSel, years, defaultYear);
  setOptions(monthSel, months, defaultMonth);

  function renderBars(container, obj) {
    container.innerHTML = '';
    const entries = Object.entries(obj || {});
    if (!entries.length) {
      container.innerHTML = '<div class="skeleton">No data.</div>';
      return;
    }
    entries.sort((a,b) => (Number(b[1]||0) - Number(a[1]||0)) || String(a[0]).localeCompare(String(b[0])));
    const maxVal = Math.max(...entries.map(([,v]) => Number(v)||0), 1);
    let i = 0;
    for (const [name, val] of entries) {
      const n = String(name);
      const v = Number(val) || 0;
      if (v === 0) continue;
      const pct = Math.round((v / maxVal) * 100);
      const color = palette[i % palette.length];
      i++;
      const row = document.createElement('div');
      row.className = 'barrow';
      row.innerHTML = `
        <div class="barlabel" title="${n}">${n}</div>
        <div class="barwrap"><div class="barfill" style="width:${pct}%; background:${color}"></div></div>
        <div class="barval">${v}</div>
      `;
      container.appendChild(row);
    }
  }

  function renderVertical(container, obj) {
    container.innerHTML = '';
    const entries = Object.entries(obj || {});
    if (!entries.length) {
      container.innerHTML = '<div class="skeleton">No data.</div>';
      return;
    }
    entries.sort((a,b) => (Number(b[1]||0) - Number(a[1]||0)) || String(a[0]).localeCompare(String(b[0])));
    const maxVal = Math.max(...entries.map(([,v]) => Number(v)||0), 1);

    let html = '<div class="vwrap">';
    let i = 0;
    for (const [name, val] of entries) {
      const n = String(name);
      const v = Number(val) || 0;
      if (v === 0) continue;
      const scale = Math.max(0.02, v / maxVal);
      const color = palette[i % palette.length];
      i++;
      html += `
        <div class="vcol" title="${n}">
          <div class="vbarArea">
            <div class="vbarStack">
              <div class="vval">${v}</div>
              <div class="vbar" style="background:${color}; height:${(scale*100).toFixed(2)}%"></div>
            </div>
          </div>
          <div class="vlabel">${n}</div>
        </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
  }

  function rangeParams() {
    const s = (document.getElementById('startDate').value || '').trim();
    const e = (document.getElementById('endDate').value || '').trim();
    if (s && e) return `&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
    return '';
  }

  // Persist range in URL so the UI always reflects the active range
  const pageUrl = new URL(window.location.href);
  const urlStart = pageUrl.searchParams.get('start') || '';
  const urlEnd = pageUrl.searchParams.get('end') || '';

  const rangeMetaEl = document.getElementById('rangeMeta');

  function daysInMonth(y, m) {
    return new Date(Number(y), Number(m), 0).getDate();
  }

  function setActive(period) {
    document.querySelectorAll('#periodTabs .pill').forEach(x => x.classList.toggle('active', x.dataset.period === period));
  }

  function setUrlRange(s, e) {
    const u = new URL(window.location.href);
    if (s && e) {
      u.searchParams.set('start', s);
      u.searchParams.set('end', e);
    } else {
      u.searchParams.delete('start');
      u.searchParams.delete('end');
    }
    window.location.href = u.toString();
  }

  function ymd(d) {
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2,'0');
    const dd = String(d.getDate()).padStart(2,'0');
    return `${yyyy}-${mm}-${dd}`;
  }

  if (urlStart && urlEnd) {
    document.getElementById('startDate').value = urlStart;
    document.getElementById('endDate').value = urlEnd;
    if (rangeMetaEl) rangeMetaEl.textContent = `${urlStart} → ${urlEnd}`;
    setActive('custom');
  } else {
    // Default to month window shown by the Year/Month selectors
    const y0 = yearSel.value;
    const m0 = monthSel.value;
    const s0 = `${y0}-${String(m0).padStart(2,'0')}-01`;
    const e0 = `${y0}-${String(m0).padStart(2,'0')}-${String(daysInMonth(y0, m0)).padStart(2,'0')}`;
    document.getElementById('startDate').value = s0;
    document.getElementById('endDate').value = e0;
    if (rangeMetaEl) rangeMetaEl.textContent = `Month: ${s0} → ${e0}`;
    setActive('thismo');
  }

  // Period tab click behavior (sets URL start/end)
  document.querySelectorAll('#periodTabs .pill').forEach(p => {
    p.addEventListener('click', () => {
      const per = p.dataset.period;
      const y = Number(yearSel.value);
      const m = Number(monthSel.value);
      const today = new Date();

      if (per === 'custom') {
        setActive('custom');
        return;
      }

      if (per === 'thismo') {
        const s = `${y}-${String(m).padStart(2,'0')}-01`;
        const e = `${y}-${String(m).padStart(2,'0')}-${String(daysInMonth(y,m)).padStart(2,'0')}`;
        setUrlRange(s, e);
      }

      if (per === 'lastmo') {
        const dt = new Date(y, m-2, 1);
        const y2 = dt.getFullYear();
        const m2 = dt.getMonth()+1;
        const s = `${y2}-${String(m2).padStart(2,'0')}-01`;
        const e = `${y2}-${String(m2).padStart(2,'0')}-${String(daysInMonth(y2,m2)).padStart(2,'0')}`;
        setUrlRange(s, e);
      }

      if (per === 'yesterday') {
        const d = new Date(today.getFullYear(), today.getMonth(), today.getDate()-1);
        const s = ymd(d);
        setUrlRange(s, s);
      }

      if (per === '2w') {
        const d0 = new Date(today.getFullYear(), today.getMonth(), today.getDate()-13);
        setUrlRange(ymd(d0), ymd(today));
      }

      if (per === 'thiswk') {
        // Monday-start
        const dow = (today.getDay() + 6) % 7; // Mon=0
        const mon = new Date(today.getFullYear(), today.getMonth(), today.getDate()-dow);
        setUrlRange(ymd(mon), ymd(today));
      }
    });
  });

  async function load() {
    const y = yearSel.value;
    const m = monthSel.value;

    const rp = rangeParams();
    const salesUrl = `/api/metrics/sales?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`;
    const createdUrl = `/api/metrics/opportunities_created?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`;
    const ranUrl = `/api/metrics/opportunities_ran?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`;

    const demoBase = `/api/metrics/demo_rate?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`;

    const demoDoorsUrl = `${demoBase}&lead_source=Doors`;
    const demoSelfGenUrl = `${demoBase}&lead_source=Self%20Gen`;
    const demoVirtualUrl = `${demoBase}&lead_source=Phones`;
    const demo3plUrl = `${demoBase}&lead_source=3PL`;

    document.getElementById('totalSales').textContent = '…';
    document.getElementById('totalCreated').textContent = '…';
    document.getElementById('opp2prelim').textContent = '…';
    
    function pickLeadSource(d, leadSource) {
      if (!d) return { ran: 0, sit: 0, pct: null };
      const ranMap = (d.breakdowns && d.breakdowns.ran_by_lead_source) ? d.breakdowns.ran_by_lead_source : {};
      const sitMap = (d.breakdowns && d.breakdowns.sit_by_lead_source) ? d.breakdowns.sit_by_lead_source : {};
      const ran = Number(ranMap[leadSource] || 0);
      const sit = Number(sitMap[leadSource] || 0);
      const pct = ran > 0 ? (sit / ran) * 100 : null;
      return { ran, sit, pct };
    }
    document.getElementById('demoRateCompany').textContent = '…';
    document.getElementById('demoRateDoors').textContent = '…';
    document.getElementById('demoRateSelfGen').textContent = '…';
    document.getElementById('demoRateVirtual').textContent = '…';
    document.getElementById('demoRate3pl').textContent = '…';

    document.getElementById('demoRateCompanyCounts').textContent = 'Demos: … • Ran: …';
    document.getElementById('demoRateDoorsCounts').textContent = 'Demos: … • Ran: …';
    document.getElementById('demoRateSelfGenCounts').textContent = 'Demos: … • Ran: …';
    document.getElementById('demoRateVirtualCounts').textContent = 'Demos: … • Ran: …';
    document.getElementById('demoRate3plCounts').textContent = 'Demos: … • Ran: …';
    document.getElementById('opp2prelimMeta').textContent = '';

    document.getElementById('createdMeta').textContent = '';
    document.getElementById('salesByPipelineV').innerHTML = '<div class="skeleton">Loading…</div>';
    document.getElementById('salesByChannelV').innerHTML = '<div class="skeleton">Loading…</div>';


    document.getElementById('createdByLead').innerHTML = '<div class="skeleton">Loading…</div>';

    const [salesRes, createdRes, ranRes, demoRes, demoDoorsRes, demoSelfGenRes, demoVirtualRes, demo3plRes] = await Promise.all([
      fetch(salesUrl, { cache: 'no-store' }),
      fetch(createdUrl, { cache: 'no-store' }),
      fetch(ranUrl, { cache: 'no-store' }),
      fetch(demoBase, { cache: 'no-store' }),
      fetch(demoDoorsUrl, { cache: 'no-store' }),
      fetch(demoSelfGenUrl, { cache: 'no-store' }),
      fetch(demoVirtualUrl, { cache: 'no-store' }),
      fetch(demo3plUrl, { cache: 'no-store' })
    ]);

    if (!salesRes.ok) {
      document.getElementById('totalSales').textContent = 'ERR';
      document.getElementById('salesMeta').textContent = `Sales HTTP ${salesRes.status}`;
      return;
    }

    const salesData = await salesRes.json();
    const createdData = createdRes.ok ? await createdRes.json() : null;
    const ranData = ranRes.ok ? await ranRes.json() : null;
    const demoData = demoRes.ok ? await demoRes.json() : null;
    const demoDoorsData = demoDoorsRes.ok ? await demoDoorsRes.json() : null;
    const demoSelfGenData = demoSelfGenRes.ok ? await demoSelfGenRes.json() : null;
    const demoVirtualData = demoVirtualRes.ok ? await demoVirtualRes.json() : null;
    const demo3plData = demo3plRes.ok ? await demo3plRes.json() : null;

    document.getElementById('totalSales').textContent = salesData.result;
    document.getElementById('salesMeta').textContent = '';

    const b = (salesData.breakdowns || {});
    renderVertical(document.getElementById('salesByPipelineV'), b.sales_by_pipeline || {});
    renderVertical(document.getElementById('salesByChannelV'), b.sales_by_lead_gen_source || {});

    if (!createdData) {
      document.getElementById('createdMeta').textContent = `Opportunities Created HTTP ${createdRes.status}`;
      return;
    }

    document.getElementById('createdMeta').textContent = '';


    document.getElementById('totalCreated').textContent = createdData.result;

    const fmtPct = (d) => (d && typeof d.result !== 'undefined') ? `${Number(d.result).toFixed(1)}%` : '—';
    const fmtCounts = (d) => {
      if (!d) return 'Demos: — • Ran: —';
      const demos = (typeof d.sit_count !== 'undefined') ? Number(d.sit_count) : null;
      const ran = (typeof d.ran_count !== 'undefined') ? Number(d.ran_count) : null;
      const demosTxt = (demos === null || Number.isNaN(demos)) ? '—' : String(demos);
      const ranTxt = (ran === null || Number.isNaN(ran)) ? '—' : String(ran);
      return `Demos: ${demosTxt} • Ran: ${ranTxt}`;
    };

    document.getElementById('demoRateCompany').textContent = fmtPct(demoData);
    document.getElementById('demoRateDoors').textContent = fmtPct(demoDoorsData);
    document.getElementById('demoRateSelfGen').textContent = fmtPct(demoSelfGenData);
    document.getElementById('demoRateVirtual').textContent = fmtPct(demoVirtualData);
    document.getElementById('demoRate3pl').textContent = fmtPct(demo3plData);

    document.getElementById('demoRateCompanyCounts').textContent = fmtCounts(demoData);
    document.getElementById('demoRateDoorsCounts').textContent = fmtCounts(demoDoorsData);
    document.getElementById('demoRateSelfGenCounts').textContent = fmtCounts(demoSelfGenData);
    document.getElementById('demoRateVirtualCounts').textContent = fmtCounts(demoVirtualData);
    document.getElementById('demoRate3plCounts').textContent = fmtCounts(demo3plData);

    // Opp2Prelim = Sales / Opportunities Ran
    if (!ranData) {
      document.getElementById('opp2prelim').textContent = '—';
      document.getElementById('opp2prelimMeta').textContent = ''; // hidden in prod UI
    } else {
      const sales = Number(salesData.result || 0);
      const ran = Number(ranData.result || 0);
      const pct = ran > 0 ? (sales / ran) * 100 : null;
      document.getElementById('opp2prelim').textContent = pct === null ? '—' : `${pct.toFixed(1)}%`;
      document.getElementById('opp2prelimMeta').textContent = ''; // hidden in prod UI
    }



    const cb = (createdData.breakdowns || {});
    renderVertical(document.getElementById('createdByLead'), cb.created_by_lead_gen_source || {});
  }

  document.getElementById('apply').addEventListener('click', () => {
    const s = (document.getElementById('startDate').value || '').trim();
    const e = (document.getElementById('endDate').value || '').trim();
    const u = new URL(window.location.href);
    if (s && e) {
      u.searchParams.set('start', s);
      u.searchParams.set('end', e);
    } else {
      u.searchParams.delete('start');
      u.searchParams.delete('end');
    }
    window.location.href = u.toString();
  });

  document.getElementById('clearRange').addEventListener('click', () => {
    const u = new URL(window.location.href);
    u.searchParams.delete('start');
    u.searchParams.delete('end');
    window.location.href = u.toString();
  });

  load();
</script>
</body>
</html>"""

    return html.replace("__YEAR__", str(year)).replace("__MONTH__", str(month))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.utcnow()
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
