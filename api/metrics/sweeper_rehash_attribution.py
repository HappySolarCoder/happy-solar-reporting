# -*- coding: utf-8 -*-

"""Credit appointments and self-gens to Sweeper/Rehash Last Name.

Confirmed Happy Solar stack field (ghl-firestore-sync-v2 Discord alerts,
extract_sweeper_rehash_last_name): contact custom field
"Sweeper/Rehash Last Name" HWfjOp8MvE6soxBAL75f.
The same id is read on the opportunity when the contact value is empty.
"""

from __future__ import annotations

import re
from typing import Any

# Confirmed contact custom field "Sweeper/Rehash Last Name".
SWEEPER_REHASH_LAST_NAME_FIELD_ID = "HWfjOp8MvE6soxBAL75f"

_BLANK_LAST_NAMES = frozenset(
    {"", "none", "null", "n/a", "na", "unknown", "unassigned", "-", "—"}
)
_SELF_GEN_FILTER_KEYS = frozenset({"selfgen", "selfgenerated"})


def compact_text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if str(item).strip())
    return " ".join(str(value or "").strip().split())


def is_blank_last_name(value: Any) -> bool:
    return compact_text(value).casefold() in _BLANK_LAST_NAMES


def _custom_field_raw(record: dict | None, field_id: str) -> Any:
    if not isinstance(record, dict):
        return None
    for cf in record.get("customFields") or []:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("id") or "").strip() != field_id:
            continue
        for key in ("value", "fieldValueString", "fieldValueNumber"):
            raw = cf.get(key)
            if raw not in (None, ""):
                return raw
    return None


def sweeper_rehash_last_name(
    contact: dict | None,
    opportunity: dict | None,
    field_id: str = SWEEPER_REHASH_LAST_NAME_FIELD_ID,
) -> str:
    """Contact field first, then the same id on the opportunity. Blank -> ''."""
    for record in (contact, opportunity):
        text = compact_text(_custom_field_raw(record, field_id))
        if text and not is_blank_last_name(text):
            return text
    return ""


def is_rehash_lead_source(value: Any) -> bool:
    return compact_text(value).casefold() == "rehash"


def is_self_gen_lead_filter(requested: str | None) -> bool:
    if requested is None or not str(requested).strip():
        return False
    key = re.sub(r"[\s\-_]+", "", compact_text(requested).casefold())
    return key in _SELF_GEN_FILTER_KEYS


def uses_sweeper_rehash_credit(lead_source: Any, sweeper_last_name: Any) -> bool:
    """True when lead source is rehash or Sweeper/Rehash Last Name is filled."""
    return is_rehash_lead_source(lead_source) or not is_blank_last_name(sweeper_last_name)


def attributed_last_name(setter: Any, lead_source: Any, sweeper_last_name: Any) -> Any:
    """Last name the appointment or self-gen counts for.

    A filled Sweeper/Rehash Last Name replaces the setter. Rehash with an
    empty field keeps the setter, because there is no sweeper person to credit.
    True self-gens with an empty field are unchanged.
    """
    sweeper = compact_text(sweeper_last_name)
    if sweeper and not is_blank_last_name(sweeper) and uses_sweeper_rehash_credit(lead_source, sweeper):
        return sweeper
    return setter


def lead_source_matches(requested: str | None, lead_source: Any, sweeper_last_name: Any) -> bool:
    """Existing lead-source equality, plus self-gen inclusion for rehash/sweeper rows.

    A Self Gen filter still matches true self-gen lead sources. It also matches
    rehash, and any row whose Sweeper/Rehash Last Name is filled, so those
    appointments show on the sales-rep self-gen dashboard.
    """
    if requested is None or not str(requested).strip():
        return True
    if str(lead_source).strip().casefold() == str(requested).strip().casefold():
        return True
    if is_self_gen_lead_filter(requested) and uses_sweeper_rehash_credit(lead_source, sweeper_last_name):
        return True
    return False
