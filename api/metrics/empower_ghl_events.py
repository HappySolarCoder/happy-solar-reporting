# -*- coding: utf-8 -*-

"""One document per continuous GHL Empower+ stage stint.

Doc id is sha1(opp_id|stage_id|first_seen_at_iso)[:20]. Replaying the same
open stint keeps that id. This collection is not a funnel metric input.
"""

from __future__ import annotations

import hashlib
from typing import Any

from metrics.empower_ids import EMPOWER_PIPELINE_ID, GHL_STAGE_NAME, GHL_STAGE_EVENTS


def event_doc_id(opp_id: str, stage_id: str, first_seen_at: str) -> str:
    raw = f"{opp_id}|{stage_id}|{first_seen_at}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _text(value: object) -> str:
    return str(value or "").strip()


def _opp_status(opp: dict) -> str:
    status = _text(opp.get("status") or "open").lower()
    if status in {"open", "won", "lost", "abandoned"}:
        return status
    return "open"


def diff_ghl_stage_events(
    open_events: dict[str, tuple[str, dict]],
    opps: list[dict],
    enrollment_by_opp: dict[str, str] | None = None,
    *,
    now_iso: str,
    source: str = "sync",
) -> list[tuple[str, dict]]:
    """Close finished stints and open new ones. Same stage and timestamp writes nothing."""
    enrollment_by_opp = enrollment_by_opp or {}
    changed: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for opp in opps:
        if not isinstance(opp, dict):
            continue
        pipeline_id = _text(opp.get("pipelineId") or opp.get("pipeline_id"))
        if pipeline_id and pipeline_id != EMPOWER_PIPELINE_ID:
            continue
        opp_id = _text(opp.get("id") or opp.get("opp_id"))
        stage_id = _text(opp.get("pipelineStageId") or opp.get("stage_id"))
        if not opp_id or not stage_id:
            continue
        seen.add(opp_id)
        existing = open_events.get(opp_id)
        status = _opp_status(opp)
        if existing is not None and _text(existing[1].get("stage_id")) == stage_id and existing[1].get("ended_at") is None:
            doc_id, previous = existing
            if (
                previous.get("last_seen_at") == now_iso
                and previous.get("status") == status
                and _text(previous.get("enrollment_id")) == _text(enrollment_by_opp.get(opp_id))
                and _text(previous.get("assigned_to")) == _text(opp.get("assignedTo") or opp.get("assigned_to"))
            ):
                continue
            updated = dict(previous)
            updated["last_seen_at"] = now_iso
            updated["status"] = status
            updated["enrollment_id"] = _text(enrollment_by_opp.get(opp_id)) or previous.get("enrollment_id") or ""
            updated["assigned_to"] = _text(opp.get("assignedTo") or opp.get("assigned_to"))
            updated["source"] = previous.get("source") or source
            changed.append((doc_id, updated))
            continue
        if existing is not None:
            doc_id, previous = existing
            ended = dict(previous)
            ended["ended_at"] = now_iso
            ended["last_seen_at"] = now_iso
            if status in {"won", "lost"}:
                ended["status"] = status
            changed.append((doc_id, ended))
        body: dict[str, Any] = {
            "opp_id": opp_id,
            "contact_id": _text(opp.get("contactId") or opp.get("contact_id")),
            "enrollment_id": _text(enrollment_by_opp.get(opp_id)),
            "stage_id": stage_id,
            "stage_name": GHL_STAGE_NAME.get(stage_id) or _text(opp.get("stage_name")),
            "status": status,
            "assigned_to": _text(opp.get("assignedTo") or opp.get("assigned_to")),
            "first_seen_at": now_iso,
            "last_seen_at": now_iso,
            "ended_at": None,
            "first_seen_is_start": existing is not None,
            "source": source,
        }
        changed.append((event_doc_id(opp_id, stage_id, now_iso), body))
    for opp_id, (doc_id, previous) in open_events.items():
        if opp_id in seen or previous.get("ended_at") is not None:
            continue
        ended = dict(previous)
        ended["ended_at"] = now_iso
        ended["last_seen_at"] = now_iso
        ended["status"] = "abandoned"
        changed.append((doc_id, ended))
    return changed


def open_map_from_docs(docs: list[tuple[str, dict]]) -> dict[str, tuple[str, dict]]:
    found: dict[str, tuple[str, dict]] = {}
    for doc_id, body in docs:
        if not isinstance(body, dict) or body.get("ended_at") is not None:
            continue
        opp_id = _text(body.get("opp_id"))
        if opp_id:
            found[opp_id] = (doc_id, body)
    return found


def load_open_ghl_events(db) -> dict[str, tuple[str, dict]]:
    try:
        query = db.collection(GHL_STAGE_EVENTS).where("ended_at", "==", None).order_by("opp_id")
    except Exception:
        return {}
    found: dict[str, tuple[str, dict]] = {}
    try:
        snaps = query.stream()
    except Exception:
        return {}
    for snap in snaps:
        data = snap.to_dict() or {}
        if not isinstance(data, dict):
            continue
        opp_id = _text(data.get("opp_id"))
        if opp_id:
            found[opp_id] = (str(getattr(snap, "id", "") or ""), data)
    return found
