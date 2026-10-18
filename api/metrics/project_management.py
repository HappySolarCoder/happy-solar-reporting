# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/project_management

JSON for the Project Management hub and Hold / Cancelled dashboards.
Rows come from the Monday Process Board NY snapshot the hub already
publishes. This module does not write to Monday or GoHighLevel.

GoHighLevel links reuse the opportunity detail URL already used by
Diamond — Opportunity List and Missing Dispositions:

https://app.gohighlevel.com/v2/location/{locationId}/opportunities/list/{oppId}?tab=OpportunityDetails

A row with an opportunity id uses that URL. A row with only a contact
id uses the contact page. Anything else stays plain text.
"""

from __future__ import annotations

import calendar
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

SNAPSHOT_URL = os.environ.get(
    "PM_HUB_DATA_URL",
    "https://happy-solar-monday-pm.vercel.app/hub-data.js",
)
GHL_APP_ORIGIN = "https://app.gohighlevel.com"
DEFAULT_GHL_LOCATION_ID = "MMKRDviKggXzlcHQTnvZ"
GHL_OPPORTUNITY_URL = (
    "https://app.gohighlevel.com/v2/location/{location_id}/opportunities/list/{opp_id}?tab=OpportunityDetails"
)
GHL_CONTACT_URL = "https://app.gohighlevel.com/v2/location/{location_id}/contacts/detail/{contact_id}"
ACTIVE_SECTIONS = ("onboarding", "ep_ops", "ep_installation")
HOLD_SECTION = "hold_cancel"
CANCELLATION_START_MONTH = "2026-01"
SNAPSHOT_TTL_SECONDS = 300

LOCATION_KEYS = ("ghlLocationId", "ghl_location_id", "locationId", "location_id")
OPPORTUNITY_KEYS = (
    "ghlOpportunityId",
    "ghl_opportunity_id",
    "opportunityId",
    "opportunity_id",
    "oppId",
    "opp_id",
)
CONTACT_KEYS = ("ghlContactId", "ghl_contact_id", "contactId", "contact_id")

LANES: tuple[tuple[str, str, str], ...] = (
    ("onboarding", "Onboarding", "Project Verification → Site Evaluation → Site Review."),
    ("ep_ops", "EP Ops", "ENG/FIN/PERM, ESOW / Final Approval, Install Ready."),
    (
        "ep_installation",
        "EP Installation",
        "Being Installed → Build / Elec Inspection → Post Install → PTO → Finalized.",
    ),
    (
        "hold_cancel",
        "Hold / Cancel",
        "Validation Hold, HOLD / HOLD 2026, and Cancelled (HO Cancelled / Cancelled at door / Cancel interconnect).",
    ),
)

_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def is_ghl_id(value: Any) -> bool:
    text = compact_text(value)
    return bool(text) and all(ch.isalnum() or ch in "-_" for ch in text)


def ghl_location_id(value: Any = None) -> str:
    return compact_text(value) or compact_text(os.environ.get("GHL_LOCATION_ID")) or DEFAULT_GHL_LOCATION_ID


def ghl_opportunity_url(location_id: Any, opportunity_id: Any) -> str:
    loc = compact_text(location_id)
    opp = compact_text(opportunity_id)
    if not is_ghl_id(loc) or not is_ghl_id(opp):
        return ""
    return GHL_OPPORTUNITY_URL.format(location_id=loc, opp_id=opp)


def ghl_contact_url(location_id: Any, contact_id: Any) -> str:
    loc = compact_text(location_id)
    contact = compact_text(contact_id)
    if not is_ghl_id(loc) or not is_ghl_id(contact):
        return ""
    return GHL_CONTACT_URL.format(location_id=loc, contact_id=contact)


def _nested_ghl(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("ghl", "gohighlevel", "goHighLevel"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return {}


def pick_field(row: dict[str, Any], keys: Iterable[str]) -> str:
    sources = (row, _nested_ghl(row))
    for source in sources:
        for key in keys:
            if key not in source:
                continue
            text = compact_text(source.get(key))
            if text:
                return text
    return ""


def phone_link(row: dict[str, Any]) -> str:
    """Opportunity detail when an opp id is present, else the contact page."""
    opportunity = compact_text(row.get("ghlOpportunityUrl"))
    if opportunity:
        return opportunity
    return compact_text(row.get("ghlContactUrl"))


def attach_ghl_links(row: dict[str, Any], *, default_location: Any = None) -> dict[str, Any]:
    item = dict(row)
    location = pick_field(item, LOCATION_KEYS)
    opportunity_id = pick_field(item, OPPORTUNITY_KEYS)
    contact_id = pick_field(item, CONTACT_KEYS)
    if not is_ghl_id(opportunity_id):
        opportunity_id = ""
    if not is_ghl_id(contact_id):
        contact_id = ""
    if not is_ghl_id(location) and (opportunity_id or contact_id):
        location = ghl_location_id(default_location)
    elif not is_ghl_id(location):
        location = ""
    opportunity_url = ghl_opportunity_url(location, opportunity_id) if opportunity_id else ""
    contact_url = ghl_contact_url(location, contact_id) if contact_id and not opportunity_url else ""
    if not opportunity_url and contact_id:
        contact_url = ghl_contact_url(location, contact_id)
    item["ghlLocationId"] = location if (opportunity_url or contact_url) else ""
    item["ghlOpportunityId"] = opportunity_id if opportunity_url else ""
    item["ghlContactId"] = contact_id if contact_url or opportunity_url else ""
    item["ghlOpportunityUrl"] = opportunity_url
    item["ghlContactUrl"] = contact_url
    item["phoneHref"] = opportunity_url or contact_url
    return item


def parse_hub_snapshot(text: str) -> dict[str, Any]:
    """Read `const rows`, `const stageCards`, and `const generatedAt` from hub-data.js."""
    raw = text or ""
    start = raw.find("[")
    if start < 0:
        raise ValueError("Project management snapshot could not be read")
    decoder = json.JSONDecoder()
    try:
        rows, end = decoder.raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("Project management snapshot could not be read") from exc
    if not isinstance(rows, list):
        raise ValueError("Project management snapshot could not be read")
    rest = raw[start + end :]
    cards: list[Any] = []
    marker = rest.find("const stageCards")
    if marker >= 0:
        card_start = rest.find("[", marker)
        if card_start >= 0:
            try:
                parsed_cards, _card_end = decoder.raw_decode(rest[card_start:])
            except json.JSONDecodeError as exc:
                raise ValueError("Project management snapshot could not be read") from exc
            if isinstance(parsed_cards, list):
                cards = parsed_cards
    generated = ""
    match = re.search(r'const generatedAt\s*=\s*"([^"]*)"', raw)
    if match:
        generated = match.group(1)
    clean_rows = [row for row in rows if isinstance(row, dict)]
    clean_cards = [card for card in cards if isinstance(card, dict) and compact_text(card.get("stage"))]
    return {"rows": clean_rows, "stage_cards": clean_cards, "generated_at": generated}


def created_date(row: dict[str, Any]) -> str:
    iso = compact_text(row.get("created_at_iso"))
    if len(iso) >= 10 and iso[4] == "-" and iso[7] == "-":
        return iso[:10]
    return ""


def row_created_month(row: dict[str, Any]) -> str:
    day = created_date(row)
    return day[:7] if len(day) >= 7 else ""


def in_date_range(row: dict[str, Any], start: str = "", end: str = "") -> bool:
    if not start and not end:
        return True
    day = created_date(row)
    if not day:
        return False
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def month_bounds(month_key: str) -> tuple[str, str] | None:
    text = compact_text(month_key)
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        return None
    year = int(text[:4])
    month = int(text[5:7])
    if month < 1 or month > 12:
        return None
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def _js_round1(value: float) -> float:
    return math.floor(value * 10 + 0.5) / 10


def install_cycle_days(row: dict[str, Any]) -> float | None:
    raw = compact_text(row.get("install_cycle_days"))
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def summarize_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    listed = list(rows)
    active = [row for row in listed if compact_text(row.get("section")) in ACTIVE_SECTIONS]
    held = [row for row in listed if compact_text(row.get("section")) == HOLD_SECTION]
    overdue = [row for row in listed if bool(row.get("is_over_sla"))]
    cycles = [value for value in (install_cycle_days(row) for row in listed) if value is not None]
    median = None
    if cycles:
        ordered = sorted(cycles)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            median = ordered[middle]
        else:
            median = _js_round1((ordered[middle - 1] + ordered[middle]) / 2)
    return {
        "active_jobs": len(active),
        "held_jobs": len(held),
        "overdue_jobs": len(overdue),
        "median_install_days": median,
        "install_sample_size": len(cycles),
        "row_count": len(listed),
    }


def has_sla(row: dict[str, Any]) -> bool:
    value = row.get("sla_days")
    return value not in ("", None)


def cards_for_rows(stage_cards: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    listed = list(rows)
    counts: dict[str, int] = {}
    overdue: dict[str, int] = {}
    for row in listed:
        bucket = compact_text(row.get("pm_bucket"))
        counts[bucket] = counts.get(bucket, 0) + 1
        if row.get("is_over_sla"):
            overdue[bucket] = overdue.get(bucket, 0) + 1
    cards = [dict(card) for card in stage_cards]
    if not cards:
        seen: set[str] = set()
        for row in listed:
            stage = compact_text(row.get("pm_bucket"))
            if not stage or stage in seen:
                continue
            seen.add(stage)
            cards.append(
                {
                    "stage": stage,
                    "full_name": stage,
                    "display_label": stage,
                    "short_label": stage,
                    "stage_slug": re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", stage.lower())),
                    "section": compact_text(row.get("section")),
                    "lane": "secondary" if compact_text(row.get("section")) == HOLD_SECTION else "primary",
                    "sla_days": None,
                    "sla_mode": "bucket",
                    "sla_label": "",
                }
            )
    display: list[dict[str, Any]] = []
    for card in cards:
        stage = compact_text(card.get("stage"))
        item = dict(card)
        item["count"] = counts.get(stage, 0)
        item["overdue_count"] = overdue.get(stage, 0)
        display.append(item)
    return display


def lanes_for_rows(stage_cards: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cards = cards_for_rows(stage_cards, rows)
    lanes: list[dict[str, Any]] = []
    for section, label, copy in LANES:
        lanes.append(
            {
                "section": section,
                "label": label,
                "copy": copy,
                "cards": [card for card in cards if compact_text(card.get("section")) == section],
            }
        )
    return lanes


def _rep_set(reps: Iterable[str] | None) -> set[str]:
    return {compact_text(rep).lower() for rep in (reps or []) if compact_text(rep)}


def rep_matches(row: dict[str, Any], reps: set[str]) -> bool:
    if not reps:
        return True
    return compact_text(row.get("assigned_rep")).lower() in reps


def filter_hub_rows(
    rows: Iterable[dict[str, Any]],
    *,
    search: str = "",
    stage: str = "",
    reps: Iterable[str] | None = None,
    start: str = "",
    end: str = "",
    overdue_only: bool = False,
    ignore_stage: bool = False,
) -> list[dict[str, Any]]:
    needle = compact_text(search).lower()
    stage_key = "" if ignore_stage else compact_text(stage).lower()
    selected = _rep_set(reps)
    matched: list[dict[str, Any]] = []
    for row in rows:
        if overdue_only and not row.get("is_over_sla"):
            continue
        if stage_key and compact_text(row.get("pm_bucket")).lower() != stage_key:
            continue
        if not rep_matches(row, selected):
            continue
        if not in_date_range(row, start, end):
            continue
        if needle:
            haystack = " ".join(
                compact_text(row.get(key))
                for key in (
                    "pm_bucket",
                    "process_bucket",
                    "display_name",
                    "assigned_rep",
                    "address",
                    "zip_code",
                    "permit_ahj",
                    "permit_phone",
                    "permit_tat",
                    "site_survey_date",
                    "first_installed_on",
                    "task_status",
                    "calc_status",
                    "finance_status",
                    "permit_status",
                    "interconnection_status",
                    "monitoring_approval",
                    "monitoring_status",
                    "process_board_note",
                    "essential_view_note",
                )
            ).lower()
            if needle not in haystack:
                continue
        matched.append(row)
    return matched


def sort_hub_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[str, float, str]:
        days = row.get("days_in_bucket")
        try:
            day_value = float(days or 0)
        except (TypeError, ValueError):
            day_value = 0
        return (
            compact_text(row.get("pm_bucket")).casefold(),
            -day_value,
            compact_text(row.get("display_name")).casefold(),
        )

    return sorted(rows, key=key)


def format_month_label(month_key: str) -> str:
    text = compact_text(month_key)
    parts = text.split("-")
    if len(parts) != 2:
        return text or "—"
    year, month = parts
    if not (year.isdigit() and month.isdigit()):
        return text
    month_number = int(month)
    year_number = int(year)
    if month_number < 1 or month_number > 12:
        return text
    return f"{month_number:02d}/{str(year_number)[-2:]}"


def cancellation_series(
    rows: Iterable[dict[str, Any]],
    *,
    reps: Iterable[str] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    selected = _rep_set(reps)
    monthly: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not rep_matches(row, selected):
            continue
        month_key = row_created_month(row)
        if not month_key or month_key < CANCELLATION_START_MONTH:
            continue
        item = monthly.setdefault(month_key, {"monthKey": month_key, "created": 0, "cancelled": 0})
        item["created"] += 1
        if compact_text(row.get("pm_bucket")).lower() == "cancelled":
            item["cancelled"] += 1
    current = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    if current < CANCELLATION_START_MONTH:
        current = CANCELLATION_START_MONTH
    series: list[dict[str, Any]] = []
    year, month = 2026, 1
    end_year, end_month = int(current[:4]), int(current[5:7])
    while (year, month) <= (end_year, end_month):
        month_key = f"{year:04d}-{month:02d}"
        item = monthly.get(month_key) or {"monthKey": month_key, "created": 0, "cancelled": 0}
        created = int(item["created"])
        cancelled = int(item["cancelled"])
        rate = (cancelled / created) * 100 if created else 0
        series.append(
            {
                "monthKey": month_key,
                "created": created,
                "cancelled": cancelled,
                "rate": rate,
                "label": format_month_label(month_key),
            }
        )
        month += 1
        if month == 13:
            month = 1
            year += 1
    return series


def cancellation_stages(rows: Iterable[dict[str, Any]], *, reps: Iterable[str] | None = None) -> list[dict[str, Any]]:
    selected = _rep_set(reps)
    counts: dict[str, int] = {}
    for row in rows:
        if not rep_matches(row, selected):
            continue
        if compact_text(row.get("pm_bucket")).lower() != "cancelled":
            continue
        stage = compact_text(row.get("cancel_source_stage")) or "Unknown prior stage"
        counts[stage] = counts.get(stage, 0) + 1
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    leading = [{"stage": stage, "count": count, "share": (count / total) * 100} for stage, count in ranked[:10]]
    other = sum(count for _stage, count in ranked[10:])
    if other:
        leading.append({"stage": "Other historical stages", "count": other, "share": (other / total) * 100})
    return leading


def hold_cancel_view(
    rows: Iterable[dict[str, Any]],
    *,
    created_month: str = "",
    start: str = "",
    end: str = "",
    bucket: str = "Cancelled",
    reps: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Same listing rules as happy-slr-hold-cancelled.html, plus the shared date range.

    A createdMonth query (the cancellation chart) lists jobs created that month
    whose bucket matches `bucket` (Cancelled by default). With no month and no
    date range, the table is the hold/cancel section. A start/end range filters
    that section by created date. Reps narrow every view. An explicit start/end
    wins over createdMonth.
    """
    listed_rows = list(rows)
    selected = _rep_set(reps)
    bucket_key = compact_text(bucket) or "Cancelled"
    month_key = compact_text(created_month)
    range_start = compact_text(start)
    range_end = compact_text(end)
    use_month = bool(month_key) and not range_start and not range_end
    if use_month:
        bounds = month_bounds(month_key)
        created_rows = [
            row
            for row in listed_rows
            if rep_matches(row, selected) and row_created_month(row) == month_key
        ]
        table_rows = [
            row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == bucket_key.lower()
        ]
        month_label = format_month_label(month_key)
        if bounds:
            range_start, range_end = bounds
        cancelled_count = len(table_rows) if bucket_key.lower() == "cancelled" else len(
            [row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == "cancelled"]
        )
        created_count = len(created_rows)
        active_month = month_key
        active_bucket = bucket_key
    else:
        created_rows = [
            row
            for row in listed_rows
            if rep_matches(row, selected) and in_date_range(row, range_start, range_end)
        ]
        table_rows = [row for row in created_rows if compact_text(row.get("section")) == HOLD_SECTION]
        cancelled_count = len(
            [row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == "cancelled"]
        )
        dated = bool(range_start or range_end)
        created_count = len(created_rows) if dated else len(table_rows)
        month_label = f"{range_start} – {range_end}" if dated else "All months"
        active_month = ""
        active_bucket = ""
    return {
        "listed": sort_hub_rows(table_rows),
        "cancelled_count": cancelled_count,
        "created_count": created_count,
        "month_label": month_label,
        "created_month": active_month,
        "start": range_start,
        "end": range_end,
        "bucket": active_bucket,
    }


def unique_reps(rows: Iterable[dict[str, Any]]) -> list[str]:
    names: dict[str, str] = {}
    for row in rows:
        name = compact_text(row.get("assigned_rep"))
        if not name:
            continue
        key = name.casefold()
        current = names.get(key)
        if current is None or (current == current.lower() and name != name.lower()):
            names[key] = name
    return [names[key] for key in sorted(names, key=str.casefold)]


def build_payload(snapshot: dict[str, Any], *, default_location: Any = None) -> dict[str, Any]:
    rows = [
        attach_ghl_links(row, default_location=default_location)
        for row in snapshot.get("rows") or []
        if isinstance(row, dict)
    ]
    cards = [card for card in snapshot.get("stage_cards") or [] if isinstance(card, dict)]
    summary = summarize_rows(rows)
    return {
        "ok": True,
        "metric": "Project Management",
        "source": "Monday Process Board - NY",
        "generated_at": snapshot.get("generated_at") or "",
        "row_count": len(rows),
        "summary": summary,
        "lanes": [
            {"section": section, "label": label, "copy": copy}
            for section, label, copy in LANES
        ],
        "stage_cards": cards_for_rows(cards, rows),
        "reps": unique_reps(rows),
        "ghl_opportunity_url": GHL_OPPORTUNITY_URL,
        "ghl_contact_url": GHL_CONTACT_URL,
        "rows": rows,
    }


def load_snapshot_text(fetch: Callable[[], str] | None = None) -> str:
    if fetch is not None:
        return fetch()
    request = urllib.request.Request(SNAPSHOT_URL, headers={"User-Agent": "happy-solar-reporting"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def load_project_management(
    *,
    fetch: Callable[[], str] | None = None,
    now: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if fetch is None and not force:
        cached = _CACHE.get("payload")
        stamp = float(_CACHE.get("at") or 0)
        current = time.time() if now is None else now
        if isinstance(cached, dict) and current - stamp < SNAPSHOT_TTL_SECONDS:
            return cached
    text = load_snapshot_text(fetch)
    payload = build_payload(parse_hub_snapshot(text))
    if fetch is None:
        _CACHE["payload"] = payload
        _CACHE["at"] = time.time() if now is None else now
    return payload


def clear_snapshot_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["payload"] = None


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = load_project_management()
            qs = parse_qs(urlparse(self.path).query)
            view = compact_text(qs.get("view", [""])[0]).lower()
            if view == "hold":
                reps = [part for part in compact_text(qs.get("reps", [""])[0]).split(",") if compact_text(part)]
                hold = hold_cancel_view(
                    payload.get("rows") or [],
                    created_month=compact_text(qs.get("createdMonth", [""])[0]),
                    start=compact_text(qs.get("start", [""])[0]),
                    end=compact_text(qs.get("end", [""])[0]),
                    bucket=compact_text(qs.get("bucket", ["Cancelled"])[0]) or "Cancelled",
                    reps=reps,
                )
                _write_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "metric": "Hold / Cancelled",
                        "source": payload.get("source"),
                        "generated_at": payload.get("generated_at"),
                        "ghl_opportunity_url": payload.get("ghl_opportunity_url"),
                        "ghl_contact_url": payload.get("ghl_contact_url"),
                        "reps": payload.get("reps") or [],
                        "month_label": hold["month_label"],
                        "cancelled_count": hold["cancelled_count"],
                        "created_count": hold["created_count"],
                        "created_month": hold["created_month"],
                        "start": hold["start"],
                        "end": hold["end"],
                        "bucket": hold["bucket"],
                        "row_count": len(hold["listed"]),
                        "rows": hold["listed"],
                    },
                )
                return
            _write_json(self, 200, payload)
        except Exception:
            _write_json(self, 502, {"ok": False, "error": "Project management data is unavailable"})
