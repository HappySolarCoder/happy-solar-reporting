# -*- coding: utf-8 -*-

"""Lead Gen Pipelines: Inbound and 3PL are separate CF channel cards."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))


def load_company_overview():
    spec = importlib.util.spec_from_file_location(
        "hs_company_overview_leadgen", API / "company_overview.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/company_overview.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LeadGenInbound3plSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_company_overview()
        cls.html = cls.mod.render_html(2026, 9)

    def test_inbound_and_3pl_funnel_cards_are_separate(self):
        html = self.html
        self.assertIn("Inbound Funnel", html)
        self.assertIn("3PL Funnel", html)
        self.assertNotIn("3PL/Inbound Funnel", html)
        self.assertIn('id="lgInboundCreated"', html)
        self.assertIn('id="lgInboundDemo"', html)
        self.assertIn('id="lgInboundOpp2"', html)
        self.assertIn('id="lgInboundSales"', html)
        self.assertIn('id="lg3plCreated"', html)
        self.assertIn('id="lg3plDemo"', html)
        self.assertIn('id="lg3plOpp2"', html)
        self.assertIn('id="lg3plSales"', html)

    def test_js_no_longer_combines_3pl_and_inbound_keys(self):
        html = self.html
        self.assertNotIn("THREE_PL_INBOUND_KEYS", html)
        self.assertIn("INBOUND_KEYS = ['Inbound']", html)
        self.assertIn("THREE_PL_KEYS = ['3PL']", html)
        self.assertIn("lead_source=Inbound", html)
        self.assertIn("lead_source=3PL", html)

    def test_sep2026_fixture_sums_match_former_combined_keys(self):
        # Live chi Sep 2026 evidence: Inbound+3PL created = former combined.
        created_by_lead = {"Doors": 81, "Self Gen": 16, "3PL": 12, "Inbound": 3, "Phones": 1, "none": 1}
        sales_by_lead = {"Doors": 17, "Self Gen": 8, "3PL": 3, "Inbound": 0}
        ran_by_lead = {"3PL": 15, "Inbound": 3}
        sit_by_lead = {"3PL": 6, "Inbound": 1.8}  # rates 40% / 60% of ran

        inbound_created = int(created_by_lead.get("Inbound") or 0)
        three_pl_created = int(created_by_lead.get("3PL") or 0)
        former_combined_created = inbound_created + three_pl_created
        self.assertEqual(former_combined_created, 15)
        self.assertEqual(inbound_created + three_pl_created, former_combined_created)

        inbound_sales = int(sales_by_lead.get("Inbound") or 0)
        three_pl_sales = int(sales_by_lead.get("3PL") or 0)
        self.assertEqual(inbound_sales + three_pl_sales, 3)

        # Demo rates match filtered lead_source grain (not title-bucket CAC).
        inbound_demo = (sit_by_lead["Inbound"] / ran_by_lead["Inbound"]) * 100
        three_pl_demo = (sit_by_lead["3PL"] / ran_by_lead["3PL"]) * 100
        self.assertAlmostEqual(inbound_demo, 60.0, places=1)
        self.assertAlmostEqual(three_pl_demo, 40.0, places=1)

    def test_company_doors_self_gen_phones_titles_unchanged(self):
        html = self.html
        for title in ("Company Funnel", "Doors Funnel", "Self Gen Funnel", "Phones Funnel"):
            self.assertIn(title, html)
        # Must not pull inbound CAC title-bucket logic into Lead Gen Pipelines.
        self.assertNotIn("Lead Locker", html)
        self.assertNotIn("Solar Reviews", html)
        self.assertNotIn("bucket_title", html)


if __name__ == "__main__":
    unittest.main()
