# -*- coding: utf-8 -*-
"""Booking-date credits for Opportunities Created.

A Happy Solar Booking Hub set normally creates a regional opportunity
(Buffalo, Syracuse, Rochester, or Virtual) whose createdAt is the booking.
When the contact already has one of those opportunities, the hub does not
create another. The set then exists only as a calendar appointment (and
sometimes an Inbound/Lead Locker opportunity, which this metric excludes),
so a createdAt count misses it.

One countable appointment booked on an America/New_York day, for a contact
with no in-scope opportunity created that same day, counts as one set on
the booking date. It is attributed to that contact's most recent regional
opportunity. A second appointment the same day does not add another credit,
and a regional opportunity created that day already is the credit.

Reads the appointment collections the warehouse and the leads app already
use. One dateAdded range per collection per window, cached in process.
No full collection stream and no GoHighLevel writes.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from cycle_view import base_opp_id

NY = ZoneInfo("America/New_York")
CACHE_SECONDS = 600
_CACHE: dict[tuple, tuple[float, Any, list[dict[str, Any]]]] = {}

REGIONAL_PIPELINES = frozenset({"buffalo", "syracuse", "rochester", "virtual"})

# GHL appointment statuses this reporting stack already treats as not a set.
IGNORED_APPOINTMENT_STATUSES = frozenset({
    "cancelled",
    "canceled",
    "deleted",
    "invalid",
})

_DELETED_FLAGS = ("deleted", "isDeleted", "is_deleted")


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def fold_status(value: Any) -> str:
    text = compact(value).casefold().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def appointment_collections() -> list[str]:
    """Collections already read for calendar appointments. Env override first."""
    names = [
        os.environ.get("GHL_APPOINTMENT_EVENTS_COLLECTION"),
        "ghl_appointment_events_v2",
        "ghl_calendar_events_v2",
        "ghl_appointments_v2",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = compact(raw)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # GHL sometimes sends unix seconds or milliseconds.
        seconds = float(value)
        if seconds > 1e12:
            seconds = seconds / 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.isdigit():
            return as_utc(int(text))
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def booking_moment(event: dict | None) -> datetime | None:
    """When the appointment was booked, not when it is scheduled to start."""
    if not isinstance(event, dict):
        return None
    for key in ("dateAdded", "date_added", "dateCreated", "createdAt"):
        moment = as_utc(event.get(key))
        if moment is not None:
            return moment
    return None


def appointment_status_ignored(event: dict | None) -> bool:
    if not isinstance(event, dict):
        return True
    for key in _DELETED_FLAGS:
        flag = event.get(key)
        if flag is True or fold_status(flag) in {"true", "1", "yes"}:
            return True
    if as_utc(event.get("deletedAt") or event.get("deleted_at")) is not None:
        return True
    for key in ("appointmentStatus", "appoinmentStatus", "status", "appointment_status"):
        status = fold_status(event.get(key))
        if status in IGNORED_APPOINTMENT_STATUSES:
            return True
    return False


def appointment_id(event: dict, fallback: str = "") -> str:
    for key in ("id", "eventId", "appointmentId", "calendarEventId"):
        text = compact(event.get(key))
        if text:
            return text
    return fallback


def contact_id_of(event: dict) -> str:
    for key in ("contactId", "contact_id"):
        text = compact(event.get(key))
        if text:
            return text
    contact = event.get("contact")
    if isinstance(contact, dict):
        return compact(contact.get("id") or contact.get("contactId"))
    return ""


def assignee_id(event: dict) -> str:
    """Calendar user the booking was assigned to. Empty when the event has none."""
    for key in ("assignedUserId", "assignedTo", "userId", "assigned_user_id"):
        text = compact(event.get(key))
        if text:
            return text
    for key in ("assignedUser", "user", "assignedToUser"):
        person = event.get(key)
        if isinstance(person, dict):
            text = compact(person.get("id") or person.get("userId"))
            if text:
                return text
    return ""


def is_regional_pipeline(name: Any) -> bool:
    return compact(name).casefold() in REGIONAL_PIPELINES


def opportunity_created_moment(opp: dict) -> datetime | None:
    return as_utc(opp.get("createdAt")) or as_utc(opp.get("cycleOriginalCreatedAt"))


def booking_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def created_row_identity(row: dict | None) -> str:
    """Distinct key for a created row. Booking credits on two days both count."""
    if not isinstance(row, dict):
        return ""
    oid = compact(row.get("opportunityId"))
    if not oid:
        return ""
    booked = compact(row.get("bookingDate"))
    return f"{oid}|{booked}" if booked else oid


def _db_cache_key(db: Any) -> tuple:
    project, database = getattr(db, "project", None), getattr(db, "_database", None)
    if isinstance(project, str) and project:
        return ("firestore", project, str(database or ""))
    return ("object", id(db))


def _query_range(db: Any, collection: str, start: Any, end: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    query = (
        db.collection(collection)
        .where("dateAdded", ">=", start)
        .where("dateAdded", "<", end)
    )
    for snap in query.stream():
        data = snap.to_dict() or {}
        if isinstance(data, dict):
            data.setdefault("id", snap.id)
            data["_collection"] = collection
            out.append(data)
    return out


def _query_date_added(db: Any, collection: str, start_bound: str, end_bound: str) -> list[dict[str, Any]]:
    """Range query only. A failure must not fall through to a full stream.

    ISO strings are the usual warehouse shape. When that range is empty, one
    timestamp range covers dateAdded stored as a Firestore datetime. A second
    failure returns the empty string result instead of scanning the collection.
    """
    rows = _query_range(db, collection, start_bound, end_bound)
    if rows:
        return rows
    start_dt = datetime.combine(date.fromisoformat(start_bound), datetime.min.time(), tzinfo=NY)
    end_dt = datetime.combine(date.fromisoformat(end_bound), datetime.min.time(), tzinfo=NY)
    try:
        return _query_range(db, collection, start_dt, end_dt)
    except Exception:
        return rows


def load_booked_appointments(
    db: Any,
    start_local: datetime,
    end_local: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Appointments whose dateAdded falls in [start_local, end_local).

    The range is widened by a calendar day, matching the createdAt query, then
    cut back to America/New_York. Cached per database and window.
    """
    start_bound = start_local.date().isoformat()
    end_bound = (end_local + timedelta(days=1)).date().isoformat()
    key = (_db_cache_key(db), start_bound, end_bound, tuple(appointment_collections()))
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < CACHE_SECONDS and (key[0][0] == "firestore" or hit[1] is db):
        cached = [dict(row) for row in hit[2]]
        kept = _window_filter(cached, start_local, end_local)
        return kept, {"cache": "hit", "appointments_in_window": len(kept)}

    scanned = 0
    errors: dict[str, str] = {}
    found: dict[str, dict[str, Any]] = {}
    for name in appointment_collections():
        try:
            rows = _query_date_added(db, name, start_bound, end_bound)
        except Exception as exc:
            errors[name] = str(exc)[:200]
            continue
        scanned += len(rows)
        for row in rows:
            dedupe = appointment_id(row) or f"{name}:{id(row)}"
            found.setdefault(dedupe, row)
    merged = list(found.values())
    if len(_CACHE) > 32:
        _CACHE.clear()
    _CACHE[key] = (now, db if key[0][0] == "object" else None, [dict(row) for row in merged])
    kept = _window_filter(merged, start_local, end_local)
    return kept, {
        "cache": "miss",
        "collections": appointment_collections(),
        "appointments_scanned": scanned,
        "query_errors": errors,
        "appointments_in_window": len(kept),
    }


def _window_filter(rows: list[dict[str, Any]], start_local: datetime, end_local: datetime) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in rows:
        moment = booking_moment(row)
        if moment is None:
            continue
        local = moment.astimezone(start_local.tzinfo or NY)
        if start_local <= local < end_local:
            kept.append(row)
    return kept


def select_daily_bookings(
    events: Iterable[dict[str, Any]],
    counted_contact_days: set[tuple[str, date]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """One countable booking per contact per ET day, earliest time that day.

    ``counted_contact_days`` holds contacts that already have an in-scope
    opportunity created that ET day. Those days are not credited again.
    """
    stats = {
        "ignored_status": 0,
        "missing_contact": 0,
        "same_day_opportunity": 0,
        "duplicate_same_day": 0,
    }
    chosen: dict[tuple[str, date], dict[str, Any]] = {}
    for event in events:
        if appointment_status_ignored(event):
            stats["ignored_status"] += 1
            continue
        cid = contact_id_of(event)
        moment = booking_moment(event)
        if not cid or moment is None:
            stats["missing_contact"] += 1
            continue
        day = moment.astimezone(NY).date()
        if (cid, day) in counted_contact_days:
            stats["same_day_opportunity"] += 1
            continue
        key = (cid, day)
        current = chosen.get(key)
        if current is not None:
            stats["duplicate_same_day"] += 1
            current_moment = booking_moment(current) or moment
            if moment < current_moment:
                if not assignee_id(event) and assignee_id(current):
                    event = dict(event)
                    event["assignedUserId"] = assignee_id(current)
                chosen[key] = event
            elif not assignee_id(current) and assignee_id(event):
                copied = dict(current)
                copied["assignedUserId"] = assignee_id(event)
                chosen[key] = copied
            continue
        chosen[key] = event
    ordered = sorted(chosen.values(), key=lambda ev: (booking_moment(ev) or datetime.min.replace(tzinfo=timezone.utc), appointment_id(ev)))
    return ordered, stats


def load_opportunities_for_contacts(db: Any, contact_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Bounded contactId ``in`` reads. Not a collection scan."""
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        cid = compact(raw)
        if cid and cid not in seen:
            seen.add(cid)
            wanted.append(cid)
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i in range(0, len(wanted), 30):
        chunk = wanted[i : i + 30]
        for snap in db.collection("ghl_opportunities_v2").where("contactId", "in", chunk).stream():
            data = snap.to_dict() or {}
            if not isinstance(data, dict):
                continue
            data.setdefault("id", snap.id)
            oid = compact(data.get("id") or snap.id)
            if oid and oid not in seen_ids:
                seen_ids.add(oid)
                rows.append(data)
    return rows


def pick_most_recent_regional(
    opportunities: Iterable[dict[str, Any]],
    pipeline_name: Callable[[Any], str],
) -> dict[str, Any] | None:
    """Latest Buffalo/Syracuse/Rochester/Virtual opportunity for one contact.

    A live opportunity wins a tie with its frozen cycle copy. Recency uses
    createdAt, then cycleOriginalCreatedAt when a revive cleared createdAt.
    """
    best: dict[str, Any] | None = None
    best_dt: datetime | None = None
    best_live = False
    for opp in opportunities:
        if not isinstance(opp, dict):
            continue
        if not is_regional_pipeline(pipeline_name(opp.get("pipelineId"))):
            continue
        moment = opportunity_created_moment(opp)
        live = "~cycle" not in compact(opp.get("id"))
        if best is None:
            best, best_dt, best_live = opp, moment, live
            continue
        if moment is not None and (best_dt is None or moment > best_dt):
            best, best_dt, best_live = opp, moment, live
            continue
        if moment == best_dt and live and not best_live:
            best, best_dt, best_live = opp, moment, live
    if best is None:
        return None
    real_id = base_opp_id(best.get("id"))
    if real_id and real_id != compact(best.get("id")):
        for opp in opportunities:
            if compact(opp.get("id")) == real_id and is_regional_pipeline(pipeline_name(opp.get("pipelineId"))):
                return opp
        best = dict(best)
        best["id"] = real_id
    return best
