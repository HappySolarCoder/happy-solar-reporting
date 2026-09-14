# -*- coding: utf-8 -*-

"""Vercel Python function: /api/website_traffic

Website Traffic Dashboard v1 for Marketing + Charles QA.
HTML default. Optional ?format=json returns live/stub tile fields.

Live tiles (warehouse + GA4 Data API, property 408492342 / G-V02RZFR4SZ):
Overview KPIs + brand vs estimate/calc, Acquisition channel/source/medium
+ FB organic vs paid (GA4 only), Funnel estimate/LP → start → address →
bill → submit → named fill, Named-fill aggregates.

EXAMPLE until real: Audience, Meta spend, Contact step, paid landing
mismatch, Content exits. CTA taps / FB post→sessions only if events exist.

Locks: Funnel TOP = /estimate + legacy wny calc, NOT all-site sessions.
Test filter ON by default. Instant Form / 3PL are NOT website leads.
Named fills = Marketing aggregates; PII stays gated. Do not invent Meta
spend. Form freeze: this page does not change the calculator form.

Exclude list (test filter ON):
Hawkstone Way, 313 E Stonebridge Gilbert, Test Test, Evan Day,
adchday@gmail.com, evanrday23@gmail.com, preview/debug/internal.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav

NY_TZ = ZoneInfo("America/New_York")


def _load_metric():
    path = API_DIR / "metrics" / "website_traffic.py"
    spec = importlib.util.spec_from_file_location("hs_website_traffic_metric", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load website_traffic metric from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metric = _load_metric()


def default_range_et(now: datetime | None = None) -> tuple[str, str]:
    return metric.default_range(now)


def json_for_script(payload: dict) -> str:
    return json.dumps(payload, default=str).replace("<", "\\u003c")


def tile_status(data: dict | None, name: str) -> str:
    return ((data or {}).get("tiles") or {}).get(name, {}).get("status") or "example"


def fmt_num(value) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def fmt_pct(value) -> str:
    if value is None or value == "":
        return "—"
    return f"{float(value) * 100:.1f}%"


def fmt_delta_html(value) -> str:
    if value is None or value == "":
        return ""
    n = float(value)
    cls = "down" if n < 0 else "up"
    sign = "+" if n > 0 else ""
    return f'vs prior <span class="delta {cls}">{sign}{n * 100:.1f}%</span>'


def example_tag_html(data: dict | None, name: str, fallback: str = "EXAMPLE") -> str:
    """First-paint tile tag. Live tiles say LIVE; stub wording like STEP % STUBS is not used."""
    status = tile_status(data, name)
    if status == "live":
        return f'<span class="example-tag live" data-tile="{escape(name)}">LIVE</span>'
    if status == "not_wired":
        return f'<span class="example-tag" data-tile="{escape(name)}">NOT WIRED</span>'
    label = "EXAMPLE" if fallback in {"LIVE", "STEP % STUBS", "GA4"} else fallback
    return f'<span class="example-tag" data-tile="{escape(name)}">{escape(label)}</span>'


def domain_select_key(domain: str | None) -> str:
    key = (domain or "all").casefold()
    if key in {"wny", "wny.happyslr.com"}:
        return "wny.happyslr.com"
    if key in {"happyslr.com", "www.happyslr.com", "brand"}:
        return "happyslr.com"
    return "all"


def domain_label(domain: str | None) -> str:
    key = domain_select_key(domain)
    return {"all": "All", "happyslr.com": "happyslr.com", "wny.happyslr.com": "wny.happyslr.com"}[key]


def selected_attr(current: str, want: str) -> str:
    return " selected" if current == want else ""


def html_acq_body(rows: list | None) -> str:
    if not rows:
        return '<tr><td colspan="4">No GA4 acquisition rows yet.</td></tr>'
    parts = []
    for row in rows:
        parts.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(str(row.get("channel") or "")),
                escape(str(row.get("source_medium") or "")),
                escape(fmt_num(row.get("sessions"))),
                escape(fmt_num(row.get("users"))),
            )
        )
    return "".join(parts)


def html_landing_body(rows: list | None) -> str:
    if not rows:
        return '<tr><td colspan="2">No path report yet.</td></tr>'
    parts = []
    for row in list(rows)[:5]:
        parts.append(
            "<tr><td>{}</td><td>{}</td></tr>".format(
                escape(str(row.get("page") or "")),
                escape(fmt_num(row.get("sessions"))),
            )
        )
    return "".join(parts)


def first_paint_substitutions(data: dict, start: str, end: str) -> dict[str, str]:
    """HTML first paint from the same payload as initialPayload. Mirrors client paint()."""
    overview = data.get("overview") or {}
    funnel = data.get("funnel") or {}
    named = data.get("named_fills") or {}
    acq = data.get("acquisition") or {}
    content = data.get("content") or {}
    rates = funnel.get("rates") or {}
    live = list(data.get("live_fields") or [])
    stub = list(data.get("stub_fields") or [])
    test_on = bool(data.get("test_filter", True))
    compare = bool(data.get("compare_prior", True))
    domain_key = domain_select_key(data.get("domain"))
    new_share = overview.get("new_share")
    ret_share = overview.get("returning_share")
    if new_share is None and ret_share is None:
        new_ret = "—"
    else:
        new_ret = f"{fmt_pct(new_share)} / {fmt_pct(ret_share)}"
    pages_per = overview.get("pages_per_session")
    bounce = overview.get("bounce_rate")
    engaged = overview.get("engaged_rate")
    if bounce is None and engaged is None:
        bounce_label = "—"
    else:
        bounce_label = f"{fmt_pct(bounce)} / {fmt_pct(engaged)}"
    vs_prior = overview.get("vs_prior_sessions")
    if vs_prior is None:
        vs_prior_kpi = "—"
    else:
        vs_prior_kpi = f"{'+' if vs_prior > 0 else ''}{float(vs_prior) * 100:.1f}%"
    cta = fmt_num(overview.get("cta_taps")) if tile_status(data, "cta_taps") == "live" else "—"
    fb_post = (
        fmt_num(overview.get("fb_organic_sessions"))
        if tile_status(data, "fb_post_sessions") == "live"
        else "—"
    )
    landings = html_landing_body(content.get("top_landings") or [])
    return {
        "START": start,
        "END": end,
        "TITLE_TAG_CLASS": "example-tag live" if live else "example-tag",
        "TITLE_TAG_TEXT": "LIVE + EXAMPLE" if live else "EXAMPLE DATA",
        "STATUS_BANNER": (
            f"LIVE: {', '.join(live) or 'none'}. EXAMPLE / not-wired: {', '.join(stub) or 'none'}"
            ". Funnel top is estimate/LP, not all-site. Instant Form / 3PL are not website leads. "
            "Meta spend was not invented. Charles QA before treating as live."
        ),
        "CHROME_LABEL": (
            f"Range {start} → {end} ET · domain {domain_label(domain_key)}"
            f" · test filter {'ON' if test_on else 'OFF'}"
            f" · compare prior {'ON' if compare else 'OFF'}"
        ),
        "TEST_CHECKED": " checked" if test_on else "",
        "COMPARE_CHECKED": " checked" if compare else "",
        "SEL_ALL": selected_attr(domain_key, "all"),
        "SEL_HAPPY": selected_attr(domain_key, "happyslr.com"),
        "SEL_WNY": selected_attr(domain_key, "wny.happyslr.com"),
        "VS_PRIOR": "vs-prior" if compare else "vs-prior is-off",
        "LEAK_CLASS": "" if funnel.get("alert_visits_up_starts_zero") else " is-off",
        "EXCLUDE_CLASS": "" if test_on else " is-off",
        "JSON_HREF": "/api/website_traffic?"
        + urlencode(
            {
                "format": "json",
                "start": start,
                "end": end,
                "domain": domain_key,
                "test_filter": "1" if test_on else "0",
                "compare_prior": "1" if compare else "0",
            }
        ),
        "TAG_META_SPEND": example_tag_html(data, "meta_spend"),
        "TAG_FUNNEL": example_tag_html(data, "funnel"),
        "TAG_OVERVIEW": example_tag_html(data, "overview"),
        "TAG_OVERVIEW_USERS": example_tag_html(data, "overview_users"),
        "TAG_OVERVIEW_BRAND": example_tag_html(data, "overview_brand_vs_estimate"),
        "TAG_CTA": example_tag_html(data, "cta_taps"),
        "TAG_FB": example_tag_html(data, "fb_post_sessions"),
        "TAG_ACQUISITION": example_tag_html(data, "acquisition"),
        "TAG_PAID_MISMATCH": example_tag_html(data, "paid_mismatch"),
        "TAG_CONTENT": example_tag_html(data, "content"),
        "TAG_AUDIENCE": example_tag_html(data, "audience"),
        "TAG_NAMED": example_tag_html(data, "named_fills"),
        "KPI_SESSIONS": escape(fmt_num(overview.get("sessions"))),
        "KPI_USERS": escape(fmt_num(overview.get("users"))),
        "KPI_NEW_RET": escape(new_ret),
        "KPI_PAGEVIEWS": escape(fmt_num(overview.get("pageviews"))),
        "KPI_PAGES_PER": escape("—" if pages_per is None else f"{float(pages_per):.2f}"),
        "KPI_BOUNCE": escape(bounce_label),
        "KPI_ENGAGE": escape(overview.get("avg_engagement_label") or "—"),
        "KPI_VS_PRIOR": escape(vs_prior_kpi),
        "KPI_BRAND": escape(fmt_num(overview.get("brand_site_sessions"))),
        "KPI_ESTIMATE": escape(fmt_num(overview.get("estimate_calc_sessions"))),
        "KPI_CTA": escape(cta),
        "KPI_FB_POST": escape(fb_post),
        "META_SESSIONS": fmt_delta_html(overview.get("vs_prior_sessions")),
        "META_BRAND": fmt_delta_html(overview.get("vs_prior_brand")),
        "META_ESTIMATE": fmt_delta_html(overview.get("vs_prior_estimate")),
        "FUNNEL_BRAND": escape(fmt_num(funnel.get("brand_site_sessions"))),
        "FUNNEL_TOP": escape(fmt_num(funnel.get("estimate_lp_visits"))),
        "STEP_LP": escape(fmt_num(funnel.get("estimate_lp_visits"))),
        "STEP_START": escape(fmt_num(funnel.get("starts"))),
        "STEP_ADDRESS": escape(fmt_num(funnel.get("address"))),
        "STEP_BILL": escape(fmt_num(funnel.get("bill"))),
        "STEP_SUBMIT": escape(fmt_num(funnel.get("submit"))),
        "STEP_NAMED": escape(fmt_num(funnel.get("named_fill"))),
        "META_START": escape(f"{fmt_pct(rates.get('start_of_estimate_lp'))} of estimate/LP"),
        "META_ADDRESS": escape(f"{fmt_pct(rates.get('address_of_start'))} of start"),
        "META_BILL": escape(f"{fmt_pct(rates.get('bill_of_address'))} of address"),
        "META_SUBMIT": escape(f"{fmt_pct(rates.get('submit_of_bill'))} of bill · estimate_submit only"),
        "META_NAMED": escape(f"{fmt_pct(rates.get('named_fill_of_submit'))} of submit"),
        "SCOREBOARD_KPI": escape(fmt_num(funnel.get("named_fill"))),
        "SCOREBOARD_META": escape(
            f"Named fills {fmt_num(funnel.get('named_fill'))}"
            f" · submit / estimate/LP {fmt_pct(rates.get('submit_of_estimate_lp'))}"
            f" · start→submit {fmt_pct(rates.get('start_to_submit'))}"
            " · CPA when paid — (Meta not wired)"
        ),
        "NAMED_KPI": escape(fmt_num(named.get("live_count"))),
        "NAMED_META": escape(
            f"Live named fills {fmt_num(named.get('live_count'))}"
            f" · excluded tests {fmt_num(named.get('excluded_count'))}"
            f" · new-site-estimate {fmt_num(named.get('new_site_estimate'))}"
            f" · legacy leads@ {fmt_num(named.get('legacy_wny'))}"
            ". Counts only — no names, emails, or phones for Marketing."
        ),
        "ACQ_BODY": html_acq_body(acq.get("rows") or []),
        "FB_SPLIT_META": escape(
            f"Organic social {fmt_num(acq.get('fb_organic'))}"
            f" · Paid social {fmt_num(acq.get('fb_paid'))}"
            " · GA4 only, not Ads Manager."
        ),
        "LANDING_BODY": landings,
        "PAGES_BODY": landings,
    }


def apply_first_paint(html: str, data: dict, start: str, end: str) -> str:
    subs = first_paint_substitutions(data, start, end)
    out = html
    for key in sorted(subs, key=len, reverse=True):
        out = out.replace(f"__{key}__", str(subs[key]))
    return out


def build_payload(qs: dict[str, list[str]] | None = None, now: datetime | None = None) -> dict:
    qs = qs or {}
    db = None
    db_connected = False
    try:
        db = metric.get_db()
        db_connected = True
    except AttributeError as e:
        return metric.example_degrade_payload(error=str(e), now=now)
    except Exception:
        db = None
    try:
        return metric.payload_from_query(qs, db=db, now=now)
    except AttributeError as e:
        return metric.example_degrade_payload(error=str(e), now=now)
    except Exception as e:
        if db_connected:
            return metric.example_degrade_payload(error=str(e), now=now)
        raise


def render_html(now: datetime | None = None, payload: dict | None = None) -> str:
    data = payload or metric.compute_website_traffic(None, now=now, fetch_remote=False)
    start = data.get("start") or default_range_et(now)[0]
    end = data.get("end") or default_range_et(now)[1]
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
    .example-tag.live { background:#dcfce7; color:#166534; }
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
        <div class="title">Website Traffic <span id="titleTag" class="__TITLE_TAG_CLASS__">__TITLE_TAG_TEXT__</span></div>
        <div class="subtitle">Marketing dashboard. Primary CTA is <b>www.happyslr.com/estimate</b>. Dual-domain history stays (happyslr.com + wny.happyslr.com). Instant Form / 3PL are not website leads. Funnel top is estimate/LP visits, not all-site sessions. EXAMPLE tags stay on tiles that are not wired. Charles QA before treating as live.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Date range ET</div><input id="startDate" type="date" value="__START__" /><input id="endDate" type="date" value="__END__" /></div>
        <div class="filter"><div class="filter-label">Domain</div>
          <select id="domain">
            <option value="all"__SEL_ALL__>All</option>
            <option value="happyslr.com"__SEL_HAPPY__>happyslr.com</option>
            <option value="wny.happyslr.com"__SEL_WNY__>wny.happyslr.com</option>
          </select>
        </div>
        <label class="check"><input id="testFilter" type="checkbox"__TEST_CHECKED__ /> Test filter ON</label>
        <label class="check"><input id="comparePrior" type="checkbox"__COMPARE_CHECKED__ /> Compare prior</label>
        <button id="apply" type="button">Apply</button>
      </div>
    </div>

    <div class="grid">
      <div id="statusBanner" class="banner">__STATUS_BANNER__</div>
      <div class="card span-12">
        <div class="card-title">Chrome</div>
        <div class="meta" id="chromeLabel">__CHROME_LABEL__</div>
      </div>

      <div class="section-label">Strips</div>
      <div class="card span-4">
        <div class="card-title">Meta spend / reach / clicks __TAG_META_SPEND__</div>
        <div class="kpi">—</div>
        <div class="meta">Meta is not wired. Do not treat the dash as spend. Shown when Ads ACTIVE in a later wiring pass. Do not invent Ads Manager numbers.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Scoreboard __TAG_FUNNEL__</div>
        <div class="kpi" id="scoreboardKpi">__SCOREBOARD_KPI__</div>
        <div class="meta" id="scoreboardMeta">__SCOREBOARD_META__</div>
      </div>
      <div id="leakAlert" class="banner alert span-12__LEAK_CLASS__">estimate/LP visits ↑ · starts → 0 — leak uses /estimate (or WNY calc) visits, not all-site sessions.</div>

      <div class="card span-12">
        <div class="card-title">Where each question lives</div>
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
        <div class="card span-3"><div class="card-title">Sessions __TAG_OVERVIEW__</div><div class="kpi" id="kpiSessions">__KPI_SESSIONS__</div><div class="meta __VS_PRIOR__" id="metaSessions">__META_SESSIONS__</div></div>
        <div class="card span-3"><div class="card-title">Users __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiUsers">__KPI_USERS__</div><div class="meta">GA4 totalUsers on allowlisted hosts.</div></div>
        <div class="card span-3"><div class="card-title">New / returning __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiNewRet">__KPI_NEW_RET__</div><div class="meta" id="metaNewRet">new vs returning share</div></div>
        <div class="card span-3"><div class="card-title">Pageviews __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiPageviews">__KPI_PAGEVIEWS__</div><div class="meta">GA4 screenPageViews</div></div>
        <div class="card span-3"><div class="card-title">Pages / session __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiPagesPer">__KPI_PAGES_PER__</div><div class="meta">pageviews / sessions</div></div>
        <div class="card span-3"><div class="card-title">Bounce / engaged __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiBounce">__KPI_BOUNCE__</div><div class="meta">GA4 bounce + engaged session rate.</div></div>
        <div class="card span-3"><div class="card-title">Avg engagement __TAG_OVERVIEW_USERS__</div><div class="kpi" id="kpiEngage">__KPI_ENGAGE__</div><div class="meta __VS_PRIOR__">GA4 averageSessionDuration</div></div>
        <div class="card span-3 __VS_PRIOR__"><div class="card-title">Vs prior __TAG_OVERVIEW__</div><div class="kpi" id="kpiVsPrior">__KPI_VS_PRIOR__</div><div class="meta">Sessions vs prior period (same length, ET). Toggle Compare prior in chrome.</div></div>
        <div class="card span-3"><div class="card-title">Brand site sessions __TAG_OVERVIEW_BRAND__</div><div class="kpi" id="kpiBrand">__KPI_BRAND__</div><div class="meta">happyslr.com / www brand pages. Not the funnel top. <span class="__VS_PRIOR__" id="metaBrand">__META_BRAND__</span></div></div>
        <div class="card span-3"><div class="card-title">Estimate / calc sessions __TAG_OVERVIEW_BRAND__</div><div class="kpi" id="kpiEstimate">__KPI_ESTIMATE__</div><div class="meta">/estimate + legacy wny calculator. Funnel step 1. <span class="__VS_PRIOR__" id="metaEstimate">__META_ESTIMATE__</span></div></div>
        <div class="card span-3"><div class="card-title">CTA taps → /estimate __TAG_CTA__</div><div class="kpi" id="kpiCta">__KPI_CTA__</div><div class="meta">Brand-page CTA clicks (estimate_cta_click) when that event exists. Else EXAMPLE.</div></div>
        <div class="card span-3"><div class="card-title">Organic FB post → sessions __TAG_FB__</div><div class="kpi" id="kpiFbPost">__KPI_FB_POST__</div><div class="meta">facebook / organic sessions from GA4 only. Not Ads Manager.</div></div>
      </div>
    </section>

    <section id="tab-acquisition" class="tabpanel" data-tab="acquisition">
      <div class="grid">
        <div class="section-label">Acquisition</div>
        <div class="card span-8">
          <div class="card-title">Channel + source / medium __TAG_ACQUISITION__</div>
          <div class="meta" style="margin-bottom:10px">GA4 sessionDefaultChannelGroup + sessionSource / sessionMedium on allowlisted hosts. Not Meta spend.</div>
          <table>
            <thead><tr><th>Channel</th><th>Source / medium</th><th>Sessions</th><th>Users</th></tr></thead>
            <tbody id="acqBody">
              __ACQ_BODY__
            </tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">FB organic vs Meta paid</div>
          <div class="callout" id="fbCallout">Facebook / Instagram organic vs paid from GA4 source/medium only. Not Ads Manager. Meta spend stays not-wired.</div>
          <div class="meta" style="margin-top:10px" id="fbSplitMeta">__FB_SPLIT_META__</div>
        </div>
        <div class="card span-12 callout warn">Paid landing mismatch: EXAMPLE — landing × source is not queried in v1. Do not read this as Ads numbers. Later wiring flags www-without-estimate_start.</div>
        <div class="card span-12">
          <div class="card-title">Landing × source — top 10 __TAG_PAID_MISMATCH__</div>
          <table>
            <thead><tr><th>#</th><th>Landing</th><th>Source / medium</th><th>Sessions</th></tr></thead>
            <tbody>
              <tr><td colspan="4">EXAMPLE — extra landing × source report not pulled. Content/LPs shows path landings when cheap.</td></tr>
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
          <div class="card-title">Top landings __TAG_CONTENT__</div>
          <table>
            <thead><tr><th>Page</th><th>Sessions</th></tr></thead>
            <tbody id="landingBody">__LANDING_BODY__</tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">Top pages __TAG_CONTENT__</div>
          <table>
            <thead><tr><th>Page</th><th>Views</th></tr></thead>
            <tbody id="pagesBody">__PAGES_BODY__</tbody>
          </table>
        </div>
        <div class="card span-4">
          <div class="card-title">Top exits <span class="example-tag">EXAMPLE</span></div>
          <table>
            <thead><tr><th>Page</th><th>Exits</th></tr></thead>
            <tbody>
              <tr><td>/estimate</td><td>—</td></tr>
              <tr><td>/</td><td>—</td></tr>
              <tr><td>wny /calculator (legacy)</td><td>—</td></tr>
            </tbody>
          </table>
          <div class="meta">Exit report not pulled (not cheap enough for v1).</div>
        </div>
      </div>
    </section>

    <section id="tab-funnel" class="tabpanel" data-tab="funnel">
      <div class="grid">
        <div class="section-label">Funnel</div>
        <div class="card span-12">
          <div class="card-title">estimate/LP visits → start → address → bill → contact → submit → named fill __TAG_FUNNEL__</div>
          <div class="meta" style="margin-bottom:10px">Funnel top is <b>estimate/LP visits</b> (/estimate + legacy wny calculator), not all-site sessions. All-site sessions as step 1 muddies the visits-without-starts leak. Instant Form / 3PL are NOT website leads.</div>
          <div id="excludeChip" class="chip__EXCLUDE_CLASS__" style="margin-bottom:12px">Test filter ON — excluded: Hawkstone / Stonebridge / Test Test / Evan Day / test emails / preview</div>
          <div class="steps" style="margin-bottom:10px">
            <div class="step"><div class="name">Brand-site sessions</div><div class="val" id="funnelBrand">__FUNNEL_BRAND__</div><div class="meta">Dual top — not funnel step 1</div></div>
            <div class="step"><div class="name">Estimate / LP visits</div><div class="val" id="funnelTop">__FUNNEL_TOP__</div><div class="meta">Funnel step 1 · 100%</div></div>
          </div>
          <div class="steps">
            <div class="step"><div class="name">Estimate / LP visits</div><div class="val" id="stepLp">__STEP_LP__</div><div class="meta">100% of estimate/LP</div></div>
            <div class="step"><div class="name">Start</div><div class="val" id="stepStart">__STEP_START__</div><div class="meta" id="metaStart">__META_START__</div></div>
            <div class="step"><div class="name">Address</div><div class="val" id="stepAddress">__STEP_ADDRESS__</div><div class="meta" id="metaAddress">__META_ADDRESS__</div></div>
            <div class="step"><div class="name">Bill</div><div class="val" id="stepBill">__STEP_BILL__</div><div class="meta" id="metaBill">__META_BILL__</div></div>
            <div class="step"><div class="name">Contact</div><div class="val">—</div><div class="meta">EXAMPLE — no contact event</div></div>
            <div class="step"><div class="name">Submit</div><div class="val" id="stepSubmit">__STEP_SUBMIT__</div><div class="meta" id="metaSubmit">__META_SUBMIT__</div></div>
            <div class="step"><div class="name">Named fill</div><div class="val" id="stepNamed">__STEP_NAMED__</div><div class="meta" id="metaNamed">__META_NAMED__</div></div>
          </div>
        </div>
        <div class="card span-12 callout warn">Instant Form and 3PL bought leads do not belong on this funnel. They are not website leads.</div>
      </div>
    </section>

    <section id="tab-audience" class="tabpanel" data-tab="audience">
      <div class="grid">
        <div class="section-label">Audience</div>
        <div class="card span-6">
          <div class="card-title">WNY metros __TAG_AUDIENCE__</div>
          <table>
            <thead><tr><th>Metro</th><th>Sessions</th><th>Share</th></tr></thead>
            <tbody>
              <tr><td>Buffalo</td><td>—</td><td>—</td></tr>
              <tr><td>Rochester</td><td>—</td><td>—</td></tr>
              <tr><td>Syracuse</td><td>—</td><td>—</td></tr>
              <tr><td>Niagara-area</td><td>—</td><td>—</td></tr>
              <tr><td>Other NY / unknown</td><td>—</td><td>—</td></tr>
            </tbody>
          </table>
          <div class="meta">City report not pulled (not cheap enough for v1).</div>
        </div>
        <div class="card span-6">
          <div class="card-title">Device / browser __TAG_AUDIENCE__</div>
          <table>
            <thead><tr><th>Device</th><th>Sessions</th><th>Browser</th><th>Share</th></tr></thead>
            <tbody>
              <tr><td>mobile</td><td>—</td><td>Chrome</td><td>—</td></tr>
              <tr><td>desktop</td><td>—</td><td>Safari</td><td>—</td></tr>
              <tr><td>tablet</td><td>—</td><td>Other</td><td>—</td></tr>
            </tbody>
          </table>
          <div class="meta">Device report not pulled (not cheap enough for v1).</div>
        </div>
      </div>
    </section>

    <section id="tab-named" class="tabpanel" data-tab="named">
      <div class="grid">
        <div class="section-label">Named fills</div>
        <div class="banner gate span-12">Role-gated: Marketing sees aggregates only. The PII table is gated for sales. This page does not authenticate — the blur/disabled table is the intended sales-only slot.</div>
        <div class="card span-6">
          <div class="card-title">Marketing aggregates __TAG_NAMED__</div>
          <div class="kpi" id="namedKpi">__NAMED_KPI__</div>
          <div class="meta" id="namedMeta">__NAMED_META__</div>
        </div>
        <div class="card span-6">
          <div class="card-title">Warehouse source</div>
          <div class="meta" style="margin-top:10px">Reads <b>web_funnel_named_fills_v1</b> (bounded). Prefer source=new-site-estimate when present. Dual-domain history (wny calculator / leads@) stays for compare. Exclude list is documented in the handler comment — not shown as live rows.</div>
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
          <div class="meta disabled-note">Disabled. Not live warehouse rows. Marketing JSON never includes PII.</div>
        </div>
      </div>
    </section>

    <div class="footer">
      <div><b>Data sources</b> — GA4 property 408492342 / G-V02RZFR4SZ. Warehouse named fills source=new-site-estimate + leads@. Meta if wired (not wired). Primary CTA: www.happyslr.com/estimate. Dual-domain history: happyslr.com + wny.happyslr.com. Instant Form / 3PL excluded from website leads. <a class="jsonlink" id="jsonLink" href="__JSON_HREF__">JSON</a></div>
    </div>
  </div>
<script>
var initialPayload = __PAYLOAD__;
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
  function num(v) {
    if (v == null || v === '') return '—';
    return String(v);
  }
  function pct(v) {
    if (v == null || v === '') return '—';
    return (Number(v) * 100).toFixed(1) + '%';
  }
  function delta(v) {
    if (v == null || v === '') return '';
    var n = Number(v);
    var cls = n < 0 ? 'down' : 'up';
    var sign = n > 0 ? '+' : '';
    return 'vs prior <span class="delta ' + cls + '">' + sign + (n * 100).toFixed(1) + '%</span>';
  }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }
  function setHtml(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }
  function tileStatus(data, name) {
    return ((data.tiles || {})[name] || {}).status || 'example';
  }
  function markTiles(data) {
    document.querySelectorAll('[data-tile]').forEach(function(tag) {
      var status = tileStatus(data, tag.getAttribute('data-tile'));
      tag.classList.toggle('live', status === 'live');
      if (status === 'live') tag.textContent = 'LIVE';
      else if (status === 'not_wired') tag.textContent = 'NOT WIRED';
      else if (tag.textContent === 'LIVE') tag.textContent = 'EXAMPLE';
    });
    var live = data.live_fields || [];
    var title = document.getElementById('titleTag');
    if (title) {
      title.textContent = live.length ? 'LIVE + EXAMPLE' : 'EXAMPLE DATA';
      title.classList.toggle('live', live.length > 0);
    }
  }
  function paint(data) {
    data = data || {};
    var o = data.overview || {};
    var f = data.funnel || {};
    var n = data.named_fills || {};
    var acq = data.acquisition || {};
    var content = data.content || {};
    markTiles(data);
    setText('kpiSessions', num(o.sessions));
    setText('kpiUsers', num(o.users));
    setText('kpiNewRet', (o.new_share == null && o.returning_share == null) ? '—' : (pct(o.new_share) + ' / ' + pct(o.returning_share)));
    setText('kpiPageviews', num(o.pageviews));
    setText('kpiPagesPer', o.pages_per_session == null ? '—' : Number(o.pages_per_session).toFixed(2));
    setText('kpiBounce', (o.bounce_rate == null && o.engaged_rate == null) ? '—' : (pct(o.bounce_rate) + ' / ' + pct(o.engaged_rate)));
    setText('kpiEngage', o.avg_engagement_label || '—');
    setText('kpiVsPrior', o.vs_prior_sessions == null ? '—' : ((o.vs_prior_sessions > 0 ? '+' : '') + (o.vs_prior_sessions * 100).toFixed(1) + '%'));
    setText('kpiBrand', num(o.brand_site_sessions));
    setText('kpiEstimate', num(o.estimate_calc_sessions));
    setText('kpiCta', tileStatus(data, 'cta_taps') === 'live' ? num(o.cta_taps) : '—');
    setText('kpiFbPost', tileStatus(data, 'fb_post_sessions') === 'live' ? num(o.fb_organic_sessions) : '—');
    setHtml('metaSessions', delta(o.vs_prior_sessions));
    setHtml('metaBrand', delta(o.vs_prior_brand));
    setHtml('metaEstimate', delta(o.vs_prior_estimate));
    setText('funnelBrand', num(f.brand_site_sessions));
    setText('funnelTop', num(f.estimate_lp_visits));
    setText('stepLp', num(f.estimate_lp_visits));
    setText('stepStart', num(f.starts));
    setText('stepAddress', num(f.address));
    setText('stepBill', num(f.bill));
    setText('stepSubmit', num(f.submit));
    setText('stepNamed', num(f.named_fill));
    var rates = f.rates || {};
    setText('metaStart', pct(rates.start_of_estimate_lp) + ' of estimate/LP');
    setText('metaAddress', pct(rates.address_of_start) + ' of start');
    setText('metaBill', pct(rates.bill_of_address) + ' of address');
    setText('metaSubmit', pct(rates.submit_of_bill) + ' of bill · estimate_submit only');
    setText('metaNamed', pct(rates.named_fill_of_submit) + ' of submit');
    setText('scoreboardKpi', num(f.named_fill));
    setText('scoreboardMeta',
      'Named fills ' + num(f.named_fill) +
      ' · submit / estimate/LP ' + pct(rates.submit_of_estimate_lp) +
      ' · start→submit ' + pct(rates.start_to_submit) +
      ' · CPA when paid — (Meta not wired)');
    var leak = document.getElementById('leakAlert');
    if (leak) leak.classList.toggle('is-off', !f.alert_visits_up_starts_zero);
    setText('namedKpi', num(n.live_count));
    setText('namedMeta',
      'Live named fills ' + num(n.live_count) +
      ' · excluded tests ' + num(n.excluded_count) +
      ' · new-site-estimate ' + num(n.new_site_estimate) +
      ' · legacy leads@ ' + num(n.legacy_wny) +
      '. Counts only — no names, emails, or phones for Marketing.');
    var acqBody = document.getElementById('acqBody');
    if (acqBody) {
      var rows = acq.rows || [];
      acqBody.innerHTML = rows.length ? rows.map(function(row) {
        return '<tr><td>' + (row.channel || '') + '</td><td>' + (row.source_medium || '') +
          '</td><td>' + num(row.sessions) + '</td><td>' + num(row.users) + '</td></tr>';
      }).join('') : '<tr><td colspan="4">No GA4 acquisition rows yet.</td></tr>';
    }
    setText('fbSplitMeta', 'Organic social ' + num(acq.fb_organic) + ' · Paid social ' + num(acq.fb_paid) + ' · GA4 only, not Ads Manager.');
    var landings = content.top_landings || [];
    var landingHtml = landings.length ? landings.slice(0, 5).map(function(row) {
      return '<tr><td>' + (row.page || '') + '</td><td>' + num(row.sessions) + '</td></tr>';
    }).join('') : '<tr><td colspan="2">No path report yet.</td></tr>';
    var landingBody = document.getElementById('landingBody');
    var pagesBody = document.getElementById('pagesBody');
    if (landingBody) landingBody.innerHTML = landingHtml;
    if (pagesBody) pagesBody.innerHTML = landingHtml;
    var banner = document.getElementById('statusBanner');
    if (banner) {
      var live = (data.live_fields || []).join(', ') || 'none';
      var stub = (data.stub_fields || []).join(', ') || 'none';
      banner.textContent = 'LIVE: ' + live + '. EXAMPLE / not-wired: ' + stub +
        '. Funnel top is estimate/LP, not all-site. Instant Form / 3PL are not website leads. Meta spend was not invented. Charles QA before treating as live.';
    }
    paintChrome(data);
  }
  function query() {
    return new URLSearchParams({
      start: document.getElementById('startDate').value,
      end: document.getElementById('endDate').value,
      domain: document.getElementById('domain').value,
      test_filter: document.getElementById('testFilter').checked ? '1' : '0',
      compare_prior: document.getElementById('comparePrior').checked ? '1' : '0',
      format: 'json'
    }).toString();
  }
  function paintChrome(data) {
    var start = document.getElementById('startDate').value;
    var end = document.getElementById('endDate').value;
    var domain = document.getElementById('domain');
    var testOn = document.getElementById('testFilter').checked;
    var compare = document.getElementById('comparePrior').checked;
    document.getElementById('chromeLabel').textContent =
      'Range ' + start + ' → ' + end + ' ET · domain ' + domain.options[domain.selectedIndex].text +
      ' · test filter ' + (testOn ? 'ON' : 'OFF') + ' · compare prior ' + (compare ? 'ON' : 'OFF');
    document.querySelectorAll('.vs-prior').forEach(function(el) {
      el.classList.toggle('is-off', !compare);
    });
    var chip = document.getElementById('excludeChip');
    if (chip) chip.classList.toggle('is-off', !testOn);
    var link = document.getElementById('jsonLink');
    if (link) link.href = '/api/website_traffic?' + query();
  }
  async function load() {
    var q = query();
    document.getElementById('jsonLink').href = '/api/website_traffic?' + q;
    var res = await fetch('/api/website_traffic?' + q);
    var data = await res.json();
    if (!res.ok) {
      document.getElementById('statusBanner').textContent = data.error || 'Failed to load Website Traffic.';
      return;
    }
    paint(data);
  }
  document.getElementById('apply').addEventListener('click', load);
  document.getElementById('testFilter').addEventListener('change', function() { paintChrome(); });
  document.getElementById('comparePrior').addEventListener('change', function() { paintChrome(); });
  document.getElementById('domain').addEventListener('change', function() { paintChrome(); });
  paint(initialPayload);
})();
</script>
</body>
</html>
"""
    painted = apply_first_paint(html, data, start, end)
    return (
        painted.replace("__PAYLOAD__", json_for_script(data))
        .replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css())
        .replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("website_traffic"))
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        want_json = (qs.get("format", [""])[0] or "").lower() == "json"
        payload = None
        try:
            payload = build_payload(qs)
        except AttributeError as e:
            payload = metric.example_degrade_payload(error=str(e))
        except Exception as e:
            # Marketing HTML smoke must not 500 after a compute miss.
            payload = metric.example_degrade_payload(error=str(e))
            if want_json and "exclusion_reason" not in str(e):
                body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        try:
            if want_json:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(payload=payload).encode("utf-8")
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
