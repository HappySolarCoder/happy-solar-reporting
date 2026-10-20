# -*- coding: utf-8 -*-
"""Sales Dashboard Owner Performance leaves Sweeper/Rehash off every owner.

October 1–20, 2026 (America/New_York) Owner Performance matched
opportunities_ran (appointmentOccurredAt) and sales (Sold Date). The row
labeled "Ollie Calabrese / Jeff Salas" was a display merge of two GHL
owners. In that window every ran and the one sale were owner Jeff Salas.
Ollie Calabrese had none. Thirteen of Jeff's 20 ran are Sweeper/Rehash
(12 lead source Sweeper and one Self Gen, all Sweeper/Rehash Last Name
Diamond). No other owner had one. None of the 25 sales did.

Diamond Sweeper stays 14 created / 14 ran / 4 demos / 0 sales. That page
does not pass exclude_sweeper_rehash.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
API = ROOT / "api"
for path in (API, METRICS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from sweeper_rehash_attribution import (  # noqa: E402
    excluded_from_owner_performance,
    excluded_from_self_gen,
    lead_source_matches,
)

WHEN = date(2026, 10, 15)

# opportunities_ran 2026-10-01 through 2026-10-20, joined to demo_rate on
# opportunity id for lead source and Sweeper/Rehash Last Name.
# Non-sweeper rows are stored as (owner, count). Their lead sources vary;
# none were Sweeper/Rehash and none had a filled last name.
OCTOBER_KEPT = {
    "Quincy Sermons": 21,
    "Zachary Maecker": 28,
    "Brooke Simpson": 11,
    "Rueben Hand": 23,
    "Allen Frazier": 11,
    "Mark Fino": 1,
}
JEFF_EXCLUDED = [("Sweeper", "Diamond")] * 12 + [("Self Gen", "Diamond")]
JEFF_KEPT = [
    ("3PL", ""),
    ("Inbound", ""),
    ("Inbound", ""),
    ("Inbound", ""),
    ("Inbound", ""),
    ("Doors", ""),
    ("none", ""),
]
OCTOBER_SALES = {
    "Quincy Sermons": 8,
    "Zachary Maecker": 6,
    "Brooke Simpson": 4,
    "Allen Frazier": 3,
    "Rueben Hand": 3,
    "Jeff Salas": 1,
    "Mark Fino": 0,
}
# Every October sale lead source. None is Sweeper/Rehash and none has a last name.
OCTOBER_SALE_LEADS = ["Doors", "Inbound", "none", "Phones", "3PL", "Self Gen"]


def _opp2(sales: int, ran: int) -> str:
    if ran <= 0:
        return "—"
    return f"{(sales / ran) * 100:.1f}%"


def _october_ran(exclude: bool) -> dict[str, int]:
    counts = dict(OCTOBER_KEPT)
    for lead, sweeper in JEFF_EXCLUDED + JEFF_KEPT:
        if exclude and excluded_from_owner_performance(lead, sweeper):
            continue
        counts["Jeff Salas"] = counts.get("Jeff Salas", 0) + 1
    return counts


class OwnerPerformanceRuleTests(unittest.TestCase):
    def test_lead_source_or_filled_last_name_is_excluded_for_every_owner(self):
        self.assertTrue(excluded_from_owner_performance("Sweeper", "Diamond"))
        self.assertTrue(excluded_from_owner_performance("Sweeper", ""))
        self.assertTrue(excluded_from_owner_performance(" Sweeper / Rehash ", "n/a"))
        self.assertTrue(excluded_from_owner_performance("Rehash", ""))
        self.assertTrue(excluded_from_owner_performance("Self Gen", "Diamond"))
        self.assertTrue(excluded_from_owner_performance("Doors", "Diamond"))
        self.assertFalse(excluded_from_owner_performance("Doors", ""))
        self.assertFalse(excluded_from_owner_performance("Doors", "none"))
        self.assertFalse(excluded_from_owner_performance("Doors", "n/a"))
        self.assertFalse(excluded_from_owner_performance("3PL", ""))
        self.assertFalse(excluded_from_owner_performance("Inbound", ""))
        self.assertFalse(excluded_from_owner_performance("Phones", ""))
        self.assertFalse(excluded_from_owner_performance("Self Gen", ""))
        self.assertFalse(excluded_from_owner_performance("none", ""))
        self.assertFalse(excluded_from_owner_performance(None, None))

    def test_rehash_with_a_blank_field_still_matches_self_gen(self):
        # Owner Performance is stricter than the Self Gen filter in #128.
        self.assertTrue(excluded_from_owner_performance("Rehash", ""))
        self.assertFalse(excluded_from_self_gen("Self Gen", ""))
        self.assertTrue(lead_source_matches("Self Gen", "Rehash", "", WHEN))
        self.assertFalse(lead_source_matches("Self Gen", "Self Gen", "Diamond", WHEN))

    def test_october_1_20_only_jeff_ran_changes(self):
        before = _october_ran(False)
        after = _october_ran(True)
        self.assertEqual(before["Jeff Salas"], 20)
        self.assertEqual(after["Jeff Salas"], 7)
        self.assertEqual(sum(before.values()), 115)
        self.assertEqual(sum(after.values()), 102)
        for owner, ran in OCTOBER_KEPT.items():
            self.assertEqual(before[owner], ran)
            self.assertEqual(after[owner], ran)
        self.assertEqual(_opp2(OCTOBER_SALES["Jeff Salas"], before["Jeff Salas"]), "5.0%")
        self.assertEqual(_opp2(OCTOBER_SALES["Jeff Salas"], after["Jeff Salas"]), "14.3%")
        self.assertEqual(_opp2(sum(OCTOBER_SALES.values()), sum(before.values())), "21.7%")
        self.assertEqual(_opp2(sum(OCTOBER_SALES.values()), sum(after.values())), "24.5%")
        for lead in OCTOBER_SALE_LEADS:
            self.assertFalse(excluded_from_owner_performance(lead, ""))
        self.assertEqual(sum(1 for _lead, sweeper in JEFF_EXCLUDED if sweeper == "Diamond"), 13)

    def test_flag_defaults_off_and_only_the_owner_fetches_send_it(self):
        ran_src = (METRICS / "opportunities_ran.py").read_text(encoding="utf-8")
        sales_src = (METRICS / "sales.py").read_text(encoding="utf-8")
        self.assertIn("exclude_sweeper_rehash: bool = False", ran_src)
        self.assertIn("exclude_sweeper_rehash: bool = False", sales_src)
        for src, owner_count in (
            (ran_src, "add_casefold_count(by_owner, owner_labels, oname, empty=\"unassigned\")"),
            (sales_src, "add_casefold_count(owner_counts, owner_labels, oname, empty=\"unassigned\")"),
        ):
            gate = "if exclude_sweeper_rehash and excluded_from_owner_performance("
            self.assertIn(gate, src)
            self.assertLess(src.index(gate), src.index(owner_count))
            self.assertIn('truthy_flag(qs.get("exclude_sweeper_rehash", [""])[0])', src)

        html = (API / "sales_dashboard.py").read_text(encoding="utf-8")
        self.assertNotIn("Ollie Calabrese / Jeff Salas", html)
        self.assertIn("Jeff Salas and Ollie Calabrese are different GHL owners", html)
        self.assertEqual(html.count("exclude_sweeper_rehash=1"), 1)
        self.assertEqual(html.count("${ownerSweeperParam}"), 2)
        for line in html.splitlines():
            if "const salesUrl" in line or "const ranUrl" in line:
                self.assertNotIn("exclude_sweeper_rehash", line)
        self.assertIn("lead_source=${encodeURIComponent('Self Gen')}", html)

        diamond = (METRICS / "diamond_sweeper.py").read_text(encoding="utf-8")
        snapshot = (METRICS / "company_snapshot.py").read_text(encoding="utf-8")
        self.assertNotIn("exclude_sweeper_rehash", diamond)
        self.assertNotIn("exclude_sweeper_rehash", snapshot)
        self.assertIn("compute_sales", diamond)
        self.assertIn("on_sale=on_sale", diamond)


if __name__ == "__main__":
    unittest.main()
