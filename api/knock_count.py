# -*- coding: utf-8 -*-

"""Count Raydar door knocks from visit history.

Evan, 2026-11-03: no disposition ever subtracts a knock. Each
``dispositionHistory`` entry is one knock for ``entry.userId`` at
``entry.timestamp``, except Shade DQ (``shade-dq``), Already Has Solar
(``has-solar`` / ``already-has-solar``), and the non-knock ownership states.

The disposition catalog is used only to resolve a name to an id. The gate is
the sets below, not ``countsAsDoorKnock``. Day buckets stay America/New_York.
The Raydar app buckets in device-local time (Phoenix); this module does not.

This module does not read or write Firestore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

EXCLUDED_KNOCK_KEYS = frozenset({"shade-dq", "has-solar", "already-has-solar"})
NON_KNOCK_KEYS = frozenset(
    {
        "",
        "assigned",
        "unassigned",
        "unclaimed",
        "claimed",
        "new",
        "not-knocked",
        "available",
        "my-targets",
    }
)

# Unknown legacy strings count. Only the two sets above are dropped.
REPORTING_TZ = ZoneInfo("America/New_York")
_SPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class KnockEvent:
    key: str
    lead_id: str
    user_id: str
    at: int
    disposition_id: str
    dedupe_key: str


def normalize_token(raw: Any) -> str:
    """Trim, lowercase, and turn whitespace into single dashes."""

    if raw is None:
        return ""
    text = str(raw).strip().lower()
    return _SPACE_RUN.sub("-", text)


def _disposition_rows(dispositions: Any) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(dispositions, dict):
        for did, rec in dispositions.items():
            name = rec.get("name") if isinstance(rec, dict) else rec
            rows.append((str(did), name))
        return rows
    if isinstance(dispositions, (list, tuple)):
        for rec in dispositions:
            if not isinstance(rec, dict):
                continue
            did = rec.get("id")
            if did in (None, ""):
                did = rec.get("dispositionId")
            rows.append((str(did or ""), rec.get("name")))
    return rows


def normalize_dispo_key(raw: Any, dispositions: Any = None) -> str:
    """Resolve a disposition id or name to the catalog id, else the normalized raw value.

    Id match is exact. Name match uses :func:`normalize_token` (so a trailing
    space on ``Spoke with Non Homeowner`` still hits ``spoke-with-non-homeowner``).
    A normalized raw value that equals a normalized id also resolves to that id.
    """

    norm = normalize_token(raw)
    text = "" if raw is None else str(raw).strip()
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_norm_id: dict[str, str] = {}
    for did, name in _disposition_rows(dispositions):
        if not did:
            continue
        by_id[did] = did
        norm_id = normalize_token(did)
        if norm_id:
            by_norm_id.setdefault(norm_id, did)
        norm_name = normalize_token(name)
        if norm_name:
            by_name.setdefault(norm_name, did)
    if text in by_id:
        return by_id[text]
    if norm and norm in by_name:
        return by_name[norm]
    if norm and norm in by_norm_id:
        return by_norm_id[norm]
    return norm


def is_counted_knock(disposition_id: str | None) -> bool:
    """True when this resolved key is a knock under Evan's rule."""

    key = disposition_id or ""
    return key not in EXCLUDED_KNOCK_KEYS and key not in NON_KNOCK_KEYS


def _raw_is_blocked(raw: Any) -> bool:
    """Block the normalized raw name even if a catalog maps it to some other id."""

    norm = normalize_token(raw)
    return norm in EXCLUDED_KNOCK_KEYS or norm in NON_KNOCK_KEYS


def to_millis(value: Any) -> int | None:
    """Parse a knock clock. Invalid values are skipped, not raised.

    Accepts ``datetime`` (including Firestore ``DatetimeWithNanoseconds``),
    ISO strings (``T`` or space separator, ``Z`` or numeric offset), and
    ``{seconds, nanoseconds}`` / ``{_seconds, _nanoseconds}`` maps. Objects
    with ``seconds`` and ``nanoseconds`` attributes are accepted too.
    """

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(moment.timestamp() * 1000)
    if isinstance(value, dict):
        seconds = value.get("seconds")
        if seconds is None:
            seconds = value.get("_seconds")
        if seconds is None or isinstance(seconds, bool):
            return None
        nanos = value.get("nanoseconds")
        if nanos is None:
            nanos = value.get("_nanoseconds") or 0
        try:
            return int(float(seconds) * 1000 + int(nanos) / 1_000_000)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    seconds = getattr(value, "seconds", None)
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        nanos = getattr(value, "nanoseconds", 0) or 0
        try:
            return int(float(seconds) * 1000 + int(nanos) / 1_000_000)
        except (TypeError, ValueError):
            return None
    return None


def _lead_id(lead: dict[str, Any]) -> str:
    for key in ("id", "leadId"):
        value = lead.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _event_id(entry: dict[str, Any]) -> str:
    event_id = entry.get("eventId")
    if event_id in (None, ""):
        field = entry.get("field")
        if isinstance(field, dict):
            event_id = field.get("eventId")
    if event_id in (None, ""):
        return ""
    return str(event_id)


def _user_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _append_event(
    events: list[KnockEvent],
    seen: set[str],
    *,
    lead_id: str,
    user_id: str,
    at_ms: int,
    disposition_id: str,
    event_id: str,
) -> None:
    if event_id:
        dedupe_key = event_id
    else:
        dedupe_key = f"{lead_id}|{user_id}|{disposition_id}|{at_ms}"
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    events.append(
        KnockEvent(
            key=disposition_id,
            lead_id=lead_id,
            user_id=user_id,
            at=at_ms,
            disposition_id=disposition_id,
            dedupe_key=dedupe_key,
        )
    )


def _legacy_event(
    lead: dict[str, Any],
    dispositions: Any,
    seen: set[str],
) -> list[KnockEvent]:
    raw = lead.get("dispositionId")
    if raw in (None, ""):
        raw = lead.get("status")
    if _raw_is_blocked(raw):
        return []
    disposition_id = normalize_dispo_key(raw, dispositions)
    if not is_counted_knock(disposition_id):
        return []
    at_ms = to_millis(lead.get("dispositionedAt"))
    if at_ms is None:
        return []
    user_id = _user_text(lead.get("claimedBy")) or _user_text(lead.get("assignedTo"))
    if not user_id:
        return []
    events: list[KnockEvent] = []
    _append_event(
        events,
        seen,
        lead_id=_lead_id(lead),
        user_id=user_id,
        at_ms=at_ms,
        disposition_id=disposition_id,
        event_id="",
    )
    return events


def knock_events(
    lead: dict[str, Any] | None,
    dispositions: Any = None,
    seen: set[str] | None = None,
) -> list[KnockEvent]:
    """History entries on one lead. ``seen`` dedupes across snapshots and devices.

    Fallback to one event from ``status`` / ``dispositionId`` + ``dispositionedAt``
    only when ``dispositionHistory`` is missing or empty. The actor is then
    ``claimedBy`` or ``assignedTo``. Entries with no user id or no parseable
    time are skipped. A non-empty history of unusable entries does not fall back.
    """

    if not isinstance(lead, dict):
        return []
    bag = seen if seen is not None else set()
    history = lead.get("dispositionHistory")
    if not isinstance(history, list):
        if history in (None, ""):
            return _legacy_event(lead, dispositions, bag)
        return []
    if len(history) == 0:
        return _legacy_event(lead, dispositions, bag)

    events: list[KnockEvent] = []
    lead_id = _lead_id(lead)
    for entry in history:
        if not isinstance(entry, dict):
            continue
        user_id = _user_text(entry.get("userId"))
        if not user_id:
            continue
        at_ms = to_millis(entry.get("timestamp"))
        if at_ms is None:
            continue
        raw = entry.get("disposition")
        if raw in (None, ""):
            raw = entry.get("dispositionId")
        if _raw_is_blocked(raw):
            continue
        disposition_id = normalize_dispo_key(raw, dispositions)
        if not is_counted_knock(disposition_id):
            continue
        _append_event(
            events,
            bag,
            lead_id=lead_id,
            user_id=user_id,
            at_ms=at_ms,
            disposition_id=disposition_id,
            event_id=_event_id(entry),
        )
    return events


def collect_knock_events(
    leads: Iterable[Any],
    dispositions: Any = None,
    *,
    user_id: str | None = None,
    start: Any = None,
    end: Any = None,
) -> list[KnockEvent]:
    """Union of knock events across every snapshot of a lead id.

    The same lead may arrive as a full history, a trimmed history, and a local
    ack. Events are only added. A later, shorter snapshot cannot remove one.
    ``eventId`` dedupes across leads (two devices, one write). Otherwise the
    key is ``leadId|userId|dispositionId|atMs``.

    ``start`` is inclusive and ``end`` is exclusive, compared in epoch millis.
    """

    start_ms = to_millis(start) if start is not None else None
    end_ms = to_millis(end) if end is not None else None
    wanted = _user_text(user_id) if user_id is not None else ""
    seen: set[str] = set()
    found: list[KnockEvent] = []
    for index, lead in enumerate(leads):
        if not isinstance(lead, dict):
            continue
        prepared = lead
        if not _lead_id(lead):
            prepared = dict(lead)
            prepared["id"] = f"__row{index}"
        for event in knock_events(prepared, dispositions, seen=seen):
            if wanted and event.user_id != wanted:
                continue
            if start_ms is not None and event.at < start_ms:
                continue
            if end_ms is not None and event.at >= end_ms:
                continue
            found.append(event)
    return found


def count_knocks(
    leads: Iterable[Any],
    dispositions: Any = None,
    *,
    user_id: str | None = None,
    start: Any = None,
    end: Any = None,
) -> int:
    return len(
        collect_knock_events(
            leads,
            dispositions,
            user_id=user_id,
            start=start,
            end=end,
        )
    )


def knocks_by_user(
    leads: Iterable[Any],
    dispositions: Any = None,
    *,
    user_id: str | None = None,
    start: Any = None,
    end: Any = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in collect_knock_events(
        leads,
        dispositions,
        user_id=user_id,
        start=start,
        end=end,
    ):
        counts[event.user_id] = counts.get(event.user_id, 0) + 1
    return counts


def knocks_by_day(
    leads: Iterable[Any],
    dispositions: Any = None,
    *,
    user_id: str | None = None,
    start: Any = None,
    end: Any = None,
) -> dict[str, int]:
    """Bucket by the America/New_York calendar date of the event, not Phoenix."""

    counts: dict[str, int] = {}
    for event in collect_knock_events(
        leads,
        dispositions,
        user_id=user_id,
        start=start,
        end=end,
    ):
        moment = datetime.fromtimestamp(event.at / 1000, tz=timezone.utc).astimezone(REPORTING_TZ)
        day = moment.date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return counts


def raydar_lead_query(collection: Any, start: Any, *, order: bool = False) -> Any:
    """Leads whose latest ``dispositionedAt`` is on or after ``start``.

    Before: ``dispositionedAt >= start AND dispositionedAt < end`` (and, on
    the doors metric, ``order_by dispositionedAt``).

    After: ``dispositionedAt >= start`` on the same single-field index, with
    the same optional ``order_by``. There is no upper bound. A later re-dispo
    moves ``dispositionedAt`` forward, and the earlier knock is still on that
    document. Callers keep the reporting window by filtering event times.

    Windows that already end at "now" read the same documents as before,
    because nothing is dispositioned in the future. A closed window also
    reads leads touched after the window. That is the extra read. It is not
    a collection scan and it does not add a per-lead follow-up: history is
    already on the lead document the old counters streamed.

    Firestore returns the whole document either way, so reading
    ``dispositionHistory[0]`` was already downloading the full array.
    """

    query = collection.where("dispositionedAt", ">=", start)
    if order:
        query = query.order_by("dispositionedAt")
    return query
