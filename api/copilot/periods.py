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
_LAST_MONTH = re.compile(r"\blast month\b", re.I)
_RELATIVE_BLOCK = re.compile(r"\b(?:this month|mtd|so far|this week)\b", re.I)
_STRAY_NOW = re.compile(r"\b(?:today|now)\b", re.I)
_MONTH_ALT = (
    r"january|february|march|april|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec|may"
)
_DAY_RANGE = re.compile(
    rf"\b(?:from\s+)?({_MONTH_ALT})\s+(\d{{1,2}})\s+(?:to|through|thru)\s+(?:({_MONTH_ALT})\s+)?(\d{{1,2}})\b",
    re.I,
)
_SINCE_MONTH = re.compile(rf"\bsince\s+({_MONTH_ALT})\b(?:\s+((?:19|20)\d{{2}}))?", re.I)
_FIRST_WEEK = re.compile(rf"\bfirst week of\s+({_MONTH_ALT})\b(?:\s+((?:19|20)\d{{2}}))?", re.I)
_LAST_N_DAYS = re.compile(r"\blast\s+(\d+)\s+days?\b", re.I)
_YESTERDAY = re.compile(r"\byesterday\b", re.I)
_LAST_WEEK = re.compile(r"\blast week\b", re.I)
_THIS_YEAR = re.compile(r"\b(?:ytd|year to date|this year)\b", re.I)
_LAST_YEAR = re.compile(r"\blast year\b", re.I)
_QUARTER = re.compile(r"\bq([1-4])\b(?:\s+((?:19|20)\d{2}))?", re.I)
_FULL_MONTH = re.compile(
    r"\b(january|february|march|april|june|july|august|september|october|november|december)\b",
    re.I,
)
# "may" and short abbreviations are ordinary words unless the sentence uses them as a month.
_SHORT_MONTH_TOKEN = r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec|may"
_SHORT_MONTH = re.compile(
    rf"\b(?:in|for|during)\s+({_SHORT_MONTH_TOKEN})\b"
    rf"|\b({_SHORT_MONTH_TOKEN})\s+(?:of\s+)?((?:19|20)\d{{2}}|\d{{1,2}})\b",
    re.I,
)
_MONTH_NUMBERS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


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


def _relative_period_wins(text: str) -> bool:
    """this month, MTD, so far, and this week beat a month name.

    A stray today or now does not. "in september? I need it today" stays September.
    today and now still count when the message does not name a month.
    """
    if _RELATIVE_BLOCK.search(text or ""):
        return True
    if _month_token(text or ""):
        return False
    return bool(_STRAY_NOW.search(text or ""))


def _all_month_tokens(text: str) -> list[tuple[int, int, int]]:
    """Month tokens as (start, end, month number), earliest first.

    Full names always count. "may" and 3-letter forms count only in a month
    phrase: "in may", "for may", "during may", "may 2026", or "may 1".
    """
    found: list[tuple[int, int, int]] = []
    for match in _FULL_MONTH.finditer(text):
        found.append((match.start(1), match.end(1), _MONTH_NUMBERS[match.group(1).lower()]))
    for match in _SHORT_MONTH.finditer(text):
        token = (match.group(1) or match.group(2) or "").lower()
        if not token:
            continue
        if match.group(1):
            found.append((match.start(1), match.end(1), _MONTH_NUMBERS[token]))
        else:
            found.append((match.start(2), match.end(2), _MONTH_NUMBERS[token]))
    found.sort()
    return found


def _month_token(text: str) -> tuple[int, int, int] | None:
    found = _all_month_tokens(text)
    return found[0] if found else None


def _distinct_months(text: str) -> list[tuple[int, int, int]]:
    seen: list[int] = []
    ordered: list[tuple[int, int, int]] = []
    for token in _all_month_tokens(text):
        if token[2] in seen:
            continue
        seen.append(token[2])
        ordered.append(token)
    return ordered


def _year_for(month: int, today: date, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    return today.year if month <= today.month else today.year - 1


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _window_ending(start: date, end: date, today: date, label: str) -> _NamedWindow:
    if start > today:
        return _NamedWindow("", "", False, label)
    if end > today:
        end = today
    if end < start:
        return _NamedWindow("", "", False, label)
    return _NamedWindow(start.isoformat(), end.isoformat(), True, label)


def _year_beside(text: str, start: int, end: int) -> int | None:
    after = re.match(r"\s+(?:of\s+)?((?:19|20)\d{2})\b", text[end : end + 24])
    if after:
        return int(after.group(1))
    before = re.search(r"\b((?:19|20)\d{2})\s+(?:of\s+)?$", text[max(0, start - 16) : start])
    if before:
        return int(before.group(1))
    return None


@dataclass(frozen=True)
class _NamedWindow:
    start: str
    end: str
    served: bool
    label: str


def _day_after(text: str, token_end: int) -> int | None:
    match = re.match(r"\s+(\d{1,2})\b", text[token_end : token_end + 8])
    if not match:
        return None
    return int(match.group(1))


def _on_day(text: str, token_start: int) -> bool:
    return bool(re.search(r"\bon\s+$", text[max(0, token_start - 4) : token_start], re.I))


def _special_window(text: str, today: date) -> _NamedWindow | None:
    """Exact windows that are cheaper to apply than to caveat. None if not one of these."""
    ranged = _DAY_RANGE.search(text)
    if ranged:
        month = _MONTH_NUMBERS[ranged.group(1).lower()]
        end_month_word = ranged.group(3)
        end_month = _MONTH_NUMBERS[end_month_word.lower()] if end_month_word else month
        year = _year_for(month, today, _year_beside(text, ranged.start(1), ranged.end(1)))
        end_year = year if end_month >= month else year + 1
        start = _safe_date(year, month, int(ranged.group(2)))
        end = _safe_date(end_year, end_month, int(ranged.group(4)))
        label = "that date range"
        if start is None or end is None:
            return _NamedWindow("", "", False, label)
        return _window_ending(start, end, today, label)
    since = _SINCE_MONTH.search(text)
    if since:
        month = _MONTH_NUMBERS[since.group(1).lower()]
        explicit = int(since.group(2)) if since.group(2) else None
        year = _year_for(month, today, explicit)
        start = date(year, month, 1)
        return _window_ending(start, today, today, f"since {_MONTH_NAMES[month]}")
    first = _FIRST_WEEK.search(text)
    if first:
        month = _MONTH_NUMBERS[first.group(1).lower()]
        explicit = int(first.group(2)) if first.group(2) else None
        year = _year_for(month, today, explicit)
        start = date(year, month, 1)
        end = _safe_date(year, month, 7) or start
        return _window_ending(start, end, today, f"the first week of {_MONTH_NAMES[month]}")
    last_n = _LAST_N_DAYS.search(text)
    if last_n:
        count = max(1, int(last_n.group(1)))
        start = today - timedelta(days=count - 1)
        return _NamedWindow(start.isoformat(), today.isoformat(), True, f"last {count} days")
    if _YESTERDAY.search(text):
        day = today - timedelta(days=1)
        iso = day.isoformat()
        return _NamedWindow(iso, iso, True, "yesterday")
    if _LAST_WEEK.search(text):
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last week")
    if _THIS_YEAR.search(text):
        start = date(today.year, 1, 1)
        return _window_ending(start, today, today, "this year")
    if _LAST_YEAR.search(text):
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last year")
    quarter = _QUARTER.search(text)
    if quarter:
        number = int(quarter.group(1))
        explicit = int(quarter.group(2)) if quarter.group(2) else None
        start_month = (number - 1) * 3 + 1
        year = explicit if explicit is not None else _year_for(start_month, today, None)
        start = date(year, start_month, 1)
        end = _month_end(date(year, start_month + 2, 1))
        return _window_ending(start, end, today, f"Q{number}")
    return None


def _named_window(message: str, timezone_name: str | None, now: datetime) -> _NamedWindow | None:
    text = message or ""
    if _relative_period_wins(text):
        return None
    today = today_in(timezone_name, now)
    special = _special_window(text, today)
    if special is not None:
        return special
    distinct = _distinct_months(text)
    if len(distinct) >= 2:
        months = [token[2] for token in distinct]
        earlier, later = min(months), max(months)
        same_year = _year_for(earlier, today, None) == _year_for(later, today, None)
        day_level = any(_day_after(text, token[1]) for token in distinct)
        label = f"{_MONTH_NAMES[earlier]} and {_MONTH_NAMES[later]}"
        if day_level or not same_year or later - earlier != 1:
            return _NamedWindow("", "", False, label)
        year = _year_for(earlier, today, None)
        start = date(year, earlier, 1)
        end = _month_end(date(year, later, 1))
        return _window_ending(start, end, today, label)
    token = _month_token(text)
    if token:
        token_start, token_end, month = token
        explicit_year = _year_beside(text, token_start, token_end)
        year = _year_for(month, today, explicit_year)
        label = f"{_MONTH_NAMES[month]} {year}" if explicit_year is not None else _MONTH_NAMES[month]
        day = _day_after(text, token_end)
        # "may 1" still means the month of May. "sep 15" and "on oct 3" are that day.
        if day is not None and (day > 1 or _on_day(text, token_start)):
            concrete = _safe_date(year, month, day)
            day_label = f"{_MONTH_NAMES[month]} {day}"
            if concrete is None or concrete > today:
                return _NamedWindow("", "", False, day_label)
            iso = concrete.isoformat()
            return _NamedWindow(iso, iso, True, day_label)
        start = date(year, month, 1)
        if start > today:
            return _NamedWindow("", "", False, label)
        end = today if (year == today.year and month == today.month) else _month_end(start)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, label)
    if _LAST_MONTH.search(text):
        start = _shift_months(date(today.year, today.month, 1), -1)
        end = _month_end(start)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last month")
    return None


def message_names_explicit_month(message: str) -> bool:
    text = message or ""
    if _relative_period_wins(text):
        return False
    return _month_token(text) is not None


def named_calendar_range(message: str, timezone_name: str | None, now: datetime) -> tuple[str, str] | None:
    """Month named in the message, or last month as the previous full calendar month.

    A month later than today, with no year, uses the previous year. The current
    month is month-to-date. A 4-digit year next to the month is that year.
    A future window is not returned; named_period_unserved carries its label.
    this month, MTD, so far, and this week win over a month word.
    A named month beats a stray today or now. A day number is that day, not the whole month.
    """
    window = _named_window(message, timezone_name, now)
    if window is None or not window.served:
        return None
    return window.start, window.end


def named_period_unserved(message: str, timezone_name: str | None, now: datetime) -> str | None:
    """Label of a named period the tools cannot answer, such as a future year."""
    window = _named_window(message, timezone_name, now)
    if window is None or window.served:
        return None
    return window.label


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
