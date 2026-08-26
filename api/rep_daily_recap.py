# -*- coding: utf-8 -*-

"""Vercel Python function: /api/rep_daily_recap

Rep Daily Recap dashboard.

Purpose:
- Show prior-day GHL appointments grouped by opportunity owner.
- Show the logged appointment outcome for each appointment.
- Add prior-day Powerline dials and Raydar doors knocked into each owner bucket
  as a simple "worked yesterday" recap.

Identity join (Powerline / Raydar -> owner row):
- Prefer roster_people_v1.ghl_user_id / raydar_user_id / display_name.
- Also index GHL user names, owner-bucket labels, and OWNER_NAME_OVERRIDES.
- Hyphenated last names accept an unambiguous first+last short form
  ("April Cornell" -> "April Cornell-DeAngelis"). Do not invent knock counts.

Window semantics:
- Default window is yesterday in America/New_York.
- Optional query params:
  - date=YYYY-MM-DD
  - start=YYYY-MM-DD&end=YYYY-MM-DD

Data sources:
- happy-solar Firestore:
  - ghl_opportunities_v2
  - ghl_contacts_v2
  - ghl_pipelines_v2
  - ghl_users_v2
  - roster_people_v1
  - raydar_leads_v1
- Powerline Firestore:
  - powerline_call_history
  - powerline_agents
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


TZ = ZoneInfo("America/New_York")
POWERLINE_DEFAULT_PROJECT_ID = "gen-lang-client-0395385938"
OWNER_NAME_OVERRIDES = {
    "0fhsjcmlntce0cpjyfhj": "William Breen",
}
SETTER_LAST_NAME_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"
SETTER_LAST_NAME_FALLBACK_FIELD_ID = "Xhy6k4xfHRJ6s5IbfA5x"
LEAD_SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"

NICKNAME_EQUIVALENTS = {
    "josh": "joshua",
    "joshua": "josh",
    "zach": "zachary",
    "zachary": "zach",
    "tom": "thomas",
    "thomas": "tom",
    "will": "william",
    "william": "will",
    "mike": "michael",
    "michael": "mike",
}


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def looks_like_identifier(value: Any) -> bool:
    text = compact_str(value)
    if not text or " " in text or len(text) < 12:
        return False
    return all(ch.isalnum() or ch in {"-", "_"} for ch in text)


def html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    try:
        year, month, day = [int(part) for part in str(value).strip().split("-")]
        return year, month, day
    except Exception:
        return None


def parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return parse_iso_dt(value)
    return None


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
    email = compact_str(record.get("email"))
    if "@" in email:
        return email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
    return fallback


def normalize_disposition(value: Any) -> str:
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


def normalize_lead_source(value: Any) -> str:
    text = compact_str(value)
    if not text:
        return "none"
    low = text.lower()
    if low in {"crm ui", "hand", "none", "null", "n/a"}:
        return "none"
    if low == "virtual":
        return "Phones"
    if low == "selfgen":
        return "Self Gen"
    if low == "inbound":
        return "Inbound"
    if low == "3pl/inbound":
        return "3PL/Inbound"
    if low == "phones":
        return "Phones"
    if low == "doors":
        return "Doors"
    if low == "3pl":
        return "3PL"
    if low == "self gen":
        return "Self Gen"
    return text


def format_local_datetime(value: Any) -> str:
    dt = as_dt(value)
    if not dt:
        return ""
    return dt.astimezone(TZ).strftime("%Y-%m-%d %I:%M %p")


def time_only_local(value: Any) -> str:
    dt = as_dt(value)
    if not dt:
        return ""
    return dt.astimezone(TZ).strftime("%I:%M %p").lstrip("0")


def slugify_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", normalize_name_key(value))
    return text.strip("-") or "unknown"


def normalize_name_key(value: Any) -> str:
    text = compact_str(value).lower()
    text = text.replace(".", " ").replace(",", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " ".join(text.split())
    return text


def nickname_aliases(name: str) -> set[str]:
    base = normalize_name_key(name)
    if not base:
        return set()
    aliases = {base}
    parts = base.split()
    if parts:
        first = parts[0]
        alt = NICKNAME_EQUIVALENTS.get(first)
        if alt:
            aliases.add(" ".join([alt] + parts[1:]))
    return aliases


def identity_name_keys(name: str, *, include_short_form: bool = True) -> set[str]:
    """Lookup keys for a person name, including an unambiguous first+last short form.

    Hyphenated last names normalize to extra tokens ("April Cornell-DeAngelis" ->
    "april cornell deangelis"). The short form "april cornell" is also generated
    so Raydar labels that drop the hyphenated suffix can join when unique.
    """
    base = normalize_name_key(name)
    if not base:
        return set()
    keys = set(nickname_aliases(name))
    if include_short_form:
        parts = base.split()
        if len(parts) >= 3:
            keys.add(" ".join(parts[:2]))
    return {key for key in keys if key}


def first_name_equivalent(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if NICKNAME_EQUIVALENTS.get(left) == right or NICKNAME_EQUIVALENTS.get(right) == left:
        return True
    # Allow small prefix-style variations such as "josh" -> "joshua".
    return (len(left) >= 3 and right.startswith(left)) or (len(right) >= 3 and left.startswith(right))


def fuzzy_name_match(left: str, right: str) -> bool:
    left_key = normalize_name_key(left)
    right_key = normalize_name_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if left_key in nickname_aliases(right_key) or right_key in nickname_aliases(left_key):
        return True

    left_parts = left_key.split()
    right_parts = right_key.split()
    if not left_parts or not right_parts:
        return False

    # Strong fuzzy rule for person names: same last name + compatible first name.
    if left_parts[-1] == right_parts[-1] and first_name_equivalent(left_parts[0], right_parts[0]):
        return True

    # Hyphenated last names: "April Cornell" vs "April Cornell-DeAngelis".
    if first_name_equivalent(left_parts[0], right_parts[0]):
        left_rest = left_parts[1:]
        right_rest = right_parts[1:]
        if left_rest and right_rest and (
            left_rest == right_rest[: len(left_rest)] or right_rest == left_rest[: len(right_rest)]
        ):
            return True

    return False


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [
            key
            for key in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(key)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def get_powerline_db() -> firestore.Client:
    creds_json = os.environ.get("POWERLINE_FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("POWERLINE_GCP_PROJECT_ID") or POWERLINE_DEFAULT_PROJECT_ID
    if not creds_json:
        raise RuntimeError("Missing POWERLINE_FIREBASE_SERVICE_ACCOUNT_JSON")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, credentials=creds)


def resolve_window(qs: dict[str, list[str]]) -> tuple[datetime, datetime, str]:
    date_q = compact_str((qs.get("date", [""])[0] or ""))
    start_q = compact_str((qs.get("start", [""])[0] or ""))
    end_q = compact_str((qs.get("end", [""])[0] or ""))

    if date_q:
        parts = parse_date_ymd(date_q)
        if not parts:
            raise ValueError("Invalid date; expected YYYY-MM-DD")
        start_local = datetime(parts[0], parts[1], parts[2], 0, 0, 0, tzinfo=TZ)
        return start_local, start_local + timedelta(days=1), date_q

    if start_q and end_q:
        sp = parse_date_ymd(start_q)
        ep = parse_date_ymd(end_q)
        if not (sp and ep):
            raise ValueError("Invalid start/end; expected YYYY-MM-DD")
        start_local = datetime(sp[0], sp[1], sp[2], 0, 0, 0, tzinfo=TZ)
        end_local_excl = datetime(ep[0], ep[1], ep[2], 0, 0, 0, tzinfo=TZ) + timedelta(days=1)
        return start_local, end_local_excl, start_local.strftime("%Y-%m-%d")

    now_local = datetime.now(TZ)
    default_day = now_local.date() - timedelta(days=1)
    start_local = datetime(default_day.year, default_day.month, default_day.day, 0, 0, 0, tzinfo=TZ)
    return start_local, start_local + timedelta(days=1), start_local.strftime("%Y-%m-%d")


def contact_custom_field(contact: dict[str, Any] | None, field_id: str) -> Any:
    if not isinstance(contact, dict):
        return None
    for cf in (contact.get("customFields") or []):
        if isinstance(cf, dict) and cf.get("id") == field_id:
            return cf.get("value")
    return None


def user_name_lookup(db: firestore.Client) -> dict[str, str]:
    names: dict[str, str] = {}
    for snap in db.collection("ghl_users_v2").stream():
        row = snap.to_dict() or {}
        label = best_person_name(row)
        for key in {compact_str(row.get("id")), compact_str(row.get("userId")), compact_str(snap.id)}:
            if key and label:
                names[key] = label
    return names


def pipeline_name_lookup(db: firestore.Client) -> tuple[dict[str, str], dict[str, str]]:
    pipeline_names: dict[str, str] = {}
    stage_names: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        row = snap.to_dict() or {}
        pid = compact_str(row.get("id") or snap.id)
        pname = compact_str(row.get("name"))
        if pid and pname:
            pipeline_names[pid] = pname
        for stage in row.get("stages") or []:
            sid = compact_str((stage or {}).get("id"))
            sname = compact_str((stage or {}).get("name"))
            if sid and sname:
                stage_names[sid] = sname
    return pipeline_names, stage_names


def resolve_owner_name(opp: dict[str, Any], owner_id: str, user_names: dict[str, str]) -> str:
    if not owner_id:
        return "Unassigned"
    override = OWNER_NAME_OVERRIDES.get(owner_id.lower())
    if override:
        return override
    if owner_id in user_names:
        return user_names[owner_id]
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


def load_rep_roster(db: firestore.Client, user_names: dict[str, str]) -> dict[str, dict[str, str]]:
    """Identity rows from roster_people_v1 keyed by ghl_user_id.

    Do not require role=rep. Closers on the recap are GHL opportunity owners;
    some roster docs omit role/categories even when ghl_user_id and raydar_user_id
    are populated. People without a GHL owner id cannot join to an owner row.
    """
    reps: dict[str, dict[str, str]] = {}
    for snap in db.collection("roster_people_v1").stream():
        row = snap.to_dict() or {}
        owner_id = compact_str(row.get("ghl_user_id") or row.get("ghlUserId"))
        if not owner_id:
            continue
        reps[owner_id] = {
            "owner_id": owner_id,
            "label": compact_str(row.get("display_name"))
            or user_names.get(owner_id)
            or compact_str(row.get("ghl_user_name"))
            or owner_id,
            "team": compact_str(row.get("team") or row.get("segment")),
            "person_key": compact_str(row.get("person_key") or snap.id),
            "raydar_user_id": compact_str(row.get("raydar_user_id")),
            "ghl_user_name": compact_str(row.get("ghl_user_name")) or user_names.get(owner_id, ""),
        }
    return reps


def collect_owner_identities(
    rep_roster: dict[str, dict[str, str]],
    user_names: dict[str, str],
    extra_labels: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge roster, GHL user names, overrides, and live owner-bucket labels."""
    identities: dict[str, dict[str, Any]] = {}

    def upsert(owner_id: str, label: str = "", **extra: Any) -> None:
        owner_id = compact_str(owner_id)
        if not owner_id:
            return
        current = identities.get(owner_id)
        incoming_label = compact_str(label)
        if current is None:
            identities[owner_id] = {
                "owner_id": owner_id,
                "label": incoming_label or compact_str(user_names.get(owner_id)) or owner_id,
                "team": compact_str(extra.get("team")),
                "person_key": compact_str(extra.get("person_key")),
                "raydar_user_id": compact_str(extra.get("raydar_user_id")),
                "ghl_user_name": compact_str(extra.get("ghl_user_name")) or compact_str(user_names.get(owner_id)),
                "extra_names": set(),
            }
            current = identities[owner_id]
        elif incoming_label and incoming_label != current.get("label"):
            current.setdefault("extra_names", set()).add(incoming_label)
        extra_names = current.setdefault("extra_names", set())
        extra_incoming = extra.get("extra_names")
        if isinstance(extra_incoming, (set, list, tuple)):
            extra_names.update(compact_str(item) for item in extra_incoming if compact_str(item))
        for key in ("team", "person_key", "raydar_user_id", "ghl_user_name"):
            value = compact_str(extra.get(key))
            if value and not current.get(key):
                current[key] = value
        if incoming_label and (
            not current.get("label") or current.get("label") == owner_id or looks_like_identifier(current.get("label"))
        ):
            current["label"] = incoming_label

    for owner_id, row in rep_roster.items():
        extra = {key: value for key, value in row.items() if key not in {"owner_id", "label"}}
        upsert(owner_id, compact_str(row.get("label")), **extra)

    for uid, name in user_names.items():
        upsert(uid, name, ghl_user_name=name)

    for uid, name in OWNER_NAME_OVERRIDES.items():
        match = next((key for key in identities if key.lower() == uid.lower()), uid)
        if match in identities:
            identities[match]["label"] = name
            identities[match].setdefault("extra_names", set()).add(name)
        else:
            upsert(match, name)

    if extra_labels:
        for owner_id, label in extra_labels.items():
            upsert(owner_id, label)

    return identities


def _identity_display_names(row: dict[str, Any]) -> set[str]:
    names = {
        compact_str(row.get("label")),
        compact_str(row.get("ghl_user_name")),
    }
    extra = row.get("extra_names")
    if isinstance(extra, (set, list, tuple)):
        names.update(compact_str(item) for item in extra)
    return {name for name in names if name and not looks_like_identifier(name)}


def build_owner_alias_index(identities: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Unique name keys -> owner_id.

    Full-name keys win over hyphenated short forms. "April Cornell" stays on
    the owner whose full label is April Cornell when a second owner is
    April Cornell-DeAngelis. A short form is used only when it is unambiguous.
    """
    full_claimed: dict[str, set[str]] = defaultdict(set)
    short_claimed: dict[str, set[str]] = defaultdict(set)
    for owner_id, row in identities.items():
        for name in _identity_display_names(row):
            full_keys = identity_name_keys(name, include_short_form=False)
            short_keys = identity_name_keys(name, include_short_form=True) - full_keys
            for alias in full_keys:
                full_claimed[alias].add(owner_id)
            for alias in short_keys:
                short_claimed[alias].add(owner_id)

    aliases: dict[str, str] = {}
    for alias, owner_ids in full_claimed.items():
        if len(owner_ids) == 1:
            aliases[alias] = next(iter(owner_ids))
    for alias, owner_ids in short_claimed.items():
        if alias in full_claimed:
            continue
        if len(owner_ids) == 1:
            aliases[alias] = next(iter(owner_ids))
    return aliases


def get_contact(db: firestore.Client, cache: dict[str, dict[str, Any]], contact_id: str) -> dict[str, Any] | None:
    cid = compact_str(contact_id)
    if not cid:
        return None
    if cid in cache:
        return cache[cid]
    snap = db.collection("ghl_contacts_v2").document(cid).get()
    if snap.exists:
        cache[cid] = snap.to_dict() or {}
        return cache[cid]
    docs = list(db.collection("ghl_contacts_v2").where("id", "==", cid).limit(1).stream())
    cache[cid] = (docs[0].to_dict() or {}) if docs else {}
    return cache[cid] or None


def outcome_class(outcome: str) -> str:
    low = outcome.lower()
    if low == "sit":
        return "good"
    if low == "no sit":
        return "warn"
    return "pending"


def map_powerline_agent_to_owner(label: str, alias_index: dict[str, str]) -> str | None:
    key = normalize_name_key(label)
    if not key:
        return None
    if key in alias_index:
        return alias_index[key]
    for alias in nickname_aliases(label):
        if alias in alias_index:
            return alias_index[alias]
    return None


def map_label_to_owner_fuzzy(
    label: str,
    alias_index: dict[str, str],
    identities: dict[str, dict[str, Any]],
) -> str | None:
    owner_key = map_powerline_agent_to_owner(label, alias_index)
    if owner_key:
        return owner_key

    matches: list[str] = []
    for owner_id, row in identities.items():
        candidates = {
            compact_str(row.get("label")),
            compact_str(row.get("ghl_user_name")),
        }
        extra = row.get("extra_names")
        if isinstance(extra, (set, list, tuple)):
            candidates.update(compact_str(item) for item in extra)
        if any(fuzzy_name_match(label, candidate) for candidate in candidates if candidate):
            if owner_id not in matches:
                matches.append(owner_id)
    if len(matches) == 1:
        return matches[0]
    return None


def build_payload(start_local: datetime, end_local_excl: datetime) -> dict[str, Any]:
    db = get_db()
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local_excl.astimezone(timezone.utc)

    user_names = user_name_lookup(db)
    pipeline_names, stage_names = pipeline_name_lookup(db)
    rep_roster = load_rep_roster(db, user_names)
    identities = collect_owner_identities(rep_roster, user_names)

    owner_buckets: dict[str, dict[str, Any]] = {}
    contact_cache: dict[str, dict[str, Any]] = {}
    unmapped_powerline = Counter()
    unmapped_raydar = Counter()

    def ensure_owner_bucket(owner_id: str, label: str) -> dict[str, Any]:
        bucket = owner_buckets.get(owner_id)
        if bucket:
            return bucket
        roster_row = identities.get(owner_id) or rep_roster.get(owner_id, {})
        bucket = {
            "owner_id": owner_id,
            "owner_label": label,
            "owner_slug": slugify_name(label),
            "team": compact_str(roster_row.get("team")) or "",
            "appointments": [],
            "appointment_total": 0,
            "completed_total": 0,
            "sit_total": 0,
            "no_sit_total": 0,
            "pending_total": 0,
            "powerline_dials": 0,
            "powerline_results": Counter(),
            "doors_knocked": 0,
            "door_statuses": Counter(),
        }
        owner_buckets[owner_id] = bucket
        return bucket

    # GHL appointments by yesterday's scheduled appointment time.
    ghl_query = (
        db.collection("ghl_opportunities_v2")
        .where("appointmentStartTime", ">=", start_utc)
        .where("appointmentStartTime", "<", end_utc)
    )

    for snap in ghl_query.stream():
        opp = snap.to_dict() or {}
        appt_dt = as_dt(opp.get("appointmentStartTime"))
        if not appt_dt:
            continue
        owner_id = compact_str(opp.get("assignedTo"))
        owner_label = resolve_owner_name(opp, owner_id, user_names) if owner_id else "Unassigned"
        owner_key = owner_id or normalize_name_key(owner_label) or "unassigned"
        bucket = ensure_owner_bucket(owner_key, owner_label)

        contact = get_contact(db, contact_cache, compact_str(opp.get("contactId")))
        contact_name = ""
        if isinstance(opp.get("contact"), dict):
            contact_name = compact_str((opp.get("contact") or {}).get("name"))
        if not contact_name and isinstance(contact, dict):
            contact_name = compact_str(contact.get("contactName"))
        if not contact_name:
            contact_name = compact_str(opp.get("name"))

        setter_last = (
            compact_str(contact_custom_field(contact, SETTER_LAST_NAME_FIELD_ID))
            or compact_str(contact_custom_field(contact, SETTER_LAST_NAME_FALLBACK_FIELD_ID))
            or compact_str((contact or {}).get("setter"))
        )
        lead_source = normalize_lead_source(contact_custom_field(contact, LEAD_SOURCE_FIELD_ID) if contact else None)
        outcome = normalize_disposition(opp.get("dispositionValue")) or "No outcome logged"
        pipeline_name = pipeline_names.get(compact_str(opp.get("pipelineId")), compact_str(opp.get("pipelineId")) or "Unknown")
        stage_name = stage_names.get(
            compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId")),
            compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId")) or "Unknown",
        )

        bucket["appointments"].append(
            {
                "time_local": time_only_local(appt_dt),
                "appointment_at": format_local_datetime(appt_dt),
                "contact_name": contact_name,
                "outcome": outcome,
                "outcome_class": outcome_class(outcome),
                "pipeline": pipeline_name,
                "stage": stage_name,
                "setter_last_name": setter_last or "—",
                "lead_source": lead_source,
                "opportunity_id": compact_str(opp.get("id") or snap.id),
            }
        )
        bucket["appointment_total"] += 1
        if outcome == "Sit":
            bucket["completed_total"] += 1
            bucket["sit_total"] += 1
        elif outcome == "No Sit":
            bucket["completed_total"] += 1
            bucket["no_sit_total"] += 1
        else:
            bucket["pending_total"] += 1

    # Register live owner-bucket labels so Powerline/Raydar exact names join
    # even when roster_people_v1 is missing the person or omits role=rep.
    identities = collect_owner_identities(
        rep_roster,
        user_names,
        extra_labels={owner_id: bucket["owner_label"] for owner_id, bucket in owner_buckets.items()},
    )
    alias_index = build_owner_alias_index(identities)
    raydar_to_owner = {
        row["raydar_user_id"]: owner_id
        for owner_id, row in identities.items()
        if row.get("raydar_user_id")
    }

    # Powerline calls by agent for the same ET window.
    powerline_available = True
    try:
        powerline_db = get_powerline_db()
        agent_labels: dict[str, str] = {}
        for snap in powerline_db.collection("powerline_agents").stream():
            row = snap.to_dict() or {}
            label = best_person_name(row, fallback="Unknown Agent")
            for key in {compact_str(row.get("id")), compact_str(row.get("userId")), compact_str(row.get("agentId")), compact_str(snap.id)}:
                if key:
                    agent_labels[key] = label

        for snap in powerline_db.collection("powerline_call_history").stream():
            row = snap.to_dict() or {}
            call_dt = parse_iso_dt(row.get("timestamp"))
            if not call_dt:
                continue
            call_local = call_dt.astimezone(TZ)
            if not (start_local <= call_local < end_local_excl):
                continue
            agent_id = compact_str(row.get("agentId"))
            agent_label = agent_labels.get(agent_id) or (f"Unknown Agent ({agent_id[-6:]})" if agent_id else "Unassigned")
            owner_key = map_label_to_owner_fuzzy(agent_label, alias_index, identities)
            if not owner_key:
                unmapped_powerline[agent_label] += 1
                continue
            bucket = ensure_owner_bucket(
                owner_key,
                identities.get(owner_key, {}).get("label") or user_names.get(owner_key) or agent_label,
            )
            result = compact_str(row.get("result")) or "unknown"
            bucket["powerline_dials"] += 1
            bucket["powerline_results"][result] += 1
    except Exception:
        powerline_available = False

    # Raydar door knocks by primary actor for the same ET window.
    raydar_users = {
        snap.id: compact_str((snap.to_dict() or {}).get("name")) or snap.id
        for snap in db.collection("raydar_users_v1").stream()
    }
    for snap in db.collection("raydar_leads_v1").where("dispositionedAt", ">=", start_utc).where("dispositionedAt", "<", end_utc).stream():
        row = snap.to_dict() or {}
        actor = None
        hist0 = (row.get("dispositionHistory") or [None])[0]
        if isinstance(hist0, dict):
            actor = compact_str(hist0.get("userId"))
        if not actor:
            actor = compact_str(row.get("claimedBy"))
        if not actor:
            unmapped_raydar["Unassigned"] += 1
            continue
        owner_key = raydar_to_owner.get(actor)
        actor_name = raydar_users.get(actor, actor)
        if not owner_key:
            # Fallback name match only if the actor name resolves to a rep alias.
            owner_key = map_label_to_owner_fuzzy(actor_name, alias_index, identities)
        if not owner_key:
            unmapped_raydar[actor_name] += 1
            continue
        bucket = ensure_owner_bucket(
            owner_key,
            identities.get(owner_key, {}).get("label") or user_names.get(owner_key) or actor_name,
        )
        status = compact_str(row.get("status")) or "unknown"
        bucket["doors_knocked"] += 1
        bucket["door_statuses"][status] += 1

    owners = []
    for bucket in owner_buckets.values():
        bucket["appointments"].sort(key=lambda item: item["appointment_at"])
        bucket["powerline_results_top"] = [
            {"label": label, "count": count}
            for label, count in bucket["powerline_results"].most_common(5)
        ]
        bucket["door_statuses_top"] = [
            {"label": label, "count": count}
            for label, count in bucket["door_statuses"].most_common(5)
        ]
        bucket["work_total"] = bucket["appointment_total"] + bucket["powerline_dials"] + bucket["doors_knocked"]
        if bucket["work_total"] > 0:
            owners.append(bucket)

    owners.sort(
        key=lambda item: (
            -int(item["work_total"]),
            -int(item["appointment_total"]),
            item["owner_label"].lower(),
        )
    )

    appointment_total = sum(int(item["appointment_total"]) for item in owners)
    completed_total = sum(int(item["completed_total"]) for item in owners)
    powerline_total = sum(int(item["powerline_dials"]) for item in owners)
    raydar_total = sum(int(item["doors_knocked"]) for item in owners)

    return {
        "metric": "Rep Daily Recap",
        "timezone": "America/New_York",
        "window_start_local": start_local.isoformat(),
        "window_end_local_exclusive": end_local_excl.isoformat(),
        "date_label": start_local.strftime("%Y-%m-%d"),
        "summary": {
            "owners_with_activity": len(owners),
            "appointments_total": appointment_total,
            "completed_outcomes_total": completed_total,
            "pending_outcomes_total": appointment_total - completed_total,
            "powerline_dials_total": powerline_total,
            "doors_knocked_total": raydar_total,
            "work_total": appointment_total + powerline_total + raydar_total,
        },
        "owners": owners,
        "powerline_available": powerline_available,
        "unmapped_activity": {
            "powerline": [{"label": label, "count": count} for label, count in unmapped_powerline.most_common(10)],
            "raydar": [{"label": label, "count": count} for label, count in unmapped_raydar.most_common(10)],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def render_stat(label: str, value: Any, sub: str) -> str:
    return f"""
      <div class="stat-card">
        <div class="stat-label">{html_escape(label)}</div>
        <div class="stat-value">{html_escape(value)}</div>
        <div class="stat-sub">{html_escape(sub)}</div>
      </div>
    """


def render_owner_card(owner: dict[str, Any]) -> str:
    summary_bits = []
    for row in owner.get("powerline_results_top", []):
        summary_bits.append(f"{row['label']}: {row['count']}")
    powerline_mix = " | ".join(summary_bits) if summary_bits else "No Powerline results"

    knock_bits = []
    for row in owner.get("door_statuses_top", []):
        knock_bits.append(f"{row['label']}: {row['count']}")
    knock_mix = " | ".join(knock_bits) if knock_bits else "No Raydar knock detail"

    appointments = owner.get("appointments") or []
    if appointments:
        appointment_rows = "".join(
            f"""
              <tr>
                <td>{html_escape(row['time_local'])}</td>
                <td>{html_escape(row['contact_name'])}</td>
                <td><span class="outcome-pill {html_escape(row['outcome_class'])}">{html_escape(row['outcome'])}</span></td>
                <td>{html_escape(row['pipeline'])}</td>
                <td>{html_escape(row['stage'])}</td>
                <td>{html_escape(row['setter_last_name'])}</td>
                <td>{html_escape(row['lead_source'])}</td>
              </tr>
            """
            for row in appointments
        )
    else:
        appointment_rows = """
          <tr>
            <td colspan="7" class="empty-state">No GHL appointments in this window for this owner.</td>
          </tr>
        """

    team_label = f" · {owner['team'].title()}" if owner.get("team") else ""
    return f"""
      <section class="owner-card">
        <div class="owner-header">
          <div>
            <div class="owner-title">{html_escape(owner['owner_label'])}{html_escape(team_label)}</div>
            <div class="owner-sub">Worked total = appointments + Powerline dials + doors knocked</div>
          </div>
          <div class="owner-total">{html_escape(owner['work_total'])}</div>
        </div>
        <div class="owner-stats">
          <div class="mini-stat"><span>Appointments</span><strong>{html_escape(owner['appointment_total'])}</strong></div>
          <div class="mini-stat"><span>Completed</span><strong>{html_escape(owner['completed_total'])}</strong></div>
          <div class="mini-stat"><span>Sits</span><strong>{html_escape(owner['sit_total'])}</strong></div>
          <div class="mini-stat"><span>No Sits</span><strong>{html_escape(owner['no_sit_total'])}</strong></div>
          <div class="mini-stat"><span>Pending</span><strong>{html_escape(owner['pending_total'])}</strong></div>
          <div class="mini-stat"><span>Powerline Dials</span><strong>{html_escape(owner['powerline_dials'])}</strong></div>
          <div class="mini-stat"><span>Doors Knocked</span><strong>{html_escape(owner['doors_knocked'])}</strong></div>
        </div>
        <div class="owner-grid">
          <div class="info-card">
            <div class="info-title">Powerline Result Mix</div>
            <div class="info-body">{html_escape(powerline_mix)}</div>
          </div>
          <div class="info-card">
            <div class="info-title">Door Knock Status Mix</div>
            <div class="info-body">{html_escape(knock_mix)}</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Appointment</th>
                <th>Outcome</th>
                <th>Pipeline</th>
                <th>Stage</th>
                <th>Setter</th>
                <th>Lead Source</th>
              </tr>
            </thead>
            <tbody>
              {appointment_rows}
            </tbody>
          </table>
        </div>
      </section>
    """


def render_html(payload: dict[str, Any], selected_date: str) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("rep_daily_recap")
    summary = payload["summary"]
    owner_cards = "".join(render_owner_card(owner) for owner in payload.get("owners") or [])
    if not owner_cards:
        owner_cards = '<section class="owner-card"><div class="empty-state">No owner activity in this window.</div></section>'

    unmapped_powerline = payload.get("unmapped_activity", {}).get("powerline") or []
    unmapped_raydar = payload.get("unmapped_activity", {}).get("raydar") or []
    unmapped_text = []
    if unmapped_powerline:
        unmapped_text.append(
            "Powerline unmatched: " + ", ".join(f"{row['label']} ({row['count']})" for row in unmapped_powerline[:6])
        )
    if unmapped_raydar:
        unmapped_text.append(
            "Raydar unmatched: " + ", ".join(f"{row['label']} ({row['count']})" for row in unmapped_raydar[:6])
        )
    unmapped_note = " | ".join(unmapped_text) if unmapped_text else "All mapped activity matched to an owner bucket."
    powerline_note = "Powerline live" if payload.get("powerline_available") else "Powerline unavailable in current environment"

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Rep Daily Recap</title>
  <style>
    :root {{
      --bg:#f6f8fb;
      --card:#ffffff;
      --border:#e7ebf0;
      --text:#142033;
      --muted:#66758a;
      --muted2:#94a3b8;
      --pink:#ec4899;
      --pink2:#f472b6;
      --violet:#8b5cf6;
      --green:#10b981;
      --amber:#f59e0b;
      --red:#ef4444;
      --shadow:0 10px 30px rgba(15, 23, 42, 0.07);
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:
      radial-gradient(circle at top left, rgba(236,72,153,0.12), transparent 26%),
      radial-gradient(circle at top right, rgba(139,92,246,0.10), transparent 24%),
      linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
      color:var(--text); }}
    .wrap {{ max-width:1400px; margin:0 auto; padding:24px; }}
    .hero {{ padding:22px 24px; border-radius:22px; background:var(--card); border:1px solid var(--border); box-shadow:var(--shadow); }}
    .title {{ font-size:28px; font-weight:950; letter-spacing:-0.03em; }}
    .subtitle {{ margin-top:6px; color:var(--muted); font-size:14px; }}
    .pinkline {{ height:4px; width:220px; border-radius:999px; margin-top:12px; background:linear-gradient(90deg, var(--pink) 0%, var(--pink2) 55%, rgba(244,114,182,0) 100%); }}
__DASHBOARD_NAV_CSS__
    .filters {{ margin-top:16px; display:flex; gap:10px; flex-wrap:wrap; align-items:end; }}
    .filters label {{ display:block; font-size:12px; color:var(--muted); font-weight:900; margin-bottom:6px; text-transform:uppercase; letter-spacing:.05em; }}
    .filters input[type=date] {{ padding:10px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; font-size:14px; font-weight:800; }}
    .btn {{ display:inline-flex; align-items:center; justify-content:center; border-radius:12px; padding:10px 14px; border:1px solid var(--border); background:#fff; color:#334155; font-size:13px; font-weight:900; text-decoration:none; cursor:pointer; }}
    .btn.primary {{ background:linear-gradient(90deg, var(--pink), #fb7185); color:#fff; border:none; }}
    .grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; margin-top:16px; }}
    .stat-card {{ background:var(--card); border:1px solid var(--border); border-radius:18px; box-shadow:var(--shadow); padding:18px; min-height:120px; }}
    .stat-label {{ color:var(--muted); font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }}
    .stat-value {{ margin-top:10px; font-size:40px; font-weight:950; line-height:1; }}
    .stat-sub {{ margin-top:10px; color:var(--muted); font-size:13px; }}
    .meta-note {{ margin-top:14px; background:#fff7fb; border:1px solid #f6d6e7; color:#7a3158; border-radius:16px; padding:14px 16px; font-size:13px; line-height:1.5; }}
    .owners {{ margin-top:18px; display:flex; flex-direction:column; gap:18px; }}
    .owner-card {{ background:var(--card); border:1px solid var(--border); border-radius:22px; box-shadow:var(--shadow); padding:20px; }}
    .owner-header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
    .owner-title {{ font-size:22px; font-weight:950; letter-spacing:-0.02em; }}
    .owner-sub {{ margin-top:4px; color:var(--muted); font-size:13px; }}
    .owner-total {{ min-width:64px; text-align:center; font-size:40px; font-weight:950; line-height:1; color:#be185d; }}
    .owner-stats {{ display:grid; grid-template-columns:repeat(7, minmax(0,1fr)); gap:10px; margin-top:16px; }}
    .mini-stat {{ border:1px solid var(--border); border-radius:16px; background:#fbfcfe; padding:12px; }}
    .mini-stat span {{ display:block; color:var(--muted); font-size:11px; font-weight:900; text-transform:uppercase; letter-spacing:.05em; }}
    .mini-stat strong {{ display:block; margin-top:8px; font-size:24px; font-weight:950; }}
    .owner-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px; }}
    .info-card {{ border:1px solid var(--border); border-radius:18px; padding:14px 16px; background:linear-gradient(180deg, rgba(236,72,153,0.05), rgba(255,255,255,0)); }}
    .info-title {{ color:#9d174d; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }}
    .info-body {{ margin-top:8px; color:#334155; font-size:14px; line-height:1.5; }}
    .table-wrap {{ margin-top:16px; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:880px; }}
    th, td {{ border-bottom:1px solid var(--border); padding:12px 10px; text-align:left; font-size:14px; }}
    th {{ color:var(--muted); font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; background:#fff8fc; }}
    td {{ font-weight:700; color:#162233; }}
    .outcome-pill {{ display:inline-flex; align-items:center; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:900; }}
    .outcome-pill.good {{ background:rgba(16,185,129,0.12); color:#047857; }}
    .outcome-pill.warn {{ background:rgba(245,158,11,0.14); color:#b45309; }}
    .outcome-pill.pending {{ background:rgba(148,163,184,0.18); color:#475569; }}
    .empty-state {{ color:var(--muted); text-align:center; padding:28px 12px; }}
    @media (max-width: 1180px) {{
      .grid {{ grid-template-columns:repeat(2, minmax(0,1fr)); }}
      .owner-stats {{ grid-template-columns:repeat(3, minmax(0,1fr)); }}
    }}
    @media (max-width: 760px) {{
      .wrap {{ padding:14px; }}
      .grid {{ grid-template-columns:1fr; }}
      .owner-header {{ flex-direction:column; }}
      .owner-stats {{ grid-template-columns:repeat(2, minmax(0,1fr)); }}
      .owner-grid {{ grid-template-columns:1fr; }}
      .owner-total {{ text-align:left; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="title">Rep Daily Recap</div>
      <div class="subtitle">Previous-day rep activity grouped by GHL opportunity owner. Appointments come from GHL; extra work is layered in from Powerline dials and Raydar doors knocked.</div>
      <div class="pinkline"></div>
__DASHBOARD_NAV_HTML__
      <div class="filters">
        <div>
          <label>Date</label>
          <input id="dateInput" type="date" value="{html_escape(selected_date)}" />
        </div>
        <button class="btn primary" id="applyBtn">Apply</button>
        <button class="btn" id="yesterdayBtn">Yesterday</button>
      </div>
    </section>

    <section class="grid">
      {render_stat("Appointments", summary["appointments_total"], "All GHL appointments scheduled in the selected ET day")}
      {render_stat("Completed Outcomes", summary["completed_outcomes_total"], "Appointments with Sit or No Sit logged")}
      {render_stat("Powerline Dials", summary["powerline_dials_total"], powerline_note)}
      {render_stat("Doors Knocked", summary["doors_knocked_total"], "Raydar knocks attributed to mapped rep actors")}
    </section>

    <div class="meta-note">
      <strong>Worked total:</strong> {html_escape(summary["work_total"])} across {html_escape(summary["owners_with_activity"])} owner buckets.
      <br />
      {html_escape(unmapped_note)}
    </div>

    <section class="owners">
      {owner_cards}
    </section>
  </div>

  <script>
    (function() {{
      const dateInput = document.getElementById('dateInput');
      const applyBtn = document.getElementById('applyBtn');
      const yesterdayBtn = document.getElementById('yesterdayBtn');

      function nyYmd(date) {{
        const parts = new Intl.DateTimeFormat('en-CA', {{
          timeZone: 'America/New_York',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }}).formatToParts(date);
        const map = Object.fromEntries(parts.map(p => [p.type, p.value]));
        return `${{map.year}}-${{map.month}}-${{map.day}}`;
      }}

      function ymdAddDays(ymd, delta) {{
        const [y, m, d] = ymd.split('-').map(Number);
        const dt = new Date(Date.UTC(y, m - 1, d));
        dt.setUTCDate(dt.getUTCDate() + delta);
        return `${{dt.getUTCFullYear()}}-${{String(dt.getUTCMonth() + 1).padStart(2, '0')}}-${{String(dt.getUTCDate()).padStart(2, '0')}}`;
      }}

      applyBtn.addEventListener('click', () => {{
        const value = String(dateInput.value || '').trim();
        if (!value) return;
        window.location.search = `?date=${{encodeURIComponent(value)}}`;
      }});

      yesterdayBtn.addEventListener('click', () => {{
        const today = nyYmd(new Date());
        const y = ymdAddDays(today, -1);
        window.location.search = `?date=${{encodeURIComponent(y)}}`;
      }});
    }})();
  </script>
</body>
</html>
"""
    return html.replace("__DASHBOARD_NAV_CSS__", nav_css).replace("__DASHBOARD_NAV_HTML__", nav_html)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            start_local, end_local_excl, selected_date = resolve_window(qs)
            payload = build_payload(start_local, end_local_excl)

            response_format = (qs.get("format", ["html"])[0] or "html").lower()
            if response_format == "json":
                body = json.dumps(payload, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(payload, selected_date).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
