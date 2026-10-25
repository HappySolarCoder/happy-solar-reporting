# -*- coding: utf-8 -*-

"""Growth Command Center metrics. JSON: /api/metrics/growth_command_center

View-only. This module never calls a Meta write endpoint and the handler
implements GET only. Demo mode is the default and is a labeled sample.
Live mode reads existing sources and returns null — never fixture numbers —
when a source is missing or the cohort join is not validated.

Lead created = a website form fill counted the same way inbound CAC counts
live named fills (not every opportunity on pipeline 7nSEgeoBYXZiIS7x41Jy).
Demo = a Sit on Buffalo, Rochester, Syracuse, or Virtual. The UI says demo.
Sold = distinct contactId on the locked Sold / Sale Cancelled stage IDs with
Contact Sold Date P9oBjgbZjJdeE0OkBj9T, date-only, America/New_York. Sale
Cancelled stays in the sold count. That is the same contract as sales.py.
"""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

TIMEZONE_NAME = "America/New_York"
TZ = ZoneInfo(TIMEZONE_NAME)
CURRENCY = "USD"

LEADS_GOAL_BY_MONTH = {"2026-10": 10, "2026-11": 20}
CPL_GOAL = 25
DEMO_COST_GOAL = 50
SOLD_CPA_GOAL = 200
MONTHLY_SPEND_CAP = None

INBOUND_PIPELINE_ID = "7nSEgeoBYXZiIS7x41Jy"
INBOUND_PIPELINE_NAME = "Inbound/Lead Locker"
SOLD_DATE_CUSTOM_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"
LEAD_GEN_SOURCE_CONTACT_CF_ID = "hd5QqHEOVSsPom5bJ32P"
TERRITORY_PIPELINE_IDS = (
    "GQtUlcTmLJ61HZjrGEPC",  # Buffalo
    "qJNvqKWp8Xc7DaBr8QYc",  # Rochester
    "etLURrEVxupngZZRlISG",  # Syracuse
    "r1b9pwgliYj7WyWBchTV",  # Virtual
)
TERRITORY_PIPELINE_ID_SET = set(TERRITORY_PIPELINE_IDS)
# Locked to sales.SalesMetricContract.stage_ids. Sale Cancelled is included.
SOLD_STAGE_IDS = (
    "7981f111-73f2-4593-9662-6b95d99bf51a",
    "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
    "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
    "34a1882f-7959-4d22-878d-91fe35a42907",
    "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
    "9bd71abf-7285-47bb-8800-a255e7b90630",
    "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
    "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
)
SOLD_STAGE_ID_SET = set(SOLD_STAGE_IDS)

DEMO_AS_OF = datetime(2026, 11, 16, 0, 0, tzinfo=TZ)
DEMO_RANGE_START = date(2026, 11, 1)
DEMO_RANGE_END = date(2026, 11, 15)

# Period totals are the authority. Daily spend is the raw series the charts use.
# The 3/2/1 split is adjusted on the last day so each ad lands on its total.
DAILY_SPEND_CENTS = (
    800, 1400, 100, 2500, 100, 100, 2650, 2750, 200, 2900, 250, 3050, 3150, 350, 3700,
)
AD_SPEND_TARGETS = {
    "ad_local_savings": 12000,
    "ad_solar_explained": 8000,
    "ad_homeowner_story": 4000,
}
VISITS_BY_DAY = (22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 20, 20, 20, 20, 20)
STARTS_BY_DAY = (3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2)

AD_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "ad_local_savings",
        "name": "Local savings",
        "copy": "Save more with solar",
        "campaign_id": "camp_demo_prospecting",
        "campaign_name": "Prospecting",
        "adset_id": "adset_demo_local",
        "platform": "meta",
        "configured_status": "active",
        "effective_status": "active",
        "rejected": False,
        "thumbnail": "house",
        "landing_url": "https://www.happyslr.com/estimate",
        "impressions": 10000,
        "outbound_clicks": 180,
    },
    {
        "id": "ad_solar_explained",
        "name": "Solar explained",
        "copy": "A cleaner, brighter future",
        "campaign_id": "camp_demo_prospecting",
        "campaign_name": "Prospecting",
        "adset_id": "adset_demo_explain",
        "platform": "meta",
        "configured_status": "active",
        "effective_status": "active",
        "rejected": False,
        "thumbnail": "sun",
        "landing_url": "https://www.happyslr.com/estimate",
        "impressions": 8000,
        "outbound_clicks": 140,
    },
    {
        "id": "ad_homeowner_story",
        "name": "Homeowner story",
        "copy": "Real families, real savings",
        "campaign_id": "camp_demo_prospecting",
        "campaign_name": "Prospecting",
        "adset_id": "adset_demo_story",
        "platform": "meta",
        "configured_status": "active",
        "effective_status": "active",
        "rejected": False,
        "thumbnail": "home",
        "landing_url": "https://www.happyslr.com/estimate",
        "impressions": 6000,
        "outbound_clicks": 80,
    },
)

# acquisition date, ad, contact, pipeline, demo, sold, sold date, cancelled
FIXTURE_LEADS: tuple[tuple[Any, ...], ...] = (
    ("2026-11-02", "ad_local_savings", "demo_contact_02", "GQtUlcTmLJ61HZjrGEPC", True, True, "2026-11-10", False),
    ("2026-11-04", "ad_solar_explained", "demo_contact_04", "qJNvqKWp8Xc7DaBr8QYc", True, False, None, False),
    ("2026-11-07", "ad_local_savings", "demo_contact_07", "etLURrEVxupngZZRlISG", False, False, None, False),
    ("2026-11-08", "ad_homeowner_story", "demo_contact_08", "r1b9pwgliYj7WyWBchTV", True, False, None, False),
    ("2026-11-10", "ad_local_savings", "demo_contact_10", "GQtUlcTmLJ61HZjrGEPC", False, False, None, False),
    ("2026-11-12", "ad_solar_explained", "demo_contact_12", "qJNvqKWp8Xc7DaBr8QYc", True, False, None, False),
    ("2026-11-13", "ad_local_savings", "demo_contact_13", "etLURrEVxupngZZRlISG", False, False, None, False),
    ("2026-11-15", "ad_homeowner_story", "demo_contact_15", "r1b9pwgliYj7WyWBchTV", False, False, None, False),
)


def allocate_ints(total: int, weights: list[int]) -> list[int]:
    """Largest-remainder split. Empty or zero weight returns zeros."""
    n = len(weights)
    if n == 0:
        return []
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0] * n
    raw = [total * w / weight_sum for w in weights]
    floors = [int(v) for v in raw]
    left = total - sum(floors)
    order = sorted(range(n), key=lambda i: (raw[i] - floors[i], weights[i]), reverse=True)
    for i in order[:left]:
        floors[i] += 1
    return floors


def daily_spend_by_ad() -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for total in DAILY_SPEND_CENTS:
        local = total * 3 // 6
        solar = total * 2 // 6
        home = total - local - solar
        rows.append(
            {
                "ad_local_savings": local,
                "ad_solar_explained": solar,
                "ad_homeowner_story": home,
            }
        )
    sums = {ad: sum(row[ad] for row in rows) for ad in AD_SPEND_TARGETS}
    last = rows[-1]
    for ad, target in AD_SPEND_TARGETS.items():
        last[ad] += target - sums[ad]
    if sum(last.values()) != DAILY_SPEND_CENTS[-1]:
        raise RuntimeError("demo spend split does not match the daily total")
    for ad, target in AD_SPEND_TARGETS.items():
        if sum(row[ad] for row in rows) != target:
            raise RuntimeError(f"demo spend for {ad} drifted from {target}")
    return rows


def _lead_record(row: tuple[Any, ...], *, duplicate: bool = False, test: bool = False, invalid: bool = False) -> dict[str, Any]:
    acquired, ad_id, contact_id, pipeline_id, is_demo, is_sold, sold_on, cancelled = row
    lead_id = f"lead_{acquired}_{contact_id}"
    return {
        "id": lead_id,
        "contact_id": contact_id,
        "acquired_on": acquired,
        "ad_id": ad_id,
        "pipeline_id": pipeline_id,
        "duplicate": duplicate,
        "test": test,
        "invalid": invalid,
        "demo_id": f"demo_{contact_id}" if is_demo else None,
        "demo_observed_on": acquired if is_demo else None,
        "sold_id": f"sold_{contact_id}" if is_sold else None,
        "sold_on": sold_on if is_sold else None,
        "sold_observed_on": sold_on if is_sold else None,
        "sale_cancelled": bool(cancelled) if is_sold else False,
        "stage_group": ("sale_cancelled" if cancelled else "sold") if is_sold else None,
    }


def build_fixture_days() -> list[dict[str, Any]]:
    spend_rows = daily_spend_by_ad()
    if not (len(spend_rows) == len(VISITS_BY_DAY) == len(STARTS_BY_DAY) == 15):
        raise RuntimeError("demo fixture day grids are different lengths")
    leads_by_day: dict[str, list[dict[str, Any]]] = {}
    for row in FIXTURE_LEADS:
        leads_by_day.setdefault(row[0], []).append(_lead_record(row))
    catalog = {ad["id"]: ad for ad in AD_CATALOG}
    per_ad_weights = {
        ad_id: [row[ad_id] for row in spend_rows] for ad_id in catalog
    }
    impressions = {
        ad_id: allocate_ints(int(catalog[ad_id]["impressions"]), weights)
        for ad_id, weights in per_ad_weights.items()
    }
    clicks = {
        ad_id: allocate_ints(int(catalog[ad_id]["outbound_clicks"]), weights)
        for ad_id, weights in per_ad_weights.items()
    }
    days: list[dict[str, Any]] = []
    for index, total in enumerate(DAILY_SPEND_CENTS):
        day = DEMO_RANGE_START + timedelta(days=index)
        key = day.isoformat()
        day_leads = leads_by_day.get(key, [])
        ads = {}
        for ad_id in catalog:
            ads[ad_id] = {
                "spend_cents": spend_rows[index][ad_id],
                "impressions": impressions[ad_id][index],
                "outbound_clicks": clicks[ad_id][index],
            }
        accepted = len(day_leads)
        days.append(
            {
                "date": key,
                "visits": VISITS_BY_DAY[index],
                "form_starts": STARTS_BY_DAY[index],
                "submissions_accepted": accepted,
                "submissions_delivered": accepted,
                "ads": ads,
                "leads": day_leads,
                "spend_cents": total,
            }
        )
    return days


def parse_ymd(value: str | None) -> date | None:
    text = " ".join(str(value or "").split())
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def completed_cutoff(as_of: datetime) -> date:
    local = as_of.astimezone(TZ)
    return local.date() - timedelta(days=1)


def iter_dates(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def fmt_day(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def fmt_range(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%b')} {start.day} – {end.day}, {start.year}"
    if start.year == end.year:
        return f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}, {start.year}"
    return f"{start.strftime('%b')} {start.day}, {start.year} – {end.strftime('%b')} {end.day}, {end.year}"


def fmt_as_of(as_of: datetime) -> str:
    local = as_of.astimezone(TZ)
    clock = local.strftime("%I:%M %p").lstrip("0")
    return f"{local.strftime('%b')} {local.day}, {local.year} · {clock}"


def fmt_sync(as_of: datetime) -> str:
    local = as_of.astimezone(TZ)
    clock = local.strftime("%I:%M %p").lstrip("0")
    return f"{local.strftime('%b')} {local.day}, {local.year} · {clock}"


def money_number(cents: int | None) -> float | None:
    if cents is None:
        return None
    return round(cents / 100.0, 2)


def ratio(numer: int | None, denom: int | None) -> float | None:
    if numer is None or denom is None or denom == 0:
        return None
    return numer / denom


def cost_cents(spend_cents: int | None, outcomes: int | None) -> int | None:
    if spend_cents is None or outcomes is None or outcomes <= 0:
        return None
    return int(round(spend_cents / outcomes))


def whole_dollars(cents: int | None) -> str:
    if cents is None:
        return "—"
    dollars = cents / 100.0
    if abs(dollars - round(dollars)) < 0.001:
        return f"${round(dollars):,.0f}"
    return f"${dollars:,.2f}"


def leads_goal_for_month(year: int, month: int) -> int | None:
    return LEADS_GOAL_BY_MONTH.get(f"{year:04d}-{month:02d}")


def months_touched(start: date, end: date) -> list[tuple[int, int]]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = shift_month(year, month, 1)
    return months


def range_is_full_months(start: date, end: date) -> bool:
    return start.day == 1 and end == month_end(end.year, end.month)


def completed_days(year: int, month: int, start: date, end: date, cutoff: date) -> int:
    first = date(year, month, 1)
    last = month_end(year, month)
    window_start = max(first, start)
    window_end = min(last, end, cutoff)
    if window_end < window_start:
        return 0
    return (window_end - window_start).days + 1


def resolve_scope(params: dict[str, str], now: datetime | None = None) -> dict[str, Any]:
    mode = (params.get("mode") or "demo").strip().lower()
    if mode not in {"demo", "live"}:
        mode = "demo"
    clock = DEMO_AS_OF if mode == "demo" else (now or datetime.now(TZ)).astimezone(TZ)
    cutoff = completed_cutoff(clock)
    preset = (params.get("preset") or "").strip().lower()
    start = parse_ymd(params.get("start"))
    end = parse_ymd(params.get("end"))
    error = None
    if params.get("start") or params.get("end"):
        if start is None or end is None or end < start:
            error = "Enter a valid start and end date."
            start, end = (DEMO_RANGE_START, DEMO_RANGE_END) if mode == "demo" else (clock.date().replace(day=1), cutoff)
        preset = preset or "custom"
    elif preset == "this_month":
        start = clock.date().replace(day=1)
        end = month_end(start.year, start.month)
    elif preset == "last_month":
        year, month = shift_month(clock.year, clock.month, -1)
        start = date(year, month, 1)
        end = month_end(year, month)
    elif preset in {"last_30", "last_30_days"}:
        end = cutoff
        start = end - timedelta(days=29)
        preset = "last_30"
    elif preset == "sample" or (mode == "demo" and not preset):
        start, end = DEMO_RANGE_START, DEMO_RANGE_END
        preset = "sample"
    else:
        start = clock.date().replace(day=1)
        end = min(cutoff, month_end(clock.year, clock.month))
        preset = preset or "this_month"
    touched = months_touched(start, end)
    single = len(touched) == 1
    goal_month_param = (params.get("goal_month") or "").strip()
    goal_month = None
    ambiguous = not single
    if single:
        goal_month = f"{touched[0][0]:04d}-{touched[0][1]:02d}"
        ambiguous = False
    elif goal_month_param:
        parsed = parse_ymd(goal_month_param + "-01") if len(goal_month_param) == 7 else None
        if parsed and (parsed.year, parsed.month) in touched:
            goal_month = goal_month_param
    return {
        "mode": mode,
        "is_demo": mode == "demo",
        "preset": preset,
        "start": start,
        "end": end,
        "as_of": clock,
        "cutoff": cutoff,
        "goal_month": goal_month,
        "goal_month_ambiguous": ambiguous and goal_month is None,
        "selected_goal_month": goal_month,
        "error": error,
        "months": touched,
        "full_months": range_is_full_months(start, end),
    }


def _source(status: str, detail: str, *, reason: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "detail": detail,
        "validated": False,
    }


def lead_counts(leads: list[dict[str, Any]]) -> dict[str, Any]:
    kept = []
    duplicates = 0
    tests = 0
    invalid_kept = 0
    for lead in leads:
        if lead.get("test"):
            tests += 1
            continue
        if lead.get("duplicate"):
            duplicates += 1
            continue
        if lead.get("invalid"):
            invalid_kept += 1
        kept.append(lead)
    return {
        "leads": kept,
        "count": len(kept),
        "duplicates_excluded": duplicates,
        "tests_excluded": tests,
        "invalid_kept_in_denominator": invalid_kept,
    }


def demo_eligible(lead: dict[str, Any], cutoff: date) -> bool:
    if not lead.get("demo_id"):
        return False
    pipeline = lead.get("pipeline_id")
    if pipeline not in TERRITORY_PIPELINE_ID_SET:
        return False
    observed = parse_ymd(lead.get("demo_observed_on"))
    return observed is not None and observed <= cutoff


def sold_eligible(lead: dict[str, Any], cutoff: date) -> bool:
    if not lead.get("sold_id") or not lead.get("contact_id"):
        return False
    if lead.get("stage_group") not in {"sold", "sale_cancelled"}:
        return False
    sold_on = parse_ymd(lead.get("sold_on"))
    observed = parse_ymd(lead.get("sold_observed_on"))
    if sold_on is None or observed is None or observed > cutoff:
        return False
    return True


def outcome_sets(leads: list[dict[str, Any]], cutoff: date) -> dict[str, Any]:
    demos = [lead for lead in leads if demo_eligible(lead, cutoff)]
    sold_contacts = []
    seen = set()
    cancelled = 0
    for lead in leads:
        if not sold_eligible(lead, cutoff):
            continue
        if lead.get("sale_cancelled"):
            cancelled += 1
        contact = lead["contact_id"]
        if contact in seen:
            continue
        seen.add(contact)
        sold_contacts.append(contact)
    return {
        "demos": len({lead["demo_id"] for lead in demos}),
        "sold": len(sold_contacts),
        "sold_contacts": sold_contacts,
        "sale_cancelled_included": cancelled,
    }


def day_ad_spend(day: dict[str, Any], ad_id: str | None = None) -> int:
    ads = day.get("ads") or {}
    if ad_id:
        return int((ads.get(ad_id) or {}).get("spend_cents") or 0)
    if day.get("spend_cents") is not None and not ad_id:
        return int(day["spend_cents"])
    return sum(int((row or {}).get("spend_cents") or 0) for row in ads.values())


def filter_days(days: list[dict[str, Any]], start: date, end: date, cutoff: date) -> list[dict[str, Any]]:
    last = min(end, cutoff)
    kept = []
    for day in days:
        current = parse_ymd(day.get("date"))
        if current is None or current < start or current > last:
            continue
        kept.append(day)
    return kept


def pace_block(scope: dict[str, Any], actual: int) -> dict[str, Any]:
    months = scope["months"]
    cutoff = scope["cutoff"]
    start = scope["start"]
    end = scope["end"]
    if not months:
        return {
            "goal": None,
            "expected": None,
            "delta": None,
            "label": "Pace N/A",
            "attained": None,
            "reason": "no_month",
        }
    if len(months) > 1 and not scope["full_months"]:
        return {
            "goal": None,
            "expected": None,
            "delta": None,
            "label": "Pace N/A",
            "attained": None,
            "reason": "partial_multi_month",
        }
    goal_total = 0
    expected = 0.0
    for year, month in months:
        goal = leads_goal_for_month(year, month)
        if goal is None:
            return {
                "goal": None,
                "expected": None,
                "delta": None,
                "label": "Goal not configured",
                "attained": None,
                "reason": "goal_not_configured",
            }
        done = completed_days(year, month, start, end, cutoff)
        dim = monthrange(year, month)[1]
        goal_total += goal
        expected += goal * done / dim
    delta = actual - expected
    if abs(delta) < 0.05:
        label = "On pace"
    else:
        mag = abs(delta)
        text = str(int(round(mag))) if abs(mag - round(mag)) < 0.05 else f"{mag:.1f}"
        label = f"{text} behind pace" if delta < 0 else f"{text} ahead of pace"
    return {
        "goal": goal_total,
        "expected": expected,
        "delta": delta,
        "label": label,
        "attained": (actual / goal_total) if goal_total else None,
        "reason": None,
    }


def _chart_month(scope: dict[str, Any]) -> tuple[int, int] | None:
    if scope.get("selected_goal_month"):
        parsed = parse_ymd(scope["selected_goal_month"] + "-01")
        if parsed:
            return parsed.year, parsed.month
    if len(scope["months"]) == 1:
        return scope["months"][0]
    return None


def lead_series(days: list[dict[str, Any]], scope: dict[str, Any], catalog_leads: list[dict[str, Any]]) -> dict[str, Any]:
    month = _chart_month(scope)
    if month is None:
        return {
            "status": "choose_goal_month",
            "label": "Choose goal month",
            "points": [],
            "goal": None,
            "annotations": {},
        }
    year, month_num = month
    goal = leads_goal_for_month(year, month_num)
    dim = monthrange(year, month_num)[1]
    cutoff = scope["cutoff"]
    points = []
    running = 0
    month_start = date(year, month_num, 1)
    month_last = month_end(year, month_num)
    leads_by_day: dict[str, list[dict[str, Any]]] = {}
    for lead in catalog_leads:
        if lead.get("test") or lead.get("duplicate"):
            continue
        acquired = parse_ymd(lead.get("acquired_on"))
        if acquired is None:
            continue
        if acquired < scope["start"] or acquired > min(scope["end"], cutoff):
            continue
        if acquired < month_start or acquired > month_last:
            continue
        leads_by_day.setdefault(acquired.isoformat(), []).append(lead)
    for day_num in range(1, dim + 1):
        current = date(year, month_num, day_num)
        future = current > cutoff
        in_range = scope["start"] <= current <= scope["end"]
        if not future and in_range:
            running += len(leads_by_day.get(current.isoformat(), []))
        pace = None if goal is None else goal * day_num / dim
        points.append(
            {
                "date": current.isoformat(),
                "day": day_num,
                "label": fmt_day(current),
                "actual": None if future or current < scope["start"] else running,
                "pace": pace,
                "future": future,
                "in_range": in_range,
            }
        )
    cutoff_point = next((p for p in points if p["date"] == cutoff.isoformat()), None)
    end_point = points[-1] if points else None
    annotations = {}
    if cutoff_point and cutoff_point.get("actual") is not None:
        annotations["actual"] = {
            "date": cutoff_point["date"],
            "value": cutoff_point["actual"],
            "label": f"{cutoff_point['actual']} actual",
        }
        if cutoff_point.get("pace") is not None:
            pace_value = cutoff_point["pace"]
            pace_label = str(int(pace_value)) if abs(pace_value - round(pace_value)) < 0.05 else f"{pace_value:.1f}"
            annotations["paced"] = {
                "date": cutoff_point["date"],
                "value": pace_value,
                "label": f"{pace_label} paced",
            }
    if end_point and goal is not None:
        annotations["goal"] = {
            "date": end_point["date"],
            "value": goal,
            "label": f"{goal} goal",
        }
    return {
        "status": "ok",
        "month": f"{year:04d}-{month_num:02d}",
        "days_in_month": dim,
        "goal": goal,
        "cutoff": cutoff.isoformat(),
        "points": points,
        "annotations": annotations,
        "summary": _lead_summary(cutoff_point, goal),
    }


def _lead_summary(cutoff_point: dict[str, Any] | None, goal: int | None) -> str:
    if not cutoff_point or cutoff_point.get("actual") is None:
        return "Lead progress is unavailable for this goal month."
    goal_text = "Goal not configured." if goal is None else f"Monthly goal {goal}."
    pace = cutoff_point.get("pace")
    pace_text = "Pace is not configured." if pace is None else f"Goal pace {pace:.1f}."
    return f"Cumulative leads through {cutoff_point['label']}: {cutoff_point['actual']}. {pace_text} {goal_text}"


def cost_series(days: list[dict[str, Any]], scope: dict[str, Any]) -> dict[str, Any]:
    cutoff = scope["cutoff"]
    last = min(scope["end"], cutoff)
    axis_end = last
    month = _chart_month(scope)
    if month and len(scope["months"]) == 1:
        axis_end = month_end(month[0], month[1])
    leads = []
    for day in days:
        for lead in day.get("leads") or []:
            leads.append(lead)
    counted = lead_counts(leads)["leads"]
    points = {"cpl": [], "demo": [], "sold": []}
    goals = {"cpl": CPL_GOAL, "demo": DEMO_COST_GOAL, "sold": SOLD_CPA_GOAL}
    for current in iter_dates(scope["start"], axis_end):
        future = current > cutoff or current > scope["end"]
        through = [day for day in days if (parse_ymd(day["date"]) or date.min) <= current]
        spend = sum(day_ad_spend(day) for day in through)
        acquired = [
            lead for lead in counted
            if (parse_ymd(lead.get("acquired_on")) or date.max) <= current
        ]
        outcomes = outcome_sets(acquired, cutoff)
        lead_n = len(acquired)
        row = {
            "date": current.isoformat(),
            "label": fmt_day(current),
            "future": future or current > last,
            "spend_cents": None if future or current > last else spend,
        }
        if future or current > last:
            for key in points:
                points[key].append({**row, "value": None, "outcomes": None})
            continue
        specs = (
            ("cpl", lead_n),
            ("demo", outcomes["demos"]),
            ("sold", outcomes["sold"]),
        )
        for key, count in specs:
            cents = cost_cents(spend, count)
            points[key].append(
                {
                    **row,
                    "value": money_number(cents),
                    "value_cents": cents,
                    "outcomes": count,
                    "spend": money_number(spend),
                }
            )
    return {
        "goals": goals,
        "provisional": True,
        "label": "Acquisition cohort · sales still maturing",
        "series": points,
        "summary": _cost_summary(points),
    }


def _cost_summary(points: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    out = {}
    for key, rows in points.items():
        last = next((row for row in reversed(rows) if row.get("value") is not None), None)
        if last is None:
            out[key] = "No cohort cost yet. Denominator is zero or the source is missing."
        else:
            out[key] = (
                f"Cumulative cohort cost through {last['label']}: "
                f"{whole_dollars(last.get('value_cents'))} "
                f"from {whole_dollars(int(round((last.get('spend') or 0) * 100)))} "
                f"over {last.get('outcomes')} outcomes."
            )
    return out


def build_ads(days: list[dict[str, Any]], catalog: list[dict[str, Any]], cutoff: date) -> list[dict[str, Any]]:
    leads = []
    for day in days:
        leads.extend(day.get("leads") or [])
    counted = lead_counts(leads)["leads"]
    rows = []
    for ad in catalog:
        ad_id = ad["id"]
        spend = 0
        impressions = 0
        clicks = 0
        seen_metric = False
        for day in days:
            metrics = (day.get("ads") or {}).get(ad_id)
            if not metrics:
                continue
            seen_metric = True
            spend += int(metrics.get("spend_cents") or 0)
            impressions += int(metrics.get("impressions") or 0)
            clicks += int(metrics.get("outbound_clicks") or 0)
        ad_leads = [lead for lead in counted if lead.get("ad_id") == ad_id]
        lead_n = len(ad_leads)
        outcomes = outcome_sets(ad_leads, cutoff)
        cpl = cost_cents(spend if seen_metric else None, lead_n)
        rows.append(
            {
                "id": ad_id,
                "name": ad["name"],
                "copy": ad["copy"],
                "campaign_id": ad.get("campaign_id"),
                "campaign_name": ad.get("campaign_name"),
                "adset_id": ad.get("adset_id"),
                "platform": ad.get("platform") or "meta",
                "configured_status": ad.get("configured_status"),
                "effective_status": ad.get("effective_status"),
                "rejected": bool(ad.get("rejected")),
                "thumbnail": ad.get("thumbnail") or "fallback",
                "landing_url": ad.get("landing_url"),
                "impressions": impressions if seen_metric else None,
                "outbound_clicks": clicks if seen_metric else None,
                "spend": money_number(spend if seen_metric else None),
                "spend_cents": spend if seen_metric else None,
                "leads": lead_n if seen_metric or ad_leads else 0,
                "ctr": ratio(clicks, impressions) if seen_metric else None,
                "cpl": money_number(cpl),
                "cpl_cents": cpl,
                "demos": outcomes["demos"],
                "sold": outcomes["sold"],
                "delivering": bool(seen_metric and spend > 0 and ad.get("effective_status") == "active"),
                "attribution": "crm_lead" if lead_n else "none",
            }
        )
    rows.sort(key=lambda row: (-(row["spend_cents"] or 0), row["name"]))
    return rows


def pct_text(value: float | None, places: int = 1) -> str:
    if value is None:
        return "—"
    text = f"{value * 100:.{places}f}".rstrip("0").rstrip(".")
    return f"{text}%"


def build_funnel(totals: dict[str, Any]) -> dict[str, Any]:
    stages = [
        ("impressions", "Impressions", totals.get("impressions"), "meta_ads", "Ad account impressions"),
        ("outbound_clicks", "Outbound clicks", totals.get("outbound_clicks"), "meta_ads", "Meta outbound clicks"),
        ("landing_visits", "Landing visits", totals.get("visits"), "ga4_page_view", "Landing visits. A Meta click is not a GA4 session."),
        ("form_starts", "Form starts", totals.get("form_starts"), "ga4_estimate_start", "Sessions with a form start. Not a submission."),
        ("leads", "Leads created", totals.get("leads"), "crm_named_fills", "Inbound website form fills. Not every Lead Locker opportunity."),
        ("demos", "Demos", totals.get("demos"), "crm_demo", "Demos on Buffalo, Rochester, Syracuse, or Virtual, using the existing CRM demo definition."),
        ("sold", "Sold deals", totals.get("sold"), "crm_sold_date", "Distinct contacts with Sold Date on a Sold or Sale Cancelled stage."),
    ]
    hop_labels = (
        "click rate",
        "click → visit",
        "visit → start",
        "start → lead",
        "lead → demo",
        "demo → sale",
    )
    built = []
    for index, (sid, label, count, source, note) in enumerate(stages):
        prev = stages[index - 1][2] if index else None
        rate = ratio(count, prev) if index else None
        built.append(
            {
                "id": sid,
                "label": label,
                "count": count,
                "source": source,
                "note": note,
                "conversion_from_previous": rate,
                "conversion_label": pct_text(rate, 1) if index else None,
                "hop_label": hop_labels[index - 1] if index else None,
                "directional": index in {2, 4},
            }
        )
    return {
        "directional": True,
        "badge": "Directional funnel",
        "title": "Illustrative linked funnel",
        "detail": "Mixed Meta, website, and CRM stages. Ratios are directional where the join is not person-level.",
        "stages": built,
    }


def build_recommendations(totals: dict[str, Any], pace: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
    recs = []
    visits = totals.get("visits")
    starts = totals.get("form_starts")
    start_rate = ratio(starts, visits)
    if start_rate is not None:
        recs.append(
            {
                "id": "rec_form_start",
                "priority": 1,
                "title": "Inspect form drop-off",
                "text": f"Review the {pct_text(start_rate, 1)} visit-to-form-start rate.",
                "evidence": (
                    f"{starts} form starts / {visits} landing visits = {pct_text(start_rate, 1)}. "
                    "No baseline is configured, so this is a review, not a verdict that the rate is bad."
                ),
                "metric": "visit_to_form_start",
                "metric_value": start_rate,
                "entity": {"type": "funnel_stage", "id": "form_starts"},
                "proposed_action": "Review the landing-page to form-start path. This screen cannot edit the page or the ads.",
                "state": "open",
                "confidence": "directional",
                "owner": "Growth",
                "next_review": scope["as_of"].date().isoformat(),
                "source_timestamp": scope["as_of"].isoformat(),
                "evidence_window": {"start": scope["start"].isoformat(), "end": scope["end"].isoformat()},
            }
        )
    over = []
    comparisons = (
        ("CPL", totals.get("cpl_cents"), CPL_GOAL * 100, "cpl"),
        ("demo cost", totals.get("demo_cost_cents"), DEMO_COST_GOAL * 100, "demo_cost"),
        ("sold CPA", totals.get("sold_cpa_cents"), SOLD_CPA_GOAL * 100, "sold_cpa"),
    )
    for label, cents, goal_cents, metric in comparisons:
        if cents is None:
            continue
        if cents > goal_cents:
            over.append(f"{label} {whole_dollars(cents)} (>{whole_dollars(goal_cents)})")
    if over:
        recs.append(
            {
                "id": "rec_hold_scaling",
                "priority": 2,
                "title": "Hold scaling while costs exceed targets",
                "text": f"{' and '.join(over) if len(over) < 3 else ', '.join(over[:-1]) + ', and ' + over[-1]}. Maintain current spend until costs improve.",
                "evidence": "Costs use acquisition-cohort spend divided by outcomes from those leads. Above-target costs are not healthy.",
                "metric": "cohort_cost",
                "metric_value": None,
                "entity": {"type": "account", "id": "demo" if scope["is_demo"] else "live"},
                "proposed_action": "Keep the current budget. This screen cannot change spend.",
                "state": "open",
                "confidence": "measured",
                "owner": "Growth",
                "next_review": scope["as_of"].date().isoformat(),
                "source_timestamp": scope["as_of"].isoformat(),
                "evidence_window": {"start": scope["start"].isoformat(), "end": scope["end"].isoformat()},
            }
        )
    cpl_cents = totals.get("cpl_cents")
    if cpl_cents is not None and cpl_cents > CPL_GOAL * 100:
        recs.append(
            {
                "id": "rec_creative",
                "priority": 3,
                "title": "Review approved creative test",
                "text": "Test an approved creative against lead cost. Investigate load failures and measurement before attributing arrival loss to creative.",
                "evidence": f"Lead cost is {whole_dollars(cpl_cents)} against a ${CPL_GOAL} goal. Arrival rate is not assumed to be a creative result.",
                "metric": "cpl",
                "metric_value": money_number(cpl_cents),
                "entity": {"type": "creative_test", "id": "approved_test"},
                "proposed_action": "Compare an already approved creative on lead cost. Do not launch or edit ads from this screen.",
                "state": "open",
                "confidence": "hypothesis",
                "owner": "Growth",
                "next_review": scope["as_of"].date().isoformat(),
                "source_timestamp": scope["as_of"].isoformat(),
                "evidence_window": {"start": scope["start"].isoformat(), "end": scope["end"].isoformat()},
            }
        )
    if not recs and pace.get("delta") is not None and pace["delta"] < -0.05 and pace.get("goal"):
        recs.append(
            {
                "id": "rec_pace",
                "priority": 4,
                "title": "Leads are behind the monthly goal",
                "text": f"{totals.get('leads') or 0} leads created against a goal of {pace['goal']}.",
                "evidence": pace["label"],
                "metric": "leads_pace",
                "metric_value": totals.get("leads"),
                "entity": {"type": "goal", "id": scope.get("selected_goal_month") or "range"},
                "proposed_action": "Review pace before adding budget. This screen cannot change ads.",
                "state": "open",
                "confidence": "measured",
                "owner": "Growth",
                "next_review": scope["as_of"].date().isoformat(),
                "source_timestamp": scope["as_of"].isoformat(),
                "evidence_window": {"start": scope["start"].isoformat(), "end": scope["end"].isoformat()},
            }
        )
    recs.sort(key=lambda item: item["priority"])
    return recs[:3]


def variance_block(cents: int | None, goal: int | None) -> dict[str, Any]:
    if cents is None or goal is None:
        return {"value": money_number(cents), "goal": goal, "variance": None, "status": "unknown"}
    actual = cents / 100.0
    delta = actual - goal
    if abs(delta) < 0.001:
        status = "on_goal"
    elif delta > 0:
        status = "over"
    else:
        status = "under"
    return {
        "value": round(actual, 2),
        "goal": goal,
        "variance": round(delta, 2),
        "status": status,
    }


def build_bot(totals: dict[str, Any], pace: dict[str, Any], recs: list[dict[str, Any]], sources: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    source_states = [item.get("status") for item in sources.values()]
    broken = any(item == "error" for item in source_states)
    missing = any(item in {"unavailable", "stale", "partial"} for item in source_states)
    costs_over = any(
        block.get("status") == "over"
        for block in (totals["cpl"], totals["demo_cost"], totals["sold_cpa"])
    )
    pace_behind = pace.get("delta") is not None and pace["delta"] < -0.05
    if broken:
        overall, label = "incident", "INCIDENT · Source error"
    elif missing:
        overall, label = "unknown", "UNKNOWN · Source missing"
    elif pace_behind and costs_over:
        overall, label = "watch", "WATCH · Lead pace & costs"
    elif pace_behind:
        overall, label = "watch", "WATCH · Lead pace"
    elif costs_over:
        overall, label = "watch", "WATCH · Costs"
    else:
        overall, label = "healthy", "Healthy"
    accepted = totals.get("submissions_accepted")
    delivered = totals.get("submissions_delivered")
    if accepted is None or delivered is None:
        delivery = {"status": "unknown", "label": "CRM delivery unavailable"}
    else:
        delivery = {
            "status": "ok" if delivered == accepted else "watch",
            "accepted": accepted,
            "delivered": delivered,
            "label": f"{delivered} of {accepted} submissions reached CRM",
        }
    tracking = "unknown" if missing or broken else "healthy"
    next_title = recs[0]["title"] if recs else ("No action required" if overall == "healthy" else "No recommendation until sources are fresh")
    next_detail = recs[0]["text"] if recs else ""
    if recs and recs[0]["id"] == "rec_form_start":
        next_detail = "Largest drop between landing visit and form start."
    return {
        "overall": overall,
        "label": label,
        "tracking": tracking,
        "tracking_label": "Tracking healthy" if tracking == "healthy" else "Tracking unknown",
        "crm_delivery": delivery,
        "last_sync": scope["as_of"].isoformat(),
        "last_sync_label": fmt_sync(scope["as_of"]),
        "cutoff_label": f"Completed through {fmt_day(scope['cutoff'])}, {scope['cutoff'].year}",
        "next_action": next_title,
        "next_action_detail": next_detail,
    }


def _empty_sources(status: str, detail: str, reason: str | None = None) -> dict[str, Any]:
    return {
        key: _source(status, detail, reason=reason)
        for key in ("meta_ads", "website_analytics", "submissions", "crm")
    }


def assemble(days: list[dict[str, Any]], catalog: list[dict[str, Any]], scope: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    cutoff = scope["cutoff"]
    window_days = filter_days(days, scope["start"], scope["end"], cutoff)
    meta_ok = sources.get("meta_ads", {}).get("status") == "ok"
    web_ok = sources.get("website_analytics", {}).get("status") == "ok"
    sub_ok = sources.get("submissions", {}).get("status") == "ok"
    crm_ok = sources.get("crm", {}).get("status") == "ok"
    spend_cents = sum(day_ad_spend(day) for day in window_days) if meta_ok else None
    impressions = None
    clicks = None
    if meta_ok:
        impressions = 0
        clicks = 0
        for day in window_days:
            for metrics in (day.get("ads") or {}).values():
                impressions += int(metrics.get("impressions") or 0)
                clicks += int(metrics.get("outbound_clicks") or 0)
    visits = sum(int(day.get("visits") or 0) for day in window_days) if web_ok else None
    starts = sum(int(day.get("form_starts") or 0) for day in window_days) if web_ok else None
    accepted = sum(int(day.get("submissions_accepted") or 0) for day in window_days) if sub_ok else None
    delivered = sum(int(day.get("submissions_delivered") or 0) for day in window_days) if sub_ok else None
    raw_leads = []
    for day in window_days:
        raw_leads.extend(day.get("leads") or [])
    counted = lead_counts(raw_leads) if crm_ok else {"leads": [], "count": None, "duplicates_excluded": None, "tests_excluded": None, "invalid_kept_in_denominator": None}
    outcomes = outcome_sets(counted["leads"], cutoff) if crm_ok else {"demos": None, "sold": None, "sold_contacts": [], "sale_cancelled_included": None}
    lead_n = counted["count"]
    cpl = cost_cents(spend_cents, lead_n)
    demo_cost = cost_cents(spend_cents, outcomes["demos"])
    sold_cpa = cost_cents(spend_cents, outcomes["sold"])
    ads = build_ads(window_days, catalog, cutoff) if meta_ok else []
    active = None
    rejected = None
    if meta_ok:
        # Count an ad only when this range actually contains its rows.
        # A zero-spend row still counts as active; a missing row does not.
        active = sum(
            1
            for row in ads
            if row.get("effective_status") == "active" and row.get("spend_cents") is not None
        )
        rejected = sum(1 for row in ads if row.get("rejected") and row.get("spend_cents") is not None)
    totals = {
        "spend_cents": spend_cents,
        "impressions": impressions,
        "outbound_clicks": clicks,
        "visits": visits,
        "form_starts": starts,
        "submissions_accepted": accepted,
        "submissions_delivered": delivered,
        "leads": lead_n,
        "demos": outcomes["demos"],
        "sold": outcomes["sold"],
        "cpl_cents": cpl,
        "demo_cost_cents": demo_cost,
        "sold_cpa_cents": sold_cpa,
        "cpl": variance_block(cpl, CPL_GOAL if cpl is not None else None),
        "demo_cost": variance_block(demo_cost, DEMO_COST_GOAL if demo_cost is not None else None),
        "sold_cpa": variance_block(sold_cpa, SOLD_CPA_GOAL if sold_cpa is not None else None),
        "lead_audit": {
            "duplicates_excluded": counted["duplicates_excluded"],
            "tests_excluded": counted["tests_excluded"],
            "invalid_kept_in_denominator": counted["invalid_kept_in_denominator"],
            "sale_cancelled_included": outcomes["sale_cancelled_included"],
        },
    }
    pace = pace_block(scope, lead_n or 0)
    if lead_n is None:
        pace = {
            "goal": pace.get("goal"),
            "expected": None,
            "delta": None,
            "label": "Pace N/A",
            "attained": None,
            "reason": "leads_unavailable",
        }
    funnel = build_funnel(totals)
    recs = []
    if not any(item.get("status") in {"unavailable", "error", "stale"} for item in sources.values()):
        recs = build_recommendations(totals, pace, scope)
    elif cpl is not None and totals["cpl"]["status"] == "over":
        recs = build_recommendations(totals, pace, scope)
        recs = [rec for rec in recs if rec["id"] in {"rec_hold_scaling", "rec_creative"}]
    bot = build_bot(totals, pace, recs, sources, scope)
    goal_month = scope.get("selected_goal_month")
    if len(scope["months"]) == 1 and goal_month:
        parsed = parse_ymd(goal_month + "-01")
        goal_leads = leads_goal_for_month(parsed.year, parsed.month) if parsed else None
    elif scope["full_months"]:
        goal_leads = pace.get("goal")
    else:
        goal_leads = None
    kpis = {
        "leads": {
            "actual": lead_n,
            "goal": pace.get("goal") if pace.get("reason") != "leads_unavailable" else goal_leads,
            "attained": pace.get("attained"),
            "expected_pace": pace.get("expected"),
            "pace_delta": pace.get("delta"),
            "pace_label": pace.get("label"),
            "progress": None if lead_n is None or not pace.get("goal") else min(lead_n / pace["goal"], 1),
        },
        "cpl": totals["cpl"],
        "demos": {"value": outcomes["demos"]},
        "demo_cost": {**totals["demo_cost"], "cohort": "acquisition", "provisional": True},
        "sold": {"value": outcomes["sold"], "sale_cancelled_included": outcomes["sale_cancelled_included"]},
        "sold_cpa": {**totals["sold_cpa"], "cohort": "acquisition", "provisional": True, "maturity": "Sales still maturing"},
        "spend": {
            "value": money_number(spend_cents),
            "cap": MONTHLY_SPEND_CAP,
            "cap_label": "Not configured" if MONTHLY_SPEND_CAP is None else whole_dollars(MONTHLY_SPEND_CAP * 100),
        },
        "active_ads": {
            "effective": active,
            "rejected": rejected,
            "delivering": sum(1 for row in ads if row.get("delivering")) if meta_ok else None,
            "note": "Effective active includes an ad with zero spend. Delivering means it spent in this range.",
        },
    }
    return {
        "metric": "Growth command center",
        "read_only": True,
        "mutations": [],
        "mode": scope["mode"],
        "is_demo": scope["is_demo"],
        "sample_data": scope["is_demo"],
        "validated_live": False,
        "badge": "SAMPLE DATA" if scope["is_demo"] else "LIVE · UNVALIDATED",
        "currency": CURRENCY,
        "account_timezone": TIMEZONE_NAME,
        "account_id": "demo" if scope["is_demo"] else None,
        "preset": scope["preset"],
        "selected_range": {
            "start": scope["start"].isoformat(),
            "end": scope["end"].isoformat(),
            "label": fmt_range(scope["start"], scope["end"]),
        },
        "goal_month": goal_month if not scope["goal_month_ambiguous"] else None,
        "goal_month_ambiguous": scope["goal_month_ambiguous"],
        "goal_months_available": [f"{year:04d}-{month:02d}" for year, month in scope["months"]],
        "as_of": scope["as_of"].isoformat(),
        "as_of_label": fmt_as_of(scope["as_of"]),
        "data_cutoff": cutoff.isoformat(),
        "cutoff_label": f"Completed through {fmt_day(cutoff)}, {cutoff.year}",
        "range_error": scope.get("error"),
        "goals": {
            "leads_by_month": dict(LEADS_GOAL_BY_MONTH),
            "leads": kpis["leads"]["goal"],
            "cpl": CPL_GOAL,
            "demo_cost": DEMO_COST_GOAL,
            "sold_cpa": SOLD_CPA_GOAL,
            "monthly_spend_cap": MONTHLY_SPEND_CAP,
            "monthly_spend_cap_label": "Not configured",
        },
        "kpis": kpis,
        "funnel": funnel,
        "ads": ads,
        "bot": bot,
        "recommendations": recs,
        "charts": {
            "leads": lead_series(window_days, scope, counted["leads"] if crm_ok else []),
            "costs": cost_series(window_days, scope) if meta_ok and crm_ok else {
                "goals": {"cpl": CPL_GOAL, "demo": DEMO_COST_GOAL, "sold": SOLD_CPA_GOAL},
                "provisional": True,
                "label": "Acquisition cohort · sales still maturing",
                "series": {"cpl": [], "demo": [], "sold": []},
                "summary": {},
                "status": "unavailable",
            },
        },
        "sources": sources,
        "lead_rows": [
            {
                "id": lead["id"],
                "contact_id": lead["contact_id"],
                "acquired_on": lead["acquired_on"],
                "ad_id": lead.get("ad_id"),
                "demo": bool(lead.get("demo_id")) and demo_eligible(lead, cutoff),
                "sold": sold_eligible(lead, cutoff),
                "invalid": bool(lead.get("invalid")),
            }
            for lead in (counted["leads"] if crm_ok else [])
        ],
        "definitions": definitions(),
        "links": {
            "page": "/api/growth_command_center",
            "json": "/api/metrics/growth_command_center",
            "growth": "/growth",
            "website_funnel": "/api/website_funnel",
            "website_traffic": "/api/website_traffic",
            "inbound_cac": "/api/inbound_cac",
        },
    }


def definitions() -> dict[str, str]:
    return {
        "lead_created": (
            "Website form fill attributed as inbound, same grain as inbound CAC "
            "named fills in web_funnel_named_fills_v1. Not every opportunity in "
            f"pipeline {INBOUND_PIPELINE_ID} ({INBOUND_PIPELINE_NAME}). "
            "Test fills are excluded. Duplicate flags are excluded. Invalid flags "
            "stay in the denominator and are counted beside it."
        ),
        "opp": (
            "A separate opportunity on that contact in Buffalo, Rochester, Syracuse, "
            "or Virtual only. Opp count is not an Overview KPI."
        ),
        "demo": (
            "Existing CRM demo definition on Buffalo, Rochester, Syracuse, or Virtual. "
            "Cohort demos are linked to leads acquired in the selected range and "
            "observed by the completed-day cutoff."
        ),
        "sold": (
            "Distinct contactId on Sold or Sale Cancelled stage IDs "
            f"{', '.join(SOLD_STAGE_IDS)} with Contact Sold Date "
            f"{SOLD_DATE_CUSTOM_FIELD_ID}, date-only, {TIMEZONE_NAME}. "
            "Sale Cancelled remains in the count. Missing Sold Date is excluded."
        ),
        "cpl": "Spend divided by new ad-sourced leads created. Not an average of row CPLs.",
        "demo_cost": "Acquisition-cohort spend divided by cohort demos. Blank when demos are 0.",
        "sold_cpa": "Acquisition-cohort spend divided by cohort sold contacts. Blank when sold is 0.",
        "spend_cap": "No monthly spend cap is configured. The demo does not invent one.",
        "read_only": "This dashboard does not create, edit, pause, or budget ads.",
    }


def demo_sources() -> dict[str, Any]:
    return {
        "meta_ads": _source("ok", "Sample ad spend, impressions, and outbound clicks. Not the live account."),
        "website_analytics": _source("ok", "Sample landing visits and form starts. Not a live GA4 pull."),
        "submissions": _source("ok", "Sample accepted submissions, all marked delivered in the fixture."),
        "crm": _source("ok", "Sample cohort demos and one sold deal linked to the fixture leads."),
    }


def compute_payload(params: dict[str, str] | None = None, *, now: datetime | None = None, live_loader: Callable | None = None) -> dict[str, Any]:
    scope = resolve_scope(params or {}, now=now)
    if scope["mode"] == "demo":
        days = build_fixture_days()
        return assemble(days, list(AD_CATALOG), scope, demo_sources())
    loader = live_loader or load_live
    try:
        live = loader(scope)
    except Exception as exc:
        live = {
            "days": [],
            "catalog": [],
            "sources": _empty_sources("error", "Live read failed.", reason=type(exc).__name__),
        }
    return assemble(
        list(live.get("days") or []),
        list(live.get("catalog") or []),
        scope,
        live.get("sources") or _empty_sources("unavailable", "Live source missing.", reason="missing"),
    )


def load_live(scope: dict[str, Any]) -> dict[str, Any]:
    """Read-only live attempt. Failures become unavailable sources, never demo numbers."""
    sources = _empty_sources("unavailable", "Not loaded.", reason="not_loaded")
    days: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    start = scope["start"]
    end = min(scope["end"], scope["cutoff"])
    meta_days, meta_catalog, meta_source = _live_meta(start, end)
    sources["meta_ads"] = meta_source
    web_days, web_source = _live_website(start, end)
    sources["website_analytics"] = web_source
    fill_days, fill_source = _live_fills(start, end)
    sources["submissions"] = fill_source
    sources["crm"] = _source(
        "unavailable",
        "Named fills do not carry a GHL contact id, so demos and sold deals cannot be joined to the acquisition cohort. Calendar sits are not substituted.",
        reason="lead_to_crm_contact_join_not_validated",
    )
    by_date: dict[str, dict[str, Any]] = {}
    for bucket in (meta_days, web_days, fill_days):
        for row in bucket:
            current = by_date.setdefault(
                row["date"],
                {
                    "date": row["date"],
                    "visits": None,
                    "form_starts": None,
                    "submissions_accepted": None,
                    "submissions_delivered": None,
                    "ads": {},
                    "leads": [],
                    "spend_cents": None,
                },
            )
            for key in ("visits", "form_starts", "submissions_accepted", "submissions_delivered", "spend_cents"):
                if row.get(key) is not None:
                    current[key] = row[key]
            if row.get("ads"):
                current["ads"] = row["ads"]
            if row.get("leads"):
                current["leads"] = row["leads"]
    if meta_source.get("status") != "ok":
        for row in by_date.values():
            row["spend_cents"] = None
            row["ads"] = {}
    if web_source.get("status") != "ok":
        for row in by_date.values():
            row["visits"] = None
            row["form_starts"] = None
    if fill_source.get("status") != "ok":
        for row in by_date.values():
            row["leads"] = []
            row["submissions_accepted"] = None
            row["submissions_delivered"] = None
    days = [by_date[key] for key in sorted(by_date)]
    catalog = meta_catalog
    return {"days": days, "catalog": catalog, "sources": sources}


def _live_meta(start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        from inbound_cac import read_meta_ads_credentials
    except Exception as exc:
        return [], [], _source("unavailable", "Meta helper could not be loaded.", reason=type(exc).__name__)
    token, account_id, reason = read_meta_ads_credentials()
    if reason:
        return [], [], _source("unavailable", "Meta Ads credentials are not set on the server.", reason=reason)
    try:
        rows = _meta_insights(token, account_id, start.isoformat(), end.isoformat(), level="ad", time_increment="1")
    except Exception as exc:
        return [], [], _source("unavailable", "Meta insights request failed.", reason=type(exc).__name__)
    if rows is None:
        return [], [], _source("unavailable", "Meta insights request failed.", reason="graph_request_failed")
    days: dict[str, dict[str, Any]] = {}
    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        ad_id = str(row.get("ad_id") or "")
        day = str(row.get("date_start") or "")[:10]
        if not ad_id or len(day) != 10:
            continue
        spend = _dollars_to_cents(row.get("spend"))
        impressions = _optional_int(row.get("impressions"))
        clicks = _outbound_clicks(row)
        bucket = days.setdefault(
            day,
            {"date": day, "ads": {}, "spend_cents": 0, "leads": [], "visits": None, "form_starts": None, "submissions_accepted": None, "submissions_delivered": None},
        )
        bucket["ads"][ad_id] = {
            "spend_cents": spend or 0,
            "impressions": impressions or 0,
            "outbound_clicks": clicks or 0,
        }
        bucket["spend_cents"] += spend or 0
        catalog.setdefault(
            ad_id,
            {
                "id": ad_id,
                "name": row.get("ad_name") or ad_id,
                "copy": "",
                "campaign_id": row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "adset_id": row.get("adset_id"),
                "platform": "meta",
                "configured_status": "unknown",
                "effective_status": "unknown",
                "rejected": False,
                "thumbnail": "fallback",
                "landing_url": None,
            },
        )
    return list(days.values()), list(catalog.values()), _source(
        "ok",
        "Read-only Meta insights. Effective status was not requested, so active-ad count stays unknown. No ad was changed.",
    )


def _meta_insights(token: str, account_id: str, since: str, until: str, *, level: str, time_increment: str | None) -> list[dict[str, Any]] | None:
    import urllib.parse
    import urllib.request

    params = {
        "fields": "ad_id,ad_name,campaign_id,campaign_name,adset_id,impressions,spend,inline_link_clicks,outbound_clicks",
        "level": level,
        "access_token": token,
        "time_range": json.dumps({"since": since, "until": until}, separators=(",", ":")),
        "limit": "500",
    }
    if time_increment:
        params["time_increment"] = time_increment
    url = f"https://graph.facebook.com/v21.0/{urllib.parse.quote(account_id)}/insights?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None
    return [row for row in data if isinstance(row, dict)]


def _dollars_to_cents(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _outbound_clicks(row: dict[str, Any]) -> int | None:
    outbound = row.get("outbound_clicks")
    if isinstance(outbound, list):
        total = 0
        found = False
        for item in outbound:
            if isinstance(item, dict) and item.get("value") is not None:
                parsed = _optional_int(item.get("value"))
                if parsed is not None:
                    total += parsed
                    found = True
        if found:
            return total
    parsed = _optional_int(row.get("inline_link_clicks"))
    return parsed


def _live_website(start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from sales import get_db
        db = get_db()
    except Exception as exc:
        return [], _source("unavailable", "Website warehouse is not configured on the server.", reason=type(exc).__name__)
    dates = [day.isoformat() for day in iter_dates(start, end)]
    try:
        refs = [db.collection("web_funnel_daily_v1").document(day) for day in dates]
        snaps = list(db.get_all(refs))
    except Exception as exc:
        return [], _source("unavailable", "Website daily docs could not be read.", reason=type(exc).__name__)
    by_id = {}
    for snap in snaps:
        doc_id = getattr(snap, "id", None)
        data = snap.to_dict() if hasattr(snap, "to_dict") else None
        if doc_id and isinstance(data, dict):
            by_id[doc_id] = data
    if len(by_id) != len(dates):
        return [], _source(
            "partial",
            "One or more website days are missing. Totals are withheld so a partial sum cannot look like a drop.",
            reason="missing_daily_docs",
        )
    rows = []
    for day in dates:
        doc = by_id[day]
        visits = doc.get("visits_total")
        if visits is None:
            visits = doc.get("sessions")
        starts = doc.get("estimate_start")
        if starts is None:
            starts = doc.get("starts")
        if visits is None or starts is None:
            return [], _source("unavailable", "A website day has no visit or form-start count.", reason="null_daily_metric")
        rows.append({"date": day, "visits": int(visits), "form_starts": int(starts)})
    return rows, _source("ok", "Landing visits and form starts from web_funnel_daily_v1. Not a person-level join to Meta.")


def _live_fills(start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from sales import get_db
        from funnel_test_address import fetch_named_fills
        from inbound_cac import inbound_named_fill_is_live
        db = get_db()
    except Exception as exc:
        return [], _source("unavailable", "Form-fill warehouse is not configured on the server.", reason=type(exc).__name__)
    rows = []
    try:
        for day in iter_dates(start, end):
            fills = fetch_named_fills(db, day.isoformat())
            live = [fill for fill in fills if inbound_named_fill_is_live(fill)]
            leads = []
            for index, fill in enumerate(live):
                leads.append(
                    {
                        "id": f"fill_{day.isoformat()}_{index}",
                        "contact_id": fill.get("contact_id") or fill.get("contactId") or f"fill_{day.isoformat()}_{index}",
                        "acquired_on": day.isoformat(),
                        "ad_id": fill.get("ad_id"),
                        "pipeline_id": None,
                        "duplicate": bool(fill.get("duplicate")),
                        "test": False,
                        "invalid": bool(fill.get("invalid")),
                        "demo_id": None,
                        "demo_observed_on": None,
                        "sold_id": None,
                        "sold_on": None,
                        "sold_observed_on": None,
                        "sale_cancelled": False,
                        "stage_group": None,
                    }
                )
            rows.append(
                {
                    "date": day.isoformat(),
                    "leads": leads,
                    "submissions_accepted": len(leads),
                    "submissions_delivered": None,
                }
            )
    except Exception as exc:
        return [], _source("unavailable", "Named fills could not be read.", reason=type(exc).__name__)
    return rows, _source(
        "ok",
        "Accepted submissions are live named fills. CRM delivery is a separate join and is not marked delivered from the fill alone.",
    )


def _query_params(path: str) -> dict[str, str]:
    qs = parse_qs(urlparse(path).query)
    return {key: values[-1] for key, values in qs.items() if values}


def _write(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = compute_payload(_query_params(self.path))
            _write(self, 200, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")
        except Exception as exc:
            _write(self, 500, json.dumps({"error": str(exc), "read_only": True}).encode("utf-8"), "application/json; charset=utf-8")

    def do_POST(self):
        _write(
            self,
            405,
            json.dumps({"error": "Growth Command Center is view-only.", "read_only": True}).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_PUT(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()
