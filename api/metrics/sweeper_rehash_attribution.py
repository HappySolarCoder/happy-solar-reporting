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
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_METRICS_DIR = Path(__file__).resolve().parent
if str(_METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(_METRICS_DIR))

from lead_gen_source import is_inbound_lead_source

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


def _stage_folded(stage_name: Any) -> str:
    text = compact_text(stage_name).casefold().replace("-", " ").replace("/", " ")
    return " ".join(text.split())


def stage_is_one_legger(stage_name: Any) -> bool:
    """One Legger is a post-appointment stage and is not a demo."""
    return "one legger" in _stage_folded(stage_name)


def stage_implies_demo(stage_name: Any) -> bool:
    """A Demo-* stage or Sold. One Legger and New Appointment are not demos."""
    if stage_is_one_legger(stage_name):
        return False
    folded = _stage_folded(stage_name)
    if not folded:
        return False
    if folded == "sold" or folded.startswith("sold "):
        return True
    return folded == "demo" or folded.startswith("demo ")


def sweeper_is_demo(disposition: Any, stage_name: Any) -> bool:
    """Appointment Outcome Sit, or a Demo-* / Sold stage. One Legger is never a demo.

    GHL writes Sit when the stage is a demo and No Sit otherwise. Sold still
    counts when the outcome was not written. One Legger overrides a Sit.
    """
    if stage_is_one_legger(stage_name):
        return False
    if stage_implies_demo(stage_name):
        return True
    return compact_text(disposition) == "Sit"


def sweeper_counts_as_ran(disposition: Any, stage_name: Any) -> bool:
    """Sit / No Sit has run. New Appointment has not. One Legger has run."""
    if compact_text(disposition) in {"Sit", "No Sit"}:
        return True
    if stage_is_one_legger(stage_name):
        return True
    return stage_implies_demo(stage_name)


def sweeper_funnel_rows(
    rows: list[dict] | None,
    *,
    name: str | None = None,
    name_field: str = "sweeperRehashLastName",
) -> list[dict]:
    """Dispositioned sweeper/rehash opportunities, one row per opportunity.

    Any pipeline counts, including Virtual. An earlier FMA sit on the same
    contact does not drop the later opportunity whose Sweeper/Rehash Last
    Name is filled. Rows without that name stay with the FMA.
    """
    seen: set[str] = set()
    kept: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sweeper = compact_text(row.get(name_field))
        if is_blank_last_name(sweeper):
            continue
        if name is not None and sweeper.casefold() != compact_text(name).casefold():
            continue
        opp_id = compact_text(row.get("opportunityId"))
        if opp_id and opp_id in seen:
            continue
        stage = row.get("pipelineStage") or row.get("pipelineStageName") or row.get("stageName")
        if not sweeper_counts_as_ran(row.get("disposition"), stage):
            continue
        if opp_id:
            seen.add(opp_id)
        kept.append(row)
    return kept


def sweeper_ran_and_demos(rows: list[dict] | None, *, name: str | None = None) -> tuple[int, int]:
    """(ran, demos) for sweeper_funnel_rows. One Legger is ran and not a demo."""
    chosen = sweeper_funnel_rows(rows, name=name)
    demos = 0
    for row in chosen:
        stage = row.get("pipelineStage") or row.get("pipelineStageName") or row.get("stageName")
        if sweeper_is_demo(row.get("disposition"), stage):
            demos += 1
    return len(chosen), demos


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
    if is_inbound_lead_source(requested) and is_inbound_lead_source(lead_source):
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
