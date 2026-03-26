# -*- coding: utf-8 -*-

"""Vercel Python function: /api/daily_update

Daily Update dashboard for morning meetings.

Uses existing metric APIs with date-only window (America/New_York):
- /api/metrics/sales
- /api/metrics/opportunities_created
- /api/metrics/raydar_doors_knocked
- /api/metrics/kixie_calls_summary
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler


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

    .title { font-size: 24px; font-weight: 950; color: #1a2b4a; letter-spacing: -0.02em; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px; width: 220px; border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

    .nav { margin-top: 12px; display:flex; gap: 10px; flex-wrap: wrap; }
    .navbtn {
      display:inline-flex; align-items:center; padding: 9px 12px;
      border-radius: 12px; border: 1px solid var(--border);
      background: #fff; color: #1f2937; font-size: 13px; font-weight: 800; text-decoration:none;
    }
    .navbtn.active { background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color: #b80b66; }

    .filters { display:flex; align-items:flex-end; gap: 10px; flex-wrap: wrap; }
    .filters label { display:block; font-size: 12px; color: var(--muted); font-weight: 900; margin-bottom: 4px; }
    .filters input[type=date] {
      border: 1px solid var(--border); border-radius: 10px; padding: 9px 10px; font-size: 13px; font-weight: 900; background:#fff;
    }
    .btn {
      display:inline-flex; align-items:center; justify-content:center;
      border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px;
      background:#fff; color:#334155; font-size: 12px; font-weight: 900; cursor:pointer;
      text-decoration:none;
    }
    .btn.primary { background: var(--green); border-color: var(--green); color: #fff; }

    .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap: 14px; margin-top: 14px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow); }
    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-12 { grid-column: span 12; }

    @media (max-width: 1200px) { .span-3, .span-4, .span-6 { grid-column: span 12; } }

    .kpi-label { color: var(--muted); font-size: 12px; font-weight: 900; }
    .kpi { margin-top: 4px; font-size: 36px; font-weight: 950; }
    .kpi-sub { margin-top: 6px; font-size: 12px; color: var(--muted2); }

    .card-title { color: var(--muted); font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: .03em; }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom: 1px solid var(--border); padding: 8px; font-size: 12px; text-align: left; }
    th { color: var(--muted); font-weight: 950; }
    td { color: #0f172a; font-weight: 800; }
    td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }

    .muted { color: var(--muted2); }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Daily Dashboard</div>
        <div class=\"subtitle\">Morning meeting snapshot across GHL, Raydar, and Kixie</div>
        <div class=\"pinkline\"></div>
        <div class=\"nav\">
          <a class=\"navbtn\" href=\"/api/company_overview\">Company Overview</a>
          <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales Dashboard</a>
          <a class=\"navbtn\" href=\"/api/fma_dashboard\">FMA Dashboard</a>
          <a class=\"navbtn\" href=\"/api/virtual_team_dashboard\">Virtual Team</a>
          <a class=\"navbtn active\" href=\"/api/daily_update\">Daily Dashboard</a>
          <a class=\"navbtn\" href=\"/api/settings\">Settings</a>
        </div>
      </div>

      <div>
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
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-3\">
        <div class=\"kpi-label\">Sales (GHL)</div>
        <div class=\"kpi\" id=\"kpiSales\">—</div>
      </div>
      <div class=\"card span-3\">
        <div class=\"kpi-label\">Opportunities Created (GHL)</div>
        <div class=\"kpi\" id=\"kpiOpps\">—</div>
      </div>
      <div class=\"card span-3\">
        <div class=\"kpi-label\">Door Knocks (Raydar)</div>
        <div class=\"kpi\" id=\"kpiKnocks\">—</div>
      </div>
      <div class=\"card span-3\">
        <div class=\"kpi-label\">Kixie Calls</div>
        <div class=\"kpi\" id=\"kpiCalls\">—</div>
        <div class=\"kpi-sub\" id=\"kpiConn\">Connections: —</div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-3\">
        <div class=\"card-title\">Sales by Owner</div>
        <div id=\"tblSalesOwner\"></div>
      </div>
      <div class=\"card span-3\">
        <div class=\"card-title\">Sales by Setter Last Name</div>
        <div id=\"tblSalesSetter\"></div>
      </div>
      <div class=\"card span-3\">
        <div class=\"card-title\">Sales by Lead Gen Source</div>
        <div id=\"tblSalesLead\"></div>
      </div>
      <div class=\"card span-3\">
        <div class=\"card-title\">Opportunities Created by Lead Gen Source</div>
        <div id=\"tblOppsLead\"></div>
      </div>

      <div class=\"card span-6\">
        <div class=\"card-title\">Opportunities Created by Setter Last Name</div>
        <div id=\"tblOppsSetter\"></div>
      </div>
      <div class=\"card span-6\">
        <div class=\"card-title\">Door Knocks by Raydar User</div>
        <div id=\"tblKnocks\"></div>
      </div>

      <div class=\"card span-12\">
        <div class=\"card-title\">Kixie Calls by User</div>
        <div id=\"tblKixie\"></div>
      </div>
    </div>
  </div>

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

  function percentFmt(v) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${n.toFixed(1)}%`;
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

  function renderKixieTable(containerId, rows) {
    const el = document.getElementById(containerId);
    const list = Array.isArray(rows) ? rows.slice().sort((a,b)=> (Number(b.calls||0)-Number(a.calls||0)) || String(a.agent||'').localeCompare(String(b.agent||''))) : [];
    if (!list.length) {
      el.innerHTML = `<div class=\"muted\" style=\"margin-top:8px\">No rows</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>User</th>
            <th class=\"num\">Calls</th>
            <th class=\"num\">Connections</th>
            <th class=\"num\">Connection %</th>
          </tr>
        </thead>
        <tbody>
          ${list.map(r => `<tr><td>${r.agent || '—'}</td><td class=\"num\">${numberFmt(r.calls)}</td><td class=\"num\">${numberFmt(r.connections)}</td><td class=\"num\">${percentFmt(r.connection_rate)}</td></tr>`).join('')}
        </tbody>
      </table>
    `;
  }

  async function fetchJson(u) {
    const res = await fetch(u);
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

    const q = `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=json`;

    try {
      const [sales, opps, knocks, kixie] = await Promise.all([
        fetchJson(`/api/metrics/sales?${q}&dedupe_by=contact`),
        fetchJson(`/api/metrics/opportunities_created?${q}`),
        fetchJson(`/api/metrics/raydar_doors_knocked?${q}`),
        fetchJson(`/api/metrics/kixie_calls_summary?${q}`),
      ]);

      document.getElementById('kpiSales').textContent = numberFmt(sales.result);
      document.getElementById('kpiOpps').textContent = numberFmt(opps.result);
      document.getElementById('kpiKnocks').textContent = numberFmt(knocks.result);
      document.getElementById('kpiCalls').textContent = numberFmt(kixie.calls);
      document.getElementById('kpiConn').textContent = `Connections: ${numberFmt(kixie.connections)} (${percentFmt(kixie.connection_rate)})`;

      renderKVTable('tblSalesOwner', sales?.breakdowns?.sales_by_owner || {}, 'Sales');
      renderKVTable('tblSalesSetter', sales?.breakdowns?.sales_by_setter_last_name || {}, 'Sales');
      renderKVTable('tblSalesLead', sales?.breakdowns?.sales_by_lead_gen_source || {}, 'Sales');
      renderKVTable('tblOppsLead', opps?.breakdowns?.created_by_lead_gen_source || {}, 'Opps');

      renderKVTable('tblOppsSetter', opps?.breakdowns?.created_by_setter_last_name || {}, 'Opps');

      // Match FMA schema: use knocks_by_actor and map actor id -> Raydar user name.
      const knocksByActor = (knocks && knocks.breakdowns && knocks.breakdowns.knocks_by_actor) ? knocks.breakdowns.knocks_by_actor : {};
      const topKnockers = Array.isArray(knocks?.top_knockers) ? knocks.top_knockers : [];
      const actorNameMap = {};
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

      renderKixieTable('tblKixie', kixie?.by_agent || []);

      document.getElementById('status').textContent = `Loaded daily update for ${start} → ${end}`;
    } catch (e) {
      console.error(e);
      document.getElementById('status').textContent = `Error loading dashboard: ${String(e)}`;
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

  load();
</script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
