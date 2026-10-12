# -*- coding: utf-8 -*-

"""One FMA demo per contact, dated from the disposition and appointment."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

METRICS = Path(__file__).resolve().parents[1] / "api" / "metrics"
if str(METRICS) not in sys.path:
    sys.path.insert(0, str(METRICS))

from fma_demo_credit import (  # noqa: E402
    is_demo_stage,
    make_demo_candidate,
    names_match,
    select_fma_demos,
)

T_DEMO = datetime(2026, 9, 4, 20, 20, tzinfo=timezone.utc)
T_APPT = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)
T_SWEEP = datetime(2026, 9, 13, 12, 13, tzinfo=timezone.utc)
T_RESET = datetime(2026, 9, 25, 16, 11, tzinfo=timezone.utc)
T_RESET_APPT = datetime(2026, 9, 23, 22, 30, tzinfo=timezone.utc)


def _one(**kwargs):
    base = dict(
        contact_id="contact-1",
        opportunity_id="opp-1",
        setter="Hill",
        sweeper="Calabrese",
        pipeline_name="Buffalo",
        stage_name="Demo-Negotiating",
        dispo_at=T_DEMO,
        appointment_times=[T_APPT],
        appointment_source="opportunity_appointment",
        history=[
            {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_DEMO},
        ],
    )
    base.update(kwargs)
    return select_fma_demos([base])


class DemoStageTests(unittest.TestCase):
    def test_demo_stages_are_demo_star_one_legger_or_sold(self):
        for name in ("Demo-Negotiating", "Demo - Not Interested", "DEMO NO SALE", "One Legger", "Sold", "Sold Pending"):
            self.assertTrue(is_demo_stage(name), name)
        for name in ("New Appointment", "No Show", "Rescheduled", "Sale Cancelled", "Sale Canceled", "Negotiating", ""):
            self.assertFalse(is_demo_stage(name), name)

    def test_last_name_match_is_case_insensitive(self):
        self.assertTrue(names_match("Hill", " hill "))
        self.assertTrue(names_match("Calabrese", "CALABRESE"))
        self.assertFalse(names_match("Hill", "Calabrese"))
        self.assertFalse(names_match("Hill", "none"))
        self.assertFalse(names_match("Hill", ""))


class CreditTests(unittest.TestCase):
    def test_blank_sweeper_keeps_the_setter(self):
        for sweeper in ("", "none", "n/a", None):
            demos = _one(sweeper=sweeper, pipeline_name="Sweeper", stage_name="Reset")
            self.assertEqual(len(demos), 1)
            self.assertEqual(demos[0].last_name, "Hill")
            self.assertEqual(demos[0].reason, "original")

    def test_original_city_demo_stays_with_the_fma(self):
        demos = _one(
            pipeline_name="Sweeper",
            stage_name="Reset",
            history=[
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_DEMO},
                {
                    "pipelineName": "Sweeper",
                    "fromStageName": "Demo-Negotiating",
                    "toStageName": "Reset",
                    "effectiveAt": T_SWEEP,
                },
            ],
        )
        self.assertEqual([(d.last_name, d.reason) for d in demos], [("Hill", "original")])

    def test_sweeper_pipeline_without_an_earlier_city_demo_counts_for_the_sweeper(self):
        demos = _one(pipeline_name="Sweeper", stage_name="Demo-Negotiating", history=[], dispo_at=T_RESET)
        self.assertEqual(demos[0].last_name, "Calabrese")
        self.assertEqual(demos[0].reason, "after_sweep")

    def test_city_pipeline_with_no_sweep_timestamp_keeps_the_fma(self):
        demos = _one(history=[], pipeline_name="Buffalo")
        self.assertEqual(demos[0].last_name, "Hill")
        self.assertEqual(demos[0].reason, "original")

    def test_reset_duplicate_does_not_add_a_second_demo(self):
        """Stacy S. shape: original Buffalo sit, then a reset opp that also sits."""
        original = {
            "contact_id": "stacy",
            "opportunity_id": "original",
            "setter": "Dole",
            "sweeper": "Diamond",
            "pipeline_name": "Sweeper",
            "stage_name": "Reset",
            "dispo_at": T_DEMO,
            "appointment_times": [T_APPT, T_RESET_APPT],
            "appointment_source": "opportunity_appointment",
            "history": [
                {"pipelineName": "Buffalo", "toStageName": "New Appointment", "effectiveAt": T_APPT},
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_DEMO},
                {"pipelineName": "Sweeper", "fromStageName": "Demo-Negotiating", "toStageName": "Reset", "effectiveAt": T_SWEEP},
            ],
        }
        duplicate = {
            "contact_id": "stacy",
            "opportunity_id": "reset",
            "setter": "Dole",
            "sweeper": "Diamond",
            "pipeline_name": "Buffalo",
            "stage_name": "Sold",
            "dispo_at": T_RESET,
            "appointment_times": [T_RESET_APPT],
            "appointment_source": "opportunity_appointment",
            "history": [
                {"pipelineName": "Buffalo", "toStageName": "New Appointment", "effectiveAt": T_RESET_APPT},
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_RESET},
                {"pipelineName": "Buffalo", "toStageName": "Sold", "effectiveAt": T_RESET + timedelta(hours=1)},
            ],
        }
        demos = select_fma_demos([duplicate, original])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].opportunity_id, "original")
        self.assertEqual(demos[0].last_name, "Dole")
        self.assertEqual(demos[0].counted_at, T_APPT)
        self.assertEqual(demos[0].date_source, "opportunity_appointment")

    def test_self_sweep_can_add_a_second_demo(self):
        first = {
            "contact_id": "c",
            "opportunity_id": "first",
            "setter": "Hill",
            "sweeper": "Hill",
            "pipeline_name": "Buffalo",
            "dispo_at": T_DEMO,
            "appointment_times": [T_APPT],
            "appointment_source": "opportunity_appointment",
            "history": [
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_DEMO},
                {"pipelineName": "Sweeper", "toStageName": "Reset", "effectiveAt": T_SWEEP},
            ],
        }
        second = {
            "contact_id": "c",
            "opportunity_id": "second",
            "setter": "Hill",
            "sweeper": "Hill",
            "pipeline_name": "Buffalo",
            "dispo_at": T_RESET,
            "appointment_times": [T_RESET_APPT],
            "appointment_source": "appointment_history",
            "history": [
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_RESET},
            ],
        }
        demos = select_fma_demos([first, second])
        self.assertEqual([(d.opportunity_id, d.last_name, d.reason) for d in demos], [
            ("first", "Hill", "original"),
            ("second", "Hill", "self_sweep"),
        ])

    def test_aidan_dates_to_the_reschedule_not_the_no_show(self):
        """Sep 1 occurred-at is outside 3 days of the Sep 8 disposition. Sep 5 start is inside."""
        dispo = datetime(2026, 9, 8, 16, 59, tzinfo=timezone.utc)
        no_show = datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc)
        reschedule = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
        opp = {
            "dispositionDate": dispo,
            "appointmentOccurredAt": no_show,
            "appointmentStartTime": reschedule,
            "lastStageChangeAt": dispo,
        }
        candidate = make_demo_candidate(
            opp,
            contact_id="aidan",
            opportunity_id="aidan-opp",
            setter="Cornell-DeAngelis",
            sweeper="",
            pipeline_name="Syracuse",
            stage_name="Demo-Negotiating",
            history=[
                {"pipelineName": "Syracuse", "toStageName": "New Appointment", "effectiveAt": datetime(2026, 8, 20, tzinfo=timezone.utc)},
                {"pipelineName": "Syracuse", "toStageName": "No Show/Pre-Cancel", "effectiveAt": no_show},
                {"pipelineName": "Syracuse", "toStageName": "Rescheduled", "effectiveAt": datetime(2026, 9, 2, 23, 14, tzinfo=timezone.utc)},
                {"pipelineName": "Syracuse", "toStageName": "Demo-Negotiating", "effectiveAt": dispo},
            ],
            appointment_rows=[],
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].dispo_at, dispo)
        self.assertEqual(demos[0].counted_at, reschedule)
        self.assertEqual(demos[0].date_source, "opportunity_appointment")
        self.assertEqual(demos[0].last_name, "Cornell-DeAngelis")

    def test_appointment_history_beats_the_opportunity_snapshot(self):
        dispo = datetime(2026, 9, 8, 16, 59, tzinfo=timezone.utc)
        history_start = datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc)
        opp = {
            "dispositionDate": dispo,
            "appointmentStartTime": datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc),
        }
        candidate = make_demo_candidate(
            opp,
            contact_id="c",
            opportunity_id="o",
            setter="Hill",
            sweeper="",
            pipeline_name="Syracuse",
            stage_name="Demo-Negotiating",
            history=[{"pipelineName": "Syracuse", "toStageName": "Demo-Negotiating", "effectiveAt": dispo}],
            appointment_rows=[{"contactId": "c", "startTime": history_start, "status": "confirmed"}],
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(demos[0].counted_at, history_start)
        self.assertEqual(demos[0].date_source, "appointment_history")

    def test_cancelled_appointment_history_is_ignored(self):
        dispo = datetime(2026, 9, 8, 16, 59, tzinfo=timezone.utc)
        opp = {"dispositionDate": dispo, "appointmentStartTime": datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)}
        candidate = make_demo_candidate(
            opp,
            contact_id="c",
            opportunity_id="o",
            setter="Hill",
            sweeper="",
            pipeline_name="Buffalo",
            history=[{"toStageName": "Sold", "effectiveAt": dispo, "pipelineName": "Buffalo"}],
            appointment_rows=[{"startTime": datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc), "status": "cancelled"}],
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(demos[0].date_source, "opportunity_appointment")
        self.assertEqual(demos[0].counted_at, opp["appointmentStartTime"])

    def test_no_appointment_inside_three_days_uses_the_dispo(self):
        dispo = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
        old = dispo - timedelta(days=4)
        demos = _one(dispo_at=dispo, appointment_times=[old], history=[
            {"pipelineName": "Buffalo", "toStageName": "One Legger", "effectiveAt": dispo},
        ])
        self.assertEqual(demos[0].counted_at, dispo)
        self.assertEqual(demos[0].date_source, "dispo")

    def test_appointment_after_the_dispo_does_not_move_the_date(self):
        later = T_DEMO + timedelta(days=2)
        demos = _one(appointment_times=[later])
        self.assertEqual(demos[0].counted_at, T_DEMO)
        self.assertEqual(demos[0].date_source, "dispo")


if __name__ == "__main__":
    unittest.main()
