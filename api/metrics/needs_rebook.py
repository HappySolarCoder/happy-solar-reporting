# -*- coding: utf-8 -*-

"""Needs Rebook is a holding stage, not a new disposition.

Rochester, Virtual, and Self Gen are getting a GHL stage named Needs Rebook.
A server job moves No Show and Rescheduled opportunities there when no future
appointment is booked, and moves them back to New Appointment once one is
booked. Reporting keeps the prior real disposition: the last stage on
``ghl_opportunity_stage_history_v1`` that was not Needs Rebook.

Needs Rebook is not a demo, not a sit, not an appointment that ran, and not
New Appointment. It does not rewrite the stored Sit / No Sit outcome. A move
into it is not a disposition, does not take a disposition slot, and does not
create an inferred appointment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
_IN_QUERY_LIMIT = 30


def fold_stage(value: Any) -> str:
    text = str(value or "").strip().casefold()
    for char in ("_", "-", "/", "\\"):
        text = text.replace(char, " ")
    return " ".join(text.split())


def is_needs_rebook_stage(stage_name: Any) -> bool:
    """True for the holding stage. Not a demo, sit, ran appointment, or New Appointment."""
    return fold_stage(stage_name) == "needs rebook"


def is_new_appointment_name(stage_name: Any) -> bool:
    return fold_stage(stage_name) == "new appointment"


def stage_name_is_demo(stage_name: Any) -> bool:
    """Master demo check. Needs Rebook is never a demo.

    A Demo-* stage, One Legger, or Sold is a demo. Sale Cancelled is not.
    """
    if is_needs_rebook_stage(stage_name):
        return False
    folded = fold_stage(stage_name)
    if not folded:
        return False
    if folded == "sold" or folded.startswith("sold "):
        return True
    if "one legger" in folded:
        return True
    return folded == "demo" or folded.startswith("demo ")


def stage_name_is_sit(stage_name: Any, history: list[dict[str, Any]] | None = None) -> bool:
    """A stage name does not grant a sit. Needs Rebook never does.

    Sit / No Sit stays on the opportunity's stored disposition. Resolving
    Needs Rebook to No Show or Rescheduled does not create a sit.
    """
    resolved = reporting_stage_name(stage_name, history)
    if is_needs_rebook_stage(stage_name) or is_needs_rebook_stage(resolved):
        return False
    return False


def stage_name_is_ran(stage_name: Any) -> bool:
    """Needs Rebook is not an appointment that ran."""
    if is_needs_rebook_stage(stage_name) or is_new_appointment_name(stage_name):
        return False
    return False


def keeps_sit_outcome(
    disposition: Any,
    stage_name: Any = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """True when the stored disposition is Sit.

    Needs Rebook does not create a sit and does not clear an existing one.
    """
    if is_needs_rebook_stage(stage_name):
        reporting_stage_name(stage_name, history)
    return " ".join(str(disposition or "").strip().split()) == "Sit"


def keeps_ran_outcome(
    disposition: Any,
    stage_name: Any = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """True for an existing Sit or No Sit.

    The Needs Rebook move itself is not a ran appointment. The appointment
    that already has Sit or No Sit still counts, once.
    """
    if is_needs_rebook_stage(stage_name):
        reporting_stage_name(stage_name, history)
    text = fold_stage(disposition).replace("nosit", "no sit")
    return text in {"sit", "no sit"}


def is_dispo_stage_move(stage_name: Any) -> bool:
    """True when a stage transition is a real disposition.

    Needs Rebook and New Appointment are not. Needs Rebook does not take a
    disposition slot and does not create an inferred appointment.
    """
    if not fold_stage(stage_name):
        return False
    if is_needs_rebook_stage(stage_name) or is_new_appointment_name(stage_name):
        return False
    return True


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def history_stage_label(row: dict[str, Any] | None, stage_names: dict[str, str] | None = None) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("toStageName", "stageName", "name"):
        label = _compact(row.get(key))
        if label:
            return label
    names = stage_names or {}
    for key in ("toStageId", "stageId", "pipelineStageId"):
        stage_id = _compact(row.get(key))
        if stage_id and names.get(stage_id):
            return names[stage_id]
    return ""


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _row_time(row: dict[str, Any]) -> datetime:
    for key in ("effectiveAt", "lastStageChangeAt", "opportunityUpdatedAt", "createdAt"):
        moment = _as_utc(row.get(key))
        if moment is not None:
            return moment
    return datetime.min.replace(tzinfo=timezone.utc)


def ordered_history(
    history: list[dict[str, Any]] | None,
    stage_names: dict[str, str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    rows = [row for row in (history or []) if isinstance(row, dict)]
    rows.sort(key=_row_time)
    labeled: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        label = history_stage_label(row, stage_names)
        if label:
            labeled.append((label, row))
    return labeled


def prior_real_stage_name(
    history: list[dict[str, Any]] | None,
    stage_names: dict[str, str] | None = None,
) -> str:
    """Last stage on the opportunity that was not Needs Rebook."""
    prior = ""
    for label, _row in ordered_history(history, stage_names):
        if is_needs_rebook_stage(label):
            continue
        prior = label
    return prior


def reporting_stage_name(
    stage_name: Any,
    history: list[dict[str, Any]] | None = None,
    stage_names: dict[str, str] | None = None,
) -> Any:
    """Use the stage as-is, unless it is Needs Rebook.

    Needs Rebook resolves to the prior real stage so a No Show or
    Rescheduled opportunity stays in that bucket. Any other stage is
    returned unchanged.
    """
    if not is_needs_rebook_stage(stage_name):
        return stage_name
    prior = prior_real_stage_name(history, stage_names)
    return prior or stage_name


def interpret_appointment_history(
    history: list[dict[str, Any]] | None,
    stage_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Walk stage history without treating Needs Rebook as a new disposition.

    A Needs Rebook move does not take a disposition slot and does not create
    an inferred appointment. The original disposition stays on its
    appointment. New Appointment opens the next appointment, and a later
    demo credits that new appointment.
    """
    appointments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    needs_rebook_moves = 0

    def open_appointment() -> dict[str, Any]:
        nonlocal current
        current = {
            "disposition": "",
            "demo_credit": False,
            "inferred": False,
            "source": "stage_history",
        }
        appointments.append(current)
        return current

    for label, _row in ordered_history(history, stage_names):
        if is_needs_rebook_stage(label):
            needs_rebook_moves += 1
            continue
        if is_new_appointment_name(label):
            open_appointment()
            continue
        if not is_dispo_stage_move(label):
            continue
        target = current if current is not None else open_appointment()
        target["disposition"] = label
        if stage_name_is_demo(label):
            target["demo_credit"] = True

    dispositions = [row["disposition"] for row in appointments if row["disposition"]]
    return {
        "appointments": appointments,
        "dispositions": dispositions,
        "needs_rebook_moves": needs_rebook_moves,
        "dispo_slots_taken_by_needs_rebook": 0,
        "inferred_appointments": [row for row in appointments if row["inferred"]],
    }


def load_stage_history_for_opportunities(db: Any, opportunity_ids: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """History for the given opportunities. An empty id list does not query."""
    ids: list[str] = []
    seen: set[str] = set()
    for raw in opportunity_ids:
        opp_id = _compact(raw)
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        ids.append(opp_id)
    if not ids or db is None:
        return {}
    found: dict[str, list[dict[str, Any]]] = {}
    for offset in range(0, len(ids), _IN_QUERY_LIMIT):
        chunk = ids[offset : offset + _IN_QUERY_LIMIT]
        query = db.collection(HISTORY_COLLECTION).where("opportunityId", "in", chunk)
        for snap in query.stream():
            row = snap.to_dict() or {}
            opp_id = _compact(row.get("opportunityId"))
            if opp_id:
                found.setdefault(opp_id, []).append(row)
    for rows in found.values():
        rows.sort(key=_row_time)
    return found


def apply_reporting_stages(
    db: Any,
    rows: list[dict[str, Any]] | None,
    *,
    stage_key: str,
    id_key: str,
) -> None:
    """Replace a Needs Rebook label with the prior real stage.

    Sit / No Sit fields on the row are left as they are. No query runs when
    no row is in Needs Rebook.
    """
    pending = [
        row
        for row in (rows or [])
        if isinstance(row, dict) and is_needs_rebook_stage(row.get(stage_key))
    ]
    if not pending:
        return
    history = load_stage_history_for_opportunities(db, [row.get(id_key) for row in pending])
    for row in pending:
        opp_id = _compact(row.get(id_key))
        row[stage_key] = reporting_stage_name(row.get(stage_key), history.get(opp_id))
