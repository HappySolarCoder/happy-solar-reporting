# -*- coding: utf-8 -*-
"""Lock Website Funnel metric → source contract and tag-miss presentation."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.append(path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load_module("hs_funnel_metric_contract", METRICS / "funnel_metric_contract.py")
funnel = load_module("hs_website_funnel_source_contract", METRICS / "website_funnel.py")
patch = load_module("hs_funnel_test_address_source_contract", METRICS / "funnel_test_address.py")

LIVE_31 = [
    {"date": "2026-08-31", "name": "Phil Pyrce", "email": "pyrce@verizon.net", "address": "Getzville"},
    {"date": "2026-08-31", "name": "Bob Goodrich", "email": "bggoodrich@gmail.com", "address": "Naples"},
]
LIVE_01 = [
    {"date": "2026-09-01", "name": "Art Sieczkarek", "email": "Sieart@msn.com"},
    {"date": "2026-09-01", "name": "Richard Wooliver", "email": "rwooliver@gmail.com"},
]
TESTS_28 = [
    {
        "date": "2026-08-28",
        "name": "Test Test",
        "email": "adchday@gmail.com",
        "address": "313 E Stonebridge Dr, Gilbert, AZ 85234",
    },
    {
        "date": "2026-08-28",
        "name": "Evan Day",
        "email": "evanrday23@gmail.com",
        "address": "24 Hawkstone Way",
    },
]


class MetricSourceContractTests(unittest.TestCase):
    def test_required_metrics_lock_one_source(self):
        sources = contract.METRIC_SOURCES
        self.assertEqual(funnel.METRIC_SOURCES, sources)
        self.assertEqual(patch.METRIC_SOURCES, sources)
        self.assertEqual(sources["completed_forms"]["source"], "live_named_wny_submits")
        self.assertEqual(sources["completed_forms"]["store"], "web_funnel_named_fills_v1")
        self.assertEqual(sources["completed_forms"]["ingest"], "leads@")
        self.assertEqual(sources["estimate_submit"]["source"], "live_named_wny_submits")
        self.assertEqual(sources["estimate_submit"]["same_as"], "completed_forms")
        self.assertEqual(sources["visits_wny"]["source"], "ga4_sessions")
        self.assertEqual(sources["visits_wny"]["filter"], "filters.visits_wny_hosts")
        self.assertEqual(sources["visits_wny"]["hosts"], ("wny.happyslr.com",))
        self.assertEqual(sources["visits_wny"]["do_not_backfill_from"], "named_fills")
        self.assertEqual(sources["starts"]["source"], "ga4_event")
        self.assertEqual(sources["starts"]["event"], "estimate_start")
        self.assertEqual(sources["address_complete"]["source"], "ga4_event")
        self.assertEqual(sources["address_complete"]["event"], "estimate_address_complete")
        self.assertEqual(sources["bill_complete"]["source"], "ga4_event")
        self.assertEqual(sources["bill_complete"]["event"], "estimate_bill_complete")
        self.assertEqual(sources["visits_total"]["source"], "ga4_sessions")
        self.assertEqual(sources["visits_total"]["distinct_from"], "visits_wny")
        self.assertEqual(sources["sessions"]["same_as"], "visits_total")
        self.assertEqual(sources["sessions"]["distinct_from"], "visits_wny")
        for key in ("completed_forms", "estimate_submit"):
            self.assertIn("24 Hawkstone Way", sources[key]["tests_out"])
            self.assertIn("313 E Stonebridge Dr / 313 East Stonebridge Drive Gilbert AZ", sources[key]["tests_out"])
            self.assertIn("Test Test", sources[key]["tests_out"])
            self.assertIn("Evan Day", sources[key]["tests_out"])
            self.assertIn("adchday@gmail.com", sources[key]["tests_out"])
            self.assertIn("evanrday23@gmail.com", sources[key]["tests_out"])
            self.assertIn("ga4_visit", sources[key]["not"])
            self.assertIn("by_page.calculator", sources[key]["not"])
        self.assertIn("by_page.calculator.sessions", sources["visits_wny"]["not"])
        self.assertIn("named_fill", sources["visits_wny"]["not"])
        self.assertIn("named_fill", sources["starts"]["not"])
        self.assertEqual(contract.TAG_MISS_RULE["flag"], "tag_missed")
        self.assertIsNone(contract.TAG_MISS_RULE["rates"]["fills_over_visits_wny"])
        self.assertIsNone(contract.TAG_MISS_RULE["rates"]["fills_over_starts"])
        self.assertIn("2/0", contract.TAG_MISS_RULE["never"])
        self.assertIn("invented_visits_wny", contract.TAG_MISS_RULE["never"])

    def test_named_fill_is_not_a_ga4_visit(self):
        self.assertIn("NOT a GA4 visit", sources_note())
        self.assertFalse(contract.is_tag_missed(9, 2))
        self.assertFalse(contract.is_tag_missed(0, 0))
        self.assertFalse(contract.is_tag_missed(None, 2))
        self.assertTrue(contract.is_tag_missed(0, 2))
        self.assertIsNone(contract.named_fill_rate(2, 0, tag_missed=True))
        self.assertIsNone(contract.named_fill_rate(2, 0, tag_missed=False))
        self.assertIsNone(contract.named_fill_rate(2, None, tag_missed=False))
        self.assertAlmostEqual(contract.named_fill_rate(2, 9, tag_missed=False), 2 / 9)
        self.assertIsNone(contract.named_fill_rate(2, 3, tag_missed=True))

    def test_scoreboard_contract_exposes_metric_sources(self):
        payload = funnel.aggregate_daily_docs([], year=2026, month=8)
        self.assertEqual(payload["contract"]["metric_sources"], contract.METRIC_SOURCES)
        self.assertEqual(payload["contract"]["visits_wny"], contract.METRIC_SOURCES["visits_wny"]["equals"])
        self.assertEqual(
            payload["contract"]["completed_forms"],
            contract.METRIC_SOURCES["completed_forms"]["equals"],
        )
        self.assertIn("by_page.calculator", payload["contract"]["by_page_calculator"])
        html = funnel.render_html(2026, 8)
        self.assertIn("not by_page.calculator", html)
        self.assertIn("tag-miss", html)
        self.assertNotIn("Designer", html)
        self.assertNotIn("2/0", html.replace("not 2/0", ""))


def sources_note() -> str:
    return contract.METRIC_SOURCES["completed_forms"]["note"]


class ControlAndTagMissDayTests(unittest.TestCase):
    def test_aug31_control_no_tag_miss(self):
        ga4 = {
            "ga4": "ok",
            "sessions": 57,
            "visits_total": 57,
            "visits_wny": 9,
            "starts": 3,
            "address_complete": 4,
            "bill_complete": 2,
            "estimate_submit": 0,
            "wix_form_submits": 0,
            "completed_forms": 0,
            "filters": {"visits_wny_hosts": ["wny.happyslr.com"]},
        }
        out = patch.apply_named_fill_test_day(ga4, LIVE_31)
        self.assertEqual(out["visits_wny"], 9)
        self.assertEqual(out["starts"], 3)
        self.assertEqual(out["address_complete"], 4)
        self.assertEqual(out["bill_complete"], 2)
        self.assertEqual(out["estimate_submit"], 2)
        self.assertEqual(out["completed_forms"], 2)
        self.assertEqual(out["filters"]["named_fills_live_count"], 2)
        self.assertFalse(out["tag_missed"])
        self.assertFalse(out["filters"]["tag_missed"])
        self.assertFalse(out["filters"]["tag_miss"])
        doc = funnel.build_daily_doc("2026-08-31", out)
        self.assertEqual(doc["visits_wny"], 9)
        self.assertEqual(doc["completed_forms"], 2)
        self.assertFalse(doc["tag_missed"])
        self.assertAlmostEqual(doc["forms_over_wny"], 2 / 9)
        self.assertAlmostEqual(doc["forms_over_starts"], 2 / 3)
        self.assertNotEqual(doc["visits_wny"], doc["by_page"]["calculator"]["sessions"])
        snap = funnel.build_day_snapshot(doc, "2026-08-31")
        self.assertFalse(snap["tag_missed"])
        self.assertEqual(snap["visits_wny"], 9)
        self.assertEqual(snap["completed_forms"], 2)
        self.assertAlmostEqual(snap["forms_over_wny"], 2 / 9)
        self.assertAlmostEqual(snap["start_to_submit"], 2 / 3)

    def test_sep01_tag_miss_no_impossible_rate(self):
        ga4 = {
            "ga4": "ok",
            "sessions": 38,
            "visits_total": 38,
            "visits_wny": 0,
            "starts": 0,
            "address_complete": 0,
            "bill_complete": 0,
            "estimate_submit": 0,
            "wix_form_submits": 0,
            "completed_forms": 0,
            "filters": {"visits_wny_hosts": ["wny.happyslr.com"]},
        }
        out = patch.apply_named_fill_test_day(ga4, LIVE_01)
        self.assertEqual(out["visits_wny"], 0)
        self.assertEqual(out["starts"], 0)
        self.assertEqual(out["estimate_submit"], 2)
        self.assertEqual(out["completed_forms"], 2)
        self.assertTrue(out["tag_missed"])
        self.assertTrue(out["filters"]["tag_missed"])
        self.assertTrue(out["filters"]["tag_miss"])
        self.assertEqual(out["visits_wny"], 0)
        self.assertNotEqual(out["visits_wny"], out["filters"]["named_fills_live_count"])
        doc = funnel.build_daily_doc("2026-09-01", out)
        self.assertEqual(doc["visits_wny"], 0)
        self.assertEqual(doc["completed_forms"], 2)
        self.assertTrue(doc["tag_missed"])
        self.assertIsNone(doc["forms_over_wny"])
        self.assertIsNone(doc["forms_over_starts"])
        self.assertNotEqual(doc["forms_over_wny"], float("inf"))
        snap = funnel.build_day_snapshot(doc, "2026-09-01")
        self.assertTrue(snap["tag_missed"])
        self.assertTrue(snap["tag_miss"])
        self.assertEqual(snap["visits_wny"], 0)
        self.assertEqual(snap["estimate_submit"], 2)
        self.assertIsNone(snap["forms_over_wny"])
        self.assertIsNone(snap["forms_over_starts"])
        self.assertIsNone(snap["start_to_submit"])
        self.assertIsNone(snap["start→submit"])
        chart = funnel.chart_day_from_doc(doc, "2026-09-01")
        self.assertTrue(chart["tag_missed"])
        self.assertEqual(chart["visits_wny"], 0)
        self.assertEqual(chart["completed_forms"], 2)
        self.assertIsNone(chart["forms_over_wny"])
        self.assertIsNone(chart["forms_over_starts"])
        month = funnel.aggregate_daily_docs([doc], year=2026, month=9)
        self.assertEqual(month["tag_miss_dates"], ["2026-09-01"])
        self.assertTrue(month["tag_missed"])
        self.assertIsNone(month["forms_over_wny"])
        self.assertIsNone(month["kpis"]["start_to_completed_form"]["value"])
        notes = " ".join(month["notes"]).lower()
        self.assertIn("tag missed", notes)
        self.assertIn("2026-09-01", notes)
        self.assertIn("not a conversion from 0 wny visits", notes)
        self.assertNotIn("designer", notes)

    def test_sep01_pre_flag_doc_still_flags_on_read(self):
        """Warehouse docs written before this flag still recompute tag-miss."""
        old = {
            "date": "2026-09-01",
            "ga4": "ok",
            "sessions": 38,
            "visits_total": 38,
            "visits_wny": 0,
            "starts": 0,
            "estimate_submit": 2,
            "completed_forms": 2,
            "filters": {
                "visits_wny_hosts": ["wny.happyslr.com"],
                "named_fills_live_count": 2,
                "named_fill_counted": True,
            },
        }
        self.assertTrue(contract.tag_missed_from_doc(old))
        snap = funnel.build_day_snapshot(old, "2026-09-01")
        self.assertTrue(snap["tag_missed"])
        self.assertIsNone(snap["forms_over_wny"])
        self.assertIsNone(snap["start_to_submit"])
        chart = funnel.chart_day_from_doc(old, "2026-09-01")
        self.assertTrue(chart["tag_missed"])
        self.assertIsNone(chart["forms_over_wny"])

    def test_aug28_tests_still_zero(self):
        ga4 = {
            "ga4": "ok",
            "visits_wny": 12,
            "starts": 2,
            "estimate_submit": 2,
            "wix_form_submits": 0,
            "completed_forms": 2,
        }
        out = patch.apply_named_fill_test_day(ga4, TESTS_28)
        self.assertEqual(out["estimate_submit"], 0)
        self.assertEqual(out["completed_forms"], 0)
        self.assertEqual(out["visits_wny"], 12)
        self.assertEqual(out["starts"], 2)
        self.assertTrue(out["filters"]["named_fill_zeroed"])
        self.assertFalse(out["tag_missed"])
        doc = funnel.build_daily_doc("2026-08-28", out)
        self.assertEqual(doc["completed_forms"], 0)
        self.assertFalse(doc["tag_missed"])

    def test_does_not_backfill_visits_wny_from_named_fills(self):
        ga4 = {
            "ga4": "ok",
            "visits_wny": 0,
            "starts": 0,
            "estimate_submit": 0,
            "completed_forms": 0,
            "wix_form_submits": 0,
        }
        out = patch.apply_named_fill_test_day(ga4, LIVE_01)
        self.assertEqual(out["visits_wny"], 0)
        self.assertEqual(out["completed_forms"], 2)
        self.assertNotEqual(out["visits_wny"], 2)
        doc = funnel.build_daily_doc("2026-09-01", out)
        self.assertEqual(doc["visits_wny"], 0)
        self.assertNotEqual(doc["visits_wny"], doc["completed_forms"])


class ByPageCalculatorIsNotWnyVisitsTests(unittest.TestCase):
    def test_wny_host_page_views_are_visits_wny_not_calculator_bucket(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {
                    "event_name": "page_view",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "count": 9,
                },
                {
                    "event_name": "page_view",
                    "host_name": "www.happyslr.com",
                    "page_path": "/",
                    "count": 57,
                },
                {
                    "event_name": "estimate_start",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "count": 3,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "count": 0,
                },
            ]
        )
        self.assertEqual(out["visits_wny"], 9)
        self.assertEqual(out["visits_total"], 57)
        self.assertEqual(out["sessions"], 57)
        self.assertNotEqual(out["visits_wny"], out["sessions"])
        self.assertEqual(out["by_page"]["calculator"]["sessions"], 0)
        self.assertNotEqual(out["visits_wny"], out["by_page"]["calculator"]["sessions"])
        self.assertEqual(out["filters"]["visits_wny_hosts"], ["wny.happyslr.com"])
        self.assertEqual(out["starts"], 3)
        self.assertEqual(out["by_page"]["calculator"]["completed_forms"], 0)
        self.assertNotEqual(out["visits_wny"], out["by_page"]["calculator"]["completed_forms"])

    def test_visits_wny_never_read_from_by_page_calculator(self):
        src = Path(METRICS / "website_funnel.py").read_text()
        self.assertIn('LIVE_WNY_HOSTS = frozenset({HOST_WNY})', src)
        self.assertIn('"visits_wny_hosts": sorted(LIVE_WNY_HOSTS)', src)
        self.assertIn("host_kind == \"wny\"", src)
        summarize = Path(METRICS / "website_funnel.py").read_text()
        self.assertNotIn('visits_wny = by_page', summarize)
        self.assertNotIn('visits_wny = bucket', summarize)
        self.assertNotIn('["calculator"]["sessions"]', src)
        doc = funnel.build_daily_doc(
            "2026-08-31",
            {
                "ga4": "ok",
                "visits_total": 57,
                "visits_wny": 9,
                "sessions": 57,
                "starts": 3,
                "estimate_submit": 2,
                "completed_forms": 2,
                "by_page": {"calculator": {"sessions": 0, "starts": 0, "completed_forms": 0}},
                "filters": {"named_fills_live_count": 2, "visits_wny_hosts": ["wny.happyslr.com"]},
            },
        )
        self.assertEqual(doc["visits_wny"], 9)
        self.assertEqual(doc["by_page"]["calculator"]["sessions"], 0)
        self.assertEqual(doc["by_page"]["calculator"]["completed_forms"], 0)
        self.assertNotEqual(doc["visits_wny"], doc["by_page"]["calculator"]["sessions"])
        self.assertNotEqual(doc["completed_forms"], doc["by_page"]["calculator"]["completed_forms"])


class SalesContractUntouchedTests(unittest.TestCase):
    def test_funnel_contract_module_does_not_read_sold_date_field(self):
        text = (METRICS / "funnel_metric_contract.py").read_text()
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", text)
        self.assertNotIn("hd5QqHEOVSsPom5bJ32P", text)
        self.assertNotIn("ghl_opportunities_v2", text)
        sales = (METRICS / "sales.py").read_text()
        self.assertIn("P9oBjgbZjJdeE0OkBj9T", sales)
        self.assertNotIn("METRIC_SOURCES", sales)
        self.assertNotIn("tag_missed", sales)


if __name__ == "__main__":
    unittest.main()
