# -*- coding: utf-8 -*-

"""One FMA demo per contact.

An FMA gets one demo per contact. The demo is dated to the nearest past
appointment within 3 days before the disposition. The disposition time is
the stage-history ``effectiveAt`` when the opportunity entered a Demo-*
stage, One Legger, or Sold. If no appointment falls in that window, the
demo uses the disposition time.

Appointments come from ``ghl_appointments_history_v1`` (contactId, start
time). That collection fills going forward and may be empty. An empty
result falls back to the opportunity's appointmentStartTime and
appointmentOccurredAt, then to the disposition time.

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
OPPORTUNITY_COLLECTION = "ghl_opportunities_v2"
SWEEP_PIPELINES = frozenset({"sweeper", "rehash"})
APPOINTMENT_LOOKBACK = timedelta(days=3)
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


def _skipped_appointment(row: dict) -> bool:
    for key in ("appointmentStatus", "status", "appStatus"):
        label = normalize_label(row.get(key))
        if label in _SKIPPED_APPOINTMENT_STATUSES:
            return True
    return False


def appointment_instants(rows: list[dict] | None) -> list[datetime]:
    """Start times from appointment-history documents."""
    found: list[datetime] = []
    seen: set[datetime] = set()
    for row in rows or []:
        if not isinstance(row, dict) or _skipped_appointment(row):
            continue
        moment = None
        for key in (
            "startTime",
            "startTimeMs",
            "appointmentStartTime",
            "startAt",
            "start",
            "scheduledAt",
            "appointmentTime",
        ):
            moment = _coerce_time(row.get(key))
            if moment is not None:
                break
        if moment is None or moment in seen:
            continue
        seen.add(moment)
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


def counted_demo_time(dispo_at: datetime, appointment_times: list[datetime]) -> tuple[datetime, bool]:
    """Nearest past appointment within 3 days, otherwise the disposition.

    The bool is true when an appointment was used.
    """
    window_start = dispo_at - APPOINTMENT_LOOKBACK
    eligible = [moment for moment in appointment_times if window_start <= moment <= dispo_at]
    if not eligible:
        return dispo_at, False
    return max(eligible), True


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


def select_fma_demos(candidates: list[dict] | None) -> list[FmaDemo]:
    """Demos that count. One per FMA per contact, plus a self-sweep follow-up.

    Each candidate needs contact_id, opportunity_id, setter, sweeper,
    pipeline_name, dispo_at, and appointment_times. history, stage_name,
    created_at, stage_changed_at, and appointment_source are optional.
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
            times = [moment for moment in (candidate.get("appointment_times") or []) if isinstance(moment, datetime)]
            counted_at, used_appointment = counted_demo_time(candidate["dispo_at"], times)
            if used_appointment:
                date_source = compact_text(candidate.get("appointment_source")) or "opportunity_appointment"
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
        "appointment_times": times,
        "appointment_source": source,
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
