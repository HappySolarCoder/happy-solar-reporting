# -*- coding: utf-8 -*-

"""NYHEP enrollment stage events.

One document per continuous state in ``nyhep_empower_stage_events``. The id is
the first 20 hex characters of sha1(enrollment_id|enrollment_status|stage|
todo_stage|step_status|on_todo|first_seen_snapshot), so a re-post or a backfill
replay writes the same document.

``days_in_stage`` is calculated when a page is read. It is not stored.
``first_seen_is_start`` is false the first time an enrollment is seen, because
that check is not proof the stage began then.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


PHOENIX = ZoneInfo("America/Phoenix")
COLLECTION = "nyhep_empower_stage_events"
LOOKBACK_DAYS = 120

OURS_STAGES = frozenset(
    {
        "Enrollment Acceptance",
        "Workscope Submission",
        "Final Project Submission",
        "Assessment Started",
        "Install Started",
        "Create an Enrollment",
    }
)
PROGRAM_STAGES = frozenset(
    {
        "Contractor Assignment",
        "Workscope Review",
        "Provisional Approval",
        "Assessment Review",
        "Final Project Review",
        "Final Technical Review",
        "Funding Allocations",
        "Installation Review",
        "Installation Funding Allocations",
        "Payment",
    }
)
REVIEW_BUSINESS_DAYS = {
    "Workscope Review": 5,
    "Final Project Review": 5,
}
CALENDAR_DAY_LIMITS = {
    "Contractor Assignment": 14,
    "Funding Allocations": 14,
}
ENROLLMENT_DAY_LIMITS = {
    "Workscope Submission": 30,
    "Final Project Submission": 75,
}

_PERIODS = {"am": 1, "pm": 2, "eod": 3}
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_SNAPSHOT_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_CLOCK = re.compile(
    r"([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{1,2}):(\d{2})\s*([AP]M)",
    re.IGNORECASE,
)
_DUE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_STATUS_OPEN = {"open", "active"}
_STATUS_CLOSED = {"closed", "completed", "complete"}
_STATUS_CANCELLED = {"cancelled", "canceled"}


def normalize_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in _STATUS_OPEN:
        return "Open"
    if text in _STATUS_CLOSED:
        return "Closed"
    if text in _STATUS_CANCELLED:
        return "Cancelled"
    return "Other"


def is_on_todo(row: dict) -> bool:
    value = row.get("onTodo")
    if "on_todo" in row and "onTodo" not in row:
        value = row.get("on_todo")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def snapshot_day(snapshot: object) -> date | None:
    match = _SNAPSHOT_DAY.match(str(snapshot or "").strip())
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def snapshot_rank(snapshot: object) -> tuple:
    text = str(snapshot or "").strip()
    day = text[:10]
    suffix = text.split("_", 1)[1].lower() if "_" in text else ""
    return (day, _PERIODS.get(suffix, 0), text)


def parse_mdy(value: object) -> date | None:
    match = _DUE.match(str(value or "").strip())
    if match is None:
        return None
    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def event_time(snapshot: object, checked_at: object) -> str:
    """Phoenix time for a check. The snapshot id supplies the year."""
    as_of = snapshot_day(snapshot)
    text = str(snapshot or "").strip()
    suffix = text.split("_", 1)[1].lower() if "_" in text else ""
    hour, minute = {"am": (9, 0), "pm": (16, 0), "eod": (20, 0)}.get(suffix, (12, 0))
    year = as_of.year if as_of else 2026
    month = as_of.month if as_of else 1
    day = as_of.day if as_of else 1
    match = _CLOCK.search(str(checked_at or ""))
    if match is not None:
        month_name, day_text, hour_text, minute_text, ampm = match.groups()
        parsed_month = _MONTHS.get(month_name.lower())
        if parsed_month is not None:
            month = parsed_month
            day = int(day_text)
            hour = int(hour_text) % 12
            if ampm.upper() == "PM":
                hour += 12
            minute = int(minute_text)
    try:
        moment = datetime(year, month, day, hour, minute, tzinfo=PHOENIX)
    except ValueError:
        moment = datetime(year, as_of.month if as_of else 1, as_of.day if as_of else 1, 12, 0, tzinfo=PHOENIX)
    return moment.isoformat()


def _date_from_stored(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def display_date(value: object) -> str:
    parsed = _date_from_stored(value)
    if parsed is None:
        return ""
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def business_days(start: date | None, end: date | None) -> int:
    """Weekdays in [start, end). The end date is the as-of day and is not counted."""
    if start is None or end is None or end <= start:
        return 0
    count = 0
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def calendar_days(start: date | None, end: date | None) -> int:
    if start is None or end is None or end <= start:
        return 0
    return (end - start).days


def owner_side(on_todo: bool, stage: str, todo_stage: str) -> str:
    """Who the enrollment is waiting on.

    Unknown when the To-Do step and the Enrollment List step disagree.
    Otherwise ours when it is on the To-Do list or in an office stage, and
    the program when the stage is one NYSERDA holds.
    """
    if on_todo and todo_stage and todo_stage != stage:
        return "unknown"
    if on_todo or stage in OURS_STAGES:
        return "ours"
    if stage in PROGRAM_STAGES:
        return "program"
    return "unknown"


def project_state(project: dict) -> dict[str, Any]:
    stage = str(project.get("step") or "").strip()
    on_todo = is_on_todo(project)
    todo_raw = str(project.get("todoStep") or project.get("todo_stage") or "").strip()
    if not on_todo:
        todo = ""
    else:
        todo = todo_raw or stage
    return {
        "enrollment_status": normalize_status(project.get("status") or project.get("enrollment_status")),
        "stage": stage,
        "todo": todo,
        "step_status": str(
            (project.get("stepStatus") if "stepStatus" in project else project.get("step_status")) or ""
        ).strip(),
        "on_todo": on_todo,
    }


def stored_state(event: dict) -> tuple:
    stage = str(event.get("stage") or "").strip()
    on_todo = bool(event.get("on_todo"))
    if not on_todo:
        todo = ""
    elif str(event.get("todo_stage") or "").strip():
        todo = str(event.get("todo_stage") or "").strip()
    else:
        todo = stage
    return (
        str(event.get("enrollment_status") or "").strip(),
        stage,
        todo,
        str(event.get("step_status") or "").strip(),
        on_todo,
    )


def state_tuple(state: dict) -> tuple:
    return (
        state["enrollment_status"],
        state["stage"],
        state["todo"],
        state["step_status"],
        state["on_todo"],
    )


def event_doc_id(
    enrollment_id: str,
    enrollment_status: str,
    stage: str,
    todo_stage: str,
    step_status: str,
    on_todo: bool,
    first_seen_snapshot: str,
) -> str:
    raw = "|".join(
        [
            enrollment_id,
            enrollment_status,
            stage,
            todo_stage,
            step_status,
            "true" if on_todo else "false",
            first_seen_snapshot,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _build_event(
    project: dict,
    state: dict,
    snapshot: str,
    moment: str,
    *,
    first_seen_is_start: bool,
) -> tuple[str, dict]:
    enrollment_id = str(project.get("id") or project.get("enrollment_id") or "").strip()
    todo_stage = state["todo"]
    doc_id = event_doc_id(
        enrollment_id,
        state["enrollment_status"],
        state["stage"],
        todo_stage,
        state["step_status"],
        state["on_todo"],
        snapshot,
    )
    body: dict[str, Any] = {
        "enrollment_id": enrollment_id,
        "program": str(project.get("program") or "").strip(),
        "project_type": str(project.get("projectType") or project.get("project_type") or "").strip(),
        "customer": str(project.get("customer") or "").strip(),
        "enrollment_status": state["enrollment_status"],
        "stage": state["stage"],
        "step_status": state["step_status"],
        "on_todo": state["on_todo"],
        "owner_side": owner_side(state["on_todo"], state["stage"], todo_stage),
        "first_seen_at": moment,
        "last_seen_at": moment,
        "ended_at": None,
        "due_date": str(project.get("due") or project.get("due_date") or "").strip(),
        "first_seen_is_start": first_seen_is_start,
        "source_snapshots": [snapshot],
    }
    if state["on_todo"] and todo_stage and todo_stage != state["stage"]:
        body["todo_stage"] = todo_stage
    return doc_id, body


def apply_snapshot(
    open_events: dict[str, tuple[str, dict]],
    projects: object,
    snapshot: str,
    checked_at: object,
) -> tuple[dict[str, tuple[str, dict]], list[tuple[str, dict]]]:
    """Move open events forward one check. Returns the new open map and changed docs."""
    snapshot_id = str(snapshot or "").strip()
    moment = event_time(snapshot_id, checked_at)
    current = dict(open_events)
    changed: list[tuple[str, dict]] = []
    seen: set[str] = set()
    rows = projects if isinstance(projects, list) else []
    for project in rows:
        if not isinstance(project, dict):
            continue
        enrollment_id = str(project.get("id") or project.get("enrollment_id") or "").strip()
        if not enrollment_id:
            continue
        seen.add(enrollment_id)
        state = project_state(project)
        existing = current.get(enrollment_id)
        if existing is not None and stored_state(existing[1]) == state_tuple(state):
            doc_id, previous = existing
            sources = list(previous.get("source_snapshots") or [])
            if snapshot_id in sources and previous.get("last_seen_at") == moment and previous.get("ended_at") is None:
                continue
            updated = dict(previous)
            if snapshot_id not in sources:
                sources.append(snapshot_id)
            updated["source_snapshots"] = sources
            updated["last_seen_at"] = moment
            updated["ended_at"] = None
            current[enrollment_id] = (doc_id, updated)
            changed.append((doc_id, updated))
            continue
        if existing is not None:
            doc_id, previous = existing
            ended = dict(previous)
            ended["ended_at"] = moment
            changed.append((doc_id, ended))
        doc_id, created = _build_event(
            project,
            state,
            snapshot_id,
            moment,
            first_seen_is_start=existing is not None,
        )
        current[enrollment_id] = (doc_id, created)
        changed.append((doc_id, created))
    for enrollment_id, (doc_id, previous) in list(current.items()):
        if enrollment_id in seen or previous.get("ended_at") is not None:
            continue
        ended = dict(previous)
        ended["ended_at"] = moment
        changed.append((doc_id, ended))
        del current[enrollment_id]
    return current, changed


def fold_snapshots(snapshots: list[dict]) -> dict[str, dict]:
    """Replay checks from an empty collection. The same inputs produce the same ids."""
    ordered = sorted(
        [row for row in snapshots if isinstance(row, dict) and str(row.get("snapshot") or "").strip()],
        key=lambda row: snapshot_rank(row.get("snapshot")),
    )
    open_events: dict[str, tuple[str, dict]] = {}
    stored: dict[str, dict] = {}
    for row in ordered:
        open_events, changed = apply_snapshot(
            open_events,
            row.get("projects") or [],
            str(row.get("snapshot") or ""),
            row.get("checkedAt"),
        )
        for doc_id, body in changed:
            stored[doc_id] = body
    return stored


def observation_count(snapshots: list[dict]) -> int:
    total = 0
    for row in snapshots:
        projects = row.get("projects") if isinstance(row, dict) else None
        if isinstance(projects, list):
            total += sum(1 for item in projects if isinstance(item, dict) and str(item.get("id") or "").strip())
    return total


def summarize(events: dict[str, dict], snapshots: list[dict] | None = None) -> dict[str, Any]:
    current = [row for row in events.values() if row.get("ended_at") is None]
    ended = [row for row in events.values() if row.get("ended_at") is not None]
    owners = {"ours": 0, "program": 0, "unknown": 0}
    programs: dict[str, int] = {}
    with_program = 0
    review_flags = {"Workscope Review >5 business days": 0, "Final Project Review >5 business days": 0}
    as_of = None
    if snapshots:
        ranked = sorted(
            (str(row.get("snapshot") or "") for row in snapshots if isinstance(row, dict)),
            key=snapshot_rank,
        )
        if ranked:
            as_of = snapshot_day(ranked[-1])
    projects: dict[str, dict] = {}
    if snapshots and as_of is not None:
        latest_id = sorted(
            (str(row.get("snapshot") or "") for row in snapshots if isinstance(row, dict)),
            key=snapshot_rank,
        )[-1]
        for row in snapshots:
            if isinstance(row, dict) and str(row.get("snapshot") or "") == latest_id:
                for project in row.get("projects") or []:
                    if isinstance(project, dict):
                        projects[str(project.get("id") or "").strip()] = project
    for row in current:
        side = str(row.get("owner_side") or "unknown")
        owners[side] = owners.get(side, 0) + 1
        program = str(row.get("program") or "").strip() or "(blank)"
        programs[program] = programs.get(program, 0) + 1
        if (
            row.get("enrollment_status") == "Open"
            and not row.get("on_todo")
            and side == "program"
        ):
            with_program += 1
        if row.get("enrollment_status") == "Open" and not row.get("on_todo") and as_of is not None:
            for label in stage_flags(row, projects.get(str(row.get("enrollment_id") or "")), as_of):
                if label in review_flags:
                    review_flags[label] += 1
    return {
        "observations": observation_count(snapshots or []),
        "enrollments": len({str(row.get("enrollment_id") or "") for row in events.values()}),
        "events": len(events),
        "current": len(current),
        "ended": len(ended),
        "unique_keys": len(events),
        "owner_side": owners,
        "programs": programs,
        "with_program": with_program,
        "flags": review_flags,
    }


def format_summary(summary: dict) -> str:
    lines = [
        f"observations {summary['observations']}",
        f"enrollments {summary['enrollments']}",
        f"events {summary['events']}",
        f"current {summary['current']}",
        f"ended {summary['ended']}",
        f"unique_keys {summary['unique_keys']}",
        f"owner_side ours {summary['owner_side'].get('ours', 0)}",
        f"owner_side program {summary['owner_side'].get('program', 0)}",
        f"owner_side unknown {summary['owner_side'].get('unknown', 0)}",
    ]
    for name in sorted(summary["programs"]):
        lines.append(f"program {name} {summary['programs'][name]}")
    lines.append(f"with_program {summary['with_program']}")
    for label, count in summary["flags"].items():
        lines.append(f"flag {label} {count}")
    return "\n".join(lines) + "\n"


def stage_flags(event: dict, project: dict | None, as_of: date | None) -> list[str]:
    stage = str(event.get("stage") or "").strip()
    start = _date_from_stored(event.get("first_seen_at"))
    labels: list[str] = []
    if stage in REVIEW_BUSINESS_DAYS and business_days(start, as_of) > REVIEW_BUSINESS_DAYS[stage]:
        labels.append(f"{stage} >{REVIEW_BUSINESS_DAYS[stage]} business days")
    if stage in CALENDAR_DAY_LIMITS and calendar_days(start, as_of) > CALENDAR_DAY_LIMITS[stage]:
        labels.append(f"{stage} >{CALENDAR_DAY_LIMITS[stage]} days")
    due = str((project or {}).get("due") or event.get("due_date") or "").strip()
    enrolled = parse_mdy((project or {}).get("enrolled"))
    limit = ENROLLMENT_DAY_LIMITS.get(stage)
    if limit is not None and not due and calendar_days(enrolled, as_of) > limit:
        labels.append(f"{stage} >{limit} days from enrollment")
    return labels


def since_label(event: dict) -> str:
    shown = display_date(event.get("first_seen_at"))
    if not shown:
        return ""
    if event.get("first_seen_is_start") is False:
        return f"since at least {shown}"
    return f"since {shown}"


def timeline_rows(events: list[dict], as_of: date | None) -> list[dict]:
    rows = []
    ordered = sorted(
        [event for event in events if isinstance(event, dict)],
        key=lambda event: str(event.get("first_seen_at") or ""),
    )
    for event in ordered:
        if not isinstance(event, dict):
            continue
        ended = event.get("ended_at") is not None
        end_day = _date_from_stored(event.get("ended_at")) if ended else as_of
        rows.append(
            {
                "stage": str(event.get("stage") or "").strip(),
                "todoStage": str(event.get("todo_stage") or "").strip(),
                "stepStatus": str(event.get("step_status") or "").strip(),
                "enrollmentStatus": str(event.get("enrollment_status") or "").strip(),
                "onTodo": bool(event.get("on_todo")),
                "ownerSide": str(event.get("owner_side") or "").strip(),
                "since": since_label(event),
                "sinceAtLeast": event.get("first_seen_is_start") is False,
                "firstSeen": display_date(event.get("first_seen_at")),
                "ended": ended,
                "daysInStage": calendar_days(_date_from_stored(event.get("first_seen_at")), end_day),
                "current": not ended,
            }
        )
    return rows


def with_program_rows(events: list[dict], projects: list[dict], as_of: date | None) -> list[dict]:
    """Open enrollments that are off the To-Do list, longest current stage first."""
    by_id = {}
    for project in projects:
        if isinstance(project, dict):
            enroll_id = str(project.get("id") or "").strip()
            if enroll_id:
                by_id[enroll_id] = project
    rows = []
    for event in events:
        if not isinstance(event, dict) or event.get("ended_at") is not None:
            continue
        if event.get("enrollment_status") != "Open" or event.get("on_todo"):
            continue
        enroll_id = str(event.get("enrollment_id") or "").strip()
        project = by_id.get(enroll_id)
        start = _date_from_stored(event.get("first_seen_at"))
        flags = stage_flags(event, project, as_of)
        rows.append(
            {
                "id": enroll_id,
                "customer": str(event.get("customer") or "").strip(),
                "stage": str(event.get("stage") or "").strip(),
                "daysInStage": calendar_days(start, as_of),
                "since": since_label(event),
                "sinceAtLeast": event.get("first_seen_is_start") is False,
                "flag": "; ".join(flags),
                "ownerSide": str(event.get("owner_side") or "").strip(),
            }
        )
    rows.sort(key=lambda row: row["id"])
    rows.sort(key=lambda row: row["daysInStage"], reverse=True)
    return rows


def attach_timelines(enrollments: list[dict], events: list[dict], as_of: date | None) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for event in events:
        if isinstance(event, dict):
            grouped.setdefault(str(event.get("enrollment_id") or "").strip(), []).append(event)
    attached = []
    for row in enrollments:
        item = dict(row)
        item["timeline"] = timeline_rows(grouped.get(str(row.get("id") or "").strip(), []), as_of)
        attached.append(item)
    return attached


def load_open_events(db) -> dict[str, tuple[str, dict]]:
    """Open events only. One query, no listener."""
    query = db.collection(COLLECTION).where("ended_at", "==", None).order_by("enrollment_id")
    found: dict[str, tuple[str, dict]] = {}
    for snap in query.stream():
        data = snap.to_dict() or {}
        if not isinstance(data, dict):
            continue
        enrollment_id = str(data.get("enrollment_id") or "").strip()
        if enrollment_id:
            found[enrollment_id] = (str(snap.id), data)
    return found


def sync_stage_events(db, projects: list, snapshot: str, checked_at: object) -> int:
    """Apply one check to the open events and batch-write only the documents that changed."""
    open_events = load_open_events(db)
    _open, changed = apply_snapshot(open_events, projects, snapshot, checked_at)
    if not changed:
        return 0
    batch = db.batch()
    for doc_id, body in changed:
        batch.set(db.collection(COLLECTION).document(doc_id), body)
    batch.commit()
    return len(changed)


def load_recent_events(db, payload: dict | None) -> list[dict]:
    """One query: events last seen in the 120 days before the snapshot date."""
    source = payload if isinstance(payload, dict) else {}
    as_of = snapshot_day(source.get("snapshot"))
    if as_of is None:
        cutoff = date(1970, 1, 1)
    else:
        cutoff = as_of - timedelta(days=LOOKBACK_DAYS)
    lower = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=PHOENIX).isoformat()
    query = db.collection(COLLECTION).where("last_seen_at", ">=", lower)
    rows = []
    for snap in query.stream():
        data = snap.to_dict() or {}
        if isinstance(data, dict):
            rows.append(data)
    return rows
