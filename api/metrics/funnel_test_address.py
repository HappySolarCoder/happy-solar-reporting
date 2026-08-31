# -*- coding: utf-8 -*-
"""Website-funnel test traffic lock (Evan 2026-08-26 / 2026-08-30). Reason test_address.

Event-row matcher is defense in depth. Named fills the rollup can see
(web_funnel_named_fills_v1 / leads@) are the path that zeros a day when
GA4 rows have no address/name/email.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

def compact_str(value):
    return " ".join(str(value or "").split())

TEST_ADDRESS_STREET = "24 hawkstone way"
TEST_ADDRESS_LOCK_DATE = "2026-08-30"
TEST_ADDRESS_PATTERN = re.compile(r"(?<!\d)24 hawkstone way")
STONEBRIDGE_PATTERN = re.compile(r"(?<!\d)313 (e|east) stonebridge (dr|drive)")
TEST_NAME_PATTERNS = (
    re.compile(r"(?<![a-z0-9])test test(?![a-z0-9])"),
    re.compile(r"(?<![a-z0-9])evan day(?![a-z0-9])"),
)
TEST_EMAILS = frozenset({"adchday@gmail.com", "evanrday23@gmail.com"})
NAMED_FILLS_COLLECTION = "web_funnel_named_fills_v1"
NAMED_FILLS_QUERY_LIMIT = 50
ROW_KEYS = (
    "address",
    "estimate_address",
    "customEvent:address",
    "custom_event_address",
    "page_location",
    "page_path",
    "name",
    "estimate_name",
    "email",
    "user_email",
    "contact_email",
    "estimate_email",
    "customEvent:email",
    "customEvent:name",
)
FILL_KEYS = ("name", "email", "address", "estimate_address")

def _normalize_haystack(value: Any) -> str:
    """Collapse whitespace/punctuation and URL encoding for address/name matching."""
    text = compact_str(value)
    if not text:
        return ""
    try:
        text = unquote(text.replace("+", " "))
    except Exception:
        text = text.replace("+", " ")
    cleaned = []
    for ch in text:
        cleaned.append(ch if ch.isalnum() or ch.isspace() else " ")
    return compact_str("".join(cleaned)).casefold()


def is_test_address(value: Any) -> bool:
    """True for locked test addresses, names, or emails. 124 Hawkstone Way is not a match."""
    raw = compact_str(value).casefold()
    if any(email in raw for email in TEST_EMAILS):
        return True
    haystack = _normalize_haystack(value)
    if not haystack:
        return False
    if TEST_ADDRESS_PATTERN.search(haystack):
        return True
    if STONEBRIDGE_PATTERN.search(haystack):
        return True
    if any(pat.search(haystack) for pat in TEST_NAME_PATTERNS):
        return True
    return False


def row_has_test_address(row):
    row = row or {}
    return any(is_test_address(row.get(k)) for k in ROW_KEYS)


def fill_is_test(fill: dict[str, Any] | None) -> bool:
    fill = fill or {}
    return any(is_test_address(fill.get(k)) for k in FILL_KEYS)


def fetch_named_fills(db: Any, date_ymd: str) -> list[dict[str, Any]]:
    """Bounded date query. Not a collection stream. Empty on missing/broken db."""
    if db is None or not date_ymd:
        return []
    try:
        col = db.collection(NAMED_FILLS_COLLECTION)
        if not hasattr(col, "where"):
            return []
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = col.where(filter=FieldFilter("date", "==", date_ymd))
        except Exception:
            query = col.where("date", "==", date_ymd)
        if hasattr(query, "limit"):
            query = query.limit(NAMED_FILLS_QUERY_LIMIT)
        if hasattr(query, "stream"):
            snaps = list(query.stream())
        elif hasattr(query, "get"):
            snaps = list(query.get())
        else:
            return []
    except Exception:
        return []
    fills: list[dict[str, Any]] = []
    for snap in snaps:
        data = snap.to_dict() if hasattr(snap, "to_dict") else None
        if isinstance(data, dict) and data:
            fills.append(data)
        elif isinstance(snap, dict):
            fills.append(snap)
    return fills[:NAMED_FILLS_QUERY_LIMIT]


def apply_named_fill_test_day(ga4: dict[str, Any] | None, fills: list[dict[str, Any]] | None) -> dict[str, Any]:
    """If that ET day's named fills are all on the test list, zero estimate_submit / completed_forms."""
    out = dict(ga4 or {})
    dropped = dict(out.get("dropped") or {})
    filters = dict(out.get("filters") or {})
    fills = list(fills or [])
    filters["named_fills_collection"] = NAMED_FILLS_COLLECTION
    filters["named_fills_count"] = len(fills)
    filters["named_fill_zeroed"] = False
    if not fills:
        out["filters"] = filters
        out["dropped"] = dropped
        return out
    all_test = all(fill_is_test(fill) for fill in fills)
    filters["named_fills_all_test"] = all_test
    if not all_test:
        out["filters"] = filters
        out["dropped"] = dropped
        return out
    try:
        prev = int(out.get("estimate_submit") or 0)
    except Exception:
        prev = 0
    dropped["test_address"] = dropped.get("test_address", 0) + prev
    out["estimate_submit"] = 0
    try:
        wix = int(out.get("wix_form_submits") or 0)
    except Exception:
        wix = 0
    out["completed_forms"] = wix
    filters["named_fill_zeroed"] = True
    filters["named_fill_zeroed_reason"] = "all_named_fills_are_test"
    out["filters"] = filters
    out["dropped"] = dropped
    return out

def install(module):
    if getattr(module, "_hawkstone_installed", False):
        return module
    orig_reason = module.exclusion_reason
    orig_summarize = module.summarize_ga4_event_rows
    orig_rollup = module.rollup_day
    extra_keys = (
        "address",
        "estimate_address",
        "custom_event_address",
        "page_path",
        "name",
        "estimate_name",
        "email",
        "user_email",
        "contact_email",
        "estimate_email",
    )
    def exclusion_reason(**kwargs):
        extra = {k: kwargs.pop(k, None) for k in extra_keys}
        reason = orig_reason(**kwargs)
        if reason:
            return reason
        candidates = list(extra.values()) + [kwargs.get("page_location")]
        for candidate in candidates:
            if is_test_address(candidate):
                return "test_address"
        return None
    def summarize_ga4_event_rows(rows):
        kept, extra_dropped = [], 0
        for row in rows or []:
            if row_has_test_address(row):
                try:
                    extra_dropped += int(row.get("count") or 0)
                except Exception:
                    pass
                continue
            kept.append(row)
        out = orig_summarize(kept)
        dropped = dict(out.get("dropped") or {})
        dropped["test_address"] = dropped.get("test_address", 0) + extra_dropped
        out["dropped"] = dropped
        filters = dict(out.get("filters") or {})
        filters.update({
            "test_address": TEST_ADDRESS_STREET,
            "test_address_lock_date": TEST_ADDRESS_LOCK_DATE,
            "test_address_grain": "event",
            "test_traffic": [
                "24 Hawkstone Way",
                "313 E Stonebridge Dr / 313 East Stonebridge Drive, Gilbert AZ",
                "Test Test",
                "Evan Day",
                "adchday@gmail.com",
                "evanrday23@gmail.com",
            ],
        })
        out["filters"] = filters
        return out
    def rollup_day(db, date_ymd=None):
        date_key = date_ymd or module.yesterday_ny_date()
        if not module.parse_date_ymd(date_key):
            raise ValueError("Invalid date; expected YYYY-MM-DD")
        ingest_info = {"attempted": False, "wrote": 0, "reason": "gmail_not_configured"}
        try:
            import importlib.util
            import sys
            ingest_path = Path(__file__).resolve().parent / "funnel_named_fills_ingest.py"
            cached = sys.modules.get("hs_funnel_named_fills_ingest")
            if cached is not None:
                ingest_mod = cached
            else:
                ispec = importlib.util.spec_from_file_location(
                    "hs_funnel_named_fills_ingest", ingest_path
                )
                ingest_mod = importlib.util.module_from_spec(ispec)
                sys.modules["hs_funnel_named_fills_ingest"] = ingest_mod
                ispec.loader.exec_module(ingest_mod)
            if ingest_mod.gmail_configured():
                ingest_info = ingest_mod.ingest_leads_at(db, date_ymd=date_key)
        except Exception:
            ingest_info = {"attempted": True, "wrote": 0, "reason": "ingest_failed"}
        ga4 = module.fetch_ga4_event_counts(date_key)
        fills = fetch_named_fills(db, date_key)
        ga4 = apply_named_fill_test_day(ga4, fills)
        doc = module.build_daily_doc(date_key, ga4)
        db.collection(module.DAILY_COLLECTION).document(date_key).set(doc, merge=True)
        return {
            "wrote": True,
            "collection": module.DAILY_COLLECTION,
            "id": date_key,
            "doc": doc,
            "named_fills": len(fills),
            "ingest": ingest_info,
        }
    module.exclusion_reason = exclusion_reason
    module.summarize_ga4_event_rows = summarize_ga4_event_rows
    module.rollup_day = rollup_day
    module.is_test_address = is_test_address
    module.fetch_named_fills = fetch_named_fills
    module.apply_named_fill_test_day = apply_named_fill_test_day
    module.NAMED_FILLS_COLLECTION = NAMED_FILLS_COLLECTION
    module._orig_rollup_day = orig_rollup
    module._hawkstone_installed = True
    return module
