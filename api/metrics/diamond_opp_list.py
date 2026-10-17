# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/diamond_opp_list

One Diamond opportunity per row. The population is opportunities_created
with pipeline_scope=all, then created_rows() from diamond_sweeper: Sweeper/
Rehash Last Name equals Diamond, case-insensitive. That is the same set as
the Diamond Sweeper "Opps created" KPI for the same dates.

Deleted opportunities are not in ghl_opportunities_v2. A deleted opp created
within 10 minutes of another opp for the same lead is ignored because it is
not in that collection. Live opportunities created a few minutes apart both
stay. This list does not pull deleted opps back in from stage history.

Dates are the opportunity created date in America/New_York. All time uses
2025-01-01 through today. The default row order is appointment time, latest
first, with opportunities that have no appointment last. Phone numbers are
omitted unless the request is a same-origin dashboard fetch or presents the
Settings password.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from diamond_sweeper import (
    DIAMOND_LAST_NAME,
    created_rows,
    fill_pipeline_stages,
    pipeline_stage_name,
    resolve_window,
)

NY = ZoneInfo("America/New_York")
ALL_TIME_START = "2025-01-01"
TITLE = "Diamond — Opportunity List"
GHL_OPPORTUNITY_URL = (
    "https://app.gohighlevel.com/v2/location/{location_id}/opportunities/list/{opp_id}?tab=OpportunityDetails"
)
SIBLING_CACHE = "public, s-maxage=600, stale-while-revalidate=3600"
PHONE_CACHE = "private, no-store"
OPP_COLLECTION = "ghl_opportunities_v2"
CONTACT_COLLECTION = "ghl_contacts_v2"


def _header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return "" if value is None else str(value)
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name)
    return "" if value is None else str(value)


def _settings_password_matches(headers: Any) -> bool:
    password = os.environ.get("SETTINGS_PASSWORD") or ""
    if not password:
        return False
    auth = _header(headers, "Authorization")
    if not auth.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth.split(" ", 1)[1].strip()).decode("utf-8")
        _user, presented = raw.split(":", 1)
    except Exception:
        return False
    if len(presented) != len(password):
        return False
    return hmac.compare_digest(presented, password)


def phones_allowed(headers: Any) -> bool:
    """Phone numbers stay off a bare request.

    The page itself is open, same as Diamond Sweeper. A browser fetch from
    that page sends Sec-Fetch-Site: same-origin, which the page cannot forge
    from another origin. Settings basic auth also unlocks the numbers.
    """
    site = _header(headers, "Sec-Fetch-Site").strip().lower()
    if site in {"same-origin", "same-site"}:
        return True
    return _settings_password_matches(headers)


def resolve_list_window(qs: dict[str, list[str]], now: datetime | None = None) -> tuple[int, int, str, str]:
    """start/end or year/month use Diamond Sweeper's window. Otherwise all time."""
    start = (qs.get("start") or [""])[0].strip()
    end = (qs.get("end") or [""])[0].strip()
    year_raw = (qs.get("year") or [""])[0].strip()
    month_raw = (qs.get("month") or [""])[0].strip()
    if start or end or year_raw or month_raw:
        year, month, resolved_start, resolved_end = resolve_window(qs, now)
        if resolved_start and resolved_end:
            return year, month, resolved_start, resolved_end
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=NY)
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=NY)
        last = (next_month - timedelta(days=1)).date().isoformat()
        return year, month, f"{year:04d}-{month:02d}-01", last
    clock = now or datetime.now(NY)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=NY)
    else:
        clock = clock.astimezone(NY)
    end_ymd = clock.date().isoformat()
    year, month, _day = (int(part) for part in ALL_TIME_START.split("-"))
    return year, month, ALL_TIME_START, end_ymd


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    to_dt = getattr(value, "to_datetime", None) or getattr(value, "ToDatetime", None)
    if callable(to_dt):
        try:
            return as_datetime(to_dt())
        except Exception:
            return None
    return None


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_appointment_et(value: Any) -> str:
    """America/New_York clock time. Blank when the opportunity has no appointment."""
    moment = as_datetime(value)
    if moment is None:
        return ""
    local = moment.astimezone(NY)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{_MONTHS[local.month - 1]} {local.day}, {local.year}, {hour}:{local.minute:02d} {ampm} ET"


def appointment_moment(opp: dict | None) -> Any:
    if not isinstance(opp, dict):
        return None
    for key in ("appointmentStartTime", "appointmentScheduledAtCanonical", "appointmentDateTime"):
        if opp.get(key) not in (None, ""):
            return opp.get(key)
    return None


def person_name(contact: dict | None, opp: dict | None) -> str:
    if isinstance(contact, dict):
        full = " ".join(
            part
            for part in (compact(contact.get("firstName")), compact(contact.get("lastName")))
            if part
        )
        if full:
            return full
        for key in ("name", "contactName", "fullName"):
            text = compact(contact.get(key))
            if text:
                return text
    if isinstance(opp, dict):
        for key in ("contactName", "name"):
            text = compact(opp.get(key))
            if text:
                return text
    return ""


def contact_phone(contact: dict | None) -> str:
    if not isinstance(contact, dict):
        return ""
    for key in ("phone", "phoneNumber", "mobile"):
        text = compact(contact.get(key))
        if text:
            return text
    return ""


def location_id(opp: dict | None, contact: dict | None) -> str:
    """Same source as missing_dispos: opportunity locationId, then the contact."""
    loc = compact((opp or {}).get("locationId") if isinstance(opp, dict) else "")
    if not loc and isinstance(contact, dict):
        loc = compact(contact.get("locationId"))
    return loc


def opportunity_url(loc: str, opp_id: str) -> str:
    if not loc or not opp_id:
        return ""
    return GHL_OPPORTUNITY_URL.format(location_id=loc, opp_id=opp_id)


def appointment_outcome(stage: str, disposition: str) -> str:
    stage_text = compact(stage)
    disposition_text = compact(disposition)
    if stage_text and disposition_text:
        return f"{stage_text} · {disposition_text}"
    return stage_text or disposition_text


def load_docs_by_ids(db, collection: str, doc_ids) -> dict[str, dict]:
    """Bounded get_all by document id. Does not stream the collection."""
    needed: list[str] = []
    seen: set[str] = set()
    for raw in doc_ids:
        doc_id = compact(raw)
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        needed.append(doc_id)
    if not needed or not hasattr(db, "get_all") or not hasattr(db, "collection"):
        return {}
    refs = [db.collection(collection).document(doc_id) for doc_id in needed]
    found: dict[str, dict] = {}
    for index in range(0, len(refs), 300):
        for snap in db.get_all(refs[index : index + 300]):
            exists = getattr(snap, "exists", True)
            if exists is False:
                continue
            data = snap.to_dict() or {}
            if not isinstance(data, dict):
                continue
            for key in (getattr(snap, "id", ""), data.get("id")):
                text = compact(key)
                if text:
                    found[text] = data
    return found


def appointment_iso(value: Any) -> str:
    """UTC timestamp for sorting. Blank when the opportunity has no appointment."""
    moment = as_datetime(value)
    if moment is None:
        return ""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pipeline_id_of(row: dict | None, opp: dict | None) -> str:
    pid = compact(row.get("pipelineId")) if isinstance(row, dict) else ""
    if pid:
        return pid
    if isinstance(opp, dict):
        return compact(opp.get("pipelineId"))
    return ""


def load_pipeline_directory(db, pipeline_ids) -> tuple[dict[str, str], dict[str, str]]:
    """Pipeline and stage names from ghl_pipelines_v2.

    Uses sold_date_gaps.load_pipelines_by_ids, the same bounded get_all
    fill_pipeline_stages uses. A lookup failure leaves both maps empty.
    """
    try:
        from sold_date_gaps import load_pipelines_by_ids

        names, stages = load_pipelines_by_ids(db, pipeline_ids)
    except Exception:
        return {}, {}
    clean_names: dict[str, str] = {}
    if isinstance(names, dict):
        for key, value in names.items():
            pid = compact(key)
            label = compact(value)
            if pid and label:
                clean_names[pid] = label
    return clean_names, stages if isinstance(stages, dict) else {}


def apply_directory_stages(rows: list[dict[str, Any]], stage_names: dict[str, str]) -> None:
    if not stage_names:
        return
    for row in rows:
        if not isinstance(row, dict) or pipeline_stage_name(row):
            continue
        name = pipeline_stage_name(row, stage_names)
        if name:
            row["pipelineStage"] = name


def pipeline_label(row: dict | None, opp: dict | None, names: dict[str, str]) -> str:
    pid = pipeline_id_of(row, opp)
    looked = names.get(pid, "") if pid else ""
    if looked:
        return looked
    return compact(row.get("pipeline")) if isinstance(row, dict) else ""


def _sort_key(row: dict[str, Any]) -> tuple[bool, float, str]:
    """Appointment time, latest first. No appointment sorts last."""
    moment = as_datetime(row.get("appointmentAtIso"))
    stamp = 0.0 if moment is None else moment.timestamp()
    return (moment is None, -stamp, str(row.get("opportunityId") or ""))


def compute_diamond_opp_list(
    db,
    *,
    year: int,
    month: int,
    start: str,
    end: str,
    include_phones: bool = False,
    last_name: str = DIAMOND_LAST_NAME,
) -> dict[str, Any]:
    from opportunities_created import MetricContract, compute

    created = compute(
        db,
        MetricContract(),
        year=year,
        month=month,
        start=start,
        end=end,
        pipeline_scope="all",
    )
    appointments = created_rows(created, last_name)
    contacts = load_docs_by_ids(db, CONTACT_COLLECTION, (row.get("contactId") for row in appointments))
    opps = load_docs_by_ids(db, OPP_COLLECTION, (row.get("opportunityId") for row in appointments))
    directory_names, stage_names = load_pipeline_directory(
        db,
        (
            pipeline_id_of(row, opps.get(str(row.get("opportunityId") or "")))
            for row in appointments
        ),
    )
    apply_directory_stages(appointments, stage_names)
    fill_pipeline_stages(db, appointments)

    rows: list[dict[str, Any]] = []
    for row in appointments:
        opp_id = str(row.get("opportunityId") or "")
        contact_id = compact(row.get("contactId"))
        opp = opps.get(opp_id)
        contact = contacts.get(contact_id) if contact_id else None
        stage = pipeline_stage_name(row) or compact(row.get("pipelineStage"))
        disposition = ""
        if isinstance(opp, dict):
            disposition = compact(opp.get("dispositionValue") or opp.get("disposition"))
        if not disposition:
            disposition = compact(row.get("disposition"))
        moment = appointment_moment(opp)
        item = {
            "opportunityId": opp_id,
            "contactId": contact_id or None,
            "name": person_name(contact, opp),
            "opportunityUrl": opportunity_url(location_id(opp, contact), opp_id),
            "pipeline": pipeline_label(row, opp, directory_names),
            "pipelineStage": stage,
            "appointmentOutcome": appointment_outcome(stage, disposition),
            "appointmentAt": format_appointment_et(moment),
            "appointmentAtIso": appointment_iso(moment),
            "createdAt": row.get("createdAt") or "",
        }
        if disposition:
            item["disposition"] = disposition
        if include_phones:
            item["phone"] = contact_phone(contact)
        rows.append(item)
    rows.sort(key=_sort_key)
    return {
        "metric": "diamond_opp_list",
        "title": TITLE,
        "last_name": last_name,
        "timezone": "America/New_York",
        "date_field": "createdAt",
        "date_note": "Dates filter on the opportunity created date (ET).",
        "year": year,
        "month": month,
        "start": start,
        "end": end,
        "all_time_start": ALL_TIME_START,
        "window_start_local": created.get("window_start_local"),
        "window_end_local": created.get("window_end_local"),
        "row_count": len(rows),
        "phones_included": bool(include_phones),
        "rows": rows,
        "contract": {
            "population": (
                "created_rows() of opportunities_created.compute pipeline_scope=all. "
                "Sweeper/Rehash Last Name equals Diamond, case-insensitive. "
                "One row per opportunity. Default order is appointment time, latest "
                "first. Opportunities with no appointment are last. The date "
                "filter is still the opportunity created date."
            ),
            "sort": (
                "appointmentAtIso is the real appointment timestamp. "
                "The page sorts that value, not the ET display string."
            ),
            "pipeline": (
                "ghl_opportunities_v2.pipelineId -> ghl_pipelines_v2.name via "
                "sold_date_gaps.load_pipelines_by_ids, the same bounded read "
                "fill_pipeline_stages uses. Falls back to the name already on "
                "the created row when the directory has none."
            ),
            "opps_created": (
                "len(rows) equals Diamond Sweeper opps_created for the same start and end"
            ),
            "deleted_opps": (
                "Deleted opportunities are not in ghl_opportunities_v2, so a deleted opp "
                "created within 10 minutes of another opp for the same lead is ignored. "
                "Live opportunities are not collapsed by that window."
            ),
            "appointment": (
                "appointmentStartTime, else appointmentScheduledAtCanonical, else "
                "appointmentDateTime, shown in America/New_York and labeled ET. "
                "Blank when none of those is set."
            ),
            "outcome": (
                "pipeline stage from pipeline_stage_name / fill_pipeline_stages, "
                "plus dispositionValue when the opportunity document has it"
            ),
            "phone": (
                "ghl_contacts_v2.phone via get_all by contact id. "
                "Omitted on an unauthenticated request."
            ),
            "name_url": GHL_OPPORTUNITY_URL,
            "collections": [OPP_COLLECTION, CONTACT_COLLECTION, "ghl_pipelines_v2"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            year, month, start, end = resolve_list_window(qs)
            allowed = phones_allowed(self.headers)
            from sales import get_db

            payload = compute_diamond_opp_list(
                get_db(),
                year=year,
                month=month,
                start=start,
                end=end,
                include_phones=allowed,
            )
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", PHONE_CACHE if allowed else SIBLING_CACHE)
            self.send_header("Vary", "Sec-Fetch-Site, Authorization")
            self.end_headers()
            self.wfile.write(body)
        except ValueError as exc:
            self._err(400, "ERROR: " + str(exc))
        except Exception:
            self._err(500, "ERROR: diamond opportunity list unavailable")

    def _err(self, code: int, text: str):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
