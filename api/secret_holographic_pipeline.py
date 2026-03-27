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
  <title>Happy Solar — Holographic Pipeline</title>
  <style>
    :root { --bg:#050914; --card:#0c1427; --border:#1f2a44; --txt:#e5ecff; --muted:#8ca0cc; --pink:#ec4899; --cyan:#22d3ee; --vio:#8b5cf6; }
    body { margin:0; font-family: Inter, -apple-system, sans-serif; background: radial-gradient(1200px 700px at 20% -10%, #13203f 0%, #060b17 45%, #03060e 100%); color:var(--txt); }
    .wrap { max-width:1280px; margin:0 auto; padding:18px; }
    .top { display:flex; flex-wrap:wrap; gap:12px; justify-content:space-between; align-items:flex-start; background:rgba(8,13,24,.72); border:1px solid var(--border); border-radius:16px; padding:14px 16px; backdrop-filter: blur(8px); }
    .title { font-size:24px; font-weight:900; letter-spacing:.02em; display:flex; align-items:center; gap:8px; }
    .sub { color:var(--muted); font-size:13px; margin-top:4px; }
    .nav { margin-top:10px; display:flex; gap:8px; flex-wrap:wrap; }
    .nav a { color:#d7e0ff; text-decoration:none; border:1px solid var(--border); border-radius:10px; padding:7px 10px; font-size:12px; font-weight:800; background:#0a1326; }
    .ctrl { display:flex; gap:8px; align-items:end; flex-wrap:wrap; }
    .ctrl label { font-size:11px; color:var(--muted); font-weight:900; display:block; margin-bottom:4px; }
    .ctrl input,.ctrl select,.ctrl button { border:1px solid var(--border); border-radius:10px; background:#0a1326; color:var(--txt); padding:8px 10px; font-weight:900; }
    .ctrl button { background:linear-gradient(90deg,#0ea5e9,#8b5cf6); border:none; cursor:pointer; }

    .grid { display:grid; grid-template-columns: 2fr 1fr; gap:12px; margin-top:12px; }
    .card { background:rgba(10,17,33,.78); border:1px solid var(--border); border-radius:14px; padding:12px; }

    .sceneWrap { height:520px; perspective: 1200px; overflow:hidden; position:relative; }
    .scene { position:absolute; inset:0; transform-style:preserve-3d; }
    .ring { position:absolute; left:50%; top:50%; border:1px solid rgba(139,92,246,.28); border-radius:50%; transform: translate(-50%,-50%) rotateX(70deg); }
    .planet { position:absolute; border-radius:50%; box-shadow:0 0 20px rgba(34,211,238,.35), inset 0 0 20px rgba(255,255,255,.12); transform: translate(-50%,-50%); display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px; font-weight:900; text-align:center; padding:4px; }

    .legend h3 { margin:2px 0 8px; font-size:14px; color:#dbe7ff; }
    .legend p { margin:0 0 8px; font-size:12px; color:var(--muted); }
    .pill { display:inline-flex; margin:0 6px 6px 0; border:1px solid var(--border); border-radius:999px; padding:4px 9px; font-size:11px; color:#c7d6ff; }

    table { width:100%; border-collapse:collapse; margin-top:8px; }
    th,td { border-bottom:1px solid var(--border); padding:7px 6px; font-size:12px; }
    th { text-align:left; color:var(--muted); }
    td.num { text-align:right; font-variant-numeric:tabular-nums; }

    @media (max-width: 920px) {
      .grid { grid-template-columns: 1fr; }
      .sceneWrap { height:420px; }
      .ctrl { width:100%; display:grid; grid-template-columns:1fr 1fr 1fr; }
      .ctrl > div { min-width:0; }
      .ctrl input,.ctrl select,.ctrl button { width:100%; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"top\">
      <div>
        <div class=\"title\">🪐 Holographic Pipeline</div>
        <div class=\"sub\">Spatial pipeline view — each planet scales by opp volume, glow by efficiency.</div>
        <div class=\"nav\">
          <a href=\"/api/settings\">Settings</a>
          <a href=\"/api/daily_update\">Daily Dashboard</a>
          <a href=\"/api/secret_futurecast\">Futurecast Simulator</a>
        </div>
      </div>
      <div class=\"ctrl\">
        <div><label>Year</label><input id=\"year\" type=\"number\" min=\"2024\" max=\"2035\" /></div>
        <div><label>Month</label><input id=\"month\" type=\"number\" min=\"1\" max=\"12\" /></div>
        <div><label>&nbsp;</label><button id=\"apply\">Render</button></div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card\">
        <div class=\"sceneWrap\"><div class=\"scene\" id=\"scene\"></div></div>
      </div>
      <div class=\"card legend\">
        <h3>Pipeline Telemetry</h3>
        <p id=\"status\">Loading…</p>
        <div id=\"chips\"></div>
        <table>
          <thead><tr><th>Pipeline</th><th class=\"num\">Created</th><th class=\"num\">Sales</th><th class=\"num\">Eff.</th></tr></thead>
          <tbody id=\"rows\"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>
  const url = new URL(window.location.href);
  const now = new Date();
  const yEl = document.getElementById('year');
  const mEl = document.getElementById('month');
  yEl.value = url.searchParams.get('year') || now.getFullYear();
  mEl.value = url.searchParams.get('month') || (now.getMonth()+1);

  function nf(v){ return Number(v||0).toLocaleString(); }
  function pct(v){ return Number.isFinite(v)?`${v.toFixed(1)}%`:'—'; }

  function colorFor(i){ const pal=['#22d3ee','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444']; return pal[i%pal.length]; }

  function renderScene(pipes){
    const scene=document.getElementById('scene');
    scene.innerHTML='';
    const cx=scene.clientWidth/2, cy=scene.clientHeight/2;
    const maxCreated=Math.max(1,...pipes.map(p=>p.created));

    // rings
    [110,170,230,290].forEach(r=>{
      const e=document.createElement('div'); e.className='ring'; e.style.width=`${r*2}px`; e.style.height=`${r*2}px`; scene.appendChild(e);
    });

    pipes.forEach((p,i)=>{
      const angle=(Math.PI*2/pipes.length)*i - Math.PI/2;
      const radius=120 + (i%4)*55;
      const x=cx + Math.cos(angle)*radius;
      const y=cy + Math.sin(angle)*radius*0.45;
      const sz=34 + Math.round((p.created/maxCreated)*56);
      const c=colorFor(i);
      const div=document.createElement('div');
      div.className='planet';
      div.style.left=`${x}px`; div.style.top=`${y}px`;
      div.style.width=`${sz}px`; div.style.height=`${sz}px`;
      div.style.background=`radial-gradient(circle at 30% 30%, #fff, ${c} 45%, #020617 150%)`;
      div.title=`${p.name} | Created ${p.created} | Sales ${p.sales} | Eff ${p.eff.toFixed(1)}%`;
      div.textContent=p.name.split(' ')[0];
      scene.appendChild(div);
    });
  }

  function renderTable(pipes){
    const rows=document.getElementById('rows');
    rows.innerHTML=pipes.map(p=>`<tr><td>${p.name}</td><td class=\"num\">${nf(p.created)}</td><td class=\"num\">${nf(p.sales)}</td><td class=\"num\">${pct(p.eff)}</td></tr>`).join('');
    document.getElementById('chips').innerHTML = pipes.map((p,i)=>`<span class=\"pill\" style=\"border-color:${colorFor(i)}55;color:${colorFor(i)}\">${p.name}</span>`).join('');
  }

  async function load(){
    const y=yEl.value, m=mEl.value;
    const q=`format=json&year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`;
    const [sales, created, ran] = await Promise.all([
      fetch(`/api/metrics/sales?${q}`).then(r=>r.json()),
      fetch(`/api/metrics/opportunities_created?${q}&pipeline_scope=all`).then(r=>r.json()),
      fetch(`/api/metrics/opportunities_ran?${q}`).then(r=>r.json()),
    ]);

    const bySales = sales?.breakdowns?.sales_by_pipeline || {};
    const byCreated = created?.breakdowns?.created_by_pipeline || {};
    const byRan = ran?.breakdowns?.ran_by_pipeline || {};
    const keys=[...new Set([...Object.keys(byCreated),...Object.keys(bySales),...Object.keys(byRan)])].filter(Boolean);

    const pipes=keys.map(k=>{
      const c=Number(byCreated[k]||0), s=Number(bySales[k]||0), r=Number(byRan[k]||0);
      const eff=(r>0)?(s/r*100):0;
      return {name:k, created:c, sales:s, ran:r, eff};
    }).sort((a,b)=>b.created-a.created);

    document.getElementById('status').textContent = `Window ${y}-${String(m).padStart(2,'0')} • Pipelines ${pipes.length}`;
    renderScene(pipes);
    renderTable(pipes);
  }

  document.getElementById('apply').addEventListener('click',()=>{
    url.searchParams.set('year', yEl.value); url.searchParams.set('month', mEl.value); history.replaceState(null,'',url.toString()); load();
  });

  load().catch(e=>{ document.getElementById('status').textContent=`Error: ${String(e)}`; });
  window.addEventListener('resize', ()=> load());
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
