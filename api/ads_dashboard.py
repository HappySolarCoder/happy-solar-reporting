# -*- coding: utf-8 -*-

"""Ads Dashboard page. Read-only.

The numbers come from api/metrics/ads_dashboard.py. This page does not
change ads, budgets, or campaigns.
"""

from __future__ import annotations

import html
import importlib.util
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parent
METRICS_DIR = API_DIR / "metrics"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav  # noqa: E402

MONTHS = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
PIE_COLORS = (
    "#26d9eb",
    "#2ea8fa",
    "#11c99b",
    "#ffbe45",
    "#c9a0ff",
    "#ff8292",
    "#7fd0c4",
    "#f4f7fb",
)
KPI_ORDER = (
    ("spend", "Spend"),
    ("inbound_leads", "Inbound leads"),
    ("cost_per_lead", "Cost/lead"),
    ("opps", "Opps"),
    ("cost_per_opp", "Cost/opp"),
    ("demos", "Demos"),
    ("cost_per_demo", "Cost/demo"),
    ("sales", "Sales"),
    ("cost_per_sale", "Cost/sale"),
)

PAGE_CSS = """
.oc-page .kpis.ads-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.oc-page .ads-detail { color: #9ebbd0; font-size: 11px; margin-top: 8px; }
.oc-page .pie-wrap { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
.oc-page .pie {
  width: 168px; height: 168px; border-radius: 50%; flex: none; position: relative;
}
.oc-page .pie:after {
  content: ""; position: absolute; inset: 46px; border-radius: 50%; background: #0d293f;
}
.oc-page .pie-legend { list-style: none; margin: 0; padding: 0; min-width: 220px; flex: 1; }
.oc-page .pie-legend li {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; border-bottom: 1px solid #1c3a4f; color: #d5e4ef; font-size: 12px;
}
.oc-page .pie-legend li:last-child { border-bottom: 0; }
.oc-page .swatch { width: 10px; height: 10px; border-radius: 2px; flex: none; }
.oc-page .pie-legend b { margin-left: auto; font-variant-numeric: tabular-nums; }
.oc-page .ads-chart { width: 100%; height: auto; display: block; }
.oc-page .ads-chart text { fill: #8eabc0; font: 10px 'DM Sans', sans-serif; }
.oc-page .rate-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
.oc-page .rate-grid article {
  background: #0a2235; border: 1px solid #2b4c63; border-radius: 8px; padding: 14px 14px 12px;
}
.oc-page .rate-grid span { display: block; color: #8eabc0; font-size: 10px; letter-spacing: .4px; text-transform: uppercase; }
.oc-page .rate-grid strong { display: block; margin-top: 8px; font: 700 22px Manrope, sans-serif; letter-spacing: -.4px; }
.oc-page .rate-grid small { display: block; margin-top: 6px; color: #8eabc0; font-size: 10px; }
@media (max-width: 800px) {
  .oc-page .kpis.ads-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .oc-page .rate-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 520px) {
  .oc-page .kpis.ads-kpis, .oc-page .rate-grid { grid-template-columns: 1fr; }
}
"""


def _metric():
    name = "hs_ads_dashboard_page_metric"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "ads_dashboard.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load ads dashboard metric")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _pretty(ymd: str) -> str:
    try:
        year, month, day = (int(part) for part in str(ymd).split("-"))
        return f"{MONTHS[month]} {day}, {year}"
    except Exception:
        return str(ymd or "")


def _pie_style(stages: list[dict]) -> str | None:
    total = sum(int(stage.get("count") or 0) for stage in stages)
    if total <= 0:
        return None
    stops = []
    cursor = 0.0
    for index, stage in enumerate(stages):
        share = int(stage.get("count") or 0) / total * 100
        color = PIE_COLORS[index % len(PIE_COLORS)]
        end = cursor + share
        stops.append(f"{color} {cursor:.4f}% {end:.4f}%")
        cursor = end
    return "conic-gradient(" + ", ".join(stops) + ")"


def _pie_html(stages: list[dict]) -> str:
    style = _pie_style(stages)
    if not style:
        return (
            '<div class="blank-chart"><b>No inbound leads in this window.</b>'
            "<p>The stage chart stays empty until an inbound lead is created.</p></div>"
        )
    total = sum(int(stage.get("count") or 0) for stage in stages)
    items = []
    for index, stage in enumerate(stages):
        count = int(stage.get("count") or 0)
        share = f"{(count / total * 100):.1f}%" if total else ""
        color = PIE_COLORS[index % len(PIE_COLORS)]
        items.append(
            "<li><i class=\"swatch\" style=\"background:"
            + color
            + "\"></i><span>"
            + _esc(stage.get("stage"))
            + "</span><b>"
            + _esc(count)
            + " · "
            + share
            + "</b></li>"
        )
    return (
        '<div class="pie-wrap"><div class="pie" style="background:'
        + _esc(style)
        + '" role="img" aria-label="Inbound lead stages"></div><ul class="pie-legend">'
        + "".join(items)
        + "</ul></div>"
    )


def _line_chart(series: list[dict] | None) -> str:
    if not series:
        return (
            '<div class="blank-chart"><b>Paid sessions are unavailable.</b>'
            "<p>A missing read stays blank. It is not drawn as zero.</p></div>"
        )
    values = []
    for point in series:
        raw = point.get("value")
        if raw is None:
            values.append(None)
        else:
            values.append(float(raw))
    if not any(value is not None for value in values):
        return (
            '<div class="blank-chart"><b>Paid sessions are unavailable.</b>'
            "<p>A missing read stays blank. It is not drawn as zero.</p></div>"
        )
    width, height = 720, 240
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 32
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b
    peak = max(value for value in values if value is not None)
    peak = peak if peak > 0 else 1
    count = max(len(values) - 1, 1)

    def xy(index: int, value: float) -> tuple[float, float]:
        x = pad_l + (inner_w * index / count)
        y = pad_t + inner_h - (inner_h * value / peak)
        return x, y

    segments: list[str] = []
    current: list[str] = []
    for index, value in enumerate(values):
        if value is None:
            if len(current) >= 2:
                segments.append(" ".join(current))
            current = []
            continue
        x, y = xy(index, value)
        current.append(f"{x:.1f},{y:.1f}")
    if len(current) >= 2:
        segments.append(" ".join(current))
    elif len(current) == 1:
        x, y = (float(part) for part in current[0].split(","))
        segments.append(f"{x - 2:.1f},{y:.1f} {x + 2:.1f},{y:.1f}")
    lines = "".join(f'<polyline fill="none" stroke="#26d9eb" stroke-width="2.4" points="{seg}"/>' for seg in segments)
    dots = []
    for index, value in enumerate(values):
        if value is None:
            continue
        x, y = xy(index, value)
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#26d9eb"/>')
    labels = []
    last = len(series) - 1
    for index in {0, last // 2, last}:
        point = series[index]
        x, _y = xy(index, 0)
        labels.append(
            f'<text x="{x:.1f}" y="{height - 10}" text-anchor="middle">{_esc(str(point.get("date") or "")[5:])}</text>'
        )
    grid = []
    for step in range(4):
        y = pad_t + inner_h * step / 3
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="#1e3e53"/>')
        tick = peak * (1 - step / 3)
        grid.append(f'<text x="4" y="{y + 3:.1f}">{int(round(tick))}</text>')
    return (
        f'<svg class="ads-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Daily paid sessions">'
        + "".join(grid)
        + lines
        + "".join(dots)
        + "".join(labels)
        + "</svg>"
    )


def _kpi_cards(payload: dict) -> str:
    kpis = payload.get("kpis") or {}
    cards = []
    for key, label in KPI_ORDER:
        kpi = kpis.get(key) or {}
        tone = kpi.get("tone")
        tone_class = " positive" if tone == "good" else " negative" if tone == "bad" else ""
        detail = f'<div class="ads-detail">{_esc(kpi.get("detail"))}</div>' if kpi.get("detail") else ""
        goal = kpi.get("goal_display")
        goal_line = "no goal" if goal == "no goal" else f"Goal {goal}"
        cards.append(
            "<article class=\"kpi\">"
            f'<div class="label"><span>{_esc(label)}</span></div>'
            f'<div class="number{tone_class}">{_esc(kpi.get("display"))}</div>'
            f'<div class="sub">{_esc(goal_line)}</div>'
            f"{detail}</article>"
        )
    return "".join(cards)


def _rate_card(label: str, display: str, detail: str = "") -> str:
    extra = f"<small>{_esc(detail)}</small>" if detail else ""
    return f"<article><span>{_esc(label)}</span><strong>{_esc(display)}</strong>{extra}</article>"


def _rates_html(payload: dict) -> str:
    rates = payload.get("rates") or {}

    def show(key: str) -> str:
        return str((rates.get(key) or {}).get("display") or "\u2014")

    per_session = show("leads_per_session")
    per_click = show("leads_per_click")
    cards = [
        _rate_card("Sessions", show("sessions"), "GA4 Paid Social + Paid Search"),
        _rate_card("Clicks", show("clicks"), "Meta outbound clicks"),
        _rate_card("Conv. rate", per_session, f"leads / click {per_click}"),
        _rate_card("Est. CPC", show("cpc"), "Spend / clicks"),
        _rate_card("CTR", show("ctr"), "Clicks / impressions"),
        _rate_card("CPM", show("cpm"), "Spend / impressions × 1000"),
    ]
    return '<div class="rate-grid">' + "".join(cards) + "</div>"


def _notices(payload: dict) -> str:
    blocks = []
    for note in payload.get("errors") or []:
        blocks.append(f'<div class="notice warn"><span class="symbol">!</span><div>{_esc(note)}</div></div>')
    for note in payload.get("notes") or []:
        blocks.append(f'<div class="notice"><span class="symbol">i</span><div>{_esc(note)}</div></div>')
    return "".join(blocks)


def render_html(payload: dict) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("ads_dashboard")
    start = str(payload.get("start") or "")
    end = str(payload.get("end") or "")
    period = f"{_pretty(start)} – {_pretty(end)}"
    quick = (payload.get("kpis") or {}).get("inbound_leads") or {}
    quick_line = quick.get("detail") or "of which FB Quick Form: —"
    included = "counted in inbound leads" if payload.get("include_fb_quick_form") else "left out of inbound leads"
    return f"""<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Ads Dashboard</title>
  <style>{nav_css}
{PAGE_CSS}</style>
</head>
<body class="oc-root">
  {nav_html}
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>Ads Dashboard</strong></div>
      <div class="top-right"><span class="badge cyan">Read only</span></div>
    </header>
    <main>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Inbound</div>
          <h1>Ads Dashboard</h1>
          <p class="subtitle">America/Phoenix days. The window runs from midnight at the start through midnight after the last day. {_esc(quick_line)}. FB Quick Form contacts are {included}.</p>
        </div>
        <div class="period"><span>{_esc(period)}</span></div>
      </div>
      <form class="global-filterbar" method="get" action="/api/ads_dashboard">
        <div class="filter-controls">
          <label>Start<input type="date" name="start" value="{_esc(start)}" required></label>
          <label>End<input type="date" name="end" value="{_esc(end)}" required></label>
          <button class="primary" type="submit">Apply</button>
        </div>
        <div class="filter-chips"><span>Default is the last 7 full days.</span></div>
      </form>
      {_notices(payload)}
      <section class="kpis ads-kpis" aria-label="Ads scorecard">
        {_kpi_cards(payload)}
      </section>
      <div class="grid equal">
        <section class="panel">
          <div class="panel-head"><div><h2>Lead stages</h2><div class="meta">Current Inbound/Lead Locker stage of the ad-lead opportunities.</div></div></div>
          <div class="panel-body">{_pie_html(payload.get("stages") or [])}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><div><h2>Paid sessions</h2><div class="meta">GA4 stream G-V02RZFR4SZ. Paid Social and Paid Search, by Phoenix day.</div></div></div>
          <div class="panel-body">{_line_chart(payload.get("sessions_daily"))}</div>
        </section>
      </div>
      <section class="panel">
        <div class="panel-head"><div><h2>Traffic and cost</h2><div class="meta">Sessions, clicks, conversion, estimated CPC, CTR, and CPM for this window.</div></div></div>
        <div class="panel-body">{_rates_html(payload)}</div>
      </section>
      <p class="source-note"><span>Read only. Meta account insights and GA4 are not changed from this page. A missing source stays as — and a zero denominator stays N/A.</span></p>
    </main>
  </div>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        metric = _metric()
        try:
            qs = parse_qs(urlparse(self.path).query)
            payload = metric.compute_from_query(qs)
            status = 200
            cache = "public, s-maxage=600, stale-while-revalidate=1800"
        except ValueError as exc:
            payload = metric.unavailable_payload(str(exc))
            status = 400
            cache = "no-store"
        except Exception as exc:
            metric._log_read_error(exc)
            payload = metric.unavailable_payload("Ads Dashboard could not be read.")
            status = 200
            cache = "no-store"
        body = render_html(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)
