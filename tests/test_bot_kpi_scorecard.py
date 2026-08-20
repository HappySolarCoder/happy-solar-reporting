# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
WARM = API / "warm_cache.py"
NAV_PATH = API / "dashboard_nav.py"
PAGE_PATH = API / "bot_kpi_scorecard.py"
SCORING_PATH = METRICS / "bot_kpi.py"

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


scoring = load_module("bot_kpi", SCORING_PATH)
nav = load_module("dashboard_nav_bot_kpi", NAV_PATH)
page = load_module("bot_kpi_scorecard_page", PAGE_PATH)

SCORE_SRC = SCORING_PATH.read_text(encoding="utf-8")
PAGE_SRC = PAGE_PATH.read_text(encoding="utf-8")
WARM_SRC = WARM.read_text(encoding="utf-8")

UNFILTERED_STREAMS = (
    'db.collection("ghl_opportunities_v2").stream()',
    "db.collection('ghl_opportunities_v2').stream()",
    'db.collection("ghl_contacts_v2").stream()',
    "db.collection('ghl_contacts_v2').stream()",
    "db.collection(c.opp_collection).stream()",
    "db.collection(c.contact_collection).stream()",
)

WEBSITE_CONTACT_FIELDS = (
    "Website Landing Page",
    "Page Group",
    "GA Client ID",
    "FIELD_NAME",
)


def _row(lane: dict, name_substr: str) -> dict:
    for row in lane.get("rows") or []:
        if name_substr.lower() in str(row.get("name") or "").lower():
            return row
    raise AssertionError(f"missing row containing {name_substr!r} in {lane}")


class WarmCacheGuardTests(unittest.TestCase):
    def test_warm_cache_urls_empty_and_omits_bot_kpi_and_funnel(self):
        self.assertIn("urls = []", WARM_SRC)
        self.assertNotIn("bot_kpi", WARM_SRC)
        self.assertNotIn("website_funnel", WARM_SRC)
        self.assertNotIn("/api/bot_kpi_scorecard", WARM_SRC)


class ScorecardSourceGuardTests(unittest.TestCase):
    def test_scorecard_does_not_stream_opps_or_contacts(self):
        for src in (SCORE_SRC, PAGE_SRC):
            for needle in UNFILTERED_STREAMS:
                self.assertNotIn(needle, src)
            self.assertNotIn('db.collection("ghl_opportunities_v2")', src)
            self.assertNotIn('db.collection("ghl_contacts_v2")', src)

    def test_no_ghl_join_or_four_website_contact_fields(self):
        for src in (SCORE_SRC, PAGE_SRC):
            for needle in WEBSITE_CONTACT_FIELDS:
                self.assertNotIn(needle, src)
            self.assertNotIn("ghl_contacts_v2", src)
            self.assertNotIn("opportunity.source", src)

    def test_designer_conversion_is_not_hard_coded_not_live_yet(self):
        self.assertNotIn('status="not_live_yet"', SCORE_SRC)
        self.assertNotIn("status = \"not_live_yet\"", SCORE_SRC)
        self.assertNotIn('session_status = "not_live_yet"', SCORE_SRC)
        self.assertNotIn('start_status = "not_live_yet"', SCORE_SRC)
        # Conversion lives against goals; not_live_yet must not be assigned there.
        designer_fn = SCORE_SRC.split("def score_designer", 1)[1].split("def _permalinks_from_social_doc", 1)[0]
        self.assertNotIn("not_live_yet", designer_fn)


class DesignerScoringTests(unittest.TestCase):
    def test_missing_docs_leave_conversion_null_not_not_live_yet(self):
        lane = scoring.score_designer([], [], week_dates=["2026-08-17", "2026-08-18"])
        volume = _row(lane, "Completed form volume")
        sessions = _row(lane, "Sessions → completed form")
        start = _row(lane, "Start → completed form")
        self.assertEqual(volume["status"], "baseline_pending")
        self.assertIsNone(volume["value"])
        self.assertIsNone(sessions["value"])
        self.assertIsNone(start["value"])
        self.assertEqual(sessions["status"], "not_wired")
        self.assertEqual(start["status"], "not_wired")
        self.assertNotEqual(sessions["status"], "not_live_yet")
        self.assertNotEqual(start["status"], "not_live_yet")

    def test_live_conversion_scores_against_goals_when_numbers_exist(self):
        week_doc = {
            "date": "2026-08-17",
            "sessions": 100,
            "starts": 10,
            "estimate_submit": 3,
            "wix_form_submits": 0,
            "completed_forms": 3,
            "ga4": "ok",
        }
        lane = scoring.score_designer([week_doc], [week_doc], week_dates=["2026-08-17"])
        volume = _row(lane, "Completed form volume")
        sessions = _row(lane, "Sessions → completed form")
        start = _row(lane, "Start → completed form")
        self.assertEqual(volume["status"], "baseline_pending")
        self.assertEqual(volume["value"], 3)
        self.assertAlmostEqual(sessions["value"], 0.03)
        self.assertAlmostEqual(start["value"], 0.30)
        self.assertEqual(sessions["status"], "hit")
        self.assertEqual(start["status"], "hit")
        self.assertNotEqual(sessions["status"], "not_live_yet")
        self.assertNotEqual(start["status"], "not_live_yet")

    def test_live_conversion_can_miss_goals(self):
        week_doc = {
            "date": "2026-08-17",
            "sessions": 100,
            "starts": 20,
            "estimate_submit": 1,
            "wix_form_submits": 0,
            "completed_forms": 1,
            "ga4": "ok",
        }
        lane = scoring.score_designer([week_doc], [week_doc], week_dates=["2026-08-17"])
        self.assertEqual(_row(lane, "Sessions → completed form")["status"], "miss")
        self.assertEqual(_row(lane, "Start → completed form")["status"], "miss")

    def test_docs_without_ga4_numbers_are_unknown_not_invented(self):
        week_doc = {"date": "2026-08-17", "ga4": "not_configured"}
        lane = scoring.score_designer([week_doc], [week_doc], week_dates=["2026-08-17"])
        sessions = _row(lane, "Sessions → completed form")
        start = _row(lane, "Start → completed form")
        self.assertIsNone(sessions["value"])
        self.assertIsNone(start["value"])
        self.assertEqual(sessions["status"], "unknown")
        self.assertEqual(start["status"], "unknown")

    def test_volume_leaves_baseline_after_fourteen_instrumented_days(self):
        lookback = [
            {
                "date": f"2026-08-{day:02d}",
                "completed_forms": 1,
                "sessions": 10,
                "ga4": "ok",
            }
            for day in range(1, 15)
        ]
        week_doc = {
            "date": "2026-08-17",
            "completed_forms": 4,
            "sessions": 50,
            "starts": 8,
            "estimate_submit": 4,
            "ga4": "ok",
        }
        lane = scoring.score_designer([week_doc], lookback, week_dates=["2026-08-17"])
        volume = _row(lane, "Completed form volume")
        self.assertEqual(volume["value"], 4)
        self.assertEqual(volume["status"], "informational")
        self.assertNotEqual(volume["status"], "baseline_pending")


class SocialScoringTests(unittest.TestCase):
    def test_missing_doc_is_pending_and_does_not_invent_reach(self):
        lane = scoring.score_social(None)
        blob = json.dumps(lane)
        self.assertNotIn("999", blob)
        self.assertNotRegex(blob, r'(?i)"value":\s*[1-9].*reach')
        for row in lane["rows"]:
            self.assertNotIn("reach", str(row.get("name") or "").lower())
            self.assertNotIn("impression", str(row.get("name") or "").lower())
        posts = _row(lane, "weekday posts")
        clicks = _row(lane, "Clicks to")
        attributed = _row(lane, "Attributed")
        self.assertIsNone(posts["value"])
        self.assertIn(posts["status"], {"pending", "not_wired"})
        self.assertIsNone(clicks["value"])
        self.assertEqual(clicks["status"], "not_wired")
        self.assertEqual(attributed["status"], "later")
        self.assertIsNone(attributed["value"])
        self.assertNotIn("facebook_reach", blob)
        self.assertNotIn("impressions", blob)

    def test_warehouse_reach_numbers_are_not_emitted(self):
        lane = scoring.score_social(
            {
                "permalinks": ["https://facebook.com/p/1", "https://facebook.com/p/2", "https://facebook.com/p/3"],
                "wny_clicks": 12,
                "facebook_reach": 88001,
                "impressions": 77002,
                "reach": 66003,
            }
        )
        blob = json.dumps(lane)
        self.assertNotIn("88001", blob)
        self.assertNotIn("77002", blob)
        self.assertNotIn("66003", blob)
        posts = _row(lane, "weekday posts")
        clicks = _row(lane, "Clicks to")
        self.assertEqual(posts["value"], 3)
        self.assertEqual(posts["status"], "hit")
        self.assertEqual(clicks["value"], 12)
        self.assertNotIn("reach", json.dumps(posts.get("permalinks")))


class BorisAndDataTests(unittest.TestCase):
    def test_boris_is_checklist_without_fake_pass(self):
        lane = scoring.score_boris(None)
        self.assertEqual(lane["kind"], "contract_checklist")
        pin = _row(lane, "Knock pin")
        self.assertEqual(pin["status"], "informational")
        self.assertIsNone(pin["value"])
        self.assertIn("270e335", pin["notes"])
        hanging = _row(lane, "Knocking map")
        self.assertIn(hanging["status"], {"pending", "informational"})
        self.assertIsNone(hanging["value"])

    def test_opps_scanned_hundreds_hit_thousands_miss(self):
        hit = scoring.score_opps_scanned(264, 132)
        miss = scoring.score_opps_scanned(4545, 132)
        missing = scoring.score_opps_scanned(None, None, error="no db")
        self.assertEqual(hit["status"], "hit")
        self.assertEqual(miss["status"], "miss")
        self.assertEqual(missing["status"], "not_wired")
        self.assertIsNone(missing["value"])

    def test_compute_without_db_keeps_nulls_and_json_is_qaable(self):
        payload = scoring.compute(
            None,
            year=2026,
            week=34,
            write_cost_snapshot=False,
            created_scan=(None, None, "test skip"),
            funnel_docs=[],
            social_doc=None,
            raydar_doc=None,
            cost_doc=None,
            prev_cost_doc=None,
        )
        self.assertEqual(payload["week"]["id"], "2026-W34")
        self.assertEqual(payload["week"]["start"], "2026-08-17")
        self.assertEqual(payload["week"]["end"], "2026-08-23")
        self.assertTrue(payload["constraints"]["no_ghl_join"])
        self.assertTrue(payload["constraints"]["no_facebook_reach"])
        self.assertEqual(payload["constraints"]["calculator_ga4"], "live")
        self.assertEqual(payload["not_scored"], ["Charles"])
        designer = payload["lanes"]["designer"]
        self.assertEqual(_row(designer, "Sessions → completed form")["status"], "not_wired")
        self.assertEqual(_row(designer, "Completed form volume")["status"], "baseline_pending")
        blob = json.dumps(payload)
        self.assertNotIn("ghl_contacts_v2", blob)
        html = page.render_html(payload)
        self.assertIn("Weekly Bot KPI", html)
        self.assertIn("Designer", html)
        self.assertIn("Social", html)
        self.assertIn("Boris", html)
        self.assertIn("Data", html)
        self.assertNotIn("Charles widget", html.lower())


class NavTests(unittest.TestCase):
    def test_nav_includes_bot_kpi_after_project_management(self):
        html = nav.render_dashboard_nav("bot_kpi_scorecard")
        self.assertIn("Bot KPI", html)
        self.assertIn("/api/bot_kpi_scorecard", html)
        self.assertIn('href="/api/bot_kpi_scorecard"', html)
        self.assertIn("navbtn active", html)
        project = html.find("Project Management")
        bot = html.find("Bot KPI")
        website = html.find("Website Funnel")
        self.assertNotEqual(project, -1)
        self.assertLess(project, bot)
        self.assertNotEqual(website, -1)
        self.assertLess(bot, website)
        self.assertIn('href="/api/website_funnel"', html)


class WeekWindowTests(unittest.TestCase):
    def test_resolve_week_from_year_week_and_start_end(self):
        window = scoring.resolve_week(year=2026, week=34)
        self.assertEqual(window.week_id, "2026-W34")
        self.assertEqual(window.start, "2026-08-17")
        self.assertEqual(window.end, "2026-08-23")
        self.assertEqual(window.dates[0], "2026-08-17")
        self.assertEqual(window.dates[-1], "2026-08-23")
        custom = scoring.resolve_week(start="2026-08-17", end="2026-08-20")
        self.assertEqual(custom.start, "2026-08-17")
        self.assertEqual(custom.end, "2026-08-20")
        self.assertEqual(scoring.previous_week_id(window), "2026-W33")

    def test_instrumented_day_requires_a_real_number(self):
        self.assertFalse(scoring.is_instrumented_day({"ga4": "not_configured"}))
        self.assertTrue(scoring.is_instrumented_day({"completed_forms": 0}))
        self.assertTrue(scoring.is_instrumented_day({"ga4": "ok"}))


class NoCuriosityStreamTests(unittest.TestCase):
    def test_scoring_uses_get_all_of_known_ids(self):
        self.assertIn("db.get_all(", SCORE_SRC)
        self.assertIn("web_funnel_daily_v1", SCORE_SRC)
        self.assertNotIn(f'{scoring.FUNNEL_COLLECTION}").stream()', SCORE_SRC)
        self.assertNotIn("getAllLeads(", SCORE_SRC)
        self.assertNotIn("gen-lang-client-0395385938", PAGE_SRC)


if __name__ == "__main__":
    unittest.main()
