# -*- coding: utf-8 -*-

"""Sweeper/Rehash Last Name attribution for self-gen and FMA appointments.

Confirmed contact custom field from the Happy Solar stack
(ghl-firestore-sync-v2 Discord alerts / extract_sweeper_rehash_last_name):
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

from datetime import date, datetime, timezone  # noqa: E402
from unittest.mock import patch  # noqa: E402

from sweeper_rehash_attribution import (  # noqa: E402
    SWEEPER_ATTRIBUTION_START,
    SWEEPER_REHASH_LAST_NAME_FIELD_ID,
    appointment_business_date,
    attributed_last_name,
    is_rehash_lead_source,
    lead_source_matches,
    sweeper_attribution_in_effect,
    sweeper_rehash_last_name,
)

FIELD = SWEEPER_REHASH_LAST_NAME_FIELD_ID
CREATED = (METRICS / "opportunities_created.py").read_text(encoding="utf-8")
DEMO = (METRICS / "demo_rate.py").read_text(encoding="utf-8")
SALES = (METRICS / "sales.py").read_text(encoding="utf-8")
SALES_DASH = (API / "sales_dashboard.py").read_text(encoding="utf-8")
FMA_DASH = (API / "fma_dashboard.py").read_text(encoding="utf-8")
RECAP = (API / "rep_daily_recap.py").read_text(encoding="utf-8")
COMMISSIONS = (API / "fma_commissions.py").read_text(encoding="utf-8")
INCENTIVE = (API / "scottsdale_incentive.py").read_text(encoding="utf-8")
PAYROLL = (API / "private" / "fma_payroll.py").read_text(encoding="utf-8")
PAYROLL_LOGIC = (API / "private" / "fma_payroll_logic.py").read_text(encoding="utf-8")

# Existing credit examples describe the rule once the pay week has started.
POST_CUTOFF = SWEEPER_ATTRIBUTION_START
PRE_CUTOFF = date(2026, 9, 23)
AUGUST = date(2026, 8, 15)


def _contact(sweeper: str | None, *, lead: str | None = None, setter: str | None = "Hill") -> dict:
    fields = []
    if setter is not None:
        fields.append({"id": "Eq4NLTSkJ56KTxbxypuE", "value": setter})
    if lead is not None:
        fields.append({"id": "hd5QqHEOVSsPom5bJ32P", "value": lead})
    if sweeper is not None:
        fields.append({"id": FIELD, "value": sweeper})
    return {"customFields": fields}


def _credit(
    setter: str,
    lead: str,
    sweeper: str,
    lead_filter: str | None = None,
    when=POST_CUTOFF,
):
    """Name the row counts for, or None when the lead-source filter drops it."""
    if not lead_source_matches(lead_filter, lead, sweeper, when):
        return None
    return attributed_last_name(setter, lead, sweeper, when)


class SweeperRehashFieldTests(unittest.TestCase):
    def test_cutoff_is_the_thursday_payroll_week(self):
        self.assertEqual(SWEEPER_ATTRIBUTION_START, date(2026, 9, 24))
        self.assertEqual(SWEEPER_ATTRIBUTION_START.strftime("%A"), "Thursday")
        self.assertTrue(sweeper_attribution_in_effect(POST_CUTOFF))
        self.assertTrue(sweeper_attribution_in_effect(date(2026, 9, 26)))
        self.assertFalse(sweeper_attribution_in_effect(PRE_CUTOFF))
        self.assertFalse(sweeper_attribution_in_effect(AUGUST))
        self.assertFalse(sweeper_attribution_in_effect(None))
        # 2026-09-24 03:30 UTC is still Wednesday evening in ET, same as payroll.
        before = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)
        on_cutoff = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(appointment_business_date(before), PRE_CUTOFF)
        self.assertEqual(appointment_business_date(on_cutoff), POST_CUTOFF)
        self.assertFalse(sweeper_attribution_in_effect(before))
        self.assertTrue(sweeper_attribution_in_effect(on_cutoff))

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

    def test_before_cutoff_flagged_contact_stays_with_setter(self):
        for when in (PRE_CUTOFF, AUGUST, date(2026, 9, 14), date(2026, 9, 20)):
            self.assertEqual(_credit("Hill", "Rehash", "Calabrese", "Self Gen", when), None)
            self.assertEqual(_credit("Hill", "Rehash", "Calabrese", None, when), "Hill")
            self.assertEqual(_credit("Hill", "Doors", "Smith", None, when), "Hill")
            self.assertEqual(_credit("Hill", "Doors", "Smith", "Self Gen", when), None)
            self.assertEqual(_credit("Hill", "Doors", "Smith", "Doors", when), "Hill")
            self.assertEqual(_credit("Mancini", "Self Gen", "", "Self Gen", when), "Mancini")


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

    def test_pay_pages_read_the_same_demo_breakdown(self):
        for src in (COMMISSIONS, INCENTIVE):
            self.assertIn("sit_by_setter_last_name", src)
            self.assertIn("2026-09-24", src)
            self.assertNotIn("attributed_last_name", src)
        self.assertIn("attributed_last_name(setter, lead, sweeper_last, local_dt.date())", PAYROLL)
        self.assertIn("scheduling_manager", PAYROLL_LOGIC)
        self.assertIn("HWfjOp8MvE6soxBAL75f", PAYROLL_LOGIC)
        self.assertNotIn("sweeper_rehash", PAYROLL_LOGIC.split("scheduling_manager")[1])


class _Snap:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def where(self, *args, **kwargs):
        return self

    def stream(self):
        return list(self._rows)


class _Db:
    def __init__(self, rows):
        self._rows = rows

    def collection(self, name):
        return _Query(self._rows)


def _sit_stamp(day: date) -> datetime:
    """3:00pm ET on ``day`` (EDT, UTC-4), safely in the past relative to 2026-09-26."""
    return datetime(day.year, day.month, day.day, 19, 0, tzinfo=timezone.utc)


def _flagged_records(day: date, *, sweeper: str | None, lead: str = "Doors"):
    contact = _contact(sweeper, lead=lead, setter="Hill")
    contact["id"] = "contact-1"
    opp = {
        "id": "opp-1",
        "contactId": "contact-1",
        "pipelineId": "pipe-buffalo",
        "dispositionValue": "Sit",
        "appointmentOccurredAt": _sit_stamp(day),
        "dispositionDate": _sit_stamp(day),
        "createdAt": _sit_stamp(day).isoformat().replace("+00:00", "Z"),
        "customFields": [
            {"id": "Eq4NLTSkJ56KTxbxypuE", "value": "Hill"},
        ],
    }
    return contact, opp


class SurfaceCreditTests(unittest.TestCase):
    """Dashboard, commissions, Scottsdale incentive, and payroll share one fixture."""

    def setUp(self):
        private = str(API / "private")
        if private not in sys.path:
            sys.path.insert(0, private)
        import demo_rate
        import fma_payroll
        import opportunities_created

        self.demo_rate = demo_rate
        self.payroll = fma_payroll
        self.created = opportunities_created

    def _run(self, day: date, *, sweeper: str | None, lead: str = "Doors", lead_filter: str | None = None):
        contact, opp = _flagged_records(day, sweeper=sweeper, lead=lead)
        snap = _Snap("opp-1", opp)
        filters = {"pipeline": None, "setter": None, "lead_source": lead_filter}
        start = day.isoformat()
        end = day.isoformat()
        with (
            patch.object(self.demo_rate, "load_demo_rate_snaps", return_value=[snap]),
            patch.object(self.demo_rate, "pipeline_name_lookup", return_value={"pipe-buffalo": "Buffalo"}),
            patch.object(self.demo_rate, "load_contacts_by_ids", return_value={"contact-1": contact}),
            patch.object(self.created, "pipeline_name_lookup", return_value={"pipe-buffalo": "Buffalo"}),
            patch.object(self.created, "load_contacts_by_ids", return_value={"contact-1": contact}),
            patch.object(self.created, "user_name_lookup", return_value={}),
            patch.object(self.payroll, "load_users_by_ids", return_value={}),
        ):
            demo = self.demo_rate.build_payload(object(), day.year, day.month, filters, start, end)
            created = self.created.compute(
                _Db([snap]),
                self.created.MetricContract(),
                year=day.year,
                month=day.month,
                start=start,
                end=end,
                lead_source=lead_filter,
                pipeline_scope="all",
            )
            sits = self.payroll.collect_sits(object(), day, day)
        sit_by = demo["breakdowns"]["sit_by_setter_last_name"]
        ran_by = demo["breakdowns"]["ran_by_setter_last_name"]
        created_by = created["breakdowns"]["created_by_setter_last_name"]
        payroll_setter = sits[0]["setter_last_name"] if sits else None
        payroll_manager = sits[0]["scheduling_manager"] if sits else None
        return {
            "dashboard_ran": ran_by,
            "dashboard_sit": sit_by,
            "dashboard_created": created_by,
            "commissions": sit_by,
            "incentive": sit_by,
            "payroll_setter": payroll_setter,
            "payroll_manager": payroll_manager,
        }

    def test_pre_cutoff_flagged_contact_stays_with_setter_on_all_four_surfaces(self):
        for day in (AUGUST, date(2026, 9, 16), PRE_CUTOFF):
            out = self._run(day, sweeper="Calabrese")
            self.assertEqual(out["dashboard_ran"], {"Hill": 1})
            self.assertEqual(out["dashboard_sit"], {"Hill": 1})
            self.assertEqual(out["dashboard_created"], {"Hill": 1})
            self.assertEqual(out["commissions"], {"Hill": 1})
            self.assertEqual(out["incentive"], {"Hill": 1})
            self.assertEqual(out["payroll_setter"], "Hill")
            self.assertEqual(out["payroll_manager"], "")

    def test_post_cutoff_flagged_contact_goes_to_sweeper_on_all_four_surfaces(self):
        out = self._run(POST_CUTOFF, sweeper="Calabrese")
        self.assertEqual(out["dashboard_ran"], {"Calabrese": 1})
        self.assertEqual(out["dashboard_sit"], {"Calabrese": 1})
        self.assertEqual(out["dashboard_created"], {"Calabrese": 1})
        self.assertEqual(out["commissions"], {"Calabrese": 1})
        self.assertEqual(out["incentive"], {"Calabrese": 1})
        self.assertEqual(out["payroll_setter"], "Calabrese")

    def test_empty_field_stays_with_setter_after_cutoff(self):
        out = self._run(POST_CUTOFF, sweeper="")
        self.assertEqual(out["dashboard_sit"], {"Hill": 1})
        self.assertEqual(out["dashboard_created"], {"Hill": 1})
        self.assertEqual(out["commissions"], {"Hill": 1})
        self.assertEqual(out["payroll_setter"], "Hill")

    def test_commissions_and_payroll_agree_for_the_same_fixture(self):
        for day, sweeper, expected in (
            (AUGUST, "Calabrese", "Hill"),
            (date(2026, 9, 20), "Calabrese", "Hill"),
            (POST_CUTOFF, "Calabrese", "Calabrese"),
            (date(2026, 9, 26), "Nguyen", "Nguyen"),
            (POST_CUTOFF, "", "Hill"),
            (POST_CUTOFF, "none", "Hill"),
        ):
            out = self._run(day, sweeper=sweeper)
            commission_names = list(out["commissions"])
            self.assertEqual(commission_names, [expected])
            self.assertEqual(out["incentive"], out["commissions"])
            self.assertEqual(out["payroll_setter"], expected)
            self.assertEqual(out["dashboard_sit"], out["commissions"])

    def test_scheduling_manager_does_not_follow_the_sweeper(self):
        contact, opp = _flagged_records(POST_CUTOFF, sweeper="Calabrese")
        contact["customFields"].append({"id": "6QmaNZha745jNHnh3U86", "value": "Diamond"})
        snap = _Snap("opp-1", opp)
        with (
            patch.object(self.demo_rate, "load_demo_rate_snaps", return_value=[snap]),
            patch.object(self.demo_rate, "pipeline_name_lookup", return_value={"pipe-buffalo": "Buffalo"}),
            patch.object(self.demo_rate, "load_contacts_by_ids", return_value={"contact-1": contact}),
            patch.object(self.payroll, "load_users_by_ids", return_value={}),
        ):
            sits = self.payroll.collect_sits(object(), POST_CUTOFF, POST_CUTOFF)
        self.assertEqual(sits[0]["setter_last_name"], "Calabrese")
        self.assertEqual(sits[0]["scheduling_manager"], "Diamond")

    def test_self_gen_filter_matches_base_before_cutoff(self):
        before = self._run(AUGUST, sweeper="Calabrese", lead="Doors", lead_filter="Self Gen")
        self.assertEqual(before["dashboard_created"], {})
        self.assertEqual(before["dashboard_sit"], {})
        after = self._run(POST_CUTOFF, sweeper="Calabrese", lead="Doors", lead_filter="Self Gen")
        self.assertEqual(after["dashboard_created"], {"Calabrese": 1})
        self.assertEqual(after["dashboard_sit"], {"Calabrese": 1})
        self.assertEqual(after["commissions"], {"Calabrese": 1})


if __name__ == "__main__":
    unittest.main()
