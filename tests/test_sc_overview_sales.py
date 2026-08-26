# -*- coding: utf-8 -*-

"""Consultant Overview Summary Sales match the completed-appointment pie."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

SC_OVERVIEW_SRC = (API / "sc_overview.py").read_text(encoding="utf-8")
SALES_SRC = (METRICS / "sales.py").read_text(encoding="utf-8")
SALES_CANCELLATIONS_SRC = (METRICS / "sales_cancellations.py").read_text(encoding="utf-8")

# Jeff / Maecker window lock — do not invent another owner or ratio.
MAECKER_OWNER_ID = "nFf2FIr40kvWRCVaMej2"
MAECKER_SOLD = 28
MAECKER_SALE_CANCELLED = 8
MAECKER_SALES = 36
MAECKER_DEMOS = 74
MAECKER_CLOSE_RATE = 48.6
SOLD_DATE_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"


def _install_google_stubs() -> None:
    google = sys.modules.setdefault("google", MagicMock())
    cloud = sys.modules.setdefault("google.cloud", MagicMock())
    oauth2 = sys.modules.setdefault("google.oauth2", MagicMock())
    sys.modules.setdefault("google.cloud.firestore", MagicMock())
    sys.modules.setdefault("google.oauth2.service_account", MagicMock())
    google.cloud = cloud
    google.oauth2 = oauth2


def load_sc_overview():
    _install_google_stubs()
    spec = importlib.util.spec_from_file_location("sc_overview_sales_lock", API / "sc_overview.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/sc_overview.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sc_overview_sales_lock"] = module
    spec.loader.exec_module(module)
    return module


sc_overview = load_sc_overview()


class CompletedSaleBucketTests(unittest.TestCase):
    def test_pie_keeps_sold_and_sale_cancelled_labels(self):
        self.assertEqual(sc_overview.normalize_completed_outcome_bucket("Buffalo", "Sold"), "Sold")
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Virtual", "Sale Cancelled"),
            "Sale Cancelled",
        )
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Rehash", "Sold"),
            "Sold",
        )

    def test_only_sold_and_sale_cancelled_count(self):
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("Sold"))
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("Sale Cancelled"))
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("sale canceled"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Auto Text Sent"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("No Show/Pre-cancelled"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Demo-Negotiating"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Rescheduled"))


class MaeckerWindowLockTests(unittest.TestCase):
    def test_summary_sales_are_pie_sold_plus_sale_cancelled(self):
        stage_counts = {
            "Sold": MAECKER_SOLD,
            "Sale Cancelled": MAECKER_SALE_CANCELLED,
            "Auto Text Sent": 27,
            "No Show/Pre-cancelled": 20,
            "DQ'ed": 14,
            "Rescheduled": 6,
            "Call 1": 5,
            "Not Interested": 3,
            "Demo-Negotiating": 2,
            "Demo-Not Interested": 2,
            "Do not Contact": 2,
            "Reschedule Needed": 2,
            "One Legger": 1,
        }
        self.assertEqual(sum(stage_counts.values()), 120)
        self.assertEqual(sc_overview.completed_sale_count(stage_counts), MAECKER_SALES)
        self.assertEqual(
            sc_overview.close_rate_on_demos(MAECKER_SALES, MAECKER_DEMOS),
            MAECKER_CLOSE_RATE,
        )
        self.assertNotEqual(sc_overview.close_rate_on_demos(6, MAECKER_DEMOS), MAECKER_CLOSE_RATE)
        self.assertEqual(sc_overview.close_rate_on_demos(28, MAECKER_DEMOS), 37.8)
        self.assertIsNone(sc_overview.close_rate_on_demos(MAECKER_SALES, 0))


class OverviewContractTests(unittest.TestCase):
    def test_summary_sales_reuse_pie_buckets_not_sold_date(self):
        self.assertIn("if is_completed_sale_outcome_bucket(outcome_bucket):", SC_OVERVIEW_SRC)
        self.assertIn('owner_rows[owner]["sales"] += 1', SC_OVERVIEW_SRC)
        self.assertIn('"sales": completed_sale_count(stage_counts),', SC_OVERVIEW_SRC)
        self.assertIn("totals[\"close_rate_on_demos\"] = close_rate_on_demos(totals[\"sales\"], totals[\"demos\"])", SC_OVERVIEW_SRC)
        self.assertNotIn("Sales and Two-Touch stay on Sold Date.", SC_OVERVIEW_SRC)
        self.assertIn(
            "Sales are completed-appointment Sold + Sale Cancelled (same grain as the pie).",
            SC_OVERVIEW_SRC,
        )
        self.assertIn("Two-Touch stays on Sold Date.", SC_OVERVIEW_SRC)
        self.assertIn(MAECKER_OWNER_ID, "nFf2FIr40kvWRCVaMej2")

    def test_sold_date_loop_no_longer_increments_summary_sales(self):
        sold_date_loop = SC_OVERVIEW_SRC.split("if not sold_date_in_window(contact, touch_start_local, touch_end_local):", 1)[1]
        sold_date_loop = sold_date_loop.split("for doc in db.collection", 1)[0]
        self.assertNotIn('owner_rows[owner]["sales"] += 1', sold_date_loop)
        self.assertIn('touch_rows[owner]["sales_total"] += 1', sold_date_loop)

    def test_company_sold_date_sales_contract_is_untouched(self):
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_SRC)
        self.assertIn("Time filter is based on Contact Sold Date", SALES_SRC)
        self.assertIn('sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"', SALES_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SC_OVERVIEW_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_CANCELLATIONS_SRC)
        self.assertNotIn("completed_sale_count", SALES_SRC)
        self.assertNotIn("is_completed_sale_outcome_bucket", SALES_SRC)
