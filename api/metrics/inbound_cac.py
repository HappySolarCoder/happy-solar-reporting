# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/inbound_cac

Inbound lead-source CAC for Happy Solar. Leadership page (direct URL).

Warehouse facts (locked — do not invent names):
- Firestore DB `happy-solar` on GCP project `gemini-assistant-bot`
- Pipeline: name `Inbound/Lead Locker`, id `7nSEgeoBYXZiIS7x41Jy`
  (Charles said "Inbound/3PL"; that name is not in ghl_pipelines_v2.)
- Opportunity title field: ghl_opportunities_v2.name (not title)
- Refunded stage on this pipeline: name `Refunded`,
  id `5bb63eb2-2208-481e-a0b9-f82ece3c030a`
- Sale stages: locked Sold / Sale Cancelled IDs from sales.py.
  There is no stage named `Won`. Charles said Won; warehouse uses Sold.

Title buckets (case-insensitive):
- contains `lead locker` → Lead Locker, unit cost $45
- contains `solar review` or `solar reviews` → Solar Reviews, unit cost $70

Metric per row (same rules for YTD window or a single NY month):
1. Scope inbound opps: pipelineId == Inbound/Lead Locker AND title match
   AND pipelineStageId != Refunded AND createdAt in the window.
2. Spend = count(those opps) × unit cost.
3. Sales = distinct contactId among those spend-scope opps that also appear
   on at least one opportunity currently in the 8 Sold/Sale Cancelled stage
   IDs AND whose Contact Sold Date (P9oBjgbZjJdeE0OkBj9T) falls in the same
   window (date-only; do not timezone-shift a ...Z wrapper).
   Missing Sold Date is excluded — same as sales.py.
4. CAC (lead) = spend / sales. sales == 0 → JSON null, never 0.
5. Setter unit cost SETTER_UNIT_COST = $500 per sale (constant; not invented).
   setter_spend = sales × 500.
   TAC = (lead_spend + setter_spend) / sales  (= CAC + 500 when sales > 0).
   sales == 0 → TAC JSON null, never 0 (same as CAC).
6. Overall CAC / TAC use the same formulas on totals.
7. Monthly chart series: Lead Locker / Solar Reviews CAC plus matching TAC
   series. Months with sales=0 are JSON null gaps, never 0.

Performance KPIs (same window; table under YTD totals):
- opportunities_created = four-pipeline Opportunities Created (createdAt).
  No inbound title→four-pipeline join exists; do not invent one.
- opp_to_prelim = inbound CAC sales / opportunities_created (null if created=0).
- demo_rate = four-pipeline sits / opportunities_created (Evan’s formula;
  not Bot KPI Sit/(Sit+No Sit); exclude rehash/sweeper; sit time =
  appointmentOccurredAt, exclude future vs now UTC).

Queries:
- Inbound: where pipelineId == 7nSEgeoBYXZiIS7x41Jy (≈1261 historical docs;
  window filter in memory).
- Sales: pipelineStageId IN the 8 locked stage IDs, then get_all those
  intersection contacts only.
- Created: createdAt range on ghl_opportunities_v2, then four-pipeline name filter.
- Sits: appointmentOccurredAt range, dispositionValue==Sit, four-pipeline only.
- No full-stream of ghl_opportunities_v2 or ghl_contacts_v2.

Params:
- year (America/New_York; default current ET year)
- month optional (1-12). Omitted / blank / ytd → YTD for that year.
- format=json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from opportunities_created import pipeline_id_keys, pipeline_name_lookup, resolve_pipeline_name
from sales import SalesMetricContract, get_db

TIMEZONE_NAME = "America/New_York"
OPP_COLLECTION = "ghl_opportunities_v2"
CONTACT_COLLECTION = "ghl_contacts_v2"
CREATED_AT_FIELD = "createdAt"
STAGE_FIELD = "pipelineStageId"
TITLE_FIELD = "name"
APPOINTMENT_OCCURRED_AT_FIELD = "appointmentOccurredAt"
DISPOSITION_VALUE_FIELD = "dispositionValue"
SIT_DISPOSITION = "Sit"

# Opportunities Created core scope (Buffalo / Syracuse / Rochester / Virtual).
# Rehash / Sweeper are not in this set — do not silently include them for sits.
FOUR_PIPELINE_NAMES: tuple[str, ...] = ("buffalo", "syracuse", "rochester", "virtual")
EXCLUDED_PIPELINE_NAMES: tuple[str, ...] = ("inbound/lead locker",)

# Investigated 2026-08-25: no warehouse field maps inbound CAC title buckets
# (Lead Locker / Solar Reviews on pipeline 7nSEgeoBYXZiIS7x41Jy) onto the four
# sales pipelines. Contact lead gen source hd5QqHEOVSsPom5bJ32P can be Inbound
# on four-pipeline opps, but it is not Lead Locker / Solar Reviews and is not
# a join from inbound CAC spend-scope opps. Do not invent a key.
INBOUND_FOUR_PIPELINE_JOIN_EXISTS = False
INBOUND_FOUR_PIPELINE_JOIN_FIELD = None
INBOUND_FOUR_PIPELINE_JOIN_GAP = (
    "No warehouse field maps inbound CAC Lead Locker / Solar Reviews "
    "(ghl_opportunities_v2.name on pipeline 7nSEgeoBYXZiIS7x41Jy) onto "
    "Buffalo / Rochester / Syracuse / Virtual. Opportunities Created excludes "
    "Inbound/Lead Locker. Contact CF hd5QqHEOVSsPom5bJ32P can be Inbound but "
    "is not Lead Locker / Solar Reviews."
)
INBOUND_FOUR_PIPELINE_JOIN_GAP_SHORT = (
    "No inbound Lead Locker / Solar Reviews join onto the four sales pipelines; "
    "this is the four-pipeline Opportunities Created count."
)

INBOUND_PIPELINE_NAME = "Inbound/Lead Locker"
INBOUND_PIPELINE_ID = "7nSEgeoBYXZiIS7x41Jy"
REFUNDED_STAGE_NAME = "Refunded"
REFUNDED_STAGE_ID = "5bb63eb2-2208-481e-a0b9-f82ece3c030a"
SOLD_DATE_CUSTOM_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"
SETTER_UNIT_COST = 500

SALE_STAGE_NAMES: tuple[str, ...] = (
    "Buffalo Sold",
    "Buffalo Sale Cancelled",
    "Syracuse Sold",
    "Syracuse Sale Cancelled",
    "Rochester Sold",
    "Rochester Sale Cancelled",
    "Virtual Sold",
    "Virtual Sale Cancelled",
)


@dataclass(frozen=True)
class InboundSource:
    key: str
    label: str
    unit_cost: int


SOURCES: tuple[InboundSource, ...] = (
    InboundSource("lead_locker", "Lead Locker", 45),
    InboundSource("solar_reviews", "Solar Reviews", 70),
)

SOURCE_LABELS: tuple[str, ...] = tuple(source.label for source in SOURCES)


@dataclass(frozen=True)
class InboundOppRecord:
    bucket: str | None
    in_window: bool
    refunded: bool
    contact_id: str


@dataclass(frozen=True)
class RawInboundOpp:
    bucket: str | None
    created_local: datetime | None
    refunded: bool
    contact_id: str


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def bucket_title(name: Any) -> str | None:
    """Case-insensitive title bucket. Uses ghl_opportunities_v2.name only."""
    text = str(name or "").casefold()
    if "lead locker" in text:
        return "Lead Locker"
    if "solar review" in text:
        return "Solar Reviews"
    return None


def is_refunded_stage(stage_id: Any) -> bool:
    return compact_str(stage_id) == REFUNDED_STAGE_ID


def compute_cac(spend: float | int, sales: int) -> float | None:
    if sales == 0:
        return None
    return spend / sales


def compute_setter_spend(sales: int, setter_unit_cost: int = SETTER_UNIT_COST) -> int:
    return int(sales) * setter_unit_cost


def compute_tac(
    lead_spend: float | int,
    sales: int,
    setter_unit_cost: int = SETTER_UNIT_COST,
) -> float | None:
    """TAC = (lead_spend + sales × 500) / sales. sales == 0 → JSON null."""
    if sales == 0:
        return None
    return (lead_spend + compute_setter_spend(sales, setter_unit_cost)) / sales


def attach_acquisition_costs(
    row: dict[str, Any],
    setter_unit_cost: int = SETTER_UNIT_COST,
) -> dict[str, Any]:
    """Add setter_unit_cost, setter_spend, and tac. Does not invent other $."""
    sales = int(row.get("sales") or 0)
    spend = int(row.get("spend") or 0)
    row["setter_unit_cost"] = setter_unit_cost
    row["setter_spend"] = compute_setter_spend(sales, setter_unit_cost)
    row["tac"] = compute_tac(spend, sales, setter_unit_cost)
    return row


def parse_inbound_cac_params(qs: dict[str, list[str]], now: datetime) -> tuple[int, int | None]:
    """Default year = current ET year. Default month omitted → YTD."""
    year_raw = (qs.get("year") or [str(now.year)])[0]
    year = int(year_raw)
    month_raw = compact_str((qs.get("month") or [""])[0]).casefold()
    if month_raw in ("", "ytd"):
        return year, None
    return year, int(month_raw)


def parse_optional_range(qs: dict[str, list[str]]) -> tuple[str | None, str | None]:
    """Optional inclusive YYYY-MM-DD start/end for QA windows. Both required."""
    start = compact_str((qs.get("start") or [""])[0]) or None
    end = compact_str((qs.get("end") or [""])[0]) or None
    if start and end:
        return start, end
    return None, None


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value or not isinstance(value, str):
        return None
    try:
        year, month, day = [int(part) for part in value.strip().split("-")]
        return year, month, day
    except Exception:
        return None


def date_range_window(start_ymd: str, end_ymd: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
    """Inclusive start/end dates in America/New_York; end_local is exclusive next midnight."""
    tz = ZoneInfo(tz_name)
    start_parts = parse_date_ymd(start_ymd)
    end_parts = parse_date_ymd(end_ymd)
    if not (start_parts and end_parts):
        raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
    sy, sm, sd = start_parts
    ey, em, ed = end_parts
    start_local = datetime(sy, sm, sd, 0, 0, 0, tzinfo=tz)
    end_local = datetime(ey, em, ed, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def compute_share(numer: int, denom: int) -> float | None:
    """Ratio numer/denom. denom == 0 → JSON null (same as CAC when sales=0)."""
    if denom == 0:
        return None
    return numer / denom


def build_performance_kpis(*, opportunities_created: int, sales: int, sits: int) -> dict[str, Any]:
    return {
        "opportunities_created": int(opportunities_created),
        "sales": int(sales),
        "sits": int(sits),
        "opp_to_prelim": compute_share(int(sales), int(opportunities_created)),
        "demo_rate": compute_share(int(sits), int(opportunities_created)),
        "join_exists": INBOUND_FOUR_PIPELINE_JOIN_EXISTS,
        "join_field": INBOUND_FOUR_PIPELINE_JOIN_FIELD,
        "join_gap": INBOUND_FOUR_PIPELINE_JOIN_GAP,
        "join_gap_short": INBOUND_FOUR_PIPELINE_JOIN_GAP_SHORT,
        "formulas": {
            "opportunities_created": (
                "COUNT_DISTINCT(ghl_opportunities_v2.id) where createdAt in window "
                "(America/New_York) and pipeline in {Buffalo,Syracuse,Rochester,Virtual} "
                "excluding Inbound/Lead Locker"
            ),
            "opp_to_prelim": "inbound_cac.sales / opportunities_created",
            "demo_rate": "sits / opportunities_created",
            "sits": (
                "COUNT_DISTINCT four-pipeline ghl_opportunities_v2.id where "
                "dispositionValue==Sit and appointmentOccurredAt in window "
                "(exclude future vs now UTC; exclude rehash/sweeper)"
            ),
        },
    }


def _in_four_sales_pipelines(pipe_names: dict[str, str], raw_pipeline_id: Any) -> bool:
    pname = resolve_pipeline_name(pipe_names, raw_pipeline_id).strip().lower()
    if pname in EXCLUDED_PIPELINE_NAMES:
        return False
    return pname in FOUR_PIPELINE_NAMES


def count_four_pipeline_opportunities_created(
    db: firestore.Client,
    start_local: datetime,
    end_local: datetime,
) -> tuple[int, int]:
    """Four-pipeline Opportunities Created. Bounded createdAt range; no full stream."""
    start_bound = start_local.date().isoformat()
    end_bound = (end_local + timedelta(days=1)).date().isoformat()
    snaps = list(
        db.collection(OPP_COLLECTION)
        .where(CREATED_AT_FIELD, ">=", start_bound)
        .where(CREATED_AT_FIELD, "<", end_bound)
        .stream()
    )
    scanned = len(snaps)
    kept: list[dict[str, Any]] = []
    needed_pipeline_ids: list[str] = []
    for snap in snaps:
        opp = snap.to_dict() or {}
        created = parse_iso_dt(opp.get(CREATED_AT_FIELD))
        if not created:
            continue
        created_local = created.astimezone(start_local.tzinfo)
        if not (start_local <= created_local < end_local):
            continue
        oid = compact_str(opp.get("id") or snap.id)
        if not oid:
            continue
        opp["_oid"] = oid
        kept.append(opp)
        needed_pipeline_ids.extend(pipeline_id_keys(opp.get("pipelineId")))
    pipe_names = pipeline_name_lookup(db, needed_pipeline_ids)
    ids: set[str] = set()
    for opp in kept:
        if _in_four_sales_pipelines(pipe_names, opp.get("pipelineId")):
            ids.add(opp["_oid"])
    return len(ids), scanned


def as_occurred_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if hasattr(value, "to_datetime"):
        try:
            converted = value.to_datetime()
            if isinstance(converted, datetime):
                if converted.tzinfo is None:
                    return converted.replace(tzinfo=timezone.utc)
                return converted
        except Exception:
            return None
    return parse_iso_dt(value)


def count_four_pipeline_sits(
    db: firestore.Client,
    start_local: datetime,
    end_local: datetime,
    now_utc: datetime,
) -> tuple[int, int]:
    """Sits on the four sales pipelines. Bounded appointmentOccurredAt; no rehash/sweeper."""
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    if end_utc > now_utc:
        end_utc = now_utc
    snaps = list(
        db.collection(OPP_COLLECTION)
        .where(APPOINTMENT_OCCURRED_AT_FIELD, ">=", start_utc)
        .where(APPOINTMENT_OCCURRED_AT_FIELD, "<", end_utc)
        .stream()
    )
    scanned = len(snaps)
    kept: list[dict[str, Any]] = []
    needed_pipeline_ids: list[str] = []
    for snap in snaps:
        opp = snap.to_dict() or {}
        if opp.get(DISPOSITION_VALUE_FIELD) != SIT_DISPOSITION:
            continue
        occurred = as_occurred_dt(opp.get(APPOINTMENT_OCCURRED_AT_FIELD))
        if not occurred or occurred > now_utc:
            continue
        occurred_local = occurred.astimezone(start_local.tzinfo)
        if not (start_local <= occurred_local < end_local):
            continue
        oid = compact_str(opp.get("id") or snap.id)
        if not oid:
            continue
        opp["_oid"] = oid
        kept.append(opp)
        needed_pipeline_ids.extend(pipeline_id_keys(opp.get("pipelineId")))
    pipe_names = pipeline_name_lookup(db, needed_pipeline_ids)
    ids: set[str] = set()
    for opp in kept:
        if _in_four_sales_pipelines(pipe_names, opp.get("pipelineId")):
            ids.add(opp["_oid"])
    return len(ids), scanned


def parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = compact_str(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def month_window(year: int, month: int, tz_name: str) -> tuple[datetime, datetime, str, str]:
    tz = ZoneInfo(tz_name)
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def ytd_months(year: int, now: datetime) -> list[int]:
    """Calendar months in the YTD window for `year` in now's timezone."""
    if year < now.year:
        return list(range(1, 13))
    if year == now.year:
        return list(range(1, now.month + 1))
    return []


def ytd_window(year: int, tz_name: str, now: datetime) -> tuple[datetime, datetime, str, str]:
    """Jan 1 of `year` through exclusive end of the YTD window (America/New_York)."""
    tz = ZoneInfo(tz_name)
    start_local = datetime(year, 1, 1, 0, 0, 0, tzinfo=tz)
    months = ytd_months(year, now)
    if not months:
        end_local = start_local
    else:
        last_month = months[-1]
        _, end_local, _, _ = month_window(year, last_month, tz_name)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def created_at_in_window(created_at: Any, start_local: datetime, end_local: datetime) -> bool:
    created = parse_iso_dt(created_at)
    if not created:
        return False
    created_local = created.astimezone(start_local.tzinfo)
    return start_local <= created_local < end_local


def extract_sold_date_ymd(contact: dict[str, Any] | None) -> str | None:
    """Date-only Sold Date. Do not timezone-shift a ...Z wrapper (sales.py)."""
    if not isinstance(contact, dict):
        return None
    date_sold = None
    for cf in contact.get("customFields") or []:
        if isinstance(cf, dict) and cf.get("id") == SOLD_DATE_CUSTOM_FIELD_ID:
            date_sold = cf.get("value")
            break
    if isinstance(date_sold, str) and len(date_sold.strip()) >= 10:
        return date_sold.strip()[:10]
    return None


def sold_date_in_window(sold_date_ymd: str | None, start_local: datetime, end_local: datetime) -> bool:
    if not sold_date_ymd:
        return False
    start_date_str = start_local.date().isoformat()
    end_date_str = end_local.date().isoformat()
    return start_date_str <= sold_date_ymd < end_date_str


def classify_inbound_opp(opp: dict[str, Any], start_local: datetime, end_local: datetime) -> InboundOppRecord:
    return InboundOppRecord(
        bucket=bucket_title(opp.get(TITLE_FIELD)),
        in_window=created_at_in_window(opp.get(CREATED_AT_FIELD), start_local, end_local),
        refunded=is_refunded_stage(opp.get(STAGE_FIELD)),
        contact_id=compact_str(opp.get("contactId")),
    )


def raw_from_opp(opp: dict[str, Any], tzinfo) -> RawInboundOpp:
    created = parse_iso_dt(opp.get(CREATED_AT_FIELD))
    created_local = created.astimezone(tzinfo) if created else None
    return RawInboundOpp(
        bucket=bucket_title(opp.get(TITLE_FIELD)),
        created_local=created_local,
        refunded=is_refunded_stage(opp.get(STAGE_FIELD)),
        contact_id=compact_str(opp.get("contactId")),
    )


def records_for_window(raws: list[RawInboundOpp], start_local: datetime, end_local: datetime) -> list[InboundOppRecord]:
    records: list[InboundOppRecord] = []
    for raw in raws:
        in_window = bool(raw.created_local and start_local <= raw.created_local < end_local)
        records.append(
            InboundOppRecord(
                bucket=raw.bucket,
                in_window=in_window,
                refunded=raw.refunded,
                contact_id=raw.contact_id,
            )
        )
    return records


def spend_contact_ids(records: list[InboundOppRecord]) -> set[str]:
    ids: set[str] = set()
    for rec in records:
        if rec.bucket and rec.in_window and not rec.refunded and rec.contact_id:
            ids.add(rec.contact_id)
    return ids


def build_source_rows(
    records: list[InboundOppRecord],
    sold_contact_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        opp_count = 0
        refunded_excluded_count = 0
        spend_contacts: set[str] = set()
        for rec in records:
            if rec.bucket != source.label or not rec.in_window:
                continue
            if rec.refunded:
                refunded_excluded_count += 1
                continue
            opp_count += 1
            if rec.contact_id:
                spend_contacts.add(rec.contact_id)
        sales = len(spend_contacts & sold_contact_ids)
        spend = opp_count * source.unit_cost
        rows.append(
            attach_acquisition_costs(
                {
                    "source": source.label,
                    "unit_cost": source.unit_cost,
                    "opp_count": opp_count,
                    "refunded_excluded_count": refunded_excluded_count,
                    "spend": spend,
                    "sales": sales,
                    "cac": compute_cac(spend, sales),
                }
            )
        )
    return rows


def build_overall(rows: list[dict[str, Any]]) -> dict[str, Any]:
    spend = sum(int(row.get("spend") or 0) for row in rows)
    sales = sum(int(row.get("sales") or 0) for row in rows)
    opp_count = sum(int(row.get("opp_count") or 0) for row in rows)
    refunded_excluded_count = sum(int(row.get("refunded_excluded_count") or 0) for row in rows)
    return attach_acquisition_costs(
        {
            "source": "Overall",
            "opp_count": opp_count,
            "refunded_excluded_count": refunded_excluded_count,
            "spend": spend,
            "sales": sales,
            "cac": compute_cac(spend, sales),
        }
    )


def row_by_source(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("source") == name:
            return row
    return None


def build_chart(monthly: list[dict[str, Any]]) -> dict[str, Any]:
    """Chart-friendly arrays. Missing CAC/TAC is null, never 0."""
    months: list[str] = []
    labels: list[str] = []
    lead_locker_cac: list[float | None] = []
    solar_reviews_cac: list[float | None] = []
    lead_locker_tac: list[float | None] = []
    solar_reviews_tac: list[float | None] = []
    for item in monthly:
        months.append(item["label"])
        labels.append(item["month_label"])
        locker = row_by_source(item.get("rows") or [], "Lead Locker")
        reviews = row_by_source(item.get("rows") or [], "Solar Reviews")
        lead_locker_cac.append(None if locker is None else locker.get("cac"))
        solar_reviews_cac.append(None if reviews is None else reviews.get("cac"))
        lead_locker_tac.append(None if locker is None else locker.get("tac"))
        solar_reviews_tac.append(None if reviews is None else reviews.get("tac"))
    return {
        "months": months,
        "labels": labels,
        "lead_locker_cac": lead_locker_cac,
        "solar_reviews_cac": solar_reviews_cac,
        "lead_locker_tac": lead_locker_tac,
        "solar_reviews_tac": solar_reviews_tac,
    }


def load_contacts_by_ids(db: firestore.Client, contact_ids) -> dict[str, dict]:
    """Bounded ghl_contacts_v2 get_all for contactIds on the already-fetched opp set."""
    contacts_map: dict[str, dict] = {}
    needed: list[str] = []
    seen: set[str] = set()
    for raw in contact_ids:
        cid = compact_str(raw)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        needed.append(cid)
    refs = [db.collection(CONTACT_COLLECTION).document(cid) for cid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            cid = compact_str(d.get("id") or snap.id)
            if cid:
                contacts_map[cid] = d
            if snap.id:
                contacts_map[compact_str(snap.id)] = d
    for cid in needed:
        if cid in contacts_map:
            continue
        misses = list(db.collection(CONTACT_COLLECTION).where("id", "==", cid).limit(1).stream())
        if misses:
            contacts_map[cid] = misses[0].to_dict() or {}
    return contacts_map


def load_inbound_opps(db: firestore.Client) -> list[dict[str, Any]]:
    snaps = list(
        db.collection(OPP_COLLECTION).where("pipelineId", "==", INBOUND_PIPELINE_ID).stream()
    )
    return [snap.to_dict() or {} for snap in snaps]


def load_sold_stage_contact_ids(db: firestore.Client, inbound_contact_ids: set[str]) -> set[str]:
    """Sold/Sale Cancelled contacts that also appear on spend-scope inbound opps."""
    if not inbound_contact_ids:
        return set()
    contract = SalesMetricContract()
    stage_ids = list(contract.stage_ids)
    stage_set = set(contract.stage_ids)
    snaps = list(db.collection(OPP_COLLECTION).where(STAGE_FIELD, "in", stage_ids).stream())
    sold_ids: set[str] = set()
    for snap in snaps:
        opp = snap.to_dict() or {}
        if opp.get(STAGE_FIELD) not in stage_set:
            continue
        cid = compact_str(opp.get("contactId"))
        if cid and cid in inbound_contact_ids:
            sold_ids.add(cid)
    return sold_ids


def sold_contacts_in_window(
    contacts_map: dict[str, dict],
    candidate_ids: set[str],
    start_local: datetime,
    end_local: datetime,
) -> set[str]:
    matched: set[str] = set()
    for cid in candidate_ids:
        sold_date = extract_sold_date_ymd(contacts_map.get(cid))
        if sold_date_in_window(sold_date, start_local, end_local):
            matched.add(cid)
    return matched


def _window_bundle(
    raws: list[RawInboundOpp],
    contacts_map: dict[str, dict],
    sold_stage_ids: set[str],
    start_local: datetime,
    end_local: datetime,
) -> tuple[list[InboundOppRecord], list[dict[str, Any]], dict[str, Any], set[str]]:
    records = records_for_window(raws, start_local, end_local)
    sold_in_window = sold_contacts_in_window(contacts_map, sold_stage_ids, start_local, end_local)
    rows = build_source_rows(records, sold_in_window)
    return records, rows, build_overall(rows), sold_in_window


def assemble_inbound_cac(
    raws: list[RawInboundOpp],
    contacts_map: dict[str, dict],
    sold_stage_ids: set[str],
    *,
    year: int,
    month: int | None = None,
    tz: str = TIMEZONE_NAME,
    now: datetime | None = None,
    inbound_opps_scanned: int | None = None,
    start: str | None = None,
    end: str | None = None,
    opportunities_created: int = 0,
    sits: int = 0,
    created_scanned: int | None = None,
    sit_scanned: int | None = None,
) -> dict[str, Any]:
    tzinfo = ZoneInfo(tz)
    now = now or datetime.now(tzinfo)
    if start and end:
        start_local, end_local, start_iso, end_iso = date_range_window(start, end, tz)
        timeframe = "range"
    elif month is None:
        start_local, end_local, start_iso, end_iso = ytd_window(year, tz, now)
        timeframe = "ytd"
    else:
        start_local, end_local, start_iso, end_iso = month_window(year, month, tz)
        timeframe = "month"

    records, rows, overall, sold_in_window = _window_bundle(
        raws, contacts_map, sold_stage_ids, start_local, end_local
    )

    monthly: list[dict[str, Any]] = []
    if timeframe != "range":
        for chart_month in ytd_months(year, now):
            m_start, m_end, _, _ = month_window(year, chart_month, tz)
            _m_records, m_rows, m_overall, _ = _window_bundle(
                raws, contacts_map, sold_stage_ids, m_start, m_end
            )
            monthly.append(
                {
                    "year": year,
                    "month": chart_month,
                    "label": f"{year}-{chart_month:02d}",
                    "month_label": datetime(year, chart_month, 1).strftime("%b"),
                    "window_start_local": m_start.isoformat(),
                    "window_end_local": m_end.isoformat(),
                    "rows": m_rows,
                    "overall": m_overall,
                }
            )
    chart = build_chart(monthly)
    performance_kpis = build_performance_kpis(
        opportunities_created=opportunities_created,
        sales=int(overall.get("sales") or 0),
        sits=sits,
    )

    contract = SalesMetricContract()
    spend_ids = spend_contact_ids(records)
    return {
        "metric": "Inbound CAC",
        "unit": "usd_per_sale",
        "year": year,
        "month": month,
        "timeframe": timeframe,
        "timezone": tz,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "rows": rows,
        "overall": overall,
        "performance_kpis": performance_kpis,
        "chart": chart,
        "monthly": monthly,
        "count_method": (
            "spend = count(ghl_opportunities_v2 where pipelineId=Inbound/Lead Locker "
            "AND name title-bucket AND pipelineStageId!=Refunded AND createdAt in window) "
            "× unit_cost; sales = COUNT_DISTINCT(contactId) among those opps that also have "
            "a Sold/Sale Cancelled opp and Contact Sold Date in the same window; "
            "default window is YTD (calendar year America/New_York); "
            "setter_spend = sales × SETTER_UNIT_COST (500); "
            "TAC = (lead_spend + setter_spend) / sales (= CAC + 500 when sales>0); "
            "overall CAC/TAC = totals (null if sales=0); "
            "monthly chart CAC/TAC is null (gap) when that month's sales=0; "
            "performance_kpis.opportunities_created = four-pipeline Opportunities Created "
            "(no inbound title→four-pipeline join); "
            "opp_to_prelim = inbound_cac.sales / opportunities_created; "
            "demo_rate = four-pipeline sits / opportunities_created "
            "(null if opportunities_created=0)"
        ),
        "contract": {
            "base_collection": OPP_COLLECTION,
            "title_field": f"{OPP_COLLECTION}.{TITLE_FIELD}",
            "pipeline_name": INBOUND_PIPELINE_NAME,
            "pipeline_id": INBOUND_PIPELINE_ID,
            "refunded_stage_name": REFUNDED_STAGE_NAME,
            "refunded_stage_id": REFUNDED_STAGE_ID,
            "sale_stage_names": list(SALE_STAGE_NAMES),
            "included_stage_ids": list(contract.stage_ids),
            "sold_date_field": (
                f"{CONTACT_COLLECTION}.customFields[{SOLD_DATE_CUSTOM_FIELD_ID}] (ISO, date-only)"
            ),
            "sales_grain": f"COUNT_DISTINCT({OPP_COLLECTION}.contactId)",
            "setter_unit_cost": SETTER_UNIT_COST,
            "tac_formula": "(lead_spend + sales * setter_unit_cost) / sales",
            "charles_pipeline_name": "Inbound/3PL",
            "warehouse_pipeline_name": INBOUND_PIPELINE_NAME,
            "charles_sale_stage": "Won",
            "warehouse_sale_stages": "Sold / Sale Cancelled",
            "sources": [
                {"source": source.label, "unit_cost": source.unit_cost, "title_match": source.key}
                for source in SOURCES
            ],
            "performance_kpis": {
                "opportunities_created_pipelines": list(FOUR_PIPELINE_NAMES),
                "excluded_pipelines": list(EXCLUDED_PIPELINE_NAMES),
                "sit_field": f"{OPP_COLLECTION}.{APPOINTMENT_OCCURRED_AT_FIELD}",
                "sit_disposition": SIT_DISPOSITION,
                "inbound_to_four_pipeline_join_exists": INBOUND_FOUR_PIPELINE_JOIN_EXISTS,
                "inbound_to_four_pipeline_join_field": INBOUND_FOUR_PIPELINE_JOIN_FIELD,
                "inbound_to_four_pipeline_join_gap": INBOUND_FOUR_PIPELINE_JOIN_GAP,
            },
        },
        "debug": {
            "inbound_opps_scanned": inbound_opps_scanned if inbound_opps_scanned is not None else len(raws),
            "inbound_opps_in_window": sum(1 for rec in records if rec.in_window),
            "title_matched_in_window": sum(1 for rec in records if rec.in_window and rec.bucket),
            "spend_scope_contacts": len(spend_ids),
            "sold_stage_intersection_contacts": len(sold_stage_ids),
            "sold_date_in_window_contacts": len(sold_in_window),
            "join": f"{OPP_COLLECTION}.contactId -> {CONTACT_COLLECTION}.id",
            "four_pipeline_created_scanned": created_scanned,
            "four_pipeline_sit_scanned": sit_scanned,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def compute_inbound_cac(
    db: firestore.Client,
    *,
    year: int,
    month: int | None = None,
    tz: str = TIMEZONE_NAME,
    now: datetime | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    tzinfo = ZoneInfo(tz)
    now = now or datetime.now(tzinfo)
    inbound_opps = load_inbound_opps(db)
    raws = [raw_from_opp(opp, tzinfo) for opp in inbound_opps]

    if start and end:
        start_local, end_local, _, _ = date_range_window(start, end, tz)
    elif month is None:
        start_local, end_local, _, _ = ytd_window(year, tz, now)
    else:
        start_local, end_local, _, _ = month_window(year, month, tz)

    spend_ids = spend_contact_ids(records_for_window(raws, start_local, end_local))
    if not (start and end):
        for chart_month in ytd_months(year, now):
            m_start, m_end, _, _ = month_window(year, chart_month, tz)
            spend_ids |= spend_contact_ids(records_for_window(raws, m_start, m_end))

    sold_stage_ids = load_sold_stage_contact_ids(db, spend_ids)
    contacts_map = load_contacts_by_ids(db, sold_stage_ids)
    now_utc = now.astimezone(timezone.utc)
    opportunities_created, created_scanned = count_four_pipeline_opportunities_created(
        db, start_local, end_local
    )
    sits, sit_scanned = count_four_pipeline_sits(db, start_local, end_local, now_utc)
    return assemble_inbound_cac(
        raws,
        contacts_map,
        sold_stage_ids,
        year=year,
        month=month,
        tz=tz,
        now=now,
        inbound_opps_scanned=len(inbound_opps),
        start=start,
        end=end,
        opportunities_created=opportunities_created,
        sits=sits,
        created_scanned=created_scanned,
        sit_scanned=sit_scanned,
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo(TIMEZONE_NAME))
            year, month = parse_inbound_cac_params(qs, now)
            start, end = parse_optional_range(qs)
            tz = TIMEZONE_NAME
            payload = compute_inbound_cac(
                get_db(), year=year, month=month, tz=tz, now=now, start=start, end=end
            )
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
