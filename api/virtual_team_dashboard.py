# -*- coding: utf-8 -*-

"""Vercel Python function: /api/virtual_team_dashboard

Virtual Team Dashboard

KPIs:
- Total Calls (Kixie)
- Connections (Kixie)
- Appointments (Opportunities Created) for setters whose last name matches Kixie agents

Chart:
- Connection rate by day over selected date range

Notes:
- Kixie timestamp field is receivedAt (ISO string), filtered via /api/metrics/kixie_calls_summary
- Appointments are computed from /api/metrics/opportunities_created breakdown created_by_setter_last_name
  and summing for the set of Kixie last names found in-window.
"""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler


def render_html() -> str:
    return r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Virtual Team</title>
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
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background: var(--bg); color: var(--text); }
    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar { position:relative; display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap;
      padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:var(--shadow);
    }

    .adminSettings { position:absolute; top:16px; right:18px; }

    .title { font-size: 22px; font-weight: 950; color: #1a2b4a; letter-spacing: -0.02em; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }
    .pinkline { height:3px; width:200px; border-radius:999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top:10px;
    }

    .nav { margin-top: 12px; display:flex; gap:10px; flex-wrap:wrap; }
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border);
      background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none;
    }
    .navbtn:hover { border-color: rgba(236,72,153,0.45); box-shadow: 0 1px 2px rgba(17,24,39,0.06); }
    .navbtn.active { background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color:#b80b66; }

    .filters { display:flex; gap: 10px; flex-wrap:wrap; align-items:flex-end; margin-top:10px; }
    .filters label { font-size: 12px; font-weight: 900; color: var(--muted); }
    .filters input { border:1px solid var(--border); border-radius: 10px; padding: 8px 10px; font-weight: 900; }
    .btn { background: var(--pink); border: 1px solid var(--pink); color:#fff; border-radius:10px; padding: 8px 10px; font-size: 13px; font-weight: 950; cursor:pointer; }
    .btn.secondary { background:#fff; border: 1px solid var(--border); color:#334155; }

    .pillbar { margin-top: 14px; display:flex; gap: 10px; flex-wrap: wrap; }
    .pill { display:inline-flex; align-items:center; padding: 8px 12px; border-radius: 999px; border:1px solid var(--border);
      background:#fff; color:#334155; font-size:12px; font-weight:950; cursor:pointer; user-select:none;
    }
    .pill:hover { border-color: rgba(236,72,153,0.45); box-shadow: 0 1px 2px rgba(17,24,39,0.06); }
    .pill.active { background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color:#b80b66; }

    .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap:14px; margin-top:14px; align-content:start; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow: var(--shadow); min-height: 120px; }
    .card-title { font-size: 13px; font-weight: 800; color: var(--muted); }
    .kpi { font-size: 46px; font-weight: 950; margin-top: 8px; letter-spacing: -0.02em; }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }
    .span-4 { grid-column: span 4; }
    .span-12 { grid-column: span 12; }

    .chartWrap { margin-top: 10px; }

    /* Lightweight line chart */
    .lineChart { width:100%; height: 260px; }

    .bars { margin-top: 8px; }
    .barRow { display:flex; align-items:center; gap:12px; margin-top:10px; }
    .barName { width: 220px; font-size:12px; color: var(--muted); font-weight: 950; overflow:hidden; text-overflow: ellipsis; white-space: nowrap; }
    .barTrack { flex:1; height: 10px; border-radius: 999px; background: #f1f5f9; overflow:hidden; }
    .barFill { height:100%; background: var(--pink); width: 0%; }
    .barVal { width: 70px; text-align:right; font-variant-numeric: tabular-nums; font-weight: 950; }

    .axisLabel { font-size: 11px; fill: #94a3b8; }
    .tickLine { stroke: #eef2f7; stroke-width: 1; }
    .pathLine { stroke: var(--pink); stroke-width: 3; fill: none; }
    .dot { fill: var(--pink); opacity: 0.9; }
    .dot:hover { opacity: 1; }
    .dotLabel { font-size: 10px; fill: #334155; font-weight: 900; }

    table { width:100%; border-collapse: collapse; margin-top: 8px; }
    th { text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); color: var(--muted); font-size: 12px; font-weight: 950; }
    td { font-size: 12px; padding: 10px 8px; border-bottom:1px solid var(--border); }
    .num { text-align:right; font-variant-numeric: tabular-nums; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Virtual Team</div>
        <div class="subtitle">Kixie performance + appointments set</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn" href="/api/fma_dashboard">FMA dashboard</a>
          <a class="navbtn" href="/api/missing_dispos">Missing Dispos</a>
          <a class="navbtn active" href="/api/virtual_team_dashboard">Virtual Team</a>
        </div>
      </div>

      <div style="min-width:320px">
        <a class="navbtn adminSettings" href="/api/settings">Admin Settings</a>
        <div style="color: var(--muted); font-size: 12px; font-weight: 900;">Date Range</div>
        <div class="filters">
          <div>
            <label>Start</label><br />
            <input id="startDate" type="date" />
          </div>
          <div>
            <label>End</label><br />
            <input id="endDate" type="date" />
          </div>
          <button class="btn" id="apply">Apply</button>
          <button class="btn secondary" id="clear">Clear</button>
        </div>
      </div>
    </div>

    <div class="pillbar" id="periodTabs">
      <div class="pill" data-period="today">Today</div>
      <div class="pill" data-period="yesterday">Yesterday</div>
      <div class="pill" data-period="thismo">This Month</div>
      <div class="pill" data-period="thiswk">This Week</div>
      <div class="pill" data-period="2w">Last 2 Weeks</div>
      <div class="pill" data-period="custom">Custom</div>
    </div>

    <div class="grid">
      <div class="card span-4">
        <div class="card-title">Total Calls (Kixie)</div>
        <div class="kpi" id="kpiCalls">—</div>
        <div class="meta" id="kpiCallsMeta">—</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Connections (Kixie)</div>
        <div class="kpi" id="kpiConnections">—</div>
        <div class="meta" id="kpiConnectionsMeta">—</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Appointments (Opps Created)</div>
        <div class="kpi" id="kpiAppts">—</div>
        <div class="meta" id="kpiApptsMeta">Setters matched by last name to Kixie agents</div>
      </div>

      <div class="card span-12">
        <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap">
          <div>
            <div class="card-title">Connection Rate by Day</div>
            <div class="meta">Connections / Calls • daily points</div>
          </div>
          <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap">
            <div class="pillbar" style="margin-top:0" id="chartMode">
              <div class="pill" data-mode="team">Team</div>
              <div class="pill" data-mode="agent">By Agent</div>
            </div>
            <select id="agentSelect" style="display:none; border:1px solid var(--border); border-radius:10px; padding:8px 10px; font-weight:900"></select>
          </div>
        </div>
        <div class="chartWrap" id="chart"></div>
      </div>

      <div class="card span-12">
        <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap">
          <div>
            <div class="card-title">Opportunities Created by Setter (Phones + 3PL)</div>
            <div class="meta">Setter last name breakdown • filtered to Phones + 3PL</div>
          </div>
        </div>
        <div class="chartWrap" id="apptsChart"></div>
      </div>

      <div class="card span-12">
        <div class="card-title">Agents</div>
        <div class="meta">Calls + connections by agent</div>
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th class="num">Calls</th>
              <th class="num">Connections</th>
              <th class="num">Conn %</th>
            </tr>
          </thead>
          <tbody id="agentRows">
            <tr><td colspan="4" style="color: var(--muted2)">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

<script>
  const url = new URL(window.location.href);
  const start = url.searchParams.get('start') || '';
  const end = url.searchParams.get('end') || '';

  const startEl = document.getElementById('startDate');
  const endEl = document.getElementById('endDate');

  function nyYmd(d = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year:'numeric', month:'2-digit', day:'2-digit' }).formatToParts(d);
    const get = (t) => parts.find(p => p.type === t)?.value;
    return `${get('year')}-${get('month')}-${get('day')}`;
  }

  function ymdAddDays(ymd, deltaDays) {
    const [y,m,d] = ymd.split('-').map(x=>parseInt(x,10));
    const dt = new Date(Date.UTC(y, m-1, d));
    dt.setUTCDate(dt.getUTCDate() + deltaDays);
    const y2 = dt.getUTCFullYear();
    const m2 = String(dt.getUTCMonth()+1).padStart(2,'0');
    const d2 = String(dt.getUTCDate()).padStart(2,'0');
    return `${y2}-${m2}-${d2}`;
  }

  function setActive(period) {
    document.querySelectorAll('#periodTabs .pill').forEach(x => x.classList.toggle('active', x.dataset.period === period));
  }

  function setRange(s, e) {
    url.searchParams.set('start', s);
    url.searchParams.set('end', e);
    window.location.href = url.toString();
  }

  function clearRange() {
    url.searchParams.delete('start');
    url.searchParams.delete('end');
    window.location.href = url.toString();
  }

  if (!start || !end) {
    // default this month
    const today = nyYmd(new Date());
    const monthStart = today.slice(0,8) + '01';
    setActive('thismo');
    startEl.value = monthStart;
    endEl.value = today;
  } else {
    startEl.value = start;
    endEl.value = end;
    setActive('custom');
  }

  document.querySelectorAll('#periodTabs .pill').forEach(p => {
    p.addEventListener('click', () => {
      const per = p.dataset.period;
      if (per === 'custom') { setActive('custom'); return; }
      const today = nyYmd(new Date());
      if (per === 'today') return setRange(today, today);
      if (per === 'yesterday') { const y = ymdAddDays(today,-1); return setRange(y,y); }
      if (per === 'thismo') return setRange(today.slice(0,8) + '01', today);
      if (per === 'thiswk') {
        const dt = new Date();
        const wd = new Intl.DateTimeFormat('en-US', { timeZone:'America/New_York', weekday:'short' }).format(dt);
        const map = { Mon:0, Tue:1, Wed:2, Thu:3, Fri:4, Sat:5, Sun:6 };
        const off = map[wd] ?? 0;
        return setRange(ymdAddDays(today, -off), today);
      }
      if (per === '2w') return setRange(ymdAddDays(today,-13), today);
    });
  });

  document.getElementById('apply').addEventListener('click', () => {
    const s = startEl.value;
    const e = endEl.value;
    if (s && e) setRange(s,e);
  });
  document.getElementById('clear').addEventListener('click', clearRange);

  function fmtPct(x) {
    if (x === null || typeof x === 'undefined') return '—';
    return `${Number(x).toFixed(1)}%`;
  }

  async function load() {
    const s = startEl.value;
    const e = endEl.value;
    if (!s || !e) return;

    document.getElementById('kpiCalls').textContent = '…';
    document.getElementById('kpiConnections').textContent = '…';
    document.getElementById('kpiAppts').textContent = '…';

    const kixieUrl = `/api/metrics/kixie_calls_summary?format=json&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
    const oppCreatedPhonesUrl = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}&lead_source=${encodeURIComponent('Phones')}`;
    const oppCreated3plUrl = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}&lead_source=${encodeURIComponent('3PL')}`;

    const [kixieRes, createdPhonesRes, created3plRes] = await Promise.all([
      fetch(kixieUrl, { cache:'no-store' }),
      fetch(oppCreatedPhonesUrl, { cache:'no-store' }),
      fetch(oppCreated3plUrl, { cache:'no-store' })
    ]);

    if (!kixieRes.ok) {
      document.getElementById('kpiCalls').textContent = 'ERR';
      document.getElementById('kpiCallsMeta').textContent = `Kixie HTTP ${kixieRes.status}`;
      return;
    }

    const k = await kixieRes.json();
    document.getElementById('kpiCalls').textContent = String(k.calls ?? '—');
    document.getElementById('kpiConnections').textContent = String(k.connections ?? '—');
    document.getElementById('kpiCallsMeta').textContent = `Conn rate: ${fmtPct(k.connection_rate)}`;
    document.getElementById('kpiConnectionsMeta').textContent = `Conn rate: ${fmtPct(k.connection_rate)}`;

    // agent table
    const rows = (k.by_agent || []);
    let html = '';
    for (const r of rows) {
      html += `<tr>
        <td>${(r.agent || '—')}</td>
        <td class="num">${(r.calls ?? 0)}</td>
        <td class="num">${(r.connections ?? 0)}</td>
        <td class="num">${fmtPct(r.connection_rate)}</td>
      </tr>`;
    }
    document.getElementById('agentRows').innerHTML = html || '<tr><td colspan="4" style="color: var(--muted2)">No rows</td></tr>';

    // Chart: connection rate line (daily points)
    const teamSeries = (k.by_day || []);
    const byAgentDay = (k.by_agent_day || {});

    // Fill agent dropdown
    const agentSel = document.getElementById('agentSelect');
    agentSel.innerHTML = '';
    for (const r of (k.by_agent || [])) {
      const opt = document.createElement('option');
      opt.value = r.agent;
      opt.textContent = r.userId ? `${r.agent} (${r.userId})` : r.agent;
      agentSel.appendChild(opt);
    }

    let chartMode = 'team';
    if (url.searchParams.get('chart') === 'agent') chartMode = 'agent';

    function setChartMode(mode) {
      chartMode = mode;
      document.querySelectorAll('#chartMode .pill').forEach(p => p.classList.toggle('active', p.dataset.mode === mode));
      agentSel.style.display = (mode === 'agent') ? 'inline-flex' : 'none';
      const u = new URL(window.location.href);
      u.searchParams.set('chart', mode);
      if (mode === 'agent') u.searchParams.set('agent', agentSel.value || '');
      else { u.searchParams.delete('agent'); }
      window.history.replaceState({}, '', u.toString());
      renderChart();
    }

    function ptsFromSeries(series) {
      return (series || []).map(d => ({
        day: String(d.day || ''),
        rate: (d.connection_rate === null || typeof d.connection_rate === 'undefined') ? null : Number(d.connection_rate),
        calls: Number(d.calls || 0),
        connections: Number(d.connections || 0)
      })).filter(p => p.day);
    }

    function renderChart() {
      const series = (chartMode === 'agent') ? (byAgentDay[agentSel.value] || []) : teamSeries;
      const pts = ptsFromSeries(series);

      if (!pts.length) {
        document.getElementById('chart').innerHTML = '<div class="meta">No data.</div>';
        return;
      }

      const W = 1120;
      const H = 260;
      const padL = 44, padR = 16, padT = 12, padB = 36;
      const iw = W - padL - padR;
      const ih = H - padT - padB;

      const minX = 0;
      const maxX = Math.max(1, pts.length - 1);

      // y-domain 0..50 (per request)
      const minY = 0;
      const maxY = 50;

      const x = (i) => padL + (i - minX) / (maxX - minX) * iw;
      const y = (v) => {
        const vv = Math.max(minY, Math.min(maxY, v));
        return padT + (1 - ((vv - minY) / (maxY - minY))) * ih;
      };

      // gridlines (0, 10, 20, 30, 40, 50)
      const yTicks = [0,10,20,30,40,50];
      let grid = '';
      for (const t of yTicks) {
        grid += `<line class="tickLine" x1="${padL}" x2="${W-padR}" y1="${y(t)}" y2="${y(t)}" />`;
        grid += `<text class="axisLabel" x="${padL-10}" y="${y(t)+4}" text-anchor="end">${t}%</text>`;
      }

      // path
      let dpath = '';
      let started = false;
      for (let i=0;i<pts.length;i++) {
        const p = pts[i];
        if (p.rate === null || Number.isNaN(p.rate)) { started = false; continue; }
        const cmd = started ? 'L' : 'M';
        dpath += `${cmd}${x(i).toFixed(2)},${y(p.rate).toFixed(2)} `;
        started = true;
      }

      // x labels: show every ~7th tick + last
      let xlabels = '';
      const step = Math.max(1, Math.floor(pts.length / 8));
      for (let i=0;i<pts.length;i+=step) {
        xlabels += `<text class="axisLabel" x="${x(i)}" y="${H-14}" text-anchor="middle">${pts[i].day.slice(5)}</text>`;
      }
      if ((pts.length-1) % step !== 0) {
        const i = pts.length - 1;
        xlabels += `<text class="axisLabel" x="${x(i)}" y="${H-14}" text-anchor="middle">${pts[i].day.slice(5)}</text>`;
      }

      // dots + labels
      let dots = '';
      let labels = '';
      for (let i=0;i<pts.length;i++) {
        const p = pts[i];
        if (p.rate === null || Number.isNaN(p.rate)) continue;
        const title = `${p.day} — ${fmtPct(p.rate)} (${p.connections}/${p.calls})`;
        const cx = x(i);
        const cy = y(p.rate);
        dots += `<circle class="dot" cx="${cx}" cy="${cy}" r="3.5"><title>${title}</title></circle>`;
        labels += `<text class="dotLabel" x="${cx}" y="${Math.max(10, cy-8)}" text-anchor="middle">${fmtPct(p.rate)}</text>`;
      }

      const svg = `
        <svg class="lineChart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
          ${grid}
          <path class="pathLine" d="${dpath}" />
          ${dots}
          ${labels}
          ${xlabels}
        </svg>
      `;
      document.getElementById('chart').innerHTML = svg;
    }

    document.querySelectorAll('#chartMode .pill').forEach(p => {
      p.addEventListener('click', () => setChartMode(p.dataset.mode));
    });

    agentSel.addEventListener('change', () => {
      const u = new URL(window.location.href);
      u.searchParams.set('agent', agentSel.value || '');
      window.history.replaceState({}, '', u.toString());
      renderChart();
    });

    // init
    const urlAgent = url.searchParams.get('agent');
    if (urlAgent) agentSel.value = urlAgent;

    setChartMode(chartMode);

    // Appointments: opps created where lead gen source is Phones or 3PL,
    // limited to setters whose last name matches Kixie agents.
    const kAgents = new Set((k.by_agent || []).map(x => {
      const nm = (x.agent || '').trim();
      const parts = nm.split(/\s+/);
      return (parts.length ? parts[parts.length-1].toLowerCase() : '');
    }).filter(Boolean));

    let appts = 0;
    const createdPhones = createdPhonesRes.ok ? await createdPhonesRes.json() : null;
    const created3pl = created3plRes.ok ? await created3plRes.json() : null;

    if (createdPhones) {
      const created = createdPhones;
      const breakdown = (created.breakdowns && created.breakdowns.created_by_setter_last_name) ? created.breakdowns.created_by_setter_last_name : {};
      for (const [setterLast, cnt] of Object.entries(breakdown || {})) {
        const key = String(setterLast||'').trim().toLowerCase();
        if (kAgents.has(key)) appts += Number(cnt||0);
      }
    }

    if (created3pl) {
      const created = created3pl;
      const breakdown = (created.breakdowns && created.breakdowns.created_by_setter_last_name) ? created.breakdowns.created_by_setter_last_name : {};
      for (const [setterLast, cnt] of Object.entries(breakdown || {})) {
        const key = String(setterLast||'').trim().toLowerCase();
        if (kAgents.has(key)) appts += Number(cnt||0);
      }
    }

    document.getElementById('kpiAppts').textContent = String(appts);
    document.getElementById('kpiApptsMeta').textContent = 'Lead Gen Source: Phones + 3PL';

    // Render setter breakdown chart (top 12) for Phones + 3PL (not limited to Kixie names)
    const setterCounts = {};
    function addBreakdown(resJson) {
      const bd = (resJson.breakdowns && resJson.breakdowns.created_by_setter_last_name) ? resJson.breakdowns.created_by_setter_last_name : {};
      for (const [setterLast, cnt] of Object.entries(bd || {})) {
        const key = (String(setterLast || '—').trim() || '—');
        setterCounts[key] = (setterCounts[key] || 0) + Number(cnt || 0);
      }
    }

    if (createdPhones) addBreakdown(createdPhones);
    if (created3pl) addBreakdown(created3pl);

    const sorted = Object.entries(setterCounts).sort((a,b) => (Number(b[1]||0) - Number(a[1]||0))).slice(0, 12);
    const maxv = Math.max(1, ...sorted.map(x => Number(x[1]||0)));

    let apHtml = '<div class="bars">';
    for (const [name, v0] of sorted) {
      const v = Number(v0||0);
      const pct = Math.max(0, Math.min(100, (v / maxv) * 100));
      apHtml += `<div class="barRow">
        <div class="barName" title="${name}">${name}</div>
        <div class="barTrack"><div class="barFill" style="width:${pct.toFixed(1)}%"></div></div>
        <div class="barVal">${v}</div>
      </div>`;
    }
    apHtml += '</div>';
    document.getElementById('apptsChart').innerHTML = sorted.length ? apHtml : '<div class="meta">No data.</div>';

  }

  // If we defaulted values but URL had no params, set them once
  if (!start || !end) {
    setRange(startEl.value, endEl.value);
  } else {
    load();
  }
</script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


"""
NOTE: This endpoint is intentionally HTML-only; data is loaded via existing JSON metric endpoints.
"""
