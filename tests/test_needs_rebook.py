# -*- coding: utf-8 -*-

"""Needs Rebook stays in the prior No Show or Rescheduled disposition."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from missing_disposition_rule import is_new_appointment_stage
from needs_rebook import (
    interpret_appointment_history,
    is_dispo_stage_move,
    is_needs_rebook_stage,
    is_new_appointment_name,
    keeps_ran_outcome,
    keeps_sit_outcome,
    reporting_stage_name,
    stage_name_is_demo,
    stage_name_is_ran,
    stage_name_is_sit,
)


def _install_google_stubs() -> None:
    google = sys.modules.setdefault("google", MagicMock())
    cloud = sys.modules.setdefault("google.cloud", MagicMock())
    oauth2 = sys.modules.setdefault("google.oauth2", MagicMock())
    sys.modules.setdefault("google.cloud.firestore", MagicMock())
    sys.modules.setdefault("google.oauth2.service_account", MagicMock())
    google.cloud = cloud
    google.oauth2 = oauth2


def load_sc_overview():
    _install_google_stubs()
    spec = importlib.util.spec_from_file_location("sc_overview_needs_rebook", API / "sc_overview.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/sc_overview.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sc_overview_needs_rebook"] = module
    spec.loader.exec_module(module)
    return module


sc_overview = load_sc_overview()


def _history(*names: str) -> list[dict[str, str]]:
    rows = []
    for index, name in enumerate(names, start=1):
        rows.append(
            {
                "toStageName": name,
                "effectiveAt": f"2026-10-{index:02d}T15:00:00Z",
                "changeType": "stage_transition",
            }
        )
    return rows


class NeedsRebookStageTests(unittest.TestCase):
    def test_helper_matches_the_holding_stage_only(self):
        self.assertTrue(is_needs_rebook_stage("Needs Rebook"))
        self.assertTrue(is_needs_rebook_stage(" needs-rebook "))
        self.assertFalse(is_needs_rebook_stage("Needs Reschedule"))
        self.assertFalse(is_needs_rebook_stage("Reschedule Needed"))
        self.assertFalse(is_needs_rebook_stage("No Show"))
        self.assertFalse(is_needs_rebook_stage("New Appointment"))

    def test_it_is_not_a_demo_sit_ran_appointment_or_new_appointment(self):
        self.assertFalse(stage_name_is_demo("Needs Rebook"))
        self.assertTrue(stage_name_is_demo("Demo-Negotiating"))
        self.assertTrue(stage_name_is_demo("One Legger"))
        self.assertFalse(stage_name_is_sit("Needs Rebook"))
        self.assertFalse(stage_name_is_sit("No Show"))
        self.assertFalse(stage_name_is_ran("Needs Rebook"))
        self.assertFalse(stage_name_is_ran("New Appointment"))
        self.assertFalse(is_new_appointment_name("Needs Rebook"))
        self.assertFalse(is_new_appointment_stage("Needs Rebook"))
        self.assertFalse(sc_overview.is_new_appointment_stage("Needs Rebook"))
        self.assertTrue(is_new_appointment_stage("New Appointment"))
        self.assertTrue(sc_overview.is_new_appointment_stage("New Appointment"))

    def test_existing_sit_and_ran_outcomes_are_not_rewritten(self):
        history = _history("No Show", "Needs Rebook")
        self.assertTrue(keeps_sit_outcome("Sit", "Needs Rebook", history))
        self.assertFalse(keeps_sit_outcome("No Sit", "Needs Rebook", history))
        self.assertTrue(keeps_ran_outcome("Sit", "Needs Rebook", history))
        self.assertTrue(keeps_ran_outcome("No Sit", "Needs Rebook", history))
        self.assertTrue(keeps_ran_outcome("Sit", "Demo-Negotiating"))
        self.assertFalse(keeps_ran_outcome("", "Needs Rebook", history))
        self.assertFalse(is_dispo_stage_move("Needs Rebook"))
        self.assertFalse(is_dispo_stage_move("New Appointment"))
        self.assertTrue(is_dispo_stage_move("No Show"))
        self.assertTrue(is_dispo_stage_move("Rescheduled"))

    def test_existing_buckets_are_unchanged_when_the_stage_is_absent(self):
        labels = (
            "Sold",
            "Sale Cancelled",
            "No Show/Pre-cancelled",
            "Rescheduled",
            "Reschedule Needed",
            "Demo-Negotiating",
            "One Legger",
            "New Appointment",
        )
        for label in labels:
            self.assertEqual(
                sc_overview.normalize_completed_outcome_bucket("Rochester", label),
                sc_overview.normalize_completed_outcome_bucket("Rochester", label, None),
            )
            self.assertEqual(
                sc_overview.is_rescheduled_stage(label),
                sc_overview.is_rescheduled_stage(label, None),
            )
        self.assertEqual(sc_overview.normalize_completed_outcome_bucket("Buffalo", "Sold"), "Sold")
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Virtual", "Sale Cancelled"),
            "Sale Cancelled",
        )
        self.assertTrue(sc_overview.is_rescheduled_stage("Rescheduled"))
        self.assertFalse(sc_overview.is_rescheduled_stage("No Show"))
        self.assertEqual(reporting_stage_name("Demo-Negotiating", _history("No Show", "Needs Rebook")), "Demo-Negotiating")


class ReportingWiringTests(unittest.TestCase):
    def test_stage_name_matches_resolve_needs_rebook(self):
        sources = {
            "ads": (METRICS / "ads_dashboard.py").read_text(encoding="utf-8"),
            "overview": (API / "sc_overview.py").read_text(encoding="utf-8"),
            "recap": (API / "rep_daily_recap.py").read_text(encoding="utf-8"),
            "weekly_metric": (METRICS / "fma_weekly_review.py").read_text(encoding="utf-8"),
            "weekly_page": (API / "fma_weekly_review.py").read_text(encoding="utf-8"),
            "scheduling": (METRICS / "scheduling_manager_performance.py").read_text(encoding="utf-8"),
            "outcomes": (API / "appointment_outcomes.py").read_text(encoding="utf-8"),
            "inbound": (METRICS / "inbound_cac.py").read_text(encoding="utf-8"),
            "goose": (API / "copilot" / "prompt.py").read_text(encoding="utf-8"),
        }
        self.assertIn("reporting_stage_name", sources["overview"])
        self.assertIn("apply_reporting_stages", sources["recap"])
        self.assertIn("apply_reporting_stages", sources["weekly_metric"])
        self.assertIn("apply_reporting_stages", sources["outcomes"])
        self.assertIn("reporting_stage_name", sources["scheduling"])
        self.assertIn("reporting_stage_name", sources["inbound"])
        self.assertIn("stage_name_is_demo", sources["ads"])
        self.assertIn("is_needs_rebook_stage(stage_name)", sources["overview"])


class PriorDispositionTests(unittest.TestCase):
    def test_no_show_then_needs_rebook_stays_in_no_show(self):
        history = _history("New Appointment", "No Show", "Needs Rebook")
        self.assertEqual(reporting_stage_name("Needs Rebook", history), "No Show")
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Rochester", "Needs Rebook", history),
            sc_overview.normalize_completed_outcome_bucket("Rochester", "No Show"),
        )
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Virtual", "Needs Rebook", history),
            "No Show",
        )
        self.assertFalse(sc_overview.is_rescheduled_stage("Needs Rebook", history))

        pre_cancel = _history("No Show/Pre-cancelled", "Needs Rebook")
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Self Gen", "Needs Rebook", pre_cancel),
            "No Show/Pre-cancelled",
        )

    def test_rescheduled_then_needs_rebook_still_counts_as_a_reschedule(self):
        history = _history("New Appointment", "Rescheduled", "Needs Rebook")
        self.assertEqual(reporting_stage_name("Needs Rebook", history), "Rescheduled")
        self.assertTrue(sc_overview.is_rescheduled_stage("Needs Rebook", history))
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Rochester", "Needs Rebook", history),
            "Rescheduled",
        )
        needed = _history("Reschedule Needed", "Needs Rebook")
        self.assertTrue(sc_overview.is_rescheduled_stage("Needs Rebook", needed))
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Rehash", "Needs Rebook", needed),
            "Reschedule Needed",
        )

    def test_needs_rebook_then_new_appointment_then_demo_credits_the_new_appointment(self):
        history = _history("No Show", "Needs Rebook", "New Appointment", "Demo-Negotiating")
        interpreted = interpret_appointment_history(history)
        self.assertEqual(interpreted["dispositions"], ["No Show", "Demo-Negotiating"])
        self.assertEqual(interpreted["needs_rebook_moves"], 1)
        self.assertEqual(interpreted["dispo_slots_taken_by_needs_rebook"], 0)
        self.assertEqual(interpreted["inferred_appointments"], [])
        original, new_appointment = interpreted["appointments"]
        self.assertEqual(original["disposition"], "No Show")
        self.assertFalse(original["demo_credit"])
        self.assertFalse(original["inferred"])
        self.assertEqual(new_appointment["disposition"], "Demo-Negotiating")
        self.assertTrue(new_appointment["demo_credit"])
        self.assertFalse(new_appointment["inferred"])
        self.assertEqual(new_appointment["source"], "stage_history")

    def test_history_keeps_the_original_dispo(self):
        history = _history("Rescheduled", "Needs Rebook", "Needs Rebook")
        interpreted = interpret_appointment_history(history)
        self.assertEqual(interpreted["dispositions"], ["Rescheduled"])
        self.assertEqual(interpreted["appointments"][0]["disposition"], "Rescheduled")
        self.assertEqual(interpreted["needs_rebook_moves"], 2)
        self.assertEqual(interpreted["dispo_slots_taken_by_needs_rebook"], 0)
        self.assertEqual(interpreted["inferred_appointments"], [])
        self.assertEqual(reporting_stage_name("Needs Rebook", history), "Rescheduled")
        self.assertFalse(stage_name_is_demo("Needs Rebook"))


if __name__ == "__main__":
    unittest.main()
