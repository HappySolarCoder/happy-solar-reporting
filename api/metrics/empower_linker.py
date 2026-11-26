# -*- coding: utf-8 -*-

"""Link NYHEP enrollments to GHL opportunities.

Phone and email stay in memory for the match. Persisted match keys are
SHA-256 hashes. Street+ZIP and fuzzy name never auto-link.

This module does not write ``ghl_opportunities_v2`` or any other funnel
collection. Those counts are excluded in a separate pipeline-scope change.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


from metrics.empower_ids import (
    EMPOWER_PIPELINE_ID,
    FUNNEL_COLLECTIONS,
    GHL_STAGE_INDEX,
    GHL_STAGE_NAME,
    INCOME_QUAL_POS,
    LINKS_COLLECTION,
    NYHEP_STAGE_POS,
)
from metrics.nyhep_stage_events import calendar_days, snapshot_day


PHOENIX = ZoneInfo("America/Phoenix")
_DIGITS = re.compile(r"\d+")
_STREET_NO = re.compile(r"^\s*(\d+)")
_ZIP5 = re.compile(r"(\d{5})")

# Public dashboard rows never carry these substrings in keys or method values.
_PUBLIC_KEYS = (
    "id",
    "customer",
    "city",
    "step",
    "oppId",
    "suggestedOppId",
    "pipelineName",
    "reason",
    "ghlStage",
    "nyhepStage",
    "days",
    "enrollmentStatus",
    "priority",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_phone(value: object) -> str:
    digits = "".join(_DIGITS.findall(str(value or "")))
    if len(digits) < 10:
        return ""
    return digits[-10:]


def normalize_email(value: object) -> str:
    text = str(value or "").strip().lower()
    if "@" not in text or " " in text or text.startswith("@") or text.endswith("@"):
        return ""
    return text


def name_tokens(value: object) -> set[str]:
    text = str(value or "").lower().replace(",", " ")
    text = re.sub(r"[^a-z\s]", " ", text)
    skip = {"jr", "sr", "ii", "iii"}
    return {token for token in text.split() if token and token not in skip}


def names_match(left: object, right: object) -> bool:
    a = name_tokens(left)
    b = name_tokens(right)
    if len(a) < 2 or len(b) < 2:
        return False
    if a == b:
        return True
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    return smaller <= larger and len(smaller) >= 2


def _ordered_tokens(value: object) -> list[str]:
    text = str(value or "").lower().replace(",", " ")
    text = re.sub(r"[^a-z\s]", " ", text)
    skip = {"jr", "sr", "ii", "iii"}
    return [token for token in text.split() if token and token not in skip]


def name_parts(value: object) -> tuple[str, str]:
    """First name and last name. 'Last, First' and 'First Last' both work."""
    raw = str(value or "").strip()
    if "," in raw:
        last_raw, first_raw = raw.split(",", 1)
        firsts = _ordered_tokens(first_raw)
        lasts = _ordered_tokens(last_raw)
    else:
        tokens = _ordered_tokens(raw)
        if len(tokens) < 2:
            return "", ""
        firsts = tokens[:1]
        lasts = tokens[-1:]
    return (firsts[0] if firsts else "", lasts[-1] if lasts else "")


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, char in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(
                min(current[-1] + 1, previous[other_index] + 1, previous[other_index - 1] + (char != other))
            )
        previous = current
    return previous[-1]


def names_suggest(left: object, right: object) -> bool:
    """Exact token match, or the same first name and a last name one edit away.

    Callers must keep this as a suggestion. It never authorizes an automatic link.
    """
    if names_match(left, right):
        return True
    first_left, last_left = name_parts(left)
    first_right, last_right = name_parts(right)
    if not first_left or first_left != first_right or not last_left or not last_right:
        return False
    distance = edit_distance(last_left, last_right)
    if distance <= 1:
        return True
    longest = max(len(last_left), len(last_right))
    return longest > 0 and (1 - distance / longest) >= 0.85


def street_number(value: object) -> str:
    match = _STREET_NO.match(str(value or ""))
    return match.group(1) if match else ""


def zip5(value: object) -> str:
    match = _ZIP5.search(str(value or ""))
    return match.group(1) if match else ""


def address_key(street: object, postal: object) -> tuple[str, str] | None:
    number = street_number(street)
    code = zip5(postal)
    if not number or not code:
        return None
    return number, code


def _text(value: object) -> str:
    return str(value or "").strip()


def custom_field_map(raw: object) -> dict[str, str]:
    if isinstance(raw, dict) and "customFields" in raw:
        fields = raw.get("customFields") or []
    else:
        fields = raw or []
    found: dict[str, str] = {}
    if isinstance(fields, dict):
        for key, value in fields.items():
            found[str(key)] = "" if value is None else str(value)
        return found
    if not isinstance(fields, list):
        return found
    for item in fields:
        if not isinstance(item, dict):
            continue
        field_id = _text(item.get("id") or item.get("key"))
        if not field_id:
            continue
        value = item.get("field_value")
        if value is None:
            value = item.get("value")
        if value is None:
            value = item.get("fieldValue")
        found[field_id] = "" if value is None else str(value)
    return found


def enrollment_id_on_opp(opp: dict) -> str:
    from metrics.empower_ids import FIELD_ENROLLMENT_ID

    return _text(custom_field_map(opp.get("customFields")).get(FIELD_ENROLLMENT_ID))


def _opp_id(opp: dict) -> str:
    return _text(opp.get("id") or opp.get("opp_id"))


def _pipeline_id(opp: dict) -> str:
    return _text(opp.get("pipelineId") or opp.get("pipeline_id"))


def _contact_id(opp: dict) -> str:
    return _text(opp.get("contactId") or opp.get("contact_id"))


def _stage_id(opp: dict) -> str:
    return _text(opp.get("pipelineStageId") or opp.get("pipeline_stage_id") or opp.get("stage_id"))


def is_empower_opp(opp: dict) -> bool:
    return _pipeline_id(opp) == EMPOWER_PIPELINE_ID


def _contact_of(opp: dict, contacts: dict[str, dict]) -> dict:
    cid = _contact_id(opp)
    contact = contacts.get(cid) or {}
    nested = opp.get("contact")
    if isinstance(nested, dict):
        merged = dict(contact)
        merged.update(nested)
        return merged
    return contact if isinstance(contact, dict) else {}


def _phones(match: dict, contact: dict) -> list[str]:
    values = []
    for source, keys in (
        (match, ("phone", "altPhone", "alt_phone", "phoneNumber")),
        (contact, ("phone", "phoneNumber", "altPhone", "alt_phone", "additionalPhone")),
    ):
        for key in keys:
            number = normalize_phone(source.get(key) if isinstance(source, dict) else "")
            if number:
                values.append(number)
    return values


def _emails(match: dict, contact: dict) -> list[str]:
    values = []
    for source, keys in (
        (match, ("email", "applicantEmail", "applicant_email")),
        (contact, ("email", "emailAddress")),
    ):
        for key in keys:
            mail = normalize_email(source.get(key) if isinstance(source, dict) else "")
            if mail:
                values.append(mail)
    return values


def _names(opp: dict, contact: dict) -> list[str]:
    names = []
    if contact:
        first = _text(contact.get("firstName") or contact.get("first_name"))
        last = _text(contact.get("lastName") or contact.get("last_name"))
        if first or last:
            names.append(f"{first} {last}")
            names.append(f"{last}, {first}")
        if contact.get("name"):
            names.append(_text(contact.get("name")))
    if opp.get("name"):
        names.append(_text(opp.get("name")))
    return [name for name in names if name]


def _rejected(existing: dict | None) -> set[str]:
    if not isinstance(existing, dict):
        return set()
    found = set()
    for item in existing.get("rejected_opp_ids") or []:
        text = _text(item)
        if text:
            found.add(text)
    if existing.get("confidence") == "rejected":
        text = _text(existing.get("rejected_opp_id") or existing.get("suggested_opp_id"))
        if text:
            found.add(text)
    return found


def _base(enrollment_id: str, existing: dict | None, now: str) -> dict[str, Any]:
    prior = existing if isinstance(existing, dict) else {}
    return {
        "enrollment_id": enrollment_id,
        "opp_id": None,
        "contact_id": None,
        "pipeline_id": None,
        "pipeline_name": "",
        "method": "",
        "confidence": "",
        "status": "unmatched_nyhep",
        "other_pipeline": False,
        "suggested_opp_id": None,
        "suggested_reason": "",
        "confirmed_by": prior.get("confirmed_by") or "",
        "confirmed_at": prior.get("confirmed_at"),
        "updated_at": now,
        "rejected_opp_ids": sorted(_rejected(prior)),
        "bucket": "not_in_ghl",
    }


def _stamp_hashes(body: dict, match: dict) -> None:
    phones = _phones(match, {})
    emails = _emails(match, {})
    if phones:
        body["phone_sha256"] = sha256_text(phones[0])
    if emails:
        body["email_sha256"] = sha256_text(emails[0])


def _linked(body: dict, opp: dict, method: str, *, other: bool, reason: str) -> dict:
    body.update(
        {
            "opp_id": _opp_id(opp),
            "contact_id": _contact_id(opp),
            "pipeline_id": _pipeline_id(opp),
            "pipeline_name": _text(opp.get("pipeline_name") or opp.get("pipelineName")),
            "method": method,
            "confidence": "exact",
            "status": "linked",
            "other_pipeline": other,
            "suggested_opp_id": None,
            "suggested_reason": reason,
            "bucket": "other_pipeline" if other else "linked",
        }
    )
    return body


def _suggested(body: dict, opp: dict, method: str, reason: str) -> dict:
    body.update(
        {
            "opp_id": None,
            "contact_id": _contact_id(opp),
            "pipeline_id": _pipeline_id(opp),
            "pipeline_name": _text(opp.get("pipeline_name") or opp.get("pipelineName")),
            "method": method,
            "confidence": "suggested",
            "status": "needs_confirmation",
            "other_pipeline": not is_empower_opp(opp),
            "suggested_opp_id": _opp_id(opp),
            "suggested_reason": reason,
            "bucket": "suggested",
        }
    )
    return body


def match_job(
    project: dict,
    match: dict | None,
    opps: list[dict],
    contacts: dict[str, dict] | None,
    existing: dict | None = None,
    *,
    now: str = "",
    opener=None,
    location_id: str = "",
) -> dict:
    """Stop at the first match. Address and name stay suggestions."""
    contacts = contacts or {}
    match = match if isinstance(match, dict) else {}
    enrollment_id = _text(project.get("id") or project.get("enrollment_id"))
    moment = now or datetime.now(PHOENIX).isoformat()
    body = _base(enrollment_id, existing, moment)
    _stamp_hashes(body, match)
    rejected = set(body["rejected_opp_ids"])

    if (
        isinstance(existing, dict)
        and existing.get("confidence") in {"exact", "confirmed"}
        and existing.get("status") == "linked"
        and _text(existing.get("opp_id"))
    ):
        kept = dict(body)
        kept.update(
            {
                "opp_id": _text(existing.get("opp_id")),
                "contact_id": existing.get("contact_id"),
                "pipeline_id": existing.get("pipeline_id"),
                "pipeline_name": existing.get("pipeline_name") or "",
                "method": existing.get("method") or "id",
                "confidence": existing.get("confidence"),
                "status": "linked",
                "other_pipeline": bool(existing.get("other_pipeline")),
                "suggested_opp_id": None,
                "suggested_reason": existing.get("suggested_reason") or "",
                "bucket": "other_pipeline" if existing.get("other_pipeline") else "linked",
                "confirmed_by": existing.get("confirmed_by") or "",
                "confirmed_at": existing.get("confirmed_at"),
            }
        )
        return kept

    usable = [opp for opp in opps if isinstance(opp, dict) and _opp_id(opp) and _opp_id(opp) not in rejected]
    empower = [opp for opp in usable if is_empower_opp(opp)]
    others = [opp for opp in usable if not is_empower_opp(opp)]

    for opp in empower:
        if enrollment_id_on_opp(opp) == enrollment_id and enrollment_id:
            return _linked(body, opp, "id", other=False, reason="id on opportunity")

    def phone_hit(rows: list[dict]) -> dict | None:
        wanted = set(_phones(match, {}))
        if not wanted:
            return None
        for opp in rows:
            contact = _contact_of(opp, contacts)
            if wanted.intersection(_phones({}, contact)):
                return opp
        return None

    hit = phone_hit(empower)
    if hit is not None:
        return _linked(body, hit, "phone", other=False, reason="same pipeline")
    hit = phone_hit(others)
    if hit is not None:
        name = _text(hit.get("pipeline_name") or hit.get("pipelineName")) or "other pipeline"
        return _linked(body, hit, "phone", other=True, reason=name)

    def email_hit(rows: list[dict]) -> dict | None:
        wanted = set(_emails(match, {}))
        if not wanted:
            return None
        for opp in rows:
            contact = _contact_of(opp, contacts)
            if wanted.intersection(_emails({}, contact)):
                return opp
        return None

    hit = email_hit(empower)
    if hit is not None:
        return _linked(body, hit, "email", other=False, reason="same pipeline")
    hit = email_hit(others)
    if hit is not None:
        name = _text(hit.get("pipeline_name") or hit.get("pipelineName")) or "other pipeline"
        return _linked(body, hit, "email", other=True, reason=name)

    wanted_address = address_key(
        match.get("street") or match.get("address") or match.get("address1"),
        match.get("zip") or match.get("postalCode") or match.get("postal_code"),
    )
    if wanted_address is not None:
        for opp in empower + others:
            contact = _contact_of(opp, contacts)
            found = address_key(
                contact.get("address1") or contact.get("street") or contact.get("address"),
                contact.get("postalCode") or contact.get("zip") or contact.get("postal_code"),
            )
            if found == wanted_address:
                return _suggested(body, opp, "address", "street and zip")

    customer = _text(project.get("customer"))
    if customer:
        for opp in empower + others:
            contact = _contact_of(opp, contacts)
            if any(names_suggest(customer, candidate) for candidate in _names(opp, contact)):
                return _suggested(body, opp, "name", "name")

    found = find_contact_without_empower_opp(match, customer, opener=opener, location_id=location_id)
    if found is not None:
        return _classify_contact_search(body, found)
    return body


def _ghl_readonly_get(path: str, params: dict, *, opener, location_id: str) -> dict:
    """GET only. A missing opener does not call the network."""
    from urllib.parse import urlencode
    import urllib.request

    from metrics.empower_ids import GHL_API_VERSION, GHL_LOCATION_ID_DEFAULT

    if opener is None:
        return {}
    query = {key: value for key, value in params.items() if value}
    if "locationId" not in query and "location_id" not in query:
        if path.startswith("/contacts"):
            query["locationId"] = location_id or GHL_LOCATION_ID_DEFAULT
        else:
            query["location_id"] = location_id or GHL_LOCATION_ID_DEFAULT
    url = "https://services.leadconnectorhq.com" + path
    if query:
        url = url + "?" + urlencode(query)
    headers = {"Version": GHL_API_VERSION, "Accept": "application/json"}
    import os

    api_key = (os.environ.get("GHL_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    if request.get_method() != "GET":
        raise RuntimeError("contact search is read-only")
    payload = opener(request)
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, bytes):
        import json
        return json.loads(payload.decode("utf-8") or "{}")
    return {}


def _pick_contact(rows: list, kind: str, query: str) -> dict | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if kind == "phone" and query in _phones({}, row):
            return row
        if kind == "email" and query in _emails({}, row):
            return row
        if kind == "name":
            candidate = " ".join(
                part
                for part in (
                    _text(row.get("firstName") or row.get("first_name")),
                    _text(row.get("lastName") or row.get("last_name")),
                )
                if part
            ) or _text(row.get("name"))
            if candidate and names_suggest(query, candidate):
                return row
    return None


def readonly_opener_from_env():
    """Live GET opener only when GHL_API_KEY is set. Otherwise matching stays local."""
    import json
    import os
    import urllib.request

    if not (os.environ.get("GHL_API_KEY") or "").strip():
        return None

    def opener(request):
        if request.get_method() != "GET":
            raise RuntimeError("contact search is read-only")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    return opener


def find_contact_without_empower_opp(match: dict, customer: str, *, opener=None, location_id: str = "") -> dict | None:
    """Search contacts by phone, then email, then name. Read-only GETs."""
    if opener is None:
        return None
    queries: list[tuple[str, str]] = []
    phone = ""
    for key in ("phone", "altPhone", "alt_phone"):
        phone = normalize_phone(match.get(key))
        if phone:
            break
    if phone:
        queries.append(("phone", phone))
    mail = normalize_email(match.get("email") or match.get("applicantEmail"))
    if mail:
        queries.append(("email", mail))
    if customer:
        queries.append(("name", customer))
    for kind, query in queries:
        payload = _ghl_readonly_get("/contacts/", {"query": query}, opener=opener, location_id=location_id)
        chosen = _pick_contact(payload.get("contacts") or [], kind, query)
        if chosen is None:
            continue
        contact_id = _text(chosen.get("id"))
        opps_payload = _ghl_readonly_get(
            "/opportunities/search",
            {"contact_id": contact_id},
            opener=opener,
            location_id=location_id,
        )
        return {"method": kind, "contact": chosen, "opportunities": opps_payload.get("opportunities") or []}
    return None


def _classify_contact_search(body: dict, found: dict) -> dict:
    contact = found.get("contact") or {}
    method = found.get("method") or "name"
    contact_id = _text(contact.get("id"))
    opportunities = [row for row in found.get("opportunities") or [] if isinstance(row, dict)]
    empower = [row for row in opportunities if _pipeline_id(row) == EMPOWER_PIPELINE_ID]
    others = [row for row in opportunities if _pipeline_id(row) and _pipeline_id(row) != EMPOWER_PIPELINE_ID]
    if empower:
        if method == "name":
            return _suggested(body, empower[0], "name", "name")
        return _linked(body, empower[0], method, other=False, reason="same pipeline")
    body["contact_id"] = contact_id
    body["method"] = method
    if others:
        opp = others[0]
        body.update(
            {
                "opp_id": None,
                "pipeline_id": _pipeline_id(opp),
                "pipeline_name": _text(opp.get("pipeline_name") or opp.get("pipelineName")) or "other pipeline",
                "suggested_opp_id": _opp_id(opp),
                "confidence": "suggested",
                "status": "unmatched_nyhep",
                "other_pipeline": True,
                "bucket": "ghl_other_pipeline",
                "suggested_reason": _text(opp.get("pipeline_name") or opp.get("pipelineName")) or "other pipeline",
            }
        )
        return body
    body.update(
        {
            "opp_id": None,
            "suggested_opp_id": None,
            "confidence": "suggested",
            "status": "unmatched_nyhep",
            "other_pipeline": False,
            "bucket": "ghl_contact_only",
            "suggested_reason": "ghl record only",
        }
    )
    return body


def match_matches_by_id(matches: object) -> dict[str, dict]:
    found: dict[str, dict] = {}
    if not isinstance(matches, list):
        return found
    for row in matches:
        if not isinstance(row, dict):
            continue
        enrollment_id = _text(row.get("id") or row.get("enrollment_id") or row.get("enrollmentId"))
        if enrollment_id:
            found[enrollment_id] = row
    return found


def link_doc_id(enrollment_id: str, opp_id: str = "") -> str:
    if enrollment_id:
        return enrollment_id
    return f"opp_{opp_id}"


def guarded_set(db, collection: str, doc_id: str, payload: dict) -> None:
    """Write tracking docs only. Funnel collections stay untouched."""
    if collection in FUNNEL_COLLECTIONS:
        raise RuntimeError("empower tracking does not write funnel collections")
    db.collection(collection).document(doc_id).set(payload)


def _same_link(previous: dict | None, new_body: dict) -> bool:
    if not isinstance(previous, dict):
        return False
    keys = (
        "opp_id",
        "contact_id",
        "pipeline_id",
        "method",
        "confidence",
        "status",
        "other_pipeline",
        "suggested_opp_id",
        "suggested_reason",
        "bucket",
    )
    return all(previous.get(key) == new_body.get(key) for key in keys)


def sync_links(
    projects: list[dict],
    matches: list[dict] | None,
    opps: list[dict],
    contacts: dict[str, dict] | None,
    existing: dict[str, dict] | None = None,
    *,
    now: str = "",
) -> list[tuple[str, dict]]:
    """Return enrollment docs that changed. Does not write by itself."""
    existing = existing or {}
    by_match = match_matches_by_id(matches)
    changed: list[tuple[str, dict]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        enrollment_id = _text(project.get("id"))
        if not enrollment_id:
            continue
        prior = existing.get(enrollment_id)
        body = match_job(
            project,
            by_match.get(enrollment_id),
            opps,
            contacts,
            prior,
            now=now,
            opener=readonly_opener_from_env(),
        )
        if _same_link(prior, body):
            continue
        changed.append((link_doc_id(enrollment_id), body))
    linked_opp_ids = {
        _text(body.get("opp_id"))
        for _doc, body in changed
        if body.get("status") == "linked" and body.get("opp_id") and not body.get("other_pipeline")
    }
    linked_opp_ids.update(
        _text(body.get("opp_id"))
        for body in existing.values()
        if isinstance(body, dict) and body.get("status") == "linked" and not body.get("other_pipeline")
    )
    for opp in opps:
        if not isinstance(opp, dict) or not is_empower_opp(opp):
            continue
        opp_id = _opp_id(opp)
        if not opp_id or opp_id in linked_opp_ids:
            continue
        doc_id = link_doc_id("", opp_id)
        prior = existing.get(doc_id) or existing.get(opp_id)
        if isinstance(prior, dict) and prior.get("status") == "linked":
            continue
        body = {
            "enrollment_id": "",
            "opp_id": opp_id,
            "contact_id": _contact_id(opp),
            "pipeline_id": EMPOWER_PIPELINE_ID,
            "pipeline_name": _text(opp.get("pipeline_name") or opp.get("pipelineName")) or "Empower+",
            "method": "",
            "confidence": "",
            "status": "unmatched_ghl",
            "other_pipeline": False,
            "suggested_opp_id": None,
            "suggested_reason": "",
            "confirmed_by": "",
            "confirmed_at": None,
            "updated_at": now or datetime.now(PHOENIX).isoformat(),
            "bucket": "unmatched_ghl",
        }
        if not _same_link(prior if isinstance(prior, dict) else None, body):
            changed.append((doc_id, body))
    return changed


def apply_link_action(
    existing: dict | None,
    action: str,
    enrollment_id: str,
    opp_id: str,
    actor: str,
    *,
    now: str,
) -> dict | None:
    """Confirm, reject, or manually bind. Returns None when the action is unknown."""
    action_name = _text(action).lower()
    enrollment_id = _text(enrollment_id)
    opp_id = _text(opp_id)
    if not enrollment_id or action_name not in {"confirm", "reject", "manual_link"}:
        return None
    prior = dict(existing or {})
    prior.setdefault("enrollment_id", enrollment_id)
    prior["updated_at"] = now
    if action_name == "confirm":
        chosen = opp_id or _text(prior.get("suggested_opp_id") or prior.get("opp_id"))
        if not chosen:
            return None
        prior.update(
            {
                "opp_id": chosen,
                "suggested_opp_id": None,
                "confidence": "confirmed",
                "status": "linked",
                "method": prior.get("method") or "manual",
                "confirmed_by": actor,
                "confirmed_at": now,
                "other_pipeline": bool(prior.get("other_pipeline")) and not opp_id,
                "bucket": "linked",
            }
        )
        return prior
    if action_name == "reject":
        rejected = set(_rejected(prior))
        suggestion = _text(prior.get("suggested_opp_id"))
        if suggestion:
            rejected.add(suggestion)
        prior.update(
            {
                "suggested_opp_id": None,
                "suggested_reason": "",
                "confidence": "rejected",
                "status": "unmatched_nyhep",
                "opp_id": None,
                "rejected_opp_ids": sorted(rejected),
                "bucket": "not_in_ghl",
            }
        )
        return prior
    if not opp_id:
        return None
    prior.update(
        {
            "opp_id": opp_id,
            "suggested_opp_id": None,
            "method": "manual",
            "confidence": "confirmed",
            "status": "linked",
            "other_pipeline": False,
            "pipeline_id": prior.get("pipeline_id") or EMPOWER_PIPELINE_ID,
            "confirmed_by": actor,
            "confirmed_at": now,
            "bucket": "linked",
        }
    )
    return prior


def _public_row(row: dict) -> dict:
    return {key: row.get(key, "") for key in _PUBLIC_KEYS if key in row or key in {"id", "customer"}}


def _days_in_stage(opp: dict, event: dict | None, as_of) -> int:
    start = None
    if isinstance(event, dict):
        text = _text(event.get("first_seen_at"))
        if len(text) >= 10:
            try:
                from datetime import date

                start = date.fromisoformat(text[:10])
            except ValueError:
                start = None
    if start is None:
        text = _text(opp.get("createdAt") or opp.get("created_at"))
        if len(text) >= 10:
            try:
                from datetime import date

                start = date.fromisoformat(text[:10])
            except ValueError:
                start = None
    return calendar_days(start, as_of)


def build_link_health(
    projects: list[dict],
    links: list[dict],
    opps: list[dict],
    *,
    ghl_events: list[dict] | None = None,
    as_of=None,
    today=None,
) -> dict[str, Any]:
    """Dashboard queue. Keys and reasons omit raw match channels."""
    as_of = as_of or snapshot_day("")
    check_day = today or datetime.now(PHOENIX).date()
    stale = False
    banner = ""
    if as_of is not None:
        from metrics.nyhep_stage_events import business_days

        if business_days(as_of, check_day) > 1:
            stale = True
            banner = "NYHEP check is more than one business day old. Alerts are paused."

    by_enroll = {}
    for link in links:
        if isinstance(link, dict) and _text(link.get("enrollment_id")):
            by_enroll[_text(link.get("enrollment_id"))] = link
    linked_empower = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        pipeline_id = _text(link.get("pipeline_id"))
        if (
            link.get("status") == "linked"
            and link.get("opp_id")
            and not link.get("other_pipeline")
            and pipeline_id in {"", EMPOWER_PIPELINE_ID}
        ):
            linked_empower.add(_text(link.get("opp_id")))

    opps_by_id = {_opp_id(opp): opp for opp in opps if isinstance(opp, dict)}
    events_by_opp = {}
    for event in ghl_events or []:
        if isinstance(event, dict) and event.get("ended_at") is None:
            events_by_opp[_text(event.get("opp_id"))] = event

    suggested = []
    other_pipeline = []
    ghl_other_pipeline = []
    contact_only = []
    not_in_ghl = []
    closed_or_cancelled = []
    disagreements = []

    for project in projects:
        if not isinstance(project, dict):
            continue
        enrollment_status = _text(project.get("status")).lower()
        closed = enrollment_status in {"closed", "completed", "complete", "cancelled", "canceled"}
        enrollment_id = _text(project.get("id"))
        link = by_enroll.get(enrollment_id) or {}
        opp = opps_by_id.get(_text(link.get("opp_id") or link.get("suggested_opp_id")))
        base = {
            "id": enrollment_id,
            "customer": _text(project.get("customer")),
            "city": _text(project.get("city")),
            "step": _text(project.get("step")),
        }
        status = _text(link.get("status"))
        empower_linked = (
            status == "linked"
            and not link.get("other_pipeline")
            and _text(link.get("pipeline_id")) in {"", EMPOWER_PIPELINE_ID}
            and _text(link.get("opp_id"))
        )
        if closed:
            if not empower_linked:
                label = "Cancelled" if enrollment_status in {"cancelled", "canceled"} else "Closed"
                closed_or_cancelled.append(
                    _public_row(
                        {
                            **base,
                            "enrollmentStatus": label,
                            "suggestedOppId": _text(link.get("suggested_opp_id")),
                            "reason": _text(link.get("suggested_reason")) or "missing match",
                            "priority": "low",
                        }
                    )
                )
            continue
        if enrollment_status not in {"open", "active", ""}:
            continue
        if status == "needs_confirmation":
            suggested.append(
                _public_row(
                    {
                        **base,
                        "suggestedOppId": _text(link.get("suggested_opp_id")),
                        "reason": _text(link.get("suggested_reason")) or "needs confirmation",
                    }
                )
            )
            continue
        if link.get("bucket") == "ghl_contact_only" or (
            _text(link.get("contact_id")) and not _text(link.get("opp_id")) and not link.get("other_pipeline")
        ):
            contact_only.append(_public_row(base))
            continue
        if link.get("bucket") == "ghl_other_pipeline":
            ghl_other_pipeline.append(
                _public_row(
                    {
                        **base,
                        "oppId": _text(link.get("suggested_opp_id") or link.get("opp_id")),
                        "pipelineName": _text(link.get("pipeline_name")) or "other pipeline",
                        "reason": _text(link.get("suggested_reason")) or "other pipeline",
                    }
                )
            )
            continue
        if link.get("other_pipeline") or (
            status == "linked" and _text(link.get("pipeline_id")) not in {"", EMPOWER_PIPELINE_ID}
        ):
            other_pipeline.append(
                _public_row(
                    {
                        **base,
                        "oppId": _text(link.get("opp_id")),
                        "pipelineName": _text(link.get("pipeline_name")) or "other pipeline",
                        "reason": _text(link.get("pipeline_name")) or "other pipeline",
                    }
                )
            )
            continue
        if status == "linked" and not link.get("other_pipeline"):
            stage_id = _stage_id(opp or {})
            ghl_pos = GHL_STAGE_INDEX.get(stage_id)
            nyhep_pos = NYHEP_STAGE_POS.get(_text(project.get("step")))
            if ghl_pos is not None and nyhep_pos is not None and ghl_pos < nyhep_pos:
                disagreements.append(
                    _public_row(
                        {
                            **base,
                            "oppId": _text(link.get("opp_id")),
                            "ghlStage": GHL_STAGE_NAME.get(stage_id, ""),
                            "nyhepStage": _text(project.get("step")),
                            "reason": "GHL stage is behind NYHEP",
                        }
                    )
                )
            continue
        not_in_ghl.append(_public_row(base))

    unmatched_ghl = []
    for opp in opps:
        if not isinstance(opp, dict) or not is_empower_opp(opp):
            continue
        opp_id = _opp_id(opp)
        if opp_id in linked_empower:
            continue
        status = _text(opp.get("status") or "open").lower()
        if status not in {"", "open"}:
            continue
        pos = GHL_STAGE_INDEX.get(_stage_id(opp))
        if pos is None:
            continue
        days = _days_in_stage(opp, events_by_opp.get(opp_id), check_day)
        if pos > INCOME_QUAL_POS or (pos <= INCOME_QUAL_POS and days >= 14):
            unmatched_ghl.append(
                _public_row(
                    {
                        "id": opp_id,
                        "oppId": opp_id,
                        "customer": "",
                        "ghlStage": GHL_STAGE_NAME.get(_stage_id(opp), ""),
                        "days": days,
                        "reason": "no NYHEP enrollment",
                    }
                )
            )

    return {
        "stale": stale,
        "staleBanner": banner,
        "suggested": suggested,
        "otherPipeline": other_pipeline,
        "ghlOtherPipeline": ghl_other_pipeline,
        "ghlContactOnly": contact_only,
        "notInGhl": not_in_ghl,
        "closedOrCancelled": closed_or_cancelled,
        "unmatchedGhl": unmatched_ghl,
        "stageDisagreements": disagreements,
    }


def empty_link_health() -> dict[str, Any]:
    return {
        "stale": False,
        "staleBanner": "",
        "suggested": [],
        "otherPipeline": [],
        "ghlOtherPipeline": [],
        "ghlContactOnly": [],
        "notInGhl": [],
        "closedOrCancelled": [],
        "unmatchedGhl": [],
        "stageDisagreements": [],
    }


def _stream(db, collection: str, field: str, op: str, value) -> list[tuple[str, dict]]:
    try:
        query = db.collection(collection).where(field, op, value)
        rows = []
        for snap in query.stream():
            data = snap.to_dict() or {}
            if isinstance(data, dict):
                rows.append((str(getattr(snap, "id", "") or ""), data))
        return rows
    except Exception:
        return []


def load_empower_opps(db) -> list[dict]:
    rows = []
    for doc_id, data in _stream(db, "ghl_opportunities_v2", "pipelineId", "==", EMPOWER_PIPELINE_ID):
        opp = dict(data)
        opp.setdefault("id", doc_id)
        rows.append(opp)
    return rows


def load_links(db) -> dict[str, dict]:
    found = {}
    for doc_id, data in _stream(db, LINKS_COLLECTION, "updated_at", ">=", "0"):
        found[doc_id] = data
        enrollment_id = _text(data.get("enrollment_id"))
        if enrollment_id:
            found[enrollment_id] = data
    return found


def load_contacts(db, contact_ids: list[str]) -> dict[str, dict]:
    found = {}
    for contact_id in contact_ids:
        if not contact_id:
            continue
        try:
            snap = db.collection("ghl_contacts_v2").document(contact_id).get()
        except Exception:
            continue
        if not getattr(snap, "exists", False):
            continue
        data = snap.to_dict() or {}
        if isinstance(data, dict):
            found[contact_id] = data
    return found


def persist_links(db, changed: list[tuple[str, dict]]) -> int:
    for doc_id, body in changed:
        guarded_set(db, LINKS_COLLECTION, doc_id, body)
    return len(changed)


def link_health_for_portal(db, payload: dict | None, events: list | None = None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    projects = [row for row in source.get("projects") or [] if isinstance(row, dict)]
    opps = load_empower_opps(db)
    unique = []
    seen = set()
    for row in load_links(db).values():
        marker = (_text(row.get("enrollment_id")), _text(row.get("opp_id")), _text(row.get("status")))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
    ghl_events = []
    try:
        from metrics.empower_ghl_events import load_open_ghl_events

        ghl_events = [body for _doc_id, body in load_open_ghl_events(db).values()]
    except Exception:
        ghl_events = []
    as_of = snapshot_day(source.get("snapshot"))
    return build_link_health(projects, unique, opps, ghl_events=ghl_events, as_of=as_of)
