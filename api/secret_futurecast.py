# -*- coding: utf-8 -*-

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import base64
import os


def _unauthorized(h: BaseHTTPRequestHandler):
    h.send_response(401)
    h.send_header('WWW-Authenticate', 'Basic realm="Happy Solar Settings"')
    h.send_header('Content-Type', 'text/plain; charset=utf-8')
    h.end_headers()
    h.wfile.write(b'Unauthorized')


def _check_auth(h: BaseHTTPRequestHandler) -> bool:
    pw = os.environ.get('SETTINGS_PASSWORD')
    if not pw:
        return False
    auth = h.headers.get('Authorization') or ''
    if not auth.startswith('Basic '):
        return False
    try:
        raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
        _user, pwd = raw.split(':', 1)
        return pwd == pw
    except Exception:
        return False


HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Futurecast Simulator</title>
  <style>
    :root{--bg:#060b17;--card:#0c1427;--border:#1f2a44;--txt:#e5ecff;--muted:#9cb2dc;--pink:#ec4899;--cyan:#22d3ee;--green:#00C853;--shadow:0 1px 3px rgba(0,0,0,.35)}
    body{margin:0;font-family:Inter,-apple-system,sans-serif;background:radial-gradient(1200px 700px at 90% -20%,#15325d 0%,#070c1a 46%,#04060e 100%);color:var(--txt)}
    .wrap{max-width:1280px;margin:0 auto;padding:18px}
    .top{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;background:rgba(8,13,24,.74);border:1px solid var(--border);border-radius:16px;padding:14px 16px;backdrop-filter: blur(8px)}
    .title{font-size:24px;font-weight:950;display:flex;gap:8px;align-items:center}
    .sub{margin-top:4px;color:var(--muted);font-size:13px}
    .nav{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
    .nav a{color:#d7e0ff;text-decoration:none;border:1px solid var(--border);border-radius:10px;padding:7px 10px;font-size:12px;font-weight:800;background:#0a1326}

    .ctrl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;min-width:min(560px,100%)}
    .ctrl .f{display:flex;flex-direction:column;gap:4px}
    .ctrl label{font-size:11px;font-weight:900;color:var(--muted)}
    .ctrl input,.ctrl select{border:1px solid var(--border);border-radius:10px;background:#0a1326;color:var(--txt);padding:8px 10px;font-weight:900}

    .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px}
    .card{background:rgba(10,17,33,.78);border:1px solid var(--border);border-radius:14px;padding:12px;box-shadow:var(--shadow)}
    .span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-6{grid-column:span 6}.span-8{grid-column:span 8}.span-12{grid-column:span 12}
    .label{font-size:12px;color:var(--muted);font-weight:900}
    .kpi{font-size:34px;font-weight:950;margin-top:6px}
    .meta{font-size:12px;color:var(--muted);margin-top:4px}

    .sl{display:grid;grid-template-columns:150px 1fr 72px;gap:8px;align-items:center;margin-top:8px}
    .sl .n{font-size:12px;font-weight:900;color:#c7d6ff}
    .sl input[type=range]{width:100%}
    .sl .v{text-align:right;font-variant-numeric:tabular-nums;font-weight:900}

    canvas{width:100%;height:260px;background:#0a1326;border:1px solid var(--border);border-radius:10px}

    table{width:100%;border-collapse:collapse;margin-top:8px}
    th,td{padding:8px;border-bottom:1px solid var(--border);font-size:12px}
    th{color:var(--muted);text-align:left} td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}

    @media (max-width:960px){
      .ctrl{grid-template-columns:1fr 1fr;min-width:0;width:100%}
      .span-3,.span-4,.span-6,.span-8{grid-column:span 12}
      .sl{grid-template-columns:120px 1fr 66px}
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"top\">
      <div>
        <div class=\"title\">🔮 Futurecast Simulator</div>
        <div class=\"sub\">Monte Carlo forecast + scenario bands for month-end outcome planning.</div>
        <div class=\"nav\">
          <a href=\"/api/settings\">Settings</a>
          <a href=\"/api/daily_update\">Daily Dashboard</a>
          <a href=\"/api/secret_holographic_pipeline\">Holographic Pipeline</a>
        </div>
      </div>

      <div class=\"ctrl\">
        <div class=\"f\"><label>Year</label><input id=\"year\" type=\"number\" min=\"2024\" max=\"2035\"></div>
        <div class=\"f\"><label>Month</label><input id=\"month\" type=\"number\" min=\"1\" max=\"12\"></div>
        <div class=\"f\"><label>Sim Runs</label><select id=\"runs\"><option>1000</option><option selected>2500</option><option>5000</option></select></div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-8\">
        <div class=\"label\">Scenario Controls</div>
        <div class=\"sl\"><div class=\"n\">Lead Volume</div><input id=\"sVol\" type=\"range\" min=\"70\" max=\"140\" value=\"100\"><div class=\"v\" id=\"sVolV\">100%</div></div>
        <div class=\"sl\"><div class=\"n\">Demo Rate Delta</div><input id=\"sDemo\" type=\"range\" min=\"-15\" max=\"15\" value=\"0\"><div class=\"v\" id=\"sDemoV\">0 pts</div></div>
        <div class=\"sl\"><div class=\"n\">Close Rate Delta</div><input id=\"sClose\" type=\"range\" min=\"-10\" max=\"10\" value=\"0\"><div class=\"v\" id=\"sCloseV\">0 pts</div></div>
        <div class=\"sl\"><div class=\"n\">Volatility</div><input id=\"sVolatility\" type=\"range\" min=\"5\" max=\"40\" value=\"18\"><div class=\"v\" id=\"sVolatilityV\">18%</div></div>
        <div class=\"meta\" id=\"status\">Loading baseline…</div>
      </div>
      <div class=\"card span-4\">
        <div class=\"label\">Forecast Summary</div>
        <div class=\"kpi\" id=\"kExpected\">—</div>
        <div class=\"meta\">Expected Month-End Sales</div>
        <div class=\"meta\" id=\"kRange\">P10–P90: —</div>
        <div class=\"meta\" id=\"kUpside\">Upside: —</div>
      </div>

      <div class=\"card span-12\">
        <div class=\"label\">Scenario Movie (Remaining Days)</div>
        <canvas id=\"pathChart\" width=\"1100\" height=\"280\"></canvas>
      </div>

      <div class=\"card span-6\">
        <div class=\"label\">Distribution</div>
        <canvas id=\"histChart\" width=\"540\" height=\"260\"></canvas>
      </div>
      <div class=\"card span-6\">
        <div class=\"label\">Baseline Inputs</div>
        <table>
          <tbody id=\"baselineRows\"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
  const $=id=>document.getElementById(id);
  const url=new URL(window.location.href);
  const now=new Date();
  $('year').value=url.searchParams.get('year')||now.getFullYear();
  $('month').value=url.searchParams.get('month')||(now.getMonth()+1);

  const sliders=[['sVol',v=>`${v}%`],['sDemo',v=>`${v>0?'+':''}${v} pts`],['sClose',v=>`${v>0?'+':''}${v} pts`],['sVolatility',v=>`${v}%`]];
  sliders.forEach(([id,fmt])=>{ const el=$(id), out=$(id+'V'); const sync=()=>out.textContent=fmt(Number(el.value)); el.addEventListener('input',sync); sync(); });

  function nf(v){ return Number(v||0).toLocaleString(undefined,{maximumFractionDigits:1}); }
  function randn(){ let u=0,v=0; while(!u)u=Math.random(); while(!v)v=Math.random(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }

  function percentile(arr,p){ if(!arr.length)return 0; const a=[...arr].sort((x,y)=>x-y); const i=(a.length-1)*p; const lo=Math.floor(i), hi=Math.ceil(i); if(lo===hi)return a[lo]; return a[lo]+(a[hi]-a[lo])*(i-lo); }

  function drawHist(canvas, values){
    const c=canvas.getContext('2d'); const W=canvas.width,H=canvas.height; c.clearRect(0,0,W,H);
    c.fillStyle='#0a1326'; c.fillRect(0,0,W,H);
    if(!values.length)return;
    const min=Math.min(...values), max=Math.max(...values); const bins=24; const span=Math.max(1,max-min); const step=span/bins;
    const counts=Array(bins).fill(0);
    values.forEach(v=>{ const i=Math.min(bins-1,Math.max(0,Math.floor((v-min)/step))); counts[i]++; });
    const m=Math.max(...counts,1);
    counts.forEach((n,i)=>{
      const x=20 + i*((W-40)/bins), bw=((W-40)/bins)-2; const h=(n/m)*(H-40);
      c.fillStyle='rgba(34,211,238,.78)'; c.fillRect(x,H-20-h,bw,h);
    });
    c.fillStyle='#9fb3df'; c.font='12px Inter'; c.fillText(`P10 ${nf(percentile(values,.1))}`,20,14); c.fillText(`P50 ${nf(percentile(values,.5))}`,W/2-25,14); c.fillText(`P90 ${nf(percentile(values,.9))}`,W-90,14);
  }

  function drawPaths(canvas, p10,p50,p90){
    const c=canvas.getContext('2d'); const W=canvas.width,H=canvas.height; c.clearRect(0,0,W,H); c.fillStyle='#0a1326'; c.fillRect(0,0,W,H);
    const max=Math.max(...p90,1); const m=26, pw=W-m*2, ph=H-m*2;
    const X=i=>m+(i/(p90.length-1))*pw; const Y=v=>H-m-(v/max)*ph;
    c.strokeStyle='rgba(139,92,246,.25)'; c.lineWidth=10; c.beginPath(); c.moveTo(X(0),Y(p10[0])); for(let i=1;i<p10.length;i++) c.lineTo(X(i),Y(p10[i])); for(let i=p90.length-1;i>=0;i--) c.lineTo(X(i),Y(p90[i])); c.closePath(); c.fillStyle='rgba(139,92,246,.22)'; c.fill();
    const line=(arr,color,w=2)=>{ c.beginPath(); c.strokeStyle=color; c.lineWidth=w; c.moveTo(X(0),Y(arr[0])); for(let i=1;i<arr.length;i++) c.lineTo(X(i),Y(arr[i])); c.stroke(); };
    line(p10,'#94a3b8',1.5); line(p90,'#94a3b8',1.5); line(p50,'#22d3ee',3);
    c.fillStyle='#9fb3df'; c.font='12px Inter'; c.fillText('P10/P50/P90 scenario path to month-end',16,16);
  }

  async function load(){
    const y=Number($('year').value), m=Number($('month').value), runs=Number($('runs').value);
    const q=`format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    $('status').textContent='Loading baseline…';

    const [sales, ran, created] = await Promise.all([
      fetch(`/api/metrics/sales?${q}`).then(r=>r.json()),
      fetch(`/api/metrics/opportunities_ran?${q}`).then(r=>r.json()),
      fetch(`/api/metrics/opportunities_created?${q}&pipeline_scope=all`).then(r=>r.json())
    ]);

    const salesBase=Number(sales.result||0), ranBase=Number(ran.result||0), createdBase=Number(created.result||0);
    const demoRate = createdBase>0 ? (ranBase/createdBase*100) : 0;
    const closeRate = ranBase>0 ? (salesBase/ranBase*100) : 0;

    const today=new Date();
    const start=new Date(y,m-1,1); const end=new Date(y,m,0);
    const elapsed=Math.max(1, Math.min(end.getDate(), (today.getMonth()+1===m && today.getFullYear()===y)?today.getDate():end.getDate()));
    const rem=Math.max(0,end.getDate()-elapsed);
    const dailyCreated = createdBase/elapsed;

    const volMult=Number($('sVol').value)/100;
    const demoAdj=Number($('sDemo').value)/100;
    const closeAdj=Number($('sClose').value)/100;
    const vol=Number($('sVolatility').value)/100;

    const sims=[];
    const p10Path=Array(rem+1).fill(0), p50Path=Array(rem+1).fill(0), p90Path=Array(rem+1).fill(0);
    const pathSamples=[];

    for(let i=0;i<runs;i++){
      let cumulative=salesBase;
      const arr=[cumulative];
      for(let d=0; d<rem; d++){
        const dc=Math.max(0, dailyCreated*volMult*(1+randn()*vol*0.35));
        const dr=Math.max(0, (demoRate+demoAdj*100)/100 * dc * (1+randn()*vol*0.25));
        const ds=Math.max(0, (closeRate+closeAdj*100)/100 * dr * (1+randn()*vol*0.25));
        cumulative += ds;
        arr.push(cumulative);
      }
      sims.push(cumulative);
      if(i<800) pathSamples.push(arr);
    }

    for(let d=0; d<=rem; d++){
      const col=pathSamples.map(a=>a[d]);
      p10Path[d]=percentile(col,.1); p50Path[d]=percentile(col,.5); p90Path[d]=percentile(col,.9);
    }

    const p10=percentile(sims,.1), p50=percentile(sims,.5), p90=percentile(sims,.9);

    $('kExpected').textContent=nf(p50);
    $('kRange').textContent=`P10–P90: ${nf(p10)} → ${nf(p90)}`;
    $('kUpside').textContent=`Upside vs current: +${nf(Math.max(0,p50-salesBase))}`;

    $('baselineRows').innerHTML = `
      <tr><th>Current Sales</th><td class=\"num\">${nf(salesBase)}</td></tr>
      <tr><th>Current Opps Ran</th><td class=\"num\">${nf(ranBase)}</td></tr>
      <tr><th>Current Opps Created</th><td class=\"num\">${nf(createdBase)}</td></tr>
      <tr><th>Base Demo Rate (Ran/Created)</th><td class=\"num\">${demoRate.toFixed(1)}%</td></tr>
      <tr><th>Base Close Rate (Sales/Ran)</th><td class=\"num\">${closeRate.toFixed(1)}%</td></tr>
      <tr><th>Days Remaining in Month</th><td class=\"num\">${rem}</td></tr>
    `;

    drawHist($('histChart'), sims);
    drawPaths($('pathChart'), p10Path, p50Path, p90Path);
    $('status').textContent = `Window ${y}-${String(m).padStart(2,'0')} • ${runs.toLocaleString()} simulations`;
  }

  ['year','month','runs','sVol','sDemo','sClose','sVolatility'].forEach(id=>$(id).addEventListener('change',load));
  ['sVol','sDemo','sClose','sVolatility'].forEach(id=>$(id).addEventListener('input',load));

  load().catch(e=>{ $('status').textContent=`Error: ${String(e)}`; });
</script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _check_auth(self):
            return _unauthorized(self)
        body = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
