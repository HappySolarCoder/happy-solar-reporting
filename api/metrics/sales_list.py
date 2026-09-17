# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sales_list

JSON grain for the Sales List dashboard (Essential / Momentum / 3rd Roc / All).
Reuses compute_essential_sales → compute_sales. Does not invent a new sales grain,
does not change locked stage IDs or the Sold Date field, and does not write to GHL.

Dashboard notes live in Firestore named DB happy-solar, collection
sales_list_notes_v1, keyed by contactId. GHL Appointment Notes stay read-only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from essential_sales import ESSENTIAL_COLUMNS, compute_essential_sales
from sales import SalesMetricContract, get_db

NOTES_COLLECTION = "sales_list_notes_v1"

INSTALLER_TABS: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("essential", "Essential"),
    ("momentum", "Momentum"),
    ("3rd_roc", "3rd Roc"),
)

INSTALLER_ALIASES: dict[str, frozenset[str]] = {
    "essential": frozenset(
        {
            "essential",
            "essential solar",
            "essential energy",
            "essentials",
            "essential slr",
            "happy essential",
        }
    ),
    "momentum": frozenset(
        {
            "momentum",
            "momentum solar",
            "momentum energy",
            "momentum slr",
        }
    ),
    "3rd_roc": frozenset(
        {
            "3rd roc",
            "3rdroc",
            "3rd-roc",
            "3rd rock",
            "3rdrock",
            "3rd-rock",
            "third roc",
            "third rock",
            "3rd rochester",
            "third rochester",
            "3rdroc solar",
            "3rd roc solar",
        }
    ),
}

SALES_LIST_COLUMNS: tuple[tuple[str, str], ...] = tuple(
    list(ESSENTIAL_COLUMNS[:13])
    + [("dashboardNote", "Dashboard notes")]
    + list(ESSENTIAL_COLUMNS[13:])
)


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_installer_tab(value: Any) -> str | None:
    """Map a raw GHL installer string onto Essential / Momentum / 3rd Roc."""
    text = compact_text(value).lower()
    if not text:
        return None
    slug = text.replace("-", " ").replace("_", " ")
    slug = " ".join(slug.split())
    collapsed = slug.replace(" ", "")
    for key, aliases in INSTALLER_ALIASES.items():
        if text in aliases or slug in aliases or collapsed in {a.replace(" ", "") for a in aliases}:
            return key
    if ("3rd" in slug or "third" in slug) and ("roc" in slug or "rock" in slug or "rochester" in slug):
        return "3rd_roc"
    if "momentum" in slug:
        return "momentum"
    if "essential" in slug:
        return "essential"
    return None


def parse_installer_filter(value: Any) -> str:
    raw = compact_text(value)
    if not raw or raw.lower() == "all":
        return "all"
    key = normalize_installer_tab(raw)
    return key or "all"


def parse_salesperson_filter(value: Any) -> str:
    text = compact_text(value)
    if not text or text.lower() == "all":
        return ""
    return text


def installer_matches(raw_installer: Any, installer_filter: str) -> bool:
    wanted = parse_installer_filter(installer_filter)
    if wanted == "all":
        return True
    return normalize_installer_tab(raw_installer) == wanted


def salesperson_matches(raw_salesperson: Any, salesperson_filter: str) -> bool:
    wanted = parse_salesperson_filter(salesperson_filter)
    if not wanted:
        return True
    return compact_text(raw_salesperson).casefold() == wanted.casefold()


def apply_sales_list_filters(
    rows: Iterable[dict[str, Any]],
    *,
    installer: str = "all",
    salesperson: str = "",
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if installer_matches(row.get("installer"), installer)
        and salesperson_matches(row.get("salesperson"), salesperson)
    ]


def unique_salespeople(rows: Iterable[dict[str, Any]]) -> list[str]:
    names: dict[str, str] = {}
    for row in rows:
        name = compact_text(row.get("salesperson"))
        if not name:
            continue
        key = name.casefold()
        current = names.get(key)
        if current is None or (current == current.lower() and name != name.lower()):
            names[key] = name
    return [names[key] for key in sorted(names)]


def merge_dashboard_notes(
    rows: Iterable[dict[str, Any]],
    notes_by_contact: dict[str, str] | None,
) -> list[dict[str, Any]]:
    stored = notes_by_contact or {}
    merged: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        contact_id = compact_text(item.get("contactId"))
        note = stored.get(contact_id, "")
        item["dashboardNote"] = "" if note is None else str(note)
        merged.append(item)
    return merged


def load_notes_by_contact_ids(db: Any, contact_ids: Iterable[Any]) -> dict[str, str]:
    ids = [compact_text(cid) for cid in contact_ids]
    unique_ids = [cid for cid in dict.fromkeys(ids) if cid]
    notes: dict[str, str] = {}
    if not unique_ids or db is None:
        return notes
    refs = [db.collection(NOTES_COLLECTION).document(cid) for cid in unique_ids]
    snaps: list[Any]
    if hasattr(db, "get_all"):
        snaps = []
        for idx in range(0, len(refs), 100):
            snaps.extend(list(db.get_all(refs[idx : idx + 100])))
    else:
        snaps = [ref.get() for ref in refs]
    for snap in snaps:
        if snap is None or not getattr(snap, "exists", False):
            continue
        data = snap.to_dict() if hasattr(snap, "to_dict") else None
        data = data if isinstance(data, dict) else {}
        contact_id = compact_text(data.get("contactId") or getattr(snap, "id", ""))
        if not contact_id:
            continue
        note = data.get("note")
        notes[contact_id] = "" if note is None else str(note)
    return notes


def upsert_sales_list_note(db: Any, *, contact_id: Any, note: Any) -> dict[str, str]:
    cid = compact_text(contact_id)
    if not cid:
        raise ValueError("contactId is required")
    text = "" if note is None else str(note)
    payload = {
        "contactId": cid,
        "note": text,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    db.collection(NOTES_COLLECTION).document(cid).set(payload, merge=True)
    return {"contactId": cid, "note": text, "updated_at": payload["updated_at"]}


def compute_sales_list(
    db,
    contract: SalesMetricContract,
    *,
    year: int,
    month: int,
    tz: str,
    start: str | None = None,
    end: str | None = None,
    installer: str = "all",
    salesperson: str = "",
    notes_by_contact: dict[str, str] | None = None,
) -> dict[str, Any]:
    installer_key = parse_installer_filter(installer)
    salesperson_key = parse_salesperson_filter(salesperson)

    base = compute_essential_sales(
        db,
        contract,
        year=year,
        month=month,
        tz=tz,
        start=start,
        end=end,
    )
    base_rows = list(base.get("rows") or [])
    stored_notes = (
        notes_by_contact
        if notes_by_contact is not None
        else load_notes_by_contact_ids(db, (row.get("contactId") for row in base_rows))
    )
    rows_with_notes = merge_dashboard_notes(base_rows, stored_notes)
    salespeople = unique_salespeople(rows_with_notes)
    filtered = apply_sales_list_filters(
        rows_with_notes,
        installer=installer_key,
        salesperson=salesperson_key,
    )
    locked_result = base.get("result")
    sales_count = len(filtered)
    unfiltered = installer_key == "all" and not salesperson_key
    return {
        "metric": "Sales List",
        "unit": "count",
        "year": base.get("year"),
        "month": base.get("month"),
        "timezone": base.get("timezone"),
        "window_start_local": base.get("window_start_local"),
        "window_end_local": base.get("window_end_local"),
        "result": locked_result if unfiltered else sales_count,
        "sales_count": sales_count,
        "filtered_row_count": len(filtered),
        "count_method": base.get("count_method"),
        "filters": {
            "installer": installer_key,
            "salesperson": salesperson_key,
        },
        "installer_tabs": [{"key": key, "label": label} for key, label in INSTALLER_TABS],
        "salespeople": salespeople,
        "columns": [{"key": key, "label": label} for key, label in SALES_LIST_COLUMNS],
        "rows": filtered,
        "debug": {
            **(base.get("debug") or {}),
            "sales_result": locked_result,
            "unfiltered_row_count": len(rows_with_notes),
            "filtered_row_count": len(filtered),
            "installer_filter": installer_key,
            "salesperson_filter": salesperson_key,
            "notes_collection": NOTES_COLLECTION,
            "notes_loaded": len(stored_notes),
        },
        "contract": {
            **(base.get("contract") or {}),
            "layout": "Yadmada Job Tracker Essential/Momentum/3rd Roc columns plus Dashboard notes",
            "installer_filter": None if installer_key == "all" else installer_key,
            "salesperson_filter": salesperson_key or None,
            "dashboard_notes": {
                "collection": NOTES_COLLECTION,
                "database": "happy-solar",
                "key": "contactId",
                "ghl_writeback": False,
            },
            "fields": {
                **((base.get("contract") or {}).get("fields") or {}),
                "notes": ((base.get("contract") or {}).get("fields") or {}).get(
                    "notes",
                    "ghl_contacts_v2.customFields[Q2NUde7fCBQWp7GU76ca] Appointment Notes only",
                ),
                "dashboardNote": f"firestore {NOTES_COLLECTION}/{{contactId}}.note (dashboard only; never GHL)",
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
            installer = parse_installer_filter(qs.get("installer", ["all"])[0])
            salesperson = parse_salesperson_filter(qs.get("salesperson", [""])[0])
            tz = "America/New_York"

            contract = SalesMetricContract()
            payload = compute_sales_list(
                get_db(),
                contract,
                year=year,
                month=month,
                tz=tz,
                start=start,
                end=end,
                installer=installer,
                salesperson=salesperson,
            )
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
