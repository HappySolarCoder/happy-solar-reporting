# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sweeper_credit

Month-to-date sweeper/rehash credit for one Sweeper/Rehash Last Name.

- appointments_set: distinct opportunities created in the month (America/New_York, any pipeline,
  opportunities_created with pipeline_scope=all) whose contact Sweeper/Rehash Last Name
  (field HWfjOp8MvE6soxBAL75f, opportunity fallback) equals ``last_name``.
- sales: the locked Sales grain from sales.py (Sold or Sale Cancelled stage, contact Sold Date in
  the month, distinct contact) where that same field equals ``last_name``.

Reads only. Does not change either locked metric.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sweeper_rehash_attribution import SWEEPER_REHASH_LAST_NAME_FIELD_ID, sweeper_rehash_last_name


def same_name(value: Any, wanted: str) -> bool:
    want = " ".join(str(wanted or "").split()).casefold()
    return bool(want) and " ".join(str(value or "").split()).casefold() == want


def appointment_rows(created_payload: dict[str, Any], last_name: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in created_payload.get("sample_rows") or []:
        if not isinstance(row, dict) or not same_name(row.get("sweeperRehashLastName"), last_name):
            continue
        opp_id = str(row.get("opportunityId") or "")
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        rows.append(
            {
                "opportunityId": opp_id,
                "contactId": row.get("contactId"),
                "pipeline": row.get("pipeline"),
                "createdAt": row.get("createdAt"),
            }
        )
    return rows


def compute_sweeper_credit(db, *, year: int, month: int, last_name: str) -> dict[str, Any]:
    from opportunities_created import MetricContract, compute
    from sales import SalesMetricContract, compute_sales

    created = compute(db, MetricContract(), year=year, month=month, pipeline_scope="all")
    appts = appointment_rows(created, last_name)

    sales_rows: dict[str, dict[str, Any]] = {}

    def on_sale(*, opp, contact, contact_id, sold_date, salesperson):
        if not same_name(sweeper_rehash_last_name(contact, opp), last_name):
            return
        key = str(contact_id or "")
        if not key or key in sales_rows:
            return
        sales_rows[key] = {
            "contactId": key,
            "opportunityId": (opp or {}).get("id"),
            "soldDate": sold_date,
        }

    sales = compute_sales(db, SalesMetricContract(), year=year, month=month, tz="America/New_York", on_sale=on_sale)
    return {
        "metric": "Sweeper credit",
        "last_name": last_name,
        "year": year,
        "month": month,
        "timezone": "America/New_York",
        "window_start_local": sales.get("window_start_local"),
        "window_end_local": sales.get("window_end_local"),
        "appointments_set": len(appts),
        "sales": len(sales_rows),
        "appointment_rows": appts,
        "sale_rows": sorted(sales_rows.values(), key=lambda r: str(r.get("soldDate") or "")),
        "contract": {
            "field": f"ghl_contacts_v2.customFields[{SWEEPER_REHASH_LAST_NAME_FIELD_ID}] then the same id on the opportunity",
            "appointments_set": "COUNT_DISTINCT opportunity id from opportunities_created pipeline_scope=all, createdAt in month",
            "sales": "Locked Sales grain (sales.py) filtered by the field",
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            now = datetime.utcnow()
            year = int(qs.get("year", [str(now.year)])[0])
            month = int(qs.get("month", [str(now.month)])[0])
            last_name = " ".join((qs.get("last_name", [""])[0] or "").split())[:60]
            if not last_name or not (1 <= month <= 12):
                raise ValueError("last_name and a valid month are required")
            from sales import get_db

            payload = compute_sweeper_credit(get_db(), year=year, month=month, last_name=last_name)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(body)
        except ValueError as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            body = b"ERROR: sweeper credit unavailable"
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
