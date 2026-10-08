# -*- coding: utf-8 -*-
"""Human dates for Goose. Answer templates and the panel footer both use this module.

The panel does not format clocks itself. Chat builds footnote.updated_label
with format_updated, and the panel prints that string.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

MONTHS = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(EASTERN)
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
        except ValueError:
            return None
    return None


def parse_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_day(value, *, year: bool = True) -> str:
    """Oct 7, 2026. Pass year=False for Oct 7."""
    day = _as_date(value)
    if day is None:
        return ""
    label = f"{MONTHS[day.month]} {day.day}"
    if year:
        return f"{label}, {day.year}"
    return label


def format_range(start, end) -> str:
    """Oct 1–7, 2026 when the month matches. A wider span spells both months."""
    first = _as_date(start)
    last = _as_date(end)
    if first is None and last is None:
        return ""
    if first is None:
        return format_day(last)
    if last is None or first == last:
        return format_day(first)
    if first.year == last.year and first.month == last.month:
        return f"{MONTHS[first.month]} {first.day}–{last.day}, {first.year}"
    if first.year == last.year:
        return f"{MONTHS[first.month]} {first.day} – {MONTHS[last.month]} {last.day}, {first.year}"
    return f"{format_day(first)} – {format_day(last)}"


def format_chip(start, end) -> str:
    """Oct 1 – Oct 7. Same rules as the old panel chip, without a year."""
    first = _as_date(start)
    last = _as_date(end)
    if first is None and last is None:
        return ""
    if first is None:
        return format_day(last, year=False)
    if last is None or first == last:
        return format_day(first, year=False)
    return f"{MONTHS[first.month]} {first.day} – {MONTHS[last.month]} {last.day}"


def format_updated(value) -> str:
    """Updated Oct 7 at 10:29 PM ET. UTC instants are converted to Eastern."""
    moment = parse_datetime(value)
    if moment is None:
        return ""
    local = moment.astimezone(EASTERN)
    hour = local.hour
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    clock = f"{hour12}:{local.minute:02d} {suffix}"
    return f"Updated {MONTHS[local.month]} {local.day} at {clock} ET"


def is_stale(value, now: datetime | None, *, hours: int = 24) -> bool:
    moment = parse_datetime(value)
    if moment is None or now is None:
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - moment) > timedelta(hours=hours)
