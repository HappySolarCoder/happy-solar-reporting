# -*- coding: utf-8 -*-

"""Vercel Python function: /api/website_traffic

Website Traffic Dashboard v1 — WIREFRAME / EXAMPLE DATA stub for
Marketing + Charles QA. HTML default. Optional ?format=json returns
{stub:true, example:true}. No live metric wiring in this file.

Do NOT wire GA4 Data API or warehouse document reads here. Do not invent
Meta spend or claim an Ads connection. Instant Form / 3PL are NOT
website leads. Form freeze: this page does not change the calculator form.

Later wiring exclude list (do not count as live website leads):
Hawkstone Way, 313 E Stonebridge Gilbert, Test Test, Evan Day,
adchday@gmail.com, evanrday23@gmail.com, preview/debug/internal.

Primary CTA: www.happyslr.com/estimate. Dual-domain history stays
(www.happyslr.com / happyslr.com + wny.happyslr.com). Warehouse named
fills later: source=new-site-estimate.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav

NY_TZ = ZoneInfo("America/New_York")
JSON_STUB = {"stub": True, "example": True}


def default_range_et(now: datetime | None = None) -> tuple[str, str]:
    today = (now or datetime.now(NY_TZ)).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def render_html(now: datetime | None = None) -> str:
    start, end = default_range_et(now)
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Website Traffic</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#00C853; --blue:#2196F3; --red:#dc2626; --amber:#d97706;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1180px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }
    .title { font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:820px; }
    .accentline { height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,var(--green) 0%, var(--blue) 55%, rgba(33,150,243,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(0,200,83,.10); border-color:rgba(0,200,83,.45); color:#0a7a34; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f2f5; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button, input[type="date"] { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--green); border-color:var(--green); color:#fff; font-weight:900; cursor:pointer; }
    .check { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:800; color:#334155; background:#f0f2f5; padding:8px 10px; border-radius:10px; border:1px solid var(--border); }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); }
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-6 { grid-column:span 6; } .span-8 { grid-column:span 8; } .span-12 { grid-column:span 12; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:36px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .example-tag { display:inline-block; margin-left:6px; padding:2px 6px; border-radius:999px; background:#fef3c7; color:#92400e; font-size:10px; font-weight:900; letter-spacing:.03em; vertical-align:middle; }
    .banner { grid-column:span 12; padding:12px 14px; border-radius:12px; border:1px solid #fde68a; background:#fffbeb; color:#92400e; font-size:13px; font-weight:700; }
    .banner.alert { border-color:#fecaca; background:#fef2f2; color:#991b1b; }
    .banner.gate { border-color:#bfdbfe; background:#eff6ff; color:#1e3a8a; }
    .banner.meta { border-color:#e5e7eb; background:#f8fafc; color:#334155; }
    table { width:100%; border-collapse:collapse; }
    th, td { border-bottom:1px solid var(--border); padding:9px 10px; text-align:left; font-size:13px; }
    th { color:#64748b; font-weight:900; background:#fafbfc; }
    .jsonlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    .section-label { grid-column:span 12; margin-top:4px; font-size:12px; font-weight:900; letter-spacing:.04em; text-transform:uppercase; color:#64748b; }
    .tabs { display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }
    .tabbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; cursor:pointer; }
    .tabbtn.active { background:rgba(33,150,243,.10); border-color:rgba(33,150,243,.45); color:#1d4ed8; }
    .tabpanel { display:none; }
    .tabpanel.active { display:block; }
    .delta { font-weight:900; }
    .delta.up { color:#047857; }
    .delta.down { color:#b45309; }
    .vs-prior.is-off, .is-off { display:none !important; }
    .callout { padding:12px 14px; border-radius:12px; border:1px dashed #93c5fd; background:#f8fbff; color:#1e3a8a; font-size:13px; font-weight:700; }
    .callout.warn { border-color:#fcd34d; background:#fffbeb; color:#92400e; }
    .chip { display:inline-flex; align-items:center; flex-wrap:wrap; gap:6px; padding:7px 10px; border-radius:999px; border:1px solid #fde68a; background:#fffbeb; color:#92400e; font-size:12px; font-weight:800; }
    .steps { display:flex; flex-wrap:wrap; gap:8px; align-items:stretch; }
    .step { flex:1 1 120px; background:#f8fafc; border:1px solid var(--border); border-radius:12px; padding:12px; }
    .step .name { font-size:12px; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:.03em; }
    .step .val { font-size:22px; font-weight:950; margin-top:6px; }
    .map { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px 16px; font-size:13px; }
    .map b { color:#1a2b4a; }
    .footer { margin-top:18px; padding:14px 16px; border-radius:14px; border:1px solid var(--border); background:#fff; color:#64748b; font-size:12px; line-height:1.55; }
    .pii-wrap { position:relative; min-height:180px; }
    .pii-mock { filter:blur(7px); user-select:none; pointer-events:none; opacity:.72; }
    .pii-gate { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; text-align:center; padding:16px; font-size:13px; font-weight:800; color:#1e3a8a; background:rgba(255,255,255,.55); border-radius:12px; }
    .disabled-note { color:#94a3b8; font-weight:800; }
    @media (max-width:980px) { .span-3,.span-4,.span-6,.span-8,.span-12 { grid-column:span 12; } .map { grid-template-columns:1fr; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:28px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Website Traffic <span class="example-tag">EXAMPLE DATA</span></div>
        <div class="subtitle">Wireframe for Marketing + Charles QA. Primary CTA is <b>www.happyslr.com/estimate</b>. Dual-domain history stays (happyslr.com + wny.happyslr.com). Instant Form / 3PL are not website leads. Numbers below are placeholders — not live GA4, warehouse, or Meta.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Date range ET</div><input id="startDate" type="date" value="__START__" /><input id="endDate" type="date" value="__END__" /></div>
        <div class="filter"><div class="filter-label">Domain</div>
          <select id="domain">
            <option value="all" selected>All</option>
            <option value="happyslr.com">happyslr.com</option>
            <option value="wny.happyslr.com">wny.happyslr.com</option>
          </select>
        </div>
        <label class="check"><input id="testFilter" type="checkbox" checked /> Test filter ON</label>
        <label class="check"><input id="comparePrior" type="checkbox" checked /> Compare prior</label>
        <button id="apply" type="button">Apply</button>
      </div>
    </div>

    <div class="grid">
      <div id="wireframeBanner" class="banner">WIREFRAME / EXAMPLE DATA — not live metrics. Chrome changes the selected range label only. No GA4 Data API, Firestore, or Meta Ads read in this stub.</div>
      <div class="card span-12">
        <div class="card-title">Chrome <span class="example-tag">STUB</span></div>
        <div class="meta" id="chromeLabel">Range __START__ → __END__ ET · domain All · test filter ON · compare prior ON</div>
      </div>

      <div class="section-label">Strips</div>
      <div class="card span-4">
        <div class="card-title">Meta spend / reach / clicks <span class="example-tag">WHEN ADS ACTIVE</span></div>
        <div class="kpi">—</div>
        <div class="meta">Placeholder only. Meta is not wired. Do not treat the dash as spend. Shown when Ads ACTIVE in a later wiring pass.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Scoreboard <span class="example-tag">EXAMPLE</span></div>
        <div class="kpi">12</div>
        <div class="meta">Named fills · session→submit 2.1% · start→submit 24% · CPA when paid — (paid window only; blank until Meta is wired)</div>
      </div>
      <div class="banner alert span-12">EXAMPLE ALERT: estimate/LP visits ↑ · starts → 0 — leak uses /estimate (or WNY calc) visits, not all-site sessions. Not a live alert.</div>

      <div class="card span-12">
        <div class="card-title">Where each question will live</div>
        <div class="map" style="margin-top:10px">
          <div><b>Brand site vs estimate/calc sessions</b> → Overview</div>
          <div><b>Channel + FB organic vs Meta paid + CTA taps</b> → Overview / Acquisition</div>
          <div><b>/estimate + legacy wny pages</b> → Content/LPs</div>
          <div><b>Step drop-off + named-fill %</b> → Funnel</div>
          <div><b>WNY metros + device/browser</b> → Audience</div>
          <div><b>Who filled (sales) / counts (Marketing)</b> → Named fills</div>
        </div>
      </div>
    </div>

    <div class="tabs" role="tablist">
      <button type="button" class="tabbtn active" data-tab="overview">Overview</button>
      <button type="button" class="tabbtn" data-tab="acquisition">Acquisition</button>
      <button type="button" class="tabbtn" data-tab="content">Content/LPs</button>
      <button type="button" class="tabbtn" data-tab="funnel">Funnel</button>
      <button type="button" class="tabbtn" data-tab="audience">Audience</button>
      <button type="button" class="tabbtn" data-tab="named">Named fills</button>
    </div>

    <section id="tab-overview" class="tabpanel active" data-tab="overview">
      <div class="grid">
        <div class="section-label">Overview — KPI cards</div>
        <div class="card span-3"><div class="card-title">Sessions <span class="example-tag">EXAMPLE</span></div><div class="kpi">4,218</div><div class="meta vs-prior">vs prior <span class="delta up">+8%</span></div></div>
        <div class="card span-3"><div class="card-title">Users <span class="example-tag">EXAMPLE</span></div><div class="kpi">3,640</div><div class="meta vs-prior">vs prior <span class="delta up">+6%</span></div></div>
        <div class="card span-3"><div class="card-title">New / returning <span class="example-tag">EXAMPLE</span></div><div class="kpi">78% / 22%</div><div class="meta vs-prior">new vs prior <span class="delta up">+2 pts</span></div></div>
        <div class="card span-3"><div class="card-title">Pageviews <span class="example-tag">EXAMPLE</span></div><div class="kpi">9,104</div><div class="meta vs-prior">vs prior <span class="delta up">+5%</span></div></div>
        <div class="card span-3"><div class="card-title">Pages / session <span class="example-tag">EXAMPLE</span></div><div class="kpi">2.16</div><div class="meta vs-prior">vs prior <span class="delta down">−0.04</span></div></div>
        <div class="card span-3"><div class="card-title">Bounce / engaged <span class="example-tag">GA4</span></div><div class="kpi">41% / 59%</div><div class="meta">GA4 bounce + engaged session rate. <span class="vs-prior">vs prior <span class="delta down">bounce −3 pts</span></span></div></div>
        <div class="card span-3"><div class="card-title">Avg engagement <span class="example-tag">GA4</span></div><div class="kpi">1m 12s</div><div class="meta vs-prior">vs prior <span class="delta up">+4s</span></div></div>
        <div class="card span-3 vs-prior"><div class="card-title">Vs prior <span class="example-tag">EXAMPLE</span></div><div class="kpi">+8%</div><div class="meta">Sessions vs prior period (same length, ET). Toggle Compare prior in chrome.</div></div>
        <div class="card span-3"><div class="card-title">Brand site sessions <span class="example-tag">EXAMPLE</span></div><div class="kpi">2,768</div><div class="meta">happyslr.com / www brand pages. Not the funnel top. <span class="vs-prior">vs prior <span class="delta up">+5%</span></span></div></div>
        <div class="card span-3"><div class="card-title">Estimate / calc sessions <span class="example-tag">EXAMPLE</span></div><div class="kpi">1,450</div><div class="meta">/estimate + legacy wny calculator. Funnel step 1. <span class="vs-prior">vs prior <span class="delta up">+11%</span></span></div></div>
        <div class="card span-3"><div class="card-title">CTA taps → /estimate <span class="example-tag">EXAMPLE</span></div><div class="kpi">186</div><div class="meta">Brand-page CTA clicks that land on /estimate. Placeholder only.</div></div>
        <div class="card span-3"><div class="card-title">Organic FB post → sessions <span class="example-tag">EXAMPLE</span></div><div class="kpi">94</div><div class="meta">facebook / organic sessions from a post. Placeholder — not Ads Manager.</div></div>
      </div>
    </section>

    <section id="tab-acquisition" class="tabpanel" data-tab="acquisition">
      <div class="grid">
        <div class="section-label">Acquisition</div>
        <div class="card span-8">
          <div class="card-title">Channel + source / medium <span class="example-tag">EXAMPLE</span></div>
          <div class="meta" style="margin-bottom:10px">Stub table. Later: GA4 session default channel group + sessionSource / sessionMedium.</div>
          <table>
            <thead><tr><th>Channel</th><th>Source / medium</th><th>Sessions</th><th>Users</th></tr></thead>
            <tbody>
              <tr><td>Organic Search</td><td>google / organic</td><td>1,640</td><td>1,410</td></tr>
              <tr><td>Direct</td><td>(direct) / (none)</td><td>980</td><td>860</td></tr>
              <tr><td>Paid Social</td><td>facebook / paid</td><td>720</td><td>610</td></tr>
              <tr><td>Organic Social</td><td>facebook / organic</td><td>410</td><td>360</td></tr>
              <tr><td>Referral</td><td>wix.com / referral</td><td>180</td><td>150</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">FB organic vs Meta paid</div>
          <div class="callout">Callout slot: Facebook / Instagram organic vs Meta paid. Not live. Do not read this as Ads Manager numbers.</div>
          <div class="meta" style="margin-top:10px">Organic social 410 · Paid social 720 · example split only.</div>
        </div>
        <div class="card span-12 callout warn">Paid landing mismatch: facebook / paid landed on www (home or city LP) without a calc start. Later wiring flags www-without-estimate_start. Not live Ads numbers.</div>
        <div class="card span-12">
          <div class="card-title">Landing × source — top 10 <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>#</th><th>Landing</th><th>Source / medium</th><th>Sessions</th></tr></thead>
            <tbody>
              <tr><td>1</td><td>/estimate</td><td>google / organic</td><td>540</td></tr>
              <tr><td>2</td><td>/</td><td>(direct) / (none)</td><td>430</td></tr>
              <tr><td>3</td><td>/estimate</td><td>facebook / paid</td><td>310</td></tr>
              <tr><td>4</td><td>/buffalo</td><td>google / organic</td><td>220</td></tr>
              <tr><td>5</td><td>/rochester</td><td>google / organic</td><td>180</td></tr>
              <tr><td>6</td><td>wny /calculator</td><td>(direct) / (none)</td><td>160</td></tr>
              <tr><td>7</td><td>/syracuse</td><td>google / organic</td><td>140</td></tr>
              <tr><td>8</td><td>/ny-incentives</td><td>facebook / organic</td><td>110</td></tr>
              <tr><td>9</td><td>/estimate</td><td>facebook / organic</td><td>90</td></tr>
              <tr><td>10</td><td>/contact-me</td><td>(direct) / (none)</td><td>70</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-content" class="tabpanel" data-tab="content">
      <div class="grid">
        <div class="section-label">Content / LPs</div>
        <div class="card span-12 callout">Call out: primary landing is <b>/estimate</b> on www.happyslr.com. Legacy wny.happyslr.com calculator pages stay in dual-domain history — do not drop them.</div>
        <div class="card span-4">
          <div class="card-title">Top landings <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Page</th><th>Sessions</th></tr></thead>
            <tbody>
              <tr><td>/estimate</td><td>1,210</td></tr>
              <tr><td>/</td><td>860</td></tr>
              <tr><td>/buffalo</td><td>310</td></tr>
              <tr><td>wny /calculator (legacy)</td><td>240</td></tr>
              <tr><td>/rochester</td><td>210</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">Top pages <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Page</th><th>Views</th></tr></thead>
            <tbody>
              <tr><td>/estimate</td><td>2,040</td></tr>
              <tr><td>/</td><td>1,120</td></tr>
              <tr><td>/buffalo</td><td>390</td></tr>
              <tr><td>/rochester</td><td>280</td></tr>
              <tr><td>wny /calculator (legacy)</td><td>260</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">Top exits <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Page</th><th>Exits</th></tr></thead>
            <tbody>
              <tr><td>/estimate</td><td>640</td></tr>
              <tr><td>/</td><td>410</td></tr>
              <tr><td>/contact-me</td><td>90</td></tr>
              <tr><td>wny /calculator (legacy)</td><td>80</td></tr>
              <tr><td>/ny-incentives</td><td>60</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-funnel" class="tabpanel" data-tab="funnel">
      <div class="grid">
        <div class="section-label">Funnel</div>
        <div class="card span-12">
          <div class="card-title">estimate/LP visits → start → address → bill → contact → submit → named fill <span class="example-tag">STEP % STUBS</span></div>
          <div class="meta" style="margin-bottom:10px">Funnel top is <b>estimate/LP visits</b> (/estimate + legacy wny calculator), not all-site sessions. All-site sessions as step 1 muddies the visits-without-starts leak. Instant Form / 3PL are NOT website leads.</div>
          <div id="excludeChip" class="chip" style="margin-bottom:12px">Test filter ON — excluded: Hawkstone / Stonebridge / Test Test / Evan Day / test emails / preview</div>
          <div class="steps" style="margin-bottom:10px">
            <div class="step"><div class="name">Brand-site sessions</div><div class="val">2,768</div><div class="meta">Dual top — not funnel step 1</div></div>
            <div class="step"><div class="name">Estimate / LP visits</div><div class="val">1,450</div><div class="meta">Funnel step 1 · 100%</div></div>
          </div>
          <div class="steps">
            <div class="step"><div class="name">Estimate / LP visits</div><div class="val">1,450</div><div class="meta">100% of estimate/LP</div></div>
            <div class="step"><div class="name">Start</div><div class="val">337</div><div class="meta">23.2% of estimate/LP</div></div>
            <div class="step"><div class="name">Address</div><div class="val">268</div><div class="meta">79.5% of start</div></div>
            <div class="step"><div class="name">Bill</div><div class="val">214</div><div class="meta">79.9% of address</div></div>
            <div class="step"><div class="name">Contact</div><div class="val">156</div><div class="meta">72.9% of bill</div></div>
            <div class="step"><div class="name">Submit</div><div class="val">88</div><div class="meta">56.4% of contact</div></div>
            <div class="step"><div class="name">Named fill</div><div class="val">12</div><div class="meta">13.6% of submit</div></div>
          </div>
        </div>
        <div class="card span-12 callout warn">Instant Form and 3PL bought leads do not belong on this funnel. They are not website leads.</div>
      </div>
    </section>

    <section id="tab-audience" class="tabpanel" data-tab="audience">
      <div class="grid">
        <div class="section-label">Audience</div>
        <div class="card span-6">
          <div class="card-title">WNY metros <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Metro</th><th>Sessions</th><th>Share</th></tr></thead>
            <tbody>
              <tr><td>Buffalo</td><td>1,180</td><td>28%</td></tr>
              <tr><td>Rochester</td><td>980</td><td>23%</td></tr>
              <tr><td>Syracuse</td><td>640</td><td>15%</td></tr>
              <tr><td>Niagara-area</td><td>300</td><td>7%</td></tr>
              <tr><td>Other NY / unknown</td><td>1,118</td><td>27%</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card span-6">
          <div class="card-title">Device / browser <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Device</th><th>Sessions</th><th>Browser</th><th>Share</th></tr></thead>
            <tbody>
              <tr><td>mobile</td><td>2,740</td><td>Chrome</td><td>58%</td></tr>
              <tr><td>desktop</td><td>1,280</td><td>Safari</td><td>29%</td></tr>
              <tr><td>tablet</td><td>198</td><td>Other</td><td>13%</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-named" class="tabpanel" data-tab="named">
      <div class="grid">
        <div class="section-label">Named fills</div>
        <div class="banner gate span-12">Role-gated: Marketing sees aggregates only. The PII table is gated for sales. This stub does not authenticate — the blur/disabled table is the intended sales-only slot.</div>
        <div class="card span-6">
          <div class="card-title">Marketing aggregates <span class="example-tag">EXAMPLE</span></div>
          <div class="kpi">12</div>
          <div class="meta">Named fills in range · 8 source=new-site-estimate · 4 legacy wny. Counts only — no names, emails, or phones for Marketing.</div>
        </div>
        <div class="card span-6">
          <div class="card-title">Warehouse source</div>
          <div class="meta" style="margin-top:10px">Later wiring reads named fills with <b>source=new-site-estimate</b>. Dual-domain history (wny calculator / leads@) stays for compare. Exclude list is documented in the handler comment — not shown as live rows.</div>
        </div>
        <div class="card span-12">
          <div class="card-title">PII table — sales only <span class="example-tag">GATED</span></div>
          <div class="pii-wrap">
            <table class="pii-mock" aria-hidden="true">
              <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Address</th><th>Source</th></tr></thead>
              <tbody>
                <tr><td>A. Example</td><td>alex@example.com</td><td>716-555-0100</td><td>1 Sample St</td><td>new-site-estimate</td></tr>
                <tr><td>B. Placeholder</td><td>blair@example.com</td><td>585-555-0142</td><td>2 Sample Ave</td><td>new-site-estimate</td></tr>
                <tr><td>C. Mock</td><td>casey@example.com</td><td>315-555-0199</td><td>3 Sample Rd</td><td>legacy-wny</td></tr>
              </tbody>
            </table>
            <div class="pii-gate">Blurred / disabled PII mock. Sales role unlocks this table in a later pass. Marketing stays on aggregates.</div>
          </div>
          <div class="meta disabled-note">Disabled in this wireframe. Not live warehouse rows.</div>
        </div>
      </div>
    </section>

    <div class="footer">
      <div><b>Data sources (later wiring)</b> — GA4 property 408492342 / G-V02RZFR4SZ. Warehouse named fills source=new-site-estimate. Meta if wired (not wired on this stub). Primary CTA: www.happyslr.com/estimate. Dual-domain history: happyslr.com + wny.happyslr.com. Instant Form / 3PL excluded from website leads. <a class="jsonlink" href="/api/website_traffic?format=json">JSON stub</a></div>
    </div>
  </div>
<script>
(function() {
  var tabs = document.querySelectorAll('.tabbtn');
  var panels = document.querySelectorAll('.tabpanel');
  function showTab(id) {
    tabs.forEach(function(btn) { btn.classList.toggle('active', btn.getAttribute('data-tab') === id); });
    panels.forEach(function(panel) { panel.classList.toggle('active', panel.getAttribute('data-tab') === id); });
  }
  tabs.forEach(function(btn) {
    btn.addEventListener('click', function() { showTab(btn.getAttribute('data-tab')); });
  });
  function paintChrome() {
    var start = document.getElementById('startDate').value;
    var end = document.getElementById('endDate').value;
    var domain = document.getElementById('domain');
    var testOn = document.getElementById('testFilter').checked;
    var compare = document.getElementById('comparePrior').checked;
    document.getElementById('chromeLabel').textContent =
      'Range ' + start + ' → ' + end + ' ET · domain ' + domain.options[domain.selectedIndex].text +
      ' · test filter ' + (testOn ? 'ON' : 'OFF') + ' · compare prior ' + (compare ? 'ON' : 'OFF') +
      ' · example numbers unchanged';
    document.querySelectorAll('.vs-prior').forEach(function(el) {
      el.classList.toggle('is-off', !compare);
    });
    var chip = document.getElementById('excludeChip');
    if (chip) chip.classList.toggle('is-off', !testOn);
  }
  document.getElementById('apply').addEventListener('click', paintChrome);
  document.getElementById('testFilter').addEventListener('change', paintChrome);
  document.getElementById('comparePrior').addEventListener('change', paintChrome);
  document.getElementById('domain').addEventListener('change', paintChrome);
  paintChrome();
})();
</script>
</body>
</html>
"""
    return (
        html.replace("__START__", start)
        .replace("__END__", end)
        .replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css())
        .replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("website_traffic"))
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = (qs.get("format", [""])[0] or "").lower() == "json"
            if want_json:
                body = json.dumps(JSON_STUB).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
