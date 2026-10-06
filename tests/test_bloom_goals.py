# -*- coding: utf-8 -*-

"""Bloom account goals: same portal_goal_documents contract as the portal."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "api" / "metrics" / "bloom_goals.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hs_bloom_goals", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load bloom_goals.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bloom = load_module()


def _doc(goals):
    return json.dumps({"accountGoals": goals})


class BloomGoalParseTests(unittest.TestCase):
    def test_october_2026_territory_sales_match_stored_documents(self):
        documents = [
            (
                "scope:territory:Buffalo",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Buffalo",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 37,
                            "unit": "count",
                        }
                    ]
                ),
            ),
            (
                "scope:territory:Rochester",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Rochester",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 17,
                            "unit": "count",
                        }
                    ]
                ),
            ),
            (
                "scope:territory:Virtual/Sweeper",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Virtual/Sweeper",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 7,
                            "unit": "count",
                        }
                    ]
                ),
            ),
        ]
        payload = bloom.build_payload("2026-10", documents)
        self.assertTrue(payload["available"])
        self.assertIsNone(payload["company_sales"])
        self.assertEqual(payload["demo_pct"]["target"], bloom.COMPANY_DEMO_PCT_TARGET)
        self.assertFalse(payload["demo_pct"]["stored"])
        self.assertEqual(payload["demo_pct"]["unit"], "percent")
        self.assertIsNone(payload["opp2prelim"])
        self.assertIsNone(payload["opportunities_created"])
        by_name = {row["territory"]: row for row in payload["territory_sales"]}
        self.assertEqual(by_name["Buffalo"]["target"], 37)
        self.assertEqual(by_name["Rochester"]["target"], 17)
        self.assertEqual(by_name["Virtual/Sweeper"]["target"], 7)
        self.assertEqual(by_name["Virtual/Sweeper"]["ops_territory"], "Virtual")
        self.assertFalse(by_name["Virtual/Sweeper"]["locked_default"])
        self.assertIsNone(by_name["Syracuse"]["target"])
        self.assertIn("scope:company", payload["unset"]["company_sales"])

    def test_virtual_sweeper_uses_portal_locked_default_when_unstored(self):
        payload = bloom.build_payload("2026-11", [])
        virtual = next(row for row in payload["territory_sales"] if row["territory"] == "Virtual/Sweeper")
        self.assertEqual(virtual["target"], 7)
        self.assertTrue(virtual["locked_default"])
        self.assertFalse(virtual["stored"])

    def test_october_2026_company_sales_document_is_not_a_territory_sum(self):
        company = {
            "id": "account_goal_company_company_sales_2026-10",
            "scope": "company",
            "territory": None,
            "metricKey": "sales",
            "periodId": "2026-10",
            "periodStart": "2026-10-01",
            "periodEnd": "2026-11-01",
            "timezone": "America/New_York",
            "target": 60,
            "unit": "count",
            "version": 1,
            "updatedBy": "evan-october-2026-company-sales",
            "updatedAt": "2026-10-05T23:00:00.000Z",
        }
        documents = [
            ("scope:company", _doc([company])),
            (
                "scope:territory:Buffalo",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Buffalo",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 37,
                            "unit": "count",
                        }
                    ]
                ),
            ),
            (
                "scope:territory:Rochester",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Rochester",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 17,
                            "unit": "count",
                        }
                    ]
                ),
            ),
            (
                "scope:territory:Virtual/Sweeper",
                _doc(
                    [
                        {
                            "scope": "territory",
                            "territory": "Virtual/Sweeper",
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 7,
                            "unit": "count",
                        }
                    ]
                ),
            ),
        ]
        payload = bloom.build_payload("2026-10", documents)
        self.assertEqual(payload["company_sales"]["target"], 60)
        self.assertTrue(payload["company_sales"]["stored"])
        self.assertIn("scope:company", payload["unset"]["company_sales"])
        self.assertNotIn("No scope:company sales goal is stored", payload["unset"]["company_sales"])
        self.assertNotEqual(payload["company_sales"]["target"], 37 + 17 + 7)
        self.assertEqual(payload["demo_pct"]["target"], bloom.COMPANY_DEMO_PCT_TARGET)
        self.assertFalse(payload["demo_pct"]["stored"])
        self.assertIsNone(payload["opp2prelim"])
        self.assertIsNone(payload["opportunities_created"])
        by_name = {row["territory"]: row for row in payload["territory_sales"]}
        self.assertEqual(by_name["Buffalo"]["target"], 37)
        self.assertEqual(by_name["Rochester"]["target"], 17)
        self.assertEqual(by_name["Virtual/Sweeper"]["target"], 7)
        self.assertFalse(by_name["Virtual/Sweeper"]["locked_default"])
        november = bloom.build_payload("2026-11", documents)
        self.assertIsNone(november["company_sales"])

    def test_company_sales_goal_is_not_a_sum_of_territories(self):
        documents = [
            (
                "scope:company",
                _doc(
                    [
                        {
                            "scope": "company",
                            "territory": None,
                            "metricKey": "sales",
                            "periodId": "2026-10",
                            "target": 40,
                            "unit": "count",
                        }
                    ]
                ),
            )
        ]
        payload = bloom.build_payload("2026-10", documents)
        self.assertEqual(payload["company_sales"]["target"], 40)

    def test_person_goals_keep_the_newest_version(self):
        older = {
            "goals": [
                {
                    "assigneeUserId": "user-1",
                    "assigneeNameSnapshot": "Ada Setter",
                    "role": "fma",
                    "metricKey": "door-knocks",
                    "periodId": "2026-10",
                    "target": 100,
                    "unit": "count",
                    "version": 1,
                }
            ]
        }
        newer = {
            "goals": [
                {
                    "assigneeUserId": "user-1",
                    "assigneeNameSnapshot": "Ada Setter",
                    "role": "fma",
                    "metricKey": "door-knocks",
                    "periodId": "2026-10",
                    "target": 320,
                    "unit": "count",
                    "version": 2,
                },
                {
                    "assigneeUserId": "user-1",
                    "assigneeNameSnapshot": "Ada Setter",
                    "role": "fma",
                    "metricKey": "demos",
                    "periodId": "2026-10",
                    "target": 12,
                    "unit": "count",
                    "version": 1,
                },
                {
                    "assigneeUserId": "user-2",
                    "assigneeNameSnapshot": "Bo Closer",
                    "role": "closer",
                    "metricKey": "sales",
                    "periodId": "2026-09",
                    "target": 4,
                    "unit": "count",
                    "version": 1,
                },
            ]
        }
        rows = bloom.parse_person_goals([("team:a", older), ("company", newer)], "2026-10")
        by_metric = {row["metric"]: row for row in rows}
        self.assertEqual(set(by_metric), {"door-knocks", "demos"})
        self.assertEqual(by_metric["door-knocks"]["target"], 320)
        self.assertEqual(by_metric["door-knocks"]["settings_metric"], "doors_goal")
        self.assertEqual(by_metric["demos"]["settings_metric"], "demos_goal")
        self.assertNotIn("updatedBy", by_metric["demos"])

    def test_query_selects_only_scope_rows(self):
        self.assertIn("portal_goal_documents", bloom.SCOPE_SQL)
        self.assertIn("scope:company", bloom.SCOPE_SQL)
        self.assertNotIn("portal_users", bloom.SCOPE_SQL)
        self.assertNotIn("subject_id = 'company'", bloom.SCOPE_SQL)

    def test_missing_database_url_does_not_invent_a_goal(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            payload = bloom.read_bloom_goals("2026-10")
        self.assertFalse(payload["available"])
        self.assertIn("DATABASE_URL", payload["blocker"])
        self.assertNotIn("postgresql://", payload["blocker"])

    def test_neon_rows_and_read_path(self):
        body = json.dumps(
            {
                "rows": [
                    {
                        "subject_id": "scope:territory:Buffalo",
                        "document": _doc(
                            [
                                {
                                    "scope": "territory",
                                    "territory": "Buffalo",
                                    "metricKey": "sales",
                                    "periodId": "2026-10",
                                    "target": 37,
                                    "unit": "count",
                                }
                            ]
                        ),
                    }
                ]
            }
        ).encode("utf-8")

        class Response:
            def read(self):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:secret@ep-example.neon.tech/neondb"}, clear=True):
            payload = bloom.read_bloom_goals("2026-10", opener=lambda *_args, **_kwargs: Response())
        self.assertTrue(payload["available"])
        buffalo = next(row for row in payload["territory_sales"] if row["territory"] == "Buffalo")
        self.assertEqual(buffalo["target"], 37)
        self.assertNotIn("secret", json.dumps(payload))

    def test_period_from_start_date(self):
        self.assertEqual(bloom.period_from_parts(start="2026-10-05"), "2026-10")
        self.assertEqual(bloom.period_from_parts(year="2026", month="8"), "2026-08")

    def test_missing_company_demo_pct_target_is_50_percent(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertEqual(source.count("COMPANY_DEMO_PCT_TARGET = 50"), 1)
        self.assertEqual(bloom.COMPANY_DEMO_PCT_TARGET, 50)
        self.assertNotIn("No company Demo % goal is set in Bloom.", source)
        for blank in (None, "", "none", False, 0, -5, 50_000_000):
            goal = bloom.company_demo_pct_goal("2026-10", blank)
            self.assertEqual(goal["target"], 50)
            self.assertEqual(goal["unit"], "percent")
            self.assertFalse(goal["stored"])
            self.assertEqual(bloom.demo_pct_note(goal), "Company Demo % target is 50%.")
        stored = bloom.company_demo_pct_goal("2026-10", 42)
        self.assertEqual(stored["target"], 42)
        self.assertTrue(stored["stored"])
        self.assertEqual(bloom.demo_pct_note(stored), "Stored company Demo % target is 42%.")
        payload = bloom.build_payload("2026-10", [])
        self.assertEqual(payload["demo_pct"]["target"], bloom.COMPANY_DEMO_PCT_TARGET)
        self.assertNotIn("no target", payload["unset"]["demo_pct"].lower())
        self.assertNotIn("not set", payload["unset"]["demo_pct"].lower())
        self.assertIsNone(payload["opp2prelim"])
        self.assertIsNone(payload["opportunities_created"])
        with mock.patch.dict("os.environ", {}, clear=True):
            unread = bloom.read_bloom_goals("2026-10")
        self.assertFalse(unread["available"])
        self.assertIsNone(unread.get("company_sales"))
        self.assertEqual(unread["demo_pct"]["target"], 50)
        self.assertFalse(unread["demo_pct"]["stored"])
        self.assertIn("50%", unread["unset"]["demo_pct"])


class GoalsPageWiringTests(unittest.TestCase):
    def test_goals_dashboard_uses_bloom_targets(self):
        html = (ROOT / "api" / "goals_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("/api/metrics/bloom_goals?oc_raw=1&period=", html)
        self.assertIn("goal.target", html)
        self.assertNotIn("Bloom company and territory goals are not readable", html)

    def test_company_overview_does_not_hardcode_every_pace_as_unset(self):
        script = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
        self.assertIn("/api/metrics/bloom_goals?oc_raw=1&period=", script)
        self.assertNotIn('setText("salesPace", "Goal Not Set")', script)
        self.assertIn("company_trends", script)
        page = (ROOT / "api" / "ops_overview.py").read_text(encoding="utf-8")
        self.assertIn('id="companyGoalsBody"', page)
        self.assertNotIn("not readable from this app yet", page)
        self.assertNotIn('class="navbtn"', page)

    def test_attention_bar_is_gone_and_demo_target_uses_the_constant(self):
        script = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
        page = (ROOT / "api" / "ops_overview.py").read_text(encoding="utf-8")
        css = (ROOT / "api" / "ops_theme.css").read_text(encoding="utf-8")
        goals = (ROOT / "api" / "goals_dashboard.py").read_text(encoding="utf-8")
        combined = script + page + css + goals
        self.assertNotIn("NEEDS ATTENTION", combined)
        self.assertNotIn("attentionHost", combined)
        self.assertNotIn("attention-strip", css)
        self.assertNotIn("attention-label", css)
        self.assertNotIn("no company Demo % target is stored", combined)
        self.assertNotIn('setText("demoGoal", "Goal Not Set")', script)
        self.assertIn("__COMPANY_DEMO_PCT_TARGET__", script)
        self.assertIn("companyDemoGoal", script)
        self.assertIn("demoPaceCaption", script)
        self.assertIn('id="filterHost"', page)
        self.assertIn("/api/missing_dispos", page)
        self.assertIn("/api/goals_dashboard", script)
        self.assertIn("COMPANY_DEMO_PCT_TARGET", goals)
        self.assertIn("rate: true", goals)
        self.assertNotIn("Goal 50%", goals)
        spec = importlib.util.spec_from_file_location("hs_ops_overview_demo_target", ROOT / "api" / "ops_overview.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        ops = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ops)
        overview = ops.render_body("")
        self.assertIn('id="demoGoal">Goal 50%', overview)
        self.assertIn("const COMPANY_DEMO_PCT_TARGET = 50;", overview)
        self.assertNotIn("__COMPANY_DEMO_PCT_TARGET__", overview)
        self.assertNotIn("NEEDS ATTENTION", overview)
        self.assertNotIn("attentionHost", overview)
        goals_spec = importlib.util.spec_from_file_location(
            "hs_goals_dashboard_demo_target", ROOT / "api" / "goals_dashboard.py"
        )
        self.assertIsNotNone(goals_spec)
        self.assertIsNotNone(goals_spec.loader)
        goals_mod = importlib.util.module_from_spec(goals_spec)
        goals_spec.loader.exec_module(goals_mod)
        goals_html = goals_mod.render_html()
        self.assertIn("const COMPANY_DEMO_PCT_TARGET = 50;", goals_html)
        self.assertIn("rate: true", goals_html)
        self.assertNotIn("No company Demo % goal is set", goals_html)
        self.assertNotIn("NEEDS ATTENTION", goals_html)


if __name__ == "__main__":
    unittest.main()
