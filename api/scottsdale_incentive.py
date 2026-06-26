# -*- coding: utf-8 -*-

"""Vercel Python function: /api/scottsdale_incentive

Scottsdale Summer Incentive dashboard.

Fixed incentive window:
- 2026-05-20 through 2026-09-30

Sections:
- Sales Reps: progress to 43 sales
- FMAs: progress to 63 sit demos

Data sources are fetched client-side from canonical metric endpoints:
- /api/metrics/sales
- /api/metrics/demo_rate
"""

from __future__ import annotations

import sys
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
  <title>Happy Solar — Scottsdale Incentive</title>
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
      --rose: #f43f5e;
      --blue: #2563eb;
      --cyan: #0891b2;
      --green: #059669;
      --amber: #d97706;
      --violet: #7c3aed;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      background: var(--bg);
      color: var(--text);
    }

    .wrap { max-width: 1240px; margin: 0 auto; padding: 22px; }

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
      font-size: 24px;
      font-weight: 950;
      letter-spacing: -0.02em;
      color: #1a2b4a;
    }

    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px;
      width: 240px;
      border-radius: 999px;
      margin-top: 10px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 42%, rgba(244,114,182,0) 100%);
    }

__DASHBOARD_NAV_CSS__

    .navbtn {
      display: inline-flex;
      align-items: center;
      padding: 9px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      color: #1f2937;
      font-size: 13px;
      font-weight: 800;
      text-decoration: none;
    }

    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .statusCard {
      min-width: 290px;
      max-width: 360px;
    }

    .eyebrow {
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .heroRange {
      margin-top: 8px;
      font-size: 18px;
      font-weight: 900;
      color: #0f172a;
    }

    .heroMeta {
      margin-top: 6px;
      color: var(--muted2);
      font-size: 12px;
    }

    .grid {
      display: grid;
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

    .sectionHead {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
      margin-bottom: 2px;
    }

    .sectionTitle {
      font-size: 16px;
      font-weight: 950;
      color: #111827;
      letter-spacing: -0.01em;
    }

    .sectionMeta {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }

    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .kpi {
      margin-top: 10px;
      font-size: 40px;
      line-height: 1;
      font-weight: 950;
      letter-spacing: -0.02em;
    }
    .kpi.rose { color: var(--rose); }
    .kpi.blue { color: var(--blue); }
    .kpi.green { color: var(--green); }
    .kpi.violet { color: var(--violet); }
    .kpi.amber { color: var(--amber); }
    .kpi.cyan { color: var(--cyan); }

    .progressRail {
      margin-top: 12px;
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: #f1f5f9;
      border: 1px solid var(--border);
    }

    .progressBar {
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 100%);
      transition: width 240ms ease;
    }

    .miniProgress {
      height: 8px;
      border-radius: 999px;
      overflow: hidden;
      background: #f8fafc;
      border: 1px solid var(--border);
      min-width: 140px;
    }

    .miniProgress > div {
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 100%);
    }

    .tableWrap {
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fff;
      margin-top: 10px;
    }

    table { width: 100%; border-collapse: collapse; min-width: 760px; }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 10px 12px;
      font-size: 12px;
      text-align: left;
      font-variant-numeric: tabular-nums;
    }
    th { color: var(--muted); font-weight: 950; background: #f8fafc; }
    td { color: #0f172a; font-weight: 800; }
    tbody tr:nth-child(even) { background: #fcfdff; }

    .num { text-align: right; }

    .empty {
      padding: 18px;
      border: 1px dashed var(--border);
      border-radius: 12px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
      margin-top: 10px;
    }

    @media (max-width: 980px) {
      .span-3, .span-4, .span-6, .span-8 { grid-column: span 6; }
    }
    @media (max-width: 680px) {
      .wrap { padding: 12px; }
      .topbar { padding: 12px; }
      .title { font-size: 20px; }
      .nav { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px; }
      .navbtn { white-space: nowrap; flex: 0 0 auto; }
      .span-3, .span-4, .span-6, .span-8, .span-12 { grid-column: span 12; }
      table { min-width: 640px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Scottsdale Incentive</div>
        <div class="subtitle">Summer incentive scoreboard for sales reps and FMAs</div>
        <div class="pinkline"></div>
__DASHBOARD_NAV_HTML__
        <div class="nav" style="justify-content:flex-start;">
          <a class="navbtn active" href="/api/scottsdale_incentive">Scottsdale Incentive</a>
          <a class="navbtn" href="/api/settings#secret-lab">Settings</a>
        </div>
      </div>
      <div class="statusCard">
        <div class="eyebrow">Incentive Window</div>
        <div class="heroRange">May 20, 2026 → September 30, 2026</div>
        <div class="heroMeta">Sales goal: 43 sales. FMA goal: 63 sit demos.</div>
        <div class="heroMeta" id="statusText">Loading canonical metric feeds…</div>
      </div>
    </div>

    <div class="sectionHead">
      <div>
        <div class="sectionTitle">Sales Reps</div>
        <div class="sectionMeta">Using canonical sales counts from <code>/api/metrics/sales</code>.</div>
      </div>
      <div class="sectionMeta">Goal: <strong>43 sales</strong></div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Sales Goal</div>
        <div class="kpi rose">43</div>
        <div class="meta">Sales</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Top Rep</div>
        <div class="kpi green" id="salesTopValue">—</div>
        <div class="meta" id="salesTopMeta"></div>
      </div>

      <div class="card span-8">
        <div class="card-title">Sales Rep Leaderboard</div>
        <div class="tableWrap" id="salesRows"><div class="empty">Loading…</div></div>
      </div>
      <div class="card span-4">
        <div class="card-title">Sales Notes</div>
        <div class="meta">
          Sales are counted from the canonical sales metric using the sold-date window semantics in
          <code>America/New_York</code>.
        </div>
        <div class="meta">
          Breakdown source: <code>sales_by_owner</code>.
        </div>
      </div>
    </div>

    <div class="sectionHead">
      <div>
        <div class="sectionTitle">FMAs</div>
        <div class="sectionMeta">Using sit demo counts from <code>/api/metrics/demo_rate</code>.</div>
      </div>
      <div class="sectionMeta">Goal: <strong>63 demos</strong></div>
    </div>

    <div class="grid">
      <div class="card span-3">
        <div class="card-title">Demo Goal</div>
        <div class="kpi blue">63</div>
        <div class="meta">Demos</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Top FMA</div>
        <div class="kpi green" id="demoTopValue">—</div>
        <div class="meta" id="demoTopMeta"></div>
      </div>

      <div class="card span-8">
        <div class="card-title">FMA Leaderboard</div>
        <div class="tableWrap" id="demoRows"><div class="empty">Loading…</div></div>
      </div>
      <div class="card span-4">
        <div class="card-title">Demo Notes</div>
        <div class="meta">
          Demos are <strong>Sit</strong> outcomes only, using the canonical demo metric appointment window semantics in
          <code>America/New_York</code>.
        </div>
        <div class="meta">
          Breakdown source: <code>sit_by_setter_last_name</code>.
        </div>
      </div>
    </div>
  </div>

  <script>
    const START = '2026-05-20';
    const END = '2026-09-30';
    const SALES_GOAL = 43;
    const DEMO_GOAL = 63;

    function esc(s) {
      return String(s == null ? '' : s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }

    function formatNum(n) {
      return new Intl.NumberFormat('en-US').format(Number(n || 0));
    }

    function pct(value, goal) {
      if (!goal) return 0;
      return (Number(value || 0) / Number(goal)) * 100;
    }

    function clampPct(v) {
      return Math.max(0, Math.min(100, Number(v || 0)));
    }

    function normName(v) {
      return String(v || '').trim();
    }

    function filteredEntries(obj, skipNone) {
      return Object.entries(obj || {})
        .map(([name, value]) => [normName(name), Number(value || 0)])
        .filter(([name, value]) => name && value > 0 && (!skipNone || name.toLowerCase() !== 'none'))
        .sort((a, b) => Number(b[1]) - Number(a[1]) || a[0].localeCompare(b[0]));
    }

    function addManualCount(entries, targetName, delta) {
      const wanted = String(targetName || '').trim().toLowerCase();
      if (!wanted || !delta) return entries.slice();

      const adjusted = entries.map(([name, value]) => [name, value]);
      const idx = adjusted.findIndex(([name]) => String(name || '').trim().toLowerCase() === wanted);
      if (idx >= 0) {
        adjusted[idx][1] = Number(adjusted[idx][1] || 0) + Number(delta || 0);
      } else {
        adjusted.push([targetName, Number(delta || 0)]);
      }

      return adjusted.sort((a, b) => Number(b[1]) - Number(a[1]) || a[0].localeCompare(b[0]));
    }

    function renderLeaderboard(hostId, rows, goalLabel) {
      const host = document.getElementById(hostId);
      if (!rows.length) {
        host.innerHTML = '<div class="empty">No activity found for this incentive window.</div>';
        return;
      }

      host.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th class="num">${esc(goalLabel)}</th>
              <th>Progress</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${esc(row.name)}</td>
                <td class="num">${formatNum(row.value)}</td>
                <td>
                  <div style="display:flex; align-items:center; gap:10px;">
                    <div class="miniProgress"><div style="width:${clampPct(row.goal_pct)}%"></div></div>
                    <span>${row.goal_pct.toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    async function fetchJson(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
      return await res.json();
    }

    async function load() {
      const q = `format=json&start=${encodeURIComponent(START)}&end=${encodeURIComponent(END)}`;
      document.getElementById('statusText').textContent = `Loading ${START} → ${END}…`;

      try {
        const [salesData, demoData] = await Promise.all([
          fetchJson(`/api/metrics/sales?${q}`),
          fetchJson(`/api/metrics/demo_rate?${q}`),
        ]);

        const salesEntries = addManualCount(
          addManualCount(
            filteredEntries((salesData && salesData.breakdowns && salesData.breakdowns.sales_by_owner) || {}, true),
            'Brooke Simpson',
            1
          ),
          'Zach Maecker',
          1
        );
        const demoEntries = filteredEntries((demoData && demoData.breakdowns && demoData.breakdowns.sit_by_setter_last_name) || {}, true);

        const totalSales = salesEntries.reduce((sum, [, value]) => sum + value, 0);
        const totalDemos = demoEntries.reduce((sum, [, value]) => sum + value, 0);

        const salesRows = salesEntries.map(([name, value]) => ({
          name,
          value,
          goal_pct: pct(value, SALES_GOAL),
        }));

        const demoRows = demoEntries.map(([name, value]) => ({
          name,
          value,
          goal_pct: pct(value, DEMO_GOAL),
        }));

        const salesTop = salesRows[0] || null;
        const demoTop = demoRows[0] || null;
        document.getElementById('salesTopValue').textContent = salesTop ? formatNum(salesTop.value) : '0';
        document.getElementById('salesTopMeta').textContent = salesTop ? `${salesTop.name} currently leads` : 'No sales yet';

        document.getElementById('demoTopValue').textContent = demoTop ? formatNum(demoTop.value) : '0';
        document.getElementById('demoTopMeta').textContent = demoTop ? `${demoTop.name} currently leads` : 'No demos yet';

        renderLeaderboard('salesRows', salesRows, 'Sales');
        renderLeaderboard('demoRows', demoRows, 'Sit Demos');

        document.getElementById('statusText').textContent = `Loaded canonical sales and demo metrics for ${START} → ${END}.`;
      } catch (err) {
        const msg = String(err);
        document.getElementById('statusText').textContent = msg;
        document.getElementById('salesRows').innerHTML = `<div class="empty">${esc(msg)}</div>`;
        document.getElementById('demoRows').innerHTML = `<div class="empty">${esc(msg)}</div>`;
      }
    }

    load();
  </script>
</body>
</html>
""".replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css()).replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("scottsdale_incentive"))


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
