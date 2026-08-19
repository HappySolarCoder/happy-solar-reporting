# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SALES = (ROOT / "api" / "metrics" / "sales.py").read_text()
WARM = (ROOT / "api" / "warm_cache.py").read_text()


class BoundLookupTests(unittest.TestCase):
    def test_compute_sales_does_not_stream_roster_or_pipelines(self):
        self.assertNotIn('db.collection("ghl_pipelines_v2").stream()', SALES)
        self.assertNotIn('db.collection("roster_people_v1").stream()', SALES)
        self.assertIn('db.collection("ghl_pipelines_v2").document', SALES)
        self.assertIn('db.collection("roster_people_v1").document', SALES)
        self.assertIn('where("ghl_user_id", "in", chunk)', SALES)
        self.assertIn('where("id", "==", pid).limit(1)', SALES)

    def test_warm_cache_has_no_metric_urls(self):
        self.assertIn("urls = []", WARM)
        self.assertNotIn("opportunities_created", WARM)
        self.assertNotIn("opportunities_ran", WARM)
        self.assertNotIn("demo_rate", WARM)
        self.assertNotIn("company_snapshot", WARM)
        self.assertNotIn("metrics/sales", WARM)
        self.assertNotIn("essential_sales", WARM)


if __name__ == "__main__":
    unittest.main()
