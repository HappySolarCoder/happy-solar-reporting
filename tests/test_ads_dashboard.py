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


def assemble(contacts, pipeline, city, names, *, include=None, meta=None, sessions=None, goals=None, now=NOW, history=None):
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
        history=history,
    )


class AdsDashboardTests(unittest.TestCase):
    def setUp(self):
        metric.reset_caches()

    def test_constant_and_phoenix_window(self):
        self.assertTrue(metric.INCLUDE_FB_QUICK_FORM)
        self.assertEqual(metric.TIMEZONE_NAME, "America/Phoenix")
        self.assertEqual(metric.COST_PER_LEAD_GOAL, 25)
        self.assertEqual(metric.COST_PER_OPP_GOAL, 100)
        self.assertEqual(metric.COST_PER_DEMO_GOAL, 300)
        self.assertEqual(metric.COST_PER_SALE_GOAL, 600)
        on_goal = metric.cost_block(100, 1, metric.COST_PER_OPP_GOAL, "$100")
        over_goal = metric.cost_block(100.01, 1, metric.COST_PER_OPP_GOAL, "$100")
        self.assertEqual(on_goal["tone"], "good")
        self.assertEqual(over_goal["tone"], "bad")
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
        self.assertEqual(sum(row["count"] for row in payload["stages"]), 2)

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
        self.assertEqual(payload["kpis"]["cost_per_opp"]["goal"], 100)
        self.assertEqual(payload["kpis"]["cost_per_opp"]["goal_display"], "$100")
        self.assertEqual(payload["kpis"]["cost_per_opp"]["tone"], "bad")
        self.assertEqual(payload["kpis"]["cost_per_demo"]["goal"], 300)
        self.assertEqual(payload["kpis"]["cost_per_demo"]["display"], "N/A")
        self.assertEqual(payload["kpis"]["cost_per_sale"]["goal"], 600)
        self.assertEqual(payload["kpis"]["cost_per_sale"]["display"], "N/A")
        self.assertEqual(payload["kpis"]["cost_per_lead"]["tone"], "good")
        self.assertEqual(payload["kpis"]["spend"]["goal_display"], "no goal")
        self.assertEqual(payload["kpis"]["demos"]["goal_display"], "no goal")
        self.assertEqual(payload["kpis"]["sales"]["goal_display"], "no goal")
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
        self.assertIn(">Goal $25<", html)
        self.assertIn(">Goal $100<", html)
        self.assertIn(">Goal $300<", html)
        self.assertIn(">Goal $600<", html)
        self.assertLess(html.index("Cost/lead"), html.index("Cost/opp"))
        self.assertLess(html.index("Cost/opp"), html.index("Cost/demo"))
        self.assertLess(html.index("Cost/demo"), html.index("Cost/sale"))
        self.assertIn('class="number positive"', html)
        self.assertIn('class="number negative"', html)
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

    def test_demo_comes_from_the_pipeline_stage(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {"stage-New Lead": "New Lead", "stage-reschedule": "Reschedule Needed", "stage-demo": "Demo-Negotiating"}
        reschedule = city_opp("city", "c", INSIDE, metric.cac.SIT_DISPOSITION)
        waiting = assemble(contacts, pipeline, [reschedule], names)
        self.assertEqual(waiting["kpis"]["demos"]["value"], 0)
        self.assertEqual(waiting["kpis"]["opps"]["value"], 1)
        showed = city_opp("city", "c", INSIDE, "No Sit")
        showed["pipelineStageId"] = "stage-demo"
        demo = assemble(contacts, pipeline, [showed], names)
        self.assertEqual(demo["kpis"]["demos"]["value"], 1)
        outside = dict(showed)
        outside["createdAt"] = "2026-10-12T18:00:00.000Z"
        later = assemble(contacts, pipeline, [outside], names)
        self.assertEqual(later["kpis"]["opps"]["value"], 0)
        self.assertEqual(later["kpis"]["demos"]["value"], 0)

    def test_title_phone_and_near_name_dedupe(self):
        self.assertTrue(metric.is_ad_lead(contact("qf", "Facebook Quick Form", "fb-quick-form"), True))
        self.assertTrue(metric.is_ad_lead(contact("fb", "FB Quick Form"), True))
        self.assertFalse(metric.is_ad_lead(contact("qf", "Facebook Quick Form", "fb-quick-form"), False))
        self.assertFalse(metric.is_ad_lead(contact("fb", "FB Quick Form"), False))
        quick_locker = pipeline_opp("quick-locker", "quick-locked", INSIDE, "New Lead")
        quick_locker["name"] = "Lead Locker"
        excluded = assemble(
            {"quick-locked": contact("quick-locked", "FB Quick Form")},
            [quick_locker],
            [],
            {"stage-New Lead": "New Lead"},
        )
        self.assertEqual(excluded["kpis"]["inbound_leads"]["value"], 0)
        locker = pipeline_opp("locker", "locked", INSIDE, "New Lead")
        locker["name"] = "Lead Locker Jane"
        reviews = pipeline_opp("reviews", "solar", INSIDE, "New Lead")
        reviews["name"] = "Solar Review"
        kept = pipeline_opp("kept", "kept", INSIDE, "New Lead")
        same_phone_a = contact("a", "inbound")
        same_phone_a["phone"] = "+1 (480) 555-1212"
        same_phone_b = contact("b", "inbound")
        same_phone_b["phone"] = "4805551212"
        same_phone_b["firstName"] = "Other"
        same_phone_b["lastName"] = "Person"
        phone = assemble(
            {
                "locked": contact("locked", "inbound"),
                "solar": contact("solar", "inbound"),
                "kept": contact("kept", "inbound"),
                "a": same_phone_a,
                "b": same_phone_b,
            },
            [
                locker,
                reviews,
                kept,
                pipeline_opp("oa", "a", INSIDE, "New Lead"),
                pipeline_opp("ob", "b", INSIDE, "Call 2"),
            ],
            [],
            {"stage-New Lead": "New Lead", "stage-Call 2": "Call 2"},
        )
        self.assertEqual(phone["kpis"]["inbound_leads"]["value"], 2)
        self.assertEqual(sorted(phone["lead_contact_ids"]), ["a", "kept"])
        self.assertEqual(sum(row["count"] for row in phone["stages"]), 2)
        madison = contact("IB5lTSmPUjf8QVQKk7t4", "inbound")
        madison["firstName"] = "Malcolm"
        madison["lastName"] = "Madison"
        maddison = contact("I1iqm4WgG6Ryxt4mBCgo", "inbound")
        maddison["firstName"] = "Malcolm"
        maddison["lastName"] = "Maddison"
        first = pipeline_opp("m1", "IB5lTSmPUjf8QVQKk7t4", "2026-10-08T18:00:00.000Z", "New Lead")
        first["name"] = "Inbound Malcolm Madison"
        second = pipeline_opp("m2", "I1iqm4WgG6Ryxt4mBCgo", "2026-10-08T18:05:00.000Z", "Call 2")
        second["name"] = "Malcolm Maddison"
        names = {"stage-New Lead": "New Lead", "stage-Call 2": "Call 2"}
        merged = assemble(
            {"IB5lTSmPUjf8QVQKk7t4": madison, "I1iqm4WgG6Ryxt4mBCgo": maddison},
            [first, second],
            [],
            names,
        )
        self.assertEqual(merged["kpis"]["inbound_leads"]["value"], 1)
        self.assertEqual(sum(row["count"] for row in merged["stages"]), 1)
        apart = dict(second)
        apart["id"] = "m3"
        apart["createdAt"] = "2026-10-08T18:20:00.000Z"
        split = assemble(
            {"IB5lTSmPUjf8QVQKk7t4": madison, "I1iqm4WgG6Ryxt4mBCgo": maddison},
            [first, apart],
            [],
            names,
        )
        self.assertEqual(split["kpis"]["inbound_leads"]["value"], 2)

    def test_history_keeps_an_opp_moved_to_sweeper(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        moved = city_opp("moved", "c", INSIDE, "No Sit")
        moved["pipelineId"] = metric.SWEEPER_PIPELINE_ID
        names = {"stage-New Lead": "New Lead", "stage-reschedule": "Reschedule Needed", "stage-demo": "Demo-Negotiating"}
        without = assemble(contacts, pipeline, [moved], names)
        self.assertEqual(without["kpis"]["opps"]["value"], 0)
        with_history = assemble(
            contacts,
            pipeline,
            [moved],
            names,
            history={"moved": [{"opportunityId": "moved", "pipelineName": "Virtual"}]},
        )
        self.assertEqual(with_history["kpis"]["opps"]["value"], 1)
        self.assertEqual(with_history["kpis"]["demos"]["value"], 0)
        moved["pipelineStageId"] = "stage-demo"
        demo = assemble(
            contacts,
            pipeline,
            [moved],
            names,
            history={"moved": [{"pipelineId": VIRTUAL}]},
        )
        self.assertEqual(demo["kpis"]["demos"]["value"], 1)

    def test_deleted_opp_counts_from_contact_history(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {"stage-New Lead": "New Lead"}
        history = {
            "gone": [
                {
                    "opportunityId": "gone",
                    "contactId": "c",
                    "pipelineName": "Buffalo",
                    "toStageName": "New Appointment",
                    "effectiveAt": "2026-10-08T16:00:00.000Z",
                },
                {
                    "opportunityId": "gone",
                    "contactId": "c",
                    "pipelineName": "Buffalo",
                    "toStageName": "Reschedule Needed",
                    "effectiveAt": "2026-10-08T18:00:00.000Z",
                },
            ],
            "too-early": [
                {
                    "opportunityId": "too-early",
                    "contactId": "c",
                    "pipelineName": "Rochester",
                    "toStageName": "New Appointment",
                    "effectiveAt": "2026-10-04T12:00:00.000Z",
                }
            ],
            "not-city": [
                {
                    "opportunityId": "not-city",
                    "contactId": "c",
                    "pipelineName": "Sweeper",
                    "toStageName": "New Appointment",
                    "effectiveAt": INSIDE,
                }
            ],
        }
        payload = assemble(contacts, pipeline, [], names, history=history)
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 0)
        self.assertEqual(metric._first_history_time(history["gone"]).isoformat(), "2026-10-08T16:00:00+00:00")

    def test_deleted_opp_within_ten_minutes_of_another_is_ignored(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        live = city_opp("live", "c", INSIDE, "No Sit")
        names = {"stage-New Lead": "New Lead", "stage-reschedule": "Reschedule Needed"}

        def history_only(opp_id: str, effective_at: str) -> dict:
            return {
                opp_id: [
                    {
                        "opportunityId": opp_id,
                        "contactId": "c",
                        "pipelineName": "Buffalo",
                        "toStageName": "New Appointment",
                        "effectiveAt": effective_at,
                    }
                ]
            }

        near = assemble(
            contacts,
            pipeline,
            [live],
            names,
            history=history_only("dup", "2026-10-08T18:05:00.000Z"),
        )
        self.assertEqual(near["kpis"]["opps"]["value"], 1)
        self.assertEqual(near["kpis"]["demos"]["value"], 0)
        apart = assemble(
            contacts,
            pipeline,
            [live],
            names,
            history=history_only("kept", "2026-10-08T18:20:00.000Z"),
        )
        self.assertEqual(apart["kpis"]["opps"]["value"], 2)
        lead_only = assemble(
            contacts,
            pipeline,
            [],
            names,
            history=history_only("dup-of-lead", "2026-10-08T18:05:00.000Z"),
        )
        self.assertEqual(lead_only["kpis"]["opps"]["value"], 0)

    def test_sweeper_opp_keeps_a_prior_demo_stage(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        moved = city_opp("moved", "c", INSIDE, "No Sit")
        moved["pipelineId"] = metric.SWEEPER_PIPELINE_ID
        moved["pipelineStageId"] = "stage-rehash"
        names = {
            "stage-New Lead": "New Lead",
            "stage-rehash": "Rehash",
            "stage-reschedule": "Reschedule Needed",
        }
        payload = assemble(
            contacts,
            pipeline,
            [moved],
            names,
            history={
                "moved": [
                    {
                        "opportunityId": "moved",
                        "contactId": "c",
                        "pipelineName": "Rochester",
                        "toStageName": "Demo-Negotiating",
                        "effectiveAt": "2026-10-08T17:00:00.000Z",
                    },
                    {
                        "opportunityId": "moved",
                        "contactId": "c",
                        "pipelineName": "Sweeper",
                        "toStageName": "Rehash",
                        "effectiveAt": "2026-10-09T17:00:00.000Z",
                    },
                ]
            },
        )
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 1)

    def test_sold_stage_counts_as_a_demo(self):
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        sold = city_opp("sold", "c", INSIDE, "No Sit")
        sold["pipelineStageId"] = "stage-sold"
        names = {"stage-New Lead": "New Lead", "stage-sold": "Sold", "stage-leg": "One Legger"}
        payload = assemble(contacts, pipeline, [sold], names)
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 1)
        self.assertFalse(metric.stage_is_demo("One Legger"))
        self.assertTrue(metric.stage_is_demo("Demo-Not Interested"))
        self.assertTrue(metric.stage_is_demo("Sale Cancelled"))
        self.assertTrue(metric.stage_is_demo("Sale Canceled"))
        self.assertFalse(metric.stage_is_demo("Reschedule Needed"))

    def test_one_legger_is_not_a_demo(self):
        self.assertFalse(metric.stage_is_demo("One Legger"))
        self.assertIn("A One Legger is not a demo.", metric.stage_is_demo.__doc__ or "")
        contacts = {"c": contact("c", "inbound")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {
            "stage-New Lead": "New Lead",
            "stage-leg": "One Legger",
            "stage-reschedule": "Reschedule Needed",
        }
        current = city_opp("leg", "c", INSIDE, "No Sit")
        current["pipelineStageId"] = "stage-leg"
        payload = assemble(contacts, pipeline, [current], names)
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 0)
        history_only = city_opp("past", "c", INSIDE, "No Sit")
        from_history = assemble(
            contacts,
            pipeline,
            [history_only],
            names,
            history={
                "past": [
                    {
                        "opportunityId": "past",
                        "contactId": "c",
                        "pipelineName": "Buffalo",
                        "toStageName": "One Legger",
                        "effectiveAt": INSIDE,
                    }
                ]
            },
        )
        self.assertEqual(from_history["kpis"]["opps"]["value"], 1)
        self.assertEqual(from_history["kpis"]["demos"]["value"], 0)

    def test_sale_cancelled_counts_as_a_demo_and_a_sale(self):
        self.assertNotIn("stage_is_sale", METRIC_SRC)
        self.assertIn("Sale Cancelled", metric.stage_is_demo.__doc__ or "")
        self.assertIn("eight", (metric._sold_stage_ids.__doc__ or "").lower())
        cancelled_id = "adf3106e-d371-47ff-ab9e-6f7f33ecf415"
        sold_id = "7981f111-73f2-4593-9662-6b95d99bf51a"
        self.assertEqual(len(metric._sold_stage_ids()), 8)
        self.assertIn(cancelled_id, metric._sold_stage_ids())
        self.assertIn(sold_id, metric._sold_stage_ids())
        contacts = {"c": contact("c", "inbound", sold="2026-10-08")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {
            "stage-New Lead": "New Lead",
            cancelled_id: "Sale Cancelled",
            sold_id: "Sold",
            "stage-cancelled": "Sale Cancelled",
        }
        cancelled = city_opp("cancelled", "c", INSIDE, "No Sit")
        cancelled["pipelineStageId"] = cancelled_id
        payload = assemble(contacts, pipeline, [cancelled], names)
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 1)
        self.assertEqual(payload["kpis"]["sales"]["value"], 1)
        self.assertEqual(payload["kpis"]["cost_per_sale"]["value"], 270.30)
        named = city_opp("named", "c", INSIDE, "No Sit")
        named["pipelineStageId"] = "stage-cancelled"
        by_name = assemble(contacts, pipeline, [named], names)
        self.assertNotIn("stage-cancelled", metric._sold_stage_ids())
        self.assertEqual(by_name["kpis"]["demos"]["value"], 1)
        self.assertEqual(by_name["kpis"]["sales"]["value"], 0)
        self.assertIsNone(by_name["kpis"]["cost_per_sale"]["value"])
        self.assertEqual(by_name["kpis"]["cost_per_sale"]["display"], "N/A")
        sold = city_opp("sold-opp", "c", INSIDE, "No Sit")
        sold["pipelineStageId"] = sold_id
        pair = assemble(contacts, pipeline, [sold, cancelled], names)
        self.assertEqual(pair["kpis"]["opps"]["value"], 2)
        self.assertEqual(pair["kpis"]["demos"]["value"], 1)
        self.assertEqual(pair["kpis"]["sales"]["value"], 1)
        self.assertEqual(pair["kpis"]["cost_per_sale"]["value"], 270.30)
        outside = {"c": contact("c", "inbound", sold="2026-09-15")}
        missed = assemble(outside, pipeline, [cancelled], names)
        self.assertEqual(missed["kpis"]["sales"]["value"], 0)
        self.assertEqual(missed["kpis"]["demos"]["value"], 1)

    def test_sale_cancelled_after_a_demo_on_the_same_opp_is_one_demo(self):
        contacts = {"c": contact("c", "inbound", sold="2026-10-08")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        opp = city_opp("moved", "c", INSIDE, "No Sit")
        opp["pipelineStageId"] = "stage-cancelled"
        names = {"stage-New Lead": "New Lead", "stage-cancelled": "Sale Cancelled"}
        payload = assemble(
            contacts,
            pipeline,
            [opp],
            names,
            history={
                "moved": [
                    {
                        "opportunityId": "moved",
                        "contactId": "c",
                        "pipelineName": "Buffalo",
                        "toStageName": "Demo-Negotiating",
                        "effectiveAt": INSIDE,
                    },
                    {
                        "opportunityId": "moved",
                        "contactId": "c",
                        "pipelineName": "Buffalo",
                        "toStageName": "Sale Cancelled",
                        "effectiveAt": "2026-10-09T17:00:00.000Z",
                    },
                ]
            },
        )
        self.assertEqual(payload["kpis"]["opps"]["value"], 1)
        self.assertEqual(payload["kpis"]["demos"]["value"], 1)
        self.assertEqual(payload["kpis"]["sales"]["value"], 0)

    def test_demos_count_once_per_lead_unless_sweeper_rehash_is_filled(self):
        sweeper_field = "HWfjOp8MvE6soxBAL75f"
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {
            "stage-New Lead": "New Lead",
            "stage-demo": "Demo-Negotiating",
            "stage-sold": "Sold",
            "stage-cancelled": "Sale Cancelled",
            "stage-leg": "One Legger",
        }

        def city_pair(second_stage: str):
            showed = city_opp("demo", "c", "2026-10-08T16:00:00.000Z", "No Sit")
            showed["pipelineStageId"] = "stage-demo"
            later = city_opp("later", "c", INSIDE, "No Sit")
            later["pipelineStageId"] = second_stage
            return [showed, later]

        plain = {"c": contact("c", "inbound")}
        sold_pair = assemble(plain, pipeline, city_pair("stage-sold"), names)
        self.assertEqual(sold_pair["kpis"]["opps"]["value"], 2)
        self.assertEqual(sold_pair["kpis"]["demos"]["value"], 1)
        cancelled_pair = assemble(plain, pipeline, city_pair("stage-cancelled"), names)
        self.assertEqual(cancelled_pair["kpis"]["opps"]["value"], 2)
        self.assertEqual(cancelled_pair["kpis"]["demos"]["value"], 1)
        self.assertNotIn("stage-sold", metric._sold_stage_ids())
        self.assertNotIn("stage-cancelled", metric._sold_stage_ids())

        filled_contact = contact("c", "inbound")
        filled_contact["customFields"].append({"id": sweeper_field, "value": "Diamond"})
        filled = assemble({"c": filled_contact}, pipeline, city_pair("stage-sold"), names)
        self.assertEqual(filled["kpis"]["demos"]["value"], 2)
        blank_contact = contact("c", "inbound")
        blank_contact["customFields"].append({"id": sweeper_field, "value": "  "})
        blank = assemble({"c": blank_contact}, pipeline, city_pair("stage-sold"), names)
        self.assertEqual(blank["kpis"]["demos"]["value"], 1)

        legger = city_opp("leg", "c", INSIDE, "No Sit")
        legger["pipelineStageId"] = "stage-leg"
        only_leg = assemble(plain, pipeline, [legger], names)
        self.assertEqual(only_leg["kpis"]["opps"]["value"], 1)
        self.assertEqual(only_leg["kpis"]["demos"]["value"], 0)
        with_demo = city_pair("stage-leg")
        still_one = assemble({"c": filled_contact}, pipeline, with_demo, names)
        self.assertEqual(still_one["kpis"]["opps"]["value"], 2)
        self.assertEqual(still_one["kpis"]["demos"]["value"], 1)

    def test_october_and_september_two_lead_demos_stay_two(self):
        """Two different leads stay two demos. Oct 1–16 and September stay at 2."""
        names = {"stage-New Lead": "New Lead", "stage-demo": "Demo-Negotiating"}

        def counted(created: str, start: str, end: str) -> int:
            contacts = {
                "a": contact("a", "inbound"),
                "b": contact("b", "inbound"),
            }
            pipeline = [
                pipeline_opp("lead-a", "a", created, "New Lead"),
                pipeline_opp("lead-b", "b", created, "New Lead"),
            ]
            first = city_opp("city-a", "a", created, "No Sit")
            second = city_opp("city-b", "b", created, "No Sit")
            first["pipelineStageId"] = "stage-demo"
            second["pipelineStageId"] = "stage-demo"
            start_local, end_local = metric.date_window(start, end)
            result = metric.classify_window(
                pipeline,
                [first, second],
                contacts,
                names,
                start_local,
                end_local,
                NOW.astimezone(timezone.utc),
            )
            return result["demos"]

        self.assertEqual(counted("2026-10-08T18:00:00.000Z", "2026-10-01", "2026-10-16"), 2)
        self.assertEqual(counted("2026-09-15T18:00:00.000Z", "2026-09-01", "2026-09-30"), 2)

    def test_stage_name_sold_or_sale_cancelled_is_not_a_sale(self):
        self.assertNotIn("stage_is_sale", METRIC_SRC)
        contacts = {"c": contact("c", "inbound", sold="2026-10-08")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "New Lead")]
        names = {
            "stage-New Lead": "New Lead",
            "unknown-sold": "Sold",
            "unknown-refund": "Sale Cancelled - refund",
            "unknown-cancelled": "Sale Cancelled",
        }
        sweeper = city_opp("sweeper-sold", "c", INSIDE, "No Sit")
        sweeper["pipelineId"] = metric.SWEEPER_PIPELINE_ID
        sweeper["pipelineStageId"] = "unknown-sold"
        sweeper_sale = assemble(contacts, pipeline, [sweeper], names)
        self.assertNotIn("unknown-sold", metric._sold_stage_ids())
        self.assertEqual(sweeper_sale["kpis"]["sales"]["value"], 0)
        self.assertEqual(sweeper_sale["kpis"]["demos"]["value"], 0)

        locker = city_opp("locker-refund", "c", INSIDE, "No Sit")
        locker["pipelineId"] = PIPELINE
        locker["pipelineStageId"] = "unknown-refund"
        locker_sale = assemble(contacts, pipeline, [locker], names)
        self.assertEqual(locker_sale["kpis"]["sales"]["value"], 0)
        self.assertEqual(locker_sale["kpis"]["demos"]["value"], 0)

        city = city_opp("city-cancelled", "c", INSIDE, "No Sit")
        city["pipelineStageId"] = "unknown-cancelled"
        city_sale = assemble(contacts, pipeline, [city], names)
        self.assertNotIn("unknown-cancelled", metric._sold_stage_ids())
        self.assertEqual(city_sale["kpis"]["sales"]["value"], 0)
        self.assertEqual(city_sale["kpis"]["demos"]["value"], 1)
        self.assertEqual(city_sale["kpis"]["opps"]["value"], 1)

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

    def test_lead_date_sale_counts_when_sold_after_the_window(self):
        # 9/14 Inbound lead whose Virtual opp was won on 10/29.
        sold_stage = "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad"
        self.assertIn(sold_stage, metric._sold_stage_ids())
        contacts = {"c": contact("c", "Inbound", sold="2026-10-29T00:00:00.000Z")}
        pipeline = [pipeline_opp("lead", "c", INSIDE, "Reconnect to Book")]
        won = city_opp("won", "c", INSIDE, "Sit")
        won["pipelineStageId"] = sold_stage
        won["status"] = "won"
        payload = assemble(contacts, pipeline, [won], {"stage-Reconnect to Book": "Reconnect to Book", sold_stage: "Sold"})
        self.assertEqual(payload["kpis"]["demos"]["value"], 1)
        self.assertEqual(payload["kpis"]["sales"]["value"], 1)
        later = city_opp("later", "c", "2026-10-27T18:00:00.000Z", "Sit")
        later["pipelineStageId"] = sold_stage
        moved = assemble(contacts, pipeline, [later], {})
        self.assertEqual(moved["kpis"]["opps"]["value"], 0)
        self.assertEqual(moved["kpis"]["sales"]["value"], 1)
        deleted = dict(won, deleted=True)
        gone = assemble(contacts, pipeline, [deleted], {})
        self.assertEqual(gone["kpis"]["sales"]["value"], 0)
        no_date = assemble({"c": contact("c", "Inbound")}, pipeline, [won], {})
        self.assertEqual(no_date["kpis"]["sales"]["value"], 0)

    def test_sales_by_sold_date_view(self):
        sold_stage = sorted(metric._sold_stage_ids())[0]

        def sold(opp_id, contact_id):
            return {"id": opp_id, "contactId": contact_id, "pipelineStageId": sold_stage}

        contacts = {
            "in": contact("in", "Inbound", sold="2026-10-08T00:00:00.000Z"),
            "qf": contact("qf", "Facebook Quick Form", sold="2026-10-11"),
            "early": contact("early", "Inbound", sold="2026-10-04"),
            "late": contact("late", "Inbound", sold="2026-10-12"),
            "door": contact("door", "Door Knock", sold="2026-10-08"),
            "gone": contact("gone", "Inbound", sold="2026-10-08"),
        }
        opps = [
            sold("a", "in"),
            sold("b", "in"),
            sold("c", "qf"),
            sold("d", "early"),
            sold("e", "late"),
            sold("f", "door"),
            dict(sold("g", "gone"), deleted=True),
            {"id": "h", "contactId": "door", "pipelineStageId": "stage-sold"},
        ]
        start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
        view = metric.sales_by_sold_date(opps, contacts, start_local, end_local, include_quick_form=True)
        self.assertEqual(view["value"], 2)
        self.assertEqual(view["contact_ids"], ["in", "qf"])
        no_qf = metric.sales_by_sold_date(opps, contacts, start_local, end_local, include_quick_form=False)
        self.assertEqual(no_qf["contact_ids"], ["in"])
        payload = assemble({}, [], [], {})
        self.assertIsNone(payload["kpis"]["sales_by_sold_date"]["value"])
        shown = metric.assemble_ads_dashboard(
            pipeline_opps=[], contact_opps=[], contacts={}, stage_names={},
            start_local=start_local, end_local=end_local, now=NOW, meta=None,
            sessions=None, goals=None, sold_date_sales=view,
        )
        self.assertEqual(shown["kpis"]["sales_by_sold_date"]["value"], 2)
        self.assertIn("by Sold Date: 2", shown["kpis"]["sales"]["detail"])

    def test_sold_candidates_use_the_eight_stage_ids_once(self):
        db = FakeDB()
        sold_stage = sorted(metric._sold_stage_ids())[0]
        db.rows["ghl_opportunities_v2"] = [Snap({"id": "s", "contactId": "c", "pipelineStageId": sold_stage})]
        db.contacts["c"] = contact("c", "Inbound", sold="2026-10-08")
        opps, contacts = metric.load_sold_candidates(db)
        metric.load_sold_candidates(db)
        self.assertEqual(len(db.streams), 1)
        self.assertEqual(db.streams[0][1], [("pipelineStageId", "in", sorted(metric._sold_stage_ids()))])
        self.assertEqual([opp["id"] for opp in opps], ["s"])
        self.assertIn("c", contacts)

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
        self.assertNotIn('db.collection("ghl_opportunity_stage_history_v1").stream()', METRIC_SRC)
        self.assertIn('.where("opportunityId", "in", chunk)', METRIC_SRC)
        self.assertIn('HISTORY_COLLECTION).where("contactId", "in", chunk)', METRIC_SRC)
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

    def test_missing_index_falls_back_to_created_at_range(self):
        class RaisingQuery(Query):
            def where(self, field, op, value):
                return RaisingQuery(self.db, self.name, self.filters + [(field, op, value)])

            def stream(self):
                self.db.streams.append((self.name, list(self.filters)))
                if any(field == "pipelineId" for field, _op, _value in self.filters):
                    raise RuntimeError("The query requires an index. You can create it here: https://example.test/token")
                return [
                    snap
                    for snap in self.db.rows.get(self.name, [])
                    if _matches(snap, self.filters)
                ]

        class RaisingCollection(Collection):
            def where(self, field, op, value):
                return RaisingQuery(self.db, self.name, [(field, op, value)])

        class RaisingDB(FakeDB):
            def collection(self, name):
                return RaisingCollection(self, name)

        def _matches(snap, filters):
            data = snap.to_dict()
            for field, op, value in filters:
                if field == "limit":
                    continue
                current = data.get(field)
                if op == ">=" and not (current >= value):
                    return False
                if op == "<" and not (current < value):
                    return False
                if op == "==" and current != value:
                    return False
            return True

        db = RaisingDB()
        other = pipeline_opp("other", "z", INSIDE, "New Lead")
        other["pipelineId"] = "other-pipeline"
        db.rows["ghl_opportunities_v2"] = [
            Snap(pipeline_opp("in", "c", INSIDE, "New Lead")),
            Snap(pipeline_opp("out", "d", "2026-10-04T12:00:00.000Z", "New Lead")),
            Snap(other),
        ]
        start_local, end_local = metric.date_window("2026-10-05", "2026-10-11")
        loaded = metric.load_pipeline_opps(db, start_local, end_local)
        self.assertEqual([opp["id"] for opp in loaded], ["in"])
        self.assertEqual(metric._PIPELINE_READ_NOTE, metric.INDEX_FALLBACK_NOTE)
        self.assertEqual(len(db.streams), 2)
        self.assertNotIn("pipelineId", [field for field, _op, _value in db.streams[1][1]])

        class OtherErrorQuery(RaisingQuery):
            def where(self, field, op, value):
                return OtherErrorQuery(self.db, self.name, self.filters + [(field, op, value)])

            def stream(self):
                raise RuntimeError("permission denied")

        class OtherCollection(RaisingCollection):
            def where(self, field, op, value):
                return OtherErrorQuery(self.db, self.name, [(field, op, value)])

        class OtherDB(RaisingDB):
            def collection(self, name):
                return OtherCollection(self, name)

        with self.assertRaises(RuntimeError):
            metric.load_pipeline_opps(OtherDB(), start_local, end_local)
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
        self.assertIsNone(goal["demos"])
        absent = metric.goals_from_doc({"goals": {"setter:jane": {"sales_goal": 3}}}, "2026-10")
        self.assertEqual(absent["status"], "missing")
        october = metric.goals_from_doc(
            {
                "goals": {
                    "ads_dashboard": {
                        "budget": "1800",
                        "leads": 30,
                        "opps": 10,
                        "demos": 6,
                        "sales": 3,
                        "cost_per_lead": 25,
                        "cost_per_opp": 100,
                        "cost_per_demo": 300,
                        "cost_per_sale": 600,
                    }
                }
            },
            "2026-10",
        )
        self.assertEqual(october["status"], "ok")
        self.assertEqual(october["spend"], 1800)
        self.assertEqual(october["leads"], 30)
        self.assertEqual(october["opps"], 10)
        self.assertEqual(october["demos"], 6)
        self.assertEqual(october["sales"], 3)
        contacts, pipeline, city, names = warehouse()
        shown = assemble(contacts, pipeline, city, names, goals=october)
        self.assertEqual(shown["kpis"]["spend"]["goal_display"], "$1,800.00")
        self.assertEqual(shown["kpis"]["inbound_leads"]["goal"], 30)
        self.assertEqual(shown["kpis"]["opps"]["goal"], 10)
        self.assertEqual(shown["kpis"]["demos"]["goal"], 6)
        self.assertEqual(shown["kpis"]["sales"]["goal"], 3)
        goal_html = page.render_html(shown)
        self.assertIn(">Goal $1,800.00<", goal_html)
        self.assertIn(">Goal 30<", goal_html)
        self.assertIn(">Goal 10<", goal_html)
        self.assertIn(">Goal 6<", goal_html)
        self.assertIn(">Goal 3<", goal_html)
        self.assertIn(">Goal $100<", goal_html)

    def test_cost_goals_use_the_month_doc_and_fall_back_to_constants(self):
        contacts, pipeline, city, names = warehouse()
        missing = metric.goals_from_doc(None, "2026-10")
        self.assertEqual(missing["status"], "missing")
        self.assertIsNone(missing["cost_per_lead"])
        fallback = assemble(contacts, pipeline, city, names, goals=missing)
        self.assertEqual(fallback["kpis"]["cost_per_lead"]["goal"], 25)
        self.assertEqual(fallback["kpis"]["cost_per_opp"]["goal"], 100)
        self.assertEqual(fallback["kpis"]["cost_per_demo"]["goal"], 300)
        self.assertEqual(fallback["kpis"]["cost_per_sale"]["goal"], 600)
        self.assertEqual(fallback["kpis"]["cost_per_lead"]["goal_display"], "$25")
        partial = metric.goals_from_doc(
            {"goals": {"ads_dashboard": {"leads": 30, "cost_per_opp": 80}}},
            "2026-10",
        )
        self.assertEqual(partial["status"], "ok")
        self.assertIsNone(partial["cost_per_lead"])
        self.assertEqual(partial["cost_per_opp"], 80)
        mixed = assemble(contacts, pipeline, city, names, goals=partial)
        self.assertEqual(mixed["kpis"]["cost_per_lead"]["goal"], 25)
        self.assertEqual(mixed["kpis"]["cost_per_opp"]["goal"], 80)
        self.assertEqual(mixed["kpis"]["cost_per_opp"]["goal_display"], "$80")
        self.assertEqual(mixed["kpis"]["cost_per_demo"]["goal"], 300)
        self.assertEqual(mixed["kpis"]["cost_per_sale"]["goal"], 600)
        self.assertEqual(mixed["kpis"]["inbound_leads"]["goal"], 30)
        overridden = metric.goals_from_doc(
            {
                "goals": {
                    "ads_dashboard": {
                        "cost_per_lead": 10,
                        "cost_per_opp": 40,
                        "cost_per_demo": 90,
                        "cost_per_sale": 250,
                    }
                }
            },
            "2026-10",
        )
        custom = assemble(contacts, pipeline, city, names, goals=overridden)
        self.assertEqual(custom["kpis"]["cost_per_lead"]["goal"], 10)
        self.assertEqual(custom["kpis"]["cost_per_opp"]["goal"], 40)
        self.assertEqual(custom["kpis"]["cost_per_demo"]["goal"], 90)
        self.assertEqual(custom["kpis"]["cost_per_sale"]["goal"], 250)
        self.assertEqual(custom["kpis"]["cost_per_lead"]["tone"], "bad")
        self.assertEqual(custom["kpis"]["cost_per_lead"]["goal_display"], "$10")
        html = page.render_html(custom)
        self.assertIn(">Goal $10<", html)
        self.assertIn(">Goal $40<", html)
        self.assertIn(">Goal $90<", html)
        self.assertIn(">Goal $250<", html)

    def test_unusable_cost_goals_fall_back_to_constants(self):
        contacts, pipeline, city, names = warehouse()
        cases = (
            ("zero", 0),
            ("negative", -5),
            ("nan", float("nan")),
            ("infinite", float("inf")),
            ("non_numeric", "nope"),
        )
        for label, bad in cases:
            parsed = metric.goals_from_doc(
                {
                    "goals": {
                        "ads_dashboard": {
                            "leads": 30,
                            "cost_per_lead": bad,
                            "cost_per_opp": bad,
                            "cost_per_demo": bad,
                            "cost_per_sale": bad,
                        }
                    }
                },
                "2026-10",
            )
            self.assertEqual(parsed["leads"], 30, label)
            for key in ("cost_per_lead", "cost_per_opp", "cost_per_demo", "cost_per_sale"):
                self.assertIsNone(parsed[key], f"{label} {key}")
            shown = assemble(contacts, pipeline, city, names, goals=parsed)
            self.assertEqual(shown["kpis"]["cost_per_lead"]["goal"], 25, label)
            self.assertEqual(shown["kpis"]["cost_per_opp"]["goal"], 100, label)
            self.assertEqual(shown["kpis"]["cost_per_demo"]["goal"], 300, label)
            self.assertEqual(shown["kpis"]["cost_per_sale"]["goal"], 600, label)
            self.assertEqual(shown["kpis"]["cost_per_lead"]["goal_display"], "$25", label)
            self.assertEqual(shown["kpis"]["cost_per_opp"]["goal_display"], "$100", label)
            self.assertEqual(shown["kpis"]["cost_per_demo"]["goal_display"], "$300", label)
            self.assertEqual(shown["kpis"]["cost_per_sale"]["goal_display"], "$600", label)
            self.assertNotIn("inf", shown["kpis"]["cost_per_sale"]["goal_display"].lower(), label)
            raw = {
                "cost_per_lead": bad,
                "cost_per_opp": bad,
                "cost_per_demo": bad,
                "cost_per_sale": bad,
            }
            self.assertEqual(metric.cost_goal_value(raw, "cost_per_lead"), 25, label)
            self.assertEqual(metric.cost_goal_value(raw, "cost_per_opp"), 100, label)
            self.assertEqual(metric.cost_goal_value(raw, "cost_per_demo"), 300, label)
            self.assertEqual(metric.cost_goal_value(raw, "cost_per_sale"), 600, label)

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
