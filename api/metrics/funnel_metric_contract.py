# -*- coding: utf-8 -*-
"""Website Funnel written contract: one source of truth per metric.

Evan lock: funnel numbers must be absolutely accurate.
Website Funnel is a separate metric family — do not merge into Sales /
Opportunities / Sold Date.

A named fill is not a GA4 visit. Do not backfill visits_wny from named
fills. Do not treat by_page.calculator as WNY visits or completed_forms.

Live chi (re-curled 2026-09-02 ET, do not invent):
- 2026-08-31 control: visits_wny=9, starts=3, completed_forms=2,
  named_fills_live_count=2, by_page.calculator all 0, ga4=ok.
- 2026-09-01 tag-miss: visits_wny=0, starts=0, completed_forms=2
  (Art Sieczkarek, Richard Wooliver — real WNY leads@).
  sessions/visits_total=38 (not WNY host). by_page.calculator all 0.
- 2026-08-28: completed_forms=0 (tests zeroed).
- Window 2026-08-21–2026-09-02 daily docs: visits_wny=64, starts=15,
  completed_forms=4 (Pyrce+Goodrich 8/31, Sieczkarek+Wooliver 9/01).
  Not 0, not 6.

Tag-miss is a data flag (GA4 recorded 0 sessions on wny.happyslr.com
while live named fills landed). Not a Designer task in this repo.
wny.happyslr.com HTML has gtag G-V02RZFR4SZ; GTM-K6LW45DT is happyslr.com.
Do not change the calculator form or site HTML from this reporting repo.
"""

from __future__ import annotations

from typing import Any

# Locked test traffic. Tests stay out of completed_forms / estimate_submit.
TEST_TRAFFIC_EXCLUSIONS: tuple[str, ...] = (
    "24 Hawkstone Way",
    "313 E Stonebridge Dr / 313 East Stonebridge Drive Gilbert AZ",
    "Test Test",
    "Evan Day",
    "adchday@gmail.com",
    "evanrday23@gmail.com",
)

NAMED_FILLS_COLLECTION = "web_funnel_named_fills_v1"
NAMED_FILLS_INGEST = "leads@"
WNY_HOST = "wny.happyslr.com"
VISITS_WNY_HOSTS_FILTER = "filters.visits_wny_hosts"

METRIC_SOURCES: dict[str, dict[str, Any]] = {
    "completed_forms": {
        "source": "live_named_wny_submits",
        "store": NAMED_FILLS_COLLECTION,
        "ingest": NAMED_FILLS_INGEST,
        "equals": "live named WNY submits (server / web_funnel_named_fills_v1 / leads@)",
        "tests_out": list(TEST_TRAFFIC_EXCLUSIONS),
        "not": (
            "ga4_visit",
            "by_page.calculator",
            "by_page.calculator.completed_forms",
            "test_named_fill",
        ),
        "note": "A named fill is NOT a GA4 visit.",
    },
    "estimate_submit": {
        "source": "live_named_wny_submits",
        "store": NAMED_FILLS_COLLECTION,
        "ingest": NAMED_FILLS_INGEST,
        "same_as": "completed_forms",
        "equals": "live named WNY submits (server / web_funnel_named_fills_v1 / leads@)",
        "tests_out": list(TEST_TRAFFIC_EXCLUSIONS),
        "not": ("ga4_visit", "by_page.calculator", "test_named_fill"),
    },
    "visits_wny": {
        "source": "ga4_sessions",
        "hosts": (WNY_HOST,),
        "filter": VISITS_WNY_HOSTS_FILTER,
        "equals": "GA4 sessions on host wny.happyslr.com (filters.visits_wny_hosts)",
        "event": "page_view",
        "not": (
            "by_page.calculator",
            "by_page.calculator.sessions",
            "named_fill",
            "named_fills_live_count",
            "completed_forms",
        ),
        "do_not_backfill_from": "named_fills",
    },
    "starts": {
        "source": "ga4_event",
        "event": "estimate_start",
        "equals": "existing GA4 event contract (estimate_start)",
        "not": ("named_fill", "named_fills_live_count", "completed_forms"),
    },
    "address_complete": {
        "source": "ga4_event",
        "event": "estimate_address_complete",
        "equals": "existing GA4 event contract (estimate_address_complete)",
        "not": ("named_fill", "named_fills_live_count"),
    },
    "bill_complete": {
        "source": "ga4_event",
        "event": "estimate_bill_complete",
        "equals": "existing GA4 event contract (estimate_bill_complete)",
        "not": ("named_fill", "named_fills_live_count"),
    },
    "visits_total": {
        "source": "ga4_sessions",
        "hosts": ("happyslr.com", "www.happyslr.com"),
        "filter": "filters.visits_total_hosts",
        "equals": "GA4 on happyslr.com / www as already filtered",
        "distinct_from": "visits_wny",
        "event": "page_view",
    },
    "sessions": {
        "source": "ga4_sessions",
        "same_as": "visits_total",
        "equals": "GA4 on happyslr.com / www as already filtered — same as visits_total",
        "distinct_from": "visits_wny",
        "not": ("visits_wny", "by_page.calculator.sessions"),
    },
}

TAG_MISS_RULE: dict[str, Any] = {
    "when": "live named fills > 0 and visits_wny == 0 (GA4 ok, host wny.happyslr.com)",
    "flag": "tag_missed",
    "alias": "tag_miss",
    "meaning": (
        "Tag missed: GA4 recorded 0 sessions on wny.happyslr.com while live "
        "named WNY fills landed. This is a data flag, not a 2-from-0 conversion."
    ),
    "rates": {
        "fills_over_visits_wny": None,
        "fills_over_starts": None,
    },
    "never": ("2/0", "invented_visits_wny", "backfill_visits_wny_from_named_fills"),
    "example_day": "2026-09-01",
    "control_day": "2026-08-31",
}


def is_tag_missed(visits_wny: Any, live_named_fills_count: Any) -> bool:
    """True when live named fills landed and GA4 recorded 0 WNY host sessions.

    Missing/not_configured visits_wny is not a tag-miss (that is an unready
    source). Do not invent visits. Do not treat fills as visits.
    """
    try:
        fills = int(live_named_fills_count or 0)
    except (TypeError, ValueError):
        fills = 0
    if fills <= 0:
        return False
    if visits_wny is None or visits_wny == "":
        return False
    try:
        return int(visits_wny) == 0
    except (TypeError, ValueError):
        return False


def named_fill_rate(
    fills: Any,
    denominator: Any,
    *,
    tag_missed: bool = False,
) -> float | None:
    """fills / visits_wny or fills / starts.

    Tag-miss day → null (never 2/0, never invented visits).
    Denominator 0 or missing → null.
    """
    if tag_missed:
        return None
    if fills is None or fills == "" or denominator is None or denominator == "":
        return None
    try:
        denom = float(denominator)
        numer = float(fills)
    except (TypeError, ValueError):
        return None
    if denom <= 0:
        return None
    return numer / denom


def tag_missed_from_doc(doc: dict[str, Any] | None) -> bool:
    """Read or recompute tag-miss from a daily warehouse doc.

    Recomputes from visits_wny + named_fills_live_count so a pre-flag
    2026-09-01 doc still flags on read. Never invents visits_wny.
    """
    if not doc:
        return False
    filters = doc.get("filters") if isinstance(doc.get("filters"), dict) else {}
    if doc.get("tag_missed") or filters.get("tag_missed") or filters.get("tag_miss"):
        return True
    live = filters.get("named_fills_live_count")
    if live is None:
        live = doc.get("named_fills_live_count")
    return is_tag_missed(doc.get("visits_wny"), live)


def apply_tag_miss_filters(filters: dict[str, Any] | None, visits_wny: Any) -> dict[str, Any]:
    """Stamp tag_missed / tag_miss onto a filters dict. Does not touch visits."""
    out = dict(filters or {})
    live = out.get("named_fills_live_count")
    missed = is_tag_missed(visits_wny, live)
    out["tag_missed"] = missed
    out["tag_miss"] = missed
    return out
