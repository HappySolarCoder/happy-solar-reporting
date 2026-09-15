# -*- coding: utf-8 -*-

"""Rep Daily Recap Self Gen appointment counts.

Locked definition (Jeff Salas / ClickUp 86bc13yza, 86bc14j3d):
- Appointment already on this recap (appointmentStartTime in the ET day), AND
- Contact lead-source custom field hd5QqHEOVSsPom5bJ32P normalizes to
  "Self Gen" via existing normalize_lead_source (self gen / selfgen).
- Per-owner bucket is the same GHL owner as today. Not Raydar role
  Self Gen and not sales-dashboard Self Gen opps.

Live chi spot-check (existing lead_source on listed appointments, 2026-09-15):
- 2026-09-14: 20 appointments, 0 Self Gen
- 2026-09-12: 8 appointments, 1 Self Gen (Quincy / Cesar Rodriguez)
- 2026-09-10: 10 appointments, 4 Self Gen (Rueben 1, Zachary 2, Walter 1)
- 2026-09-08: 16 appointments, 3 Self Gen (Quincy, Rueben, Matthew Dole)
- 2026-09-05: 4 appointments, 1 Self Gen (April / Aidan Pike)

Do not invent counts. Form freeze / calculator unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
RECAP_SRC = (API / "rep_daily_recap.py").read_text(encoding="utf-8")
SC_OVERVIEW_SRC = (API / "sc_overview.py").read_text(encoding="utf-8")
SALES_SRC = (API / "metrics" / "sales.py").read_text(encoding="utf-8")

# Live chi 2026-09-10 appointment lead_source lists. Do not invent extras.
CHI_2026_09_10_OWNERS = (
    ("Rueben Hand", ("Self Gen",)),
    (
        "Zachary Maecker",
        ("3PL", "3PL", "Self Gen", "Self Gen"),
    ),
    ("Walter Mysiak", ("Self Gen",)),
    ("Allen Frazier", ("Doors",)),
    ("Brooke Simpson", ("Doors",)),
    ("Mark Fino", ("none",)),
    ("Quincy Sermons", ("Doors",)),
    ("Brian Grim", ()),
)

CHI_2026_09_14_LEAD_SOURCES = (
    "Inbound",
    "Inbound",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "3PL",
    "3PL",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "3PL",
    "3PL",
    "3PL",
)

CHI_2026_09_12_LEAD_SOURCES = (
    "Doors",
    "Doors",
    "Doors",
    "Self Gen",
    "3PL",
    "3PL",
    "Doors",
    "Doors",
)

CHI_2026_09_08_LEAD_SOURCES = (
    "Doors",
    "Doors",
    "Inbound",
    "Doors",
    "Doors",
    "Self Gen",
    "3PL",
    "3PL",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Doors",
    "Self Gen",
    "Doors",
    "Self Gen",
)

CHI_2026_09_05_LEAD_SOURCES = (
    "3PL",
    "3PL",
    "Self Gen",
    "Doors",
)


def _install_google_stubs() -> None:
    google = sys.modules.setdefault("google", MagicMock())
    cloud = sys.modules.setdefault("google.cloud", MagicMock())
    oauth2 = sys.modules.setdefault("google.oauth2", MagicMock())
    sys.modules.setdefault("google.cloud.firestore", MagicMock())
    sys.modules.setdefault("google.oauth2.service_account", MagicMock())
    google.cloud = cloud
    google.oauth2 = oauth2


def load_recap():
    _install_google_stubs()
    if str(API) not in sys.path:
        sys.path.insert(0, str(API))
    spec = importlib.util.spec_from_file_location("rep_daily_recap_self_gen", API / "rep_daily_recap.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/rep_daily_recap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rep_daily_recap_self_gen"] = module
    spec.loader.exec_module(module)
    return module


recap = load_recap()


def _appt(lead_source: str) -> dict[str, str]:
    return {"lead_source": lead_source}


def _owner(label: str, lead_sources: tuple[str, ...]) -> dict:
    appointments = [_appt(source) for source in lead_sources]
    return {
        "owner_label": label,
        "appointments": appointments,
        "appointment_total": len(appointments),
        "self_gen_appointment_total": recap.count_self_gen_appointments(appointments),
        "completed_total": 0,
        "sit_total": 0,
        "no_sit_total": 0,
        "pending_total": 0,
        "powerline_dials": 0,
        "doors_knocked": 0,
        "work_total": len(appointments),
        "team": "",
        "powerline_results_top": [],
        "door_statuses_top": [],
    }


class NormalizeLeadSourceSelfGenTests(unittest.TestCase):
    def test_self_gen_aliases(self):
        self.assertEqual(recap.normalize_lead_source("self gen"), "Self Gen")
        self.assertEqual(recap.normalize_lead_source("selfgen"), "Self Gen")
        self.assertEqual(recap.normalize_lead_source("Self Gen"), "Self Gen")
        self.assertEqual(recap.normalize_lead_source("SELFGEN"), "Self Gen")
        self.assertEqual(recap.normalize_lead_source("  Self  Gen  "), "Self Gen")

    def test_does_not_invent_hyphen_or_role_aliases(self):
        self.assertEqual(recap.normalize_lead_source("self-gen"), "self-gen")
        self.assertEqual(recap.normalize_lead_source("Doors"), "Doors")
        self.assertEqual(recap.normalize_lead_source(""), "none")
        self.assertFalse(recap.is_self_gen_lead_source("self-gen"))
        self.assertFalse(recap.is_self_gen_lead_source("Doors"))
        self.assertTrue(recap.is_self_gen_lead_source("Self Gen"))


class OwnerSelfGenAggregationTests(unittest.TestCase):
    def test_zero_is_valid(self):
        self.assertEqual(recap.count_self_gen_appointments([]), 0)
        self.assertEqual(recap.count_self_gen_appointments(None), 0)
        self.assertEqual(
            recap.count_self_gen_appointments([_appt("Doors"), _appt("3PL"), _appt("none")]),
            0,
        )

    def test_chi_2026_09_14_twenty_appointments_zero_self_gen(self):
        self.assertEqual(len(CHI_2026_09_14_LEAD_SOURCES), 20)
        self.assertEqual(
            recap.count_self_gen_appointments([_appt(source) for source in CHI_2026_09_14_LEAD_SOURCES]),
            0,
        )

    def test_chi_2026_09_12_eight_appointments_one_self_gen(self):
        self.assertEqual(len(CHI_2026_09_12_LEAD_SOURCES), 8)
        self.assertEqual(
            recap.count_self_gen_appointments([_appt(source) for source in CHI_2026_09_12_LEAD_SOURCES]),
            1,
        )

    def test_chi_2026_09_08_sixteen_appointments_three_self_gen(self):
        self.assertEqual(len(CHI_2026_09_08_LEAD_SOURCES), 16)
        self.assertEqual(
            recap.count_self_gen_appointments([_appt(source) for source in CHI_2026_09_08_LEAD_SOURCES]),
            3,
        )

    def test_chi_2026_09_05_four_appointments_one_self_gen(self):
        self.assertEqual(len(CHI_2026_09_05_LEAD_SOURCES), 4)
        self.assertEqual(
            recap.count_self_gen_appointments([_appt(source) for source in CHI_2026_09_05_LEAD_SOURCES]),
            1,
        )

    def test_chi_2026_09_10_owner_counts_and_summary(self):
        owners = [_owner(label, sources) for label, sources in CHI_2026_09_10_OWNERS]
        by_label = {row["owner_label"]: row["self_gen_appointment_total"] for row in owners}
        self.assertEqual(by_label["Rueben Hand"], 1)
        self.assertEqual(by_label["Zachary Maecker"], 2)
        self.assertEqual(by_label["Walter Mysiak"], 1)
        self.assertEqual(by_label["Allen Frazier"], 0)
        self.assertEqual(by_label["Brian Grim"], 0)
        self.assertEqual(sum(row["appointment_total"] for row in owners), 10)
        self.assertEqual(sum(row["self_gen_appointment_total"] for row in owners), 4)


class SelfGenHtmlTests(unittest.TestCase):
    def test_owner_card_puts_self_gen_next_to_appointments(self):
        owner = _owner(
            "Zachary Maecker",
            ("3PL", "Self Gen"),
        )
        owner["appointments"] = [
            {
                "time_local": "6:00 PM",
                "contact_name": "Teryy Tredo",
                "outcome": "Sit",
                "outcome_class": "good",
                "pipeline": "Buffalo",
                "stage": "Demo-Negotiating",
                "setter_last_name": "Maecker",
                "lead_source": "Self Gen",
            },
            {
                "time_local": "4:00 PM",
                "contact_name": "Greg Voss",
                "outcome": "Sit",
                "outcome_class": "good",
                "pipeline": "Buffalo",
                "stage": "Demo-Negotiating",
                "setter_last_name": "Calabrese",
                "lead_source": "3PL",
            },
        ]
        owner["self_gen_appointment_total"] = recap.count_self_gen_appointments(owner["appointments"])
        html = recap.render_owner_card(owner)
        appointments_at = html.find("<span>Appointments</span>")
        self_gen_at = html.find("<span>Self Gen</span>")
        completed_at = html.find("<span>Completed</span>")
        self.assertGreater(appointments_at, 0)
        self.assertGreater(self_gen_at, appointments_at)
        self.assertGreater(completed_at, self_gen_at)
        self.assertIn("<strong>2</strong>", html)
        self.assertIn("<strong>1</strong>", html)
        self.assertIn("self-gen-row", html)
        self.assertIn("Teryy Tredo", html)
        self.assertIn("Greg Voss", html)

    def test_page_footer_defines_contact_lead_source(self):
        html = recap.render_html(
            {
                "summary": {
                    "work_total": 0,
                    "owners_with_activity": 0,
                    "owners_total": 0,
                    "appointments_total": 0,
                    "self_gen_appointments_total": 0,
                    "completed_outcomes_total": 0,
                    "powerline_dials_total": 0,
                    "doors_knocked_total": 0,
                },
                "owners": [],
                "unmapped_activity": {},
                "powerline_available": True,
            },
            "2026-09-10",
        )
        self.assertIn("self_gen_appointments_total", RECAP_SRC)
        self.assertIn("Self Gen appointments", html)
        self.assertIn(
            "Self Gen = contact lead source Self Gen (hd5QqHEOVSsPom5bJ32P) on appointments scheduled that ET day.",
            html,
        )


class SelfGenContractTests(unittest.TestCase):
    def test_derives_from_built_appointments_not_a_new_stream(self):
        self.assertEqual(recap.LEAD_SOURCE_FIELD_ID, "hd5QqHEOVSsPom5bJ32P")
        self.assertIn("count_self_gen_appointments(bucket[\"appointments\"])", RECAP_SRC)
        self.assertIn("self_gen_appointment_total", RECAP_SRC)
        self.assertIn("self_gen_appointments_total", RECAP_SRC)
        self.assertNotIn("self_gen_opportunities", RECAP_SRC)
        self.assertNotIn("raydar_user_roles", RECAP_SRC)

    def test_does_not_change_form_freeze_or_calculator(self):
        self.assertIn("normalize_completed_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("sold_date", SALES_SRC.lower())
        self.assertNotIn("self_gen_appointment_total", SC_OVERVIEW_SRC)
        self.assertNotIn("self_gen_appointment_total", SALES_SRC)


if __name__ == "__main__":
    unittest.main()
