# -*- coding: utf-8 -*-

"""Vercel Python function: /api/dashboard

Mobile-friendly QA dashboard:
- Date filter (year/month)
- Total Sales KPI
- Sales breakdown bars
- Owner table: Opps Ran, Sales, Opp2Prelim (Sales / Opps Ran) with totals row

Metric sources:
- /api/metrics/sales
- /api/metrics/opportunities_ran
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
    .wrap { padding: 18px; max-width: 1100px; margin: 0 auto; }
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
    .barlabel { width: 160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#e8eef6; }
    .barwrap { flex:1; background:#0e1520; border:1px solid #1f2a38; border-radius:999px; height: 14px; overflow:hidden; }
    .barfill { height: 100%; background:#00C853; }
    .barval { width: 42px; text-align:right; font-variant-numeric: tabular-nums; color:#9db0c7; font-size:13px; }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { padding: 10px 8px; border-bottom: 1px solid #1f2a38; font-size: 13px; }
    th { text-align: left; color: #9db0c7; font-weight: 700; }
    td.num { text-align: right; font-variant-numeric: tabular-nums; }
    tr.total td { font-weight: 900; }
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
        <div class="muted">
          Sales endpoint: <a id="salesLink" href="#">/api/metrics/sales</a>
          &nbsp;|&nbsp;
          Opps Ran endpoint: <a id="ranLink" href="#">/api/metrics/opportunities_ran</a>
        </div>
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

      <div class="card">
        <div class="label">Sales by Setter Last Name</div>
        <div id="salesBySetter" style="margin-top:10px"></div>
        <div class="muted" style="margin-top:8px">(Requires setter custom field mapping)</div>
      </div>

      <div class="card">
        <div class="label">Sales by Lead Gen Source</div>
        <div id="salesByLeadSource" style="margin-top:10px"></div>
        <div class="muted" style="margin-top:8px">(Requires lead source custom field mapping)</div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="label">Owner Table</div>
      <div class="muted">Opp2Prelim = Sales / Opps Ran</div>
      <div id="ownerTable"></div>
      <div class="muted" style="margin-top:8px">Totals row sums Opps Ran and Sales, then computes Opp2Prelim from totals.</div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="label">Debug</div>
      <div class="muted">This dashboard reads live from <code>/api/metrics/sales</code> and <code>/api/metrics/opportunities_ran</code>. If numbers look off, open the metric QA pages and compare sample rows.</div>
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
  const ranLink = document.getElementById('ranLink');

  const salesByPipeline = document.getElementById('salesByPipeline');
  const salesByOwner = document.getElementById('salesByOwner');
  const salesBySetter = document.getElementById('salesBySetter');
  const salesByLeadSource = document.getElementById('salesByLeadSource');
  const ownerTable = document.getElementById('ownerTable');

  const years = [];
  for (let y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
  const months = Array.from({length:12}, (_,i)=>({value:i+1, label: new Date(2000,i,1).toLocaleString('en-US',{month:'long'})}));

  setOptions(yearSel, years, defaultYear);
  setOptions(monthSel, months, defaultMonth);

  function renderBars(container, obj) {
    container.innerHTML = '';
    const entries = Object.entries(obj || {});
    if (!entries.length) {
      container.innerHTML = '<div class="muted">No values in this window.</div>';
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

  function fmtPct(x) {
    if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
    return (Number(x) * 100).toFixed(1) + '%';
  }

  function renderOwnerTable(ranByOwner, salesByOwnerObj) {
    const ran = ranByOwner || {};
    const sales = salesByOwnerObj || {};

    const owners = new Set([...Object.keys(ran), ...Object.keys(sales)]);
    const rows = [];

    let totalRan = 0;
    let totalSales = 0;

    for (const owner of owners) {
      const oppsRan = Number(ran[owner] || 0);
      const ownerSales = Number(sales[owner] || 0);

      // hide fully-zero owners to reduce noise
      if (oppsRan === 0 && ownerSales === 0) continue;

      const opp2prelim = oppsRan > 0 ? (ownerSales / oppsRan) : null;
      rows.push({ owner, oppsRan, ownerSales, opp2prelim });

      totalRan += oppsRan;
      totalSales += ownerSales;
    }

    // sort by sales desc then opps ran desc
    rows.sort((a,b) => (b.ownerSales - a.ownerSales) || (b.oppsRan - a.oppsRan) || a.owner.localeCompare(b.owner));

    const totalOpp2 = totalRan > 0 ? (totalSales / totalRan) : null;

    let html = '<table>';
    html += '<thead><tr>';
    html += '<th>Owner</th>';
    html += '<th style="text-align:right">Opps Ran</th>';
    html += '<th style="text-align:right">Sales</th>';
    html += '<th style="text-align:right">Opp2Prelim</th>';
    html += '</tr></thead><tbody>';

    for (const r of rows) {
      html += '<tr>';
      html += `<td>${r.owner}</td>`;
      html += `<td class="num">${r.oppsRan}</td>`;
      html += `<td class="num">${r.ownerSales}</td>`;
      html += `<td class="num">${fmtPct(r.opp2prelim)}</td>`;
      html += '</tr>';
    }

    html += '<tr class="total">';
    html += '<td>Total</td>';
    html += `<td class="num">${totalRan}</td>`;
    html += `<td class="num">${totalSales}</td>`;
    html += `<td class="num">${fmtPct(totalOpp2)}</td>`;
    html += '</tr>';

    html += '</tbody></table>';
    ownerTable.innerHTML = html;
  }

  async function load() {
    const y = yearSel.value;
    const m = monthSel.value;

    const salesUrl = `/api/metrics/sales?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    const ranUrl = `/api/metrics/opportunities_ran?format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;

    salesLink.href = `/api/metrics/sales?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    salesLink.textContent = '/api/metrics/sales';

    ranLink.href = `/api/metrics/opportunities_ran?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    ranLink.textContent = '/api/metrics/opportunities_ran';

    salesKpi.textContent = '…';
    salesMeta.textContent = '';

    salesByPipeline.innerHTML = '';
    salesByOwner.innerHTML = '';
    salesBySetter.innerHTML = '';
    salesByLeadSource.innerHTML = '';
    ownerTable.innerHTML = '<div class="muted">Loading…</div>';

    const [salesRes, ranRes] = await Promise.all([
      fetch(salesUrl, { cache: 'no-store' }),
      fetch(ranUrl, { cache: 'no-store' })
    ]);

    if (!salesRes.ok) {
      salesKpi.textContent = 'ERR';
      salesMeta.textContent = `Sales HTTP ${salesRes.status}`;
      ownerTable.innerHTML = '<div class="muted">Unable to load sales.</div>';
      return;
    }
    if (!ranRes.ok) {
      ownerTable.innerHTML = `<div class="muted">Opps Ran HTTP ${ranRes.status}</div>`;
      // still render sales bars
    }

    const salesData = await salesRes.json();
    const ranData = ranRes.ok ? await ranRes.json() : null;

    salesKpi.textContent = salesData.result;
    salesMeta.textContent = `${salesData.window_start_local} → ${salesData.window_end_local} (${salesData.timezone})`;

    renderBars(salesByPipeline, (salesData.breakdowns && salesData.breakdowns.sales_by_pipeline) || {});
    renderBars(salesByOwner, (salesData.breakdowns && salesData.breakdowns.sales_by_owner) || {});
    renderBars(salesBySetter, (salesData.breakdowns && salesData.breakdowns.sales_by_setter_last_name) || {});
    renderBars(salesByLeadSource, (salesData.breakdowns && salesData.breakdowns.sales_by_lead_gen_source) || {});

    const ranByOwner = ranData && ranData.breakdowns ? (ranData.breakdowns.ran_by_owner || {}) : {};
    const salesByOwnerObj = salesData && salesData.breakdowns ? (salesData.breakdowns.sales_by_owner || {}) : {};

    renderOwnerTable(ranByOwner, salesByOwnerObj);
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
