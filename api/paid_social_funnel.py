# -*- coding: utf-8 -*-

"""Growth command center.

Dark overview for paid acquisition. The default screen is the sample
fixture. Live mode reads the paid-social adapter and does not invent
missing sources. Viewing this page does not change ads or spend.
"""

from __future__ import annotations

import html
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

API_DIR = Path(__file__).resolve().parent
METRICS_DIR = API_DIR / "metrics"
for path in (str(API_DIR), str(METRICS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from growth_command import (  # noqa: E402
    CPL_TARGET,
    DEMO_COST_TARGET,
    LEAD_GOALS,
    SOLD_CPA_TARGET,
    demo_model,
    live_model,
    unavailable_model,
)


def render_html(start: str | None = None, end: str | None = None, model: dict | None = None) -> str:
    if model is None:
        query = {}
        if start and end:
            query = {"start": [start], "end": [end]}
        model = demo_model(query)
    return _document(model)


def model_for_query(qs: dict, live_loader=None) -> dict:
    source = " ".join(str((qs.get("source") or ["demo"])[0] or "").split()) or "demo"
    if source == "live":
        try:
            loader = live_loader or _load_live
            return live_model(loader(qs), qs)
        except Exception:
            return unavailable_model(
                "Live sources could not be read. Sample numbers are not shown."
            )
    return demo_model(qs)


def _load_live(qs: dict) -> dict:
    import importlib.util
    from datetime import datetime
    from zoneinfo import ZoneInfo

    name = "hs_growth_paid_social_metric"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "paid_social_funnel.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("missing metric")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    now = datetime.now(ZoneInfo("America/New_York"))
    start, end = module.parse_range(qs, now)
    return module.compute_paid_social_funnel(module.cac.get_db(), start=start, end=end, now=now)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            body = render_html(model=model_for_query(qs)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            body = b"Growth command center could not render."
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)


def _href(model: dict, **extra: str) -> str:
    params = {"source": "demo" if model.get("is_demo") else "live"}
    params.update({key: value for key, value in extra.items() if value})
    return "/api/paid_social_funnel?" + urlencode(params)


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _document(model: dict) -> str:
    badge = (
        f'<span class="badge">{_esc(model["badge"])}</span>'
        if model.get("badge")
        else '<span class="badge badge-live">Live · not validated</span>'
    )
    banner = ""
    if model.get("missing_days"):
        banner = (
            '<p class="banner">Some days in this range are outside the sample fixture and stay blank. '
            "They are not filled with zeros.</p>"
        )
    if model.get("read_error"):
        banner += f'<p class="banner">{_esc(model["read_error"])}</p>'
    if not model.get("is_demo") and model.get("spend_gap"):
        gap = model["spend_gap"]
        banner += (
            '<p class="banner">Unmatched Meta spend. Account insights '
            f'{_esc(gap.get("account_insights_total"))} and daily rows '
            f'{_esc(gap.get("daily_rows_sum"))} differ. Neither figure is tied to a lead or an opp. '
            "This page does not pick one.</p>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Growth command center</title>
  <style>
    {CSS}
  </style>
</head>
<body>
  <div class="app">
    <input class="sr-input" type="radio" name="screen" id="screen-overview" checked />
    <input class="sr-input" type="radio" name="screen" id="screen-campaigns" />
    <input class="sr-input" type="radio" name="screen" id="screen-funnel" />
    <input class="sr-input" type="radio" name="screen" id="screen-trends" />
    <input class="sr-input" type="radio" name="screen" id="screen-activity" />
    <input class="sr-input" type="radio" name="screen" id="screen-settings" />
    <input class="sr-input" type="checkbox" id="nav-toggle" />
    <label class="scrim" for="nav-toggle" aria-label="Close menu"></label>
    <aside class="sidebar">
      <div class="wordmark">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="#FFBE45"/><g stroke="#FFBE45" stroke-width="1.6" stroke-linecap="round"><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6.2 6.2l1.5 1.5M16.3 16.3l1.5 1.5M17.8 6.2l-1.5 1.5M7.7 16.3l-1.5 1.5"/></g></svg>
        <span class="wordmark-text">Happy Solar</span>
      </div>
      <nav class="sidenav" aria-label="Growth">
        {_nav("screen-overview", "Overview", _icon_grid())}
        {_nav("screen-campaigns", "Campaigns", _icon_ads())}
        {_nav("screen-funnel", "Funnel", _icon_funnel())}
        {_nav("screen-trends", "Trends", _icon_trend())}
        {_nav("screen-activity", "Activity", _icon_pulse())}
        {_nav("screen-settings", "Settings", _icon_gear())}
      </nav>
    </aside>
    <div class="content">
      <section class="panel panel-overview">
        {_header(model, badge)}
        {banner}
        {_kpis(model)}
        <div class="main-row">
          {_lead_panel(model)}
          {_bot_panel(model)}
          {_rec_panel(model)}
        </div>
        {_funnel(model)}
        <div class="bottom-row">
          {_cost_panel(model, "overview")}
          {_ads_panel(model, compact=True)}
        </div>
      </section>
      <section class="panel panel-campaigns">
        {_header(model, badge)}
        <div class="section-head"><h2>Campaigns</h2><label class="text-btn" for="screen-overview">Back to overview</label></div>
        <p class="fine">Account-level totals are not split into guessed ads. This list is the sample ad table when the fixture range is selected.</p>
        {_ads_panel(model, compact=False)}
      </section>
      <section class="panel panel-funnel">
        {_header(model, badge)}
        <div class="section-head"><h2>Funnel</h2><label class="text-btn" for="screen-overview">Back to overview</label></div>
        {_funnel(model)}
        {_stage_notes(model)}
      </section>
      <section class="panel panel-trends">
        {_header(model, badge)}
        <div class="section-head"><h2>Trends</h2><label class="text-btn" for="screen-overview">Back to overview</label></div>
        {_lead_panel(model)}
        {_cost_panel(model, "trends")}
      </section>
      <section class="panel panel-activity">
        {_header(model, badge)}
        {_activity(model)}
      </section>
      <section class="panel panel-settings">
        {_header(model, badge)}
        {_settings(model)}
      </section>
    </div>
  </div>
  <script>
    document.querySelectorAll("[data-sort]").forEach(function(button) {{
      button.addEventListener("click", function() {{
        var table = button.closest("[data-ad-table]");
        if (!table) return;
        var key = button.getAttribute("data-sort");
        var asc = table.getAttribute("data-sort-key") === key && table.getAttribute("data-sort-dir") !== "asc";
        table.setAttribute("data-sort-key", key);
        table.setAttribute("data-sort-dir", asc ? "asc" : "desc");
        var rows = Array.prototype.slice.call(table.querySelectorAll("[data-ad-row]"));
        rows.sort(function(a, b) {{
          var av = a.getAttribute("data-" + key) || "";
          var bv = b.getAttribute("data-" + key) || "";
          var an = Number(av);
          var bn = Number(bv);
          var cmp = av !== "" && bv !== "" && !Number.isNaN(an) && !Number.isNaN(bn) ? an - bn : av.localeCompare(bv);
          return asc ? cmp : -cmp;
        }});
        rows.forEach(function(row) {{ table.appendChild(row); }});
      }});
    }});
  </script>
</body>
</html>
"""


def _nav(screen_id: str, label: str, icon: str) -> str:
    return (
        f'<label class="nav-link" for="{screen_id}">'
        f'{icon}<span class="nav-label">{_esc(label)}</span></label>'
    )


def _header(model: dict, badge: str) -> str:
    source = "demo" if model.get("is_demo") else "live"
    hidden_source = f'<input type="hidden" name="source" value="{source}" />'
    return f"""
    <header class="header">
      <div>
        <div class="title-row">
          <h1>{_esc(model["title"])}</h1>
          {badge}
        </div>
        <p class="subtitle">{_esc(model["subtitle"])}</p>
        <p class="cutoff">{_esc(model["as_of_label"])}</p>
      </div>
      <div class="header-tools">
        <label class="menu-btn" for="nav-toggle">Menu</label>
        <details class="date-menu">
          <summary>{_esc(model["range_label"])}</summary>
          <div class="date-panel">
            <a href="{_esc(_href(model, preset="this-month"))}">This month</a>
            <a href="{_esc(_href(model, preset="last-month"))}">Last month</a>
            <a href="{_esc(_href(model, preset="last-30"))}">Last 30 days</a>
            <form method="get" action="/api/paid_social_funnel">
              {hidden_source}
              <input type="hidden" name="preset" value="custom" />
              <label>Start <input type="date" name="start" value="{_esc(model["range_start"])}" /></label>
              <label>End <input type="date" name="end" value="{_esc(model["range_end"])}" /></label>
              <button type="submit">Apply custom range</button>
            </form>
            <p class="fine">Goal month: {_esc(model["goal_month_label"])}. Pace uses completed days.</p>
          </div>
        </details>
        <a class="mode-link" href="{_esc(_href(model, source="live" if model.get("is_demo") else "demo"))}">{'Live data' if model.get('is_demo') else 'Sample fixture'}</a>
      </div>
    </header>
    """


def _kpis(model: dict) -> str:
    kpis = model["kpis"]
    leads = kpis["leads"]
    cards = [
        _kpi("Leads created", leads["text"], f'{leads["percent_label"]} · {leads["pace"]}', leads["tone"], bar=leads["bar"], extra="kpi-leads"),
        _kpi("Cost per lead", kpis["cpl"]["display"], kpis["cpl"]["note"], kpis["cpl"]["tone"], title=f'Exact {kpis["cpl"]["exact"]} · target ${CPL_TARGET}'),
        _kpi("Demos", kpis["demos"]["display"], kpis["demos"]["note"], "neutral"),
        _kpi("Cost per demo", kpis["demo_cost"]["display"], kpis["demo_cost"]["note"], kpis["demo_cost"]["tone"], title=f'Exact {kpis["demo_cost"]["exact"]} · target ${DEMO_COST_TARGET}'),
        _kpi("Sold", kpis["sold"]["display"], kpis["sold"]["note"], "neutral"),
        _kpi("Sold CPA", kpis["cpa"]["display"], kpis["cpa"]["note"], kpis["cpa"]["tone"], title=f'Exact {kpis["cpa"]["exact"]} · target ${SOLD_CPA_TARGET}'),
        _kpi(
            "Spend",
            kpis["spend"]["display"],
            kpis["spend"]["active_label"],
            kpis["spend"]["tone"],
            extra="kpi-spend",
            title=(
                f'Effective active {kpis["spend"]["active"]}. Delivering {kpis["spend"]["delivering"]}. '
                f'Rejected {kpis["spend"]["rejected"]}. An ad with zero spend can still be active. '
                f'Monthly spend cap: {kpis["spend"]["cap_label"]}.'
                if kpis["spend"]["active"] is not None
                else f'Active ads are unavailable. Monthly spend cap: {kpis["spend"]["cap_label"]}.'
            ),
        ),
    ]
    return '<section class="kpis" aria-label="Goals">' + "".join(cards) + "</section>"


def _kpi(label, value, note, tone, bar=None, extra="", title="") -> str:
    bar_html = ""
    if bar is not None:
        width = max(0, min(float(bar), 100))
        bar_html = f'<span class="bar" aria-hidden="true"><span style="width:{width:.4f}%"></span></span>'
    tip = f' title="{_esc(title)}"' if title else ""
    return (
        f'<article class="kpi tone-{_esc(tone)} {extra}"{tip}>'
        f'<p class="kpi-label">{_esc(label)}</p>'
        f'<p class="kpi-value num">{_esc(value)}</p>'
        f"{bar_html}"
        f'<p class="kpi-note">{_esc(note)}</p>'
        "</article>"
    )


def _lead_panel(model: dict) -> str:
    chart = model["lead_chart"]
    svg = chart.get("svg") or '<p class="empty">Choose goal month</p>'
    return f"""
    <section class="card lead-panel">
      <div class="section-head">
        <h2>Lead progress</h2>
        <p class="legend"><span class="swatch actual"></span> {_esc(chart.get("actual_label") or "Actual")} <span class="swatch guide"></span> {_esc(chart.get("pace_label") or "Pace")}</p>
      </div>
      <p class="sr-only">{_esc(chart.get("summary"))}</p>
      <div class="chart-frame">{svg}</div>
      <p class="fine">{_esc(chart.get("summary"))}</p>
    </section>
    """


def _bot_panel(model: dict) -> str:
    bot = model["bot"]
    rows = []
    for row in bot["rows"]:
        detail = f'<span class="fine">{_esc(row.get("detail"))}</span>' if row.get("detail") else ""
        rows.append(
            f'<li><span>{_esc(row["label"])}</span>'
            f'<strong class="tone-{_esc(row["tone"])}">{_esc(row["value"])}</strong>{detail}</li>'
        )
    return f"""
    <section class="card bot-panel">
      <div class="section-head"><h2>Bot status</h2><span class="status-pill tone-{_esc(bot["tone"])}">{_esc(bot["status"])}</span></div>
      <ul class="status-list">{''.join(rows)}</ul>
      <p class="fine">Healthy tracking does not make an expensive stretch a healthy result. This screen does not change ads or spend.</p>
    </section>
    """


def _rec_panel(model: dict) -> str:
    items = model["recommendations"]
    if not items:
        if model.get("missing_days"):
            empty = "No recommendation is calculated where the sample does not cover the range."
        elif model["bot"]["status"] == "UNKNOWN":
            empty = "No recommendation until the missing sources are available."
        else:
            empty = "No action required"
        body = f'<p class="empty">{_esc(empty)}</p>'
    else:
        blocks = []
        for item in items:
            ids = ", ".join(item.get("entity_ids") or []) or "none"
            blocks.append(
                f'''<details class="rec">
                  <summary><span>{_esc(item["title"])}</span><em>{_esc(item["status"])}</em></summary>
                  <p>{_esc(item["evidence"])}</p>
                  <p>{_esc(item["action"])}</p>
                  <dl>
                    <div><dt>Entity IDs</dt><dd>{_esc(ids)}</dd></div>
                    <div><dt>Source time</dt><dd>{_esc(item["source_timestamp"])}</dd></div>
                    <div><dt>Confidence</dt><dd>{_esc(item["confidence"])}</dd></div>
                    <div><dt>Owner</dt><dd>{_esc(item["owner"])}</dd></div>
                    <div><dt>Next review</dt><dd>{_esc(item["next_review"])}</dd></div>
                  </dl>
                </details>'''
            )
        body = "".join(blocks)
    return f'<section class="card rec-panel"><div class="section-head"><h2>Recommendations</h2></div>{body}</section>'


def _funnel(model: dict) -> str:
    bits = ['<section class="card funnel-panel"><div class="section-head"><h2>Funnel</h2><span class="status-pill tone-unknown">Directional</span></div><div class="funnel-scroll"><div class="funnel-row">']
    stages = model["stages"]
    for index, stage in enumerate(stages):
        note = stage["note"]
        if stage["key"] == "landing_visits":
            note = model["sources"]["landing_visits"]["note"]
        opp = ""
        if stage["key"] == "leads" and model.get("territory_opps"):
            territory = model["territory_opps"]
            parts = []
            for name in ("Buffalo", "Rochester", "Syracuse", "Virtual"):
                parts.append(f"{name} {int((territory.get('by_territory') or {}).get(name) or 0)}")
            opp = f'<p>Territory opps are not a funnel stage: {_esc(territory.get("total"))} ({_esc(", ".join(parts))}).</p>'
        elif stage["key"] == "leads":
            opp = "<p>Territory opps are not a funnel stage. The sample fixture does not invent an opp count.</p>"
        bits.append(
            f'''<details class="stage">
              <summary>
                <span class="stage-label">{_esc(stage["label"])}</span>
                <span class="stage-value num">{_esc(stage["display"])}</span>
                <span class="stage-state">{_esc(stage["status"] if stage["status"] != "ok" else "")}</span>
              </summary>
              <div class="stage-detail">
                <p>{_esc(note)}</p>
                <p>Window {_esc(model["range_label"])}. Dedup is within the stage definition. Mixed sources stay directional.</p>
                {opp}
              </div>
            </details>'''
        )
        if index < len(stages) - 1:
            bits.append(f'<span class="ratio num">{_esc(stage["ratio_label"])}</span>')
    bits.append("</div></div><p class=\"fine\">A Meta click is not a GA4 session. Ratios across those stages are directional.</p></section>")
    return "".join(bits)


def _stage_notes(model: dict) -> str:
    rows = []
    for stage in model["stages"]:
        rows.append(
            f'<li><strong>{_esc(stage["label"])}</strong> {_esc(stage["display"])} · {_esc(stage["note"])}</li>'
        )
    return f'<section class="card"><h2>Stage detail</h2><ul class="plain">{"".join(rows)}</ul></section>'


def _cost_panel(model: dict, uid: str) -> str:
    charts = model["cost_charts"]
    return f"""
    <section class="card cost-panel">
      <input class="sr-input" type="radio" name="costtab-{_esc(uid)}" id="cost-cpl-{_esc(uid)}" checked />
      <input class="sr-input" type="radio" name="costtab-{_esc(uid)}" id="cost-demo-{_esc(uid)}" />
      <input class="sr-input" type="radio" name="costtab-{_esc(uid)}" id="cost-cpa-{_esc(uid)}" />
      <div class="section-head">
        <h2>Cost trend</h2>
        <div class="tabs" role="tablist">
          <label for="cost-cpl-{_esc(uid)}">CPL</label>
          <label for="cost-demo-{_esc(uid)}">Demo</label>
          <label for="cost-cpa-{_esc(uid)}">CPA</label>
        </div>
      </div>
      <div class="chart cpl">
        <p class="sr-only">{_esc(charts["cpl"]["summary"])}</p>
        {charts["cpl"]["svg"]}
        <p class="fine">{_esc(charts["cpl"]["summary"])} Daily cumulative cohort cost. A zero count stays N/A, not $0.</p>
      </div>
      <div class="chart demo">
        <p class="sr-only">{_esc(charts["demo"]["summary"])}</p>
        {charts["demo"]["svg"]}
        <p class="fine">{_esc(charts["demo"]["summary"])}</p>
      </div>
      <div class="chart cpa">
        <p class="sr-only">{_esc(charts["cpa"]["summary"])}</p>
        {charts["cpa"]["svg"]}
        <p class="fine">{_esc(charts["cpa"]["summary"])} One sale does not prove a trend.</p>
      </div>
    </section>
    """


def _ads_panel(model: dict, compact: bool) -> str:
    ads = model["ads"]
    if ads.get("status") != "ok":
        return (
            '<section class="card ads-panel"><div class="section-head"><h2>Active ads</h2></div>'
            f'<p class="empty">{_esc(ads.get("reason") or "Unavailable")}</p></section>'
        )
    head = """
      <div class="ad-head" role="row">
        <span>Ad</span>
        <button type="button" data-sort="status">Status</button>
        <button type="button" data-sort="impressions">Impr.</button>
        <button type="button" data-sort="clicks">Clicks</button>
        <button type="button" data-sort="ctr">CTR</button>
        <button type="button" data-sort="leads">Leads</button>
        <button type="button" data-sort="cpl">CPL</button>
      </div>
    """
    rows = []
    for ad in ads["rows"]:
        rows.append(
            f'''<details class="ad-row" data-ad-row data-name="{_esc(ad["name"])}" data-status="{_esc(ad["status"])}" data-impressions="{int(ad["impressions"])}" data-clicks="{int(ad["outbound_clicks"])}" data-ctr="{ad["ctr"]}" data-leads="{int(ad["leads"])}" data-cpl="{ad["cpl"]}" data-spend="{ad["spend"]}">
              <summary>
                <span class="ad-name"><span class="thumb" aria-hidden="true">{_esc(ad["name"][:1])}</span><span><strong>{_esc(ad["name"])}</strong><small>{_esc(ad["copy"])}</small></span></span>
                <span class="pill-ok">{_esc(ad["status"])}</span>
                <span class="num">{_esc(f'{int(ad["impressions"]):,}')}</span>
                <span class="num">{_esc(f'{int(ad["outbound_clicks"]):,}')}</span>
                <span class="num">{_esc(ad["ctr_label"])}</span>
                <span class="num">{int(ad["leads"])}</span>
                <span class="num tone-{_esc(ad["tone"])}">{_esc(ad["cpl_label"])}</span>
              </summary>
              <p class="ad-detail">Sample ad {_esc(ad["id"])}. Spend {_esc(f'${ad["spend"]:.0f}')}. CTR is outbound clicks / impressions. CPL is spend / leads. No live ad is edited from this row.</p>
            </details>'''
        )
    total = ads["total"]
    total_row = (
        f'<div class="ad-total" role="row"><span>Total</span><span></span>'
        f'<span class="num">{int(total["impressions"]):,}</span>'
        f'<span class="num">{int(total["outbound_clicks"]):,}</span>'
        f'<span class="num">{_esc(total["ctr_label"])}</span>'
        f'<span class="num">{int(total["leads"])}</span>'
        f'<span class="num tone-{_esc(total["tone"])}">{_esc(total["cpl_label"])}</span></div>'
    )
    view = "" if not compact else '<label class="text-btn" for="screen-campaigns">View all</label>'
    return f'''<section class="card ads-panel"><div class="section-head"><h2>Active ads</h2>{view}</div>
      <div class="table-scroll" data-ad-table data-sort-key="spend" data-sort-dir="desc" role="table">
        {head}{"".join(rows)}{total_row}
      </div>
      <p class="fine">Totals are recomputed from summed counts. CTR display uses outbound clicks / impressions.</p>
    </section>'''


def _activity(model: dict) -> str:
    return f"""
    <section class="card">
      <div class="section-head"><h2>Activity</h2><label class="text-btn" for="screen-overview">Back to overview</label></div>
      <p>Opening this screen does not change ads or spend.</p>
      <p class="empty">A live bot audit log is unavailable. The sample fixture records no ad changes.</p>
      <ul class="plain">
        <li>Sample check at {_esc(model["as_of_label"])}: tracking is a fixture flag, not a live certification.</li>
        <li>No campaign, budget, or ad setting is written by this dashboard.</li>
      </ul>
    </section>
    """


def _settings(model: dict) -> str:
    goals = model["goals"]
    month_bits = []
    for key, value in goals["leads_by_month"].items():
        month_bits.append(f"<li>{_esc(key)} lead goal: {int(value)}</li>")
    return f"""
    <section class="card">
      <div class="section-head"><h2>Settings</h2><label class="text-btn" for="screen-overview">Back to overview</label></div>
      <p>Saving goals is unavailable on this view-only screen. Later months do not inherit November’s goal.</p>
      <ul class="plain">
        {''.join(month_bits)}
        <li>Cost per lead target: ${int(goals["cpl"])}</li>
        <li>Cost per demo target: ${int(goals["demo_cost"])}</li>
        <li>Sold CPA target: ${int(goals["sold_cpa"])}</li>
        <li>Monthly spend cap: {_esc(model["kpis"]["spend"]["cap_label"])}</li>
      </ul>
      <h3>Field mapping</h3>
      <ul class="plain">
        <li>Lead: pipeline {_esc(model["lead_pipeline_id"])}, Lead Gen Source {_esc(model["source_field_id"])} strips to Inbound. Blank, 3PL, and Doors do not count.</li>
        <li>Territory opportunities in Buffalo, Rochester, Syracuse, or Virtual are not a funnel stage.</li>
        <li>Demo uses the existing appointment outcome for those lead contacts. The label on this screen is demo.</li>
        <li>Sold uses contact sold date {_esc(model["sold_date_field_id"])}. The sales metric contract is unchanged.</li>
        <li>Website visits are GA4 paid sessions on {_esc(model["measurement_id"])}. Meta landing-page views are not used.</li>
        <li>CRM clock {_esc(model["crm_timezone"])}. Sample cutoff clock {_esc(model["account_timezone"])}.</li>
      </ul>
    </section>
    """


def _icon_grid() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>'


def _icon_ads() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M4 7h10v10H4zM14 10l6-3v10l-6-3"/></svg>'


def _icon_funnel() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M4 6h16M6 12h12M9 18h6"/></svg>'


def _icon_trend() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M4 16l5-5 3 3 7-7"/><path fill="none" stroke="currentColor" stroke-width="1.6" d="M4 20h16"/></svg>'


def _icon_pulse() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M3 12h4l2-5 4 10 2-5h6"/></svg>'


def _icon_gear() -> str:
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path fill="none" stroke="currentColor" stroke-width="1.6" d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6"/></svg>'


CSS = r"""
:root {
  --canvas:#071B2D; --sidebar:#0A2238; --panel:#0C253B; --raised:#14334A; --border:#24435A;
  --cyan:#26D9EB; --blue:#2EA8FA; --amber:#FFBE45; --success:#11C99B; --critical:#F16D79;
  --text:#F1F6FF; --secondary:#B5C7DC; --muted:#8FA7BF;
  --sidebar-w:194px;
}
* { box-sizing:border-box; }
html, body { margin:0; background:var(--canvas); color:var(--text); }
body { font-family:Inter, ui-sans-serif, system-ui, sans-serif; font-size:13px; line-height:19px; }
.num { font-variant-numeric:tabular-nums; }
button, input, summary, a, label { font-family:inherit; }
.sr-input { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
:focus-visible { outline:2px solid var(--cyan); outline-offset:2px; }
.app { display:grid; grid-template-columns:var(--sidebar-w) minmax(0,1fr); min-height:100vh; background:var(--canvas); }
.sidebar { background:var(--sidebar); min-height:100vh; padding:16px 0; }
.wordmark { display:flex; align-items:center; gap:10px; height:50px; padding:0 16px; font-weight:650; letter-spacing:-.02em; }
.sidenav { display:flex; flex-direction:column; }
.nav-link { display:flex; align-items:center; gap:10px; height:50px; padding:0 14px 0 12px; color:var(--secondary); border-left:4px solid transparent; cursor:pointer; }
.nav-link svg { flex:0 0 20px; }
#screen-overview:checked ~ .sidebar label[for="screen-overview"],
#screen-campaigns:checked ~ .sidebar label[for="screen-campaigns"],
#screen-funnel:checked ~ .sidebar label[for="screen-funnel"],
#screen-trends:checked ~ .sidebar label[for="screen-trends"],
#screen-activity:checked ~ .sidebar label[for="screen-activity"],
#screen-settings:checked ~ .sidebar label[for="screen-settings"] {
  background:var(--blue); color:#fff; border-left-color:#F1F6FF; font-weight:650;
}
.content { min-width:0; padding:18px; display:flex; flex-direction:column; gap:12px; }
.panel { display:none; gap:12px; min-width:0; }
#screen-overview:checked ~ .content .panel-overview,
#screen-campaigns:checked ~ .content .panel-campaigns,
#screen-funnel:checked ~ .content .panel-funnel,
#screen-trends:checked ~ .content .panel-trends,
#screen-activity:checked ~ .content .panel-activity,
#screen-settings:checked ~ .content .panel-settings { display:flex; flex-direction:column; gap:12px; }
.header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; min-height:62px; }
.title-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
h1 { margin:0; font-size:30px; line-height:36px; font-weight:650; letter-spacing:-.03em; }
h2 { margin:0; font-size:18px; line-height:24px; font-weight:600; }
h3 { margin:16px 0 8px; font-size:13px; line-height:19px; }
.subtitle { margin:2px 0 0; color:var(--secondary); }
.cutoff, .fine { margin:2px 0 0; color:var(--muted); font-size:12px; line-height:16px; }
.badge { border:1px solid var(--amber); color:var(--amber); background:rgba(255,190,69,.12); border-radius:999px; padding:4px 8px; font-size:11px; font-weight:700; letter-spacing:.06em; }
.badge-live { border-color:var(--muted); color:var(--muted); background:transparent; }
.header-tools { display:flex; align-items:center; gap:8px; }
.menu-btn { display:none; }
.date-menu summary, .mode-link, .text-btn, button {
  background:transparent; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; cursor:pointer;
}
.mode-link, .text-btn { text-decoration:none; color:var(--secondary); display:inline-flex; align-items:center; }
.date-panel { position:absolute; right:0; z-index:5; margin-top:8px; background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px; display:flex; flex-direction:column; gap:8px; min-width:240px; }
.date-menu { position:relative; }
.date-panel a { color:var(--cyan); text-decoration:none; }
.date-panel label { display:flex; justify-content:space-between; gap:8px; color:var(--secondary); font-size:12px; }
input[type="date"] { background:var(--canvas); color:var(--text); border:1px solid var(--border); border-radius:8px; padding:6px 8px; }
.banner { margin:0; padding:10px 12px; border:1px solid var(--amber); border-radius:8px; color:var(--amber); background:rgba(255,190,69,.08); }
.kpis { display:grid; grid-template-columns:1.3fr 1.1fr .7fr 1.1fr .7fr 1.1fr .7fr; gap:12px; }
.kpi, .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:16px; }
.kpi { min-height:142px; display:flex; flex-direction:column; gap:6px; padding:12px; }
.kpi-label { margin:0; color:var(--muted); font-size:12px; line-height:16px; }
.kpi-value { margin:0; font-size:36px; line-height:40px; font-weight:650; letter-spacing:-.03em; }
.kpi-note { margin:0; color:var(--secondary); font-size:12px; line-height:16px; }
.tone-amber .kpi-note, .tone-amber { color:var(--amber); }
.kpi.tone-amber .kpi-value { color:var(--text); }
.kpi.tone-amber .kpi-note { color:var(--amber); }
.kpi.tone-success .kpi-note, .tone-success { color:var(--success); }
.tone-unknown { color:var(--muted); }
.tone-critical { color:var(--critical); }
.bar { display:block; height:6px; border-radius:999px; background:var(--raised); overflow:hidden; }
.bar > span { display:block; height:100%; background:var(--cyan); }
.main-row { display:grid; grid-template-columns:56fr 24fr 20fr; gap:12px; min-height:324px; }
.bottom-row { display:grid; grid-template-columns:45fr 55fr; gap:12px; min-height:235px; }
.section-head { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px; }
.legend { display:flex; gap:8px; align-items:center; margin:0; color:var(--secondary); font-size:12px; }
.swatch { width:16px; height:3px; display:inline-block; }
.swatch.actual { background:var(--cyan); }
.swatch.guide { background:transparent; border-top:2px dashed var(--secondary); height:0; }
.chart-frame, .chart { min-width:0; }
.chart-svg { width:100%; height:auto; display:block; }
.grid { stroke:#24435A; stroke-opacity:.55; }
.tick { fill:#8FA7BF; font-size:11px; }
.actual { fill:none; stroke:#26D9EB; stroke-width:2.5; }
.guide { fill:none; stroke:#B5C7DC; stroke-width:1.5; stroke-dasharray:5 4; }
.area { fill:#26D9EB; opacity:.12; }
.dot { fill:#26D9EB; }
.future { fill:#F1F6FF; opacity:.04; }
.actual-label { fill:#26D9EB; font-size:12px; font-weight:650; }
.guide-label { fill:#B5C7DC; font-size:12px; }
.bot-panel, .rec-panel, .lead-panel { min-width:0; overflow:auto; }
.status-list { list-style:none; margin:8px 0 0; padding:0; display:flex; flex-direction:column; gap:10px; }
.status-list li { display:flex; flex-direction:column; gap:2px; }
.status-pill { border-radius:999px; padding:3px 8px; border:1px solid currentColor; font-size:12px; font-weight:700; letter-spacing:.04em; }
.rec { border-top:1px solid var(--border); padding:8px 0; }
.rec summary { display:flex; justify-content:space-between; gap:8px; cursor:pointer; color:var(--text); }
.rec summary em { color:var(--amber); font-style:normal; font-size:12px; }
.rec p, .rec dl { margin:8px 0 0; color:var(--secondary); }
.rec dl { display:grid; gap:4px; }
.rec dt { color:var(--muted); font-size:12px; }
.rec dd { margin:0; }
.funnel-scroll { overflow-x:auto; }
.funnel-row { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr); gap:8px; align-items:stretch; }
.stage { background:var(--raised); border:1px solid var(--border); border-radius:8px; min-width:0; }
.stage summary { list-style:none; cursor:pointer; padding:12px; display:flex; flex-direction:column; gap:4px; min-height:96px; }
.stage summary::-webkit-details-marker { display:none; }
.stage-label { color:var(--muted); font-size:12px; line-height:16px; }
.stage-value { font-size:22px; line-height:28px; font-weight:650; }
.stage-state { color:var(--muted); font-size:12px; min-height:16px; }
.stage-detail { padding:0 12px 12px; color:var(--secondary); }
.ratio { align-self:center; color:var(--secondary); font-size:12px; }
.tabs { display:flex; gap:6px; }
.tabs label { border:1px solid var(--border); border-radius:8px; padding:6px 10px; color:var(--secondary); cursor:pointer; }
.cost-panel input[id^="cost-cpl-"]:checked ~ .section-head label[for^="cost-cpl-"],
.cost-panel input[id^="cost-demo-"]:checked ~ .section-head label[for^="cost-demo-"],
.cost-panel input[id^="cost-cpa-"]:checked ~ .section-head label[for^="cost-cpa-"] { background:var(--blue); color:#fff; border-color:var(--blue); }
.cost-panel .chart { display:none; }
.cost-panel input[id^="cost-cpl-"]:checked ~ .chart.cpl,
.cost-panel input[id^="cost-demo-"]:checked ~ .chart.demo,
.cost-panel input[id^="cost-cpa-"]:checked ~ .chart.cpa { display:block; }
.ads-panel { display:flex; flex-direction:column; min-height:0; }
.ads-panel .table-scroll { flex:1 1 auto; min-height:0; overflow:auto; max-width:100%; }
.table-scroll { overflow:auto; max-width:100%; }
.ad-head, .ad-row > summary, .ad-total {
  display:grid; grid-template-columns:minmax(140px,1.6fr) .7fr .7fr .7fr .6fr .5fr .6fr; gap:8px; align-items:center;
}
.ad-head { color:var(--muted); font-size:12px; padding-bottom:8px; }
.ad-head button { background:transparent; border:0; color:var(--muted); text-align:right; padding:0; cursor:pointer; }
.ad-row { border-top:1px solid var(--border); }
.ad-row summary { list-style:none; cursor:pointer; padding:4px 0; }
.ad-row summary::-webkit-details-marker { display:none; }
.ad-name { display:flex; gap:8px; align-items:center; min-width:0; }
.ad-name small { display:block; color:var(--muted); }
.thumb { width:28px; height:28px; border-radius:6px; background:var(--raised); display:inline-flex; align-items:center; justify-content:center; color:var(--secondary); }
.ad-head span:not(:first-child), .ad-row summary span:not(.ad-name), .ad-total span:not(:first-child) { text-align:right; }
.pill-ok { color:var(--success); }
.ad-total { border-top:1px solid var(--border); padding-top:8px; font-weight:650; }
.ad-detail { margin:0 0 8px 36px; color:var(--secondary); }
.plain { margin:8px 0 0; padding-left:18px; color:var(--secondary); }
.empty { color:var(--secondary); }
.scrim { display:none; }
@media (max-width:1439px) and (min-width:1200px) {
  :root { --sidebar-w:176px; }
}
@media (max-width:1199px) {
  :root { --sidebar-w:64px; }
  .wordmark-text, .nav-label { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }
  .wordmark, .nav-link { justify-content:center; padding-left:0; padding-right:0; }
  .kpis { grid-template-columns:repeat(3, minmax(0,1fr)); }
  .main-row { grid-template-columns:1fr 1fr; min-height:0; }
  .lead-panel { grid-column:1 / -1; min-height:240px; }
  .funnel-row { min-width:980px; }
}
@media (max-width:767px) {
  .app { grid-template-columns:minmax(0,1fr); }
  .menu-btn { display:inline-flex; }
  .sidebar { position:fixed; z-index:20; width:240px; transform:translateX(-105%); transition:transform .2s ease; }
  #nav-toggle:checked ~ .sidebar { transform:none; }
  #nav-toggle:checked ~ .scrim { display:block; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:15; }
  .wordmark-text, .nav-label { position:static; width:auto; height:auto; overflow:visible; clip:auto; }
  .wordmark, .nav-link { justify-content:flex-start; padding-left:14px; }
  .kpis { grid-template-columns:1fr 1fr; }
  .kpi-spend { grid-column:1 / -1; }
  .main-row, .bottom-row { grid-template-columns:1fr; }
  .lead-panel { min-height:240px; }
  .header { flex-direction:column; }
  .funnel-scroll { overflow:visible; }
  .funnel-row { min-width:0; display:flex; flex-direction:column; }
  .ratio { align-self:flex-start; padding-left:12px; }
  h1 { font-size:26px; line-height:32px; }
  .kpi { min-height:0; }
}
@media (min-width:1200px) and (min-height:960px) {
  .app { height:100vh; }
  .content { height:100vh; overflow:hidden; }
  #screen-overview:checked ~ .content .panel-overview {
    height:calc(100vh - 36px);
    display:grid;
    grid-template-rows:auto auto minmax(200px,1fr) minmax(112px,128px) minmax(292px,1fr);
    overflow:hidden;
  }
  #screen-overview:checked ~ .content { overflow:hidden; }
  #screen-overview:checked ~ .content .panel-overview .main-row,
  #screen-overview:checked ~ .content .panel-overview .bottom-row {
    min-height:0;
    height:100%;
  }
  #screen-overview:checked ~ .content .panel-overview .lead-panel,
  #screen-overview:checked ~ .content .panel-overview .cost-panel,
  #screen-overview:checked ~ .content .panel-overview .funnel-panel {
    min-height:0;
    overflow:hidden;
  }
  #screen-overview:checked ~ .content .panel-overview .lead-panel,
  #screen-overview:checked ~ .content .panel-overview .cost-panel {
    display:flex;
    flex-direction:column;
  }
  #screen-overview:checked ~ .content .panel-overview .chart-frame,
  #screen-overview:checked ~ .content .panel-overview .cost-panel .chart {
    flex:1 1 auto;
    min-height:0;
  }
  #screen-overview:checked ~ .content .panel-overview .chart-svg {
    width:100%;
    height:100%;
  }
  #screen-overview:checked ~ .content .panel-overview .ads-panel {
    height:100%;
    overflow:hidden;
    padding:12px;
  }
  #screen-overview:checked ~ .content .panel-overview .ads-panel .section-head { margin-bottom:4px; }
  #screen-overview:checked ~ .content .panel-overview .ads-panel .fine { margin-top:4px; }
  #screen-overview:checked ~ .content .panel-overview .funnel-panel { padding:12px; }
  #screen-overview:checked ~ .content .panel-overview .stage summary { min-height:0; padding:8px; }
  #screen-overview:checked ~ .content .panel-overview .stage-state:empty { display:none; }
}
"""
