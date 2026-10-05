# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
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


metric = load_module("paid_social_funnel_metric", METRICS / "paid_social_funnel.py")
page = load_module("paid_social_funnel_page", API / "paid_social_funnel.py")
nav = load_module("dashboard_nav_paid_social", API / "dashboard_nav.py")
sales = load_module("sales_for_paid_social", METRICS / "sales.py")
index = load_module("index_for_paid_social", API / "index.py")

METRIC_SRC = (METRICS / "paid_social_funnel.py").read_text(encoding="utf-8")
PAGE_SRC = (API / "paid_social_funnel.py").read_text(encoding="utf-8")
SALES_SRC = (METRICS / "sales.py").read_text(encoding="utf-8")
NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
PIPELINE = metric.LEAD_PIPELINE_ID
FIELD = metric.SOURCE_FIELD_ID
SOLD_FIELD = metric.SOLD_DATE_FIELD_ID
VIRTUAL = "r1b9pwgliYj7WyWBchTV"
BUFFALO = "GQtUlcTmLJ61HZjrGEPC"
WORD = re.compile(r"\b(sit|sits|sat)\b", re.IGNORECASE)


def contact(contact_id: str, source: str | None, sold: str | None = None) -> dict:
    fields = []
    if source is not None:
        fields.append({"id": FIELD, "value": source})
    if sold is not None:
        fields.append({"id": SOLD_FIELD, "value": sold})
    return {"id": contact_id, "customFields": fields}


def pipeline_opp(
    opp_id: str,
    contact_id: str,
    created: str,
    *,
    name: str = "Lead Locker: not the lead number",
    stage: str = "open-stage",
) -> dict:
    return {
        "id": opp_id,
        "pipelineId": PIPELINE,
        "contactId": contact_id,
        "name": name,
        "createdAt": created,
        "pipelineStageId": stage,
    }


def territory(
    opp_id: str,
    contact_id: str,
    pipeline_id: str,
    created_local: datetime,
    *,
    occurred_utc: datetime | None = None,
    disposition: str | None = None,
):
    return metric.cac.TerritoryOpp(
        opportunity_id=opp_id,
        contact_id=contact_id,
        pipeline_id=pipeline_id,
        created_local=created_local,
        occurred_utc=occurred_utc,
        disposition=disposition,
    )


def run_window(start: str, end: str, pipeline, created, demos, sold_ids, contacts):
    start_local, end_local, _, _ = metric.cac.date_range_window(start, end, "America/New_York")
    counts = metric.count_paid_social(
        pipeline,
        created,
        demos,
        sold_ids,
        contacts,
        start_local,
        end_local,
        NOW,
    )
    payload = metric.assemble_paid_social(
        counts,
        start_local=start_local,
        end_local=end_local,
        daily_meta={"status": "unavailable", "rows": [], "lead_actions_ignored": False},
        aggregate_spend=metric.cac.unavailable_meta_spend("missing_env"),
    )
    return counts, payload


class SourceFilterTests(unittest.TestCase):
    def test_only_stripped_inbound_matches(self):
        self.assertTrue(metric.source_is_inbound(contact("c", "Inbound")))
        self.assertTrue(metric.source_is_inbound(contact("c", " inbound ")))
        self.assertTrue(metric.source_is_inbound(contact("c", "INBOUND")))
        self.assertFalse(metric.source_is_inbound(contact("c", "3PL")))
        self.assertFalse(metric.source_is_inbound(contact("c", "3pl")))
        self.assertFalse(metric.source_is_inbound(contact("c", "Doors")))
        self.assertFalse(metric.source_is_inbound(contact("c", "")))
        self.assertFalse(metric.source_is_inbound(contact("c", None)))
        self.assertFalse(metric.source_is_inbound(contact("c", "   ")))
        self.assertFalse(metric.source_is_inbound({"customFields": []}))
        self.assertFalse(metric.source_is_inbound(None))

    def test_module_does_not_use_title_buckets_or_the_form_fill_row(self):
        self.assertNotIn("bucket_title(", METRIC_SRC)
        self.assertNotIn("compute_inbound_cac", METRIC_SRC)
        self.assertNotIn("count_inbound_named_fills", METRIC_SRC)
        self.assertNotIn("build_performance_kpis", METRIC_SRC)
        self.assertNotIn("7981f111-73f2-4593-9662-6b95d99bf51a", METRIC_SRC)
        self.assertEqual(
            metric.SOLD_DATE_FIELD_ID,
            sales.SalesMetricContract().sold_date_custom_field_id,
        )
        self.assertEqual(set(metric.TERRITORY_PIPELINE_NAMES), set(metric.cac.TERRITORY_PIPELINE_IDS))

    def test_meta_read_is_account_level_and_skips_lead_actions(self):
        url = metric.insights_request_url(
            metric.META_ACCOUNT_ID,
            "test-token",
            "2026-10-01",
            "2026-10-04",
            "1",
        )
        parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
        query = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query)
        self.assertEqual(query["fields"][0], "impressions,outbound_clicks,spend")
        self.assertNotIn("landing_page_views", query["fields"][0])
        self.assertNotIn("actions", query["fields"][0].split(","))
        self.assertEqual(query["level"][0], "account")
        self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, parsed.path)
        self.assertNotIn("campaign", query)
        self.assertIn('method="GET"', METRIC_SRC)


class EvidenceWindowTests(unittest.TestCase):
    def test_oct1_through_oct4_does_not_plot_pipeline_opps_as_leads(self):
        contacts = {}
        pipeline = []
        created = []
        demos = []
        for index in range(5):
            contact_id = f"blank-{index}"
            contacts[contact_id] = contact(contact_id, None, sold="2026-10-02")
            pipeline.append(
                pipeline_opp(
                    f"p-{index}",
                    contact_id,
                    "2026-10-02T15:00:00+00:00",
                    name="Lead Locker: blank source",
                )
            )
            created.append(
                territory(
                    f"t-{index}",
                    contact_id,
                    BUFFALO,
                    datetime(2026, 10, 2, 12, 0, tzinfo=NY),
                    occurred_utc=datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc),
                    disposition="Sit",
                )
            )
            demos.append(created[-1])
        counts, payload = run_window(
            "2026-10-01",
            "2026-10-04",
            pipeline,
            created,
            demos,
            set(contacts),
            contacts,
        )
        self.assertEqual(payload["window_start_local"], "2026-10-01T00:00:00-04:00")
        self.assertEqual(payload["window_end_local"], "2026-10-05T00:00:00-04:00")
        leads = payload["funnel"][3]
        opps = payload["funnel"][4]
        self.assertEqual(leads["total"], 0)
        self.assertEqual(counts["pipeline_opportunities_in_window"], 5)
        self.assertNotEqual(leads["total"], 5)
        self.assertEqual(leads["excluded_by_source"], {"(blank)": 5})
        self.assertTrue(all(point["value"] == 0 for point in leads["series"]))
        self.assertNotIn(5, [point["value"] for point in leads["series"]])
        self.assertEqual(opps["total"], 0)
        self.assertEqual(payload["demos"]["total"], 0)
        self.assertEqual(payload["demos"]["note"], "no demo")
        self.assertEqual(payload["sales"]["total"], 0)
        self.assertIsNone(payload["kpis"]["cost_per_lead"]["value"])
        self.assertEqual(payload["kpis"]["cost_per_lead"]["target"], 25)
        self.assertIsNone(payload["kpis"]["cost_per_demo"]["value"])
        self.assertEqual(payload["kpis"]["cost_per_demo"]["target"], 50)

    def test_sep7_through_oct4_matches_source_filter(self):
        contacts = {}
        pipeline = []
        created = []
        demos = []
        lead_ids = ("c1", "c2", "c3")
        created_at = (
            "2026-09-10T15:00:00+00:00",
            "2026-09-12T15:00:00+00:00",
            "2026-09-20T15:00:00+00:00",
        )
        for contact_id, stamp in zip(lead_ids, created_at):
            contacts[contact_id] = contact(contact_id, "Inbound", sold="2026-08-15")
            pipeline.append(
                pipeline_opp(f"lead-{contact_id}", contact_id, stamp, name="Website form")
            )
        contacts["c1"] = contact("c1", "Inbound", sold="2026-08-15T00:00:00.000Z")
        territory_rows = (
            ("opp-v1", "c1", VIRTUAL, datetime(2026, 9, 11, 11, 0, tzinfo=NY), datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc), "Sit"),
            ("opp-v2", "c2", VIRTUAL, datetime(2026, 9, 14, 11, 0, tzinfo=NY), None, None),
            ("opp-b1", "c3", BUFFALO, datetime(2026, 9, 21, 11, 0, tzinfo=NY), None, None),
        )
        for opp_id, contact_id, pipeline_id, created_local, occurred, disposition in territory_rows:
            row = territory(
                opp_id,
                contact_id,
                pipeline_id,
                created_local,
                occurred_utc=occurred,
                disposition=disposition,
            )
            created.append(row)
            if disposition:
                demos.append(row)
        for index in range(97):
            contact_id = f"blank-{index}"
            contacts[contact_id] = contact(contact_id, None)
            pipeline.append(pipeline_opp(f"blank-{index}", contact_id, "2026-09-15T15:00:00+00:00", name="Lead Locker: blank"))
        for index in range(13):
            contact_id = f"3pl-{index}"
            contacts[contact_id] = contact(contact_id, "3PL", sold="2026-09-20")
            pipeline.append(pipeline_opp(f"3pl-{index}", contact_id, "2026-09-16T15:00:00+00:00", name="Solar Reviews: 3PL"))
        for index in range(2):
            contact_id = f"doors-{index}"
            contacts[contact_id] = contact(contact_id, "Doors", sold="2026-09-22")
            pipeline.append(pipeline_opp(f"doors-{index}", contact_id, "2026-09-18T15:00:00+00:00", name="Doors"))
            demos.append(
                territory(
                    f"doors-demo-{index}",
                    contact_id,
                    BUFFALO,
                    datetime(2026, 9, 19, 11, 0, tzinfo=NY),
                    occurred_utc=datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc),
                    disposition="Sit",
                )
            )
        contacts["before"] = contact("before", "Inbound", sold="2026-09-20")
        pipeline.append(pipeline_opp("before-window", "before", "2026-09-06T15:00:00+00:00"))
        created.append(
            territory(
                "before-opp",
                "before",
                VIRTUAL,
                datetime(2026, 9, 8, 11, 0, tzinfo=NY),
            )
        )
        sold_ids = {f"3pl-{index}" for index in range(13)}
        sold_ids.update({f"doors-{index}" for index in range(2)})
        sold_ids.add("c1")
        sold_ids.add("before")
        counts, payload = run_window(
            "2026-09-07",
            "2026-10-04",
            pipeline,
            created,
            demos,
            sold_ids,
            contacts,
        )
        leads = payload["funnel"][3]
        opps = payload["funnel"][4]
        self.assertEqual(payload["window_start_local"], "2026-09-07T00:00:00-04:00")
        self.assertEqual(payload["window_end_local"], "2026-10-05T00:00:00-04:00")
        self.assertEqual(counts["pipeline_opportunities_in_window"], 115)
        self.assertEqual(leads["total"], 3)
        self.assertEqual(leads["matched_source_values"], {"Inbound": 3})
        self.assertEqual(leads["excluded_by_source"], {"(blank)": 97, "3PL": 13, "Doors": 2})
        self.assertEqual(leads["refunded_leads"], 0)
        self.assertNotIn(leads["total"], (5, 72, 115, 51, 21))
        self.assertNotIn(115, [point["value"] for point in leads["series"]])
        self.assertEqual(sum(point["value"] for point in leads["series"]), 3)
        self.assertEqual(opps["total"], 3)
        self.assertEqual(opps["by_territory"]["Virtual"], 2)
        self.assertEqual(opps["by_territory"]["Buffalo"], 1)
        self.assertEqual(opps["by_territory"]["Rochester"], 0)
        self.assertEqual(opps["by_territory"]["Syracuse"], 0)
        self.assertEqual(payload["demos"]["total"], 1)
        self.assertEqual(payload["sales"]["total"], 0)
        self.assertIsNone(payload["kpis"]["cost_per_acquisition"]["value"])
        self.assertEqual(payload["kpis"]["cost_per_acquisition"]["target"], 200)

    def test_window_edges_and_refunded_inbound_still_match_the_source_rule(self):
        contacts = {
            "edge": contact("edge", "Inbound"),
            "late": contact("late", "Inbound"),
            "refunded": contact("refunded", "Inbound"),
        }
        pipeline = [
            pipeline_opp("edge", "edge", "2026-10-05T03:30:00+00:00", name="not a title"),
            pipeline_opp("late", "late", "2026-10-05T04:00:00+00:00"),
            pipeline_opp(
                "refunded",
                "refunded",
                "2026-09-10T15:00:00+00:00",
                stage=metric.cac.REFUNDED_STAGE_ID,
            ),
        ]
        _counts, payload = run_window("2026-10-01", "2026-10-04", pipeline, [], [], set(), contacts)
        self.assertEqual(payload["funnel"][3]["total"], 1)
        _counts, wider = run_window("2026-09-07", "2026-10-04", pipeline, [], [], set(), contacts)
        self.assertEqual(wider["funnel"][3]["total"], 2)
        self.assertEqual(wider["funnel"][3]["refunded_leads"], 1)


ROCHESTER = "qJNvqKWp8Xc7DaBr8QYc"
SYRACUSE = "etLURrEVxupngZZRlISG"


def demo_row(opp_id, contact_id, pipeline_id, occurred_utc, disposition="Sit"):
    return territory(
        opp_id,
        contact_id,
        pipeline_id,
        datetime(2026, 9, 1, 11, 0, tzinfo=NY),
        occurred_utc=occurred_utc,
        disposition=disposition,
    )


class LeadDefinitionTests(unittest.TestCase):
    def test_only_inbound_source_in_the_lead_pipeline_is_a_lead(self):
        sources = {
            "in-1": "Inbound",
            "in-2": " inbound ",
            "in-3": "INBOUND",
            "tpl": "3PL",
            "doors": "Doors",
            "empty": "",
            "spaces": "   ",
            "none": None,
        }
        contacts = {cid: contact(cid, value) for cid, value in sources.items()}
        pipeline = [pipeline_opp(f"opp-{cid}", cid, "2026-10-02T15:00:00+00:00") for cid in sources]
        contacts["terr"] = contact("terr", "Inbound")
        pipeline.append(
            {
                "id": "territory-not-lead",
                "pipelineId": BUFFALO,
                "contactId": "terr",
                "createdAt": "2026-10-02T15:00:00+00:00",
            }
        )
        counts, payload = run_window("2026-10-01", "2026-10-04", pipeline, [], [], set(), contacts)
        leads = payload["funnel"][3]
        self.assertEqual(leads["total"], 3)
        self.assertEqual(counts["lead_contacts"], {"in-1", "in-2", "in-3"})
        self.assertEqual(counts["pipeline_opportunities_in_window"], 8)
        self.assertEqual(leads["excluded_by_source"], {"3PL": 1, "Doors": 1, "(blank)": 3})
        self.assertIn("Doors", payload["lead_definition"]["does_not_match"])
        self.assertIn("Doors do not count", leads["note"])
        self.assertIn("Not every opportunity in that pipeline is a lead", leads["note"])


class DemoDefinitionTests(unittest.TestCase):
    def test_inbound_territory_demo_counts_without_a_lead_pipeline_opp(self):
        contacts = {cid: contact(cid, "Inbound") for cid in ("b", "r", "s", "v")}
        demos = [
            demo_row("d-b", "b", BUFFALO, datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)),
            demo_row("d-r", "r", ROCHESTER, datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)),
            demo_row("d-s", "s", SYRACUSE, datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)),
            demo_row("d-v", "v", VIRTUAL, datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)),
        ]
        counts, payload = run_window("2026-10-01", "2026-10-04", [], [], demos, set(), contacts)
        self.assertEqual(counts["leads"], 0)
        self.assertEqual(payload["demos"]["total"], 4)
        self.assertEqual(
            payload["demos"]["by_territory"],
            {"Buffalo": 1, "Rochester": 1, "Syracuse": 1, "Virtual": 1},
        )
        self.assertEqual([point["value"] for point in payload["demos"]["series"]], [1, 1, 1, 1])
        self.assertEqual(payload["demos"]["note"], metric.DEMO_NOTE)
        self.assertIsNone(WORD.search(payload["demos"]["note"]))
        definition = payload["demo_definition"]
        self.assertEqual(set(definition["pipeline_ids"]), {BUFFALO, ROCHESTER, SYRACUSE, VIRTUAL})
        self.assertEqual(definition["excluded_pipeline_ids"], [PIPELINE])
        self.assertEqual(definition["outcome_field"], "dispositionValue")
        self.assertEqual(definition["outcome_value"], metric.cac.SIT_DISPOSITION)
        self.assertEqual(definition["date_field"], "appointmentOccurredAt")
        self.assertFalse(definition["limited_to_lead_contacts"])

    def test_non_inbound_source_is_not_a_demo(self):
        contacts = {
            "tpl": contact("tpl", "3PL"),
            "doors": contact("doors", "Doors"),
            "blank": contact("blank", None),
            "self": contact("self", "Self Gen"),
        }
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        demos = [demo_row(f"d-{cid}", cid, BUFFALO, occurred) for cid in contacts]
        demos.append(demo_row("d-missing", "no-contact-doc", VIRTUAL, occurred))
        _counts, payload = run_window("2026-10-01", "2026-10-04", [], [], demos, set(), contacts)
        self.assertEqual(payload["demos"]["total"], 0)
        self.assertEqual(payload["demos"]["note"], "no demo")
        self.assertEqual(
            payload["demos"]["excluded_by_source"],
            {"3PL": 1, "Doors": 1, "(blank)": 2, "Self Gen": 1},
        )

    def test_inbound_territory_opp_without_the_exact_outcome_is_not_a_demo(self):
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        outcomes = (None, "", "No Sit", "sit", "SIT", "Rescheduled", "Cancelled")
        contacts = {f"c{i}": contact(f"c{i}", "Inbound") for i in range(len(outcomes))}
        demos = [
            demo_row(f"d{i}", f"c{i}", VIRTUAL, occurred, disposition=value)
            for i, value in enumerate(outcomes)
        ]
        _counts, payload = run_window("2026-10-01", "2026-10-04", [], [], demos, set(), contacts)
        self.assertEqual(payload["demos"]["total"], 0)
        self.assertEqual(payload["demos"]["excluded_by_source"], {})

    def test_lead_pipeline_opp_is_never_a_demo(self):
        contacts = {"lead": contact("lead", "Inbound")}
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        pipeline = [pipeline_opp("lead-opp", "lead", "2026-10-02T14:00:00+00:00")]
        demos = [
            demo_row("lead-opp", "lead", PIPELINE, occurred),
            demo_row("other", "lead", "someOtherPipeline", occurred),
        ]
        counts, payload = run_window("2026-10-01", "2026-10-04", pipeline, [], demos, set(), contacts)
        self.assertEqual(counts["leads"], 1)
        self.assertEqual(payload["demos"]["total"], 0)

    def test_lead_contact_demo_still_needs_its_own_rule(self):
        contacts = {"lead": contact("lead", "Inbound"), "other": contact("other", "Inbound")}
        pipeline = [pipeline_opp("lead-opp", "lead", "2026-10-02T14:00:00+00:00")]
        occurred = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
        demos = [
            demo_row("lead-demo", "lead", ROCHESTER, occurred),
            demo_row("other-demo", "other", SYRACUSE, occurred),
            demo_row("lead-no-outcome", "lead", BUFFALO, occurred, disposition=None),
        ]
        _counts, payload = run_window("2026-10-01", "2026-10-04", pipeline, [], demos, set(), contacts)
        self.assertEqual(payload["funnel"][3]["total"], 1)
        self.assertEqual(payload["demos"]["total"], 2)
        self.assertEqual(payload["demos"]["by_territory"]["Rochester"], 1)
        self.assertEqual(payload["demos"]["by_territory"]["Syracuse"], 1)
        self.assertEqual(payload["demos"]["by_territory"]["Buffalo"], 0)

    def test_demo_window_uses_new_york_appointment_time_and_dedupes(self):
        contacts = {cid: contact(cid, "Inbound") for cid in ("early", "first", "last", "next", "future", "dup")}
        demos = [
            demo_row("early", "early", BUFFALO, datetime(2026, 10, 1, 3, 59, tzinfo=timezone.utc)),
            demo_row("first", "first", BUFFALO, datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)),
            demo_row("last", "last", VIRTUAL, datetime(2026, 10, 5, 3, 59, tzinfo=timezone.utc)),
            demo_row("next", "next", VIRTUAL, datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)),
            demo_row("dup", "dup", SYRACUSE, datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)),
            demo_row("dup", "dup", SYRACUSE, datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)),
            demo_row("no-time", "dup", SYRACUSE, None),
        ]
        _counts, payload = run_window("2026-10-01", "2026-10-04", [], [], demos, set(), contacts)
        self.assertEqual(payload["demos"]["total"], 3)
        by_day = {point["date"]: point["value"] for point in payload["demos"]["series"]}
        self.assertEqual(by_day, {"2026-10-01": 1, "2026-10-02": 1, "2026-10-03": 0, "2026-10-04": 1})

        start_local, end_local, _, _ = metric.cac.date_range_window("2026-10-01", "2026-10-31", "America/New_York")
        future = [demo_row("future", "future", BUFFALO, datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc))]
        counts = metric.count_paid_social([], [], future, set(), contacts, start_local, end_local, NOW)
        self.assertEqual(counts["demos"], 0)

    def test_loader_keeps_only_the_exact_outcome_on_territory_pipelines(self):
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        docs = [
            {"id": "ok", "pipelineId": BUFFALO, "contactId": "c", "dispositionValue": "Sit", "appointmentOccurredAt": occurred},
            {"id": "pad", "pipelineId": BUFFALO, "contactId": "c", "dispositionValue": " Sit ", "appointmentOccurredAt": occurred},
            {"id": "lower", "pipelineId": BUFFALO, "contactId": "c", "dispositionValue": "sit", "appointmentOccurredAt": occurred},
            {"id": "nosit", "pipelineId": VIRTUAL, "contactId": "c", "dispositionValue": "No Sit", "appointmentOccurredAt": occurred},
            {"id": "lead", "pipelineId": PIPELINE, "contactId": "c", "dispositionValue": "Sit", "appointmentOccurredAt": occurred},
        ]

        class Snap:
            def __init__(self, doc):
                self.id = doc["id"]
                self._doc = doc

            def to_dict(self):
                return dict(self._doc)

        class Query:
            def where(self, *_args):
                return self

            def stream(self):
                return [Snap(doc) for doc in docs]

        class Db:
            def collection(self, _name):
                return Query()

        start_local, end_local, _, _ = metric.cac.date_range_window("2026-10-01", "2026-10-04", "America/New_York")
        loaded = metric.cac.load_territory_sits(Db(), start_local, end_local, NOW)
        self.assertEqual([opp.opportunity_id for opp in loaded], ["ok"])

    def test_live_records_load_contacts_for_demo_only_opps(self):
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        demo_only = demo_row("demo-only", "walk-in", VIRTUAL, occurred)
        requested = {}

        def load_contacts(_db, ids):
            requested["ids"] = set(ids)
            return {"walk-in": contact("walk-in", "Inbound")}

        with patch.object(metric.cac, "load_inbound_opps", return_value=[]), \
                patch.object(metric.cac, "load_territory_created", return_value=[]), \
                patch.object(metric.cac, "load_territory_sits", return_value=[demo_only]), \
                patch.object(metric.cac, "load_sold_stage_contact_ids", return_value=set()), \
                patch.object(metric.cac, "load_contacts_by_ids", side_effect=load_contacts):
            payload = metric.compute_paid_social_funnel(
                object(),
                start="2026-10-01",
                end="2026-10-04",
                now=NOW,
                token="test-token",
                account_id=metric.META_ACCOUNT_ID,
                daily_fetcher=lambda _s, _e: {"status": "unavailable", "rows": [], "lead_actions_ignored": False},
                aggregate_fetcher=lambda _s, _e: metric.cac.unavailable_meta_spend("missing_env"),
                ga4_fetcher=lambda _s, _e: {},
            )
        self.assertIn("walk-in", requested["ids"])
        self.assertEqual(payload["funnel"][3]["total"], 0)
        self.assertEqual(payload["demos"]["total"], 1)
        model = growth.live_model(payload)
        self.assertEqual(model["kpis"]["demos"]["value"], 1)
        demo_stage = [stage for stage in model["stages"] if stage["key"] == "demos"][0]
        self.assertEqual(demo_stage["label"], "Demos")
        self.assertEqual(demo_stage["value"], 1)
        html = page.render_html(model=model)
        self.assertIn(">Demos<", html)
        self.assertIn("It does not have to be one of the lead contacts", html)
        self.assertIsNone(WORD.search(html))
        self.assertIsNone(WORD.search(metric.DEMO_NOTE))
        self.assertIsNone(WORD.search(metric.LEAD_NOTE))


class MetaAndVisitorTests(unittest.TestCase):
    def _counts(self):
        start_local, end_local, _, _ = metric.cac.date_range_window("2026-10-01", "2026-10-02", "America/New_York")
        counts = metric.count_paid_social([], [], [], set(), {}, start_local, end_local, NOW)
        return start_local, end_local, counts

    def test_missing_meta_and_visitors_stay_blank(self):
        start_local, end_local, counts = self._counts()
        payload = metric.assemble_paid_social(
            counts,
            start_local=start_local,
            end_local=end_local,
            daily_meta={"status": "unavailable", "rows": [], "lead_actions_ignored": True},
            aggregate_spend=metric.cac.unavailable_meta_spend("missing_env"),
        )
        steps = {step["key"]: step for step in payload["funnel"]}
        self.assertIsNone(steps["ad_views"]["series"])
        self.assertIsNone(steps["ad_views"]["total"])
        self.assertIsNone(steps["clicks"]["series"])
        self.assertEqual(steps["website_visitors"]["status"], "not_wired")
        self.assertIsNone(steps["website_visitors"]["total"])
        self.assertIsNone(steps["website_visitors"]["series"])
        self.assertEqual(steps["website_visitors"]["measurement_id"], "G-V02RZFR4SZ")
        self.assertIn("not wired", steps["website_visitors"]["note"])
        self.assertFalse(payload["meta_lead_actions"]["plotted"])
        self.assertIsNone(payload["meta_lead_actions"]["series"])
        self.assertEqual(payload["meta_lead_actions"]["status"], "absent_not_zero")
        self.assertTrue(payload["spend"]["unmatched"])
        self.assertNotIn('"total": 0', json.dumps(steps["ad_views"]))
        self.assertNotIn('"total": 0', json.dumps(steps["clicks"]))
        self.assertNotIn('"total": 0', json.dumps(steps["website_visitors"]))

    def test_spend_gap_is_labeled_and_not_picked(self):
        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")

            def read(self):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def urlopen(req, timeout=20):
            self.assertEqual(req.method, "GET")
            self.assertNotIn("actions", req.full_url.split("fields=")[1].split("&", 1)[0])
            return Response(
                {
                    "data": [
                        {
                            "date_start": "2026-10-01",
                            "impressions": "10",
                            "clicks": "2",
                            "spend": "50.00",
                            "actions": [{"action_type": "lead", "value": "0"}],
                        },
                        {"date_start": "2026-10-02", "spend": "60.11"},
                    ]
                }
            )

        daily = metric.fetch_meta_daily(
            datetime(2026, 10, 1, tzinfo=NY),
            datetime(2026, 10, 3, tzinfo=NY),
            token="test-token",
            account_id=metric.META_ACCOUNT_ID,
            urlopen=urlopen,
        )
        self.assertTrue(daily["lead_actions_ignored"])
        self.assertNotIn("actions", daily["rows"][0])
        self.assertEqual(daily["rows"][0]["impressions"], 10)
        self.assertIsNone(daily["rows"][1]["impressions"])
        self.assertIsNone(daily["rows"][1]["clicks"])
        start_local, end_local, counts = self._counts()
        counts["leads"] = 2
        counts["opps"] = 2
        counts["demos"] = 1
        counts["sales"] = 1
        payload = metric.assemble_paid_social(
            counts,
            start_local=start_local,
            end_local=end_local,
            daily_meta=daily,
            aggregate_spend=metric.cac.MetaSpendResult(
                spend=110.60,
                spend_status="ok",
                account_id=metric.META_ACCOUNT_ID,
            ),
        )
        gap = payload["spend"]["gap"]
        self.assertEqual(gap["account_insights_total"], 110.60)
        self.assertEqual(gap["daily_rows_sum"], 110.11)
        self.assertIn("does not pick one", gap["note"])
        self.assertIn("Neither figure is tied to a lead or an opp", gap["note"])
        self.assertIsNone(payload["spend"]["spend"])
        self.assertIsNone(payload["kpis"]["cost_per_lead"]["value"])
        by_spend = payload["kpis"]["cost_per_lead"]["by_spend"]
        self.assertEqual(by_spend["account_insights_total"], round(110.60 / 2, 2))
        self.assertEqual(by_spend["daily_rows_sum"], round(110.11 / 2, 2))
        self.assertNotEqual(by_spend["account_insights_total"], by_spend["daily_rows_sum"])
        views = {step["key"]: step for step in payload["funnel"]}["ad_views"]
        by_day = {point["date"]: point["value"] for point in views["series"]}
        self.assertEqual(by_day["2026-10-01"], 10)
        self.assertIsNone(by_day["2026-10-02"])
        self.assertNotIn("lead", json.dumps(payload["meta_lead_actions"]["series"]))

    def test_agreed_spend_sets_costs_against_targets(self):
        start_local, end_local, counts = self._counts()
        counts["leads"] = 3
        counts["opps"] = 3
        counts["demos"] = 1
        counts["sales"] = 1
        daily = {
            "status": "ok",
            "rows": [
                {"date": "2026-10-01", "impressions": 4, "clicks": 1, "spend": 30.0},
                {"date": "2026-10-02", "impressions": 0, "clicks": 0, "spend": 60.0},
            ],
            "lead_actions_ignored": False,
        }
        payload = metric.assemble_paid_social(
            counts,
            start_local=start_local,
            end_local=end_local,
            daily_meta=daily,
            aggregate_spend=metric.cac.MetaSpendResult(spend=90.0, spend_status="ok"),
        )
        self.assertIsNone(payload["spend"]["gap"])
        self.assertEqual(payload["spend"]["spend"], 90.0)
        self.assertTrue(payload["spend"]["unmatched"])
        self.assertEqual(payload["kpis"]["cost_per_lead"]["value"], 30.0)
        self.assertEqual(payload["kpis"]["cost_per_lead"]["target"], 25)
        self.assertEqual(payload["kpis"]["cost_per_opp"]["value"], 30.0)
        self.assertIsNone(payload["kpis"]["cost_per_opp"]["target"])
        self.assertEqual(payload["kpis"]["cost_per_demo"]["value"], 90.0)
        self.assertEqual(payload["kpis"]["cost_per_demo"]["target"], 50)
        self.assertEqual(payload["kpis"]["cost_per_acquisition"]["value"], 90.0)
        self.assertEqual(payload["kpis"]["cost_per_acquisition"]["target"], 200)
        views = {step["key"]: step for step in payload["funnel"]}["ad_views"]
        self.assertEqual([point["value"] for point in views["series"]], [4, 0])


growth = load_module("growth_command_center", METRICS / "growth_command.py")


class GrowthFixtureTests(unittest.TestCase):
    def setUp(self):
        self.model = growth.demo_model()

    def test_fixture_formulas_match_the_guide(self):
        self.assertEqual(sum(growth.DAILY_LEADS), 8)
        self.assertEqual(sum(growth.DAILY_SPEND), 240)
        self.assertEqual(sum(growth.DAILY_IMPRESSIONS), 24000)
        self.assertEqual(sum(growth.DAILY_CLICKS), 400)
        self.assertEqual(sum(growth.DAILY_VISITS), 320)
        self.assertEqual(sum(growth.DAILY_FORM_STARTS), 40)
        self.assertEqual(sum(growth.DAILY_DEMOS), 4)
        self.assertEqual(sum(growth.DAILY_SOLD), 1)
        self.assertEqual(self.model["kpis"]["leads"]["text"], "8/20")
        self.assertEqual(self.model["kpis"]["leads"]["percent_label"], "40%")
        self.assertEqual(self.model["kpis"]["leads"]["pace"], "2 behind pace")
        self.assertEqual(self.model["pace"]["expected"], 10)
        self.assertEqual(self.model["kpis"]["cpl"]["value"], 30)
        self.assertEqual(self.model["kpis"]["cpl"]["note"], "$5 over goal")
        self.assertEqual(self.model["kpis"]["cpl"]["tone"], "amber")
        self.assertNotEqual(self.model["kpis"]["cpl"]["tone"], "success")
        self.assertEqual(self.model["kpis"]["demo_cost"]["value"], 60)
        self.assertEqual(self.model["kpis"]["demo_cost"]["note"], "$10 over goal")
        self.assertEqual(self.model["kpis"]["demo_cost"]["tone"], "amber")
        self.assertEqual(self.model["kpis"]["cpa"]["value"], 240)
        self.assertEqual(self.model["kpis"]["cpa"]["note"], "$40 over goal")
        self.assertEqual(self.model["kpis"]["cpa"]["tone"], "amber")
        self.assertEqual(self.model["kpis"]["spend"]["display"], "$240")
        self.assertEqual(self.model["kpis"]["spend"]["active_label"], "3 active")
        self.assertEqual(self.model["kpis"]["spend"]["cap_label"], "Not configured")
        self.assertEqual([stage["key"] for stage in self.model["stages"]], [
            "impressions", "outbound_clicks", "landing_visits", "form_starts", "leads", "demos", "sold",
        ])
        self.assertEqual(self.model["stages"][0]["ratio_label"], "1.7%")
        self.assertEqual(self.model["stages"][1]["ratio_label"], "80%")
        self.assertEqual(self.model["stages"][2]["ratio_label"], "12.5%")
        self.assertEqual(self.model["stages"][3]["ratio_label"], "20%")
        self.assertEqual(self.model["stages"][4]["ratio_label"], "50%")
        self.assertEqual(self.model["stages"][5]["ratio_label"], "25%")
        self.assertEqual(self.model["ads"]["rows"][0]["ctr_label"], "1.8%")
        self.assertEqual(self.model["ads"]["rows"][1]["ctr_label"], "1.75%")
        self.assertEqual(self.model["ads"]["rows"][2]["ctr_label"], "1.33%")
        self.assertEqual(self.model["ads"]["total"]["ctr_label"], "1.67%")
        self.assertEqual(self.model["ads"]["total"]["cpl_label"], "$30")
        self.assertLess(self.model["cost_charts"]["cpl"]["end_y"], self.model["cost_charts"]["cpl"]["target_y"])
        self.assertEqual(self.model["cost_charts"]["cpl"]["end_value"], 30)
        self.assertEqual(self.model["cost_charts"]["cpl"]["target"], 25)
        self.assertTrue(self.model["is_demo"])
        self.assertEqual(self.model["badge"], "SAMPLE DATA")
        self.assertFalse(self.model["validated"])
        self.assertEqual(self.model["bot"]["status"], "WATCH")
        self.assertNotEqual(self.model["bot"]["status"], "ON TRACK")
        titles = " ".join(item["title"] + " " + item["action"] for item in self.model["recommendations"])
        self.assertIn("Review the 12.5% visit-to-form-start rate", titles)
        self.assertIn("Test an approved creative against lead cost", titles)
        self.assertNotIn("16%", titles)
        self.assertNotIn("80% of visitors", titles)
        self.assertIsNone(self.model["territory_opps"])
        self.assertNotIn(5, (self.model["kpis"]["leads"]["actual"],))
        self.assertNotEqual(self.model["kpis"]["leads"]["actual"], 115)

    def test_zero_denominator_is_not_a_dollar_cost(self):
        start = growth.date(2026, 11, 1)
        model = growth.summarize(
            {
                "is_demo": True,
                "validated": False,
                "preset": "custom",
                "range_start": start,
                "range_end": start,
                "goal_month": "2026-11",
                "as_of": growth.FIXTURE_AS_OF,
                "days": [
                    {
                        "date": "2026-11-01",
                        "spend": 10,
                        "impressions": 0,
                        "outbound_clicks": 0,
                        "landing_visits": 0,
                        "form_starts": 0,
                        "leads": 0,
                        "demos": 0,
                        "sold": 0,
                        "known": True,
                    }
                ],
                "ads": {"status": "unavailable", "reason": "none", "rows": []},
                "submissions": None,
                "tracking": "unknown",
                "territory_opps": None,
                "spend_gap": None,
                "window_totals": None,
            }
        )
        self.assertIsNone(model["kpis"]["cpl"]["value"])
        self.assertEqual(model["kpis"]["cpl"]["display"], "N/A")
        self.assertNotEqual(model["kpis"]["cpl"]["display"], "$0")
        self.assertEqual(model["stages"][0]["ratio_label"], "N/A")

    def test_october_goal_does_not_inherit_november(self):
        model = growth.demo_model({"preset": ["last-month"]})
        self.assertEqual(model["goal_month"], "2026-10")
        self.assertEqual(model["pace"]["goal"], 10)
        self.assertIsNone(model["kpis"]["leads"]["actual"])
        self.assertEqual(model["kpis"]["leads"]["text"], "—")
        self.assertNotEqual(model["kpis"]["leads"]["text"], "0/10")

    def test_live_model_does_not_copy_the_sample_or_invent_visits(self):
        paid = {
            "window_start_local": "2026-10-01T00:00:00-04:00",
            "window_end_local": "2026-10-05T00:00:00-04:00",
            "funnel": [
                {"key": "ad_views", "status": "unavailable", "total": None, "series": None},
                {"key": "clicks", "status": "unavailable", "total": None, "series": None},
                {"key": "website_visitors", "status": "not_wired", "total": None, "series": None},
                {"key": "leads_created", "status": "ok", "total": 0, "series": [
                    {"date": day, "value": 0} for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04")
                ]},
                {"key": "opps_created", "status": "ok", "total": 0, "by_territory": {
                    "Buffalo": 0, "Rochester": 0, "Syracuse": 0, "Virtual": 0,
                }},
            ],
            "outbound_clicks": {"status": "unavailable", "total": None, "series": None},
            "demos": {"status": "ok", "total": 0, "series": [
                {"date": day, "value": 0} for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04")
            ]},
            "sales": {"status": "ok", "total": 0, "series": [
                {"date": day, "value": 0} for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04")
            ]},
            "spend": {"spend": None, "gap": None, "series": None, "note": metric.UNMATCHED_SPEND_NOTE},
        }
        model = growth.live_model(paid)
        self.assertFalse(model["is_demo"])
        self.assertIsNone(model["badge"])
        self.assertEqual(model["kpis"]["leads"]["actual"], 0)
        self.assertNotEqual(model["kpis"]["leads"]["actual"], 5)
        self.assertIsNone(model["stages"][2]["value"])
        self.assertEqual(model["stages"][2]["status"], "unavailable")
        self.assertIn("unavailable", model["sources"]["landing_visits"]["note"])
        self.assertIn("not zero", model["sources"]["landing_visits"]["note"])
        self.assertNotIn("not wired", model["sources"]["landing_visits"]["note"])
        self.assertNotEqual(model["stages"][2]["value"], sum(growth.DAILY_VISITS))
        self.assertEqual(model["stages"][3]["label"], "Abandoned Form")
        self.assertNotEqual(model["stages"][3]["value"], sum(growth.DAILY_FORM_STARTS))
        self.assertIn("Abandoned Form", model["sources"]["form_starts"]["note"])
        self.assertNotIn("Form starts", model["sources"]["form_starts"]["note"])
        self.assertNotIn("opp", [stage["key"] for stage in model["stages"]])
        self.assertEqual(model["territory_opps"]["total"], 0)
        self.assertEqual(model["kpis"]["cpl"]["display"], "N/A")
        self.assertEqual(model["ads"]["status"], "unavailable")
        self.assertNotEqual(model["kpis"]["spend"]["display"], "$240")
        self.assertNotEqual(model["bot"]["status"], "ON TRACK")

    def test_live_spend_gap_is_not_chosen(self):
        paid = {
            "window_start_local": "2026-10-01T00:00:00-04:00",
            "window_end_local": "2026-10-03T00:00:00-04:00",
            "funnel": [
                {"key": "ad_views", "status": "ok", "total": 10, "series": [
                    {"date": "2026-10-01", "value": 10},
                    {"date": "2026-10-02", "value": None},
                ]},
                {"key": "leads_created", "status": "ok", "total": 2, "series": [
                    {"date": "2026-10-01", "value": 2},
                    {"date": "2026-10-02", "value": 0},
                ]},
                {"key": "opps_created", "status": "ok", "total": 2, "by_territory": {}},
            ],
            "outbound_clicks": {"status": "ok", "total": 4, "series": [
                {"date": "2026-10-01", "value": 4},
                {"date": "2026-10-02", "value": 0},
            ]},
            "demos": {"status": "ok", "total": 1, "series": [
                {"date": "2026-10-01", "value": 1},
                {"date": "2026-10-02", "value": 0},
            ]},
            "sales": {"status": "ok", "total": 0, "series": [
                {"date": "2026-10-01", "value": 0},
                {"date": "2026-10-02", "value": 0},
            ]},
            "spend": {
                "spend": None,
                "gap": {
                    "account_insights_total": 110.60,
                    "daily_rows_sum": 110.11,
                    "note": "Neither figure is tied to a lead or an opp. This page does not pick one.",
                },
                "series": [
                    {"date": "2026-10-01", "value": 50.0},
                    {"date": "2026-10-02", "value": 60.11},
                ],
                "note": "Neither figure is tied to a lead or an opp. This page does not pick one.",
            },
        }
        model = growth.live_model(paid)
        self.assertIsNone(model["kpis"]["cpl"]["value"])
        self.assertIsNone(model["kpis"]["spend"]["value"])
        self.assertTrue(any(item["id"] == "rec-spend-gap" for item in model["recommendations"]))


class PageTests(unittest.TestCase):
    def test_page_matches_the_command_center(self):
        html = page.render_html(model=page.model_for_query({"source": ["demo"]}))
        funnel = html.split('class="funnel-row"', 1)[1].split("</section>", 1)[0]
        labels = [
            "Impressions",
            "Outbound clicks",
            "Landing visits",
            "Form starts",
            "Leads created",
            "Demos",
            "Sold",
        ]
        positions = [funnel.find(label) for label in labels]
        self.assertTrue(all(pos > 0 for pos in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Growth command center", html)
        self.assertIn("SAMPLE DATA", html)
        self.assertIn("Directional", html)
        self.assertIn("2 behind pace", html)
        self.assertIn("$5 over goal", html)
        self.assertIn("Not configured", html)
        self.assertIn("G-V02RZFR4SZ", html)
        self.assertIn("7nSEgeoBYXZiIS7x41Jy", html)
        self.assertIn('href="/api/paid_social_funnel', html)
        self.assertNotIn("/api/metrics/inbound_cac", html)
        self.assertNotIn("|| 0", html)
        self.assertNotIn("16%", html)
        self.assertIsNone(WORD.search(html))
        self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, PAGE_SRC)
        self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, html)
        nav_html = nav.render_dashboard_nav("paid_social_funnel")
        self.assertLess(nav_html.find("Ads & Inbound Funnel"), nav_html.find("Website Traffic"))
        self.assertIn('class="navlink active" href="/api/paid_social_funnel"', nav_html)
        self.assertEqual(
            index.dispatch_route("/api/metrics/paid_social_funnel?start=2026-09-07&end=2026-10-04"),
            "metrics/paid_social_funnel",
        )
        self.assertEqual(index.dispatch_route("/api/paid_social_funnel"), "paid_social_funnel")

    def test_explicit_sample_mode_still_renders_the_fixture(self):
        handler = page.handler.__new__(page.handler)
        handler.path = "/api/paid_social_funnel?source=demo"
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.do_GET()
        body = handler.wfile.write.call_args[0][0].decode("utf-8")
        self.assertIn("SAMPLE DATA", body)
        self.assertIn("Nov 1–15, 2026", body)
        self.assertIn("8/20", body)
        self.assertIsNone(WORD.search(body))
        for source in ("sample", "fixture"):
            model = page.model_for_query({"source": [source]})
            self.assertTrue(model["is_demo"])
            self.assertEqual(model["badge"], "SAMPLE DATA")

    def test_default_screen_is_live_current_month_without_sample_numbers(self):
        days = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
        paid = {
            "window_start_local": "2026-10-01T00:00:00-04:00",
            "window_end_local": "2026-10-05T00:00:00-04:00",
            "funnel": [
                {"key": "ad_views", "status": "ok", "total": 100, "series": [
                    {"date": day, "value": 25} for day in days
                ]},
                {"key": "website_visitors", "status": "not_wired", "total": None, "series": None},
                {"key": "leads_created", "status": "ok", "total": 2, "series": [
                    {"date": days[0], "value": 2},
                    *[{"date": day, "value": 0} for day in days[1:]],
                ]},
                {"key": "opps_created", "status": "ok", "total": 1, "by_territory": {
                    "Buffalo": 1, "Rochester": 0, "Syracuse": 0, "Virtual": 0,
                }},
            ],
            "outbound_clicks": {"status": "ok", "total": 10, "series": [
                {"date": days[0], "value": 10},
                *[{"date": day, "value": 0} for day in days[1:]],
            ]},
            "demos": {"status": "ok", "total": 1, "series": [
                {"date": days[0], "value": 1},
                *[{"date": day, "value": 0} for day in days[1:]],
            ]},
            "sales": {"status": "ok", "total": 0, "series": [
                {"date": day, "value": 0} for day in days
            ]},
            "spend": {
                "spend": 80.0,
                "gap": None,
                "series": [{"date": day, "value": 20.0} for day in days],
                "note": metric.UNMATCHED_SPEND_NOTE,
            },
        }
        seen = {}

        def loader(qs):
            seen["qs"] = qs
            return paid

        model = page.model_for_query({}, live_loader=loader)
        self.assertEqual(seen["qs"], {})
        self.assertFalse(model["is_demo"])
        self.assertIsNone(model["badge"])
        self.assertEqual(model["range_start"], "2026-10-01")
        self.assertEqual(model["range_end"], "2026-10-04")
        self.assertEqual(model["goal_month"], "2026-10")
        self.assertEqual(model["pace"]["goal"], 10)
        self.assertNotEqual(model["pace"]["goal"], 20)
        self.assertEqual(model["kpis"]["leads"]["text"], "2/10")
        self.assertEqual(model["kpis"]["cpl"]["value"], 40)
        self.assertEqual(model["kpis"]["cpl"]["tone"], "amber")
        self.assertNotEqual(model["kpis"]["cpl"]["tone"], "success")
        self.assertEqual(model["kpis"]["demo_cost"]["value"], 80)
        self.assertEqual(model["kpis"]["demo_cost"]["tone"], "amber")
        self.assertEqual(model["kpis"]["cpa"]["display"], "N/A")
        self.assertNotEqual(model["kpis"]["cpa"]["display"], "$0")
        visits = model["stages"][2]
        forms = model["stages"][3]
        self.assertIsNone(visits["value"])
        self.assertEqual(visits["status"], "unavailable")
        self.assertEqual(visits["display"], "—")
        self.assertNotEqual(visits["display"], "0")
        self.assertIsNone(forms["value"])
        self.assertEqual(forms["label"], "Abandoned Form")
        self.assertEqual(forms["status"], "unavailable")
        self.assertEqual(forms["display"], "—")
        self.assertIn("unavailable", model["sources"]["landing_visits"]["note"])
        self.assertIn("not zero", model["sources"]["landing_visits"]["note"])
        self.assertNotIn("not wired", model["sources"]["landing_visits"]["note"])
        self.assertIn("Abandoned Form", model["sources"]["form_starts"]["note"])
        self.assertNotIn("Form starts", model["sources"]["form_starts"]["note"])
        self.assertIn("unavailable", model["sources"]["form_starts"]["note"])
        self.assertIn("not zero", model["sources"]["form_starts"]["note"])
        self.assertNotEqual(visits["value"], sum(growth.DAILY_VISITS))
        self.assertNotEqual(forms["value"], sum(growth.DAILY_FORM_STARTS))
        self.assertNotIn("opp", [stage["key"] for stage in model["stages"]])

        html = page.render_html(model=model)
        self.assertIn(">Live<", html)
        self.assertIn("Oct 1–4, 2026", html)
        self.assertIn("Sample fixture", html)
        self.assertIn("This read is unavailable, so the stage stays blank.", html)
        self.assertIn("A failed read is not zero.", html)
        self.assertIn("Abandoned Form", html)
        self.assertNotIn("Form starts", html)
        self.assertNotIn("Form starts are not wired", html)
        self.assertNotIn("SAMPLE DATA", html)
        self.assertNotIn("Nov 1–15, 2026", html)
        self.assertNotIn("8/20", html)
        self.assertNotIn("$240", html)
        self.assertNotIn("Local savings", html)
        self.assertNotIn("Solar explained", html)
        self.assertNotIn("Homeowner story", html)
        self.assertNotIn("sample-ad-", html)
        self.assertNotIn("Review the 12.5% visit-to-form-start rate", html)
        self.assertIsNone(WORD.search(html))
        self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, html)

        failed = page.model_for_query(
            {"source": ["live"]},
            live_loader=lambda _qs: (_ for _ in ()).throw(RuntimeError("no creds")),
        )
        failed_html = page.render_html(model=failed)
        self.assertFalse(failed["is_demo"])
        self.assertNotIn("SAMPLE DATA", failed_html)
        self.assertIn("Sample numbers are not shown", failed_html)
        self.assertNotIn("$240", failed_html)
        self.assertNotIn("Local savings", failed_html)
        self.assertIsNone(WORD.search(failed_html))

        demo_calls = {"n": 0}

        def exploding(_qs):
            demo_calls["n"] += 1
            raise AssertionError("sample mode must not read live sources")

        sample = page.model_for_query({"source": ["demo"]}, live_loader=exploding)
        self.assertEqual(demo_calls["n"], 0)
        self.assertTrue(sample["is_demo"])
        self.assertEqual(sample["range_label"], "Nov 1–15, 2026")

    def test_default_handler_uses_the_live_loader(self):
        calls = {}

        def loader(qs):
            calls["qs"] = dict(qs)
            now = datetime(2026, 10, 4, 15, 0, tzinfo=NY)
            start, end = metric.parse_range(qs, now)
            calls["start"] = start
            calls["end"] = end
            return {
                "window_start_local": "2026-10-01T00:00:00-04:00",
                "window_end_local": "2026-10-05T00:00:00-04:00",
                "funnel": [
                    {"key": "leads_created", "status": "ok", "total": 1, "series": [
                        {"date": "2026-10-01", "value": 1},
                        {"date": "2026-10-02", "value": 0},
                        {"date": "2026-10-03", "value": 0},
                        {"date": "2026-10-04", "value": 0},
                    ]},
                ],
                "outbound_clicks": {"status": "unavailable", "total": None, "series": None},
                "demos": {"status": "ok", "total": 0, "series": [
                    {"date": day, "value": 0}
                    for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04")
                ]},
                "sales": {"status": "ok", "total": 0, "series": [
                    {"date": day, "value": 0}
                    for day in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04")
                ]},
                "spend": {"spend": None, "gap": None, "series": None},
            }

        original = page._load_live
        page._load_live = loader
        try:
            handler = page.handler.__new__(page.handler)
            handler.path = "/api/paid_social_funnel"
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()
            handler.do_GET()
        finally:
            page._load_live = original
        body = handler.wfile.write.call_args[0][0].decode("utf-8")
        self.assertEqual(calls["qs"], {})
        self.assertEqual(calls["start"], "2026-10-01")
        self.assertEqual(calls["end"], "2026-10-04")
        self.assertNotIn("SAMPLE DATA", body)
        self.assertNotIn("Nov 1–15, 2026", body)
        self.assertIn("Oct 1–4, 2026", body)
        self.assertIn("1/10", body)
        self.assertNotIn("8/20", body)
        self.assertIn("unavailable", body)
        self.assertIsNone(WORD.search(body))

    def test_load_live_requests_the_current_month_through_today(self):
        from types import SimpleNamespace

        calls = {}

        def compute(db, *, start, end, now):
            calls["db"] = db
            calls["start"] = start
            calls["end"] = end
            calls["zone"] = getattr(now.tzinfo, "key", str(now.tzinfo))
            return {"ok": True}

        fake = SimpleNamespace(
            parse_range=metric.parse_range,
            compute_paid_social_funnel=compute,
            cac=SimpleNamespace(get_db=lambda: "db-handle"),
        )
        name = "hs_growth_paid_social_metric"
        previous = sys.modules.get(name)
        sys.modules[name] = fake
        try:
            before = datetime.now(NY).date()
            result = page._load_live({})
            after = datetime.now(NY).date()
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls["db"], "db-handle")
        self.assertEqual(calls["zone"], "America/New_York")
        self.assertIn(calls["start"], {before.replace(day=1).isoformat(), after.replace(day=1).isoformat()})
        self.assertIn(calls["end"], {before.isoformat(), after.isoformat()})
        self.assertNotEqual((calls["start"], calls["end"]), ("2026-11-01", "2026-11-15"))


class LiveWindowTests(unittest.TestCase):
    def test_parse_range_is_the_current_month_through_today(self):
        now = datetime(2026, 10, 4, 18, 30, tzinfo=NY)
        self.assertEqual(metric.parse_range({}, now), ("2026-10-01", "2026-10-04"))
        self.assertEqual(metric.parse_range({"preset": ["this-month"]}, now), ("2026-10-01", "2026-10-04"))
        self.assertEqual(metric.parse_range({"preset": ["last-month"]}, now), ("2026-09-01", "2026-09-30"))
        self.assertEqual(metric.parse_range({"preset": ["last-30"]}, now), ("2026-09-05", "2026-10-04"))
        self.assertEqual(
            metric.parse_range(
                {"preset": ["custom"], "start": ["2026-08-01"], "end": ["2026-08-10"]},
                now,
            ),
            ("2026-08-01", "2026-08-10"),
        )
        self.assertEqual(
            metric.parse_range({"start": ["2026-11-01"], "end": ["2026-11-15"]}, now),
            ("2026-11-01", "2026-11-15"),
        )
        utc_evening = datetime(2026, 10, 5, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(metric.parse_range({}, utc_evening), ("2026-10-01", "2026-10-04"))
        january = datetime(2026, 1, 1, 8, 0, tzinfo=NY)
        self.assertEqual(metric.parse_range({}, january), ("2026-01-01", "2026-01-01"))
        self.assertEqual(metric.parse_range({"preset": ["last-month"]}, january), ("2025-12-01", "2025-12-31"))

    def test_live_november_goal_stays_20_and_october_stays_10(self):
        october = growth.live_model(
            {
                "window_start_local": "2026-10-01T00:00:00-04:00",
                "window_end_local": "2026-10-05T00:00:00-04:00",
                "funnel": [{"key": "leads_created", "status": "ok", "total": 2, "series": []}],
                "outbound_clicks": {"status": "unavailable", "total": None},
                "demos": {"status": "ok", "total": 0, "series": []},
                "sales": {"status": "ok", "total": 0, "series": []},
                "spend": {"spend": None, "gap": None, "series": None},
            }
        )
        november = growth.live_model(
            {
                "window_start_local": "2026-11-01T00:00:00-05:00",
                "window_end_local": "2026-11-16T00:00:00-05:00",
                "funnel": [{"key": "leads_created", "status": "ok", "total": 2, "series": []}],
                "outbound_clicks": {"status": "unavailable", "total": None},
                "demos": {"status": "ok", "total": 0, "series": []},
                "sales": {"status": "ok", "total": 0, "series": []},
                "spend": {"spend": None, "gap": None, "series": None},
            }
        )
        self.assertEqual(october["pace"]["goal"], 10)
        self.assertEqual(november["pace"]["goal"], 20)
        self.assertNotEqual(october["kpis"]["leads"]["text"], "8/20")
        self.assertFalse(october["is_demo"])
        self.assertIsNone(october["stages"][2]["value"])
        self.assertEqual(october["stages"][2]["status"], "unavailable")


def _ga4_row(dimensions: list[str], metric: int) -> dict:
    return {
        "dimensionValues": [{"value": value} for value in dimensions],
        "metricValues": [{"value": str(metric)}],
    }


def _ga4_ok(rows: list[dict]) -> dict:
    return {"ga4": "ok", "report": {"rowCount": len(rows), "rows": rows}}


class PaidWebsiteStageTests(unittest.TestCase):
    def setUp(self):
        self.start_local, self.end_local, _, _ = metric.cac.date_range_window(
            "2026-10-01", "2026-10-02", "America/New_York"
        )
        self.days = ["2026-10-01", "2026-10-02"]

    def test_paid_session_rule_includes_facebook_and_instagram_only(self):
        traffic = metric._load_website_traffic()
        self.assertTrue(traffic.session_is_paid("facebook", "paid", "Paid Social"))
        self.assertTrue(traffic.session_is_paid("instagram", "cpc", "Paid Social"))
        self.assertTrue(traffic.session_is_paid("l.facebook.com", "paidsocial", "Paid Social"))
        self.assertFalse(traffic.session_is_paid("facebook", "organic", "Organic Social"))
        self.assertFalse(traffic.session_is_paid("instagram", "organic", "Organic Social"))
        self.assertFalse(traffic.session_is_paid("google", "cpc", "Paid Search"))
        self.assertFalse(traffic.session_is_paid("google", "organic", "Organic Search"))
        counted = metric.count_paid_rows(
            [
                {"date": "2026-10-01", "sessionSource": "facebook", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "sessions": 10},
                {"date": "2026-10-01", "sessionSource": "instagram", "sessionMedium": "cpc", "sessionDefaultChannelGroup": "Paid Social", "sessions": 4},
                {"date": "2026-10-02", "sessionSource": "facebook", "sessionMedium": "organic", "sessionDefaultChannelGroup": "Organic Social", "sessions": 7},
                {"date": "2026-10-02", "sessionSource": "google", "sessionMedium": "cpc", "sessionDefaultChannelGroup": "Paid Search", "sessions": 9},
                {"date": "2026-10-01", "eventName": "estimate_start", "sessionSource": "facebook", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "sessions": 3},
            ],
            self.days,
            value_keys=("sessions",),
        )
        self.assertEqual(counted["total"], 14)
        self.assertEqual([point["value"] for point in counted["series"]], [14, 0])
        starts = metric.count_paid_rows(
            [
                {"date": "20261001", "eventName": "estimate_start", "sessionSource": "facebook", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "eventCount": 3},
                {"date": "20261001", "eventName": "estimate_submit", "sessionSource": "facebook", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "eventCount": 8},
                {"date": "20261001", "eventName": "estimate_start", "sessionSource": "facebook", "sessionMedium": "organic", "sessionDefaultChannelGroup": "Organic Social", "eventCount": 5},
                {"date": "20261002", "eventName": "estimate_start", "sessionSource": "instagram", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "eventCount": 1},
                {"date": "20261002", "eventName": "wix_form_submit", "sessionSource": "instagram", "sessionMedium": "paid", "sessionDefaultChannelGroup": "Paid Social", "eventCount": 6},
            ],
            self.days,
            value_keys=("eventCount",),
            event_name="estimate_start",
        )
        self.assertEqual(starts["total"], 4)
        self.assertEqual([point["value"] for point in starts["series"]], [3, 1])
        self.assertEqual(metric.FORM_START_EVENT, "estimate_start")
        self.assertNotEqual(metric.FORM_START_EVENT, "estimate_submit")

    def test_fetch_counts_paid_rows_and_a_failed_read_stays_null(self):
        session_rows = [
            _ga4_row(["20261001", "Paid Social", "facebook", "paid"], 10),
            _ga4_row(["20261001", "Paid Social", "instagram", "cpc"], 4),
            _ga4_row(["20261002", "Organic Social", "facebook", "organic"], 7),
            _ga4_row(["20261002", "Paid Search", "google", "cpc"], 9),
        ]
        start_rows = [
            _ga4_row(["20261001", "Paid Social", "facebook", "paid", "estimate_start"], 5),
            _ga4_row(["20261001", "Organic Social", "facebook", "organic", "estimate_start"], 5),
            _ga4_row(["20261002", "Paid Social", "instagram", "paid", "estimate_start"], 1),
            _ga4_row(["20261002", "Paid Search", "google", "cpc", "estimate_start"], 9),
        ]
        submit_rows = [
            _ga4_row(["20261001", "Paid Social", "facebook", "paid", "estimate_submit"], 2),
            _ga4_row(["20261002", "Paid Social", "instagram", "paid", "estimate_submit"], 1),
            _ga4_row(["20261002", "Paid Social", "instagram", "paid", "wix_form_submit"], 6),
            _ga4_row(["20261001", "Organic Social", "facebook", "organic", "estimate_submit"], 4),
        ]
        seen = []

        def event_values(body):
            return body["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["inListFilter"]["values"]

        def runner(body, timeout=25):
            seen.append(body)
            self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, json.dumps(body))
            self.assertNotIn("landingPageViews", json.dumps(body))
            self.assertEqual(body["dateRanges"], [{"startDate": "2026-10-01", "endDate": "2026-10-02"}])
            hosts = json.dumps(body["dimensionFilter"])
            self.assertIn("www.happyslr.com", hosts)
            self.assertIn("happyslr.com", hosts)
            self.assertIn("wny.happyslr.com", hosts)
            name = body["metrics"][0]["name"]
            if name == "sessions":
                self.assertNotIn("estimate_start", json.dumps(body))
                self.assertNotIn("estimate_submit", json.dumps(body))
                return _ga4_ok(session_rows)
            self.assertEqual(name, "eventCount")
            values = event_values(body)
            self.assertEqual(len(values), 1)
            if values == ["estimate_start"]:
                self.assertNotIn("estimate_submit", json.dumps(body["dimensionFilter"]))
                return _ga4_ok(start_rows)
            self.assertEqual(values, ["estimate_submit"])
            self.assertNotIn("estimate_start", json.dumps(body["dimensionFilter"]))
            return _ga4_ok(submit_rows)

        website = metric.fetch_paid_website_stages(
            self.start_local, self.end_local, report_runner=runner
        )
        self.assertEqual(len(seen), 3)
        visits = website["landing_visits"]
        forms = website["form_starts"]
        self.assertEqual(visits["status"], "ok")
        self.assertEqual(visits["total"], 14)
        self.assertEqual(visits["property_id"], "408492342")
        self.assertEqual(visits["measurement_id"], "G-V02RZFR4SZ")
        self.assertEqual([point["value"] for point in visits["series"]], [14, 0])
        self.assertEqual(forms["status"], "ok")
        self.assertEqual(forms["label"], "Abandoned Form")
        self.assertEqual(forms["total"], 3)
        self.assertEqual(forms["paid_estimate_start"], 6)
        self.assertEqual(forms["paid_estimate_submit"], 3)
        self.assertEqual(forms["start_event"], "estimate_start")
        self.assertEqual(forms["finished_event"], "estimate_submit")
        self.assertEqual([point["value"] for point in forms["series"]], [3, 0])
        self.assertIn("Abandoned Form", forms["note"])
        self.assertNotIn("Form starts", forms["note"])
        self.assertNotEqual(forms["total"], 0)
        self.assertNotEqual(forms["total"], sum(growth.DAILY_FORM_STARTS))

        def fail_sessions(body, timeout=25):
            if body["metrics"][0]["name"] == "sessions":
                return {"ga4": "failed", "rows": [], "error": "ga4_run_report_failed"}
            return runner(body)

        partial = metric.fetch_paid_website_stages(
            self.start_local, self.end_local, report_runner=fail_sessions
        )
        self.assertEqual(partial["landing_visits"]["status"], "unavailable")
        self.assertIsNone(partial["landing_visits"]["total"])
        self.assertIsNone(partial["landing_visits"]["series"])
        self.assertEqual(partial["form_starts"]["status"], "ok")
        self.assertEqual(partial["form_starts"]["total"], 3)
        self.assertNotIn('"total": 0', json.dumps(partial["landing_visits"]))

        def fail_both(body, timeout=25):
            return {"ga4": "not_configured", "rows": [], "error": None}

        failed = metric.fetch_paid_website_stages(
            self.start_local, self.end_local, report_runner=fail_both
        )
        self.assertIsNone(failed["landing_visits"]["total"])
        self.assertIsNone(failed["form_starts"]["total"])
        self.assertIsNone(failed["landing_visits"]["series"])
        self.assertIsNone(failed["form_starts"]["series"])
        self.assertNotEqual(failed["landing_visits"]["total"], 0)
        self.assertNotEqual(failed["form_starts"]["total"], 0)

        calls = {"n": 0}

        def refuse(body, timeout=25):
            calls["n"] += 1
            raise AssertionError("a different property must not be queried")

        with patch.dict(os.environ, {"GA4_PROPERTY_ID": "999999"}):
            mismatched = metric.fetch_paid_website_stages(
                self.start_local, self.end_local, report_runner=refuse
            )
        self.assertEqual(calls["n"], 0)
        self.assertIsNone(mismatched["landing_visits"]["total"])
        self.assertIsNone(mismatched["form_starts"]["total"])

        if any(
            os.environ.get(name)
            for name in ("GA4_PROPERTY_ID", "GA4_SERVICE_ACCOUNT_JSON", "FIREBASE_SERVICE_ACCOUNT_JSON")
        ):
            return
        with patch("urllib.request.urlopen", side_effect=AssertionError("GA4 must not be called")):
            unwired = metric.fetch_paid_website_stages(self.start_local, self.end_local)
        self.assertEqual(unwired["landing_visits"]["status"], "unavailable")
        self.assertEqual(unwired["landing_visits"]["reason"], "not_configured")
        self.assertIsNone(unwired["landing_visits"]["total"])
        self.assertIsNone(unwired["landing_visits"]["series"])
        self.assertIsNone(unwired["form_starts"]["total"])
        self.assertIsNone(unwired["form_starts"]["series"])
        self.assertNotEqual(unwired["landing_visits"]["total"], 0)
        self.assertNotEqual(unwired["form_starts"]["total"], 0)

    def test_abandoned_form_floors_at_zero_and_a_failed_event_stays_null(self):
        def rows_for(event_name, day_one, day_two):
            return [
                _ga4_row(["20261001", "Paid Social", "facebook", "paid", event_name], day_one),
                _ga4_row(["20261002", "Paid Social", "instagram", "cpc", event_name], day_two),
            ]

        def respond(starts, submits, fail=None):
            def runner(body, timeout=25):
                name = body["metrics"][0]["name"]
                if name == "sessions":
                    return _ga4_ok([_ga4_row(["20261001", "Paid Social", "facebook", "paid"], 14)])
                values = body["dimensionFilter"]["andGroup"]["expressions"][1]["filter"]["inListFilter"]["values"]
                if fail == "start" and values == ["estimate_start"]:
                    return {"ga4": "failed", "rows": [], "error": "ga4_run_report_failed"}
                if fail == "submit" and values == ["estimate_submit"]:
                    return {"ga4": "failed", "rows": [], "error": "ga4_run_report_failed"}
                if values == ["estimate_start"]:
                    return _ga4_ok(rows_for("estimate_start", *starts))
                return _ga4_ok(rows_for("estimate_submit", *submits))

            return runner

        floored = metric.fetch_paid_website_stages(
            self.start_local, self.end_local, report_runner=respond((1, 6), (4, 0))
        )
        forms = floored["form_starts"]
        self.assertEqual(forms["status"], "ok")
        self.assertEqual(forms["paid_estimate_start"], 7)
        self.assertEqual(forms["paid_estimate_submit"], 4)
        self.assertEqual(forms["total"], 3)
        self.assertEqual([point["value"] for point in forms["series"]], [0, 6])
        self.assertNotEqual(forms["total"], sum(point["value"] for point in forms["series"]))
        self.assertTrue(all(point["value"] >= 0 for point in forms["series"]))

        nobody = metric.fetch_paid_website_stages(
            self.start_local, self.end_local, report_runner=respond((2, 0), (5, 0))
        )
        self.assertEqual(nobody["form_starts"]["status"], "ok")
        self.assertEqual(nobody["form_starts"]["total"], 0)
        self.assertEqual([point["value"] for point in nobody["form_starts"]["series"]], [0, 0])
        self.assertIsNotNone(nobody["form_starts"]["series"])
        counts_start, counts_end, counts = MetaAndVisitorTests()._counts()
        zero_payload = metric.assemble_paid_social(
            counts,
            start_local=counts_start,
            end_local=counts_end,
            daily_meta={"status": "unavailable", "rows": [], "lead_actions_ignored": False},
            aggregate_spend=metric.cac.unavailable_meta_spend("missing_env"),
            website={"form_starts": nobody["form_starts"], "landing_visits": nobody["landing_visits"]},
        )
        zero_model = growth.live_model(zero_payload)
        self.assertEqual(zero_model["stages"][3]["label"], "Abandoned Form")
        self.assertEqual(zero_model["stages"][3]["value"], 0)
        self.assertEqual(zero_model["stages"][3]["display"], "0")
        self.assertEqual(zero_model["stages"][3]["status"], "ok")
        self.assertNotEqual(zero_model["stages"][3]["display"], "—")

        for failure in ("start", "submit"):
            failed = metric.fetch_paid_website_stages(
                self.start_local, self.end_local, report_runner=respond((5, 1), (2, 1), fail=failure)
            )
            self.assertEqual(failed["landing_visits"]["status"], "ok")
            self.assertEqual(failed["landing_visits"]["total"], 14)
            self.assertEqual(failed["form_starts"]["status"], "unavailable")
            self.assertIsNone(failed["form_starts"]["total"])
            self.assertIsNone(failed["form_starts"]["series"])
            self.assertNotEqual(failed["form_starts"]["total"], 0)
            self.assertNotEqual(failed["form_starts"]["total"], 6)
            self.assertIn("Abandoned Form", failed["form_starts"]["note"])
            self.assertIn("not zero", failed["form_starts"]["note"])
            self.assertNotIn("Form starts", failed["form_starts"]["note"])

    def test_live_adapter_shows_counts_and_keeps_a_failed_read_null(self):
        start_local, end_local, counts = MetaAndVisitorTests()._counts()
        website = {
            "landing_visits": {
                "status": "ok",
                "total": 14,
                "series": [
                    {"date": "2026-10-01", "value": 14},
                    {"date": "2026-10-02", "value": 0},
                ],
                "measurement_id": "G-V02RZFR4SZ",
                "property_id": "408492342",
            },
            "form_starts": {
                "status": "unavailable",
                "total": 0,
                "series": [
                    {"date": "2026-10-01", "value": 0},
                    {"date": "2026-10-02", "value": 0},
                ],
            },
        }
        payload = metric.assemble_paid_social(
            counts,
            start_local=start_local,
            end_local=end_local,
            daily_meta={"status": "unavailable", "rows": [], "lead_actions_ignored": False},
            aggregate_spend=metric.cac.unavailable_meta_spend("missing_env"),
            website=website,
        )
        self.assertEqual(payload["funnel"][2]["total"], 14)
        self.assertEqual(payload["funnel"][3]["key"], "leads_created")
        self.assertIsNone(payload["form_starts"]["total"])
        self.assertIsNone(payload["form_starts"]["series"])
        self.assertEqual(payload["form_starts"]["status"], "unavailable")
        self.assertNotIn('"total": 0', json.dumps(payload["form_starts"]))
        model = growth.live_model(payload)
        visits = model["stages"][2]
        forms = model["stages"][3]
        self.assertEqual(visits["value"], 14)
        self.assertEqual(visits["display"], "14")
        self.assertEqual(visits["status"], "ok")
        self.assertEqual([point["value"] for point in payload["landing_visits"]["series"]], [14, 0])
        self.assertIsNone(forms["value"])
        self.assertEqual(forms["label"], "Abandoned Form")
        self.assertEqual(forms["display"], "—")
        self.assertEqual(forms["status"], "unavailable")
        self.assertIsNone(payload["form_starts"]["series"])
        self.assertNotEqual(visits["value"], sum(growth.DAILY_VISITS))
        self.assertNotEqual(forms["value"], sum(growth.DAILY_FORM_STARTS))
        self.assertNotEqual(forms["value"], 0)
        self.assertIn("Facebook and Instagram", model["sources"]["landing_visits"]["note"])
        self.assertNotIn("not wired", model["sources"]["landing_visits"]["note"])
        both = metric.assemble_paid_social(
            counts,
            start_local=start_local,
            end_local=end_local,
            daily_meta={"status": "unavailable", "rows": [], "lead_actions_ignored": False},
            aggregate_spend=metric.cac.unavailable_meta_spend("missing_env"),
            website={
                "landing_visits": website["landing_visits"],
                "form_starts": {
                    "status": "ok",
                    "total": 4,
                    "series": [
                        {"date": "2026-10-01", "value": 3},
                        {"date": "2026-10-02", "value": 1},
                    ],
                },
            },
        )
        both_model = growth.live_model(both)
        self.assertEqual(both_model["stages"][2]["value"], 14)
        self.assertEqual(both_model["stages"][2]["status"], "ok")
        self.assertEqual(both_model["stages"][3]["label"], "Abandoned Form")
        self.assertEqual(both_model["stages"][3]["value"], 4)
        self.assertEqual(both_model["stages"][3]["status"], "ok")
        self.assertEqual(both_model["stages"][3]["display"], "4")
        self.assertNotEqual(both_model["stages"][2]["value"], 320)
        self.assertNotEqual(both_model["stages"][3]["value"], 40)
        self.assertIn("Abandoned Form", model["sources"]["form_starts"]["note"])
        self.assertNotIn("Form starts", model["sources"]["form_starts"]["note"])
        self.assertIn("not zero", model["sources"]["form_starts"]["note"])
        html = page.render_html(model=model)
        self.assertIn(">14<", html)
        self.assertIn("Abandoned Form", html)
        self.assertNotIn("Form starts", html)
        self.assertNotIn("SAMPLE DATA", html)
        self.assertNotIn("Nov 1–15, 2026", html)
        self.assertNotIn("8/20", html)
        self.assertNotIn("Form starts are not wired", html)
        both_html = page.render_html(model=both_model)
        self.assertIn("Abandoned Form", both_html)
        self.assertNotIn("Form starts", both_html)
        self.assertNotIn("form starts", both_html)
        self.assertIn("abandoned forms", both_html)
        self.assertNotIn(metric.META_CAMPAIGN_NOT_MODIFIED, html)

        original = metric.load_window_records
        metric.load_window_records = lambda *_args, **_kwargs: ([], [], [], set(), {})
        try:
            failed = metric.compute_paid_social_funnel(
                object(),
                start="2026-10-01",
                end="2026-10-02",
                now=NOW,
                token="test-token",
                account_id=metric.META_ACCOUNT_ID,
                daily_fetcher=lambda _start, _end: {
                    "status": "unavailable",
                    "rows": [],
                    "lead_actions_ignored": False,
                },
                aggregate_fetcher=lambda _start, _end: metric.cac.unavailable_meta_spend("missing_env"),
                ga4_fetcher=lambda _start, _end: (_ for _ in ()).throw(RuntimeError("ga4 down")),
            )
        finally:
            metric.load_window_records = original
        self.assertIsNone(failed["landing_visits"]["total"])
        self.assertIsNone(failed["form_starts"]["total"])
        self.assertIsNone(failed["landing_visits"]["series"])
        self.assertIsNone(failed["form_starts"]["series"])
        failed_model = growth.live_model(failed)
        self.assertIsNone(failed_model["stages"][2]["value"])
        self.assertIsNone(failed_model["stages"][3]["value"])
        self.assertEqual(failed_model["stages"][2]["display"], "—")
        self.assertEqual(failed_model["stages"][3]["display"], "—")
        self.assertNotEqual(failed_model["stages"][2]["value"], 0)
        self.assertNotEqual(failed_model["stages"][3]["value"], 0)
        self.assertNotEqual(failed_model["stages"][2]["value"], 320)
        self.assertNotEqual(failed_model["stages"][3]["value"], 40)
        failed_html = page.render_html(model=failed_model)
        self.assertNotIn("SAMPLE DATA", failed_html)
        self.assertNotIn("Nov 1–15, 2026", failed_html)
        self.assertIn("A failed read is not zero.", failed_html)


if __name__ == "__main__":
    unittest.main()
