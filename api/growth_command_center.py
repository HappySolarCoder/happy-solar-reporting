# -*- coding: utf-8 -*-

"""Growth Command Center page. HTML: /api/growth_command_center and /growth.

View-only. The screen observes spend, pace, and the ads bot. It has no
control that creates, edits, pauses, or budgets an ad. Not on the main
dashboard nav (same direct-URL pattern as inbound CAC).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _load_metric():
    path = API_DIR / "metrics" / "growth_command_center.py"
    spec = importlib.util.spec_from_file_location("hs_growth_command_center_metric", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load growth command center metric from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metric = _load_metric()


def _query_params(path: str) -> dict[str, str]:
    parsed = parse_qs(urlparse(path).query)
    return {key: values[-1] for key, values in parsed.items() if values}


def render_html(payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    return PAGE_HTML.replace("__PAYLOAD__", data)


PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Growth command center · Happy Solar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: dark;
    --canvas: #071B2D;
    --sidebar: #0A2238;
    --panel: #0C253B;
    --raised: #14334A;
    --border: #24435A;
    --cyan: #26D9EB;
    --blue: #2EA8FA;
    --amber: #FFBE45;
    --success: #11C99B;
    --critical: #F16D79;
    --text: #F1F6FF;
    --secondary: #B5C7DC;
    --muted: #8FA7BF;
    --sidebar-w: 194px;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--canvas); color: var(--text); }
  body {
    font-family: Inter, "Segoe UI", ui-sans-serif, system-ui, sans-serif;
    font-size: 13px;
    line-height: 19px;
    font-variant-numeric: tabular-nums;
  }
  button, input, select { font: inherit; color: inherit; }
  button { cursor: pointer; }
  button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {
    outline: 2px solid var(--cyan);
    outline-offset: 2px;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
  }
  .app { min-height: 100%; display: flex; background: var(--canvas); }
  .sidebar {
    width: var(--sidebar-w); flex: 0 0 var(--sidebar-w); background: var(--sidebar);
    border-right: 1px solid var(--border); display: flex; flex-direction: column;
    padding: 16px 0 20px; min-height: 100vh;
  }
  .brand { display: flex; align-items: center; gap: 10px; padding: 4px 16px 18px; }
  .brand-name { font-weight: 700; font-size: 16px; letter-spacing: -0.02em; }
  .nav-btn {
    height: 50px; display: flex; align-items: center; gap: 12px;
    width: calc(100% - 16px); margin: 1px 8px; padding: 0 12px;
    border: 0; border-radius: 8px; background: transparent; color: var(--secondary);
    text-align: left; font-weight: 600; font-size: 14px;
  }
  .nav-btn svg { flex: 0 0 20px; }
  .nav-btn:hover { background: rgba(255,255,255,0.04); color: var(--text); }
  .nav-btn.active { background: #1D6FBF; color: var(--text); box-shadow: inset 4px 0 0 var(--cyan); }
  .content {
    flex: 1; min-width: 0; padding: 14px 18px 16px;
    display: flex; flex-direction: column; gap: 12px;
  }
  .overview { display: flex; flex-direction: column; gap: 12px; min-width: 0; min-height: 0; flex: 1; }
  .header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; min-height: 58px; }
  .kicker { margin: 0; color: var(--muted); font-size: 12px; line-height: 16px; letter-spacing: 0.04em; }
  .title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  h1 { margin: 2px 0 0; font-size: 30px; line-height: 36px; font-weight: 650; letter-spacing: -0.03em; }
  h2 { margin: 0; font-size: 18px; line-height: 24px; font-weight: 600; }
  .badge {
    border: 1px solid var(--cyan); color: var(--cyan); border-radius: 999px;
    padding: 3px 8px; font-size: 11px; line-height: 16px; font-weight: 700; letter-spacing: 0.06em;
  }
  .badge.warn { border-color: var(--amber); color: var(--amber); }
  .header-tools { display: flex; align-items: flex-start; gap: 18px; }
  .date-wrap { position: relative; }
  .date-btn, .ghost-btn, .menu-btn {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 10px; color: var(--text);
  }
  .date-btn:hover, .ghost-btn:hover, .menu-btn:hover { background: var(--raised); }
  .menu-btn { display: none; width: 40px; height: 40px; justify-content: center; padding: 0; }
  .asof { text-align: right; }
  .asof .label, .label { color: var(--muted); font-size: 12px; line-height: 16px; }
  .asof strong { display: block; font-weight: 600; font-size: 13px; }
  .asof .cutoff { color: var(--secondary); font-size: 12px; }
  .menu {
    position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; width: 280px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px;
    box-shadow: 0 10px 24px rgba(0,0,0,0.28);
  }
  .menu button, .menu-link {
    display: block; width: 100%; text-align: left; background: transparent; border: 0;
    border-radius: 6px; padding: 8px 10px; color: var(--text);
  }
  .menu button:hover { background: var(--raised); }
  .menu .custom { display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; padding: 8px 4px 4px; }
  .menu input, .search, .select {
    background: var(--canvas); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
  }
  .kpis { display: grid; grid-template-columns: 1.3fr 1.1fr 0.7fr 1.1fr 0.7fr 1.1fr 0.85fr; gap: 12px; }
  .panel, .stat {
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0) 42%), var(--panel);
    border: 1px solid var(--border); border-radius: 8px;
  }
  .stat { padding: 12px 12px 10px; min-height: 128px; text-align: left; width: 100%; display: flex; flex-direction: column; gap: 4px; }
  .stat .label { display: flex; align-items: center; gap: 6px; }
  .info {
    width: 16px; height: 16px; border-radius: 50%; border: 1px solid var(--border);
    background: transparent; color: var(--muted); font-size: 10px; line-height: 14px; padding: 0;
  }
  .value { font-size: 36px; line-height: 40px; font-weight: 650; letter-spacing: -0.03em; }
  .value .goal { color: var(--secondary); font-size: 22px; font-weight: 600; }
  .goal-word { color: var(--muted); font-size: 12px; font-weight: 600; margin-left: 2px; }
  .bar { height: 6px; border-radius: 99px; background: var(--raised); overflow: hidden; margin-top: 6px; }
  .bar span { display: block; height: 100%; background: var(--blue); border-radius: 99px; }
  .meta-row { display: flex; justify-content: space-between; gap: 8px; margin-top: auto; font-size: 12px; line-height: 16px; }
  .attained { color: var(--cyan); }
  .behind, .critical { color: var(--critical); }
  .ahead, .under, .ok { color: var(--success); }
  .over { color: var(--amber); font-weight: 600; }
  .sub { color: var(--secondary); font-size: 12px; line-height: 16px; }
  .split { display: grid; grid-template-columns: 1fr 1px 1fr; gap: 8px; align-items: stretch; }
  .split .value { font-size: 28px; line-height: 32px; }
  .rule { background: var(--border); }
  .main-row { display: grid; grid-template-columns: minmax(0,56fr) minmax(0,24fr) minmax(0,20fr); gap: 12px; min-height: 300px; }
  .bottom-row { display: grid; grid-template-columns: minmax(0,45fr) minmax(0,55fr); gap: 12px; min-height: 220px; }
  .panel { padding: 12px 14px 10px; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
  .panel-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
  .legend { display: flex; gap: 12px; flex-wrap: wrap; color: var(--secondary); font-size: 12px; }
  .swatch { display: inline-block; width: 18px; height: 0; border-top: 2.5px solid var(--cyan); margin-right: 6px; vertical-align: middle; }
  .swatch.dash { border-top-style: dashed; border-top-color: var(--secondary); }
  .swatch.blue { border-top-color: var(--blue); }
  .chart-wrap { flex: 1; min-height: 180px; min-width: 0; }
  .chart-wrap svg { width: 100%; height: 100%; display: block; }
  .foot-note { margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 16px; }
  .watch {
    display: flex; gap: 8px; align-items: center; background: rgba(255,190,69,0.16);
    color: var(--amber); border-radius: 8px; padding: 8px 10px; font-weight: 700; margin: 4px 0 8px;
  }
  .unknown-banner { background: rgba(143,167,191,0.16); color: var(--secondary); }
  .incident-banner { background: rgba(241,109,121,0.16); color: var(--critical); }
  .check { display: flex; gap: 8px; align-items: flex-start; margin: 5px 0; color: var(--secondary); }
  .check strong { color: var(--text); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); display: inline-block; margin-top: 5px; flex: 0 0 8px; }
  .dot.amber { background: var(--amber); }
  .dot.muted { background: var(--muted); }
  .dot.bad { background: var(--critical); }
  .next { margin-top: auto; padding-top: 8px; border-top: 1px solid var(--border); }
  .next .label { margin-bottom: 2px; }
  .recs { display: flex; flex-direction: column; gap: 10px; overflow: auto; }
  .rec {
    display: grid; grid-template-columns: 22px 1fr; gap: 8px; width: 100%; text-align: left;
    background: transparent; border: 0; color: inherit; padding: 0;
  }
  .num {
    width: 22px; height: 22px; border-radius: 50%; background: var(--blue); color: #071B2D;
    display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700;
  }
  .rec p { margin: 2px 0 0; color: var(--secondary); }
  .empty { color: var(--secondary); padding: 12px 0; }
  .funnel-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
  .pill {
    border: 1px solid var(--amber); color: var(--amber); border-radius: 999px; padding: 2px 8px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
  }
  .funnel-scroll { overflow-x: auto; }
  .funnel { display: flex; align-items: stretch; gap: 4px; min-height: 92px; }
  .stage {
    flex: 1 1 0; background: var(--raised); border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 8px; text-align: left; min-width: 0;
  }
  .stage:hover { border-color: var(--blue); }
  .stage .count { font-size: 22px; line-height: 26px; font-weight: 650; margin-top: 4px; }
  .hop { width: 72px; flex: 0 0 72px; text-align: center; color: var(--secondary); font-size: 11px; line-height: 14px; align-self: center; }
  .hop strong { display: block; color: var(--text); font-size: 12px; }
  .tabs { display: flex; gap: 6px; }
  .tab {
    border: 1px solid var(--border); background: transparent; border-radius: 8px; padding: 4px 10px; color: var(--secondary);
  }
  .tab[aria-selected="true"] { background: var(--blue); border-color: var(--blue); color: white; }
  .linkish { background: none; border: 0; color: var(--cyan); padding: 0; font-weight: 600; }
  .table-scroll { overflow: auto; min-height: 0; flex: 1; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 7px 8px; border-bottom: 1px solid rgba(36,67,90,0.9); vertical-align: middle; }
  th { color: var(--muted); font-size: 12px; font-weight: 600; text-align: left; }
  th.num, td.num { text-align: right; }
  th button { background: none; border: 0; color: inherit; padding: 0; font-weight: 600; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: rgba(46,168,250,0.06); }
  .ad { display: flex; gap: 8px; align-items: center; text-align: left; }
  .thumb { width: 36px; height: 36px; border-radius: 6px; background: var(--raised); display: inline-flex; align-items: center; justify-content: center; flex: 0 0 36px; }
  .ad small { display: block; color: var(--muted); font-size: 12px; }
  .status { display: inline-flex; align-items: center; gap: 6px; }
  .toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
  .search { min-width: 0; flex: 1; }
  .stack { display: flex; flex-direction: column; gap: 12px; }
  .defs { display: grid; gap: 8px; }
  .defs div { background: var(--raised); border-radius: 8px; padding: 10px 12px; }
  .scrim { display: none; }
  .drawer-back {
    position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 50;
    display: flex; justify-content: flex-end;
  }
  .drawer {
    width: min(420px, 100%); height: 100%; background: var(--panel); border-left: 1px solid var(--border);
    padding: 18px 16px 28px; overflow: auto;
  }
  .drawer h2 { margin-bottom: 8px; }
  .drawer dl { display: grid; grid-template-columns: 140px 1fr; gap: 6px 10px; margin: 12px 0; }
  .drawer dt { color: var(--muted); }
  .drawer dd { margin: 0; }
  .icon-btn { background: transparent; border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; }
  .error { color: var(--critical); margin: 0; }
  .tip {
    position: fixed; z-index: 40; background: #10283C; border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; padding: 8px 10px; pointer-events: none; font-size: 12px; line-height: 16px; max-width: 240px;
  }
  @media (min-width: 1200px) and (max-width: 1439px) {
    :root { --sidebar-w: 176px; }
  }
  @media (max-width: 1199px) {
    .main-row { grid-template-columns: 1fr 1fr; }
    .chart-card { grid-column: 1 / -1; min-height: 280px; }
    .bottom-row { grid-template-columns: 1fr; }
    .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
  @media (max-width: 1199px) and (min-width: 768px) {
    :root { --sidebar-w: 64px; }
    .brand-name, .nav-btn span, .word { display: none; }
    .brand { justify-content: center; padding-left: 0; padding-right: 0; }
    .nav-btn { width: 48px; justify-content: center; padding: 0; }
    .funnel { min-width: 920px; }
  }
  @media (max-width: 767px) {
    .menu-btn { display: inline-flex; }
    .sidebar {
      position: fixed; z-index: 40; transform: translateX(-105%); transition: transform 0.18s ease;
      width: 240px; flex-basis: 240px;
    }
    .nav-open .sidebar { transform: none; }
    .nav-open .scrim { display: block; position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 30; }
    .brand-name, .nav-btn span { display: inline; }
    .nav-btn { width: calc(100% - 16px); justify-content: flex-start; padding: 0 12px; }
    .header { flex-wrap: wrap; }
    .kpis { grid-template-columns: 1fr 1fr; }
    .stat.spend { grid-column: 1 / -1; }
    .main-row, .bottom-row { grid-template-columns: 1fr; }
    .chart-card { min-height: 260px; }
    .funnel { flex-direction: column; min-width: 0; }
    .hop { width: auto; flex-basis: auto; display: flex; gap: 8px; justify-content: flex-start; padding: 0 8px; }
    .value { font-size: 30px; line-height: 34px; }
    h1 { font-size: 26px; line-height: 32px; }
    .asof { text-align: left; }
  }
  @media (min-width: 1200px) and (min-height: 900px) {
    .content { height: 100vh; overflow: hidden; }
    .overview { overflow: hidden; }
    .main-row { flex: 1.25; }
    .bottom-row { flex: 0.95; }
    .chart-wrap { min-height: 0; }
  }
</style>
</head>
<body>
<a class="sr-only" href="#main">Skip to command center</a>
<div id="app" aria-busy="false"></div>
<div id="tip" class="tip" hidden></div>
<script id="gcc-data" type="application/json">__PAYLOAD__</script>
<script>
const INITIAL = JSON.parse(document.getElementById('gcc-data').textContent);
const state = {
  payload: INITIAL,
  view: 'overview',
  costTab: 'cpl',
  sortKey: 'spend',
  sortDir: 'desc',
  query: '',
  drawer: null,
  navOpen: false,
  dateOpen: false,
  loading: false,
  error: ''
};

function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function money(value, exact) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const number = Number(value);
  if (exact) return number.toLocaleString('en-US', {style: 'currency', currency: 'USD'});
  return '$' + Math.round(number).toLocaleString('en-US');
}
function pct(value, places) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const digits = places == null ? 1 : places;
  const text = (Number(value) * 100).toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
  return text + '%';
}
function num(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-US');
}
function varianceCopy(block) {
  if (!block || block.value == null || block.status === 'unknown') return 'Unavailable';
  if (block.variance == null) return '';
  const amount = money(Math.abs(block.variance), false);
  if (block.status === 'over') return amount + ' over goal';
  if (block.status === 'under') return amount + ' under goal';
  return 'On goal';
}
function varianceClass(block) {
  if (!block || block.status === 'over') return 'over';
  if (block.status === 'under' || block.status === 'on_goal') return 'under';
  return 'sub';
}

function icon(name) {
  const common = 'viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  const paths = {
    home: '<path d="M4 11.5 12 4l8 7.5"/><path d="M7 10.5V20h10v-9.5"/>',
    campaign: '<path d="M4 10v4l10 4V6L4 10z"/><path d="M14 9.5c1.6.6 2.5 1.6 2.5 2.5S15.6 13.9 14 14.5"/><path d="M7 14.5v3"/>',
    funnel: '<path d="M4 5h16l-6 7v6l-4 2v-8L4 5z"/>',
    trend: '<path d="M4 16l5-5 3 3 7-7"/><path d="M15 7h4v4"/>',
    activity: '<circle cx="12" cy="12" r="8"/><path d="M12 8v5l3 2"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M18 6l-1.6 1.6M7.6 16.4 6 18"/>',
    sun: '<circle cx="12" cy="12" r="4" fill="#FFBE45" stroke="none"/><g stroke="#FFBE45"><path d="M12 2.6v2.3M12 19.1v2.3M2.6 12h2.3M19.1 12h2.3M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6"/></g>'
  };
  return `<svg ${common}>${paths[name] || ''}</svg>`;
}
function thumb(kind) {
  const inner = {
    house: '<path d="M4 12 12 5l8 7"/><path d="M7 11v8h10v-8"/>',
    sun: '<circle cx="12" cy="12" r="3.2"/><path d="M12 4v2M12 18v2M4 12H6M18 12h2M6.2 6.2l1.4 1.4M16.4 16.4l1.4 1.4M17.8 6.2 16.4 7.6M7.6 16.4 6.2 17.8"/>',
    home: '<circle cx="9" cy="10" r="2"/><circle cx="15" cy="10" r="2"/><path d="M5 18c.6-2.2 2.2-3.2 4-3.2S12.4 15.8 13 18"/><path d="M12 18c.5-1.8 1.7-2.8 3.2-2.8 1.4 0 2.6.9 3.3 2.8"/>',
    fallback: '<circle cx="12" cy="12" r="4"/>'
  }[kind] || '<circle cx="12" cy="12" r="4"/>';
  return `<span class="thumb"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#B5C7DC" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">${inner}</svg></span>`;
}

function Sidebar(state) {
  const items = [
    ['overview', 'Overview', 'home'],
    ['campaigns', 'Campaigns', 'campaign'],
    ['funnel', 'Funnel', 'funnel'],
    ['trends', 'Trends', 'trend'],
    ['activity', 'Activity', 'activity'],
    ['settings', 'Settings', 'settings']
  ];
  return `<aside class="sidebar" data-component="Sidebar" aria-label="Growth">
    <div class="brand">${icon('sun')}<span class="brand-name">Happy Solar</span></div>
    <nav>${items.map(([id, label, glyph]) => `<button class="nav-btn${state.view === id ? ' active' : ''}" data-action="nav" data-view="${id}" aria-current="${state.view === id ? 'page' : 'false'}">${icon(glyph)}<span>${label}</span></button>`).join('')}</nav>
  </aside>`;
}

function Header(state) {
  const data = state.payload;
  const badgeClass = data.sample_data ? 'badge' : 'badge warn';
  return `<header class="header" data-component="Header">
    <div>
      <button class="menu-btn" data-action="menu" aria-label="Open navigation" aria-expanded="${state.navOpen ? 'true' : 'false'}"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>
      <p class="kicker">02 / Operations Control</p>
      <div class="title-row"><h1>Growth command center</h1><span class="${badgeClass}">${esc(data.badge)}</span></div>
    </div>
    <div class="header-tools">
      <div class="date-wrap">
        <button class="date-btn" data-action="date-toggle" aria-expanded="${state.dateOpen ? 'true' : 'false'}" aria-haspopup="true">
          <span aria-hidden="true">▣</span> ${esc(data.selected_range.label)} <span aria-hidden="true">▾</span>
        </button>
        ${state.dateOpen ? DateMenu(data) : ''}
      </div>
      <div class="asof">
        <div class="label">Data as of</div>
        <strong>${esc(data.as_of_label)}</strong>
        <div class="cutoff">${esc(data.cutoff_label)}</div>
      </div>
    </div>
  </header>`;
}
function DateMenu(data) {
  const months = (data.goal_months_available || []).map((month) => `<button data-action="goal-month" data-month="${esc(month)}">${esc(month)} goal month</button>`).join('');
  return `<div class="menu" role="menu">
    <button data-action="preset" data-preset="sample">Sample window · Nov 1–15</button>
    <button data-action="preset" data-preset="this_month">This month</button>
    <button data-action="preset" data-preset="last_month">Last month</button>
    <button data-action="preset" data-preset="last_30">Last 30 days</button>
    ${data.goal_month_ambiguous ? `<div class="label" style="padding:8px 10px 0">Choose goal month</div>${months}` : ''}
    <form class="custom" data-action="custom-range">
      <input aria-label="Start date" name="start" type="date" value="${esc(data.selected_range.start)}" required>
      <input aria-label="End date" name="end" type="date" value="${esc(data.selected_range.end)}" required>
      <button class="ghost-btn" type="submit">Apply</button>
    </form>
  </div>`;
}

function StatCard(opts) {
  return `<button class="stat${opts.split ? ' spend' : ''}" data-component="StatCard" data-action="drawer" data-kind="kpi" data-id="${esc(opts.id)}" title="${esc(opts.exact || '')}">
    ${opts.body}
  </button>`;
}
function infoBtn(id) {
  return `<span class="info" aria-hidden="true">i</span>`;
}
function KpiStrip(data) {
  const leads = data.kpis.leads;
  const attained = leads.attained == null ? '—' : Math.round(leads.attained * 100) + '% attained';
  const paceClass = leads.pace_delta < -0.05 ? 'behind' : (leads.pace_delta > 0.05 ? 'ahead' : 'sub');
  const progress = leads.progress == null ? 0 : Math.max(0, Math.min(1, leads.progress)) * 100;
  const goalText = leads.goal == null ? '—' : leads.goal;
  const cards = [
    StatCard({id: 'leads', exact: leads.actual == null ? '' : String(leads.actual), body: `
      <div class="label">Leads created ${infoBtn('leads')}</div>
      <div class="value">${leads.actual == null ? '—' : leads.actual} <span class="goal">/ ${esc(goalText)}</span> <span class="goal-word">goal</span></div>
      <div class="bar" aria-hidden="true"><span style="width:${progress}%"></span></div>
      <div class="meta-row"><span class="attained">${esc(attained)}</span><span class="${paceClass}">${esc(leads.pace_label || '')}</span></div>`}),
    StatCard({id: 'cpl', exact: money(data.kpis.cpl.value, true), body: `
      <div class="label">Cost / lead (CPL) ${infoBtn('cpl')}</div>
      <div class="value">${money(data.kpis.cpl.value)}</div>
      <div class="sub">vs goal ≤ ${money(data.goals.cpl)}</div>
      <div class="${varianceClass(data.kpis.cpl)}">${esc(varianceCopy(data.kpis.cpl))}</div>`}),
    StatCard({id: 'demos', body: `
      <div class="label">Demos ${infoBtn('demos')}</div>
      <div class="value">${num(data.kpis.demos.value)}</div>
      <div class="sub">Cohort demos</div>`}),
    StatCard({id: 'demo_cost', exact: money(data.kpis.demo_cost.value, true), body: `
      <div class="label">Cost / demo ${infoBtn('demo_cost')}</div>
      <div class="value">${money(data.kpis.demo_cost.value)}</div>
      <div class="sub">vs goal ≤ ${money(data.goals.demo_cost)}</div>
      <div class="${varianceClass(data.kpis.demo_cost)}">${esc(varianceCopy(data.kpis.demo_cost))}</div>`}),
    StatCard({id: 'sold', body: `
      <div class="label">Sold deals ${infoBtn('sold')}</div>
      <div class="value">${num(data.kpis.sold.value)}</div>
      <div class="sub">Still maturing</div>`}),
    StatCard({id: 'sold_cpa', exact: money(data.kpis.sold_cpa.value, true), body: `
      <div class="label">Sold CPA ${infoBtn('sold_cpa')}</div>
      <div class="value">${money(data.kpis.sold_cpa.value)}</div>
      <div class="sub">vs goal ≤ ${money(data.goals.sold_cpa)}</div>
      <div class="${varianceClass(data.kpis.sold_cpa)}">${esc(varianceCopy(data.kpis.sold_cpa))}</div>`}),
    StatCard({id: 'spend', split: true, exact: money(data.kpis.spend.value, true), body: `
      <div class="split">
        <div><div class="label">Ad spend</div><div class="value">${money(data.kpis.spend.value)}</div><div class="sub">Cap ${esc(data.kpis.spend.cap_label)}</div></div>
        <div class="rule"></div>
        <div><div class="label">Active ads</div><div class="value">${num(data.kpis.active_ads.effective)}</div><div class="sub">${num(data.kpis.active_ads.rejected)} rejected</div></div>
      </div>`})
  ];
  return `<section class="kpis" aria-label="Key results">${cards.join('')}</section>`;
}

function chartFrame(points, yMax, pad) {
  const w = 640, h = 250;
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const useIndex = new Set(points.map((p) => p.date.slice(0, 7))).size > 1;
  const xFor = (point, index) => {
    if (useIndex) {
      const denom = Math.max(points.length - 1, 1);
      return pad.l + (index / denom) * plotW;
    }
    const day = point.day || Number(point.date.slice(8, 10));
    const days = point.days || points.reduce((max, row) => Math.max(max, row.day || Number(row.date.slice(8, 10))), 1);
    return pad.l + (day / days) * plotW;
  };
  const yFor = (value) => pad.t + (1 - (value / yMax)) * plotH;
  return {w, h, pad, plotW, plotH, xFor, yFor, useIndex};
}

function GoalProgressChart(chart) {
  if (!chart || chart.status === 'choose_goal_month') {
    return `<section class="panel chart-card" data-component="GoalProgressChart"><div class="panel-head"><h2>Cumulative leads vs. target pace</h2></div><p class="empty">Choose goal month to plot pace. The selected range crosses more than one month.</p></section>`;
  }
  const days = chart.days_in_month || 30;
  const yMax = Math.max(chart.goal || 0, ...chart.points.map((p) => p.actual || 0), 10);
  const niceMax = yMax <= 20 ? 20 : Math.ceil(yMax / 10) * 10;
  const pad = {l: 34, r: 18, t: 16, b: 28};
  const frame = chartFrame(chart.points.map((p) => ({...p, days})), niceMax, pad);
  const x = (day) => pad.l + (day / days) * frame.plotW;
  const y = frame.yFor;
  const grid = [0, niceMax / 2, niceMax].map((tick) => {
    const yy = y(tick);
    return `<line x1="${pad.l}" y1="${yy}" x2="${640 - pad.r}" y2="${yy}" stroke="#24435A" stroke-opacity="0.85"></line><text x="${pad.l - 8}" y="${yy + 4}" fill="#8FA7BF" font-size="11" text-anchor="end">${tick}</text>`;
  }).join('');
  const labels = [1, 8, 15, 22, days].filter((day, index, all) => day <= days && all.indexOf(day) === index);
  const xLabels = labels.map((day) => {
    const point = chart.points.find((row) => row.day === day);
    return `<text x="${x(day)}" y="242" fill="#8FA7BF" font-size="11" text-anchor="middle">${esc(point ? point.label : day)}</text>`;
  }).join('');
  const cutoff = chart.points.find((row) => row.date === chart.cutoff);
  const future = cutoff ? `<rect x="${x(cutoff.day)}" y="${pad.t}" width="${Math.max(0, x(days) - x(cutoff.day))}" height="${frame.plotH}" fill="#071B2D" fill-opacity="0.45"></rect>` : '';
  const pace = chart.goal == null ? '' : `<line x1="${x(0)}" y1="${y(0)}" x2="${x(days)}" y2="${y(chart.goal)}" stroke="#B5C7DC" stroke-width="2" stroke-dasharray="5 4"></line>`;
  let step = '';
  let area = '';
  const actuals = chart.points.filter((row) => row.actual != null);
  if (actuals.length) {
    let path = `M ${x(0)} ${y(0)}`;
    actuals.forEach((row) => { path += ` H ${x(row.day)} V ${y(row.actual)}`; });
    step = `<path d="${path}" fill="none" stroke="#26D9EB" stroke-width="2.5" stroke-linejoin="round"></path>`;
    const last = actuals[actuals.length - 1];
    area = `<path d="${path} V ${y(0)} H ${x(0)} Z" fill="#26D9EB" fill-opacity="0.13"></path>`;
    step += `<circle cx="${x(last.day)}" cy="${y(last.actual)}" r="4" fill="#26D9EB"></circle>`;
  }
  const halo = 'stroke="#0C253B" stroke-width="4" paint-order="stroke" stroke-linejoin="round"';
  const notes = [];
  const ann = chart.annotations || {};
  if (ann.paced && cutoff) notes.push(`<text x="${x(cutoff.day) - 10}" y="${Math.max(14, y(ann.paced.value) - 16)}" fill="#B5C7DC" font-size="11" text-anchor="end" ${halo}>${esc(ann.paced.label)} (${esc(cutoff.label)})</text>`);
  if (ann.actual && cutoff) notes.push(`<text x="${x(cutoff.day) - 10}" y="${y(ann.actual.value) + 22}" fill="#26D9EB" font-size="11" text-anchor="end" ${halo}>${esc(ann.actual.label)} (${esc(cutoff.label)})</text>`);
  if (ann.goal) notes.push(`<text x="${x(days) - 6}" y="${Math.max(14, y(ann.goal.value) + 14)}" fill="#B5C7DC" font-size="11" text-anchor="end" ${halo}>${esc(ann.goal.label)} (${esc(chart.points[chart.points.length - 1].label)})</text>`);
  const hover = chart.points.filter((row) => row.actual != null).map((row) => `<rect x="${x(row.day) - 8}" y="${pad.t}" width="16" height="${frame.plotH}" fill="transparent" data-tip="Date ${esc(row.label)} · Cumulative leads ${row.actual} · Goal pace ${row.pace == null ? 'n/a' : Number(row.pace).toFixed(1)} · ${esc(chart.summary || '')}"></rect>`).join('');
  const goalLabel = chart.goal == null ? 'Goal not configured' : 'Target pace (to ' + chart.goal + ')';
  return `<section class="panel chart-card" data-component="GoalProgressChart">
    <div class="panel-head">
      <h2>Cumulative leads vs. target pace</h2>
      <div class="legend"><span><i class="swatch"></i>Actual leads</span><span><i class="swatch dash"></i>${esc(goalLabel)}</span></div>
    </div>
    <div class="chart-wrap">
      <svg viewBox="0 0 640 250" role="img" aria-label="${esc(chart.summary || 'Lead progress')}">
        ${grid}${future}${area}${pace}${step}${xLabels}${notes.join('')}${hover}
      </svg>
    </div>
    <p class="sr-only">${esc(chart.summary || '')}</p>
  </section>`;
}

function BotStatusPanel(bot) {
  const bannerClass = bot.overall === 'incident' ? 'watch incident-banner' : (bot.overall === 'unknown' ? 'watch unknown-banner' : 'watch');
  const deliveryDot = bot.crm_delivery.status === 'ok' ? 'dot' : (bot.crm_delivery.status === 'watch' ? 'dot amber' : 'dot muted');
  const trackDot = bot.tracking === 'healthy' ? 'dot' : 'dot muted';
  return `<section class="panel" data-component="BotStatusPanel">
    <div class="panel-head"><h2>Bot status</h2><span class="sub">${bot.tracking === 'healthy' ? '<i class="dot"></i> Tracking healthy' : 'Tracking unknown'}</span></div>
    <div class="${bannerClass}" role="status">${bot.overall === 'healthy' ? '' : '▲ '}${esc(bot.label)}</div>
    <div class="check"><i class="${deliveryDot}"></i><div><strong>${esc(bot.crm_delivery.label)}</strong></div></div>
    <div class="check"><i class="${trackDot}"></i><div>${esc(bot.tracking_label)}</div></div>
    <div class="check"><i class="dot muted"></i><div>Last sync ${esc(bot.last_sync_label)}</div></div>
    <div class="next"><div class="label">Next action</div><strong>${esc(bot.next_action)}</strong><div class="sub">${esc(bot.next_action_detail || '')}</div></div>
  </section>`;
}
function RecommendationList(recs, bot) {
  const body = recs.length ? recs.map((rec, index) => `<button class="rec" data-action="drawer" data-kind="recommendation" data-id="${esc(rec.id)}">
      <span class="num">${index + 1}</span>
      <span><strong>${esc(rec.title)}</strong><p>${esc(rec.text)}</p></span>
    </button>`).join('') : `<p class="empty">${bot.overall === 'healthy' ? 'No action required' : 'Recommendations unavailable until sources are fresh.'}</p>`;
  return `<section class="panel" data-component="RecommendationList"><div class="panel-head"><h2>Bot recommendations</h2></div><div class="recs">${body}</div></section>`;
}

function FunnelStrip(funnel, rangeLabel) {
  const parts = [];
  funnel.stages.forEach((stage, index) => {
    if (index) {
      const prev = funnel.stages[index - 1];
      parts.push(`<div class="hop"><span aria-hidden="true">→</span><strong>${esc(stage.conversion_label || '—')}</strong>${esc(stage.hop_label || '')}</div>`);
    }
    parts.push(`<button class="stage" data-action="drawer" data-kind="stage" data-id="${esc(stage.id)}"><div class="label">${esc(stage.label)}</div><div class="count">${num(stage.count)}</div></button>`);
  });
  return `<section class="panel" data-component="FunnelStrip">
    <div class="funnel-head"><div><h2>${esc(funnel.title)}</h2><div class="sub">From ads to sales (${esc(rangeLabel)})</div></div>${funnel.directional ? `<span class="pill">${esc(funnel.badge)}</span>` : ''}</div>
    <div class="funnel-scroll"><div class="funnel">${parts.join('')}</div></div>
  </section>`;
}

function CostTrendChart(costs, tab) {
  const series = (costs && costs.series && costs.series[tab]) || [];
  const goal = costs && costs.goals ? costs.goals[tab] : null;
  const titles = {cpl: 'Cost trend (CPL)', demo: 'Cost trend (Demo)', sold: 'Cost trend (CPA)'};
  const names = {cpl: 'CPL', demo: 'Demo', sold: 'CPA'};
  const values = series.map((row) => row.value).filter((value) => value != null);
  let yMax = 60;
  const peak = Math.max(goal || 0, ...values, 0);
  if (peak > 40 && peak <= 60) yMax = 80;
  else if (peak > 60) {
    const step = peak > 200 ? 100 : 20;
    yMax = Math.ceil((peak * 1.15) / step) * step;
  }
  const pad = {l: 42, r: 64, t: 16, b: 28};
  const frame = chartFrame(series, yMax, pad);
  const ticks = [];
  const step = yMax <= 80 ? 20 : (yMax >= 200 ? yMax / 3 : yMax / 4);
  for (let value = 0; value <= yMax + 0.1; value += step) ticks.push(Math.round(value));
  const grid = ticks.map((tick) => {
    const yy = frame.yFor(tick);
    return `<line x1="${pad.l}" y1="${yy}" x2="${640 - pad.r}" y2="${yy}" stroke="#24435A"></line><text x="${pad.l - 6}" y="${yy + 4}" fill="#8FA7BF" font-size="11" text-anchor="end">$${tick}</text>`;
  }).join('');
  const xLabels = series.filter((row, index) => index === 0 || index === series.length - 1 || row.date.endsWith('-08') || row.date.endsWith('-15') || row.date.endsWith('-22')).map((row) => {
    const index = series.indexOf(row);
    return `<text x="${frame.xFor(row, index)}" y="242" fill="#8FA7BF" font-size="11" text-anchor="middle">${esc(row.label)}</text>`;
  }).join('');
  let path = '';
  let pen = false;
  series.forEach((row, index) => {
    if (row.value == null || row.future) { pen = false; return; }
    path += `${pen ? 'L' : 'M'} ${frame.xFor(row, index)} ${frame.yFor(row.value)} `;
    pen = true;
  });
  const known = series.filter((row) => row.value != null && !row.future);
  const last = known[known.length - 1];
  const lastIndex = last ? series.indexOf(last) : -1;
  const area = last ? `<path d="${path} L ${frame.xFor(last, lastIndex)} ${frame.yFor(0)} L ${frame.xFor(known[0], series.indexOf(known[0]))} ${frame.yFor(0)} Z" fill="#2EA8FA" fill-opacity="0.12"></path>` : '';
  const goalLine = goal == null ? '' : `<line x1="${pad.l}" y1="${frame.yFor(goal)}" x2="${640 - pad.r}" y2="${frame.yFor(goal)}" stroke="#B5C7DC" stroke-width="2" stroke-dasharray="5 4"></line><text x="${628}" y="${frame.yFor(goal) - 6}" fill="#B5C7DC" font-size="11" text-anchor="end">$${goal} goal</text>`;
  const dot = last ? `<circle cx="${frame.xFor(last, lastIndex)}" cy="${frame.yFor(last.value)}" r="4" fill="#2EA8FA"></circle><text x="${frame.xFor(last, lastIndex) - 10}" y="${Math.max(14, frame.yFor(last.value) - 16)}" fill="#2EA8FA" font-size="11" text-anchor="end" stroke="#0C253B" stroke-width="4" paint-order="stroke">${money(last.value)} (${esc(last.label)})</text>` : '';
  const hover = series.map((row, index) => `<rect x="${frame.xFor(row, index) - 8}" y="${pad.t}" width="16" height="${frame.plotH}" fill="transparent" data-tip="${esc(row.label)} · ${names[tab]} ${row.value == null ? 'N/A' : money(row.value, true)} · Spend ${row.spend == null ? '—' : money(row.spend, true)} · Outcomes ${row.outcomes == null ? '—' : row.outcomes} · Goal ${goal == null ? '—' : money(goal)}"></rect>`).join('');
  const empty = known.length ? '' : '<p class="empty">N/A — denominator is zero for this range. A zero outcome is not a $0 cost.</p>';
  const tabs = ['cpl', 'demo', 'sold'].map((key) => `<button class="tab" data-action="cost-tab" data-tab="${key}" aria-selected="${tab === key ? 'true' : 'false'}">${key === 'cpl' ? 'CPL' : key === 'demo' ? 'Demo' : 'CPA'}</button>`).join('');
  const summary = (costs.summary && costs.summary[tab]) || '';
  return `<section class="panel" data-component="CostTrendChart">
    <div class="panel-head">
      <h2>${titles[tab]}</h2>
      <div class="tabs" role="tablist">${tabs}</div>
    </div>
    <div class="legend"><span><i class="swatch blue"></i>${esc(names[tab])} (actual)</span><span><i class="swatch dash"></i>Goal (≤ ${money(goal)})</span></div>
    ${series.length ? `<div class="chart-wrap"><svg viewBox="0 0 640 250" role="img" aria-label="${esc(summary)}">${grid}${area}<path d="${path}" fill="none" stroke="#2EA8FA" stroke-width="2.5"></path>${goalLine}${dot}${xLabels}${hover}</svg></div>` : '<p class="empty">Cost trend unavailable for this source.</p>'}
    ${empty}
    <p class="foot-note">${esc(costs.label || '')}</p>
    <p class="sr-only">${esc(summary)}</p>
  </section>`;
}

function sortedAds(ads) {
  const rows = ads.filter((ad) => {
    const hay = (ad.name + ' ' + (ad.copy || '') + ' ' + (ad.campaign_name || '')).toLowerCase();
    return !state.query || hay.includes(state.query.toLowerCase());
  });
  const dir = state.sortDir === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    const key = state.sortKey;
    const av = key === 'status' ? a.effective_status : a[key === 'clicks' ? 'outbound_clicks' : key];
    const bv = key === 'status' ? b.effective_status : b[key === 'clicks' ? 'outbound_clicks' : key];
    if (av == null && bv == null) return a.name.localeCompare(b.name);
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });
  return rows;
}
function ActiveAdsTable(ads, compact) {
  const rows = sortedAds(ads);
  const headers = [
    ['name', 'Ad name', ''],
    ['status', 'Status', ''],
    ['impressions', 'Impressions', 'num'],
    ['clicks', 'Clicks', 'num'],
    ['ctr', 'CTR', 'num'],
    ['leads', 'Leads', 'num'],
    ['cpl', 'CPL', 'num']
  ];
  const head = headers.map(([key, label, cls]) => `<th class="${cls}"><button data-action="sort" data-key="${key}" aria-label="Sort by ${label}">${label}${state.sortKey === key ? (state.sortDir === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>`).join('');
  const body = rows.map((ad) => `<tr data-action="drawer" data-kind="ad" data-id="${esc(ad.id)}">
    <td><div class="ad">${thumb(ad.thumbnail)}<span><strong>${esc(ad.name)}</strong><small>${esc(ad.copy || ad.campaign_name || '')}</small></span></div></td>
    <td><span class="status"><i class="dot${ad.effective_status === 'active' ? '' : ' muted'}"></i>${esc(ad.effective_status === 'active' ? 'Active' : (ad.effective_status || 'Unknown'))}</span></td>
    <td class="num">${num(ad.impressions)}</td>
    <td class="num">${num(ad.outbound_clicks)}</td>
    <td class="num">${pct(ad.ctr, 2)}</td>
    <td class="num">${num(ad.leads)}</td>
    <td class="num">${ad.cpl == null ? 'N/A' : money(ad.cpl)}</td>
  </tr>`).join('');
  const totals = rows.reduce((sum, ad) => {
    sum.impressions += ad.impressions || 0;
    sum.clicks += ad.outbound_clicks || 0;
    sum.spend += ad.spend_cents || 0;
    sum.leads += ad.leads || 0;
    return sum;
  }, {impressions: 0, clicks: 0, spend: 0, leads: 0});
  const totalCtr = totals.impressions ? totals.clicks / totals.impressions : null;
  const totalCpl = totals.leads ? (totals.spend / totals.leads) / 100 : null;
  const foot = compact ? '' : `<tfoot><tr><td colspan="2">Total · recomputed from sums</td><td class="num">${num(totals.impressions)}</td><td class="num">${num(totals.clicks)}</td><td class="num">${pct(totalCtr, 2)}</td><td class="num">${num(totals.leads)}</td><td class="num">${totalCpl == null ? 'N/A' : money(totalCpl)}</td></tr></tfoot>`;
  return `<section class="panel" data-component="ActiveAdsTable">
    <div class="panel-head"><div><h2>Active ad performance</h2><div class="sub">${esc(state.payload.selected_range.label)}</div></div>
      ${compact ? '<button class="linkish" data-action="nav" data-view="campaigns">View all campaigns →</button>' : ''}
    </div>
    ${compact ? '' : `<div class="toolbar"><input class="search" aria-label="Filter ads" placeholder="Filter this table" value="${esc(state.query)}" data-action="filter"><span class="sub">Table filter only</span></div>`}
    <div class="table-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body || '<tr><td colspan="7">No ads in this range.</td></tr>'}</tbody>${foot}</table></div>
  </section>`;
}

function Overview(state) {
  const data = state.payload;
  return `<div class="overview">
    ${state.error ? `<p class="error">${esc(state.error)}</p>` : ''}
    ${KpiStrip(data)}
    <div class="main-row">
      ${GoalProgressChart(data.charts.leads)}
      ${BotStatusPanel(data.bot)}
      ${RecommendationList(data.recommendations, data.bot)}
    </div>
    ${FunnelStrip(data.funnel, data.selected_range.label)}
    <div class="bottom-row">
      ${CostTrendChart(data.charts.costs, state.costTab)}
      ${ActiveAdsTable(data.ads, true)}
    </div>
  </div>`;
}

function CampaignView(state) {
  return `<div class="stack"><p class="sub">Campaign list for ${esc(state.payload.selected_range.label)}. Sorting and the filter stay on this table.</p>${ActiveAdsTable(state.payload.ads, false)}</div>`;
}
function FunnelView(state) {
  const stages = state.payload.funnel.stages.map((stage) => `<button class="stat" data-action="drawer" data-kind="stage" data-id="${esc(stage.id)}"><div class="label">${esc(stage.label)}</div><div class="value">${num(stage.count)}</div><div class="sub">${esc(stage.note)}</div></button>`).join('');
  return `<div class="stack">${FunnelStrip(state.payload.funnel, state.payload.selected_range.label)}<div class="kpis">${stages}</div></div>`;
}
function TrendsView(state) {
  return `<div class="stack">${GoalProgressChart(state.payload.charts.leads)}${CostTrendChart(state.payload.charts.costs, state.costTab)}</div>`;
}
function ActivityView() {
  return `<section class="panel"><h2>Activity</h2><p class="empty">Audit log unavailable. No bot action history is connected to this screen. Opening Activity does not change ads, budgets, or spend.</p></section>`;
}
function SettingsView(data) {
  const goals = Object.entries(data.goals.leads_by_month).map(([month, goal]) => `<div><strong>${esc(month)}</strong><div class="sub">${goal} leads created. Later months do not inherit this goal.</div></div>`).join('');
  const sources = Object.entries(data.sources).map(([name, source]) => `<div><strong>${esc(name.replaceAll('_', ' '))}</strong><div class="sub">${esc(source.status)} · ${esc(source.detail || '')}</div></div>`).join('');
  return `<section class="panel"><h2>Settings</h2>
    <p class="sub">View-only. Goal edits and ad changes are not available here. Monthly spend cap: ${esc(data.goals.monthly_spend_cap_label)}.</p>
    <div class="toolbar">
      <button class="ghost-btn" data-action="mode" data-mode="demo">Demo sample</button>
      <button class="ghost-btn" data-action="mode" data-mode="live">Load live sources</button>
    </div>
    <h2>Lead goals</h2><div class="defs">${goals}<div><strong>Cost goals</strong><div class="sub">CPL ≤ ${money(data.goals.cpl)} · Demo cost ≤ ${money(data.goals.demo_cost)} · Sold CPA ≤ ${money(data.goals.sold_cpa)}</div></div></div>
    <h2>Sources</h2><div class="defs">${sources}</div>
    <p class="sub">Related reports: <a href="${esc(data.links.inbound_cac)}">Inbound CAC</a> · <a href="${esc(data.links.website_funnel)}">Website funnel</a> · <a href="${esc(data.links.website_traffic)}">Website traffic</a></p>
  </section>`;
}

function DetailDrawer(state) {
  if (!state.drawer) return '';
  const data = state.payload;
  const drawer = state.drawer;
  let title = 'Details';
  let body = '';
  if (drawer.kind === 'ad') {
    const ad = data.ads.find((row) => row.id === drawer.id);
    if (!ad) return '';
    title = ad.name;
    body = `<p>${esc(ad.copy || '')}</p><dl>
      <dt>Status</dt><dd>${esc(ad.effective_status)}</dd>
      <dt>Spend</dt><dd>${money(ad.spend, true)}</dd>
      <dt>Impressions</dt><dd>${num(ad.impressions)}</dd>
      <dt>Outbound clicks</dt><dd>${num(ad.outbound_clicks)}</dd>
      <dt>CTR</dt><dd>${pct(ad.ctr, 2)} = clicks / impressions</dd>
      <dt>Leads</dt><dd>${num(ad.leads)}</dd>
      <dt>CPL</dt><dd>${ad.cpl == null ? 'N/A' : money(ad.cpl, true)} = spend / leads</dd>
      <dt>Campaign</dt><dd>${esc(ad.campaign_id || '—')}</dd>
      <dt>Ad set</dt><dd>${esc(ad.adset_id || '—')}</dd>
      <dt>Landing</dt><dd>${esc(ad.landing_url || '—')}</dd>
      <dt>Attribution</dt><dd>${ad.leads ? 'Leads linked to this ad' : 'No attributed leads. CPL is N/A, not a guessed share of spend.'}</dd>
    </dl>`;
  } else if (drawer.kind === 'recommendation') {
    const rec = data.recommendations.find((row) => row.id === drawer.id);
    if (!rec) return '';
    title = rec.title;
    body = `<p>${esc(rec.text)}</p><dl>
      <dt>Evidence</dt><dd>${esc(rec.evidence)}</dd>
      <dt>Proposed action</dt><dd>${esc(rec.proposed_action)}</dd>
      <dt>Status</dt><dd>${esc(rec.state)}</dd>
      <dt>Confidence</dt><dd>${esc(rec.confidence)}</dd>
      <dt>Owner</dt><dd>${esc(rec.owner)}</dd>
      <dt>Next review</dt><dd>${esc(rec.next_review)}</dd>
      <dt>Source time</dt><dd>${esc(rec.source_timestamp)}</dd>
      <dt>Entity</dt><dd>${esc(rec.entity.type)} ${esc(rec.entity.id)}</dd>
      <dt>Window</dt><dd>${esc(rec.evidence_window.start)} → ${esc(rec.evidence_window.end)}</dd>
    </dl><p class="sub">This drawer cannot apply the action.</p>`;
  } else if (drawer.kind === 'stage') {
    const stage = data.funnel.stages.find((row) => row.id === drawer.id);
    if (!stage) return '';
    title = stage.label;
    body = `<p>${esc(stage.note)}</p><dl>
      <dt>Count</dt><dd>${num(stage.count)}</dd>
      <dt>From previous</dt><dd>${esc(stage.conversion_label || '—')} ${esc(stage.hop_label || '')}</dd>
      <dt>Source</dt><dd>${esc(stage.source)}</dd>
      <dt>Join</dt><dd>${stage.directional ? 'Directional. Not a verified person-level path.' : 'Same-source ratio.'}</dd>
      <dt>Window</dt><dd>${esc(data.selected_range.label)}</dd>
      <dt>As of</dt><dd>${esc(data.as_of_label)}</dd>
    </dl>`;
  } else if (drawer.kind === 'kpi') {
    const copy = data.definitions[drawer.id] || data.definitions.lead_created;
    const map = {
      leads: data.definitions.lead_created,
      cpl: data.definitions.cpl,
      demos: data.definitions.demo,
      demo_cost: data.definitions.demo_cost,
      sold: data.definitions.sold,
      sold_cpa: data.definitions.sold_cpa,
      spend: data.definitions.spend_cap
    };
    title = drawer.id.replaceAll('_', ' ');
    const rows = drawer.id === 'leads' ? data.lead_rows.map((lead) => `<li>${esc(lead.acquired_on)} · ${esc(lead.ad_id || 'unlinked')} · ${lead.demo ? 'demo' : 'no demo'} · ${lead.sold ? 'sold' : 'open'}</li>`).join('') : '';
    body = `<p>${esc(map[drawer.id] || copy)}</p>${rows ? `<ul>${rows}</ul>` : ''}<p class="sub">${esc(data.definitions.read_only)}</p>`;
  }
  return `<div class="drawer-back" data-component="DetailDrawer"><aside class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}"><button class="icon-btn" data-action="close-drawer">Close</button><h2>${esc(title)}</h2>${body}</aside></div>`;
}

function DashboardShell(state) {
  const view = {
    overview: Overview(state),
    campaigns: CampaignView(state),
    funnel: FunnelView(state),
    trends: TrendsView(state),
    activity: ActivityView(),
    settings: SettingsView(state.payload)
  }[state.view] || Overview(state);
  return `<div class="app${state.navOpen ? ' nav-open' : ''}" data-component="DashboardShell">
    <div class="scrim" data-action="menu"></div>
    ${Sidebar(state)}
    <main class="content" id="main">${Header(state)}${view}</main>
    ${DetailDrawer(state)}
  </div>`;
}

function render() {
  document.getElementById('app').setAttribute('aria-busy', state.loading ? 'true' : 'false');
  document.getElementById('app').innerHTML = DashboardShell(state);
}
async function reload(updates) {
  const data = state.payload;
  const params = new URLSearchParams();
  params.set('mode', updates.mode || data.mode || 'demo');
  if (updates.preset) params.set('preset', updates.preset);
  else if (updates.start && updates.end) {
    params.set('start', updates.start);
    params.set('end', updates.end);
  } else if (!updates.preset) {
    params.set('start', data.selected_range.start);
    params.set('end', data.selected_range.end);
  }
  if (updates.goal_month) params.set('goal_month', updates.goal_month);
  else if (data.goal_month && !updates.preset && !updates.start) params.set('goal_month', data.goal_month);
  state.loading = true;
  state.error = '';
  render();
  try {
    const response = await fetch(data.links.json + '?' + params.toString(), {headers: {'Accept': 'application/json'}});
    if (!response.ok) throw new Error('Could not refresh the range.');
    state.payload = await response.json();
    state.dateOpen = false;
  } catch (error) {
    state.error = error.message || 'Refresh failed.';
  } finally {
    state.loading = false;
    render();
  }
}

document.getElementById('app').addEventListener('click', (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) {
    if (state.dateOpen && !event.target.closest('.date-wrap')) {
      state.dateOpen = false;
      render();
    }
    return;
  }
  const action = target.dataset.action;
  if (action === 'nav') {
    state.view = target.dataset.view;
    state.navOpen = false;
    state.drawer = null;
    render();
  } else if (action === 'menu') {
    state.navOpen = !state.navOpen;
    render();
  } else if (action === 'date-toggle') {
    state.dateOpen = !state.dateOpen;
    render();
  } else if (action === 'preset') {
    reload({preset: target.dataset.preset});
  } else if (action === 'goal-month') {
    reload({goal_month: target.dataset.month, start: state.payload.selected_range.start, end: state.payload.selected_range.end});
  } else if (action === 'cost-tab') {
    state.costTab = target.dataset.tab;
    render();
  } else if (action === 'sort') {
    if (state.sortKey === target.dataset.key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    else { state.sortKey = target.dataset.key; state.sortDir = target.dataset.key === 'name' || target.dataset.key === 'status' ? 'asc' : 'desc'; }
    render();
  } else if (action === 'drawer') {
    state.drawer = {kind: target.dataset.kind, id: target.dataset.id};
    render();
    const close = document.querySelector('[data-action="close-drawer"]');
    if (close) close.focus();
  } else if (action === 'close-drawer') {
    state.drawer = null;
    render();
  } else if (action === 'mode') {
    reload({mode: target.dataset.mode, preset: target.dataset.mode === 'demo' ? 'sample' : 'this_month'});
  }
});
document.getElementById('app').addEventListener('submit', (event) => {
  const form = event.target.closest('[data-action="custom-range"]');
  if (!form) return;
  event.preventDefault();
  const start = form.elements.start.value;
  const end = form.elements.end.value;
  reload({start, end, preset: ''});
});
document.getElementById('app').addEventListener('input', (event) => {
  if (event.target.dataset.action === 'filter') {
    state.query = event.target.value;
    const panel = event.target.closest('[data-component="ActiveAdsTable"]');
    const cursor = event.target.selectionStart;
    render();
    const next = document.querySelector('[data-action="filter"]');
    if (next) { next.focus(); next.setSelectionRange(cursor, cursor); }
  }
});
document.getElementById('app').addEventListener('mousemove', (event) => {
  const tip = document.getElementById('tip');
  const host = event.target.closest('[data-tip]');
  if (!host) { tip.hidden = true; return; }
  tip.hidden = false;
  tip.textContent = host.getAttribute('data-tip');
  tip.style.left = Math.min(window.innerWidth - 250, event.clientX + 12) + 'px';
  tip.style.top = (event.clientY + 14) + 'px';
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    state.drawer = null;
    state.dateOpen = false;
    state.navOpen = false;
    render();
  }
});
render();
</script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = metric.compute_payload(_query_params(self.path))
            body = render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = ("ERROR: " + str(exc)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        body = b'{"error":"Growth Command Center is view-only.","read_only":true}'
        self.send_response(405)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()
