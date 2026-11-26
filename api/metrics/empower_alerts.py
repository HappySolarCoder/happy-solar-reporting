# -*- coding: utf-8 -*-

"""Stall rules, alert documents, and the daily digest body.

Alerts pause when the NYHEP snapshot is more than one business day old.
Text channels stay off unless EMPOWER_INTERNAL_TEXTS_ENABLED is true.
Nothing here writes a funnel collection or sends mail by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from metrics.empower_ids import (
    FIELD_AUDIT_DATE,
    FIELD_FUNDED_DATE,
    FIELD_INSTALL_DATE,
    GHL_STAGE_NAME,
    OWNER_USER_IDS,
)
from metrics.empower_linker import (
    _opp_id,
    _pipeline_id,
    _stage_id,
    _text,
    custom_field_map,
    is_empower_opp,
)
from metrics.nyhep_stage_events import business_days, calendar_days, parse_mdy


PHOENIX = ZoneInfo("America/Phoenix")


def alert_doc_id(rule_id: str, entity_key: str) -> str:
    return hashlib.sha1(f"{rule_id}|{entity_key}".encode("utf-8")).hexdigest()[:20]


def parse_day(value: object) -> date | None:
    text = _text(value)
    if len(text) >= 10 and text[4] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return parse_mdy(text)


def _day_from_iso(value: object) -> date | None:
    return parse_day(value)


def alerts_enabled() -> bool:
    return _text(os.environ.get("EMPOWER_ALERTS_ENABLED")).lower() == "true"


def texts_enabled() -> bool:
    return _text(os.environ.get("EMPOWER_INTERNAL_TEXTS_ENABLED")).lower() == "true"


def snapshot_is_stale(as_of: date | None, today: date | None) -> bool:
    if as_of is None or today is None:
        return False
    return business_days(as_of, today) > 1


def _owner(role: str) -> tuple[str, str]:
    return role, OWNER_USER_IDS.get(role, "")


def _breach(
    rule_id: str,
    severity: str,
    subject: dict,
    role: str,
    channels: list[str],
    summary: str,
    *,
    copy_roles: list[str] | None = None,
) -> dict[str, Any]:
    owner_role, owner_user_id = _owner(role)
    return {
        "rule_id": rule_id,
        "severity": severity,
        "entity_key": subject.get("entity_key") or "",
        "opp_id": subject.get("opp_id") or "",
        "enrollment_id": subject.get("enrollment_id") or "",
        "customer": subject.get("customer") or "",
        "owner_role": owner_role,
        "owner_user_id": owner_user_id,
        "channels": list(channels),
        "summary": summary,
        "copy_roles": list(copy_roles or []),
    }


def _ghl_name(subject: dict) -> str:
    return _text(subject.get("ghl_stage_name"))


def _nyhep(subject: dict) -> str:
    return _text(subject.get("nyhep_stage"))


def _in_stage(subject: dict, *names: str) -> bool:
    current = {_ghl_name(subject), _nyhep(subject)}
    return any(name in current for name in names)


def evaluate_subject(subject: dict, as_of: date) -> list[dict]:
    """Rules for one open job. Stage rules do not stack on the same subject."""
    start = subject.get("stage_start")
    enrolled = subject.get("enrolled")
    stage_cal = calendar_days(start if isinstance(start, date) else None, as_of)
    stage_bd = business_days(start if isinstance(start, date) else None, as_of)
    enrolled_cal = calendar_days(enrolled if isinstance(enrolled, date) else None, as_of)
    breaches: list[dict] = []

    audit = subject.get("audit_date")
    due = subject.get("due")
    if isinstance(audit, date) and isinstance(due, date) and audit > due:
        breaches.append(
            _breach(
                "audit_after_due",
                "red",
                subject,
                "steven",
                ["text", "task"],
                "Booked audit date is after the NYHEP workscope due date",
                copy_roles=["tyler"],
            )
        )

    if _in_stage(subject, "Portal Creation Needed"):
        missing_owner = not _text(subject.get("assigned_to"))
        if (missing_owner and stage_bd >= 1) or stage_cal > 3:
            role = "brooke" if stage_cal >= 7 else "rep"
            severity = "red" if stage_cal >= 7 else "warn"
            breaches.append(
                _breach(
                    "lead_intake",
                    severity,
                    subject,
                    role,
                    ["task", "digest"],
                    "Lead intake is past its owner or stage limit",
                )
            )
        return breaches

    if _in_stage(subject, "Income Documents Needed"):
        if stage_cal > 7:
            role = "brooke" if stage_cal >= 14 else "rep"
            breaches.append(
                _breach(
                    "income_documents",
                    "red" if stage_cal >= 14 else "warn",
                    subject,
                    role,
                    ["task", "digest"],
                    "Income documents are past the stage limit",
                )
            )
        return breaches

    if _in_stage(subject, "Awaiting Income Qualification"):
        if stage_cal > 14 and not _text(subject.get("enrollment_id")):
            breaches.append(
                _breach(
                    "income_qualification",
                    "warn",
                    subject,
                    "brooke",
                    ["digest"],
                    "Income qualification has no NYHEP enrollment after 14 days",
                )
            )
        return breaches

    if _in_stage(subject, "Contractor Assignment", "Waiting on Assignment"):
        if stage_cal > 14:
            breaches.append(
                _breach(
                    "contractor_assignment",
                    "warn",
                    subject,
                    "brooke",
                    ["digest"],
                    "Contractor assignment is past 14 days",
                )
            )
        return breaches

    if _in_stage(subject, "Enrollment Acceptance", "Enrollment Accepted"):
        on_todo = bool(subject.get("on_todo")) or _ghl_name(subject) == "Enrollment Accepted"
        if on_todo:
            severity = "red" if stage_bd >= 3 else "warn"
            channels = ["text", "task"] if stage_bd >= 3 else ["task"]
            breaches.append(
                _breach(
                    "enrollment_acceptance",
                    severity,
                    subject,
                    "brooke",
                    channels,
                    "Enrollment acceptance is still on the to-do list",
                )
            )
        return breaches

    if _in_stage(subject, "Audit Confirmed") or (
        _nyhep(subject) == "Workscope Submission" and _text(subject.get("step_status")).lower() == "new"
    ):
        if not isinstance(audit, date) and stage_bd >= 5:
            breaches.append(
                _breach(
                    "audit_unbooked",
                    "red",
                    subject,
                    "steven",
                    ["text", "task"],
                    "No audit booked 5 business days after acceptance",
                    copy_roles=["tyler"],
                )
            )
        return breaches

    if _in_stage(subject, "Workscope Submission", "Workscope Submitted"):
        span = enrolled_cal or stage_cal
        if span >= 20:
            severity = "red" if span >= 25 else "warn"
            channels = ["text", "task"] if span >= 25 else ["task"]
            label = "Workscope submission is at the 30 day portal mark" if span >= 30 else "Workscope submission is past the warn day"
            breaches.append(
                _breach("workscope_submitted", severity, subject, "steven", channels, label, copy_roles=["tyler"])
            )
        return breaches

    if _in_stage(subject, "Workscope Review", "Provisional Approval", "With Program – Workscope Review"):
        if stage_bd > 5:
            breaches.append(
                _breach(
                    "workscope_review",
                    "warn",
                    subject,
                    "brooke",
                    ["digest"],
                    "Workscope review is past 5 business days",
                )
            )
        return breaches

    if _in_stage(subject, "Final Project Submission", "Install Scheduled", "Install Started"):
        install = subject.get("install_date")
        late_schedule = not isinstance(install, date) and stage_cal >= 14
        span = enrolled_cal or stage_cal
        if late_schedule or span >= 60:
            severity = "red" if span >= 75 else "warn"
            breaches.append(
                _breach(
                    "install_scheduled",
                    severity,
                    subject,
                    "tyler",
                    ["task", "digest"],
                    "Install is unscheduled or the final submission is past its day count",
                )
            )
        return breaches

    if _in_stage(subject, "Install Complete", "Close Out Photos Complete"):
        install = subject.get("install_date")
        if isinstance(install, date) and business_days(install, as_of) > 5:
            breaches.append(
                _breach(
                    "install_closeout",
                    "warn",
                    subject,
                    "tyler",
                    ["task"],
                    "Work complete is not processed 5 business days after install",
                    copy_roles=["brooke"],
                )
            )
        return breaches

    if _in_stage(subject, "Final Project Review", "Final Technical Review", "With Program – Final Review"):
        if stage_bd > 5:
            breaches.append(
                _breach(
                    "final_review",
                    "warn",
                    subject,
                    "brooke",
                    ["digest"],
                    "Final review is past 5 business days",
                )
            )
        return breaches

    if _in_stage(subject, "Funding Allocations", "Installation Funding Allocations", "Funding Allocated"):
        if stage_cal > 14:
            breaches.append(
                _breach(
                    "funding",
                    "warn",
                    subject,
                    "tyler",
                    ["digest"],
                    "Funding allocation is past 14 days",
                )
            )
        return breaches

    if _in_stage(subject, "Payment", "Paid"):
        funded = subject.get("funded_date") or start
        if isinstance(funded, date) and calendar_days(funded, as_of) >= 30:
            breaches.append(
                _breach(
                    "paid",
                    "red",
                    subject,
                    "tyler",
                    ["digest", "text"],
                    "Payment is not confirmed 30 days after funding",
                    copy_roles=["evan"],
                )
            )
    return breaches


def _subject_from_parts(project: dict | None, opp: dict | None, nyhep_event: dict | None, ghl_event: dict | None) -> dict | None:
    project = project or {}
    opp = opp or {}
    enrollment_id = _text(project.get("id") or (nyhep_event or {}).get("enrollment_id"))
    opp_id = _opp_id(opp)
    if not enrollment_id and not opp_id:
        return None
    status = _text(project.get("status") or (nyhep_event or {}).get("enrollment_status") or "Open")
    if project and status.lower() not in {"open", "active"}:
        return None
    if opp and _text(opp.get("status") or "open").lower() not in {"open", ""}:
        return None
    if opp and _pipeline_id(opp) and not is_empower_opp(opp):
        return None
    fields = custom_field_map(opp.get("customFields"))
    stage_name = ""
    stage_id = _stage_id(opp)
    if stage_id:
        stage_name = GHL_STAGE_NAME.get(stage_id, "")
    nyhep_stage = _text(project.get("step") or (nyhep_event or {}).get("stage"))
    start = _day_from_iso((nyhep_event or {}).get("first_seen_at")) or _day_from_iso((ghl_event or {}).get("first_seen_at"))
    if start is None:
        start = _day_from_iso(opp.get("createdAt") or opp.get("created_at"))
    return {
        "entity_key": enrollment_id or opp_id,
        "enrollment_id": enrollment_id,
        "opp_id": opp_id,
        "customer": _text(project.get("customer") or (nyhep_event or {}).get("customer")),
        "nyhep_stage": nyhep_stage,
        "ghl_stage_name": stage_name,
        "ghl_stage_id": stage_id,
        "step_status": _text(project.get("stepStatus") or project.get("step_status") or (nyhep_event or {}).get("step_status")),
        "on_todo": bool(project.get("onTodo") or project.get("on_todo") or (nyhep_event or {}).get("on_todo")),
        "assigned_to": _text(opp.get("assignedTo") or opp.get("assigned_to") or (ghl_event or {}).get("assigned_to")),
        "stage_start": start,
        "enrolled": parse_day(project.get("enrolled")),
        "due": parse_day(project.get("due") or (nyhep_event or {}).get("due_date")),
        "audit_date": parse_day(project.get("auditDate") or project.get("audit_date") or fields.get(FIELD_AUDIT_DATE)),
        "install_date": parse_day(project.get("installDate") or project.get("install_date") or fields.get(FIELD_INSTALL_DATE)),
        "funded_date": parse_day(project.get("fundedDate") or project.get("funded_date") or fields.get(FIELD_FUNDED_DATE)),
    }


def evaluate_jobs(
    projects: list[dict] | None,
    opps: list[dict] | None,
    links: list[dict] | None,
    nyhep_events: list[dict] | None,
    ghl_events: list[dict] | None,
    as_of: date,
    *,
    today: date | None = None,
    snapshot_day: date | None = None,
) -> list[dict]:
    """Evaluate open NYHEP enrollments and open Empower+ opportunities."""
    if snapshot_is_stale(snapshot_day, today or as_of):
        return []
    link_by_enroll = {}
    for link in links or []:
        if isinstance(link, dict) and _text(link.get("enrollment_id")):
            link_by_enroll[_text(link.get("enrollment_id"))] = link
    opps_by_id = {}
    for opp in opps or []:
        if isinstance(opp, dict) and _opp_id(opp):
            opps_by_id[_opp_id(opp)] = opp
    nyhep_open = {}
    for event in nyhep_events or []:
        if isinstance(event, dict) and event.get("ended_at") is None and _text(event.get("enrollment_id")):
            nyhep_open[_text(event.get("enrollment_id"))] = event
    ghl_open = {}
    for event in ghl_events or []:
        if isinstance(event, dict) and event.get("ended_at") is None and _text(event.get("opp_id")):
            ghl_open[_text(event.get("opp_id"))] = event

    subjects = []
    seen_opps: set[str] = set()
    for project in projects or []:
        if not isinstance(project, dict):
            continue
        enrollment_id = _text(project.get("id"))
        link = link_by_enroll.get(enrollment_id) or {}
        opp_id = _text(link.get("opp_id"))
        opp = opps_by_id.get(opp_id)
        if opp_id:
            seen_opps.add(opp_id)
        subject = _subject_from_parts(project, opp, nyhep_open.get(enrollment_id), ghl_open.get(opp_id))
        if subject is not None:
            subjects.append(subject)
    for opp in opps or []:
        if not isinstance(opp, dict) or not is_empower_opp(opp):
            continue
        opp_id = _opp_id(opp)
        if not opp_id or opp_id in seen_opps:
            continue
        subject = _subject_from_parts(None, opp, None, ghl_open.get(opp_id))
        if subject is not None:
            subjects.append(subject)

    breaches = []
    seen_rules: set[tuple[str, str]] = set()
    for subject in subjects:
        for breach in evaluate_subject(subject, as_of):
            key = (breach["rule_id"], breach["entity_key"])
            if key in seen_rules:
                continue
            seen_rules.add(key)
            breaches.append(breach)
    return breaches


def stall_summary(breaches: list[dict], *, enrollment_id: str = "", opp_id: str = "") -> str:
    lines = []
    for breach in breaches:
        if enrollment_id and breach.get("enrollment_id") != enrollment_id:
            continue
        if opp_id and not enrollment_id and breach.get("opp_id") not in {opp_id, ""}:
            continue
        text = _text(breach.get("summary"))
        if text and text not in lines:
            lines.append(text)
    return "; ".join(lines)


def apply_alerts(
    open_alerts: dict[str, tuple[str, dict]],
    breaches: list[dict],
    now_iso: str,
    *,
    task_creator: Callable[[dict], str] | None = None,
    texts_on: bool = False,
) -> list[tuple[str, dict]]:
    """Update one active doc per rule and entity. An open task is not created again."""
    changed: list[tuple[str, dict]] = []
    active_ids: set[str] = set()
    for breach in breaches:
        doc_id = alert_doc_id(breach["rule_id"], breach["entity_key"])
        active_ids.add(doc_id)
        previous = open_alerts.get(doc_id)
        prior = previous[1] if previous else None
        if isinstance(prior, dict) and prior.get("resolved_at") is None and prior.get("ghl_task_id"):
            updated = dict(prior)
            updated["last_fired_at"] = now_iso
            updated["severity"] = breach["severity"]
            updated["summary"] = breach["summary"]
            changed.append((doc_id, updated))
            continue
        reopened = isinstance(prior, dict) and prior.get("resolved_at") is not None
        body = dict(prior or {})
        body.update(
            {
                "rule_id": breach["rule_id"],
                "severity": breach["severity"],
                "entity_key": breach["entity_key"],
                "opp_id": breach.get("opp_id") or "",
                "enrollment_id": breach.get("enrollment_id") or "",
                "customer": breach.get("customer") or "",
                "owner_role": breach["owner_role"],
                "owner_user_id": breach["owner_user_id"],
                "first_fired_at": now_iso if prior is None or reopened else prior.get("first_fired_at") or now_iso,
                "last_fired_at": now_iso,
                "resolved_at": None,
                "channels_sent": list(prior.get("channels_sent") or []) if prior and not reopened else [],
                "ghl_task_id": "" if prior is None or reopened else prior.get("ghl_task_id") or "",
                "summary": breach["summary"],
            }
        )
        wants_task = "task" in breach.get("channels", []) or (texts_on and "text" in breach.get("channels", []))
        if wants_task and not body.get("ghl_task_id") and task_creator is not None:
            body["ghl_task_id"] = _text(task_creator(body)) or body.get("ghl_task_id") or ""
            sent = list(body.get("channels_sent") or [])
            if "task" in breach.get("channels", []) and "task" not in sent:
                sent.append("task")
            if texts_on and "text" in breach.get("channels", []) and "text" not in sent:
                sent.append("text")
            body["channels_sent"] = sent
        elif "digest" in breach.get("channels", []):
            sent = list(body.get("channels_sent") or [])
            if "digest" not in sent:
                sent.append("digest")
            body["channels_sent"] = sent
        changed.append((doc_id, body))

    for doc_id, (_stored_id, previous) in open_alerts.items():
        if doc_id in active_ids or previous.get("resolved_at") is not None:
            continue
        resolved = dict(previous)
        resolved["resolved_at"] = now_iso
        changed.append((doc_id, resolved))
    return changed


def recipient_map(raw: str | None = None, users: list[dict] | None = None) -> dict[str, list[str]]:
    """Env JSON wins. Otherwise read email off ghl user rows. No personal addresses are hardcoded."""
    text = raw if raw is not None else os.environ.get("EMPOWER_DIGEST_RECIPIENTS_JSON") or ""
    if text.strip():
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}
        found = {}
        for role, emails in parsed.items():
            if isinstance(emails, str):
                emails = [emails]
            if isinstance(emails, list):
                found[str(role).strip().lower()] = [item.strip() for item in emails if isinstance(item, str) and item.strip()]
        return found
    found: dict[str, list[str]] = {}
    by_id = {}
    for user in users or []:
        if isinstance(user, dict):
            by_id[_text(user.get("id"))] = user
    for role, user_id in OWNER_USER_IDS.items():
        user = by_id.get(user_id) or {}
        email = _text(user.get("email"))
        if email:
            found[role] = [email]
    return found


def _items_for(role: str, alerts: list[dict]) -> list[dict]:
    if role in {"tyler", "evan"}:
        return list(alerts)
    return [row for row in alerts if row.get("owner_role") == role]


def _esc(value: object) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_digest_messages(
    alerts: list[dict],
    *,
    as_of: date,
    recipients: dict[str, list[str]],
    stage_counts: dict[str, int] | None = None,
    from_address: str | None = None,
) -> list[dict[str, Any]]:
    """One Resend message per person. Adam gets Monday stage counts only."""
    sender = from_address or os.environ.get("EMPOWER_DIGEST_FROM") or "EmPower+ Alerts <alerts@example.com>"
    active = [row for row in alerts if isinstance(row, dict) and row.get("resolved_at") is None]
    messages = []
    subject = f"EmPower+ digest {as_of.isoformat()}"
    for role in ("steven", "brooke", "tyler", "evan"):
        emails = recipients.get(role) or []
        if not emails:
            continue
        rows = _items_for(role, active)
        items = "".join(
            f"<li><b>{_esc(row.get('severity'))}</b> {_esc(row.get('customer') or row.get('entity_key'))}: {_esc(row.get('summary'))}</li>"
            for row in rows
        ) or "<li>No open items.</li>"
        html = f"<h1>{_esc(subject)}</h1><p>Items for {_esc(role)}.</p><ul>{items}</ul>"
        messages.append(
            {
                "role": role,
                "from": sender,
                "to": emails,
                "subject": subject,
                "html": html,
            }
        )
    if as_of.weekday() == 0 and (recipients.get("adam") or []):
        counts = stage_counts or {}
        lines = "".join(f"<li>{_esc(name)}: {int(count)}</li>" for name, count in sorted(counts.items()))
        html = f"<h1>EmPower+ weekly stage counts {as_of.isoformat()}</h1><ul>{lines or '<li>No open stages.</li>'}</ul>"
        messages.append(
            {
                "role": "adam",
                "from": sender,
                "to": recipients["adam"],
                "subject": f"EmPower+ weekly stage counts {as_of.isoformat()}",
                "html": html,
            }
        )
    return messages


def resend_payload(message: dict) -> dict[str, Any]:
    return {
        "from": message["from"],
        "to": list(message["to"]),
        "subject": message["subject"],
        "html": message["html"],
    }


def send_resend(message: dict, *, api_key: str, transport: Callable[[dict], dict] | None = None) -> dict:
    """POST https://api.resend.com/emails. Fail closed when the key is missing."""
    if not api_key:
        raise RuntimeError("missing_env:RESEND_API_KEY")
    payload = resend_payload(message)
    if transport is not None:
        return transport(payload)
    import urllib.request

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def deliver_digest(
    alerts: list[dict],
    *,
    as_of: date,
    recipients: dict[str, list[str]],
    stage_counts: dict[str, int] | None = None,
    dry_run: bool = True,
    send: bool = False,
    transport: Callable[[dict], dict] | None = None,
) -> dict[str, Any]:
    messages = build_digest_messages(alerts, as_of=as_of, recipients=recipients, stage_counts=stage_counts)
    payloads = [resend_payload(message) for message in messages]
    if dry_run or not send:
        return {"ok": True, "dryRun": True, "sent": 0, "messages": messages, "payloads": payloads}
    if not alerts_enabled():
        return {"ok": False, "error": "alerts_disabled", "sent": 0, "messages": messages, "payloads": payloads}
    api_key = os.environ.get("RESEND_API_KEY") or ""
    if not api_key:
        return {
            "ok": False,
            "error": "missing_env",
            "missing": ["RESEND_API_KEY"],
            "sent": 0,
            "messages": messages,
            "payloads": payloads,
        }
    sent = 0
    receipts = []
    for message in messages:
        receipts.append(send_resend(message, api_key=api_key, transport=transport))
        sent += 1
    return {"ok": True, "dryRun": False, "sent": sent, "messages": messages, "receipts": receipts}
