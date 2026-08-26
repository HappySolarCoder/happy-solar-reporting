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
