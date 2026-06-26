# -*- coding: utf-8 -*-

"""Vercel Python function: /api/fma_weekly_review

Admin-only FMA weekly performance review dashboard.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler


HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — FMA Weekly Review</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #94a3b8;
      --pink: #ec4899;
      --pink2: #f472b6;
      --blue: #2563eb;
      --green: #059669;
      --amber: #d97706;
      --violet: #7c3aed;
      --slate: #334155;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }

    .wrap { max-width: 1280px; margin: 0 auto; padding: 22px; }

    .topbar {
      display: flex;
      align-items: flex-start;
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
      width: 240px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

    .nav { margin-top: 12px; display:flex; gap:10px; flex-wrap:wrap; }
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
    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .statusBox {
      min-width: 280px;
      padding-top: 2px;
    }

    .statusLabel {
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .statusText { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .panel {
      margin-top: 14px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      box-shadow: var(--shadow);
    }

    .filters {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 10px;
      align-items: end;
    }

    .col-2 { grid-column: span 2; }
    .col-3 { grid-column: span 3; }
    .col-4 { grid-column: span 4; }

    label {
      display:block;
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      margin-bottom: 4px;
    }

    input, select {
      width:100%;
      box-sizing:border-box;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 10px;
      font-size: 13px;
      font-weight: 900;
      background: #fff;
      color: #0f172a;
    }

    .btnRow { display:flex; gap:8px; flex-wrap:wrap; }
    .btn {
      display:inline-flex;
      align-items:center;
      justify-content:center;
      border-radius: 10px;
      border: 1px solid var(--border);
      background:#fff;
      color:#334155;
      padding: 9px 12px;
      font-size: 13px;
      font-weight: 950;
      cursor:pointer;
      text-decoration:none;
    }
    .btn.primary {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .grid {
      display:grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      margin-top: 14px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }

    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .kpi {
      font-size: 38px;
      line-height: 1;
      font-weight: 950;
      letter-spacing: -0.02em;
      margin-top: 12px;
      color: #0f172a;
    }
    .kpi.blue { color: var(--blue); }
    .kpi.green { color: var(--green); }
    .kpi.amber { color: var(--amber); }
    .kpi.violet { color: var(--violet); }
    .kpi-sub { margin-top: 8px; color: var(--muted2); font-size: 12px; font-weight: 800; }

    .chartShell {
      margin-top: 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
      padding: 12px;
    }

    svg { width: 100%; height: auto; display:block; }

    .legend { display:flex; gap:12px; flex-wrap:wrap; margin-top: 8px; }
    .legendItem { display:flex; align-items:center; gap:6px; font-size:12px; color:#475569; font-weight:800; }
    .swatch { width:10px; height:10px; border-radius:999px; }

    .bars { display:flex; flex-direction:column; gap:10px; margin-top:12px; }
    .barRow { display:grid; grid-template-columns: 180px 1fr auto; gap:10px; align-items:center; }
    .barLabel { font-size:12px; font-weight:900; color:#0f172a; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .barTrack {
      position:relative;
      width:100%;
      height:18px;
      border-radius:999px;
      background:#f1f5f9;
      overflow:hidden;
    }
    .segSit, .segNoSit, .segSales {
      position:absolute;
      top:0;
      bottom:0;
    }
    .segSit { left:0; background: rgba(16,185,129,0.92); }
    .segNoSit { background: rgba(245,158,11,0.90); }
    .segSales { background: rgba(124,58,237,0.88); }
    .barValue { font-size:12px; font-weight:900; color:#475569; }

    .tableWrap {
      overflow:auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-top: 12px;
      background:#fff;
    }

    table { width:100%; border-collapse: collapse; min-width: 1080px; }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 10px 12px;
      font-size: 12px;
      text-align:left;
      font-variant-numeric: tabular-nums;
    }
    th { color: var(--muted); font-weight: 950; background:#f8fafc; }
    td { color: #0f172a; font-weight: 800; }
    tbody tr:nth-child(even) { background:#fcfdff; }
    .num { text-align:right; }

    .pill {
      display:inline-flex;
      align-items:center;
      gap:6px;
      padding: 5px 9px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background:#fff;
      font-size: 11px;
      font-weight: 900;
      color:#334155;
    }
    .pill.sit { color:#047857; border-color: rgba(16,185,129,0.28); background: rgba(16,185,129,0.08); }
    .pill.nosit { color:#b45309; border-color: rgba(245,158,11,0.28); background: rgba(245,158,11,0.08); }
    .pill.sale { color:#6d28d9; border-color: rgba(124,58,237,0.28); background: rgba(124,58,237,0.08); }

    .empty {
      padding: 18px;
      border: 1px dashed var(--border);
      border-radius: 12px;
      color: var(--muted2);
      font-size: 13px;
      text-align:center;
      margin-top: 12px;
    }

    @media (max-width: 1080px) {
      .span-8, .span-6, .span-4 { grid-column: span 12; }
      .span-3 { grid-column: span 6; }
      .col-4, .col-3, .col-2 { grid-column: span 6; }
    }

    @media (max-width: 720px) {
      .wrap { padding: 12px; }
      .topbar { padding: 12px; }
      .title { font-size: 20px; }
      .span-3, .span-12 { grid-column: span 12; }
      .col-4, .col-3, .col-2 { grid-column: span 12; }
      .nav { overflow-x:auto; flex-wrap:nowrap; padding-bottom:4px; }
      .navbtn { white-space:nowrap; flex:0 0 auto; }
      .barRow { grid-template-columns: 120px 1fr auto; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">FMA Weekly Review</div>
        <div class="subtitle">Weekly performance review for door-to-door appointment setters</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/settings#secret-lab">Settings</a>
          <a class="navbtn" href="/api/fma_dashboard">FMA Dashboard</a>
          <a class="navbtn active" href="/api/fma_weekly_review">Weekly Review</a>
        </div>
      </div>
      <div class="statusBox">
        <div class="statusLabel">Status</div>
        <div class="statusText" id="statusText">Loading…</div>
      </div>
    </div>

    <div class="panel">
      <div class="filters">
        <div class="col-2">
          <label for="startDate">Start</label>
          <input id="startDate" type="date" />
        </div>
        <div class="col-2">
          <label for="endDate">End</label>
          <input id="endDate" type="date" />
        </div>
        <div class="col-3">
          <label for="personFilter">Team Member</label>
          <select id="personFilter">
            <option value="">All FMAs</option>
          </select>
        </div>
        <div class="col-4">
          <label>Quick Range</label>
          <div class="btnRow">
            <button class="btn" id="lastWeekBtn" type="button">Last Week</button>
            <button class="btn" id="thisWeekBtn" type="button">This Week</button>
            <button class="btn" id="last7Btn" type="button">Last 7 Days</button>
          </div>
        </div>
        <div class="col-1">
          <label>&nbsp;</label>
          <button class="btn primary" id="applyBtn" type="button">Apply</button>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Knocks</div>
        <div class="kpi blue" id="kpiKnocks">—</div>
        <div class="kpi-sub" id="kpiKnocksSub">—</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Appointments</div>
        <div class="kpi green" id="kpiAppts">—</div>
        <div class="kpi-sub" id="kpiApptsSub">—</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Demos</div>
        <div class="kpi amber" id="kpiDemos">—</div>
        <div class="kpi-sub" id="kpiDemosSub">—</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Sales</div>
        <div class="kpi violet" id="kpiSales">—</div>
        <div class="kpi-sub" id="kpiSalesSub">—</div>
      </div>

      <div class="card span-8">
        <div class="card-title">Daily Trend</div>
        <div class="meta">Knocks, appointments, demos, and sales across the selected review window.</div>
        <div class="chartShell" id="trendChartShell"></div>
        <div class="legend">
          <div class="legendItem"><span class="swatch" style="background:#2563eb;"></span>Knocks</div>
          <div class="legendItem"><span class="swatch" style="background:#059669;"></span>Appointments</div>
          <div class="legendItem"><span class="swatch" style="background:#d97706;"></span>Demos</div>
          <div class="legendItem"><span class="swatch" style="background:#7c3aed;"></span>Sales</div>
        </div>
      </div>

      <div class="card span-4">
        <div class="card-title">Outcome Split By FMA</div>
        <div class="meta">Sit vs No Sit vs Sales helps frame review conversations fast.</div>
        <div class="bars" id="outcomeBars"></div>
      </div>

      <div class="card span-12">
        <div class="card-title">Weekly Scoreboard</div>
        <div class="meta">Totals plus per-day pace across the selected review window.</div>
        <div class="tableWrap">
          <table>
            <thead>
              <tr>
                <th>FMA</th>
                <th class="num">Knocks</th>
                <th class="num">Knocks/Day</th>
                <th class="num">Appointments</th>
                <th class="num">Appts/Day</th>
                <th class="num">Demos</th>
                <th class="num">Demos/Day</th>
                <th class="num">Sales</th>
                <th class="num">Sales/Day</th>
                <th class="num">Demo %</th>
                <th class="num">Close %</th>
              </tr>
            </thead>
            <tbody id="scoreboardBody">
              <tr><td colspan="11" class="empty">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card span-12">
        <div class="card-title">Ran Appointments Review</div>
        <div class="meta">Dispositioned appointments for review conversations, newest first.</div>
        <div class="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Occurred</th>
                <th>FMA</th>
                <th>Outcome</th>
                <th>Contact</th>
                <th>Owner</th>
                <th>Pipeline</th>
                <th>Stage</th>
                <th>Notes</th>
                <th class="num">Opp ID</th>
              </tr>
            </thead>
            <tbody id="appointmentsBody">
              <tr><td colspan="9" class="empty">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);

    function pad(n) { return String(n).padStart(2, '0'); }

    function fmtNum(v) {
      const n = Number(v || 0);
      return n.toLocaleString();
    }

    function fmtAvg(v) {
      const n = Number(v || 0);
      return n.toFixed(1).replace(/\.0$/, '');
    }

    function fmtPct(v) {
      if (!isFinite(v)) return '—';
      return `${v.toFixed(1)}%`;
    }

    function isoDate(d) {
      return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
    }

    function localDateParts(iso) {
      const [y,m,d] = String(iso || '').split('-').map(Number);
      return new Date(y, (m || 1) - 1, d || 1);
    }

    function getLastWeekRange() {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const weekday = (today.getDay() + 6) % 7;
      const thisMonday = new Date(today);
      thisMonday.setDate(today.getDate() - weekday);
      const lastMonday = new Date(thisMonday);
      lastMonday.setDate(thisMonday.getDate() - 7);
      const lastSunday = new Date(thisMonday);
      lastSunday.setDate(thisMonday.getDate() - 1);
      return { start: isoDate(lastMonday), end: isoDate(lastSunday) };
    }

    function getThisWeekRange() {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const weekday = (today.getDay() + 6) % 7;
      const monday = new Date(today);
      monday.setDate(today.getDate() - weekday);
      return { start: isoDate(monday), end: isoDate(today) };
    }

    function getLast7Range() {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const start = new Date(today);
      start.setDate(today.getDate() - 6);
      return { start: isoDate(start), end: isoDate(today) };
    }

    function setRange(range) {
      $('startDate').value = range.start;
      $('endDate').value = range.end;
    }

    function queryFromInputs() {
      const params = new URLSearchParams();
      if ($('startDate').value) params.set('start', $('startDate').value);
      if ($('endDate').value) params.set('end', $('endDate').value);
      return params.toString();
    }

    function formatOccurred(iso) {
      if (!iso) return '';
      const dt = new Date(iso);
      return dt.toLocaleString('en-US', {
        timeZone: 'America/New_York',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: 'numeric',
        minute: '2-digit',
      });
    }

    function renderTrendChart(series) {
      const host = $('trendChartShell');
      if (!series || !series.length) {
        host.innerHTML = '<div class="empty">No daily data in this window.</div>';
        return;
      }

      const width = 900;
      const height = 260;
      const margin = { top: 14, right: 18, bottom: 36, left: 28 };
      const innerW = width - margin.left - margin.right;
      const innerH = height - margin.top - margin.bottom;
      const maxVal = Math.max(1, ...series.flatMap(d => [d.knocks, d.appointments, d.demos, d.sales]));
      const stepX = series.length > 1 ? innerW / (series.length - 1) : innerW / 2;
      const colors = {
        knocks: '#2563eb',
        appointments: '#059669',
        demos: '#d97706',
        sales: '#7c3aed',
      };

      function xAt(i) { return margin.left + (series.length === 1 ? innerW / 2 : i * stepX); }
      function yAt(v) { return margin.top + innerH - ((Number(v || 0) / maxVal) * innerH); }
      function lineFor(key) {
        return series.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(d[key]).toFixed(1)}`).join(' ');
      }

      const ticks = [];
      for (let i = 0; i < 4; i += 1) {
        const value = maxVal * (i / 3);
        const y = yAt(value);
        ticks.push(`<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e8ecf0" stroke-width="1" />`);
        ticks.push(`<text x="${margin.left - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="#94a3b8">${Math.round(value)}</text>`);
      }

      const labels = series.map((d, i) => {
        const dt = localDateParts(d.date);
        const label = `${dt.getMonth()+1}/${dt.getDate()}`;
        return `<text x="${xAt(i)}" y="${height - 10}" text-anchor="middle" font-size="10" fill="#94a3b8">${label}</text>`;
      }).join('');

      const points = Object.keys(colors).map((key) => (
        series.map((d, i) => `<circle cx="${xAt(i)}" cy="${yAt(d[key])}" r="3.5" fill="${colors[key]}"><title>${key}: ${d[key]} on ${d.date}</title></circle>`).join('')
      )).join('');

      host.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily trend chart">
          ${ticks.join('')}
          <path d="${lineFor('knocks')}" fill="none" stroke="${colors.knocks}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${lineFor('appointments')}" fill="none" stroke="${colors.appointments}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${lineFor('demos')}" fill="none" stroke="${colors.demos}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="${lineFor('sales')}" fill="none" stroke="${colors.sales}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
          ${points}
          ${labels}
        </svg>
      `;
    }

    function renderOutcomeBars(rows) {
      const host = $('outcomeBars');
      if (!rows.length) {
        host.innerHTML = '<div class="empty">No FMA rows for this filter.</div>';
        return;
      }
      const maxTotal = Math.max(1, ...rows.map(r => Number(r.ran || 0) + Number(r.sales || 0)));
      host.innerHTML = rows.slice(0, 10).map((row) => {
        const sit = Number(row.demos || 0);
        const noSit = Number(row.no_sit || 0);
        const sales = Number(row.sales || 0);
        const total = Math.max(1, sit + noSit + sales);
        const width = (total / maxTotal) * 100;
        const sitPct = (sit / total) * 100;
        const noSitPct = (noSit / total) * 100;
        const salesPct = (sales / total) * 100;
        return `
          <div class="barRow">
            <div class="barLabel">${row.display_name}</div>
            <div class="barTrack" style="width:${width}%">
              <div class="segSit" style="width:${sitPct}%;"></div>
              <div class="segNoSit" style="left:${sitPct}%; width:${noSitPct}%;"></div>
              <div class="segSales" style="left:${sitPct + noSitPct}%; width:${salesPct}%;"></div>
            </div>
            <div class="barValue">${sit}/${noSit}/${sales}</div>
          </div>
        `;
      }).join('');
    }

    function renderScoreboard(rows, dayCount) {
      const body = $('scoreboardBody');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="11" class="empty">No FMA rows for this filter.</td></tr>';
        return;
      }
      body.innerHTML = rows.map((row) => {
        const knocks = Number(row.knocks || 0);
        const appts = Number(row.appointments || 0);
        const demos = Number(row.demos || 0);
        const sales = Number(row.sales || 0);
        const ran = Number(row.ran || 0);
        const demoPct = ran > 0 ? (demos / ran) * 100 : NaN;
        const closePct = demos > 0 ? (sales / demos) * 100 : NaN;
        return `
          <tr>
            <td>${row.display_name}</td>
            <td class="num">${fmtNum(knocks)}</td>
            <td class="num">${fmtAvg(knocks / dayCount)}</td>
            <td class="num">${fmtNum(appts)}</td>
            <td class="num">${fmtAvg(appts / dayCount)}</td>
            <td class="num">${fmtNum(demos)}</td>
            <td class="num">${fmtAvg(demos / dayCount)}</td>
            <td class="num">${fmtNum(sales)}</td>
            <td class="num">${fmtAvg(sales / dayCount)}</td>
            <td class="num">${fmtPct(demoPct)}</td>
            <td class="num">${fmtPct(closePct)}</td>
          </tr>
        `;
      }).join('');
    }

    function renderAppointments(rows) {
      const body = $('appointmentsBody');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="9" class="empty">No ran appointments in this window.</td></tr>';
        return;
      }
      body.innerHTML = rows.map((row) => {
        const outcomeClass = row.outcome === 'Sit' ? 'sit' : 'nosit';
        const salePill = row.is_sale_stage ? '<span class="pill sale">Sale Stage</span>' : '';
        return `
          <tr>
            <td>${formatOccurred(row.appointment_occurred_at)}</td>
            <td>${row.display_name}</td>
            <td><span class="pill ${outcomeClass}">${row.outcome}</span> ${salePill}</td>
            <td>${row.contact || ''}</td>
            <td>${row.owner || ''}</td>
            <td>${row.pipeline || ''}</td>
            <td>${row.pipeline_stage || ''}</td>
            <td>${row.disposition_notes || ''}</td>
            <td class="num">${row.opportunity_id || ''}</td>
          </tr>
        `;
      }).join('');
    }

    let latestPayload = null;

    function filteredRows(payload) {
      const personKey = $('personFilter').value || '';
      const people = Array.isArray(payload.people) ? payload.people.slice() : [];
      const appts = Array.isArray(payload.ran_appointments) ? payload.ran_appointments.slice() : [];
      const daily = Array.isArray(payload.daily_series) ? payload.daily_series.slice() : [];
      if (!personKey) return { people, appts, daily, totals: payload.totals };

      const row = people.find(p => p.person_key === personKey);
      if (!row) return { people: [], appts: [], daily, totals: { knocks:0, appointments:0, demos:0, sales:0, ran:0, no_sit:0 } };

      const personAppts = appts.filter(r => r.person_key === personKey);
      const totals = {
        knocks: Number(row.knocks || 0),
        appointments: Number(row.appointments || 0),
        demos: Number(row.demos || 0),
        sales: Number(row.sales || 0),
        ran: Number(row.ran || 0),
        no_sit: Number(row.no_sit || 0),
      };

      const personDailyMap = row.daily || {};
      const personDaily = daily.map((d) => {
        const bucket = personDailyMap[d.date] || {};
        return {
          date: d.date,
          knocks: Number(bucket.knocks || 0),
          appointments: Number(bucket.appointments || 0),
          demos: Number(bucket.demos || 0),
          sales: Number(bucket.sales || 0),
          sit: Number(bucket.sit || 0),
          no_sit: Number(bucket.no_sit || 0),
          ran: Number(bucket.ran || 0),
        };
      });

      return { people: [row], appts: personAppts, daily: personDaily, totals };
    }

    function render(payload) {
      latestPayload = payload;
      const scoped = filteredRows(payload);
      const dayCount = Number(payload.day_count || 7);

      const totals = scoped.totals;
      $('kpiKnocks').textContent = fmtNum(totals.knocks);
      $('kpiKnocksSub').textContent = `${fmtAvg((totals.knocks || 0) / dayCount)} per day`;
      $('kpiAppts').textContent = fmtNum(totals.appointments);
      $('kpiApptsSub').textContent = `${fmtAvg((totals.appointments || 0) / dayCount)} per day`;
      $('kpiDemos').textContent = fmtNum(totals.demos);
      $('kpiDemosSub').textContent = `${fmtAvg((totals.demos || 0) / dayCount)} per day`;
      $('kpiSales').textContent = fmtNum(totals.sales);
      $('kpiSalesSub').textContent = `${fmtAvg((totals.sales || 0) / dayCount)} per day`;

      renderTrendChart(scoped.daily);
      renderOutcomeBars(scoped.people);
      renderScoreboard(scoped.people, dayCount);
      renderAppointments(scoped.appts);
    }

    async function load() {
      const q = queryFromInputs();
      $('statusText').textContent = 'Loading review data…';
      try {
        const res = await fetch(`/api/metrics/fma_weekly_review?${q}`);
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || `Request failed (${res.status})`);

        const sel = $('personFilter');
        const current = sel.value;
        const options = ['<option value="">All FMAs</option>'].concat(
          (data.people || []).map((p) => `<option value="${p.person_key}">${p.display_name}</option>`)
        );
        sel.innerHTML = options.join('');
        if ((data.people || []).some((p) => p.person_key === current)) sel.value = current;

        const summary = `${data.start} → ${data.end} • ${(data.people || []).length} FMAs • ${(data.ran_appointments || []).length} ran appointments`;
        $('statusText').textContent = summary;
        render(data);
      } catch (err) {
        $('statusText').textContent = String(err && err.message ? err.message : err);
        $('trendChartShell').innerHTML = '<div class="empty">Unable to load weekly review data.</div>';
        $('outcomeBars').innerHTML = '';
        $('scoreboardBody').innerHTML = '<tr><td colspan="11" class="empty">Unable to load data.</td></tr>';
        $('appointmentsBody').innerHTML = '<tr><td colspan="9" class="empty">Unable to load data.</td></tr>';
      }
    }

    $('lastWeekBtn').addEventListener('click', () => { setRange(getLastWeekRange()); load(); });
    $('thisWeekBtn').addEventListener('click', () => { setRange(getThisWeekRange()); load(); });
    $('last7Btn').addEventListener('click', () => { setRange(getLast7Range()); load(); });
    $('applyBtn').addEventListener('click', load);
    $('personFilter').addEventListener('change', () => { if (latestPayload) render(latestPayload); });

    setRange(getLastWeekRange());
    load();
  </script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = ("ERROR: " + str(exc)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
