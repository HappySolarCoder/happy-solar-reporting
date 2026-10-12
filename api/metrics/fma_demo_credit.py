# -*- coding: utf-8 -*-

"""FMA (setter) demo credit when a contact has been swept or rehashed.

An FMA keeps the original appointment when it sat. Demo means a Demo-* stage,
One Legger, or Sold, on the current stage or in city-stage history (the same
Sit the demo-rate dashboards already count). When Sweeper/Rehash Last Name is
set and it does not match the FMA's last name, a demo that happens after the
sweep or rehash — on the sweeper/rehash appointment or opportunity — does not
count for that FMA. A matching last name keeps the credit. Stage history
timestamps decide which event came first.

Ran and created counts stay on ``attributed_last_name`` (the Thu Sep 24, 2026
cutoff). This helper is only who receives the demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sit_timestamp import as_aware_utc
from sweeper_rehash_attribution import compact_text, is_blank_last_name

HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
SWEEP_PIPELINES = frozenset({"sweeper", "rehash"})


@dataclass(frozen=True)
class DemoCredit:
    """``last_name`` is who receives this demo. ``reason`` is stable for tests."""

    last_name: str
    reason: str


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
            # Leaving a demo stage as the opp enters Sweeper/Rehash is the
            # original appointment. A later move inside that pipeline is not.
            came_from_city = previous_pipeline is not None and not is_sweep_pipeline(previous_pipeline)
            entered_sweep = on_sweep and (previous is None or came_from_city)
            if came_from_city or entered_sweep or not on_sweep:
                city_demos.append(_just_before(moment))
            else:
                sweep_demos.append(_just_before(moment))
    return city_demos, sweep_demos, sweeps


def fma_demo_credit(
    setter: Any,
    sweeper: Any,
    *,
    pipeline_name: Any = "",
    stage_name: Any = "",
    stage_changed_at: Any = None,
    created_at: Any = None,
    demo_at: Any = None,
    history: list[dict] | None = None,
) -> DemoCredit:
    """Last name that receives this one demo.

    Blank Sweeper/Rehash Last Name, or a last name that matches the FMA,
    keeps the setter. Otherwise the original city demo stays with the FMA,
    and a demo at or after the sweep counts for the sweeper.
    """
    setter_name = compact_text(setter)
    sweeper_name = compact_text(sweeper)
    if not sweeper_name or is_blank_last_name(sweeper_name):
        return DemoCredit(setter_name, "setter")
    if names_match(setter_name, sweeper_name):
        return DemoCredit(setter_name, "name_matches")

    city_demos, sweep_demos, sweeps = _history_marks(history)
    changed_at = as_aware_utc(stage_changed_at)
    if is_demo_stage(stage_name) and changed_at is not None:
        if is_sweep_pipeline(pipeline_name) or is_sweep_stage(stage_name):
            sweep_demos.append(changed_at)
        else:
            city_demos.append(changed_at)

    sweep_at = min(sweeps) if sweeps else None
    if sweep_at is None and (is_sweep_pipeline(pipeline_name) or is_sweep_stage(stage_name)):
        sweep_at = as_aware_utc(created_at) or changed_at

    city_demo_at = min(city_demos) if city_demos else None
    if city_demo_at is not None and (sweep_at is None or city_demo_at < sweep_at):
        return DemoCredit(setter_name, "original_appointment")

    sweep_demo_at = min(sweep_demos) if sweep_demos else None
    if sweep_demo_at is not None and (sweep_at is None or sweep_demo_at >= sweep_at):
        return DemoCredit(sweeper_name, "after_sweep")

    sit_at = as_aware_utc(demo_at)
    if is_sweep_pipeline(pipeline_name) and city_demo_at is None:
        return DemoCredit(sweeper_name, "after_sweep")
    if sit_at is not None and sweep_at is not None and sit_at >= sweep_at and city_demo_at is None:
        return DemoCredit(sweeper_name, "after_sweep")
    return DemoCredit(setter_name, "original_appointment")


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


def load_stage_history(db: Any, opportunity_ids) -> dict[str, list[dict]]:
    """Stage history rows keyed by opportunity id. Empty ids skip the query."""
    ids: list[str] = []
    seen: set[str] = set()
    for raw in opportunity_ids or []:
        oid = compact_text(raw)
        if oid and oid not in seen:
            seen.add(oid)
            ids.append(oid)
    out: dict[str, list[dict]] = {oid: [] for oid in ids}
    if not ids or db is None:
        return out
    collection = db.collection(HISTORY_COLLECTION)
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


def load_stage_names(db: Any, pipeline_ids) -> dict[str, str]:
    """Stage id to stage name from the pipelines already in this window."""
    if db is None:
        return {}
    ids: list[str] = []
    seen: set[str] = set()
    for raw in pipeline_ids or []:
        pid = compact_text(raw)
        if pid and pid not in seen:
            seen.add(pid)
            ids.append(pid)
    out: dict[str, str] = {}
    if not ids:
        return out
    refs = [db.collection("ghl_pipelines_v2").document(pid) for pid in ids]
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
