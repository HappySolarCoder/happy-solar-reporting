# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/sales_list

JSON grain for the Sales List dashboard (Essential / Momentum / 3rd Roc / All).
Reuses compute_essential_sales → compute_sales. Does not invent a new sales grain,
does not change locked stage IDs or the Sold Date field, and does not write to GHL.

Dashboard overlays (notes, email, phone) live in Firestore named DB happy-solar,
collection sales_list_notes_v1, keyed by contactId. GHL Appointment Notes stay
read-only. Email/phone fall back to ghl_contacts_v2 until an overlay is saved.
"""

from __future__ import annotations

import calendar
import json
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from essential_sales import ESSENTIAL_COLUMNS, compute_essential_sales
from sales import SalesMetricContract, get_db

NOTES_COLLECTION = "sales_list_notes_v1"
ALL_TIME_START = "2018-01-01"
DEFAULT_TZ = "America/New_York"
TIMEFRAMES: tuple[str, ...] = ("all", "month", "quarter")
OVERLAY_UNSET = object()
SEARCH_FIELDS: tuple[str, ...] = (
    "client",
    "address",
    "email",
    "phone",
    "salesperson",
    "installer",
    "contactId",
    "notes",
    "dashboardNote",
)

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

# Date sold stays first. Evan: client name 2nd, installer 3rd. Remaining
# Essential-tab fields keep their prior relative order, plus dashboard notes.
_ESSENTIAL_LABELS = {key: label for key, label in ESSENTIAL_COLUMNS}
SALES_LIST_COLUMN_KEYS: tuple[str, ...] = (
    "submissionDate",
    "client",
    "installer",
    "financeType",
    "salesperson",
    "wc",
    "asi",
    "esco",
    "cdg",
    "size",
    "phone",
    "email",
    "address",
    "notes",
    "dashboardNote",
    "retentionRep",
    "systemChecks",
    "qp",
)
SALES_LIST_COLUMNS: tuple[tuple[str, str], ...] = tuple(
    (key, "Dashboard notes" if key == "dashboardNote" else _ESSENTIAL_LABELS[key])
    for key in SALES_LIST_COLUMN_KEYS
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


def parse_timeframe(value: Any) -> str:
    text = compact_text(value).lower().replace("_", "-")
    if text in {"month"}:
        return "month"
    if text in {"quarter", "q"}:
        return "quarter"
    if text in {"range", "custom"}:
        return "range"
    return "all"


def current_quarter(month: int) -> int:
    return ((int(month) - 1) // 3) + 1


def parse_quarter(value: Any, *, default: int | None = None) -> int:
    raw = compact_text(value).upper().replace("QTR", "Q")
    if raw in {"1", "Q1"}:
        return 1
    if raw in {"2", "Q2"}:
        return 2
    if raw in {"3", "Q3"}:
        return 3
    if raw in {"4", "Q4"}:
        return 4
    if default is not None:
        return default
    return 1


def quarter_date_bounds(year: int, quarter: int) -> tuple[str, str]:
    q = parse_quarter(quarter, default=1)
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(int(year), end_month)[1]
    return f"{int(year):04d}-{start_month:02d}-01", f"{int(year):04d}-{end_month:02d}-{last_day:02d}"


def all_time_date_bounds(now: datetime | None = None, tz: str = DEFAULT_TZ) -> tuple[str, str]:
    """Wide sold-date window: 2018-01-01 through now+1 day (end inclusive in compute_sales)."""
    zone = ZoneInfo(tz)
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    end = (current.date() + timedelta(days=1)).isoformat()
    return ALL_TIME_START, end


def resolve_sales_list_window(
    *,
    timeframe: str = "all",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    start: str | None = None,
    end: str | None = None,
    tz: str = DEFAULT_TZ,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve timeframe to compute_sales start/end (or year/month for Month mode)."""
    zone = ZoneInfo(tz)
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    tf = parse_timeframe(timeframe)
    resolved_year = int(year) if year else current.year
    resolved_month = int(month) if month else current.month
    resolved_quarter = parse_quarter(quarter, default=current_quarter(current.month))
    custom_start = compact_text(start) or None
    custom_end = compact_text(end) or None

    if custom_start and custom_end:
        out_tf = tf if tf in TIMEFRAMES else "range"
        if tf == "range":
            out_tf = "range"
        return {
            "timeframe": out_tf,
            "year": resolved_year,
            "month": resolved_month,
            "quarter": resolved_quarter,
            "start": custom_start,
            "end": custom_end,
        }
    if tf == "month":
        return {
            "timeframe": "month",
            "year": resolved_year,
            "month": resolved_month,
            "quarter": current_quarter(resolved_month),
            "start": None,
            "end": None,
        }
    if tf == "quarter":
        q_start, q_end = quarter_date_bounds(resolved_year, resolved_quarter)
        return {
            "timeframe": "quarter",
            "year": resolved_year,
            "month": (resolved_quarter - 1) * 3 + 1,
            "quarter": resolved_quarter,
            "start": q_start,
            "end": q_end,
        }
    all_start, all_end = all_time_date_bounds(current, tz)
    return {
        "timeframe": "all",
        "year": current.year,
        "month": current.month,
        "quarter": current_quarter(current.month),
        "start": all_start,
        "end": all_end,
    }


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


def overlay_text(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_overlays(notes_by_contact: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """Accept legacy {contactId: note} maps or full {contactId: {note, email, phone}} overlays."""
    overlays: dict[str, dict[str, str]] = {}
    for raw_id, value in (notes_by_contact or {}).items():
        contact_id = compact_text(raw_id)
        if not contact_id:
            continue
        if isinstance(value, dict):
            overlay: dict[str, str] = {"note": overlay_text(value.get("note"))}
            if "email" in value:
                overlay["email"] = overlay_text(value.get("email"))
            if "phone" in value:
                overlay["phone"] = overlay_text(value.get("phone"))
            overlays[contact_id] = overlay
        else:
            overlays[contact_id] = {"note": overlay_text(value)}
    return overlays


def merge_dashboard_notes(
    rows: Iterable[dict[str, Any]],
    notes_by_contact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return merge_contact_overlays(rows, notes_by_contact)


def merge_contact_overlays(
    rows: Iterable[dict[str, Any]],
    notes_by_contact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    stored = normalize_overlays(notes_by_contact)
    merged: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        contact_id = compact_text(item.get("contactId"))
        overlay = stored.get(contact_id) or {}
        item["dashboardNote"] = overlay.get("note", "")
        if "email" in overlay:
            item["email"] = overlay["email"]
        if "phone" in overlay:
            item["phone"] = overlay["phone"]
        merged.append(item)
    return merged


def _overlay_from_snap(snap: Any) -> tuple[str, dict[str, str]] | None:
    if snap is None or not getattr(snap, "exists", False):
        return None
    data = snap.to_dict() if hasattr(snap, "to_dict") else None
    data = data if isinstance(data, dict) else {}
    contact_id = compact_text(data.get("contactId") or getattr(snap, "id", ""))
    if not contact_id:
        return None
    overlay: dict[str, str] = {"note": overlay_text(data.get("note"))}
    if "email" in data:
        overlay["email"] = overlay_text(data.get("email"))
    if "phone" in data:
        overlay["phone"] = overlay_text(data.get("phone"))
    return contact_id, overlay


def load_overlays_by_contact_ids(db: Any, contact_ids: Iterable[Any]) -> dict[str, dict[str, str]]:
    ids = [compact_text(cid) for cid in contact_ids]
    unique_ids = [cid for cid in dict.fromkeys(ids) if cid]
    overlays: dict[str, dict[str, str]] = {}
    if not unique_ids or db is None:
        return overlays
    refs = [db.collection(NOTES_COLLECTION).document(cid) for cid in unique_ids]
    snaps: list[Any]
    if hasattr(db, "get_all"):
        snaps = []
        for idx in range(0, len(refs), 100):
            snaps.extend(list(db.get_all(refs[idx : idx + 100])))
    else:
        snaps = [ref.get() for ref in refs]
    for snap in snaps:
        parsed = _overlay_from_snap(snap)
        if parsed is None:
            continue
        contact_id, overlay = parsed
        overlays[contact_id] = overlay
    return overlays


def load_notes_by_contact_ids(db: Any, contact_ids: Iterable[Any]) -> dict[str, str]:
    overlays = load_overlays_by_contact_ids(db, contact_ids)
    return {cid: overlay.get("note", "") for cid, overlay in overlays.items()}


def upsert_sales_list_overlay(
    db: Any,
    *,
    contact_id: Any,
    note: Any = OVERLAY_UNSET,
    email: Any = OVERLAY_UNSET,
    phone: Any = OVERLAY_UNSET,
) -> dict[str, str]:
    cid = compact_text(contact_id)
    if not cid:
        raise ValueError("contactId is required")
    if note is OVERLAY_UNSET and email is OVERLAY_UNSET and phone is OVERLAY_UNSET:
        raise ValueError("note, email, or phone is required")
    payload: dict[str, str] = {
        "contactId": cid,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if note is not OVERLAY_UNSET:
        payload["note"] = overlay_text(note)
    if email is not OVERLAY_UNSET:
        payload["email"] = compact_text(email)
    if phone is not OVERLAY_UNSET:
        payload["phone"] = compact_text(phone)
    db.collection(NOTES_COLLECTION).document(cid).set(payload, merge=True)
    return dict(payload)


def upsert_sales_list_note(db: Any, *, contact_id: Any, note: Any) -> dict[str, str]:
    return upsert_sales_list_overlay(db, contact_id=contact_id, note=note)


def digits_only(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def row_matches_search(row: dict[str, Any] | None, query: Any) -> bool:
    q = compact_text(query).casefold()
    if not q:
        return True
    item = row if isinstance(row, dict) else {}
    for field in SEARCH_FIELDS:
        if q in compact_text(item.get(field)).casefold():
            return True
    q_digits = digits_only(query)
    if len(q_digits) >= 4 and q_digits in digits_only(item.get("phone")):
        return True
    return False


def search_sales_list_rows(rows: Iterable[dict[str, Any]], query: Any) -> list[dict[str, Any]]:
    if not compact_text(query):
        return list(rows)
    return [row for row in rows if row_matches_search(row, query)]


def parse_sort_order(value: Any, *, default: str = "asc") -> str:
    text = compact_text(value).lower()
    if text in {"desc", "descending", "newest", "newest-first", "newest_first"}:
        return "desc"
    if text in {"asc", "ascending", "oldest", "oldest-first", "oldest_first"}:
        return "asc"
    return "asc" if default == "asc" else "desc"


def sort_sales_list_rows(
    rows: Iterable[dict[str, Any]],
    *,
    order: str = "asc",
) -> list[dict[str, Any]]:
    descending = parse_sort_order(order) == "desc"

    def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            compact_text(row.get("submissionDate")),
            compact_text(row.get("client")).casefold(),
            compact_text(row.get("contactId")),
        )

    return sorted(rows, key=sort_key, reverse=descending)


def compute_sales_list(
    db,
    contract: SalesMetricContract,
    *,
    tz: str = DEFAULT_TZ,
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    timeframe: str = "all",
    start: str | None = None,
    end: str | None = None,
    installer: str = "all",
    salesperson: str = "",
    query: str = "",
    sort_order: str = "asc",
    notes_by_contact: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    installer_key = parse_installer_filter(installer)
    salesperson_key = parse_salesperson_filter(salesperson)
    search_query = compact_text(query)
    order_key = parse_sort_order(sort_order)
    window = resolve_sales_list_window(
        timeframe=timeframe,
        year=year,
        month=month,
        quarter=quarter,
        start=start,
        end=end,
        tz=tz,
        now=now,
    )

    base = compute_essential_sales(
        db,
        contract,
        year=window["year"],
        month=window["month"],
        tz=tz,
        start=window["start"],
        end=window["end"],
    )
    base_rows = list(base.get("rows") or [])
    stored_overlays = (
        normalize_overlays(notes_by_contact)
        if notes_by_contact is not None
        else load_overlays_by_contact_ids(db, (row.get("contactId") for row in base_rows))
    )
    rows_with_notes = merge_contact_overlays(base_rows, stored_overlays)
    salespeople = unique_salespeople(rows_with_notes)
    filtered = apply_sales_list_filters(
        rows_with_notes,
        installer=installer_key,
        salesperson=salesperson_key,
    )
    tab_filtered_count = len(filtered)
    if search_query:
        filtered = search_sales_list_rows(filtered, search_query)
    filtered = sort_sales_list_rows(filtered, order=order_key)
    locked_result = base.get("result")
    sales_count = tab_filtered_count
    unfiltered = installer_key == "all" and not salesperson_key
    return {
        "metric": "Sales List",
        "unit": "count",
        "timeframe": window["timeframe"],
        "year": base.get("year"),
        "month": base.get("month"),
        "quarter": window["quarter"] if window["timeframe"] == "quarter" else None,
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
            "timeframe": window["timeframe"],
            "start": window["start"],
            "end": window["end"],
            "q": search_query,
            "sort": "submissionDate",
            "order": order_key,
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
            "timeframe": window["timeframe"],
            "resolved_start": window["start"],
            "resolved_end": window["end"],
            "search_query": search_query,
            "sort": "submissionDate",
            "order": order_key,
            "notes_collection": NOTES_COLLECTION,
            "notes_loaded": len(stored_overlays),
        },
        "contract": {
            **(base.get("contract") or {}),
            "layout": "Yadmada Job Tracker columns: date sold, client, installer, then remaining Essential fields plus Dashboard notes",
            "installer_filter": None if installer_key == "all" else installer_key,
            "salesperson_filter": salesperson_key or None,
            "dashboard_notes": {
                "collection": NOTES_COLLECTION,
                "database": "happy-solar",
                "key": "contactId",
                "ghl_writeback": False,
                "fields": ["note", "email", "phone"],
            },
            "fields": {
                **((base.get("contract") or {}).get("fields") or {}),
                "notes": ((base.get("contract") or {}).get("fields") or {}).get(
                    "notes",
                    "ghl_contacts_v2.customFields[Q2NUde7fCBQWp7GU76ca] Appointment Notes only",
                ),
                "dashboardNote": f"firestore {NOTES_COLLECTION}/{{contactId}}.note (dashboard only; never GHL)",
                "email": (
                    "ghl_contacts_v2.email, overlaid by "
                    f"firestore {NOTES_COLLECTION}/{{contactId}}.email when set"
                ),
                "phone": (
                    "ghl_contacts_v2.phone, overlaid by "
                    f"firestore {NOTES_COLLECTION}/{{contactId}}.phone when set"
                ),
            },
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            tz = DEFAULT_TZ
            now = datetime.now(ZoneInfo(tz))
            timeframe = parse_timeframe(qs.get("timeframe", ["all"])[0])
            year_raw = compact_text(qs.get("year", [""])[0])
            month_raw = compact_text(qs.get("month", [""])[0])
            year = int(year_raw) if year_raw else None
            month = int(month_raw) if month_raw else None
            quarter = parse_quarter(qs.get("quarter", [""])[0], default=None) if compact_text(qs.get("quarter", [""])[0]) else None
            start = compact_text(qs.get("start", [""])[0]) or None
            end = compact_text(qs.get("end", [""])[0]) or None
            installer = parse_installer_filter(qs.get("installer", ["all"])[0])
            salesperson = parse_salesperson_filter(qs.get("salesperson", [""])[0])
            query = compact_text(qs.get("q", [""])[0])
            sort_order = parse_sort_order(qs.get("order", ["asc"])[0])

            contract = SalesMetricContract()
            payload = compute_sales_list(
                get_db(),
                contract,
                tz=tz,
                year=year,
                month=month,
                quarter=quarter,
                timeframe=timeframe,
                start=start,
                end=end,
                installer=installer,
                salesperson=salesperson,
                query=query,
                sort_order=sort_order,
                now=now,
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
