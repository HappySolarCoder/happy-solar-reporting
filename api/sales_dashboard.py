# -*- coding: utf-8 -*-

"""Vercel Python function: /api/sales_dashboard

Sales Dashboard (production)

Requested layout:
- Total Sales (KPI)
- Sales by Pipeline
- Owner table with columns:
  - Owner
  - Opps Ran
  - Sales
  - Opp2Prelim% (Sales / Opps Ran)

Data sources:
- /api/metrics/sales?format=json&year=YYYY&month=M
- /api/metrics/opportunities_ran?format=json&year=YYYY&month=M

Style:
- PatientPop green/blue (primary green #00C853, accent blue #2196F3)
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
  <title>Happy Solar — Sales Dashboard</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;

      /* PatientPop */
      --green: #00C853;
      --green2: #2EE07A;
      --blue: #2196F3;
      --blue2: #64B5F6;

      --purple: #8b5cf6;
      --cyan: #06b6d4;
      --amber: #f59e0b;
    }

    body {
      font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      margin:0;
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
      box-shadow: 0 1px 3px rgba(17,24,39,0.05);
    }

    .title {
      font-size: 22px;
      font-weight: 900;
      color: #1a2b4a;
      letter-spacing: -0.02em;
    }

    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .accentline {
      height: 3px;
      width: 180px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--green) 0%, var(--blue) 55%, rgba(100,181,246,0) 100%);
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
      border-color: rgba(0,200,83,0.45);
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }

    .navbtn.active {
      background: rgba(0,200,83,0.10);
      border-color: rgba(0,200,83,0.45);
      color: #0a7a34;
    }

    .filters { display:flex; align-items:center; gap: 10px; flex-wrap: wrap; }
    .filter { display:flex; align-items:center; gap: 8px; }
    .filter-label {
      font-size: 12px;
      color: var(--muted);
      background:#f0f2f5;
      padding: 9px 10px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }

    select, button, input[type=date] {
      background: var(--card);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 13px;
    }

    button {
      background: var(--green);
      border-color: var(--green);
      color: #fff;
      font-weight: 900;
      cursor:pointer;
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
      box-shadow: 0 1px 3px rgba(17,24,39,0.06);
      min-height: 120px;
    }

    .card-header { display:flex; align-items:flex-start; justify-content: space-between; gap: 10px; }
    .card-title { font-size: 13px; font-weight: 800; color: var(--muted); }

    .kpi { font-size: 46px; font-weight: 950; margin-top: 8px; letter-spacing: -0.02em; }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .span-4 { grid-column: span 4; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }

    @media (max-width: 980px) {
      .span-4, .span-8, .span-12 { grid-column: span 12; }
    }

    .skeleton { color: var(--muted2); font-size: 13px; }

    /* Vertical bars (same pattern as company overview) */
    .vchart { margin-top: 10px; }
    .vwrap {
      display:flex;
      align-items:stretch;
      justify-content:center;
      gap: 10px;
      height: 260px;
      padding: 12px 12px;
      background:#fafbfc;
      border:1px solid var(--border);
      border-radius:12px;
      overflow-x:auto;
    }
    .vcol {
      width: 86px;
      flex: 0 0 86px;
      height: 100%;
      display:flex;
      flex-direction:column;
      align-items:center;
      gap: 8px;
    }
    .vbarArea {
      width: 100%;
      flex: 1;
      display:flex;
      align-items:stretch;
      justify-content:center;
    }
    .vbarStack {
      width: 100%;
      height: 100%;
      display:flex;
      flex-direction:column;
      justify-content:flex-end;
      align-items:stretch;
      gap: 6px;
    }
    .vval {
      font-size: 12px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      text-align:center;
      width:100%;
    }
    .vbar {
      width: 100%;
      border-radius: 14px 14px 6px 6px;
    }
    .vlabel {
      font-size: 11px;
      color: var(--muted);
      text-align:center;
      width: 100%;
      overflow:hidden;
      text-overflow:ellipsis;
      white-space:nowrap;
    }

    /* Owner table */
    .tablewrap {
      margin-top: 10px;
      overflow:auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fafbfc;
    }
    table { width:100%; border-collapse: collapse; min-width: 760px; }
    th, td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid var(--border); text-align:left; }
    th { font-size: 12px; color: var(--muted); font-weight: 900; background: #f3f5f7; position: sticky; top: 0; }
    td.num { text-align:right; font-variant-numeric: tabular-nums; }
    tr.total td { font-weight: 900; background: #ffffff; }

    a { color: var(--green); text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Sales Dashboard</div>
        <div class="subtitle">Happy Solar — sales + owner performance</div>
        <div class="accentline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn active" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn" href="/api/fma_dashboard">FMA dashboard</a>
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
        </div>
      </div>

      <div class="filters">
        <div class="filter">
          <div class="filter-label">Year</div>
          <select id="year"></select>
        </div>
        <div class="filter">
          <div class="filter-label">Month</div>
          <select id="month"></select>
        </div>
        <button id="apply">Apply</button>
        <div class="filter">
          <div class="filter-label">Start</div>
          <input id="startDate" type="date" />
        </div>
        <div class="filter">
          <div class="filter-label">End</div>
          <input id="endDate" type="date" />
        </div>
        <button id="clearRange" style="background:#fff;color:#1f2937;border-color:var(--border);font-weight:900">Clear</button>
      </div>
    </div>

    <div class="grid">
      <div class="card span-4">
        <div class="card-header">
          <div class="card-title">Total Sales</div>
          <div class="meta"><a href="/api/metrics/sales">QA</a></div>
        </div>
        <div class="kpi" id="totalSales">—</div>
        <div class="meta" id="salesMeta"></div>
      </div>

      <div class="card span-8">
        <div class="card-header">
          <div class="card-title">Sales by Pipeline</div>
          <div class="meta">Vertical bars</div>
        </div>
        <div class="vchart" id="salesByPipelineV"><div class="skeleton">Loading…</div></div>
      </div>

      <div class="card span-12">
        <div class="card-header">
          <div class="card-title">Owner Performance</div>
          <div class="meta">Opp2Prelim = Sales / Opps Ran (Opps Ran uses appointmentOccurredAt month window)</div>
        </div>
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Owner</th>
                <th style="text-align:right">Opps Ran</th>
                <th style="text-align:right">Sales</th>
                <th style="text-align:right">Opp2Prelim%</th>
              </tr>
            </thead>
            <tbody id="ownerRows">
              <tr><td colspan="4" class="skeleton">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

<script>
  const defaultYear = __YEAR__;
  const defaultMonth = __MONTH__;

  const palette = [
    'var(--green)',
    'var(--blue)',
    'var(--purple)',
    'var(--cyan)',
    'var(--amber)'
  ];

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

  function renderVertical(container, data) {
    const entries = Object.entries(data || {}).sort((a,b)=>b[1]-a[1]);
    if (!entries.length) {
      container.innerHTML = '<div class="skeleton">No data</div>';
      return;
    }
    const maxV = Math.max(...entries.map(([,v])=>Number(v)||0), 1);
    let html = '<div class="vwrap">';
    let i = 0;
    for (const [n, val] of entries) {
      const v = Number(val) || 0;
      const scale = maxV > 0 ? (v / maxV) : 0;
      const color = palette[i % palette.length];
      i++;
      html += `
        <div class="vcol" title="${n}">
          <div class="vbarArea">
            <div class="vbarStack">
              <div class="vval">${v}</div>
              <div class="vbar" style="background:${color}; height:${(scale*100).toFixed(2)}%"></div>
            </div>
          </div>
          <div class="vlabel">${n}</div>
        </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
  }

  function pct(sales, ran) {
    const s = Number(sales||0);
    const r = Number(ran||0);
    if (r <= 0) return null;
    return (s / r) * 100;
  }

  function rangeParams() {
    const s = (document.getElementById('startDate').value || '').trim();
    const e = (document.getElementById('endDate').value || '').trim();
    if (s && e) return `&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
    return '';
  }

  async function load() {
    const y = yearSel.value;
    const m = monthSel.value;

    const rp = rangeParams();
    const salesUrl = `/api/metrics/sales?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`;
    const ranUrl = `/api/metrics/opportunities_ran?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}${rp}`; // now filtered by appointmentOccurredAt

    document.getElementById('totalSales').textContent = '…';
    document.getElementById('salesByPipelineV').innerHTML = '<div class="skeleton">Loading…</div>';
    document.getElementById('ownerRows').innerHTML = '<tr><td colspan="4" class="skeleton">Loading…</td></tr>';

    const [salesRes, ranRes] = await Promise.all([
      fetch(salesUrl, { cache: 'no-store' }),
      fetch(ranUrl, { cache: 'no-store' })
    ]);

    if (!salesRes.ok) {
      document.getElementById('totalSales').textContent = 'ERR';
      return;
    }

    const salesData = await salesRes.json();
    const ranData = ranRes.ok ? await ranRes.json() : null;

    document.getElementById('totalSales').textContent = salesData.result;
    document.getElementById('salesMeta').textContent = '';

    const sbp = (salesData.breakdowns || {}).sales_by_pipeline || {};
    renderVertical(document.getElementById('salesByPipelineV'), sbp);

    const salesByOwner = (salesData.breakdowns || {}).sales_by_owner || {};
    const ranByOwner = (ranData && ranData.breakdowns ? (ranData.breakdowns.ran_by_owner || {}) : {}) || {};

    // union of owners
    const owners = new Set([...Object.keys(salesByOwner||{}), ...Object.keys(ranByOwner||{})]);
    const rows = [];
    for (const owner of owners) {
      const s = Number(salesByOwner[owner] || 0);
      const r = Number(ranByOwner[owner] || 0);
      rows.push({ owner, ran: r, sales: s, opp2: pct(s, r) });
    }

    rows.sort((a,b)=> (b.sales - a.sales) || (b.ran - a.ran) || a.owner.localeCompare(b.owner));

    const totSales = rows.reduce((acc,x)=>acc+x.sales,0);
    const totRan = rows.reduce((acc,x)=>acc+x.ran,0);
    const totOpp2 = pct(totSales, totRan);

    function fmtPct(v) {
      if (v === null || typeof v === 'undefined') return '—';
      return `${v.toFixed(1)}%`;
    }

    let html = '';
    for (const r of rows) {
      html += `
        <tr>
          <td>${r.owner || '—'}</td>
          <td class="num">${r.ran}</td>
          <td class="num">${r.sales}</td>
          <td class="num">${fmtPct(r.opp2)}</td>
        </tr>`;
    }
    html += `
      <tr class="total">
        <td>Total</td>
        <td class="num">${totRan}</td>
        <td class="num">${totSales}</td>
        <td class="num">${fmtPct(totOpp2)}</td>
      </tr>`;

    document.getElementById('ownerRows').innerHTML = html;
  }

  const yearSel = document.getElementById('year');
  const monthSel = document.getElementById('month');

  const years = [];
  for (let y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
  const months = Array.from({length:12}, (_,i)=>({value:i+1, label: new Date(2000,i,1).toLocaleString('en-US',{month:'long'})}));

  setOptions(yearSel, years, defaultYear);
  setOptions(monthSel, months, defaultMonth);

  document.getElementById('apply').addEventListener('click', load);
  document.getElementById('clearRange').addEventListener('click', () => {
    document.getElementById('startDate').value = '';
    document.getElementById('endDate').value = '';
    load();
  });
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
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
