# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import inspect
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


funnel = load_module("website_funnel_metric", METRICS / "website_funnel.py")
page = load_module("website_funnel_page", API / "website_funnel.py")
nav = load_module("dashboard_nav_website_funnel", API / "dashboard_nav.py")

WARM = (API / "warm_cache.py").read_text()
SALES = (METRICS / "sales.py").read_text()
CREATED = (METRICS / "opportunities_created.py").read_text()
DEMO = (METRICS / "demo_rate.py").read_text()
FUNNEL_SRC = (METRICS / "website_funnel.py").read_text()
PAGE_SRC = (API / "website_funnel.py").read_text()
ROLLUP_SRC = (API / "web_funnel_rollup.py").read_text()


class WebsiteFunnelIsolationTests(unittest.TestCase):
    def test_website_funnel_is_not_referenced_from_warm_cache(self):
        self.assertNotIn("website_funnel", WARM)
        self.assertNotIn("web_funnel", WARM)
        self.assertNotIn("web_funnel_daily_v1", WARM)
        self.assertIn("urls = []", WARM)

    def test_locked_metric_contracts_are_unchanged(self):
        self.assertNotIn("website_funnel", SALES)
        self.assertNotIn("web_funnel", SALES)
        self.assertIn("P9oBjgbZjJdeE0OkBj9T", SALES)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", SALES)
        self.assertIn("COUNT_DISTINCT(ghl_opportunities_v2.contactId)", SALES)

        self.assertNotIn("website_funnel", CREATED)
        self.assertNotIn("web_funnel", CREATED)
        self.assertIn("inbound/lead locker", CREATED)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", CREATED)

        self.assertNotIn("website_funnel", DEMO)
        self.assertNotIn("web_funnel", DEMO)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", DEMO)
        self.assertIn('dispositionValue == "Sit"', DEMO)

    def test_funnel_does_not_use_sold_date_or_lead_gen_field(self):
        lookup_src = "\n".join(
            [
                inspect.getsource(funnel.custom_field_value),
                inspect.getsource(funnel.is_website_attributed),
                inspect.getsource(funnel.lead_attribution),
                inspect.getsource(funnel.compute_ghl_website_leads_for_day),
            ]
        )
        self.assertNotIn("hd5QqHEOVSsPom5bJ32P", lookup_src)
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", lookup_src)
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", PAGE_SRC)
        self.assertNotIn("hd5QqHEOVSsPom5bJ32P", PAGE_SRC)
        self.assertNotIn("hd5QqHEOVSsPom5bJ32P", ROLLUP_SRC)
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", ROLLUP_SRC)


class WebsiteFunnelContractTests(unittest.TestCase):
    def test_daily_collection_name(self):
        self.assertEqual(funnel.DAILY_COLLECTION, "web_funnel_daily_v1")
        self.assertIn('DAILY_COLLECTION = "web_funnel_daily_v1"', FUNNEL_SRC)
        self.assertIn("DAILY_COLLECTION", inspect.getsource(funnel.rollup_day))
        self.assertIn("DAILY_COLLECTION", inspect.getsource(funnel.read_month_docs))
        self.assertIn("web_funnel_daily_v1", FUNNEL_SRC)

    def test_compute_path_does_not_stream_ghl_collections(self):
        compute_src = "\n".join(
            [
                inspect.getsource(funnel.compute_ghl_website_leads_for_day),
                inspect.getsource(funnel._query_opps_created_in_window),
                inspect.getsource(funnel.fetch_contacts_by_ids),
                inspect.getsource(funnel.compute_month),
                inspect.getsource(funnel.read_month_docs),
                inspect.getsource(funnel.rollup_day),
                FUNNEL_SRC,
            ]
        )
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', compute_src)
        self.assertNotIn('db.collection("ghl_contacts_v2").stream()', compute_src)
        self.assertIn('col.where("createdAt", ">=", lower).where("createdAt", "<", upper).stream()', FUNNEL_SRC)
        self.assertIn("db.get_all", inspect.getsource(funnel.fetch_contacts_by_ids))
        self.assertIn("db.get_all", inspect.getsource(funnel.read_month_docs))

    def test_field_id_constants_exist_and_may_be_empty(self):
        self.assertEqual(funnel.WEBSITE_LANDING_PAGE_FIELD_NAME, "Website Landing Page")
        self.assertEqual(funnel.WEBSITE_PAGE_GROUP_FIELD_NAME, "Website Page Group")
        self.assertEqual(funnel.WEBSITE_UTM_FIELD_NAME, "Website UTM")
        self.assertEqual(funnel.GA_CLIENT_ID_FIELD_NAME, "GA Client ID")
        self.assertIsInstance(funnel.WEBSITE_LANDING_PAGE_FIELD_ID, str)
        self.assertIsInstance(funnel.WEBSITE_PAGE_GROUP_FIELD_ID, str)
        self.assertIsInstance(funnel.WEBSITE_UTM_FIELD_ID, str)
        self.assertIsInstance(funnel.GA_CLIENT_ID_FIELD_ID, str)

    def test_ga4_env_names_are_documented(self):
        self.assertEqual(funnel.GA4_PROPERTY_ID_ENV, "GA4_PROPERTY_ID")
        self.assertEqual(funnel.GA4_SERVICE_ACCOUNT_JSON_ENV, "GA4_SERVICE_ACCOUNT_JSON")
        self.assertEqual(funnel.GA4_MEASUREMENT_ID, "G-V02RZFR4SZ")
        self.assertIn("GA4_PROPERTY_ID", FUNNEL_SRC)
        self.assertIn("GA4_SERVICE_ACCOUNT_JSON", FUNNEL_SRC)
        self.assertIn("FIREBASE_SERVICE_ACCOUNT_JSON", FUNNEL_SRC)


class WebsiteFunnelHtmlTests(unittest.TestCase):
    def test_dashboard_html_includes_eight_kpi_names_and_goal_rates(self):
        html = funnel.render_html(2026, 8)
        for name in (
            "GHL website leads",
            "Session → GHL lead",
            "Submit → GHL lead",
            "Estimate start → submit",
            "Session → estimate start",
            "Page contribution",
            "Orphan Wix submits",
            "Attributed source coverage",
        ):
            self.assertIn(name, html)
        for rate in ("1.5%", "≥95%", "25%", "8%", "6%", "12%", "10%", "70%", "≥90%"):
            self.assertIn(rate, html)
        self.assertIn("baseline pending", html)
        self.assertIn("Goal 0", html)
        self.assertIn("/contact-me submits are orphans until wired", html)
        self.assertIn("home / buffalo / rochester / syracuse / ny-incentives / calculator / contact-me", html)

    def test_page_handler_renders_same_kpis(self):
        html = page.render_html(2026, 8)
        self.assertIn("GHL website leads", html)
        self.assertIn("Website Funnel", html)
        self.assertIn('href="/api/website_funnel"', html)


class WebsiteFunnelNavTests(unittest.TestCase):
    def test_nav_lists_website_funnel_after_project_management(self):
        html = nav.render_dashboard_nav("website_funnel")
        self.assertIn('href="/api/website_funnel"', html)
        self.assertIn("Website Funnel", html)
        self.assertLess(html.find("Project Management"), html.find("Website Funnel"))
        self.assertIn('class="navbtn active" href="/api/website_funnel"', html)
        self.assertNotIn('summary class="navbtn active"', html)

    def test_pm_dropdown_still_active_for_hub(self):
        html = nav.render_dashboard_nav("project_management_hub")
        self.assertIn('summary class="navbtn active"', html)
        self.assertIn("Project Management Hub", html)
        self.assertIn("Website Funnel", html)


class WebsiteFunnelLogicTests(unittest.TestCase):
    def test_website_attribution_by_source_and_named_fields(self):
        self.assertTrue(funnel.is_website_attributed({"source": "Website"}, {}))
        self.assertFalse(funnel.is_website_attributed({"source": "doors"}, {"customFields": []}))
        contact = {
            "customFields": [
                {"name": "Website Landing Page", "value": "/buffalo"},
            ]
        }
        self.assertTrue(funnel.is_website_attributed({"source": "facebook"}, contact))
        self.assertFalse(
            funnel.is_website_attributed(
                {"source": "facebook"},
                {"customFields": [{"name": "Website Landing Page", "value": "  "}]},
            )
        )

    def test_page_group_from_landing(self):
        self.assertEqual(funnel.page_group_from_landing("/"), "home")
        self.assertEqual(funnel.page_group_from_landing("https://happysolar.com/buffalo"), "city_buffalo")
        self.assertEqual(funnel.page_group_from_landing("/rochester-solar"), "city_rochester")
        self.assertEqual(funnel.page_group_from_landing("/syracuse"), "city_syracuse")
        self.assertEqual(funnel.page_group_from_landing("/ny-incentives"), "ny_incentives")
        self.assertEqual(funnel.page_group_from_landing("/calculator"), "calculator")
        self.assertEqual(funnel.page_group_from_landing("/contact-me"), "contact_me")
        self.assertEqual(funnel.page_group_from_landing("/blog/hello"), "other")
        self.assertEqual(funnel.normalize_page_group("Buffalo"), "city_buffalo")

    def test_orphans_zero_when_ga4_missing(self):
        self.assertEqual(funnel.compute_orphans(12, 1, "not_configured"), 0)
        self.assertEqual(funnel.compute_orphans(12, 1, "ok"), 11)
        self.assertEqual(funnel.compute_orphans(1, 4, "ok"), 0)

    def test_month_aggregation_and_baseline_pending(self):
        docs = [
            {
                "date": "2026-08-01",
                "sessions": 100,
                "starts": 10,
                "submits": 4,
                "ghl_leads": 3,
                "orphans": 1,
                "attributed_leads": 3,
                "ga4": "ok",
                "by_page": {
                    "home": {"sessions": 80, "starts": 5, "submits": 2, "ghl_leads": 2},
                    "contact_me": {"sessions": 20, "starts": 0, "submits": 0, "ghl_leads": 1},
                },
                "by_source": {"website": 3},
            },
            {
                "date": "2026-08-02",
                "sessions": 100,
                "starts": 6,
                "submits": 1,
                "ghl_leads": 1,
                "orphans": 0,
                "attributed_leads": 1,
                "ga4": "ok",
                "by_page": {
                    "home": {"sessions": 100, "starts": 6, "submits": 1, "ghl_leads": 1},
                },
                "by_source": {"website": 1},
            },
        ]
        payload = funnel.aggregate_daily_docs(docs, year=2026, month=8)
        self.assertEqual(payload["collection"], "web_funnel_daily_v1")
        self.assertEqual(payload["totals"]["sessions"], 200)
        self.assertEqual(payload["totals"]["ghl_leads"], 4)
        self.assertEqual(payload["kpis"]["ghl_website_leads"]["status"], "baseline_pending")
        self.assertEqual(payload["kpis"]["ghl_website_leads"]["goal_label"], "baseline pending")
        self.assertAlmostEqual(payload["kpis"]["session_to_ghl_lead"]["value"], 0.02)
        self.assertEqual(payload["kpis"]["session_to_ghl_lead"]["status"], "hit")
        self.assertEqual(payload["kpis"]["submit_to_ghl_lead"]["status"], "miss")
        self.assertGreater(len(payload["missing_dates"]), 0)
        self.assertIn("do not count as leads", " ".join(payload["notes"]).lower())

    def test_missing_docs_and_ga4_not_configured_are_plain(self):
        empty = funnel.aggregate_daily_docs([], year=2026, month=8)
        self.assertEqual(empty["ga4"], "missing_docs")
        self.assertTrue(any("No daily warehouse docs" in note for note in empty["notes"]))

        docs = [{"date": "2026-08-01", "ga4": "not_configured", "ghl_leads": 2, "orphans": 0}]
        partial = funnel.aggregate_daily_docs(docs, year=2026, month=8)
        self.assertEqual(partial["ga4"], "not_configured")
        self.assertTrue(any("not_configured" in note for note in partial["notes"]))

    def test_rollup_endpoint_exists_and_is_not_cronned(self):
        self.assertIn("rollup_day", ROLLUP_SRC)
        vercel = (ROOT / "vercel.json").read_text()
        self.assertNotIn("web_funnel", vercel)
        self.assertNotIn("website_funnel", vercel)


if __name__ == "__main__":
    unittest.main()
