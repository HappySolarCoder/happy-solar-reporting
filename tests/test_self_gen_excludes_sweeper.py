# -*- coding: utf-8 -*-
"""Sweeper/Rehash Last Name is never Self Gen.

October 2026 MTD (America/New_York, 2026-10-01 through 2026-10-20) on the
Sales Dashboard Self Gen card included Tyler Diamond for 14 appointments.
Those rows are setter Diamond and owner Jeff Salas (one is Rueben Hand), so
the setter-last-name-equals-owner override does not match. They were included
because a Self Gen lead-source filter also matched a filled Sweeper/Rehash
Last Name. Thirteen are lead source Sweeper. One (Syracuse) is lead source
Self Gen and still has to be excluded.

Other reps on that card, all blank Sweeper/Rehash Last Name and lead source
Self Gen, stay: Frazier 7, Sermons 7, Hand 6, Maecker 6.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
API = ROOT / "api"
for p in (API, METRICS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sweeper_rehash_attribution import (  # noqa: E402
    attributed_last_name,
    excluded_from_self_gen,
    lead_source_matches,
    self_gen_count_label,
)

WHEN = date(2026, 10, 15)
FIELD = "HWfjOp8MvE6soxBAL75f"
LEAD_FIELD = "hd5QqHEOVSsPom5bJ32P"


def _kept(setter: str, lead: str, sweeper: str) -> str | None:
    if not lead_source_matches("Self Gen", lead, sweeper, WHEN):
        return None
    return attributed_last_name(setter, lead, sweeper, WHEN)


class OctoberSelfGenCardTests(unittest.TestCase):
    def test_diamond_fourteen_leave_self_gen_and_other_reps_stay(self):
        rows = [("Diamond", "Sweeper", "Diamond")] * 13
        rows.append(("Diamond", "Self Gen", "Diamond"))
        rows += [("Frazier", "Self Gen", "")] * 7
        rows += [("Sermons", "Self Gen", "")] * 7
        rows += [("Hand", "Self Gen", "")] * 6
        rows += [("Maecker", "Self Gen", "")] * 6

        kept = [_kept(*row) for row in rows]
        self.assertEqual(kept.count("Diamond"), 0)
        self.assertEqual(kept.count(None), 14)
        self.assertEqual(kept.count("Frazier"), 7)
        self.assertEqual(kept.count("Sermons"), 7)
        self.assertEqual(kept.count("Hand"), 6)
        self.assertEqual(kept.count("Maecker"), 6)
        self.assertEqual(sum(1 for name in kept if name), 26)

    def test_setter_owner_override_is_not_why_diamond_matched(self):
        from channel_goals import self_gen_reason

        # Owner is Jeff Salas, not Tyler Diamond. The override does not fire.
        self.assertIsNone(self_gen_reason("Sweeper", "Diamond", "Jeff Salas"))
        self.assertIsNone(self_gen_reason("Sweeper", "Diamond", "Rueben Hand"))
        # Lead source Self Gen would count until the sweeper name is passed.
        self.assertEqual(self_gen_reason("Self Gen", "Diamond", "Jeff Salas"), "lead_source")
        self.assertIsNone(self_gen_reason("Self Gen", "Diamond", "Jeff Salas", "Diamond"))
        # A real self-gen where the setter owns the deal is unchanged.
        self.assertEqual(self_gen_reason("Doors", "Frazier", "Allen Frazier", ""), "override")
        self.assertEqual(self_gen_reason("Self Gen", "Sermons", "Quincy Sermons"), "lead_source")

    def test_unfiltered_credit_and_histogram_still_name_the_sweeper(self):
        self.assertEqual(attributed_last_name("Hill", "Sweeper", "Diamond", WHEN), "Diamond")
        self.assertEqual(attributed_last_name("Hill", "Self Gen", "Diamond", WHEN), "Diamond")
        self.assertTrue(lead_source_matches(None, "Sweeper", "Diamond", WHEN))
        self.assertFalse(excluded_from_self_gen(None, "Diamond"))
        self.assertTrue(excluded_from_self_gen("Self Gen", "Diamond"))
        self.assertFalse(excluded_from_self_gen("Self Gen", ""))
        self.assertFalse(excluded_from_self_gen("Self Gen", "n/a"))
        self.assertEqual(self_gen_count_label("Self Gen", "Diamond"), "Sweeper")
        self.assertEqual(self_gen_count_label("self gen", ""), "self gen")
        self.assertEqual(self_gen_count_label("Doors", "Diamond"), "Doors")
        self.assertFalse(lead_source_matches("Self Gen", "Self Gen", "Diamond", WHEN))
        self.assertEqual(_kept("Hill", "Rehash", ""), "Hill")

    def test_diamond_sweeper_does_not_use_the_self_gen_filter(self):
        src = (METRICS / "diamond_sweeper.py").read_text(encoding="utf-8")
        self.assertNotIn("lead_source_matches", src)
        self.assertNotIn("excluded_from_self_gen", src)
        self.assertIn("Sweeper/Rehash Last Name", src)

    def test_sales_dashboard_copy_drops_the_self_gen_inclusion(self):
        html = (API / "sales_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("Sweeper/Rehash Last Name", html)
        self.assertIn("14-appointment Sweeper/Rehash goal", html)
        self.assertNotIn("counts for that person", html)
        self.assertIn("lead_source=${encodeURIComponent('Self Gen')}", html)


class ScOverviewSelfGenFilterTests(unittest.TestCase):
    def test_self_gen_filter_drops_a_named_sweeper_contact(self):
        import sc_overview

        contact = {
            "customFields": [
                {"id": LEAD_FIELD, "value": "Self Gen"},
                {"id": FIELD, "value": "Diamond"},
            ]
        }
        opp = {"customFields": []}
        self.assertFalse(sc_overview.passes_lead_source_filter("Self Gen", contact, opp))
        plain = {"customFields": [{"id": LEAD_FIELD, "value": "Self Gen"}]}
        self.assertTrue(sc_overview.passes_lead_source_filter("Self Gen", plain, opp))
        self.assertTrue(sc_overview.passes_lead_source_filter("", contact, opp))
        doors = {"customFields": [{"id": LEAD_FIELD, "value": "Doors"}, {"id": FIELD, "value": "Diamond"}]}
        self.assertTrue(sc_overview.passes_lead_source_filter("Doors", doors, opp))
        src = (API / "sc_overview.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("passes_lead_source_filter"), 4)


if __name__ == "__main__":
    unittest.main()
