# -*- coding: utf-8 -*-
"""24 Hawkstone Way standing lock. Isolated from sales."""
from __future__ import annotations
import importlib.util
import inspect
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def _load():
    metric_path = ROOT / "api" / "metrics" / "website_funnel.py"
    spec = importlib.util.spec_from_file_location("hs_website_funnel_hawkstone", metric_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
    pspec = importlib.util.spec_from_file_location("hs_funnel_test_address", patch_path)
    patch = importlib.util.module_from_spec(pspec)
    pspec.loader.exec_module(patch)
    return patch.install(module)

funnel = _load()

class HawkstoneFunnelTests(unittest.TestCase):
    def test_hawkstone_test_address_drops_event_level_rows(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {
                    "event_name": "page_view",
                    "host_name": "www.happyslr.com",
                    "page_path": "/",
                    "count": 10,
                },
                {
                    "event_name": "page_view",
                    "host_name": "www.happyslr.com",
                    "page_path": "/calculator",
                    "page_location": "https://www.happyslr.com/calculator?address=24+Hawkstone+Way",
                    "count": 3,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "24 hawkstone way",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "24 Hawkstone Way",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "24 Hawkstone Way, Buffalo, NY 14221",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "124 Hawkstone Way",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "page_location": "https://wny.happyslr.com/calculator",
                    "count": 1,
                },
            ]
        )
        self.assertEqual(out["visits_total"], 10)
        self.assertEqual(out["sessions"], 10)
        self.assertEqual(out["visits_wny"], 0)
        self.assertEqual(out["estimate_submit"], 2)
        self.assertEqual(out["completed_forms"], 2)
        self.assertEqual(out["dropped"]["test_address"], 6)
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="24 hawkstone way",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="24 Hawkstone Way",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="happyslr.com",
                address="24 Hawkstone Way, Buffalo, NY 14221",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="www.happyslr.com",
                page_location="https://www.happyslr.com/calculator?address=24+Hawkstone+Way",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="24   Hawkstone    Way",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                estimate_address="24 Hawkstone Way, Williamsville, NY 14221",
            ),
            "test_address",
        )
        self.assertIsNone(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="124 Hawkstone Way",
            )
        )
        self.assertIsNone(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                page_location="https://wny.happyslr.com/calculator",
            )
        )
        self.assertEqual(inspect.getsource(funnel.fetch_ga4_event_counts).count("runReport"), 1)
        self.assertNotIn("sessionId", funnel.GA4_REPORT_DIMENSIONS)
        self.assertNotIn("address", funnel.GA4_REPORT_DIMENSIONS)
        self.assertNotIn("estimate_address", funnel.GA4_REPORT_DIMENSIONS)
        self.assertNotIn("customEvent:address", funnel.GA4_REPORT_DIMENSIONS)

    def test_stonebridge_name_email_test_traffic_drops(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "313 E Stonebridge Dr, Gilbert, AZ 85234",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "313 East Stonebridge Drive",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "name": "Test Test",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "name": "Evan Day",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "email": "adchday@gmail.com",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "email": "evanrday23@gmail.com",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "address": "100 Sullys Trail, Pittsford, NY",
                    "name": "Jane Neighbor",
                    "email": "jane@example.com",
                    "count": 1,
                },
            ]
        )
        self.assertEqual(out["estimate_submit"], 1)
        self.assertEqual(out["completed_forms"], 1)
        self.assertEqual(out["dropped"]["test_address"], 6)
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="313 E Stonebridge Dr, Gilbert, AZ 85234",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="313 East Stonebridge Drive",
            ),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", name="Test Test"),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", name="Evan Day"),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", email="adchday@gmail.com"),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", email="EVANRDAY23@GMAIL.COM"),
            "test_address",
        )
        self.assertIsNone(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                address="100 Sullys Trail",
                name="Jane Neighbor",
                email="jane@example.com",
            )
        )
        self.assertNotIn("email", funnel.GA4_REPORT_DIMENSIONS)
        self.assertNotIn("name", funnel.GA4_REPORT_DIMENSIONS)

    def test_named_fills_all_test_zeros_estimate_submit(self):
        patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
        pspec = importlib.util.spec_from_file_location("hs_funnel_test_address_named", patch_path)
        patch = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(patch)
        ga4 = {
            "ga4": "ok",
            "estimate_submit": 2,
            "wix_form_submits": 0,
            "completed_forms": 2,
            "starts": 2,
            "dropped": {"host": 0, "debug_mode": 0, "internal": 0, "test_address": 0},
            "filters": {},
        }
        fills = [
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
                "address": "24 Hawkstone Way, Pittsford, NY 14534",
            },
        ]
        out = patch.apply_named_fill_test_day(ga4, fills)
        self.assertEqual(out["estimate_submit"], 0)
        self.assertEqual(out["completed_forms"], 0)
        self.assertEqual(out["starts"], 2)
        self.assertEqual(out["dropped"]["test_address"], 2)
        self.assertTrue(out["filters"]["named_fill_zeroed"])
        self.assertEqual(out["filters"]["named_fills_count"], 2)

    def test_named_fills_empty_leaves_ga4_counts(self):
        patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
        pspec = importlib.util.spec_from_file_location("hs_funnel_test_address_empty", patch_path)
        patch = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(patch)
        ga4 = {
            "ga4": "ok",
            "estimate_submit": 2,
            "wix_form_submits": 0,
            "completed_forms": 2,
            "dropped": {"test_address": 0},
        }
        out = patch.apply_named_fill_test_day(ga4, [])
        self.assertEqual(out["estimate_submit"], 2)
        self.assertEqual(out["completed_forms"], 2)
        self.assertFalse(out["filters"]["named_fill_zeroed"])

    def test_named_fills_mixed_live_does_not_zero_day(self):
        patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
        pspec = importlib.util.spec_from_file_location("hs_funnel_test_address_mixed", patch_path)
        patch = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(patch)
        ga4 = {
            "ga4": "ok",
            "estimate_submit": 3,
            "wix_form_submits": 0,
            "completed_forms": 3,
            "dropped": {"test_address": 0},
        }
        fills = [
            {"name": "Test Test", "email": "adchday@gmail.com", "address": "313 E Stonebridge Dr"},
            {"name": "Jane Neighbor", "email": "jane@example.com", "address": "100 Sullys Trail"},
        ]
        out = patch.apply_named_fill_test_day(ga4, fills)
        self.assertEqual(out["estimate_submit"], 3)
        self.assertEqual(out["completed_forms"], 3)
        self.assertFalse(out["filters"]["named_fill_zeroed"])
        self.assertFalse(out["filters"]["named_fills_all_test"])

    def test_live_named_fills_count_when_ga4_is_zero(self):
        patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
        pspec = importlib.util.spec_from_file_location("hs_funnel_test_address_live", patch_path)
        patch = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(patch)
        live = [
            {"date": "2026-08-31", "name": "Phil Pyrce", "email": "", "address": "Getzville"},
            {"date": "2026-08-31", "name": "Bob Goodrich", "email": "", "address": "Naples"},
        ]
        tests = [
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
        ga4_zero = {
            "ga4": "ok",
            "estimate_submit": 0,
            "wix_form_submits": 0,
            "completed_forms": 0,
            "dropped": {"test_address": 0},
        }
        out_31 = patch.apply_named_fill_test_day(ga4_zero, live)
        self.assertEqual(out_31["estimate_submit"], 2)
        self.assertEqual(out_31["completed_forms"], 2)
        self.assertTrue(out_31["filters"]["named_fill_counted"])
        self.assertFalse(out_31["filters"]["named_fill_zeroed"])
        out_28 = patch.apply_named_fill_test_day(dict(ga4_zero, estimate_submit=2, completed_forms=2), tests)
        self.assertEqual(out_28["estimate_submit"], 0)
        self.assertEqual(out_28["completed_forms"], 0)
        self.assertTrue(out_28["filters"]["named_fill_zeroed"])
        sept = [
            {"date": "2026-09-01", "name": "Art Sieczkarek", "email": "Sieart@msn.com"},
            {"date": "2026-09-01", "name": "Richard Wooliver", "email": "rwooliver@gmail.com"},
        ]
        out_01 = patch.apply_named_fill_test_day(ga4_zero, sept)
        self.assertEqual(out_01["estimate_submit"], 2)
        self.assertEqual(out_01["completed_forms"], 2)
        mixed = patch.apply_named_fill_test_day(ga4_zero, live + tests)
        self.assertEqual(mixed["estimate_submit"], 2)
        self.assertEqual(mixed["completed_forms"], 2)
        self.assertNotEqual(mixed["completed_forms"], 6)
        self.assertEqual(len(patch.live_named_fills(live + tests + sept)), 4)

    def test_aug21_sep03_window_is_four_live_not_six(self):
        patch_path = ROOT / "api" / "metrics" / "funnel_test_address.py"
        pspec = importlib.util.spec_from_file_location("hs_funnel_test_address_window", patch_path)
        patch = importlib.util.module_from_spec(pspec)
        pspec.loader.exec_module(patch)
        by_date = {
            "2026-08-28": [
                {"name": "Test Test", "email": "adchday@gmail.com", "address": "313 E Stonebridge Dr"},
                {"name": "Evan Day", "email": "evanrday23@gmail.com", "address": "24 Hawkstone Way"},
            ],
            "2026-08-31": [
                {"name": "Phil Pyrce", "email": "", "address": "Getzville"},
                {"name": "Bob Goodrich", "email": "", "address": "Naples"},
            ],
            "2026-09-01": [
                {"name": "Art Sieczkarek", "email": "Sieart@msn.com"},
                {"name": "Richard Wooliver", "email": "rwooliver@gmail.com"},
            ],
        }
        ga4 = {"ga4": "ok", "estimate_submit": 0, "wix_form_submits": 0, "completed_forms": 0}
        total = 0
        day_28 = None
        from datetime import date, timedelta

        start = date(2026, 8, 21)
        end = date(2026, 9, 3)
        day = start
        while day <= end:
            key = day.isoformat()
            out = patch.apply_named_fill_test_day(ga4, by_date.get(key, []))
            if key == "2026-08-28":
                day_28 = out
            total += int(out.get("completed_forms") or 0)
            day += timedelta(days=1)
        self.assertEqual(day_28["estimate_submit"], 0)
        self.assertEqual(day_28["completed_forms"], 0)
        self.assertEqual(total, 4)
        self.assertNotEqual(total, 0)
        self.assertNotEqual(total, 6)
