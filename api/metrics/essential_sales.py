# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/essential_sales

JSON grain for the Essential tab layout (Yadmada Job Tracker).
Reuses the locked Sales metric from sales.py — same distinct contactId
among the 8 Sold/Sale Cancelled stage IDs, Sold Date date-only, NY window.

Does not filter Installer=Essential. Does not fill System Checks from
Submission Checklist. WC / ESCO / CDG / Retention Rep / System Checks / QP
are left empty.
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

from sales import SalesMetricContract, compute_sales, get_db

FINANCE_TYPE_FIELD_ID = "gaUfeEjWzA0jOmyuIUKg"
CLIENT_FIELD_ID = "mgGFiaHdEFf6lwiKu513"
ASI_FIELD_ID = "kD6CYjEawVwDSmyjurbT"
SIZE_FIELD_ID = "MVpb9cXvTFTdUVjqybQl"
NOTES_FIELD_ID = "Q2NUde7fCBQWp7GU76ca"  # Appointment Notes only

ESSENTIAL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("submissionDate", "Submission Date"),
    ("financeType", "Finance type"),
    ("client", "Cient"),
    ("salesperson", "Salesperson"),
    ("wc", "WC"),
    ("asi", "ASI"),
    ("esco", "ESCO"),
    ("cdg", "CDG"),
    ("size", "Size"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("notes", "Notes"),
    ("retentionRep", "Retention Rep"),
    ("systemChecks", "System Checks"),
    ("qp", "QP"),
)


def custom_field_raw(contact: dict[str, Any] | None, field_id: str) -> Any:
    if not isinstance(contact, dict) or not field_id:
        return None
    for cf in contact.get("customFields") or []:
        if not isinstance(cf, dict):
            continue
        if str(cf.get("id") or "") != field_id:
            continue
        val = cf.get("value")
        if val in (None, ""):
            val = cf.get("fieldValueString")
        return val
    return None


def raw_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def client_display(contact: dict[str, Any] | None, custom_value: Any) -> str:
    custom = raw_text(custom_value).strip()
    if custom:
        return custom
    if not isinstance(contact, dict):
        return ""
    last = " ".join(str(contact.get("lastName") or "").strip().split())
    first = " ".join(str(contact.get("firstName") or "").strip().split())
    if last and first:
        return f"{last}, {first}"
    return last or first


def build_essential_row(
    *,
    contact: dict[str, Any] | None,
    contact_id: str,
    sold_date: str,
    salesperson: str,
) -> dict[str, Any]:
    contact = contact if isinstance(contact, dict) else {}
    return {
        "contactId": contact_id,
        "submissionDate": sold_date or "",
        "financeType": raw_text(custom_field_raw(contact, FINANCE_TYPE_FIELD_ID)).strip(),
        "client": client_display(contact, custom_field_raw(contact, CLIENT_FIELD_ID)),
        "salesperson": salesperson or "",
        "wc": "",
        "asi": raw_text(custom_field_raw(contact, ASI_FIELD_ID)).strip(),
        "esco": "",
        "cdg": "",
        "size": raw_text(custom_field_raw(contact, SIZE_FIELD_ID)),
        "phone": raw_text(contact.get("phone")).strip(),
        "email": raw_text(contact.get("email")).strip(),
        "notes": raw_text(custom_field_raw(contact, NOTES_FIELD_ID)).strip(),
        "retentionRep": "",
        "systemChecks": "",
        "qp": "",
    }


def compute_essential_sales(
    db,
    contract: SalesMetricContract,
    *,
    year: int,
    month: int,
    tz: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    def on_sale(*, opp, contact, contact_id, sold_date, salesperson):
        rows.append(
            build_essential_row(
                contact=contact,
                contact_id=str(contact_id or ""),
                sold_date=str(sold_date or ""),
                salesperson=str(salesperson or ""),
            )
        )

    sales = compute_sales(
        db,
        contract,
        year=year,
        month=month,
        tz=tz,
        start=start,
        end=end,
        on_sale=on_sale,
    )
    rows.sort(key=lambda r: (r.get("submissionDate") or "", r.get("client") or "", r.get("contactId") or ""))
    return {
        "metric": "Essential Sales",
        "unit": "count",
        "year": sales.get("year"),
        "month": sales.get("month"),
        "timezone": sales.get("timezone"),
        "window_start_local": sales.get("window_start_local"),
        "window_end_local": sales.get("window_end_local"),
        "result": sales.get("result"),
        "count_method": sales.get("count_method"),
        "columns": [{"key": key, "label": label} for key, label in ESSENTIAL_COLUMNS],
        "rows": rows,
        "debug": {
            "sales_result": sales.get("result"),
            "row_count": len(rows),
            "opportunities_scanned": (sales.get("debug") or {}).get("opportunities_scanned"),
            "distinct_contact_ids": (sales.get("debug") or {}).get("distinct_contact_ids"),
            "owner_sum": sum(((sales.get("breakdowns") or {}).get("sales_by_owner") or {}).values()),
            "join": (sales.get("debug") or {}).get("join"),
        },
        "contract": {
            **(sales.get("contract") or {}),
            "layout": "Yadmada Job Tracker Essential tab columns A-O",
            "installer_filter": None,
            "system_checks_source": None,
            "empty_columns": ["wc", "esco", "cdg", "retentionRep", "systemChecks", "qp"],
            "fields": {
                "submissionDate": f"ghl_contacts_v2.customFields[{contract.sold_date_custom_field_id}] date-only",
                "financeType": f"ghl_contacts_v2.customFields[{FINANCE_TYPE_FIELD_ID}]",
                "client": f"ghl_contacts_v2.customFields[{CLIENT_FIELD_ID}] else lastName, firstName",
                "salesperson": "ghl_opportunities_v2.assignedTo via roster_people_v1 then bounded ghl_users_v2",
                "asi": f"ghl_contacts_v2.customFields[{ASI_FIELD_ID}]",
                "size": f"ghl_contacts_v2.customFields[{SIZE_FIELD_ID}] raw",
                "phone": "ghl_contacts_v2.phone",
                "email": "ghl_contacts_v2.email",
                "notes": f"ghl_contacts_v2.customFields[{NOTES_FIELD_ID}] Appointment Notes only",
            },
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
            start = (qs.get("start", [""])[0] or "").strip() or None
            end = (qs.get("end", [""])[0] or "").strip() or None
            tz = "America/New_York"

            contract = SalesMetricContract()
            payload = compute_essential_sales(
                get_db(),
                contract,
                year=year,
                month=month,
                tz=tz,
                start=start,
                end=end,
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
