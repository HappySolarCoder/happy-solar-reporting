# -*- coding: utf-8 -*-

"""Missing Dispositions drops an appointment once any of its opportunities is dispositioned."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from missing_disposition_rule import (
    appointment_is_missing,
    appointment_start_minute,
    is_new_appointment_stage,
    is_post_appointment_stage,
    opportunity_is_dispositioned,
)

MISSING_SRC = (API / "missing_dispos.py").read_text(encoding="utf-8")

# Warehouse lock — Ivan Garcia, appointment 2026-10-03 1:30 PM ET.
# Buffalo opp stayed in New Appointment. The same appointment event was
# dispositioned on the Rehash duplicate (No Sit, then Rehash Attempt 1).
IVAN_CONTACT_ID = "GHH65DvN7rSta9jvsSHV"
IVAN_BUFFALO_OPP_ID = "UaPqvpLqJmSvgolZiZ3C"
IVAN_REHASH_OPP_ID = "hiYh6ePg3gn2WDPfe3Rj"
IVAN_EVENT_ID = "JUFGqdYGBvhmfdcDiyTQ"
IVAN_START = datetime(2026, 10, 3, 17, 30, tzinfo=timezone.utc)


def _opp(**overrides):
    row = {
        "opportunity_id": "opp-new",
        "contact_id": "contact-1",
        "appointment_event_id": "event-1",
        "appointment_start": IVAN_START,
        "stage_name": "New Appointment",
        "pipeline_name": "Buffalo",
        "disposition_value": None,
    }
    row.update(overrides)
    return row


class StageAndOutcomeTests(unittest.TestCase):
    def test_new_appointment_is_not_a_post_appointment_stage(self):
        self.assertTrue(is_new_appointment_stage("New Appointment"))
        self.assertTrue(is_new_appointment_stage("New Appointment "))
        self.assertFalse(is_post_appointment_stage("New Appointment"))
        self.assertFalse(is_post_appointment_stage("new appointment"))
        self.assertFalse(opportunity_is_dispositioned("New Appointment", None))
        self.assertFalse(opportunity_is_dispositioned("New Appointment", ""))
        self.assertFalse(opportunity_is_dispositioned("New Appointment", "none"))

    def test_demo_negotiating_variants_are_post_appointment(self):
        for name in ("Demo-Negotiating", "Demo - Negotiating", "DEMO NEGOTIATING", "Negotiating"):
            self.assertTrue(is_post_appointment_stage(name), name)
            self.assertTrue(opportunity_is_dispositioned(name, None), name)

    def test_other_post_appointment_stages(self):
        for name in (
            "Sold",
            "Sale Cancelled",
            "Sale Canceled",
            "No Show/Pre-cancelled",
            "No Show/Pre-canceled",
            "No Show",
            "Rescheduled",
            "Reschedule Needed",
            "Needs Reschedule",
            "Re-set Appointment",
            "One Legger",
            "DQ'ed",
            "DQ'd",
            "Waiting on Rep Closing Notes",
            "Rehash Attempt 1",
            "Not Interested",
        ):
            self.assertTrue(is_post_appointment_stage(name), name)

    def test_lead_stages_are_not_appointment_dispositions(self):
        for name in ("Call 1", "Appointment Set", "Reconnect to Book", "New Lead", "Auto Text Sent"):
            self.assertFalse(is_post_appointment_stage(name), name)

    def test_appointment_outcome_dispositions_even_in_new_appointment(self):
        self.assertTrue(opportunity_is_dispositioned("New Appointment", "No Sit"))
        self.assertTrue(opportunity_is_dispositioned("New Appointment", "Sit"))


class DuplicateAppointmentTests(unittest.TestCase):
    def test_ivan_rehash_duplicate_drops_off_the_list(self):
        buffalo = _opp(
            opportunity_id=IVAN_BUFFALO_OPP_ID,
            contact_id=IVAN_CONTACT_ID,
            appointment_event_id=IVAN_EVENT_ID,
            appointment_start=IVAN_START,
            stage_name="New Appointment",
            pipeline_name="Buffalo",
            disposition_value=None,
        )
        rehash = _opp(
            opportunity_id=IVAN_REHASH_OPP_ID,
            contact_id=IVAN_CONTACT_ID,
            appointment_event_id=IVAN_EVENT_ID,
            appointment_start=appointment_start_minute("2026-10-03 17:30:00+00:00"),
            stage_name="Rehash Attempt 1",
            pipeline_name="Rehash",
            disposition_value="No Sit",
        )
        self.assertFalse(appointment_is_missing(buffalo, [buffalo, rehash]))

    def test_demo_negotiating_sibling_without_outcome_drops_off(self):
        current = _opp()
        moved = _opp(
            opportunity_id="opp-moved",
            stage_name="Demo - Negotiating",
            disposition_value=None,
        )
        self.assertFalse(appointment_is_missing(current, [moved]))

    def test_same_start_time_rehash_duplicate_without_shared_event_drops_off(self):
        current = _opp(appointment_event_id="event-buffalo")
        rehash = _opp(
            opportunity_id="opp-rehash",
            appointment_event_id="event-rehash",
            stage_name="No Show/Pre-cancelled",
            pipeline_name="Rehash",
            disposition_value=None,
        )
        self.assertFalse(appointment_is_missing(current, [rehash]))

    def test_undispositioned_appointment_stays(self):
        current = _opp(opportunity_id="rokemHGoOF7eTW1OhT1t", contact_id="philip")
        self.assertTrue(appointment_is_missing(current, [current]))

    def test_outcome_on_the_new_appointment_opp_drops_off(self):
        current = _opp(disposition_value="No Sit")
        self.assertFalse(appointment_is_missing(current, []))

    def test_another_appointment_for_the_same_contact_does_not_hide_this_one(self):
        current = _opp()
        other = _opp(
            opportunity_id="opp-other-day",
            appointment_event_id="event-other",
            appointment_start=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
            stage_name="Demo-Negotiating",
            disposition_value="Sit",
        )
        self.assertTrue(appointment_is_missing(current, [other]))

    def test_lead_locker_opp_with_the_same_clock_time_does_not_hide(self):
        current = _opp(appointment_event_id="event-buffalo")
        locker = _opp(
            opportunity_id="opp-locker",
            appointment_event_id="event-locker",
            stage_name="Not Interested",
            pipeline_name="Inbound/Lead Locker",
            disposition_value=None,
        )
        self.assertTrue(appointment_is_missing(current, [locker]))

    def test_page_uses_the_rule_and_says_demo(self):
        self.assertIn("appointment_is_missing", MISSING_SRC)
        self.assertIn("demo negotiating", MISSING_SRC)
        self.assertNotIn("No Sit", MISSING_SRC)
        self.assertNotIn(">Sit<", MISSING_SRC)
