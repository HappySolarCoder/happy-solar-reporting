# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/project_management

JSON for the Project Management hub and Hold / Cancelled dashboards.
Rows come from the Monday Process Board NY snapshot the hub already
publishes. This module does not write to Monday or GoHighLevel.

GoHighLevel links reuse the opportunity detail URL already used by
Diamond — Opportunity List and Missing Dispositions:

https://app.gohighlevel.com/v2/location/{locationId}/opportunities/list/{oppId}?tab=OpportunityDetails

A row with an opportunity id uses that URL. A row with only a contact
id uses the contact page. Anything else is matched against the synced
GoHighLevel collections (ghl_contacts_v2 and ghl_opportunities_v2):
normalized phone, then email, then customer name. Several opportunities
on one contact prefer a project or sold stage, then the most recent.
A contact with no opportunity uses the contact page. Anything still
unmatched stays plain text.

The lookup is a handful of batched Firestore `in` queries plus one
pipeline read, cached in memory. It does not read one document per row.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

SNAPSHOT_URL = os.environ.get(
    "PM_HUB_DATA_URL",
    "https://happy-solar-monday-pm.vercel.app/hub-data.js",
)
GHL_APP_ORIGIN = "https://app.gohighlevel.com"
DEFAULT_GHL_LOCATION_ID = "MMKRDviKggXzlcHQTnvZ"
GHL_OPPORTUNITY_URL = (
    "https://app.gohighlevel.com/v2/location/{location_id}/opportunities/list/{opp_id}?tab=OpportunityDetails"
)
GHL_CONTACT_URL = "https://app.gohighlevel.com/v2/location/{location_id}/contacts/detail/{contact_id}"
ACTIVE_SECTIONS = ("onboarding", "ep_ops", "ep_installation")
HOLD_SECTION = "hold_cancel"
CANCELLATION_START_MONTH = "2026-01"
SNAPSHOT_TTL_SECONDS = 300
GHL_INDEX_TTL_SECONDS = 900
FIRESTORE_IN_LIMIT = 30
MAX_CONTACTS_PER_KEY = 8
CONTACT_COLLECTION = "ghl_contacts_v2"
OPP_COLLECTION = "ghl_opportunities_v2"
PIPELINE_COLLECTION = "ghl_pipelines_v2"
CONTACT_FIELDS = (
    "id",
    "phone",
    "email",
    "firstName",
    "lastName",
    "contactName",
    "name",
    "fullName",
    "locationId",
    "dateUpdated",
    "dateAdded",
    "additionalPhones",
    "additionalEmails",
)
OPP_FIELDS = (
    "id",
    "contactId",
    "locationId",
    "name",
    "pipelineStageId",
    "pipelineStageName",
    "stageName",
    "createdAt",
    "updatedAt",
    "lastStatusChangeAt",
    "lastStageChangeAt",
)
_NAME_WORD = re.compile(r"[A-Za-z][A-Za-z']*")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PROJECT_STAGE = re.compile(
    r"sold|sale cancel|project|install|permit|\bpto\b|finaliz|final approval|"
    r"interconnect|onboarding|site survey|site evaluation|inspection|engineering",
    re.IGNORECASE,
)
_GHL_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "index": None}

LOCATION_KEYS = ("ghlLocationId", "ghl_location_id", "locationId", "location_id")
OPPORTUNITY_KEYS = (
    "ghlOpportunityId",
    "ghl_opportunity_id",
    "opportunityId",
    "opportunity_id",
    "oppId",
    "opp_id",
)
CONTACT_KEYS = ("ghlContactId", "ghl_contact_id", "contactId", "contact_id")

LANES: tuple[tuple[str, str, str], ...] = (
    ("onboarding", "Onboarding", "Project Verification → Site Evaluation → Site Review."),
    ("ep_ops", "EP Ops", "ENG/FIN/PERM, ESOW / Final Approval, Install Ready."),
    (
        "ep_installation",
        "EP Installation",
        "Being Installed → Build / Elec Inspection → Post Install → PTO → Finalized.",
    ),
    (
        "hold_cancel",
        "Hold / Cancel",
        "Validation Hold, HOLD / HOLD 2026, and Cancelled (HO Cancelled / Cancelled at door / Cancel interconnect).",
    ),
)

_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def is_ghl_id(value: Any) -> bool:
    text = compact_text(value)
    return bool(text) and all(ch.isalnum() or ch in "-_" for ch in text)


def ghl_location_id(value: Any = None) -> str:
    return compact_text(value) or compact_text(os.environ.get("GHL_LOCATION_ID")) or DEFAULT_GHL_LOCATION_ID


def ghl_opportunity_url(location_id: Any, opportunity_id: Any) -> str:
    loc = compact_text(location_id)
    opp = compact_text(opportunity_id)
    if not is_ghl_id(loc) or not is_ghl_id(opp):
        return ""
    return GHL_OPPORTUNITY_URL.format(location_id=loc, opp_id=opp)


def ghl_contact_url(location_id: Any, contact_id: Any) -> str:
    loc = compact_text(location_id)
    contact = compact_text(contact_id)
    if not is_ghl_id(loc) or not is_ghl_id(contact):
        return ""
    return GHL_CONTACT_URL.format(location_id=loc, contact_id=contact)


def _nested_ghl(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("ghl", "gohighlevel", "goHighLevel"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return {}


def pick_field(row: dict[str, Any], keys: Iterable[str]) -> str:
    sources = (row, _nested_ghl(row))
    for source in sources:
        for key in keys:
            if key not in source:
                continue
            text = compact_text(source.get(key))
            if text:
                return text
    return ""


def phone_link(row: dict[str, Any]) -> str:
    """Opportunity detail when an opp id is present, else the contact page."""
    opportunity = compact_text(row.get("ghlOpportunityUrl"))
    if opportunity:
        return opportunity
    return compact_text(row.get("ghlContactUrl"))


def attach_ghl_links(row: dict[str, Any], *, default_location: Any = None) -> dict[str, Any]:
    item = dict(row)
    location = pick_field(item, LOCATION_KEYS)
    opportunity_id = pick_field(item, OPPORTUNITY_KEYS)
    contact_id = pick_field(item, CONTACT_KEYS)
    if not is_ghl_id(opportunity_id):
        opportunity_id = ""
    if not is_ghl_id(contact_id):
        contact_id = ""
    if not is_ghl_id(location) and (opportunity_id or contact_id):
        location = ghl_location_id(default_location)
    elif not is_ghl_id(location):
        location = ""
    opportunity_url = ghl_opportunity_url(location, opportunity_id) if opportunity_id else ""
    contact_url = ghl_contact_url(location, contact_id) if contact_id and not opportunity_url else ""
    if not opportunity_url and contact_id:
        contact_url = ghl_contact_url(location, contact_id)
    item["ghlLocationId"] = location if (opportunity_url or contact_url) else ""
    item["ghlOpportunityId"] = opportunity_id if opportunity_url else ""
    item["ghlContactId"] = contact_id if contact_url or opportunity_url else ""
    item["ghlOpportunityUrl"] = opportunity_url
    item["ghlContactUrl"] = contact_url
    item["phoneHref"] = opportunity_url or contact_url
    return item


def phone_key(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 10:
        return ""
    return digits[-10:]


def phone_keys(value: Any) -> list[str]:
    """Last-10 keys for one phone field. Separators keep two numbers apart."""
    if isinstance(value, dict):
        return phone_keys(value.get("phone") or value.get("number") or value.get("value"))
    if isinstance(value, (list, tuple)):
        found: list[str] = []
        for item in value:
            for key in phone_keys(item):
                if key not in found:
                    found.append(key)
        return found
    keys: list[str] = []
    for part in re.split(r"[A-Za-z;/|]+", str(value or "")):
        key = phone_key(part)
        if key and key not in keys:
            keys.append(key)
    if not keys:
        key = phone_key(value)
        if key:
            keys.append(key)
    return keys


def phone_query_values(key: str) -> list[str]:
    """Formats stored on ghl_contacts_v2.phone. The sync uses +1 and 10 digits."""
    if len(key) != 10 or not key.isdigit():
        return []
    return [f"+1{key}", f"1{key}", key]


def email_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return email_keys(value.get("email") or value.get("address") or value.get("value"))
    if isinstance(value, (list, tuple)):
        found: list[str] = []
        for item in value:
            for key in email_keys(item):
                if key not in found:
                    found.append(key)
        return found
    found = []
    for match in _EMAIL.findall(str(value or "")):
        key = match.casefold()
        if key not in found:
            found.append(key)
    return found


def email_query_values(value: Any) -> list[str]:
    found: list[str] = []
    for match in _EMAIL.findall(str(value or "")):
        for item in (match, match.casefold()):
            if item not in found:
                found.append(item)
    return found


def _name_tokens(value: Any) -> list[str]:
    return _NAME_WORD.findall(compact_text(value))


def _split_person_name(value: Any) -> tuple[list[str], list[str]]:
    text = compact_text(value)
    if not text:
        return [], []
    if "," in text:
        last_text, _, first_text = text.partition(",")
        first = _name_tokens(first_text)
        last = _name_tokens(last_text)
        if first and last:
            return first, last
    tokens = _name_tokens(text)
    if len(tokens) >= 2:
        return tokens[:-1], tokens[-1:]
    return [], []


def name_match_keys(value: Any) -> list[str]:
    """Case-folded first/last keys, including Last, First reversed."""
    first, last = _split_person_name(value)
    if not first or not last:
        return []
    raw = (
        " ".join(first + last),
        " ".join(last + first),
        f"{first[0]} {last[-1]}",
        f"{last[-1]} {first[0]}",
    )
    keys: list[str] = []
    for item in raw:
        key = " ".join(item.casefold().split())
        if " " not in key or key in keys:
            continue
        keys.append(key)
    return keys


def contact_name_keys(contact: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    first = _name_tokens(contact.get("firstName"))
    last = _name_tokens(contact.get("lastName"))
    if first and last:
        keys.extend(name_match_keys(f"{' '.join(last)}, {' '.join(first)}"))
    for field in ("contactName", "name", "fullName"):
        keys.extend(name_match_keys(contact.get(field)))
    found: list[str] = []
    for key in keys:
        if key not in found:
            found.append(key)
    return found


def name_query_values(value: Any) -> list[str]:
    """Original-case strings to query. GHL contact names are First Last."""
    first, last = _split_person_name(value)
    if not first or not last:
        return []
    forms = (
        f"{' '.join(first)} {' '.join(last)}",
        f"{' '.join(last)}, {' '.join(first)}",
        f"{first[0]} {last[-1]}",
        f"{last[-1]}, {first[0]}",
    )
    found: list[str] = []
    for item in forms:
        text = " ".join(item.split())
        if text and text not in found:
            found.append(text)
    return found


def last_name_query_values(value: Any) -> list[str]:
    _first, last = _split_person_name(value)
    if not last:
        return []
    text = " ".join(last)
    titled = " ".join(part[:1].upper() + part[1:].lower() for part in last)
    found: list[str] = []
    for item in (text, titled):
        if item and item not in found:
            found.append(item)
    return found


def timestamp_seconds(value: Any) -> float:
    if value is None or value == "" or isinstance(value, bool):
        return 0.0
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    if isinstance(value, (int, float)):
        num = float(value)
        if num > 10_000_000_000:
            return num / 1000.0
        if num > 1_000_000_000:
            return num
        return 0.0
    text = compact_text(value)
    if not text:
        return 0.0
    if text.isdigit():
        return timestamp_seconds(int(text))
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def project_sold_stage_ids() -> set[str]:
    """Sold and Sale Cancelled stage ids shared with the sales metric."""
    try:
        from sales import SalesMetricContract

        return {compact_text(stage_id) for stage_id in SalesMetricContract().stage_ids if compact_text(stage_id)}
    except Exception:
        return set()


def stage_is_project_or_sold(stage_id: Any, stage_name: Any, sold_ids: set[str] | None = None) -> bool:
    stage = compact_text(stage_id)
    if stage and stage in (sold_ids or set()):
        return True
    return bool(_PROJECT_STAGE.search(compact_text(stage_name)))


def opp_recency(opp: dict[str, Any]) -> float:
    return max(
        timestamp_seconds(opp.get(key))
        for key in ("updatedAt", "createdAt", "lastStatusChangeAt", "lastStageChangeAt")
    )


def contact_recency(contact: dict[str, Any]) -> float:
    return max(timestamp_seconds(contact.get(key)) for key in ("dateUpdated", "dateAdded", "updatedAt", "createdAt"))


def contact_phone_values(contact: dict[str, Any]) -> list[Any]:
    values: list[Any] = [contact.get("phone")]
    extra = contact.get("additionalPhones") or contact.get("additionalPhone") or []
    if isinstance(extra, dict):
        extra = list(extra.values())
    if isinstance(extra, list):
        values.extend(extra)
    return values


def contact_email_values(contact: dict[str, Any]) -> list[Any]:
    values: list[Any] = [contact.get("email")]
    extra = contact.get("additionalEmails") or contact.get("additionalEmail") or []
    if isinstance(extra, dict):
        extra = list(extra.values())
    if isinstance(extra, list):
        values.extend(extra)
    return values


def empty_ghl_index() -> dict[str, Any]:
    return {"by_phone": {}, "by_email": {}, "by_name": {}, "contacts": {}, "opps_by_contact": {}}


def _append_key(bucket: dict[str, list[str]], key: str, contact_id: str) -> None:
    if not key or not contact_id:
        return
    found = bucket.setdefault(key, [])
    if contact_id not in found:
        found.append(contact_id)


def build_ghl_link_index(
    contacts: Iterable[dict[str, Any]],
    opportunities: Iterable[dict[str, Any]],
    stage_names: dict[str, str] | None = None,
    sold_ids: set[str] | None = None,
) -> dict[str, Any]:
    """In-memory phone, email, and name index. No Firestore reads."""
    names = stage_names or {}
    sold = sold_ids if sold_ids is not None else project_sold_stage_ids()
    index = empty_ghl_index()
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        contact_id = compact_text(contact.get("contact_id") or contact.get("id") or contact.get("_doc_id"))
        if not is_ghl_id(contact_id):
            continue
        current = index["contacts"].get(contact_id)
        recency = contact_recency(contact)
        if current is None or recency >= current["recency"]:
            index["contacts"][contact_id] = {
                "contact_id": contact_id,
                "location_id": compact_text(contact.get("locationId") or contact.get("location_id")),
                "recency": recency,
            }
        for value in contact_phone_values(contact):
            for key in phone_keys(value):
                _append_key(index["by_phone"], key, contact_id)
        for value in contact_email_values(contact):
            for key in email_keys(value):
                _append_key(index["by_email"], key, contact_id)
        for key in contact_name_keys(contact):
            _append_key(index["by_name"], key, contact_id)
    for opp in opportunities:
        if not isinstance(opp, dict):
            continue
        opportunity_id = compact_text(opp.get("opportunity_id") or opp.get("id") or opp.get("_doc_id"))
        contact_id = compact_text(opp.get("contactId") or opp.get("contact_id"))
        if not is_ghl_id(opportunity_id) or not is_ghl_id(contact_id):
            continue
        stage_id = compact_text(opp.get("pipelineStageId"))
        stage_name = compact_text(
            opp.get("pipelineStageName") or opp.get("stageName") or names.get(stage_id)
        )
        location_id = compact_text(opp.get("locationId") or opp.get("location_id"))
        if not location_id:
            stored = index["contacts"].get(contact_id) or {}
            location_id = compact_text(stored.get("location_id"))
        choice = {
            "opportunity_id": opportunity_id,
            "contact_id": contact_id,
            "location_id": location_id,
            "project_or_sold": stage_is_project_or_sold(stage_id, stage_name, sold),
            "recency": opp_recency(opp),
        }
        bucket = index["opps_by_contact"].setdefault(contact_id, [])
        if any(item["opportunity_id"] == opportunity_id for item in bucket):
            continue
        bucket.append(choice)
        for key in name_match_keys(opp.get("name")):
            _append_key(index["by_name"], key, contact_id)
        if contact_id not in index["contacts"]:
            index["contacts"][contact_id] = {
                "contact_id": contact_id,
                "location_id": location_id,
                "recency": choice["recency"],
            }
    return index


def _contact_ids_for(index: dict[str, Any], kind: str, keys: Iterable[str]) -> list[str]:
    found: list[str] = []
    buckets = index.get(kind) or {}
    for key in keys:
        bucket = buckets.get(key) or []
        if len(bucket) > MAX_CONTACTS_PER_KEY:
            continue
        for contact_id in bucket:
            if contact_id not in found:
                found.append(contact_id)
    return found


def best_opportunity(opportunities: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    choices = [opp for opp in opportunities if isinstance(opp, dict) and opp.get("opportunity_id")]
    if not choices:
        return None
    return max(
        choices,
        key=lambda opp: (
            1 if opp.get("project_or_sold") else 0,
            float(opp.get("recency") or 0),
            compact_text(opp.get("opportunity_id")),
        ),
    )


def resolve_ghl_match(row: dict[str, Any], index: dict[str, Any] | None) -> dict[str, str] | None:
    """Phone, then email, then name. An earlier tier wins even with no opportunity."""
    if not isinstance(index, dict):
        return None
    tiers = (
        ("by_phone", phone_keys(row.get("permit_phone"))),
        ("by_email", email_keys(row.get("permit_email"))),
        ("by_name", name_match_keys(row.get("display_name"))),
    )
    contacts = index.get("contacts") or {}
    opps_by_contact = index.get("opps_by_contact") or {}
    for kind, keys in tiers:
        if not keys:
            continue
        contact_ids = _contact_ids_for(index, kind, keys)
        if not contact_ids:
            continue
        choices: list[dict[str, Any]] = []
        for contact_id in contact_ids:
            choices.extend(opps_by_contact.get(contact_id) or [])
        best = best_opportunity(choices)
        if best is not None:
            return {
                "opportunity_id": compact_text(best.get("opportunity_id")),
                "contact_id": compact_text(best.get("contact_id")),
                "location_id": compact_text(best.get("location_id")),
            }
        stored = [contacts[contact_id] for contact_id in contact_ids if contact_id in contacts]
        if not stored:
            continue
        chosen = max(stored, key=lambda item: (float(item.get("recency") or 0), item.get("contact_id") or ""))
        return {
            "opportunity_id": "",
            "contact_id": compact_text(chosen.get("contact_id")),
            "location_id": compact_text(chosen.get("location_id")),
        }
    return None


def apply_ghl_index(
    row: dict[str, Any],
    index: dict[str, Any] | None,
    *,
    default_location: Any = None,
) -> dict[str, Any]:
    if compact_text(row.get("phoneHref")) or not isinstance(index, dict):
        return row
    match = resolve_ghl_match(row, index)
    if not match:
        return row
    enriched = dict(row)
    if match.get("opportunity_id"):
        enriched["opportunityId"] = match["opportunity_id"]
    if match.get("contact_id"):
        enriched["contactId"] = match["contact_id"]
    if match.get("location_id"):
        enriched["locationId"] = match["location_id"]
    return attach_ghl_links(enriched, default_location=default_location)


def ghl_link_kind_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    opportunity = 0
    contact = 0
    plain = 0
    for row in rows:
        href = compact_text(row.get("phoneHref") if isinstance(row, dict) else "")
        if "/opportunities/list/" in href:
            opportunity += 1
        elif "/contacts/detail/" in href:
            contact += 1
        else:
            plain += 1
    return {
        "opportunity": opportunity,
        "contact": contact,
        "plain": plain,
        "rows": opportunity + contact + plain,
    }


def _unique_texts(values: Iterable[Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = compact_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        found.append(text)
    return found


def _chunks(values: Iterable[Any], size: int = FIRESTORE_IN_LIMIT) -> list[list[str]]:
    clean = _unique_texts(values)
    return [clean[start : start + size] for start in range(0, len(clean), size)]


def _stream_in(db: Any, collection: str, field: str, values: Iterable[Any], fields: Iterable[str]) -> list[Any]:
    snaps: list[Any] = []
    columns = list(fields)
    for batch in _chunks(values):
        query = db.collection(collection).where(field, "in", batch)
        select = getattr(query, "select", None)
        if select is not None:
            query = select(columns)
        snaps.extend(query.stream())
    return snaps


def _snap_dict(snap: Any) -> dict[str, Any]:
    data = snap.to_dict() or {}
    if not isinstance(data, dict):
        return {}
    item = dict(data)
    item["_doc_id"] = compact_text(getattr(snap, "id", "") or item.get("id"))
    if not item.get("id"):
        item["id"] = item["_doc_id"]
    return item


def _stage_names(db: Any) -> dict[str, str]:
    names: dict[str, str] = {}
    query = db.collection(PIPELINE_COLLECTION)
    select = getattr(query, "select", None)
    if select is not None:
        query = select(["id", "stages"])
    for snap in query.stream():
        data = snap.to_dict() or {}
        stages = data.get("stages") or []
        if not isinstance(stages, list):
            continue
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_id = compact_text(stage.get("id"))
            stage_name = compact_text(stage.get("name"))
            if stage_id and stage_name and stage_id not in names:
                names[stage_id] = stage_name
    return names


def _lookup_signature(rows: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in phone_keys(row.get("permit_phone")):
            parts.append("p:" + key)
        for key in email_keys(row.get("permit_email")):
            parts.append("e:" + key)
        for key in name_match_keys(row.get("display_name")):
            parts.append("n:" + key)
    digest = hashlib.sha1("\n".join(sorted(parts)).encode("utf-8")).hexdigest()
    return digest


def query_ghl_link_index(db: Any, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Batched contact and opportunity reads for the rows that need a link.

    Phone and email run first. Name queries run only for rows those two
    missed, so a shared last name is not scanned for every project.
    Opportunities are loaded once, by contact id, in batches of 30.
    """
    listed = [row for row in rows if isinstance(row, dict)]
    phone_values: list[str] = []
    email_values: list[str] = []
    for row in listed:
        for key in phone_keys(row.get("permit_phone")):
            phone_values.extend(phone_query_values(key))
        email_values.extend(email_query_values(row.get("permit_email")))
    contacts: dict[str, dict[str, Any]] = {}

    def absorb(snaps: Iterable[Any]) -> None:
        for snap in snaps:
            item = _snap_dict(snap)
            contact_id = compact_text(item.get("id") or item.get("_doc_id"))
            if contact_id:
                contacts[contact_id] = item

    if phone_values:
        absorb(_stream_in(db, CONTACT_COLLECTION, "phone", phone_values, CONTACT_FIELDS))
    if email_values:
        absorb(_stream_in(db, CONTACT_COLLECTION, "email", email_values, CONTACT_FIELDS))

    partial = build_ghl_link_index(contacts.values(), [], sold_ids=set())
    name_values: list[str] = []
    last_values: list[str] = []
    for row in listed:
        if phone_keys(row.get("permit_phone")) and _contact_ids_for(partial, "by_phone", phone_keys(row.get("permit_phone"))):
            continue
        if email_keys(row.get("permit_email")) and _contact_ids_for(partial, "by_email", email_keys(row.get("permit_email"))):
            continue
        name_values.extend(name_query_values(row.get("display_name")))
        last_values.extend(last_name_query_values(row.get("display_name")))
    if name_values:
        absorb(_stream_in(db, CONTACT_COLLECTION, "contactName", name_values, CONTACT_FIELDS))
    if last_values:
        absorb(_stream_in(db, CONTACT_COLLECTION, "lastName", last_values, CONTACT_FIELDS))

    wanted_names = set()
    for value in name_values:
        wanted_names.update(name_match_keys(value))
    wanted_phones = {key for row in listed for key in phone_keys(row.get("permit_phone"))}
    wanted_emails = {key for row in listed for key in email_keys(row.get("permit_email"))}
    relevant: dict[str, dict[str, Any]] = {}
    for contact_id, contact in contacts.items():
        phones = {key for value in contact_phone_values(contact) for key in phone_keys(value)}
        emails = {key for value in contact_email_values(contact) for key in email_keys(value)}
        names = set(contact_name_keys(contact))
        if phones & wanted_phones or emails & wanted_emails or names & wanted_names:
            relevant[contact_id] = contact

    named_opps: list[dict[str, Any]] = []
    if name_values:
        for snap in _stream_in(db, OPP_COLLECTION, "name", name_values, OPP_FIELDS):
            item = _snap_dict(snap)
            if wanted_names.intersection(name_match_keys(item.get("name"))):
                named_opps.append(item)
                contact_id = compact_text(item.get("contactId"))
                if contact_id and contact_id not in relevant:
                    relevant[contact_id] = {"id": contact_id, "locationId": item.get("locationId")}

    opportunities: dict[str, dict[str, Any]] = {}
    for opp in named_opps:
        opp_id = compact_text(opp.get("id") or opp.get("_doc_id"))
        if opp_id:
            opportunities[opp_id] = opp
    contact_ids = [contact_id for contact_id in relevant if is_ghl_id(contact_id)]
    if contact_ids:
        for snap in _stream_in(db, OPP_COLLECTION, "contactId", contact_ids, OPP_FIELDS):
            item = _snap_dict(snap)
            opp_id = compact_text(item.get("id") or item.get("_doc_id"))
            if opp_id:
                opportunities[opp_id] = item
    stage_names = _stage_names(db) if relevant or opportunities else {}
    return build_ghl_link_index(relevant.values(), opportunities.values(), stage_names)


def load_ghl_link_index(
    rows: Iterable[dict[str, Any]],
    *,
    db: Any = None,
    now: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    listed = [row for row in rows if isinstance(row, dict)]
    signature = _lookup_signature(listed)
    current = time.time() if now is None else now
    if db is None and not force:
        cached = _GHL_CACHE.get("index")
        cached_at = float(_GHL_CACHE.get("at") or 0)
        if isinstance(cached, dict) and _GHL_CACHE.get("key") == signature and current - cached_at < GHL_INDEX_TTL_SECONDS:
            return cached
    own_client = db is None
    if own_client:
        from sales import get_db

        db = get_db()
    index = query_ghl_link_index(db, listed)
    if own_client:
        _GHL_CACHE["index"] = index
        _GHL_CACHE["key"] = signature
        _GHL_CACHE["at"] = current
    return index


def parse_hub_snapshot(text: str) -> dict[str, Any]:
    """Read `const rows`, `const stageCards`, and `const generatedAt` from hub-data.js."""
    raw = text or ""
    start = raw.find("[")
    if start < 0:
        raise ValueError("Project management snapshot could not be read")
    decoder = json.JSONDecoder()
    try:
        rows, end = decoder.raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError("Project management snapshot could not be read") from exc
    if not isinstance(rows, list):
        raise ValueError("Project management snapshot could not be read")
    rest = raw[start + end :]
    cards: list[Any] = []
    marker = rest.find("const stageCards")
    if marker >= 0:
        card_start = rest.find("[", marker)
        if card_start >= 0:
            try:
                parsed_cards, _card_end = decoder.raw_decode(rest[card_start:])
            except json.JSONDecodeError as exc:
                raise ValueError("Project management snapshot could not be read") from exc
            if isinstance(parsed_cards, list):
                cards = parsed_cards
    generated = ""
    match = re.search(r'const generatedAt\s*=\s*"([^"]*)"', raw)
    if match:
        generated = match.group(1)
    clean_rows = [row for row in rows if isinstance(row, dict)]
    clean_cards = [card for card in cards if isinstance(card, dict) and compact_text(card.get("stage"))]
    return {"rows": clean_rows, "stage_cards": clean_cards, "generated_at": generated}


def created_date(row: dict[str, Any]) -> str:
    iso = compact_text(row.get("created_at_iso"))
    if len(iso) >= 10 and iso[4] == "-" and iso[7] == "-":
        return iso[:10]
    return ""


def row_created_month(row: dict[str, Any]) -> str:
    day = created_date(row)
    return day[:7] if len(day) >= 7 else ""


def in_date_range(row: dict[str, Any], start: str = "", end: str = "") -> bool:
    if not start and not end:
        return True
    day = created_date(row)
    if not day:
        return False
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def month_bounds(month_key: str) -> tuple[str, str] | None:
    text = compact_text(month_key)
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        return None
    year = int(text[:4])
    month = int(text[5:7])
    if month < 1 or month > 12:
        return None
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def _js_round1(value: float) -> float:
    return math.floor(value * 10 + 0.5) / 10


def install_cycle_days(row: dict[str, Any]) -> float | None:
    raw = compact_text(row.get("install_cycle_days"))
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def summarize_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    listed = list(rows)
    active = [row for row in listed if compact_text(row.get("section")) in ACTIVE_SECTIONS]
    held = [row for row in listed if compact_text(row.get("section")) == HOLD_SECTION]
    overdue = [row for row in listed if bool(row.get("is_over_sla"))]
    cycles = [value for value in (install_cycle_days(row) for row in listed) if value is not None]
    median = None
    if cycles:
        ordered = sorted(cycles)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            median = ordered[middle]
        else:
            median = _js_round1((ordered[middle - 1] + ordered[middle]) / 2)
    return {
        "active_jobs": len(active),
        "held_jobs": len(held),
        "overdue_jobs": len(overdue),
        "median_install_days": median,
        "install_sample_size": len(cycles),
        "row_count": len(listed),
    }


def has_sla(row: dict[str, Any]) -> bool:
    value = row.get("sla_days")
    return value not in ("", None)


def cards_for_rows(stage_cards: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    listed = list(rows)
    counts: dict[str, int] = {}
    overdue: dict[str, int] = {}
    for row in listed:
        bucket = compact_text(row.get("pm_bucket"))
        counts[bucket] = counts.get(bucket, 0) + 1
        if row.get("is_over_sla"):
            overdue[bucket] = overdue.get(bucket, 0) + 1
    cards = [dict(card) for card in stage_cards]
    if not cards:
        seen: set[str] = set()
        for row in listed:
            stage = compact_text(row.get("pm_bucket"))
            if not stage or stage in seen:
                continue
            seen.add(stage)
            cards.append(
                {
                    "stage": stage,
                    "full_name": stage,
                    "display_label": stage,
                    "short_label": stage,
                    "stage_slug": re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", stage.lower())),
                    "section": compact_text(row.get("section")),
                    "lane": "secondary" if compact_text(row.get("section")) == HOLD_SECTION else "primary",
                    "sla_days": None,
                    "sla_mode": "bucket",
                    "sla_label": "",
                }
            )
    display: list[dict[str, Any]] = []
    for card in cards:
        stage = compact_text(card.get("stage"))
        item = dict(card)
        item["count"] = counts.get(stage, 0)
        item["overdue_count"] = overdue.get(stage, 0)
        display.append(item)
    return display


def lanes_for_rows(stage_cards: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cards = cards_for_rows(stage_cards, rows)
    lanes: list[dict[str, Any]] = []
    for section, label, copy in LANES:
        lanes.append(
            {
                "section": section,
                "label": label,
                "copy": copy,
                "cards": [card for card in cards if compact_text(card.get("section")) == section],
            }
        )
    return lanes


def _rep_set(reps: Iterable[str] | None) -> set[str]:
    return {compact_text(rep).lower() for rep in (reps or []) if compact_text(rep)}


def rep_matches(row: dict[str, Any], reps: set[str]) -> bool:
    if not reps:
        return True
    return compact_text(row.get("assigned_rep")).lower() in reps


def filter_hub_rows(
    rows: Iterable[dict[str, Any]],
    *,
    search: str = "",
    stage: str = "",
    reps: Iterable[str] | None = None,
    start: str = "",
    end: str = "",
    overdue_only: bool = False,
    ignore_stage: bool = False,
) -> list[dict[str, Any]]:
    needle = compact_text(search).lower()
    stage_key = "" if ignore_stage else compact_text(stage).lower()
    selected = _rep_set(reps)
    matched: list[dict[str, Any]] = []
    for row in rows:
        if overdue_only and not row.get("is_over_sla"):
            continue
        if stage_key and compact_text(row.get("pm_bucket")).lower() != stage_key:
            continue
        if not rep_matches(row, selected):
            continue
        if not in_date_range(row, start, end):
            continue
        if needle:
            haystack = " ".join(
                compact_text(row.get(key))
                for key in (
                    "pm_bucket",
                    "process_bucket",
                    "display_name",
                    "assigned_rep",
                    "address",
                    "zip_code",
                    "permit_ahj",
                    "permit_phone",
                    "permit_tat",
                    "site_survey_date",
                    "first_installed_on",
                    "task_status",
                    "calc_status",
                    "finance_status",
                    "permit_status",
                    "interconnection_status",
                    "monitoring_approval",
                    "monitoring_status",
                    "process_board_note",
                    "essential_view_note",
                )
            ).lower()
            if needle not in haystack:
                continue
        matched.append(row)
    return matched


def sort_hub_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[str, float, str]:
        days = row.get("days_in_bucket")
        try:
            day_value = float(days or 0)
        except (TypeError, ValueError):
            day_value = 0
        return (
            compact_text(row.get("pm_bucket")).casefold(),
            -day_value,
            compact_text(row.get("display_name")).casefold(),
        )

    return sorted(rows, key=key)


def format_month_label(month_key: str) -> str:
    text = compact_text(month_key)
    parts = text.split("-")
    if len(parts) != 2:
        return text or "—"
    year, month = parts
    if not (year.isdigit() and month.isdigit()):
        return text
    month_number = int(month)
    year_number = int(year)
    if month_number < 1 or month_number > 12:
        return text
    return f"{month_number:02d}/{str(year_number)[-2:]}"


def cancellation_series(
    rows: Iterable[dict[str, Any]],
    *,
    reps: Iterable[str] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    selected = _rep_set(reps)
    monthly: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not rep_matches(row, selected):
            continue
        month_key = row_created_month(row)
        if not month_key or month_key < CANCELLATION_START_MONTH:
            continue
        item = monthly.setdefault(month_key, {"monthKey": month_key, "created": 0, "cancelled": 0})
        item["created"] += 1
        if compact_text(row.get("pm_bucket")).lower() == "cancelled":
            item["cancelled"] += 1
    current = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    if current < CANCELLATION_START_MONTH:
        current = CANCELLATION_START_MONTH
    series: list[dict[str, Any]] = []
    year, month = 2026, 1
    end_year, end_month = int(current[:4]), int(current[5:7])
    while (year, month) <= (end_year, end_month):
        month_key = f"{year:04d}-{month:02d}"
        item = monthly.get(month_key) or {"monthKey": month_key, "created": 0, "cancelled": 0}
        created = int(item["created"])
        cancelled = int(item["cancelled"])
        rate = (cancelled / created) * 100 if created else 0
        series.append(
            {
                "monthKey": month_key,
                "created": created,
                "cancelled": cancelled,
                "rate": rate,
                "label": format_month_label(month_key),
            }
        )
        month += 1
        if month == 13:
            month = 1
            year += 1
    return series


def cancellation_stages(rows: Iterable[dict[str, Any]], *, reps: Iterable[str] | None = None) -> list[dict[str, Any]]:
    selected = _rep_set(reps)
    counts: dict[str, int] = {}
    for row in rows:
        if not rep_matches(row, selected):
            continue
        if compact_text(row.get("pm_bucket")).lower() != "cancelled":
            continue
        stage = compact_text(row.get("cancel_source_stage")) or "Unknown prior stage"
        counts[stage] = counts.get(stage, 0) + 1
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    leading = [{"stage": stage, "count": count, "share": (count / total) * 100} for stage, count in ranked[:10]]
    other = sum(count for _stage, count in ranked[10:])
    if other:
        leading.append({"stage": "Other historical stages", "count": other, "share": (other / total) * 100})
    return leading


def hold_cancel_view(
    rows: Iterable[dict[str, Any]],
    *,
    created_month: str = "",
    start: str = "",
    end: str = "",
    bucket: str = "Cancelled",
    reps: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Same listing rules as happy-slr-hold-cancelled.html, plus the shared date range.

    A createdMonth query (the cancellation chart) lists jobs created that month
    whose bucket matches `bucket` (Cancelled by default). With no month and no
    date range, the table is the hold/cancel section. A start/end range filters
    that section by created date. Reps narrow every view. An explicit start/end
    wins over createdMonth.
    """
    listed_rows = list(rows)
    selected = _rep_set(reps)
    bucket_key = compact_text(bucket) or "Cancelled"
    month_key = compact_text(created_month)
    range_start = compact_text(start)
    range_end = compact_text(end)
    use_month = bool(month_key) and not range_start and not range_end
    if use_month:
        bounds = month_bounds(month_key)
        created_rows = [
            row
            for row in listed_rows
            if rep_matches(row, selected) and row_created_month(row) == month_key
        ]
        table_rows = [
            row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == bucket_key.lower()
        ]
        month_label = format_month_label(month_key)
        if bounds:
            range_start, range_end = bounds
        cancelled_count = len(table_rows) if bucket_key.lower() == "cancelled" else len(
            [row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == "cancelled"]
        )
        created_count = len(created_rows)
        active_month = month_key
        active_bucket = bucket_key
    else:
        created_rows = [
            row
            for row in listed_rows
            if rep_matches(row, selected) and in_date_range(row, range_start, range_end)
        ]
        table_rows = [row for row in created_rows if compact_text(row.get("section")) == HOLD_SECTION]
        cancelled_count = len(
            [row for row in created_rows if compact_text(row.get("pm_bucket")).lower() == "cancelled"]
        )
        dated = bool(range_start or range_end)
        created_count = len(created_rows) if dated else len(table_rows)
        month_label = f"{range_start} – {range_end}" if dated else "All months"
        active_month = ""
        active_bucket = ""
    return {
        "listed": sort_hub_rows(table_rows),
        "cancelled_count": cancelled_count,
        "created_count": created_count,
        "month_label": month_label,
        "created_month": active_month,
        "start": range_start,
        "end": range_end,
        "bucket": active_bucket,
    }


def unique_reps(rows: Iterable[dict[str, Any]]) -> list[str]:
    names: dict[str, str] = {}
    for row in rows:
        name = compact_text(row.get("assigned_rep"))
        if not name:
            continue
        key = name.casefold()
        current = names.get(key)
        if current is None or (current == current.lower() and name != name.lower()):
            names[key] = name
    return [names[key] for key in sorted(names, key=str.casefold)]


def build_payload(
    snapshot: dict[str, Any],
    *,
    default_location: Any = None,
    ghl_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = []
    for row in snapshot.get("rows") or []:
        if not isinstance(row, dict):
            continue
        linked = attach_ghl_links(row, default_location=default_location)
        if ghl_index is not None and not compact_text(linked.get("phoneHref")):
            linked = apply_ghl_index(linked, ghl_index, default_location=default_location)
        rows.append(linked)
    cards = [card for card in snapshot.get("stage_cards") or [] if isinstance(card, dict)]
    summary = summarize_rows(rows)
    hold_rows = [row for row in rows if compact_text(row.get("section")) == HOLD_SECTION]
    return {
        "ok": True,
        "metric": "Project Management",
        "source": "Monday Process Board - NY",
        "generated_at": snapshot.get("generated_at") or "",
        "row_count": len(rows),
        "summary": summary,
        "lanes": [
            {"section": section, "label": label, "copy": copy}
            for section, label, copy in LANES
        ],
        "stage_cards": cards_for_rows(cards, rows),
        "reps": unique_reps(rows),
        "ghl_opportunity_url": GHL_OPPORTUNITY_URL,
        "ghl_contact_url": GHL_CONTACT_URL,
        "hold_ghl_links": ghl_link_kind_counts(hold_rows),
        "rows": rows,
    }


def load_snapshot_text(fetch: Callable[[], str] | None = None) -> str:
    if fetch is not None:
        return fetch()
    request = urllib.request.Request(SNAPSHOT_URL, headers={"User-Agent": "happy-solar-reporting"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def load_project_management(
    *,
    fetch: Callable[[], str] | None = None,
    now: float | None = None,
    force: bool = False,
    db: Any = None,
    ghl_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    use_cache = fetch is None and db is None and ghl_index is None and not force
    if use_cache:
        cached = _CACHE.get("payload")
        stamp = float(_CACHE.get("at") or 0)
        current = time.time() if now is None else now
        if isinstance(cached, dict) and current - stamp < SNAPSHOT_TTL_SECONDS:
            return cached
    text = load_snapshot_text(fetch)
    parsed = parse_hub_snapshot(text)
    index = ghl_index
    if index is None and (fetch is None or db is not None):
        try:
            index = load_ghl_link_index(parsed.get("rows") or [], db=db, now=now, force=force)
        except Exception:
            index = None
    payload = build_payload(parsed, ghl_index=index)
    if fetch is None and db is None and ghl_index is None:
        _CACHE["payload"] = payload
        _CACHE["at"] = time.time() if now is None else now
    return payload


def clear_snapshot_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["payload"] = None
    _GHL_CACHE["at"] = 0.0
    _GHL_CACHE["key"] = ""
    _GHL_CACHE["index"] = None


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            payload = load_project_management()
            qs = parse_qs(urlparse(self.path).query)
            view = compact_text(qs.get("view", [""])[0]).lower()
            if view == "hold":
                reps = [part for part in compact_text(qs.get("reps", [""])[0]).split(",") if compact_text(part)]
                hold = hold_cancel_view(
                    payload.get("rows") or [],
                    created_month=compact_text(qs.get("createdMonth", [""])[0]),
                    start=compact_text(qs.get("start", [""])[0]),
                    end=compact_text(qs.get("end", [""])[0]),
                    bucket=compact_text(qs.get("bucket", ["Cancelled"])[0]) or "Cancelled",
                    reps=reps,
                )
                _write_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "metric": "Hold / Cancelled",
                        "source": payload.get("source"),
                        "generated_at": payload.get("generated_at"),
                        "ghl_opportunity_url": payload.get("ghl_opportunity_url"),
                        "ghl_contact_url": payload.get("ghl_contact_url"),
                        "reps": payload.get("reps") or [],
                        "month_label": hold["month_label"],
                        "cancelled_count": hold["cancelled_count"],
                        "created_count": hold["created_count"],
                        "created_month": hold["created_month"],
                        "start": hold["start"],
                        "end": hold["end"],
                        "bucket": hold["bucket"],
                        "row_count": len(hold["listed"]),
                        "rows": hold["listed"],
                    },
                )
                return
            _write_json(self, 200, payload)
        except Exception:
            _write_json(self, 502, {"ok": False, "error": "Project management data is unavailable"})
