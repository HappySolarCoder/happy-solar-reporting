# -*- coding: utf-8 -*-

"""Ads Dashboard metrics. Read-only.

Days are America/Phoenix. The window is [start 00:00 Phoenix, end+1 00:00 Phoenix).
An ad lead is a unique contact with an Inbound/Lead Locker opportunity created
in that window whose Lead Gen Source counts as Inbound. That is the word
Inbound, or a Facebook Quick Form variant, via lead_gen_source. Quick Form
contacts are included when INCLUDE_FB_QUICK_FORM is true. They still surface
as their own count. Lead Locker and Solar Reviews titles stay out.

Sales has two views. kpis.sales is by lead date: a lead created in the window
counts once it has a Sold/Sale Cancelled stage on any city opp and a Contact
Sold Date on or after the window start, even when it sold after the window.
kpis.sales_by_sold_date counts Inbound/Quick Form contacts whose Contact Sold
Date (date-only) falls in the window, like /api/metrics/sales.

This module reads Meta account insights and GA4. It does not create, change,
or remove ads or campaigns.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

TIMEZONE_NAME = "America/Phoenix"
PHOENIX = ZoneInfo(TIMEZONE_NAME)
PHOENIX_ZONE_NAMES = frozenset({"america/phoenix", "us/arizona"})
INCLUDE_FB_QUICK_FORM = True
FB_QUICK_FORM_TAG = "fb-quick-form"
FB_QUICK_FORM_SOURCE = "facebook quick form"
INBOUND_SOURCE = "inbound"
# Evan, 2026-10-17. These cost goals stay on the card when the month doc is missing.
COST_PER_LEAD_GOAL = 25
COST_PER_OPP_GOAL = 100
COST_PER_DEMO_GOAL = 300
COST_PER_SALE_GOAL = 600
CONTACT_IN_CHUNK = 30
CONTACT_GET_ALL_CHUNK = 300
CACHE_TTL_SECONDS = 600
MAX_RANGE_DAYS = 366
OPP_COLLECTION = "ghl_opportunities_v2"
HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
# Current pipeline after a move. History still shows the city pipeline they left.
SWEEPER_PIPELINE_ID = "0VNxqmhbk7FDO64j2pKu"
REHASH_PIPELINE_ID = "vQ63K9v80I6SLIUZ0MPJ"
TERRITORY_PIPELINE_NAMES = frozenset({"buffalo", "rochester", "syracuse", "virtual"})
NEAR_NAME_WINDOW = timedelta(minutes=10)
DELETED_OPP_WINDOW = timedelta(minutes=10)
CONTACT_COLLECTION = "ghl_contacts_v2"
PIPELINE_COLLECTION = "ghl_pipelines_v2"
GOALS_COLLECTION = "goals_monthly_v1"
# Company keys only. Person goals in this collection are ignored.
# scripts/seed_ads_dashboard_goals.py writes 2026-10.
PAID_CHANNEL_GROUPS = frozenset({"paid social", "paid search"})
COMPANY_GOAL_KEYS = (
    "ads_dashboard",
    "ads",
    "inbound",
    "team:ads",
    "team:inbound",
    "company",
)
GOAL_METRIC_NAMES = {
    "spend": ("spend", "spend_goal", "ad_spend", "budget"),
    "leads": ("leads", "leads_goal", "inbound_leads"),
    "opps": ("opps", "opps_goal", "opportunities"),
    "demos": ("demos", "demos_goal"),
    "sales": ("sales", "sales_goal"),
    "cost_per_lead": ("cost_per_lead",),
    "cost_per_opp": ("cost_per_opp",),
    "cost_per_demo": ("cost_per_demo",),
    "cost_per_sale": ("cost_per_sale",),
}
HOURLY_BREAKDOWN = "hourly_stats_aggregated_by_advertiser_time_zone"
DASH = "\u2014"
NA = "N/A"

_STAGE_NAMES: dict[str, str] | None = None
_RESPONSE_CACHE: dict[tuple, tuple[float, dict]] = {}
# Sold/Sale Cancelled opps and their contacts, shared by every window for
# CACHE_TTL_SECONDS so the Sold Date view reads them once per warm instance.
_SOLD_CANDIDATES: tuple[float, list[dict[str, Any]], dict[str, dict]] | None = None
_PIPELINE_READ_NOTE: str | None = None
INDEX_FALLBACK_NOTE = (
    "The pipelineId and createdAt index is not built yet, so this read used "
    "the createdAt range and kept the Inbound/Lead Locker pipeline in memory."
)


def _load_paid_social():
    """Load the metrics module, not the /api/paid_social_funnel page."""
    name = "hs_ads_dashboard_paid_social"
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "fetch_meta_daily", None):
        return existing
    spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "paid_social_funnel.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load paid social funnel metric")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


psf = _load_paid_social()
cac = psf.cac

LEAD_PIPELINE_ID = cac.INBOUND_PIPELINE_ID
SOURCE_FIELD_ID = cac.LEAD_GEN_SOURCE_CONTACT_CF_ID
TERRITORY_PIPELINE_IDS = cac.TERRITORY_PIPELINE_IDS


def reset_caches() -> None:
    global _STAGE_NAMES, _PIPELINE_READ_NOTE, _SOLD_CANDIDATES
    _STAGE_NAMES = None
    _PIPELINE_READ_NOTE = None
    _SOLD_CANDIDATES = None
    _RESPONSE_CACHE.clear()


def _fold(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def money_round(value: Decimal | float | int | str) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def money_display(value: float | None) -> str:
    if value is None:
        return DASH
    return f"${money_round(value):,.2f}"


def count_display(value: int | None) -> str:
    if value is None:
        return DASH
    return f"{int(value):,}"


def percent_display(value: float | None) -> str:
    if value is None:
        return DASH
    return f"{value * 100:.2f}%"


def created_at_bound(moment: datetime) -> str:
    """UTC timestamp in the warehouse createdAt shape (...000Z)."""
    utc = moment.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def date_window(start_ymd: str, end_ymd: str) -> tuple[datetime, datetime]:
    """Inclusive Phoenix dates. The returned end is the next midnight."""
    start_local, end_local, _, _ = cac.date_range_window(start_ymd, end_ymd, TIMEZONE_NAME)
    return start_local, end_local


def default_range(now: datetime) -> tuple[str, str]:
    """Last 7 full Phoenix days, ending yesterday."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=PHOENIX)
    today = now.astimezone(PHOENIX).date()
    end_day = today - timedelta(days=1)
    start_day = end_day - timedelta(days=6)
    return start_day.isoformat(), end_day.isoformat()


def parse_range(qs: dict[str, list[str]], now: datetime) -> tuple[str, str]:
    start = _fold((qs.get("start") or [""])[0])
    end = _fold((qs.get("end") or [""])[0])
    if not start and not end:
        return default_range(now)
    if not start or not end:
        raise ValueError("Start and end are both required.")
    return start, end


def tag_texts(contact: dict[str, Any] | None) -> list[str]:
    if not isinstance(contact, dict):
        return []
    raw = contact.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [part for part in raw.split(",")]
    if not isinstance(raw, list):
        return []
    texts: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = item.get("name") or item.get("tag") or item.get("value") or ""
        else:
            text = item
        folded = _fold(text)
        if folded:
            texts.append(folded)
    return texts


def lead_source(contact: dict[str, Any] | None) -> str:
    return _fold(cac.contact_custom_field(contact, SOURCE_FIELD_ID))


def is_quick_form(contact: dict[str, Any] | None, source: str | None = None) -> bool:
    folded = lead_source(contact) if source is None else source
    if cac.is_facebook_quick_form_source(folded):
        return True
    return any(tag in {FB_QUICK_FORM_TAG, FB_QUICK_FORM_SOURCE} for tag in tag_texts(contact))


def is_ad_lead(contact: dict[str, Any] | None, include_quick_form: bool | None = None) -> bool:
    """Inbound, or a Facebook Quick Form variant when that switch is on."""
    if include_quick_form is None:
        include_quick_form = INCLUDE_FB_QUICK_FORM
    source = lead_source(contact)
    if is_quick_form(contact, source) and not include_quick_form:
        return False
    return cac.is_inbound_lead_source(source)


def _in_window(moment: datetime | None, start_local: datetime, end_local: datetime) -> bool:
    if moment is None:
        return False
    local = moment.astimezone(start_local.tzinfo)
    return start_local <= local < end_local


def _opp_id(opp: dict[str, Any], fallback: str) -> str:
    return cac.compact_str(opp.get("id")) or fallback


def _contact_id(opp: dict[str, Any]) -> str:
    return cac.compact_str(opp.get("contactId"))


def _stage_fold(stage_name: Any) -> str:
    folded = _fold(stage_name).replace("-", " ").replace("/", " ")
    return " ".join(folded.split())


def _is_sold_name(folded: str) -> bool:
    return folded == "sold" or folded.startswith("sold ")


def _is_sale_cancelled_name(folded: str) -> bool:
    return folded in {"sale cancelled", "sale canceled"} or folded.startswith(
        ("sale cancelled ", "sale canceled ")
    )


def stage_is_demo(stage_name: Any) -> bool:
    """A Demo-* stage, Sold, or Sale Cancelled is a demo. A One Legger is not a demo.

    Sale Cancelled matches Sold. One opportunity is one demo: a Sale Cancelled
    stage on an opportunity that already sat a Demo does not add a second demo.
    Across city opportunities the count is one demo per contact, unless that
    contact's Sweeper/Rehash Last Name is filled.
    """
    folded = _stage_fold(stage_name)
    if not folded or "one legger" in folded:
        return False
    if _is_sold_name(folded) or _is_sale_cancelled_name(folded):
        return True
    return folded == "demo" or folded.startswith("demo ")


def _sold_stage_ids() -> set[str]:
    """Buffalo, Syracuse, Rochester, and Virtual Sold and Sale Cancelled stage ids.

    Sales are these eight ids only. By lead date: one sale per deduped lead when
    Contact Sold Date is on or after the lead window start. By Sold Date: one
    sale per Inbound contact whose Sold Date is in the window. A stage named
    Sold or Sale Cancelled does not count. The four Sale Cancelled ids are
    already in this set.
    """
    return set(cac.SalesMetricContract().stage_ids)


def _opp_deleted(opp: dict[str, Any]) -> bool:
    """A deleted opportunity is never a sale."""
    if opp.get("deleted") or opp.get("isDeleted") or opp.get("deletedAt"):
        return True
    return _fold(opp.get("status")) == "deleted"


def _sold_on_or_after(sold_date_ymd: str | None, start_ymd: str) -> bool:
    """Date-only Sold Date on or after the lead window's first day."""
    return bool(sold_date_ymd) and sold_date_ymd >= start_ymd


# Contacts a sold opp had before it moved, newest first. Set by
# load_sold_candidates from the opp's stage history (each row keeps the
# contactId at the time of the stage change).
PRIOR_CONTACTS_KEY = "_priorContactIds"


def _sold_opp_contact_ids(
    opp: dict[str, Any], history: dict[str, list[dict[str, Any]]] | None = None
) -> list[str]:
    """Every contact this opp has had: the current one first, then prior ones.

    Prior contacts come from the opp's stage history rows and from
    PRIOR_CONTACTS_KEY, so a sale moved or merged onto a duplicate contact
    still reaches the original lead.
    """
    ids: list[str] = []
    current = _contact_id(opp)
    if current:
        ids.append(current)
    rows = [row for row in (history or {}).get(_opp_id(opp, ""), []) if isinstance(row, dict)]
    rows.sort(
        key=lambda row: _history_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    prior = [cac.compact_str(row.get("contactId") or row.get("contact_id")) for row in rows]
    for contact_id in [*prior, *(opp.get(PRIOR_CONTACTS_KEY) or [])]:
        contact_id = cac.compact_str(contact_id)
        if contact_id and contact_id not in ids:
            ids.append(contact_id)
    return ids


def _first_sold_date(contact_ids: list[str], *lookups: dict[str, dict] | None) -> str | None:
    """Date-only Sold Date from the first of these contacts that carries one."""
    for contact_id in contact_ids:
        for lookup in lookups:
            sold = cac.extract_sold_date_ymd((lookup or {}).get(contact_id))
            if sold:
                return sold
    return None


def _sweeper_rehash_filled(contact: dict[str, Any] | None) -> bool:
    """True when the contact Sweeper/Rehash Last Name field is non-empty."""
    from sweeper_rehash_attribution import sweeper_rehash_last_name

    return bool(sweeper_rehash_last_name(contact, None))


def _count_demos_per_lead(
    events: list[tuple[str, datetime, str]],
    contacts: dict[str, dict],
) -> int:
    """At most one demo per contact across inbound city opportunities.

    A later demo opportunity counts as another demo only when that contact's
    Sweeper/Rehash Last Name is non-empty. Sold, Sale Cancelled, and every
    Demo-* stage use this rule. One Legger is not a demo and is not passed in.
    """
    by_contact: dict[str, list[tuple[datetime, str]]] = {}
    seen: set[str] = set()
    for contact_id, created, opp_id in events:
        if not contact_id or not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        by_contact.setdefault(contact_id, []).append((created, opp_id))
    total = 0
    for contact_id, rows in by_contact.items():
        if not rows:
            continue
        if len(rows) == 1 or not _sweeper_rehash_filled(contacts.get(contact_id)):
            total += 1
            continue
        total += len(rows)
    return total


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _phone_key(value: Any) -> str:
    digits = _digits(value)
    if len(digits) < 10:
        return ""
    return digits[-10:]


def _email_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return text if "@" in text else ""


def _normalize_person_name(value: Any) -> str:
    text = "".join(ch if ch.isalnum() else " " for ch in str(value or "").casefold())
    tokens = text.split()
    if tokens and tokens[0] == "inbound":
        tokens = tokens[1:]
    return " ".join(tokens)


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return 2
    previous = list(range(len(right) + 1))
    for index, char in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (char != other),
                )
            )
        previous = current
    return previous[-1]


def _names_near(left: str, right: str) -> bool:
    """One token differs by a single character. Madison and Maddison match."""
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) < 2 or len(left_tokens) != len(right_tokens):
        return False
    diffs = 0
    for left_token, right_token in zip(left_tokens, right_tokens):
        if left_token == right_token:
            continue
        if _edit_distance(left_token, right_token) != 1:
            return False
        diffs += 1
    return diffs == 1


def _contact_blobs(contact: dict[str, Any] | None, opp: dict[str, Any]) -> list[dict[str, Any]]:
    blobs: list[dict[str, Any]] = []
    if isinstance(contact, dict):
        blobs.append(contact)
    nested = opp.get("contact")
    if isinstance(nested, dict):
        blobs.append(nested)
    return blobs


def _first_value(blobs: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    for blob in blobs:
        for key in keys:
            value = blob.get(key)
            if value not in (None, ""):
                return value
    return None


def _person_names(contact: dict[str, Any] | None, opp: dict[str, Any]) -> list[str]:
    names: list[str] = []
    blobs = _contact_blobs(contact, opp)
    for blob in blobs:
        joined = " ".join(
            part
            for part in (
                cac.compact_str(blob.get("firstName")),
                cac.compact_str(blob.get("lastName")),
            )
            if part
        )
        if joined:
            names.append(joined)
        for key in ("name", "contactName", "fullName"):
            text = cac.compact_str(blob.get(key))
            if text:
                names.append(text)
    title = cac.compact_str(opp.get(cac.TITLE_FIELD) or opp.get("name"))
    if title:
        names.append(title)
    folded: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = _normalize_person_name(name)
        if normalized and normalized not in seen:
            seen.add(normalized)
            folded.append(normalized)
    return folded


def _moment(value: Any) -> datetime | None:
    return cac.parse_iso_dt(value)


def _within(left: datetime | None, right: datetime | None, span: timedelta) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).total_seconds()) <= span.total_seconds()


def _rows_near_in_time(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for left_moment in (left.get("contact_created"), left.get("opp_created")):
        for right_moment in (right.get("contact_created"), right.get("opp_created")):
            if _within(left_moment, right_moment, NEAR_NAME_WINDOW):
                return True
    return False


def dedupe_lead_rows(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """One lead per phone, else email, else name. Near names within 10 minutes collapse."""
    count = len(rows)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    by_contact: dict[str, int] = {}
    by_phone: dict[str, int] = {}
    by_email: dict[str, int] = {}
    by_name: dict[str, int] = {}
    for index, row in enumerate(rows):
        contact_id = row["contact_id"]
        if contact_id in by_contact:
            union(index, by_contact[contact_id])
        else:
            by_contact[contact_id] = index
        for value, index_map in (
            (row.get("phone"), by_phone),
            (row.get("email"), by_email),
            (row.get("name"), by_name),
        ):
            if not value:
                continue
            if value in index_map:
                union(index, index_map[value])
            else:
                index_map[value] = index
    for left in range(count):
        for right in range(left + 1, count):
            if find(left) == find(right):
                continue
            if not _rows_near_in_time(rows[left], rows[right]):
                continue
            left_names = rows[left].get("names") or []
            right_names = rows[right].get("names") or []
            if any(_names_near(left_name, right_name) for left_name in left_names for right_name in right_names):
                union(left, right)
    groups: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(find(index), []).append(row)
    return list(groups.values())


def _history_was_territory(rows: list[dict[str, Any]] | None) -> bool:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in ("pipelineId", "toPipelineId", "fromPipelineId"):
            if cac.is_territory_pipeline(row.get(key)):
                return True
        for key in ("pipelineName", "toPipelineName", "fromPipelineName", "pipeline"):
            if _fold(row.get(key)) in TERRITORY_PIPELINE_NAMES:
                return True
    return False


def _opp_was_territory(opp: dict[str, Any], history: dict[str, list[dict[str, Any]]]) -> bool:
    if cac.is_territory_pipeline(opp.get("pipelineId")):
        return True
    return _history_was_territory(history.get(_opp_id(opp, "")))


def _history_timestamp(row: dict[str, Any]) -> datetime | None:
    for key in ("effectiveAt", "createdAt", "timestamp", "changedAt"):
        moment = cac.parse_iso_dt(row.get(key))
        if moment is not None:
            return moment
    return None


def _first_history_time(rows: list[dict[str, Any]] | None) -> datetime | None:
    moments = [_history_timestamp(row) for row in rows or [] if isinstance(row, dict)]
    found = [moment for moment in moments if moment is not None]
    if not found:
        return None
    return min(found)


def _history_contact_id(rows: list[dict[str, Any]] | None) -> str:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        contact_id = cac.compact_str(row.get("contactId") or row.get("contact_id"))
        if contact_id:
            return contact_id
    return ""


def _row_stage_pipeline_is_city(row: dict[str, Any]) -> bool:
    """The stage on this row was in Buffalo, Rochester, Syracuse, or Virtual."""
    to_id = row.get("toPipelineId")
    to_name = row.get("toPipelineName")
    if to_id not in (None, "") or to_name not in (None, ""):
        return cac.is_territory_pipeline(to_id) or _fold(to_name) in TERRITORY_PIPELINE_NAMES
    if cac.is_territory_pipeline(row.get("pipelineId")):
        return True
    return _fold(row.get("pipelineName") or row.get("pipeline")) in TERRITORY_PIPELINE_NAMES


def _history_stage_label(row: dict[str, Any], stage_names: dict[str, str]) -> str:
    for key in ("toStageName", "stageName"):
        label = cac.compact_str(row.get(key))
        if label:
            return label
    for key in ("toStageId", "stageId", "pipelineStageId"):
        stage_id = cac.compact_str(row.get(key))
        if not stage_id:
            continue
        return stage_names.get(stage_id) or stage_id
    return ""


def _history_has_city_demo(rows: list[dict[str, Any]] | None, stage_names: dict[str, str]) -> bool:
    for row in rows or []:
        if not isinstance(row, dict) or not _row_stage_pipeline_is_city(row):
            continue
        if stage_is_demo(_history_stage_label(row, stage_names)):
            return True
    return False


def opp_stage_label(opp: dict[str, Any], stage_names: dict[str, str]) -> str:
    stage_id = cac.compact_str(opp.get(cac.STAGE_FIELD))
    label = (
        stage_names.get(stage_id)
        or cac.compact_str(opp.get("pipelineStageName"))
        or cac.compact_str(opp.get("stageName"))
        or stage_id
    )
    return label or DASH


def classify_window(
    pipeline_opps: list[dict[str, Any]],
    contact_opps: list[dict[str, Any]],
    contacts: dict[str, dict],
    stage_names: dict[str, str],
    start_local: datetime,
    end_local: datetime,
    now_utc: datetime,
    *,
    include_quick_form: bool | None = None,
    history: dict[str, list[dict[str, Any]]] | None = None,
    sold_opps: list[dict[str, Any]] | None = None,
    sold_contacts: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Count deduped ad leads and the city opps that belong to them.

    sold_opps/sold_contacts (from load_sold_candidates) let a sale count for a
    lead after its sold opp moved to another contact: the opp is matched by id
    and by every contact it has had (stage history), once per lead cluster.
    """
    del now_utc
    if include_quick_form is None:
        include_quick_form = INCLUDE_FB_QUICK_FORM
    history = history or {}
    quick_matched: set[str] = set()
    rows: list[dict[str, Any]] = []
    seen_opps: set[str] = set()

    for index, opp in enumerate(pipeline_opps):
        if cac.compact_str(opp.get("pipelineId")) != LEAD_PIPELINE_ID:
            continue
        if cac.bucket_title(opp.get(cac.TITLE_FIELD) or opp.get("name")):
            continue
        created = cac.parse_iso_dt(opp.get(cac.CREATED_AT_FIELD))
        if not _in_window(created, start_local, end_local):
            continue
        contact_id = _contact_id(opp)
        if not contact_id:
            continue
        contact = contacts.get(contact_id)
        source = lead_source(contact)
        quick = is_quick_form(contact, source)
        if quick and source == INBOUND_SOURCE:
            quick_matched.add(contact_id)
        if not is_ad_lead(contact, include_quick_form):
            continue
        opp_id = _opp_id(opp, f"lead:{index}:{contact_id}")
        if opp_id in seen_opps:
            continue
        seen_opps.add(opp_id)
        blobs = _contact_blobs(contact, opp)
        names = _person_names(contact, opp)
        contact_created = _moment(_first_value(blobs, ("dateAdded", "createdAt", "dateCreated")))
        rows.append(
            {
                "contact_id": contact_id,
                "opp_id": opp_id,
                "opp_created": created,
                "contact_created": contact_created,
                "quick": quick,
                "phone": _phone_key(_first_value(blobs, ("phone", "phoneNumber"))),
                "email": _email_key(_first_value(blobs, ("email", "emailAddress"))),
                "name": names[0] if names else "",
                "names": names,
                "stage": opp_stage_label(opp, stage_names),
            }
        )

    clusters = dedupe_lead_rows(rows)
    member_ids: set[str] = set()
    quick_clusters = 0
    stages: dict[str, int] = {}
    canonical_ids: list[str] = []
    for cluster in clusters:
        ids = {row["contact_id"] for row in cluster}
        member_ids.update(ids)
        if any(row["quick"] for row in cluster):
            quick_clusters += 1
        latest = max(
            cluster,
            key=lambda row: (
                row.get("opp_created") or datetime.min.replace(tzinfo=timezone.utc),
                row["opp_id"],
            ),
        )
        stages[latest["stage"]] = stages.get(latest["stage"], 0) + 1
        earliest = min(
            cluster,
            key=lambda row: (
                row.get("opp_created") or datetime.max.replace(tzinfo=timezone.utc),
                row["contact_id"],
            ),
        )
        canonical_ids.append(earliest["contact_id"])

    opp_ids: set[str] = set()
    demo_events: list[tuple[str, datetime, str]] = []
    sold_ids = _sold_stage_ids()
    sold_members: set[str] = set()
    sold_links: dict[str, set[str]] = {}
    seen_city: set[str] = set()
    for index, opp in enumerate(contact_opps):
        contact_id = _contact_id(opp)
        if contact_id not in member_ids:
            continue
        opp_id = _opp_id(opp, f"city:{index}:{contact_id}")
        if opp_id in seen_city:
            continue
        seen_city.add(opp_id)
        stage_id = cac.compact_str(opp.get(cac.STAGE_FIELD))
        # Eight locked stage ids only. A stage named Sold or Sale Cancelled
        # is not a sale, on any pipeline. The sold opp can be any of the
        # lead's city opps, created in or after the window. Deleted opps skip.
        if stage_id in sold_ids and not _opp_deleted(opp):
            sold_members.add(contact_id)
        created = cac.parse_iso_dt(opp.get(cac.CREATED_AT_FIELD))
        if not _in_window(created, start_local, end_local):
            continue
        if not _opp_was_territory(opp, history):
            continue
        opp_ids.add(opp_id)
        if stage_is_demo(opp_stage_label(opp, stage_names)) or _history_has_city_demo(history.get(opp_id), stage_names):
            demo_events.append((contact_id, created, opp_id))

    other_created: dict[str, list[datetime]] = {}
    for opp in list(contact_opps) + list(pipeline_opps):
        contact_id = _contact_id(opp)
        if contact_id not in member_ids:
            continue
        created = cac.parse_iso_dt(opp.get(cac.CREATED_AT_FIELD))
        if created is not None:
            other_created.setdefault(contact_id, []).append(created)

    deleted_candidates: list[tuple[datetime, str, str, list[dict[str, Any]]]] = []
    for opp_id, history_rows in history.items():
        if not opp_id or opp_id in seen_city:
            continue
        contact_id = _history_contact_id(history_rows)
        if contact_id not in member_ids:
            continue
        if not _history_was_territory(history_rows):
            continue
        created = _first_history_time(history_rows)
        if not _in_window(created, start_local, end_local):
            continue
        deleted_candidates.append((created, opp_id, contact_id, history_rows))
    deleted_candidates.sort(key=lambda item: (item[0], item[1]))
    for created, opp_id, contact_id, history_rows in deleted_candidates:
        if any(_within(created, other, DELETED_OPP_WINDOW) for other in other_created.get(contact_id, [])):
            continue
        other_created.setdefault(contact_id, []).append(created)
        opp_ids.add(opp_id)
        if _history_has_city_demo(history_rows, stage_names):
            demo_events.append((contact_id, created, opp_id))

    # Fallback: a sold opp that moved to another contact (duplicate or merge)
    # still belongs to the lead it was on. Match by opp id and every contact
    # it has had; keep the contacts it moved to so their Sold Date can be read.
    seen_sold: set[str] = set()
    for index, opp in enumerate(sold_opps or []):
        opp_id = _opp_id(opp, f"sold:{index}")
        if opp_id in seen_sold:
            continue
        seen_sold.add(opp_id)
        if cac.compact_str(opp.get(cac.STAGE_FIELD)) not in sold_ids or _opp_deleted(opp):
            continue
        had = _sold_opp_contact_ids(opp, history)
        for contact_id in had:
            if contact_id in member_ids:
                sold_members.add(contact_id)
                sold_links.setdefault(contact_id, set()).update(had)

    # Lead-date view: one sale per deduped lead created in the window. Sale
    # Cancelled is already one of the eight ids. Contact Sold Date (date-only)
    # must be on or after the window's first day; it may fall after the window
    # ends, so a lead that sells weeks later still counts on its lead date.
    # The Sold Date may sit on the lead contact or on a contact its sold opp
    # moved to. One sale per cluster, so a duplicate never counts twice.
    window_start_ymd = start_local.date().isoformat()
    sales: set[str] = set()
    for cluster in clusters:
        ids = {row["contact_id"] for row in cluster}
        if not ids & sold_members:
            continue
        carriers = set(ids)
        for contact_id in ids:
            carriers.update(sold_links.get(contact_id, ()))
        if any(
            _sold_on_or_after(_first_sold_date([contact_id], contacts, sold_contacts), window_start_ymd)
            for contact_id in sorted(carriers)
        ):
            sales.add(min(ids))

    stage_rows = [
        {"stage": name, "count": count}
        for name, count in sorted(stages.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "inbound_leads": len(clusters),
        "lead_contact_ids": sorted(set(canonical_ids)),
        "fb_quick_form_leads": quick_clusters,
        "fb_quick_form_matched": len(quick_matched),
        "opps": len(opp_ids),
        "demos": _count_demos_per_lead(demo_events, contacts),
        "sales": len(sales),
        "sales_contact_ids": sorted(sales),
        "stages": stage_rows,
        "include_fb_quick_form": include_quick_form,
    }


def _blank_number(reason: str) -> dict[str, Any]:
    return {"value": None, "display": DASH, "reason": reason}


def money_goal_label(goal: float | int) -> str:
    number = float(goal)
    if number.is_integer():
        return f"${int(number):,}"
    return f"${number:,.2f}"


COST_GOAL_KEYS = frozenset({"cost_per_lead", "cost_per_opp", "cost_per_demo", "cost_per_sale"})


def _usable_cost_goal(value: Any) -> float | int | None:
    """A positive finite cost goal. Zero, negative, NaN, inf, and junk are missing."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).replace(",", "").replace("$", "").strip())
        except (TypeError, ValueError):
            return None
    if not math.isfinite(number) or number <= 0:
        return None
    if number.is_integer():
        return int(number)
    return number


def cost_goal_value(goals: dict[str, Any] | None, key: str) -> float | int:
    """Month-doc cost goal, or the standing constant when that field is unusable.

    Missing, zero, negative, NaN, infinite, and non-numeric values fall back
    to $25 / $100 / $300 / $600.
    """
    fallback = {
        "cost_per_lead": COST_PER_LEAD_GOAL,
        "cost_per_opp": COST_PER_OPP_GOAL,
        "cost_per_demo": COST_PER_DEMO_GOAL,
        "cost_per_sale": COST_PER_SALE_GOAL,
    }[key]
    if not isinstance(goals, dict):
        return fallback
    value = _usable_cost_goal(goals.get(key))
    if value is None:
        return fallback
    return value


def cost_block(spend: float | None, count: int | None, goal: float | None, goal_display: str) -> dict[str, Any]:
    if spend is None or count is None:
        block = _blank_number("missing")
    elif int(count) == 0:
        block = {"value": None, "display": NA, "reason": "zero_denominator"}
    else:
        value = money_round(Decimal(str(spend)) / Decimal(int(count)))
        block = {"value": value, "display": money_display(value), "reason": None}
    block["goal"] = goal
    block["goal_display"] = goal_display
    block["tone"] = _cost_tone(block.get("value"), goal)
    return block


def _cost_tone(value: float | None, goal: float | None) -> str | None:
    if value is None or goal is None:
        return None
    if value <= float(goal):
        return "good"
    return "bad"


def ratio_block(numer: float | int | None, denom: float | int | None, *, kind: str) -> dict[str, Any]:
    if numer is None or denom is None:
        return _blank_number("missing")
    if float(denom) == 0:
        return {"value": None, "display": NA, "reason": "zero_denominator"}
    if kind == "money":
        value = money_round(Decimal(str(numer)) / Decimal(str(denom)))
        return {"value": value, "display": money_display(value), "reason": None}
    if kind == "cpm":
        value = money_round(Decimal(str(numer)) * Decimal(1000) / Decimal(str(denom)))
        return {"value": value, "display": money_display(value), "reason": None}
    value = float(numer) / float(denom)
    return {"value": value, "display": percent_display(value), "reason": None}


def _goal_display(status: str, value: float | int | None, *, money: bool) -> str:
    if status == "unavailable":
        return DASH
    if status != "ok" or value is None:
        return "no goal"
    if money:
        return money_display(float(value))
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def _volume_kpi(value: int | None, goal_status: str, goal_value: float | int | None) -> dict[str, Any]:
    return {
        "value": value,
        "display": count_display(value),
        "goal": goal_value if goal_status == "ok" else None,
        "goal_display": _goal_display(goal_status, goal_value, money=False),
        "tone": None,
        "reason": None if value is not None else "missing",
    }


def assemble_ads_dashboard(
    *,
    pipeline_opps: list[dict[str, Any]],
    contact_opps: list[dict[str, Any]],
    contacts: dict[str, dict],
    stage_names: dict[str, str] | None,
    start_local: datetime,
    end_local: datetime,
    now: datetime,
    meta: dict[str, Any] | None,
    sessions: dict[str, Any] | None,
    goals: dict[str, Any] | None,
    include_quick_form: bool | None = None,
    stage_status: str = "ok",
    history: dict[str, list[dict[str, Any]]] | None = None,
    sold_date_sales: dict[str, Any] | None = None,
    sold_opps: list[dict[str, Any]] | None = None,
    sold_contacts: dict[str, dict] | None = None,
) -> dict[str, Any]:
    if include_quick_form is None:
        include_quick_form = INCLUDE_FB_QUICK_FORM
    now_utc = now.astimezone(timezone.utc)
    names = stage_names or {}
    counts = classify_window(
        pipeline_opps,
        contact_opps,
        contacts,
        names,
        start_local,
        end_local,
        now_utc,
        include_quick_form=include_quick_form,
        history=history,
        sold_opps=sold_opps,
        sold_contacts=sold_contacts,
    )
    notes: list[str] = []
    errors: list[str] = []
    if stage_status == "unavailable":
        errors.append("Pipeline stages could not be read, so stage names are missing.")

    meta = meta or {"status": "unavailable", "reason": "missing", "spend": None, "clicks": None, "impressions": None}
    sessions = sessions or {"status": "unavailable", "reason": "missing", "total": None, "series": None}
    goals = goals or {
        "status": "missing",
        "spend": None,
        "leads": None,
        "opps": None,
        "demos": None,
        "sales": None,
    }

    spend = meta.get("spend") if meta.get("status") == "ok" else None
    clicks = meta.get("clicks") if meta.get("status") == "ok" else None
    impressions = meta.get("impressions") if meta.get("status") == "ok" else None
    session_total = sessions.get("total") if sessions.get("status") == "ok" else None
    if meta.get("status") != "ok":
        errors.append(meta.get("note") or "Meta spend could not be read.")
    elif meta.get("note"):
        notes.append(str(meta["note"]))
    if sessions.get("status") != "ok":
        errors.append(sessions.get("note") or "Paid sessions could not be read.")
    if goals.get("status") == "unavailable":
        errors.append(goals.get("note") or "Monthly goals could not be read.")

    goal_status = goals.get("status") or "missing"
    spend_goal = goals.get("spend") if goal_status == "ok" else None
    lead_goal = goals.get("leads") if goal_status == "ok" else None
    opp_goal = goals.get("opps") if goal_status == "ok" else None
    demo_goal = goals.get("demos") if goal_status == "ok" else None
    sale_goal = goals.get("sales") if goal_status == "ok" else None
    spend_kpi = {
        "value": spend,
        "display": money_display(spend) if meta.get("status") == "ok" else DASH,
        "goal": spend_goal,
        "goal_display": _goal_display(goal_status, goals.get("spend"), money=True),
        "tone": None,
        "reason": None if meta.get("status") == "ok" else "missing",
    }
    leads_kpi = _volume_kpi(counts["inbound_leads"], goal_status, lead_goal)
    leads_kpi["detail"] = f"of which FB Quick Form: {counts['fb_quick_form_leads']}"
    opps_kpi = _volume_kpi(counts["opps"], goal_status, opp_goal)
    demos_kpi = _volume_kpi(counts["demos"], goal_status, demo_goal)
    sales_kpi = _volume_kpi(counts["sales"], goal_status, sale_goal)
    sold_view = sold_date_sales or {"status": "not_read", "value": None, "contact_ids": []}
    sold_value = sold_view.get("value") if sold_view.get("status") == "ok" else None
    sales_kpi["detail"] = f"by lead date · by Sold Date: {count_display(sold_value)}"
    sales_kpi["contact_ids"] = counts.get("sales_contact_ids") or []
    sales_by_sold_date_kpi = {
        "value": sold_value,
        "display": count_display(sold_value),
        "status": sold_view.get("status"),
        "contact_ids": sold_view.get("contact_ids") or [],
        "rule": (
            "Distinct contactId with Inbound or Facebook Quick Form Lead Gen Source, "
            "an opportunity in one of the eight Sold/Sale Cancelled stage ids, and "
            "Contact Sold Date (date-only) inside this window."
        ),
    }
    lead_cost_goal = cost_goal_value(goals, "cost_per_lead")
    opp_cost_goal = cost_goal_value(goals, "cost_per_opp")
    demo_cost_goal = cost_goal_value(goals, "cost_per_demo")
    sale_cost_goal = cost_goal_value(goals, "cost_per_sale")

    days = psf.window_dates(start_local, end_local)
    series = sessions.get("series") if sessions.get("status") == "ok" else None
    if series is None and sessions.get("status") == "ok":
        series = [{"date": day, "value": 0} for day in days]

    start_date = start_local.date().isoformat()
    end_date = (end_local.date() - timedelta(days=1)).isoformat()
    return {
        "metric": "Ads Dashboard",
        "timezone": TIMEZONE_NAME,
        "read_only": True,
        "include_fb_quick_form": include_quick_form,
        "start": start_date,
        "end": end_date,
        "window_start_local": start_local.isoformat(),
        "window_end_local": end_local.isoformat(),
        "created_at_query": {
            "start": created_at_bound(start_local),
            "end": created_at_bound(end_local),
        },
        "fb_quick_form_leads": counts["fb_quick_form_leads"],
        "fb_quick_form_matched": counts["fb_quick_form_matched"],
        "lead_contact_ids": counts["lead_contact_ids"],
        "kpis": {
            "spend": spend_kpi,
            "inbound_leads": leads_kpi,
            "cost_per_lead": cost_block(
                spend, counts["inbound_leads"], lead_cost_goal, money_goal_label(lead_cost_goal)
            ),
            "opps": opps_kpi,
            "cost_per_opp": cost_block(
                spend, counts["opps"], opp_cost_goal, money_goal_label(opp_cost_goal)
            ),
            "demos": demos_kpi,
            "cost_per_demo": cost_block(
                spend, counts["demos"], demo_cost_goal, money_goal_label(demo_cost_goal)
            ),
            "sales": sales_kpi,
            "cost_per_sale": cost_block(
                spend, counts["sales"], sale_cost_goal, money_goal_label(sale_cost_goal)
            ),
            "sales_by_sold_date": sales_by_sold_date_kpi,
        },
        "stages": counts["stages"],
        "stage_status": stage_status,
        "sessions_daily": series,
        "sessions": {
            "value": session_total,
            "display": count_display(session_total) if sessions.get("status") == "ok" else DASH,
            "status": sessions.get("status"),
            "measurement_id": psf.GA4_MEASUREMENT_ID,
        },
        "rates": {
            "sessions": {
                "value": session_total,
                "display": count_display(session_total) if sessions.get("status") == "ok" else DASH,
            },
            "clicks": {
                "value": clicks,
                "display": count_display(clicks) if meta.get("status") == "ok" else DASH,
            },
            "impressions": {
                "value": impressions,
                "display": count_display(impressions) if meta.get("status") == "ok" else DASH,
            },
            "leads_per_session": ratio_block(counts["inbound_leads"], session_total, kind="rate"),
            "leads_per_click": ratio_block(counts["inbound_leads"], clicks, kind="rate"),
            "cpc": ratio_block(spend, clicks, kind="money"),
            "ctr": ratio_block(clicks, impressions, kind="rate"),
            "cpm": ratio_block(spend, impressions, kind="cpm"),
        },
        "meta": {
            "status": meta.get("status"),
            "reason": meta.get("reason"),
            "account_timezone": meta.get("account_timezone"),
            "bucket": meta.get("bucket"),
            "aligned": meta.get("aligned"),
            "note": meta.get("note"),
            "clicks_field": meta.get("clicks_field") or "outbound_clicks",
        },
        "goals": {
            "status": goal_status,
            "month": goals.get("month"),
            "note": goals.get("note"),
        },
        "notes": [note for note in notes if note],
        "errors": [note for note in errors if note],
    }


def unavailable_payload(message: str, *, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    now = datetime.now(PHOENIX)
    if start and end:
        try:
            start_local, end_local = date_window(start, end)
        except Exception:
            start_local = now
            end_local = now
            start = None
            end = None
    else:
        start, end = default_range(now)
        start_local, end_local = date_window(start, end)
    payload = assemble_ads_dashboard(
        pipeline_opps=[],
        contact_opps=[],
        contacts={},
        stage_names={},
        start_local=start_local,
        end_local=end_local,
        now=now,
        meta={"status": "unavailable", "reason": "unavailable", "note": message, "spend": None, "clicks": None, "impressions": None},
        sessions={"status": "unavailable", "reason": "unavailable", "note": message, "total": None, "series": None},
        goals={"status": "unavailable", "note": message},
        stage_status="unavailable",
    )
    payload["start"] = start or payload["start"]
    payload["end"] = end or payload["end"]
    payload["kpis"]["inbound_leads"]["value"] = None
    payload["kpis"]["inbound_leads"]["display"] = DASH
    payload["kpis"]["inbound_leads"]["detail"] = "of which FB Quick Form: —"
    payload["kpis"]["opps"]["value"] = None
    payload["kpis"]["opps"]["display"] = DASH
    payload["kpis"]["demos"]["value"] = None
    payload["kpis"]["demos"]["display"] = DASH
    payload["kpis"]["sales"]["value"] = None
    payload["kpis"]["sales"]["display"] = DASH
    payload["fb_quick_form_leads"] = None
    payload["errors"] = [message]
    return payload


def month_keys(start_local: datetime, end_local: datetime) -> list[str]:
    if end_local <= start_local:
        return []
    months: list[str] = []
    cursor = start_local.date().replace(day=1)
    last = end_local.date()
    while cursor < last:
        months.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number


def _goal_result(
    status: str,
    month: str | None,
    note: str | None,
    found: dict[str, Any] | None = None,
) -> dict[str, Any]:
    found = found or {}
    return {
        "status": status,
        "month": month,
        "spend": found.get("spend"),
        "leads": found.get("leads"),
        "opps": found.get("opps"),
        "demos": found.get("demos"),
        "sales": found.get("sales"),
        "cost_per_lead": found.get("cost_per_lead"),
        "cost_per_opp": found.get("cost_per_opp"),
        "cost_per_demo": found.get("cost_per_demo"),
        "cost_per_sale": found.get("cost_per_sale"),
        "note": note,
    }


def goals_from_doc(data: dict[str, Any] | None, month: str) -> dict[str, Any]:
    goals = (data or {}).get("goals") if isinstance(data, dict) else None
    if not isinstance(goals, dict):
        return _goal_result("missing", month, None)
    folded = {_fold(key): value for key, value in goals.items() if isinstance(value, dict)}
    found: dict[str, Any] = {}
    for person in COMPANY_GOAL_KEYS:
        metrics = folded.get(person)
        if not isinstance(metrics, dict):
            continue
        metric_fold = {_fold(key): value for key, value in metrics.items()}
        for slot, names in GOAL_METRIC_NAMES.items():
            if slot in found:
                continue
            for name in names:
                if name in metric_fold:
                    raw = metric_fold[name]
                    if slot in COST_GOAL_KEYS:
                        found[slot] = _usable_cost_goal(raw)
                    else:
                        found[slot] = _number(raw)
                    break
    if not found:
        return _goal_result("missing", month, None)
    return _goal_result("ok", month, None, found)


def load_goals(db: Any, start_local: datetime, end_local: datetime) -> dict[str, Any]:
    months = month_keys(start_local, end_local)
    if len(months) != 1:
        return _goal_result("missing", None, "no goal")
    month = months[0]
    try:
        snap = db.collection(GOALS_COLLECTION).document(month).get()
    except Exception:
        return _goal_result("unavailable", month, "Monthly goals could not be read.")
    data = snap.to_dict() if getattr(snap, "exists", False) else {}
    return goals_from_doc(data, month)


def load_stage_names(db: Any) -> dict[str, str]:
    """One read of the Inbound/Lead Locker pipeline, memoized on the module."""
    global _STAGE_NAMES
    if _STAGE_NAMES is not None:
        return _STAGE_NAMES
    snap = db.collection(PIPELINE_COLLECTION).document(LEAD_PIPELINE_ID).get()
    names: dict[str, str] = {}
    data = snap.to_dict() if getattr(snap, "exists", False) else None
    if isinstance(data, dict):
        for stage in data.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stage_id = cac.compact_str(stage.get("id"))
            stage_name = " ".join(str(stage.get("name") or "").strip().split())
            if stage_id and stage_name:
                names[stage_id] = stage_name
    _STAGE_NAMES = names
    return names


def _missing_composite_index(exc: BaseException) -> bool:
    if type(exc).__name__ == "FailedPrecondition":
        return True
    return "requires an index" in str(exc).lower()


def _log_read_error(exc: BaseException) -> None:
    """Log a read failure without printing tokens or request URLs."""
    text = " ".join(str(exc).split())
    marker = text.lower().find("access_token=")
    if marker >= 0:
        text = text[:marker] + "access_token=redacted"
    for scheme in ("https://", "http://"):
        if scheme in text:
            text = text.split(scheme, 1)[0].rstrip()
            break
    text = text[:180]
    sys.stderr.write(f"ads_dashboard {type(exc).__name__}: {text}\n")


def load_pipeline_opps(db: Any, start_local: datetime, end_local: datetime) -> list[dict[str, Any]]:
    """Inbound pipeline created in the Phoenix window.

    Prefer pipelineId + createdAt. If that composite index is not built, fall
    back to the createdAt range and keep this pipeline in memory. Never scan
    the collection with no bound.
    """
    global _PIPELINE_READ_NOTE
    start_iso = created_at_bound(start_local)
    end_iso = created_at_bound(end_local)
    _PIPELINE_READ_NOTE = None
    try:
        snaps = list(
            db.collection(OPP_COLLECTION)
            .where("pipelineId", "==", LEAD_PIPELINE_ID)
            .where("createdAt", ">=", start_iso)
            .where("createdAt", "<", end_iso)
            .stream()
        )
    except Exception as exc:
        if not _missing_composite_index(exc):
            raise
        _PIPELINE_READ_NOTE = INDEX_FALLBACK_NOTE
        snaps = list(
            db.collection(OPP_COLLECTION)
            .where("createdAt", ">=", start_iso)
            .where("createdAt", "<", end_iso)
            .stream()
        )
    loaded: list[dict[str, Any]] = []
    for snap in snaps:
        opp = snap.to_dict() or {}
        if not cac.compact_str(opp.get("id")):
            opp["id"] = snap.id
        if cac.compact_str(opp.get("pipelineId")) != LEAD_PIPELINE_ID:
            continue
        created = cac.parse_iso_dt(opp.get("createdAt"))
        if _in_window(created, start_local, end_local):
            loaded.append(opp)
    return loaded


def load_contacts(db: Any, contact_ids: list[str]) -> dict[str, dict]:
    """Bounded get_all for the window's contact ids. No collection scan."""
    contacts: dict[str, dict] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        cid = cac.compact_str(raw)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        needed.append(cid)
    refs = [db.collection(CONTACT_COLLECTION).document(cid) for cid in needed]
    for offset in range(0, len(refs), CONTACT_GET_ALL_CHUNK):
        for snap in db.get_all(refs[offset : offset + CONTACT_GET_ALL_CHUNK]):
            if not getattr(snap, "exists", False):
                continue
            data = snap.to_dict() or {}
            cid = cac.compact_str(data.get("id") or snap.id)
            if cid:
                contacts[cid] = data
            if snap.id:
                contacts[cac.compact_str(snap.id)] = data
    for cid in needed:
        if cid in contacts:
            continue
        misses = list(db.collection(CONTACT_COLLECTION).where("id", "==", cid).limit(1).stream())
        if misses:
            contacts[cid] = misses[0].to_dict() or {}
    return contacts


def load_opps_for_contacts(db: Any, contact_ids: list[str]) -> list[dict[str, Any]]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        cid = cac.compact_str(raw)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    found: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(ids), CONTACT_IN_CHUNK):
        chunk = ids[offset : offset + CONTACT_IN_CHUNK]
        query = db.collection(OPP_COLLECTION).where("contactId", "in", chunk)
        for index, snap in enumerate(query.stream()):
            opp = snap.to_dict() or {}
            if not cac.compact_str(opp.get("id")):
                opp["id"] = snap.id
            found[cac.compact_str(opp.get("id")) or f"{offset}:{index}"] = opp
    return list(found.values())


def load_sold_candidates(db: Any) -> tuple[list[dict[str, Any]], dict[str, dict]]:
    """Opps in the eight Sold/Sale Cancelled stage ids and their contacts.

    Same bounded read as /api/metrics/sales: one `in` query on the eight ids,
    then get_all on those contacts. Shared across windows for CACHE_TTL_SECONDS.

    Moved-sale fallback: a sold opp whose current contact has no Lead Gen
    Source (a duplicate or merged stub) gets its stage history read by opp id
    (bounded `in` query) to find the contacts it had before; those contacts
    are added with get_all. Prior ids are kept on the opp under
    PRIOR_CONTACTS_KEY. A failed history read leaves the fallback off.
    """
    global _SOLD_CANDIDATES
    if _SOLD_CANDIDATES is not None and time.monotonic() - _SOLD_CANDIDATES[0] <= CACHE_TTL_SECONDS:
        return _SOLD_CANDIDATES[1], _SOLD_CANDIDATES[2]
    stage_ids = sorted(_sold_stage_ids())
    opps: list[dict[str, Any]] = []
    for snap in db.collection(OPP_COLLECTION).where(cac.STAGE_FIELD, "in", stage_ids).stream():
        opp = snap.to_dict() or {}
        if not cac.compact_str(opp.get("id")):
            opp["id"] = snap.id
        opps.append(opp)
    contacts = load_contacts(db, [_contact_id(opp) for opp in opps])
    moved = [
        opp
        for opp in opps
        if not _opp_deleted(opp) and _opp_id(opp, "") and not lead_source(contacts.get(_contact_id(opp)))
    ]
    try:
        moved_history = load_stage_history(db, [_opp_id(opp, "") for opp in moved])
    except Exception:
        moved_history = {}
    prior_ids: list[str] = []
    for opp in moved:
        prior = _sold_opp_contact_ids(opp, moved_history)[1:]
        if prior:
            opp[PRIOR_CONTACTS_KEY] = prior
            prior_ids.extend(cid for cid in prior if cid not in contacts)
    if prior_ids:
        contacts.update(load_contacts(db, prior_ids))
    _SOLD_CANDIDATES = (time.monotonic(), opps, contacts)
    return opps, contacts


def sales_by_sold_date(
    sold_opps: list[dict[str, Any]],
    contacts: dict[str, dict],
    start_local: datetime,
    end_local: datetime,
    *,
    include_quick_form: bool | None = None,
) -> dict[str, Any]:
    """Sold Date view: distinct Inbound/Quick Form contacts sold in the window.

    A sold opp counts for the original ad-lead contact it has had (current
    contact or one it moved from), once. Sold Date (date-only) comes from the
    current contact if it carries one, else the newest prior contact that does.
    """
    sold_ids = _sold_stage_ids()
    found: set[str] = set()
    for opp in sold_opps:
        if cac.compact_str(opp.get(cac.STAGE_FIELD)) not in sold_ids or _opp_deleted(opp):
            continue
        had = _sold_opp_contact_ids(opp)
        ad_ids = [cid for cid in had if is_ad_lead(contacts.get(cid), include_quick_form)]
        if not ad_ids:
            continue
        if cac.sold_date_in_window(_first_sold_date(had, contacts), start_local, end_local):
            found.add(ad_ids[-1])
    return {"status": "ok", "value": len(found), "contact_ids": sorted(found)}


def _append_history_row(found: dict[str, list[dict[str, Any]]], row: dict[str, Any]) -> None:
    opp_id = cac.compact_str(row.get("opportunityId"))
    if opp_id:
        found.setdefault(opp_id, []).append(row)


def load_stage_history(db: Any, opportunity_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Bounded history reads for opportunities that still exist. No collection scan."""
    ids: list[str] = []
    seen: set[str] = set()
    for raw in opportunity_ids:
        opp_id = cac.compact_str(raw)
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        ids.append(opp_id)
    found: dict[str, list[dict[str, Any]]] = {}
    for offset in range(0, len(ids), CONTACT_IN_CHUNK):
        chunk = ids[offset : offset + CONTACT_IN_CHUNK]
        query = db.collection(HISTORY_COLLECTION).where("opportunityId", "in", chunk)
        for snap in query.stream():
            _append_history_row(found, snap.to_dict() or {})
    return found


def load_stage_history_by_contact(db: Any, contact_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """History for lead contacts, including opportunities that were deleted."""
    ids: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        contact_id = cac.compact_str(raw)
        if not contact_id or contact_id in seen:
            continue
        seen.add(contact_id)
        ids.append(contact_id)
    found: dict[str, list[dict[str, Any]]] = {}
    for offset in range(0, len(ids), CONTACT_IN_CHUNK):
        chunk = ids[offset : offset + CONTACT_IN_CHUNK]
        query = db.collection(HISTORY_COLLECTION).where("contactId", "in", chunk)
        for snap in query.stream():
            _append_history_row(found, snap.to_dict() or {})
    return found


def merge_stage_history(*parts: dict[str, list[dict[str, Any]]] | None) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for part in parts:
        for opp_id, rows in (part or {}).items():
            merged.setdefault(opp_id, []).extend(rows)
    return merged


def load_pipeline_stage_map(db: Any, pipeline_ids: tuple[str, ...] | list[str]) -> dict[str, str]:
    """One document get per pipeline. Used for city, Sweeper, and Rehash stage names."""
    names: dict[str, str] = {}
    for pipeline_id in pipeline_ids:
        snap = db.collection(PIPELINE_COLLECTION).document(pipeline_id).get()
        data = snap.to_dict() if getattr(snap, "exists", False) else None
        if not isinstance(data, dict):
            continue
        for stage in data.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stage_id = cac.compact_str(stage.get("id"))
            stage_name = " ".join(str(stage.get("name") or "").strip().split())
            if stage_id and stage_name:
                names[stage_id] = stage_name
    return names


def _get_json(url: str, urlopen: Any) -> dict[str, Any] | None:
    opener = urlopen or urllib.request.urlopen
    req = urllib.request.Request(url, method="GET")
    with opener(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def account_timezone_url(account_id: str, token: str) -> str:
    if account_id != psf.META_ACCOUNT_ID:
        raise RuntimeError("Refusing a Meta read for a different account")
    params = urllib.parse.urlencode(
        {
            "fields": "timezone_name,timezone_offset_hours_utc",
            "access_token": token,
        }
    )
    return (
        f"{cac.META_GRAPH_API_HOST}/{cac.META_GRAPH_API_VERSION}/"
        f"{urllib.parse.quote(account_id)}?{params}"
    )


def read_account_timezone(account_id: str, token: str, urlopen: Any = None) -> dict[str, Any] | None:
    try:
        url = account_timezone_url(account_id, token)
        payload = _get_json(url, urlopen)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    name = cac.compact_str(payload.get("timezone_name")) or None
    return {
        "timezone_name": name,
        "timezone_offset_hours_utc": payload.get("timezone_offset_hours_utc"),
    }


def zone_aligns(name: str | None, start_local: datetime, end_local: datetime) -> bool:
    if not name:
        return False
    if _fold(name) in PHOENIX_ZONE_NAMES:
        return True
    try:
        zone = ZoneInfo(name)
    except Exception:
        return False
    day = start_local.date()
    last = end_local.date()
    while day < last:
        account_noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=zone)
        phoenix_noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=PHOENIX)
        if account_noon.utcoffset() != phoenix_noon.utcoffset():
            return False
        day += timedelta(days=1)
    return True


def _offset_hours(name: str, moment: datetime) -> int | None:
    try:
        zone = ZoneInfo(name)
    except Exception:
        return None
    probe = datetime(moment.year, moment.month, moment.day, 12, 0, tzinfo=zone)
    phoenix = datetime(moment.year, moment.month, moment.day, 12, 0, tzinfo=PHOENIX)
    account_off = probe.utcoffset()
    phoenix_off = phoenix.utcoffset()
    if account_off is None or phoenix_off is None:
        return None
    return int((account_off - phoenix_off).total_seconds() // 3600)


def offset_note(name: str | None, start_local: datetime, *, hourly_failed: bool) -> str:
    if not name:
        return (
            "Ad account timezone could not be read. Meta day buckets follow the "
            "ad account, which may differ from America/Phoenix."
        )
    hours = _offset_hours(name, start_local)
    if hours is None:
        base = f"Ad account timezone is {name}."
    elif hours == 0:
        base = (
            f"Ad account timezone is {name}. Its UTC offset matches America/Phoenix "
            "for this window, so Meta days are Phoenix days."
        )
    else:
        direction = "ahead of" if hours > 0 else "behind"
        base = (
            f"Ad account timezone is {name}, {abs(hours)} hours {direction} America/Phoenix."
        )
    if hourly_failed and hours not in (None, 0):
        base += " Hourly grouping was unavailable, so these Meta days follow the ad account."
    return base


def _sum_rows(rows: list[dict[str, Any]], getter, *, money: bool) -> float | int | None:
    """Successful empty insight rows are zero. Rows missing the field stay blank."""
    if not rows:
        return 0.0 if money else 0
    total = Decimal("0")
    seen = False
    for row in rows:
        value = getter(row)
        if value is None:
            continue
        seen = True
        total += Decimal(str(value))
    if not seen:
        return None
    if money:
        return money_round(total)
    return int(total)


def _row_clicks(row: dict[str, Any]) -> int | None:
    outbound = psf._outbound_click_count(row)
    if outbound is not None:
        return outbound
    if "clicks" in row:
        return psf._optional_int(row.get("clicks"), True)
    return None


def _row_spend(row: dict[str, Any]) -> float | None:
    if "spend" not in row:
        return None
    return cac.parse_meta_spend_value(row.get("spend"))


def _row_impressions(row: dict[str, Any]) -> int | None:
    if "impressions" not in row:
        return None
    return psf._optional_int(row.get("impressions"), True)


def parse_hour_start(label: Any) -> int | None:
    text = cac.compact_str(label)
    if len(text) < 2 or not text[:2].isdigit():
        return None
    hour = int(text[:2])
    if hour < 0 or hour > 23:
        return None
    return hour


def phoenix_day_for_hour(date_start: str, hour: int, account_zone: ZoneInfo) -> str | None:
    try:
        year, month, day = (int(part) for part in date_start[:10].split("-"))
        local = datetime(year, month, day, hour, 0, tzinfo=account_zone)
    except Exception:
        return None
    return local.astimezone(PHOENIX).date().isoformat()


def rebucket_hourly(
    rows: list[dict[str, Any]],
    account_timezone: str,
    start_local: datetime,
    end_local: datetime,
) -> dict[str, Any] | None:
    try:
        zone = ZoneInfo(account_timezone)
    except Exception:
        return None
    days = set(psf.window_dates(start_local, end_local))
    spend = Decimal("0")
    clicks = 0
    impressions = 0
    seen = False
    for row in rows:
        hour = parse_hour_start(row.get(HOURLY_BREAKDOWN) or row.get("hourly_stats_aggregated_by_advertiser_time_zone"))
        day = cac.compact_str(row.get("date_start"))[:10]
        if hour is None or len(day) != 10:
            continue
        phoenix_day = phoenix_day_for_hour(day, hour, zone)
        if phoenix_day not in days:
            continue
        seen = True
        row_spend = _row_spend(row)
        row_clicks = _row_clicks(row)
        row_impressions = _row_impressions(row)
        if row_spend is not None:
            spend += Decimal(str(row_spend))
        if row_clicks is not None:
            clicks += int(row_clicks)
        if row_impressions is not None:
            impressions += int(row_impressions)
    if not seen and rows:
        return None
    return {
        "status": "ok",
        "reason": None,
        "spend": money_round(spend),
        "clicks": clicks,
        "impressions": impressions,
        "account_timezone": account_timezone,
        "bucket": TIMEZONE_NAME,
        "aligned": False,
        "clicks_field": "outbound_clicks",
        "note": (
            f"Ad account timezone is {account_timezone}. "
            "Hourly insights were grouped onto America/Phoenix days."
        ),
    }


def _daily_totals(daily: dict[str, Any], account_timezone: str | None, aligned: bool, note: str | None) -> dict[str, Any]:
    ok = daily.get("status") == "ok"
    rows = list(daily.get("rows") or []) if ok else []
    if ok:
        shown = note
    else:
        shown = note or "Meta spend could not be read."
    return {
        "status": "ok" if ok else "unavailable",
        "reason": daily.get("reason"),
        "spend": _sum_rows(rows, lambda row: row.get("spend"), money=True) if ok else None,
        "clicks": _sum_rows(rows, lambda row: row.get("outbound_clicks"), money=False) if ok else None,
        "impressions": _sum_rows(rows, lambda row: row.get("impressions"), money=False) if ok else None,
        "account_timezone": account_timezone,
        "bucket": TIMEZONE_NAME if aligned else "account",
        "aligned": aligned,
        "clicks_field": "outbound_clicks",
        "note": shown,
    }


def fetch_hourly_rows(
    start_local: datetime,
    end_local: datetime,
    *,
    token: str,
    account_id: str,
    urlopen: Any = None,
) -> list[dict[str, Any]] | None:
    since = (start_local.date() - timedelta(days=1)).isoformat()
    until = (end_local.date() + timedelta(days=1)).isoformat()
    try:
        url = psf.insights_request_url(account_id, token, since, until, None)
    except RuntimeError:
        return None
    url = f"{url}&breakdowns={urllib.parse.quote(HOURLY_BREAKDOWN)}"
    try:
        payload = _get_json(url, urlopen)
    except Exception:
        return None
    if not payload or payload.get("error"):
        return None
    rows, _ignored = psf._insight_rows(payload, urlopen)
    if rows and not any(parse_hour_start(row.get(HOURLY_BREAKDOWN)) is not None for row in rows):
        return None
    return rows


def fetch_meta_for_window(
    start_local: datetime,
    end_local: datetime,
    *,
    token: str | None = None,
    account_id: str | None = None,
    urlopen: Any = None,
) -> dict[str, Any]:
    """Account insights on Phoenix days when the account timezone allows it."""
    if token is None or account_id is None:
        token, account_id, reason = cac.read_meta_ads_credentials()
        if reason or not token or not account_id:
            return {
                "status": "unavailable",
                "reason": reason or "missing_env",
                "spend": None,
                "clicks": None,
                "impressions": None,
                "account_timezone": None,
                "bucket": None,
                "aligned": None,
                "note": "Meta spend could not be read.",
                "clicks_field": "outbound_clicks",
            }
    account_tz = read_account_timezone(account_id, token, urlopen)
    tz_name = (account_tz or {}).get("timezone_name")
    aligned = zone_aligns(tz_name, start_local, end_local)
    daily = psf.fetch_meta_daily(
        start_local,
        end_local,
        token=token,
        account_id=account_id,
        urlopen=urlopen,
    )
    if aligned:
        note = None
        if tz_name and _fold(tz_name) not in PHOENIX_ZONE_NAMES:
            note = (
                f"Ad account timezone is {tz_name}. Its UTC offset matches "
                "America/Phoenix for this window, so Meta days are Phoenix days."
            )
        return _daily_totals(daily, tz_name, True, note)
    hourly_rows = fetch_hourly_rows(
        start_local,
        end_local,
        token=token,
        account_id=account_id,
        urlopen=urlopen,
    )
    if hourly_rows is not None and tz_name:
        grouped = rebucket_hourly(hourly_rows, tz_name, start_local, end_local)
        if grouped is not None:
            return grouped
    note = offset_note(tz_name, start_local, hourly_failed=True)
    return _daily_totals(daily, tz_name, False, note)


def sum_paid_channel_rows(rows: list[dict[str, Any]] | None, days: list[str]) -> dict[str, Any]:
    """Paid Social and Paid Search sessions. Other channel groups stay out."""
    by_day = {day: 0 for day in days}
    traffic = None
    try:
        traffic = psf._load_website_traffic()
    except Exception:
        traffic = None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        channel = _fold(row.get("sessionDefaultChannelGroup") or row.get("channel"))
        if channel not in PAID_CHANNEL_GROUPS:
            continue
        if traffic is not None:
            day = traffic.normalize_series_date(row.get("date"))
        else:
            day = cac.compact_str(row.get("date"))[:10]
        if day not in by_day:
            continue
        raw = row.get("sessions")
        if raw in (None, ""):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        by_day[day] += value
    return {
        "status": "ok",
        "total": sum(by_day.values()),
        "series": [{"date": day, "value": by_day[day]} for day in days],
        "note": None,
    }


def fetch_paid_sessions(
    start_local: datetime,
    end_local: datetime,
    *,
    report_runner: Any = None,
) -> dict[str, Any]:
    """GA4 paid sessions on stream G-V02RZFR4SZ. Reuses the existing report body."""
    days = psf.window_dates(start_local, end_local)
    start = start_local.date().isoformat()
    end = (end_local.date() - timedelta(days=1)).isoformat()
    if end < start:
        end = start
    blank = {
        "status": "unavailable",
        "reason": "ga4_failed",
        "total": None,
        "series": None,
        "note": "Paid sessions could not be read.",
        "measurement_id": psf.GA4_MEASUREMENT_ID,
    }
    try:
        traffic = psf._load_website_traffic()
        funnel = traffic.funnel_mod()
    except Exception:
        blank["reason"] = "ga4_client_unavailable"
        return blank
    if funnel.GA4_PROPERTY_ID != psf.GA4_PROPERTY_ID or funnel.GA4_MEASUREMENT_ID != psf.GA4_MEASUREMENT_ID:
        blank["reason"] = "property_mismatch"
        return blank
    property_id = traffic.compact_str(os.environ.get(funnel.GA4_PROPERTY_ID_ENV)) or funnel.GA4_PROPERTY_ID
    if property_id != psf.GA4_PROPERTY_ID:
        blank["reason"] = "property_mismatch"
        return blank
    if report_runner is None:
        if not funnel.ga4_credentials_available():
            blank["reason"] = "not_configured"
            blank["note"] = "Paid sessions are not configured."
            return blank
        report_runner = traffic.run_ga4_report
    body = psf._sessions_body(traffic, start, end)
    dimensions = tuple(item["name"] for item in body["dimensions"])
    metrics = tuple(item["name"] for item in body["metrics"])
    try:
        raw = report_runner(body)
        parsed = psf._parsed_ga4_rows(raw, traffic, dimensions, metrics)
    except Exception:
        return blank
    if parsed is None:
        return blank
    counted = sum_paid_channel_rows(parsed, days)
    counted["measurement_id"] = psf.GA4_MEASUREMENT_ID
    counted["reason"] = None
    return counted


def _cache_get(key: tuple) -> dict | None:
    hit = _RESPONSE_CACHE.get(key)
    if not hit:
        return None
    stored, payload = hit
    if time.monotonic() - stored > CACHE_TTL_SECONDS:
        return None
    return payload


def _cache_put(key: tuple, payload: dict) -> None:
    _RESPONSE_CACHE[key] = (time.monotonic(), payload)


def compute_ads_dashboard(
    db: Any,
    *,
    start: str,
    end: str,
    now: datetime | None = None,
    include_quick_form: bool | None = None,
    meta_fetcher: Any = None,
    sessions_fetcher: Any = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    start_local, end_local = date_window(start, end)
    if (end_local.date() - start_local.date()).days > MAX_RANGE_DAYS:
        raise ValueError(f"Date range is longer than {MAX_RANGE_DAYS} days")
    now = now or datetime.now(PHOENIX)
    flag = INCLUDE_FB_QUICK_FORM if include_quick_form is None else include_quick_form
    cache_key = (start_local.isoformat(), end_local.isoformat(), flag)
    cacheable = use_cache and meta_fetcher is None and sessions_fetcher is None
    if cacheable:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    pipeline_opps = load_pipeline_opps(db, start_local, end_local)
    index_note = _PIPELINE_READ_NOTE
    window_contacts = load_contacts(db, [_contact_id(opp) for opp in pipeline_opps])
    lead_ids = [
        cid
        for cid in {_contact_id(opp) for opp in pipeline_opps}
        if cid and is_ad_lead(window_contacts.get(cid), flag)
    ]
    contact_opps = load_opps_for_contacts(db, lead_ids)
    history_note = None
    by_opportunity: dict[str, list[dict[str, Any]]] = {}
    by_contact: dict[str, list[dict[str, Any]]] = {}
    try:
        by_opportunity = load_stage_history(db, [_opp_id(opp, "") for opp in contact_opps])
    except Exception:
        history_note = (
            "Opportunity stage history could not be read, so opps only include "
            "opportunities currently in Buffalo, Rochester, Syracuse, or Virtual."
        )
    try:
        by_contact = load_stage_history_by_contact(db, lead_ids)
    except Exception:
        history_note = history_note or (
            "Stage history for deleted opportunities could not be read."
        )
    history = merge_stage_history(by_opportunity, by_contact)
    try:
        stage_names = load_stage_names(db)
        stage_status = "ok"
    except Exception:
        stage_names = {}
        stage_status = "unavailable"
    try:
        stage_names = {
            **stage_names,
            **load_pipeline_stage_map(
                db,
                (*cac.TERRITORY_PIPELINE_IDS, SWEEPER_PIPELINE_ID, REHASH_PIPELINE_ID),
            ),
        }
    except Exception:
        pass
    try:
        goals = load_goals(db, start_local, end_local)
    except Exception:
        goals = _goal_result("unavailable", None, "Monthly goals could not be read.")
    try:
        sold_opps, sold_contacts = load_sold_candidates(db)
        sold_date_view = sales_by_sold_date(
            sold_opps, sold_contacts, start_local, end_local, include_quick_form=flag
        )
    except Exception:
        sold_opps, sold_contacts = None, None
        sold_date_view = {"status": "unavailable", "value": None, "contact_ids": []}
    if meta_fetcher:
        meta = meta_fetcher(start_local, end_local)
    else:
        meta = fetch_meta_for_window(start_local, end_local)
    if sessions_fetcher:
        sessions = sessions_fetcher(start_local, end_local)
    else:
        sessions = fetch_paid_sessions(start_local, end_local)
    payload = assemble_ads_dashboard(
        pipeline_opps=pipeline_opps,
        contact_opps=contact_opps,
        contacts=window_contacts,
        stage_names=stage_names,
        start_local=start_local,
        end_local=end_local,
        now=now,
        meta=meta,
        sessions=sessions,
        goals=goals,
        include_quick_form=flag,
        stage_status=stage_status,
        history=history,
        sold_date_sales=sold_date_view,
        sold_opps=sold_opps,
        sold_contacts=sold_contacts,
    )
    if history_note:
        payload["notes"] = [history_note, *payload.get("notes", [])]
    if index_note:
        payload["notes"] = [index_note, *payload.get("notes", [])]
    if cacheable:
        _cache_put(cache_key, payload)
    return payload


def compute_from_query(qs: dict[str, list[str]], db: Any = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(PHOENIX)
    start, end = parse_range(qs, now)
    database = db if db is not None else cac.get_db()
    return compute_ads_dashboard(database, start=start, end=end, now=now)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            payload = compute_from_query(qs)
            status = 200
            cache = "public, s-maxage=600, stale-while-revalidate=1800"
        except ValueError as exc:
            payload = unavailable_payload(str(exc))
            status = 400
            cache = "no-store"
        except Exception as exc:
            _log_read_error(exc)
            payload = unavailable_payload("Ads Dashboard could not be read.")
            status = 200
            cache = "no-store"
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)
