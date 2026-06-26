# -*- coding: utf-8 -*-

"""Vercel Python function: /api/fma_commissions

FMA Commissions dashboard.

Estimated commission rules:
- Demo commission = Sit demos * $100
- Sales commission = Sales * $500

Data sources are fetched client-side from canonical metric endpoints:
- /api/metrics/demo_rate
- /api/metrics/sales
"""

from __future__ import annotations

import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — FMA Commissions</title>
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
      --blue: #2563eb;
      --green: #059669;
      --amber: #d97706;
      --violet: #7c3aed;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body {
      font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }

    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar {
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
      width: 220px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

__DASHBOARD_NAV_CSS__

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

    .dashboardSwitch {
      margin-top: 12px;
      display:flex;
      align-items:center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .dashboardSwitch label {
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .dashboardSwitch select {
      min-width: 240px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fff;
      color: #1f2937;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 800;
      box-shadow: var(--shadow);
    }

    .panel {
      margin-top: 14px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
      box-shadow: var(--shadow);
    }

    .pillbar { display:flex; gap:8px; flex-wrap:wrap; }
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

    .filters {
      margin-top: 10px;
      display:grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      align-items:end;
    }

    .filter label {
      display:block;
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      margin-bottom: 4px;
    }

    input, select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 10px;
      font-size: 13px;
      font-weight: 900;
      background: #fff;
    }

    .btn {
      display:inline-flex;
      align-items:center;
      justify-content:center;
      background: var(--pink);
      border: 1px solid var(--pink);
      color:#fff;
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 13px;
      font-weight: 950;
      cursor:pointer;
      text-decoration:none;
    }
    .btn.secondary {
      background:#fff;
      border-color: var(--border);
      color:#334155;
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
    .span-6 { grid-column: span 6; }
    .span-12 { grid-column: span 12; }

    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .kpi {
      font-size: 40px;
      line-height: 1;
      font-weight: 950;
      letter-spacing: -0.02em;
      margin-top: 10px;
    }
    .kpi.blue { color: var(--blue); }
    .kpi.green { color: var(--green); }
    .kpi.amber { color: var(--amber); }
    .kpi.violet { color: var(--violet); }

    .tableWrap {
      overflow:auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-top: 10px;
      background: #fff;
    }
    table { width:100%; border-collapse: collapse; min-width: 880px; }
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
    tfoot td { font-weight: 950; background:#f8fafc; }
    .num { text-align:right; }

    .empty {
      padding: 18px;
      border: 1px dashed var(--border);
      border-radius: 12px;
      color: var(--muted);
      font-size: 13px;
      text-align:center;
    }

    @media (max-width: 980px) {
      .span-3, .span-6 { grid-column: span 6; }
      .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 680px) {
      .wrap { padding: 12px; }
      .topbar { padding: 12px; }
      .title { font-size: 20px; }
      .nav { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px; }
      .navbtn { white-space: nowrap; flex: 0 0 auto; }
      .span-3, .span-6, .span-12 { grid-column: span 12; }
      .filters { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">FMA Commissions</div>
        <div class="subtitle">Estimated commissions by setter for a selected time period</div>
        <div class="pinkline"></div>
__DASHBOARD_NAV_HTML__
        <div class="nav" style="justify-content:flex-start;">
          <a class="navbtn active" href="/api/fma_commissions">FMA Commissions</a>
          <a class="navbtn" href="/api/settings#secret-lab">Settings</a>
        </div>
        <div class="dashboardSwitch">
          <label for="fmaViewSelect">FMA View</label>
          <select id="fmaViewSelect" onchange="if (this.value) window.location.href = this.value;">
            <option value="/api/fma_dashboard">FMA Dashboard</option>
            <option value="/api/appointment_outcomes">Appointment Outcomes</option>
            <option value="/api/fma_commissions" selected>Commission Tracker</option>
          </select>
        </div>
      </div>
      <div style="min-width:280px;">
        <div class="card-title">Commission Rule</div>
        <div class="meta">$100 per demo (Sit) and $500 per sale.</div>
        <div class="meta" id="statusText">Loading…</div>
      </div>
    </div>

    <div class="panel">
      <div class="pillbar" id="periodTabs">
        <button class="pill active" data-period="thismo">This Month</button>
        <button class="pill" data-period="lastmo">Last Month</button>
        <button class="pill" data-period="today">Today</button>
        <button class="pill" data-period="yesterday">Yesterday</button>
        <button class="pill" data-period="custom">Custom</button>
      </div>

      <div class="filters">
        <div class="filter">
          <label for="startDate">Start</label>
          <input id="startDate" type="date" />
        </div>
        <div class="filter">
          <label for="endDate">End</label>
          <input id="endDate" type="date" />
        </div>
        <div class="filter">
          <label for="leadSource">Lead Source</label>
          <select id="leadSource">
            <option value="">All</option>
            <option value="Doors">Doors</option>
            <option value="Phones">Phones</option>
            <option value="3PL">3PL</option>
            <option value="Self Gen">Self Gen</option>
            <option value="none">none</option>
          </select>
        </div>
        <div class="filter">
          <label for="sortBy">Sort By</label>
          <select id="sortBy">
            <option value="estimated_commission">Estimated Commission</option>
            <option value="sales">Sales</option>
            <option value="demos">Demos</option>
            <option value="setter">Setter</option>
          </select>
        </div>
        <div class="filter">
          <button class="btn" id="applyBtn" style="width:100%;">Apply</button>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Estimated Commission</div>
        <div class="kpi violet" id="kpiCommission">—</div>
        <div class="meta" id="kpiCommissionSub"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Demos</div>
        <div class="kpi blue" id="kpiDemos">—</div>
        <div class="meta" id="kpiDemosSub"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Sales</div>
        <div class="kpi green" id="kpiSales">—</div>
        <div class="meta" id="kpiSalesSub"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Active Setters</div>
        <div class="kpi amber" id="kpiSetters">—</div>
        <div class="meta">FMAs with both door and demo goals in settings</div>
      </div>

      <div class="card span-12">
        <div class="card-title">Setter Breakdown</div>
        <div class="meta">Only FMAs configured in admin settings with both <code>doors_goal</code> and <code>demos_goal</code> for the selected month are shown.</div>
        <div id="rowsHost" class="tableWrap">
          <div class="empty">Loading…</div>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-title">Metric Notes</div>
        <div class="meta">
          Demo commission is based on <strong>Sit</strong> outcomes from <code>/api/metrics/demo_rate</code>.
          Sales commission is based on canonical Sales counts from <code>/api/metrics/sales</code>.
        </div>
      </div>
      <div class="card span-6">
        <div class="card-title">Window Notes</div>
        <div class="meta">
          Demo counts follow the demo metric’s appointment window semantics.
          Sales counts follow the sales metric’s sold-date window semantics.
          FMA membership is determined from admin settings for the month derived from the selected start date.
        </div>
      </div>
    </div>
  </div>

  <script>
    const DEMO_COMMISSION = 100;
    const SALE_COMMISSION = 500;

    function nyYmd(d) {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'
      }).formatToParts(d);
      const out = {};
      for (const p of parts) out[p.type] = p.value;
      return `${out.year}-${out.month}-${out.day}`;
    }

    function ymdAddDays(ymd, days) {
      const [y, m, d] = String(ymd).split('-').map(Number);
      const dt = new Date(Date.UTC(y, m - 1, d));
      dt.setUTCDate(dt.getUTCDate() + days);
      return dt.toISOString().slice(0, 10);
    }

    function currentMonthRange() {
      const now = new Date();
      const nowYmd = nyYmd(now);
      return { start: `${nowYmd.slice(0, 8)}01`, end: nowYmd };
    }

    function lastMonthRange() {
      const now = new Date();
      const parts = nyYmd(now).split('-').map(Number);
      let y = parts[0], m = parts[1] - 1;
      if (m === 0) { m = 12; y -= 1; }
      const start = `${y}-${String(m).padStart(2, '0')}-01`;
      const nextMonth = m === 12 ? new Date(Date.UTC(y + 1, 0, 1)) : new Date(Date.UTC(y, m, 1));
      const end = new Date(nextMonth.getTime() - 86400000).toISOString().slice(0, 10);
      return { start, end };
    }

    function formatMoney(n) {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(n || 0));
    }

    function formatNum(n) {
      return new Intl.NumberFormat('en-US').format(Number(n || 0));
    }

    function esc(s) {
      return String(s == null ? '' : s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }

    function normSetter(v) {
      return String(v || '').trim();
    }

    function setActivePeriod(period) {
      document.querySelectorAll('#periodTabs .pill').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-period') === period);
      });
    }

    function applyPreset(period) {
      const startEl = document.getElementById('startDate');
      const endEl = document.getElementById('endDate');
      const today = nyYmd(new Date());
      let range = currentMonthRange();
      if (period === 'today') range = { start: today, end: today };
      if (period === 'yesterday') {
        const y = ymdAddDays(today, -1);
        range = { start: y, end: y };
      }
      if (period === 'lastmo') range = lastMonthRange();
      if (period === 'custom') return;
      startEl.value = range.start;
      endEl.value = range.end;
      setActivePeriod(period);
    }

    async function fetchJson(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
      return await res.json();
    }

    function renderRows(rows) {
      const host = document.getElementById('rowsHost');
      if (!rows.length) {
        host.innerHTML = '<div class="empty">No demos or sales found for this range.</div>';
        return;
      }

      const totals = rows.reduce((acc, row) => {
        acc.demos += row.demos;
        acc.sales += row.sales;
        acc.demo_commission += row.demo_commission;
        acc.sales_commission += row.sales_commission;
        acc.estimated_commission += row.estimated_commission;
        return acc;
      }, { demos: 0, sales: 0, demo_commission: 0, sales_commission: 0, estimated_commission: 0 });

      host.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>FMA</th>
              <th class="num">Demos</th>
              <th class="num">Sales</th>
              <th class="num">Demo Comm.</th>
              <th class="num">Sales Comm.</th>
              <th class="num">Estimated Comm.</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${esc(row.display_name)}<div style="color:#94a3b8; font-size:11px; font-weight:800; margin-top:2px;">${esc(row.setter)}</div></td>
                <td class="num">${formatNum(row.demos)}</td>
                <td class="num">${formatNum(row.sales)}</td>
                <td class="num">${formatMoney(row.demo_commission)}</td>
                <td class="num">${formatMoney(row.sales_commission)}</td>
                <td class="num">${formatMoney(row.estimated_commission)}</td>
              </tr>
            `).join('')}
          </tbody>
          <tfoot>
            <tr>
              <td>TOTAL</td>
              <td class="num">${formatNum(totals.demos)}</td>
              <td class="num">${formatNum(totals.sales)}</td>
              <td class="num">${formatMoney(totals.demo_commission)}</td>
              <td class="num">${formatMoney(totals.sales_commission)}</td>
              <td class="num">${formatMoney(totals.estimated_commission)}</td>
            </tr>
          </tfoot>
        </table>
      `;
    }

    async function load() {
      const start = document.getElementById('startDate').value;
      const end = document.getElementById('endDate').value;
      const leadSource = document.getElementById('leadSource').value;
      const sortBy = document.getElementById('sortBy').value;
      const leadParam = leadSource ? `&lead_source=${encodeURIComponent(leadSource)}` : '';
      const q = `format=json&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}${leadParam}`;

      document.getElementById('statusText').textContent = `Loading ${start} → ${end}…`;

      try {
        const monthStr = String(start || '').slice(0, 7);
        const settingsReq = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'bootstrap', month: monthStr })
        };

        const [demoData, salesData, settingsData] = await Promise.all([
          fetchJson(`/api/metrics/demo_rate?${q}`),
          fetchJson(`/api/metrics/sales?${q}`),
          fetch('/api/settings_api', settingsReq).then(async res => {
            if (!res.ok) throw new Error(`HTTP ${res.status} for /api/settings_api`);
            return await res.json();
          })
        ]);

        const demoBySetter = (demoData && demoData.breakdowns && demoData.breakdowns.sit_by_setter_last_name) || {};
        const salesBySetter = (salesData && salesData.breakdowns && salesData.breakdowns.sales_by_setter_last_name) || {};

        const roster = Array.isArray(settingsData && settingsData.roster_people) ? settingsData.roster_people : [];
        const goals = Array.isArray(settingsData && settingsData.goals_for_month) ? settingsData.goals_for_month : [];

        const goalsByPerson = {};
        for (const g of goals) {
          const pk = String(g.person_key || '').trim();
          const metric = String(g.metric || '').trim();
          if (!pk || !metric) continue;
          if (!goalsByPerson[pk]) goalsByPerson[pk] = {};
          goalsByPerson[pk][metric] = Number(g.value || 0);
        }

        const activeFmas = [];
        for (const r of roster) {
          const personKey = String(r.person_key || '').trim();
          const setter = normSetter(r.ghl_setter_last_name || '');
          const role = String(r.role || '').trim().toLowerCase();
          const personGoals = goalsByPerson[personKey] || {};
          if (!setter) continue;
          if (role !== 'setter') continue;
          if (typeof personGoals.doors_goal === 'undefined') continue;
          if (typeof personGoals.demos_goal === 'undefined') continue;
          activeFmas.push({
            person_key: personKey,
            setter,
            display_name: String(r.display_name || r.raydar_user_name || r.ghl_user_name || setter).trim() || setter
          });
        }

        const rows = activeFmas.map(item => {
          const demos = Number(demoBySetter[item.setter] || 0);
          const sales = Number(salesBySetter[item.setter] || 0);
          return {
            setter: item.setter,
            display_name: item.display_name,
            demos,
            sales,
            demo_commission: demos * DEMO_COMMISSION,
            sales_commission: sales * SALE_COMMISSION,
            estimated_commission: (demos * DEMO_COMMISSION) + (sales * SALE_COMMISSION)
          };
        });

        rows.sort((a, b) => {
          if (sortBy === 'setter') return a.display_name.localeCompare(b.display_name);
          return Number(b[sortBy] || 0) - Number(a[sortBy] || 0);
        });

        const totalDemos = rows.reduce((s, r) => s + r.demos, 0);
        const totalSales = rows.reduce((s, r) => s + r.sales, 0);
        const totalCommission = rows.reduce((s, r) => s + r.estimated_commission, 0);

        document.getElementById('kpiCommission').textContent = formatMoney(totalCommission);
        document.getElementById('kpiCommissionSub').textContent = `${formatMoney(totalDemos * DEMO_COMMISSION)} from demos + ${formatMoney(totalSales * SALE_COMMISSION)} from sales`;
        document.getElementById('kpiDemos').textContent = formatNum(totalDemos);
        document.getElementById('kpiDemosSub').textContent = `${formatMoney(totalDemos * DEMO_COMMISSION)} estimated`;
        document.getElementById('kpiSales').textContent = formatNum(totalSales);
        document.getElementById('kpiSalesSub').textContent = `${formatMoney(totalSales * SALE_COMMISSION)} estimated`;
        document.getElementById('kpiSetters').textContent = formatNum(rows.length);
        document.getElementById('statusText').textContent = `Loaded ${start} → ${end}${leadSource ? ` • ${leadSource}` : ''} • ${rows.length} active FMAs`;

        renderRows(rows);
      } catch (err) {
        document.getElementById('statusText').textContent = String(err);
        document.getElementById('rowsHost').innerHTML = `<div class="empty">${esc(String(err))}</div>`;
      }
    }

    document.querySelectorAll('#periodTabs .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        const period = btn.getAttribute('data-period');
        applyPreset(period);
        if (period !== 'custom') load();
      });
    });
    document.getElementById('applyBtn').addEventListener('click', load);

    (function init() {
      const range = currentMonthRange();
      document.getElementById('startDate').value = range.start;
      document.getElementById('endDate').value = range.end;
      load();
    })();
  </script>
</body>
</html>
""".replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css()).replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("fma_commissions"))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
