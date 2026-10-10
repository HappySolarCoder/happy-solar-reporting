# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/channel_goals

Company Overview lead-gen channel goals and the actuals that are not in
company_snapshot.

CHANNEL_GOALS is the single store for these monthly targets (Evan, 2026-10-09).
Leads are only tracked for 3PL and Inbound.

Actuals served here:
- Sweeper/Rehash: rows whose contact "Sweeper/Rehash Last Name" (opportunity
  fallback) is filled with any name. Appointments = opportunities_created
  (pipeline_scope=all) rows, sales = locked Sales grain, ran / demos = demo_rate
  rows. Same field reader as sweeper_credit.
- Leads: new opportunities in the Inbound/Lead Locker pipeline created in the
  month (America/New_York). Inbound = contact Lead Gen Source "Inbound" or
  "Facebook Quick Form". 3PL = the remaining NR (non-refunded) Lead Locker /
  Solar Reviews title-bucket leads from inbound_cac.

Doors, Self Gen, 3PL and Inbound sales / appointments / ran / demos stay on
company_snapshot lead-source breakdowns. Reads only.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sweeper_rehash_attribution import is_blank_last_name, sweeper_rehash_last_name

NY = ZoneInfo("America/New_York")

# Monthly targets. Percent goals are whole percents. None = not tracked.
CHANNEL_GOALS: dict[str, dict[str, Any]] = {
    "Doors": {"sales": 34, "opp2prelim_pct": 23, "appointments": 148, "leads": None, "demo_rate_pct": 45, "demos": 67},
    "Self Gen": {"sales": 17, "opp2prelim_pct": 30, "appointments": 57, "leads": None, "demo_rate_pct": 50, "demos": 28},
    "3PL": {"sales": 7, "opp2prelim_pct": 25, "appointments": 28, "leads": 108, "demo_rate_pct": 50, "demos": 14},
    "Inbound": {"sales": 3, "opp2prelim_pct": 30, "appointments": 10, "leads": 30, "demo_rate_pct": 60, "demos": 6},
    "Sweeper/Rehash": {"sales": 7, "opp2prelim_pct": 50, "appointments": 14, "leads": None, "demo_rate_pct": 50, "demos": 10},
}
LEADS_CHANNELS = ("3PL", "Inbound")
INBOUND_LEAD_SOURCES = frozenset({"inbound", "facebook quick form"})


def filled(value: Any) -> bool:
    text = " ".join(str(value or "").split())
    return bool(text) and not is_blank_last_name(text)


def sweeper_created(created_payload: dict[str, Any]) -> int:
    ids = {
        str(row.get("opportunityId") or "")
        for row in created_payload.get("sample_rows") or []
        if isinstance(row, dict) and filled(row.get("sweeperRehashLastName"))
    }
    ids.discard("")
    return len(ids)


def sweeper_ran(demo_payload: dict[str, Any]) -> tuple[int, int]:
    ran = demos = 0
    seen: set[str] = set()
    for row in demo_payload.get("rows") or []:
        if not isinstance(row, dict) or not filled(row.get("sweeperRehashLastName")):
            continue
        key = str(row.get("opportunityId") or "")
        if key in seen:
            continue
        seen.add(key)
        ran += 1
        if row.get("disposition") == "Sit":
            demos += 1
    return ran, demos


def split_leads(raws: list, sources: dict[str, str], start_local, end_local) -> dict[str, int]:
    """raws: inbound_cac RawInboundOpp. sources: opportunity id -> lead gen source."""
    inbound: set[str] = set()
    three_pl: set[str] = set()
    for raw in raws:
        if not (raw.created_local and start_local <= raw.created_local < end_local):
            continue
        oid = raw.opportunity_id
        if not oid:
            continue
        if str(sources.get(oid) or "").strip().casefold() in INBOUND_LEAD_SOURCES:
            inbound.add(oid)
        elif raw.bucket and not raw.refunded:
            three_pl.add(oid)
    return {"Inbound": len(inbound), "3PL": len(three_pl)}


def compute_leads(db, start_local, end_local) -> dict[str, int]:
    import inbound_cac as ic

    opps = ic.load_inbound_opps(db)
    raws, contact_of = [], {}
    for opp in opps:
        raw = ic.raw_from_opp(opp, NY)
        if raw.created_local and start_local <= raw.created_local < end_local:
            raws.append(raw)
            contact_of[raw.opportunity_id] = raw.contact_id
    contacts = ic.load_contacts_by_ids(db, list(contact_of.values()))
    sources = {
        oid: ic.normalize_lead_gen_source(
            ic.contact_custom_field(contacts.get(cid) or {}, ic.LEAD_GEN_SOURCE_CONTACT_CF_ID)
        )
        for oid, cid in contact_of.items()
    }
    return split_leads(raws, sources, start_local, end_local)


def compute_channel_goals(db, *, year: int, month: int) -> dict[str, Any]:
    import demo_rate
    from opportunities_created import MetricContract, compute, month_window
    from sales import SalesMetricContract, compute_sales

    start_local, end_local, _, _ = month_window(year, month, "America/New_York")
    sold: set[str] = set()

    def on_sale(*, opp, contact, contact_id, sold_date, salesperson):
        if contact_id and filled(sweeper_rehash_last_name(contact, opp)):
            sold.add(str(contact_id))

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_created = ex.submit(compute, db, MetricContract(), year=year, month=month, pipeline_scope="all")
        f_demo = ex.submit(demo_rate.build_payload, db, year, month, {})
        f_sales = ex.submit(compute_sales, db, SalesMetricContract(), year=year, month=month, tz="America/New_York", on_sale=on_sale)
        f_leads = ex.submit(compute_leads, db, start_local, end_local)
        created = f_created.result()
        ran, demos = sweeper_ran(f_demo.result())
        f_sales.result()
        try:
            leads: dict[str, Any] = f_leads.result()
        except Exception:
            leads = {"Inbound": None, "3PL": None}

    return {
        "metric": "channel_goals",
        "year": year,
        "month": month,
        "timezone": "America/New_York",
        "goals": CHANNEL_GOALS,
        "leads_channels": list(LEADS_CHANNELS),
        "leads": leads,
        "sweeper": {"appointments": sweeper_created(created), "ran": ran, "demos": demos, "sales": len(sold)},
        "contract": {
            "sweeper": "Sweeper/Rehash Last Name filled (any name), contact then opportunity",
            "leads_inbound": "Inbound/Lead Locker pipeline opps created in month, Lead Gen Source Inbound or Facebook Quick Form",
            "leads_3pl": "Remaining non-refunded Lead Locker / Solar Reviews title-bucket opps created in month",
            "demo_rate": "demos / appointments ran",
            "opp2prelim": "sales / appointments ran",
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.now(NY)
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            if not (1 <= month <= 12 and 2020 <= year <= 2100):
                raise ValueError("valid year and month are required")
            from sales import get_db

            body = json.dumps(compute_channel_goals(get_db(), year=year, month=month)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(body)
        except ValueError as e:
            self._err(400, "ERROR: " + str(e))
        except Exception:
            self._err(500, "ERROR: channel goals unavailable")

    def _err(self, code: int, text: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))
