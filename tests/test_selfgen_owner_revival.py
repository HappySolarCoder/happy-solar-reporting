# -*- coding: utf-8 -*-
"""Owner revival Self Gen credit (Evan, 2026-10-30).

Locked case: Rueben Hand revived his own old opp gF5OLCLjhDNuEn0cZn0i on
2026-10-28 2:32 PM ET (Inbound/Lead Locker "Appointment Set" -> Buffalo "New
Appointment", owner unchanged), booked from the opp page on his own Self Gen
calendar, so the Booking Hub wrote no rebook log. The contact is LGS 3PL, setter
Calabrese, Sweeper/Rehash blank. It must count once as a Self Gen opp for Rueben
in October and change nothing else.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from test_selfgen_rebooks import BUFFALO, LEAD, SETTER, SWEEPER, FakeDB, cf, log as hub_log, october  # noqa: E402

import selfgen_rebooks as sr  # noqa: E402
from channel_goals import self_gen_actuals  # noqa: E402

UTC = timezone.utc
RUEBEN = "f4udrh1LuU0TEkF4ZFSj"
ZACH = "nFf2FIr40kvWRCVaMej2"
OPP = "gF5OLCLjhDNuEn0cZn0i"
CID = "jb_contact"
INBOUND = "7nSEgeoBYXZiIS7x41Jy"
SWEEPER_PIPE = "0VNxqmhbk7FDO64j2pKu"
APPT_SET = "5757cdbf-d675-457f-8435-5a7cec008f13"
NEW_APPT = "300b27e6-7198-4010-acdd-7e6640efd488"
DQED = "2cbcc5dc-c5b9-4e55-8de7-f8aedcda7bbd"
RESCHEDULED = "resched-buffalo"
SWEEP_STAGE = "sweep-stage"
REVIVED_AT = datetime(2026, 10, 28, 18, 32, tzinfo=UTC)  # 2:32 PM ET


def contact(sweeper=None):
    fields = [cf(LEAD, "3PL"), cf(SETTER, "Calabrese")]
    if sweeper:
        fields.append(cf(SWEEPER, sweeper))
    return {"id": CID, "lastName": "B", "customFields": fields}


def opp(**over):
    d = {
        "id": OPP,
        "contactId": CID,
        "pipelineId": BUFFALO,
        "pipelineStageId": NEW_APPT,
        "assignedTo": RUEBEN,
        "createdAt": "2026-06-01T15:00:00.000Z",
        "appointmentOccurredAt": "2026-11-13T15:00:00.000Z",
        "customFields": [],
    }
    d.update(over)
    return d


def move(**over):
    d = {
        "changeType": "stage_transition",
        "opportunityId": OPP,
        "contactId": CID,
        "pipelineId": BUFFALO,
        "pipelineName": "Buffalo",
        "fromStageId": APPT_SET,
        "fromStageName": "Appointment Set",
        "toStageId": NEW_APPT,
        "toStageName": "New Appointment",
        "fromAssignedTo": RUEBEN,
        "toAssignedTo": RUEBEN,
        "effectiveAt": REVIVED_AT,
    }
    d.update(over)
    return d


def make_db(*, moves=None, opps=None, contacts=None, logs=None):
    data = {
        "ghl_pipelines_v2": {
            BUFFALO: {"id": BUFFALO, "name": "Buffalo", "stages": [
                {"id": NEW_APPT, "name": "New Appointment"}, {"id": DQED, "name": "DQ'ed"},
                {"id": RESCHEDULED, "name": "Rescheduled"}]},
            INBOUND: {"id": INBOUND, "name": "Inbound/Lead Locker", "stages": [{"id": APPT_SET, "name": "Appointment Set"}]},
            SWEEPER_PIPE: {"id": SWEEPER_PIPE, "name": "Sweeper", "stages": [{"id": SWEEP_STAGE, "name": "Needs Rebook"}]},
        },
        "roster_people_v1": {
            "r": {"display_name": "Rueben Hand", "ghl_user_id": RUEBEN},
            "z": {"display_name": "Zachary Maecker", "ghl_user_id": ZACH},
        },
        "ghl_users_v2": {},
        "ghl_opportunities_v2": {OPP: opp()},
        "ghl_contacts_v2": {CID: contact()},
        "ghl_selfgen_rebooks_v1": logs or {},
        "ghl_opportunity_stage_history_v1": {"h1": move()} if moves is None else moves,
    }
    for o in opps or []:
        data["ghl_opportunities_v2"][o["id"]] = o
    for c in contacts or []:
        data["ghl_contacts_v2"][c["id"]] = c
    return FakeDB(data)


def run(db, **kw):
    kw.setdefault("pipeline_scope", "all")
    return october(db, include_rebooks=True, **kw)


class OwnerRevivalTests(unittest.TestCase):
    def setUp(self):
        sr._REVIVAL_CACHE.clear()

    def test_rueben_counts_once_as_his_self_gen(self):
        db = make_db()
        base = october(db, pipeline_scope="all")
        out = run(db)
        self.assertEqual(out["result"], base["result"])
        self.assertEqual(out["sample_rows"], base["sample_rows"])
        self.assertEqual(out["self_gen_rebooks_count"], 1)
        row = out["self_gen_rebooks"][0]
        self.assertEqual((row["opportunityId"], row["owner"], row["setterLastName"]), (OPP, "Rueben Hand", "Hand"))
        self.assertEqual((row["leadGenSource"], row["sweeperRehashLastName"]), ("Self Gen", None))
        self.assertEqual((row["rebookDate"], row["rebookSource"], row["pipeline"]), ("2026-10-28", "owner_revival", "Buffalo"))
        self.assertEqual(out["breakdowns"]["self_gen_rebooks_by_setter_last_name"], {"Hand": 1})
        self.assertEqual(out["breakdowns"]["self_gen_rebooks_by_owner"], {"Rueben Hand": 1})

    def test_self_gen_filter_and_week_window(self):
        db = make_db()
        self.assertEqual(run(db, lead_source="Self Gen")["self_gen_rebooks_count"], 1)
        self.assertEqual(run(db, start="2026-10-26", end="2026-11-01")["self_gen_rebooks_count"], 1)
        self.assertEqual(run(db, start="2026-10-19", end="2026-10-25")["self_gen_rebooks"], [])

    def test_3pl_filter_gets_nothing(self):
        self.assertEqual(run(make_db(), lead_source="3PL")["self_gen_rebooks"], [])

    def test_channel_goals_adds_one_appointment_only(self):
        out = self_gen_actuals(run(make_db()), {"rows": []}, {})
        self.assertEqual(out["from_rebook"], {"appointments": 1, "ran": 0, "demos": 0, "sales": 0})
        self.assertEqual(out["moved_from"], {})

    def _excluded(self, reason, **kw):
        out = run(make_db(**kw))
        self.assertEqual(out["self_gen_rebooks"], [], reason)
        self.assertIn(reason, out["debug"]["self_gen_rebooks"]["excluded"], out["debug"]["self_gen_rebooks"])

    def test_filled_sweeper_name_stays_sweeper_rehash(self):
        self._excluded("sweeper_rehash_filled", contacts=[contact(sweeper="Diamond")])
        self._excluded("sweeper_rehash_filled", opps=[opp(customFields=[cf(SWEEPER, "Diamond")])])

    def test_sweeper_pipeline_prior_stage_never_counts(self):
        self._excluded("prior_sweeper_pipeline", moves={"h": move(fromStageId=SWEEP_STAGE, fromStageName="Needs Rebook")})

    def test_owner_change_does_not_count(self):
        self._excluded("revival_owner_changed", moves={"h": move(fromAssignedTo=ZACH)})
        self._excluded("revival_owner_missing", moves={"h": move(toAssignedTo="")})

    def test_rescheduled_prior_stage_is_not_a_revival(self):
        self._excluded("prior_stage_not_dead", moves={"h": move(fromStageId=RESCHEDULED, fromStageName="Rescheduled")})

    def test_under_14_days_does_not_count(self):
        self._excluded("last_appointment_under_14_days", opps=[opp(appointmentOccurredAt="2026-10-20T15:00:00.000Z")])

    def test_opp_created_same_month_counts_through_created_at(self):
        self._excluded("revival_opportunity_created_this_month", opps=[opp(createdAt="2026-10-02T15:00:00.000Z")])

    def test_hub_log_decides_its_own_opp(self):
        # A Booking Hub log exists and fails (contact LGS 3PL): the revival must not rescue it.
        logs = {"x": hub_log(opportunityId=OPP, contactId=CID, rebookDate="2026-10-28",
                             rebookedBy="Rueben Hand", rebookedByUserId=RUEBEN, rebookSetterLastName="Hand")}
        out = run(make_db(logs=logs))
        self.assertEqual(out["self_gen_rebooks"], [])
        self.assertEqual(out["debug"]["self_gen_rebooks"]["excluded"], {"lead_gen_source_not_self_gen": 1})
        # Same under the cycle view, which re-keys history rows to '<id>~cycle<n>'.
        moves = {"h": move(opportunityId=f"{OPP}~cycle2", cycleOf=OPP)}
        self.assertEqual(run(make_db(logs=logs, moves=moves))["self_gen_rebooks"], [])
        self.assertEqual(sr.base_opportunity_id(f"{OPP}~cycle2"), OPP)

    def test_snapshots_and_other_targets_are_ignored(self):
        moves = {"a": move(changeType="initial_snapshot"), "b": move(toStageName="Rescheduled", toStageId=RESCHEDULED)}
        out = run(make_db(moves=moves))
        self.assertEqual(out["self_gen_rebooks"], [])
        self.assertEqual(out["debug"]["self_gen_rebooks"]["logs_scanned"], 0)

    def test_dqed_prior_counts_and_later_appointment_keeps_credit(self):
        moves = {"h": move(fromStageId=DQED, fromStageName="DQ'ed", pipelineId=BUFFALO)}
        o = opp(appointmentOccurredAt="2026-11-20T15:00:00.000Z")
        self.assertEqual(run(make_db(moves=moves, opps=[o]))["self_gen_rebooks_count"], 1)

    def test_ordinary_reschedules_cost_no_contact_queries(self):
        moves = {f"r{i}": move(opportunityId=f"o{i}", fromStageId=RESCHEDULED, fromStageName="Rescheduled") for i in range(5)}
        db = make_db(moves=moves)
        run(db)
        self.assertFalse([q for q in db.queries if q[0] == "ghl_opportunities_v2" and q[1] and q[1][0][0] == "contactId"])

    def test_stage_history_read_once_per_window(self):
        db = make_db()
        run(db)
        run(db, lead_source="Self Gen")
        self.assertEqual(len([q for q in db.queries if q[0] == "ghl_opportunity_stage_history_v1"]), 1)


if __name__ == "__main__":
    unittest.main()
