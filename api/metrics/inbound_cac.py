# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/inbound_cac

Inbound lead-source CAC for Happy Solar.

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

Metric per row:
1. Scope inbound opps: pipelineId == Inbound/Lead Locker AND title match
   AND pipelineStageId != Refunded AND createdAt in the NY month window.
2. Spend = count(those opps) × unit cost.
3. Sales = distinct contactId among those spend-scope opps that also appear
   on at least one opportunity currently in the 8 Sold/Sale Cancelled stage
   IDs AND whose Contact Sold Date (P9oBjgbZjJdeE0OkBj9T) falls in the same
   America/New_York month (date-only; do not timezone-shift a ...Z wrapper).
   Missing Sold Date is excluded — same as sales.py.
4. CAC = spend / sales. sales == 0 → JSON null, never 0.

Queries:
- Inbound: where pipelineId == 7nSEgeoBYXZiIS7x41Jy (≈1261 historical docs;
  month filter in memory).
- Sales: pipelineStageId IN the 8 locked stage IDs, then get_all those
  intersection contacts only.
- No full-stream of ghl_opportunities_v2 or ghl_contacts_v2.

Params:
- year, month (America/New_York; defaults to current NY month)
- format=json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sales import SalesMetricContract, get_db

TIMEZONE_NAME = "America/New_York"
OPP_COLLECTION = "ghl_opportunities_v2"
CONTACT_COLLECTION = "ghl_contacts_v2"
CREATED_AT_FIELD = "createdAt"
STAGE_FIELD = "pipelineStageId"
TITLE_FIELD = "name"

INBOUND_PIPELINE_NAME = "Inbound/Lead Locker"
INBOUND_PIPELINE_ID = "7nSEgeoBYXZiIS7x41Jy"
REFUNDED_STAGE_NAME = "Refunded"
REFUNDED_STAGE_ID = "5bb63eb2-2208-481e-a0b9-f82ece3c030a"
SOLD_DATE_CUSTOM_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"

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
    return rows


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


def compute_inbound_cac(
    db: firestore.Client,
    *,
    year: int,
    month: int,
    tz: str = TIMEZONE_NAME,
) -> dict[str, Any]:
    start_local, end_local, start_iso, end_iso = month_window(year, month, tz)
    inbound_opps = load_inbound_opps(db)
    records = [classify_inbound_opp(opp, start_local, end_local) for opp in inbound_opps]

    spend_contact_ids: set[str] = set()
    for rec in records:
        if rec.bucket and rec.in_window and not rec.refunded and rec.contact_id:
            spend_contact_ids.add(rec.contact_id)

    sold_stage_ids = load_sold_stage_contact_ids(db, spend_contact_ids)
    contacts_map = load_contacts_by_ids(db, sold_stage_ids)
    sold_in_window = sold_contacts_in_window(contacts_map, sold_stage_ids, start_local, end_local)
    rows = build_source_rows(records, sold_in_window)

    contract = SalesMetricContract()
    return {
        "metric": "Inbound CAC",
        "unit": "usd_per_sale",
        "year": year,
        "month": month,
        "timezone": tz,
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "rows": rows,
        "count_method": (
            "spend = count(ghl_opportunities_v2 where pipelineId=Inbound/Lead Locker "
            "AND name title-bucket AND pipelineStageId!=Refunded AND createdAt in NY month) "
            "× unit_cost; sales = COUNT_DISTINCT(contactId) among those opps that also have "
            "a Sold/Sale Cancelled opp and Contact Sold Date in the same NY month"
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
            "charles_pipeline_name": "Inbound/3PL",
            "warehouse_pipeline_name": INBOUND_PIPELINE_NAME,
            "charles_sale_stage": "Won",
            "warehouse_sale_stages": "Sold / Sale Cancelled",
            "sources": [
                {"source": source.label, "unit_cost": source.unit_cost, "title_match": source.key}
                for source in SOURCES
            ],
        },
        "debug": {
            "inbound_opps_scanned": len(inbound_opps),
            "inbound_opps_in_window": sum(1 for rec in records if rec.in_window),
            "title_matched_in_window": sum(1 for rec in records if rec.in_window and rec.bucket),
            "spend_scope_contacts": len(spend_contact_ids),
            "sold_stage_intersection_contacts": len(sold_stage_ids),
            "sold_date_in_window_contacts": len(sold_in_window),
            "join": f"{OPP_COLLECTION}.contactId -> {CONTACT_COLLECTION}.id",
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(ZoneInfo(TIMEZONE_NAME))
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            tz = TIMEZONE_NAME
            payload = compute_inbound_cac(get_db(), year=year, month=month, tz=tz)
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
