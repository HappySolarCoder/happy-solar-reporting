# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


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
    ]
    for candidate in candidates:
        text = compact_str(candidate)
        if text and not looks_like_identifier(text):
            return text
    return fallback


@dataclass(frozen=True)
class MetricContract:
    metric_name: str = "Sales Cancellations"
    opp_collection: str = "ghl_opportunities_v2"
    contact_collection: str = "ghl_contacts_v2"
    pipeline_collection: str = "ghl_pipelines_v2"
    users_collection: str = "ghl_users_v2"
    sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"
    setter_last_name_custom_field_id: str = "Eq4NLTSkJ56KTxbxypuE"
    setter_last_name_fallback_custom_field_id: str = "Xhy6k4xfHRJ6s5IbfA5x"
    lead_gen_source_custom_field_id: str = "hd5QqHEOVSsPom5bJ32P"
    timezone: str = "America/New_York"
    included_pipeline_names: tuple[str, ...] = (
        "buffalo",
        "syracuse",
        "rochester",
        "virtual",
    )
    sold_stage_ids: tuple[str, ...] = (
        "7981f111-73f2-4593-9662-6b95d99bf51a",
        "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
        "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
        "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
    )
    cancelled_stage_ids: tuple[str, ...] = (
        "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
        "34a1882f-7959-4d22-878d-91fe35a42907",
        "9bd71abf-7285-47bb-8800-a255e7b90630",
        "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
    )


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def parse_date_ymd(s: str | None) -> tuple[int, int, int] | None:
    if not s or not isinstance(s, str):
        return None
    try:
        y, m, d = [int(x) for x in s.strip().split("-")]
        return y, m, d
    except Exception:
        return None


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
    sp = parse_date_ymd(start_ymd)
    ep = parse_date_ymd(end_ymd)
    if not (sp and ep):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
    sy, sm, sd = sp
    ey, em, ed = ep
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def normalize_channel(v: Any) -> str:
    if v is None:
        return "none"
    norm = str(v).strip()
    if norm.lower() in {"crm ui", "hand", "", "none", "null", "n/a"}:
        return "none"
    if norm.lower() == "virtual":
        return "Phones"
    return norm


def resolve_setter(contact: dict[str, Any], c: MetricContract) -> str:
    primary = ""
    fallback = ""
    for cf in (contact.get("customFields") or []):
        if not isinstance(cf, dict):
            continue
        cid = str(cf.get("id") or "")
        val = cf.get("value")
        if val in (None, ""):
            val = cf.get("fieldValueString")
        if cid == c.setter_last_name_custom_field_id:
            primary = str(val or "").strip()
        if cid == c.setter_last_name_fallback_custom_field_id:
            fallback = str(val or "").strip()
    invalid_primary_values = {"rochester", "buffalo", "virtual", "syracuse", "doors", "phones", "3pl", "none"}
    if (not primary or primary.lower() in invalid_primary_values) and fallback:
        return fallback
    return primary or "none"


def compute(db: firestore.Client, c: MetricContract, *, year: int, month: int, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    if start and end:
        start_local, end_local, start_iso, end_iso = date_range_window(start, end, c.timezone)
    else:
        start_local, end_local, start_iso, end_iso = month_window(year, month, c.timezone)

    sold_set = set(c.sold_stage_ids)
    cancelled_set = set(c.cancelled_stage_ids)
    start_date_str = start_local.date().isoformat()
    end_date_str = end_local.date().isoformat()
    included_pipelines = {x.strip().lower() for x in c.included_pipeline_names}

    contacts_map: dict[str, dict[str, Any]] = {}
    for snap in db.collection(c.contact_collection).stream():
        d = snap.to_dict() or {}
        cid = str(d.get("id") or snap.id).strip()
        if cid:
            contacts_map[cid] = d

    pipeline_name_cache: dict[str, str] = {}
    for snap in db.collection(c.pipeline_collection).stream():
        d = snap.to_dict() or {}
        pid = str(d.get("id") or snap.id).strip()
        name = str(d.get("name") or "").strip()
        if pid and name:
            pipeline_name_cache[pid] = name

    user_name_cache: dict[str, str] = {}
    for snap in db.collection(c.users_collection).stream():
        d = snap.to_dict() or {}
        name = best_person_name(d)
        for key in {compact_str(d.get("id")), compact_str(d.get("userId")), compact_str(snap.id)}:
            if key and name:
                user_name_cache[key] = name

    def owner_name(opp: dict[str, Any]) -> str:
        owner_id = str(opp.get("assignedTo") or "").strip()
        if not owner_id:
            return "unassigned"
        override = OWNER_NAME_OVERRIDES.get(owner_id.lower())
        if override:
            return override
        hit = user_name_cache.get(owner_id)
        if hit:
            return hit
        for k in ("assignedToName", "assignedToUserName", "assignedUserName", "ownerName"):
            v = opp.get(k)
            if v and str(v).strip():
                text = compact_str(v)
                if not looks_like_identifier(text):
                    return text
        au = opp.get("assignedToUser")
        if isinstance(au, dict):
            text = best_person_name(au)
            if text:
                return text
        return f"Unknown User ({owner_id[-6:]})"

    def touch(store: dict[str, dict[str, Any]], label: str, is_cancelled: bool) -> None:
        row = store.setdefault(
            label,
            {
                "label": label,
                "sold_date_total": 0,
                "cancelled": 0,
                "not_cancelled": 0,
                "cancellation_rate": 0.0,
            },
        )
        row["sold_date_total"] += 1
        if is_cancelled:
            row["cancelled"] += 1

    sold_date_total = 0
    cancelled = 0
    scanned = 0
    matched_pipeline = 0
    matched_window = 0
    trend_map: dict[str, dict[str, int]] = {}
    owner_store: dict[str, dict[str, Any]] = {}
    pipeline_store: dict[str, dict[str, Any]] = {}
    setter_store: dict[str, dict[str, Any]] = {}
    source_store: dict[str, dict[str, Any]] = {}
    detail_rows: list[dict[str, Any]] = []

    for snap in db.collection(c.opp_collection).stream():
        scanned += 1
        opp = snap.to_dict() or {}

        contact_id = str(opp.get("contactId") or "").strip()
        if not contact_id:
            continue
        contact = contacts_map.get(contact_id)
        if not contact:
            continue

        pipeline_id = str(opp.get("pipelineId") or "").strip()
        pipeline_name = pipeline_name_cache.get(pipeline_id, pipeline_id or "unknown")
        if str(pipeline_name).strip().lower() not in included_pipelines:
            continue
        matched_pipeline += 1

        sold_date_raw = None
        for cf in (contact.get("customFields") or []):
            if isinstance(cf, dict) and str(cf.get("id") or "") == c.sold_date_custom_field_id:
                sold_date_raw = cf.get("value")
                break
        sold_date = sold_date_raw[:10] if isinstance(sold_date_raw, str) and len(sold_date_raw) >= 10 else None
        if not sold_date:
            continue
        if not (start_date_str <= sold_date < end_date_str):
            continue
        matched_window += 1

        stage_id = str(opp.get("pipelineStageId") or "").strip()
        is_cancelled = stage_id in cancelled_set
        owner = owner_name(opp)
        setter = resolve_setter(contact, c)
        lead_source = "none"
        for cf in (contact.get("customFields") or []):
            if isinstance(cf, dict) and str(cf.get("id") or "") == c.lead_gen_source_custom_field_id:
                lead_source = normalize_channel(cf.get("value") or cf.get("fieldValueString"))
                break

        sold_date_total += 1
        if is_cancelled:
            cancelled += 1

        touch(owner_store, owner, is_cancelled)
        touch(pipeline_store, pipeline_name, is_cancelled)
        touch(setter_store, setter, is_cancelled)
        touch(source_store, lead_source, is_cancelled)

        t = trend_map.setdefault(sold_date, {"date": sold_date, "sold_date_total": 0, "cancelled": 0, "not_cancelled": 0})
        t["sold_date_total"] += 1
        if is_cancelled:
            t["cancelled"] += 1

        if is_cancelled and len(detail_rows) < 200:
            detail_rows.append({
                "contactName": str(contact.get("contactName") or "").strip(),
                "owner": owner,
                "setter": setter,
                "pipeline": pipeline_name,
                "leadSource": lead_source,
                "soldDate": sold_date,
                "lastStageChangeAt": str(opp.get("lastStageChangeAt") or ""),
                "updatedAt": str(opp.get("updatedAt") or ""),
            })

    def finalize(store: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for row in store.values():
            row["not_cancelled"] = row["sold_date_total"] - row["cancelled"]
            row["cancellation_rate"] = round((row["cancelled"] / row["sold_date_total"] * 100.0), 1) if row["sold_date_total"] else 0.0
            rows.append(row)
        return sorted(rows, key=lambda r: (-r["cancelled"], r["label"]))

    trend = []
    for date_key in sorted(trend_map.keys()):
        row = trend_map[date_key]
        row["not_cancelled"] = row["sold_date_total"] - row["cancelled"]
        trend.append(row)

    return {
        "metric": c.metric_name,
        "timezone": c.timezone,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "window_semantics": "Window is filtered by Contact Sold Date (date-only, America/New_York). Cancellation indicator is current Sale Cancelled stage. Cancellation rate denominator is all included-pipeline opportunities with Sold Date in the window.",
        "kpis": {
            "sold_date_total": sold_date_total,
            "cancelled_sales": cancelled,
            "not_cancelled_sales": sold_date_total - cancelled,
            "cancellation_rate": round((cancelled / sold_date_total * 100.0), 1) if sold_date_total else 0.0,
        },
        "debug": {
            "opportunities_scanned": scanned,
            "opportunities_matched_pipeline_scope": matched_pipeline,
            "opportunities_matched_sold_date_window": matched_window,
        },
        "contract": {
            "contact_join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
            "window_field": "ghl_contacts_v2.customFields[P9oBjgbZjJdeE0OkBj9T]",
            "included_pipeline_names": list(c.included_pipeline_names),
            "sold_stage_ids": list(c.sold_stage_ids),
            "cancelled_stage_ids": list(c.cancelled_stage_ids),
        },
        "trend": trend,
        "tables": {
            "by_owner": finalize(owner_store),
            "by_pipeline": finalize(pipeline_store),
            "by_setter": finalize(setter_store),
            "by_lead_source": finalize(source_store),
            "cancelled_detail": detail_rows,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def render_html(payload: dict[str, Any]) -> str:
    return "<html><body><pre>" + json.dumps(payload, indent=2) + "</pre></body></html>"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = qs.get("format", [""])[0].lower() == "json"
            now = datetime.utcnow()
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            start = (qs.get("start", [""])[0] or "").strip() or None
            end = (qs.get("end", [""])[0] or "").strip() or None
            payload = compute(get_db(), MetricContract(), year=year, month=month, start=start, end=end)
            body = json.dumps(payload).encode("utf-8") if want_json else render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if want_json else "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
