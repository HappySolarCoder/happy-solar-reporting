# -*- coding: utf-8 -*-

"""Vercel Python function: /api/morning_brief

Morning Brief (auto narrative) for leadership standups.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler


HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Morning Brief</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --pink:#ec4899; --pink2:#f472b6; --shadow:0 1px 3px rgba(17,24,39,0.06);
      --good:#16a34a; --warn:#f59e0b; --bad:#dc2626;
    }
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;background:var(--bg);color:var(--text)}
    .wrap{padding:18px;max-width:1240px;margin:0 auto}
    .topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:16px 18px;border-radius:14px;background:var(--card);border:1px solid var(--border);box-shadow:var(--shadow)}
    .topbar>div{min-width:0}
    .title{font-size:24px;font-weight:950;color:#1a2b4a;display:flex;align-items:center;gap:8px}
    .subtitle{margin-top:4px;color:var(--muted);font-size:13px}
    .pinkline{height:3px;width:210px;border-radius:999px;background:linear-gradient(90deg,var(--pink) 0%,var(--pink2) 45%,rgba(244,114,182,0) 100%);margin-top:10px}
    .nav{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap}
    .navbtn{display:inline-flex;align-items:center;padding:9px 12px;border-radius:12px;border:1px solid var(--border);background:#fff;color:#1f2937;font-size:13px;font-weight:800;text-decoration:none}
    .navbtn.active{background:rgba(236,72,153,0.10);border-color:rgba(236,72,153,0.45);color:#b80b66}

    .filters{display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap}
    .filters label{display:block;font-size:12px;color:var(--muted);font-weight:900;margin-bottom:4px}
    .filters input[type=date]{border:1px solid var(--border);border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;background:#fff}
    .btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:#fff;color:#334155;font-size:12px;font-weight:900;cursor:pointer;text-decoration:none}
    .btn.primary{background:#00C853;border-color:#00C853;color:#fff}

    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px}
    .card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}
    .span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-6{grid-column:span 6}.span-8{grid-column:span 8}.span-12{grid-column:span 12}

    .kpi-label{color:var(--muted);font-size:12px;font-weight:900}
    .kpi{margin-top:4px;font-size:34px;font-weight:950;letter-spacing:-0.02em}
    .kpi-sub{margin-top:4px;color:var(--muted2);font-size:12px}

    .brief{font-size:18px;font-weight:800;line-height:1.4}
    .chip{display:inline-flex;align-items:center;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:900;margin-right:6px}
    .chip.good{background:rgba(22,163,74,.12);color:#166534}
    .chip.warn{background:rgba(245,158,11,.14);color:#92400e}
    .chip.bad{background:rgba(220,38,38,.14);color:#991b1b}

    .section-title{font-size:13px;font-weight:900;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin-bottom:8px}
    ul{margin:0;padding-left:18px}
    li{margin:6px 0}
    table{width:100%;border-collapse:collapse}
    th,td{padding:8px;border-bottom:1px solid var(--border);font-size:13px;text-align:left}
    th{color:var(--muted);font-weight:950}
    td{font-weight:800}
    td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}

    @media (max-width:820px){
      .wrap{padding:12px}
      .title{font-size:20px}
      .nav{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:8px;padding-bottom:4px;-webkit-overflow-scrolling:touch}
      .navbtn{white-space:nowrap;flex:0 0 auto;padding:8px 10px;font-size:12px}
      .filters{width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
      .filters input[type=date],.filters .btn{width:100%}
      .span-3,.span-4,.span-6,.span-8{grid-column:span 12}
      .brief{font-size:16px}
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">☀️ Morning Brief</div>
        <div class=\"subtitle\">Auto-narrative standup summary from yesterday/today metrics</div>
        <div class=\"pinkline\"></div>
        <div class=\"nav\">
          <a class=\"navbtn\" href=\"/api/daily_update\">Daily Dashboard</a>
          <a class=\"navbtn\" href=\"/api/company_overview\">Company Overview</a>
          <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales Dashboard</a>
          <a class=\"navbtn\" href=\"/api/fma_dashboard\">FMA Dashboard</a>
          <a class=\"navbtn\" href=\"/api/settings\">Settings</a>
          <a class=\"navbtn active\" href=\"/api/morning_brief\">Morning Brief</a>
        </div>
      </div>
      <div>
        <div class=\"filters\">
          <div><label>Start</label><input id=\"startDate\" type=\"date\" /></div>
          <div><label>End</label><input id=\"endDate\" type=\"date\" /></div>
          <button class=\"btn primary\" id=\"applyBtn\">Apply</button>
          <button class=\"btn\" id=\"yesterdayBtn\">Yesterday</button>
          <button class=\"btn\" id=\"todayBtn\">Today</button>
        </div>
        <div class=\"kpi-sub\" id=\"status\" style=\"margin-top:8px\">Loading…</div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-8\">
        <div class=\"section-title\">Narrative</div>
        <div id=\"narrative\" class=\"brief\">Loading…</div>
      </div>
      <div class=\"card span-4\">
        <div class=\"section-title\">Health Signals</div>
        <div id=\"signals\"></div>
      </div>

      <div class=\"card span-3\"><div class=\"kpi-label\">Sales</div><div class=\"kpi\" id=\"kSales\">—</div></div>
      <div class=\"card span-3\"><div class=\"kpi-label\">Opps Ran</div><div class=\"kpi\" id=\"kRan\">—</div></div>
      <div class=\"card span-3\"><div class=\"kpi-label\">Opps Created</div><div class=\"kpi\" id=\"kCreated\">—</div></div>
      <div class=\"card span-3\"><div class=\"kpi-label\">Demo Rate</div><div class=\"kpi\" id=\"kDemo\">—</div></div>

      <div class=\"card span-6\">
        <div class=\"section-title\">Highlights</div>
        <ul id=\"highlights\"></ul>
      </div>
      <div class=\"card span-6\">
        <div class=\"section-title\">Watchouts</div>
        <ul id=\"watchouts\"></ul>
      </div>

      <div class=\"card span-6\">
        <div class=\"section-title\">Top Owners / Setters</div>
        <table><thead><tr><th>Name</th><th class=\"num\">Sales</th></tr></thead><tbody id=\"tblTopSales\"></tbody></table>
      </div>
      <div class=\"card span-6\">
        <div class=\"section-title\">Lead Source Snapshot</div>
        <table><thead><tr><th>Lead Source</th><th class=\"num\">Sales</th><th class=\"num\">Created</th></tr></thead><tbody id=\"tblLead\"></tbody></table>
      </div>
    </div>
  </div>

<script>
  const url = new URL(window.location.href);
  function nyYmd(d = new Date()) {
    const p = new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);
    const g=t=>p.find(x=>x.type===t)?.value; return `${g('year')}-${g('month')}-${g('day')}`;
  }
  function ymdAddDays(ymd, delta){ const [y,m,d]=ymd.split('-').map(Number); const dt=new Date(Date.UTC(y,m-1,d)); dt.setUTCDate(dt.getUTCDate()+delta); return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth()+1).padStart(2,'0')}-${String(dt.getUTCDate()).padStart(2,'0')}`; }
  function setRange(s,e){ url.searchParams.set('start',s); url.searchParams.set('end',e); window.location.href=url.toString(); }
  const nf=v=>Number(v||0).toLocaleString();

  function topEntry(obj){
    const rows=Object.entries(obj||{}).sort((a,b)=>Number(b[1]||0)-Number(a[1]||0));
    return rows[0] || [null,0];
  }

  function renderList(id, items){
    const el=document.getElementById(id);
    if(!items.length){el.innerHTML='<li>None.</li>'; return;}
    el.innerHTML=items.map(x=>`<li>${x}</li>`).join('');
  }

  async function j(u){ const r=await fetch(u); if(!r.ok) throw new Error(`${u} -> ${r.status}`); return await r.json(); }

  async function load(){
    let s=url.searchParams.get('start');
    let e=url.searchParams.get('end');
    if(!s||!e){ const y=ymdAddDays(nyYmd(),-1); setRange(y,y); return; }
    document.getElementById('startDate').value=s; document.getElementById('endDate').value=e;
    document.getElementById('status').textContent=`Window: ${s} → ${e} (ET)`;

    const q=`format=json&start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
    const prevS=ymdAddDays(s,-1), prevE=ymdAddDays(e,-1);
    const qp=`format=json&start=${encodeURIComponent(prevS)}&end=${encodeURIComponent(prevE)}`;

    const [sales,ran,created,demo,knocks,calls,salesPrev,createdPrev] = await Promise.all([
      j(`/api/metrics/sales?${q}`),
      j(`/api/metrics/opportunities_ran?${q}`),
      j(`/api/metrics/opportunities_created?${q}`),
      j(`/api/metrics/demo_rate?${q}`),
      j(`/api/metrics/raydar_doors_knocked?${q}`),
      j(`/api/metrics/kixie_calls_summary?${q}`),
      j(`/api/metrics/sales?${qp}`),
      j(`/api/metrics/opportunities_created?${qp}`),
    ]);

    const salesDelta=Number(sales.result||0)-Number(salesPrev.result||0);
    const createdDelta=Number(created.result||0)-Number(createdPrev.result||0);

    document.getElementById('kSales').textContent=nf(sales.result);
    document.getElementById('kRan').textContent=nf(ran.result);
    document.getElementById('kCreated').textContent=nf(created.result);
    document.getElementById('kDemo').textContent = demo && demo.result!=null ? `${Number(demo.result).toFixed(1)}%` : '—';

    const [topOwner, topOwnerVal] = topEntry(sales?.breakdowns?.sales_by_owner);
    const [topSetter, topSetterVal] = topEntry(sales?.breakdowns?.sales_by_setter_last_name);
    const [topLead, topLeadVal] = topEntry(sales?.breakdowns?.sales_by_lead_gen_source);

    document.getElementById('narrative').textContent =
      `In this window, we closed ${nf(sales.result)} sales on ${nf(ran.result)} opps ran (${demo && demo.result!=null ? Number(demo.result).toFixed(1) : '—'}% demo rate), created ${nf(created.result)} new opps, logged ${nf(knocks.result)} door knocks, and handled ${nf(calls.calls)} Kixie calls.`;

    const signal = [];
    signal.push(`<span class=\"chip ${salesDelta>=0?'good':'bad'}\">Sales ${salesDelta>=0?'+':''}${salesDelta} vs prior window</span>`);
    signal.push(`<span class=\"chip ${createdDelta>=0?'good':'warn'}\">Created ${createdDelta>=0?'+':''}${createdDelta} vs prior window</span>`);
    signal.push(`<span class=\"chip ${Number(demo.result||0)>=30?'good':'warn'}\">Demo Rate ${demo && demo.result!=null ? Number(demo.result).toFixed(1)+'%' : '—'}</span>`);
    document.getElementById('signals').innerHTML = signal.join('');

    const highlights=[];
    if(topOwner) highlights.push(`Top sales owner: <b>${topOwner}</b> (${nf(topOwnerVal)})`);
    if(topSetter) highlights.push(`Top setter on sales: <b>${topSetter}</b> (${nf(topSetterVal)})`);
    if(topLead) highlights.push(`Top sales lead source: <b>${topLead}</b> (${nf(topLeadVal)})`);
    highlights.push(`Door knocks: <b>${nf(knocks.result)}</b> • Calls: <b>${nf(calls.calls)}</b> • Connections: <b>${nf(calls.connections)}</b>`);
    renderList('highlights', highlights);

    const watch=[];
    if(Number(created.result||0) < Number(sales.result||0)) watch.push('Opp creation is trailing sales volume; monitor upcoming pipeline replenishment.');
    if(Number(demo.result||0) < 25) watch.push('Demo rate is under 25%; focus setter follow-through and appointment quality.');
    if(Number(knocks.result||0) < 20) watch.push('Door activity is light for this window; consider canvassing push.');
    if(!watch.length) watch.push('No major red flags detected in this window.');
    renderList('watchouts', watch);

    const topSalesRows = Object.entries(sales?.breakdowns?.sales_by_owner || {}).sort((a,b)=>Number(b[1])-Number(a[1])).slice(0,8);
    document.getElementById('tblTopSales').innerHTML = topSalesRows.length
      ? topSalesRows.map(([k,v])=>`<tr><td>${k||'—'}</td><td class=\"num\">${nf(v)}</td></tr>`).join('')
      : '<tr><td colspan="2">No rows</td></tr>';

    const leadSales = sales?.breakdowns?.sales_by_lead_gen_source || {};
    const leadCreated = created?.breakdowns?.created_by_lead_gen_source || {};
    const leadKeys = Array.from(new Set([...Object.keys(leadSales), ...Object.keys(leadCreated)])).sort();
    document.getElementById('tblLead').innerHTML = leadKeys.length
      ? leadKeys.map(k=>`<tr><td>${k||'—'}</td><td class=\"num\">${nf(leadSales[k]||0)}</td><td class=\"num\">${nf(leadCreated[k]||0)}</td></tr>`).join('')
      : '<tr><td colspan="3">No rows</td></tr>';

    document.getElementById('status').textContent = `Loaded morning brief for ${s} → ${e}`;
  }

  document.getElementById('applyBtn').addEventListener('click',()=>{
    const s=document.getElementById('startDate').value, e=document.getElementById('endDate').value;
    if(s&&e) setRange(s,e);
  });
  document.getElementById('yesterdayBtn').addEventListener('click',()=>{ const y=ymdAddDays(nyYmd(),-1); setRange(y,y); });
  document.getElementById('todayBtn').addEventListener('click',()=>{ const t=nyYmd(); setRange(t,t); });

  load().catch(err=>{ document.getElementById('status').textContent = `Error: ${String(err)}`; });
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
