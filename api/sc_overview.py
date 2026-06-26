# -*- coding: utf-8 -*-

"""Vercel Python function: /api/sc_overview

SC Overview (admin-only)

Purpose:
- Evaluate sales rep performance with completed appointment outcomes and sales.
- Filters: Team, Sales Rep, month/date window.
- Default: company overview (all reps).

Canonical metric alignment:
- Completed appointment outcomes / Opps Ran / Demos use appointmentOccurredAt windows.
- Sales use Sold Date windows.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from zoneinfo import ZoneInfo

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from google.cloud import firestore
from google.oauth2 import service_account
from dashboard_nav import dashboard_nav_css, render_dashboard_loader

TZ = ZoneInfo("America/New_York")

OWNER_NAME_OVERRIDES = {
    "0fhsjcmlntce0cpjyfhj": "William Breen",
}

TEAM_OPTIONS = ["buffalo", "rochester", "syracuse", "virtual"]
LEAD_SOURCE_OPTIONS = ["Doors", "Self Gen", "Phones", "3PL/Inbound"]
SETTER_LAST_NAME_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"
SETTER_LAST_NAME_FALLBACK_FIELD_ID = "Xhy6k4xfHRJ6s5IbfA5x"
DISPOSITION_NOTES_FIELD_ID = "cCcnzoIp8YgW2Pr0sB5E"
TOUCH_PIPELINE_STALE_DAYS = 7
SALE_STAGE_IDS = {
    "7981f111-73f2-4593-9662-6b95d99bf51a",
    "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
    "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
    "34a1882f-7959-4d22-878d-91fe35a42907",
    "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
    "9bd71abf-7285-47bb-8800-a255e7b90630",
    "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
    "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
}
SOLD_DATE_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"
LEAD_SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"


@dataclass(frozen=True)
class RepRosterEntry:
    owner_id: str
    display_name: str
    team: str
    person_key: str


def _unauthorized(h: BaseHTTPRequestHandler):
    h.send_response(401)
    h.send_header('WWW-Authenticate', 'Basic realm="Happy Solar Settings"')
    h.send_header('Content-Type', 'text/plain; charset=utf-8')
    h.end_headers()
    h.wfile.write(b'Unauthorized')


def _check_auth(h: BaseHTTPRequestHandler) -> bool:
    pw = os.environ.get("SETTINGS_PASSWORD")
    if not pw:
        return False

    auth = h.headers.get("Authorization") or ""
    if not auth.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        _user, pwd = raw.split(":", 1)
        return pwd == pw
    except Exception:
        return False


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def looks_like_identifier(value: Any) -> bool:
    text = compact_str(value)
    if not text or " " in text or len(text) < 12:
        return False
    return all(ch.isalnum() or ch in {"-", "_"} for ch in text)


def best_person_name(record: dict[str, Any] | None, *, fallback: str = "") -> str:
    if not isinstance(record, dict):
        return fallback
    candidates = [
        record.get("name"),
        record.get("displayName"),
        record.get("fullName"),
        " ".join(part for part in (compact_str(record.get("firstName")), compact_str(record.get("lastName"))) if part),
        record.get("firstName"),
        record.get("lastName"),
        record.get("userName"),
        record.get("agentName"),
    ]
    for candidate in candidates:
        text = compact_str(candidate)
        if text and not looks_like_identifier(text):
            return text
    return fallback


def normalize_team(value: Any) -> str:
    raw = compact_str(value).lower()
    if raw in TEAM_OPTIONS:
        return raw
    return ""


def normalize_disposition(value: Any) -> str:
    if value is None:
        return ""
    text = compact_str(value)
    if not text:
        return ""
    low = text.lower().replace("_", " ").replace("-", " ")
    while "  " in low:
        low = low.replace("  ", " ")
    if low == "nosit":
        low = "no sit"
    if low == "sit":
        return "Sit"
    if low == "no sit":
        return "No Sit"
    return text


def normalize_completed_outcome_bucket(pipeline_name: Any, stage_name: Any) -> str:
    pipeline = compact_str(pipeline_name)
    stage = compact_str(stage_name)
    pipeline_low = pipeline.lower()
    stage_low = stage.lower().replace("_", " ").replace("-", " ")
    while "  " in stage_low:
        stage_low = stage_low.replace("  ", " ")

    if pipeline_low in {"rehash", "sweeper"}:
        if any(token in stage_low for token in {"rehash", "no show", "no-show", "pre cancel", "precancel"}):
            return "No Show/Pre-cancelled"
        if any(
            token in stage_low
            for token in {"reschedule", "re schedule", "re-schedule", "re set", "reset", "re-set", "sweeper"}
        ):
            return "Reschedule Needed"

    if any(token in stage_low for token in {"no show/pre cancel", "no show/pre-cancel", "no show/precancel"}):
        return "No Show/Pre-cancelled"
    if "needs reschedule" in stage_low:
        return "Reschedule Needed"

    return stage or "Unknown Stage"


def normalize_stage_text(value: Any) -> str:
    text = compact_str(value).lower().replace("_", " ").replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def is_new_appointment_stage(stage_name: Any) -> bool:
    stage_low = normalize_stage_text(stage_name)
    return stage_low == "new appointment"


def is_rescheduled_stage(stage_name: Any) -> bool:
    stage_low = normalize_stage_text(stage_name)
    if not stage_low:
        return False
    return "reschedule" in stage_low or stage_low == "rescheduled"


def is_sale_stage(stage_id: Any, stage_name: Any) -> bool:
    sid = compact_str(stage_id)
    if sid in SALE_STAGE_IDS:
        return True
    stage_low = normalize_stage_text(stage_name)
    return "sold" in stage_low or "sale cancelled" in stage_low or "sale canceled" in stage_low


def is_touch_close_stage(stage_name: Any) -> bool:
    stage_low = normalize_stage_text(stage_name)
    if not stage_low:
        return False
    return (
        "demo negotiating" in stage_low
        or "demo not interested" in stage_low
        or "one legger" in stage_low
    )


def is_touch_close_pipeline(pipeline_name: Any) -> bool:
    pipeline_low = compact_str(pipeline_name).lower()
    return pipeline_low in {"rehash", "sweeper"}


def normalize_lead_source(value: Any) -> str:
    if value is None:
        return "none"
    text = compact_str(value)
    if not text:
        return "none"
    low = text.lower()
    if low in {"crm ui", "hand", "manual", "none", "null", "n/a"}:
        return "none"
    if low in {"doors", "door", "d2d"}:
        return "Doors"
    if low in {"self gen", "selfgen", "self-gen"}:
        return "Self Gen"
    if low in {"phones", "phone", "ph", "call", "calls", "virtual", "virt"}:
        return "Phones"
    if low in {"3pl", "3p", "threepl"}:
        return "3PL"
    if low in {"inbound", "3pl/inbound", "3pl / inbound"}:
        return "Inbound"
    return text


def matches_lead_source_filter(selected: str, actual: str) -> bool:
    wanted = compact_str(selected)
    if not wanted:
        return True
    actual_norm = normalize_lead_source(actual)
    if wanted == "3PL/Inbound":
        return actual_norm in {"3PL", "Inbound"}
    return actual_norm == wanted


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value or not isinstance(value, str):
        return None
    try:
        y, m, d = [int(x) for x in value.strip().split("-")]
        return y, m, d
    except Exception:
        return None


def date_range_window(start_ymd: str, end_ymd: str) -> tuple[datetime, datetime, str, str]:
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=TZ)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=TZ) + timedelta(days=1)
    return start_local, end_local, start_local.date().isoformat(), (end_local - timedelta(days=1)).date().isoformat()


def month_window(year: int, month: int) -> tuple[datetime, datetime, str, str]:
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=TZ)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=TZ)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=TZ)
    return start_local, end_local, start_local.date().isoformat(), (end_local - timedelta(days=1)).date().isoformat()


def as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")

    if not (creds_json and project_id and database_id):
        missing = [
            k
            for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(k)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def user_name_lookup(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in db.collection("ghl_users_v2").stream():
        d = doc.to_dict() or {}
        name = best_person_name(d)
        if not name:
            continue
        for key in {compact_str(d.get("id")), compact_str(d.get("userId")), compact_str(doc.id)}:
            if key:
                out[key] = name
    return out


def stage_name_lookup(db: firestore.Client) -> tuple[dict[str, str], dict[str, str]]:
    stage_names: dict[str, str] = {}
    pipeline_names: dict[str, str] = {}
    for doc in db.collection("ghl_pipelines_v2").stream():
        d = doc.to_dict() or {}
        pid = compact_str(d.get("id") or doc.id)
        pname = compact_str(d.get("name"))
        if pid and pname:
            pipeline_names[pid] = pname
        for stage in (d.get("stages") or []):
            if not isinstance(stage, dict):
                continue
            sid = compact_str(stage.get("id") or stage.get("uid"))
            sname = compact_str(stage.get("name"))
            if sid and sname:
                stage_names[sid] = sname
    return stage_names, pipeline_names


def load_contacts(db: firestore.Client) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for doc in db.collection("ghl_contacts_v2").stream():
        d = doc.to_dict() or {}
        cid = compact_str(d.get("id") or doc.id)
        if cid:
            out[cid] = d
    return out


def load_stage_history_by_opportunity(db: firestore.Client) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for doc in db.collection("ghl_opportunity_stage_history_v1").stream():
        row = doc.to_dict() or {}
        opp_id = compact_str(row.get("opportunityId"))
        if not opp_id:
            continue
        out.setdefault(opp_id, []).append(row)
    for rows in out.values():
        rows.sort(key=lambda row: (as_dt(row.get("effectiveAt")) or datetime.min.replace(tzinfo=timezone.utc)))
    return out


def contact_custom_field(contact: dict[str, Any] | None, cf_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and compact_str(cf.get("id")) == cf_id:
            value = cf.get("value")
            if value not in (None, ""):
                return value
            for key in ("fieldValueString", "fieldValueNumber", "fieldValueBoolean"):
                if cf.get(key) not in (None, ""):
                    return cf.get(key)
    return None


def opportunity_custom_field(opp: dict[str, Any] | None, cf_id: str) -> Any:
    if not isinstance(opp, dict):
        return None
    for cf in (opp.get("customFields") or []):
        if isinstance(cf, dict) and compact_str(cf.get("id")) == cf_id:
            value = cf.get("value")
            if value not in (None, ""):
                return value
            for key in ("fieldValueString", "fieldValueNumber", "fieldValueBoolean", "fieldValue"):
                if cf.get(key) not in (None, ""):
                    return cf.get(key)
    return None


def resolve_contact_name(opp: dict[str, Any], contact: dict[str, Any] | None) -> str:
    contact_obj = opp.get("contact")
    if isinstance(contact_obj, dict):
        name = compact_str(contact_obj.get("name"))
        if name:
            return name
    if isinstance(contact, dict):
        for key in ("contactName", "name"):
            name = compact_str(contact.get(key))
            if name:
                return name
        joined = " ".join(
            part for part in (compact_str(contact.get("firstName")), compact_str(contact.get("lastName"))) if part
        )
        if joined:
            return joined
    return ""


def resolve_setter_name(opp: dict[str, Any], contact: dict[str, Any] | None) -> str:
    candidates = [
        opportunity_custom_field(opp, SETTER_LAST_NAME_FIELD_ID),
        contact_custom_field(contact, SETTER_LAST_NAME_FIELD_ID),
        contact_custom_field(contact, SETTER_LAST_NAME_FALLBACK_FIELD_ID),
        opp.get("setter"),
        (contact or {}).get("setter"),
    ]
    for candidate in candidates:
        text = compact_str(candidate)
        if text:
            return text
    return ""


def resolve_address(contact: dict[str, Any] | None) -> str:
    if not isinstance(contact, dict):
        return ""
    street_candidates = [
        contact.get("address1"),
        contact.get("address"),
        contact.get("streetAddress"),
        contact.get("street"),
        contact.get("fullAddress"),
    ]
    street = next((compact_str(value) for value in street_candidates if compact_str(value)), "")
    line2 = compact_str(contact.get("address2") or contact.get("unit") or contact.get("suite"))
    city = compact_str(contact.get("city"))
    state = compact_str(contact.get("state"))
    postal = compact_str(contact.get("postalCode") or contact.get("zip") or contact.get("zipCode"))

    locality = ", ".join(part for part in [city, state] if part)
    if postal:
        locality = f"{locality} {postal}".strip() if locality else postal

    parts = [part for part in [street, line2, locality] if part]
    return ", ".join(parts)


def google_maps_url(address: str) -> str:
    text = compact_str(address)
    if not text:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(text)}"


def format_local_datetime(value: Any) -> str:
    dt = as_dt(value)
    if not dt:
        return ""
    return dt.astimezone(TZ).strftime("%Y-%m-%d %I:%M %p")


def load_rep_roster(db: firestore.Client, user_names: dict[str, str]) -> list[RepRosterEntry]:
    rows: list[RepRosterEntry] = []
    for snap in db.collection("roster_people_v1").stream():
        d = snap.to_dict() or {}
        role = compact_str(d.get("role")).lower()
        categories = [compact_str(x).lower() for x in (d.get("categories") or []) if compact_str(x)]
        if role != "rep" and "rep" not in categories:
            continue
        owner_id = compact_str(d.get("ghl_user_id"))
        if not owner_id:
            continue
        display_name = (
            compact_str(d.get("display_name"))
            or user_names.get(owner_id, "")
            or compact_str(d.get("ghl_user_name"))
            or f"Unknown User ({owner_id[-6:]})"
        )
        team = normalize_team(d.get("team")) or normalize_team(d.get("segment"))
        rows.append(
            RepRosterEntry(
                owner_id=owner_id,
                display_name=display_name,
                team=team,
                person_key=compact_str(d.get("person_key") or snap.id),
            )
        )
    rows.sort(key=lambda r: (r.display_name.lower(), r.owner_id))
    return rows


def build_owner_directory(
    db: firestore.Client,
    rep_roster: list[RepRosterEntry],
    user_names: dict[str, str],
) -> dict[str, dict[str, str]]:
    owners: dict[str, dict[str, str]] = {
        row.owner_id: {
            "value": row.owner_id,
            "label": row.display_name,
            "team": row.team,
        }
        for row in rep_roster
        if row.owner_id
    }

    for doc in db.collection("ghl_opportunities_v2").stream():
        opp = doc.to_dict() or {}
        owner_id = compact_str(opp.get("assignedTo"))
        if not owner_id:
            continue
        existing = owners.get(owner_id)
        if existing:
            if not existing.get("team"):
                existing["team"] = normalize_team(
                    opp.get("team")
                    or opp.get("assignedTeam")
                    or opp.get("assignedToTeam")
                    or opp.get("teamName")
                )
            continue
        owners[owner_id] = {
            "value": owner_id,
            "label": resolve_owner_name(opp, owner_id, user_names),
            "team": normalize_team(
                opp.get("team")
                or opp.get("assignedTeam")
                or opp.get("assignedToTeam")
                or opp.get("teamName")
            ),
        }

    return dict(sorted(owners.items(), key=lambda item: (item[1]["label"].lower(), item[0])))


def resolve_owner_name(opp: dict[str, Any], owner_id: str, user_names: dict[str, str]) -> str:
    if not owner_id:
        return "unassigned"
    override = OWNER_NAME_OVERRIDES.get(owner_id.lower())
    if override:
        return override
    hit = user_names.get(owner_id)
    if hit:
        return hit
    for key in ("assignedToName", "assignedToUserName", "assignedUserName", "ownerName"):
        text = compact_str(opp.get(key))
        if text and not looks_like_identifier(text):
            return text
    assigned_user = opp.get("assignedToUser")
    if isinstance(assigned_user, dict):
        text = best_person_name(assigned_user)
        if text:
            return text
    return f"Unknown User ({owner_id[-6:]})"


def sold_date_in_window(contact: dict[str, Any] | None, start_local: datetime, end_local: datetime) -> bool:
    date_sold = contact_custom_field(contact, SOLD_DATE_FIELD_ID)
    if not isinstance(date_sold, str) or len(date_sold) < 10:
        return False
    sold_date = date_sold[:10]
    return start_local.date().isoformat() <= sold_date < end_local.date().isoformat()


def contact_lead_source(contact: dict[str, Any] | None) -> str:
    lead_src = contact_custom_field(contact, LEAD_SOURCE_FIELD_ID)
    if not lead_src and isinstance(contact, dict):
        attr = contact.get("attributionSource") or {}
        if isinstance(attr, dict):
            lead_src = attr.get("sessionSource") or attr.get("medium")
    return normalize_lead_source(lead_src)


def qualifies_two_touch_close(
    opp: dict[str, Any],
    contact: dict[str, Any] | None,
    stage_names: dict[str, str],
    history_rows: list[dict[str, Any]],
) -> bool:
    if normalize_disposition(opp.get("dispositionValue")) != "Sit":
        return False

    appointment_at = as_dt(opp.get("appointmentOccurredAt"))

    # Determine sold date: history rows first, then contact dateSold fallback
    sold_at_candidates = []
    for row in history_rows:
        to_stage_name = row.get("toStageName")
        to_stage_id = row.get("toStageId")
        if is_sale_stage(to_stage_id, to_stage_name):
            effective_at = as_dt(row.get("effectiveAt"))
            if effective_at:
                sold_at_candidates.append(effective_at)
    sold_at = min(sold_at_candidates) if sold_at_candidates else None
    # Fallback: contact dateSold for opps that sold before history capture started
    if sold_at is None and contact:
        raw_date = contact.get("dateSold")
        if raw_date:
            sold_at = as_dt(raw_date)

    # Current opp stage / pipeline for supplementary checks
    opp_stage_id = compact_str(opp.get("pipelineStageId") or "")
    opp_stage_name = stage_names.get(opp_stage_id, "")
    opp_pipeline_id = compact_str(opp.get("pipelineId") or "")
    opp_pipeline_name = stage_names.get(opp_pipeline_id, "")

    for row in history_rows:
        stage_name = row.get("toStageName")
        stage_id = row.get("toStageId")
        pipeline_name = row.get("pipelineName")
        if is_sale_stage(stage_id, stage_name):
            continue
        if not (is_touch_close_stage(stage_name) or is_touch_close_pipeline(pipeline_name)):
            continue
        effective_at = as_dt(row.get("effectiveAt"))
        if appointment_at and effective_at and effective_at <= appointment_at:
            continue
        if sold_at and effective_at and effective_at >= sold_at:
            continue
        return True

    # No qualifying history row — check if opp is currently in a touch stage.
    # For currently-sold opps with no history, fall back to current stage check:
    # if the opp's current stage is NOT a touch stage, it had no qualifying prior
    # touch stage (or we simply don't know from history), so don't count as 2-touch.
    if is_sale_stage(opp_stage_id, opp_stage_name):
        # Currently sold: if no history row qualifies, it's not a two-touch close
        return False
    if is_touch_close_stage(opp_stage_name) or is_touch_close_pipeline(opp_pipeline_name):
        # Currently in a touch pipeline/stage: still open, not yet sold past it
        return False
    return False


def build_payload(
    db: firestore.Client,
    *,
    year: int,
    month: int,
    start: str | None,
    end: str | None,
    touch_year: int,
    touch_month: int,
    touch_start: str | None,
    touch_end: str | None,
    owner_id: str,
    team: str,
    lead_source: str,
) -> dict[str, Any]:
    if start and end:
        start_local, end_local, start_label, end_label = date_range_window(start, end)
    else:
        start_local, end_local, start_label, end_label = month_window(year, month)

    if touch_start and touch_end:
        touch_start_local, touch_end_local, touch_start_label, touch_end_label = date_range_window(touch_start, touch_end)
    else:
        touch_start_local, touch_end_local, touch_start_label, touch_end_label = month_window(touch_year, touch_month)

    now_utc = datetime.now(timezone.utc)
    end_utc = min(end_local.astimezone(timezone.utc), now_utc)
    start_utc = start_local.astimezone(timezone.utc)

    user_names = user_name_lookup(db)
    stage_names, pipeline_names = stage_name_lookup(db)
    contacts = load_contacts(db)
    stage_history_by_opp = load_stage_history_by_opportunity(db)
    rep_roster = load_rep_roster(db, user_names)
    owner_directory = build_owner_directory(db, rep_roster, user_names)

    reps_by_id = {row.owner_id: row for row in rep_roster}
    owner_options = list(owner_directory.values())

    selected_team = normalize_team(team)
    selected_owner = compact_str(owner_id)
    selected_lead_source = compact_str(lead_source)

    allowed_owner_ids: set[str] = set(owner_directory.keys())
    if selected_team:
        allowed_owner_ids = {
            oid for oid, row in owner_directory.items() if normalize_team(row.get("team")) == selected_team
        }
    if selected_owner:
        allowed_owner_ids = {selected_owner} if not selected_team or selected_owner in allowed_owner_ids else set()

    stage_counts: dict[str, int] = {}
    stage_details: dict[str, list[dict[str, str]]] = {}
    owner_rows: dict[str, dict[str, Any]] = {}
    touch_rows: dict[str, dict[str, Any]] = {}

    for oid in allowed_owner_ids:
        if allowed_owner_ids and oid not in allowed_owner_ids:
            continue
        owner_meta = owner_directory.get(oid) or {"label": f"Unknown User ({oid[-6:]})", "team": ""}
        owner_rows[oid] = {
            "owner_id": oid,
            "owner": owner_meta["label"],
            "team": owner_meta.get("team") or "",
            "ran": 0,
            "demos": 0,
            "sales": 0,
        }
        touch_rows[oid] = {
            "owner_id": oid,
            "owner": owner_meta["label"],
            "team": owner_meta.get("team") or "",
            "two_touch_closes": 0,
            "sales_total": 0,
            "open_touch_opps": 0,
            "stale_touch_opps": 0,
            "oldest_touch_days": 0,
        }

    opp_query = (
        db.collection("ghl_opportunities_v2")
        .where("appointmentOccurredAt", ">=", start_utc)
        .where("appointmentOccurredAt", "<", end_utc)
    )

    completed_rows = 0
    for doc in opp_query.stream():
        opp = doc.to_dict() or {}
        owner = compact_str(opp.get("assignedTo"))
        if owner not in allowed_owner_ids:
            continue

        contact = contacts.get(compact_str(opp.get("contactId")))
        if not matches_lead_source_filter(selected_lead_source, contact_lead_source(contact)):
            continue

        pid = compact_str(opp.get("pipelineId"))
        pname = compact_str(pipeline_names.get(pid, pid))
        if pname.lower() == "inbound/lead locker":
            continue

        disposition = normalize_disposition(opp.get("dispositionValue"))
        if not disposition:
            continue

        completed_rows += 1

        stage_id = compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId"))
        stage_name = (
            compact_str(stage_names.get(stage_id))
            or compact_str(opp.get("pipelineStageName"))
            or compact_str(opp.get("stageName"))
            or stage_id
            or "Unknown Stage"
        )
        outcome_bucket = normalize_completed_outcome_bucket(pname, stage_name)
        stage_counts[outcome_bucket] = stage_counts.get(outcome_bucket, 0) + 1
        notes = compact_str(
            opp.get("dispositionNotes")
            or opp.get("dispositionNote")
            or opp.get("notes")
            or opportunity_custom_field(opp, DISPOSITION_NOTES_FIELD_ID)
        )
        address = resolve_address(contact)
        stage_details.setdefault(outcome_bucket, []).append(
            {
                "name": resolve_contact_name(opp, contact) or "—",
                "address": address or "—",
                "maps_url": google_maps_url(address),
                "setter": resolve_setter_name(opp, contact) or "—",
                "owner": resolve_owner_name(opp, owner, user_names) or "—",
                "appt_date": format_local_datetime(opp.get("appointmentOccurredAt")) or "—",
                "disposition_notes": notes or "—",
                "_sort": as_dt(opp.get("appointmentOccurredAt")).astimezone(TZ).isoformat()
                if as_dt(opp.get("appointmentOccurredAt"))
                else "",
            }
        )

        if owner not in owner_rows:
            owner_rows[owner] = {
                "owner_id": owner,
                "owner": resolve_owner_name(opp, owner, user_names),
                "team": owner_directory.get(owner, {}).get("team", ""),
                "ran": 0,
                "demos": 0,
                "sales": 0,
            }
        if owner not in touch_rows:
            touch_rows[owner] = {
                "owner_id": owner,
                "owner": resolve_owner_name(opp, owner, user_names),
                "team": owner_directory.get(owner, {}).get("team", ""),
                "two_touch_closes": 0,
                "sales_total": 0,
                "open_touch_opps": 0,
                "stale_touch_opps": 0,
                "oldest_touch_days": 0,
            }

        if disposition in {"Sit", "No Sit"}:
            owner_rows[owner]["ran"] += 1
        if disposition == "Sit":
            owner_rows[owner]["demos"] += 1

    for doc in db.collection("ghl_opportunities_v2").stream():
        opp = doc.to_dict() or {}
        owner = compact_str(opp.get("assignedTo"))
        if owner not in allowed_owner_ids:
            continue

        stage_id = compact_str(opp.get("pipelineStageId"))
        if stage_id not in SALE_STAGE_IDS:
            continue

        contact_id = compact_str(opp.get("contactId"))
        contact = contacts.get(contact_id)
        if not matches_lead_source_filter(selected_lead_source, contact_lead_source(contact)):
            continue
        if not sold_date_in_window(contact, touch_start_local, touch_end_local):
            continue

        if owner not in owner_rows:
            owner_rows[owner] = {
                "owner_id": owner,
                "owner": resolve_owner_name(opp, owner, user_names),
                "team": owner_directory.get(owner, {}).get("team", ""),
                "ran": 0,
                "demos": 0,
                "sales": 0,
            }
        if owner not in touch_rows:
            touch_rows[owner] = {
                "owner_id": owner,
                "owner": resolve_owner_name(opp, owner, user_names),
                "team": owner_directory.get(owner, {}).get("team", ""),
                "two_touch_closes": 0,
                "sales_total": 0,
                "open_touch_opps": 0,
                "stale_touch_opps": 0,
                "oldest_touch_days": 0,
            }
        owner_rows[owner]["sales"] += 1

        opp_id = compact_str(opp.get("id") or doc.id)
        history_rows = stage_history_by_opp.get(opp_id, [])
        touched_pipeline = qualifies_two_touch_close(opp, contact, stage_names, history_rows)
        touch_rows[owner]["sales_total"] += 1
        if touched_pipeline:
            touch_rows[owner]["two_touch_closes"] += 1

    for doc in db.collection("ghl_opportunities_v2").stream():
        opp = doc.to_dict() or {}
        owner = compact_str(opp.get("assignedTo"))
        if owner not in allowed_owner_ids:
            continue

        contact = contacts.get(compact_str(opp.get("contactId")))
        if not matches_lead_source_filter(selected_lead_source, contact_lead_source(contact)):
            continue

        pid = compact_str(opp.get("pipelineId"))
        pname = compact_str(pipeline_names.get(pid, pid))
        if pname.lower() == "inbound/lead locker":
            continue

        stage_id = compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId"))
        stage_name = (
            compact_str(stage_names.get(stage_id))
            or compact_str(opp.get("pipelineStageName"))
            or compact_str(opp.get("stageName"))
            or stage_id
        )
        if not is_touch_close_stage(stage_name):
            continue
        if stage_id in SALE_STAGE_IDS:
            continue

        if owner not in touch_rows:
            touch_rows[owner] = {
                "owner_id": owner,
                "owner": resolve_owner_name(opp, owner, user_names),
                "team": owner_directory.get(owner, {}).get("team", ""),
                "two_touch_closes": 0,
                "sales_total": 0,
                "open_touch_opps": 0,
                "stale_touch_opps": 0,
                "oldest_touch_days": 0,
            }

        touch_rows[owner]["open_touch_opps"] += 1
        stage_changed_at = as_dt(opp.get("lastStageChangeAt")) or as_dt(opp.get("updatedAt"))
        if stage_changed_at:
            age_days = max(0, int((now_utc - stage_changed_at.astimezone(timezone.utc)).total_seconds() // 86400))
            touch_rows[owner]["oldest_touch_days"] = max(touch_rows[owner]["oldest_touch_days"], age_days)
            if age_days >= TOUCH_PIPELINE_STALE_DAYS:
                touch_rows[owner]["stale_touch_opps"] += 1

    rows = []
    for row in owner_rows.values():
        ran = int(row["ran"])
        demos = int(row["demos"])
        sales = int(row["sales"])
        opp2 = round((sales / ran) * 100, 1) if ran > 0 else None
        close_rate = round((sales / demos) * 100, 1) if demos > 0 else None
        rows.append(
            {
                **row,
                "opp2prelim": opp2,
                "close_rate_on_demos": close_rate,
            }
        )

    rows.sort(key=lambda r: (-r["sales"], -r["demos"], -r["ran"], r["owner"].lower()))

    touch_table = []
    for row in touch_rows.values():
        sales_total = int(row["sales_total"])
        two_touch_closes = int(row["two_touch_closes"])
        open_touch_opps = int(row["open_touch_opps"])
        stale_touch_opps = int(row["stale_touch_opps"])
        touch_close_rate = round((two_touch_closes / sales_total) * 100, 1) if sales_total > 0 else None
        touch_table.append(
            {
                **row,
                "touch_close_rate": touch_close_rate,
                "pipeline_health": "Needs work" if stale_touch_opps > 0 else ("Working" if open_touch_opps > 0 else "Clear"),
            }
        )

    touch_table.sort(
        key=lambda r: (
            -int(r["two_touch_closes"]),
            -int(r["stale_touch_opps"]),
            -int(r["open_touch_opps"]),
            r["owner"].lower(),
        )
    )

    totals = {
        "completed": sum(stage_counts.values()),
        "opps_ran": sum(int(r["ran"]) for r in rows),
        "demos": sum(int(r["demos"]) for r in rows),
        "sales": sum(int(r["sales"]) for r in rows),
    }
    totals["opp2prelim"] = round((totals["sales"] / totals["opps_ran"]) * 100, 1) if totals["opps_ran"] > 0 else None
    totals["close_rate_on_demos"] = round((totals["sales"] / totals["demos"]) * 100, 1) if totals["demos"] > 0 else None
    touch_totals = {
        "two_touch_closes": sum(int(r["two_touch_closes"]) for r in touch_table),
        "sales_total": sum(int(r["sales_total"]) for r in touch_table),
        "open_touch_opps": sum(int(r["open_touch_opps"]) for r in touch_table),
        "stale_touch_opps": sum(int(r["stale_touch_opps"]) for r in touch_table),
        "oldest_touch_days": max((int(r["oldest_touch_days"]) for r in touch_table), default=0),
    }
    touch_totals["touch_close_rate"] = (
        round((touch_totals["two_touch_closes"] / touch_totals["sales_total"]) * 100, 1)
        if touch_totals["sales_total"] > 0
        else None
    )

    pie = [
        {"label": label, "value": value}
        for label, value in sorted(stage_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if value > 0
    ]
    for rows_for_stage in stage_details.values():
        rows_for_stage.sort(key=lambda row: row.get("_sort", ""), reverse=True)
        for row in rows_for_stage:
            row.pop("_sort", None)

    return {
        "metric": "SC Overview",
        "timezone": "America/New_York",
        "window_start": start_label,
        "window_end": end_label,
        "filters": {
            "team": selected_team,
            "owner_id": selected_owner,
            "lead_source": selected_lead_source,
        },
        "touch_filters": {
            "year": touch_year,
            "month": touch_month,
            "start": touch_start or "",
            "end": touch_end or "",
            "window_start": touch_start_label,
            "window_end": touch_end_label,
        },
        "owner_options": owner_options,
        "team_options": TEAM_OPTIONS,
        "lead_source_options": LEAD_SOURCE_OPTIONS,
        "totals": totals,
        "pie": pie,
        "pie_details": stage_details,
        "rows": rows,
        "touch_table": touch_table,
        "touch_totals": touch_totals,
        "debug": {
            "rep_roster_count": len(rep_roster),
            "completed_rows": completed_rows,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def render_html(
    year: int,
    month: int,
    touch_year: int,
    touch_month: int,
    owner_options: list[dict[str, str]],
    selected_team: str,
    selected_owner: str,
    selected_lead_source: str,
    start: str,
    end: str,
    touch_start: str,
    touch_end: str,
) -> str:
    loader_css = dashboard_nav_css()
    loader_html = render_dashboard_loader()
    year_options = "".join(
        f'<option value="{y}"{" selected" if y == year else ""}>{y}</option>'
        for y in range(year - 2, year + 2)
    )
    month_options = "".join(
        f'<option value="{m}"{" selected" if m == month else ""}>{datetime(2000, m, 1).strftime("%B")}</option>'
        for m in range(1, 13)
    )
    touch_year_options = "".join(
        f'<option value="{y}"{" selected" if y == touch_year else ""}>{y}</option>'
        for y in range(touch_year - 2, touch_year + 2)
    )
    touch_month_options = "".join(
        f'<option value="{m}"{" selected" if m == touch_month else ""}>{datetime(2000, m, 1).strftime("%B")}</option>'
        for m in range(1, 13)
    )
    team_html = ['<option value="">Company Overview</option>']
    for team in TEAM_OPTIONS:
        label = team.title()
        sel = " selected" if team == selected_team else ""
        team_html.append(f'<option value="{team}"{sel}>{label}</option>')

    owner_html = ['<option value="">All Sales Reps</option>']
    for row in owner_options:
        value = row["value"]
        label = row["label"]
        team = row.get("team") or "unassigned"
        sel = " selected" if value == selected_owner else ""
        owner_html.append(f'<option value="{value}" data-team="{team}"{sel}>{label}</option>')
    lead_source_html = ['<option value="">All Lead Sources</option>']
    for value in LEAD_SOURCE_OPTIONS:
        sel = " selected" if value == selected_lead_source else ""
        lead_source_html.append(f'<option value="{value}"{sel}>{value}</option>')

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — SC Overview</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;
      --pink: #ec4899;
      --pink2: #f472b6;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); }}
    .wrap {{ max-width: 1220px; margin: 0 auto; padding: 22px; }}
{loader_css}
    .hero {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      padding: 18px 20px;
      display:flex;
      justify-content:space-between;
      align-items:flex-start;
      gap: 18px;
      flex-wrap: wrap;
    }}
    .title {{ font-size: 24px; font-weight: 950; color:#1a2b4a; letter-spacing:-0.02em; }}
    .subtitle {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
    .pinkline {{
      height: 3px;
      width: 220px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }}
    .hero-actions {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .btn, select, input {{
      border:1px solid var(--border);
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 13px;
      background:#fff;
      color:#1f2937;
    }}
    .btn {{
      text-decoration:none;
      font-weight: 900;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      cursor:pointer;
    }}
    .btn.primary {{
      background: var(--pink);
      color:#fff;
      border-color: var(--pink);
    }}
    .filters {{
      margin-top: 14px;
      display:grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 12px;
    }}
    .field {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
      box-shadow: var(--shadow);
    }}
    .label {{
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .field.controls {{
      display:flex;
      align-items:flex-end;
      gap: 10px;
      grid-column: span 2;
    }}
    .mini-filters {{
      margin-top: 12px;
      display:grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      align-items:end;
    }}
    .mini-field {{
      display:flex;
      flex-direction:column;
      gap: 6px;
    }}
    .mini-label {{
      font-size: 11px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .mini-actions {{
      display:flex;
      gap: 8px;
      align-items:end;
      flex-wrap:wrap;
    }}
    .grid {{
      margin-top: 14px;
      display:grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }}
    .span-8 {{ grid-column: span 8; }}
    .span-4 {{ grid-column: span 4; }}
    .span-12 {{ grid-column: span 12; }}
    .card-title {{ font-size: 13px; font-weight: 900; color: var(--muted); }}
    .meta {{ margin-top: 6px; color: var(--muted2); font-size: 12px; }}
    .kpi-grid {{
      margin-top: 12px;
      display:grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .kpi {{
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #faf7fb;
      padding: 14px;
    }}
    .kpi-value {{ font-size: 28px; font-weight: 950; letter-spacing:-0.02em; }}
    .kpi-value.small {{ font-size: 24px; }}
    .pie-shell {{
      margin-top: 14px;
      display:grid;
      grid-template-columns: minmax(260px, 320px) 1fr;
      gap: 18px;
      align-items:center;
    }}
    .pie {{
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: #eef2f7;
      position: relative;
      margin: 0 auto;
    }}
    .pie::after {{
      content: "";
      position: absolute;
      inset: 66px;
      border-radius: 50%;
      background: var(--card);
      box-shadow: inset 0 0 0 1px var(--border);
    }}
    .pie-center {{
      position:absolute;
      inset:0;
      display:flex;
      flex-direction:column;
      align-items:center;
      justify-content:center;
      z-index: 2;
      text-align:center;
      pointer-events:none;
    }}
    .pie-total {{ font-size: 34px; font-weight: 950; letter-spacing:-0.02em; }}
    .legend {{ display:flex; flex-direction:column; gap: 10px; }}
    .legend-row {{
      display:grid;
      grid-template-columns: 14px 1fr auto;
      gap: 10px;
      align-items:center;
      font-size: 13px;
      padding: 8px 10px;
      border-radius: 12px;
      cursor: pointer;
      transition: background .15s ease, transform .15s ease;
    }}
    .legend-row:hover {{
      background:#faf7fb;
      transform: translateX(2px);
    }}
    .swatch {{ width: 14px; height: 14px; border-radius: 999px; }}
    .tablewrap {{
      margin-top: 12px;
      overflow:auto;
      border: 1px solid var(--border);
      border-radius: 14px;
      background:#fafbfc;
    }}
    table {{ width:100%; min-width: 920px; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align:left; font-size:13px; }}
    th {{ position: sticky; top: 0; background:#f3f5f7; color:var(--muted); font-size:12px; font-weight:900; }}
    td.num {{ text-align:right; font-variant-numeric: tabular-nums; }}
    tr.total td {{ font-weight:950; background:#fff; }}
    .empty {{ color: var(--muted2); font-size: 13px; }}
    .status-chip {{
      display:inline-flex;
      align-items:center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
    }}
    .status-good {{ background:#ecfdf5; color:#047857; }}
    .status-warn {{ background:#fff7ed; color:#c2410c; }}
    .status-neutral {{ background:#f3f4f6; color:#4b5563; }}
    .modal {{
      position: fixed;
      inset: 0;
      background: rgba(17,24,39,0.42);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 1000;
    }}
    .modal.open {{ display:flex; }}
    .modal-inner {{
      width: min(1100px, 96vw);
      max-height: 90vh;
      overflow: auto;
      background: #fff;
      border-radius: 18px;
      border: 1px solid var(--border);
      box-shadow: 0 24px 80px rgba(17,24,39,0.22);
      padding: 20px;
    }}
    .modal-header {{
      display:flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .modal-title {{ font-size: 20px; font-weight: 950; color:#1a2b4a; letter-spacing:-0.02em; }}
    .modal-subtitle {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
    .modal-close {{
      border:1px solid var(--border);
      background:#fff;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 900;
      cursor: pointer;
    }}
    #detailTable {{ min-width: 860px; }}
    .detail-address {{
      min-width: 260px;
      white-space: normal;
    }}
    .detail-address a {{
      color: #1d4ed8;
      text-decoration: underline;
      text-underline-offset: 2px;
      word-break: break-word;
    }}
    .detail-address a:hover {{ color: #1e3a8a; }}
    @media (max-width: 980px) {{
      .filters {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .field.controls {{ grid-column: span 2; }}
      .span-8, .span-4, .span-12 {{ grid-column: span 12; }}
      .pie-shell {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 640px) {{
      .wrap {{ padding: 12px; }}
      .filters {{ grid-template-columns: 1fr; }}
      .field.controls {{ grid-column: span 1; flex-wrap: wrap; }}
      .pie {{ width: 240px; height: 240px; }}
      .pie::after {{ inset: 56px; }}
      .mini-filters {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  {loader_html}
  <div class="wrap">
    <div class="hero">
      <div>
        <div class="title">SC Overview</div>
        <div class="subtitle">Sales rep performance board with completed appointment outcomes and sales.</div>
        <div class="pinkline"></div>
      </div>
      <div class="hero-actions">
        <a class="btn" href="/api/settings#secret-lab">Back to Settings</a>
      </div>
    </div>

    <form class="filters" method="get" action="/api/sc_overview">

      <div class="field">
        <div class="label">Team</div>
        <select id="team" name="team">{"".join(team_html)}</select>
      </div>
      <div class="field">
        <div class="label">Sales Rep</div>
        <select id="owner_id" name="owner_id">{"".join(owner_html)}</select>
      </div>
      <div class="field">
        <div class="label">Year</div>
        <select id="year" name="year">{year_options}</select>
      </div>
      <div class="field">
        <div class="label">Month</div>
        <select id="month" name="month">{month_options}</select>
      </div>
      <div class="field">
        <div class="label">Lead Gen Source</div>
        <select id="lead_source" name="lead_source">{"".join(lead_source_html)}</select>
      </div>
      <div class="field">
        <div class="label">Start</div>
        <input id="start" name="start" type="date" value="{start}" />
      </div>
      <div class="field">
        <div class="label">End</div>
        <input id="end" name="end" type="date" value="{end}" />
      </div>
      <div class="field controls">
        <button class="btn primary" type="submit">Apply</button>
        <a class="btn" href="/api/sc_overview">Reset</a>
      </div>
    </form>

    <div class="grid">
      <div class="card span-8">
        <div class="card-title">Completed Appointment Outcomes</div>
        <div class="meta">Pie groups completed appointments by current pipeline stage. Completed appointments are rows with a non-empty disposition.</div>
        <div class="pie-shell">
          <div id="pie" class="pie">
            <div class="pie-center">
              <div class="meta" style="margin-top:0">Completed</div>
              <div id="pieTotal" class="pie-total">—</div>
            </div>
          </div>
          <div id="legend" class="legend"><div class="empty">Loading…</div></div>
        </div>
      </div>

      <div class="card span-4">
        <div class="card-title">Summary</div>
        <div class="meta">Sales and Two-Touch stay on Sold Date. Opps Ran and Demos stay on appointmentOccurredAt.</div>
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Opps Ran</div><div id="kpiRan" class="kpi-value">—</div></div>
          <div class="kpi"><div class="label">Demos</div><div id="kpiDemos" class="kpi-value">—</div></div>
          <div class="kpi"><div class="label">Sales</div><div id="kpiSales" class="kpi-value">—</div></div>
          <div class="kpi"><div class="label">Close Rate on Demos</div><div id="kpiClose" class="kpi-value">—</div></div>
        </div>
        <div id="windowMeta" class="meta"></div>
      </div>

      <div class="card span-12">
        <div class="card-title">Owner Performance</div>
        <div class="meta">Like the sales dashboard, plus demos and close rate on demos.</div>
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Sales Rep</th>
                <th>Team</th>
                <th style="text-align:right">Opps Ran</th>
                <th style="text-align:right">Demos</th>
                <th style="text-align:right">Sales</th>
                <th style="text-align:right">Opp2Prelim%</th>
                <th style="text-align:right">Close Rate on Demos</th>
              </tr>
            </thead>
            <tbody id="ownerRows">
              <tr><td colspan="7" class="empty">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card span-4">
        <div class="card-title">Two-Touch Coaching</div>
        <div class="meta">Shows who converts after a first-appointment `Sit` and later follow-up path, plus who has touch-stage opps going stale.</div>
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Two-Touch Closes</div><div id="kpiTouchCloses" class="kpi-value small">—</div></div>
          <div class="kpi"><div class="label">Two-Touch % of Sales</div><div id="kpiTouchRate" class="kpi-value small">—</div></div>
          <div class="kpi"><div class="label">Open Touch-Stage Opps</div><div id="kpiTouchOpen" class="kpi-value small">—</div></div>
          <div class="kpi"><div class="label">Stale 7+ Day Touch Opps</div><div id="kpiTouchStale" class="kpi-value small">—</div></div>
        </div>
      </div>

      <div class="card span-8">
        <div class="card-title">Two-Touch Close / Pipeline Work Rate</div>
        <div class="meta">Two-touch close means the rep had a `Sit` on the first appointment, did not sell there, then later hit Demo-Negotiating, Demo-Not Interested, One Legger, or moved into Rehash/Sweeper before it sold in the selected Sold Date window. Rescheduled does not count. Open/stale touch-stage opps are current queue signals and are not sold-date filtered.</div>
        <div id="touchWindowMeta" class="meta"></div>
        <form class="mini-filters" method="get" action="/api/sc_overview">
          <input type="hidden" name="team" value="{selected_team}" />
          <input type="hidden" name="owner_id" value="{selected_owner}" />
          <input type="hidden" name="year" value="{year}" />
          <input type="hidden" name="month" value="{month}" />
          <input type="hidden" name="lead_source" value="{selected_lead_source}" />
          <input type="hidden" name="start" value="{start}" />
          <input type="hidden" name="end" value="{end}" />
          <div class="mini-field">
            <div class="mini-label">Two-Touch Year</div>
            <select name="touch_year">{touch_year_options}</select>
          </div>
          <div class="mini-field">
            <div class="mini-label">Two-Touch Month</div>
            <select name="touch_month">{touch_month_options}</select>
          </div>
          <div class="mini-field">
            <div class="mini-label">Touch Start</div>
            <input name="touch_start" type="date" value="{touch_start}" />
          </div>
          <div class="mini-field">
            <div class="mini-label">Touch End</div>
            <input name="touch_end" type="date" value="{touch_end}" />
          </div>
          <div class="mini-actions">
            <button class="btn primary" type="submit">Apply</button>
            <a class="btn" href="/api/sc_overview?team={quote_plus(selected_team)}&owner_id={quote_plus(selected_owner)}&year={year}&month={month}&lead_source={quote_plus(selected_lead_source)}&start={quote_plus(start)}&end={quote_plus(end)}">Reset</a>
          </div>
        </form>
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Sales Rep</th>
                <th>Team</th>
                <th style="text-align:right">Two-Touch Closes</th>
                <th style="text-align:right">Two-Touch % of Sales</th>
                <th style="text-align:right">Open Touch Opps</th>
                <th style="text-align:right">Stale 7+ Days</th>
                <th style="text-align:right">Oldest Stale Age</th>
                <th>Pipeline Health</th>
              </tr>
            </thead>
            <tbody id="touchRows">
              <tr><td colspan="8" class="empty">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div id="detailModal" class="modal" aria-hidden="true">
    <div class="modal-inner">
      <div class="modal-header">
        <div>
          <div id="detailTitle" class="modal-title">Appointments</div>
          <div id="detailSubtitle" class="modal-subtitle">Loading…</div>
        </div>
        <button id="detailClose" class="modal-close" type="button">Close</button>
      </div>
      <div class="tablewrap" style="margin-top:0">
        <table id="detailTable">
          <thead>
            <tr>
              <th>Name</th>
              <th>Address</th>
              <th>Setter</th>
              <th>Opp Owner</th>
              <th>Appt Date</th>
              <th>Disposition Notes</th>
            </tr>
          </thead>
          <tbody id="detailRows">
            <tr><td colspan="6" class="empty">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const piePalette = ['#ec4899','#06b6d4','#f59e0b','#10b981','#6366f1','#f97316','#14b8a6','#8b5cf6','#ef4444','#84cc16','#3b82f6','#d946ef'];
    let pieDetails = {{}};
    let pieSegments = [];

    (function() {{
      const loader = document.getElementById('hsDashboardLoader');
      let pendingFetches = 0;
      let hideTimer = null;

      function setLoaderVisible(visible) {{
        if (!loader) return;
        loader.classList.toggle('is-hidden', !visible);
        loader.setAttribute('aria-hidden', visible ? 'false' : 'true');
      }}

      function scheduleLoaderHide() {{
        if (!loader) return;
        if (hideTimer) window.clearTimeout(hideTimer);
        hideTimer = window.setTimeout(() => {{
          if (pendingFetches <= 0) setLoaderVisible(false);
        }}, 180);
      }}

      function shouldTrackFetch(input) {{
        let raw = '';
        if (typeof input === 'string') raw = input;
        else if (input && typeof input.url === 'string') raw = input.url;
        if (!raw) return false;
        try {{
          const url = new URL(raw, window.location.href);
          return url.origin === window.location.origin
            && url.pathname.startsWith('/api/')
            && url.pathname !== '/api/warm_cache';
        }} catch (_err) {{
          return false;
        }}
      }}

      window.HSDashboardLoader = {{
        show() {{
          if (hideTimer) window.clearTimeout(hideTimer);
          setLoaderVisible(true);
        }},
        hide() {{
          pendingFetches = 0;
          scheduleLoaderHide();
        }},
      }};

      if (window.fetch && !window.__hsDashboardLoaderPatched) {{
        window.__hsDashboardLoaderPatched = true;
        const originalFetch = window.fetch.bind(window);
        window.fetch = function(input, init) {{
          const tracked = shouldTrackFetch(input);
          if (tracked) {{
            pendingFetches += 1;
            window.HSDashboardLoader.show();
          }}
          return originalFetch(input, init).finally(() => {{
            if (!tracked) return;
            pendingFetches = Math.max(0, pendingFetches - 1);
            if (pendingFetches === 0) scheduleLoaderHide();
          }});
        }};
      }}

      setLoaderVisible(true);
      scheduleLoaderHide();
    }})();

    function fmtInt(v) {{
      return new Intl.NumberFormat('en-US', {{ maximumFractionDigits: 0 }}).format(Number(v || 0));
    }}

    function fmtPct(v) {{
      return (v === null || typeof v === 'undefined' || Number.isNaN(Number(v))) ? '—' : `${{Number(v).toFixed(1)}}%`;
    }}

    function escapeHtml(value) {{
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }}

    function updateOwnerOptions() {{
      const team = (document.getElementById('team').value || '').trim().toLowerCase();
      const ownerSel = document.getElementById('owner_id');
      const current = ownerSel.value;
      Array.from(ownerSel.options).forEach((opt, idx) => {{
        if (idx === 0) {{
          opt.hidden = false;
          return;
        }}
        const optTeam = (opt.dataset.team || '').trim().toLowerCase();
        opt.hidden = Boolean(team && optTeam && optTeam !== team);
      }});
      const active = Array.from(ownerSel.options).find((opt) => opt.value === current && !opt.hidden);
      if (!active) ownerSel.value = '';
    }}

    function renderPie(items, total) {{
      const pie = document.getElementById('pie');
      const legend = document.getElementById('legend');
      document.getElementById('pieTotal').textContent = fmtInt(total);
      pieSegments = [];

      if (!items.length || !total) {{
        pie.style.background = '#eef2f7';
        legend.innerHTML = '<div class="empty">No completed appointment outcomes in this window.</div>';
        return;
      }}

      let start = 0;
      const stops = [];
      const rows = [];
      items.forEach((item, idx) => {{
        const pct = (Number(item.value || 0) / total) * 100;
        const end = start + pct;
        const color = piePalette[idx % piePalette.length];
        pieSegments.push({{ label: item.label, startPct: start, endPct: end }});
        stops.push(`${{color}} ${{start.toFixed(2)}}% ${{end.toFixed(2)}}%`);
        rows.push(`
          <div class="legend-row" data-label="${{String(item.label || '').replace(/"/g, '&quot;')}}">
            <div class="swatch" style="background:${{color}}"></div>
            <div>${{item.label}}</div>
            <div>${{fmtInt(item.value)}} · ${{pct.toFixed(1)}}%</div>
          </div>
        `);
        start = end;
      }});

      pie.style.background = `conic-gradient(${{stops.join(', ')}})`;
      legend.innerHTML = rows.join('');
      legend.querySelectorAll('.legend-row').forEach((row) => {{
        row.addEventListener('click', () => openDetailModal(row.dataset.label || ''));
      }});
    }}

    function renderRows(rows, totals) {{
      const tbody = document.getElementById('ownerRows');
      if (!rows.length) {{
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No sales rep rows matched this filter.</td></tr>';
        return;
      }}
      let html = '';
      for (const row of rows) {{
        html += `
          <tr>
            <td>${{row.owner || '—'}}</td>
            <td>${{row.team ? row.team.charAt(0).toUpperCase() + row.team.slice(1) : '—'}}</td>
            <td class="num">${{fmtInt(row.ran)}}</td>
            <td class="num">${{fmtInt(row.demos)}}</td>
            <td class="num">${{fmtInt(row.sales)}}</td>
            <td class="num">${{fmtPct(row.opp2prelim)}}</td>
            <td class="num">${{fmtPct(row.close_rate_on_demos)}}</td>
          </tr>
        `;
      }}
      html += `
        <tr class="total">
          <td>Total</td>
          <td>—</td>
          <td class="num">${{fmtInt(totals.opps_ran)}}</td>
          <td class="num">${{fmtInt(totals.demos)}}</td>
          <td class="num">${{fmtInt(totals.sales)}}</td>
          <td class="num">${{fmtPct(totals.opp2prelim)}}</td>
          <td class="num">${{fmtPct(totals.close_rate_on_demos)}}</td>
        </tr>
      `;
      tbody.innerHTML = html;
    }}

    function healthChip(value) {{
      const text = String(value || 'Clear');
      if (text === 'Needs work') return `<span class="status-chip status-warn">${{text}}</span>`;
      if (text === 'Working') return `<span class="status-chip status-good">${{text}}</span>`;
      return `<span class="status-chip status-neutral">${{text}}</span>`;
    }}

    function renderTouchRows(rows, totals) {{
      const tbody = document.getElementById('touchRows');
      if (!rows.length) {{
        tbody.innerHTML = '<tr><td colspan="8" class="empty">No two-touch coaching rows matched this filter.</td></tr>';
        return;
      }}
      let html = '';
      for (const row of rows) {{
        html += `
          <tr>
            <td>${{row.owner || '—'}}</td>
            <td>${{row.team ? row.team.charAt(0).toUpperCase() + row.team.slice(1) : '—'}}</td>
            <td class="num">${{fmtInt(row.two_touch_closes)}}</td>
            <td class="num">${{fmtPct(row.touch_close_rate)}}</td>
            <td class="num">${{fmtInt(row.open_touch_opps)}}</td>
            <td class="num">${{fmtInt(row.stale_touch_opps)}}</td>
            <td class="num">${{row.oldest_touch_days ? `${{fmtInt(row.oldest_touch_days)}}d` : '—'}}</td>
            <td>${{healthChip(row.pipeline_health)}}</td>
          </tr>
        `;
      }}
      html += `
        <tr class="total">
          <td>Total</td>
          <td>—</td>
          <td class="num">${{fmtInt(totals.two_touch_closes)}}</td>
          <td class="num">${{fmtPct(totals.touch_close_rate)}}</td>
          <td class="num">${{fmtInt(totals.open_touch_opps)}}</td>
          <td class="num">${{fmtInt(totals.stale_touch_opps)}}</td>
          <td class="num">${{totals.oldest_touch_days ? `${{fmtInt(totals.oldest_touch_days)}}d` : '—'}}</td>
          <td>${{healthChip(totals.stale_touch_opps > 0 ? 'Needs work' : (totals.open_touch_opps > 0 ? 'Working' : 'Clear'))}}</td>
        </tr>
      `;
      tbody.innerHTML = html;
    }}

    function renderDetailRows(rows) {{
      const tbody = document.getElementById('detailRows');
      if (!rows.length) {{
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No appointments matched this outcome.</td></tr>';
        return;
      }}
      const renderAddress = (row) => {{
        const address = row.address || '—';
        const safeAddress = escapeHtml(address);
        const safeUrl = escapeHtml(row.maps_url || '');
        if (!row.maps_url) {{
          return safeAddress;
        }}
        return `<a href="${{safeUrl}}" target="_blank" rel="noopener noreferrer">${{safeAddress}}</a>`;
      }};
      tbody.innerHTML = rows.map((row) => `
        <tr>
          <td>${{escapeHtml(row.name || '—')}}</td>
          <td class="detail-address">${{renderAddress(row)}}</td>
          <td>${{escapeHtml(row.setter || '—')}}</td>
          <td>${{escapeHtml(row.owner || '—')}}</td>
          <td>${{escapeHtml(row.appt_date || '—')}}</td>
          <td>${{escapeHtml(row.disposition_notes || '—')}}</td>
        </tr>
      `).join('');
    }}

    function openDetailModal(label) {{
      const rows = Array.isArray(pieDetails[label]) ? pieDetails[label] : [];
      document.getElementById('detailTitle').textContent = label || 'Appointments';
      document.getElementById('detailSubtitle').textContent = `${{fmtInt(rows.length)}} appointments in this outcome`;
      renderDetailRows(rows);
      document.getElementById('detailModal').classList.add('open');
      document.getElementById('detailModal').setAttribute('aria-hidden', 'false');
    }}

    function closeDetailModal() {{
      document.getElementById('detailModal').classList.remove('open');
      document.getElementById('detailModal').setAttribute('aria-hidden', 'true');
    }}

    function bindModal() {{
      const modal = document.getElementById('detailModal');
      document.getElementById('detailClose').addEventListener('click', closeDetailModal);
      modal.addEventListener('click', (event) => {{
        if (event.target === modal) closeDetailModal();
      }});
      document.addEventListener('keydown', (event) => {{
        if (event.key === 'Escape') closeDetailModal();
      }});
    }}

    function bindPieClicks() {{
      const pie = document.getElementById('pie');
      pie.addEventListener('click', (event) => {{
        if (!pieSegments.length) return;
        const rect = pie.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const dx = x - cx;
        const dy = y - cy;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const outerRadius = rect.width / 2;
        const innerRadius = outerRadius * 0.53;
        if (distance < innerRadius || distance > outerRadius) return;
        let angle = Math.atan2(dy, dx) * (180 / Math.PI);
        angle = (angle + 90 + 360) % 360;
        const pct = (angle / 360) * 100;
        const hit = pieSegments.find((segment) => pct >= segment.startPct && pct < segment.endPct)
          || pieSegments[pieSegments.length - 1];
        if (hit && hit.label) openDetailModal(hit.label);
      }});
    }}

    async function load() {{
      const url = new URL(window.location.href);
      url.searchParams.set('format', 'json');
      const res = await fetch(url.toString(), {{ headers: {{ Accept: 'application/json' }} }});
      if (!res.ok) {{
        document.getElementById('ownerRows').innerHTML = `<tr><td colspan="7" class="empty">Error loading SC Overview (${{res.status}}).</td></tr>`;
        return;
      }}
      const data = await res.json();
      const totals = data.totals || {{}};
      const touchTotals = data.touch_totals || {{}};
      const touchFilters = data.touch_filters || {{}};
      pieDetails = data.pie_details || {{}};
      document.getElementById('kpiRan').textContent = fmtInt(totals.opps_ran);
      document.getElementById('kpiDemos').textContent = fmtInt(totals.demos);
      document.getElementById('kpiSales').textContent = fmtInt(totals.sales);
      document.getElementById('kpiClose').textContent = fmtPct(totals.close_rate_on_demos);
      document.getElementById('kpiTouchCloses').textContent = fmtInt(touchTotals.two_touch_closes);
      document.getElementById('kpiTouchRate').textContent = fmtPct(touchTotals.touch_close_rate);
      document.getElementById('kpiTouchOpen').textContent = fmtInt(touchTotals.open_touch_opps);
      document.getElementById('kpiTouchStale').textContent = fmtInt(touchTotals.stale_touch_opps);
      document.getElementById('windowMeta').textContent = `${{data.window_start}} to ${{data.window_end}} • America/New_York`;
      document.getElementById('touchWindowMeta').textContent = `${{touchFilters.window_start || data.window_start}} to ${{touchFilters.window_end || data.window_end}} • Two-Touch Sold Date Window`;
      renderPie(Array.isArray(data.pie) ? data.pie : [], Number(totals.completed || 0));
      renderRows(Array.isArray(data.rows) ? data.rows : [], totals);
      renderTouchRows(Array.isArray(data.touch_table) ? data.touch_table : [], touchTotals);
    }}

    document.getElementById('team').addEventListener('change', updateOwnerOptions);
    updateOwnerOptions();
    bindModal();
    bindPieClicks();
    load();
  </script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _check_auth(self):
            return _unauthorized(self)

        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(TZ)
            year = int((qs.get("year", [str(now.year)])[0] or now.year))
            month = int((qs.get("month", [str(now.month)])[0] or now.month))
            touch_year = int((qs.get("touch_year", [str(now.year)])[0] or now.year))
            touch_month = int((qs.get("touch_month", [str(now.month)])[0] or now.month))
            owner_id = compact_str(qs.get("owner_id", [""])[0])
            team = compact_str(qs.get("team", [""])[0])
            lead_source = compact_str(qs.get("lead_source", [""])[0])
            start = compact_str(qs.get("start", [""])[0])
            end = compact_str(qs.get("end", [""])[0])
            touch_start = compact_str(qs.get("touch_start", [""])[0])
            touch_end = compact_str(qs.get("touch_end", [""])[0])
            fmt = compact_str(qs.get("format", [""])[0]).lower()

            db = get_db()
            if fmt == "json":
                payload = build_payload(
                    db,
                    year=year,
                    month=month,
                    start=start or None,
                    end=end or None,
                    touch_year=touch_year,
                    touch_month=touch_month,
                    touch_start=touch_start or None,
                    touch_end=touch_end or None,
                    owner_id=owner_id,
                    team=team,
                    lead_source=lead_source,
                )
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            payload = build_payload(
                db,
                year=year,
                month=month,
                start=start or None,
                end=end or None,
                touch_year=touch_year,
                touch_month=touch_month,
                touch_start=touch_start or None,
                touch_end=touch_end or None,
                owner_id=owner_id,
                team=team,
                lead_source=lead_source,
            )
            html = render_html(
                year=year,
                month=month,
                touch_year=touch_year,
                touch_month=touch_month,
                owner_options=payload["owner_options"],
                selected_team=normalize_team(team),
                selected_owner=owner_id,
                selected_lead_source=lead_source,
                start=start,
                end=end,
                touch_start=touch_start,
                touch_end=touch_end,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as exc:
            body = ("ERROR: " + str(exc)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
