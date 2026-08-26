# -*- coding: utf-8 -*-
"""24 Hawkstone Way standing lock (Evan 2026-08-26). Reason test_address."""
from __future__ import annotations
import re
from typing import Any
from urllib.parse import unquote
def compact_str(value):
    return " ".join(str(value or "").split())
TEST_ADDRESS_STREET = "24 hawkstone way"
TEST_ADDRESS_LOCK_DATE = "2026-08-26"
TEST_ADDRESS_PATTERN = re.compile(r"(?<!\d)24 hawkstone way")

def _normalize_address_haystack(value: Any) -> str:
    """Collapse whitespace/punctuation and URL encoding for address matching."""
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
    """True for 24 Hawkstone Way; 124 Hawkstone Way is not a match."""
    haystack = _normalize_address_haystack(value)
    if not haystack:
        return False
    return bool(TEST_ADDRESS_PATTERN.search(haystack))


def row_has_test_address(row):
    row = row or {}
    keys = ("address", "estimate_address", "customEvent:address", "custom_event_address", "page_location", "page_path")
    return any(is_test_address(row.get(k)) for k in keys)

def install(module):
    if getattr(module, "_hawkstone_installed", False):
        return module
    orig_reason = module.exclusion_reason
    orig_summarize = module.summarize_ga4_event_rows
    def exclusion_reason(**kwargs):
        extra = {k: kwargs.pop(k, None) for k in ("address", "estimate_address", "custom_event_address", "page_path")}
        reason = orig_reason(**kwargs)
        if reason:
            return reason
        for candidate in (extra["address"], extra["estimate_address"], extra["custom_event_address"], kwargs.get("page_location"), extra["page_path"]):
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
        filters.update({"test_address": TEST_ADDRESS_STREET, "test_address_lock_date": TEST_ADDRESS_LOCK_DATE, "test_address_grain": "event"})
        out["filters"] = filters
        return out
    module.exclusion_reason = exclusion_reason
    module.summarize_ga4_event_rows = summarize_ga4_event_rows
    module.is_test_address = is_test_address
    module._hawkstone_installed = True
    return module
