# -*- coding: utf-8 -*-
"""Reporting windows. The company timezone is an explicit argument, never the server zone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_TODAY = re.compile(r"\btoday\b", re.I)
_THIS_WEEK = re.compile(r"\bthis week\b", re.I)
_MONTH_TO_DATE = re.compile(r"\b(?:this month|mtd|so far|current)\b", re.I)


class TimezoneUnconfirmed(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    start: str
    end: str
    timezone: str
    partial: bool
    basis: str
    label: str

    def as_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "timezone": self.timezone,
            "partial": self.partial,
            "basis": self.basis,
            "label": self.label,
        }


def _parse_ymd(value: str) -> date:
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def _shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def require_timezone(name: str | None) -> ZoneInfo:
    if not name:
        raise TimezoneUnconfirmed("company timezone is not confirmed")
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise TimezoneUnconfirmed(f"company timezone is not usable: {name}") from exc


def implied_current_range(message: str, timezone_name: str | None, now: datetime) -> tuple[str, str] | None:
    """Fill an empty panel range from the question. America/New_York via timezone_name.

    today is that calendar day. this week starts Monday and ends today.
    this month, MTD, so far, and current are month-to-date. A named day wins
    over a week, and a week wins over a month.
    """
    text = message or ""
    today = today_in(timezone_name, now)
    if _TODAY.search(text):
        iso = today.isoformat()
        return iso, iso
    if _THIS_WEEK.search(text):
        monday = today - timedelta(days=today.weekday())
        return monday.isoformat(), today.isoformat()
    if _MONTH_TO_DATE.search(text):
        return today.replace(day=1).isoformat(), today.isoformat()
    return None


def today_in(timezone_name: str | None, now: datetime) -> date:
    tz = require_timezone(timezone_name)
    if now.tzinfo is None:
        raise TimezoneUnconfirmed("current time must be timezone-aware")
    return now.astimezone(tz).date()


def period_from_dates(start: str, end: str, timezone_name: str | None, now: datetime) -> Period:
    tz_name = timezone_name or ""
    require_timezone(timezone_name)
    start_d = _parse_ymd(start)
    end_d = _parse_ymd(end)
    if end_d < start_d:
        raise ValueError("end is before start")
    today = today_in(timezone_name, now)
    month_last = _month_end(end_d)
    partial = end_d < month_last or (end_d >= today and start_d.day == 1 and today < month_last and end_d <= today)
    # A range that ends before the calendar month ends is partial.
    # A month-to-date range ending today is partial unless today is the last day.
    if start_d.day == 1 and start_d.month == end_d.month and start_d.year == end_d.year:
        partial = end_d < _month_end(start_d)
    else:
        partial = True
    basis = "inclusive_dates"
    label = f"{start} to {end}"
    return Period(start=start, end=end, timezone=tz_name, partial=partial, basis=basis, label=label)


def equivalent_prior_period(period: Period) -> Period:
    """Month-to-date compares with the same elapsed day count in the previous month.

    Full calendar months compare with the previous full calendar month.
    Other ranges compare with the immediately previous range of equal length.
    """
    start_d = _parse_ymd(period.start)
    end_d = _parse_ymd(period.end)
    month_last = _month_end(start_d)
    same_month = start_d.month == end_d.month and start_d.year == end_d.year
    if start_d.day == 1 and same_month and end_d == month_last:
        prev_start = _shift_months(start_d, -1)
        prev_end = _month_end(prev_start)
        basis = "previous_full_month"
        partial = False
    elif start_d.day == 1 and same_month:
        prev_month = _shift_months(start_d, -1)
        elapsed = (end_d - start_d).days
        prev_end = prev_month + timedelta(days=elapsed)
        prev_last = _month_end(prev_month)
        if prev_end > prev_last:
            prev_end = prev_last
        prev_start = prev_month
        basis = "month_to_date_equivalent_elapsed"
        partial = True
    else:
        length = (end_d - start_d).days + 1
        prev_end = start_d - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        basis = "previous_equal_length"
        partial = True
    return Period(
        start=prev_start.isoformat(),
        end=prev_end.isoformat(),
        timezone=period.timezone,
        partial=partial,
        basis=basis,
        label=f"{prev_start.isoformat()} to {prev_end.isoformat()}",
    )


def billing_month_key(timezone_name: str | None, now: datetime) -> str:
    day = today_in(timezone_name, now)
    return f"{day.year:04d}-{day.month:02d}"


def next_month_start(timezone_name: str | None, now: datetime) -> str:
    day = today_in(timezone_name, now)
    nxt = _shift_months(date(day.year, day.month, 1), 1)
    return nxt.isoformat()
