# -*- coding: utf-8 -*-
"""Query-result cache TTL, and the slow-dashboard maxDuration floor."""

from __future__ import annotations

import json
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
sys.path.insert(0, str(API))

from query_result_cache import (  # noqa: E402
    OPEN_TTL_SECONDS,
    PAST_TTL_SECONDS,
    QueryCache,
    range_end_ymd,
    ttl_seconds,
)

NY = ZoneInfo("America/New_York")
TODAY = datetime(2026, 10, 12, 15, 0, tzinfo=NY)


class QueryCacheTests(unittest.TestCase):
    def test_past_range_is_ten_minutes_and_open_range_is_one_minute(self):
        self.assertEqual(PAST_TTL_SECONDS, 600)
        self.assertGreaterEqual(PAST_TTL_SECONDS, 5 * 60)
        self.assertLessEqual(PAST_TTL_SECONDS, 15 * 60)
        self.assertEqual(ttl_seconds("2026-09-30", now=TODAY), 600)
        self.assertEqual(ttl_seconds("2026-10-12", now=TODAY), OPEN_TTL_SECONDS)
        self.assertEqual(ttl_seconds("2026-10-13", now=TODAY), OPEN_TTL_SECONDS)
        self.assertEqual(ttl_seconds(None, now=TODAY), OPEN_TTL_SECONDS)
        self.assertEqual(ttl_seconds("", now=TODAY), OPEN_TTL_SECONDS)

    def test_year_month_and_named_periods(self):
        self.assertEqual(range_end_ymd(end="2026-09-30", year=2026, month=10, now=TODAY), "2026-09-30")
        self.assertEqual(range_end_ymd(year=2026, month=9, now=TODAY), "2026-09-30")
        self.assertEqual(ttl_seconds(range_end_ymd(year=2026, month=9, now=TODAY), now=TODAY), 600)
        self.assertEqual(range_end_ymd(period="yesterday", now=TODAY), "2026-10-11")
        self.assertEqual(ttl_seconds(range_end_ymd(period="lastmo", now=TODAY), now=TODAY), 600)
        self.assertEqual(range_end_ymd(period="today", now=TODAY), "2026-10-12")
        self.assertEqual(ttl_seconds(range_end_ymd(year=2026, month=None, now=TODAY), now=TODAY), OPEN_TTL_SECONDS)

    def test_cache_hit_returns_a_copy_and_expires(self):
        cache = QueryCache(max_entries=2)
        payload = {"rows": [1]}
        cache.put("a", payload, 600)
        payload["rows"].append(2)
        hit = cache.get("a")
        self.assertEqual(hit, {"rows": [1]})
        hit["rows"].append(9)
        self.assertEqual(cache.get("a"), {"rows": [1]})
        self.assertIsNone(cache.get("missing"))

        cache.put("old", {"n": 1}, ttl=0)
        time.sleep(0.01)
        self.assertIsNone(cache.get("old"))

        cache.put("b", {"n": 2}, 600)
        cache.put("c", {"n": 3}, 600)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("c"), {"n": 3})

    def test_helper_does_not_write_firestore(self):
        src = (API / "query_result_cache.py").read_text(encoding="utf-8")
        self.assertNotIn("google.cloud", src)
        self.assertNotIn(".collection(", src)
        self.assertNotIn(".set(", src)
        self.assertNotIn(".update(", src)
        self.assertNotIn(".delete(", src)

    def test_slow_endpoints_allow_at_least_90_seconds(self):
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        functions = vercel["functions"]
        for key in (
            "api/index.py",
            "api/metrics/inbound_cac.py",
            "api/powerline_dashboard.py",
            "api/metrics/raydar_doors_knocked.py",
            "api/metrics/kixie_calls_summary.py",
            "api/website_traffic.py",
        ):
            self.assertGreaterEqual(int(functions[key]["maxDuration"]), 90, key)
        self.assertEqual(functions["api/index.py"]["includeFiles"], "api/**")
        routed = json.dumps({"rewrites": vercel.get("rewrites"), "crons": vercel.get("crons")})
        for name in ("inbound_cac", "website_traffic", "website_funnel", "web_funnel"):
            self.assertNotIn(name, routed)


class AppointmentOutcomesDateTests(unittest.TestCase):
    def test_top_filter_dates_drive_the_table_window(self):
        from appointment_outcomes import outcome_window_raw

        both = {
            "start": ["2026-09-01"],
            "end": ["2026-09-30"],
            "start_date": ["2026-10-11"],
            "end_date": ["2026-10-11"],
        }
        self.assertEqual(outcome_window_raw(both), ("2026-09-01", "2026-09-30"))
        page_only = {"start_date": ["2026-09-01"], "end_date": ["2026-09-30"]}
        self.assertEqual(outcome_window_raw(page_only), ("2026-09-01", "2026-09-30"))
        incomplete = {"start": ["2026-09-01"], "start_date": ["2026-10-01"], "end_date": ["2026-10-11"]}
        self.assertEqual(outcome_window_raw(incomplete), ("2026-10-01", "2026-10-11"))

        src = (API / "appointment_outcomes.py").read_text(encoding="utf-8")
        self.assertIn("hsOpsWriteFilters", src)
        self.assertIn("url.searchParams.set('start_date', ocStart.value)", src)


if __name__ == "__main__":
    unittest.main()
