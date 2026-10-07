# -*- coding: utf-8 -*-

"""Whether a passed appointment still belongs on Missing Dispositions.

An appointment stays on the list only while it is undispositioned. It drops
off when any opportunity for that appointment has moved past the
appointment-set stage or has an appointment outcome set. Sweeper and Rehash
duplicates count: the list must not keep a stale "New Appointment"
opportunity after the same appointment was dispositioned on another one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

# Territory pipelines plus the duplicate pipelines a dispositioned appointment
# is moved into. Lead-locker stages are not appointment dispositions.
SALES_PIPELINES = frozenset({
    "buffalo",
    "rochester",
    "syracuse",
    "virtual",
    "rehash",
    "sweeper",
})

# Substrings of a normalized stage name. "negotiating" covers
# "Demo-Negotiating", "Demo - Negotiating", and "Negotiating".
_POST_APPOINTMENT_MARKERS = (
    "negotiating",
    "demo not interested",
    "one legger",
    "no show",
    "pre cancel",
    "reschedule",
    "re set",
    "reset",
    "closing notes",
    "rehash",
    "sweeper",
    "not interested",
    "non responsive",
    "nonresponsive",
    "do not contact",
    "sale cancel",
    "cancelled",
    "canceled",
)

_EMPTY_OUTCOMES = frozenset({"", "none", "null", "n/a", "na", "undefined"})


def normalize_stage_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    for ch in ("-", "_", "/", "\\"):
        text = text.replace(ch, " ")
    for ch in ("'", "\u2019", "\u2018"):
        text = text.replace(ch, "")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def normalize_pipeline_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_new_appointment_stage(stage_name: Any) -> bool:
    return normalize_stage_name(stage_name) == "new appointment"


def is_post_appointment_stage(stage_name: Any) -> bool:
    """True for stages past appointment-set (demo negotiating, sold, no show, ...)."""
    name = normalize_stage_name(stage_name)
    if not name or name == "new appointment":
        return False
    if name in {"sold", "dq", "dqed", "dqd", "reset"}:
        return True
    if name.startswith("dq ") or name.startswith("sold "):
        return True
    return any(marker in name for marker in _POST_APPOINTMENT_MARKERS)


def has_appointment_outcome(value: Any) -> bool:
    text = " ".join(str(value or "").strip().split())
    return text.lower() not in _EMPTY_OUTCOMES


def opportunity_is_dispositioned(stage_name: Any, disposition_value: Any) -> bool:
    if has_appointment_outcome(disposition_value):
        return True
    return is_post_appointment_stage(stage_name)


def appointment_start_minute(value: Any, tz_name: str = "America/New_York") -> datetime | None:
    """UTC timestamp truncated to the minute, for duplicate-appointment matching."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)

    text = str(value).strip()
    if not text or text.lower() in _EMPTY_OUTCOMES:
        return None

    dt: datetime | None = None
    try:
        iso = text.replace("Z", "+00:00") if text.endswith("Z") else text
        dt = datetime.fromisoformat(iso)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = datetime.strptime(text, "%A, %B %d, %Y %I:%M %p").replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)


def shares_appointment(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Same appointment, including a Sweeper/Rehash duplicate of it.

    Matching appointment event ids always count. The same contact and start
    time counts when the other opportunity is on a sales, Sweeper, or Rehash
    pipeline. A lead-locker opportunity that merely copied the contact's
    appointment time does not disposition a different pipeline's appointment.
    """
    left_id = str(left.get("opportunity_id") or "").strip()
    right_id = str(right.get("opportunity_id") or "").strip()
    if left_id and right_id and left_id == right_id:
        return True

    left_event = str(left.get("appointment_event_id") or "").strip()
    right_event = str(right.get("appointment_event_id") or "").strip()
    if left_event and right_event and left_event == right_event:
        return True

    left_contact = str(left.get("contact_id") or "").strip()
    right_contact = str(right.get("contact_id") or "").strip()
    left_start = left.get("appointment_start")
    right_start = right.get("appointment_start")
    if not (left_contact and left_contact == right_contact and left_start and right_start and left_start == right_start):
        return False
    return normalize_pipeline_name(right.get("pipeline_name")) in SALES_PIPELINES


def appointment_is_missing(candidate: Mapping[str, Any], related: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> bool:
    """True when the candidate should stay on Missing Dispositions.

    ``related`` is every opportunity for the contact (the candidate may be
    included). The appointment drops off when any shared opportunity is in a
    post-appointment stage or has an appointment outcome.
    """
    group = [candidate, *related]
    for opp in group:
        if not shares_appointment(candidate, opp):
            continue
        if opportunity_is_dispositioned(opp.get("stage_name"), opp.get("disposition_value")):
            return False
    return True
