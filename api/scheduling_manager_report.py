# -*- coding: utf-8 -*-

"""Vercel Python function: /api/scheduling_manager_report

Scheduling Manager report UI.
"""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def month_defaults(year: int, month: int) -> tuple[str, str]:
    from calendar import monthrange

    last_day = monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def render_html(start: str, end: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Scheduling Manager Report</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --pink: #ec4899;
      --orange: #f97316;
      --teal: #14b8a6;
      --blue: #38bdf8;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }}

    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Georgia, 'Times New Roman', serif; background: radial-gradient(circle at top, #fff7fb 0%, var(--bg) 42%, #eef3f8 100%); color: var(--text); }}
    .wrap {{ max-width: 1240px; margin: 0 auto; padding: 24px; }}
    .topbar {{
      background: rgba(255,255,255,0.94);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 20px 22px;
      position: relative;
      overflow: hidden;
    }}
    .topbar::after {{
      content: "";
      position: absolute;
      inset: auto -40px -90px auto;
      width: 220px;
      height: 220px;
      background: radial-gradient(circle, rgba(236,72,153,0.16) 0%, rgba(249,115,22,0.10) 38%, rgba(255,255,255,0) 72%);
      pointer-events: none;
    }}
    .eyebrow {{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: var(--muted); font-weight: 700; }}
    .title {{ margin-top: 8px; font-size: 32px; line-height: 1.05; font-weight: 800; letter-spacing: -0.03em; max-width: 760px; }}
    .subtitle {{ margin-top: 8px; font-size: 14px; color: var(--muted); max-width: 760px; }}
    .pinkline {{ margin-top: 14px; height: 4px; width: 220px; border-radius: 999px; background: linear-gradient(90deg, var(--pink) 0%, var(--orange) 54%, rgba(249,115,22,0) 100%); }}
    .filters {{ margin-top: 18px; display:flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .filters label {{ font-size: 12px; font-weight: 700; color: var(--muted); }}
    .filters input, .filters select, .filters button {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
      background: #fff;
      color: var(--text);
      font-size: 13px;
      font-family: inherit;
    }}
    .filters button {{
      background: linear-gradient(135deg, var(--pink) 0%, var(--orange) 100%);
      color: #fff;
      font-weight: 800;
      border: none;
      cursor: pointer;
    }}
    .grid {{ display:grid; grid-template-columns: repeat(12, 1fr); gap: 14px; margin-top: 14px; }}
    .card {{
      background: rgba(255,255,255,0.94);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 16px 18px;
    }}
    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
    .span-12 {{ grid-column: span 12; }}
    .card-title {{ font-size: 12px; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); font-weight: 800; }}
    .kpi {{ margin-top: 10px; font-size: 42px; font-weight: 800; letter-spacing: -0.04em; }}
    .meta {{ margin-top: 6px; color: var(--muted); font-size: 13px; }}
    .bars {{
      margin-top: 16px;
      min-height: 340px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
      gap: 12px;
      align-items: end;
    }}
    .bar-col {{ display:flex; flex-direction: column; align-items:center; gap: 8px; min-width: 0; }}
    .bar-stack {{ width: 100%; min-height: 260px; display:flex; align-items:flex-end; justify-content:center; gap: 8px; }}
    .bar {{
      width: min(34px, 42%);
      border-radius: 12px 12px 0 0;
      position: relative;
      min-height: 8px;
      box-shadow: inset 0 -10px 14px rgba(0,0,0,0.08);
    }}
    .bar.created {{ background: linear-gradient(180deg, rgba(236,72,153,0.92) 0%, rgba(249,115,22,0.92) 100%); }}
    .bar.demoed {{ background: linear-gradient(180deg, rgba(20,184,166,0.92) 0%, rgba(56,189,248,0.92) 100%); }}
    .bar-value {{
      position: absolute;
      top: -24px;
      left: 50%;
      transform: translateX(-50%);
      font-size: 11px;
      font-weight: 800;
      color: #334155;
      white-space: nowrap;
    }}
    .bar-label {{
      width: 100%;
      text-align: center;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .bar-sub {{ font-size: 11px; color: var(--muted); }}
    .legend {{ display:flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    .swatch {{ display:inline-block; width: 10px; height: 10px; border-radius: 999px; margin-right: 6px; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 10px 8px; text-align:left; font-size: 13px; }}
    th {{ color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-size: 11px; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .loading, .empty {{ padding: 30px 0; color: var(--muted); text-align:center; }}
    .error {{ margin-top: 12px; color: #b91c1c; font-weight: 700; }}
    .foot {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 980px) {{
      .span-4, .span-6 {{ grid-column: span 12; }}
      .wrap {{ padding: 14px; }}
      .title {{ font-size: 26px; }}
      .kpi {{ font-size: 34px; }}
      .bars {{ grid-template-columns: repeat(auto-fit, minmax(76px, 1fr)); }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="eyebrow">Happy Solar Reporting</div>
      <div class="title">Scheduling Manager Report</div>
      <div class="subtitle">Created-opportunity cohort view of scheduling-manager ownership, completed demos, and demo conversion.</div>
      <div class="pinkline"></div>
      <div class="filters">
        <label>Start <input id="start" type="date" value="{start}" /></label>
        <label>End <input id="end" type="date" value="{end}" /></label>
        <label>Pipeline Scope
          <select id="pipelineScope">
            <option value="core" selected>Core Pipelines</option>
            <option value="all">All Pipelines</option>
          </select>
        </label>
        <button id="applyBtn">Apply</button>
      </div>
      <div id="errorBox" class="error" style="display:none;"></div>
    </div>

    <div class="grid">
      <div class="card span-4">
        <div class="card-title">Opps With Scheduling Manager</div>
        <div id="kpiCreated" class="kpi">—</div>
        <div class="meta">Created in selected window with a populated scheduling-manager value.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Demo'd Opps</div>
        <div id="kpiDemoed" class="kpi">—</div>
        <div class="meta">Created-cohort opps whose appointment disposition is currently <strong>Sit</strong>.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Demo Percentage</div>
        <div id="kpiPct" class="kpi">—</div>
        <div class="meta">Demo'd opps divided by created opps in the same cohort.</div>
      </div>

      <div class="card span-6">
        <div class="card-title">Created Opps By Scheduling Manager</div>
        <div class="legend"><span><span class="swatch" style="background:linear-gradient(180deg, rgba(236,72,153,0.92) 0%, rgba(249,115,22,0.92) 100%);"></span>Created</span></div>
        <div id="createdBars" class="bars"><div class="loading">Loading…</div></div>
      </div>

      <div class="card span-6">
        <div class="card-title">Created vs Demo'd</div>
        <div class="legend">
          <span><span class="swatch" style="background:linear-gradient(180deg, rgba(236,72,153,0.92) 0%, rgba(249,115,22,0.92) 100%);"></span>Created</span>
          <span><span class="swatch" style="background:linear-gradient(180deg, rgba(20,184,166,0.92) 0%, rgba(56,189,248,0.92) 100%);"></span>Demo'd</span>
        </div>
        <div id="pairBars" class="bars"><div class="loading">Loading…</div></div>
      </div>

      <div class="card span-12">
        <div class="card-title">Scheduling Manager Table</div>
        <table>
          <thead>
            <tr><th>Scheduling Manager</th><th class="num">Created</th><th class="num">Demo'd</th><th class="num">Demo %</th></tr>
          </thead>
          <tbody id="summaryBody"><tr><td colspan="4" class="loading">Loading…</td></tr></tbody>
        </table>
        <div id="footnote" class="foot"></div>
      </div>
    </div>
  </div>

  <script>
    const nf = new Intl.NumberFormat('en-US');

    function esc(text) {{
      return String(text ?? '').replace(/[&<>"']/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }})[ch]);
    }}

    function q() {{
      const start = document.getElementById('start').value;
      const end = document.getElementById('end').value;
      const pipelineScope = document.getElementById('pipelineScope').value || 'core';
      const params = new URLSearchParams();
      params.set('format', 'json');
      if (start) params.set('start', start);
      if (end) params.set('end', end);
      params.set('pipeline_scope', pipelineScope);
      return params.toString();
    }}

    function setError(msg) {{
      const box = document.getElementById('errorBox');
      if (!msg) {{
        box.style.display = 'none';
        box.textContent = '';
        return;
      }}
      box.style.display = 'block';
      box.textContent = msg;
    }}

    function fmtPct(value) {{
      const num = Number(value || 0);
      return Number.isFinite(num) ? num.toFixed(1) + '%' : '—';
    }}

    function renderSingleBars(targetId, rows) {{
      const host = document.getElementById(targetId);
      if (!rows.length) {{
        host.innerHTML = '<div class="empty">No matching scheduling-manager opps in this window.</div>';
        return;
      }}
      const maxCreated = Math.max(...rows.map((row) => Number(row.created || 0)), 1);
      host.innerHTML = rows.map((row) => {{
        const createdHeight = Math.max(10, Math.round((Number(row.created || 0) / maxCreated) * 240));
        return `
          <div class="bar-col">
            <div class="bar-stack">
              <div class="bar created" style="height:${{createdHeight}}px;">
                <div class="bar-value">${{nf.format(Number(row.created || 0))}}</div>
              </div>
            </div>
            <div class="bar-label">${{esc(row.manager)}}</div>
          </div>
        `;
      }}).join('');
    }}

    function renderPairBars(rows) {{
      const host = document.getElementById('pairBars');
      if (!rows.length) {{
        host.innerHTML = '<div class="empty">No matching scheduling-manager opps in this window.</div>';
        return;
      }}
      const maxCreated = Math.max(...rows.map((row) => Number(row.created || 0)), 1);
      host.innerHTML = rows.map((row) => {{
        const created = Number(row.created || 0);
        const demoed = Number(row.demoed || 0);
        const createdHeight = Math.max(10, Math.round((created / maxCreated) * 240));
        const demoedHeight = Math.max(demoed ? 10 : 0, Math.round((demoed / maxCreated) * 240));
        return `
          <div class="bar-col">
            <div class="bar-stack">
              <div class="bar created" style="height:${{createdHeight}}px;">
                <div class="bar-value">${{nf.format(created)}}</div>
              </div>
              <div class="bar demoed" style="height:${{demoedHeight}}px;">
                <div class="bar-value">${{nf.format(demoed)}}</div>
              </div>
            </div>
            <div class="bar-label">${{esc(row.manager)}}</div>
            <div class="bar-sub">${{fmtPct(row.demo_percentage)}}</div>
          </div>
        `;
      }}).join('');
    }}

    function renderTable(rows) {{
      const body = document.getElementById('summaryBody');
      if (!rows.length) {{
        body.innerHTML = '<tr><td colspan="4" class="empty">No matching scheduling-manager opps in this window.</td></tr>';
        return;
      }}
      body.innerHTML = rows.map((row) => `
        <tr>
          <td>${{esc(row.manager)}}</td>
          <td class="num">${{nf.format(Number(row.created || 0))}}</td>
          <td class="num">${{nf.format(Number(row.demoed || 0))}}</td>
          <td class="num">${{fmtPct(row.demo_percentage)}}</td>
        </tr>
      `).join('');
    }}

    async function loadReport() {{
      setError('');
      document.getElementById('createdBars').innerHTML = '<div class="loading">Loading…</div>';
      document.getElementById('pairBars').innerHTML = '<div class="loading">Loading…</div>';
      document.getElementById('summaryBody').innerHTML = '<tr><td colspan="4" class="loading">Loading…</td></tr>';
      try {{
        const res = await fetch(`/api/metrics/scheduling_manager_performance?${{q()}}`);
        if (!res.ok) throw new Error(`metrics endpoint returned ${{res.status}}`);
        const data = await res.json();
        const totals = data.result || {{}};
        const rows = Array.isArray(data?.breakdowns?.by_scheduling_manager) ? data.breakdowns.by_scheduling_manager : [];

        document.getElementById('kpiCreated').textContent = nf.format(Number(totals.created_with_scheduling_manager || 0));
        document.getElementById('kpiDemoed').textContent = nf.format(Number(totals.demoed_from_created_cohort || 0));
        document.getElementById('kpiPct').textContent = fmtPct(totals.demo_percentage);

        renderSingleBars('createdBars', rows);
        renderPairBars(rows);
        renderTable(rows);

        const pipelineScope = document.getElementById('pipelineScope').value === 'all' ? 'all pipelines' : 'core pipelines';
        document.getElementById('footnote').textContent =
          `Window ${{data.window_start_local}} to ${{data.window_end_local}} • Demo'd = disposition "Sit" on the created-opportunity cohort • Scope: ${{pipelineScope}}`;

        const pageUrl = new URL(window.location.href);
        pageUrl.searchParams.set('start', document.getElementById('start').value);
        pageUrl.searchParams.set('end', document.getElementById('end').value);
        pageUrl.searchParams.set('pipeline_scope', document.getElementById('pipelineScope').value);
        window.history.replaceState(null, '', pageUrl.toString());
      }} catch (err) {{
        setError(String(err));
        document.getElementById('createdBars').innerHTML = '<div class="empty">Unable to load chart.</div>';
        document.getElementById('pairBars').innerHTML = '<div class="empty">Unable to load chart.</div>';
        document.getElementById('summaryBody').innerHTML = '<tr><td colspan="4" class="empty">Unable to load table.</td></tr>';
      }}
    }}

    document.getElementById('applyBtn').addEventListener('click', loadReport);
    loadReport();
  </script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        now = datetime.utcnow()
        default_start, default_end = month_defaults(now.year, now.month)
        start = (qs.get("start", [default_start])[0] or default_start).strip()
        end = (qs.get("end", [default_end])[0] or default_end).strip()
        body = render_html(start, end).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(body)
