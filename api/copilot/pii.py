# -*- coding: utf-8 -*-
"""Drop personal fields before anything is stored for a model or a drill-down."""

from __future__ import annotations

import re
from typing import Any

_DROP_KEYS = {
    "firstname",
    "lastname",
    "first_name",
    "last_name",
    "contactfirstname",
    "contactlastname",
    "fullname",
    "name",
    "email",
    "phone",
    "mobile",
    "address",
    "street",
    "owner",
    "ownername",
    "assignedtoname",
    "assignedtousername",
    "assignedusername",
    "setter",
    "setter_contact",
    "contactlast_name",
    "lastname_contact",
    "customfieldspreview",
    "assignedto_contact",
}
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"\b(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]\d{4}\b")

_KEEP = {
    "opportunityid",
    "pipeline",
    "pipelinename",
    "disposition",
    "lead_source",
    "leadsource",
    "stagename",
    "status",
}


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def scrub_text(value: str) -> str:
    cleaned = _EMAIL.sub("[redacted-email]", value)
    return _PHONE.sub("[redacted-phone]", cleaned)


def scrub_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        norm = _norm_key(str(key))
        if norm in _DROP_KEYS or norm not in _KEEP and norm not in {"opportunityid"}:
            if norm not in _KEEP:
                continue
        if isinstance(value, str):
            cleaned[key] = scrub_text(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
        else:
            continue
    if "opportunityId" not in cleaned and "opportunityid" in {k.lower() for k in row}:
        pass
    return cleaned


def scrub_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    output = []
    for row in rows[:limit]:
        if isinstance(row, dict):
            output.append(scrub_row(row))
    return output
