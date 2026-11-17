# -*- coding: utf-8 -*-

"""Metrics for the EmPower+ NYHEP portal snapshot.

Overdue and due tones compare the portal due date to the snapshot's as-of
date in America/Phoenix. They do not use the server clock. The snapshot id
``2026-11-17_pm`` is the Phoenix calendar date 2026-11-17.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo


PHOENIX = ZoneInfo("America/Phoenix")

TITLE = "EmPower+ NYSERDA Portal Dashboard"
SUBTITLE_LEAD = (
    "Happy Home (Essential Homes LLC) EmPower+ projects in the NYHEP portal, "
    "checked at the start and end of each weekday."
)
SOURCE_LINE = (
    "Data is read from the portal enrollment list and To-Do list. "
    "A project on the To-Do list is waiting on us."
)
WAITING_DETAIL = "On the portal To-Do list"
VENDOR_WARNING = (
    "Vendor Responsibility Checklist: the portal home page says NYSERDA "
    "revokes access on 11/23 and terminates on 11/30 for contractors that "
    "haven't submitted it."
)

PIPELINE = (
    "Contractor Assignment",
    "Enrollment Acceptance",
    "Assessment Submission",
    "Assessment Review",
    "Workscope Submission",
    "Workscope Review",
    "Install Started",
    "Final Project Submission",
    "Final Project Review",
    "Final Technical Review",
    "Funding Allocations",
)

_PIPELINE_INDEX = {name: index for index, name in enumerate(PIPELINE)}
_WORKSCOPE_INDEX = _PIPELINE_INDEX["Workscope Submission"]
_DUE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_SNAPSHOT_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_TIER_SUFFIXES = (" - Low Income", " - Moderate Income")
_FORBIDDEN_KEY_WORDS = ("phone", "email", "contact")
_STATUS_OPEN = {"open", "active"}
_STATUS_CLOSED = {"closed", "completed", "complete"}
_STATUS_CANCELLED = {"cancelled", "canceled"}


def snapshot_as_of(snapshot: object) -> date | None:
    """Phoenix calendar date encoded in a snapshot id. Never the clock."""
    match = _SNAPSHOT_DAY.match(str(snapshot or "").strip())
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, tzinfo=PHOENIX).date()
    except ValueError:
        return None


def parse_due(value: object) -> date | None:
    """Portal due dates are M/D/YYYY calendar dates in America/Phoenix."""
    match = _DUE_RE.match(str(value or "").strip())
    if match is None:
        return None
    month, day, year = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, tzinfo=PHOENIX).date()
    except ValueError:
        return None


def normalize_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in _STATUS_OPEN:
        return "Open"
    if text in _STATUS_CLOSED:
        return "Closed"
    if text in _STATUS_CANCELLED:
        return "Cancelled"
    return "Other"


def display_tier(value: object) -> str:
    text = str(value or "").strip()
    for suffix in _TIER_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def display_installer(value: object) -> str:
    text = str(value or "").strip()
    return text or "Not assigned"


def is_on_todo(row: dict) -> bool:
    value = row.get("onTodo")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def is_past_workscope(step: object, status: object) -> bool:
    if normalize_status(status) != "Open":
        return False
    index = _PIPELINE_INDEX.get(str(step or "").strip())
    return index is not None and index > _WORKSCOPE_INDEX


def due_tone(due: date | None, as_of: date | None) -> str:
    if due is None or as_of is None:
        return ""
    delta = (due - as_of).days
    if delta < 0:
        return "danger"
    if delta <= 14:
        return "warning"
    return ""


def history_change_count(changes: object) -> int:
    """Length when changes is a list. The number itself when it already is one."""
    if isinstance(changes, bool):
        return 0
    if isinstance(changes, list):
        return len(changes)
    if isinstance(changes, (int, float)):
        return int(changes)
    return 0


def _norm_key(key: object) -> str:
    return re.sub(r"[^a-z]", "", str(key).lower())


def contains_forbidden_keys(value: object) -> bool:
    """True when projects or changes carry phone, email, or contact keys."""
    if isinstance(value, dict):
        for key, item in value.items():
            norm = _norm_key(key)
            if any(word in norm for word in _FORBIDDEN_KEY_WORDS):
                return True
            if contains_forbidden_keys(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_forbidden_keys(item) for item in value)
    return False


def _step_label(step: object, step_status: object) -> str:
    step_text = str(step or "").strip()
    status_text = str(step_status or "").strip()
    if step_text and status_text:
        return f"{step_text} ({status_text})"
    return step_text or status_text


def _history_rank(entry: dict) -> tuple:
    snapshot = str(entry.get("snapshot") or "")
    day = snapshot[:10]
    suffix = snapshot.split("_", 1)[1].lower() if "_" in snapshot else ""
    period = {"am": 1, "pm": 2}.get(suffix, 0)
    return (day, period, snapshot)


def _stage_rows(projects: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in projects:
        if normalize_status(row.get("status")) != "Open":
            continue
        step = str(row.get("step") or "").strip() or "Unknown"
        counts[step] = counts.get(step, 0) + 1

    def sort_key(step: str) -> tuple:
        index = _PIPELINE_INDEX.get(step)
        if index is None:
            return (1, step.lower())
        return (0, index)

    return [{"step": step, "count": counts[step]} for step in sorted(counts, key=sort_key)]


def _waiting_rows(projects: list[dict], as_of: date | None) -> list[dict]:
    rows = []
    for row in projects:
        if not isinstance(row, dict) or not is_on_todo(row):
            continue
        due_text = str(row.get("due") or "").strip()
        due = parse_due(due_text)
        tone = due_tone(due, as_of)
        due_label = f"{due_text} overdue" if tone == "danger" and due_text else due_text
        rows.append(
            {
                "id": str(row.get("id") or "").strip(),
                "customer": str(row.get("customer") or "").strip(),
                "step": str(row.get("step") or "").strip(),
                "stepStatus": str(row.get("stepStatus") or "").strip(),
                "stepLabel": _step_label(row.get("step"), row.get("stepStatus")),
                "due": due_text,
                "dueLabel": due_label,
                "tone": tone,
            }
        )

    def sort_key(item: dict) -> tuple:
        due = parse_due(item.get("due"))
        if due is None:
            return (1, date.max.toordinal(), item.get("id") or "")
        return (0, due.toordinal(), item.get("id") or "")

    rows.sort(key=sort_key)
    return rows


def _enrollment_rows(projects: list[dict]) -> list[dict]:
    rows = []
    for row in projects:
        if not isinstance(row, dict):
            continue
        status = normalize_status(row.get("status"))
        rows.append(
            {
                "id": str(row.get("id") or "").strip(),
                "customer": str(row.get("customer") or "").strip(),
                "city": str(row.get("city") or "").strip(),
                "enrolled": str(row.get("enrolled") or "").strip(),
                "status": status,
                "statusTone": "success" if status == "Closed" else "",
                "step": str(row.get("step") or "").strip(),
                "installer": display_installer(row.get("installer")),
                "tier": display_tier(row.get("tier")),
            }
        )
    return rows


def _history_rows(history: object) -> list[dict]:
    if not isinstance(history, list):
        return []
    rows = []
    for item in history:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "snapshot": str(item.get("snapshot") or "").strip(),
                "checkedAt": str(item.get("checkedAt") or "").strip(),
                "total": item.get("total"),
                "open": item.get("open"),
                "closed": item.get("closed"),
                "cancelled": item.get("cancelled"),
                "changeCount": history_change_count(item.get("changes")),
            }
        )
    rows.sort(key=_history_rank, reverse=True)
    return rows


def _public_changes(changes: object) -> list[dict]:
    if not isinstance(changes, list):
        return []
    rows = []
    for item in changes:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": str(item.get("id") or "").strip(),
                "customer": str(item.get("customer") or "").strip(),
                "change": str(item.get("change") or "").strip(),
            }
        )
    return rows


def build_portal_view(payload: dict | None) -> dict[str, Any]:
    """Public view model. Phone, email, and contact keys are not copied."""
    source = payload if isinstance(payload, dict) else {}
    projects = [row for row in source.get("projects") or [] if isinstance(row, dict)]
    as_of = snapshot_as_of(source.get("snapshot"))
    statuses = [normalize_status(row.get("status")) for row in projects]
    open_count = statuses.count("Open")
    closed_count = statuses.count("Closed")
    cancelled_count = statuses.count("Cancelled")
    waiting = _waiting_rows(projects, as_of)
    overdue = sum(1 for row in waiting if row["tone"] == "danger")
    past = sum(1 for row in projects if is_past_workscope(row.get("step"), row.get("status")))
    return {
        "title": TITLE,
        "subtitleLead": SUBTITLE_LEAD,
        "sourceLine": SOURCE_LINE,
        "waitingDetail": WAITING_DETAIL,
        "warning": VENDOR_WARNING,
        "snapshot": str(source.get("snapshot") or "").strip(),
        "checkedAt": str(source.get("checkedAt") or "").strip(),
        "asOf": as_of.isoformat() if as_of else "",
        "timezone": "America/Phoenix",
        "metrics": {
            "total": len(projects),
            "open": open_count,
            "closed": closed_count,
            "cancelled": cancelled_count,
            "waitingOnUs": len(waiting),
            "pastWorkscope": past,
            "overdue": overdue,
            "overdueTone": "danger" if overdue > 0 else "",
        },
        "filters": {
            "Open": open_count,
            "Closed": closed_count,
            "Cancelled": cancelled_count,
            "All": len(projects),
        },
        "changes": _public_changes(source.get("changes")),
        "stages": _stage_rows(projects),
        "waiting": waiting,
        "enrollments": _enrollment_rows(projects),
        "history": _history_rows(source.get("history")),
    }
