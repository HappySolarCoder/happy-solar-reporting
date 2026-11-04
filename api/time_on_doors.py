# -*- coding: utf-8 -*-

"""FMA time on doors.

Time on doors is the span from the first counted door knock to the last counted
door knock in the dashboard window. The knock clock is the history event
timestamp from ``knock_count``, not the lead's latest ``dispositionedAt``.

Knock totals credit ``entry.userId``. ``knock_actor_id`` is the legacy
latest-row actor (``dispositionHistory[0].userId``, then ``claimedBy``) and is
not used for knock totals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def knock_actor_id(lead: dict[str, Any] | None) -> str | None:
    """Actor for a knock: dispositionHistory[0].userId, else claimedBy."""

    if not isinstance(lead, dict):
        return None
    actor = None
    try:
        hist0 = (lead.get("dispositionHistory") or [None])[0]
        if isinstance(hist0, dict):
            actor = hist0.get("userId")
    except Exception:
        actor = None
    if actor in (None, ""):
        actor = lead.get("claimedBy")
    if actor in (None, ""):
        return None
    return str(actor)


def coerce_knock_timestamp(value: Any) -> datetime | None:
    """Parse a knock clock into an aware datetime.

    Firestore returns datetimes (including DatetimeWithNanoseconds). ISO strings
    are accepted so cached JSON and tests can reuse the same helper. Naive
    values are treated as UTC instants.
    """

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            parsed = datetime.fromisoformat(text)
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def format_time_on_doors(seconds: int | float | None) -> str:
    """Human duration. Total hours, minutes floored, e.g. ``4h 12m`` or ``0h 00m``."""

    if seconds is None:
        return "—"
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "—"
    if total < 0:
        total = 0
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours}h {minutes:02d}m"


def _empty_span() -> dict[str, Any]:
    return {"knocks": 0, "timestamped_knocks": 0, "first": None, "last": None}


def observe_door_knock(spans: dict[str, dict[str, Any]], actor_id: str, timestamp: Any) -> None:
    """Record one counted knock. Missing clocks still increment knocks."""

    if actor_id in (None, ""):
        return
    key = str(actor_id)
    span = spans.get(key)
    if span is None:
        span = _empty_span()
        spans[key] = span
    span["knocks"] = int(span.get("knocks") or 0) + 1
    moment = coerce_knock_timestamp(timestamp)
    if moment is None:
        return
    span["timestamped_knocks"] = int(span.get("timestamped_knocks") or 0) + 1
    if span["first"] is None or moment < span["first"]:
        span["first"] = moment
    if span["last"] is None or moment > span["last"]:
        span["last"] = moment


def _span_seconds(first: datetime | None, last: datetime | None, timestamped: int) -> int | None:
    if timestamped <= 0 or first is None or last is None:
        return None
    delta = (last - first).total_seconds()
    if delta <= 0:
        return 0
    return int(delta)


def time_on_doors_record(span: dict[str, Any]) -> dict[str, Any]:
    first = span.get("first") if isinstance(span.get("first"), datetime) else None
    last = span.get("last") if isinstance(span.get("last"), datetime) else None
    knocks = int(span.get("knocks") or 0)
    timestamped = int(span.get("timestamped_knocks") or 0)
    seconds = _span_seconds(first, last, timestamped)
    return {
        "seconds": seconds,
        "knocks": knocks,
        "first_dispositionedAt": first.isoformat() if first else None,
        "last_dispositionedAt": last.isoformat() if last else None,
        "duration": format_time_on_doors(seconds),
        "timestamps_missing": max(0, knocks - timestamped),
    }


def time_on_doors_by_actor(spans: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-actor spans, longest time first, then knocks, then actor id."""

    records = {uid: time_on_doors_record(span) for uid, span in spans.items()}

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple:
        uid, rec = item
        seconds = rec.get("seconds")
        rank = -(seconds if isinstance(seconds, int) else -1)
        return (rank, -int(rec.get("knocks") or 0), uid)

    return {uid: rec for uid, rec in sorted(records.items(), key=sort_key)}


def aggregate_time_on_doors(events: list[tuple[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate ``(actor_id, dispositioned_at)`` pairs for counted knocks."""

    spans: dict[str, dict[str, Any]] = {}
    for actor_id, timestamp in events:
        observe_door_knock(spans, actor_id, timestamp)
    return time_on_doors_by_actor(spans)


EASTERN = ZoneInfo("America/New_York")
BUCKET_MINUTES = 30
_BUCKET_MS = BUCKET_MINUTES * 60 * 1000
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def actor_display_name(actor_id: Any, names: dict[str, str] | None = None) -> str:
    """Same label ``time_on_doors_table`` uses for a Raydar user id."""

    names = names or {}
    label = names.get(str(actor_id)) if actor_id not in (None, "") else None
    return str(label or actor_id or "—").strip() or "—"


def _floor_eastern_bucket(moment: datetime) -> datetime:
    local = moment.astimezone(EASTERN)
    minute = (local.minute // BUCKET_MINUTES) * BUCKET_MINUTES
    return local.replace(minute=minute, second=0, microsecond=0)


def _clock_parts(hour: int, minute: int) -> tuple[str, str]:
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d}", suffix


def format_half_hour_label(start: datetime, *, with_date: bool = False, with_tz: bool = False) -> str:
    """Wall-clock range, e.g. ``3:00–3:30 PM``. The end is 30 clock minutes later.

    The end is added on the clock face. Aware timedelta math is not used, so a
    spring-forward gap and a fall-back fold do not rename the bucket.
    """

    end_total = (start.hour * 60 + start.minute + BUCKET_MINUTES) % (24 * 60)
    end_hour, end_minute = divmod(end_total, 60)
    start_clock, start_suffix = _clock_parts(start.hour, start.minute)
    end_clock, end_suffix = _clock_parts(end_hour, end_minute)
    if start_suffix == end_suffix:
        text = f"{start_clock}\u2013{end_clock} {end_suffix}"
    else:
        text = f"{start_clock} {start_suffix}\u2013{end_clock} {end_suffix}"
    if with_tz:
        text = f"{text} {start.tzname() or 'ET'}"
    if with_date:
        text = f"{_MONTHS[start.month - 1]} {start.day}, {text}"
    return text


def knock_time_chart(
    events: list[tuple[str, Any]],
    names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """30-minute Eastern knock counts for the daily chart.

    ``events`` are counted knocks only, ``(actor_id, timestamp)``. The clock is
    the history event time (the same instant time on doors stores as
    ``first_dispositionedAt`` / ``last_dispositionedAt``), converted to
    America/New_York and floored into a half-hour bucket. A knock at 3:30 PM
    belongs to 3:30–4:00, not the bucket that just ended.

    Each value is the knocks in that bucket, not a running total. Buckets from
    the earliest knock to the latest knock are present even when the count is
    zero. Names, merges, and sort match ``time_on_doors_table``.
    """

    names = names or {}
    table = time_on_doors_table(aggregate_time_on_doors(events), names)
    by_name: dict[str, dict[int, int]] = {str(row["name"]): {} for row in table}
    bucket_at: dict[int, datetime] = {}

    for actor_id, timestamp in events:
        if actor_id in (None, ""):
            continue
        name = actor_display_name(actor_id, names)
        moment = coerce_knock_timestamp(timestamp)
        counts = by_name.setdefault(name, {})
        if moment is None:
            continue
        start = _floor_eastern_bucket(moment)
        key = int(start.timestamp() * 1000)
        counts[key] = int(counts.get(key) or 0) + 1
        bucket_at.setdefault(key, start)

    order = [str(row["name"]) for row in table]
    for name in by_name:
        if name not in order:
            order.append(name)

    if not bucket_at:
        return {
            "timezone": "America/New_York",
            "bucket_minutes": BUCKET_MINUTES,
            "buckets": [],
            "series": [{"name": name, "counts": []} for name in order],
        }

    first = min(bucket_at)
    last = max(bucket_at)
    keys: list[int] = []
    cursor = first
    while cursor <= last and len(keys) <= 366 * 48:
        keys.append(cursor)
        if cursor not in bucket_at:
            bucket_at[cursor] = datetime.fromtimestamp(cursor / 1000, tz=EASTERN)
        cursor += _BUCKET_MS

    starts = [bucket_at[key] for key in keys]
    with_date = len({item.date() for item in starts}) > 1
    base_labels = [format_half_hour_label(item, with_date=with_date) for item in starts]
    with_tz = len(base_labels) != len(set(base_labels))
    buckets: list[dict[str, str]] = []
    for start, base in zip(starts, base_labels):
        label = format_half_hour_label(start, with_date=with_date, with_tz=True) if with_tz else base
        buckets.append({"start": start.isoformat(), "label": label})

    series = [
        {"name": name, "counts": [int((by_name.get(name) or {}).get(key, 0)) for key in keys]}
        for name in order
    ]
    return {
        "timezone": "America/New_York",
        "bucket_minutes": BUCKET_MINUTES,
        "buckets": buckets,
        "series": series,
    }


def time_on_doors_table(
    by_actor: dict[str, dict[str, Any]] | None,
    names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Display rows for the daily dashboard.

    Names come from the same Raydar user map as ``top_knockers``. Rows that share
    a display name are one span (earliest first knock through latest last knock).

    Sort: time on doors descending, then knocks descending, then name.
    """

    names = names or {}
    grouped: dict[str, dict[str, Any]] = {}
    for uid, rec in (by_actor or {}).items():
        if not isinstance(rec, dict):
            continue
        name = actor_display_name(uid, names)
        first = coerce_knock_timestamp(rec.get("first_dispositionedAt"))
        last = coerce_knock_timestamp(rec.get("last_dispositionedAt"))
        try:
            knocks = int(rec.get("knocks") or 0)
        except (TypeError, ValueError):
            knocks = 0
        bucket = grouped.get(name)
        if bucket is None:
            grouped[name] = {"name": name, "knocks": knocks, "first": first, "last": last}
            continue
        bucket["knocks"] += knocks
        if first is not None and (bucket["first"] is None or first < bucket["first"]):
            bucket["first"] = first
        if last is not None and (bucket["last"] is None or last > bucket["last"]):
            bucket["last"] = last

    rows: list[dict[str, Any]] = []
    for bucket in grouped.values():
        first = bucket["first"] if isinstance(bucket["first"], datetime) else None
        last = bucket["last"] if isinstance(bucket["last"], datetime) else None
        timestamped = 1 if first is not None and last is not None else 0
        seconds = _span_seconds(first, last, timestamped)
        rows.append(
            {
                "name": bucket["name"],
                "seconds": seconds,
                "duration": format_time_on_doors(seconds),
                "knocks": int(bucket["knocks"] or 0),
                "first_dispositionedAt": first.isoformat() if first else None,
                "last_dispositionedAt": last.isoformat() if last else None,
            }
        )

    def sort_key(row: dict[str, Any]) -> tuple:
        seconds = row.get("seconds")
        rank = -(seconds if isinstance(seconds, int) else -1)
        return (rank, -int(row.get("knocks") or 0), str(row.get("name") or "").lower())

    rows.sort(key=sort_key)
    return rows
