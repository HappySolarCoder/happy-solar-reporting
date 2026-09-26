# -*- coding: utf-8 -*-

"""Sweeper/Rehash Last Name attribution for self-gen and FMA appointments.

Field id is the warehouse contact custom field documented in
ghl-firestore-sync-v2 extract_sweeper_rehash_last_name:
"Sweeper/Rehash Last Name" HWfjOp8MvE6soxBAL75f.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
API = ROOT / "api"
if str(METRICS) not in sys.path:
    sys.path.insert(0, str(METRICS))

from sweeper_rehash_attribution import (  # noqa: E402
    SWEEPER_REHASH_LAST_NAME_FIELD_ID,
    attributed_last_name,
    is_rehash_lead_source,
    lead_source_matches,
    sweeper_rehash_last_name,
)

FIELD = SWEEPER_REHASH_LAST_NAME_FIELD_ID
CREATED = (METRICS / "opportunities_created.py").read_text(encoding="utf-8")
DEMO = (METRICS / "demo_rate.py").read_text(encoding="utf-8")
SALES = (METRICS / "sales.py").read_text(encoding="utf-8")
SALES_DASH = (API / "sales_dashboard.py").read_text(encoding="utf-8")
FMA_DASH = (API / "fma_dashboard.py").read_text(encoding="utf-8")
RECAP = (API / "rep_daily_recap.py").read_text(encoding="utf-8")


def _contact(sweeper: str | None, *, lead: str | None = None, setter: str | None = "Hill") -> dict:
    fields = []
    if setter is not None:
        fields.append({"id": "Eq4NLTSkJ56KTxbxypuE", "value": setter})
    if lead is not None:
        fields.append({"id": "hd5QqHEOVSsPom5bJ32P", "value": lead})
    if sweeper is not None:
        fields.append({"id": FIELD, "value": sweeper})
    return {"customFields": fields}


def _credit(setter: str, lead: str, sweeper: str, lead_filter: str | None = None):
    """Name the row counts for, or None when the lead-source filter drops it."""
    if not lead_source_matches(lead_filter, lead, sweeper):
        return None
    return attributed_last_name(setter, lead, sweeper)


class SweeperRehashFieldTests(unittest.TestCase):
    def test_field_id_matches_warehouse_sweeper_rehash_last_name(self):
        self.assertEqual(FIELD, "HWfjOp8MvE6soxBAL75f")
        self.assertIn(FIELD, CREATED)
        self.assertIn(FIELD, DEMO)
        self.assertNotIn(FIELD, SALES)
        self.assertNotIn(FIELD, RECAP)

    def test_contact_value_then_opportunity_fallback(self):
        contact = _contact("Calabrese")
        opportunity = {"customFields": [{"id": FIELD, "value": "OppLast"}]}
        self.assertEqual(sweeper_rehash_last_name(contact, opportunity), "Calabrese")
        self.assertEqual(sweeper_rehash_last_name({}, opportunity), "OppLast")
        self.assertEqual(
            sweeper_rehash_last_name(
                {"customFields": [{"id": FIELD, "fieldValueString": "  Smith  "}]},
                None,
            ),
            "Smith",
        )
        self.assertEqual(sweeper_rehash_last_name(None, None), "")
        self.assertEqual(sweeper_rehash_last_name(_contact("none"), {}), "")
        self.assertEqual(sweeper_rehash_last_name(_contact("  "), {}), "")


class AttributionTests(unittest.TestCase):
    def test_rehash_with_sweeper_last_name_counts_for_that_person(self):
        self.assertTrue(is_rehash_lead_source("Rehash"))
        self.assertTrue(is_rehash_lead_source(" REHASH "))
        # Sales-rep self-gen filter and unfiltered FMA appointments.
        self.assertEqual(_credit("Hill", "Rehash", "Calabrese", "Self Gen"), "Calabrese")
        self.assertEqual(_credit("Hill", "rehash", "Calabrese", None), "Calabrese")
        self.assertNotEqual(_credit("Hill", "Rehash", "Calabrese", None), "Hill")

    def test_filled_sweeper_last_name_without_rehash_counts_for_that_person(self):
        self.assertEqual(_credit("Hill", "Doors", "Smith", "Self Gen"), "Smith")
        self.assertEqual(_credit("Hill", "Doors", "Smith", None), "Smith")
        self.assertEqual(_credit("Hill", "Self Gen", "Smith", "Self Gen"), "Smith")
        self.assertEqual(_credit("Hill", "Phones", "  Nguyen ", None), "Nguyen")

    def test_empty_field_and_non_rehash_keeps_setter(self):
        self.assertEqual(_credit("Hill", "Doors", "", None), "Hill")
        self.assertEqual(_credit("Hill", "Self Gen", "", "Self Gen"), "Hill")
        self.assertEqual(_credit("Hill", "Doors", "none", None), "Hill")
        self.assertEqual(_credit("Hill", "Phones", "null", "Self Gen"), None)
        self.assertIsNone(_credit("Hill", "Doors", "", "Self Gen"))
        self.assertIsNone(_credit("Hill", "3PL", "n/a", "Self Gen"))

    def test_true_self_gen_with_empty_field_stays_in_self_gen_on_setter(self):
        self.assertEqual(_credit("Mancini", "Self Gen", "", "Self Gen"), "Mancini")
        self.assertEqual(_credit("Mancini", "self gen", "", "self gen"), "Mancini")
        self.assertIsNone(_credit("Mancini", "self-gen", "", "Self Gen"))

    def test_rehash_with_empty_field_stays_on_setter_and_counts_as_self_gen(self):
        self.assertEqual(_credit("Hill", "Rehash", "", "Self Gen"), "Hill")
        self.assertEqual(_credit("Hill", "Rehash", "", None), "Hill")
        self.assertIsNone(_credit("Hill", "Rehash", "", "Doors"))

    def test_doors_filter_still_includes_a_doors_row_credited_to_sweeper(self):
        self.assertEqual(_credit("Hill", "Doors", "Smith", "Doors"), "Smith")
        self.assertIsNone(_credit("Hill", "Rehash", "Smith", "Doors"))


class DashboardWiringTests(unittest.TestCase):
    def test_created_and_demo_use_the_same_credit_before_setter_counts(self):
        for src, count_call in (
            (CREATED, "add_casefold_count(by_setter"),
            (DEMO, "add_casefold_count(ran_by_setter"),
        ):
            self.assertIn("sweeper_rehash_last_name(", src)
            self.assertIn("credited = attributed_last_name(", src)
            self.assertIn("lead_source_matches(", src)
            self.assertLess(src.index("credited = attributed_last_name("), src.index(count_call))

        self.assertIn("created_by_setter_last_name", CREATED)
        self.assertIn("ran_by_setter_last_name", DEMO)
        self.assertIn("sit_by_setter_last_name", DEMO)
        self.assertIn("lead_source=${encodeURIComponent('Self Gen')}", SALES_DASH)
        self.assertIn("Sweeper/Rehash Last Name", SALES_DASH)
        self.assertIn("created_by_setter_last_name", FMA_DASH)
        self.assertIn("Sweeper/Rehash Last Name", FMA_DASH)

    def test_aug_2026_sales_contract_untouched(self):
        self.assertIn('sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"', SALES)
        self.assertIn("COUNT_DISTINCT(ghl_opportunities_v2.contactId)", SALES)
        self.assertIn('tz = "America/New_York"', SALES)
        self.assertNotIn("sweeper_rehash_attribution", SALES)
        self.assertNotIn("HWfjOp8MvE6soxBAL75f", SALES)

    def test_rep_daily_recap_still_excludes_sweeper_rehash_pipelines(self):
        self.assertIn("SWEEPER_PIPELINE_ID", RECAP)
        self.assertIn("REHASH_PIPELINE_ID", RECAP)
        self.assertIn("excluded_non_territory_appointments", RECAP)
        self.assertNotIn("sweeper_rehash_attribution", RECAP)
        self.assertNotIn("is_recap_appointment_pipeline", CREATED)


if __name__ == "__main__":
    unittest.main()
