# -*- coding: utf-8 -*-

"""Vercel Python function: /api/fma_dashboard

FMA Dashboard (production)

Intent: mirror the Raydar "Team Performance" layout for canvassing/FMA lead gen.
Metric wiring will be added after schema is confirmed.

UI intent (Customer Insights production style):
- White cards on light gray background
- 3-column responsive grid
- Gradient accent line

NOTE: Metrics are placeholders until we finalize the Raydar/FMA metric schema.
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
  <title>Happy Solar — FMS Dashboard</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;

      /* Customer Insights vibe */
      --pink: #ec4899;
      --pink2: #f472b6;

      --blue: #3b82f6;
      --purple: #8b5cf6;
      --green: #10b981;
      --amber: #f59e0b;
      --cyan: #06b6d4;

      --shadow: 0 1px 3px rgba(17,24,39,0.06);
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
      box-shadow: var(--shadow);
    }

    .title {
      font-size: 22px;
      font-weight: 950;
      color: #1a2b4a;
      letter-spacing: -0.02em;
    }

    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px;
      width: 200px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
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
      border-color: rgba(236,72,153,0.45);
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }

    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .adminSettings {
      position: absolute;
      top: 16px;
      right: 18px;
    }

    .missingDisposTop {
      position: absolute;
      top: 16px;
      right: 158px;
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
      box-shadow: var(--shadow);
      min-height: 120px;
    }

    .card-header { display:flex; align-items:flex-start; justify-content: space-between; gap: 10px; }
    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .span-12 { grid-column: span 12; }
    .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; }
    .span-3 { grid-column: span 3; }

    @media (max-width: 980px) {
      .span-6, .span-4 { grid-column: span 12; }
      .span-3 { grid-column: span 6; }
    }
    @media (max-width: 560px) {
      .span-3 { grid-column: span 12; }
    }

    /* Raydar-like KPI cards */
    .kpiRow {
      display:flex;
      align-items:flex-end;
      justify-content: space-between;
      gap: 10px;
      margin-top: 10px;
    }

    .kpiVal {
      font-size: 36px;
      line-height: 1;
      font-weight: 950;
      letter-spacing: -0.02em;
      color: #0f172a;
    }

    .kpiVal.blue { color: #1d4ed8; }
    .kpiVal.purple { color: #6d28d9; }
    .kpiVal.green { color: #047857; }
    .kpiVal.amber { color: #b45309; }

    .kpiSub {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted2);
      font-weight: 800;
    }

    .pillbar {
      display:flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
      box-shadow: var(--shadow);
    }

    .pill {
      border: 1px solid var(--border);
      background: #f8fafc;
      color: #334155;
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 12px;
      font-weight: 900;
      cursor: pointer;
      user-select: none;
    }

    .pill.active {
      background: rgba(236,72,153,0.12);
      border-color: rgba(236,72,153,0.40);
      color: #b80b66;
    }

    /* Funnel */
    .funnelWrap { margin-top: 10px; }
    .funnelBar {
      display:grid;
      grid-template-columns: 1fr auto 0.4fr auto 0.2fr;
      align-items:center;
      gap: 10px;
      margin-top: 12px;
    }

    .seg {
      height: 46px;
      border-radius: 10px;
      display:flex;
      align-items:center;
      justify-content:center;
      color:#fff;
      font-weight: 950;
      letter-spacing: -0.01em;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
      white-space: nowrap;
      overflow:hidden;
      text-overflow: ellipsis;
      padding: 0 10px;
    }

    .seg.blue { background: rgba(59,130,246,0.92); }
    .seg.purple { background: rgba(139,92,246,0.92); }
    .seg.green { background: rgba(16,185,129,0.92); }

    .arrow { color: #94a3b8; font-weight: 900; }

    /* Top performers tables */
    .list {
      margin-top: 10px;
      display:flex;
      flex-direction: column;
      gap: 10px;
    }

    .row {
      display:flex;
      align-items:center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fff;
    }

    .left {
      display:flex;
      align-items:center;
      gap: 10px;
      min-width: 0;
    }

    .badge {
      width: 22px;
      height: 22px;
      border-radius: 999px;
      display:flex;
      align-items:center;
      justify-content:center;
      font-size: 12px;
      font-weight: 950;
      color: #0f172a;
      background: #eef2ff;
      border: 1px solid #e0e7ff;
      flex: 0 0 auto;
    }

    .name {
      font-weight: 900;
      color: #0f172a;
      font-size: 13px;
      overflow:hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .val {
      font-weight: 950;
      color: #0f172a;
      font-size: 14px;
    }

    .skeleton {
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg,#f1f5f9,#e2e8f0,#f1f5f9);
      background-size: 200% 100%;
      animation: sh 1.4s ease-in-out infinite;
    }

    @keyframes sh {
      0% { background-position: 0% 0%; }
      100% { background-position: -200% 0%; }
    }

    .note {
      color: var(--muted);
      font-size: 12px;
      margin-top: 10px;
      line-height: 1.35;
    }
  

    /* Mobile optimizations */
    @media (max-width: 820px) {
      .wrap { padding: 14px; }
      .topbar { padding: 14px 14px; }
      .title { font-size: 18px; }
      .navbtn { padding: 8px 10px; font-size: 12px; }
      .filters { gap: 8px; }
      .filter-label { font-size: 11px; }
      .kpi { font-size: 38px; }
      .card { padding: 14px 14px; }
      table { display: block; overflow-x: auto; white-space: nowrap; }
    }

    @media (max-width: 820px) {
      .grid { grid-template-columns: repeat(2, 1fr); }
      .card { min-height: 100px; }
      .kpi { font-size: 34px; }
      .span-12 { grid-column: span 2; }
    }

    @media (max-width: 520px) {
      .grid { grid-template-columns: 1fr; }
      .span-3, .span-4, .span-6, .span-8, .span-9, .span-12 { grid-column: span 12; }
      .adminSettings { top: 12px; right: 12px; }
      .missingDisposTop { top: 12px; right: 134px; }
    }
</style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">FMS Dashboard</div>
        <div class="subtitle">Team Performance — real-time setter metrics (Raydar-style cards)</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn active" href="/api/fma_dashboard">FMS dashboard</a>
          <a class="navbtn" href="/api/virtual_team_dashboard">Virtual Team</a>
        </div>
      </div>
      <div style="min-width:320px">
        <a class="navbtn missingDisposTop" href="/api/missing_dispos">Missing Dispos</a>
        <a class="navbtn adminSettings" href="/api/settings">Admin Settings</a>
        <div class="card-title">Custom Range (date-only)</div>
        <div class="meta">Overrides tabs when set</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; align-items:center">
          <input id="startDate" type="date" style="border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px;" />
          <input id="endDate" type="date" style="border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px;" />
          <button id="applyRange" style="background: var(--pink); border: 1px solid var(--pink); color:#fff; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900; cursor:pointer;">Apply</button>
          <button id="clearRange" style="background:#fff; border:1px solid var(--border); color:#334155; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900; cursor:pointer;">Clear</button>
        </div>
        <div class="meta" id="rangeMeta">Month view: __YEAR__-__MONTH__</div>
      </div>
    </div>

    <!-- Raydar-style period selector (UI only for now) -->
    <div class="pillbar" id="periodTabs">
      <div class="pill active" data-period="today">Today</div>
      <div class="pill" data-period="yesterday">Yesterday</div>
      <div class="pill" data-period="7d">7 Days</div>
      <div class="pill" data-period="thiswk">This Wk</div>
      <div class="pill" data-period="lastwk">Last Wk</div>
      <div class="pill" data-period="thismo">This Mo</div>
      <div class="pill" data-period="lastmo">Last Mo</div>
      <div class="pill" data-period="all">All</div>
    </div>

    <div class="grid">
      <!-- KPI row (Raydar-style cards) -->
      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Total Knocks</div>
          <div class="meta">(Dispositioned leads)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal" id="kpiKnocks">—</div>
        </div>
        <div class="kpiSub" id="kpiKnocksSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Convos</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal blue" id="kpiConvos">—</div>
        </div>
        <div class="kpiSub" id="kpiConvosSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Appts</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal purple" id="kpiAppts">—</div>
        </div>
        <div class="kpiSub" id="kpiApptsSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Appt % Knocks</div>
          <div class="meta">Appts / Knocks</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal amber" id="kpiApptPct">—</div>
        </div>
        <div class="kpiSub" id="kpiApptPctSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Go-Backs</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal green" id="kpiGobacks">—</div>
        </div>
        <div class="kpiSub" id="kpiGobacksSub">—</div>
      </div>

      <div class="card span-12">
        <div class="card-header">
          <div class="card-title">Conversion Funnel</div>
          <div class="meta">Knocks → Convos → Appts</div>
        </div>
        <div class="funnelWrap">
          <div class="funnelBar">
            <div class="seg blue" id="segKnocks">— Knocks</div>
            <div class="arrow">→</div>
            <div class="seg purple" id="segConvos">— Convos</div>
            <div class="arrow">→</div>
            <div class="seg green" id="segAppts">— Appts</div>
          </div>
          <div class="note" id="funnelNote">Metric schema pending for Convos/Appts. Knocks currently backed by Raydar dispositioned leads.</div>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Top Performers — Knocks</div>
          <div class="meta">Total knocks per user (claimedBy) for selected range</div>
        </div>
        <div class="list" id="topKnocks">
          <div class="row"><div class="left"><div class="badge">1</div><div class="name"><div class="skeleton" style="width:160px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">2</div><div class="name"><div class="skeleton" style="width:140px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">3</div><div class="name"><div class="skeleton" style="width:150px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Top Performers — Appointments</div>
          <div class="meta">(Placeholder until schema is finalized)</div>
        </div>
        <div class="list" id="topAppts">
          <div class="row"><div class="left"><div class="badge">1</div><div class="name"><div class="skeleton" style="width:160px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">2</div><div class="name"><div class="skeleton" style="width:140px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">3</div><div class="name"><div class="skeleton" style="width:150px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
        </div>
      </div>

            <div class="card span-12">
        <div class="card-header">
          <div>
            <div class="card-title">GHL — Demo Rate by Setter (Current Month)</div>
            <div class="meta">Opps Ran / Demos / Demo % (Sit / Ran)</div>
          </div>
          <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <div class="meta" style="margin-top:0">Lead Gen Source</div>
            <select id="setterTableLeadSource" style="border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900;">
              <option value="">All</option>
              <option value="Doors">Doors</option>
              <option value="Phones">Phones</option>
              <option value="3PL">3PL</option>
              <option value="Self Gen">Self Gen</option>
              <option value="none">none</option>
            </select>

            <div class="meta" style="margin-top:0">Start</div>
            <input id="setterTableStart" type="date" style="border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900;" />
            <div class="meta" style="margin-top:0">End</div>
            <input id="setterTableEnd" type="date" style="border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900;" />
            <button id="setterTableApply" style="background: var(--pink); border: 1px solid var(--pink); color:#fff; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900; cursor:pointer;">Apply</button>
            <button id="setterTableClear" style="background:#fff; border:1px solid var(--border); color:#334155; border-radius:10px; padding:8px 10px; font-size:13px; font-weight:900; cursor:pointer;">Clear</button>
          </div>
        </div>
        <div style="margin-top:10px; overflow:auto">
          <table style="width:100%; border-collapse: collapse;">
            <thead>
              <tr>
                <th style="text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Setter Last Name</th>
                <th style="text-align:right; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Knocks / Goal</th>
                <th style="text-align:right; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Appts Set / Goal</th>
                <th style="text-align:right; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Opps Ran</th>
                <th style="text-align:right; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Demos / Goal</th>
                <th style="text-align:right; padding:10px 8px; border-bottom:1px solid var(--border); color:var(--muted); font-size:12px; font-weight:900;">Demo %</th>
              </tr>
            </thead>
            <tbody id="setterDemoRows">
              <tr><td colspan="6" style="padding:12px 8px; color:var(--muted2);">Loading…</td></tr>
            </tbody>
            <tfoot id="setterDemoTotals">
              <tr>
                <td style="padding:10px 8px; font-weight:950;">TOTAL</td>
                <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
                <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
                <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
                <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
                <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

<div class="card span-12">
        <div class="card-title">Status</div>
        <div class="meta">
          UI is built to match Raydar. Next step: confirm metric definitions + exact field mappings (Knocks, Convos, Appts, Go-backs) and wire these cards.
        </div>
      </div>
    </div>
  </div>

<script>
  // Custom range persistence
  const rangeKey = 'fms_range_v1';

  // Keep range in URL too (so the date inputs always reflect current state)
  const pageUrl = new URL(window.location.href);
  const urlStart = pageUrl.searchParams.get('start') || '';
  const urlEnd = pageUrl.searchParams.get('end') || '';

  // Setter demo table range persistence (table-only)
  const setterRangeKey = 'fms_setter_table_range_v1';
  function getSetterRange() {
    try {
      const raw = localStorage.getItem(setterRangeKey);
      if (!raw) return null;
      const j = JSON.parse(raw);
      if (j && j.start && j.end) return j;
      return null;
    } catch { return null; }
  }
  function setSetterRange(r) {
    try { localStorage.setItem(setterRangeKey, JSON.stringify(r)); } catch {}
  }
  function clearSetterRange() {
    try { localStorage.removeItem(setterRangeKey); } catch {}
  }


  function getRange() {
    try {
      const raw = localStorage.getItem(rangeKey);
      if (!raw) return null;
      const j = JSON.parse(raw);
      if (j && j.start && j.end) return j;
      return null;
    } catch { return null; }
  }
  function setRange(r) {
    try { localStorage.setItem(rangeKey, JSON.stringify(r)); } catch {}
  }
  function clearRange() {
    try { localStorage.removeItem(rangeKey); } catch {}
  }

  // Sync date inputs from URL/localStorage and wire Apply/Clear buttons
  (function initRangeUI() {
    const startEl = document.getElementById('startDate');
    const endEl = document.getElementById('endDate');
    const metaEl = document.getElementById('rangeMeta');

    // prefer URL params when present
    if (urlStart && urlEnd) {
      if (startEl) startEl.value = urlStart;
      if (endEl) endEl.value = urlEnd;
      setRange({ start: urlStart, end: urlEnd });
      if (metaEl) metaEl.textContent = `Custom range: ${urlStart} → ${urlEnd}`;
      return;
    }

    const r = getRange();
    if (r && r.start && r.end) {
      if (startEl) startEl.value = r.start;
      if (endEl) endEl.value = r.end;
      if (metaEl) metaEl.textContent = `Custom range: ${r.start} → ${r.end}`;
    }
  })();

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

  const applyBtn = document.getElementById('applyRange');
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      const s = (document.getElementById('startDate').value || '').trim();
      const e = (document.getElementById('endDate').value || '').trim();
      if (s && e) {
        setRange({ start: s, end: e });
        setUrlRange(s, e);
      }
    });
  }

  const clearBtn = document.getElementById('clearRange');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      clearRange();
      setUrlRange('', '');
    });
  }

  // Period tabs: UI only (metric wiring comes after schema confirmation)
  document.querySelectorAll('#periodTabs .pill').forEach(p => {
    p.addEventListener('click', () => {
      document.querySelectorAll('#periodTabs .pill').forEach(x => x.classList.remove('active'));
      p.classList.add('active');
      // placeholder; will call metrics endpoint once defined
      load();
    });
  });

  function setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  }

  function renderTopList(containerId, rows) {
    const el = document.getElementById(containerId);
    if (!el) return;
    let html = '';
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      html += `
        <div class="row">
          <div class="left">
            <div class="badge">${i + 1}</div>
            <div class="name">${(r.name || '—')}</div>
          </div>
          <div class="val">${(typeof r.value !== 'undefined' ? r.value : '—')}</div>
        </div>`;
    }
    el.innerHTML = html;
  }

  async function load() {
    // For now, only Knocks is backed by Raydar (dispositioned leads).
    // We'll wire the rest after metric schema is confirmed.

    setText('kpiKnocks', '…');
    setText('kpiConvos', '—');
    setText('kpiAppts', '—');
    setText('kpiApptPct', '—');
    setText('kpiGobacks', '—');

    setText('kpiKnocksSub', 'Loading…');
    setText('kpiConvosSub', 'Schema pending');
    setText('kpiApptsSub', 'Schema pending');
    setText('kpiApptPctSub', 'Schema pending');
    setText('kpiGobacksSub', 'Schema pending');

    setText('segKnocks', '… Knocks');
    setText('segConvos', '— Convos');
    setText('segAppts', '— Appts');

    try {
      // Knocks (Doors Knocked) date filter is raydar_leads_v1.dispositionedAt (canonical).
      // Wire to the selected period tab.
      const active = document.querySelector('#periodTabs .pill.active');
      const period = active ? String(active.getAttribute('data-period') || '') : '';

      const y = __YEAR__;
      const m = __MONTH__;

      const r = getRange();
      const url = (r && r.start && r.end)
        ? `/api/metrics/raydar_doors_knocked?format=json&start=${encodeURIComponent(r.start)}&end=${encodeURIComponent(r.end)}`
        : (period
            ? `/api/metrics/raydar_doors_knocked?format=json&period=${encodeURIComponent(period)}`
            : `/api/metrics/raydar_doors_knocked?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`);

      const res = await fetch(url);
      const data = res.ok ? await res.json() : null;

      const knocks = data && typeof data.result !== 'undefined' ? Number(data.result) : null;
      setText('kpiKnocks', knocks === null ? '—' : String(knocks));

      const sub = data && data.window_start_local && data.window_end_local
        ? `Dispositioned leads (${data.window_start_local} → ${data.window_end_local})`
        : 'Dispositioned leads (dispositionedAt)';
      setText('kpiKnocksSub', sub);

      setText('segKnocks', `${knocks === null ? '—' : knocks} Knocks`);

      // Convos = homeowner conversations (Raydar disposition allowlist; Shade DQ excluded)
      const convos = (data && data.breakdowns && typeof data.breakdowns.convos_total !== 'undefined')
        ? Number(data.breakdowns.convos_total)
        : null;
      setText('kpiConvos', convos === null ? '—' : String(convos));
      setText('kpiConvosSub', 'Disposition allowlist (Shade DQ excluded)');



      // Appointments = Raydar leads with disposition name "Appointment Set" (case-insensitive)
      const appts = (data && data.breakdowns && typeof data.breakdowns.appointments_set_total !== 'undefined')
        ? Number(data.breakdowns.appointments_set_total)
        : null;

      setText('kpiAppts', appts === null ? '—' : String(appts));
      setText('kpiApptsSub', 'Disposition = Appointment Set');

      const pct = (appts !== null && knocks !== null && knocks > 0) ? (appts / knocks) * 100 : null;
      setText('kpiApptPct', pct === null ? '—' : `${pct.toFixed(1)}%`);
      setText('kpiApptPctSub', 'Appointments / Knocks');

      // Funnel (Convos still pending)
      setText('segConvos', `${convos === null ? '—' : convos} Convos`);
      setText('segAppts', `${appts === null ? '—' : appts} Appts`);

      const top = (data && Array.isArray(data.top_knockers)) ? data.top_knockers : [];
      renderTopList('topKnocks', top.slice(0, 10).map(r => ({ name: r.name || r.userId || '—', value: r.knocks })));

      // Top Performers — Appointments (GHL Opportunities Created by Setter Last Name)
      // NOTE: scope matches /api/metrics/opportunities_created (pipeline include/exclude rules).
      // Uses same window + lead source filter as the setter demo table.
      // Rendered later once opp-created breakdown is loaded.
      renderTopList('topAppts', [{ name: 'Loading…', value: '' }]);

      // --- GHL Demo Rate by Setter (current month) ---
      try {
        const lsEl = document.getElementById('setterTableLeadSource');
        const ls = lsEl ? String(lsEl.value || '') : '';
        const lsParam = ls ? `&lead_source=${encodeURIComponent(ls)}` : '';

        // Table-only custom date range (applies ONLY to the demo-rate-by-setter table)
        const srTable = getSetterRange();
        const rangeParam = (srTable && srTable.start && srTable.end)
          ? `&start=${encodeURIComponent(srTable.start)}&end=${encodeURIComponent(srTable.end)}`
          : '';

        // 1) GHL demo rate counts (opps ran + sit demos)
        const demoRes = await fetch(`/api/metrics/demo_rate?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${lsParam}${rangeParam}`);
        const demoData = demoRes.ok ? await demoRes.json() : null;
        const ranBy = (demoData && demoData.breakdowns && demoData.breakdowns.ran_by_setter_last_name) ? demoData.breakdowns.ran_by_setter_last_name : {};
        const sitBy = (demoData && demoData.breakdowns && demoData.breakdowns.sit_by_setter_last_name) ? demoData.breakdowns.sit_by_setter_last_name : {};

        // 2) Roster + goals for month (to pull goal values)
        const monthStr = `${y}-${String(m).padStart(2,'0')}`;
        const settingsRes = await fetch('/api/settings_api', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'bootstrap', month: monthStr }),
        });
        const settings = settingsRes.ok ? await settingsRes.json() : null;
        const roster = settings && Array.isArray(settings.roster_people) ? settings.roster_people : [];
        const goalsRows = settings && Array.isArray(settings.goals_for_month) ? settings.goals_for_month : [];

        const setterToPerson = {};
        const setterToRaydar = {};
        for (const r of roster) {
          // Do not filter by role here. If someone has a GHL setter last name mapping,
          // we should apply goals + Raydar actuals regardless of their role label.
          const sln = String(r.ghl_setter_last_name || '').trim();
          if (!sln) continue;
          setterToPerson[sln] = String(r.person_key || '');
          setterToRaydar[sln] = String(r.raydar_user_id || '');
        }

        const goalsByPerson = {};
        for (const gr of goalsRows) {
          const pk = String(gr.person_key || '');
          const metric = String(gr.metric || '');
          const value = Number(gr.value || 0);
          if (!pk || !metric) continue;
          if (!goalsByPerson[pk]) goalsByPerson[pk] = {};
          goalsByPerson[pk][metric] = value;
        }

        // Top Performers — Appointments should follow the TOP page date range (not the table-only range)
        const srTop = getRange();
        let oppTopUrl = '';
        if (srTop && srTop.start && srTop.end) {
          oppTopUrl = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(srTop.start)}&end=${encodeURIComponent(srTop.end)}&pipeline_scope=all`;
        } else {
          oppTopUrl = `/api/metrics/opportunities_created?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&pipeline_scope=all`;
        }
        if (lsParam) oppTopUrl += lsParam;

        const oppTopRes = await fetch(oppTopUrl);
        const oppTop = oppTopRes.ok ? await oppTopRes.json() : null;
        const apptsTopBySetter = (oppTop && oppTop.breakdowns && oppTop.breakdowns.created_by_setter_last_name) ? oppTop.breakdowns.created_by_setter_last_name : {};
        const apptsBySetterNormTop = {};
        for (const [k,v] of Object.entries(apptsTopBySetter || {})) {
          const kk = normSetterLast(k);
          if (!kk) continue;
          apptsBySetterNormTop[kk] = (apptsBySetterNormTop[kk] || 0) + Number(v || 0);
        }

        // 3) Raydar knocks/appts set for the SAME window as the demo-rate table
        // (table-only range if set; otherwise default to this month)
        let rayUrl = '';
        if (srTable && srTable.start && srTable.end) {
          rayUrl = `/api/metrics/raydar_doors_knocked?format=json&start=${encodeURIComponent(srTable.start)}&end=${encodeURIComponent(srTable.end)}`;
        } else {
          rayUrl = `/api/metrics/raydar_doors_knocked?format=json&period=thismo`;
        }
        const rayRes = await fetch(rayUrl);
        const ray = rayRes.ok ? await rayRes.json() : null;
        const knocksByClaimed = ray && ray.breakdowns && ray.breakdowns.knocks_by_claimed_by ? ray.breakdowns.knocks_by_claimed_by : {};
        const apptsByClaimed = ray && ray.breakdowns && ray.breakdowns.appointments_set_by_claimed_by ? ray.breakdowns.appointments_set_by_claimed_by : {};

        // 3b) GHL opportunities created (appointments) by setter last name for the same window + lead source filter
        let oppUrl = '';
        if (srTable && srTable.start && srTable.end) {
          oppUrl = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(srTable.start)}&end=${encodeURIComponent(srTable.end)}&pipeline_scope=all`;
        } else {
          oppUrl = `/api/metrics/opportunities_created?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&pipeline_scope=all`;
        }
        const oppLs = (lsEl && lsEl.value) ? String(lsEl.value) : '';
        if (oppLs) oppUrl += `&lead_source=${encodeURIComponent(oppLs)}`;

        const oppRes = await fetch(oppUrl);
        const opp = oppRes.ok ? await oppRes.json() : null;
        const apptsBySetter = (opp && opp.breakdowns && opp.breakdowns.created_by_setter_last_name) ? opp.breakdowns.created_by_setter_last_name : {};

        function normSetterLast(x) {
          return String(x || '').trim().toLowerCase();
        }

        const apptsBySetterNorm = {};
        for (const [k,v] of Object.entries(apptsBySetter || {})) {
          const kk = normSetterLast(k);
          if (!kk) continue;
          apptsBySetterNorm[kk] = (apptsBySetterNorm[kk] || 0) + Number(v || 0);
        }

        // Top Performers — Appointments (map setter last name -> roster display_name)
        const setterDisplayByLast = {};
        for (const r of roster) {
          const sln = normSetterLast(r.ghl_setter_last_name);
          if (!sln) continue;
          const dn = String(r.display_name || r.ghl_user_name || r.raydar_user_name || r.ghl_setter_last_name || '').trim();
          if (dn) setterDisplayByLast[sln] = dn;
        }

        const topAppts = Object.entries(apptsBySetterNormTop)
          .map(([ln, cnt]) => ({
            last: ln,
            name: setterDisplayByLast[ln] || (ln ? (ln[0].toUpperCase() + ln.slice(1)) : '—'),
            value: Number(cnt || 0),
          }))
          .sort((a,b) => (b.value - a.value) || a.name.localeCompare(b.name))
          .slice(0, 10);

        renderTopList('topAppts', topAppts.map(r => ({ name: r.name, value: r.value })));


        // Build row list
        // IMPORTANT: include setters who only have "appointments created" but no ran/sit yet
        // Canonicalize setter key to avoid duplicate rows (e.g., Calabrese vs calabrese)
        const canSetter = (s) => {
          const raw = String(s || '').trim();
          if (!raw) return 'none';
          const low = raw.toLowerCase();
          if (low === 'none' || low === 'null' || low === 'n/a' || low === 'crm ui' || low === 'hand') return low; // keep explicit
          // Title-case for display
          return low.charAt(0).toUpperCase() + low.slice(1);
        };

        const keys = new Set([ ...Object.keys(ranBy || {}), ...Object.keys(sitBy || {}), ...Object.keys(apptsBySetterNorm || {}) ]);
        const agg = {};

        for (const k of keys) {
          const key = canSetter(k);
          if (!agg[key]) agg[key] = { setter: key, ran: 0, sit: 0 };
          agg[key].ran += Number(ranBy[k] || 0);
          agg[key].sit += Number(sitBy[k] || 0);
        }

        // Add appointments created by setter (already normalized to lowercase keys)
        for (const [ln, cnt] of Object.entries(apptsBySetterNorm || {})) {
          const key = canSetter(ln);
          if (!agg[key]) agg[key] = { setter: key, ran: 0, sit: 0 };
          agg[key].appts = (agg[key].appts || 0) + Number(cnt || 0);
        }

        const rows = Object.values(agg).map(r => {
          const setter = r.setter;
          const ran = Number(r.ran || 0);
          const sit = Number(r.sit || 0);
          const pct = ran > 0 ? (sit / ran) * 100 : 0;

          const pk = setterToPerson[setter] || setterToPerson[setter.toLowerCase()] || '';
          const rayId = setterToRaydar[setter] || setterToRaydar[setter.toLowerCase()] || '';

          const knocks = rayId ? Number(knocksByClaimed[rayId] || 0) : 0;
          const appts = Number(r.appts || 0);

          const g = pk ? (goalsByPerson[pk] || {}) : {};
          const knocksGoal = (typeof g.doors_goal !== 'undefined') ? Number(g.doors_goal) : null;
          const apptsGoal = (typeof g.appts_goal !== 'undefined') ? Number(g.appts_goal) : null;
          const demosGoal = (typeof g.demos_goal !== 'undefined') ? Number(g.demos_goal) : null;

          return { setter, ran, sit, pct, knocks, appts, knocksGoal, apptsGoal, demosGoal };
        }).sort((a,b) => (b.ran - a.ran) || (b.sit - a.sit) || a.setter.localeCompare(b.setter));

        const totalRan = rows.reduce((acc, r) => acc + (Number(r.ran) || 0), 0);
        const totalSit = rows.reduce((acc, r) => acc + (Number(r.sit) || 0), 0);
        const totalPct = totalRan > 0 ? (totalSit / totalRan) * 100 : 0;

        const tbody = document.getElementById('setterDemoRows');
        const tfoot = document.getElementById('setterDemoTotals');

        if (tbody) {
          if (!rows.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="padding:12px 8px; color:var(--muted2);">No data</td></tr>`;
          } else {
            tbody.innerHTML = rows.map(r => `
              <tr>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); font-weight:900; color:#0f172a;">${r.setter}</td>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); text-align:right; font-variant-numeric: tabular-nums;">${Number(r.knocks || 0)} / ${(r.knocksGoal === null || Number.isNaN(r.knocksGoal)) ? 'X' : r.knocksGoal}</td>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); text-align:right; font-variant-numeric: tabular-nums;">${Number(r.appts || 0)} / ${(r.apptsGoal === null || Number.isNaN(r.apptsGoal)) ? 'X' : r.apptsGoal}</td>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); text-align:right; font-variant-numeric: tabular-nums;">${Number(r.ran || 0)}</td>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); text-align:right; font-variant-numeric: tabular-nums;">${Number(r.sit || 0)} / ${(r.demosGoal === null || Number.isNaN(r.demosGoal)) ? 'X' : r.demosGoal}</td>
                <td style="padding:10px 8px; border-bottom:1px solid var(--border); text-align:right; font-variant-numeric: tabular-nums;">${r.pct.toFixed(1)}%</td>
              </tr>`).join('');
          }
        }

        if (tfoot) {
          tfoot.innerHTML = `
            <tr>
              <td style="padding:10px 8px; font-weight:950;">TOTAL</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">${totalRan}</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">${totalSit}</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">${totalPct.toFixed(1)}%</td>
            </tr>`;
        }

      } catch (e) {
        const tbody = document.getElementById('setterDemoRows');
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="padding:12px 8px; color:var(--muted2);">Error loading demo table: ${String(e)}</td></tr>`;
        const tfoot = document.getElementById('setterDemoTotals');
        if (tfoot) {
          tfoot.innerHTML = `
            <tr>
              <td style="padding:10px 8px; font-weight:950;">TOTAL</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
              <td style="padding:10px 8px; text-align:right; font-weight:950; font-variant-numeric: tabular-nums;">—</td>
            </tr>`;
        }

      }


    } catch (e) {
      setText('kpiKnocks', 'ERR');
      setText('kpiKnocksSub', String(e));
      setText('segKnocks', 'ERR Knocks');
    }
  }

  // Setter demo table filter (Lead Gen Source)
  const setterLs2 = document.getElementById('setterTableLeadSource');
  if (setterLs2) {
    setterLs2.addEventListener('change', () => {
      load();
    });
  }

  // Setter demo table date range (filters demo_rate by appointmentOccurredAt)
  const stEl = document.getElementById('setterTableStart');
  const enEl = document.getElementById('setterTableEnd');
  const apBtn = document.getElementById('setterTableApply');
  const clBtn = document.getElementById('setterTableClear');

  const existingSetterRange = getSetterRange();
  if (existingSetterRange && stEl && enEl) {
    stEl.value = existingSetterRange.start;
    enEl.value = existingSetterRange.end;
  }

  if (apBtn && stEl && enEl) {
    apBtn.addEventListener('click', () => {
      if (stEl.value && enEl.value) {
        setSetterRange({ start: stEl.value, end: enEl.value });
      }
      load();
    });
  }

  if (clBtn && stEl && enEl) {
    clBtn.addEventListener('click', () => {
      stEl.value = '';
      enEl.value = '';
      clearSetterRange();
      load();
    });
  }


  load();
</script>
</body>
</html>"""

    return html.replace("__YEAR__", str(year)).replace("__MONTH__", str(month))


class handler(BaseHTTPRequestHandler):
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
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
