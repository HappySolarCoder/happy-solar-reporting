# -*- coding: utf-8 -*-

"""FMA time on doors.

Time on doors is the span from the first counted door knock to the last counted
door knock in the dashboard window. The knock clock is
``raydar_leads_v1.dispositionedAt`` for dispositions with ``countsAsDoorKnock``.

Actor attribution matches the daily dashboard knock table:
``dispositionHistory[0].userId``, then ``claimedBy``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        label = names.get(str(uid))
        name = str(label or uid or "—").strip() or "—"
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
