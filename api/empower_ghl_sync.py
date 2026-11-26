# -*- coding: utf-8 -*-

"""Fields-only Empower+ shadow sync.

Phase 3 writes NYHEP custom fields onto linked opportunities. It never sends
pipelineStageId. Auto-create stays off unless EMPOWER_AUTO_CREATE_OPPS is the
string "true". Created opportunities are posted to GoHighLevel only. They are
not inserted into ghl_opportunities_v2, so this path does not feed funnel counts.
The pipeline-id exclusion for those counts is a separate change.

dry_run plans the writes and does not call GHL or Firestore.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from metrics.empower_alerts import evaluate_jobs, stall_summary
from metrics.empower_ghl_events import diff_ghl_stage_events, load_open_ghl_events
from metrics.empower_ids import (
    EMPOWER_PIPELINE_ID,
    FIELD_DUE,
    FIELD_ENROLLMENT_ID,
    FIELD_ENROLLMENT_STATUS,
    FIELD_LAST_SYNCED,
    FIELD_PROGRAM,
    FIELD_STALL,
    FIELD_STEP,
    FIELD_STEP_SINCE,
    FIELD_STEP_STATUS,
    FIELD_TRADE_ALLY,
    FIELD_WITH,
    GHL_API_VERSION,
    GHL_LOCATION_ID_DEFAULT,
    GHL_STAGE_EVENTS,
    GHL_STAGE_ID_BY_NAME,
    NYHEP_STAGE_POS,
    PROGRAM_OPTIONS,
    STATUS_OPTIONS,
    TRADE_OPTIONS,
    USER_BROOKE,
    WITH_OPTIONS,
)
from metrics.empower_linker import (
    _opp_id,
    _text,
    custom_field_map,
    guarded_set,
    load_empower_opps,
    load_links,
    match_matches_by_id,
    persist_links,
    sync_links,
)
from metrics.nyhep_stage_events import owner_side, parse_mdy


PHOENIX = ZoneInfo("America/Phoenix")
GHL_BASE = "https://services.leadconnectorhq.com"


def auto_create_enabled() -> bool:
    return _text(os.environ.get("EMPOWER_AUTO_CREATE_OPPS")).lower() == "true"


def shadow_on_ingest() -> bool:
    return _text(os.environ.get("EMPOWER_SHADOW_SYNC_ON_INGEST")).lower() == "true"


def program_option(project: dict) -> str:
    text = f"{project.get('program') or ''} {project.get('tier') or ''}".lower()
    if "comfort" in text:
        return "Comfort Home"
    if "rea" in text and "empower" not in text:
        return "REA"
    if "empower" in text:
        return "EmPower+"
    return ""


def trade_ally_option(project: dict) -> str:
    text = _text(project.get("installer")).lower()
    if "essential" in text:
        return "Essential Homes LLC"
    if "happy" in text:
        return "A Happy Day LLC"
    return ""


def with_option(project: dict, event: dict | None) -> str:
    stage = _text((event or {}).get("stage") or project.get("step"))
    todo = _text((event or {}).get("todo_stage") or project.get("todoStep"))
    on_todo = bool(project.get("onTodo") or project.get("on_todo") or (event or {}).get("on_todo"))
    side = owner_side(on_todo, stage, todo)
    if side == "ours":
        return "Us"
    if side == "program":
        return "Program"
    return "Unclear"


def _iso_day(value: object) -> str:
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()[:10]
    text = _text(value)
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    parsed = parse_mdy(text)
    return parsed.isoformat() if parsed else ""


def desired_fields(
    project: dict,
    event: dict | None,
    *,
    stall: str,
    today,
) -> dict[str, str]:
    """Field id -> value. Dates are omitted when we do not have one."""
    status = _text(project.get("status"))
    if status.lower() == "open":
        status = "Open"
    elif status.lower() in {"closed", "completed", "complete"}:
        status = "Closed"
    elif status.lower() in {"cancelled", "canceled"}:
        status = "Cancelled"
    program = program_option(project)
    trade = trade_ally_option(project)
    who = with_option(project, event)
    fields = {
        FIELD_ENROLLMENT_ID: _text(project.get("id")),
        FIELD_STEP: _text(project.get("step")),
        FIELD_STEP_STATUS: _text(project.get("stepStatus") or project.get("step_status")),
        FIELD_LAST_SYNCED: today.isoformat(),
        FIELD_STALL: stall,
    }
    if program in PROGRAM_OPTIONS:
        fields[FIELD_PROGRAM] = program
    if status in STATUS_OPTIONS:
        fields[FIELD_ENROLLMENT_STATUS] = status
    if who in WITH_OPTIONS:
        fields[FIELD_WITH] = who
    if trade in TRADE_OPTIONS:
        fields[FIELD_TRADE_ALLY] = trade
    due = _iso_day(project.get("due"))
    if due:
        fields[FIELD_DUE] = due
    since = _iso_day((event or {}).get("first_seen_at"))
    if since:
        fields[FIELD_STEP_SINCE] = since
    return fields


def changed_custom_fields(current: dict[str, str], desired: dict[str, str]) -> list[dict[str, str]]:
    changes = []
    for field_id, value in desired.items():
        previous = "" if current.get(field_id) is None else str(current.get(field_id)).strip()
        if previous == str(value).strip():
            continue
        changes.append({"id": field_id, "field_value": value})
    return changes


def mapped_stage_id(step: str) -> str:
    """Used only when auto-create is explicitly enabled. Shadow puts do not send it."""
    pos = NYHEP_STAGE_POS.get(_text(step))
    if pos is None:
        return ""
    for name, stage_id in GHL_STAGE_ID_BY_NAME.items():
        from metrics.empower_ids import GHL_STAGES

        if GHL_STAGES[pos][0] == name:
            return stage_id
    return ""


def _phoenix_day(now: datetime | None):
    moment = now or datetime.now(PHOENIX)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PHOENIX)
    return moment.astimezone(PHOENIX).date()


def run_shadow_sync(
    projects: list[dict],
    opps: list[dict],
    links: list[dict] | None = None,
    nyhep_events: list[dict] | None = None,
    *,
    contacts: dict[str, dict] | None = None,
    matches: list[dict] | None = None,
    open_ghl_events: dict | None = None,
    existing_links: dict[str, dict] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
    client: Callable[[str, str, dict | None], dict] | None = None,
    db=None,
    as_of=None,
) -> dict[str, Any]:
    """Plan or apply field puts, stage events, and link docs. Never moves a stage."""
    moment = now or datetime.now(PHOENIX)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PHOENIX)
    now_iso = moment.astimezone(PHOENIX).isoformat()
    today = _phoenix_day(moment)
    link_rows = list(links or [])
    if existing_links:
        for row in existing_links.values():
            if isinstance(row, dict):
                link_rows.append(row)
    changed_links = sync_links(projects, matches, opps, contacts, existing_links, now=now_iso)
    merged_links = { _text(row.get("enrollment_id")): row for row in link_rows if _text(row.get("enrollment_id")) }
    for _doc_id, body in changed_links:
        if body.get("enrollment_id"):
            merged_links[body["enrollment_id"]] = body

    events_by_enroll = {}
    for event in nyhep_events or []:
        if isinstance(event, dict) and event.get("ended_at") is None and _text(event.get("enrollment_id")):
            events_by_enroll[_text(event.get("enrollment_id"))] = event
    opps_by_id = {_opp_id(opp): opp for opp in opps if isinstance(opp, dict)}
    ghl_event_rows = []
    for pair in (open_ghl_events or {}).values():
        if isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[1], dict):
            ghl_event_rows.append(pair[1])
        elif isinstance(pair, dict):
            ghl_event_rows.append(pair)
    breaches = evaluate_jobs(
        projects,
        opps,
        list(merged_links.values()),
        nyhep_events,
        ghl_event_rows,
        as_of or today,
        snapshot_day=as_of,
        today=today,
    )
    puts = []
    skipped_auto = []
    auto_creates = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        enrollment_id = _text(project.get("id"))
        link = merged_links.get(enrollment_id) or {}
        if _text(project.get("status")).lower() not in {"open", "active", ""}:
            continue
        opp = opps_by_id.get(_text(link.get("opp_id"))) if link.get("status") == "linked" and not link.get("other_pipeline") else None
        if opp is None:
            orphan = (
                _text(project.get("status")).lower() in {"open", "active"}
                and not link.get("other_pipeline")
                and not _text(link.get("opp_id"))
                and not _text(link.get("contact_id"))
                and not _text(link.get("suggested_opp_id"))
            )
            if orphan:
                skipped_auto.append({"enrollmentId": enrollment_id, "reason": "auto_create_disabled"})
            continue
        stall = stall_summary(breaches, enrollment_id=enrollment_id, opp_id=_opp_id(opp))
        desired = desired_fields(project, events_by_enroll.get(enrollment_id), stall=stall, today=today)
        changes = changed_custom_fields(custom_field_map(opp.get("customFields")), desired)
        if not changes:
            continue
        body = {"customFields": changes}
        puts.append({"oppId": _opp_id(opp), "body": body})

    if auto_create_enabled():
        for project in projects:
            if not isinstance(project, dict):
                continue
            enrollment_id = _text(project.get("id"))
            link = merged_links.get(enrollment_id) or {}
            if link.get("status") == "linked" or link.get("contact_id") or link.get("opp_id"):
                continue
            if _text(project.get("status")).lower() not in {"open", "active"}:
                continue
            stage_id = mapped_stage_id(_text(project.get("step")))
            match = (match_matches_by_id(matches).get(enrollment_id) or {})
            create = {
                "enrollmentId": enrollment_id,
                "pipelineId": EMPOWER_PIPELINE_ID,
                "pipelineStageId": stage_id,
                "source": "NYHEP",
                "assignedTaskUser": USER_BROOKE,
                "hasTransientContact": bool(match.get("phone") or match.get("email") or match.get("name")),
            }
            auto_creates.append(create)
        skipped_auto = [row for row in skipped_auto if row["enrollmentId"] not in {item["enrollmentId"] for item in auto_creates}]

    enrollment_by_opp = {
        _text(body.get("opp_id")): _text(body.get("enrollment_id"))
        for body in merged_links.values()
        if body.get("status") == "linked" and body.get("opp_id") and not body.get("other_pipeline")
    }
    event_changes = diff_ghl_stage_events(
        open_ghl_events or {},
        opps,
        enrollment_by_opp,
        now_iso=now_iso,
        source="sync",
    )
    plan = {
        "dryRun": dry_run,
        "puts": puts,
        "autoCreates": auto_creates if auto_create_enabled() else [],
        "skippedAutoCreates": skipped_auto,
        "stageEvents": [{"id": doc_id, "body": body} for doc_id, body in event_changes],
        "links": [{"id": doc_id, "body": body} for doc_id, body in changed_links],
        "autoCreateEnabled": auto_create_enabled(),
    }
    if dry_run or client is None and db is None:
        return plan
    if not dry_run and client is not None:
        for put in puts:
            client("PUT", f"/opportunities/{put['oppId']}", put["body"])
        if auto_create_enabled():
            for create in auto_creates:
                client(
                    "POST",
                    "/opportunities/",
                    {
                        "pipelineId": create["pipelineId"],
                        "pipelineStageId": create["pipelineStageId"],
                        "locationId": os.environ.get("GHL_LOCATION_ID") or GHL_LOCATION_ID_DEFAULT,
                        "status": "open",
                        "source": "NYHEP",
                        "name": create["enrollmentId"],
                        "customFields": [{"id": FIELD_ENROLLMENT_ID, "field_value": create["enrollmentId"]}],
                    },
                )
                client(
                    "POST",
                    "/contacts/tasks",
                    {
                        "title": f"Review NYHEP enrollment {create['enrollmentId']}",
                        "assignedTo": USER_BROOKE,
                    },
                )
    if not dry_run and db is not None:
        persist_links(db, changed_links)
        for doc_id, body in event_changes:
            guarded_set(db, GHL_STAGE_EVENTS, doc_id, body)
    return plan


def ghl_http(method: str, path: str, body: dict | None, api_key: str) -> dict:
    """Live GHL call. Callers must not reach this without an explicit sync request."""
    import urllib.request

    if not api_key:
        raise RuntimeError("missing_env:GHL_API_KEY")
    url = GHL_BASE + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Version": GHL_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def after_ingest(db, cleaned: dict, matches: list | None) -> dict[str, int]:
    """Warehouse link and stage-event maintenance. No GHL writes unless explicitly enabled.

    An empty Empower+ warehouse and no transient matches write nothing, so a
    portal snapshot post stays the same shape.
    """
    projects = [row for row in (cleaned.get("projects") or []) if isinstance(row, dict)]
    opps = load_empower_opps(db)
    match_rows = matches or []
    open_events = load_open_ghl_events(db)
    if not match_rows and not opps and not open_events:
        return {"linkWrites": 0, "ghlStageEventWrites": 0}
    client = None
    # Ingest never calls GoHighLevel unless this flag is explicitly true.
    # The default is off, so a portal post cannot move or create opportunities.
    if shadow_on_ingest():
        api_key = os.environ.get("GHL_API_KEY") or ""
        if api_key:
            def client(method, path, body, api_key=api_key):
                return ghl_http(method, path, body, api_key)
    plan = run_shadow_sync(
        projects,
        opps,
        existing_links=load_links(db),
        open_ghl_events=open_events,
        matches=match_rows,
        dry_run=False,
        client=client,
        db=db,
    )
    return {
        "linkWrites": len(plan["links"]),
        "ghlStageEventWrites": len(plan["stageEvents"]),
        "ghlPuts": len(plan["puts"]) if client is not None else 0,
    }


def _wants_dry_run(path: str, body: dict) -> bool:
    query = parse_qs(urlparse(path).query)
    flag = (query.get("dry_run", [""])[0] or body.get("dry_run") or body.get("dryRun") or "")
    return str(flag).strip().lower() in {"1", "true", "yes"}


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("invalid_body")
    return payload


def _write(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    raw = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        from empower_portal import view_identity

        if view_identity(self.headers) is None:
            _write(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            body = _read_json(self)
        except Exception:
            _write(self, 400, {"ok": False, "error": "invalid_body"})
            return
        dry_run = _wants_dry_run(self.path, body)
        try:
            from empower_portal_ingest import get_db, load_latest
            from metrics.nyhep_stage_events import load_open_events

            db = get_db()
            latest = load_latest(db) or {}
            projects = latest.get("projects") or []
            opps = body.get("opportunities") if isinstance(body.get("opportunities"), list) else load_empower_opps(db)
            open_nyhep = load_open_events(db)
            nyhep_events = [row[1] for row in open_nyhep.values() if isinstance(row, tuple) and len(row) == 2]
            client = None
            if not dry_run:
                api_key = os.environ.get("GHL_API_KEY") or ""
                if not api_key:
                    _write(self, 500, {"ok": False, "error": "missing_env", "missing": ["GHL_API_KEY"]})
                    return

                def client(method, path, payload, api_key=api_key):
                    return ghl_http(method, path, payload, api_key)

            plan = run_shadow_sync(
                projects,
                opps,
                nyhep_events=nyhep_events,
                existing_links=load_links(db),
                open_ghl_events=load_open_ghl_events(db),
                matches=body.get("matches") if isinstance(body.get("matches"), list) else None,
                dry_run=dry_run,
                client=client,
                db=None if dry_run else db,
            )
        except Exception:
            _write(self, 500, {"ok": False, "error": "warehouse_unavailable"})
            return
        _write(self, 200, {"ok": True, "plan": plan})


Handler = handler
