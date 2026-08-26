# -*- coding: utf-8 -*-

"""Website Funnel — completed-form contract. Isolated from sales/demo/opps."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

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
ESSENTIAL = (METRICS / "essential_sales.py").read_text()
CREATED = (METRICS / "opportunities_created.py").read_text()
DEMO = (METRICS / "demo_rate.py").read_text()
FUNNEL_SRC = (METRICS / "website_funnel.py").read_text()
PAGE_SRC = (API / "website_funnel.py").read_text()
ROLLUP_SRC = (API / "web_funnel_rollup.py").read_text()
YESTERDAY_SRC = (API / "website_funnel_yesterday.py").read_text()

FAMILY_PATHS = (
    METRICS / "website_funnel.py",
    API / "website_funnel.py",
    API / "web_funnel_rollup.py",
    API / "website_funnel_yesterday.py",
)
FAMILY_TEXT = FUNNEL_SRC + "\n" + PAGE_SRC + "\n" + ROLLUP_SRC + "\n" + YESTERDAY_SRC

FORBIDDEN_GHL = (
    "ghl_contacts_v2",
    "ghl_opportunities_v2",
    "ghl_custom_fields_v2",
    "Website Landing Page",
    "Website Page Group",
    "Website UTM",
    "Website GA Client ID",
    "GA Client ID",
    "ghl_leads",
    "attributed_leads",
    "orphan",
    "Submit → GHL",
    "GHL website leads",
    "opportunity.source",
    "hd5QqHEOVSsPom5bJ32P",
    "P9oBjgbZjJdeE0OkBj9T",
)

DROPPED_HELPERS = (
    "compute_ghl_website_leads_for_day",
    "_query_opps_created_in_window",
    "fetch_contacts_by_ids",
    "compute_orphans",
    "is_website_attributed",
    "lead_attribution",
    "custom_field_value",
    "WEBSITE_FIELD_NAMES",
    "WEBSITE_LANDING_PAGE_FIELD_NAME",
    "WEBSITE_PAGE_GROUP_FIELD_NAME",
    "WEBSITE_UTM_FIELD_NAME",
    "GA_CLIENT_ID_FIELD_NAME",
    "OPP_COLLECTION",
    "CONTACT_COLLECTION",
    "GHL_LEAD_GOAL",
    "SUBMIT_TO_GHL_GOAL",
    "SESSION_TO_LEAD_GOAL",
)


class WebsiteFunnelIsolationTests(unittest.TestCase):
    def test_website_funnel_is_not_referenced_from_warm_cache(self):
        self.assertNotIn("website_funnel", WARM)
        self.assertNotIn("website_funnel_yesterday", WARM)
        self.assertNotIn("web_funnel", WARM)
        self.assertNotIn("web_funnel_daily_v1", WARM)
        self.assertIn("urls = []", WARM)
        self.assertNotIn("/api/website_funnel", WARM)
        self.assertNotIn("/api/website_funnel_yesterday", WARM)

    def test_locked_metric_contracts_are_unchanged(self):
        self.assertNotIn("website_funnel", SALES)
        self.assertNotIn("web_funnel", SALES)
        self.assertIn("P9oBjgbZjJdeE0OkBj9T", SALES)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", SALES)
        self.assertIn("COUNT_DISTINCT(ghl_opportunities_v2.contactId)", SALES)

        self.assertNotIn("website_funnel", ESSENTIAL)
        self.assertNotIn("web_funnel", ESSENTIAL)
        self.assertIn("from sales import SalesMetricContract, compute_sales, get_db", ESSENTIAL)

        self.assertNotIn("website_funnel", CREATED)
        self.assertNotIn("web_funnel", CREATED)
        self.assertIn("inbound/lead locker", CREATED)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", CREATED)

        self.assertNotIn("website_funnel", DEMO)
        self.assertNotIn("web_funnel", DEMO)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", DEMO)
        self.assertIn('dispositionValue == "Sit"', DEMO)

    def test_funnel_does_not_use_sold_date_or_lead_gen_field(self):
        self.assertNotIn("hd5QqHEOVSsPom5bJ32P", FAMILY_TEXT)
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", FAMILY_TEXT)


class WebsiteFunnelContractTests(unittest.TestCase):
    def test_daily_collection_name(self):
        self.assertEqual(funnel.DAILY_COLLECTION, "web_funnel_daily_v1")
        self.assertIn('DAILY_COLLECTION = "web_funnel_daily_v1"', FUNNEL_SRC)
        self.assertIn("DAILY_COLLECTION", inspect.getsource(funnel.rollup_day))
        self.assertIn("DAILY_COLLECTION", inspect.getsource(funnel.read_month_docs))
        self.assertIn("DAILY_COLLECTION", inspect.getsource(funnel.read_daily_doc))
        self.assertIn("get_all", inspect.getsource(funnel.read_daily_doc))
        self.assertNotIn(".stream(", inspect.getsource(funnel.read_daily_doc))
        self.assertNotIn(".stream(", inspect.getsource(funnel.compute_day_snapshot))

    def test_goals_are_completed_form_not_ghl(self):
        self.assertEqual(funnel.GOAL_SESSION_TO_FORM, 0.02)
        self.assertEqual(funnel.GOAL_START_TO_FORM, 0.25)
        self.assertEqual(funnel.GOAL_SESSION_TO_START_SITE, 0.08)
        self.assertEqual(funnel.GOAL_SESSION_TO_START_HOME, 0.06)
        self.assertEqual(funnel.GOAL_SESSION_TO_START_CITY, 0.12)
        self.assertEqual(funnel.GOAL_SESSION_TO_START_NY_INCENTIVES, 0.10)
        self.assertEqual(funnel.GOAL_SESSION_TO_START_CALCULATOR, 0.70)
        self.assertEqual(funnel.SCOREBOARD, "sessions → start → completed form")
        self.assertEqual(
            funnel.KPI_NAMES,
            (
                "Completed form",
                "Sessions → completed form",
                "Start → completed form",
                "Page contribution",
            ),
        )

    def test_family_has_no_ghl_or_orphan_contract(self):
        for path in FAMILY_PATHS:
            text = path.read_text()
            for token in FORBIDDEN_GHL:
                self.assertNotIn(token, text, f"{path.name} still mentions {token}")

    def test_metric_source_never_reads_ghl_collections(self):
        tree = ast.parse(FUNNEL_SRC)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn(node.value, ("ghl_contacts_v2", "ghl_opportunities_v2"))
        compute_src = "\n".join(
            [
                inspect.getsource(funnel.compute_month),
                inspect.getsource(funnel.read_month_docs),
                inspect.getsource(funnel.read_daily_doc),
                inspect.getsource(funnel.compute_day_snapshot),
                inspect.getsource(funnel.build_day_snapshot),
                inspect.getsource(funnel.rollup_day),
                inspect.getsource(funnel.fetch_ga4_event_counts),
                inspect.getsource(funnel.aggregate_daily_docs),
            ]
        )
        self.assertNotIn("ghl_opportunities_v2", compute_src)
        self.assertNotIn("ghl_contacts_v2", compute_src)
        self.assertNotIn("createdAt", compute_src)
        self.assertNotIn("customFields", compute_src)

    def test_dropped_ghl_helpers_are_gone(self):
        for name in DROPPED_HELPERS:
            self.assertFalse(hasattr(funnel, name), name)

    def test_ga4_env_names_are_documented(self):
        self.assertEqual(funnel.GA4_PROPERTY_ID_ENV, "GA4_PROPERTY_ID")
        self.assertEqual(funnel.GA4_SERVICE_ACCOUNT_JSON_ENV, "GA4_SERVICE_ACCOUNT_JSON")
        self.assertEqual(funnel.GA4_MEASUREMENT_ID, "G-V02RZFR4SZ")
        self.assertIn("FIREBASE_SERVICE_ACCOUNT_JSON", FUNNEL_SRC)
        self.assertNotIn("secretmanager", FUNNEL_SRC.lower())
        self.assertNotIn("SECRET_MANAGER", FUNNEL_SRC)
        self.assertNotIn("GHL_API_KEY", FUNNEL_SRC)
        self.assertNotIn("API_KEY", FUNNEL_SRC)

    def test_handlers_exist_and_do_not_mention_ghl(self):
        self.assertNotIn("ghl_", PAGE_SRC)
        self.assertNotIn("ghl_", ROLLUP_SRC)
        self.assertNotIn("ghl_", FUNNEL_SRC)
        self.assertNotIn("ghl_", YESTERDAY_SRC)
        self.assertNotIn("GHL", PAGE_SRC)
        self.assertNotIn("GHL", ROLLUP_SRC)
        self.assertNotIn("GHL", FUNNEL_SRC)
        self.assertNotIn("GHL", YESTERDAY_SRC)
        self.assertNotIn("FIELD_NAME", FUNNEL_SRC)
        self.assertIn("compute_month", PAGE_SRC)
        self.assertIn("compute_day_snapshot", PAGE_SRC)
        self.assertIn("compute_day_snapshot", YESTERDAY_SRC)
        self.assertIn("rollup_day", ROLLUP_SRC)
        self.assertIn("sessions → start → completed form", PAGE_SRC)
        self.assertIn("completed form", PAGE_SRC)


class WebsiteFunnelHtmlTests(unittest.TestCase):
    def test_dashboard_html_uses_completed_form_kpis(self):
        html = funnel.render_html(2026, 8)
        self.assertIn("sessions → start → completed form", html)
        for name in (
            "Completed form",
            "Sessions → completed form",
            "Start → completed form",
            "Page contribution",
        ):
            self.assertIn(name, html)
        self.assertNotIn("Completed form submits", html)
        self.assertNotIn(">Session → completed form<", html)
        self.assertNotIn("Estimate start → completed form", html)
        self.assertNotIn("Session → estimate start", html)
        self.assertIn("baseline pending", html)
        self.assertIn("Goal 2%", html)
        self.assertIn("Goal 25%", html)
        self.assertIn("site 8%", html)
        self.assertIn("home 6%", html)
        self.assertIn("city 12%", html)
        self.assertIn("ny-incentives 10%", html)
        self.assertIn("calculator-direct 70%", html)
        self.assertIn("Sessions → start", html)
        self.assertIn("not scored", html.lower())
        self.assertIn("home / buffalo / rochester / syracuse / ny-incentives / calculator / contact-me", html)
        self.assertIn("estimate_submit / estimate_start", html)
        self.assertIn("Total site visits", html)
        self.assertIn("wny.happyslr.com visits", html)
        self.assertIn("Forms completed", html)
        self.assertIn("forms completed / wny.happyslr.com visits", html)
        self.assertIn("forms completed / total site visits", html)
        self.assertIn("id=\"visitsChart\"", html)
        self.assertIn("id=\"rateChart\"", html)
        self.assertNotIn("GHL", html)
        self.assertNotIn("orphan", html.lower())
        self.assertNotIn("Submit → GHL", html)
        self.assertNotIn("ghl_leads", html)
        self.assertNotIn("Designer", html)
        self.assertNotIn("1.5%", html)
        self.assertNotIn("≥95%", html)
        self.assertNotIn("estimate_cta_click", html)
        self.assertNotIn("wix_form_submit", html)

    def test_page_handler_renders_same_kpis(self):
        html = page.render_html(2026, 8)
        self.assertIn("Completed form", html)
        self.assertIn("sessions → start → completed form", html)
        self.assertIn("Website Funnel", html)
        self.assertIn('href="/api/website_funnel"', html)
        self.assertNotIn("GHL website leads", html)


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
        self.assertEqual(funnel.normalize_page_group("contact-me"), "contact_me")

    def test_completed_form_math_and_calculator_only_start_to_form(self):
        self.assertEqual(funnel.sum_completed_forms(2, 3), 5)
        self.assertIsNone(funnel.sum_completed_forms(None, None))
        self.assertEqual(funnel.ratio(2, 100), 0.02)
        self.assertIsNone(funnel.ratio(1, 0))
        self.assertEqual(funnel.ratio(10, 40), 0.25)
        self.assertNotEqual(funnel.ratio(13, 40), funnel.ratio(10, 40))

    def test_daily_doc_fields_are_completed_form_not_ghl(self):
        doc = funnel.build_daily_doc(
            "2026-08-18",
            {
                "ga4": "ok",
                "sessions": 100,
                "cta_clicks": 10,
                "starts": 8,
                "address_complete": 6,
                "bill_complete": 5,
                "estimate_submit": 2,
                "wix_form_submits": 1,
                "completed_forms": 3,
                "by_page": {
                    "home": {"sessions": 80, "starts": 5, "completed_forms": 2},
                    "contact_me": {"sessions": 5, "starts": 0, "completed_forms": 1},
                },
                "error": None,
            },
        )
        for key in (
            "date",
            "sessions",
            "cta_clicks",
            "starts",
            "address_complete",
            "bill_complete",
            "completed_forms",
            "by_page",
            "ga4",
            "generated_at",
        ):
            self.assertIn(key, doc)
        self.assertEqual(doc["completed_forms"], 3)
        self.assertEqual(doc["estimate_submit"], 2)
        self.assertEqual(doc["wix_form_submits"], 1)
        self.assertEqual(doc["by_page"]["contact_me"]["completed_forms"], 1)
        self.assertNotIn("ghl_leads", doc)
        self.assertNotIn("orphans", doc)
        self.assertNotIn("attributed_leads", doc)
        self.assertNotIn("ghl_leads", doc["by_page"]["home"])
        self.assertNotIn("orphans", doc["by_page"]["home"])

    def test_contact_me_counts_in_volume_and_session_not_start_to_form(self):
        docs = [
            {
                "date": "2026-08-01",
                "sessions": 100,
                "cta_clicks": 12,
                "starts": 8,
                "address_complete": 6,
                "bill_complete": 5,
                "estimate_submit": 2,
                "wix_form_submits": 3,
                "completed_forms": 5,
                "ga4": "ok",
                "by_page": {
                    "home": {"sessions": 70, "starts": 4, "completed_forms": 1},
                    "calculator": {"sessions": 10, "starts": 4, "completed_forms": 1},
                    "contact_me": {"sessions": 8, "starts": 0, "completed_forms": 3},
                },
            },
            {
                "date": "2026-08-02",
                "sessions": 100,
                "cta_clicks": 8,
                "starts": 8,
                "address_complete": 6,
                "bill_complete": 4,
                "estimate_submit": 2,
                "wix_form_submits": 0,
                "completed_forms": 2,
                "ga4": "ok",
                "by_page": {
                    "home": {"sessions": 80, "starts": 4, "completed_forms": 1},
                    "city_buffalo": {"sessions": 20, "starts": 4, "completed_forms": 1},
                },
            },
        ]
        payload = funnel.aggregate_daily_docs(docs, year=2026, month=8)
        self.assertEqual(payload["collection"], "web_funnel_daily_v1")
        self.assertEqual(payload["totals"]["sessions"], 200)
        self.assertEqual(len(payload["days"]), 31)
        self.assertEqual(payload["days"][0]["date"], "2026-08-01")
        self.assertIsNone(payload["days"][0]["visits_total"])
        self.assertIsNone(payload["days"][0]["visits_wny"])
        self.assertIsNone(payload["days"][0]["completed_forms"])
        self.assertEqual(len(payload["running"]), 31)
        self.assertIsNone(payload["running"][0]["forms_over_total"])
        self.assertEqual(payload["totals"]["starts"], 16)
        self.assertEqual(payload["totals"]["estimate_submit"], 4)
        self.assertEqual(payload["totals"]["wix_form_submits"], 3)
        self.assertEqual(payload["totals"]["completed_forms"], 7)
        self.assertNotIn("ghl_leads", payload["totals"])
        self.assertNotIn("orphans", payload)
        self.assertNotIn("attributed_leads", payload)
        self.assertNotIn("ghl_website_leads", payload["kpis"])
        self.assertNotIn("submit_to_ghl_lead", payload["kpis"])
        self.assertEqual(payload["scoreboard"], "sessions → start → completed form")
        self.assertEqual(payload["kpis"]["completed_form"]["name"], "Completed form")
        self.assertEqual(payload["kpis"]["sessions_to_completed_form"]["name"], "Sessions → completed form")
        self.assertEqual(payload["kpis"]["start_to_completed_form"]["name"], "Start → completed form")
        self.assertEqual(payload["kpis"]["completed_form"]["status"], "baseline_pending")
        self.assertEqual(payload["kpis"]["completed_form"]["goal_label"], "baseline pending")
        self.assertAlmostEqual(payload["kpis"]["sessions_to_completed_form"]["value"], 7 / 200)
        self.assertEqual(payload["kpis"]["sessions_to_completed_form"]["goal"], 0.02)
        self.assertEqual(payload["kpis"]["sessions_to_completed_form"]["status"], "hit")
        self.assertAlmostEqual(payload["kpis"]["start_to_completed_form"]["value"], 4 / 16)
        self.assertNotAlmostEqual(payload["kpis"]["start_to_completed_form"]["value"], 7 / 16)
        self.assertEqual(payload["kpis"]["start_to_completed_form"]["scope"], "calculator_only")
        self.assertEqual(payload["kpis"]["start_to_completed_form"]["status"], "hit")
        self.assertEqual(payload["by_page"]["contact_me"]["completed_forms"], 3)
        self.assertAlmostEqual(payload["kpis"]["page_contribution"]["value"]["contact_me"], 3 / 7)
        self.assertEqual(payload["secondary"]["sessions_to_start"]["name"], "Sessions → start")
        self.assertFalse(payload["secondary"]["sessions_to_start"]["scored"])
        self.assertFalse(payload["secondary"]["address_complete"]["scored"])
        self.assertFalse(payload["secondary"]["bill_complete"]["scored"])
        self.assertGreater(len(payload["missing_dates"]), 0)
        notes = " ".join(payload["notes"]).lower()
        self.assertIn("contact-me", notes)
        self.assertIn("calculator-only", notes)
        self.assertNotIn("orphan", notes)
        self.assertNotIn("ghl", notes)

    def test_missing_docs_and_ga4_not_configured_are_plain(self):
        empty = funnel.aggregate_daily_docs([], year=2026, month=8)
        self.assertEqual(empty["ga4"], "missing_docs")
        self.assertTrue(any("No daily warehouse docs" in note for note in empty["notes"]))

        docs = [{"date": "2026-08-01", "ga4": "not_configured"}]
        partial = funnel.aggregate_daily_docs(docs, year=2026, month=8)
        self.assertEqual(partial["ga4"], "not_configured")
        self.assertIsNone(partial["totals"]["sessions"])
        self.assertIsNone(partial["totals"]["completed_forms"])
        self.assertTrue(any("not_configured" in note for note in partial["notes"]))
        self.assertTrue(any("not faked" in note for note in partial["notes"]))

    def test_ga4_missing_creds_does_not_invent_traffic(self):
        with patch.object(funnel, "ga4_credentials_available", return_value=False):
            out = funnel.fetch_ga4_event_counts("2026-08-18")
        self.assertEqual(out["ga4"], "not_configured")
        self.assertIsNone(out["sessions"])
        self.assertIsNone(out["visits_total"])
        self.assertIsNone(out["visits_wny"])
        self.assertIsNone(out["starts"])
        self.assertIsNone(out["estimate_submit"])
        self.assertIsNone(out["wix_form_submits"])
        self.assertIsNone(out["completed_forms"])

    def test_rollup_writes_completed_forms_not_ghl_fields(self):
        captured = {}

        class FakeDoc:
            def set(self, payload, merge=True):
                captured.update(payload)

        class FakeCol:
            def document(self, _id):
                return FakeDoc()

        class FakeDb:
            def collection(self, name):
                self.name = name
                return FakeCol()

        ga4 = {
            "ga4": "ok",
            "sessions": 100,
            "cta_clicks": 10,
            "starts": 8,
            "address_complete": 6,
            "bill_complete": 5,
            "estimate_submit": 2,
            "wix_form_submits": 1,
            "completed_forms": 3,
            "by_page": {
                "home": {"sessions": 80, "starts": 5, "completed_forms": 2},
                "contact_me": {"sessions": 5, "starts": 0, "completed_forms": 1},
            },
            "error": None,
        }
        db = FakeDb()
        with patch.object(funnel, "fetch_ga4_event_counts", return_value=ga4):
            out = funnel.rollup_day(db, "2026-08-18")
        self.assertEqual(db.name, "web_funnel_daily_v1")
        self.assertEqual(out["collection"], "web_funnel_daily_v1")
        self.assertEqual(out["doc"]["completed_forms"], 3)
        self.assertEqual(out["doc"]["estimate_submit"], 2)
        self.assertEqual(out["doc"]["wix_form_submits"], 1)
        self.assertNotIn("ghl_leads", out["doc"])
        self.assertNotIn("orphans", out["doc"])
        self.assertNotIn("attributed_leads", out["doc"])
        self.assertEqual(captured["completed_forms"], 3)
        self.assertEqual(captured["by_page"]["contact_me"]["completed_forms"], 1)
        self.assertNotIn("ghl_leads", captured)

    def test_rollup_endpoint_exists_and_is_not_cronned(self):
        self.assertIn("rollup_day", ROLLUP_SRC)
        vercel = (ROOT / "vercel.json").read_text()
        self.assertNotIn("web_funnel", vercel)
        self.assertNotIn("website_funnel", vercel)
        self.assertNotIn("website_funnel_yesterday", vercel)


class _RecordingDb:
    def __init__(self, snap):
        self.snap = snap
        self.collections = []
        self.get_all_refs = []

    def collection(self, name):
        self.collections.append(name)
        return self

    def document(self, doc_id):
        self.doc_id = doc_id
        return f"ref:{doc_id}"

    def get_all(self, refs):
        self.get_all_refs.extend(list(refs))
        return [self.snap]


class _Snap:
    def __init__(self, exists, doc_id, payload=None):
        self.exists = exists
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return self._payload


class WebsiteFunnelYesterdayTests(unittest.TestCase):
    def test_yesterday_window_is_ny_date_not_utc(self):
        utc = datetime(2026, 8, 21, 3, 30, tzinfo=timezone.utc)
        ny = utc.astimezone(ZoneInfo("America/New_York"))
        self.assertEqual(ny.date().isoformat(), "2026-08-20")
        self.assertEqual((utc.date() - timedelta(days=1)).isoformat(), "2026-08-20")
        with patch.object(funnel, "ny_now", return_value=ny):
            self.assertEqual(funnel.yesterday_ny_date(), "2026-08-19")
            self.assertEqual(funnel.resolve_query_date(None), "2026-08-19")
            self.assertEqual(funnel.resolve_query_date("yesterday"), "2026-08-19")
            window = funnel.ny_calendar_day_window(funnel.yesterday_ny_date())
        self.assertTrue(window["start"].startswith("2026-08-19T00:00:00"))
        self.assertIn("23:59:59", window["end"])
        self.assertEqual(window["timezone"], "America/New_York")
        self.assertEqual(window["kind"], "calendar_day")
        self.assertNotEqual(funnel.resolve_query_date("2026-08-19"), "2026-08-20")

    def test_missing_doc_is_ready_false_with_nulls(self):
        db = _RecordingDb(_Snap(False, "2026-08-19"))
        payload = funnel.compute_day_snapshot(db, "2026-08-19")
        self.assertEqual(db.collections, ["web_funnel_daily_v1"])
        self.assertEqual(db.get_all_refs, ["ref:2026-08-19"])
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["reason"], "source isn't ready")
        self.assertEqual(payload["ga4"], "missing")
        self.assertEqual(payload["lead_field"], "estimate_submit")
        self.assertIsNone(payload["lead"])
        for field in (
            "sessions",
            "estimate_start",
            "address_complete",
            "bill_complete",
            "estimate_submit",
            "session_to_submit",
            "start_to_submit",
            "session→submit",
            "start→submit",
            "starts",
        ):
            self.assertIn(field, payload)
            self.assertIsNone(payload[field])

    def test_not_configured_or_failed_doc_does_not_invent_counts(self):
        for ga4_status in ("not_configured", "failed"):
            db = _RecordingDb(
                _Snap(
                    True,
                    "2026-08-19",
                    {
                        "date": "2026-08-19",
                        "ga4": ga4_status,
                        "sessions": 0,
                        "starts": 0,
                        "address_complete": 0,
                        "bill_complete": 0,
                        "estimate_submit": 0,
                        "wix_form_submits": 0,
                    },
                )
            )
            payload = funnel.compute_day_snapshot(db, "2026-08-19")
            self.assertFalse(payload["ready"], ga4_status)
            self.assertEqual(payload["reason"], "source isn't ready")
            self.assertIsNone(payload["sessions"])
            self.assertIsNone(payload["estimate_start"])
            self.assertIsNone(payload["estimate_submit"])
            self.assertIsNone(payload["session_to_submit"])
            self.assertIsNone(payload["start_to_submit"])
            self.assertNotEqual(payload["sessions"], 0)

    def test_present_doc_fills_calculator_fields(self):
        db = _RecordingDb(
            _Snap(
                True,
                "2026-08-19",
                {
                    "date": "2026-08-19",
                    "ga4": "ok",
                    "sessions": 100,
                    "starts": 8,
                    "address_complete": 6,
                    "bill_complete": 5,
                    "estimate_submit": 2,
                    "wix_form_submits": 9,
                    "completed_forms": 11,
                },
            )
        )
        payload = funnel.compute_day_snapshot(db, "2026-08-19")
        self.assertTrue(payload["ready"])
        self.assertIsNone(payload["reason"])
        self.assertEqual(payload["scope"], "calculator")
        self.assertEqual(payload["site"], "wny.happyslr.com")
        self.assertEqual(payload["lead_field"], "estimate_submit")
        self.assertEqual(payload["lead"], 2)
        self.assertEqual(payload["sessions"], 100)
        self.assertEqual(payload["estimate_start"], 8)
        self.assertEqual(payload["starts"], 8)
        self.assertEqual(payload["address_complete"], 6)
        self.assertEqual(payload["bill_complete"], 5)
        self.assertEqual(payload["estimate_submit"], 2)
        self.assertAlmostEqual(payload["session_to_submit"], 0.02)
        self.assertAlmostEqual(payload["start_to_submit"], 0.25)
        self.assertEqual(payload["session→submit"], payload["session_to_submit"])
        self.assertEqual(payload["start→submit"], payload["start_to_submit"])
        self.assertNotEqual(payload["lead"], 9)
        self.assertNotEqual(payload["lead"], 11)
        self.assertFalse(payload["auto_rollup"])
        self.assertEqual(payload["reads"]["count"], 1)
        self.assertEqual(payload["reads"]["method"], "get_all")
        self.assertEqual(db.collections, ["web_funnel_daily_v1"])
        self.assertNotIn("ghl_contacts_v2", db.collections)
        self.assertNotIn("ghl_opportunities_v2", db.collections)

    def test_yesterday_read_does_not_touch_ghl_collections(self):
        tree = ast.parse(FUNNEL_SRC + "\n" + YESTERDAY_SRC)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn(node.value, ("ghl_contacts_v2", "ghl_opportunities_v2", "ghl_custom_fields_v2"))
        src = inspect.getsource(funnel.read_daily_doc) + inspect.getsource(funnel.compute_day_snapshot)
        self.assertNotIn("ghl_", src)
        self.assertNotIn(".stream(", src)
        self.assertIn("get_all", src)

    def test_zero_traffic_ok_day_is_ready_with_zeros(self):
        db = _RecordingDb(
            _Snap(
                True,
                "2026-08-19",
                {
                    "date": "2026-08-19",
                    "ga4": "ok",
                    "sessions": 0,
                    "starts": 0,
                    "address_complete": 0,
                    "bill_complete": 0,
                    "estimate_submit": 0,
                },
            )
        )
        payload = funnel.compute_day_snapshot(db, "2026-08-19")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["sessions"], 0)
        self.assertEqual(payload["estimate_submit"], 0)
        self.assertIsNone(payload["session_to_submit"])
        self.assertIsNone(payload["start_to_submit"])


class WebsiteFunnelHostSplitTests(unittest.TestCase):
    def test_host_allowlist_and_exclusions(self):
        self.assertEqual(funnel.classify_host("www.happyslr.com"), "total")
        self.assertEqual(funnel.classify_host("happyslr.com"), "total")
        self.assertEqual(funnel.classify_host("https://www.happyslr.com/buffalo"), "total")
        self.assertEqual(funnel.classify_host("wny.happyslr.com"), "wny")
        self.assertEqual(funnel.classify_host("WNY.happyslr.com"), "wny")
        for host in (
            "yadmada.com",
            "www.yadmada.com",
            "shop.yadmada.com",
            "happy-solar-git-qa-evan.vercel.app",
            "something.vercel.app",
            "localhost",
            "localhost:3000",
            "127.0.0.1",
            "gtm-msr.appspot.com",
            "www.gtm-msr.appspot.com",
            "",
            None,
        ):
            self.assertEqual(funnel.classify_host(host), "excluded", host)
        self.assertNotIn("session_start", funnel.GA4_EVENT_NAMES)
        self.assertEqual(funnel.EVENT_COUNT_FIELDS["page_view"], "sessions")
        self.assertIn("hostName", funnel.GA4_REPORT_DIMENSIONS)
        self.assertIn("pageLocation", funnel.GA4_REPORT_DIMENSIONS)
        self.assertEqual(inspect.getsource(funnel.fetch_ga4_event_counts).count("runReport"), 1)
        self.assertIn('qs.get("date"', ROLLUP_SRC)

    def test_preview_form_and_excluded_hosts_do_not_count(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {"event_name": "page_view", "host_name": "www.happyslr.com", "page_path": "/", "count": 200},
                {"event_name": "page_view", "host_name": "happyslr.com", "page_path": "/", "count": 151},
                {"event_name": "page_view", "host_name": "yadmada.com", "page_path": "/", "count": 40},
                {"event_name": "page_view", "host_name": "preview.vercel.app", "page_path": "/", "count": 12},
                {"event_name": "page_view", "host_name": "localhost", "page_path": "/", "count": 3},
                {"event_name": "page_view", "host_name": "gtm-msr.appspot.com", "page_path": "/", "count": 5},
                {"event_name": "page_view", "host_name": "wny.happyslr.com", "page_path": "/calculator", "count": 7},
                {
                    "event_name": "estimate_submit",
                    "host_name": "happy-solar-git-qa.vercel.app",
                    "page_path": "/calculator",
                    "page_location": "https://happy-solar-git-qa.vercel.app/calculator",
                    "count": 1,
                },
                {
                    "event_name": "wix_form_submit",
                    "host_name": "www.happyslr.com",
                    "page_path": "/contact-me",
                    "count": 2,
                },
            ]
        )
        self.assertEqual(out["visits_total"], 351)
        self.assertEqual(out["sessions"], 351)
        self.assertEqual(out["visits_wny"], 7)
        self.assertEqual(out["completed_forms"], 2)
        self.assertEqual(out["estimate_submit"], 0)
        self.assertEqual(out["wix_form_submits"], 2)
        self.assertGreater(out["dropped"]["host"], 0)
        self.assertEqual(out["by_page"]["home"]["sessions"], 351)
        self.assertNotEqual(out["visits_total"], 351 + 40 + 12 + 3 + 5)

    def test_debug_mode_and_internal_flags_drop_events(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {"event_name": "page_view", "host_name": "www.happyslr.com", "page_path": "/", "count": 10},
                {
                    "event_name": "page_view",
                    "host_name": "www.happyslr.com",
                    "page_path": "/",
                    "debug_mode": "true",
                    "count": 4,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "www.happyslr.com",
                    "page_path": "/calculator",
                    "debug_mode": "1",
                    "count": 1,
                },
                {
                    "event_name": "wix_form_submit",
                    "host_name": "happyslr.com",
                    "page_path": "/contact-me",
                    "traffic_type": "internal",
                    "count": 1,
                },
                {
                    "event_name": "estimate_submit",
                    "host_name": "wny.happyslr.com",
                    "page_path": "/calculator",
                    "page_location": "https://wny.happyslr.com/calculator?internal=1",
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
        self.assertEqual(out["completed_forms"], 1)
        self.assertEqual(out["estimate_submit"], 1)
        self.assertEqual(out["wix_form_submits"], 0)
        self.assertGreater(out["dropped"]["debug_mode"], 0)
        self.assertGreater(out["dropped"]["internal"], 0)
        self.assertIsNone(funnel.exclusion_reason(host_name="www.happyslr.com"))
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="www.happyslr.com",
                page_location="https://www.happyslr.com/?internal=1",
            ),
            "internal",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="www.happyslr.com", debug_mode="true"),
            "debug_mode",
        )

    def test_cumulative_ratio_null_on_zero_and_gaps(self):
        days = [
            {"date": "2026-08-01", "visits_total": None, "visits_wny": None, "completed_forms": None},
            {"date": "2026-08-02", "visits_total": 100, "visits_wny": 0, "completed_forms": 2},
            {"date": "2026-08-03", "visits_total": 50, "visits_wny": 10, "completed_forms": 1},
            {"date": "2026-08-04", "visits_total": 0, "visits_wny": 0, "completed_forms": 0},
        ]
        running = funnel.cumulative_form_ratios(days)
        self.assertIsNone(running[0]["forms_over_total"])
        self.assertIsNone(running[0]["forms_over_wny"])
        self.assertAlmostEqual(running[1]["forms_over_total"], 0.02)
        self.assertIsNone(running[1]["forms_over_wny"])
        self.assertAlmostEqual(running[2]["forms_over_total"], 3 / 150)
        self.assertAlmostEqual(running[2]["forms_over_wny"], 0.3)
        self.assertAlmostEqual(running[3]["forms_over_total"], 3 / 150)
        self.assertAlmostEqual(running[3]["forms_over_wny"], 0.3)
        zero = funnel.cumulative_form_ratios(
            [{"date": "2026-08-19", "visits_total": 0, "visits_wny": 0, "completed_forms": 1}]
        )
        self.assertIsNone(zero[0]["forms_over_total"])
        self.assertIsNone(zero[0]["forms_over_wny"])
        self.assertIsNone(funnel.ratio(1, 0))
        self.assertIsNone(funnel.ratio(0, 0))

    def test_month_json_days_use_nulls_until_host_split(self):
        docs = [
            {
                "date": "2026-08-19",
                "ga4": "ok",
                "sessions": 999,
                "completed_forms": 1,
            },
            {
                "date": "2026-08-20",
                "ga4": "ok",
                "visits_total": 209,
                "visits_wny": 0,
                "completed_forms": 0,
                "sessions": 209,
            },
            {"date": "2026-08-21", "ga4": "not_configured", "visits_total": 0, "visits_wny": 0, "completed_forms": 0},
        ]
        payload = funnel.aggregate_daily_docs(docs, year=2026, month=8)
        by_date = {row["date"]: row for row in payload["days"]}
        self.assertEqual(len(payload["days"]), 31)
        self.assertIsNone(by_date["2026-08-19"]["visits_total"])
        self.assertIsNone(by_date["2026-08-19"]["completed_forms"])
        self.assertEqual(by_date["2026-08-20"]["visits_total"], 209)
        self.assertEqual(by_date["2026-08-20"]["visits_wny"], 0)
        self.assertEqual(by_date["2026-08-20"]["completed_forms"], 0)
        self.assertIsNone(by_date["2026-08-21"]["visits_total"])
        self.assertEqual(payload["totals"]["visits_total"], 209)
        self.assertEqual(payload["totals"]["sessions"], 1208)
        self.assertIn("data_api_missing", payload["contract"]["exclusions"])
        self.assertTrue(payload["contract"]["exclusions"]["no_tester_ip_list"])

    def test_rollup_writes_host_split_and_sessions_match_visits_total(self):
        captured = {}

        class FakeDoc:
            def set(self, payload, merge=True):
                captured.update(payload)

        class FakeCol:
            def document(self, _id):
                return FakeDoc()

        class FakeDb:
            def collection(self, name):
                self.name = name
                return FakeCol()

        ga4 = funnel.summarize_ga4_event_rows(
            [
                {"event_name": "page_view", "host_name": "www.happyslr.com", "page_path": "/", "count": 351},
                {
                    "event_name": "estimate_submit",
                    "host_name": "preview.vercel.app",
                    "page_path": "/calculator",
                    "count": 1,
                },
            ]
        )
        with patch.object(funnel, "fetch_ga4_event_counts", return_value=ga4):
            out = funnel.rollup_day(FakeDb(), "2026-08-19")
        self.assertEqual(out["doc"]["visits_total"], 351)
        self.assertEqual(out["doc"]["sessions"], 351)
        self.assertEqual(out["doc"]["visits_wny"], 0)
        self.assertEqual(out["doc"]["completed_forms"], 0)
        self.assertEqual(out["doc"]["estimate_submit"], 0)
        self.assertEqual(captured["sessions"], 351)
        self.assertEqual(captured["completed_forms"], 0)
        self.assertNotIn("ghl_leads", captured)
        self.assertNotIn("TESTER_IPS", FUNNEL_SRC)
        self.assertNotIn("ip_allowlist", FUNNEL_SRC)
        self.assertNotIn("ipAddress", FUNNEL_SRC)

    def test_hawkstone_test_address_drops_event_level_rows(self):
        out = funnel.summarize_ga4_event_rows(
            [
                {"event_name": "page_view", "host_name": "www.happyslr.com", "page_path": "/", "count": 10},
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
        self.assertEqual(out["estimate_submit"], 2)
        self.assertEqual(out["completed_forms"], 2)
        self.assertEqual(out["dropped"]["test_address"], 6)
        self.assertEqual(out["filters"]["test_address"], "24 hawkstone way")
        self.assertEqual(out["filters"]["test_address_lock_date"], "2026-08-26")
        self.assertEqual(out["filters"]["test_address_grain"], "event")
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", address="24 HAWKSTONE WAY"),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(host_name="wny.happyslr.com", address="  24   Hawkstone   Way  "),
            "test_address",
        )
        self.assertEqual(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
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
        self.assertIsNone(funnel.exclusion_reason(host_name="wny.happyslr.com", address="124 Hawkstone Way"))
        self.assertIsNone(
            funnel.exclusion_reason(
                host_name="wny.happyslr.com",
                page_location="https://wny.happyslr.com/calculator",
            )
        )
        self.assertEqual(inspect.getsource(funnel.fetch_ga4_event_counts).count("runReport"), 1)
        for name in ("address", "estimate_address", "customEvent:address", "sessionId"):
            self.assertNotIn(name, funnel.GA4_REPORT_DIMENSIONS)
        parsed = funnel.parse_ga4_report_rows(
            {
                "rows": [
                    {
                        "dimensionValues": [
                            {"value": "estimate_submit"},
                            {"value": "/calculator"},
                            {"value": "wny.happyslr.com"},
                            {"value": "https://wny.happyslr.com/calculator"},
                            {"value": "24 Hawkstone Way"},
                            {"value": "24 hawkstone way"},
                            {"value": "24 Hawkstone Way, Buffalo, NY 14221"},
                        ],
                        "metricValues": [{"value": "1"}],
                    }
                ]
            },
            (
                "eventName",
                "pagePath",
                "hostName",
                "pageLocation",
                "address",
                "estimate_address",
                "customEvent:address",
            ),
        )
        self.assertEqual(parsed[0]["address"], "24 Hawkstone Way")
        self.assertEqual(parsed[0]["estimate_address"], "24 hawkstone way")
        self.assertEqual(parsed[0]["custom_event_address"], "24 Hawkstone Way, Buffalo, NY 14221")
        self.assertEqual(funnel.GA4_REPORT_DIMENSIONS, ("eventName", "pagePath", "hostName", "pageLocation"))


if __name__ == "__main__":
    unittest.main()
