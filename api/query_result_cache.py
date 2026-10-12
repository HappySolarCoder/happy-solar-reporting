# -*- coding: utf-8 -*-

"""In-process cache of dashboard query results.

Mirrors company_snapshot's short cache for ranges that still include today.
Ranges that end before today stay warm for 10 minutes (inside the 5–15
minute window). Nothing here writes to Firestore.
"""

from __future__ import annotations

import copy
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

OPEN_TTL_SECONDS = 60
PAST_TTL_SECONDS = 600
_MAX_ENTRIES = 32
_NY = ZoneInfo("America/New_York")
_PAST_PERIODS = frozenset({"yesterday", "lastwk", "lastmo"})


def today_ny(now: datetime | None = None) -> date:
    current = now or datetime.now(_NY)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_NY)
    return current.astimezone(_NY).date()


def month_end_ymd(year: int, month: int) -> str:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def range_end_ymd(
    *,
    start: str | None = None,
    end: str | None = None,
    year: int | None = None,
    month: int | None = None,
    period: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Inclusive end date for a query, when the query names one."""
    text = (end or "").strip()
    if len(text) >= 10:
        return text[:10]
    period_key = (period or "").strip().lower()
    if period_key in _PAST_PERIODS:
        return (today_ny(now) - timedelta(days=1)).isoformat()
    if period_key:
        return today_ny(now).isoformat()
    if year and month:
        return month_end_ymd(int(year), int(month))
    return None


def ttl_seconds(end_ymd: str | None, *, now: datetime | None = None, past_ttl: int = PAST_TTL_SECONDS) -> int:
    text = (end_ymd or "").strip()[:10]
    if len(text) == 10 and text < today_ny(now).isoformat():
        return past_ttl
    return OPEN_TTL_SECONDS


class QueryCache:
    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._store: dict[str, tuple[float, int, object]] = {}
        self.max_entries = max_entries

    def get(self, key: str):
        hit = self._store.get(key)
        if not hit:
            return None
        stored, ttl, payload = hit
        if time.monotonic() - stored > ttl:
            self._store.pop(key, None)
            return None
        return copy.deepcopy(payload)

    def put(self, key: str, payload, ttl: int) -> None:
        self._store.pop(key, None)
        self._store[key] = (time.monotonic(), int(ttl), copy.deepcopy(payload))
        while len(self._store) > self.max_entries:
            self._store.pop(next(iter(self._store)))

    def clear(self) -> None:
        self._store.clear()
