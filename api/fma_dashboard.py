# -*- coding: utf-8 -*-

"""Vercel Python function: /api/fma_dashboard

FMA Dashboard (production)

Intent: mirror the Raydar "Team Performance" layout for canvassing/FMA lead gen.
Metric wiring will be added after schema is confirmed.

UI intent (Customer Insights production style):
- White cards on light gray background
- 3-column responsive grid
- Gradient accent line

NOTE: Metrics are placeholders until we finalize the Raydar/FMA metric schema.
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
  <title>Happy Solar — FMA Dashboard</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;

      /* Customer Insights vibe */
      --pink: #ec4899;
      --pink2: #f472b6;

      --blue: #3b82f6;
      --purple: #8b5cf6;
      --green: #10b981;
      --amber: #f59e0b;
      --cyan: #06b6d4;

      --shadow: 0 1px 3px rgba(17,24,39,0.06);
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
      width: 200px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
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
      border-color: rgba(236,72,153,0.45);
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }

    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
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
      box-shadow: var(--shadow);
      min-height: 120px;
    }

    .card-header { display:flex; align-items:flex-start; justify-content: space-between; gap: 10px; }
    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .span-12 { grid-column: span 12; }
    .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; }
    .span-3 { grid-column: span 3; }

    @media (max-width: 980px) {
      .span-6, .span-4 { grid-column: span 12; }
      .span-3 { grid-column: span 6; }
    }
    @media (max-width: 560px) {
      .span-3 { grid-column: span 12; }
    }

    /* Raydar-like KPI cards */
    .kpiRow {
      display:flex;
      align-items:flex-end;
      justify-content: space-between;
      gap: 10px;
      margin-top: 10px;
    }

    .kpiVal {
      font-size: 36px;
      line-height: 1;
      font-weight: 950;
      letter-spacing: -0.02em;
      color: #0f172a;
    }

    .kpiVal.blue { color: #1d4ed8; }
    .kpiVal.purple { color: #6d28d9; }
    .kpiVal.green { color: #047857; }
    .kpiVal.amber { color: #b45309; }

    .kpiSub {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted2);
      font-weight: 800;
    }

    .pillbar {
      display:flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
      box-shadow: var(--shadow);
    }

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

    /* Funnel */
    .funnelWrap { margin-top: 10px; }
    .funnelBar {
      display:grid;
      grid-template-columns: 1fr auto 0.4fr auto 0.2fr;
      align-items:center;
      gap: 10px;
      margin-top: 12px;
    }

    .seg {
      height: 46px;
      border-radius: 10px;
      display:flex;
      align-items:center;
      justify-content:center;
      color:#fff;
      font-weight: 950;
      letter-spacing: -0.01em;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
      white-space: nowrap;
      overflow:hidden;
      text-overflow: ellipsis;
      padding: 0 10px;
    }

    .seg.blue { background: rgba(59,130,246,0.92); }
    .seg.purple { background: rgba(139,92,246,0.92); }
    .seg.green { background: rgba(16,185,129,0.92); }

    .arrow { color: #94a3b8; font-weight: 900; }

    /* Top performers tables */
    .list {
      margin-top: 10px;
      display:flex;
      flex-direction: column;
      gap: 10px;
    }

    .row {
      display:flex;
      align-items:center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fff;
    }

    .left {
      display:flex;
      align-items:center;
      gap: 10px;
      min-width: 0;
    }

    .badge {
      width: 22px;
      height: 22px;
      border-radius: 999px;
      display:flex;
      align-items:center;
      justify-content:center;
      font-size: 12px;
      font-weight: 950;
      color: #0f172a;
      background: #eef2ff;
      border: 1px solid #e0e7ff;
      flex: 0 0 auto;
    }

    .name {
      font-weight: 900;
      color: #0f172a;
      font-size: 13px;
      overflow:hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .val {
      font-weight: 950;
      color: #0f172a;
      font-size: 14px;
    }

    .skeleton {
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg,#f1f5f9,#e2e8f0,#f1f5f9);
      background-size: 200% 100%;
      animation: sh 1.4s ease-in-out infinite;
    }

    @keyframes sh {
      0% { background-position: 0% 0%; }
      100% { background-position: -200% 0%; }
    }

    .note {
      color: var(--muted);
      font-size: 12px;
      margin-top: 10px;
      line-height: 1.35;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">FMA Dashboard</div>
        <div class="subtitle">Team Performance — real-time setter metrics (Raydar-style cards)</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn active" href="/api/fma_dashboard">FMA dashboard</a>
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
        </div>
      </div>
      <div style="min-width:260px">
        <div class="card-title">Month</div>
        <div class="meta">Year: __YEAR__ • Month: __MONTH__</div>
      </div>
    </div>

    <!-- Raydar-style period selector (UI only for now) -->
    <div class="pillbar" id="periodTabs">
      <div class="pill active" data-period="today">Today</div>
      <div class="pill" data-period="yesterday">Yesterday</div>
      <div class="pill" data-period="7d">7 Days</div>
      <div class="pill" data-period="thiswk">This Wk</div>
      <div class="pill" data-period="lastwk">Last Wk</div>
      <div class="pill" data-period="thismo">This Mo</div>
      <div class="pill" data-period="lastmo">Last Mo</div>
      <div class="pill" data-period="all">All</div>
    </div>

    <div class="grid">
      <!-- KPI row (Raydar-style cards) -->
      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Total Knocks</div>
          <div class="meta">(Dispositioned leads)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal" id="kpiKnocks">—</div>
        </div>
        <div class="kpiSub" id="kpiKnocksSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Convos</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal blue" id="kpiConvos">—</div>
        </div>
        <div class="kpiSub" id="kpiConvosSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Appts</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal purple" id="kpiAppts">—</div>
        </div>
        <div class="kpiSub" id="kpiApptsSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Appt % Knocks</div>
          <div class="meta">Appts / Knocks</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal amber" id="kpiApptPct">—</div>
        </div>
        <div class="kpiSub" id="kpiApptPctSub">—</div>
      </div>

      <div class="card span-3">
        <div class="card-header">
          <div class="card-title">Go-Backs</div>
          <div class="meta">(Metric schema pending)</div>
        </div>
        <div class="kpiRow">
          <div class="kpiVal green" id="kpiGobacks">—</div>
        </div>
        <div class="kpiSub" id="kpiGobacksSub">—</div>
      </div>

      <div class="card span-12">
        <div class="card-header">
          <div class="card-title">Conversion Funnel</div>
          <div class="meta">Knocks → Convos → Appts</div>
        </div>
        <div class="funnelWrap">
          <div class="funnelBar">
            <div class="seg blue" id="segKnocks">— Knocks</div>
            <div class="arrow">→</div>
            <div class="seg purple" id="segConvos">— Convos</div>
            <div class="arrow">→</div>
            <div class="seg green" id="segAppts">— Appts</div>
          </div>
          <div class="note" id="funnelNote">Metric schema pending for Convos/Appts. Knocks currently backed by Raydar dispositioned leads.</div>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Top Performers — Knocks</div>
          <div class="meta">(Placeholder until schema is finalized)</div>
        </div>
        <div class="list" id="topKnocks">
          <div class="row"><div class="left"><div class="badge">1</div><div class="name"><div class="skeleton" style="width:160px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">2</div><div class="name"><div class="skeleton" style="width:140px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">3</div><div class="name"><div class="skeleton" style="width:150px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div class="card-title">Top Performers — Appointments</div>
          <div class="meta">(Placeholder until schema is finalized)</div>
        </div>
        <div class="list" id="topAppts">
          <div class="row"><div class="left"><div class="badge">1</div><div class="name"><div class="skeleton" style="width:160px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">2</div><div class="name"><div class="skeleton" style="width:140px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
          <div class="row"><div class="left"><div class="badge">3</div><div class="name"><div class="skeleton" style="width:150px"></div></div></div><div class="val"><div class="skeleton" style="width:40px"></div></div></div>
        </div>
      </div>

      <div class="card span-12">
        <div class="card-title">Status</div>
        <div class="meta">
          UI is built to match Raydar. Next step: confirm metric definitions + exact field mappings (Knocks, Convos, Appts, Go-backs) and wire these cards.
        </div>
      </div>
    </div>
  </div>

<script>
  // Period tabs: UI only (metric wiring comes after schema confirmation)
  document.querySelectorAll('#periodTabs .pill').forEach(p => {
    p.addEventListener('click', () => {
      document.querySelectorAll('#periodTabs .pill').forEach(x => x.classList.remove('active'));
      p.classList.add('active');
      // placeholder; will call metrics endpoint once defined
      load();
    });
  });

  function setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  }

  function renderTopList(containerId, rows) {
    const el = document.getElementById(containerId);
    if (!el) return;
    let html = '';
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      html += `
        <div class="row">
          <div class="left">
            <div class="badge">${i + 1}</div>
            <div class="name">${(r.name || '—')}</div>
          </div>
          <div class="val">${(typeof r.value !== 'undefined' ? r.value : '—')}</div>
        </div>`;
    }
    el.innerHTML = html;
  }

  async function load() {
    // For now, only Knocks is backed by Raydar (dispositioned leads).
    // We'll wire the rest after metric schema is confirmed.

    setText('kpiKnocks', '…');
    setText('kpiConvos', '—');
    setText('kpiAppts', '—');
    setText('kpiApptPct', '—');
    setText('kpiGobacks', '—');

    setText('kpiKnocksSub', 'Loading…');
    setText('kpiConvosSub', 'Schema pending');
    setText('kpiApptsSub', 'Schema pending');
    setText('kpiApptPctSub', 'Schema pending');
    setText('kpiGobacksSub', 'Schema pending');

    setText('segKnocks', '… Knocks');
    setText('segConvos', '— Convos');
    setText('segAppts', '— Appts');

    try {
      // Temporary wiring: treat "knocks" as the number of Raydar dispositioned leads in the selected month window.
      // Next: replace with proper period handling + breakdown by user.
      const y = __YEAR__;
      const m = __MONTH__;
      const res = await fetch(`/api/raydar/stats?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}`, { cache: 'no-store' });
      const data = res.ok ? await res.json() : null;

      const knocks = data && typeof data.leads !== 'undefined' ? Number(data.leads) : null;
      setText('kpiKnocks', knocks === null ? '—' : String(knocks));
      setText('kpiKnocksSub', 'Dispositioned leads (all-time in reporting DB)');
      setText('segKnocks', `${knocks === null ? '—' : knocks} Knocks`);

      // Placeholder funnel numbers
      setText('segConvos', '— Convos');
      setText('segAppts', '— Appts');

      renderTopList('topKnocks', [
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
      ]);
      renderTopList('topAppts', [
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
        { name: '—', value: '—' },
      ]);

    } catch (e) {
      setText('kpiKnocks', 'ERR');
      setText('kpiKnocksSub', String(e));
      setText('segKnocks', 'ERR Knocks');
    }
  }

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
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
