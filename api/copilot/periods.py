# -*- coding: utf-8 -*-
"""Reporting windows. The company timezone is an explicit argument, never the server zone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_TODAY = re.compile(r"\b(?:so far\s+)?today\b", re.I)
_THIS_WEEK = re.compile(r"\bthis week\b", re.I)
_MONTH_WORD = r"month|mnth|mth|montn|mnoth"
_MONTH_TO_DATE = re.compile(
    rf"\b(?:this (?:whole\s+)?(?:{_MONTH_WORD})|the whole (?:{_MONTH_WORD})|"
    rf"for the (?:{_MONTH_WORD})|month to date|mtd|so far|current)\b",
    re.I,
)
_LAST_MONTH = re.compile(rf"\blast (?:{_MONTH_WORD})\b", re.I)
_RELATIVE_BLOCK = re.compile(
    rf"\b(?:this (?:whole\s+)?(?:{_MONTH_WORD})|month to date|mtd|so far|this week)\b",
    re.I,
)
_STRAY_NOW = re.compile(r"\b(?:today|now)\b", re.I)
_MONTH_ALT = (
    r"january|february|march|april|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec|may"
)
_RANGE_JOIN = r"to|through|thru|until|[-–—]"
_RANGE_END = r"today|now|date"
_DAY_RANGE = re.compile(
    rf"\b(?:from\s+)?({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:{_RANGE_JOIN})\s+"
    rf"(?:({_MONTH_ALT})\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\b",
    re.I,
)
_TO_TODAY_NAMED = re.compile(
    rf"\b(?:from\s+)?({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:{_RANGE_JOIN})\s+(?:{_RANGE_END})\b",
    re.I,
)
_TO_TODAY_NUM = re.compile(
    rf"\b(?:from\s+)?(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{2,4}}))?\s*(?:{_RANGE_JOIN})\s*(?:{_RANGE_END})\b",
    re.I,
)
_SINCE_POINT = re.compile(
    r"\bsince\s+the\s+(?:start|beginning)\s+of\s+(?:the\s+)?(year|month|week|quarter)\b",
    re.I,
)
_SO_FAR_WEEK = re.compile(r"\bso far\s+this week\b", re.I)
_SINCE_MONTH = re.compile(rf"\bsince\s+({_MONTH_ALT})\b(?:\s+((?:19|20)\d{{2}}))?", re.I)
_FIRST_WEEK = re.compile(rf"\bfirst week of\s+({_MONTH_ALT})\b(?:\s+((?:19|20)\d{{2}}))?", re.I)
_LAST_N_DAYS = re.compile(r"\blast\s+(\d+)\s+days?\b", re.I)
_YESTERDAY = re.compile(r"\byesterday\b", re.I)
_LAST_WEEK = re.compile(r"\blast week\b", re.I)
_THIS_YEAR = re.compile(r"\b(?:ytd|year to date|this year)\b", re.I)
_LAST_YEAR = re.compile(r"\blast year\b", re.I)
_QUARTER = re.compile(r"\bq([1-4])\b(?:\s+((?:19|20)\d{2}))?", re.I)
_THIS_QUARTER = re.compile(r"\bthis quarter\b", re.I)
_NUM_RANGE = re.compile(
    rf"\b(?:from\s+)?(\d{{1,2}})/(\d{{1,2}})(?:/(\d{{2,4}}))?\s*(?:{_RANGE_JOIN})\s*"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b",
    re.I,
)
_NUM_DAY = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_BETWEEN_DAYS = re.compile(
    rf"\bbetween\s+({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+and\s+"
    rf"(?:({_MONTH_ALT})\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\b",
    re.I,
)
_WEEK_OF = re.compile(rf"\bweek of\s+({_MONTH_ALT})\s+(\d{{1,2}})\b", re.I)
_LAST_N_WEEKS = re.compile(
    r"\b(?:last|past)\s+(\d+|one|two|three|four|six|twelve)\s+weeks?\b",
    re.I,
)
_PAST_N_MONTHS = re.compile(
    r"\b(?:past|last)\s+(\d+|one|two|three|four|six|twelve)\s+months?\b",
    re.I,
)
_PAST_MONTH = re.compile(r"\bpast\s+month\b", re.I)
_YEAR_ONLY = re.compile(r"\b(?:in|for|during)\s+((?:19|20)\d{2})\b", re.I)
_PAGE_RELATIVE = re.compile(
    rf"\b(?:this (?:whole\s+)?(?:{_MONTH_WORD})|the whole (?:{_MONTH_WORD})|"
    rf"for the (?:{_MONTH_WORD})|month to date|mtd|so far)\b",
    re.I,
)
# "to" / "through" between months is a span. compare / vs / better / beat is two windows.
_REAL_COMPARE = re.compile(
    r"\b(?:compare|compared|versus|vs\.?|against|changed|change|beat|beats|outperform(?:s|ed|ing)?)\b"
    r"|\bstack(?:s|ed|ing)?\s+up\s+against\b"
    r"|\b(?:go|going|went)\s+up\s+or\s+down\b"
    r"|\bbetter(?:\s+or\s+worse)?(?:\s+than)?\b"
    r"|\bworse(?:\s+or\s+better)?(?:\s+than)?\b"
    r"|\btrend\s+(?:vs\.?|versus|against)\b",
    re.I,
)
_WEEKDAY = re.compile(
    r"\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}
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
# Misspellings only. Edit distance also matches names (Marco, Marcy).
_MONTH_TYPOS = {
    "septmber": 9,
    "setember": 9,
    "septmeber": 9,
    "sepetember": 9,
    "septembe": 9,
    "sepember": 9,
    "septemer": 9,
    "ocotber": 10,
    "octobr": 10,
    "octber": 10,
    "octoer": 10,
    "febuary": 2,
    "februray": 2,
    "feburary": 2,
    "febraury": 2,
    "agust": 8,
    "augst": 8,
    "augus": 8,
    "novmber": 11,
    "novembr": 11,
    "novemeber": 11,
    "decembr": 12,
    "decmber": 12,
    "janurary": 1,
    "janury": 1,
    "aprill": 4,
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


def _at_sentence_start(text: str, start: int) -> bool:
    prefix = text[:start]
    return not prefix.strip() or bool(re.search(r"[.!?]\s*$", prefix))


def _in_month_slot(text: str, start: int, end: int) -> bool:
    """in/for/during April, or a month next to a year or a day. Not "how did April do"."""
    before = text[max(0, start - 24) : start]
    after = text[end : end + 16]
    if re.match(r"\s+(?:do|doing)\b", after, re.I):
        return False
    if re.search(
        r"\b(?:in|for|during|since|from|to|through|thru|of|versus|vs\.?|against|and|between)\s+$",
        before,
        re.I,
    ):
        return True
    if re.match(r"\s+(?:of\s+)?(?:19|20)\d{2}\b", after):
        return True
    if re.match(r"\s+\d{1,2}(?:st|nd|rd|th)?\b", after, re.I):
        return True
    if re.search(r"(?:the\s+)?month\s+of\s+$", before, re.I):
        return True
    return False


def _month_word_is_person(text: str, start: int, end: int) -> bool:
    """A month word used as a person. "how did April do" is April the rep, not April 1–30.

    "in April" and "for April" stay the month. A capitalized month that is not in a
    month slot could be either, so it is treated as a person and the answer caveats.
    """
    word = text[start:end].lower()
    if word not in _MONTH_NUMBERS and word not in _MONTH_TYPOS:
        return False
    after = text[end : end + 12]
    if re.match(r"['’]s\b", after):
        return True
    before = text[max(0, start - 40) : start]
    if re.search(r"\b(?:how\s+did|how(?:'s|’s|s)|how\s+is)\s+$", before, re.I):
        return True
    if re.search(r"\bdid\s+$", before, re.I) and re.match(r"\s+(?:do|doing)\b", after, re.I):
        return True
    if _in_month_slot(text, start, end):
        return False
    token = text[start:end]
    if token[:1].isupper() and not _at_sentence_start(text, start):
        return True
    if re.match(r"\s+(?:do|doing)\b", after, re.I):
        return True
    return False


def _typo_blocked(text: str, start: int, end: int) -> bool:
    """Known misspellings still count after "for". Names do not.

    Skip a capitalized mid-sentence typo, a possessive, and a word right after
    "how did" / "how's" / "by". "for agust" stays August.
    """
    after = text[end : end + 8]
    if re.match(r"['’]s\b", after):
        return True
    before = text[max(0, start - 32) : start]
    if re.search(r"\b(?:how\s+did|how(?:'s|’s|s)|how\s+is|by)\s+$", before, re.I):
        return True
    token = text[start:end]
    if token[:1].isupper() and not _at_sentence_start(text, start):
        return True
    return False


def _remember_month(found: list[tuple[int, int, int]], text: str, start: int, end: int, month: int) -> None:
    if _month_word_is_person(text, start, end):
        return
    found.append((start, end, month))


def _relative_period_wins(text: str) -> bool:
    """this month, MTD, so far, and this week beat a month name.

    "today" is its own day, including "so far today". A month already named
    keeps that month: "in september? I need it today" stays September.
    "so far this week" is that week, not the page month.
    """
    raw = text or ""
    if _SO_FAR_WEEK.search(raw):
        return False
    if _TODAY.search(raw) and _month_token(raw) is None and not _LAST_MONTH.search(raw):
        return False
    if _RELATIVE_BLOCK.search(raw):
        return True
    return False


def _all_month_tokens(text: str) -> list[tuple[int, int, int]]:
    """Month tokens as (start, end, month number), earliest first.

    Full names always count, unless the word is a person ("how did April do",
    "Marcy's", or a capitalized month that is not in a month phrase).
    "may" and 3-letter forms count only in a month phrase.
    Typos come from an explicit list, never edit distance.
    """
    found: list[tuple[int, int, int]] = []
    for match in _FULL_MONTH.finditer(text):
        _remember_month(found, text, match.start(1), match.end(1), _MONTH_NUMBERS[match.group(1).lower()])
    for match in _SHORT_MONTH.finditer(text):
        token = (match.group(1) or match.group(2) or "").lower()
        if not token:
            continue
        if match.group(1):
            _remember_month(found, text, match.start(1), match.end(1), _MONTH_NUMBERS[token])
        else:
            _remember_month(found, text, match.start(2), match.end(2), _MONTH_NUMBERS[token])
    # Separate searches so "sep vs aug" and "jan through mar" keep both months.
    for match in re.finditer(
        rf"\b({_SHORT_MONTH_TOKEN})\s+(?=to|through|thru|versus|vs\.?|against)\b",
        text,
        re.I,
    ):
        token = match.group(1).lower()
        _remember_month(found, text, match.start(1), match.end(1), _MONTH_NUMBERS[token])
    for match in re.finditer(
        rf"\b(?:compare|versus|vs\.?|to|through|thru|against)\s+({_SHORT_MONTH_TOKEN})\b",
        text,
        re.I,
    ):
        token = match.group(1).lower()
        _remember_month(found, text, match.start(1), match.end(1), _MONTH_NUMBERS[token])
    for match in re.finditer(r"\b([A-Za-z]{4,12})\b", text):
        token = match.group(1)
        month = _MONTH_TYPOS.get(token.lower())
        if month is None or token.lower() in _MONTH_NUMBERS:
            continue
        if _typo_blocked(text, match.start(1), match.end(1)):
            continue
        _remember_month(found, text, match.start(1), match.end(1), month)
    found.sort()
    deduped: list[tuple[int, int, int]] = []
    seen_at: set[int] = set()
    for item in found:
        if item[0] in seen_at:
            continue
        seen_at.add(item[0])
        deduped.append(item)
    return deduped


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


def _window_ending(
    start: date,
    end: date,
    today: date,
    label: str,
    cover: tuple[int, int] | None = None,
) -> _NamedWindow:
    if start > today:
        return _NamedWindow("", "", False, label, cover)
    if end > today:
        end = today
    if end < start:
        return _NamedWindow("", "", False, label, cover)
    return _NamedWindow(start.isoformat(), end.isoformat(), True, label, cover)


def _count_token(token: str | None) -> int | None:
    if not token:
        return None
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token.lower())


def _expand_year(token: str | None) -> int | None:
    if not token:
        return None
    year = int(token)
    if year < 100:
        year += 2000
    return year


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last = _month_end(date(year, month, 1)).day
    return date(year, month, min(day.day, last))


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
    cover: tuple[int, int] | None = None


def _day_after(text: str, token_end: int) -> int | None:
    match = re.match(r"\s+(\d{1,2})(?:st|nd|rd|th)?\b", text[token_end : token_end + 8], re.I)
    if not match:
        return None
    return int(match.group(1))


def _cover_start(text: str, token_start: int) -> int:
    """Include a year or 'the month of' that sits in front of a month word."""
    start = token_start
    month_of = re.search(r"(?:the\s+)?month\s+of\s+$", text[max(0, start - 24) : start], re.I)
    if month_of:
        start -= len(month_of.group(0))
    year_before = re.search(r"\b(?:19|20)\d{2}\s+$", text[max(0, start - 12) : start])
    if year_before:
        start -= len(year_before.group(0))
    return start


def _on_day(text: str, token_start: int) -> bool:
    return bool(re.search(r"\bon\s+$", text[max(0, token_start - 4) : token_start], re.I))


def _numeric_year(token: str | None, month: int, today: date) -> int:
    explicit = _expand_year(token)
    return _year_for(month, today, explicit)


def _special_window(text: str, today: date) -> _NamedWindow | None:
    """Exact windows that are cheaper to apply than to caveat. None if not one of these."""
    # "<month> <day> to today" is that span, not the whole month and not that one day.
    to_today = _TO_TODAY_NAMED.search(text)
    if to_today:
        month = _MONTH_NUMBERS[to_today.group(1).lower()]
        year = _year_for(month, today, _year_beside(text, to_today.start(1), to_today.end(1)))
        start = _safe_date(year, month, int(to_today.group(2)))
        label = "that date range"
        if start is None or start > today:
            return _NamedWindow("", "", False, label, to_today.span())
        return _window_ending(start, today, today, label, to_today.span())
    to_today_num = _TO_TODAY_NUM.search(text)
    if to_today_num:
        month = int(to_today_num.group(1))
        day_number = int(to_today_num.group(2))
        year = _numeric_year(to_today_num.group(3), month, today)
        start = _safe_date(year, month, day_number)
        label = "that date range"
        if start is None or start > today:
            return _NamedWindow("", "", False, label, to_today_num.span())
        return _window_ending(start, today, today, label, to_today_num.span())
    so_far_week = _SO_FAR_WEEK.search(text)
    if so_far_week:
        monday = today - timedelta(days=today.weekday())
        return _window_ending(monday, today, today, "so far this week", so_far_week.span())
    since_point = _SINCE_POINT.search(text)
    if since_point:
        unit = since_point.group(1).lower()
        if unit == "year":
            start = date(today.year, 1, 1)
        elif unit == "week":
            start = today - timedelta(days=today.weekday())
        elif unit == "quarter":
            start_month = ((today.month - 1) // 3) * 3 + 1
            start = date(today.year, start_month, 1)
        else:
            start = date(today.year, today.month, 1)
        return _window_ending(start, today, today, f"since the start of the {unit}", since_point.span())
    numeric_range = _NUM_RANGE.search(text)
    if numeric_range:
        month = int(numeric_range.group(1))
        end_month = int(numeric_range.group(4))
        year = _numeric_year(numeric_range.group(3), month, today)
        end_explicit = _expand_year(numeric_range.group(6))
        end_year = end_explicit if end_explicit is not None else (year if end_month >= month else year + 1)
        start = _safe_date(year, month, int(numeric_range.group(2)))
        end = _safe_date(end_year, end_month, int(numeric_range.group(5)))
        label = "that date range"
        if start is None or end is None:
            return _NamedWindow("", "", False, label, numeric_range.span())
        return _window_ending(start, end, today, label, numeric_range.span())
    between = _BETWEEN_DAYS.search(text)
    if between:
        month = _MONTH_NUMBERS[between.group(1).lower()]
        end_word = between.group(3)
        end_month = _MONTH_NUMBERS[end_word.lower()] if end_word else month
        year = _year_for(month, today, _year_beside(text, between.start(1), between.end(1)))
        end_year = year if end_month >= month else year + 1
        start = _safe_date(year, month, int(between.group(2)))
        end = _safe_date(end_year, end_month, int(between.group(4)))
        label = "that date range"
        if start is None or end is None:
            return _NamedWindow("", "", False, label, between.span())
        return _window_ending(start, end, today, label, between.span())
    week_of = _WEEK_OF.search(text)
    if week_of:
        month = _MONTH_NUMBERS[week_of.group(1).lower()]
        year = _year_for(month, today, _year_beside(text, week_of.start(1), week_of.end(1)))
        anchor = _safe_date(year, month, int(week_of.group(2)))
        label = "that week"
        if anchor is None:
            return _NamedWindow("", "", False, label, week_of.span())
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        return _window_ending(start, end, today, label, week_of.span())
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
            return _NamedWindow("", "", False, label, ranged.span())
        return _window_ending(start, end, today, label, ranged.span())
    numeric_day = _NUM_DAY.search(text)
    if numeric_day:
        month = int(numeric_day.group(1))
        day_number = int(numeric_day.group(2))
        year = _numeric_year(numeric_day.group(3), month, today)
        concrete = _safe_date(year, month, day_number)
        label = f"{month}/{day_number}"
        if concrete is None or concrete > today:
            return _NamedWindow("", "", False, label, numeric_day.span())
        iso = concrete.isoformat()
        return _NamedWindow(iso, iso, True, label, numeric_day.span())
    since_day = re.search(
        r"\bsince\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+((?:19|20)\d{2}))?\b",
        text,
        re.I,
    )
    if since_day:
        month_word = since_day.group(1).lower()
        month = _MONTH_NUMBERS.get(month_word) or _MONTH_TYPOS.get(month_word)
        if month is not None:
            day_number = int(since_day.group(2))
            explicit = int(since_day.group(3)) if since_day.group(3) else None
            year = _year_for(month, today, explicit)
            start = _safe_date(year, month, day_number)
            label = f"since {_MONTH_NAMES[month]} {day_number}"
            if start is None or start > today:
                return _NamedWindow("", "", False, label, since_day.span())
            return _window_ending(start, today, today, label, since_day.span())
    since = _SINCE_MONTH.search(text)
    if since:
        month = _MONTH_NUMBERS[since.group(1).lower()]
        explicit = int(since.group(2)) if since.group(2) else None
        year = _year_for(month, today, explicit)
        start = date(year, month, 1)
        return _window_ending(start, today, today, f"since {_MONTH_NAMES[month]}", since.span())
    first = _FIRST_WEEK.search(text)
    if first:
        month = _MONTH_NUMBERS[first.group(1).lower()]
        explicit = int(first.group(2)) if first.group(2) else None
        year = _year_for(month, today, explicit)
        start = date(year, month, 1)
        end = _safe_date(year, month, 7) or start
        return _window_ending(start, end, today, f"the first week of {_MONTH_NAMES[month]}", first.span())
    last_n = _LAST_N_DAYS.search(text)
    if last_n:
        count = max(1, int(last_n.group(1)))
        start = today - timedelta(days=count - 1)
        return _NamedWindow(start.isoformat(), today.isoformat(), True, f"last {count} days", last_n.span())
    yesterday = re.search(r"\b(?:(?:thru|through)\s+)?yesterday\b", text, re.I)
    if yesterday:
        day = today - timedelta(days=1)
        iso = day.isoformat()
        return _NamedWindow(iso, iso, True, "yesterday", yesterday.span())
    last_weeks = _LAST_N_WEEKS.search(text)
    if last_weeks:
        count = max(1, _count_token(last_weeks.group(1)) or 1)
        this_monday = today - timedelta(days=today.weekday())
        end = this_monday - timedelta(days=1)
        start = this_monday - timedelta(days=7 * count)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, f"last {count} weeks", last_weeks.span())
    if _LAST_WEEK.search(text):
        match = _LAST_WEEK.search(text)
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last week", match.span() if match else None)
    if _THIS_YEAR.search(text):
        match = _THIS_YEAR.search(text)
        start = date(today.year, 1, 1)
        return _window_ending(start, today, today, "this year", match.span() if match else None)
    if _LAST_YEAR.search(text):
        match = _LAST_YEAR.search(text)
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last year", match.span() if match else None)
    if _THIS_QUARTER.search(text):
        match = _THIS_QUARTER.search(text)
        start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, start_month, 1)
        end = _month_end(date(today.year, start_month + 2, 1))
        return _window_ending(start, end, today, "this quarter", match.span() if match else None)
    quarters = list(_QUARTER.finditer(text))
    if quarters:
        quarter = quarters[0]
        number = int(quarter.group(1))
        years = [int(item.group(2)) if item.group(2) else None for item in quarters[:2]]
        shared = _one_sided_year(years) if len(quarters) >= 2 else None
        explicit = int(quarter.group(2)) if quarter.group(2) else shared
        start_month = (number - 1) * 3 + 1
        year = explicit if explicit is not None else _year_for(start_month, today, None)
        start = date(year, start_month, 1)
        end = _month_end(date(year, start_month + 2, 1))
        return _window_ending(start, end, today, f"Q{number}", quarter.span())
    past_n = _PAST_N_MONTHS.search(text)
    if past_n:
        count = max(1, _count_token(past_n.group(1)) or 1)
        start = _add_months(today, -count)
        return _window_ending(start, today, today, f"past {count} months", past_n.span())
    if _PAST_MONTH.search(text):
        match = _PAST_MONTH.search(text)
        start = _add_months(today, -1)
        return _window_ending(start, today, today, "the past month", match.span() if match else None)
    if _month_token(text) is None:
        year_only = _YEAR_ONLY.search(text)
        if year_only:
            year = int(year_only.group(1))
            start = date(year, 1, 1)
            end = date(year, 12, 31)
            label = str(year)
            if start > today:
                return _NamedWindow("", "", False, label, year_only.span())
            return _window_ending(start, end, today, label, year_only.span())
    # A lone today, or the most recent Monday–Sunday. A month already named
    # keeps that month, so a trailing "today" does not replace it.
    if _month_token(text) is None and not _LAST_MONTH.search(text):
        weekday = _WEEKDAY.search(text)
        if weekday and not re.search(rf"\b{re.escape(weekday.group(1))}s\b", text, re.I):
            name = weekday.group(1).lower()
            delta = (today.weekday() - _WEEKDAY_INDEX[name]) % 7
            day = today - timedelta(days=delta)
            iso = day.isoformat()
            return _NamedWindow(iso, iso, True, name, weekday.span())
        today_match = _TODAY.search(text)
        if today_match:
            iso = today.isoformat()
            return _NamedWindow(iso, iso, True, "today", today_match.span())
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
    # "compare September to August" is two periods, not one merged span.
    # "from July to September" and "Jan through Mar" are one span.
    comparing = bool(_REAL_COMPARE.search(text)) and not _DAY_RANGE.search(text) and not _BETWEEN_DAYS.search(text)
    if len(distinct) >= 2 and not comparing:
        months = [token[2] for token in distinct]
        earlier, later = min(months), max(months)
        explicit_years = [_year_beside(text, token[0], token[1]) for token in distinct]
        shared_year = next((year for year in explicit_years if year is not None), None)
        if shared_year is not None:
            same_year = True
        else:
            same_year = _year_for(earlier, today, None) == _year_for(later, today, None)
        day_level = any(_day_after(text, token[1]) for token in distinct)
        label = f"{_MONTH_NAMES[earlier]} and {_MONTH_NAMES[later]}"
        cover_end = distinct[-1][1]
        year_after = re.match(r"\s+((?:19|20)\d{2})\b", text[cover_end : cover_end + 8])
        if year_after:
            cover_end += year_after.end()
        cover = (distinct[0][0], cover_end)
        middle = text[distinct[0][1] : distinct[-1][0]]
        ranged = bool(re.search(r"\b(?:to|through|thru)\b", middle, re.I))
        if day_level or not same_year or (later - earlier != 1 and not ranged):
            return _NamedWindow("", "", False, label, cover)
        year = shared_year if shared_year is not None else _year_for(earlier, today, None)
        start = date(year, earlier, 1)
        end = _month_end(date(year, later, 1))
        return _window_ending(start, end, today, label, cover)
    shared_compare_year = None
    if comparing and len(distinct) >= 2:
        side_years = [_year_beside(text, token[0], token[1]) for token in distinct[:2]]
        shared_compare_year = _one_sided_year(side_years)
        distinct = distinct[:1]
    token = distinct[0] if distinct else _month_token(text)
    if token:
        token_start, token_end, month = token
        explicit_year = _year_beside(text, token_start, token_end)
        if explicit_year is None:
            explicit_year = shared_compare_year
        year = _year_for(month, today, explicit_year)
        label = f"{_MONTH_NAMES[month]} {year}" if explicit_year is not None else _MONTH_NAMES[month]
        day = _day_after(text, token_end)
        cover_end = token_end
        year_match = re.match(r"\s+(?:of\s+)?((?:19|20)\d{2})\b", text[token_end : token_end + 24])
        day_match = re.match(r"\s+(\d{1,2})(?:st|nd|rd|th)?\b", text[token_end : token_end + 8], re.I)
        if year_match:
            cover_end = token_end + year_match.end()
        elif day_match:
            cover_end = token_end + day_match.end()
        cover = (_cover_start(text, token_start), cover_end)
        # "may 1" still means the month of May. "sep 15" and "on oct 3" are that day.
        if day is not None and (day > 1 or _on_day(text, token_start)):
            concrete = _safe_date(year, month, day)
            day_label = f"{_MONTH_NAMES[month]} {day}"
            if concrete is None or concrete > today:
                return _NamedWindow("", "", False, day_label, cover)
            iso = concrete.isoformat()
            return _NamedWindow(iso, iso, True, day_label, cover)
        start = date(year, month, 1)
        if start > today:
            return _NamedWindow("", "", False, label, cover)
        end = today if (year == today.year and month == today.month) else _month_end(start)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, label, cover)
    if _LAST_MONTH.search(text):
        match = _LAST_MONTH.search(text)
        start = _shift_months(date(today.year, today.month, 1), -1)
        end = _month_end(start)
        return _NamedWindow(start.isoformat(), end.isoformat(), True, "last month", match.span() if match else None)
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


def _one_sided_year(years: list[int | None]) -> int | None:
    """A year named on only one side of a compare applies to both sides."""
    present = [year for year in years if year is not None]
    if len(present) == 1 and any(year is None for year in years):
        return present[0]
    return None


def _quarter_bounds(match: re.Match, today: date, fallback_year: int | None = None) -> tuple[date, date]:
    number = int(match.group(1))
    explicit = int(match.group(2)) if match.group(2) else fallback_year
    start_month = (number - 1) * 3 + 1
    year = explicit if explicit is not None else _year_for(start_month, today, None)
    start = date(year, start_month, 1)
    end = _month_end(date(year, start_month + 2, 1))
    return start, end


def _resolved_quarters(text: str, today: date) -> list[tuple[re.Match, date, date]]:
    matches = list(_QUARTER.finditer(text))
    years = [int(match.group(2)) if match.group(2) else None for match in matches]
    shared = _one_sided_year(years[:2]) if len(matches) >= 2 else None
    resolved = []
    for index, match in enumerate(matches):
        fallback = shared if index < 2 else None
        start, end = _quarter_bounds(match, today, fallback)
        resolved.append((match, start, end))
    return resolved


def _month_compare_windows(
    text: str,
    today: date,
) -> list[tuple[str, str]] | None:
    if _DAY_RANGE.search(text) or _BETWEEN_DAYS.search(text):
        return None
    months = _distinct_months(text)
    if len(months) < 2:
        return None
    years = [_year_beside(text, start, end) for start, end, _month in months[:2]]
    shared = _one_sided_year(years)
    windows: list[tuple[str, str]] = []
    for (token_start, token_end, month), year in zip(months[:2], years):
        use_year = year if year is not None else shared
        year_n = _year_for(month, today, use_year)
        start = date(year_n, month, 1)
        end = _month_end(start)
        window = _window_ending(start, end, today, "", (token_start, token_end))
        if not window.served:
            return None
        windows.append((window.start, window.end))
    if windows[0] == windows[1]:
        return None
    return windows


def named_compare_pair(
    message: str,
    timezone_name: str | None,
    now: datetime,
) -> tuple[tuple[str, str], tuple[str, str]] | None:
    """Two quarters or months joined by compare/vs, in the order they were named.

    A trailing year applies to both sides: "q1 vs q2 2025" is Q1 2025 vs Q2 2025.
    None unless both windows can be served. The first is the current window.
    """
    text = message or ""
    if not _REAL_COMPARE.search(text):
        return None
    today = today_in(timezone_name, now)
    quarters = _resolved_quarters(text, today)
    if len(quarters) >= 2:
        windows: list[tuple[str, str]] = []
        for match, start, end in quarters[:2]:
            window = _window_ending(start, end, today, "", match.span())
            if not window.served:
                return None
            windows.append((window.start, window.end))
        if windows[0] == windows[1]:
            return None
        return windows[0], windows[1]
    months = _month_compare_windows(text, today)
    if months is None:
        return None
    return months[0], months[1]


def quarter_spans_covering(
    message: str,
    timezone_name: str | None,
    now: datetime,
    start: str,
    end: str,
) -> list[tuple[int, int]]:
    """Quarter words whose served window is exactly start–end."""
    if not start or not end:
        return []
    try:
        today = today_in(timezone_name, now)
    except TimezoneUnconfirmed:
        return []
    spans: list[tuple[int, int]] = []
    for match, qstart, qend in _resolved_quarters(message or "", today):
        window = _window_ending(qstart, qend, today, "", match.span())
        if window.served and window.start == start and window.end == end:
            spans.append(match.span())
    return spans


def applied_period_covers(
    message: str,
    timezone_name: str | None,
    now: datetime,
    start: str,
    end: str,
) -> list[tuple[int, int]]:
    """Character spans of period words that the applied dates actually used."""
    text = message or ""
    spans: list[tuple[int, int]] = []
    window = None
    try:
        window = _named_window(message, timezone_name, now)
    except TimezoneUnconfirmed:
        window = None
    matched = bool(
        window
        and window.served
        and window.cover
        and window.start == (start or "")
        and window.end == (end or "")
    )
    if matched and window is not None and window.cover is not None:
        spans.append(window.cover)
    elif window is None or not window.served:
        for relative in _PAGE_RELATIVE.finditer(text):
            spans.append(relative.span())
        if _relative_period_wins(text):
            for token in _all_month_tokens(text):
                spans.append((token[0], token[1]))
    for week in re.finditer(r"\bthis week\b", text, re.I):
        implied = None
        try:
            implied = implied_current_range(text, timezone_name, now)
        except TimezoneUnconfirmed:
            implied = None
        if implied == (start or "", end or ""):
            spans.append(week.span())
    for match in _STRAY_NOW.finditer(text):
        spans.append(match.span())
    return spans


def month_spans_covering(message: str, start: str, end: str) -> list[tuple[int, int]]:
    """Month words whose calendar month is the whole of start–end."""
    if not start or not end:
        return []
    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
    except ValueError:
        return []
    text = message or ""
    spans: list[tuple[int, int]] = []
    for token_start, token_end, month in _all_month_tokens(text):
        if start_d.month == month and end_d.month == month and start_d.year == end_d.year:
            span_start = token_start
            span_end = token_end
            year_after = re.match(r"\s+((?:19|20)\d{2})\b", text[token_end : token_end + 8])
            if year_after and int(year_after.group(1)) == start_d.year:
                span_end = token_end + year_after.end()
            before = text[max(0, token_start - 8) : token_start]
            year_before = re.search(r"\b((?:19|20)\d{2})\s+$", before)
            if year_before and int(year_before.group(1)) == start_d.year:
                span_start = token_start - (len(before) - year_before.start())
            spans.append((span_start, span_end))
    return spans


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
