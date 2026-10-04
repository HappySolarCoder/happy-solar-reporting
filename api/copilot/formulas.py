# -*- coding: utf-8 -*-
"""Observed company-overview math. These are not approved definitions."""

from __future__ import annotations

from typing import Any, Mapping

# Copied from api/company_overview.py card alias lists. A test asserts the
# source file still contains these arrays.
OBSERVED_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "doors": ("Doors",),
    "self_gen": ("Self Gen", "self gen", "selfgen", "SelfGen"),
    "phones": ("Phones", "Virtual"),
    "inbound": ("Inbound",),
    "3pl": ("3PL",),
}

SOURCE_LABELS = {
    "doors": "Doors",
    "self_gen": "Self Gen",
    "phones": "Phones",
    "inbound": "Inbound",
    "3pl": "3PL",
}

ALLOWED_SOURCE_IDS = frozenset(OBSERVED_SOURCE_ALIASES)
ALLOWED_METRIC_IDS = frozenset(
    {"sales", "opps_created", "opps_ran", "demo_rate", "opp2prelim"}
)


def sum_aliases(counts: Mapping[str, Any] | None, aliases: tuple[str, ...] | list[str]) -> int:
    total = 0
    for key in aliases:
        try:
            total += int((counts or {}).get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def unmapped_labels(counts: Mapping[str, Any] | None) -> list[str]:
    known = {alias for aliases in OBSERVED_SOURCE_ALIASES.values() for alias in aliases}
    labels = []
    for key, value in (counts or {}).items():
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            continue
        if count > 0 and key not in known:
            labels.append(str(key))
    return sorted(labels)


def opp2prelim_percent(sales: int | None, ran: int | None) -> float | None:
    """Company overview card: null when Ran is 0, so the UI shows an em dash.

    company_trends uses 0.0 when Ran is 0. That conflict is unresolved.
    """
    if sales is None or ran is None:
        return None
    if ran == 0:
        return None
    return round((sales / ran) * 100, 1)


def demo_rate_percent(sits: int | None, ran: int | None) -> float | None:
    """Company overview card uses 0 when Ran is 0. Distinguish that from a true zero rate.

    Returns None when either input is missing. Returns 0.0 when Ran is 0, matching
    the card (`ran > 0 ? sit/ran*100 : 0`), and sets the caller-facing flag separately.
    """
    if sits is None or ran is None:
        return None
    if ran == 0:
        return 0.0
    return round((sits / ran) * 100, 1)


def percent_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return round(((current - baseline) / baseline) * 100, 1)


def absolute_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 1)
