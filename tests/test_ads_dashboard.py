# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import re
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


metric = load_module("ads_dashboard_metric", METRICS / "ads_dashboard.py")
page = load_module("ads_dashboard_page", API / "ads_dashboard.py")
nav = load_module("dashboard_nav_ads", API / "dashboard_nav.py")
index = load_module("index_for_ads_dashboard", API / "index.py")

METRIC_SRC = (METRICS / "ads_dashboard.py").read_text(encoding="utf-8")
PAGE_SRC = (API / "ads_dashboard.py").read_text(encoding="utf-8")
INDEXES = (ROOT / "firestore.indexes.json").read_text(encoding="utf-8")
WORD = re.compile(r"\b(sit|sits|sat)\b", re.IGNORECASE)
PHOENIX = ZoneInfo("America/Phoenix")
NY = ZoneInfo("America/New_York")
PIPELINE = metric.LEAD_PIPELINE_ID
FIELD = metric.SOURCE_FIELD_ID
VIRTUAL = "r1b9pwgliYj7WyWBchTV"
NOW = datetime(2026, 10, 12, 15, 0, tzinfo=PHOENIX)
INSIDE = "2026-10-08T18:00:00.000Z"
# 02:00 ET on Oct 12 is still Oct 11 in Phoenix, and already Oct 12 in New York.
PHOENIX_ONLY = "2026-10-12T02:00:00-04:00"

WEX = "wexVPJjfOx44b9Qpb9Fd"
CITY = "UfBneQ7YRXk4QSD480xq"
THREE_PL = "AxDUF0qxgVHnYNgzHtgO"
BLANKS = ("Cecxq4EKHoC2xmOibEx6", "IaGnbEj6JN3iE6ksazo6")
STAGES = (
    "Not Qualified",
    "Not Qualified",
    "Not Qualified",
    "Not Interested",
    "Not Interested",
    "Not Interested",
    "Reconnect to Book",
    "Reconnect to Book",
    "New Lead",
    "Call 4",
    "Appointment Set",
)


class Snap:
    def __init__(self, data, sid=None, exists=True):
        self._data = data
        self.id = sid or (data or {}).get("id")
        self.exists = exists

    def to_dict(self):
        return dict(self._data or {})


class DocRef:
    def __init__(self, db, name, doc_id):
        self.db = db
        self.name = name
        self.doc_id = doc_id

    def get(self):
        self.db.gets.append((self.name, self.doc_id))
        data = self.db.docs.get((self.name, self.doc_id))
        if data is None:
            return Snap({}, self.doc_id, exists=False)
        return Snap(data, self.doc_id)


class Query:
    def __init__(self, db, name, filters):
        self.db = db
        self.name = name
        self.filters = list(filters)

    def where(self, field, op, value):
        return Query(self.db, self.name, self.filters + [(field, op, value)])

    def limit(self, count):
        return Query(self.db, self.name, self.filters + [("limit", "==", count)])

    def stream(self):
        self.db.streams.append((self.name, list(self.filters)))
        return list(self.db.rows.get(self.name, []))


class Collection:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def where(self, field, op, value):
        return Query(self.db, self.name, [(field, op, value)])

    def document(self, doc_id):
        return DocRef(self.db, self.name, doc_id)


class FakeDB:
    def __init__(self):
        self.streams = []
        self.gets = []
        self.get_all_calls = []
        self.rows = {}
        self.docs = {}
        self.contacts = {}

    def collection(self, name):
        return Collection(self, name)

    def get_all(self, refs):
        self.get_all_calls.append([ref.doc_id for ref in refs])
        snaps = []
        for ref in refs:
            data = self.contacts.get(ref.doc_id)
            snaps.append(Snap(data, ref.doc_id, exists=data is not None))
        return snaps


def contact(contact_id: str, source: str | None, *tags: str, sold: str | None = None) -> dict:
    fields = []
    if source is not None:
        fields.append({"id": FIELD, "value": source})
    if sold is not None:
        fields.append({"id": metric.cac.SOLD_DATE_CUSTOM_FIELD_ID, "value": sold})
    return {"id": contact_id, "customFields": fields, "tags": list(tags)}


def pipeline_opp(opp_id: str, contact_id: str, created: str, stage: str) -> dict:
    return {
        "id": opp_id,
        "contactId": contact_id,
        "pipelineId": PIPELINE,
        "createdAt": created,
        "pipelineStageId": f"stage-{stage}",
        "name": "Inbound",
    }


def city_opp(opp_id: str, contact_id: str, created: str, outcome: str) -> dict:
    return {
        "id": opp_id,
        "contactId": contact_id,
        "pipelineId": VIRTUAL,
        "createdAt": created,
        "pipelineStageId": "stage-reschedule",
        "dispositionValue": outcome,
        "appointmentOccurredAt": created,
    }


def warehouse():
    """QA pull for Oct 5–11. Eleven inbound contacts, ten of them Quick Form."""
    contacts = {}
    pipeline = []
    ids = [WEX, CITY] + [f"qf-{index}" for index in range(1, 10)]
    assert len(ids) == 11
    for index, contact_id in enumerate(ids):
        tags = () if contact_id == WEX else ("fb-quick-form",)
        contacts[contact_id] = contact(contact_id, "Inbound", *tags)
        pipeline.append(pipeline_opp(f"lead-{index}", contact_id, INSIDE, STAGES[index]))
    contacts[THREE_PL] = contact(THREE_PL, "3PL")
    pipeline.append(pipeline_opp("opp-3pl", THREE_PL, INSIDE, "3PL"))
    for blank_id in BLANKS:
        contacts[blank_id] = contact(blank_id, None)
        pipeline.append(pipeline_opp(f"opp-{blank_id}", blank_id, INSIDE, "blank"))
    for index in range(12):
        contact_id = f"locker-{index}"
        contacts[contact_id] = contact(contact_id, "  ")
        opp = pipeline_opp(f"locker-{index}", contact_id, INSIDE, "Lead Locker")
        opp["name"] = "Lead Locker"
        pipeline.append(opp)
    city = [city_opp("city-1", CITY, "2026-10-08T17:00:00.000Z", "No Sit")]
    names = {f"stage-{name}": name for name in STAGES}
    names["stage-reschedule"] = "Reschedule Needed"
    return contacts, pipeline, city, names


def assemble(contacts, pipeline, city, names, *, include=None, meta=None, sessions=None, goals=None, now=NOW):
    start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
    return metric.assemble_ads_dashboard(
        pipeline_opps=pipeline,
        contact_opps=city,
        contacts=contacts,
        stage_names=names,
        start_local=start_local,
        end_local=end_local,
        now=now,
        meta=meta
        or {
            "status": "ok",
            "spend": 270.30,
            "clicks": None,
            "impressions": None,
            "note": None,
            "account_timezone": "America/Phoenix",
            "aligned": True,
            "bucket": "America/Phoenix",
        },
        sessions=sessions
        or {"status": "unavailable", "reason": "not_configured", "note": "Paid sessions could not be read.", "total": None, "series": None},
        goals=goals or {"status": "missing", "spend": None, "leads": None, "opps": None},
        include_quick_form=include,
    )


class AdsDashboardTests(unittest.TestCase):
    def setUp(self):
        metric.reset_caches()

    def test_constant_and_phoenix_window(self):
        self.assertTrue(metric.INCLUDE_FB_QUICK_FORM)
        self.assertEqual(metric.TIMEZONE_NAME, "America/Phoenix")
        start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
        self.assertEqual(start_local.isoformat(), "2026-10-05T00:00:00-07:00")
        self.assertEqual(end_local.isoformat(), "2026-10-12T00:00:00-07:00")
        self.assertEqual(metric.created_at_bound(start_local), "2026-10-05T07:00:00.000Z")
        self.assertEqual(metric.created_at_bound(end_local), "2026-10-12T07:00:00.000Z")
        self.assertEqual(metric.default_range(NOW), ("2026-10-05", "2026-10-11"))
        early_phoenix = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(metric.default_range(early_phoenix), ("2026-10-04", "2026-10-10"))

    def test_window_boundary_case_and_dedupe(self):
        contacts = {
            "edge-in": contact("edge-in", "  InBound "),
            "edge-out": contact("edge-out", "INBOUND"),
            "dup": contact("dup", "inbound"),
            "locker": contact("locker", "Lead Locker"),
            "reviews": contact("reviews", "Solar Reviews"),
            "three": contact("three", "3pl"),
            "blank": contact("blank", None),
        }
        pipeline = [
            pipeline_opp("in", "edge-in", "2026-10-05T07:00:00.000Z", "New Lead"),
            pipeline_opp("out-before", "edge-out", "2026-10-05T06:59:59.000Z", "New Lead"),
            pipeline_opp("out-after", "edge-out", "2026-10-12T07:00:00.000Z", "New Lead"),
            pipeline_opp("dup-a", "dup", INSIDE, "Call 2"),
            pipeline_opp("dup-b", "dup", INSIDE, "Call 4"),
            pipeline_opp("locker", "locker", INSIDE, "Lead Locker"),
            pipeline_opp("reviews", "reviews", INSIDE, "Solar Reviews"),
            pipeline_opp("three", "three", INSIDE, "3PL"),
            pipeline_opp("blank", "blank", INSIDE, "blank"),
        ]
        payload = assemble(contacts, pipeline, [], {f"stage-{name}": name for name in ("New Lead", "Call 2", "Call 4", "Lead Locker", "Solar Reviews", "3PL", "blank")})
        self.assertEqual(payload["kpis"]["inbound_leads"]["value"], 2)
        self.assertEqual(sorted(payload["lead_contact_ids"]), ["dup", "edge-in"])
        self.assertEqual(sum(row["count"] for row in payload["stages"]), 3)

    def test_oct_5_11_warehouse_reports_actual_not_the_rounded_target(self):
        contacts, pipeline, city, names = warehouse()
        payload = assemble(contacts, pipeline, city, names)
        leads = payload["kpis"]["inbound_leads"]["value"]
        cpl = payload["kpis"]["cost_per_lead"]["value"]
        self.assertEqual(payload["kpis"]["spend"]["value"], 270.30)
        self.assertEqual(leads, 11)
        self.assertEqual(payload["fb_quick_form_leads"], 10)
        self.assertEqual(payload["kpis"]["inbound_leads"]["detail"], "of which FB Quick Form: 10")
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 0)
        self.assertEqual(payload["kpis"]["sales"]["value"], 0)
        self.assertEqual(cpl, 24.57)
        self.assertEqual(payload["kpis"]["cost_per_opp"]["value"], 270.30)
        self.assertEqual(payload["kpis"]["cost_per_demo"]["display"], "N/A")
        self.assertEqual(payload["kpis"]["cost_per_sale"]["display"], "N/A")
        self.assertEqual(payload["kpis"]["cost_per_lead"]["tone"], "good")
        self.assertEqual(payload["kpis"]["spend"]["goal_display"], "no goal")
        # Charles's Phoenix expectation is about 12 leads and $22.53. The warehouse
        # list is 11 inbound contacts, so the gap is reported instead of overwritten.
        self.assertEqual(leads - 12, -1)
        self.assertEqual(round(cpl - 22.53, 2), 2.04)
        html = page.render_html(payload)
        self.assertIn("of which FB Quick Form: 10", html)
        self.assertIn("$270.30", html)
        self.assertIn("$24.57", html)
        self.assertNotIn("$22.53", html)
        self.assertIn(">N/A<", html)
        self.assertIn("no goal", html)
        self.assertIn('class="number positive"', html)
        self.assertIsNone(WORD.search(html))
        self.assertIn("America/Phoenix", html)
        self.assertIn("G-V02RZFR4SZ", html)

    def test_phoenix_only_hour_is_the_twelfth_lead(self):
        contacts, pipeline, city, names = warehouse()
        contacts["edge"] = contact("edge", "inbound", "fb-quick-form")
        pipeline.append(pipeline_opp("edge", "edge", PHOENIX_ONLY, "Call 2"))
        phoenix = assemble(contacts, pipeline, city, names)
        self.assertEqual(phoenix["kpis"]["inbound_leads"]["value"], 12)
        self.assertEqual(phoenix["fb_quick_form_leads"], 11)
        self.assertEqual(phoenix["kpis"]["cost_per_lead"]["value"], 22.53)
        start_et = datetime(2026, 10, 5, tzinfo=NY)
        end_et = datetime(2026, 10, 12, tzinfo=NY)
        eastern = metric.classify_window(
            pipeline,
            city,
            contacts,
            names,
            start_et,
            end_et,
            NOW.astimezone(timezone.utc),
        )
        self.assertEqual(eastern["inbound_leads"], 11)
        self.assertNotIn("edge", eastern["lead_contact_ids"])

    def test_quick_form_can_be_left_out_by_the_constant(self):
        contacts, pipeline, city, names = warehouse()
        self.assertTrue(metric.INCLUDE_FB_QUICK_FORM)
        payload = assemble(contacts, pipeline, city, names, include=False)
        self.assertEqual(payload["kpis"]["inbound_leads"]["value"], 1)
        self.assertEqual(payload["lead_contact_ids"], [WEX])
        self.assertEqual(payload["fb_quick_form_leads"], 0)
        self.assertEqual(payload["fb_quick_form_matched"], 10)
        self.assertEqual(payload["kpis"]["opps"]["value"], 0)
        self.assertEqual(payload["kpis"]["cost_per_lead"]["value"], 270.30)
        self.assertEqual(payload["kpis"]["cost_per_lead"]["tone"], "bad")

    def test_demo_outcome_requires_the_existing_rule(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {"stage-New Lead": "New Lead"}
        no_show = assemble(contacts, pipeline, [city_opp("city", "c", INSIDE, "No Sit")], names)
        self.assertEqual(no_show["kpis"]["demos"]["value"], 0)
        self.assertEqual(no_show["kpis"]["opps"]["value"], 1)
        showed = assemble(
            contacts,
            pipeline,
            [city_opp("city", "c", INSIDE, metric.cac.SIT_DISPOSITION)],
            names,
        )
        self.assertEqual(showed["kpis"]["demos"]["value"], 1)
        later = city_opp("city", "c", INSIDE, metric.cac.SIT_DISPOSITION)
        later["appointmentOccurredAt"] = "2026-10-12T18:00:00.000Z"
        outside = assemble(contacts, pipeline, [later], names)
        self.assertEqual(outside["kpis"]["opps"]["value"], 1)
        self.assertEqual(outside["kpis"]["demos"]["value"], 0)

    def test_sales_use_sold_stage_and_sold_date(self):
        sold_stage = sorted(metric._sold_stage_ids())[0]
        contacts = {"c": contact("c", "inbound", sold="2026-10-08")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        opp = city_opp("sold", "c", INSIDE, "No Sit")
        opp["pipelineStageId"] = sold_stage
        payload = assemble(contacts, pipeline, [opp], {"stage-New Lead": "New Lead"})
        self.assertEqual(payload["kpis"]["sales"]["value"], 1)
        contacts["c"] = contact("c", "inbound", sold="2026-10-04")
        missed = assemble(contacts, pipeline, [opp], {"stage-New Lead": "New Lead"})
        self.assertEqual(missed["kpis"]["sales"]["value"], 0)

    def test_zero_denominator_is_na_and_missing_source_is_blank(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        payload = assemble(
            contacts,
            pipeline,
            [],
            {"stage-New Lead": "New Lead"},
            meta={"status": "ok", "spend": 10, "clicks": 0, "impressions": 0, "note": None},
            sessions={"status": "ok", "total": 0, "series": [{"date": "2026-10-05", "value": 0}]},
        )
        self.assertEqual(payload["rates"]["cpc"]["display"], "N/A")
        self.assertEqual(payload["rates"]["ctr"]["display"], "N/A")
        self.assertEqual(payload["rates"]["cpm"]["display"], "N/A")
        self.assertEqual(payload["rates"]["leads_per_session"]["display"], "N/A")
        self.assertEqual(payload["rates"]["leads_per_click"]["display"], "N/A")
        missing = assemble(
            contacts,
            pipeline,
            [],
            {"stage-New Lead": "New Lead"},
            meta={"status": "unavailable", "reason": "missing_env", "note": "Meta spend could not be read.", "spend": None, "clicks": None, "impressions": None},
        )
        self.assertEqual(missing["kpis"]["spend"]["display"], "\u2014")
        self.assertEqual(missing["kpis"]["cost_per_lead"]["display"], "\u2014")
        self.assertIn("Meta spend could not be read.", missing["errors"])

    def test_paid_channels_and_meta_day_bucketing(self):
        counted = metric.sum_paid_channel_rows(
            [
                {"date": "2026-10-05", "sessionDefaultChannelGroup": "Paid Social", "sessions": 4},
                {"date": "2026-10-05", "sessionDefaultChannelGroup": "Paid Search", "sessions": 3},
                {"date": "2026-10-06", "sessionDefaultChannelGroup": "Organic Social", "sessions": 9},
                {"date": "2026-10-06", "channel": "Direct", "sessions": 8},
            ],
            ["2026-10-05", "2026-10-06"],
        )
        self.assertEqual(counted["total"], 7)
        self.assertEqual(counted["series"][0]["value"], 7)
        self.assertEqual(counted["series"][1]["value"], 0)
        start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
        self.assertTrue(metric.zone_aligns("America/Phoenix", start_local, end_local))
        self.assertTrue(metric.zone_aligns("America/Los_Angeles", start_local, end_local))
        self.assertFalse(metric.zone_aligns("America/New_York", start_local, end_local))
        grouped = metric.rebucket_hourly(
            [
                {
                    "date_start": "2026-10-12",
                    HOURLY: "01:00:00 - 01:59:59",
                    "spend": "10.00",
                    "impressions": "1000",
                    "outbound_clicks": [{"action_type": "outbound_click", "value": "4"}],
                },
                {
                    "date_start": "2026-10-05",
                    HOURLY: "00:00:00 - 00:59:59",
                    "spend": "99.00",
                    "impressions": "50",
                    "outbound_clicks": [{"action_type": "outbound_click", "value": "1"}],
                },
            ],
            "America/New_York",
            start_local,
            end_local,
        )
        self.assertEqual(grouped["spend"], 10.0)
        self.assertEqual(grouped["clicks"], 4)
        self.assertEqual(grouped["impressions"], 1000)
        self.assertIn("America/Phoenix", grouped["note"])
        self.assertIn("3 hours ahead", metric.offset_note("America/New_York", start_local, hourly_failed=True))

    def test_reads_are_bounded_and_graph_is_get_only(self):
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', METRIC_SRC)
        self.assertNotIn('db.collection("ghl_contacts_v2").stream()', METRIC_SRC)
        self.assertNotIn('db.collection("ghl_pipelines_v2").stream()', METRIC_SRC)
        self.assertIn("db.get_all(", METRIC_SRC)
        self.assertIn('.where("pipelineId", "==", LEAD_PIPELINE_ID)', METRIC_SRC)
        self.assertIn('.where("createdAt", ">=", start_iso)', METRIC_SRC)
        self.assertIn('.where("createdAt", "<", end_iso)', METRIC_SRC)
        self.assertIn('.where("contactId", "in", chunk)', METRIC_SRC)
        self.assertIn("CONTACT_IN_CHUNK = 30", METRIC_SRC)
        self.assertIn('method="GET"', METRIC_SRC)
        for verb in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotRegex(METRIC_SRC, rf"method\s*=\s*['\"]{verb}['\"]")
            self.assertNotRegex(PAGE_SRC, rf"method\s*=\s*['\"]{verb}['\"]")
            self.assertNotRegex(METRIC_SRC, rf"requests\.{verb.lower()}\(")
        self.assertIn("s-maxage=600, stale-while-revalidate=1800", METRIC_SRC)
        self.assertIn("s-maxage=600, stale-while-revalidate=1800", PAGE_SRC)
        self.assertIn("pipelineId", INDEXES)
        self.assertIn("createdAt", INDEXES)
        self.assertIn("ghl_opportunities_v2", INDEXES)
        url = metric.account_timezone_url(metric.psf.META_ACCOUNT_ID, "test-token")
        self.assertIn("timezone_name", url)
        self.assertNotIn("/campaigns", url)
        with self.assertRaises(RuntimeError):
            metric.account_timezone_url("act_other", "test-token")

    def test_firestore_queries_use_the_phoenix_bounds_and_chunks(self):
        db = FakeDB()
        db.rows["ghl_opportunities_v2"] = [
            Snap(pipeline_opp("in", "c", INSIDE, "New Lead")),
            Snap(pipeline_opp("out", "d", "2026-10-04T12:00:00.000Z", "New Lead")),
        ]
        db.contacts["c"] = contact("c", "inbound")
        start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
        loaded = metric.load_pipeline_opps(db, start_local, end_local)
        self.assertEqual([opp["id"] for opp in loaded], ["in"])
        filters = db.streams[0][1]
        self.assertIn(("pipelineId", "==", PIPELINE), filters)
        self.assertIn(("createdAt", ">=", "2026-10-05T07:00:00.000Z"), filters)
        self.assertIn(("createdAt", "<", "2026-10-12T07:00:00.000Z"), filters)
        ids = [f"contact-{index}" for index in range(31)]
        metric.load_opps_for_contacts(db, ids)
        chunks = [
            value
            for _name, filters in db.streams
            for field, _op, value in filters
            if field == "contactId"
        ]
        self.assertEqual(sorted(len(chunk) for chunk in chunks), [1, 30])
        metric.load_contacts(db, ["c", "missing"])
        self.assertEqual(db.get_all_calls, [["c", "missing"]])
        db.docs[("ghl_pipelines_v2", PIPELINE)] = {
            "id": PIPELINE,
            "stages": [{"id": "stage-New Lead", "name": "New Lead"}],
        }
        self.assertEqual(metric.load_stage_names(db), {"stage-New Lead": "New Lead"})
        self.assertEqual(len(db.gets), 1)
        metric.load_stage_names(db)
        self.assertEqual(len(db.gets), 1)
        goal = metric.goals_from_doc({"goals": {"ads": {"spend": "400", "leads": 20, "opps": 5}}}, "2026-10")
        self.assertEqual(goal["status"], "ok")
        self.assertEqual(goal["spend"], 400)
        self.assertEqual(goal["leads"], 20)
        absent = metric.goals_from_doc({"goals": {"setter:jane": {"sales_goal": 3}}}, "2026-10")
        self.assertEqual(absent["status"], "missing")

    def test_nav_and_routes(self):
        html = nav.render_dashboard_nav("ads_dashboard")
        self.assertIn('class="navlink active" href="/api/ads_dashboard"', html)
        self.assertIn("Ads Dashboard", html)
        self.assertIsNone(WORD.search(html))
        embed = nav.render_embed_section_row("ads_dashboard")
        self.assertIn('href="/api/ads_dashboard"', embed)
        self.assertEqual(index.dispatch_route("/api/ads_dashboard"), "ads_dashboard")
        self.assertEqual(
            index.dispatch_route("/api/metrics/ads_dashboard?start=2026-10-05&end=2026-10-11"),
            "metrics/ads_dashboard",
        )
        shell = page.render_html(metric.unavailable_payload("Ads Dashboard could not be read."))
        self.assertIsNone(WORD.search(shell))
        self.assertIn("Ads Dashboard", shell)
        self.assertIn("\u2014", shell)


HOURLY = metric.HOURLY_BREAKDOWN


if __name__ == "__main__":
    unittest.main()
