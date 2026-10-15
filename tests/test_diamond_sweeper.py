# -*- coding: utf-8 -*-
"""Diamond sweeper/rehash dashboard: name filter and Company Overview rates."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (API, METRICS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import importlib.util

from dashboard_nav import render_dashboard_nav  # noqa: E402
import dashboard_nav as nav  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


page = _load("diamond_sweeper_page", API / "diamond_sweeper.py")
metrics = _load("diamond_sweeper_metrics", METRICS / "diamond_sweeper.py")
index = _load("diamond_sweeper_index", API / "index.py")

FIELD = "HWfjOp8MvE6soxBAL75f"
NY = ZoneInfo("America/New_York")


class DiamondFilterTests(unittest.TestCase):
    def test_created_rows_match_diamond_only(self):
        payload = {
            "sample_rows": [
                {"opportunityId": "o1", "sweeperRehashLastName": "Diamond", "pipeline": "Rehash", "createdAt": "a"},
                {"opportunityId": "o1", "sweeperRehashLastName": "diamond ", "pipeline": "Rehash"},
                {"opportunityId": "o2", "sweeperRehashLastName": "Other"},
                {"opportunityId": "o3", "sweeperRehashLastName": None, "setterLastName": "Diamond"},
                {"opportunityId": "o4", "sweeperRehashLastName": "DIAMOND", "pipeline": "Virtual"},
                {"opportunityId": "o5", "sweeperRehashLastName": "Tyler Diamond"},
                {"opportunityId": "", "sweeperRehashLastName": "Diamond"},
                {"opportunityId": "o6", "sweeperRehashLastName": "N/A"},
            ]
        }
        rows = metrics.created_rows(payload)
        self.assertEqual([row["opportunityId"] for row in rows], ["o1", "o4"])

    def test_demos_count_sits_and_ran_includes_no_demo(self):
        demo = {
            "rows": [
                {"opportunityId": "a", "sweeperRehashLastName": "Diamond", "disposition": "Sit", "pipeline": "Rehash"},
                {"opportunityId": "a", "sweeperRehashLastName": "diamond", "disposition": "Sit"},
                {"opportunityId": "b", "sweeperRehashLastName": "Diamond", "disposition": "No Sit"},
                {"opportunityId": "c", "sweeperRehashLastName": "Smith", "disposition": "Sit"},
                {"opportunityId": "d", "sweeperRehashLastName": None, "disposition": "Sit", "setter": "Diamond"},
                {"opportunityId": "e", "sweeperRehashLastName": " Diamond ", "disposition": "Sit"},
            ]
        }
        self.assertEqual(metrics.ran_and_demos(demo), (3, 2))
        self.assertEqual([row["opportunityId"] for row in metrics.demo_rows(demo)], ["a", "b", "e"])

    def test_rates_match_channel_ran_denominator(self):
        summary = metrics.summarize(opps_created=4, ran=2, demos=1, sales=1)
        self.assertEqual(summary["demo_pct"], 50.0)
        self.assertEqual(summary["opp2prelim"], 50.0)
        self.assertNotEqual(summary["demo_pct"], round(100 * 1 / 4, 1))
        self.assertNotEqual(summary["opp2prelim"], round(100 * 1 / 4, 1))

    def test_rates_are_blank_when_nothing_ran(self):
        summary = metrics.summarize(opps_created=3, ran=0, demos=0, sales=2)
        self.assertIsNone(summary["demo_pct"])
        self.assertIsNone(summary["opp2prelim"])
        self.assertEqual(summary["opps_created"], 3)
        self.assertEqual(summary["sales"], 2)

    def test_name_match_uses_sweeper_field_not_setter(self):
        tagged = {"customFields": [{"id": FIELD, "value": " diamond "}]}
        other = {"customFields": [{"id": FIELD, "value": "Smith"}]}
        setter_only = {"customFields": [{"id": "Eq4NLTSkJ56KTxbxypuE", "value": "Diamond"}]}
        self.assertTrue(metrics.name_matches(tagged, {}))
        self.assertTrue(metrics.name_matches({}, {"customFields": [{"id": FIELD, "value": "DIAMOND"}]}))
        self.assertFalse(metrics.name_matches(other, {}))
        self.assertFalse(metrics.name_matches(setter_only, {}))
        self.assertFalse(metrics.name_matches({}, {}))


class DiamondWindowTests(unittest.TestCase):
    def test_default_is_month_to_date_new_york(self):
        now = datetime(2026, 10, 15, 18, 0, tzinfo=NY)
        self.assertEqual(metrics.month_to_date(now), ("2026-10-01", "2026-10-15"))
        year, month, start, end = metrics.resolve_window({}, now)
        self.assertEqual((year, month, start, end), (2026, 10, "2026-10-01", "2026-10-15"))

    def test_explicit_dates_win_over_year_month(self):
        window = metrics.resolve_window({"start": ["2026-09-03"], "end": ["2026-09-09"], "year": ["2026"], "month": ["10"]})
        self.assertEqual(window, (2026, 9, "2026-09-03", "2026-09-09"))

    def test_year_month_is_a_full_month(self):
        self.assertEqual(metrics.resolve_window({"year": ["2026"], "month": ["9"]}), (2026, 9, None, None))

    def test_rejects_bad_ranges(self):
        with self.assertRaises(ValueError):
            metrics.resolve_window({"start": ["2026-10-15"], "end": ["2026-10-01"]})
        with self.assertRaises(ValueError):
            metrics.resolve_window({"start": ["10/01/2026"], "end": ["2026-10-15"]})
        with self.assertRaises(ValueError):
            metrics.resolve_window({"year": ["2026"]})


class DiamondComputeTests(unittest.TestCase):
    def test_compute_filters_created_demos_and_sales(self):
        created = {
            "window_start_local": "2026-10-01T00:00:00-04:00",
            "window_end_local": "2026-10-16T00:00:00-04:00",
            "sample_rows": [
                {"opportunityId": "o1", "sweeperRehashLastName": "Diamond", "pipeline": "Rehash", "createdAt": "2026-10-02"},
                {"opportunityId": "o2", "sweeperRehashLastName": "Smith"},
            ],
        }
        demo = {
            "rows": [
                {"opportunityId": "d1", "sweeperRehashLastName": "Diamond", "disposition": "Sit", "pipeline": "Buffalo", "frozenAppointmentOccurredAt": "2026-10-03"},
                {"opportunityId": "d2", "sweeperRehashLastName": "Diamond", "disposition": "No Sit", "pipeline": "Rehash"},
                {"opportunityId": "d3", "sweeperRehashLastName": "Smith", "disposition": "Sit"},
            ]
        }
        tagged = {"customFields": [{"id": FIELD, "value": "Diamond"}]}

        def fake_sales(db, contract, **kwargs):
            hook = kwargs["on_sale"]
            hook(opp={"id": "s1"}, contact=tagged, contact_id="c1", sold_date="2026-10-04", salesperson="Closer")
            hook(opp={"id": "s1b"}, contact=tagged, contact_id="c1", sold_date="2026-10-04", salesperson="Closer")
            hook(opp={"id": "s2"}, contact={}, contact_id="c2", sold_date="2026-10-05", salesperson="Closer")
            self.assertEqual(kwargs["start"], "2026-10-01")
            self.assertEqual(kwargs["end"], "2026-10-15")
            self.assertEqual(kwargs["tz"], "America/New_York")
            return {"window_start_local": "s", "window_end_local": "e"}

        def fake_created(db, contract, **kwargs):
            self.assertEqual(kwargs["pipeline_scope"], "all")
            self.assertEqual(kwargs["start"], "2026-10-01")
            self.assertEqual(kwargs["end"], "2026-10-15")
            self.assertNotIn("setter_last_name", kwargs)
            return created

        with (
            mock.patch("opportunities_created.compute", side_effect=fake_created),
            mock.patch("demo_rate.build_payload", return_value=demo) as demo_mock,
            mock.patch("sales.compute_sales", side_effect=fake_sales),
        ):
            out = metrics.compute_diamond_sweeper(object(), year=2026, month=10, start="2026-10-01", end="2026-10-15")
        self.assertEqual(out["opps_created"], 1)
        self.assertEqual(out["ran"], 2)
        self.assertEqual(out["demos"], 1)
        self.assertEqual(out["sales"], 1)
        self.assertEqual(out["demo_pct"], 50.0)
        self.assertEqual(out["opp2prelim"], 50.0)
        self.assertEqual(out["last_name"], "Diamond")
        self.assertEqual(out["title"], "Diamond — Sweeper/Rehash")
        self.assertEqual([row["opportunityId"] for row in out["created_rows"]], ["o1"])
        self.assertEqual(out["sale_rows"][0]["contactId"], "c1")
        self.assertIn("ghl_opportunities_v2", out["contract"]["collections"])
        self.assertIn("ghl_contacts_v2", out["contract"]["collections"])
        self.assertIn(FIELD, out["contract"]["field"])
        demo_mock.assert_called_once()
        self.assertEqual(
            demo_mock.call_args.args[1:],
            (2026, 10, {}, "2026-10-01", "2026-10-15"),
        )


class DiamondPageTests(unittest.TestCase):
    def test_page_is_open_and_wired(self):
        html = page.render_html()
        src = (API / "diamond_sweeper.py").read_text(encoding="utf-8")
        self.assertIn("<title>Diamond — Sweeper/Rehash</title>", html)
        self.assertIn("<h1>Diamond — Sweeper/Rehash</h1>", html)
        self.assertIn('class="navlink active" href="/api/diamond_sweeper"', html)
        self.assertIn("/api/metrics/diamond_sweeper?", html)
        self.assertIn("pipeline_scope", html)
        self.assertIn("hsOpsPresetButtons", html)
        self.assertIn('data-oc-native-filters="1"', html)
        self.assertIn("America/New_York", html)
        self.assertIn("Demos / appointments ran", html)
        self.assertIn("Sales / appointments ran", html)
        self.assertIn("ghl_opportunities_v2", html)
        self.assertIn("ghl_contacts_v2", html)
        self.assertIn(FIELD, html)
        self.assertNotIn("SETTINGS_PASSWORD", src)
        self.assertNotIn("def _check_auth", src)
        self.assertNotIn("WWW-Authenticate", src)

    def test_nav_lists_diamond_under_sales(self):
        html = render_dashboard_nav("diamond_sweeper")
        sales_items = next(items for label, items in nav.NAV_GROUPS if label == "SALES")
        sales_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Sales")
        self.assertIn(("diamond_sweeper", "Diamond Sweeper", "/api/diamond_sweeper"), sales_items)
        self.assertIn("diamond_sweeper", sales_keys)
        self.assertIn('class="navlink active" href="/api/diamond_sweeper"', html)
        self.assertIn("Diamond Sweeper", html)
        nav.embed_menu_plan()

    def test_index_dispatches_both_routes(self):
        self.assertEqual(index.dispatch_route("/api/diamond_sweeper"), "diamond_sweeper")
        self.assertEqual(index.dispatch_file("diamond_sweeper"), API / "diamond_sweeper.py")
        self.assertEqual(index.dispatch_route("/api/metrics/diamond_sweeper"), "metrics/diamond_sweeper")
        self.assertEqual(index.dispatch_file("metrics/diamond_sweeper"), METRICS / "diamond_sweeper.py")


if __name__ == "__main__":
    unittest.main()
