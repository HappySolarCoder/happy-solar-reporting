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
    """Blank when Ran is 0. Cards and the trend chart both use that rule.

    A positive denominator with zero sales is 0%, which is different from N/A.
    """
    if sales is None or ran is None:
        return None
    if ran == 0:
        return None
    return round((sales / ran) * 100, 1)


# Company target for Demo Rate. Approval replaces the whole terminology entry,
# so this does not live on the seed.
DEMO_RATE_TARGET_PERCENT = 50.0


def demo_rate_percent(demos: int | None, ran: int | None) -> float | None:
    """N/A when Ran is 0. A real zero rate requires a positive denominator."""
    if demos is None or ran is None:
        return None
    if ran == 0:
        return None
    return round((demos / ran) * 100, 1)


def percent_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return round(((current - baseline) / baseline) * 100, 1)


def absolute_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 1)
