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
    .bar { height: 10px; border-radius: 999px; background: #f1f5f9; overflow:hidden; }
    .bar > div { height:100%; background: var(--pink); width:0%; }

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
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
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
      <div class="pill" data-period="2w">Last 2 Weeks</div>
      <div class="pill" data-period="yesterday">Yesterday</div>
      <div class="pill" data-period="thiswk">This Week</div>
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
        <div class="card-title">Connection Rate by Day</div>
        <div class="meta">Connections / Calls</div>
        <div class="chartWrap" id="chart"></div>
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
    // default last 2 weeks
    const today = nyYmd(new Date());
    const s = ymdAddDays(today, -13);
    setActive('2w');
    startEl.value = s;
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
      if (per === '2w') return setRange(ymdAddDays(today,-13), today);
      if (per === 'yesterday') { const y = ymdAddDays(today,-1); return setRange(y,y); }
      if (per === 'thiswk') {
        const dt = new Date();
        const wd = new Intl.DateTimeFormat('en-US', { timeZone:'America/New_York', weekday:'short' }).format(dt);
        const map = { Mon:0, Tue:1, Wed:2, Thu:3, Fri:4, Sat:5, Sun:6 };
        const off = map[wd] ?? 0;
        return setRange(ymdAddDays(today, -off), today);
      }
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
    const oppCreatedUrl = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;

    const [kixieRes, createdRes] = await Promise.all([
      fetch(kixieUrl, { cache:'no-store' }),
      fetch(oppCreatedUrl, { cache:'no-store' })
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

    // Chart (simple bar rows)
    const series = (k.by_day || []);
    let cHtml = '';
    for (const d of series) {
      const rate = (d.connection_rate === null || typeof d.connection_rate === 'undefined') ? 0 : Number(d.connection_rate);
      cHtml += `<div style="display:flex; align-items:center; gap:12px; margin-top:10px">
        <div style="width:110px; font-size:12px; color: var(--muted); font-weight:900">${d.day}</div>
        <div class="bar" style="flex:1"><div style="width:${Math.max(0, Math.min(100, rate)).toFixed(1)}%"></div></div>
        <div style="width:80px; text-align:right; font-variant-numeric: tabular-nums; font-weight:950">${fmtPct(d.connection_rate)}</div>
        <div style="width:120px; text-align:right; color: var(--muted2); font-variant-numeric: tabular-nums;">${d.connections}/${d.calls}</div>
      </div>`;
    }
    document.getElementById('chart').innerHTML = cHtml || '<div class="meta">No data.</div>';

    // Appointments: sum created_by_setter_last_name for last names seen in Kixie agent list
    if (createdRes.ok) {
      const created = await createdRes.json();
      const breakdown = (created.breakdowns && created.breakdowns.created_by_setter_last_name) ? created.breakdowns.created_by_setter_last_name : {};
      const kAgents = new Set((k.by_agent || []).map(x => {
        const nm = (x.agent || '').trim();
        const parts = nm.split(/\s+/);
        return (parts.length ? parts[parts.length-1].toLowerCase() : '');
      }).filter(Boolean));

      let appts = 0;
      for (const [setterLast, cnt] of Object.entries(breakdown || {})) {
        const key = String(setterLast||'').trim().toLowerCase();
        if (kAgents.has(key)) appts += Number(cnt||0);
      }
      document.getElementById('kpiAppts').textContent = String(appts);
    } else {
      document.getElementById('kpiAppts').textContent = '—';
    }
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
