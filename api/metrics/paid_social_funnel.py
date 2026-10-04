# -*- coding: utf-8 -*-

"""Paid social funnel. Read-only.

Lead: an opportunity on pipeline Inbound/Lead Locker
(7nSEgeoBYXZiIS7x41Jy) whose contact Lead Gen Source
(hd5QqHEOVSsPom5bJ32P) strips to Inbound, case-insensitive.
3PL does not count. A blank field does not count.
Title buckets are not the lead number. The inbound CAC form-fill
row is not the lead number.

Opp: a separate opportunity for that same lead contact in Buffalo,
Rochester, Syracuse, or Virtual, dated by that territory
opportunity's createdAt in America/New_York.

Demos: distinct territory opportunity with the existing demo
disposition and appointmentOccurredAt in the window, limited to
those lead contacts.

Sales: distinct contactId with Contact Sold Date
P9oBjgbZjJdeE0OkBj9T in the window, limited to those lead contacts.
Uses SalesMetricContract stage ids. Does not change that contract.

Meta account act_1624979685613708 is read-only. This module does not
send campaign, budget, or ad updates.

Landing visits and form starts are a read of the existing GA4 property.
A failed read stays null. This module does not change the calculator form.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))


def _load_inbound_cac():
    """Load the metrics module, not the /api/inbound_cac page."""
    name = "hs_paid_social_inbound_cac"
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "TIMEZONE_NAME", None):
        return existing
    spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "inbound_cac.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load inbound CAC metric")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cac = _load_inbound_cac()

TIMEZONE_NAME = cac.TIMEZONE_NAME
LEAD_PIPELINE_ID = cac.INBOUND_PIPELINE_ID
LEAD_PIPELINE_NAME = cac.INBOUND_PIPELINE_NAME
SOURCE_FIELD_ID = cac.LEAD_GEN_SOURCE_CONTACT_CF_ID
SOURCE_FIELD_NAME = "Lead Gen Source"
SOURCE_VALUE = "Inbound"
SOLD_DATE_FIELD_ID = cac.SOLD_DATE_CUSTOM_FIELD_ID
META_ACCOUNT_ID = "act_1624979685613708"
META_CAMPAIGN_NOT_MODIFIED = "120251885305880744"
GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID = "408492342"
FORM_START_EVENT = "estimate_start"
FINISHED_FORM_EVENT = "estimate_submit"
PAID_GA4_DIMENSIONS = (
    "date",
    "sessionDefaultChannelGroup",
    "sessionSource",
    "sessionMedium",
)
CPL_TARGET = 25
DEMO_COST_TARGET = 50
CPA_TARGET = 200
META_INSIGHT_FIELDS = "impressions,outbound_clicks,spend"
MAX_RANGE_DAYS = 366

TERRITORY_PIPELINE_NAMES = {
    "GQtUlcTmLJ61HZjrGEPC": "Buffalo",
    "qJNvqKWp8Xc7DaBr8QYc": "Rochester",
    "etLURrEVxupngZZRlISG": "Syracuse",
    "r1b9pwgliYj7WyWBchTV": "Virtual",
}

UNMATCHED_SPEND_NOTE = (
    "Unmatched Meta spend. This is Meta account spend. "
    "It is not tied to a lead or an opp."
)
VISITORS_NOTE = (
    "Website visitors are GA4 paid sessions on stream G-V02RZFR4SZ. "
    "That series is not wired on this page, so it stays blank. "
    "Meta landing-page views are not used."
)
VISITS_OK_NOTE = (
    "Website visitors are GA4 paid sessions on property 408492342, "
    "measurement G-V02RZFR4SZ. The website traffic paid-session rule: "
    "paid medium or paid channel, Facebook and Instagram included. "
    "A Meta click is not a session. Meta landing-page views are not visits."
)
VISITS_UNAVAILABLE_NOTE = (
    "Website visitors are GA4 paid sessions on property 408492342, "
    "measurement G-V02RZFR4SZ. This read is unavailable, so the stage stays "
    "blank. A failed read is not zero. The November sample is not used. "
    "Meta landing-page views are not visits."
)
FORMS_OK_NOTE = (
    "Form starts are calculator estimate_start events from paid traffic, "
    "using the same paid-session rule as landing visits. A finished form "
    "(estimate_submit) is not a form start. Instant Form and 3PL are not "
    "form starts."
)
FORMS_UNAVAILABLE_NOTE = (
    "Form starts are calculator estimate_start events from paid traffic. "
    "This read is unavailable, so the stage stays blank. A failed read is "
    "not zero. The November sample is not used. A finished form "
    "(estimate_submit) is not a form start. Instant Form and 3PL are not "
    "form starts."
)
FORMS_UNWIRED_NOTE = (
    "Form starts are not wired on this read, so the stage stays blank. "
    "A missing read is not zero. The November sample is not used."
)
LEAD_ACTIONS_NOTE = (
    "Meta lead actions are not shown. They were absent, not zero."
)
LEAD_NOTE = (
    "A lead is an opportunity in Inbound/Lead Locker whose Lead Gen Source "
    "strips to Inbound. 3PL does not count. A blank field does not count. "
    "Title buckets are not this number."
)
OPP_NOTE = (
    "An opp is a separate opportunity for that same lead contact in "
    "Buffalo, Rochester, Syracuse, or Virtual, dated by that opportunity's "
    "created time in America/New_York."
)
DEMO_NOTE = (
    "A demo is a distinct territory opportunity with the existing demo "
    "disposition and appointment time in this window, limited to these "
    "lead contacts."
)
SALES_NOTE = (
    "A sold deal is a distinct contact whose Sold Date falls in this window, "
    "limited to these lead contacts. The sales metric contract is unchanged."
)


def territory_name(pipeline_id: Any) -> str | None:
    return TERRITORY_PIPELINE_NAMES.get(cac.compact_str(pipeline_id))


def source_is_inbound(contact: dict[str, Any] | None) -> bool:
    """True only when Lead Gen Source strips to Inbound. 3PL and blank do not."""
    raw = cac.contact_custom_field(contact, SOURCE_FIELD_ID)
    return cac.is_inbound_lead_source(raw)


def source_label(contact: dict[str, Any] | None) -> str:
    raw = cac.contact_custom_field(contact, SOURCE_FIELD_ID)
    if raw is None:
        return "(blank)"
    text = str(raw).strip()
    if not text:
        return "(blank)"
    return text


def window_dates(start_local: datetime, end_local: datetime) -> list[str]:
    days: list[str] = []
    cursor = start_local.date()
    end_day = end_local.date()
    while cursor < end_day:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def _day_key(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.date().isoformat()


def _series(days: list[str], counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"date": day, "value": int(counts.get(day) or 0)} for day in days]


def _bump(counts: dict[str, int], day: str | None) -> None:
    if day:
        counts[day] = counts.get(day, 0) + 1


def count_paid_social(
    pipeline_opps: list[dict[str, Any]],
    territory_created: list[cac.TerritoryOpp],
    territory_demos: list[cac.TerritoryOpp],
    sold_contact_ids: set[str],
    contacts: dict[str, dict],
    start_local: datetime,
    end_local: datetime,
    now_utc: datetime,
) -> dict[str, Any]:
    """Count one window. Lead and opp numbers come only from the source filter."""
    days = window_dates(start_local, end_local)
    lead_ids: set[str] = set()
    lead_contacts: set[str] = set()
    lead_days: dict[str, int] = {}
    matched_values: dict[str, int] = {}
    excluded: dict[str, int] = {}
    refunded_leads = 0
    pipeline_in_window = 0
    unparsed_created = 0

    for index, opp in enumerate(pipeline_opps):
        if cac.compact_str(opp.get("pipelineId")) != LEAD_PIPELINE_ID:
            continue
        created = cac.parse_iso_dt(opp.get(cac.CREATED_AT_FIELD))
        if created is None:
            unparsed_created += 1
            continue
        created_local = created.astimezone(start_local.tzinfo)
        if not (start_local <= created_local < end_local):
            continue
        pipeline_in_window += 1
        contact_id = cac.compact_str(opp.get("contactId"))
        contact = contacts.get(contact_id) if contact_id else None
        label = source_label(contact)
        if not source_is_inbound(contact):
            excluded[label] = excluded.get(label, 0) + 1
            continue
        lead_id = cac.compact_str(opp.get("id")) or f"lead:{index}:{contact_id}"
        if lead_id in lead_ids:
            continue
        lead_ids.add(lead_id)
        if contact_id:
            lead_contacts.add(contact_id)
        matched_values[label] = matched_values.get(label, 0) + 1
        if cac.is_refunded_stage(opp.get(cac.STAGE_FIELD)):
            refunded_leads += 1
        _bump(lead_days, _day_key(created_local))

    opp_ids: set[str] = set()
    opp_days: dict[str, int] = {}
    by_territory = {name: 0 for name in TERRITORY_PIPELINE_NAMES.values()}
    for opp in territory_created:
        if not cac.is_territory_pipeline(opp.pipeline_id):
            continue
        if opp.contact_id not in lead_contacts:
            continue
        if not cac.territory_created_in_window(opp, start_local, end_local):
            continue
        if not opp.opportunity_id or opp.opportunity_id in opp_ids:
            continue
        opp_ids.add(opp.opportunity_id)
        name = territory_name(opp.pipeline_id)
        if name:
            by_territory[name] = by_territory.get(name, 0) + 1
        _bump(opp_days, _day_key(opp.created_local))

    demo_ids: set[str] = set()
    demo_days: dict[str, int] = {}
    for opp in territory_demos:
        if opp.contact_id not in lead_contacts:
            continue
        if not cac.territory_sit_in_window(opp, start_local, end_local, now_utc):
            continue
        if opp.opportunity_id:
            demo_ids.add(opp.opportunity_id)
        if opp.occurred_utc is not None and start_local.tzinfo is not None:
            occurred_local = opp.occurred_utc.astimezone(start_local.tzinfo)
            _bump(demo_days, _day_key(occurred_local))

    sales: set[str] = set()
    sale_days: dict[str, int] = {}
    for contact_id in lead_contacts:
        if contact_id not in sold_contact_ids:
            continue
        sold_date = cac.extract_sold_date_ymd(contacts.get(contact_id))
        if cac.sold_date_in_window(sold_date, start_local, end_local):
            sales.add(contact_id)
            _bump(sale_days, sold_date)

    return {
        "leads": len(lead_ids),
        "lead_contacts": lead_contacts,
        "lead_series": _series(days, lead_days),
        "matched_source_values": matched_values,
        "excluded_by_source": excluded,
        "refunded_leads": refunded_leads,
        "pipeline_opportunities_in_window": pipeline_in_window,
        "unparsed_created_at": unparsed_created,
        "opps": len(opp_ids),
        "opp_series": _series(days, opp_days),
        "opps_by_territory": by_territory,
        "demos": len(demo_ids),
        "demo_series": _series(days, demo_days),
        "sales": len(sales),
        "sale_series": _series(days, sale_days),
        "days": days,
    }


def _optional_int(value: Any, present: bool) -> int | None:
    if not present or value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _outbound_click_count(row: dict[str, Any]) -> int | None:
    """Meta outbound_clicks is a list of action stats, not the lead actions field."""
    if "outbound_clicks" not in row:
        return None
    value = row.get("outbound_clicks")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("action_type") == "outbound_click":
                return _optional_int(item.get("value"), True)
        return None
    return _optional_int(value, True)


def insights_request_url(account_id: str, token: str, since: str, until: str, time_increment: str | None) -> str:
    """Account insights GET. Impressions, outbound clicks, and spend. No lead actions."""
    fields = [part.strip() for part in META_INSIGHT_FIELDS.split(",") if part.strip()]
    if "actions" in fields:
        raise RuntimeError("Meta lead actions are not requested")
    if account_id != META_ACCOUNT_ID:
        raise RuntimeError("Refusing a Meta read for a different account")
    params = {
        "fields": META_INSIGHT_FIELDS,
        "level": "account",
        "access_token": token,
        "time_range": json.dumps({"since": since, "until": until}, separators=(",", ":")),
    }
    if time_increment:
        params["time_increment"] = time_increment
    return (
        f"{cac.META_GRAPH_API_HOST}/{cac.META_GRAPH_API_VERSION}/"
        f"{urllib.parse.quote(account_id)}/insights?{urllib.parse.urlencode(params)}"
    )


def _read_insights(url: str, urlopen: Any) -> dict[str, Any] | None:
    opener = urlopen or urllib.request.urlopen
    req = urllib.request.Request(url, method="GET")
    with opener(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def _insight_rows(payload: dict[str, Any] | None, urlopen: Any) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    ignored_actions = False
    seen: set[str] = set()
    current = payload
    pages = 0
    while isinstance(current, dict) and pages < 20:
        pages += 1
        data = current.get("data")
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    if "actions" in row:
                        ignored_actions = True
                    rows.append(row)
        next_url = str(((current.get("paging") or {}).get("next")) or "")
        if not next_url or next_url in seen:
            break
        if not next_url.startswith(f"{cac.META_GRAPH_API_HOST}/"):
            break
        if META_CAMPAIGN_NOT_MODIFIED in urllib.parse.urlparse(next_url).path:
            break
        seen.add(next_url)
        try:
            current = _read_insights(next_url, urlopen)
        except Exception:
            break
    return rows, ignored_actions


def fetch_meta_daily(
    start_local: datetime,
    end_local: datetime,
    *,
    token: str | None = None,
    account_id: str | None = None,
    urlopen: Any = None,
) -> dict[str, Any]:
    bounds = cac.meta_date_bounds(start_local, end_local)
    if bounds is None:
        return {"status": "unavailable", "reason": "empty_window", "rows": [], "lead_actions_ignored": False}
    since, until = bounds
    if token is None or account_id is None:
        token, account_id, reason = cac.read_meta_ads_credentials()
        if reason:
            return {"status": "unavailable", "reason": reason, "rows": [], "since": since, "until": until, "lead_actions_ignored": False}
    if account_id != META_ACCOUNT_ID:
        return {
            "status": "unavailable",
            "reason": "account_mismatch",
            "account_id": account_id,
            "rows": [],
            "since": since,
            "until": until,
            "lead_actions_ignored": False,
        }
    try:
        url = insights_request_url(account_id, token, since, until, "1")
    except RuntimeError as exc:
        return {"status": "unavailable", "reason": str(exc), "rows": [], "lead_actions_ignored": False}
    try:
        payload = _read_insights(url, urlopen)
    except urllib.error.HTTPError as exc:
        code = getattr(exc, "code", None)
        reason = "graph_auth_error" if code in (401, 403) else f"graph_http_{code}"
        return {"status": "unavailable", "reason": reason, "rows": [], "account_id": account_id, "lead_actions_ignored": False}
    except Exception:
        return {"status": "unavailable", "reason": "graph_request_failed", "rows": [], "account_id": account_id, "lead_actions_ignored": False}
    if not payload or payload.get("error"):
        return {"status": "unavailable", "reason": "graph_error", "rows": [], "account_id": account_id, "lead_actions_ignored": False}
    raw_rows, ignored_actions = _insight_rows(payload, urlopen)
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        day = cac.compact_str(row.get("date_start"))[:10]
        rows.append(
            {
                "date": day,
                "impressions": _optional_int(row.get("impressions"), "impressions" in row),
                "clicks": _optional_int(row.get("clicks"), "clicks" in row),
                "outbound_clicks": _outbound_click_count(row),
                "spend": cac.parse_meta_spend_value(row.get("spend")) if "spend" in row else None,
            }
        )
    return {
        "status": "ok",
        "reason": None,
        "account_id": account_id,
        "since": since,
        "until": until,
        "rows": rows,
        "lead_actions_ignored": ignored_actions,
    }


def _point_series(days: list[str], rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_day = {cac.compact_str(row.get("date"))[:10]: row.get(key) for row in rows}
    series = []
    for day in days:
        if day not in by_day:
            series.append({"date": day, "value": None})
            continue
        series.append({"date": day, "value": by_day[day]})
    return series


def _sum_present(rows: list[dict[str, Any]], key: str) -> float | int | None:
    total = 0
    seen = False
    numeric = 0.0
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        seen = True
        numeric += float(value)
        total += value if isinstance(value, int) and key != "spend" else 0
    if not seen:
        return None
    if key == "spend":
        return round(numeric, 2)
    return int(numeric)


def _unit_cost(spend: float | None, count: int | None) -> float | None:
    if spend is None or count is None or int(count) == 0:
        return None
    return round(float(spend) / int(count), 2)


def _spend_block(aggregate: cac.MetaSpendResult | None, daily_rows: list[dict[str, Any]], daily_status: str) -> dict[str, Any]:
    aggregate_spend = None
    aggregate_status = "unavailable"
    aggregate_reason = "missing"
    if aggregate is not None:
        aggregate_status = aggregate.spend_status
        aggregate_reason = aggregate.reason
        if aggregate.spend_status == "ok":
            aggregate_spend = aggregate.spend
    daily_spend = _sum_present(daily_rows, "spend") if daily_status == "ok" else None
    gap = None
    if aggregate_spend is not None and daily_spend is not None and round(float(aggregate_spend), 2) != round(float(daily_spend), 2):
        gap = {
            "account_insights_total": aggregate_spend,
            "daily_rows_sum": daily_spend,
            "difference": round(float(aggregate_spend) - float(daily_spend), 2),
            "note": (
                "Unmatched Meta spend. The inbound CAC account insights total and "
                "the sum of daily account rows differ. Neither figure is tied to a "
                "lead or an opp. This page does not pick one."
            ),
        }
    agreed = None
    agreed_source = None
    if gap is None:
        if aggregate_spend is not None:
            agreed = aggregate_spend
            agreed_source = "account_insights_total"
        elif daily_spend is not None:
            agreed = daily_spend
            agreed_source = "daily_rows_sum"
    return {
        "label": "Unmatched Meta spend",
        "unmatched": True,
        "note": gap["note"] if gap else UNMATCHED_SPEND_NOTE,
        "account_insights_total": aggregate_spend,
        "account_insights_status": aggregate_status,
        "account_insights_reason": None if aggregate_status == "ok" else aggregate_reason,
        "daily_rows_sum": daily_spend,
        "daily_rows_status": daily_status,
        "spend": agreed,
        "spend_source": agreed_source,
        "gap": gap,
    }


def _cost_block(
    *,
    label: str,
    count: int | None,
    count_label: str,
    target: int | None,
    empty_note: str,
    spend: dict[str, Any],
) -> dict[str, Any]:
    gap = spend.get("gap")
    total_cost = _unit_cost(spend.get("account_insights_total"), count)
    daily_cost = _unit_cost(spend.get("daily_rows_sum"), count)
    agreed = _unit_cost(spend.get("spend"), count) if not gap else None
    if count is None:
        status = "unavailable"
        note = f"{count_label} is missing, so this cost stays blank."
    elif int(count) == 0:
        status = "no_count"
        note = empty_note
    elif gap:
        status = "spend_gap"
        note = gap["note"]
    elif agreed is None:
        status = "spend_unavailable"
        note = "Meta spend is unavailable, so this cost stays blank."
    else:
        status = "ok"
        note = UNMATCHED_SPEND_NOTE
    return {
        "label": label,
        "count": count,
        "count_label": count_label,
        "target": target,
        "value": agreed,
        "status": status,
        "note": note,
        "by_spend": {
            "account_insights_total": total_cost,
            "daily_rows_sum": daily_cost,
        },
    }


def _source_phrase(label: str) -> str:
    return "blank" if label == "(blank)" else label


def _excluded_sentence(counts: dict[str, Any]) -> str:
    excluded = counts.get("excluded_by_source") or {}
    other = sum(int(value) for value in excluded.values())
    if other <= 0:
        return "Pipeline opportunities in this window are leads only when Lead Gen Source is Inbound."
    parts = [
        f"{_source_phrase(name)} {excluded[name]}"
        for name in sorted(excluded, key=lambda key: (-int(excluded[key]), key))
    ]
    sentence = (
        f"{other} pipeline opportunities in this window are not leads: "
        + ", ".join(parts)
        + "."
    )
    refunded = int(counts.get("refunded_leads") or 0)
    if refunded:
        sentence += f" Includes {refunded} leads in the refunded stage."
    return sentence


def _load_website_traffic():
    """Load the metrics module that already owns the paid-session rule and GA4 client."""
    name = "hs_paid_social_website_traffic"
    existing = sys.modules.get(name)
    if existing is not None and callable(getattr(existing, "session_is_paid", None)):
        return existing
    spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "website_traffic.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load website traffic metric")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _row_metric(row: dict[str, Any], value_keys: tuple[str, ...]) -> int | None:
    for key in value_keys:
        if key not in row:
            continue
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        return value
    return None


def count_paid_rows(
    rows: list[dict[str, Any]] | None,
    days: list[str],
    *,
    value_keys: tuple[str, ...],
    event_name: str | None = None,
) -> dict[str, Any]:
    """Sum rows the website-traffic paid-session rule accepts.

    A successful report omits days with no paid rows. Those days are 0.
    This function does not turn a failed read into a number. The caller
    keeps total and series null when the report itself failed.
    """
    traffic = _load_website_traffic()
    by_day = {day: 0 for day in days}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        event = traffic.compact_str(row.get("eventName") or row.get("event_name"))
        if event_name:
            if event != event_name:
                continue
        elif event in {FORM_START_EVENT, FINISHED_FORM_EVENT, "wix_form_submit"}:
            continue
        if not traffic.session_is_paid(
            row.get("sessionSource") or row.get("source"),
            row.get("sessionMedium") or row.get("medium"),
            row.get("sessionDefaultChannelGroup") or row.get("channel"),
        ):
            continue
        day = traffic.normalize_series_date(row.get("date"))
        if day not in by_day:
            continue
        value = _row_metric(row, value_keys)
        if value is None:
            continue
        by_day[day] += value
    return {
        "total": sum(by_day.values()),
        "series": [{"date": day, "value": by_day[day]} for day in days],
    }


def _visits_stage(status: str, total: int | None, series: list | None, note: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "key": "website_visitors",
        "label": "Website visitors from the ad",
        "order": 3,
        "status": status,
        "total": total,
        "series": series,
        "measurement_id": GA4_MEASUREMENT_ID,
        "property_id": GA4_PROPERTY_ID,
        "note": note,
        "reason": reason,
    }


def _forms_stage(status: str, total: int | None, series: list | None, note: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "key": "form_starts",
        "label": "Form starts",
        "status": status,
        "total": total,
        "series": series,
        "event": FORM_START_EVENT,
        "measurement_id": GA4_MEASUREMENT_ID,
        "property_id": GA4_PROPERTY_ID,
        "note": note,
        "reason": reason,
    }


def _blank_website(reason: str) -> dict[str, Any]:
    return {
        "landing_visits": _visits_stage("unavailable", None, None, VISITS_UNAVAILABLE_NOTE, reason),
        "form_starts": _forms_stage("unavailable", None, None, FORMS_UNAVAILABLE_NOTE, reason),
    }


def _unwired_forms() -> dict[str, Any]:
    return _forms_stage("not_wired", None, None, FORMS_UNWIRED_NOTE, "not_wired")


def _sanitize_stage(stage: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """A status other than ok cannot carry a plotted zero."""
    ok_note = VISITS_OK_NOTE if kind == "visits" else FORMS_OK_NOTE
    blank_note = VISITS_UNAVAILABLE_NOTE if kind == "visits" else FORMS_UNAVAILABLE_NOTE
    builder = _visits_stage if kind == "visits" else _forms_stage
    status = stage.get("status")
    total = stage.get("total")
    ready = status == "ok" and total is not None and not isinstance(total, bool)
    number: int | None = None
    if ready:
        try:
            number = int(total)
        except (TypeError, ValueError):
            ready = False
    if not ready:
        kept = "not_wired" if status == "not_wired" else "unavailable"
        note = stage.get("note") or (FORMS_UNWIRED_NOTE if kept == "not_wired" and kind == "forms" else blank_note)
        return builder(kept, None, None, note, stage.get("reason"))
    series = stage.get("series")
    if not isinstance(series, list):
        series = None
    return builder("ok", number, series, stage.get("note") or ok_note, None)


def _parsed_ga4_rows(raw: Any, traffic: Any, dimensions: tuple[str, ...], metrics: tuple[str, ...]) -> list[dict[str, Any]] | None:
    if not isinstance(raw, dict) or raw.get("ga4") != "ok":
        return None
    report = raw.get("report")
    if not isinstance(report, dict):
        return None
    returned = report.get("rows") or []
    if not isinstance(returned, list):
        return None
    row_count = report.get("rowCount")
    if row_count not in (None, ""):
        try:
            if int(row_count) > len(returned):
                return None
        except (TypeError, ValueError):
            return None
    parsed = traffic.parse_ga4_generic_rows(report, dimensions, metrics)
    return parsed if isinstance(parsed, list) else None


def _sessions_body(traffic: Any, start: str, end: str) -> dict[str, Any]:
    return {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": name} for name in PAID_GA4_DIMENSIONS],
        "metrics": [{"name": "sessions"}],
        "limit": "10000",
        "dimensionFilter": traffic.live_host_filter(),
    }


def _form_starts_body(traffic: Any, start: str, end: str) -> dict[str, Any]:
    return {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": name} for name in (*PAID_GA4_DIMENSIONS, "eventName")],
        "metrics": [{"name": "eventCount"}],
        "limit": "10000",
        "dimensionFilter": {
            "andGroup": {
                "expressions": [
                    traffic.live_host_filter(),
                    {
                        "filter": {
                            "fieldName": "eventName",
                            "inListFilter": {"values": [FORM_START_EVENT]},
                        }
                    },
                ]
            }
        },
    }


def _read_stage(runner: Any, traffic: Any, body: dict[str, Any], days: list[str], *, kind: str) -> dict[str, Any]:
    dimensions = tuple(item["name"] for item in body["dimensions"])
    metrics = tuple(item["name"] for item in body["metrics"])
    value_keys = metrics
    event_name = FORM_START_EVENT if kind == "forms" else None
    ok_note = VISITS_OK_NOTE if kind == "visits" else FORMS_OK_NOTE
    bad_note = VISITS_UNAVAILABLE_NOTE if kind == "visits" else FORMS_UNAVAILABLE_NOTE
    builder = _visits_stage if kind == "visits" else _forms_stage
    try:
        raw = runner(body)
        parsed = _parsed_ga4_rows(raw, traffic, dimensions, metrics)
    except Exception:
        return builder("unavailable", None, None, bad_note, "ga4_failed")
    if parsed is None:
        return builder("unavailable", None, None, bad_note, "ga4_failed")
    counted = count_paid_rows(parsed, days, value_keys=value_keys, event_name=event_name)
    return builder("ok", counted["total"], counted["series"], ok_note, None)


def fetch_paid_website_stages(
    start_local: datetime,
    end_local: datetime,
    *,
    report_runner: Any = None,
) -> dict[str, Any]:
    """Read GA4 paid sessions and paid calculator starts. Failures stay null.

    Uses the existing Data API client, property 408492342, and measurement
    G-V02RZFR4SZ. Does not change ads, spend, campaigns, or the calculator form.
    """
    days = window_dates(start_local, end_local)
    start = start_local.date().isoformat()
    end = (end_local.date() - timedelta(days=1)).isoformat()
    if end < start:
        end = start
    try:
        traffic = _load_website_traffic()
        funnel = traffic.funnel_mod()
    except Exception:
        return _blank_website("ga4_client_unavailable")
    if funnel.GA4_PROPERTY_ID != GA4_PROPERTY_ID or funnel.GA4_MEASUREMENT_ID != GA4_MEASUREMENT_ID:
        return _blank_website("property_mismatch")
    if FORM_START_EVENT not in funnel.GA4_EVENT_NAMES or FINISHED_FORM_EVENT not in funnel.GA4_EVENT_NAMES:
        return _blank_website("form_start_event_missing")
    property_id = traffic.compact_str(os.environ.get(funnel.GA4_PROPERTY_ID_ENV)) or funnel.GA4_PROPERTY_ID
    if property_id != GA4_PROPERTY_ID:
        return _blank_website("property_mismatch")
    if report_runner is None:
        if not funnel.ga4_credentials_available():
            return _blank_website("not_configured")
        report_runner = traffic.run_ga4_report
    return {
        "landing_visits": _read_stage(
            report_runner, traffic, _sessions_body(traffic, start, end), days, kind="visits"
        ),
        "form_starts": _read_stage(
            report_runner, traffic, _form_starts_body(traffic, start, end), days, kind="forms"
        ),
    }


def assemble_paid_social(
    counts: dict[str, Any],
    *,
    start_local: datetime,
    end_local: datetime,
    daily_meta: dict[str, Any],
    aggregate_spend: cac.MetaSpendResult | None,
    timezone_name: str = TIMEZONE_NAME,
    website: dict[str, Any] | None = None,
) -> dict[str, Any]:
    days = list(counts.get("days") or window_dates(start_local, end_local))
    meta_ok = daily_meta.get("status") == "ok"
    rows = list(daily_meta.get("rows") or []) if meta_ok else []
    spend = _spend_block(aggregate_spend, rows, "ok" if meta_ok else "unavailable")
    spend["series"] = _point_series(days, rows, "spend") if meta_ok else None
    ad_views_total = _sum_present(rows, "impressions") if meta_ok else None
    clicks_total = _sum_present(rows, "clicks") if meta_ok else None
    outbound_total = _sum_present(rows, "outbound_clicks") if meta_ok else None
    impressions = _point_series(days, rows, "impressions") if ad_views_total is not None else None
    clicks = _point_series(days, rows, "clicks") if clicks_total is not None else None
    ad_views_note = (
        "Meta account impressions. Days Meta did not return stay blank on the chart. They are not drawn as zero."
        if ad_views_total is not None
        else "Ad views are missing for this window, so this chart stays blank. A missing series is not zero."
    )
    clicks_note = (
        "Meta account clicks. Lead actions are not this series. Days Meta did not return stay blank on the chart."
        if clicks_total is not None
        else "Clicks are missing for this window, so this chart stays blank. A missing series is not zero."
    )
    leads = int(counts["leads"])
    opps = int(counts["opps"])
    demos = int(counts["demos"])
    sales = int(counts["sales"])
    territory = counts.get("opps_by_territory") or {}
    territory_bits = [f"{name} {int(territory.get(name) or 0)}" for name in ("Buffalo", "Rochester", "Syracuse", "Virtual")]
    if isinstance(website, dict):
        supplied_visits = website.get("landing_visits")
        supplied_forms = website.get("form_starts")
        visitors = _sanitize_stage(supplied_visits, kind="visits") if isinstance(supplied_visits, dict) else _visits_stage(
            "unavailable", None, None, VISITS_UNAVAILABLE_NOTE, "missing"
        )
        forms = _sanitize_stage(supplied_forms, kind="forms") if isinstance(supplied_forms, dict) else _forms_stage(
            "unavailable", None, None, FORMS_UNAVAILABLE_NOTE, "missing"
        )
    else:
        visitors = _visits_stage("not_wired", None, None, VISITORS_NOTE, "not_wired")
        forms = _unwired_forms()
    return {
        "metric": "Paid social funnel",
        "timezone": timezone_name,
        "window_start_local": start_local.isoformat(),
        "window_end_local": end_local.isoformat(),
        "lead_definition": {
            "pipeline_id": LEAD_PIPELINE_ID,
            "pipeline_name": LEAD_PIPELINE_NAME,
            "source_field_id": SOURCE_FIELD_ID,
            "source_field_name": SOURCE_FIELD_NAME,
            "source_value": SOURCE_VALUE,
            "match": "strip_case_insensitive",
            "does_not_match": ["3PL", "(blank)"],
            "not_the_lead_number": [
                "title bucket Lead Locker",
                "title bucket Solar Reviews",
                "inbound_cac Inbound form-fill row",
            ],
        },
        "funnel": [
            {
                "key": "ad_views",
                "label": "Ad views",
                "order": 1,
                "status": "ok" if ad_views_total is not None else "unavailable",
                "total": ad_views_total,
                "series": impressions,
                "note": ad_views_note,
            },
            {
                "key": "clicks",
                "label": "Clicks",
                "order": 2,
                "status": "ok" if clicks_total is not None else "unavailable",
                "total": clicks_total,
                "series": clicks,
                "note": clicks_note,
            },
            visitors,
            {
                "key": "leads_created",
                "label": "Leads created",
                "order": 4,
                "status": "ok",
                "total": leads,
                "series": counts["lead_series"],
                "refunded_leads": counts["refunded_leads"],
                "pipeline_opportunities_in_window": counts["pipeline_opportunities_in_window"],
                "excluded_by_source": counts["excluded_by_source"],
                "matched_source_values": counts["matched_source_values"],
                "note": LEAD_NOTE + " " + _excluded_sentence(counts),
            },
            {
                "key": "opps_created",
                "label": "Opps created",
                "order": 5,
                "status": "ok",
                "total": opps,
                "series": counts["opp_series"],
                "by_territory": territory,
                "note": OPP_NOTE + " " + ", ".join(territory_bits) + ".",
            },
        ],
        "landing_visits": visitors,
        "form_starts": forms,
        "outbound_clicks": {
            "label": "Outbound clicks",
            "status": "ok" if outbound_total is not None else "unavailable",
            "total": outbound_total,
            "series": _point_series(days, rows, "outbound_clicks") if outbound_total is not None else None,
            "note": (
                "Meta outbound clicks. All-clicks are not this series. "
                "Lead actions are not this series. Landing-page views are not website visits."
            ),
        },
        "demos": {
            "label": "Demos",
            "total": demos,
            "status": "ok",
            "series": counts.get("demo_series"),
            "note": "no demo" if demos == 0 else DEMO_NOTE,
        },
        "sales": {
            "label": "Sold deals",
            "total": sales,
            "status": "ok",
            "series": counts.get("sale_series"),
            "sold_date_field_id": SOLD_DATE_FIELD_ID,
            "note": SALES_NOTE,
        },
        "spend": spend,
        "kpis": {
            "cost_per_lead": _cost_block(
                label="Cost per lead",
                count=leads,
                count_label="Leads",
                target=CPL_TARGET,
                empty_note="No lead in this window, so cost per lead stays blank.",
                spend=spend,
            ),
            "cost_per_opp": _cost_block(
                label="Cost per opp",
                count=opps,
                count_label="Opps",
                target=None,
                empty_note="No opp in this window, so cost per opp stays blank.",
                spend=spend,
            ),
            "cost_per_demo": _cost_block(
                label="Cost per demo",
                count=demos,
                count_label="Demos",
                target=DEMO_COST_TARGET,
                empty_note="No demo in this window, so cost per demo stays blank.",
                spend=spend,
            ),
            "cost_per_acquisition": _cost_block(
                label="Cost per acquisition",
                count=sales,
                count_label="Sold deals",
                target=CPA_TARGET,
                empty_note="No sold deal in this window, so cost per acquisition stays blank.",
                spend=spend,
            ),
        },
        "meta_lead_actions": {
            "status": "absent_not_zero",
            "series": None,
            "plotted": False,
            "ignored_if_present": bool(daily_meta.get("lead_actions_ignored")),
            "note": LEAD_ACTIONS_NOTE,
        },
        "meta_account_id": META_ACCOUNT_ID,
        "meta_writes": False,
        "campaign_not_modified": META_CAMPAIGN_NOT_MODIFIED,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def load_window_records(db: Any, start_local: datetime, end_local: datetime, now_utc: datetime):
    pipeline_opps = cac.load_inbound_opps(db)
    territory_created = cac.load_territory_created(db, start_local, end_local)
    territory_demos = cac.load_territory_sits(db, start_local, end_local, now_utc)
    sold_contact_ids = cac.load_sold_stage_contact_ids(db, None)
    contact_ids: set[str] = set(sold_contact_ids)
    for opp in pipeline_opps:
        contact_id = cac.compact_str(opp.get("contactId"))
        if contact_id:
            contact_ids.add(contact_id)
    for opp in list(territory_created) + list(territory_demos):
        if opp.contact_id:
            contact_ids.add(opp.contact_id)
    contacts = cac.load_contacts_by_ids(db, contact_ids)
    return pipeline_opps, territory_created, territory_demos, sold_contact_ids, contacts


def compute_paid_social_funnel(
    db: Any,
    *,
    start: str,
    end: str,
    now: datetime | None = None,
    tz: str = TIMEZONE_NAME,
    token: str | None = None,
    account_id: str | None = None,
    urlopen: Any = None,
    aggregate_fetcher: Any = None,
    daily_fetcher: Any = None,
    ga4_fetcher: Any = None,
) -> dict[str, Any]:
    start_local, end_local, _, _ = cac.date_range_window(start, end, tz)
    if (end_local.date() - start_local.date()).days > MAX_RANGE_DAYS:
        raise ValueError(f"Date range is longer than {MAX_RANGE_DAYS} days")
    now = now or datetime.now(ZoneInfo(tz))
    now_utc = now.astimezone(timezone.utc)
    pipeline_opps, territory_created, territory_demos, sold_contact_ids, contacts = load_window_records(
        db, start_local, end_local, now_utc
    )
    counts = count_paid_social(
        pipeline_opps,
        territory_created,
        territory_demos,
        sold_contact_ids,
        contacts,
        start_local,
        end_local,
        now_utc,
    )
    if token is None or account_id is None:
        env_token, env_account, _reason = cac.read_meta_ads_credentials()
        token = env_token if token is None else token
        account_id = env_account if account_id is None else account_id
    if daily_fetcher:
        daily_meta = daily_fetcher(start_local, end_local)
    else:
        daily_meta = fetch_meta_daily(
            start_local, end_local, token=token, account_id=account_id, urlopen=urlopen
        )
    if aggregate_fetcher:
        aggregate = aggregate_fetcher(start_local, end_local)
    elif token and account_id == META_ACCOUNT_ID:
        aggregate = cac.fetch_meta_ads_spend(
            start_local, end_local, token=token, account_id=account_id, urlopen=urlopen
        )
    elif account_id and account_id != META_ACCOUNT_ID:
        aggregate = cac.unavailable_meta_spend("account_mismatch")
    else:
        aggregate = cac.unavailable_meta_spend("missing_env")
    if ga4_fetcher:
        try:
            website = ga4_fetcher(start_local, end_local)
        except Exception:
            website = _blank_website("ga4_fetcher_failed")
        if not isinstance(website, dict):
            website = _blank_website("ga4_fetcher_failed")
    else:
        website = fetch_paid_website_stages(start_local, end_local)
    return assemble_paid_social(
        counts,
        start_local=start_local,
        end_local=end_local,
        daily_meta=daily_meta,
        aggregate_spend=aggregate,
        timezone_name=tz,
        website=website,
    )


def parse_range(qs: dict[str, list[str]], now: datetime) -> tuple[str, str]:
    """Inclusive dates on the America/New_York calendar.

    Named presets use that calendar. A custom start and end are used when
    no named preset is set. Otherwise the window is the current month
    through today.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(TIMEZONE_NAME))
    today = now.astimezone(ZoneInfo(TIMEZONE_NAME)).date()
    preset = " ".join(str((qs.get("preset") or [""])[0] or "").split()).lower()
    if preset == "this-month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if preset == "last-month":
        last_prev = today.replace(day=1) - timedelta(days=1)
        return last_prev.replace(day=1).isoformat(), last_prev.isoformat()
    if preset == "last-30":
        return (today - timedelta(days=29)).isoformat(), today.isoformat()
    start, end = cac.parse_optional_range(qs)
    if start and end:
        return start, end
    return today.replace(day=1).isoformat(), today.isoformat()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo(TIMEZONE_NAME))
            start, end = parse_range(qs, now)
            payload = compute_paid_social_funnel(cac.get_db(), start=start, end=end, now=now)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
