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

The warehouse collection is ``ghl_appointment_events_v2``, written by
ghl-firestore-sync-v2 (not by this service). One dateAdded range per window,
cached in process. A zero-row range probes a single document so an empty
collection is not confused with a field mismatch. No full collection stream
and no GoHighLevel writes.
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
APPOINTMENT_COLLECTION = "ghl_appointment_events_v2"
# Happy Solar Booking Hub sales calendar group. Personal, interview, and
# onboarding calendars are not in this group. Empower+ is excluded by id
# even if it is ever attached to the group.
BOOKING_HUB_GROUP_ID = "Blxh1ULhWznbBH5kZQBK"
EXCLUDED_CALENDAR_IDS = frozenset({"fglYHXEMSyXFHyi3BFN4"})
EXCLUDED_CALENDAR_NAME_MARKERS = ("interview", "onboarding", "personal")
DELAYED_CREATE_DAYS = 7

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


def appointment_collection() -> str:
    """The one collection ghl-firestore-sync-v2 writes. Env override optional."""
    override = compact(os.environ.get("GHL_APPOINTMENT_EVENTS_COLLECTION"))
    return override or APPOINTMENT_COLLECTION


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


def calendar_id_of(event: dict | None) -> str:
    if not isinstance(event, dict):
        return ""
    return compact(event.get("calendarId") or event.get("calendar_id"))


def calendar_allowed(event: dict | None) -> bool:
    """True only for the Booking Hub sales group, never Empower+ or personal calendars."""
    if not isinstance(event, dict):
        return False
    if calendar_id_of(event) in EXCLUDED_CALENDAR_IDS:
        return False
    name = compact(event.get("calendarName") or event.get("calendar_name")).casefold()
    if any(marker in name for marker in EXCLUDED_CALENDAR_NAME_MARKERS):
        return False
    group = compact(event.get("calendarGroupId") or event.get("groupId"))
    return group == BOOKING_HUB_GROUP_ID


def stage_key(name: Any) -> str:
    text = compact(name).casefold().replace("\u2019", "'").replace("'", "")
    for ch in "/-_":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def is_terminal_stage(name: Any) -> bool:
    """Sold and Sale Cancelled only. Open DQ'd / DQ'ed is not terminal."""
    key = stage_key(name)
    if not key:
        return False
    if key == "sold" or key.startswith("sold "):
        return True
    return key.startswith("sale cancelled") or key.startswith("sale canceled")


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


def probe_appointment_collection(db: Any, name: str) -> dict[str, Any]:
    """One document, not a scan. Separates an empty collection from a bad field.

    ``collection_state=empty`` means limit(1) returned nothing.
    ``field_mismatch`` means a document exists and ``dateAdded`` is missing or blank,
    so a dateAdded range cannot see it.
    ``range_empty`` means the field is present and this window simply has no rows.
    """
    try:
        snaps = list(db.collection(name).limit(1).stream())
    except Exception as exc:
        return {"collection_state": "error", "field_mismatch": None, "error": str(exc)[:200]}
    if not snaps:
        return {"collection_state": "empty", "field_mismatch": False, "range_empty": True}
    data = snaps[0].to_dict() or {}
    if not isinstance(data, dict):
        data = {}
    present = "dateAdded" in data and data.get("dateAdded") not in (None, "")
    return {
        "collection_state": "not_empty",
        "field_mismatch": not present,
        "range_empty": present,
        "dateAdded_present": present,
        "dateAdded_type": type(data.get("dateAdded")).__name__ if "dateAdded" in data else None,
        "sample_id": compact(getattr(snaps[0], "id", "")) or None,
        "sample_fields": sorted(str(key) for key in data.keys())[:40],
    }


def load_booked_appointments(
    db: Any,
    start_local: datetime,
    end_local: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Appointments whose dateAdded falls in [start_local, end_local).

    The range is widened by a calendar day, matching the createdAt query, then
    cut back to America/New_York. Cached per database and window. One collection.
    """
    name = appointment_collection()
    start_bound = start_local.date().isoformat()
    end_bound = (end_local + timedelta(days=1)).date().isoformat()
    key = (_db_cache_key(db), start_bound, end_bound, name)
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < CACHE_SECONDS and (key[0][0] == "firestore" or hit[1] is db):
        cached = [dict(row) for row in hit[2]]
        kept = _window_filter(cached, start_local, end_local)
        debug = dict(hit[3])
        debug["cache"] = "hit"
        debug["appointments_in_window"] = len(kept)
        return kept, debug

    errors: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    try:
        rows = _query_date_added(db, name, start_bound, end_bound)
    except Exception as exc:
        errors[name] = str(exc)[:200]
    probe: dict[str, Any]
    if rows:
        probe = {"collection_state": "range_matched", "field_mismatch": False, "range_empty": False}
    else:
        probe = probe_appointment_collection(db, name)
    if len(_CACHE) > 32:
        _CACHE.clear()
    debug = {
        "cache": "miss",
        "collection": name,
        "appointments_scanned": len(rows),
        "query_errors": errors,
        "collection_probe": probe,
        "appointments_in_window": 0,
    }
    _CACHE[key] = (now, db if key[0][0] == "object" else None, [dict(row) for row in rows], debug)
    kept = _window_filter(rows, start_local, end_local)
    debug["appointments_in_window"] = len(kept)
    return kept, debug


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
        "calendar_excluded": 0,
        "missing_contact": 0,
        "same_day_opportunity": 0,
        "duplicate_same_day": 0,
    }
    chosen: dict[tuple[str, date], dict[str, Any]] = {}
    for event in events:
        if not calendar_allowed(event):
            stats["calendar_excluded"] += 1
            continue
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


def _et_date(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(NY).date()


def has_earlier_appointment(opp: dict, booking: datetime) -> bool:
    """The open opportunity already existed, or already carried an appointment."""
    created = opportunity_created_moment(opp)
    if created is not None and _et_date(created) < _et_date(booking):
        return True
    for key in ("appointmentEventId", "appointmentStartTime", "appointmentScheduledAtCanonical", "appointmentOccurredAt"):
        if opp.get(key) not in (None, ""):
            return True
    return False


def rebook_decision(
    opportunities: Iterable[dict[str, Any]],
    pipeline_name: Callable[[Any], str],
    stage_name: Callable[[dict[str, Any]], str],
    booking: datetime,
) -> tuple[str, dict[str, Any] | None]:
    """Whether this booking is a true rebook onto a closed regional opportunity.

    Credit only when every regional opportunity is terminal (Sold or Sale
    Cancelled). An open DQ'd stage is not terminal. An in-scope regional
    opportunity created within 7 days after the booking is the set itself,
    so the booking is not a second credit. A still-active regional
    opportunity, including one that already had an earlier appointment, is
    not a rebook.
    """
    regional = [
        opp
        for opp in opportunities
        if isinstance(opp, dict) and is_regional_pipeline(pipeline_name(opp.get("pipelineId")))
    ]
    if not regional:
        return "no_regional", None
    booking_day = _et_date(booking)
    for opp in regional:
        created = opportunity_created_moment(opp)
        if created is None:
            continue
        created_day = _et_date(created)
        if created_day == booking_day:
            return "same_day_opportunity", None
        if 0 < (created_day - booking_day).days <= DELAYED_CREATE_DAYS:
            return "created_within_7_days", None
    open_opps = [opp for opp in regional if not is_terminal_stage(stage_name(opp))]
    if open_opps:
        if any(has_earlier_appointment(opp, booking) for opp in open_opps):
            return "open_opp_earlier_appointment", None
        return "open_regional_opp", None
    return "credit", pick_most_recent_regional(regional, pipeline_name)


def load_stage_names(db: Any, pipeline_ids: Iterable[Any]) -> dict[str, str]:
    """Stage id -> name from the pipeline docs already needed for those opportunities."""
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in pipeline_ids:
        pid = compact(raw)
        if pid and pid not in seen:
            seen.add(pid)
            wanted.append(pid)
    names: dict[str, str] = {}
    if not wanted:
        return names
    refs = [db.collection("ghl_pipelines_v2").document(pid) for pid in wanted]
    for snap in db.get_all(refs):
        if not getattr(snap, "exists", False):
            continue
        data = snap.to_dict() or {}
        for stage in data.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            sid = compact(stage.get("id"))
            sname = compact(stage.get("name"))
            if sid and sname:
                names[sid] = sname
    return names


def stage_name_of(opp: dict, stage_names: dict[str, str]) -> str:
    for key in ("pipelineStageName", "stageName", "stage"):
        text = compact(opp.get(key))
        if text:
            return text
    sid = compact(opp.get("pipelineStageId") or opp.get("pipelineStageUId"))
    return stage_names.get(sid, "")


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
