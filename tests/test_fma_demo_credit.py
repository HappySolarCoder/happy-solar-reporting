# -*- coding: utf-8 -*-

"""FMA demo credit: the original sit stays; a later sweeper demo does not."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

METRICS = Path(__file__).resolve().parents[1] / "api" / "metrics"
if str(METRICS) not in sys.path:
    sys.path.insert(0, str(METRICS))

from fma_demo_credit import (  # noqa: E402
    fma_demo_credit,
    is_demo_stage,
    names_match,
)

T_DEMO = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
T_SWEEP = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)
T_LATER = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)


def _credit(**kwargs):
    return fma_demo_credit("Hill", "Calabrese", **kwargs)


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
            credit = fma_demo_credit("Hill", sweeper, pipeline_name="Sweeper", demo_at=T_LATER)
            self.assertEqual(credit.last_name, "Hill")
            self.assertEqual(credit.reason, "setter")

    def test_matching_last_name_keeps_credit_after_the_sweep(self):
        credit = fma_demo_credit(
            "Hill",
            "hill",
            pipeline_name="Rehash",
            stage_name="Demo-Negotiating",
            demo_at=T_LATER,
            history=[{"pipelineName": "Rehash", "toStageName": "Demo-Negotiating", "effectiveAt": T_LATER}],
        )
        self.assertEqual(credit.last_name, "Hill")
        self.assertEqual(credit.reason, "name_matches")

    def test_original_city_demo_stays_with_the_fma(self):
        history = [
            {"pipelineName": "Buffalo", "toStageName": "Demo-Negotiating", "effectiveAt": T_DEMO},
            {"pipelineName": "Sweeper", "fromStageName": "Demo-Negotiating", "toStageName": "New Appointment", "effectiveAt": T_SWEEP},
        ]
        credit = _credit(
            pipeline_name="Sweeper",
            stage_name="New Appointment",
            demo_at=T_LATER,
            history=history,
        )
        self.assertEqual(credit.last_name, "Hill")
        self.assertEqual(credit.reason, "original_appointment")

    def test_one_legger_and_sold_before_the_sweep_count_for_the_fma(self):
        for stage in ("One Legger", "Sold"):
            credit = _credit(
                pipeline_name="Buffalo",
                history=[{"pipelineName": "Rochester", "toStageName": stage, "effectiveAt": T_DEMO}],
                demo_at=T_LATER,
            )
            self.assertEqual((credit.last_name, credit.reason), ("Hill", "original_appointment"), stage)

    def test_demo_after_the_sweep_counts_for_the_sweeper(self):
        history = [
            {"pipelineName": "Buffalo", "toStageName": "New Appointment", "effectiveAt": T_DEMO},
            {"pipelineName": "Rehash", "fromStageName": "New Appointment", "toStageName": "Demo-Negotiating", "effectiveAt": T_SWEEP},
        ]
        credit = _credit(pipeline_name="Rehash", stage_name="Demo-Negotiating", demo_at=T_LATER, history=history)
        self.assertEqual(credit.last_name, "Calabrese")
        self.assertEqual(credit.reason, "after_sweep")

    def test_sweeper_pipeline_without_an_earlier_city_demo_counts_for_the_sweeper(self):
        credit = _credit(pipeline_name="Sweeper", created_at=T_SWEEP, demo_at=T_LATER)
        self.assertEqual(credit.last_name, "Calabrese")
        self.assertEqual(credit.reason, "after_sweep")

    def test_city_pipeline_with_no_sweep_timestamp_keeps_the_fma(self):
        credit = _credit(
            pipeline_name="Buffalo",
            stage_name="Demo-Negotiating",
            stage_changed_at=T_DEMO,
            demo_at=T_DEMO,
        )
        self.assertEqual(credit.last_name, "Hill")
        self.assertEqual(credit.reason, "original_appointment")

    def test_sit_timestamp_after_a_sweep_without_a_city_demo_moves(self):
        history = [{"pipelineName": "Buffalo", "toStageName": "Rehash", "effectiveAt": T_SWEEP}]
        credit = _credit(pipeline_name="Buffalo", demo_at=T_LATER, history=history)
        self.assertEqual(credit.last_name, "Calabrese")
        self.assertEqual(credit.reason, "after_sweep")

    def test_sit_timestamp_before_the_sweep_stays(self):
        history = [{"pipelineName": "Sweeper", "toStageName": "New Appointment", "effectiveAt": T_LATER}]
        credit = _credit(pipeline_name="Buffalo", demo_at=T_DEMO, history=history)
        self.assertEqual(credit.last_name, "Hill")
        self.assertEqual(credit.reason, "original_appointment")


if __name__ == "__main__":
    unittest.main()
