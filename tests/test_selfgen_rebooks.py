# -*- coding: utf-8 -*-
"""Consultant Self Gen rebook credit (Evan, 2026-10-21).

Locked case: Zach Maecker rebooked contact TcbzRRB7KCIt994R5xZG through the
Booking Hub on 2026-10-21 (6:21 PM ET). The only opp, h0HzaCdAJ5iXujzn6RGF,
was created 2026-05-07 in Buffalo and sat in DQ'ed with a May No Sit. It must
count once as a Self Gen opp for Zach in October, on the rebook date, and
never change company Opportunities Created totals.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import selfgen_rebooks as sr  # noqa: E402
from opportunities_created import MetricContract, compute  # noqa: E402
from channel_goals import self_gen_actuals  # noqa: E402

UTC = timezone.utc
BUFFALO = "GQtUlcTmLJ61HZjrGEPC"
ZACH_ID = "nFf2FIr40kvWRCVaMej2"
OPP = "h0HzaCdAJ5iXujzn6RGF"
CONTACT = "TcbzRRB7KCIt994R5xZG"
LEAD = "hd5QqHEOVSsPom5bJ32P"
SETTER = "Eq4NLTSkJ56KTxbxypuE"
SWEEPER = "HWfjOp8MvE6soxBAL75f"


class Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._d = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._d or {})


class Query:
    def __init__(self, db, name, filters=()):
        self.db, self.name, self.filters = db, name, list(filters)

    def where(self, field, op, value):
        return Query(self.db, self.name, self.filters + [(field, op, value)])

    def limit(self, _n):
        return self

    def document(self, doc_id):
        return (self.name, str(doc_id))

    def stream(self):
        self.db.queries.append((self.name, tuple(self.filters)))
        for doc_id, data in list(self.db.data.get(self.name, {}).items()):
            if all(_match(data.get(f), op, v) for f, op, v in self.filters):
                yield Snap(doc_id, data)


def _match(actual, op, value):
    if op == "in":
        return actual in value
    if actual is None:
        return False
    try:
        if op == "==":
            return actual == value
        if op == ">=":
            return actual >= value
        if op == "<":
            return actual < value
    except TypeError:
        return False
    raise AssertionError(op)


class FakeDB:
    def __init__(self, data):
        self.data = data
        self.queries = []

    def collection(self, name):
        return Query(self, name)

    def get_all(self, refs):
        for coll, doc_id in refs:
            yield Snap(doc_id, self.data.get(coll, {}).get(doc_id))


def cf(field_id, value):
    return {"id": field_id, "value": value}


def contact(lead="Self Gen", setter="Maecker", sweeper=None, last="Capizzi"):
    fields = [cf(LEAD, lead), cf(SETTER, setter)]
    if sweeper:
        fields.append(cf(SWEEPER, sweeper))
    return {"id": CONTACT, "lastName": last, "customFields": fields}


def opp(**over):
    d = {
        "id": OPP,
        "contactId": CONTACT,
        "pipelineId": BUFFALO,
        "pipelineStageId": "300b27e6-7198-4010-acdd-7e6640efd488",
        "assignedTo": ZACH_ID,
        "createdAt": "2026-05-07T14:41:31.221Z",
        "customFields": [{"id": "6yC1MxhJn9AkVMbAYAUU", "fieldValueString": "Maecker"}],
        "appointmentCycle": 2,
        "appointmentOccurredAt": None,
        "dispositionDate": None,
        "dispositionValue": None,
        "priorCycleDispositionValue": "No Sit",
    }
    d.update(over)
    return d


def log(**over):
    d = {
        "opportunityId": OPP,
        "contactId": CONTACT,
        "pipelineId": BUFFALO,
        "rebookDate": "2026-10-21",
        "effectiveAt": datetime(2026, 10, 21, 16, 0, tzinfo=UTC),
        "rebookedBy": "Zach Maecker",
        "rebookedByUserId": ZACH_ID,
        "rebookSetterLastName": "Maecker",
        "priorStageId": "2cbcc5dc-c5b9-4e55-8de7-f8aedcda7bbd",
        "priorStageName": "DQ'ed",
        "priorOwnerId": ZACH_ID,
        "priorAppointmentOccurredAt": datetime(2026, 5, 21, 22, 0, tzinfo=UTC),
        "priorDispositionValue": "No Sit",
        "priorDispositionDate": datetime(2026, 5, 18, 20, 51, 46, tzinfo=UTC),
        "lastAppointmentBeforeRebookAt": datetime(2026, 5, 21, 22, 0, tzinfo=UTC),
        "daysSinceLastAppointment": 153,
        "cycle": 2,
    }
    d.update(over)
    return d


def october_opp(i, setter="Frazier", owner_id="allen"):
    return {
        "id": f"oct{i}",
        "contactId": f"c{i}",
        "pipelineId": BUFFALO,
        "assignedTo": owner_id,
        "createdAt": f"2026-10-{10 + i:02d}T15:00:00.000Z",
        "customFields": [],
    }


def make_db(*, logs=None, opps=None, contacts=None):
    data = {
        "ghl_pipelines_v2": {BUFFALO: {"id": BUFFALO, "name": "Buffalo"}},
        "roster_people_v1": {
            "z": {"display_name": "Zachary Maecker", "ghl_user_id": ZACH_ID},
            "a": {"display_name": "Allen Frazier", "ghl_user_id": "allen"},
        },
        "ghl_users_v2": {},
        "ghl_opportunities_v2": {OPP: opp()},
        "ghl_contacts_v2": {CONTACT: contact()},
        "ghl_selfgen_rebooks_v1": {f"{OPP}_2026-10-21": log()},
    }
    if logs is not None:
        data["ghl_selfgen_rebooks_v1"] = logs
    for o in opps or []:
        data["ghl_opportunities_v2"][o["id"]] = o
    for c in contacts or []:
        data["ghl_contacts_v2"][c["id"]] = c
    return FakeDB(data)


def october(db, **kw):
    return compute(db, MetricContract(), year=2026, month=10, **kw)


class RebookCreditTests(unittest.TestCase):
    def test_zach_counts_once_in_october_on_rebook_date(self):
        db = make_db(opps=[october_opp(1)], contacts=[{"id": "c1", "customFields": [cf(LEAD, "Self Gen"), cf(SETTER, "Frazier")]}])
        base = october(db, pipeline_scope="all", lead_source="Self Gen")
        out = october(db, pipeline_scope="all", lead_source="Self Gen", include_rebooks=True)
        self.assertEqual(out["result"], base["result"])
        self.assertEqual(out["sample_rows"], base["sample_rows"])
        self.assertEqual(out["breakdowns"]["created_by_setter_last_name"], base["breakdowns"]["created_by_setter_last_name"])
        self.assertNotIn("self_gen_rebooks", base)
        self.assertEqual(out["self_gen_rebooks_count"], 1)
        row = out["self_gen_rebooks"][0]
        self.assertEqual(row["opportunityId"], OPP)
        self.assertEqual(row["contactId"], CONTACT)
        self.assertEqual(row["rebookDate"], "2026-10-21")
        self.assertEqual(row["createdAt"], "2026-10-21T16:00:00Z")
        self.assertEqual(row["owner"], "Zachary Maecker")
        self.assertEqual(row["setterLastName"], "Maecker")
        self.assertEqual(row["leadGenSource"], "Self Gen")
        self.assertEqual(row["pipeline"], "Buffalo")
        self.assertEqual(out["breakdowns"]["self_gen_rebooks_by_setter_last_name"], {"Maecker": 1})
        self.assertEqual(out["breakdowns"]["self_gen_rebooks_by_owner"], {"Zachary Maecker": 1})

    def test_week_window_matches_month(self):
        db = make_db()
        week = october(db, start="2026-10-19", end="2026-10-25", pipeline_scope="all", include_rebooks=True)
        self.assertEqual([r["opportunityId"] for r in week["self_gen_rebooks"]], [OPP])
        before = october(db, start="2026-10-12", end="2026-10-18", pipeline_scope="all", include_rebooks=True)
        self.assertEqual(before["self_gen_rebooks"], [])
        sept = compute(db, MetricContract(), year=2026, month=9, include_rebooks=True)
        self.assertEqual(sept["self_gen_rebooks"], [])

    def test_core_scope_keeps_buffalo(self):
        out = october(make_db(), include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks_count"], 1)

    def test_other_lead_source_filter_gets_no_rebooks(self):
        out = october(make_db(), lead_source="Doors", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"], [])

    def _excluded(self, reason, **kw):
        out = october(make_db(**kw), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"], [], reason)
        self.assertIn(reason, out["debug"]["self_gen_rebooks"]["excluded"], out["debug"]["self_gen_rebooks"])

    def test_sweeper_rehash_name_is_never_a_rebook(self):
        self._excluded("sweeper_rehash_filled", contacts=[contact(sweeper="Diamond")])

    def test_lead_source_must_be_self_gen(self):
        self._excluded("lead_gen_source_not_self_gen", contacts=[contact(lead="Doors")])

    def test_setter_booking_for_someone_else_does_not_count(self):
        # Virtual booking set by Diamond for Zach.
        self._excluded("setter_not_consultant", logs={"x": log(rebookSetterLastName="Diamond")})

    def test_sold_and_sale_cancelled_never_qualify(self):
        self._excluded("prior_stage_sold", logs={"x": log(priorStageName="Sold")})
        self._excluded("prior_stage_sold", logs={"x": log(priorStageName="Sale Cancelled", priorDispositionValue="No Sit")})

    def test_demo_stage_is_not_dead(self):
        self._excluded("prior_stage_not_dead", logs={"x": log(priorStageName="Demo-Negotiating", priorDispositionValue="Sit")})

    def test_under_14_days_does_not_count(self):
        self._excluded("last_appointment_under_14_days", logs={"x": log(daysSinceLastAppointment=13)})

    def test_exactly_14_days_counts(self):
        out = october(make_db(logs={"x": log(daysSinceLastAppointment=14)}), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks_count"], 1)

    def test_other_opp_created_same_month_already_counts(self):
        fresh = {"id": "fresh", "contactId": CONTACT, "pipelineId": BUFFALO, "assignedTo": ZACH_ID,
                 "createdAt": "2026-10-02T15:00:00.000Z", "customFields": []}
        out = october(make_db(opps=[fresh]), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"], [])
        # It counted through createdAt instead.
        self.assertIn("fresh", [r["opportunityId"] for r in out["sample_rows"]])

    def test_one_credit_per_home_per_month(self):
        logs = {
            "a": log(),
            "b": log(rebookDate="2026-10-28", effectiveAt=datetime(2026, 10, 28, 16, tzinfo=UTC)),
        }
        out = october(make_db(logs=logs), pipeline_scope="all", include_rebooks=True)
        self.assertEqual([r["rebookDate"] for r in out["self_gen_rebooks"]], ["2026-10-21"])
        # A week window after the first credit cannot hand out a second one.
        wk = october(make_db(logs=logs), start="2026-10-26", end="2026-11-01", pipeline_scope="all", include_rebooks=True)
        self.assertEqual(wk["self_gen_rebooks"], [])

    def test_credit_follows_rebooked_by_when_owner_did_not_move(self):
        # Opp still owned by Allen (prior owner); Zach rebooked it.
        logs = {"x": log(rebookedByUserId="allen", priorOwnerId="allen")}
        out = october(make_db(logs=logs), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"][0]["owner"], "Zachary Maecker")
        self.assertEqual(out["breakdowns"]["self_gen_rebooks_by_setter_last_name"], {"Maecker": 1})
        self.assertEqual(sr.roster_spelling("Zach Maecker", ["Allen Frazier"]), "Zach Maecker")

    def test_missing_rebooked_by_uses_owner(self):
        out = october(make_db(logs={"x": log(rebookedBy=None)}), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"][0]["owner"], "Zachary Maecker")

    def test_recredit_on_own_old_self_gen_counts(self):
        # Zach's May opp was already his own Self Gen; the October rebook still counts.
        out = october(make_db(), pipeline_scope="all", include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"][0]["owner"], "Zachary Maecker")

    def test_no_logs_is_cheap_and_empty(self):
        db = make_db(logs={})
        out = october(db, include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"], [])
        self.assertFalse([q for q in db.queries if q[0] == "ghl_opportunities_v2" and q[1] and q[1][0][0] == "contactId"])

    def test_query_failure_does_not_break_payload(self):
        db = make_db()
        real = db.collection

        def broken(name):
            if name == "ghl_selfgen_rebooks_v1":
                raise RuntimeError("index missing")
            return real(name)

        db.collection = broken
        out = october(db, include_rebooks=True)
        self.assertEqual(out["self_gen_rebooks"], [])
        self.assertIn("self_gen_rebooks_error", out)


class StageRuleTests(unittest.TestCase):
    def test_approved_dead_stages(self):
        for name in ["DQ'ed", "DQ'd", "DQ\u2019ed", "No Show/Pre-cancelled", "No Show/Pre-Cancel", "Reschedule Needed",
                     "Needs Reschedule", "Needs Rebook", "Cancelled", "No Sit"]:
            self.assertTrue(sr.prior_stage_qualifies(name, None)[0], name)

    def test_no_sit_outcome_on_rescheduled_qualifies(self):
        self.assertTrue(sr.prior_stage_qualifies("Rescheduled", "No Sit")[0])
        self.assertFalse(sr.prior_stage_qualifies("Rescheduled", None)[0])
        self.assertFalse(sr.prior_stage_qualifies("New Appointment", "No Sit")[0])

    def test_never(self):
        for name in ["Sold", "Sale Cancelled", "Sale Canceled", "Demo-Not Interested", "One Legger"]:
            self.assertFalse(sr.prior_stage_qualifies(name, "Sit")[0], name)


class ChannelGoalsTests(unittest.TestCase):
    def test_rebook_adds_to_self_gen_appointments_only(self):
        created = {
            "sample_rows": [
                {"opportunityId": "o1", "contactId": "c1", "leadGenSource": "Self Gen", "setterLastName": "Frazier", "owner": "Allen Frazier"},
            ],
            "self_gen_rebooks": [
                {"opportunityId": OPP, "contactId": CONTACT, "leadGenSource": "Self Gen", "setterLastName": "Maecker", "owner": "Zachary Maecker"},
                {"opportunityId": "dup", "contactId": "c1", "leadGenSource": "Self Gen", "setterLastName": "Frazier", "owner": "Allen Frazier"},
            ],
        }
        out = self_gen_actuals(created, {"rows": []}, {})
        self.assertEqual(out["appointments"], 2)
        self.assertEqual(out["from_rebook"]["appointments"], 1)
        self.assertEqual(out["from_lead_source"]["appointments"], 1)
        self.assertEqual(out["moved_from"], {})

    def test_without_rebooks_unchanged(self):
        out = self_gen_actuals({"sample_rows": []}, {"rows": []}, {})
        self.assertEqual(out["appointments"], 0)
        self.assertEqual(out["from_rebook"]["appointments"], 0)


if __name__ == "__main__":
    unittest.main()
