# -*- coding: utf-8 -*-

"""Vercel Python function: /api/daily_update

Daily Update dashboard for morning meetings.

Uses existing metric APIs with date-only window (America/New_York):
- /api/metrics/sales
- /api/metrics/opportunities_created
- /api/metrics/raydar_doors_knocked (includes FMA time on doors and knocks by time)
- /api/powerline_dashboard
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Daily Update</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;
      --pink: #ec4899;
      --pink2: #f472b6;
      --green: #00C853;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background: var(--bg); color: var(--text); }
    .wrap { padding: 22px; max-width: 1320px; margin: 0 auto; }

    .topbar {
      display:flex; align-items:flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap;
      padding: 18px 20px; border-radius: 14px; background: var(--card);
      border: 1px solid var(--border); box-shadow: var(--shadow);
    }

    .topbar > div { min-width: 0; }

    .title { font-size: 24px; font-weight: 950; color: #1a2b4a; letter-spacing: -0.02em; display:flex; align-items:center; gap:8px; }
    .sunLink { text-decoration:none; font-size:20px; line-height:1; color:#ffbe45; }
    .sunLink:hover { transform: translateY(-1px); }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px; width: 220px; border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

__DASHBOARD_NAV_CSS__
    .navbtn {
      display:inline-flex; align-items:center; padding: 9px 12px;
      border-radius: 12px; border: 1px solid var(--border);
      background: #fff; color: #1f2937; font-size: 13px; font-weight: 800; text-decoration:none;
    }
    .navbtn.active { background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color: #b80b66; }

    .filters { display:flex; align-items:flex-end; gap: 10px; flex-wrap: wrap; }
    .filters label { display:block; font-size: 12px; color: var(--muted); font-weight: 900; margin-bottom: 4px; }
    .mobileFilterToggle { display:none; background:#fff; color:#1f2937; border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:12px; font-weight:900; }
    .filters input[type=date] {
      border: 1px solid var(--border); border-radius: 10px; padding: 9px 10px; font-size: 13px; font-weight: 900; background:#fff;
    }
    .btn {
      display:inline-flex; align-items:center; justify-content:center;
      border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px;
      background:#fff; color:#334155; font-size: 12px; font-weight: 900; cursor:pointer;
      text-decoration:none;
    }
    .btn.primary { background: #0a7a34; border-color: #0a7a34; color: #fff; }

    .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap: 14px; margin-top: 14px; }
    .grid-5 { display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 14px; margin-top: 14px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow); }

    /* Card accents for quick visual grouping */
    .accent-sales { border-top: 4px solid #ef4444; background: linear-gradient(180deg, rgba(239,68,68,0.06), rgba(255,255,255,0)); }
    .accent-opps { border-top: 4px solid #2563eb; background: linear-gradient(180deg, rgba(37,99,235,0.06), rgba(255,255,255,0)); }
    .accent-raydar { border-top: 4px solid #7c3aed; background: linear-gradient(180deg, rgba(124,58,237,0.06), rgba(255,255,255,0)); }
    .accent-powerline { border-top: 4px solid #ec4899; background: linear-gradient(180deg, rgba(236,72,153,0.06), rgba(255,255,255,0)); }

    .card-title.sales { color:#b91c1c; }
    .card-title.opps { color:#1d4ed8; }
    .card-title.raydar { color:#6d28d9; }
    .card-title.powerline { color:#be185d; }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-12 { grid-column: span 12; }
    .activity-grid { align-items:stretch; }

    @media (max-width: 1200px) { .span-3, .span-4, .span-6 { grid-column: span 12; } .grid-5 { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 820px) {
      .wrap { padding: 12px; }
      .topbar { padding: 12px; gap: 10px; }
      .title { font-size: 20px; }
      .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; -webkit-overflow-scrolling:touch; }
      .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; }
      .mobileFilterToggle { display:inline-flex; align-items:center; justify-content:center; }
      .filters { display:none; width:100%; grid-template-columns: repeat(2, minmax(0,1fr)); gap:8px; }
      body.filters-open .filters { display:grid; }
      .filters input[type=date], .filters .btn, .filters button { width:100%; }
      .kpi-card-center .kpi { font-size: 48px; }
      .card { padding: 12px; }
    }
    @media (max-width: 760px) { .grid-5 { grid-template-columns: 1fr; } }

    .kpi-label { color: var(--muted); font-size: 12px; font-weight: 900; }
    .kpi { margin-top: 4px; font-size: 36px; font-weight: 950; }
    .kpi-sub { margin-top: 6px; font-size: 12px; color: var(--muted2); }

    .kpi-card-center { text-align: center; display:flex; flex-direction:column; justify-content:center; min-height: 118px; }
    .kpi-card-center .kpi-label { text-align:center; }
    .kpi-card-center .kpi { text-align:center; font-size: 56px; line-height: 1.0; margin-top: 8px; }

    .card-title { color: var(--muted); font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: .03em; }
    .row-title {
      margin-top: 18px;
      text-align: center;
      font-size: 20px;
      font-weight: 900;
      color: #1f2937;
      letter-spacing: .01em;
    }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom: 1px solid var(--border); padding: 8px; font-size: 13px; text-align: left; }
    th { color: var(--muted); font-weight: 950; }
    td { color: #0f172a; font-weight: 800; }
    /* Increase readability of names in table first column */
    th:first-child { font-size: 14px; }
    td:first-child { font-size: 16px; font-weight: 900; }
    td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }

    .muted { color: var(--muted2); }

    .knock-chart-host { position: relative; min-height: 80px; }
    .knock-legend-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .knock-legend {
      display: inline-flex; align-items: center; gap: 6px;
      border: 1px solid var(--border); background: #fff; color: #1f2937;
      border-radius: 999px; padding: 5px 10px; min-height: 32px;
      font: 800 12px/1.2 inherit; cursor: pointer;
    }
    .knock-legend.off { opacity: 0.42; }
    .knock-legend.off span { text-decoration: line-through; }
    .knock-legend.dim { opacity: 0.45; }
    .knock-legend:focus-visible { outline: 2px solid #26d9eb; outline-offset: 2px; }
    .knock-chart-scroll { width: 100%; overflow-x: auto; margin-top: 8px; -webkit-overflow-scrolling: touch; }
    .knock-chart-svg { display: block; height: 320px; }
    .knock-chart-svg .axis { fill: #64748b; }
    .knock-chart-svg .grid { stroke: #eef2f7; }
    .knock-chart-svg .baseline { stroke: #cbd5e1; }
    .knock-chart-tip {
      position: absolute; z-index: 5; pointer-events: none;
      background: #0f172a; color: #fff; border-radius: 8px;
      padding: 7px 9px; font-size: 12px; font-weight: 700; line-height: 1.35;
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.28); white-space: nowrap;
    }
    body.oc-root .knock-legend {
      background: #102e46; color: #f1f6ff; border-color: #2b4e66;
    }
    body.oc-root .knock-chart-svg .axis { fill: #91abc0; }
    body.oc-root .knock-chart-svg .grid { stroke: #2b4e66; }
    body.oc-root .knock-chart-svg .baseline { stroke: #7ea3ba; }
    body.oc-root .knock-chart-tip {
      background: #061727; color: #f1f6ff; border: 1px solid #4d7894;
    }
    @media (max-width: 820px) {
      .knock-chart-svg { height: 280px; }
    }

    /* Spotlight mode for meeting walkthrough */
    .card.focusable { cursor: zoom-in; transition: box-shadow .18s ease, opacity .18s ease; }
    .card.focusable:hover { box-shadow: 0 10px 26px rgba(2, 6, 23, 0.12); }
    #spotlightBackdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(2, 6, 23, 0.68);
      z-index: 900;
      backdrop-filter: blur(3px);
    }
    body.spotlight-on #spotlightBackdrop { display: block; }
    body.spotlight-on .card:not(.spotlight) { opacity: 0.10; filter: blur(1px); }
    .card.spotlight {
      position: fixed;
      left: 50%;
      top: 50%;
      width: min(97vw, 1560px);
      max-height: 92vh;
      overflow: auto;
      transform: translate(-50%, -50%);
      z-index: 1000;
      opacity: 1 !important;
      cursor: zoom-out;
      background: #ffffff !important;
      border: 2px solid #0f172a !important;
      box-shadow: 0 28px 80px rgba(2, 6, 23, 0.55);
      padding: 22px 24px;
    }
    .card.spotlight .card-title { font-size: 18px !important; letter-spacing: 0 !important; text-transform: none !important; }
    .card.spotlight .kpi-label { font-size: 16px !important; }
    .card.spotlight .kpi { font-size: 64px !important; line-height: 1.05; }
    .card.spotlight .kpi-sub { font-size: 16px !important; }
    .card.spotlight table th, .card.spotlight table td, .card.spotlight .card-title, .card.spotlight .kpi-label, .card.spotlight .kpi, .card.spotlight .kpi-sub {
      color: #0f172a !important;
    }
    .card.spotlight table th { font-size: 16px !important; padding: 12px 10px !important; background: #f8fafc !important; }
    .card.spotlight table td { font-size: 20px !important; padding: 12px 10px !important; font-weight: 900 !important; }

  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Daily Dashboard <a class=\"sunLink\" href=\"/api/morning_brief\" title=\"Morning Brief\">☀️</a></div>
        <div class=\"subtitle\">Morning meeting snapshot across GHL and Raydar</div>
        <div class=\"pinkline\"></div>
__DASHBOARD_NAV_HTML__
      </div>

      <div>
        <button id=\"mobileFilterToggle\" class=\"mobileFilterToggle\" style=\"margin-bottom:8px\">Filters</button>
        <div class=\"filters\">
          <div>
            <label>Start</label>
            <input id=\"startDate\" type=\"date\" />
          </div>
          <div>
            <label>End</label>
            <input id=\"endDate\" type=\"date\" />
          </div>
          <button class=\"btn primary\" id=\"applyBtn\">Apply</button>
          <button class=\"btn\" id=\"yesterdayBtn\">Yesterday</button>
          <button class=\"btn\" id=\"todayBtn\">Today</button>
        </div>
        <div class=\"kpi-sub\" id=\"status\" style=\"margin-top:8px\">Loading…</div>
        <div class=\"kpi-sub\" style=\"margin-top:4px\">Tip: click any card to spotlight it for discussion (Esc to close).</div>
      </div>
    </div>

    <div class="row-title">Sales Data</div>
    <div class="grid">
      <div class="card span-3 accent-sales kpi-card-center">
        <div class="kpi-label">Sales (GHL)</div>
        <div class="kpi" id="kpiSales">—</div>
      </div>
      <div class="card span-3 accent-sales">
        <div class="card-title sales">Sales by Owner</div>
        <div id="tblSalesOwner"></div>
      </div>
      <div class="card span-3 accent-sales">
        <div class="card-title sales">Sales by Setter Last Name</div>
        <div id="tblSalesSetter"></div>
      </div>
      <div class="card span-3 accent-sales">
        <div class="card-title sales">Sales by Lead Gen Source</div>
        <div id="tblSalesLead"></div>
      </div>
    </div>

    <div class="row-title">Lead Generation</div>
    <div class="grid-5">
      <div class="card accent-opps kpi-card-center">
        <div class="kpi-label">Opportunities Created</div>
        <div class="kpi" id="kpiOpps">—</div>
        <div class="kpi-label" id="kpiOppsOther" style="display:none"></div>
      </div>
      <div class="card accent-opps kpi-card-center">
        <div class="kpi-label">Door Opportunities</div>
        <div class="kpi" id="kpiOppsDoors">—</div>
      </div>
      <div class="card accent-opps kpi-card-center">
        <div class="kpi-label">Self Gen Opportunities</div>
        <div class="kpi" id="kpiOppsSelfGen">—</div>
      </div>
      <div class="card accent-opps kpi-card-center">
        <div class="kpi-label">3PL/Inbound Opportunities</div>
        <div class="kpi" id="kpiOpps3pl">—</div>
      </div>
      <div class="card accent-opps kpi-card-center">
        <div class="kpi-label">Sweeper/Rehash/Virtual Opportunities</div>
        <div class="kpi" id="kpiOppsVirtual">—</div>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3 accent-opps">
        <div class="card-title opps">Doors Opps Created</div>
        <div id="tblOppsDoorsSetter"></div>
      </div>
      <div class="card span-3 accent-opps">
        <div class="card-title opps">Self Gen Opps Created</div>
        <div id="tblOppsSelfSetter"></div>
      </div>
      <div class="card span-3 accent-opps">
        <div class="card-title opps">3PL/Inbound Opps Created</div>
        <div id="tblOpps3plSetter"></div>
      </div>
      <div class="card span-3 accent-opps">
        <div class="card-title opps">Sweeper/Rehash/Virtual Opps Created</div>
        <div id="tblOppsVirtualSetter"></div>
      </div>
    </div>

    <div class="row-title">Activity</div>
    <div class="grid activity-grid">
      <div class="card span-6 accent-raydar">
        <div class="card-title raydar">Door Knocks by Raydar User</div>
        <div id="tblKnocks"></div>
      </div>
      <div class="card span-6 accent-raydar">
        <div class="card-title raydar">FMA Time on Doors</div>
        <div class="kpi-sub">First door knocked to last door knocked</div>
        <div id="tblTimeOnDoors"></div>
      </div>
      <div class="card span-12 accent-raydar">
        <div class="card-title raydar">FMA Knocks by Time</div>
        <div class="kpi-sub">Counted knocks in each 30-minute block, Eastern Time. A quiet block is zero, not a running total.</div>
        <div id="knockTimeChart" class="knock-chart-host"><div class="muted" style="margin-top:8px">Loading…</div></div>
      </div>
      <div class="card span-6 accent-powerline">
        <div class="card-title powerline">Powerline Calls by User</div>
        <div id="tblPowerline"></div>
      </div>
    </div>
  </div>

  <div id=\"spotlightBackdrop\"></div>

<script>
  const url = new URL(window.location.href);

  function nyYmd(d = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/New_York',
      year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(d);
    const get = (t) => parts.find(p => p.type === t)?.value;
    return `${get('year')}-${get('month')}-${get('day')}`;
  }

  function ymdAddDays(ymd, deltaDays) {
    const [y,m,d] = ymd.split('-').map(x => parseInt(x, 10));
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + deltaDays);
    const y2 = dt.getUTCFullYear();
    const m2 = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const d2 = String(dt.getUTCDate()).padStart(2, '0');
    return `${y2}-${m2}-${d2}`;
  }

  function setRange(start, end) {
    url.searchParams.set('start', start);
    url.searchParams.set('end', end);
    window.location.href = url.toString();
  }

  function numberFmt(v) {
    const n = Number(v || 0);
    return Number.isFinite(n) ? n.toLocaleString() : '0';
  }

  let spotlightCard = null;
  function closeSpotlight() {
    if (!spotlightCard) return;
    spotlightCard.classList.remove('spotlight');
    spotlightCard = null;
    document.body.classList.remove('spotlight-on');
  }

  function openSpotlight(card) {
    if (spotlightCard === card) {
      closeSpotlight();
      return;
    }
    if (spotlightCard) spotlightCard.classList.remove('spotlight');
    spotlightCard = card;
    card.classList.add('spotlight');
    document.body.classList.add('spotlight-on');
  }

  function wireSpotlight() {
    document.querySelectorAll('.card').forEach((card) => {
      card.classList.add('focusable');
      card.addEventListener('click', (ev) => {
        if (ev.target.closest('a,button,input,select,label,.knock-chart-host')) return;
        openSpotlight(card);
      });
    });

    const backdrop = document.getElementById('spotlightBackdrop');
    if (backdrop) backdrop.addEventListener('click', closeSpotlight);
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') closeSpotlight();
    });
  }

  function renderKVTable(containerId, obj, valueLabel = 'Count') {
    const el = document.getElementById(containerId);
    const rows = Object.entries(obj || {}).sort((a,b) => (Number(b[1]||0) - Number(a[1]||0)) || String(a[0]).localeCompare(String(b[0])));
    if (!rows.length) {
      el.innerHTML = `<div class=\"muted\" style=\"margin-top:8px\">No rows</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>Name</th><th class=\"num\">${valueLabel}</th></tr></thead>
        <tbody>
          ${rows.map(([k,v]) => `<tr><td>${k || '—'}</td><td class=\"num\">${numberFmt(v)}</td></tr>`).join('')}
        </tbody>
      </table>
    `;
  }

  function formatDoorDuration(seconds) {
    const n = Number(seconds);
    if (!Number.isFinite(n)) return '—';
    const total = Math.max(0, Math.floor(n));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return `${hours}h ${String(minutes).padStart(2, '0')}m`;
  }

  function renderTimeOnDoorsTable(containerId, rows) {
    const el = document.getElementById(containerId);
    // Server sorts by time on doors descending, then knocks, then name.
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class=\"muted\" style=\"margin-top:8px\">No rows</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th class=\"num\">Time on doors</th>
            <th class=\"num\">Knocks</th>
          </tr>
        </thead>
        <tbody>
          ${list.map((r) => `<tr><td>${r?.name || '—'}</td><td class=\"num\">${r?.duration || formatDoorDuration(r?.seconds)}</td><td class=\"num\">${numberFmt(r?.knocks)}</td></tr>`).join('')}
        </tbody>
      </table>
    `;
  }

  function renderPowerlineTable(containerId, rows, emptyMessage = 'No rows') {
    const el = document.getElementById(containerId);
    const list = Array.isArray(rows)
      ? rows
          .map((r) => ({
            user: String(r?.label || r?.agent || '—'),
            calls: Number(r?.call_attempts || 0),
          }))
          .sort((a, b) => (b.calls - a.calls) || a.user.localeCompare(b.user))
      : [];
    if (!list.length) {
      el.innerHTML = `<div class=\"muted\" style=\"margin-top:8px\">${emptyMessage}</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>User</th>
            <th class=\"num\">Calls</th>
          </tr>
        </thead>
        <tbody>
          ${list.map(r => `<tr><td>${r.user}</td><td class=\"num\">${numberFmt(r.calls)}</td></tr>`).join('')}
        </tbody>
      </table>
    `;
  }

  // Paul Tol bright, then a second pass with dashes so 8+ FMAs stay distinct.
  const KNOCK_LINE_COLORS = ['#4477AA', '#EE6677', '#228833', '#CCBB44', '#66CCEE', '#AA3377', '#44AA99'];
  const KNOCK_LINE_DASHES = ['', '7 4', '2 3', '10 3 2 3'];
  let knockTimePayload = null;
  let knockTimeReady = false;
  const knockTimeHidden = new Set();
  let knockRenderWidth = -1;

  function knockLineStyle(index) {
    return {
      color: KNOCK_LINE_COLORS[index % KNOCK_LINE_COLORS.length],
      dash: KNOCK_LINE_DASHES[Math.floor(index / KNOCK_LINE_COLORS.length) % KNOCK_LINE_DASHES.length],
    };
  }

  function escAttr(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function knockTickStep(max) {
    if (max <= 4) return 1;
    const raw = max / 4;
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const err = raw / pow;
    const nice = err <= 1 ? 1 : err <= 2 ? 2 : err <= 5 ? 5 : 10;
    return nice * pow;
  }

  function hideKnockTip() {
    const tip = document.getElementById('knockTimeTip');
    if (tip) tip.hidden = true;
  }

  function showKnockTip(dot) {
    const tip = document.getElementById('knockTimeTip');
    const host = document.getElementById('knockTimeChart');
    if (!tip || !host || !dot) return;
    const name = dot.getAttribute('data-name') || '—';
    const label = dot.getAttribute('data-label') || '';
    const count = Number(dot.getAttribute('data-count') || 0);
    const color = dot.getAttribute('data-color') || '#fff';
    const noun = count === 1 ? 'knock' : 'knocks';
    tip.innerHTML = `<div style="color:${escAttr(color)};font-weight:900">${escAttr(name)}</div><div>${escAttr(label)}</div><div>${count.toLocaleString()} ${noun}</div>`;
    tip.hidden = false;
    const hostBox = host.getBoundingClientRect();
    const dotBox = dot.getBoundingClientRect();
    const tipWidth = tip.offsetWidth || 120;
    let left = dotBox.left - hostBox.left + (dotBox.width / 2);
    left = Math.min(Math.max(left, tipWidth / 2 + 6), Math.max(tipWidth / 2 + 6, hostBox.width - tipWidth / 2 - 6));
    tip.style.left = `${left}px`;
    const above = dotBox.top - hostBox.top;
    if (above < 78) {
      tip.style.top = `${above + dotBox.height + 8}px`;
      tip.style.transform = 'translate(-50%, 0)';
    } else {
      tip.style.top = `${above - 8}px`;
      tip.style.transform = 'translate(-50%, -100%)';
    }
  }

  function applyKnockHighlight(name) {
    const host = document.getElementById('knockTimeChart');
    if (!host) return;
    host.querySelectorAll('.knock-series').forEach((node) => {
      const match = !name || node.getAttribute('data-name') === name;
      node.style.opacity = match ? '1' : '0.16';
    });
    host.querySelectorAll('.knock-legend').forEach((btn) => {
      const match = !name || btn.getAttribute('data-name') === name;
      btn.classList.toggle('dim', !!name && !match);
    });
  }

  function renderKnockTimeChart(force) {
    const host = document.getElementById('knockTimeChart');
    if (!host) return;
    if (!knockTimeReady && !force) return;
    const width = Math.max(280, host.clientWidth || 640);
    if (!force && width === knockRenderWidth && host.dataset.drawn === '1') return;
    knockRenderWidth = width;

    const payload = knockTimePayload || {};
    const buckets = Array.isArray(payload.buckets) ? payload.buckets : [];
    const series = Array.isArray(payload.series) ? payload.series : [];
    if (!buckets.length || !series.length) {
      host.dataset.drawn = '1';
      host.innerHTML = '<div class="muted" style="margin-top:8px">No knocks in this window</div>';
      return;
    }

    const styles = series.map((_, index) => knockLineStyle(index));
    const visible = series.map((row) => !knockTimeHidden.has(String(row?.name || '')));
    let max = 0;
    series.forEach((row, index) => {
      if (!visible[index]) return;
      (row.counts || []).forEach((value) => {
        const count = Number(value || 0);
        if (count > max) max = count;
      });
    });
    const step = knockTickStep(max);
    let yMax = Math.max(step, Math.ceil(max / step) * step);
    if (yMax === max) yMax += step;

    const n = buckets.length;
    const margin = { l: 48, r: 18, t: 12, b: 96 };
    const narrow = width < 720;
    const plotW = narrow ? Math.max(width, n * 72 + margin.l + margin.r) : width;
    const height = 320;
    const innerW = plotW - margin.l - margin.r;
    const innerH = height - margin.t - margin.b;
    const xAt = (index) => margin.l + (n <= 1 ? innerW / 2 : (index / (n - 1)) * innerW);
    const yAt = (value) => margin.t + innerH - (Number(value || 0) / yMax) * innerH;

    let grid = '';
    const tickCount = Math.round(yMax / step);
    for (let tick = 0; tick <= tickCount; tick += 1) {
      const value = tick * step;
      const y = yAt(value);
      const strokeClass = value === 0 ? 'baseline' : 'grid';
      grid += `<line class="${strokeClass}" x1="${margin.l}" y1="${y.toFixed(1)}" x2="${plotW - margin.r}" y2="${y.toFixed(1)}" />`;
      grid += `<text class="axis" x="${margin.l - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="12">${Math.round(value)}</text>`;
    }

    const gap = n <= 1 ? innerW : innerW / (n - 1);
    const labelStep = gap >= 78 ? 1 : Math.max(1, Math.ceil(78 / gap));
    const labelY = margin.t + innerH + 14;
    let xlabels = '';
    for (let index = 0; index < n; index += 1) {
      if (index % labelStep !== 0 && index !== n - 1) continue;
      const x = xAt(index);
      const label = escAttr((buckets[index] && buckets[index].label) || '');
      const anchor = index === 0 ? 'start' : 'end';
      xlabels += `<text class="axis" text-anchor="${anchor}" transform="rotate(-40 ${x.toFixed(1)} ${labelY})" x="${x.toFixed(1)}" y="${labelY}" font-size="12">${label}</text>`;
    }

    let paths = '';
    series.forEach((row, index) => {
      if (!visible[index]) return;
      const style = styles[index];
      const counts = Array.isArray(row.counts) ? row.counts : [];
      const name = String(row?.name || '—');
      let d = '';
      let dots = '';
      for (let point = 0; point < n; point += 1) {
        const value = Number(counts[point] || 0);
        const x = xAt(point).toFixed(1);
        const y = yAt(value).toFixed(1);
        d += `${point === 0 ? 'M' : 'L'}${x} ${y}`;
        const bucketLabel = (buckets[point] && buckets[point].label) || '';
        dots += `<circle class="knock-dot" cx="${x}" cy="${y}" r="8" fill="transparent" data-name="${escAttr(name)}" data-label="${escAttr(bucketLabel)}" data-count="${value}" data-color="${style.color}"><title>${escAttr(name)} — ${escAttr(bucketLabel)} — ${value}</title></circle>`;
        dots += `<circle cx="${x}" cy="${y}" r="3.4" fill="${style.color}" pointer-events="none"></circle>`;
      }
      const dash = style.dash ? ` stroke-dasharray="${style.dash}"` : '';
      paths += `<g class="knock-series" data-name="${escAttr(name)}"><path d="${d}" fill="none" stroke="${style.color}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"${dash}></path>${dots}</g>`;
    });

    const legend = series.map((row, index) => {
      const style = styles[index];
      const name = String(row?.name || '—');
      const dash = style.dash ? ` stroke-dasharray="${style.dash}"` : '';
      const off = visible[index] ? '' : ' off';
      return `<button type="button" class="knock-legend${off}" data-name="${escAttr(name)}" aria-pressed="${visible[index] ? 'true' : 'false'}"><svg width="26" height="10" aria-hidden="true" focusable="false"><line x1="1" y1="5" x2="25" y2="5" stroke="${style.color}" stroke-width="3" stroke-linecap="round"${dash}></line></svg><span>${escAttr(name)}</span></button>`;
    }).join('');
    const hiddenNote = visible.some(Boolean) ? '' : '<div class="muted" style="margin-top:6px">Every FMA is hidden. Select a name to show that line.</div>';
    const scrollWidth = plotW > width + 1 ? String(plotW) : '100%';

    host.dataset.drawn = '1';
    host.innerHTML = `
      <div class="knock-legend-row" role="group" aria-label="FMAs">${legend}</div>
      ${hiddenNote}
      <div class="knock-chart-scroll" onscroll="hideKnockTip()">
        <svg class="knock-chart-svg lineChart" viewBox="0 0 ${plotW} ${height}" width="${scrollWidth}" height="320" role="img" aria-label="FMA knocks by time of day">
          ${grid}${paths}${xlabels}
        </svg>
      </div>
      <div id="knockTimeTip" class="knock-chart-tip" hidden></div>
    `;
  }

  function bindKnockTimeChart() {
    const host = document.getElementById('knockTimeChart');
    if (!host || host.dataset.bound === '1') return;
    host.dataset.bound = '1';
    host.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.knock-legend');
      if (!btn) return;
      ev.preventDefault();
      ev.stopPropagation();
      const name = btn.getAttribute('data-name') || '';
      if (knockTimeHidden.has(name)) knockTimeHidden.delete(name);
      else knockTimeHidden.add(name);
      renderKnockTimeChart(true);
    });
    host.addEventListener('mouseover', (ev) => {
      const btn = ev.target.closest('.knock-legend');
      if (!btn || btn.classList.contains('off')) return;
      applyKnockHighlight(btn.getAttribute('data-name'));
    });
    host.addEventListener('mouseout', (ev) => {
      const btn = ev.target.closest('.knock-legend');
      if (!btn) return;
      const next = ev.relatedTarget && ev.relatedTarget.closest ? ev.relatedTarget.closest('.knock-legend') : null;
      if (next) return;
      applyKnockHighlight(null);
    });
    host.addEventListener('pointerover', (ev) => {
      const dot = ev.target.closest('.knock-dot');
      if (dot) showKnockTip(dot);
    });
    host.addEventListener('pointerdown', (ev) => {
      const dot = ev.target.closest('.knock-dot');
      if (dot) showKnockTip(dot);
    });
    host.addEventListener('pointerout', (ev) => {
      if (!ev.target.closest('.knock-dot')) return;
      const next = ev.relatedTarget;
      if (next && next.closest && next.closest('.knock-dot')) return;
      hideKnockTip();
    });
    if (window.ResizeObserver) {
      let frame = 0;
      new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => renderKnockTimeChart(false));
      }).observe(host);
    }
  }

  function mergeCountMaps(...maps) {
    const merged = {};
    for (const map of maps) {
      for (const [key, value] of Object.entries(map || {})) {
        const label = String(key || '—').trim() || '—';
        merged[label] = (merged[label] || 0) + Number(value || 0);
      }
    }
    return merged;
  }

  async function fetchJson(u) {
    let res;
    try {
      res = await fetch(u);
    } catch (error) {
      if (error && (error.name === 'AbortError' || error.name === 'TimeoutError')) return null;
      throw error;
    }
    if (!res) return null;
    if (!res.ok) throw new Error(`${u} → ${res.status}`);
    return await res.json();
  }

  async function load() {
    const start = url.searchParams.get('start');
    const end = url.searchParams.get('end');

    // Default to yesterday if not provided.
    if (!start || !end) {
      const today = nyYmd(new Date());
      const y = ymdAddDays(today, -1);
      setRange(y, y);
      return;
    }

    document.getElementById('startDate').value = start;
    document.getElementById('endDate').value = end;
    document.getElementById('status').textContent = `Window: ${start} → ${end} (America/New_York)`;
    renderPowerlineTable('tblPowerline', [], 'Loading…');

    const q = `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=json`;

    // Start Powerline immediately so the slowest activity card does not lag behind the rest of the dashboard.
    const powerlinePromise = fetchJson(`/api/powerline_dashboard?${q}`)
      .then((powerline) => ({ powerline }))
      .catch((powerlineErr) => ({ powerlineErr }));

    try {
      const [sales, opps, knocks] = await Promise.all([
        fetchJson(`/api/metrics/sales?${q}`),
        fetchJson(`/api/metrics/opportunities_created?${q}`),
        fetchJson(`/api/metrics/raydar_doors_knocked?${q}`),
      ]);
      if (!sales || !opps || !knocks) return;

      document.getElementById('kpiSales').textContent = numberFmt(sales.result);
      document.getElementById('kpiOpps').textContent = numberFmt(opps.result);

      // One bucket per opp (server side) so the boxes add up to Opportunities Created.
      const buckets = opps?.breakdowns?.created_by_leadgen_bucket || {};
      const bucketSetters = opps?.breakdowns?.created_by_leadgen_bucket_setter || {};
      const bucketVal = (k) => Number(buckets[k] || 0);
      document.getElementById('kpiOppsDoors').textContent = numberFmt(bucketVal('Doors'));
      document.getElementById('kpiOppsSelfGen').textContent = numberFmt(bucketVal('Self Gen'));
      document.getElementById('kpiOpps3pl').textContent = numberFmt(bucketVal('3PL/Inbound'));
      document.getElementById('kpiOppsVirtual').textContent = numberFmt(bucketVal('Sweeper/Rehash/Virtual'));
      const otherEl = document.getElementById('kpiOppsOther');
      if (bucketVal('Other') > 0) {
        otherEl.textContent = `incl. ${numberFmt(bucketVal('Other'))} with no lead gen source`;
        otherEl.style.display = '';
      } else {
        otherEl.style.display = 'none';
      }

      renderKVTable('tblSalesOwner', sales?.breakdowns?.sales_by_owner || {}, 'Sales');
      renderKVTable('tblSalesSetter', sales?.breakdowns?.sales_by_setter_last_name || {}, 'Sales');
      renderKVTable('tblSalesLead', sales?.breakdowns?.sales_by_lead_gen_source || {}, 'Sales');

      renderKVTable('tblOppsDoorsSetter', bucketSetters['Doors'] || {}, 'Opps');
      renderKVTable('tblOppsSelfSetter', bucketSetters['Self Gen'] || {}, 'Opps');
      renderKVTable('tblOpps3plSetter', bucketSetters['3PL/Inbound'] || {}, 'Opps');
      renderKVTable('tblOppsVirtualSetter', bucketSetters['Sweeper/Rehash/Virtual'] || {}, 'Opps');

      // Match FMA schema: use knocks_by_actor and map actor id -> Raydar user name.
      const knocksByActor = (knocks && knocks.breakdowns && knocks.breakdowns.knocks_by_actor) ? knocks.breakdowns.knocks_by_actor : {};
      const topKnockers = Array.isArray(knocks?.top_knockers) ? knocks.top_knockers : [];
      const actorNameMap = { ...((knocks && knocks.users) ? knocks.users : {}) };
      for (const r of topKnockers) {
        const id = String(r.userId || '').trim();
        const nm = String(r.name || '').trim();
        if (id) actorNameMap[id] = nm || id;
      }
      const knocksByName = {};
      for (const [actorId, v] of Object.entries(knocksByActor || {})) {
        const name = actorNameMap[String(actorId)] || String(actorId);
        knocksByName[name] = (knocksByName[name] || 0) + Number(v || 0);
      }
      renderKVTable('tblKnocks', knocksByName, 'Knocks');
      renderTimeOnDoorsTable('tblTimeOnDoors', knocks?.time_on_doors || []);
      knockTimePayload = knocks?.knocks_by_time || { buckets: [], series: [] };
      knockTimeReady = true;
      renderKnockTimeChart(true);

      const { powerline, powerlineErr } = await powerlinePromise;
      if (powerlineErr) {
        console.error(powerlineErr);
        renderPowerlineTable('tblPowerline', [], 'Powerline unavailable');
      } else {
        renderPowerlineTable('tblPowerline', powerline?.tables?.by_agent || []);
      }

      document.getElementById('status').textContent = `Loaded daily update for ${start} → ${end}`;
    } catch (e) {
      console.error(e);
      document.getElementById('status').textContent = `Error loading dashboard: ${String(e)}`;
      if (!knockTimeReady) {
        const chartHost = document.getElementById('knockTimeChart');
        if (chartHost) chartHost.innerHTML = '<div class="muted" style="margin-top:8px">Chart unavailable</div>';
      }
    }
  }

  document.getElementById('applyBtn').addEventListener('click', () => {
    const s = document.getElementById('startDate').value;
    const e = document.getElementById('endDate').value;
    if (s && e) setRange(s, e);
  });

  document.getElementById('yesterdayBtn').addEventListener('click', () => {
    const today = nyYmd(new Date());
    const y = ymdAddDays(today, -1);
    setRange(y, y);
  });

  document.getElementById('todayBtn').addEventListener('click', () => {
    const today = nyYmd(new Date());
    setRange(today, today);
  });

  const mobileFilterToggle = document.getElementById('mobileFilterToggle');
  if (mobileFilterToggle) {
    mobileFilterToggle.addEventListener('click', () => {
      document.body.classList.toggle('filters-open');
    });
  }

  wireSpotlight();
  bindKnockTimeChart();
  load();
</script>

  <a href="/api/settings#secret-lab" title="Secret Lab" aria-label="Secret Lab" style="position:fixed; right:12px; bottom:10px; z-index:9999; width:34px; height:34px; display:flex; align-items:center; justify-content:center; border-radius:999px; border:1px solid #d1d5db; background:rgba(255,255,255,.38); color:#475569; text-decoration:none; font-size:16px; backdrop-filter: blur(2px); opacity:.35;">🧪</a>
</body>
</html>
"""
HTML = HTML.replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css()).replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("daily_update"))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
