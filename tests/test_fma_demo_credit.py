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
    inferred_appointments,
    is_buffer_dispo_stage,
    is_demo_stage,
    make_demo_candidate,
    map_dispo_appointments,
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
    def test_demo_stages_are_demo_star_or_sold(self):
        for name in ("Demo-Negotiating", "Demo - Not Interested", "DEMO NO SALE", "Sold", "Sold Pending"):
            self.assertTrue(is_demo_stage(name), name)
        for name in (
            "One Legger",
            "one-legger",
            "New Appointment",
            "No Show",
            "Rescheduled",
            "Sale Cancelled",
            "Sale Canceled",
            "Negotiating",
            "",
        ):
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
            {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": dispo},
        ])
        self.assertEqual(demos[0].counted_at, dispo)
        self.assertEqual(demos[0].date_source, "dispo")

    def test_inferred_redispo_dates_the_demo_and_does_not_add_another(self):
        dispo = datetime(2026, 9, 8, 16, 59, tzinfo=timezone.utc)
        inferred = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
        later = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        opp = {
            "dispositionDate": dispo,
            "appointmentStartTime": datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc),
        }
        rows = [
            {"source": "inferred_from_dispo", "startTime": inferred, "dispositionValue": "Sit", "contactId": "c", "opportunityId": "o"},
            {"source": "inferred_from_dispo", "startTime": later, "dispositionValue": "No Sit", "contactId": "c", "opportunityId": "o"},
            {"source": "inferred_from_dispo", "startTime": datetime(2026, 9, 6, tzinfo=timezone.utc), "deleted": True},
        ]
        self.assertEqual(len(inferred_appointments(rows)), 2)
        candidate = make_demo_candidate(
            opp,
            contact_id="c",
            opportunity_id="o",
            setter="Cornell-DeAngelis",
            sweeper="",
            pipeline_name="Syracuse",
            stage_name="Demo-Negotiating",
            history=[{"pipelineName": "Syracuse", "toStageName": "Demo-Negotiating", "effectiveAt": dispo}],
            appointment_rows=rows,
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].counted_at, dispo)
        self.assertEqual(demos[0].date_source, "dispo")
        self.assertEqual(demos[0].last_name, "Cornell-DeAngelis")

    def test_no_sit_then_inferred_sit_is_dated_on_the_estimated_second_appointment(self):
        first = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
        second = datetime(2026, 9, 4, 20, 20, tzinfo=timezone.utc)
        opp = {
            "appointmentOccurredAt": first,
            "appointmentStartTime": first,
            "dispositionDate": second,
            "dispositionValue": "Sit",
        }
        rows = [
            {
                "source": "ghl-firestore-sync-v2",
                "startTime": first,
                "dispositionValue": "No Sit",
                "contactId": "c",
                "opportunityId": "o",
            },
            {
                "source": "inferred_from_dispo",
                "startTime": second,
                "dispositionValue": "Sit",
                "contactId": "c",
                "opportunityId": "o",
            },
        ]
        candidate = make_demo_candidate(
            opp,
            contact_id="c",
            opportunity_id="o",
            setter="Dole",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=[
                {"pipelineName": "Buffalo", "toStageName": "No Sit", "effectiveAt": first + timedelta(days=1), "lastStageChangeAt": first + timedelta(days=1)},
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": second, "lastStageChangeAt": second},
            ],
            appointment_rows=rows,
        )
        self.assertEqual(candidate["inferred_times"], [second])
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].counted_at, second)
        self.assertNotEqual(demos[0].counted_at, first)
        self.assertEqual(demos[0].date_source, "appointment_history")
        self.assertEqual(demos[0].last_name, "Dole")

    def test_late_first_dispo_maps_to_the_real_appointment(self):
        """A first Sit two days after the calendar appointment stays on that appointment."""
        appointment = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        dispo = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
        candidate = make_demo_candidate(
            {"dispositionDate": dispo, "dispositionValue": "Sit", "appointmentStartTime": appointment},
            contact_id="c",
            opportunity_id="o",
            setter="Dole",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=[{
                "pipelineName": "Buffalo",
                "toStageName": "Demo-Negotiating",
                "effectiveAt": dispo,
                "lastStageChangeAt": dispo,
            }],
            appointment_rows=[{
                "source": "ghl-firestore-sync-v2",
                "eventId": "appt-1",
                "startTime": appointment,
                "contactId": "c",
                "opportunityId": "o",
            }],
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].dispo_at, dispo)
        self.assertEqual(demos[0].counted_at, appointment)
        self.assertNotEqual(demos[0].counted_at, dispo)
        self.assertEqual(demos[0].date_source, "appointment_history")

    def test_later_dispo_uses_an_unused_appointment_or_the_estimated_time(self):
        """Monday's appointment is taken by the No Sit. A later Sit does not reuse it."""
        monday = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        no_sit = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
        sit = datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc)
        self.assertLessEqual(sit - monday, timedelta(days=3))

        def candidate(rows, sit_at, history):
            return make_demo_candidate(
                {"dispositionDate": sit_at, "dispositionValue": "Sit", "appointmentStartTime": monday},
                contact_id="c",
                opportunity_id="o",
                setter="Dole",
                sweeper="",
                pipeline_name="Buffalo",
                stage_name="Demo-Negotiating",
                history=history,
                appointment_rows=rows,
            )

        history = [
            {"pipelineName": "Buffalo", "toStageName": "No Sit", "effectiveAt": no_sit, "lastStageChangeAt": no_sit},
            {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": sit, "lastStageChangeAt": sit},
        ]
        only_monday = [{
            "source": "ghl-firestore-sync-v2",
            "eventId": "appt-1",
            "startTime": monday,
            "contactId": "c",
            "opportunityId": "o",
        }]
        estimated = select_fma_demos([candidate(only_monday, sit, history)])
        self.assertEqual(len(estimated), 1)
        self.assertEqual(estimated[0].counted_at, sit)
        self.assertNotEqual(estimated[0].counted_at, monday)
        self.assertEqual(estimated[0].date_source, "dispo")

        later_appointment = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
        later_sit = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
        later_history = [
            {"pipelineName": "Buffalo", "toStageName": "No Sit", "effectiveAt": no_sit, "lastStageChangeAt": no_sit},
            {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": later_sit, "lastStageChangeAt": later_sit},
        ]
        both = only_monday + [{
            "source": "ghl-firestore-sync-v2",
            "eventId": "appt-2",
            "startTime": later_appointment,
            "contactId": "c",
            "opportunityId": "o",
        }]
        unused = select_fma_demos([candidate(both, later_sit, later_history)])
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0].counted_at, later_appointment)
        self.assertNotEqual(unused[0].counted_at, monday)
        self.assertNotEqual(unused[0].counted_at, later_sit)
        self.assertEqual(unused[0].date_source, "appointment_history")

    def test_four_dispos_follow_the_later_rule_and_stay_one_fma_demo(self):
        """The second, third, and fourth dispos use the same later-dispo rule.

        Appointment A on Oct 1 is taken by the first dispo. It is still inside
        the third dispo's 3-day window and is not reused. The second and third
        are estimated at their own times. Appointment B on Oct 6 is free, so
        the fourth uses it. That is still one FMA demo. A second demo counts
        only when Sweeper/Rehash Last Name is that FMA and a later demo is at
        or after the sweep.
        """
        appointment_a = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        no_sit = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        rescheduled = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
        demo = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
        appointment_b = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
        sold = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
        sweep = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        later_appointment = datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc)
        later_demo = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(demo - appointment_a, timedelta(days=3))

        mapped = map_dispo_appointments(
            [no_sit, rescheduled, demo, sold],
            [("appt-a", appointment_a), ("appt-b", appointment_b)],
        )
        self.assertEqual(
            [(item[0], item[1], item[2]) for item in mapped],
            [
                (no_sit, appointment_a, True),
                (rescheduled, rescheduled, False),
                (demo, demo, False),
                (sold, appointment_b, True),
            ],
        )
        self.assertEqual(len({item[1] for item in mapped if item[2]}), 2)

        def city_opp(sweeper):
            return make_demo_candidate(
                {"dispositionDate": sold, "dispositionValue": "Sit", "appointmentStartTime": appointment_b},
                contact_id="contact-4",
                opportunity_id="city",
                setter="Dole",
                sweeper=sweeper,
                pipeline_name="Buffalo",
                stage_name="Sold",
                history=[
                    {"pipelineName": "Buffalo", "toStageName": "No Sit", "effectiveAt": no_sit, "lastStageChangeAt": no_sit},
                    {"pipelineName": "Buffalo", "toStageName": "Rescheduled", "effectiveAt": rescheduled, "lastStageChangeAt": rescheduled},
                    {"pipelineName": "Buffalo", "toStageName": "Demo", "effectiveAt": demo, "lastStageChangeAt": demo},
                    {"pipelineName": "Buffalo", "toStageName": "Sold", "effectiveAt": sold, "lastStageChangeAt": sold},
                    {"pipelineName": "Sweeper", "toStageName": "Reset", "effectiveAt": sweep, "lastStageChangeAt": sweep},
                ],
                appointment_rows=[
                    {"source": "ghl-firestore-sync-v2", "eventId": "appt-a", "startTime": appointment_a, "contactId": "contact-4"},
                    {"source": "ghl-firestore-sync-v2", "eventId": "appt-b", "startTime": appointment_b, "contactId": "contact-4"},
                    {"source": "ghl-firestore-sync-v2", "eventId": "appt-later", "startTime": later_appointment, "contactId": "contact-4"},
                ],
            )

        later_opp = make_demo_candidate(
            {"dispositionDate": later_demo, "dispositionValue": "Sit", "appointmentStartTime": later_appointment},
            contact_id="contact-4",
            opportunity_id="after-sweep",
            setter="Dole",
            sweeper="Diamond",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=[{"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": later_demo, "lastStageChangeAt": later_demo}],
            appointment_rows=[
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-a", "startTime": appointment_a, "contactId": "contact-4"},
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-b", "startTime": appointment_b, "contactId": "contact-4"},
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-later", "startTime": later_appointment, "contactId": "contact-4"},
            ],
        )
        someone_else = select_fma_demos([city_opp("Diamond"), later_opp])
        self.assertEqual(len(someone_else), 1)
        self.assertEqual(someone_else[0].opportunity_id, "city")
        self.assertEqual(someone_else[0].last_name, "Dole")
        self.assertEqual(someone_else[0].reason, "original")
        self.assertEqual(someone_else[0].counted_at, demo)
        self.assertNotEqual(someone_else[0].counted_at, appointment_a)
        self.assertNotEqual(someone_else[0].counted_at, appointment_b)

        own_sweep = make_demo_candidate(
            {"dispositionDate": later_demo, "dispositionValue": "Sit", "appointmentStartTime": later_appointment},
            contact_id="contact-4",
            opportunity_id="after-sweep",
            setter="Dole",
            sweeper="Dole",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=[{"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": later_demo, "lastStageChangeAt": later_demo}],
            appointment_rows=[
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-a", "startTime": appointment_a, "contactId": "contact-4"},
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-b", "startTime": appointment_b, "contactId": "contact-4"},
                {"source": "ghl-firestore-sync-v2", "eventId": "appt-later", "startTime": later_appointment, "contactId": "contact-4"},
            ],
        )
        self_sweep = select_fma_demos([city_opp("Dole"), own_sweep])
        self.assertEqual(
            [(item.opportunity_id, item.last_name, item.reason, item.counted_at) for item in self_sweep],
            [
                ("city", "Dole", "original", demo),
                ("after-sweep", "Dole", "self_sweep", later_appointment),
            ],
        )

    def test_appointment_after_the_dispo_does_not_move_the_date(self):
        later = T_DEMO + timedelta(days=2)
        demos = _one(appointment_times=[later])
        self.assertEqual(demos[0].counted_at, T_DEMO)
        self.assertEqual(demos[0].date_source, "dispo")

    def test_one_legger_stays_in_the_buffer_and_is_not_a_demo(self):
        self.assertTrue(is_buffer_dispo_stage("One Legger", "Buffalo"))
        dispo = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
        appointment = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)
        history = [
            {
                "pipelineName": "Buffalo",
                "toStageName": "One Legger",
                "effectiveAt": dispo,
                "lastStageChangeAt": dispo,
            }
        ]
        candidate = make_demo_candidate(
            {"dispositionDate": dispo, "dispositionValue": "Sit", "appointmentStartTime": appointment},
            contact_id="c",
            opportunity_id="only-one-legger",
            setter="Hill",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="One Legger",
            history=history,
            appointment_rows=[{"eventId": "appt-1", "startTime": appointment, "contactId": "c"}],
        )
        self.assertIsNone(candidate)
        self.assertEqual(
            select_fma_demos(
                [
                    {
                        "contact_id": "c",
                        "opportunity_id": "only-one-legger",
                        "setter": "Hill",
                        "sweeper": "",
                        "pipeline_name": "Buffalo",
                        "stage_name": "One Legger",
                        "dispo_at": dispo,
                        "history": history,
                    }
                ]
            ),
            [],
        )

    def test_one_legger_then_demo_negotiating_credits_the_second_appointment(self):
        first = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)
        one_legger = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
        second = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)
        demo = datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc)
        history = [
            {
                "pipelineName": "Buffalo",
                "toStageName": "One Legger",
                "effectiveAt": one_legger,
                "lastStageChangeAt": one_legger,
            },
            {
                "pipelineName": "Buffalo",
                "toStageName": "Demo-Negotiating",
                "effectiveAt": demo,
                "lastStageChangeAt": demo,
            },
        ]
        rows = [
            {"source": "ghl-firestore-sync-v2", "eventId": "appt-1", "startTime": first, "contactId": "c"},
            {"source": "ghl-firestore-sync-v2", "eventId": "appt-2", "startTime": second, "contactId": "c"},
        ]
        candidate = make_demo_candidate(
            {"dispositionDate": demo, "dispositionValue": "Sit"},
            contact_id="c",
            opportunity_id="second-appointment",
            setter="Hill",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=history,
            appointment_rows=rows,
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].counted_at, second)
        self.assertNotEqual(demos[0].counted_at, first)
        self.assertEqual(demos[0].last_name, "Hill")
        self.assertEqual(demos[0].date_source, "appointment_history")

    def test_sold_after_demo_negotiating_credits_appointment_1(self):
        """Demo-Negotiating on appointment 1, then Sold later, is one demo on appointment 1."""
        appointment_1 = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        demo = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
        appointment_2 = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
        sold = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
        history = [
            {
                "pipelineName": "Buffalo",
                "toStageName": "Demo-Negotiating",
                "effectiveAt": demo,
                "lastStageChangeAt": demo,
            },
            {
                "pipelineName": "Buffalo",
                "toStageName": "Sold",
                "effectiveAt": sold,
                "lastStageChangeAt": sold,
            },
        ]
        rows = [
            {"source": "ghl-firestore-sync-v2", "eventId": "appt-1", "startTime": appointment_1, "contactId": "c"},
            {"source": "ghl-firestore-sync-v2", "eventId": "appt-2", "startTime": appointment_2, "contactId": "c"},
        ]
        candidate = make_demo_candidate(
            {"dispositionDate": sold, "dispositionValue": "Sit"},
            contact_id="c",
            opportunity_id="deal",
            setter="Hill",
            sweeper="Hill",
            pipeline_name="Buffalo",
            stage_name="Sold",
            history=history,
            appointment_rows=rows,
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].counted_at, appointment_1)
        self.assertNotEqual(demos[0].counted_at, appointment_2)
        self.assertNotEqual(demos[0].counted_at, sold)
        self.assertEqual(demos[0].last_name, "Hill")

    def test_later_sold_does_not_add_a_second_demo(self):
        """A Sold opp after a Demo-* attaches to that demo, even when the sweeper is the FMA."""
        appointment_1 = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        demo = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
        sweep = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        sold_appointment = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
        sold = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
        first = make_demo_candidate(
            {"dispositionDate": demo, "dispositionValue": "Sit", "appointmentStartTime": appointment_1},
            contact_id="c",
            opportunity_id="demo",
            setter="Hill",
            sweeper="Hill",
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            history=[
                {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": demo, "lastStageChangeAt": demo},
                {"pipelineName": "Sweeper", "toStageName": "Reset", "effectiveAt": sweep, "lastStageChangeAt": sweep},
            ],
            appointment_rows=[
                {"eventId": "appt-1", "startTime": appointment_1, "contactId": "c"},
                {"eventId": "appt-sold", "startTime": sold_appointment, "contactId": "c"},
            ],
        )
        later = make_demo_candidate(
            {"dispositionDate": sold, "dispositionValue": "Sit", "appointmentStartTime": sold_appointment},
            contact_id="c",
            opportunity_id="sold",
            setter="Hill",
            sweeper="Hill",
            pipeline_name="Buffalo",
            stage_name="Sold",
            history=[
                {"pipelineName": "Buffalo", "toStageName": "Sold", "effectiveAt": sold, "lastStageChangeAt": sold},
            ],
            appointment_rows=[
                {"eventId": "appt-1", "startTime": appointment_1, "contactId": "c"},
                {"eventId": "appt-sold", "startTime": sold_appointment, "contactId": "c"},
            ],
        )
        demos = select_fma_demos([first, later])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].opportunity_id, "demo")
        self.assertEqual(demos[0].counted_at, appointment_1)

    def test_sale_cancelled_with_no_demo_star_counts_once(self):
        appointment = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        cancelled = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)
        candidate = make_demo_candidate(
            {"dispositionDate": cancelled, "dispositionValue": "Sit", "appointmentStartTime": appointment},
            contact_id="c",
            opportunity_id="cancelled",
            setter="Hill",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="Sale Cancelled",
            history=[
                {
                    "pipelineName": "Buffalo",
                    "toStageName": "Sale Cancelled",
                    "effectiveAt": cancelled,
                    "lastStageChangeAt": cancelled,
                }
            ],
            appointment_rows=[{"eventId": "appt-1", "startTime": appointment, "contactId": "c"}],
        )
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].counted_at, appointment)
        self.assertFalse(is_demo_stage("Sale Cancelled"))

    def test_unclassified_sit_still_counts(self):
        candidate = make_demo_candidate(
            {"dispositionDate": T_DEMO, "appointmentStartTime": T_APPT, "dispositionValue": "Sit"},
            contact_id="c",
            opportunity_id="unclassified",
            setter="Hill",
            sweeper="",
            pipeline_name="Buffalo",
            stage_name="",
            history=[],
        )
        self.assertIsNotNone(candidate)
        demos = select_fma_demos([candidate])
        self.assertEqual(len(demos), 1)
        self.assertEqual(demos[0].last_name, "Hill")


if __name__ == "__main__":
    unittest.main()
