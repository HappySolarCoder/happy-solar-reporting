# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
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


metric = load_module("inbound_cac_metric", METRICS / "inbound_cac.py")
page = load_module("inbound_cac_page", API / "inbound_cac.py")
nav = load_module("dashboard_nav_inbound_cac", API / "dashboard_nav.py")
sales = load_module("sales_for_inbound_cac", METRICS / "sales.py")

METRIC_SRC = (METRICS / "inbound_cac.py").read_text(encoding="utf-8")
PAGE_SRC = (API / "inbound_cac.py").read_text(encoding="utf-8")
WARM_SRC = (API / "warm_cache.py").read_text(encoding="utf-8")

NY = ZoneInfo("America/New_York")
START, END, _, _ = metric.month_window(2026, 8, "America/New_York")

UNFILTERED_STREAMS = (
    'db.collection("ghl_opportunities_v2").stream()',
    "db.collection('ghl_opportunities_v2').stream()",
    'db.collection("ghl_contacts_v2").stream()',
    "db.collection('ghl_contacts_v2').stream()",
)


class TitleBucketingTests(unittest.TestCase):
    def test_lead_locker_prefix_and_case(self):
        self.assertEqual(metric.bucket_title("Lead Locker: Jane Doe"), "Lead Locker")
        self.assertEqual(metric.bucket_title("LEAD LOCKER — 123 Main"), "Lead Locker")
        self.assertEqual(metric.bucket_title("contains lead locker here"), "Lead Locker")

    def test_solar_review_and_reviews(self):
        self.assertEqual(metric.bucket_title("Solar Review: Pat Lee"), "Solar Reviews")
        self.assertEqual(metric.bucket_title("Solar Reviews: Pat Lee"), "Solar Reviews")
        self.assertEqual(metric.bucket_title("solar review"), "Solar Reviews")

    def test_unmatched_and_title_field_is_name(self):
        self.assertIsNone(metric.bucket_title("Inbound/3PL: leftover"))
        self.assertIsNone(metric.bucket_title(""))
        self.assertIsNone(metric.bucket_title(None))
        rec = metric.classify_inbound_opp(
            {
                "name": "Lead Locker: Ada",
                "title": "Solar Review: ignored",
                "createdAt": "2026-08-03T14:00:00.000Z",
                "pipelineStageId": "open-stage",
                "contactId": "c1",
            },
            START,
            END,
        )
        self.assertEqual(rec.bucket, "Lead Locker")
        self.assertEqual(metric.TITLE_FIELD, "name")


class RefundedAndCacTests(unittest.TestCase):
    def test_refunded_stage_id_is_excluded_from_spend_and_sales(self):
        self.assertTrue(metric.is_refunded_stage("5bb63eb2-2208-481e-a0b9-f82ece3c030a"))
        self.assertFalse(metric.is_refunded_stage("7981f111-73f2-4593-9662-6b95d99bf51a"))
        records = [
            metric.InboundOppRecord("Lead Locker", True, True, "c-refunded"),
            metric.InboundOppRecord("Lead Locker", True, False, "c-open"),
        ]
        rows = metric.build_source_rows(records, {"c-refunded", "c-open"})
        locker = {row["source"]: row for row in rows}["Lead Locker"]
        self.assertEqual(locker["opp_count"], 1)
        self.assertEqual(locker["refunded_excluded_count"], 1)
        self.assertEqual(locker["spend"], 45)
        self.assertEqual(locker["sales"], 1)
        self.assertEqual(locker["cac"], 45.0)
        self.assertEqual(locker["setter_unit_cost"], 500)
        self.assertEqual(locker["setter_spend"], 500)
        self.assertEqual(locker["tac"], 545.0)

    def test_cac_is_json_null_when_sales_zero(self):
        self.assertIsNone(metric.compute_cac(450, 0))
        records = [metric.InboundOppRecord("Solar Reviews", True, False, "c-no-sale")]
        rows = metric.build_source_rows(records, set())
        reviews = {row["source"]: row for row in rows}["Solar Reviews"]
        self.assertEqual(reviews["spend"], 70)
        self.assertEqual(reviews["sales"], 0)
        self.assertIsNone(reviews["cac"])
        self.assertEqual(reviews["setter_unit_cost"], 500)
        self.assertEqual(reviews["setter_spend"], 0)
        self.assertIsNone(reviews["tac"])
        encoded = json.dumps(reviews)
        self.assertIn('"cac": null', encoded)
        self.assertIn('"tac": null', encoded)
        self.assertNotIn('"cac": 0', encoded)
        self.assertNotIn('"tac": 0', encoded)

    def test_always_returns_both_source_rows(self):
        rows = metric.build_source_rows([], set())
        self.assertEqual([row["source"] for row in rows], ["Lead Locker", "Solar Reviews"])
        self.assertEqual(rows[0]["unit_cost"], 45)
        self.assertEqual(rows[1]["unit_cost"], 70)
        self.assertTrue(all(row["cac"] is None for row in rows))
        self.assertTrue(all(row["tac"] is None for row in rows))
        self.assertTrue(all(row["setter_unit_cost"] == 500 for row in rows))
        self.assertTrue(all(row["setter_spend"] == 0 for row in rows))

    def test_sales_are_distinct_contact_id(self):
        records = [
            metric.InboundOppRecord("Lead Locker", True, False, "c-same"),
            metric.InboundOppRecord("Lead Locker", True, False, "c-same"),
            metric.InboundOppRecord("Lead Locker", True, False, "c-other"),
        ]
        rows = metric.build_source_rows(records, {"c-same", "c-other"})
        locker = {row["source"]: row for row in rows}["Lead Locker"]
        self.assertEqual(locker["opp_count"], 3)
        self.assertEqual(locker["spend"], 135)
        self.assertEqual(locker["sales"], 2)
        self.assertEqual(locker["cac"], 67.5)
        self.assertEqual(locker["setter_spend"], 1000)
        self.assertEqual(locker["tac"], 567.5)


class SoldDateWindowTests(unittest.TestCase):
    def test_missing_sold_date_is_excluded(self):
        contact = {"customFields": []}
        self.assertIsNone(metric.extract_sold_date_ymd(contact))
        self.assertFalse(metric.sold_date_in_window(None, START, END))

    def test_sold_date_does_not_timezone_shift_z_wrapper(self):
        contact = {
            "customFields": [
                {"id": "P9oBjgbZjJdeE0OkBj9T", "value": "2026-08-01T00:00:00.000Z"}
            ]
        }
        ymd = metric.extract_sold_date_ymd(contact)
        self.assertEqual(ymd, "2026-08-01")
        self.assertTrue(metric.sold_date_in_window(ymd, START, END))
        july_end = datetime(2026, 8, 1, 0, 0, 0, tzinfo=NY)
        july_start = datetime(2026, 7, 1, 0, 0, 0, tzinfo=NY)
        self.assertFalse(metric.sold_date_in_window(ymd, july_start, july_end))


class BoundQueryAndNavTests(unittest.TestCase):
    def test_inbound_query_is_pipeline_bounded_and_sales_use_stage_ids(self):
        self.assertIn('.where("pipelineId", "==", INBOUND_PIPELINE_ID)', METRIC_SRC)
        self.assertIn('.where(STAGE_FIELD, "in", stage_ids)', METRIC_SRC)
        self.assertIn("db.get_all(", METRIC_SRC)
        self.assertIn('db.collection(CONTACT_COLLECTION).document(cid)', METRIC_SRC)
        for needle in UNFILTERED_STREAMS:
            self.assertNotIn(needle, METRIC_SRC)
            self.assertNotIn(needle, PAGE_SRC)
        self.assertNotIn(".set(", METRIC_SRC)
        self.assertNotIn(".update(", METRIC_SRC)
        self.assertNotIn(".delete(", METRIC_SRC)

    def test_uses_sales_stage_ids_and_sold_date_field(self):
        self.assertEqual(metric.SOLD_DATE_CUSTOM_FIELD_ID, "P9oBjgbZjJdeE0OkBj9T")
        self.assertEqual(metric.INBOUND_PIPELINE_ID, "7nSEgeoBYXZiIS7x41Jy")
        self.assertEqual(metric.REFUNDED_STAGE_ID, "5bb63eb2-2208-481e-a0b9-f82ece3c030a")
        self.assertIn("SalesMetricContract", METRIC_SRC)
        self.assertIn("contract.stage_ids", METRIC_SRC)
        self.assertEqual(
            list(sales.SalesMetricContract().stage_ids),
            [
                "7981f111-73f2-4593-9662-6b95d99bf51a",
                "adf3106e-d371-47ff-ab9e-6f7f33ecf415",
                "0aea9f94-1205-4623-ad3d-6e1b08ae8791",
                "34a1882f-7959-4d22-878d-91fe35a42907",
                "fa84c1cf-2ed6-461e-b6dc-b1730fae2750",
                "9bd71abf-7285-47bb-8800-a255e7b90630",
                "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad",
                "b9af1705-6e54-4a7b-a5b9-27fea93aeea6",
            ],
        )

    def test_not_on_warm_cache(self):
        self.assertIn("urls = []", WARM_SRC)
        self.assertNotIn("inbound_cac", WARM_SRC)

    def test_inbound_cac_is_not_on_lead_generation_nav(self):
        html = nav.render_dashboard_nav("inbound_cac")
        self.assertNotIn('href="/api/inbound_cac"', html)
        self.assertNotIn("Inbound CAC", html)
        lead_start = html.find("Lead Generation")
        lead_end = html.find("Daily Dashboard")
        self.assertNotEqual(lead_start, -1)
        self.assertNotEqual(lead_end, -1)
        lead_block = html[lead_start:lead_end]
        self.assertNotIn("inbound_cac", lead_block)
        overview = nav.render_dashboard_nav("company_overview")
        self.assertNotIn("/api/inbound_cac", overview)
        self.assertNotIn("Inbound CAC", overview)

    def test_dashboard_wires_ytd_totals_and_chart(self):
        page_html = page.render_html(2026)
        self.assertIn("/api/metrics/inbound_cac?", page_html)
        self.assertIn("Lead Locker", page_html)
        self.assertIn("Solar Reviews", page_html)
        self.assertIn("Overall CAC", page_html)
        self.assertIn("Overall TAC", page_html)
        self.assertIn("lead_locker_cac", page_html)
        self.assertIn("solar_reviews_cac", page_html)
        self.assertIn("lead_locker_tac", page_html)
        self.assertIn("solar_reviews_tac", page_html)
        self.assertIn("$500", page_html)
        self.assertNotIn("$400", page_html)
        self.assertIn("format: 'json'", page_html)
        self.assertIn("value: 'ytd'", page_html)
        self.assertIn("defaultMonth = 'ytd'", page_html)
        self.assertIn("if (monthSel.value && monthSel.value !== 'ytd') params.month = monthSel.value;", page_html)
        self.assertIn("if (v === null || v === undefined || v === '') return null;", page_html)
        self.assertNotIn("|| 0", page_html)
        ytd_at = page_html.find("YTD totals")
        kpi_at = page_html.find("Performance KPIs")
        chart_at = page_html.find("Month-by-month CAC and TAC")
        self.assertTrue(0 < ytd_at < kpi_at < chart_at)
        self.assertIn('id="kpiTable"', page_html)
        self.assertIn("id=\"leadLockerCac\"", page_html)
        self.assertIn("id=\"solarReviewsCac\"", page_html)
        self.assertIn("id=\"overallCac\"", page_html)
        self.assertIn("id=\"leadLockerTac\"", page_html)
        self.assertIn("id=\"solarReviewsTac\"", page_html)
        self.assertIn("id=\"overallTac\"", page_html)
        self.assertIn("data.performance_kpis", page_html)
        self.assertIn("opp_to_prelim", page_html)
        self.assertIn("demo_rate", page_html)
        self.assertIn("that source’s sits ÷ opportunities created", page_html)
        self.assertIn("not Bot KPI Sit/(Sit+No Sit)", page_html)
        self.assertIn("Opportunities created", page_html)
        self.assertIn("Opp to prelim", page_html)


class YtdDefaultAndTotalsTests(unittest.TestCase):
    def test_api_and_page_default_to_ytd_current_year(self):
        now = datetime(2026, 8, 22, 11, 0, 0, tzinfo=NY)
        year, month = metric.parse_inbound_cac_params({}, now)
        self.assertEqual(year, 2026)
        self.assertIsNone(month)
        year, month = metric.parse_inbound_cac_params({"year": ["2025"]}, now)
        self.assertEqual(year, 2025)
        self.assertIsNone(month)
        year, month = metric.parse_inbound_cac_params({"year": ["2026"], "month": ["ytd"]}, now)
        self.assertEqual((year, month), (2026, None))
        year, month = metric.parse_inbound_cac_params({"year": ["2026"], "month": ["8"]}, now)
        self.assertEqual((year, month), (2026, 8))
        page_year, page_month = page.parse_page_params({}, now)
        self.assertEqual((page_year, page_month), (2026, None))
        start, end, _, _ = metric.ytd_window(2026, "America/New_York", now)
        self.assertEqual(start, datetime(2026, 1, 1, 0, 0, 0, tzinfo=NY))
        self.assertEqual(end, datetime(2026, 9, 1, 0, 0, 0, tzinfo=NY))
        self.assertEqual(metric.ytd_months(2026, now), [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(metric.ytd_months(2025, now), list(range(1, 13)))
        self.assertEqual(metric.ytd_months(2027, now), [])

    def test_overall_cac_is_null_when_sales_zero(self):
        overall = metric.build_overall(
            [
                {"source": "Lead Locker", "spend": 450, "sales": 0, "opp_count": 10, "refunded_excluded_count": 0},
                {"source": "Solar Reviews", "spend": 140, "sales": 0, "opp_count": 2, "refunded_excluded_count": 0},
            ]
        )
        self.assertEqual(overall["source"], "Overall")
        self.assertEqual(overall["spend"], 590)
        self.assertEqual(overall["sales"], 0)
        self.assertIsNone(overall["cac"])
        self.assertEqual(overall["setter_unit_cost"], 500)
        self.assertEqual(overall["setter_spend"], 0)
        self.assertIsNone(overall["tac"])
        encoded = json.dumps(overall)
        self.assertIn('"cac": null', encoded)
        self.assertIn('"tac": null', encoded)
        self.assertNotIn('"cac": 0', encoded)
        self.assertNotIn('"tac": 0', encoded)

    def test_overall_cac_is_total_spend_over_total_sales(self):
        overall = metric.build_overall(
            [
                {"source": "Lead Locker", "spend": 450, "sales": 2, "opp_count": 10, "refunded_excluded_count": 0},
                {"source": "Solar Reviews", "spend": 140, "sales": 1, "opp_count": 2, "refunded_excluded_count": 0},
            ]
        )
        self.assertEqual(overall["spend"], 590)
        self.assertEqual(overall["sales"], 3)
        self.assertEqual(overall["cac"], 590 / 3)
        self.assertEqual(overall["setter_unit_cost"], 500)
        self.assertEqual(overall["setter_spend"], 1500)
        self.assertEqual(overall["tac"], 590 / 3 + 500)

    def test_month_chart_gaps_are_null_not_zero(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        raws = [
            metric.RawInboundOpp(
                "Lead Locker",
                datetime(2026, 1, 10, 12, 0, tzinfo=NY),
                False,
                "c-jan-no-sale",
            ),
            metric.RawInboundOpp(
                "Lead Locker",
                datetime(2026, 2, 10, 12, 0, tzinfo=NY),
                False,
                "c-feb-sold",
            ),
            metric.RawInboundOpp(
                "Solar Reviews",
                datetime(2026, 1, 12, 12, 0, tzinfo=NY),
                False,
                "c-jan-reviews-sold",
            ),
        ]
        contacts_map = {
            "c-feb-sold": {
                "customFields": [{"id": "P9oBjgbZjJdeE0OkBj9T", "value": "2026-02-11"}]
            },
            "c-jan-reviews-sold": {
                "customFields": [{"id": "P9oBjgbZjJdeE0OkBj9T", "value": "2026-01-20"}]
            },
        }
        sold_ids = {"c-feb-sold", "c-jan-reviews-sold"}
        payload = metric.assemble_inbound_cac(
            raws,
            contacts_map,
            sold_ids,
            year=2026,
            month=None,
            now=now,
        )
        self.assertEqual(payload["timeframe"], "ytd")
        self.assertIsNone(payload["month"])
        self.assertEqual(payload["chart"]["months"], ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(payload["chart"]["labels"], ["Jan", "Feb", "Mar"])
        self.assertIsNone(payload["chart"]["lead_locker_cac"][0])
        self.assertEqual(payload["chart"]["lead_locker_cac"][1], 45.0)
        self.assertIsNone(payload["chart"]["lead_locker_cac"][2])
        self.assertEqual(payload["chart"]["solar_reviews_cac"][0], 70.0)
        self.assertIsNone(payload["chart"]["solar_reviews_cac"][1])
        self.assertIsNone(payload["chart"]["solar_reviews_cac"][2])
        self.assertIsNone(payload["chart"]["lead_locker_tac"][0])
        self.assertEqual(payload["chart"]["lead_locker_tac"][1], 545.0)
        self.assertIsNone(payload["chart"]["lead_locker_tac"][2])
        self.assertEqual(payload["chart"]["solar_reviews_tac"][0], 570.0)
        self.assertIsNone(payload["chart"]["solar_reviews_tac"][1])
        self.assertIsNone(payload["chart"]["solar_reviews_tac"][2])
        encoded = json.dumps(payload["chart"])
        self.assertIn('"lead_locker_cac": [null, 45.0, null]', encoded)
        self.assertIn('"lead_locker_tac": [null, 545.0, null]', encoded)
        self.assertIn('"solar_reviews_tac": [570.0, null, null]', encoded)
        stripped = encoded.replace("45.0", "").replace("70.0", "").replace("545.0", "").replace("570.0", "")
        self.assertNotIn("0.0", stripped)
        locker = {row["source"]: row for row in payload["rows"]}["Lead Locker"]
        reviews = {row["source"]: row for row in payload["rows"]}["Solar Reviews"]
        self.assertEqual(locker["spend"], 90)
        self.assertEqual(locker["sales"], 1)
        self.assertEqual(locker["cac"], 90.0)
        self.assertEqual(locker["setter_spend"], 500)
        self.assertEqual(locker["tac"], 590.0)
        self.assertEqual(reviews["spend"], 70)
        self.assertEqual(reviews["sales"], 1)
        self.assertEqual(reviews["cac"], 70.0)
        self.assertEqual(reviews["setter_spend"], 500)
        self.assertEqual(reviews["tac"], 570.0)
        self.assertEqual(payload["overall"]["spend"], 160)
        self.assertEqual(payload["overall"]["sales"], 2)
        self.assertEqual(payload["overall"]["cac"], 80.0)
        self.assertEqual(payload["overall"]["setter_spend"], 1000)
        self.assertEqual(payload["overall"]["tac"], 580.0)
        self.assertEqual(payload["contract"]["setter_unit_cost"], 500)
        kpis = payload["performance_kpis"]
        self.assertEqual(kpis["opportunities_created"], 0)
        self.assertEqual(kpis["sales"], 2)
        self.assertEqual(kpis["sits"], 0)
        self.assertIsNone(kpis["opp_to_prelim"])
        self.assertIsNone(kpis["demo_rate"])
        locker_kpi = {row["source"]: row for row in kpis["rows"]}["Lead Locker"]
        reviews_kpi = {row["source"]: row for row in kpis["rows"]}["Solar Reviews"]
        self.assertEqual(locker_kpi["opportunities_created"], 0)
        self.assertEqual(locker_kpi["sales"], 1)
        self.assertEqual(reviews_kpi["opportunities_created"], 0)
        self.assertEqual(reviews_kpi["sales"], 1)
        self.assertEqual(kpis["overall"]["source"], "Overall")
        self.assertEqual(kpis["created_sits_scope"], "territory_pipeline_attributed_via_inbound_contactId")
        self.assertTrue(kpis["join_exists"])
        self.assertEqual(kpis["join_field"], "ghl_opportunities_v2.contactId")
        self.assertIn("contactId", kpis["join_gap"])
        empty = metric.assemble_inbound_cac([], {}, set(), year=2026, month=None, now=now)
        self.assertIsNone(empty["overall"]["cac"])
        self.assertIsNone(empty["overall"]["tac"])
        self.assertTrue(all(v is None for v in empty["chart"]["lead_locker_cac"]))
        self.assertTrue(all(v is None for v in empty["chart"]["solar_reviews_cac"]))
        self.assertTrue(all(v is None for v in empty["chart"]["lead_locker_tac"]))
        self.assertTrue(all(v is None for v in empty["chart"]["solar_reviews_tac"]))


class SetterTacTests(unittest.TestCase):
    def test_setter_unit_cost_is_500_not_400(self):
        self.assertEqual(metric.SETTER_UNIT_COST, 500)
        self.assertEqual(metric.compute_setter_spend(3), 1500)
        self.assertEqual(metric.compute_setter_spend(0), 0)
        self.assertNotIn("SETTER_UNIT_COST = 400", METRIC_SRC)
        self.assertNotIn("$400", PAGE_SRC)
        self.assertIn("SETTER_UNIT_COST = 500", METRIC_SRC)
        self.assertIn("$500", PAGE_SRC)

    def test_tac_equals_cac_plus_500_when_sales_positive(self):
        self.assertEqual(metric.compute_tac(90, 1), 590.0)
        self.assertEqual(metric.compute_tac(90, 1), metric.compute_cac(90, 1) + 500)
        self.assertEqual(metric.compute_tac(135, 2), 567.5)
        self.assertEqual(metric.compute_tac(135, 2), metric.compute_cac(135, 2) + 500)
        rows = metric.build_source_rows(
            [
                metric.InboundOppRecord("Lead Locker", True, False, "c1"),
                metric.InboundOppRecord("Lead Locker", True, False, "c2"),
            ],
            {"c1", "c2"},
        )
        locker = {row["source"]: row for row in rows}["Lead Locker"]
        self.assertEqual(locker["cac"], 45.0)
        self.assertEqual(locker["tac"], locker["cac"] + 500)
        self.assertEqual(locker["setter_spend"], locker["sales"] * 500)

    def test_tac_is_json_null_when_sales_zero(self):
        self.assertIsNone(metric.compute_tac(450, 0))
        encoded = json.dumps({"tac": metric.compute_tac(450, 0)})
        self.assertIn('"tac": null', encoded)
        self.assertNotIn('"tac": 0', encoded)

    def test_still_un_navved_from_lead_generation(self):
        html = nav.render_dashboard_nav("inbound_cac")
        self.assertNotIn('href="/api/inbound_cac"', html)
        self.assertNotIn("Inbound CAC", html)


class PerformanceKpiTests(unittest.TestCase):
    def test_rates_are_null_when_opportunities_created_zero(self):
        row = metric.kpi_row(source="Lead Locker", opportunities_created=0, sits=2, sales=4)
        self.assertIsNone(row["opp_to_prelim"])
        self.assertIsNone(row["demo_rate"])
        encoded = json.dumps(row)
        self.assertIn('"opp_to_prelim": null', encoded)
        self.assertIn('"demo_rate": null', encoded)
        self.assertNotIn('"opp_to_prelim": 0', encoded)
        self.assertNotIn('"demo_rate": 0', encoded)

    def _territory(self, oid, contact_id, created, occurred=None, disposition=None, pipeline=None):
        return metric.TerritoryOpp(
            opportunity_id=oid,
            contact_id=contact_id,
            pipeline_id=pipeline or metric.TERRITORY_PIPELINE_IDS[0],
            created_local=created,
            occurred_utc=occurred,
            disposition=disposition,
        )

    def test_rows_are_attributed_territory_opps_not_inbound_bought_leads(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        start, end, _, _ = metric.ytd_window(2026, "America/New_York", now)
        raws = [
            metric.RawInboundOpp("Lead Locker", datetime(2026, 1, 5, 12, 0, tzinfo=NY), False, "c1"),
            metric.RawInboundOpp("Lead Locker", datetime(2026, 1, 6, 12, 0, tzinfo=NY), False, "c2"),
            metric.RawInboundOpp("Solar Reviews", datetime(2026, 1, 7, 12, 0, tzinfo=NY), False, "c3"),
        ]
        territory = [
            self._territory("t-ll-1", "c1", datetime(2026, 2, 10, 12, 0, tzinfo=NY), datetime(2026, 2, 11, 17, 0, tzinfo=timezone.utc), "Sit"),
            self._territory("t-ll-2", "c2", datetime(2026, 2, 12, 12, 0, tzinfo=NY)),
            self._territory("t-sr-1", "c3", datetime(2026, 2, 13, 12, 0, tzinfo=NY), datetime(2026, 2, 14, 17, 0, tzinfo=timezone.utc), "Sit"),
            self._territory("t-unattributed", "c-other", datetime(2026, 2, 15, 12, 0, tzinfo=NY), datetime(2026, 2, 16, 17, 0, tzinfo=timezone.utc), "Sit"),
        ]
        kpis = metric.build_performance_kpis(
            raws,
            territory,
            start,
            end,
            now.astimezone(timezone.utc),
            {"Lead Locker": 1, "Solar Reviews": 1},
        )
        self.assertEqual([row["source"] for row in kpis["rows"]], ["Lead Locker", "Solar Reviews"])
        locker = {row["source"]: row for row in kpis["rows"]}["Lead Locker"]
        reviews = {row["source"]: row for row in kpis["rows"]}["Solar Reviews"]
        self.assertEqual(locker["opportunities_created"], 2)
        self.assertEqual(locker["sits"], 1)
        self.assertEqual(locker["sales"], 1)
        self.assertEqual(locker["opp_to_prelim"], 0.5)
        self.assertEqual(locker["demo_rate"], 0.5)
        self.assertEqual(reviews["opportunities_created"], 1)
        self.assertEqual(reviews["sits"], 1)
        self.assertEqual(reviews["opp_to_prelim"], 1.0)
        self.assertEqual(reviews["demo_rate"], 1.0)
        self.assertEqual(kpis["overall"]["source"], "Overall")
        self.assertEqual(kpis["overall"]["opportunities_created"], 3)
        self.assertEqual(kpis["overall"]["sits"], 2)
        self.assertEqual(kpis["overall"]["sales"], 2)
        self.assertEqual(kpis["territory_pool_opportunities_created"], 4)
        self.assertEqual(kpis["unattributed_territory_opportunities_created"], 1)
        self.assertEqual(kpis["unattributed_territory_sits"], 1)
        self.assertEqual(kpis["created_sits_scope"], "territory_pipeline_attributed_via_inbound_contactId")
        self.assertTrue(kpis["join_exists"])
        self.assertEqual(kpis["join_field"], "ghl_opportunities_v2.contactId")
        self.assertIn("1 unattributed territory opportunities created left out of Overall", kpis["join_gap_short"])
        self.assertIn("hd5QqHEOVSsPom5bJ32P", kpis["join_gap"])
        self.assertNotEqual(kpis["overall"]["opportunities_created"], kpis["territory_pool_opportunities_created"])

    def test_refunded_inbound_title_still_attributes_territory_opp(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        start, end, _, _ = metric.ytd_window(2026, "America/New_York", now)
        raws = [
            metric.RawInboundOpp(
                "Lead Locker",
                datetime(2026, 2, 10, 12, 0, tzinfo=NY),
                True,
                "c-refunded",
                "opp-refunded",
            )
        ]
        territory = [
            self._territory("t-refunded", "c-refunded", datetime(2026, 2, 12, 12, 0, tzinfo=NY))
        ]
        kpis = metric.build_performance_kpis(
            raws, territory, start, end, now.astimezone(timezone.utc), {"Lead Locker": 0}
        )
        locker = {row["source"]: row for row in kpis["rows"]}["Lead Locker"]
        self.assertEqual(locker["opportunities_created"], 1)
        self.assertEqual(locker["sales"], 0)
        self.assertEqual(locker["opp_to_prelim"], 0.0)

    def test_inbound_bought_leads_are_not_opportunities_created(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        start, end, _, _ = metric.ytd_window(2026, "America/New_York", now)
        raws = [
            metric.RawInboundOpp("Lead Locker", datetime(2026, 2, 10, 12, 0, tzinfo=NY), False, "c1"),
        ]
        kpis = metric.build_performance_kpis(
            raws, [], start, end, now.astimezone(timezone.utc), {"Lead Locker": 43}
        )
        locker = {row["source"]: row for row in kpis["rows"]}["Lead Locker"]
        self.assertEqual(locker["opportunities_created"], 0)
        self.assertEqual(locker["sales"], 43)
        self.assertIsNone(locker["opp_to_prelim"])
        self.assertNotEqual(locker["opportunities_created"], 960)

    def test_page_kpi_table_matches_ytd_row_shape(self):
        page_html = page.render_html(2026)
        self.assertIn(">Sits</th>", PAGE_SRC)
        self.assertIn("kpis.rows", PAGE_SRC)
        self.assertIn("kpis.overall", PAGE_SRC)
        self.assertIn("join_gap_short", PAGE_SRC)
        self.assertEqual(PAGE_SRC.count('id="kpiJoinGap"'), 1)
        self.assertNotIn("0 of 1279", METRIC_SRC)
        self.assertIn("GQtUlcTmLJ61HZjrGEPC", METRIC_SRC)
        self.assertIn("qJNvqKWp8Xc7DaBr8QYc", METRIC_SRC)
        self.assertIn("etLURrEVxupngZZRlISG", METRIC_SRC)
        self.assertIn("r1b9pwgliYj7WyWBchTV", METRIC_SRC)
        self.assertIn("Lead Locker / Solar Reviews / Overall split", page_html)
        self.assertIn("Buffalo / Rochester / Syracuse / Virtual", page_html)

    def test_future_sit_is_excluded(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        start, end, _, _ = metric.ytd_window(2026, "America/New_York", now)
        raws = [
            metric.RawInboundOpp("Lead Locker", datetime(2026, 2, 10, 12, 0, tzinfo=NY), False, "c1")
        ]
        territory = [
            self._territory(
                "t-future",
                "c1",
                datetime(2026, 2, 10, 12, 0, tzinfo=NY),
                datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
                "Sit",
            )
        ]
        kpis = metric.build_performance_kpis(
            raws, territory, start, end, now.astimezone(timezone.utc), {"Lead Locker": 0}
        )
        locker = {row["source"]: row for row in kpis["rows"]}["Lead Locker"]
        self.assertEqual(locker["opportunities_created"], 1)
        self.assertEqual(locker["sits"], 0)

    def test_assemble_attributes_territory_via_inbound_contact_id(self):
        now = datetime(2026, 3, 15, tzinfo=NY)
        raws = [
            metric.RawInboundOpp(
                "Lead Locker",
                datetime(2026, 2, 10, 12, 0, tzinfo=NY),
                False,
                "c-feb-sold",
                "opp-ll",
            )
        ]
        contacts_map = {
            "c-feb-sold": {
                "customFields": [{"id": "P9oBjgbZjJdeE0OkBj9T", "value": "2026-02-11"}]
            }
        }
        territory = [
            self._territory(
                "t-buffalo",
                "c-feb-sold",
                datetime(2026, 2, 10, 14, 0, tzinfo=NY),
                datetime(2026, 2, 11, 17, 0, tzinfo=timezone.utc),
                "Sit",
            )
        ]
        payload = metric.assemble_inbound_cac(
            raws,
            contacts_map,
            {"c-feb-sold"},
            year=2026,
            month=None,
            now=now,
            territory_opps=territory,
        )
        locker = {row["source"]: row for row in payload["rows"]}["Lead Locker"]
        self.assertEqual(locker["spend"], 45)
        self.assertEqual(locker["sales"], 1)
        self.assertEqual(locker["cac"], 45.0)
        self.assertEqual(locker["tac"], 545.0)
        self.assertEqual(payload["overall"]["sales"], 1)
        kpis = payload["performance_kpis"]
        self.assertEqual(kpis["opportunities_created"], 1)
        self.assertEqual(kpis["sales"], 1)
        self.assertEqual(kpis["sits"], 1)
        self.assertEqual(kpis["opp_to_prelim"], 1.0)
        self.assertEqual(kpis["demo_rate"], 1.0)
        self.assertEqual(kpis["created_sits_scope"], "territory_pipeline_attributed_via_inbound_contactId")
        self.assertTrue(payload["contract"]["performance_kpis"]["inbound_to_four_pipeline_join_exists"])
        self.assertEqual(
            payload["contract"]["performance_kpis"]["inbound_to_four_pipeline_join_field"],
            "ghl_opportunities_v2.contactId",
        )
        self.assertTrue(payload["contract"]["performance_kpis"]["lead_gen_source_is_not_the_split"])

    def test_inclusive_range_window_is_america_new_york(self):
        start, end, start_iso, end_iso = metric.date_range_window(
            "2026-04-03", "2026-04-05", "America/New_York"
        )
        self.assertEqual(start, datetime(2026, 4, 3, 0, 0, 0, tzinfo=NY))
        self.assertEqual(end, datetime(2026, 4, 6, 0, 0, 0, tzinfo=NY))
        self.assertTrue(start_iso.startswith("2026-04-03"))
        self.assertTrue(end_iso.startswith("2026-04-06"))

    def test_created_and_sits_use_bounded_territory_queries(self):
        self.assertIn('.where("pipelineId", "==", INBOUND_PIPELINE_ID)', METRIC_SRC)
        self.assertIn("appointmentOccurredAt", METRIC_SRC)
        self.assertIn("dispositionValue", METRIC_SRC)
        self.assertIn("load_territory_created", METRIC_SRC)
        self.assertIn("load_territory_sits", METRIC_SRC)
        self.assertIn("TERRITORY_PIPELINE_IDS", METRIC_SRC)
        self.assertNotIn('db.collection(OPP_COLLECTION).stream()', METRIC_SRC)
        self.assertIn("parse_optional_range", METRIC_SRC)
        self.assertIn("territory_pipeline_attributed_via_inbound_contactId", METRIC_SRC)
        self.assertIn("hd5QqHEOVSsPom5bJ32P", METRIC_SRC)
        self.assertIn("lead_gen_source_is_not_the_split", METRIC_SRC)

    def test_demo_rate_is_not_sit_over_sit_plus_no_sit(self):
        self.assertIn("not Bot KPI Sit/(Sit+No Sit)", METRIC_SRC)
        self.assertIn("that source's sits / that source's opportunities_created", METRIC_SRC)
        self.assertEqual(metric.SIT_DISPOSITION, "Sit")
        self.assertEqual(metric.APPOINTMENT_OCCURRED_AT_FIELD, "appointmentOccurredAt")
        self.assertEqual(metric.INBOUND_COHORT_SCOPE, "territory_pipeline_attributed_via_inbound_contactId")
        self.assertEqual(metric.INBOUND_FOUR_PIPELINE_JOIN_FIELD, "ghl_opportunities_v2.contactId")
        self.assertEqual(metric.LEAD_GEN_SOURCE_CONTACT_CF_ID, "hd5QqHEOVSsPom5bJ32P")


if __name__ == "__main__":
    unittest.main()
