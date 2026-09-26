# -*- coding: utf-8 -*-

"""Credit appointments and self-gens to Sweeper/Rehash Last Name.

Confirmed Happy Solar stack field (ghl-firestore-sync-v2 Discord alerts,
extract_sweeper_rehash_last_name): contact custom field
"Sweeper/Rehash Last Name" HWfjOp8MvE6soxBAL75f.
The same id is read on the opportunity when the contact value is empty.

Credit starts with the pay week that began Thursday 2026-09-24
(America/New_York). Pay weeks are Thursday through Wednesday, the same
business dates private payroll uses. An earlier appointment stays with
the original setter on dashboards, commissions, the Scottsdale incentive,
and payroll.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Confirmed contact custom field "Sweeper/Rehash Last Name".
SWEEPER_REHASH_LAST_NAME_FIELD_ID = "HWfjOp8MvE6soxBAL75f"

# Thursday that opens the current Thu–Wed pay week. Inclusive.
# Weeks ending on or before Wednesday 2026-09-23 stay with the setter.
NY = ZoneInfo("America/New_York")
SWEEPER_ATTRIBUTION_START = date(2026, 9, 24)

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


def appointment_business_date(value: Any) -> date | None:
    """America/New_York calendar date for a sit or created appointment.

    A ``date`` is already a payroll business date and is not shifted.
    A ``datetime`` uses the same ET conversion as payroll week membership
    (``frozen_sit_timestamp`` localized with America/New_York). Naive
    datetimes are UTC instants, matching warehouse timestamps stored
    without an offset.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(NY).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            day_part = text[:10]
            rest = text[10:]
            if not rest:
                try:
                    year, month, day = (int(part) for part in day_part.split("-"))
                    return date(year, month, day)
                except ValueError:
                    return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(NY).date()
    return None


def sweeper_attribution_in_effect(appointment_date: Any) -> bool:
    """True when this appointment's ET date is on or after the cutoff."""
    business = appointment_business_date(appointment_date)
    if business is None:
        return False
    return business >= SWEEPER_ATTRIBUTION_START


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


def attributed_last_name(
    setter: Any,
    lead_source: Any,
    sweeper_last_name: Any,
    appointment_date: Any = None,
) -> Any:
    """Last name the appointment or self-gen counts for.

    A filled Sweeper/Rehash Last Name replaces the setter only when
    ``appointment_date`` falls on or after ``SWEEPER_ATTRIBUTION_START``.
    Anything earlier, or a missing date, stays with the setter. Rehash with
    an empty field keeps the setter, because there is no sweeper person to
    credit. True self-gens with an empty field are unchanged.
    """
    if not sweeper_attribution_in_effect(appointment_date):
        return setter
    sweeper = compact_text(sweeper_last_name)
    if sweeper and not is_blank_last_name(sweeper) and uses_sweeper_rehash_credit(lead_source, sweeper):
        return sweeper
    return setter


def lead_source_matches(
    requested: str | None,
    lead_source: Any,
    sweeper_last_name: Any,
    appointment_date: Any = None,
) -> bool:
    """Lead-source equality, plus self-gen inclusion once the cutoff applies.

    Before 2026-09-24 this is exact equality, matching base. On or after the
    cutoff, a Self Gen filter also matches rehash and any row whose
    Sweeper/Rehash Last Name is filled, so those appointments show on the
    sales-rep self-gen dashboard. A missing date does not widen the filter.
    """
    if requested is None or not str(requested).strip():
        return True
    if str(lead_source).strip().casefold() == str(requested).strip().casefold():
        return True
    if (
        sweeper_attribution_in_effect(appointment_date)
        and is_self_gen_lead_filter(requested)
        and uses_sweeper_rehash_credit(lead_source, sweeper_last_name)
    ):
        return True
    return False
