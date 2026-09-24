# -*- coding: utf-8 -*-

"""Vercel function: /api/private/fma_payroll

Sat demos for one Thu–Wed week, credited to the FMA (setter), plus
scheduling-manager payout. Sit membership is demo_rate's shared helpers.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parents[1]
METRICS_DIR = API_DIR / "metrics"
PRIVATE_DIR = Path(__file__).resolve().parent
for _path in (str(METRICS_DIR), str(PRIVATE_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import demo_rate
from fma_payroll_logic import (
    LEAD_GEN_SOURCE_CF,
    SCHEDULING_MANAGER_CF,
    SETTER_LAST_NAME_CF,
    SETTER_NAME_CF,
    build_payroll_payload,
    compact,
    is_blank_token,
    resolve_setter_last_name,
    resolve_week,
    today_et,
)
from payroll_gate import access_decision, send_json

GHL_APP_ORIGIN = "https://app.gohighlevel.com"
DEFAULT_GHL_LOCATION_ID = "MMKRDviKggXzlcHQTnvZ"
WEEK_ERROR = "week_start must be a Thursday (YYYY-MM-DD)"


def _cf_text(record: dict | None, cf_id: str, *, opportunity: bool = False) -> str:
    if not isinstance(record, dict):
        return ""
    if opportunity:
        raw = demo_rate.opportunity_custom_field(record, cf_id)
    else:
        raw = demo_rate.contact_custom_field(record, cf_id)
    return compact(raw)


def _assigned_user_id(opp: dict) -> str:
    raw = opp.get("assignedTo")
    if isinstance(raw, dict):
        return compact(raw.get("id") or raw.get("userId"))
    return compact(raw)


def _looks_like_id(value: str) -> bool:
    return bool(value) and " " not in value and len(value) >= 12 and all(ch.isalnum() or ch in "-_" for ch in value)


def _owner_name(user: dict | None, opp: dict) -> str:
    if isinstance(user, dict):
        for key in ("name", "displayName", "fullName"):
            text = compact(user.get(key))
            if text and not is_blank_token(text):
                return text
        joined = compact(f"{user.get('firstName') or ''} {user.get('lastName') or ''}")
        if joined and not is_blank_token(joined):
            return joined
    for key in ("assignedToName", "assignedToUserName", "assignedUserName", "ownerName"):
        text = compact(opp.get(key))
        if text and not is_blank_token(text) and not _looks_like_id(text):
            return text
    return ""


def _customer_name(contact: dict | None, opp: dict) -> str:
    if isinstance(contact, dict):
        joined = compact(f"{contact.get('firstName') or ''} {contact.get('lastName') or ''}")
        if joined:
            return joined
        for key in ("name", "contactName", "fullName"):
            text = compact(contact.get(key))
            if text:
                return text
    return compact(opp.get("name"))


def _location_id(opp: dict, contact: dict | None) -> str:
    import os

    candidates = [opp.get("locationId")]
    if isinstance(contact, dict):
        candidates.append(contact.get("locationId"))
    candidates.append(os.environ.get("GHL_LOCATION_ID"))
    candidates.append(DEFAULT_GHL_LOCATION_ID)
    for raw in candidates:
        text = compact(raw)
        if text:
            return text
    return ""


def _ghl_urls(opp: dict, contact: dict | None, opp_id: str, contact_id: str) -> tuple[str | None, str | None]:
    loc = _location_id(opp, contact)
    if not loc:
        return None, None
    opp_url = None
    contact_url = None
    if opp_id:
        opp_url = (
            f"{GHL_APP_ORIGIN}/v2/location/{loc}/opportunities/list/{opp_id}?tab=OpportunityDetails"
        )
    if contact_id:
        contact_url = f"{GHL_APP_ORIGIN}/v2/location/{loc}/contacts/detail/{contact_id}"
    return opp_url, contact_url


def load_users_by_ids(db: Any, user_ids) -> dict[str, dict]:
    """Bounded ghl_users_v2 get_all for assignedTo ids. No full-collection stream."""
    users: dict[str, dict] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in user_ids:
        uid = compact(raw)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        needed.append(uid)
    if not needed:
        return users
    refs = [db.collection("ghl_users_v2").document(uid) for uid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            for key in {compact(data.get("id")), compact(data.get("userId")), compact(snap.id)}:
                if key:
                    users[key] = data
    for uid in needed:
        if uid in users:
            continue
        misses = list(db.collection("ghl_users_v2").where("id", "==", uid).limit(1).stream())
        if misses:
            users[uid] = misses[0].to_dict() or {}
    return users


def collect_sits(db: Any, week_start, week_end) -> list[dict[str, Any]]:
    contract = demo_rate.MetricContract()
    start_local, end_local, _start_iso, _end_iso = demo_rate.date_range_window(
        week_start.isoformat(),
        week_end.isoformat(),
        contract.timezone,
    )
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    snaps = demo_rate.load_demo_rate_snaps(db, contract, start_utc, end_utc)

    contact_ids = []
    pipeline_ids = []
    user_ids = []
    opps: list[tuple[Any, dict]] = []
    for snap in snaps:
        opp = snap.to_dict() or {}
        opps.append((snap, opp))
        cid = compact(opp.get("contactId"))
        if cid:
            contact_ids.append(cid)
        pipeline_ids.extend(demo_rate.pipeline_id_keys(opp.get("pipelineId")))
        uid = _assigned_user_id(opp)
        if uid:
            user_ids.append(uid)

    pipelines = demo_rate.pipeline_name_lookup(db, pipeline_ids)
    contacts = demo_rate.load_contacts_by_ids(db, contact_ids)
    users = load_users_by_ids(db, user_ids)

    sits: list[dict[str, Any]] = []
    for snap, opp in opps:
        pname = demo_rate.resolve_pipeline_name(pipelines, opp.get("pipelineId"), fallback="").strip()
        if not demo_rate.pipeline_in_demo_scope(pname.lower(), contract):
            continue
        windowed = demo_rate.frozen_disposition_local(opp, contract, start_local, end_local, now_utc)
        if not windowed:
            continue
        local_dt, dispo = windowed
        if dispo != "Sit":
            continue

        contact_id = compact(opp.get("contactId"))
        contact = contacts.get(contact_id) or {}
        user = users.get(_assigned_user_id(opp)) or None
        setter = resolve_setter_last_name(
            [
                _cf_text(contact, SETTER_LAST_NAME_CF),
                _cf_text(opp, SETTER_LAST_NAME_CF, opportunity=True),
            ],
            [
                _cf_text(contact, SETTER_NAME_CF),
                _cf_text(opp, SETTER_NAME_CF, opportunity=True),
            ],
        )
        lead = _cf_text(contact, LEAD_GEN_SOURCE_CF)
        manager = _cf_text(contact, SCHEDULING_MANAGER_CF)
        opp_id = compact(opp.get("id") or getattr(snap, "id", ""))
        opp_url, contact_url = _ghl_urls(opp, contact, opp_id, contact_id)
        sits.append(
            {
                "opportunity_id": opp_id,
                "contact_id": contact_id,
                "customer_name": _customer_name(contact, opp),
                "sat_date": local_dt.date().isoformat(),
                "pipeline": pname,
                "lead_source": lead,
                "owner_name": _owner_name(user, opp),
                "setter_last_name": setter,
                "scheduling_manager": manager,
                "ghl_opportunity_url": opp_url,
                "ghl_contact_url": contact_url,
            }
        )
    return sits


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        decision = access_decision(self.headers)
        if decision == "unset":
            send_json(self, 503, {"error": "unavailable"})
            return
        if decision != "ok":
            send_json(self, 401, {"error": "unauthorized"})
            return
        try:
            qs = parse_qs(urlparse(self.path).query)
            raw_week = (qs.get("week_start") or [None])[0]
            start, end = resolve_week(raw_week, today_et())
            db = demo_rate.get_db()
            sits = collect_sits(db, start, end)
            payload = build_payroll_payload(sits, start, end, today=today_et())
            send_json(self, 200, payload)
        except ValueError:
            send_json(self, 400, {"error": WEEK_ERROR})
        except Exception as exc:
            send_json(self, 500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
