# -*- coding: utf-8 -*-

"""Growth command center view model.

The demo fixture is sample data for Nov 1–15, 2026. Charts and costs are
calculated from the stored daily counts. Live mode uses the paid-social
adapter and leaves a missing source unavailable. Territory opportunities
are counted for the adapter and are not a funnel stage.

Field mapping, live adapter:
- Impressions and outbound clicks: Meta account insights, read-only.
  Lead actions are not requested. Landing-page views are not visits.
- Landing visits: GA4 paid sessions on property 408492342 /
  G-V02RZFR4SZ. The website traffic paid-session rule. A failed read
  stays null. Meta landing-page views are not visits.
- Form starts: calculator estimate_start from that same paid traffic.
  estimate_submit, Instant Form, and 3PL are not form starts. A failed
  read stays null.
- Leads: pipeline 7nSEgeoBYXZiIS7x41Jy, Lead Gen Source
  hd5QqHEOVSsPom5bJ32P strips to Inbound. Blank, 3PL, and Doors do not.
- Demos: territory appointment disposition in the window, those contacts.
- Sold: contact sold date P9oBjgbZjJdeE0OkBj9T, those contacts.
  The sales metric contract is unchanged.
- Account act_1624979685613708. No campaign writes.
"""

from __future__ import annotations

import calendar
import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ACCOUNT_TZ = ZoneInfo("America/Phoenix")
CRM_TZ = ZoneInfo("America/New_York")
ACCOUNT_TZ_NAME = "America/Phoenix"
CRM_TZ_NAME = "America/New_York"

LEAD_GOALS = {"2026-10": 10, "2026-11": 20}
CPL_TARGET = 25
DEMO_COST_TARGET = 50
SOLD_CPA_TARGET = 200

FIXTURE_START = date(2026, 11, 1)
FIXTURE_END = date(2026, 11, 15)
FIXTURE_AS_OF = datetime(2026, 11, 16, 0, 0, tzinfo=ACCOUNT_TZ)
GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID = "408492342"
LEAD_PIPELINE_ID = "7nSEgeoBYXZiIS7x41Jy"
SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"
SOLD_DATE_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"

DAILY_LEADS = [0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1]
DAILY_SPEND = [16.0] * 15
DAILY_IMPRESSIONS = [1600] * 15
DAILY_DEMOS = [0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]
DAILY_SOLD = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]

SAMPLE_ADS = (
    {
        "id": "sample-ad-local-savings",
        "name": "Local savings",
        "copy": "Lower the monthly bill",
        "spend": 120.0,
        "impressions": 10000,
        "outbound_clicks": 180,
        "leads": 4,
        "status": "Active",
    },
    {
        "id": "sample-ad-solar-explained",
        "name": "Solar explained",
        "copy": "How the system pays off",
        "spend": 80.0,
        "impressions": 8000,
        "outbound_clicks": 140,
        "leads": 2,
        "status": "Active",
    },
    {
        "id": "sample-ad-homeowner-story",
        "name": "Homeowner story",
        "copy": "A neighbor's first year",
        "spend": 40.0,
        "impressions": 6000,
        "outbound_clicks": 80,
        "leads": 2,
        "status": "Active",
    },
)

STAGE_ORDER = (
    ("impressions", "Impressions"),
    ("outbound_clicks", "Outbound clicks"),
    ("landing_visits", "Landing visits"),
    ("form_starts", "Form starts"),
    ("leads", "Leads created"),
    ("demos", "Demos"),
    ("sold", "Sold"),
)


def spread(total: int, count: int) -> list[int]:
    """Split an integer total across count days. Earlier days take the remainder."""
    if count <= 0:
        return []
    base, remainder = divmod(int(total), count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


DAILY_CLICKS = spread(400, 15)
DAILY_VISITS = spread(320, 15)
DAILY_FORM_STARTS = spread(40, 15)


def fixture_days() -> list[dict]:
    days = []
    for index, current in enumerate(_dates(FIXTURE_START, FIXTURE_END)):
        days.append(
            {
                "date": current.isoformat(),
                "spend": DAILY_SPEND[index],
                "impressions": DAILY_IMPRESSIONS[index],
                "outbound_clicks": DAILY_CLICKS[index],
                "landing_visits": DAILY_VISITS[index],
                "form_starts": DAILY_FORM_STARTS[index],
                "leads": DAILY_LEADS[index],
                "demos": DAILY_DEMOS[index],
                "sold": DAILY_SOLD[index],
                "known": True,
            }
        )
    return days


def _dates(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def resolve_demo_range(qs: dict | None) -> tuple[date, date, str]:
    """Demo clock is the fixture as-of, not the wall clock."""
    query = qs or {}
    preset = " ".join(str((query.get("preset") or [""])[0] or "").split())
    start = _parse_day((query.get("start") or [""])[0] if query.get("start") else "")
    end = _parse_day((query.get("end") or [""])[0] if query.get("end") else "")
    cutoff = FIXTURE_AS_OF.date() - timedelta(days=1)
    if preset == "this-month":
        return date(cutoff.year, cutoff.month, 1), cutoff, preset
    if preset == "last-month":
        year = cutoff.year
        month = cutoff.month - 1
        if month == 0:
            year -= 1
            month = 12
        last = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last), preset
    if preset == "last-30":
        return cutoff - timedelta(days=29), cutoff, preset
    if start and end and end >= start:
        return start, end, "custom"
    return FIXTURE_START, FIXTURE_END, "fixture"


def demo_model(qs: dict | None = None) -> dict:
    start, end, preset = resolve_demo_range(qs)
    by_date = {row["date"]: row for row in fixture_days()}
    days = []
    for current in _dates(start, end):
        stored = by_date.get(current.isoformat())
        if stored:
            days.append(dict(stored))
        else:
            days.append(
                {
                    "date": current.isoformat(),
                    "spend": None,
                    "impressions": None,
                    "outbound_clicks": None,
                    "landing_visits": None,
                    "form_starts": None,
                    "leads": None,
                    "demos": None,
                    "sold": None,
                    "known": False,
                }
            )
    full_fixture = start == FIXTURE_START and end == FIXTURE_END
    goal_month = _goal_month_for_range(start, end, qs)
    return summarize(
        {
            "is_demo": True,
            "validated": False,
            "preset": preset,
            "range_start": start,
            "range_end": end,
            "goal_month": goal_month,
            "as_of": FIXTURE_AS_OF,
            "days": days,
            "ads": _sample_ads() if full_fixture else {
                "status": "unavailable",
                "reason": "Ad rows are stored for the Nov 1–15, 2026 sample. This range does not reuse them.",
                "rows": [],
            },
            "submissions": {"accepted": 8, "delivered": 8} if full_fixture else None,
            "tracking": "healthy" if full_fixture else "unknown",
            "territory_opps": None,
            "spend_gap": None,
            "window_totals": None,
        }
    )


def unavailable_model(reason: str, qs: dict | None = None) -> dict:
    today = datetime.now(CRM_TZ).date()
    start = today.replace(day=1)
    return summarize(
        {
            "is_demo": False,
            "validated": False,
            "preset": "unavailable",
            "range_start": start,
            "range_end": today,
            "goal_month": f"{start.year:04d}-{start.month:02d}",
            "as_of": datetime.now(CRM_TZ),
            "days": [
                {
                    "date": current.isoformat(),
                    "spend": None,
                    "impressions": None,
                    "outbound_clicks": None,
                    "landing_visits": None,
                    "form_starts": None,
                    "leads": None,
                    "demos": None,
                    "sold": None,
                    "known": False,
                }
                for current in _dates(start, today)
            ],
            "ads": {"status": "unavailable", "reason": reason, "rows": []},
            "submissions": None,
            "tracking": "unknown",
            "territory_opps": None,
            "spend_gap": None,
            "window_totals": None,
            "read_error": reason,
        }
    )


def live_model(paid: dict, qs: dict | None = None) -> dict:
    """Map a paid-social payload onto the command center. Never fills sample numbers."""
    start_local = datetime.fromisoformat(paid["window_start_local"])
    end_local = datetime.fromisoformat(paid["window_end_local"])
    start = start_local.date()
    end = (end_local - timedelta(days=1)).date()
    if end < start:
        end = start
    funnel = {step["key"]: step for step in paid.get("funnel") or []}
    leads_step = funnel.get("leads_created") or {}
    views = funnel.get("ad_views") or {}
    outbound = paid.get("outbound_clicks") or {}
    demos = paid.get("demos") or {}
    sales = paid.get("sales") or {}
    spend = paid.get("spend") or {}
    gap = spend.get("gap")
    leads_series = _series_map(leads_step.get("series"))
    view_series = _series_map(views.get("series"))
    outbound_series = _series_map(outbound.get("series"))
    demo_series = _series_map(demos.get("series"))
    sale_series = _series_map(sales.get("series"))
    spend_series = _series_map(spend.get("series"))
    visits_ok, visits_total, visit_series = _ready_series(
        _live_block(paid, "landing_visits", "website_visitors")
    )
    forms_ok, forms_total, form_series = _ready_series(_live_block(paid, "form_starts"))
    spend_complete = gap is None and spend.get("spend") is not None and _series_closed(spend_series, start, end)
    days = []
    for current in _dates(start, end):
        key = current.isoformat()
        days.append(
            {
                "date": key,
                "spend": spend_series.get(key) if spend_complete else None,
                "impressions": view_series.get(key) if views.get("total") is not None else None,
                "outbound_clicks": outbound_series.get(key) if outbound.get("total") is not None else None,
                "landing_visits": visit_series.get(key) if visits_ok else None,
                "form_starts": form_series.get(key) if forms_ok else None,
                "leads": leads_series.get(key) if leads_step.get("status") == "ok" else None,
                "demos": demo_series.get(key) if demos.get("status") == "ok" else None,
                "sold": sale_series.get(key) if sales.get("status") == "ok" else None,
                "known": True,
            }
        )
    territory = None
    opp_step = funnel.get("opps_created") or {}
    if opp_step.get("status") == "ok":
        territory = {
            "total": opp_step.get("total"),
            "by_territory": opp_step.get("by_territory") or {},
            "note": "Territory opportunities are not a funnel stage.",
        }
    totals = {
        "impressions": views.get("total"),
        "outbound_clicks": outbound.get("total"),
        "landing_visits": visits_total if visits_ok else None,
        "form_starts": forms_total if forms_ok else None,
        "leads": leads_step.get("total"),
        "demos": demos.get("total"),
        "sold": sales.get("total"),
        "spend": None if gap else spend.get("spend"),
    }
    return summarize(
        {
            "is_demo": False,
            "validated": False,
            "preset": (qs or {}).get("preset", ["live"])[0] if qs else "live",
            "range_start": start,
            "range_end": end,
            "goal_month": _goal_month_for_range(start, end, qs),
            "as_of": datetime.now(CRM_TZ),
            "days": days,
            "ads": {
                "status": "unavailable",
                "reason": (
                    "Ad-level rows are not on this read. "
                    "Account totals are not split into guessed ads."
                ),
                "rows": [],
            },
            "submissions": None,
            "tracking": "unknown",
            "territory_opps": territory,
            "spend_gap": gap,
            "window_totals": totals,
            "spend_unmatched_note": spend.get("note"),
        }
    )


def _live_block(paid: dict, *keys: str) -> dict:
    funnel = {}
    for step in paid.get("funnel") or []:
        if isinstance(step, dict) and step.get("key"):
            funnel[str(step.get("key"))] = step
    for key in keys:
        block = paid.get(key)
        if isinstance(block, dict):
            return block
        found = funnel.get(key)
        if isinstance(found, dict):
            return found
    return {}


def _ready_series(block: dict) -> tuple[bool, int | None, dict]:
    """Use a stage only when the read succeeded. A failed total of 0 stays blank."""
    if block.get("status") != "ok":
        return False, None, {}
    total = block.get("total")
    if total is None or isinstance(total, bool):
        return False, None, {}
    try:
        number = int(total)
    except (TypeError, ValueError):
        return False, None, {}
    return True, number, _series_map(block.get("series"))


def _series_map(series: list | None) -> dict[str, int | float | None]:
    mapped: dict[str, int | float | None] = {}
    for point in series or []:
        if not isinstance(point, dict):
            continue
        key = str(point.get("date") or "")[:10]
        if key:
            mapped[key] = point.get("value")
    return mapped


def _series_closed(series: dict, start: date, end: date) -> bool:
    if not series:
        return False
    for current in _dates(start, end):
        if series.get(current.isoformat()) is None:
            return False
    return True


def _goal_month_for_range(start: date, end: date, qs: dict | None) -> str | None:
    chosen = ""
    if qs and qs.get("goal"):
        chosen = str(qs.get("goal")[0] or "")
    if len(chosen) >= 7 and chosen[4] == "-":
        return chosen[:7]
    if start.year == end.year and start.month == end.month:
        return f"{start.year:04d}-{start.month:02d}"
    return None


def _sample_ads() -> dict:
    rows = []
    for ad in SAMPLE_ADS:
        rows.append(
            {
                **ad,
                "ctr": _rate(ad["outbound_clicks"], ad["impressions"]),
                "ctr_label": format_percent(ad["outbound_clicks"], ad["impressions"], 2),
                "cpl": _unit(ad["spend"], ad["leads"]),
                "cpl_label": format_dollars(_unit(ad["spend"], ad["leads"])),
                "tone": _cost_tone(_unit(ad["spend"], ad["leads"]), CPL_TARGET),
            }
        )
    spend = sum(row["spend"] for row in rows)
    impressions = sum(row["impressions"] for row in rows)
    clicks = sum(row["outbound_clicks"] for row in rows)
    leads = sum(row["leads"] for row in rows)
    return {
        "status": "ok",
        "rejected": 0,
        "active": len(rows),
        "delivering": len(rows),
        "rows": rows,
        "total": {
            "name": "Total",
            "spend": spend,
            "impressions": impressions,
            "outbound_clicks": clicks,
            "leads": leads,
            "ctr_label": format_percent(clicks, impressions, 2),
            "cpl_label": format_dollars(_unit(spend, leads)),
            "tone": _cost_tone(_unit(spend, leads), CPL_TARGET),
        },
    }


def summarize(spec: dict) -> dict:
    start: date = spec["range_start"]
    end: date = spec["range_end"]
    days: list[dict] = list(spec["days"])
    goal_month = spec.get("goal_month")
    as_of: datetime = spec["as_of"]
    cutoff_day = as_of.date()
    totals = spec.get("window_totals") or {}
    is_demo = bool(spec.get("is_demo"))

    def total_for(key: str):
        if key in totals and spec.get("window_totals") is not None:
            return totals.get(key)
        values = [day.get(key) for day in days]
        if any(value is None for value in values):
            return None
        if key == "spend":
            return round(sum(float(value) for value in values), 2)
        return int(sum(int(value) for value in values))

    impressions = total_for("impressions")
    outbound_clicks = total_for("outbound_clicks")
    visits = total_for("landing_visits")
    form_starts = total_for("form_starts")
    leads = total_for("leads")
    demos = total_for("demos")
    sold = total_for("sold")
    spend = None if spec.get("spend_gap") else total_for("spend")
    missing_days = sum(1 for day in days if not day.get("known", True))

    goal = LEAD_GOALS.get(goal_month) if goal_month else None
    pace = _pace(goal_month, goal, start, end, cutoff_day, days, leads if spec.get("window_totals") else None)
    kpis = {
        "leads": _lead_kpi(leads, goal, pace),
        "cpl": _cost_kpi(spend, leads, CPL_TARGET, "lead"),
        "demos": {
            "value": demos,
            "display": format_count(demos),
            "note": "No count goal",
            "tone": "neutral",
        },
        "demo_cost": _cost_kpi(spend, demos, DEMO_COST_TARGET, "demo"),
        "sold": {
            "value": sold,
            "display": format_count(sold),
            "note": "Cohort can still change",
            "tone": "neutral",
        },
        "cpa": _cost_kpi(spend, sold, SOLD_CPA_TARGET, "sold deal"),
        "spend": _spend_kpi(spend, spec.get("ads") or {}, spec.get("spend_gap")),
    }
    stages = _stages(
        [
            ("impressions", "Impressions", impressions, "Sample Meta impressions" if is_demo else "Meta account impressions"),
            ("outbound_clicks", "Outbound clicks", outbound_clicks, "Sample Meta outbound clicks" if is_demo else "Meta outbound clicks"),
            ("landing_visits", "Landing visits", visits, f"GA4 paid sessions {GA4_MEASUREMENT_ID}"),
            ("form_starts", "Form starts", form_starts, "Form starts"),
            ("leads", "Leads created", leads, "Source-filtered CRM leads"),
            ("demos", "Demos", demos, "CRM demos for those leads"),
            ("sold", "Sold", sold, "CRM sold date for those leads"),
        ]
    )
    bot = _bot(spec, kpis, pace)
    recommendations = _recommendations(spec, kpis, visits, form_starts, spend, leads)
    lead_chart = _lead_chart(spec, pace, leads)
    cost_charts = {
        "cpl": _cost_chart(days, "leads", CPL_TARGET, "Cost per lead", "$25 goal"),
        "demo": _cost_chart(days, "demos", DEMO_COST_TARGET, "Cost per demo", "$50 goal"),
        "cpa": _cost_chart(days, "sold", SOLD_CPA_TARGET, "Sold CPA", "$200 goal"),
    }
    return {
        "is_demo": is_demo,
        "validated": False,
        "badge": "SAMPLE DATA" if is_demo else None,
        "title": "Growth command center",
        "subtitle": "Paid acquisition through sold deals",
        "preset": spec.get("preset") or "",
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "range_label": format_range(start, end),
        "as_of_label": _as_of_label(as_of, is_demo),
        "goal_month": goal_month,
        "goal_month_label": _month_label(goal_month),
        "pace": pace,
        "missing_days": missing_days,
        "kpis": kpis,
        "stages": stages,
        "funnel_directional": True,
        "bot": bot,
        "recommendations": recommendations,
        "lead_chart": lead_chart,
        "cost_charts": cost_charts,
        "ads": spec.get("ads") or {"status": "unavailable", "reason": "Unavailable", "rows": []},
        "territory_opps": spec.get("territory_opps"),
        "spend_gap": spec.get("spend_gap"),
        "spend_note": spec.get("spend_unmatched_note") or (
            "Sample spend is stored on the fixture and calculated into the costs."
            if is_demo
            else "Unmatched Meta spend. This is Meta account spend. It is not tied to a lead or an opp."
        ),
        "read_error": spec.get("read_error"),
        "sources": _sources(is_demo, impressions, outbound_clicks, visits, form_starts),
        "goals": {
            "leads_by_month": dict(LEAD_GOALS),
            "cpl": CPL_TARGET,
            "demo_cost": DEMO_COST_TARGET,
            "sold_cpa": SOLD_CPA_TARGET,
            "spend_cap": None,
        },
        "submissions": spec.get("submissions"),
        "account_timezone": ACCOUNT_TZ_NAME,
        "crm_timezone": CRM_TZ_NAME,
        "measurement_id": GA4_MEASUREMENT_ID,
        "lead_pipeline_id": LEAD_PIPELINE_ID,
        "source_field_id": SOURCE_FIELD_ID,
        "sold_date_field_id": SOLD_DATE_FIELD_ID,
    }


def _landing_note(value) -> str:
    if value is None:
        return (
            f"Landing visits are GA4 paid sessions on property {GA4_PROPERTY_ID}, "
            f"measurement {GA4_MEASUREMENT_ID}. This read is unavailable, so the stage stays blank. "
            "A failed read is not zero. The November sample is not used. "
            "Meta landing-page views are not visits."
        )
    return (
        f"GA4 paid sessions on property {GA4_PROPERTY_ID}, measurement {GA4_MEASUREMENT_ID}. "
        "The website traffic paid-session rule: paid medium or paid channel, "
        "Facebook and Instagram included. A Meta click is not a session. "
        "Meta landing-page views are not visits."
    )


def _form_note(value) -> str:
    if value is None:
        return (
            "Form starts are calculator estimate_start events from paid traffic. "
            "This read is unavailable, so the stage stays blank. A failed read is not zero. "
            "The November sample is not used. A finished form is not a start. "
            "Instant Form and 3PL are not form starts."
        )
    return (
        "Calculator estimate_start events from paid traffic, same rule as landing visits. "
        "A finished form is not a start. Instant Form and 3PL are not form starts."
    )


def _sources(is_demo: bool, impressions, clicks, visits, forms) -> dict:
    def state(value, live_note: str, sample_note: str) -> dict:
        if is_demo and value is not None:
            return {"status": "sample", "note": sample_note}
        if value is None:
            return {"status": "unavailable", "note": live_note}
        return {"status": "ok", "note": live_note}

    return {
        "impressions": state(impressions, "Meta account impressions.", "Sample Meta impressions."),
        "outbound_clicks": state(clicks, "Meta outbound clicks. A Meta click is not a GA4 session.", "Sample outbound clicks."),
        "landing_visits": state(
            visits,
            _landing_note(visits),
            f"Sample landing visits. Live visits stay on GA4 paid sessions {GA4_MEASUREMENT_ID}.",
        ),
        "form_starts": state(forms, _form_note(forms), "Sample form starts."),
    }


def _pace(goal_month, goal, start, end, cutoff, days, override_actual):
    if not goal_month or goal is None:
        return {
            "status": "choose",
            "label": "Choose goal month",
            "expected": None,
            "actual": None,
            "goal": None,
            "behind": None,
            "percent": None,
            "completed_days": None,
            "days_in_month": None,
        }
    year, month = (int(goal_month[:4]), int(goal_month[5:7]))
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    completed = []
    unknown = False
    for day in days:
        current = date.fromisoformat(day["date"])
        if current < month_start or current > month_end:
            continue
        if current >= cutoff or current < start or current > end:
            continue
        completed.append(day)
        if day.get("leads") is None:
            unknown = True
    completed_days = len(completed)
    if unknown or override_actual is False:
        actual = None
    elif override_actual is not None and start >= month_start and end <= month_end and completed_days == (end - start).days + 1:
        actual = override_actual
    else:
        actual = sum(int(day["leads"]) for day in completed if day.get("leads") is not None)
        if any(day.get("leads") is None for day in completed):
            actual = None
    expected = None if completed_days == 0 else goal * completed_days / days_in_month
    behind = None if expected is None or actual is None else expected - actual
    percent = None if goal in (None, 0) or actual is None else actual / goal * 100
    if actual is None or expected is None:
        label = "Pace unavailable"
        status = "unknown"
    elif behind > 0.05:
        label = f"{_trim_number(behind)} behind pace"
        status = "behind"
    elif behind < -0.05:
        label = f"{_trim_number(abs(behind))} ahead of pace"
        status = "ahead"
    else:
        label = "On pace"
        status = "on"
    return {
        "status": status,
        "label": label,
        "expected": expected,
        "actual": actual,
        "goal": goal,
        "behind": behind,
        "percent": percent,
        "completed_days": completed_days,
        "days_in_month": days_in_month,
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
    }


def _lead_kpi(actual, goal, pace) -> dict:
    if actual is None:
        return {
            "actual": None,
            "goal": goal,
            "text": "—",
            "percent_label": "unavailable",
            "bar": 0,
            "pace": pace["label"],
            "tone": "unknown",
        }
    if goal in (None, 0):
        percent = None
        bar = 0
        percent_label = "Choose goal month"
    else:
        percent = actual / goal * 100
        bar = min(percent, 100)
        percent_label = f"{_trim_number(percent)}%"
    text = f"{format_count(actual)}/{format_count(goal)}" if goal is not None else format_count(actual)
    tone = "amber" if pace["status"] == "behind" else "neutral"
    return {
        "actual": actual,
        "goal": goal,
        "text": text,
        "percent": percent,
        "percent_label": percent_label,
        "bar": bar,
        "pace": pace["label"],
        "tone": tone,
    }


def _cost_kpi(spend, count, target, noun: str) -> dict:
    value = _unit(spend, count)
    if count is None or spend is None:
        note = "Unavailable"
        tone = "unknown"
    elif int(count) == 0:
        note = "N/A"
        tone = "unknown"
        value = None
    else:
        delta = value - target
        if delta > 0.004:
            note = f"{format_dollars(delta)} over goal"
            tone = "amber"
        elif delta < -0.004:
            note = f"{format_dollars(abs(delta))} under goal"
            tone = "success"
        else:
            note = "On goal"
            tone = "success"
    return {
        "value": value,
        "display": "N/A" if value is None else format_dollars(value),
        "exact": "N/A" if value is None else format_dollars_exact(value),
        "target": target,
        "note": note,
        "tone": tone,
        "count": count,
        "noun": noun,
    }


def _spend_kpi(spend, ads: dict, gap) -> dict:
    if gap:
        note = "Spend figures differ"
        tone = "unknown"
        display = "—"
        value = None
    elif spend is None:
        note = "Unavailable"
        tone = "unknown"
        display = "—"
        value = None
    else:
        note = "Not configured" if ads.get("status") != "ok" else f"{ads.get('active', 0)} active"
        tone = "neutral"
        display = format_dollars(spend)
        value = spend
    active_label = "unavailable"
    if ads.get("status") == "ok":
        active_label = f"{int(ads.get('active') or 0)} active"
    return {
        "value": value,
        "display": display,
        "note": note if ads.get("status") != "ok" or gap or spend is None else active_label,
        "active_label": active_label,
        "cap_label": "Not configured",
        "tone": tone,
        "rejected": ads.get("rejected") if ads.get("status") == "ok" else None,
        "delivering": ads.get("delivering") if ads.get("status") == "ok" else None,
        "active": ads.get("active") if ads.get("status") == "ok" else None,
    }


def _stages(rows: list[tuple]) -> list[dict]:
    stages = []
    for index, (key, label, value, source) in enumerate(rows):
        nxt = rows[index + 1][2] if index + 1 < len(rows) else None
        ratio = None
        ratio_label = None
        if index < len(rows) - 1:
            if value is None or nxt is None:
                ratio_label = "—"
            else:
                ratio = _rate(nxt, value)
                ratio_label = "N/A" if value == 0 else format_percent(nxt, value, 1)
        stages.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "display": "—" if value is None else format_count(value),
                "status": "unavailable" if value is None else "ok",
                "source": source,
                "ratio": ratio,
                "ratio_label": ratio_label,
                "note": "Unavailable" if value is None else source,
            }
        )
    return stages


def _bot(spec: dict, kpis: dict, pace: dict) -> dict:
    is_demo = bool(spec.get("is_demo"))
    submissions = spec.get("submissions") or {}
    costs_over = any(kpis[key]["tone"] == "amber" for key in ("cpl", "demo_cost", "cpa"))
    pace_miss = pace["status"] == "behind"
    prerequisites_missing = (
        kpis["spend"]["value"] is None and kpis["leads"]["actual"] is None
    ) or bool(spec.get("read_error"))
    if prerequisites_missing and kpis["leads"]["actual"] is None:
        status = "UNKNOWN"
    elif pace_miss or costs_over:
        status = "WATCH"
    elif not is_demo and spec.get("tracking") == "unknown":
        status = "UNKNOWN"
    else:
        status = "ON TRACK"
    if is_demo and spec.get("tracking") == "healthy":
        tracking = {"label": "Tracking", "value": "Healthy", "tone": "success"}
    else:
        tracking = {"label": "Tracking", "value": "Unknown", "tone": "unknown"}
    if submissions and submissions.get("accepted") is not None:
        accepted = int(submissions["accepted"])
        delivered = int(submissions.get("delivered") or 0)
        crm_value = "Healthy" if delivered == accepted else "Watch"
        crm_tone = "success" if delivered == accepted else "amber"
        crm_detail = f"{delivered} of {accepted} accepted submissions delivered"
    else:
        crm_value = "Unknown"
        crm_tone = "unknown"
        crm_detail = "Accepted-submission delivery is not wired."
    next_action = "Review cost per lead" if kpis["cpl"]["tone"] == "amber" else (
        "No cost exception" if status == "ON TRACK" else "Restore missing sources"
    )
    return {
        "status": status,
        "tone": {"WATCH": "amber", "UNKNOWN": "unknown", "ON TRACK": "success", "INCIDENT": "critical"}.get(status, "unknown"),
        "rows": [
            tracking,
            {"label": "CRM delivery", "value": crm_value, "tone": crm_tone, "detail": crm_detail},
            {"label": "Last sync", "value": _sync_label(spec["as_of"], is_demo), "tone": "neutral"},
            {"label": "Next action", "value": next_action, "tone": "amber" if status == "WATCH" else "neutral"},
        ],
    }


def _recommendations(spec, kpis, visits, form_starts, spend, leads) -> list[dict]:
    items = []
    as_of = spec["as_of"].isoformat()
    if visits not in (None, 0) and form_starts is not None:
        rate = format_percent(form_starts, visits, 1)
        items.append(
            {
                "id": "rec-visit-to-form",
                "title": f"Review the {rate} visit-to-form-start rate",
                "evidence": f"{format_count(form_starts)} form starts / {format_count(visits)} landing visits = {rate}. No baseline is stored, so this is a review.",
                "action": f"Review the {rate} visit-to-form-start rate.",
                "status": "Open",
                "entity_ids": [ad["id"] for ad in SAMPLE_ADS] if spec.get("is_demo") else [],
                "source_timestamp": as_of,
                "confidence": "Directional",
                "owner": "Unassigned",
                "next_review": "Next business review",
            }
        )
    if spec.get("is_demo") and visits is not None:
        items.append(
            {
                "id": "rec-creative-test",
                "title": "Test an approved creative against lead cost",
                "evidence": "The fixture does not show that a creative change improved click-to-visit. Arrival loss is not attributed to creative.",
                "action": "Test an approved creative against lead cost. Investigate load failures and measurement before attributing arrival loss to creative.",
                "status": "Open",
                "entity_ids": [ad["id"] for ad in SAMPLE_ADS],
                "source_timestamp": as_of,
                "confidence": "Directional",
                "owner": "Unassigned",
                "next_review": "Next business review",
            }
        )
    cpl = kpis["cpl"]
    if cpl["tone"] == "amber" and cpl["value"] is not None:
        items.append(
            {
                "id": "rec-cpl",
                "title": f"Cost per lead is {cpl['note']}",
                "evidence": f"Spend {format_dollars(spend)} / {format_count(leads)} leads = {cpl['display']}. Target {format_dollars(CPL_TARGET)}.",
                "action": "Review ads whose lead cost is above $25.",
                "status": "Open",
                "entity_ids": [ad["id"] for ad in SAMPLE_ADS] if spec.get("is_demo") else [],
                "source_timestamp": as_of,
                "confidence": "Calculated",
                "owner": "Unassigned",
                "next_review": "Next business review",
            }
        )
    if spec.get("spend_gap"):
        gap = spec["spend_gap"]
        items.append(
            {
                "id": "rec-spend-gap",
                "title": "Account spend does not match the daily rows",
                "evidence": gap.get("note") or "Two spend figures differ. Neither is selected.",
                "action": "Show both figures. Do not pick one for a cost.",
                "status": "Open",
                "entity_ids": [],
                "source_timestamp": as_of,
                "confidence": "Calculated",
                "owner": "Unassigned",
                "next_review": "When the next read agrees",
            }
        )
    if not items and not spec.get("read_error"):
        return []
    if spec.get("read_error") and not items:
        items.append(
            {
                "id": "rec-sources",
                "title": "Live sources are unavailable",
                "evidence": spec["read_error"],
                "action": "Leave the counts blank. Do not fill them from the sample fixture.",
                "status": "Waiting on source",
                "entity_ids": [],
                "source_timestamp": as_of,
                "confidence": "Unknown",
                "owner": "Unassigned",
                "next_review": "When credentials and the paid-session source are present",
            }
        )
    return items[:3]


def _lead_chart(spec: dict, pace: dict, actual_total) -> dict:
    goal_month = spec.get("goal_month")
    days = spec["days"]
    if not goal_month:
        return {
            "status": "choose",
            "summary": "Choose goal month. The pace line stays hidden until the month is unambiguous.",
            "svg": "",
        }
    year, month = int(goal_month[:4]), int(goal_month[5:7])
    days_in_month = calendar.monthrange(year, month)[1]
    goal = LEAD_GOALS.get(goal_month)
    by_date = {day["date"]: day for day in days}
    cumulative = []
    running = 0
    seen = False
    cutoff = spec["as_of"].date()
    for index in range(1, days_in_month + 1):
        current = date(year, month, index)
        row = by_date.get(current.isoformat())
        value = None
        if row is not None and current < cutoff:
            if row.get("leads") is None:
                value = None
                running_out = None
            else:
                seen = True
                running += int(row["leads"])
                running_out = running
                value = running_out
        else:
            running_out = None
        pace_value = None if goal is None else goal * index / days_in_month
        cumulative.append(
            {
                "date": current.isoformat(),
                "actual": value if row is not None and current < cutoff and row.get("leads") is not None else None,
                "pace": pace_value,
            }
        )
        if row is not None and current < cutoff and row.get("leads") is None:
            cumulative[-1]["actual"] = None
    y_max = goal or 0
    for point in cumulative:
        if point["actual"] is not None:
            y_max = max(y_max, point["actual"])
        if point["pace"] is not None:
            y_max = max(y_max, point["pace"])
    y_max = max(y_max, 1)
    cutoff_label = format_day(cutoff - timedelta(days=1))
    actual_label = "unavailable" if actual_total is None else f"{format_count(pace.get('actual') if pace.get('actual') is not None else actual_total)} actual"
    expected = pace.get("expected")
    pace_label = "pace unavailable" if expected is None else f"{_trim_number(expected)} paced"
    summary = (
        f"Cumulative leads {actual_label} through {cutoff_label}. "
        f"Goal pace {pace_label}. "
        f"{_month_label(goal_month)} goal {format_count(goal)}."
    )
    svg = _line_svg(
        cumulative,
        y_max=y_max,
        actual_key="actual",
        guide_key="pace",
        guide_label=pace_label,
        actual_label=actual_label,
        y_ticks=_ticks(y_max),
        month_end=days_in_month,
        value_format=format_count,
    )
    return {
        "status": "ok" if seen or actual_total == 0 else "unavailable",
        "summary": summary,
        "svg": svg,
        "y_max": y_max,
        "actual_label": actual_label,
        "pace_label": pace_label,
    }


def _cost_chart(days: list[dict], denom_key: str, target: float, title: str, guide_label: str) -> dict:
    running_spend = 0.0
    running_count = 0
    points = []
    blocked = False
    for day in days:
        spend = day.get("spend")
        count = day.get(denom_key)
        if spend is None or count is None:
            blocked = True
            points.append({"date": day["date"], "actual": None, "pace": target})
            continue
        if blocked:
            points.append({"date": day["date"], "actual": None, "pace": target})
            continue
        running_spend += float(spend)
        running_count += int(count)
        actual = None if running_count == 0 else running_spend / running_count
        points.append({"date": day["date"], "actual": actual, "pace": target})
    peak = target
    for point in points:
        if point["actual"] is not None:
            peak = max(peak, point["actual"])
    y_max = _axis_max(peak, target)
    end = next((point for point in reversed(points) if point["actual"] is not None), None)
    end_value = None if end is None else end["actual"]
    summary = (
        f"{title} is unavailable for this range."
        if end_value is None
        else f"{title} ends at {format_dollars_exact(end_value)} against the {format_dollars(target)} goal."
    )
    geometry = _chart_geometry(len(points) or 1)
    target_y = _y_at(target, y_max, geometry)
    end_y = None if end_value is None else _y_at(end_value, y_max, geometry)
    svg = _line_svg(
        points,
        y_max=y_max,
        actual_key="actual",
        guide_key="pace",
        guide_label=guide_label,
        actual_label="" if end_value is None else format_dollars(end_value),
        y_ticks=_money_ticks(y_max),
        month_end=len(points),
        value_format=format_dollars,
        flat_guide=True,
    )
    return {
        "title": title,
        "summary": summary,
        "svg": svg,
        "target": target,
        "end_value": end_value,
        "target_y": target_y,
        "end_y": end_y,
        "y_max": y_max,
    }


def _chart_geometry(count: int) -> dict:
    width, height = 640, 220
    left, right, top, bottom = 46, 16, 18, 28
    inner_w = width - left - right
    inner_h = height - top - bottom
    return {
        "width": width,
        "height": height,
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "inner_w": inner_w,
        "inner_h": inner_h,
        "count": max(count, 1),
    }


def _y_at(value: float, y_max: float, geometry: dict) -> float:
    return geometry["top"] + (1 - (value / y_max)) * geometry["inner_h"]


def _x_at(index: int, geometry: dict) -> float:
    slots = max(geometry["count"] - 1, 1)
    return geometry["left"] + index * (geometry["inner_w"] / slots)


def _line_svg(
    points: list[dict],
    *,
    y_max: float,
    actual_key: str,
    guide_key: str,
    guide_label: str,
    actual_label: str,
    y_ticks: list[float],
    month_end: int,
    value_format,
    flat_guide: bool = False,
) -> str:
    geometry = _chart_geometry(len(points) or 1)
    width = geometry["width"]
    height = geometry["height"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" class="chart-svg">',
    ]
    for tick in y_ticks:
        y = _y_at(tick, y_max, geometry)
        parts.append(
            f'<line x1="{geometry["left"]}" y1="{y:.2f}" x2="{width - geometry["right"]}" y2="{y:.2f}" class="grid"/>'
        )
        parts.append(
            f'<text x="{geometry["left"] - 8}" y="{y + 4:.2f}" text-anchor="end" class="tick">{html.escape(value_format(tick))}</text>'
        )
    if points:
        future_start = None
        for index, point in enumerate(points):
            if point.get(actual_key) is None and future_start is None and index > 0:
                if all(later.get(actual_key) is None for later in points[index:]):
                    future_start = index
                    break
        if future_start is not None:
            x = _x_at(future_start, geometry)
            parts.append(
                f'<rect x="{x:.2f}" y="{geometry["top"]}" width="{width - geometry["right"] - x:.2f}" height="{geometry["inner_h"]}" class="future"/>'
            )
        guide_pairs = []
        for index, point in enumerate(points):
            guide = point.get(guide_key)
            if guide is None:
                continue
            guide_pairs.append((index, guide))
        if guide_pairs:
            coords = " ".join(
                f"{_x_at(index, geometry):.2f},{_y_at(value, y_max, geometry):.2f}" for index, value in guide_pairs
            )
            parts.append(f'<polyline points="{coords}" class="guide"/>')
            last_index, last_value = guide_pairs[-1]
            label_x = min(_x_at(last_index, geometry) + 4, width - geometry["right"] - 4)
            label_y = _y_at(last_value, y_max, geometry) - 6
            if flat_guide:
                label_x = width - geometry["right"] - 4
                parts.append(
                    f'<text x="{label_x:.2f}" y="{max(label_y, 14):.2f}" text-anchor="end" class="guide-label">{html.escape(guide_label)}</text>'
                )
        actual_pairs = [(index, point[actual_key]) for index, point in enumerate(points) if point.get(actual_key) is not None]
        if actual_pairs:
            area = actual_pairs[:]
            baseline = geometry["top"] + geometry["inner_h"]
            area_points = " ".join(
                f"{_x_at(index, geometry):.2f},{_y_at(value, y_max, geometry):.2f}" for index, value in area
            )
            first_x = _x_at(area[0][0], geometry)
            last_x = _x_at(area[-1][0], geometry)
            parts.append(
                f'<polygon points="{first_x:.2f},{baseline:.2f} {area_points} {last_x:.2f},{baseline:.2f}" class="area"/>'
            )
            parts.append(
                f'<polyline points="{area_points}" class="actual"/>'
            )
            end_index, end_value = area[-1]
            end_x = _x_at(end_index, geometry)
            end_y = _y_at(end_value, y_max, geometry)
            parts.append(f'<circle cx="{end_x:.2f}" cy="{end_y:.2f}" r="4" class="dot"/>')
            if actual_label and not flat_guide:
                parts.append(
                    f'<text x="{end_x - 10:.2f}" y="{end_y + 4:.2f}" text-anchor="end" class="actual-label">{html.escape(actual_label)}</text>'
                )
            elif actual_label:
                parts.append(
                    f'<text x="{min(end_x - 8, width - 72):.2f}" y="{max(end_y - 10, 14):.2f}" text-anchor="end" class="actual-label">{html.escape(actual_label)}</text>'
                )
            if not flat_guide and guide_label:
                guide_here = points[end_index].get(guide_key)
                if guide_here is not None:
                    guide_y = _y_at(guide_here, y_max, geometry)
                    parts.append(
                        f'<text x="{end_x + 12:.2f}" y="{guide_y + 4:.2f}" class="guide-label">{html.escape(guide_label)}</text>'
                    )
        label_indexes = [0, len(points) // 2, len(points) - 1] if len(points) > 2 else list(range(len(points)))
        for index in label_indexes:
            if index < 0 or index >= len(points):
                continue
            parts.append(
                f'<text x="{_x_at(index, geometry):.2f}" y="{height - 8}" text-anchor="middle" class="tick">{html.escape(format_axis_day(points[index]["date"]))}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _ticks(y_max: float) -> list[float]:
    if y_max <= 10:
        return [0, round(y_max / 2, 2), y_max]
    return [0, round(y_max / 2, 2), y_max]


def _money_ticks(y_max: float) -> list[float]:
    return [0, y_max / 2, y_max]


def _axis_max(peak: float, target: float) -> float:
    needed = max(peak, target, 1) * 1.08
    if needed <= 60:
        return 60
    if needed <= 80:
        return 80
    if needed <= 100:
        return 100
    if needed <= 300:
        return 300
    return float(int(needed / 50 + 1) * 50)


def _unit(spend, count):
    if spend is None or count is None or int(count) == 0:
        return None
    return round(float(spend) / int(count), 2)


def _rate(numer, denom):
    if numer is None or denom in (None, 0):
        return None
    return numer / denom


def _cost_tone(value, target: float) -> str:
    if value is None:
        return "unknown"
    if value - target > 0.004:
        return "amber"
    return "success"


def format_dollars(value) -> str:
    if value is None:
        return "N/A"
    number = float(value)
    if abs(number - round(number)) < 0.005:
        return f"${round(number):,}"
    return f"${number:,.2f}"


def format_dollars_exact(value) -> str:
    if value is None:
        return "N/A"
    return f"${float(value):,.2f}"


def format_count(value) -> str:
    if value is None:
        return "—"
    return f"{int(round(float(value))):,}"


def format_percent(numer, denom, places: int) -> str:
    if denom in (None, 0) or numer is None:
        return "N/A"
    pct = 100.0 * float(numer) / float(denom)
    text = f"{pct:.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + "%"


def format_range(start: date, end: date) -> str:
    if start == end:
        return f"{start.strftime('%b')} {start.day}, {start.year}"
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%b')} {start.day}–{end.day}, {start.year}"
    if start.year == end.year:
        return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}, {start.year}"
    return f"{start.strftime('%b')} {start.day}, {start.year} – {end.strftime('%b')} {end.day}, {end.year}"


def format_day(current: date) -> str:
    return f"{current.strftime('%b')} {current.day}, {current.year}"


def format_axis_day(iso: str) -> str:
    current = date.fromisoformat(iso[:10])
    return f"{current.strftime('%b')} {current.day}"


def _month_label(goal_month: str | None) -> str:
    if not goal_month:
        return "Choose goal month"
    year, month = int(goal_month[:4]), int(goal_month[5:7])
    return date(year, month, 1).strftime("%B %Y")


def _trim_number(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _as_of_label(as_of: datetime, is_demo: bool) -> str:
    completed = as_of.date() - timedelta(days=1)
    clock = as_of.strftime("%b %-d, %Y, %-I:%M %p") if "%" in "%-d" else _clock(as_of)
    zone = ACCOUNT_TZ_NAME if is_demo else CRM_TZ_NAME
    return f"Completed days through {format_day(completed)}. As of {_clock(as_of)} {zone}."


def _clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{moment.strftime('%b')} {moment.day}, {moment.year}, {hour}:{moment.minute:02d} {suffix}"


def _sync_label(as_of: datetime, is_demo: bool) -> str:
    zone = "MT" if is_demo else "ET"
    return f"{_clock(as_of)} {zone}"
