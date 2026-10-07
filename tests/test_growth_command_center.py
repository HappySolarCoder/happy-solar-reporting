# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import io
import json
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


metric = load_module("growth_command_center_metric", METRICS / "growth_command_center.py")
page = load_module("growth_command_center_page", API / "growth_command_center.py")
nav = load_module("dashboard_nav_growth", API / "dashboard_nav.py")
sales = load_module("sales_for_growth", METRICS / "sales.py")
index = load_module("index_for_growth", API / "index.py")

PAGE_SRC = (API / "growth_command_center.py").read_text(encoding="utf-8")
METRIC_SRC = (METRICS / "growth_command_center.py").read_text(encoding="utf-8")
WARM_SRC = (API / "warm_cache.py").read_text(encoding="utf-8")
VERCEL = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))


def _lead(**overrides):
    base = {
        "id": "lead_x",
        "contact_id": "contact_x",
        "acquired_on": "2026-11-02",
        "ad_id": "ad_local_savings",
        "pipeline_id": "GQtUlcTmLJ61HZjrGEPC",
        "duplicate": False,
        "test": False,
        "invalid": False,
        "demo_id": None,
        "demo_observed_on": None,
        "sold_id": None,
        "sold_on": None,
        "sold_observed_on": None,
        "sale_cancelled": False,
        "stage_group": None,
    }
    base.update(overrides)
    return base


def _day(leads, spend_cents=1000, visits=10, starts=2):
    return {
        "date": "2026-11-02",
        "visits": visits,
        "form_starts": starts,
        "submissions_accepted": len(leads),
        "submissions_delivered": len(leads),
        "ads": {
            "ad_local_savings": {"spend_cents": spend_cents, "impressions": 100, "outbound_clicks": 5}
        },
        "leads": leads,
        "spend_cents": spend_cents,
    }


class GrowthCommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.payload = metric.compute_payload({})

    def test_default_fixture_matches_page_eight(self):
        kpis = self.payload["kpis"]
        self.assertTrue(self.payload["sample_data"])
        self.assertEqual(self.payload["badge"], "SAMPLE DATA")
        self.assertEqual(self.payload["selected_range"]["start"], "2026-11-01")
        self.assertEqual(self.payload["selected_range"]["end"], "2026-11-15")
        self.assertEqual(self.payload["data_cutoff"], "2026-11-15")
        self.assertTrue(self.payload["as_of"].startswith("2026-11-16T00:00:00"))
        self.assertEqual(kpis["leads"]["actual"], 8)
        self.assertEqual(kpis["leads"]["goal"], 20)
        self.assertAlmostEqual(kpis["leads"]["attained"], 0.4)
        self.assertAlmostEqual(kpis["leads"]["expected_pace"], 10)
        self.assertEqual(kpis["leads"]["pace_label"], "2 behind pace")
        self.assertEqual(kpis["cpl"]["value"], 30)
        self.assertEqual(kpis["cpl"]["variance"], 5)
        self.assertEqual(kpis["cpl"]["status"], "over")
        self.assertEqual(kpis["demos"]["value"], 4)
        self.assertEqual(kpis["demo_cost"]["value"], 60)
        self.assertEqual(kpis["demo_cost"]["status"], "over")
        self.assertEqual(kpis["sold"]["value"], 1)
        self.assertEqual(kpis["sold_cpa"]["value"], 240)
        self.assertEqual(kpis["sold_cpa"]["status"], "over")
        self.assertEqual(kpis["spend"]["value"], 240)
        self.assertIsNone(kpis["spend"]["cap"])
        self.assertEqual(kpis["spend"]["cap_label"], "Not configured")
        self.assertEqual(kpis["active_ads"]["effective"], 3)
        self.assertEqual(kpis["active_ads"]["rejected"], 0)

    def test_funnel_corrects_reference_arithmetic(self):
        stages = {stage["id"]: stage for stage in self.payload["funnel"]["stages"]}
        self.assertEqual(stages["impressions"]["count"], 24000)
        self.assertEqual(stages["outbound_clicks"]["count"], 400)
        self.assertEqual(stages["landing_visits"]["count"], 320)
        self.assertEqual(stages["form_starts"]["count"], 40)
        self.assertEqual(stages["leads"]["count"], 8)
        self.assertEqual(stages["demos"]["count"], 4)
        self.assertEqual(stages["sold"]["count"], 1)
        self.assertAlmostEqual(stages["outbound_clicks"]["conversion_from_previous"], 400 / 24000)
        self.assertEqual(stages["outbound_clicks"]["conversion_label"], "1.7%")
        self.assertAlmostEqual(stages["landing_visits"]["conversion_from_previous"], 0.8)
        self.assertEqual(stages["form_starts"]["conversion_label"], "12.5%")
        self.assertTrue(self.payload["funnel"]["directional"])
        blob = json.dumps(self.payload["recommendations"])
        self.assertNotIn("80% of landing", blob)
        self.assertNotIn("16%", stages["outbound_clicks"]["conversion_label"])
        self.assertIn("12.5%", self.payload["recommendations"][0]["text"])

    def test_row_cpl_is_spend_over_leads_and_total_is_not_an_average(self):
        rows = {row["name"]: row for row in self.payload["ads"]}
        self.assertEqual(rows["Local savings"]["spend"], 120)
        self.assertEqual(rows["Local savings"]["leads"], 4)
        self.assertEqual(rows["Local savings"]["cpl"], 30)
        self.assertEqual(rows["Local savings"]["ctr"], 180 / 10000)
        self.assertEqual(rows["Solar explained"]["cpl"], 40)
        self.assertEqual(rows["Solar explained"]["ctr"], 140 / 8000)
        self.assertEqual(rows["Homeowner story"]["cpl"], 20)
        self.assertAlmostEqual(rows["Homeowner story"]["ctr"], 80 / 6000)
        spend = sum(row["spend_cents"] for row in self.payload["ads"])
        leads = sum(row["leads"] for row in self.payload["ads"])
        clicks = sum(row["outbound_clicks"] for row in self.payload["ads"])
        impressions = sum(row["impressions"] for row in self.payload["ads"])
        self.assertEqual(spend, 24000)
        self.assertEqual(leads, 8)
        self.assertEqual(spend / leads / 100, 30)
        self.assertAlmostEqual(clicks / impressions, 400 / 24000)
        one_day = metric.compute_payload({"start": "2026-11-02", "end": "2026-11-02"})
        day_rows = one_day["ads"]
        account_cpl = one_day["kpis"]["cpl"]["value"]
        linked = [row["cpl"] for row in day_rows if row["leads"]]
        self.assertTrue(linked)
        self.assertNotEqual(account_cpl, linked[0])
        self.assertTrue(any(row["leads"] == 0 and row["cpl"] is None and row["spend"] for row in day_rows))

    def test_cost_series_is_cumulative_not_decorative(self):
        series = self.payload["charts"]["costs"]["series"]["cpl"]
        nov15 = next(point for point in series if point["date"] == "2026-11-15")
        nov1 = next(point for point in series if point["date"] == "2026-11-01")
        self.assertIsNone(nov1["value"])
        self.assertEqual(nov15["value"], 30)
        self.assertEqual(nov15["outcomes"], 8)
        self.assertEqual(self.payload["charts"]["costs"]["goals"]["cpl"], 25)
        self.assertEqual(self.payload["charts"]["costs"]["goals"]["demo"], 50)
        self.assertEqual(self.payload["charts"]["costs"]["goals"]["sold"], 200)
        lead_point = next(point for point in self.payload["charts"]["leads"]["points"] if point["date"] == "2026-11-15")
        self.assertEqual(lead_point["actual"], 8)
        self.assertEqual(lead_point["pace"], 10)
        future = next(point for point in self.payload["charts"]["leads"]["points"] if point["date"] == "2026-11-16")
        self.assertTrue(future["future"])
        self.assertIsNone(future["actual"])

    def test_goals_do_not_inherit_november(self):
        october = metric.compute_payload({"preset": "last_month"})
        self.assertEqual(october["goal_month"], "2026-10")
        self.assertEqual(october["kpis"]["leads"]["goal"], 10)
        self.assertEqual(october["kpis"]["leads"]["actual"], 0)
        self.assertIsNone(october["kpis"]["cpl"]["value"])
        self.assertEqual(october["kpis"]["leads"]["pace_label"], "10 behind pace")
        december = metric.compute_payload({"start": "2026-12-01", "end": "2026-12-15"})
        self.assertIsNone(december["kpis"]["leads"]["goal"])
        self.assertEqual(december["kpis"]["leads"]["pace_label"], "Goal not configured")
        span = metric.compute_payload({"preset": "last_30"})
        self.assertTrue(span["goal_month_ambiguous"])
        self.assertEqual(span["kpis"]["leads"]["pace_label"], "Pace N/A")
        both = metric.compute_payload({"start": "2026-10-01", "end": "2026-11-30"})
        self.assertEqual(both["kpis"]["leads"]["goal"], 30)
        self.assertAlmostEqual(both["kpis"]["leads"]["expected_pace"], 20)

    def test_recommendations_match_counts_and_corrections(self):
        recs = self.payload["recommendations"]
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["title"], "Inspect form drop-off")
        self.assertIn("Review the 12.5% visit-to-form-start rate.", recs[0]["text"])
        self.assertIn("Maintain current spend", recs[1]["text"])
        self.assertIn("CPL $30", recs[1]["text"])
        self.assertIn("sold CPA $240", recs[1]["text"])
        self.assertIn("Test an approved creative against lead cost.", recs[2]["text"])
        self.assertNotIn("better click", recs[2]["text"].lower())
        self.assertEqual(self.payload["bot"]["label"], "WATCH · Lead pace & costs")
        self.assertEqual(self.payload["bot"]["next_action"], "Inspect form drop-off")
        self.assertEqual(self.payload["bot"]["crm_delivery"]["label"], "8 of 8 submissions reached CRM")
        self.assertIn("Nov 16", self.payload["bot"]["last_sync_label"])
        self.assertNotIn("9:00 AM", self.payload["as_of_label"])

    def test_duplicate_and_test_leads_do_not_change_the_denominator(self):
        scope = metric.resolve_scope({"start": "2026-11-01", "end": "2026-11-02"})
        leads = [
            _lead(id="keep", contact_id="keep"),
            _lead(id="dup", contact_id="dup", duplicate=True),
            _lead(id="test", contact_id="test", test=True),
            _lead(id="invalid", contact_id="invalid", invalid=True),
        ]
        payload = metric.assemble([_day(leads, spend_cents=9000)], list(metric.AD_CATALOG), scope, metric.demo_sources())
        self.assertEqual(payload["kpis"]["leads"]["actual"], 2)
        self.assertEqual(
            metric.lead_counts(leads)["invalid_kept_in_denominator"],
            1,
        )
        self.assertEqual(metric.lead_counts(leads)["count"], 2)

    def test_outcome_rules(self):
        cutoff = metric.date(2026, 11, 15)
        late = _lead(
            id="late",
            contact_id="late",
            sold_id="sold_late",
            sold_on="2026-11-20",
            sold_observed_on="2026-11-20",
            stage_group="sold",
        )
        cancelled = _lead(
            id="cancel",
            contact_id="cancel",
            sold_id="sold_cancel",
            sold_on="2026-11-12",
            sold_observed_on="2026-11-12",
            stage_group="sale_cancelled",
            sale_cancelled=True,
        )
        duplicate_contact = _lead(
            id="again",
            contact_id="cancel",
            sold_id="sold_again",
            sold_on="2026-11-13",
            sold_observed_on="2026-11-13",
            stage_group="sold",
        )
        outside = _lead(
            id="outside",
            contact_id="outside",
            pipeline_id=metric.INBOUND_PIPELINE_ID,
            demo_id="demo_outside",
            demo_observed_on="2026-11-04",
        )
        counted = metric.outcome_sets([late, cancelled, duplicate_contact, outside], cutoff)
        self.assertEqual(counted["sold"], 1)
        self.assertEqual(counted["sale_cancelled_included"], 1)
        self.assertEqual(counted["demos"], 0)
        self.assertEqual(metric.SOLD_STAGE_IDS, sales.SalesMetricContract().stage_ids)

    def test_zero_outcomes_are_not_zero_dollars(self):
        scope = metric.resolve_scope({"start": "2026-11-01", "end": "2026-11-02"})
        payload = metric.assemble(
            [_day([_lead()], spend_cents=5000, visits=0, starts=0)],
            list(metric.AD_CATALOG),
            scope,
            metric.demo_sources(),
        )
        self.assertEqual(payload["kpis"]["leads"]["actual"], 1)
        self.assertIsNone(payload["kpis"]["demo_cost"]["value"])
        self.assertIsNone(payload["kpis"]["sold_cpa"]["value"])
        self.assertNotEqual(payload["kpis"]["demo_cost"]["value"], 0)

    def test_unlinked_ad_does_not_invent_cpl(self):
        scope = metric.resolve_scope({"start": "2026-11-01", "end": "2026-11-02"})
        catalog = [{
            "id": "ad_unlinked",
            "name": "Unlinked",
            "copy": "No lead",
            "campaign_id": "camp",
            "campaign_name": "Prospecting",
            "adset_id": "set",
            "platform": "meta",
            "configured_status": "active",
            "effective_status": "active",
            "rejected": False,
            "thumbnail": "fallback",
            "landing_url": None,
        }]
        day = _day([], spend_cents=2500)
        day["ads"] = {"ad_unlinked": {"spend_cents": 2500, "impressions": 50, "outbound_clicks": 2}}
        payload = metric.assemble([day], catalog, scope, metric.demo_sources())
        ad = payload["ads"][0]
        self.assertEqual(ad["leads"], 0)
        self.assertIsNone(ad["cpl"])
        self.assertEqual(ad["attribution"], "none")

    def test_live_mode_does_not_reuse_the_fixture(self):
        payload = metric.compute_payload(
            {"mode": "live", "start": "2026-11-01", "end": "2026-11-15"},
            live_loader=lambda scope: {
                "days": [],
                "catalog": [],
                "sources": {
                    key: {"status": "unavailable", "reason": "missing_env", "detail": "down", "validated": False}
                    for key in ("meta_ads", "website_analytics", "submissions", "crm")
                },
            },
        )
        self.assertFalse(payload["sample_data"])
        self.assertIsNone(payload["kpis"]["spend"]["value"])
        self.assertIsNone(payload["kpis"]["leads"]["actual"])
        self.assertIsNone(payload["kpis"]["cpl"]["value"])
        self.assertNotEqual(payload["kpis"]["spend"]["value"], 240)
        self.assertEqual(payload["bot"]["overall"], "unknown")
        self.assertEqual(payload["recommendations"], [])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["mutations"], [])

    def test_handlers_are_get_only(self):
        for module in (metric, page):
            dummy = _dummy(module.handler)
            dummy.do_POST()
            self.assertEqual(dummy.status, 405)
            self.assertNotIn(b"graph.facebook.com", dummy.wfile.getvalue())

    def test_page_names_the_specified_components(self):
        for name in (
            "DashboardShell",
            "Sidebar",
            "Header",
            "StatCard",
            "GoalProgressChart",
            "BotStatusPanel",
            "RecommendationList",
            "FunnelStrip",
            "CostTrendChart",
            "ActiveAdsTable",
            "DetailDrawer",
        ):
            self.assertIn(f"function {name}", PAGE_SRC)
            self.assertIn(f'data-component="{name}"', PAGE_SRC)
        html = page.render_html(self.payload)
        self.assertIn("SAMPLE DATA", html)
        self.assertIn("Growth command center", html)
        self.assertNotIn("graph.facebook.com", html)
        self.assertNotIn("META_ADS_ACCESS_TOKEN", html)

    def test_route_is_direct_and_not_on_shared_nav_or_warm_cache(self):
        html = nav.render_dashboard_nav("company_overview")
        self.assertNotIn("growth_command_center", html)
        self.assertNotIn("/growth", html)
        self.assertNotIn("growth_command_center", WARM_SRC)
        sources = [item.get("source") for item in VERCEL["rewrites"]]
        self.assertIn("/growth", sources)
        self.assertEqual(index.dispatch_route("/api/growth_command_center"), "growth_command_center")
        self.assertEqual(
            index.dispatch_route("/api?hs=metrics/growth_command_center"),
            "metrics/growth_command_center",
        )
        self.assertIsNotNone(index.dispatch_file("growth_command_center"))
        self.assertIsNotNone(index.dispatch_file("metrics/growth_command_center"))


def _dummy(cls):
    class Dummy(cls):
        def __init__(self):
            self.status = None
            self.wfile = io.BytesIO()
            self.path = "/api/growth_command_center"

        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, key, value):
            return None

        def end_headers(self):
            return None

    return Dummy()


if __name__ == "__main__":
    unittest.main()
