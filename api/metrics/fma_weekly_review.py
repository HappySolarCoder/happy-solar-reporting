# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/fma_weekly_review

Aggregated weekly-review payload for FMA performance reviews.

Metric semantics intentionally mirror the established dashboard contracts:
- Knocks: Raydar dispositioned leads that count as door knocks
- Appointments: GHL opportunities created by setter last name (`pipeline_scope=all`, excluding inbound/lead locker)
- Demos: GHL opportunities ran with disposition `Sit`
- Sales: canonical sales by setter last name using sold-date window

This endpoint also adds weekly-review-only outputs:
- per-day trend series
- row-level ran appointment review list
- per-setter outcome split (Sit / No Sit / Sales)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

TZ = ZoneInfo("America/New_York")
SETTER_LAST_NAME_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"
SETTER_LAST_NAME_FALLBACK_FIELD_ID = "Xhy6k4xfHRJ6s5IbfA5x"
LEAD_SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"
DISPOSITION_NOTES_FIELD_ID = "cCcnzoIp8YgW2Pr0sB5E"
DISPO_FIELD_ID = "GYGpLKBPfMpiBqyU2ogQ"
SOLD_DATE_CUSTOM_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"
INVALID_SETTER_VALUES = {
    "rochester",
    "buffalo",
    "virtual",
    "syracuse",
    "doors",
    "phones",
    "3pl",
    "none",
}
SOLD_STAGE_IDS = {
    "7981f111-73f2-4593-9662-6b95d99bf51a",
    "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
    "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
    "34a1882f-7959-4d22-878d-91fe35a42907",
    "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
    "9bd71abf-7285-47bb-8800-a255e7b90630",
    "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
    "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
}
OWNER_NAME_OVERRIDES = {
    "0fhsjcmlntce0cpjyfhj": "William Breen",
}


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


def parse_iso_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    return None


def normalize_disposition(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    low = text.lower().replace("_", " ").replace("-", " ")
    while "  " in low:
        low = low.replace("  ", " ")
    if low == "sit":
        return "Sit"
    if low in {"no sit", "nosit"}:
        return "No Sit"
    return text


def cf_value(cf: dict[str, Any]) -> Any:
    if not isinstance(cf, dict):
        return None
    if cf.get("value") not in (None, ""):
        return cf.get("value")
    for key in ("fieldValueString", "fieldValueNumber", "fieldValueBoolean", "fieldValue"):
        if cf.get(key) not in (None, ""):
            return cf.get(key)
    return None


def get_custom_field_value(custom_fields: Any, field_id: str) -> str:
    if not isinstance(custom_fields, list):
        return ""
    for cf in custom_fields:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("id") or "").strip() != field_id:
            continue
        value = cf_value(cf)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_last_name(value: Any) -> str:
    return compact_str(value).lower()


def normalize_channel(value: Any) -> str:
    if value is None:
        return "none"
    text = compact_str(value)
    if not text:
        return "none"
    low = text.lower()
    if low in {"crm ui", "hand", "manual", "none", "null", "n/a"}:
        return "none"
    if low in {"virtual", "virt"}:
        return "Phones"
    if low in {"phones", "phone", "ph", "call", "calls"}:
        return "Phones"
    if low in {"doors", "door", "d2d"}:
        return "Doors"
    if low in {"3pl", "3p", "threepl"}:
        return "3PL"
    return text


def ymd_range_or_default(qs: dict[str, list[str]]) -> tuple[str, str]:
    start = compact_str((qs.get("start", [""])[0] or ""))
    end = compact_str((qs.get("end", [""])[0] or ""))
    if start and end:
        return start, end

    now = datetime.now(TZ)
    this_monday = datetime(now.year, now.month, now.day, tzinfo=TZ) - timedelta(days=now.weekday())
    last_week_start = this_monday - timedelta(days=7)
    last_week_end = this_monday - timedelta(days=1)
    return last_week_start.date().isoformat(), last_week_end.date().isoformat()


def parse_ymd(value: str) -> tuple[int, int, int]:
    parts = [int(x) for x in value.split("-")]
    if len(parts) != 3:
        raise ValueError("expected YYYY-MM-DD")
    return parts[0], parts[1], parts[2]


def date_window(start_ymd: str, end_ymd: str) -> tuple[datetime, datetime]:
    sy, sm, sd = parse_ymd(start_ymd)
    ey, em, ed = parse_ymd(end_ymd)
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=TZ)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=TZ) + timedelta(days=1)
    return start_local, end_local


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def load_lookup_map(db: firestore.Client, collection: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for snap in db.collection(collection).stream():
        data = snap.to_dict() or {}
        out[str(data.get("id") or snap.id).strip()] = data
    return out


def build_pipeline_maps(db: firestore.Client) -> tuple[dict[str, str], dict[str, str]]:
    pipeline_names: dict[str, str] = {}
    stage_names: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        data = snap.to_dict() or {}
        pid = str(data.get("id") or snap.id).strip()
        if pid:
            pipeline_names[pid] = str(data.get("name") or pid)
        stages = data.get("stages") or []
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                sid = str(stage.get("id") or "").strip()
                sname = compact_str(stage.get("name"))
                if sid and sname and sid not in stage_names:
                    stage_names[sid] = sname
    return pipeline_names, stage_names


def build_ghl_user_names(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("ghl_users_v2").stream():
        data = snap.to_dict() or {}
        name = best_person_name(data)
        for key in {compact_str(data.get("id")), compact_str(data.get("userId")), compact_str(snap.id)}:
            if key and name:
                out[key] = name
    return out


def build_raydar_user_names(db: firestore.Client) -> dict[str, str]:
    out: dict[str, str] = {}
    for snap in db.collection("raydar_users_v1").stream():
        data = snap.to_dict() or {}
        name = best_person_name(data, fallback=str(data.get("name") or snap.id))
        for key in {compact_str(data.get("id")), compact_str(data.get("userId")), compact_str(snap.id)}:
            if key and name:
                out[key] = name
    return out


def build_raydar_dispositions(db: firestore.Client) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for snap in db.collection("raydar_dispositions_v1").stream():
        data = snap.to_dict() or {}
        out[str(snap.id)] = {
            "name": compact_str(data.get("name") or snap.id),
            "countsAsDoorKnock": bool(data.get("countsAsDoorKnock") is True),
        }
    return out


def resolve_owner_name(opp: dict[str, Any], user_names: dict[str, str]) -> str:
    owner_id = compact_str(opp.get("assignedTo"))
    if owner_id:
        override = OWNER_NAME_OVERRIDES.get(owner_id.lower())
        if override:
            return override
        if owner_id in user_names:
            return user_names[owner_id]
    for key in ("assignedToName", "assignedToUserName", "assignedUserName", "ownerName"):
        value = compact_str(opp.get(key))
        if value and not looks_like_identifier(value):
            return value
    assigned_user = opp.get("assignedToUser")
    if isinstance(assigned_user, dict):
        name = best_person_name(assigned_user)
        if name:
            return name
    if owner_id:
        return f"Unknown User ({owner_id[-6:]})"
    return "unassigned"


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
        parts = [compact_str(contact.get("firstName")), compact_str(contact.get("lastName"))]
        joined = " ".join([p for p in parts if p])
        if joined:
            return joined
    return ""


def resolve_setter_last_name(opp: dict[str, Any], contact: dict[str, Any] | None) -> str:
    opp_value = get_custom_field_value(opp.get("customFields") or [], SETTER_LAST_NAME_FIELD_ID)
    contact_primary = get_custom_field_value((contact or {}).get("customFields") or [], SETTER_LAST_NAME_FIELD_ID)
    contact_fallback = get_custom_field_value((contact or {}).get("customFields") or [], SETTER_LAST_NAME_FALLBACK_FIELD_ID)

    candidates = [opp_value, contact_primary, contact_fallback]
    chosen = ""
    for candidate in candidates:
        text = compact_str(candidate)
        if not text:
            continue
        if text.lower() in INVALID_SETTER_VALUES:
            continue
        chosen = text
        break
    if not chosen:
        for candidate in candidates:
            text = compact_str(candidate)
            if text:
                chosen = text
                break
    return chosen


def date_key_local(dt: datetime) -> str:
    return dt.astimezone(TZ).date().isoformat()


def build_payload(db: firestore.Client, *, start: str, end: str) -> dict[str, Any]:
    start_local, end_local = date_window(start, end)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    today_utc = datetime.now(timezone.utc)
    year = start_local.year
    month = start_local.month
    day_count = max((end_local.date() - start_local.date()).days, 1)

    contacts = load_lookup_map(db, "ghl_contacts_v2")
    pipeline_names, stage_names = build_pipeline_maps(db)
    ghl_user_names = build_ghl_user_names(db)
    raydar_user_names = build_raydar_user_names(db)
    raydar_dispositions = build_raydar_dispositions(db)

    roster_people: list[dict[str, Any]] = []
    person_by_key: dict[str, dict[str, Any]] = {}
    person_by_setter_last: dict[str, dict[str, Any]] = {}
    person_by_raydar_id: dict[str, dict[str, Any]] = {}

    for snap in db.collection("roster_people_v1").stream():
        data = snap.to_dict() or {}
        if compact_str(data.get("role")).lower() != "setter":
            continue
        person_key = compact_str(data.get("person_key") or snap.id)
        setter_last = compact_str(data.get("ghl_setter_last_name"))
        raydar_id = compact_str(data.get("raydar_user_id"))
        display_name = compact_str(data.get("display_name"))
        if not display_name:
            display_name = raydar_user_names.get(raydar_id) or setter_last or person_key
        if not (setter_last or raydar_id):
            continue

        row = {
            "person_key": person_key,
            "display_name": display_name,
            "ghl_setter_last_name": setter_last,
            "raydar_user_id": raydar_id,
            "metrics": {
                "knocks": 0,
                "appointments": 0,
                "demos": 0,
                "ran": 0,
                "no_sit": 0,
                "sales": 0,
            },
            "daily": {},
        }
        roster_people.append(row)
        person_by_key[person_key] = row
        if setter_last:
            person_by_setter_last[normalize_last_name(setter_last)] = row
        if raydar_id:
            person_by_raydar_id[raydar_id] = row

    daily_totals: dict[str, dict[str, int]] = {}
    ran_appointments: list[dict[str, Any]] = []

    def ensure_daily(bucket: dict[str, Any], key: str) -> dict[str, int]:
        if key not in bucket:
            bucket[key] = {
                "knocks": 0,
                "appointments": 0,
                "demos": 0,
                "sales": 0,
                "sit": 0,
                "no_sit": 0,
                "ran": 0,
            }
        return bucket[key]

    def bump_person(person: dict[str, Any], day_key: str, metric: str, amount: int = 1) -> None:
        person["metrics"][metric] = int(person["metrics"].get(metric, 0)) + amount
        ensure_daily(person["daily"], day_key)[metric] += amount
        ensure_daily(daily_totals, day_key)[metric] += amount

    # Raydar knocks
    lead_query = (
        db.collection("raydar_leads_v1")
        .where("dispositionedAt", ">=", start_utc)
        .where("dispositionedAt", "<", end_utc)
    )
    for snap in lead_query.stream():
        data = snap.to_dict() or {}
        ts = parse_iso_dt(data.get("dispositionedAt"))
        if not ts:
            continue

        actor = None
        hist = data.get("dispositionHistory") or []
        if isinstance(hist, list) and hist:
            first = hist[0]
            if isinstance(first, dict):
                actor = compact_str(first.get("userId"))
        if not actor:
            actor = compact_str(data.get("claimedBy"))
        if not actor:
            continue

        dispo_key = data.get("dispositionId")
        if dispo_key in (None, ""):
            dispo_key = data.get("status")
        dispo_rec = raydar_dispositions.get(str(dispo_key), {})
        if not bool(dispo_rec.get("countsAsDoorKnock") is True):
            continue

        person = person_by_raydar_id.get(actor)
        if not person:
            continue
        bump_person(person, date_key_local(ts), "knocks", 1)

    # GHL opp-derived metrics
    for snap in db.collection("ghl_opportunities_v2").stream():
        opp = snap.to_dict() or {}
        pipeline_id = compact_str(opp.get("pipelineId"))
        pipeline_name = compact_str(pipeline_names.get(pipeline_id) or pipeline_id or "unknown")
        if pipeline_name.lower() == "inbound/lead locker":
            continue

        contact_id = compact_str(opp.get("contactId"))
        contact = contacts.get(contact_id)
        setter_last = resolve_setter_last_name(opp, contact)
        setter_key = normalize_last_name(setter_last)
        person = person_by_setter_last.get(setter_key)
        if not person:
            continue

        created_at = parse_iso_dt(opp.get("createdAt"))
        if created_at:
            created_local = created_at.astimezone(TZ)
            if start_local <= created_local < end_local:
                bump_person(person, created_local.date().isoformat(), "appointments", 1)

        occurred_at = parse_iso_dt(opp.get("appointmentOccurredAt"))
        disposition = normalize_disposition(opp.get("dispositionValue"))
        if occurred_at and occurred_at <= today_utc and disposition in {"Sit", "No Sit"}:
            occurred_local = occurred_at.astimezone(TZ)
            if start_local <= occurred_local < end_local:
                bump_person(person, occurred_local.date().isoformat(), "ran", 1)
                bump_person(person, occurred_local.date().isoformat(), "sit" if disposition == "Sit" else "no_sit", 1)
                if disposition == "Sit":
                    bump_person(person, occurred_local.date().isoformat(), "demos", 1)

                stage_id = compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId"))
                notes = compact_str(
                    opp.get("dispositionNotes")
                    or opp.get("dispositionNote")
                    or opp.get("notes")
                    or get_custom_field_value(opp.get("customFields") or [], DISPOSITION_NOTES_FIELD_ID)
                )
                ran_appointments.append(
                    {
                        "person_key": person["person_key"],
                        "display_name": person["display_name"],
                        "setter_last_name": setter_last,
                        "appointment_occurred_at": occurred_local.isoformat(),
                        "outcome": disposition,
                        "contact": resolve_contact_name(opp, contact),
                        "owner": resolve_owner_name(opp, ghl_user_names),
                        "pipeline": pipeline_name,
                        "pipeline_stage": compact_str(stage_names.get(stage_id) or stage_id),
                        "opportunity_id": compact_str(opp.get("id") or snap.id),
                        "disposition_notes": notes,
                        "is_sale_stage": stage_id in SOLD_STAGE_IDS,
                    }
                )

        sale_stage_id = compact_str(opp.get("pipelineStageId") or opp.get("pipelineStageUId"))
        if sale_stage_id not in SOLD_STAGE_IDS:
            continue

        sold_date_raw = get_custom_field_value((contact or {}).get("customFields") or [], SOLD_DATE_CUSTOM_FIELD_ID)
        sold_date_str = sold_date_raw[:10] if isinstance(sold_date_raw, str) and len(sold_date_raw) >= 10 else ""
        if not sold_date_str:
            continue
        try:
            sold_local = datetime.strptime(sold_date_str, "%Y-%m-%d").replace(tzinfo=TZ)
        except Exception:
            continue
        if not (start_local <= sold_local < end_local):
            continue
        bump_person(person, sold_local.date().isoformat(), "sales", 1)

    roster_people.sort(key=lambda row: (-row["metrics"]["knocks"], -row["metrics"]["appointments"], row["display_name"].lower()))
    ran_appointments.sort(key=lambda row: row["appointment_occurred_at"], reverse=True)

    totals = {
        "knocks": sum(int(row["metrics"]["knocks"]) for row in roster_people),
        "appointments": sum(int(row["metrics"]["appointments"]) for row in roster_people),
        "demos": sum(int(row["metrics"]["demos"]) for row in roster_people),
        "ran": sum(int(row["metrics"]["ran"]) for row in roster_people),
        "no_sit": sum(int(row["metrics"]["no_sit"]) for row in roster_people),
        "sales": sum(int(row["metrics"]["sales"]) for row in roster_people),
    }

    outcome_totals = {
        "sit": sum(int(row["metrics"]["demos"]) for row in roster_people),
        "no_sit": sum(int(row["metrics"]["no_sit"]) for row in roster_people),
        "sales": sum(int(row["metrics"]["sales"]) for row in roster_people),
    }

    daily_series = []
    current = start_local
    while current < end_local:
        key = current.date().isoformat()
        bucket = ensure_daily(daily_totals, key)
        daily_series.append(
            {
                "date": key,
                "knocks": int(bucket["knocks"]),
                "appointments": int(bucket["appointments"]),
                "demos": int(bucket["demos"]),
                "sales": int(bucket["sales"]),
                "sit": int(bucket["sit"]),
                "no_sit": int(bucket["no_sit"]),
                "ran": int(bucket["ran"]),
            }
        )
        current += timedelta(days=1)

    people_payload = []
    for row in roster_people:
        metrics = row["metrics"]
        people_payload.append(
            {
                "person_key": row["person_key"],
                "display_name": row["display_name"],
                "ghl_setter_last_name": row["ghl_setter_last_name"],
                "raydar_user_id": row["raydar_user_id"],
                "knocks": int(metrics["knocks"]),
                "appointments": int(metrics["appointments"]),
                "demos": int(metrics["demos"]),
                "ran": int(metrics["ran"]),
                "no_sit": int(metrics["no_sit"]),
                "sales": int(metrics["sales"]),
                "daily": row["daily"],
            }
        )

    return {
        "metric": "FMA Weekly Review",
        "timezone": "America/New_York",
        "start": start,
        "end": end,
        "window_start_local": start_local.isoformat(),
        "window_end_local": end_local.isoformat(),
        "day_count": day_count,
        "totals": totals,
        "daily_averages": {k: round(v / day_count, 2) for k, v in totals.items() if k in {"knocks", "appointments", "demos", "sales"}},
        "outcome_totals": outcome_totals,
        "people": people_payload,
        "daily_series": daily_series,
        "ran_appointments": ran_appointments,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": {
            "knocks": "Raydar dispositioned leads that count as door knocks (actor attribution matches current FMA dashboard logic).",
            "appointments": "GHL opportunities created by setter last name, pipeline_scope=all, excluding inbound/lead locker.",
            "demos": "GHL opportunities ran with disposition Sit.",
            "sales": "Canonical sales by setter last name using sold-date window.",
        },
        "debug": {
            "year_hint": year,
            "month_hint": month,
            "roster_count": len(roster_people),
            "ran_appointment_rows": len(ran_appointments),
        },
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            start, end = ymd_range_or_default(qs)
            payload = build_payload(get_db(), start=start, end=end)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
