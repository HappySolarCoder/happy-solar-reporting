# -*- coding: utf-8 -*-

"""Count Raydar door knocks from visit history.

Evan, 2026-11-03: no disposition ever subtracts a knock. Each
``dispositionHistory`` entry is one knock for ``entry.userId`` at
``entry.timestamp``, except Shade DQ (``shade-dq``), Already Has Solar
(``has-solar`` / ``already-has-solar``), and the non-knock ownership states.
The same rep putting the same disposition on the same lead again within
``REPEAT_KNOCK_GAP_SECONDS`` (120) is still one knock.

The disposition catalog is used only to resolve a name to an id. The gate is
the sets below, not ``countsAsDoorKnock``. Day buckets stay America/New_York.
The Raydar app buckets in device-local time (Phoenix); this module does not.

Counts-only knocks (``fieldKnockEvents``, Raydar PR A): a knock the field API
refused to write to the lead (the pin belonged to someone else) is stored as an
event row instead. :func:`field_event_index` turns mirrored rows into
``KnockEvent`` objects keyed like a history entry without an ``eventId``,
``leadId|userId|dispositionId|atMs``, so a draft that is first counted-only and
later accepted into history counts once. :func:`knock_events` merges a lead's
events into that lead's history before the 120 s collapse (the collapse groups
are per lead, so this equals one union collapse). Events on leads the lead
query did not return come from :func:`orphan_ledger_events`. With no events
(collection absent or empty) every count is exactly what it was.

Only :func:`load_field_event_index` reads Firestore, and it never writes.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
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
# Same rep, same lead, same normalized disposition inside this gap is one knock.
# The anchor is the last kept event. A tap at exactly 120s does not start a new knock.
REPEAT_KNOCK_GAP_SECONDS = 120
REPEAT_KNOCK_GAP_MS = REPEAT_KNOCK_GAP_SECONDS * 1000
# Closed windows still start at dispositionedAt >= start, then stop at
# window end + this many days. A re-dispo later than that is not read, so
# its earlier in-window knock can drop out of that old window.
KNOCK_READ_LOOKAHEAD_DAYS = 45
KNOCK_READ_LOOKAHEAD = timedelta(days=KNOCK_READ_LOOKAHEAD_DAYS)
REPORTING_TZ = ZoneInfo("America/New_York")
# Mirror of the app's fieldKnockEvents (filled by the Raydar Firestore sync).
# A missing or empty collection is a no-op. Override only for tests.
FIELD_KNOCK_EVENTS_COLLECTION = os.environ.get("RAYDAR_FIELD_KNOCK_EVENTS_COLLECTION") or "raydar_field_knock_events_v1"
FIELD_KNOCK_EVENTS_LIMIT = 20000
_LOG = logging.getLogger(__name__)
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


def collapse_repeat_knocks(events: Iterable[KnockEvent]) -> list[KnockEvent]:
    """Drop same-lead, same-rep, same-disposition taps inside ``REPEAT_KNOCK_GAP_MS``.

    Groups are ``leadId|userId|dispositionId``. Each group is sorted by time.
    An event is kept only when it is more than 120 seconds after the last kept
    event in that group. The anchor does not move to a dropped tap.
    """

    groups: dict[tuple[str, str, str], list[KnockEvent]] = {}
    for event in events:
        groups.setdefault((event.lead_id, event.user_id, event.disposition_id), []).append(event)
    kept: list[KnockEvent] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (item.at, item.dedupe_key))
        last_kept_at: int | None = None
        for event in ordered:
            if last_kept_at is not None and event.at - last_kept_at <= REPEAT_KNOCK_GAP_MS:
                continue
            kept.append(event)
            last_kept_at = event.at
    kept.sort(key=lambda item: (item.at, item.lead_id, item.user_id, item.disposition_id, item.dedupe_key))
    return kept


def knock_events(
    lead: dict[str, Any] | None,
    dispositions: Any = None,
    seen: set[str] | None = None,
    *,
    collapse: bool = True,
    ledger: Mapping[str, list[KnockEvent]] | None = None,
) -> list[KnockEvent]:
    """History entries on one lead. ``seen`` dedupes across snapshots and devices.

    Fallback to one event from ``status`` / ``dispositionId`` + ``dispositionedAt``
    only when ``dispositionHistory`` is missing or empty. The actor is then
    ``claimedBy`` or ``assignedTo``. Entries with no user id or no parseable
    time are skipped. A null or non-object history entry is skipped. A
    non-empty history of unusable entries does not fall back.

    After dedupe and exclusions, repeats inside ``REPEAT_KNOCK_GAP_SECONDS``
    collapse to one knock unless ``collapse`` is false. ``collect_knock_events``
    turns collapse off per snapshot and collapses the union once.

    ``ledger`` is the :func:`field_event_index` result. This lead's counts-only
    events are added after its history (history wins a key tie) and then take
    part in the same collapse. ``None`` or no events for the lead changes nothing.
    """

    if not isinstance(lead, dict):
        return []
    bag = seen if seen is not None else set()
    own = ledger.get(_lead_id(lead)) if ledger else None
    if own:
        base = knock_events(lead, dispositions, bag, collapse=False)
        for event in own:
            if event.dedupe_key in bag:
                continue
            bag.add(event.dedupe_key)
            base.append(event)
        return collapse_repeat_knocks(base) if collapse else base
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
    if collapse:
        return collapse_repeat_knocks(events)
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
    key is ``leadId|userId|dispositionId|atMs``. Repeats inside
    ``REPEAT_KNOCK_GAP_SECONDS`` then collapse on the union, anchored on the
    last kept event, before the window filter. A duplicate just inside the
    window does not count when its kept anchor is before the window.

    ``start`` is inclusive and ``end`` is exclusive, compared in epoch millis.
    """

    start_ms = to_millis(start) if start is not None else None
    end_ms = to_millis(end) if end is not None else None
    wanted = _user_text(user_id) if user_id is not None else ""
    seen: set[str] = set()
    raw: list[KnockEvent] = []
    for index, lead in enumerate(leads):
        if not isinstance(lead, dict):
            continue
        prepared = lead
        if not _lead_id(lead):
            prepared = dict(lead)
            prepared["id"] = f"__row{index}"
        raw.extend(knock_events(prepared, dispositions, seen=seen, collapse=False))
    found: list[KnockEvent] = []
    for event in collapse_repeat_knocks(raw):
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


def raydar_lead_query(collection: Any, start: Any, *, end: Any = None, order: bool = False) -> Any:
    """Leads whose latest ``dispositionedAt`` may still hold in-window knocks.

    ``dispositionedAt >= start`` on the same single-field index. When ``end``
    is set, also ``dispositionedAt < end + KNOCK_READ_LOOKAHEAD`` (45 days).
    A re-dispo inside that lookahead still carries the earlier knock. A
    re-dispo more than 45 days after the window is not read, so that knock
    can drop out of the old window. Callers still filter events to
    ``[start, end)``.

    Windows that end at "now" add an upper bound 45 days in the future, so
    they still read the same existing leads. Optional ``order_by`` stays on
    ``dispositionedAt``. No per-lead follow-up: history is already on the
    document.
    """

    query = collection.where("dispositionedAt", ">=", start)
    if end is not None:
        query = query.where("dispositionedAt", "<", end + KNOCK_READ_LOOKAHEAD)
    if order:
        query = query.order_by("dispositionedAt")
    return query


def field_event_index(
    rows: Iterable[Any],
    dispositions: Any = None,
) -> dict[str, list[KnockEvent]]:
    """Mirrored ``fieldKnockEvents`` rows to ``{leadId: [KnockEvent]}``.

    A row is ``{uid, leadId, actionAt, dispositionId | status | disposition}``.
    ``actionAt`` is the draft's original time, never the server time. Rows with
    no rep, lead or parseable time are skipped. Shade DQ, Already Has Solar and
    the non-knock states are dropped here, because these rows do not pass
    through the history exclusions. Duplicate keys collapse to one.
    """

    bag: set[str] = set()  # own dedupe only; history dedupe happens at merge time
    index: dict[str, list[KnockEvent]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        user_id = _user_text(row.get("uid")) or _user_text(row.get("userId"))
        lead_id = _user_text(row.get("leadId"))
        at_ms = to_millis(row.get("actionAt"))
        if not user_id or not lead_id or at_ms is None:
            continue
        raw = row.get("dispositionId")
        if raw in (None, ""):
            raw = row.get("status")
        if raw in (None, ""):
            raw = row.get("disposition")
        if _raw_is_blocked(raw):
            continue
        disposition_id = normalize_dispo_key(raw, dispositions)
        if not is_counted_knock(disposition_id):
            continue
        events: list[KnockEvent] = []
        # Same fallback key a history entry without an eventId gets.
        _append_event(
            events,
            bag,
            lead_id=lead_id,
            user_id=user_id,
            at_ms=at_ms,
            disposition_id=disposition_id,
            event_id="",
        )
        if events:
            index.setdefault(lead_id, []).append(events[0])
    return index


def orphan_ledger_events(
    index: Mapping[str, list[KnockEvent]] | None,
    streamed_lead_ids: set[str],
    seen: set[str],
    *,
    exclude_user_ids: Iterable[str] = (),
) -> list[KnockEvent]:
    """Counts-only events on leads the lead query did not return.

    A refused pin keeps its old ``dispositionedAt``, so its lead is usually
    outside the window's lead read and has no history inside the window. Those
    events are counted here, collapsed per lead. Leads that were streamed already
    merged their events in :func:`knock_events`.
    """

    if not index:
        return []
    skip_users = set(exclude_user_ids)
    out: list[KnockEvent] = []
    for lead_id, events in index.items():
        if lead_id in streamed_lead_ids:
            continue
        fresh = []
        for event in events:
            if event.user_id in skip_users or event.dedupe_key in seen:
                continue
            seen.add(event.dedupe_key)
            fresh.append(event)
        out.extend(collapse_repeat_knocks(fresh))
    out.sort(key=lambda item: (item.at, item.lead_id, item.user_id, item.disposition_id, item.dedupe_key))
    return out


def load_field_event_index(
    db: Any,
    start: Any,
    end: Any,
    dispositions: Any = None,
    *,
    collection: str | None = None,
) -> dict[str, list[KnockEvent]]:
    """Read mirrored events with ``start <= actionAt < end`` and index them.

    One single-field range read, capped at ``FIELD_KNOCK_EVENTS_LIMIT``. An
    absent or empty collection returns ``{}``, so counts are history-only,
    exactly as before the events existed. A failed read also returns ``{}``
    and logs a warning: a broken mirror must never take a dashboard down.
    """

    name = collection or FIELD_KNOCK_EVENTS_COLLECTION
    try:
        query = db.collection(name).where("actionAt", ">=", start)
        if end is not None:
            query = query.where("actionAt", "<", end)
        rows = [snap.to_dict() or {} for snap in query.limit(FIELD_KNOCK_EVENTS_LIMIT).stream()]
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("field knock events not read (%s): %s", name, type(exc).__name__)
        return {}
    if len(rows) >= FIELD_KNOCK_EVENTS_LIMIT:
        _LOG.warning("field knock events hit the %s row cap; counts may be low", FIELD_KNOCK_EVENTS_LIMIT)
    return field_event_index(rows, dispositions)
