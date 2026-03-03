# -*- coding: utf-8 -*-

"""Vercel Python function: /api/dashboard

Mobile-friendly QA dashboard:
- Date filter (year/month)
- Total Sales KPI
- Sales by Pipeline (bar chart, hides zeros, shows human pipeline names)

All metric logic lives in /api/metrics/sales.
"""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def render_html(year: int, month: int) -> str:
    # Use placeholder substitution to avoid brace escaping issues.
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Metrics QA</title>
  <style>
    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:#0b0f14; color:#e8eef6; }
    .wrap { padding: 18px; max-width: 980px; margin: 0 auto; }
    .header { padding: 18px 20px; border-radius: 12px; background: linear-gradient(135deg,#00C853 0%,#1b5e20 100%); }
    .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(260px,1fr)); gap: 14px; margin-top: 14px; }
    .card { background:#121a24; border:1px solid #1f2a38; border-radius:12px; padding:16px; }
    .label { color:#9db0c7; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .kpi { font-size:52px; font-weight:900; margin-top: 6px; }
    .row { display:flex; gap:10px; align-items:end; flex-wrap:wrap; }
    select, button { background:#0e1520; color:#e8eef6; border:1px solid #1f2a38; border-radius:10px; padding:10px 12px; font-size:14px; }
    button { cursor:pointer; }
    a { color:#6ee7b7; }
    code { background:#0e1520; padding:2px 6px; border-radius:6px; }
    .muted { color:#9db0c7; font-size: 13px; }

    .barrow { display:flex; align-items:center; gap:10px; margin: 8px 0; }
    .barlabel { width: 140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#e8eef6; }
    .barwrap { flex:1; background:#0e1520; border:1px solid #1f2a38; border-radius:999px; height: 14px; overflow:hidden; }
    .barfill { height: 100%; background:#00C853; }
    .barval { width: 42px; text-align:right; font-variant-numeric: tabular-nums; color:#9db0c7; font-size:13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div style="font-weight:900;font-size:18px">Happy Solar — Metrics QA Dashboard</div>
      <div style="opacity:.9">Date filter → KPI cards</div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="label">Date Filter</div>
      <div class="row" style="margin-top:10px">
        <div>
          <div class="muted">Year</div>
          <select id="year"></select>
        </div>
        <div>
          <div class="muted">Month</div>
          <select id="month"></select>
        </div>
        <button id="apply">Apply</button>
        <div class="muted">Sales endpoint: <a id="salesLink" href="#">/api/metrics/sales</a></div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="label">Total Sales</div>
        <div class="kpi" id="salesKpi">—</div>
        <div class="muted" id="salesMeta"></div>
      </div>

      <div class="card">
        <div class="label">Sales by Pipeline</div>
        <div id="salesByPipeline" style="margin-top:10px"></div>
        <div class="muted" style="margin-top:8px">Pipelines with 0 sales are hidden.</div>
      </div>

      <div class="card">
        <div class="label">Sales by Owner</div>
        <div id="salesByOwner" style="margin-top:10px"></div>
        <div class="muted" style="margin-top:8px">Owners with 0 sales are hidden.</div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="label">Debug</div>
      <div class="muted">This dashboard reads live from <code>/api/metrics/sales</code>. If numbers look off, open the metric QA page and compare sample rows.</div>
    </div>
  </div>

<script>
  const defaultYear = __YEAR__;
  const defaultMonth = __MONTH__;

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
  const salesKpi = document.getElementById('salesKpi');
  const salesMeta = document.getElementById('salesMeta');
  const salesLink = document.getElementById('salesLink');
  const salesByPipeline = document.getElementById('salesByPipeline');

  const years = [];
  for (let y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
  const months = Array.from({length:12}, (_,i)=>({value:i+1, label: new Date(2000,i,1).toLocaleString('en-US',{month:'long'})}));

  setOptions(yearSel, years, defaultYear);
  setOptions(monthSel, months, defaultMonth);

  function renderBars(container, obj) {
    container.innerHTML = '';
    const entries = Object.entries(obj || {});
    if (!entries.length) {
      container.innerHTML = '<div class="muted">No sales in this window.</div>';
      return;
    }
    const maxVal = Math.max(...entries.map(([,v]) => Number(v)||0), 1);
    for (const [name, val] of entries) {
      const n = String(name);
      const v = Number(val) || 0;
      const pct = Math.round((v / maxVal) * 100);
      const row = document.createElement('div');
      row.className = 'barrow';
      row.innerHTML = `
        <div class="barlabel" title="${n}">${n}</div>
        <div class="barwrap"><div class="barfill" style="width:${pct}%"></div></div>
        <div class="barval">${v}</div>
      `;
      container.appendChild(row);
    }
  }

  async function load() {
    const y = yearSel.value;
    const m = monthSel.value;
    const url = `/api/metrics/sales?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    salesLink.href = `/api/metrics/sales?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    salesLink.textContent = url.replace('?format=json','');

    salesKpi.textContent = '…';
    salesMeta.textContent = '';
    salesByPipeline.innerHTML = '';
    salesByOwner.innerHTML = '';

    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) {
      salesKpi.textContent = 'ERR';
      salesMeta.textContent = `HTTP ${res.status}`;
      return;
    }
    const data = await res.json();
    salesKpi.textContent = data.result;
    salesMeta.textContent = `${data.window_start_local} → ${data.window_end_local} (${data.timezone})`;
    renderBars(salesByPipeline, (data.breakdowns && data.breakdowns.sales_by_pipeline) || {});
    renderBars(salesByOwner, (data.breakdowns && data.breakdowns.sales_by_owner) || {});
  }

  document.getElementById('apply').addEventListener('click', load);
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
