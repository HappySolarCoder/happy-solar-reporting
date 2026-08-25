# -*- coding: utf-8 -*-

"""FMA Demo Rate — Sit / Ran with first-write-wins sit timestamp."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
DEMO_SRC = (METRICS / "demo_rate.py").read_text()
INBOUND_SRC = (METRICS / "inbound_cac.py").read_text()
FMA_SRC = (ROOT / "api" / "fma_dashboard.py").read_text()

import sys

sys.path.insert(0, str(METRICS))
from sit_timestamp import as_aware_utc, frozen_sit_timestamp

NY = ZoneInfo("America/New_York")

# Evan 2026-08-25 live warehouse (do not invent another example).
JOANNE_OPP_ID = "OF48x1PrhxehlJS3ReMc"
JOANNE_CONTACT_ID = "vPLhdbmd9ggy9d0i0GTY"
# Live /api/qa/ghl_opps_ran_setter_table and appointment_outcomes:
# appointmentOccurredAt = 2026-08-26T18:00:00Z = Aug 26, 2026 2:00 PM ET
JOANNE_OCCURRED_AT = datetime(2026, 8, 26, 18, 0, 0, tzinfo=timezone.utc)
# First Sit/No Sit write is the same-day stage mark (Aug 20), not the follow-up.
JOANNE_DISPOSITION_DATE = datetime(2026, 8, 20, 16, 0, 0, tzinfo=NY)


class SitTimestampFreezeTests(unittest.TestCase):
    def test_joanne_follow_up_does_not_move_sit_off_aug_20(self):
        frozen = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        self.assertIsNotNone(frozen)
        self.assertEqual(frozen.astimezone(NY).date().isoformat(), "2026-08-20")
        self.assertNotEqual(frozen.astimezone(NY).date().isoformat(), "2026-08-26")

    def test_first_write_wins_when_occurred_is_already_the_original_slot(self):
        occurred = datetime(2026, 8, 20, 17, 0, 0, tzinfo=NY)
        marked = datetime(2026, 8, 20, 18, 30, 0, tzinfo=NY)
        frozen = frozen_sit_timestamp(occurred, marked)
        self.assertEqual(frozen, occurred.astimezone(timezone.utc))

    def test_missing_disposition_date_falls_back_to_occurred(self):
        frozen = frozen_sit_timestamp(JOANNE_OCCURRED_AT, None)
        self.assertEqual(frozen, JOANNE_OCCURRED_AT)

    def test_missing_occurred_falls_back_to_disposition_date(self):
        frozen = frozen_sit_timestamp(None, JOANNE_DISPOSITION_DATE)
        self.assertEqual(frozen, JOANNE_DISPOSITION_DATE.astimezone(timezone.utc))

    def test_follow_up_is_not_a_second_sit(self):
        first = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        again = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        self.assertEqual(first, again)

    def test_iso_strings_parse(self):
        frozen = frozen_sit_timestamp(
            "2026-08-26T18:00:00+00:00",
            "2026-08-20T16:00:00-04:00",
        )
        self.assertEqual(frozen.astimezone(NY).date().isoformat(), "2026-08-20")

    def test_as_aware_utc_none(self):
        self.assertIsNone(as_aware_utc(None))
        self.assertIsNone(as_aware_utc(""))


class DemoRateContractTests(unittest.TestCase):
    def test_live_fma_formula_stays_sit_over_ran(self):
        self.assertIn('Opps Ran / Demos / Demo % (Sit / Ran)', FMA_SRC)
        self.assertIn("sit_by_setter_last_name", FMA_SRC)
        self.assertIn("/api/metrics/demo_rate", FMA_SRC)
        self.assertNotIn("Sit / (Sit + No Sit)", DEMO_SRC)
        self.assertIn('if dispo == "Sit":', DEMO_SRC)
        self.assertIn("sit / ran", DEMO_SRC)

    def test_uses_existing_dispo_contract_not_a_new_field(self):
        self.assertIn("GYGpLKBPfMpiBqyU2ogQ", DEMO_SRC)
        self.assertIn('appointment_occurred_at_field: str = "appointmentOccurredAt"', DEMO_SRC)
        self.assertIn('disposition_date_field: str = "dispositionDate"', DEMO_SRC)
        self.assertIn('disposition_value_field: str = "dispositionValue"', DEMO_SRC)
        self.assertIn("frozen_sit_timestamp", DEMO_SRC)
        self.assertIn("load_demo_rate_snaps", DEMO_SRC)

    def test_does_not_full_stream_opps(self):
        self.assertNotIn('db.collection(c.opp_collection).stream()', DEMO_SRC)
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', DEMO_SRC)
        self.assertIn(".where(c.appointment_occurred_at_field, \">=\", start_utc)", DEMO_SRC)
        self.assertIn(".where(c.disposition_date_field, \">=\", start_utc)", DEMO_SRC)

    def test_does_not_change_inbound_cac_sit_query(self):
        self.assertIn('APPOINTMENT_OCCURRED_AT_FIELD = "appointmentOccurredAt"', INBOUND_SRC)
        self.assertNotIn("frozen_sit_timestamp", INBOUND_SRC)
        self.assertNotIn("dispositionDate", INBOUND_SRC)
        self.assertIn("Bounded appointmentOccurredAt range; Sit only", INBOUND_SRC)

    def test_sale_contract_untouched(self):
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", DEMO_SRC)

    def test_joanne_case_is_named_in_metric(self):
        self.assertIn(JOANNE_OPP_ID, DEMO_SRC)
        self.assertIn("Joanne Miechowski", DEMO_SRC)


if __name__ == "__main__":
    unittest.main()
