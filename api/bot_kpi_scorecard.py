# -*- coding: utf-8 -*-

"""Vercel Python function: /api/bot_kpi_scorecard

Weekly Bot KPI scorecard Charles opens to score Designer / Social / Boris / Data.

HTML by default. `?format=json` is enough to QA without the HTML.

America/New_York week window (default = current NY ISO week).
Accepts `year` + `week` or `start` / `end` (YYYY-MM-DD).

Data owns scoring (`api/metrics/bot_kpi.py`). This file is the page.
Not on warm_cache. No GHL join. No Charles widget.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
METRICS_DIR = API_DIR / "metrics"
for path in (str(API_DIR), str(METRICS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from dashboard_nav import dashboard_nav_css, render_dashboard_nav
from bot_kpi import compute, get_db, parse_int


def _qs_int(qs: dict[str, list[str]], key: str) -> int | None:
    return parse_int((qs.get(key, [""])[0] or "").strip() or None)


def _qs_text(qs: dict[str, list[str]], key: str) -> str | None:
    value = (qs.get(key, [""])[0] or "").strip()
    return value or None


def build_payload(qs: dict[str, list[str]]) -> dict:
    year = _qs_int(qs, "year")
    week = _qs_int(qs, "week")
    start = _qs_text(qs, "start")
    end = _qs_text(qs, "end")
    db = None
    db_error = None
    try:
        db = get_db()
    except Exception as exc:
        db_error = str(exc)
    payload = compute(db, year=year, week=week, start=start, end=end)
    if db_error:
        payload["db_error"] = db_error
    return payload


def _fmt_value(value, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if percent and isinstance(value, (int, float)):
        return f"{float(value) * 100:.1f}%"
    if isinstance(value, float):
        return f"{value:.4g}"
    return html.escape(str(value))


def _fmt_goal(goal, goal_label: str | None = None) -> str:
    if goal_label:
        return html.escape(str(goal_label))
    if goal is None:
        return "—"
    if isinstance(goal, float) and 0 < goal < 1:
        return f"{goal * 100:.0f}%"
    return html.escape(str(goal))


def _is_percent_row(row: dict) -> bool:
    formula = str(row.get("formula") or "")
    name = str(row.get("name") or "")
    return " / " in formula or "→" in name


def render_lane(lane_key: str, lane: dict) -> str:
    rows = lane.get("rows") or []
    note = html.escape(str(lane.get("note") or ""))
    kind = html.escape(str(lane.get("kind") or ""))
    label = html.escape(str(lane.get("label") or lane_key))
    tr = []
    for row in rows:
        status = html.escape(str(row.get("status") or "unknown"))
        percent = _is_percent_row(row)
        tr.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('name') or ''))}</td>"
            f"<td>{_fmt_value(row.get('value'), percent=percent)}</td>"
            f"<td>{_fmt_goal(row.get('goal'), row.get('goal_label'))}</td>"
            f"<td><span class=\"pill status-{status}\">{status}</span></td>"
            f"<td class=\"notes\">{html.escape(str(row.get('notes') or ''))}</td>"
            "</tr>"
        )
    rows_html = "\n".join(tr) if tr else "<tr><td colspan='5'>No rows</td></tr>"
    extra = f"<div class='lane-note'>{note}</div>" if note else ""
    return f"""
      <section class="card lane">
        <div class="lane-head">
          <div>
            <div class="lane-title">{label}</div>
            <div class="lane-kind">{kind}</div>
          </div>
        </div>
        {extra}
        <div class="tableWrap">
          <table>
            <thead>
              <tr><th>KPI</th><th>Value</th><th>Goal</th><th>Status</th><th>Notes</th></tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
      </section>
    """


def render_html(payload: dict) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("bot_kpi_scorecard")
    week = payload.get("week") or {}
    year = week.get("iso_year") or datetime.now(ZoneInfo("America/New_York")).year
    week_n = week.get("iso_week") or 1
    start = week.get("start") or ""
    end = week.get("end") or ""
    week_id = week.get("id") or ""
    json_q = urlencode({"format": "json", "year": year, "week": week_n})
    lanes = payload.get("lanes") or {}
    lanes_html = "\n".join(
        render_lane(key, lanes.get(key) or {})
        for key in ("designer", "social", "boris", "data")
    )
    db_error = payload.get("db_error")
    banner = ""
    if db_error:
        banner = (
            "<div class='banner'>"
            + html.escape(
                "Firestore client unavailable — warehouse rows stay null. " + str(db_error)
            )
            + "</div>"
        )
    lead = html.escape(str(payload.get("lead_definition") or ""))
    html_page = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Weekly Bot KPI</title>
  <style>
    :root {{
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#059669; --red:#dc2626; --amber:#d97706; --blue:#2563eb;
    }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }}
    .wrap {{ padding:22px; max-width:1180px; margin:0 auto; }}
    .topbar {{ display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }}
    .title {{ font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }}
    .subtitle {{ margin-top:4px; color:var(--muted); font-size:13px; max-width:820px; }}
    .accentline {{ height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,#10b981 0%, #2563eb 55%, rgba(37,99,235,0) 100%); margin-top:10px; }}
    {nav_css}
    .navbtn {{ display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }}
    .navbtn.active {{ background:rgba(16,185,129,.10); border-color:rgba(16,185,129,.45); color:#0f766e; }}
    .filters {{ display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap; }}
    .filters label {{ display:block; font-size:12px; color:var(--muted); font-weight:900; margin-bottom:4px; }}
    input, button {{ background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }}
    button {{ background:#10b981; border-color:#10b981; color:#fff; font-weight:900; cursor:pointer; }}
    .jsonlink {{ color:#0f766e; font-weight:800; text-decoration:none; align-self:center; }}
    .banner {{ margin-top:14px; padding:12px 14px; border-radius:12px; border:1px solid #fde68a; background:#fffbeb; color:#92400e; font-size:13px; font-weight:700; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); margin-top:14px; }}
    .lane-title {{ font-size:18px; font-weight:950; color:#1a2b4a; }}
    .lane-kind {{ margin-top:2px; color:var(--muted2); font-size:12px; font-weight:800; letter-spacing:.03em; text-transform:uppercase; }}
    .lane-note {{ margin:10px 0; color:var(--muted); font-size:13px; }}
    .tableWrap {{ overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:720px; }}
    th, td {{ border-bottom:1px solid var(--border); padding:9px 10px; text-align:left; font-size:13px; vertical-align:top; }}
    th {{ color:#64748b; font-weight:900; background:#fafbfc; }}
    td.notes {{ color:#475569; max-width:420px; }}
    .pill {{ display:inline-block; padding:3px 8px; border-radius:999px; font-size:11px; font-weight:900; letter-spacing:.02em; }}
    .status-hit {{ background:#d1fae5; color:#047857; }}
    .status-miss {{ background:#fee2e2; color:#b91c1c; }}
    .status-baseline_pending, .status-pending, .status-not_wired, .status-unknown, .status-later, .status-informational, .status-not_live_yet {{ background:#fef3c7; color:#92400e; }}
    .meta {{ color:var(--muted); font-size:13px; }}
    .contract {{ white-space:pre-wrap; color:#334155; font-size:13px; line-height:1.45; }}
    @media (max-width:640px) {{ .wrap {{ padding:12px; }} .topbar {{ padding:12px; }} .title {{ font-size:20px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Weekly Bot KPI</div>
        <div class="subtitle">{lead} Charles scores four bot lanes here. Data owns the numbers. Missing stays null.</div>
        <div class="accentline"></div>
        {nav_html}
      </div>
      <form class="filters" method="get" action="/api/bot_kpi_scorecard">
        <div><label for="year">Year</label><input id="year" name="year" type="number" value="{html.escape(str(year))}" /></div>
        <div><label for="week">ISO week</label><input id="week" name="week" type="number" min="1" max="53" value="{html.escape(str(week_n))}" /></div>
        <button type="submit">Apply</button>
        <a class="jsonlink" href="/api/bot_kpi_scorecard?{html.escape(json_q)}">JSON</a>
      </form>
    </div>
    {banner}
    <div class="card">
      <div class="lane-title">Week {html.escape(str(week_id))}</div>
      <div class="meta">{html.escape(str(start))} → {html.escape(str(end))} ({html.escape(str(payload.get('timezone') or ''))}). Calculator GA4 is live. Volume stays baseline pending until 14 instrumented days. No Facebook reach. No GHL join. Not on warm_cache.</div>
    </div>
    {lanes_html}
    <div class="card">
      <div class="lane-title">Contract</div>
      <div class="contract">Lead = estimate_submit or wix_form_submit.
Designer conversion is scored live against 2% and 25% when warehouse/GA4 numbers exist.
If docs/GA4 are missing, value is null and status is not_wired or unknown.
Social does not invent reach. Boris is a checklist (PR 129 / 270e335 is a known fact, not a live hang probe).
Data checks bounded opps_scanned + empty warm_cache urls. Bill $ stays not_wired without an export.
Charles is scored in chat/ClickUp — no widget on this page.</div>
    </div>
  </div>
</body>
</html>
"""
    return html_page


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            payload = build_payload(qs)
            want_json = (qs.get("format", [""])[0] or "").strip().lower() == "json"
            if want_json:
                body = json.dumps(payload, default=str).encode("utf-8")
                content_type = "application/json"
            else:
                body = render_html(payload).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc), "metric": "Weekly Bot KPI Scorecard"}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
