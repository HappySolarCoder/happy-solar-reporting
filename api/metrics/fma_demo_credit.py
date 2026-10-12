# -*- coding: utf-8 -*-

"""One FMA demo per contact.

An FMA gets one demo per contact. The demo date is the appointment the
delayed-dispo buffer assigns to that disposition. The buffer is 3 days,
the same window the sync uses.

The first disposition takes the real calendar appointment within 3 days
before it, including when the rep dispositions late. Every disposition
after the first — the second, third, fourth, and each one after that —
uses the same later-dispo rule: an unused real appointment in that
window, or an estimated appointment at the disposition time when none
is left. One real appointment is never assigned to two dispositions.

Appointments come from ``ghl_appointments_history_v1`` (contactId, start
time). That collection fills going forward and may be empty. An empty
result falls back to the opportunity's appointmentStartTime and
appointmentOccurredAt, then to the disposition time.

Rows with ``source`` ``inferred_from_dispo`` are the estimated
appointments the sync writes when a later disposition has no unused real
calendar appointment. Their start time is the disposition timestamp.
They count as appointments ran. They do not add an FMA demo, and they
are not a second real appointment a later disposition can claim. Closer
and opportunity metrics may still count each appointment or disposition.

A second demo on the same contact counts only when Sweeper/Rehash Last
Name is that FMA's own last name and a later demo disposition is at or
after the sweep. A sweep or rehash by someone else, including a duplicate
opportunity created from a reset, does not add a demo.

Ran and created counts stay on ``attributed_last_name``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sit_timestamp import as_aware_utc
from sweeper_rehash_attribution import compact_text, is_blank_last_name

HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
APPOINTMENT_HISTORY_COLLECTION = "ghl_appointments_history_v1"
INFERRED_APPOINTMENT_SOURCE = "inferred_from_dispo"
OPPORTUNITY_COLLECTION = "ghl_opportunities_v2"
SWEEP_PIPELINES = frozenset({"sweeper", "rehash"})
APPOINTMENT_LOOKBACK = timedelta(days=3)
# Same dispo list and exclusions as ghl-firestore-sync-v2's delayed-dispo buffer.
_BUFFER_DISPO_PHRASES = (
    "rescheduled",
    "needs reschedule",
    "reschedule needed",
    "demo",
    "sit",
    "sold",
    "no sit",
    "no show",
    "sale cancelled",
    "sale canceled",
    "one legger",
)
_HOUSEKEEPING_STAGES = frozenset({"new appointment", "new lead", "dq"})
_EXCLUDED_DISPO_PIPELINES = (
    "sweeper",
    "rehash",
    "inbound lead locker",
    "lead locker",
    "recruiting",
)
_SKIPPED_APPOINTMENT_STATUSES = frozenset(
    {"cancelled", "canceled", "invalid", "noshow", "no show", "no-show"}
)


@dataclass(frozen=True)
class FmaDemo:
    """One demo that counts for an FMA.

    ``counted_at`` is the instant dashboards use for the demo's day.
    ``date_source`` is ``appointment_history``, ``opportunity_appointment``,
    or ``dispo``.
    """

    contact_id: str
    opportunity_id: str
    last_name: str
    reason: str
    dispo_at: datetime
    counted_at: datetime
    date_source: str


def normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def is_sweep_pipeline(value: Any) -> bool:
    return normalize_label(value) in SWEEP_PIPELINES


def is_sweep_stage(value: Any) -> bool:
    name = normalize_label(value)
    if not name:
        return False
    return name in SWEEP_PIPELINES or name.startswith("sweeper ") or name.startswith("rehash ")


def is_demo_stage(value: Any) -> bool:
    """Demo-* stage, One Legger, or Sold. Sale cancelled is not a demo."""
    name = normalize_label(value)
    if not name:
        return False
    if name.startswith("demo"):
        return True
    if name == "one legger":
        return True
    return name == "sold" or name.startswith("sold ")


def names_match(setter: Any, sweeper: Any) -> bool:
    left = compact_text(setter)
    right = compact_text(sweeper)
    if not left or not right or is_blank_last_name(right):
        return False
    return left.casefold() == right.casefold()


def _event_time(row: dict) -> datetime | None:
    return as_aware_utc(row.get("effectiveAt")) or as_aware_utc(row.get("opportunityUpdatedAt"))


def _just_before(moment: datetime) -> datetime:
    return moment - timedelta(microseconds=1)


def _coerce_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000.0
        if raw > 1_000_000_000:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        return None
    return as_aware_utc(value)


def _history_marks(history: list[dict] | None) -> tuple[list[datetime], list[datetime], list[datetime]]:
    """City-demo times, sweeper-demo times, and sweep/rehash times."""
    rows = [row for row in (history or []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _event_time(row) or datetime.max.replace(tzinfo=timezone.utc))
    city_demos: list[datetime] = []
    sweep_demos: list[datetime] = []
    sweeps: list[datetime] = []
    for index, row in enumerate(rows):
        moment = _event_time(row)
        if moment is None:
            continue
        pipeline = row.get("pipelineName")
        to_stage = row.get("toStageName")
        from_stage = row.get("fromStageName")
        on_sweep = is_sweep_pipeline(pipeline) or is_sweep_stage(to_stage)
        if on_sweep:
            sweeps.append(moment)
        if is_demo_stage(to_stage):
            if on_sweep:
                sweep_demos.append(moment)
            else:
                city_demos.append(moment)
        if is_demo_stage(from_stage):
            previous = rows[index - 1] if index else None
            previous_pipeline = previous.get("pipelineName") if isinstance(previous, dict) else None
            came_from_city = previous_pipeline is not None and not is_sweep_pipeline(previous_pipeline)
            entered_sweep = on_sweep and (previous is None or came_from_city)
            if came_from_city or entered_sweep or not on_sweep:
                city_demos.append(_just_before(moment))
            else:
                sweep_demos.append(_just_before(moment))
    return city_demos, sweep_demos, sweeps


def dispo_timestamp(history: list[dict] | None, opportunity: dict | None, stage_name: Any = "") -> datetime | None:
    """When this opportunity was dispositioned as a demo.

    Stage history ``effectiveAt`` wins. The current demo stage's
    ``lastStageChangeAt`` is next, then ``dispositionDate``.
    """
    times: list[datetime] = []
    for row in history or []:
        if not isinstance(row, dict) or not is_demo_stage(row.get("toStageName")):
            continue
        moment = _event_time(row)
        if moment is not None:
            times.append(moment)
    if times:
        return min(times)
    opp = opportunity or {}
    if is_demo_stage(stage_name):
        changed = as_aware_utc(opp.get("lastStageChangeAt"))
        if changed is not None:
            return changed
    return as_aware_utc(opp.get("dispositionDate")) or as_aware_utc(opp.get("appointmentOccurredAt"))


def is_inferred_appointment(row: dict | None) -> bool:
    """True for a re-dispo the sync stored without a new GHL calendar event."""
    if not isinstance(row, dict):
        return False
    return normalize_label(row.get("source")) == normalize_label(INFERRED_APPOINTMENT_SOURCE)


def _deleted_appointment(row: dict) -> bool:
    for key in ("deleted", "isDeleted", "is_deleted"):
        value = row.get(key)
        if value in (True, 1):
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
            return True
    return False


def _skipped_appointment(row: dict) -> bool:
    if _deleted_appointment(row):
        return True
    for key in ("appointmentStatus", "status", "appStatus"):
        label = normalize_label(row.get(key))
        if label in _SKIPPED_APPOINTMENT_STATUSES:
            return True
    return False


def _appointment_moment(row: dict) -> datetime | None:
    keys = (
        "startTime",
        "startTimeMs",
        "appointmentStartTime",
        "startAt",
        "start",
        "scheduledAt",
        "appointmentTime",
    )
    if is_inferred_appointment(row):
        keys = keys + ("dispositionDate", "effectiveAt", "occurredAt")
    for key in keys:
        moment = _coerce_time(row.get(key))
        if moment is not None:
            return moment
    return None


def appointment_outcome(row: dict | None) -> str:
    """Sit or No Sit when the history row says which. Blank when it does not."""
    if not isinstance(row, dict):
        return ""
    for key in ("dispositionValue", "outcome", "whatHappened", "disposition", "appointmentStatus", "status"):
        label = normalize_label(row.get(key))
        if label == "sit":
            return "Sit"
        if label == "no sit":
            return "No Sit"
    return ""


def appointment_instants(rows: list[dict] | None) -> list[datetime]:
    """Start times from appointment-history documents.

    ``inferred_from_dispo`` rows are included. Cancelled, no-show, and
    deleted rows are not.
    """
    found: list[datetime] = []
    seen: set[datetime] = set()
    for row in rows or []:
        if not isinstance(row, dict) or _skipped_appointment(row):
            continue
        moment = _appointment_moment(row)
        if moment is None or moment in seen:
            continue
        seen.add(moment)
        found.append(moment)
    return found


@dataclass(frozen=True)
class InferredAppointment:
    """One re-dispo that counts as an appointment ran, not as an extra FMA demo."""

    contact_id: str
    opportunity_id: str
    start_at: datetime
    outcome: str
    source: str


def inferred_appointments(rows: list[dict] | None) -> list[InferredAppointment]:
    """Inferred re-dispos that count as appointments ran.

    A missing start time, a deleted row, or a cancelled row is omitted.
    Callers still apply the one-demo-per-contact rule separately.
    """
    found: list[InferredAppointment] = []
    seen: set[tuple[str, str, datetime]] = set()
    for row in rows or []:
        if not isinstance(row, dict) or not is_inferred_appointment(row) or _skipped_appointment(row):
            continue
        moment = _appointment_moment(row)
        if moment is None:
            continue
        contact_id = compact_text(row.get("contactId"))
        opportunity_id = compact_text(row.get("opportunityId") or row.get("opportunity_id"))
        key = (contact_id, opportunity_id, moment)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            InferredAppointment(
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                start_at=moment,
                outcome=appointment_outcome(row),
                source=INFERRED_APPOINTMENT_SOURCE,
            )
        )
    return found


def same_appointment_instant(left: datetime | None, right: datetime | None) -> bool:
    """True when two timestamps are the same appointment, within one second."""
    if left is None or right is None:
        return False
    return abs((left - right).total_seconds()) < 1


def _phrase_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    for char in "-_/":
        text = text.replace(char, " ")
    return " ".join(text.split())


def _phrase_match(configured: Any, actual: Any) -> bool:
    """Whole-word phrase match. Demo matches Demo-Negotiating. Sit does not match Rescheduled."""
    needle = _phrase_label(configured)
    hay = _phrase_label(actual)
    if not needle or not hay:
        return False
    return f" {needle} " in f" {hay} "


def is_buffer_dispo_stage(stage_name: Any, pipeline_name: Any = "") -> bool:
    """True for a disposition the 3-day buffer assigns to an appointment.

    Matches the sync: Demo, Sit, No Sit, Sold, Rescheduled, No Show, and the
    rest of that list. New Appointment, DQ, and Sweeper/Rehash pipelines are
    not dispositions.
    """
    name = _phrase_label(stage_name)
    if not name or name in _HOUSEKEEPING_STAGES:
        return False
    pipeline = _phrase_label(pipeline_name)
    padded = f" {pipeline} "
    if any(f" {phrase} " in padded for phrase in _EXCLUDED_DISPO_PIPELINES):
        return False
    return any(_phrase_match(phrase, stage_name) for phrase in _BUFFER_DISPO_PHRASES)


def buffer_dispo_time(row: dict) -> datetime | None:
    """Sync dispo stamp: GHL lastStageChangeAt, otherwise effectiveAt."""
    return (
        _coerce_time(row.get("lastStageChangeAt"))
        or _coerce_time(row.get("effectiveAt"))
        or _coerce_time(row.get("opportunityUpdatedAt"))
    )


def buffer_dispo_times(history: list[dict] | None) -> list[datetime]:
    """Disposition instants on this opportunity, oldest first."""
    found: list[datetime] = []
    for row in history or []:
        if not isinstance(row, dict):
            continue
        change = compact_text(row.get("changeType") or "stage_transition")
        if change != "stage_transition":
            continue
        if not is_buffer_dispo_stage(row.get("toStageName"), row.get("pipelineName")):
            continue
        moment = buffer_dispo_time(row)
        if moment is not None:
            found.append(moment)
    found.sort()
    return found


def demo_buffer_time(history: list[dict] | None, dispo_at: datetime) -> datetime:
    """Buffer stamp of the earliest demo-stage disposition, else ``dispo_at``."""
    times: list[datetime] = []
    for row in history or []:
        if not isinstance(row, dict) or not is_demo_stage(row.get("toStageName")):
            continue
        if not is_buffer_dispo_stage(row.get("toStageName"), row.get("pipelineName")):
            continue
        moment = buffer_dispo_time(row)
        if moment is not None:
            times.append(moment)
    return min(times) if times else dispo_at


def _estimated_appointment(row: dict) -> bool:
    if is_inferred_appointment(row):
        return True
    value = row.get("estimated")
    if value in (True, 1):
        return True
    if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
        return True
    return False


def real_calendar_appointments(rows: list[dict] | None) -> list[tuple[str, datetime]]:
    """GHL calendar events. Inferred and cancelled rows are not real appointments."""
    found: list[tuple[str, datetime]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict) or _skipped_appointment(row) or _estimated_appointment(row):
            continue
        moment = _appointment_moment(row)
        if moment is None:
            continue
        key = compact_text(row.get("eventId") or row.get("id") or row.get("_docId"))
        if not key:
            key = f"anon:{moment.isoformat()}:{index}"
        if key in seen:
            continue
        seen.add(key)
        found.append((key, moment))
    return found


def _opportunity_appointment_keys(opportunity: dict | None) -> list[tuple[str, datetime]]:
    found: list[tuple[str, datetime]] = []
    seen: set[datetime] = set()
    for moment in opportunity_appointment_instants(opportunity):
        if moment in seen:
            continue
        seen.add(moment)
        found.append((f"opp:{moment.isoformat()}", moment))
    return found


def map_dispo_appointments(
    dispos: list[datetime],
    appointments: list[tuple[str, datetime]],
) -> list[tuple[datetime, datetime, bool]]:
    """Map each disposition to one appointment time.

    Oldest first. The first disposition and every disposition after it use
    this same rule, including the second, third, and fourth. Each takes the
    latest unused real appointment whose start is inside the 3 days up to
    and including the disposition. A disposition with none left is dated at
    its own time. The bool is true when a real appointment was used. Each
    real appointment is used once.
    """
    assigned: set[str] = set()
    mapped: list[tuple[datetime, datetime, bool]] = []
    for dispo_at in sorted(moment for moment in dispos if isinstance(moment, datetime)):
        window_start = dispo_at - APPOINTMENT_LOOKBACK
        chosen_key = ""
        chosen_start: datetime | None = None
        for key, start in appointments:
            if key in assigned or not isinstance(start, datetime):
                continue
            if start < window_start or start > dispo_at:
                continue
            if chosen_start is None or start >= chosen_start:
                chosen_key = key
                chosen_start = start
        if chosen_start is not None:
            assigned.add(chosen_key)
            mapped.append((dispo_at, chosen_start, True))
        else:
            mapped.append((dispo_at, dispo_at, False))
    return mapped


def _dedupe_times(moments: list[datetime]) -> list[datetime]:
    found: list[datetime] = []
    for moment in sorted(item for item in moments if isinstance(item, datetime)):
        if any(same_appointment_instant(moment, existing) for existing in found):
            continue
        found.append(moment)
    return found


def opportunity_appointment_instants(opportunity: dict | None) -> list[datetime]:
    """Fallback appointments already stored on the opportunity."""
    opp = opportunity or {}
    found: list[datetime] = []
    seen: set[datetime] = set()
    for key in ("appointmentStartTime", "appointmentOccurredAt", "appointmentScheduledAtCanonical"):
        moment = as_aware_utc(opp.get(key))
        if moment is None or moment in seen:
            continue
        seen.add(moment)
        found.append(moment)
    return found


def resolve_appointment_instants(
    history_rows: list[dict] | None,
    opportunity: dict | None,
) -> tuple[list[datetime], str]:
    """History table first. Opportunity fields when that table has nothing."""
    from_history = appointment_instants(history_rows)
    if from_history:
        return from_history, "appointment_history"
    from_opp = opportunity_appointment_instants(opportunity)
    if from_opp:
        return from_opp, "opportunity_appointment"
    return [], "dispo"


def counted_demo_time(
    dispo_at: datetime,
    appointment_times: list[datetime],
    inferred_times: list[datetime] | None = None,
    prior_dispos: list[datetime] | None = None,
) -> tuple[datetime, bool]:
    """Date of the appointment assigned to this disposition.

    Earlier dispositions claim real appointments first. This disposition
    then takes the latest unused real appointment in the 3-day buffer, or
    its own time when none remains. Inferred times are not real appointments.

    The bool is true when a real appointment was used.
    """
    inferred = [moment for moment in (inferred_times or []) if isinstance(moment, datetime)]
    real = [
        moment
        for moment in appointment_times
        if isinstance(moment, datetime) and not any(same_appointment_instant(moment, item) for item in inferred)
    ]
    dispos = list(prior_dispos or [])
    if not any(same_appointment_instant(dispo_at, item) for item in dispos):
        dispos.append(dispo_at)
    appointments = [(f"t:{moment.isoformat()}:{index}", moment) for index, moment in enumerate(real)]
    for dispo, counted_at, used_real in map_dispo_appointments(dispos, appointments):
        if same_appointment_instant(dispo, dispo_at):
            return counted_at, used_real
    return dispo_at, False


def _city_demo_times(candidate: dict) -> list[datetime]:
    city, _, _ = _history_marks(candidate.get("history"))
    stage = candidate.get("stage_name")
    changed = as_aware_utc(candidate.get("stage_changed_at"))
    on_sweep = is_sweep_pipeline(candidate.get("pipeline_name")) or is_sweep_stage(stage)
    if is_demo_stage(stage) and changed is not None and not on_sweep:
        city.append(changed)
    return city


def contact_sweep_time(candidates: list[dict]) -> datetime | None:
    """Earliest sweep/rehash time across this contact's demo opportunities."""
    moments: list[datetime] = []
    for candidate in candidates:
        _, _, sweeps = _history_marks(candidate.get("history"))
        moments.extend(sweeps)
        history = candidate.get("history") or []
        on_sweep = is_sweep_pipeline(candidate.get("pipeline_name")) or is_sweep_stage(candidate.get("stage_name"))
        if history or not on_sweep:
            continue
        created = as_aware_utc(candidate.get("created_at")) or as_aware_utc(candidate.get("stage_changed_at"))
        if created is not None:
            moments.append(created)
    return min(moments) if moments else None


def demo_is_original(candidate: dict, sweep_at: datetime | None) -> bool:
    """True when this sit is the city appointment from before a sweep."""
    on_sweep = is_sweep_pipeline(candidate.get("pipeline_name")) or is_sweep_stage(candidate.get("stage_name"))
    city = _city_demo_times(candidate)
    earliest_city = min(city) if city else None
    if earliest_city is not None and (sweep_at is None or earliest_city < sweep_at):
        return True
    if sweep_at is None and not on_sweep:
        return True
    return False


def _blank(value: Any) -> bool:
    return not compact_text(value) or is_blank_last_name(value)


def _candidate_dispos(candidate: dict) -> list[datetime]:
    stored = candidate.get("dispos")
    if isinstance(stored, list) and stored:
        return [moment for moment in stored if isinstance(moment, datetime)]
    found = buffer_dispo_times(candidate.get("history"))
    dispo_at = candidate.get("demo_buffer_at")
    if not isinstance(dispo_at, datetime):
        dispo_at = candidate.get("dispo_at")
    if isinstance(dispo_at, datetime) and not any(same_appointment_instant(dispo_at, item) for item in found):
        found.append(dispo_at)
    return found


def _candidate_real_appointments(candidate: dict) -> tuple[list[tuple[str, datetime]], str]:
    stored = candidate.get("real_appointments")
    source = compact_text(candidate.get("real_source") or candidate.get("appointment_source"))
    if isinstance(stored, list):
        keyed = [
            (str(key), moment)
            for key, moment in stored
            if isinstance(moment, datetime)
        ]
        return keyed, source or "opportunity_appointment"
    inferred = [moment for moment in (candidate.get("inferred_times") or []) if isinstance(moment, datetime)]
    times = [
        moment
        for moment in (candidate.get("appointment_times") or [])
        if isinstance(moment, datetime) and not any(same_appointment_instant(moment, item) for item in inferred)
    ]
    keyed = [(f"t:{moment.isoformat()}:{index}", moment) for index, moment in enumerate(times)]
    return keyed, source or "opportunity_appointment"


def _group_dispo_map(group: list[dict]) -> tuple[list[tuple[datetime, datetime, bool]], str]:
    """Contact-level assignment. One real appointment is used for one disposition."""
    history_rows: list[tuple[str, datetime]] = []
    opportunity_rows: list[tuple[str, datetime]] = []
    dispos: list[datetime] = []
    for candidate in group:
        keyed, source = _candidate_real_appointments(candidate)
        if source == "appointment_history" and keyed:
            history_rows.extend(keyed)
        else:
            opportunity_rows.extend(keyed)
        dispos.extend(_candidate_dispos(candidate))
    chosen = history_rows or opportunity_rows
    unique: list[tuple[str, datetime]] = []
    seen: set[str] = set()
    for key, moment in chosen:
        if key in seen:
            continue
        seen.add(key)
        unique.append((key, moment))
    real_source = "appointment_history" if history_rows else ("opportunity_appointment" if opportunity_rows else "dispo")
    return map_dispo_appointments(_dedupe_times(dispos), unique), real_source


def select_fma_demos(candidates: list[dict] | None) -> list[FmaDemo]:
    """Demos that count. One per FMA per contact, plus a self-sweep follow-up.

    Each candidate needs contact_id, opportunity_id, setter, sweeper,
    pipeline_name, and dispo_at. history, dispos, real_appointments, and
    inferred_times are optional. The counted day is the appointment the
    3-day buffer assigns to that disposition.
    """
    grouped: dict[str, list[dict]] = {}
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        dispo_at = candidate.get("dispo_at")
        if not isinstance(dispo_at, datetime):
            continue
        contact_id = compact_text(candidate.get("contact_id"))
        opportunity_id = compact_text(candidate.get("opportunity_id")) or contact_id
        key = contact_id or f"opp:{opportunity_id}"
        grouped.setdefault(key, []).append(candidate)

    selected: list[FmaDemo] = []
    for group in grouped.values():
        group.sort(key=lambda row: (row["dispo_at"], compact_text(row.get("opportunity_id"))))
        mapping, real_source = _group_dispo_map(group)
        sweep_at = contact_sweep_time(group)
        primary = ""
        for candidate in group:
            setter = compact_text(candidate.get("setter"))
            sweeper = compact_text(candidate.get("sweeper"))
            original = demo_is_original(candidate, sweep_at)
            if not primary:
                if original or _blank(sweeper) or names_match(setter, sweeper):
                    credit_name = setter
                    reason = "original"
                else:
                    credit_name = sweeper
                    reason = "after_sweep"
                primary = credit_name
            elif (
                not _blank(sweeper)
                and names_match(sweeper, primary)
                and sweep_at is not None
                and candidate["dispo_at"] >= sweep_at
            ):
                credit_name = sweeper
                reason = "self_sweep"
            else:
                continue
            lookup_at = candidate.get("demo_buffer_at")
            if not isinstance(lookup_at, datetime):
                lookup_at = candidate["dispo_at"]
            matched = next(
                (item for item in mapping if same_appointment_instant(item[0], lookup_at)),
                None,
            )
            if matched is None:
                counted_at, used_appointment = lookup_at, False
            else:
                _, counted_at, used_appointment = matched
            inferred_times = [
                moment for moment in (candidate.get("inferred_times") or []) if isinstance(moment, datetime)
            ]
            if used_appointment:
                date_source = real_source if real_source in {"appointment_history", "opportunity_appointment"} else "opportunity_appointment"
            elif any(same_appointment_instant(counted_at, moment) for moment in inferred_times):
                date_source = "appointment_history"
            else:
                date_source = "dispo"
            selected.append(
                FmaDemo(
                    contact_id=compact_text(candidate.get("contact_id")),
                    opportunity_id=compact_text(candidate.get("opportunity_id")),
                    last_name=credit_name,
                    reason=reason,
                    dispo_at=candidate["dispo_at"],
                    counted_at=counted_at,
                    date_source=date_source,
                )
            )
    return selected


def make_demo_candidate(
    opportunity: dict | None,
    *,
    contact_id: Any,
    opportunity_id: Any,
    setter: Any,
    sweeper: Any,
    pipeline_name: Any,
    stage_name: Any = "",
    history: list[dict] | None = None,
    appointment_rows: list[dict] | None = None,
) -> dict | None:
    """One Sit opportunity prepared for ``select_fma_demos``. None without a dispo time."""
    opp = opportunity or {}
    dispo_at = dispo_timestamp(history, opp, stage_name)
    if dispo_at is None:
        return None
    times, source = resolve_appointment_instants(appointment_rows, opp)
    inferred_times = [item.start_at for item in inferred_appointments(appointment_rows)]
    real_appointments = real_calendar_appointments(appointment_rows)
    if real_appointments:
        real_source = "appointment_history"
    else:
        real_appointments = _opportunity_appointment_keys(opp)
        real_source = "opportunity_appointment" if real_appointments else "dispo"
    dispos = buffer_dispo_times(history)
    buffer_at = demo_buffer_time(history, dispo_at)
    if not any(same_appointment_instant(buffer_at, moment) for moment in dispos):
        dispos.append(buffer_at)
    return {
        "contact_id": compact_text(contact_id),
        "opportunity_id": compact_text(opportunity_id),
        "setter": setter,
        "sweeper": sweeper,
        "pipeline_name": pipeline_name,
        "stage_name": stage_name,
        "stage_changed_at": opp.get("lastStageChangeAt"),
        "created_at": opp.get("createdAt"),
        "history": list(history or []),
        "dispo_at": dispo_at,
        "demo_buffer_at": buffer_at,
        "dispos": dispos,
        "appointment_times": times,
        "appointment_source": source,
        "real_appointments": real_appointments,
        "real_source": real_source,
        "inferred_times": inferred_times,
    }


def current_stage_name(opportunity: dict | None, stage_names: dict[str, str] | None) -> str:
    if not isinstance(opportunity, dict):
        return ""
    stage_id = compact_text(opportunity.get("pipelineStageId") or opportunity.get("pipelineStageUId"))
    named = (stage_names or {}).get(stage_id) if stage_id else ""
    if named:
        return named
    for key in ("pipelineStageName", "stageName"):
        text = compact_text(opportunity.get(key))
        if text:
            return text
    return ""


def _safe_collection(db: Any, name: str):
    if db is None or not hasattr(db, "collection"):
        return None
    try:
        return db.collection(name)
    except KeyError:
        return None


def _unique_ids(values) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        oid = compact_text(raw)
        if oid and oid not in seen:
            seen.add(oid)
            ids.append(oid)
    return ids


def load_stage_history(db: Any, opportunity_ids) -> dict[str, list[dict]]:
    """Stage history rows keyed by opportunity id. Empty ids skip the query."""
    ids = _unique_ids(opportunity_ids)
    out: dict[str, list[dict]] = {oid: [] for oid in ids}
    collection = _safe_collection(db, HISTORY_COLLECTION)
    if not ids or collection is None:
        return out
    for start in range(0, len(ids), 30):
        chunk = ids[start : start + 30]
        for snap in collection.where("opportunityId", "in", chunk).stream():
            row = snap.to_dict() or {}
            oid = compact_text(row.get("opportunityId"))
            if oid in out:
                out[oid].append(row)
    for rows in out.values():
        rows.sort(key=lambda row: _event_time(row) or datetime.max.replace(tzinfo=timezone.utc))
    return out


def load_appointment_history(db: Any, contact_ids) -> dict[str, list[dict]]:
    """Appointment history keyed by contact id.

    A missing collection, a test double, or a query error returns empty
    lists so callers fall back to the opportunity appointment fields.
    """
    ids = _unique_ids(contact_ids)
    out: dict[str, list[dict]] = {cid: [] for cid in ids}
    collection = _safe_collection(db, APPOINTMENT_HISTORY_COLLECTION)
    if not ids or collection is None:
        return out
    try:
        for start in range(0, len(ids), 30):
            chunk = ids[start : start + 30]
            for snap in collection.where("contactId", "in", chunk).stream():
                row = snap.to_dict() or {}
                cid = compact_text(row.get("contactId"))
                if cid in out:
                    out[cid].append(row)
    except Exception:
        return {cid: [] for cid in ids}
    return out


def load_inferred_appointments(db: Any, start: datetime, end: datetime) -> list[dict]:
    """Inferred re-dispos whose startTime falls in ``[start, end)``.

    A missing collection, a missing index, or a test double returns an empty
    list. Contact-scoped history is the other way those rows are found.
    """
    collection = _safe_collection(db, APPOINTMENT_HISTORY_COLLECTION)
    if collection is None or start is None or end is None:
        return []
    try:
        query = collection.where("source", "==", INFERRED_APPOINTMENT_SOURCE)
        query = query.where("startTime", ">=", start).where("startTime", "<", end)
        return [snap.to_dict() or {} for snap in query.stream()]
    except Exception:
        return []


def load_opportunities_by_contact(db: Any, contact_ids) -> list[dict]:
    """Every opportunity for these contacts, so a later reset can see the original sit."""
    ids = _unique_ids(contact_ids)
    collection = _safe_collection(db, OPPORTUNITY_COLLECTION)
    if not ids or collection is None:
        return []
    found: list[dict] = []
    for start in range(0, len(ids), 30):
        chunk = ids[start : start + 30]
        for snap in collection.where("contactId", "in", chunk).stream():
            opp = snap.to_dict() or {}
            if not compact_text(opp.get("id")):
                opp["id"] = getattr(snap, "id", "")
            found.append(opp)
    return found


def load_stage_names(db: Any, pipeline_ids) -> dict[str, str]:
    """Stage id to stage name from the pipelines already in this window."""
    ids = _unique_ids(pipeline_ids)
    collection = _safe_collection(db, "ghl_pipelines_v2")
    if not ids or collection is None or not hasattr(db, "get_all"):
        return {}
    out: dict[str, str] = {}
    refs = [collection.document(pid) for pid in ids]
    for start in range(0, len(refs), 300):
        for snap in db.get_all(refs[start : start + 300]):
            if not getattr(snap, "exists", True):
                continue
            data = snap.to_dict() or {}
            for stage in data.get("stages") or []:
                if not isinstance(stage, dict):
                    continue
                sid = compact_text(stage.get("id") or stage.get("uid"))
                name = compact_text(stage.get("name"))
                if sid and name:
                    out[sid] = name
    return out
