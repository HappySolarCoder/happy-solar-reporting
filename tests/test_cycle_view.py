# -*- coding: utf-8 -*-
"""Reviving an old opp must not move any past-window KPI (Evan, 2026-10-21 5:44 PM AZ).

Regression: compute May / September / October KPIs on a small book, simulate
Zach's in-place revive exactly as the sync writes it (live opp reset to New
Appointment + frozen cycle 1 + rebook log + stage-history row), and compare.
Past windows must be identical; the only new number is the Oct 21 Self Gen
credit. A naive read of the same revived data (no cycle view) is shown to
break May, which is why every historical reader goes through cycle_view.
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cycle_view as cv  # noqa: E402
import demo_rate  # noqa: E402
import opportunities_created as oc  # noqa: E402
import test_selfgen_rebooks as base  # noqa: E402

UTC = timezone.utc
OPP, CONTACT, ZACH, BUFFALO = base.OPP, base.CONTACT, base.ZACH_ID, base.BUFFALO
DQED = "2cbcc5dc-c5b9-4e55-8de7-f8aedcda7bbd"
NEW_APPT = "300b27e6-7198-4010-acdd-7e6640efd488"
SETTER_OPP_CF = "6yC1MxhJn9AkVMbAYAUU"


def other(i, created, *, occurred=None, dispo=None, owner="allen", setter="Frazier", stage=DQED):
    return {
        "id": f"o{i}",
        "contactId": f"c{i}",
        "pipelineId": BUFFALO,
        "pipelineStageId": stage,
        "assignedTo": owner,
        "createdAt": created,
        "customFields": [{"id": SETTER_OPP_CF, "fieldValueString": setter}],
        "appointmentOccurredAt": occurred,
        "dispositionValue": dispo,
        "dispositionDate": occurred,
    }


def zach_before():
    """Zach's opp as prod holds it on Oct 21 before the workflow runs."""
    return {
        "id": OPP,
        "contactId": CONTACT,
        "pipelineId": BUFFALO,
        "pipelineStageId": DQED,
        "pipelineStageUId": DQED,
        "assignedTo": ZACH,
        "createdAt": "2026-05-07T14:41:31.221Z",
        "customFields": [{"id": SETTER_OPP_CF, "fieldValueString": "Maecker"},
                         {"id": "GYGpLKBPfMpiBqyU2ogQ", "fieldValueString": "No Sit"}],
        "dispositionValue": "No Sit",
        "dispositionDate": datetime(2026, 5, 18, 20, 51, 46, tzinfo=UTC),
        "appointmentOccurredAt": datetime(2026, 5, 21, 22, 0, tzinfo=UTC),
        "appointmentStartTime": datetime(2026, 10, 23, 17, 0, tzinfo=UTC),
        "appointmentEventId": "r1xK35rOBuR5CxAQc9Yv",
    }


def contacts():
    out = {CONTACT: base.contact()}
    for i in range(1, 7):
        out[f"c{i}"] = {"id": f"c{i}", "lastName": f"L{i}", "customFields": [base.cf(base.LEAD, "Doors"), base.cf(base.SETTER, "Frazier")]}
    return out


def book():
    opps = {
        OPP: zach_before(),
        "o1": other(1, "2026-09-03T15:00:00.000Z", occurred=datetime(2026, 9, 6, 18, tzinfo=UTC), dispo="Sit", stage="demo-neg"),
        "o2": other(2, "2026-09-12T15:00:00.000Z", occurred=datetime(2026, 9, 15, 18, tzinfo=UTC), dispo="No Sit"),
        "o3": other(3, "2026-10-02T15:00:00.000Z", occurred=datetime(2026, 10, 5, 18, tzinfo=UTC), dispo="Sit", stage="demo-neg"),
        "o4": other(4, "2026-10-09T15:00:00.000Z"),
        "o5": other(5, "2026-05-11T15:00:00.000Z", occurred=datetime(2026, 5, 14, 18, tzinfo=UTC), dispo="No Sit"),
    }
    return {
        "ghl_pipelines_v2": {BUFFALO: {"id": BUFFALO, "name": "Buffalo", "stages": [
            {"id": DQED, "name": "DQ'ed"}, {"id": NEW_APPT, "name": "New Appointment"}, {"id": "demo-neg", "name": "Demo-Negotiating"}]}},
        "roster_people_v1": {
            "z": {"display_name": "Zachary Maecker", "ghl_user_id": ZACH},
            "a": {"display_name": "Allen Frazier", "ghl_user_id": "allen"},
        },
        "ghl_users_v2": {},
        "ghl_opportunities_v2": opps,
        "ghl_contacts_v2": contacts(),
        "ghl_selfgen_rebooks_v1": {},
        "ghl_opportunity_stage_history_v1": {
            "h-may": {"opportunityId": OPP, "toStageId": DQED, "effectiveAt": datetime(2026, 7, 17, 14, 19, tzinfo=UTC)},
        },
    }


def revive(data, *, frozen=True):
    """Apply the sync's writes for Zach's Oct 21 revive (mirrors ghl-firestore-sync-v2 PR #7)."""
    data = copy.deepcopy(data)
    prev = data["ghl_opportunities_v2"][OPP]
    live = dict(prev)
    live.update({
        "pipelineStageId": NEW_APPT, "pipelineStageUId": NEW_APPT,
        "customFields": [{"id": SETTER_OPP_CF, "fieldValueString": "Maecker"}],
        "dispositionValue": None, "dispositionDate": None, "appointmentOccurredAt": None,
        "appointmentCycle": 2, "appointmentCycleStartedOn": "2026-10-21", "selfGenRebookDate": "2026-10-21",
        "priorCycleDispositionValue": "No Sit",
    })
    data["ghl_opportunities_v2"][OPP] = live
    data["ghl_selfgen_rebooks_v1"][f"{OPP}_2026-10-21"] = base.log()
    data["ghl_opportunity_stage_history_v1"]["h-revive"] = {
        "opportunityId": OPP, "fromStageId": DQED, "toStageId": NEW_APPT,
        "effectiveAt": datetime(2026, 10, 21, 22, 25, tzinfo=UTC),
    }
    if frozen:
        snap = dict(prev)
        snap.update({
            "id": f"{OPP}~cycle1", "cycleOf": OPP, "cycleNumber": 1, "cycleEndedOn": "2026-10-21",
            "cycleEndedAt": datetime(2026, 10, 21, 16, tzinfo=UTC),
            "appointmentStartTime": datetime(2026, 5, 21, 22, 0, tzinfo=UTC), "appointmentEventId": None,
        })
        data["ghl_opportunity_cycles_v1"] = {snap["id"]: snap}
    return data


WINDOWS = {"May": (2026, 5), "Sep": (2026, 9), "Oct": (2026, 10)}


def kpis(db, year, month):
    created = oc.compute(db, oc.MetricContract(), year=year, month=month, pipeline_scope="all", include_rebooks=True)
    start, end, _s, _e = demo_rate.month_window(year, month, "America/New_York")
    snaps = demo_rate.load_demo_rate_snaps(db, demo_rate.MetricContract(), start, end)
    ran = sorted(
        (s.to_dict().get("assignedTo"), s.to_dict().get("dispositionValue"), s.to_dict().get("pipelineStageId"))
        for s in snaps
        if (s.to_dict() or {}).get("dispositionValue") in ("Sit", "No Sit")
    )
    history = sorted(
        (s.to_dict().get("opportunityId"), s.to_dict().get("toStageId"))
        for s in db.collection("ghl_opportunity_stage_history_v1").stream()
        if (s.to_dict() or {}).get("effectiveAt") and start <= s.to_dict()["effectiveAt"] < end
    )
    stages = sorted(
        (r.get("pipelineStageId"), r.get("owner") or r.get("assignedTo")) for r in created.get("opps") or created.get("sample_rows") or []
    )
    return {
        "opps_created": created["result"],
        "created_by_owner": created["breakdowns"].get("created_by_owner"),
        "created_by_setter": created["breakdowns"].get("created_by_setter_last_name"),
        "created_by_pipeline": created["breakdowns"].get("created_by_pipeline"),
        "created_stage_owner": stages,
        "ran": len(ran),
        "demos": sum(1 for _o, d, _st in ran if d == "Sit"),
        "no_sits": sum(1 for _o, d, _st in ran if d == "No Sit"),
        "dq_no_sit_ran": sum(1 for _o, d, st in ran if st == DQED and d == "No Sit"),
        "ran_owner_dispo": ran,
        "history_rows": history,
        "self_gen_rebooks": created.get("self_gen_rebooks_count", 0),
    }


class Ref(tuple):
    """(collection, id) like the base fake, plus .get() and .id."""

    def __new__(cls, db, coll, doc_id):
        self = super().__new__(cls, (coll, doc_id))
        self.db, self.id = db, doc_id
        return self

    def get(self):
        return base.Snap(self.id, self.db.data.get(self[0], {}).get(self.id))


class Query(base.Query):
    def where(self, field, op, value):
        return Query(self.db, self.name, self.filters + [(field, op, value)])

    def document(self, doc_id):
        return Ref(self.db, self.name, str(doc_id))


class FakeDB(base.FakeDB):
    def collection(self, name):
        return Query(self, name)


def world(data, wrapped=True):
    db = FakeDB(data)
    return cv.cycle_aware(db) if wrapped else db


class ReviveKeepsPastWindows(unittest.TestCase):
    def setUp(self):
        self.before = {k: kpis(world(book()), *v) for k, v in WINDOWS.items()}
        self.after = {k: kpis(world(revive(book())), *v) for k, v in WINDOWS.items()}

    def test_book_is_meaningful(self):
        self.assertEqual(self.before["May"]["opps_created"], 2)
        self.assertEqual(self.before["May"]["no_sits"], 2)
        self.assertEqual(self.before["May"]["dq_no_sit_ran"], 2)
        self.assertEqual(self.before["Sep"]["ran"], 2)

    def test_may_and_september_identical(self):
        self.assertEqual(self.after["May"], self.before["May"])
        self.assertEqual(self.after["Sep"], self.before["Sep"])

    def test_october_only_adds_the_self_gen_credit(self):
        b, a = dict(self.before["Oct"]), dict(self.after["Oct"])
        self.assertEqual((b.pop("self_gen_rebooks"), a.pop("self_gen_rebooks")), (0, 1))
        # The revive's own stage move is a new October event on the live opp.
        self.assertEqual(sorted(set(a.pop("history_rows")) - set(b.pop("history_rows"))), [(OPP, NEW_APPT)])
        self.assertEqual(a, b)

    def test_naive_in_place_revive_would_break_may(self):
        naive = kpis(world(revive(book(), frozen=False), wrapped=False), 2026, 5)
        self.assertNotEqual(naive, self.before["May"])
        self.assertEqual(naive["no_sits"], self.before["May"]["no_sits"] - 1)  # Zach's May No Sit vanishes

    def test_after_the_new_appointment_sits(self):
        data = revive(book())
        live = data["ghl_opportunities_v2"][OPP]
        live.update({"dispositionValue": "Sit", "appointmentOccurredAt": datetime(2026, 10, 23, 17, tzinfo=UTC),
                     "dispositionDate": datetime(2026, 10, 23, 19, tzinfo=UTC), "pipelineStageId": "demo-neg"})
        may = kpis(world(data), 2026, 5)
        oct_ = kpis(world(data), 2026, 10)
        self.assertEqual(may, self.before["May"])
        self.assertEqual(oct_["demos"], self.before["Oct"]["demos"] + 1)
        self.assertEqual(oct_["opps_created"], self.before["Oct"]["opps_created"])


class CycleViewMechanics(unittest.TestCase):
    def test_no_cycles_is_pass_through(self):
        raw = base.FakeDB(book())
        db = cv.cycle_aware(raw)
        a = [(s.id, s.to_dict()) for s in raw.collection("ghl_opportunities_v2").stream()]
        b = [(s.id, s.to_dict()) for s in db.collection("ghl_opportunities_v2").stream()]
        self.assertEqual(a, b)
        self.assertIs(cv.cycle_aware(db), db)

    def test_created_query_returns_frozen_cycle_not_live(self):
        db = world(revive(book()))
        rows = list(db.collection("ghl_opportunities_v2").where("createdAt", ">=", "2026-05-01").where("createdAt", "<", "2026-06-01").stream())
        ids = sorted(s.id for s in rows)
        self.assertEqual(ids, ["h0HzaCdAJ5iXujzn6RGF~cycle1", "o5"])
        snap = next(s for s in rows if s.id.endswith("~cycle1"))
        self.assertEqual(snap.to_dict()["pipelineStageId"], DQED)

    def test_october_created_query_never_sees_live_revived_opp(self):
        db = world(revive(book()))
        rows = list(db.collection("ghl_opportunities_v2").where("createdAt", ">=", "2026-10-01").stream())
        self.assertNotIn(OPP, [s.id for s in rows])

    def test_document_and_get_all(self):
        db = world(revive(book()))
        live = db.collection("ghl_opportunities_v2").document(OPP).get().to_dict()
        self.assertIsNone(live["createdAt"])
        self.assertEqual(live["cycleOriginalCreatedAt"], "2026-05-07T14:41:31.221Z")
        frozen = db.collection("ghl_opportunities_v2").document(f"{OPP}~cycle1").get().to_dict()
        self.assertEqual(frozen["pipelineStageId"], DQED)
        refs = [db.collection("ghl_opportunities_v2").document(i) for i in (OPP, "o1", f"{OPP}~cycle1")]
        got = {s.id: s.to_dict() for s in db.get_all(refs)}
        self.assertIsNone(got[OPP]["createdAt"])
        self.assertEqual(got["o1"]["createdAt"], "2026-09-03T15:00:00.000Z")
        self.assertEqual(got[f"{OPP}~cycle1"]["dispositionValue"], "No Sit")

    def test_history_rows_before_cycle_end_move_to_frozen_cycle(self):
        db = world(revive(book()))
        rows = {s.id: s.to_dict()["opportunityId"] for s in db.collection("ghl_opportunity_stage_history_v1").stream()}
        self.assertEqual(rows, {"h-may": f"{OPP}~cycle1", "h-revive": OPP})
        by_pseudo = list(db.collection("ghl_opportunity_stage_history_v1").where("opportunityId", "in", [f"{OPP}~cycle1"]).stream())
        self.assertEqual([s.id for s in by_pseudo], ["h-may"])
        by_live = list(db.collection("ghl_opportunity_stage_history_v1").where("opportunityId", "in", [OPP]).stream())
        self.assertEqual([s.id for s in by_live], ["h-revive"])

    def test_other_collections_untouched(self):
        raw = base.FakeDB(book())
        db = cv.cycle_aware(raw)
        self.assertIs(type(db.collection("ghl_contacts_v2")), type(raw.collection("ghl_contacts_v2")))


if __name__ == "__main__":
    unittest.main()
