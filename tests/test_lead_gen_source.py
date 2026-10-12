# -*- coding: utf-8 -*-
"""Facebook Quick Form counts as Inbound through one helper."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
if str(METRICS) not in sys.path:
    sys.path.insert(0, str(METRICS))
if str(API) not in sys.path:
    sys.path.append(str(API))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lead_gen_source = load("lead_gen_source_under_test", METRICS / "lead_gen_source.py")
demo_rate = load("demo_rate_lead_source", METRICS / "demo_rate.py")
fma_weekly_review = load("fma_weekly_review_metric_lead_source", METRICS / "fma_weekly_review.py")
opportunities_created = load("opportunities_created_lead_source", METRICS / "opportunities_created.py")
sales = load("sales_lead_source", METRICS / "sales.py")
sales_cancellations = load("sales_cancellations_lead_source", METRICS / "sales_cancellations.py")
sweeper_rehash_attribution = load(
    "sweeper_rehash_attribution_lead_source",
    METRICS / "sweeper_rehash_attribution.py",
)
rep_daily_recap = load("rep_daily_recap_lead_source", API / "rep_daily_recap.py")
sc_overview = load("sc_overview_lead_source", API / "sc_overview.py")
qa = load("fma_sales_setter_table_lead_source", API / "qa" / "fma_sales_setter_table.py")


class LeadGenSourceTests(unittest.TestCase):
    def test_variants_count_as_inbound(self):
        helper = lead_gen_source.is_inbound_lead_source
        self.assertTrue(helper("Inbound"))
        self.assertTrue(helper(" INBOUND "))
        self.assertTrue(helper("Facebook Quick Form"))
        self.assertTrue(helper("facebook quick form"))
        self.assertTrue(helper("FB Quick Form"))
        self.assertTrue(helper("fb-quick-form"))
        self.assertTrue(helper("FB_Quick_Form"))
        self.assertEqual(lead_gen_source.inbound_source_label("fb quick form"), "Inbound")
        self.assertFalse(helper("3PL"))
        self.assertFalse(helper("3pl/inbound"))
        self.assertFalse(helper("3pl / inbound"))
        self.assertFalse(helper("Lead Locker"))
        self.assertFalse(helper("Quick Form"))
        self.assertFalse(helper(""))
        self.assertFalse(helper(None))

    def test_metric_buckets_use_the_helper(self):
        samples = ("Facebook Quick Form", "FB Quick Form", "fb-quick-form")
        buckets = (
            opportunities_created.normalize_channel,
            demo_rate.normalize_lead_source,
            sales.normalize_sales_lead_source,
            sales_cancellations.normalize_channel,
            fma_weekly_review.normalize_channel,
            sc_overview.normalize_lead_source,
            rep_daily_recap.normalize_lead_source,
            qa.normalize_lead_source,
        )
        for sample in samples:
            for bucket in buckets:
                self.assertEqual(bucket(sample), "Inbound", bucket.__module__)
        self.assertEqual(opportunities_created.normalize_channel("3pl/inbound"), "3pl/inbound")
        self.assertEqual(sc_overview.normalize_lead_source("3pl/inbound"), "Inbound")
        self.assertEqual(rep_daily_recap.normalize_lead_source("3pl/inbound"), "3PL/Inbound")
        self.assertTrue(
            sweeper_rehash_attribution.lead_source_matches("Inbound", "FB Quick Form", None)
        )
        self.assertFalse(
            sweeper_rehash_attribution.lead_source_matches("Inbound", "Doors", None)
        )
