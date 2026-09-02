# -*- coding: utf-8 -*-

"""Rep Daily Recap identity join + full sales-roster seed.

Warehouse 2026-09-02 (live chi settings_api bootstrap) + live recap:
- roster_people_v1 still 23 rows: 9 rep / 14 setter.
- April is still NOT a roster rep. IDs still hold:
  ghl IJrbhufMjsmwdxf252sb April Cornell-DeAngelis,
  raydar jLZoREmBADZmWjoUIiwdAf2BnsE3 April Cornell,
  email april@happyslr.com.
- Live chi 2026-08-28 (activity-only, before this fix): 5 owners
  (Brooke, Quincy, Jeff, Mark, Rueben). April unmapped:
  Powerline April Cornell-DeAngelis 34, Raydar April Cornell 95.
- Setters (William Breen, Bo Hill, Steven Emerson, Marissa Mancini,
  Jordan Meehan, Allen Frazier, Evan Test Setter) stay unmapped.
- Sales roster reps with no work that day must still appear (zeros).

Do not invent knock counts. Do not dump setters onto owner rows.
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

APRIL_OWNER_ID = "IJrbhufMjsmwdxf252sb"
APRIL_OWNER_LABEL = "April Cornell-DeAngelis"
APRIL_RAYDAR_LABEL = "April Cornell"
APRIL_EMAIL = "april@happyslr.com"
APRIL_RAYDAR_ID = "jLZoREmBADZmWjoUIiwdAf2BnsE3"
WILLIAM_OWNER_ID = "0fhSjcMLNtcE0cPjYfhj"
WILLIAM_LABEL = "William Breen"
RUEBEN_OWNER_ID = "f4udrh1LuU0TEkF4ZFSj"
BRIAN_OWNER_ID = "xOY6fGHE392ePCZJ8wFd"
ALLEN_GHL_ID = "YYkIcdAiCtNFR1pgOarJ"
STEVEN_GHL_ID = "y39YIlgRGCJFhZkBzF0h"
POWERLINE_APRIL_DIALS = 40
RAYDAR_APRIL_KNOCKS = 17
POWERLINE_APRIL_828 = 34
RAYDAR_APRIL_828 = 95
POWERLINE_WILLIAM_DIALS = 56
RAYDAR_SAWYER_KNOCKS = 125
SETTER_LABELS = (
    WILLIAM_LABEL,
    "Bo Hill",
    "Steven Emerson",
    "Marissa Mancini",
    "Jordan Meehan",
    "Allen Frazier",
    "Evan Test Setter",
    "Sawyer Vermeesch",
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
    spec = importlib.util.spec_from_file_location("rep_daily_recap_identity", API / "rep_daily_recap.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/rep_daily_recap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rep_daily_recap_identity"] = module
    spec.loader.exec_module(module)
    return module


recap = load_recap()


def _roster_row(owner_id: str, label: str, **extra: str) -> dict[str, str]:
    return {
        "owner_id": owner_id,
        "label": label,
        "team": extra.get("team", ""),
        "person_key": extra.get("person_key", ""),
        "raydar_user_id": extra.get("raydar_user_id", ""),
        "ghl_user_name": extra.get("ghl_user_name", ""),
        "email": extra.get("email", ""),
    }


def _april_ghl_users() -> dict[str, dict[str, str]]:
    return {
        APRIL_OWNER_ID: {"name": APRIL_OWNER_LABEL, "email": APRIL_EMAIL},
        RUEBEN_OWNER_ID: {"name": "Rueben Hand", "email": "rueben@happyslr.com"},
        WILLIAM_OWNER_ID: {"name": WILLIAM_LABEL, "email": "wbreen@happyslr.com"},
        ALLEN_GHL_ID: {"name": "Allen Frazier", "email": "allen@happyslr.com"},
        STEVEN_GHL_ID: {"name": "Steven Emerson", "email": "steven@happyslr.com"},
        BRIAN_OWNER_ID: {"name": "Brian Grim", "email": "brian@happyslr.com"},
    }


def _setter_blocklist():
    return recap.setter_blocklist_from_names(SETTER_LABELS)


def _attribute(identities, alias_index, powerline_rows, raydar_rows, raydar_users=None):
    owners: dict[str, dict[str, int]] = {}
    unmapped_powerline: dict[str, int] = {}
    unmapped_raydar: dict[str, int] = {}
    raydar_to_owner = recap.build_raydar_to_owner(identities, raydar_users or {})

    def bump(bucket: dict[str, dict[str, int]], owner_id: str, field: str, count: int) -> None:
        row = bucket.setdefault(owner_id, {"powerline_dials": 0, "doors_knocked": 0})
        row[field] += count

    for label, count in powerline_rows:
        owner_id = recap.map_label_to_owner_fuzzy(label, alias_index, identities)
        if owner_id:
            bump(owners, owner_id, "powerline_dials", count)
        else:
            unmapped_powerline[label] = unmapped_powerline.get(label, 0) + count

    for label, count, actor_id in raydar_rows:
        owner_id = raydar_to_owner.get(actor_id) if actor_id else None
        if not owner_id:
            owner_id = recap.map_label_to_owner_fuzzy(label, alias_index, identities)
        if owner_id:
            bump(owners, owner_id, "doors_knocked", count)
        else:
            unmapped_raydar[label] = unmapped_raydar.get(label, 0) + count

    return owners, unmapped_powerline, unmapped_raydar


class IdentityKeyTests(unittest.TestCase):
    def test_hyphenated_name_has_first_last_short_form(self):
        keys = recap.identity_name_keys(APRIL_OWNER_LABEL)
        self.assertIn("april cornell deangelis", keys)
        self.assertIn("april cornell", keys)

    def test_fuzzy_hyphenated_vs_short_first_last(self):
        self.assertTrue(recap.fuzzy_name_match(APRIL_RAYDAR_LABEL, APRIL_OWNER_LABEL))
        self.assertTrue(recap.fuzzy_name_match(APRIL_OWNER_LABEL, APRIL_RAYDAR_LABEL))
        self.assertFalse(recap.fuzzy_name_match("April Cornell", "April Smith"))


class April824IdentityTests(unittest.TestCase):
    def test_on_page_owner_gets_powerline_40_and_raydar_17(self):
        """April is not in roster. Join the GHL owner card already on the page."""
        roster = {
            RUEBEN_OWNER_ID: _roster_row(RUEBEN_OWNER_ID, "Rueben Hand", raydar_user_id="ray-rueben"),
        }
        identities = recap.collect_owner_identities(
            roster,
            extra_labels={APRIL_OWNER_ID: APRIL_OWNER_LABEL},
            ghl_users=_april_ghl_users(),
        )
        alias_index = recap.build_owner_alias_index(identities)
        raydar_users = {
            APRIL_RAYDAR_ID: {"name": APRIL_RAYDAR_LABEL, "email": APRIL_EMAIL},
            "ray-sawyer": {"name": "Sawyer Vermeesch", "email": "sawyer@happyslr.com"},
        }

        owners, unmapped_pl, unmapped_rd = _attribute(
            identities,
            alias_index,
            [
                (APRIL_OWNER_LABEL, POWERLINE_APRIL_DIALS),
                (WILLIAM_LABEL, POWERLINE_WILLIAM_DIALS),
            ],
            [
                (APRIL_RAYDAR_LABEL, RAYDAR_APRIL_KNOCKS, APRIL_RAYDAR_ID),
                ("Sawyer Vermeesch", RAYDAR_SAWYER_KNOCKS, "ray-sawyer"),
            ],
            raydar_users,
        )

        april = owners[APRIL_OWNER_ID]
        self.assertEqual(april["powerline_dials"], POWERLINE_APRIL_DIALS)
        self.assertEqual(april["doors_knocked"], RAYDAR_APRIL_KNOCKS)
        self.assertNotEqual(april["doors_knocked"], 20)
        self.assertNotIn(APRIL_OWNER_LABEL, unmapped_pl)
        self.assertNotIn(APRIL_RAYDAR_LABEL, unmapped_rd)
        self.assertNotIn(WILLIAM_OWNER_ID, owners)
        self.assertEqual(unmapped_pl.get(WILLIAM_LABEL), POWERLINE_WILLIAM_DIALS)
        self.assertEqual(unmapped_rd.get("Sawyer Vermeesch"), RAYDAR_SAWYER_KNOCKS)

    def test_raydar_email_joins_even_without_name_match(self):
        identities = recap.collect_owner_identities(
            {},
            extra_labels={APRIL_OWNER_ID: APRIL_OWNER_LABEL},
            ghl_users=_april_ghl_users(),
        )
        mapping = recap.build_raydar_to_owner(
            identities,
            {APRIL_RAYDAR_ID: {"name": "Different Label", "email": APRIL_EMAIL}},
        )
        self.assertEqual(mapping[APRIL_RAYDAR_ID], APRIL_OWNER_ID)

    def test_setters_without_owner_card_stay_unmapped(self):
        identities = recap.collect_owner_identities(
            {RUEBEN_OWNER_ID: _roster_row(RUEBEN_OWNER_ID, "Rueben Hand")},
            extra_labels={APRIL_OWNER_ID: APRIL_OWNER_LABEL},
            ghl_users=_april_ghl_users(),
        )
        alias_index = recap.build_owner_alias_index(identities)
        self.assertIsNone(recap.map_label_to_owner_fuzzy(WILLIAM_LABEL, alias_index, identities))
        self.assertIsNone(recap.map_label_to_owner_fuzzy("Sawyer Vermeesch", alias_index, identities))
        self.assertIsNone(recap.map_label_to_owner_fuzzy("Bo Hill", alias_index, identities))

    def test_short_name_stays_on_exact_owner_when_two_matches(self):
        other_id = "otherAprilId00000001"
        identities = recap.collect_owner_identities(
            {
                APRIL_OWNER_ID: _roster_row(APRIL_OWNER_ID, APRIL_OWNER_LABEL),
                other_id: _roster_row(other_id, "April Cornell"),
            },
            None,
            None,
        )
        alias_index = recap.build_owner_alias_index(identities)
        self.assertEqual(
            recap.map_label_to_owner_fuzzy(APRIL_OWNER_LABEL, alias_index, identities),
            APRIL_OWNER_ID,
        )
        self.assertEqual(
            recap.map_label_to_owner_fuzzy("April Cornell", alias_index, identities),
            other_id,
        )


class April828ZeroDayJoinTests(unittest.TestCase):
    def test_hyphenated_aliases_collapse_without_appointment_card(self):
        """8/28: no extra_labels. Both April names join the GHL user, not two rows."""
        roster = {
            RUEBEN_OWNER_ID: _roster_row(RUEBEN_OWNER_ID, "Rueben Hand", raydar_user_id="ray-rueben"),
            BRIAN_OWNER_ID: _roster_row(BRIAN_OWNER_ID, "Brian Grim"),
        }
        identities = recap.collect_owner_identities(
            roster,
            extra_labels=None,
            ghl_users=_april_ghl_users(),
            setter_blocklist=_setter_blocklist(),
        )
        self.assertIn(APRIL_OWNER_ID, identities)
        self.assertEqual(identities[APRIL_OWNER_ID]["label"], APRIL_OWNER_LABEL)
        alias_index = recap.build_owner_alias_index(identities)
        self.assertEqual(
            recap.map_label_to_owner_fuzzy(APRIL_OWNER_LABEL, alias_index, identities),
            APRIL_OWNER_ID,
        )
        self.assertEqual(
            recap.map_label_to_owner_fuzzy(APRIL_RAYDAR_LABEL, alias_index, identities),
            APRIL_OWNER_ID,
        )

        owners, unmapped_pl, unmapped_rd = _attribute(
            identities,
            alias_index,
            [
                (APRIL_OWNER_LABEL, POWERLINE_APRIL_828),
                (WILLIAM_LABEL, 77),
            ],
            [
                (APRIL_RAYDAR_LABEL, RAYDAR_APRIL_828, APRIL_RAYDAR_ID),
                ("Bo Hill", 125, "ray-bo"),
                ("Steven Emerson", 100, "ray-steven"),
                ("Marissa Mancini", 90, "ray-marissa"),
                ("Jordan Meehan", 85, "ray-jordan"),
                ("Allen Frazier", 69, "ray-allen"),
                (WILLIAM_LABEL, 22, "ray-william"),
                ("Evan Test Setter", 1, "ray-evan-test"),
            ],
            {
                APRIL_RAYDAR_ID: {"name": APRIL_RAYDAR_LABEL, "email": APRIL_EMAIL},
                "ray-bo": {"name": "Bo Hill", "email": "bo@happyslr.com"},
                "ray-steven": {"name": "Steven Emerson", "email": "steven@happyslr.com"},
                "ray-marissa": {"name": "Marissa Mancini", "email": "marissa@happyslr.com"},
                "ray-jordan": {"name": "Jordan Meehan", "email": "jordan@happyslr.com"},
                "ray-allen": {"name": "Allen Frazier", "email": "allen@happyslr.com"},
                "ray-william": {"name": WILLIAM_LABEL, "email": "wbreen@happyslr.com"},
                "ray-evan-test": {"name": "Evan Test Setter", "email": "evan@happyslr.com"},
            },
        )

        april = owners[APRIL_OWNER_ID]
        self.assertEqual(april["powerline_dials"], POWERLINE_APRIL_828)
        self.assertEqual(april["doors_knocked"], RAYDAR_APRIL_828)
        self.assertNotIn(APRIL_OWNER_LABEL, unmapped_pl)
        self.assertNotIn(APRIL_RAYDAR_LABEL, unmapped_rd)
        self.assertNotIn(WILLIAM_OWNER_ID, owners)
        self.assertNotIn(ALLEN_GHL_ID, owners)
        self.assertNotIn(STEVEN_GHL_ID, owners)
        self.assertEqual(unmapped_pl.get(WILLIAM_LABEL), 77)
        self.assertEqual(unmapped_rd.get("Bo Hill"), 125)
        self.assertEqual(unmapped_rd.get("Steven Emerson"), 100)
        self.assertEqual(unmapped_rd.get("Marissa Mancini"), 90)
        self.assertEqual(unmapped_rd.get("Jordan Meehan"), 85)
        self.assertEqual(unmapped_rd.get("Allen Frazier"), 69)
        self.assertEqual(unmapped_rd.get(WILLIAM_LABEL), 22)
        self.assertEqual(unmapped_rd.get("Evan Test Setter"), 1)

    def test_zero_day_sales_roster_rep_still_renders(self):
        brian = {
            "owner_id": BRIAN_OWNER_ID,
            "owner_label": "Brian Grim",
            "appointment_total": 0,
            "powerline_dials": 0,
            "doors_knocked": 0,
            "work_total": 0,
        }
        april = {
            "owner_id": APRIL_OWNER_ID,
            "owner_label": APRIL_OWNER_LABEL,
            "appointment_total": 0,
            "powerline_dials": POWERLINE_APRIL_828,
            "doors_knocked": RAYDAR_APRIL_828,
            "work_total": POWERLINE_APRIL_828 + RAYDAR_APRIL_828,
        }
        william = {
            "owner_id": WILLIAM_OWNER_ID,
            "owner_label": WILLIAM_LABEL,
            "appointment_total": 0,
            "powerline_dials": 77,
            "doors_knocked": 22,
            "work_total": 99,
        }
        roster_ids = {RUEBEN_OWNER_ID, BRIAN_OWNER_ID}
        self.assertTrue(recap.owner_should_render(brian, roster_ids))
        self.assertTrue(recap.owner_should_render(april, roster_ids))
        # Off-roster setters must not be seeded; a leftover zero card stays hidden.
        self.assertFalse(recap.owner_should_render({"owner_id": WILLIAM_OWNER_ID, "work_total": 0}, roster_ids))
        # If a setter bucket were created (should not happen), activity would show.
        # Keep this explicit so we do not hide on-page appointment owners.
        self.assertTrue(recap.owner_should_render(william, roster_ids))
        self.assertTrue(
            recap.owner_should_render(
                {"owner_id": RUEBEN_OWNER_ID, "owner_label": "Rueben Hand", "work_total": 0},
                roster_ids,
            )
        )

    def test_setters_with_ghl_user_rows_stay_unmapped(self):
        identities = recap.collect_owner_identities(
            {RUEBEN_OWNER_ID: _roster_row(RUEBEN_OWNER_ID, "Rueben Hand")},
            extra_labels=None,
            ghl_users=_april_ghl_users(),
            setter_blocklist=_setter_blocklist(),
        )
        self.assertNotIn(WILLIAM_OWNER_ID, identities)
        self.assertNotIn(ALLEN_GHL_ID, identities)
        self.assertNotIn(STEVEN_GHL_ID, identities)
        self.assertIn(APRIL_OWNER_ID, identities)
        alias_index = recap.build_owner_alias_index(identities)
        for label in SETTER_LABELS:
            self.assertIsNone(
                recap.map_label_to_owner_fuzzy(label, alias_index, identities),
                label,
            )


class RosterLoadTests(unittest.TestCase):
    def test_load_rep_roster_skips_setters_and_roleless_closers(self):
        class Snap:
            def __init__(self, doc_id: str, data: dict):
                self.id = doc_id
                self._data = data

            def to_dict(self):
                return self._data

        class Collection:
            def stream(self):
                return [
                    Snap(
                        "april-key",
                        {
                            "display_name": APRIL_OWNER_LABEL,
                            "ghl_user_id": APRIL_OWNER_ID,
                            "role": "closer",
                        },
                    ),
                    Snap(
                        "breen-key",
                        {
                            "display_name": WILLIAM_LABEL,
                            "ghl_user_id": WILLIAM_OWNER_ID,
                            "role": "setter",
                        },
                    ),
                    Snap(
                        "rueben-key",
                        {
                            "display_name": "Rueben Hand",
                            "ghl_user_id": RUEBEN_OWNER_ID,
                            "role": "rep",
                        },
                    ),
                    Snap(
                        "rueben-setter-key",
                        {
                            "display_name": "Rueben Hand",
                            "ghl_user_id": "",
                            "raydar_user_id": "yraITFCfOtPY0gQh4p8HyvGCdbx1",
                            "role": "setter",
                        },
                    ),
                ]

        class DB:
            def collection(self, name: str):
                self.collection_name = name
                return Collection()

        db = DB()
        loaded = recap.load_rep_roster(db, {})
        self.assertEqual(db.collection_name, "roster_people_v1")
        self.assertIn(RUEBEN_OWNER_ID, loaded)
        self.assertNotIn(APRIL_OWNER_ID, loaded)
        self.assertNotIn(WILLIAM_OWNER_ID, loaded)

        reps, setters = recap.load_roster_partitions(db, {})
        self.assertEqual(reps, loaded)
        self.assertTrue(recap.setter_identity_blocked(setters, label=WILLIAM_LABEL, owner_id=WILLIAM_OWNER_ID))
        self.assertFalse(recap.setter_identity_blocked(setters, label=APRIL_OWNER_LABEL, owner_id=APRIL_OWNER_ID))
        # Dual-role warehouse row: setter name is blocked for GHL sweep, but
        # the role=rep row still seeds an owner.
        self.assertTrue(recap.setter_identity_blocked(setters, label="Rueben Hand"))
        self.assertIn(RUEBEN_OWNER_ID, reps)

    def test_source_keeps_role_rep_filter_roster_seed_and_join(self):
        self.assertIn("load_roster_partitions", RECAP_SRC)
        self.assertIn("owner_should_render", RECAP_SRC)
        self.assertIn("setter_blocklist", RECAP_SRC)
        self.assertIn("Full sales roster first", RECAP_SRC)
        self.assertIn("build_raydar_to_owner", RECAP_SRC)
        self.assertIn("normalize_email", RECAP_SRC)
        self.assertIn("identity_name_keys", RECAP_SRC)
        self.assertIn("owners already on the page", RECAP_SRC)
        self.assertIn('is_rep = role == "rep" or "rep" in categories', RECAP_SRC)
        self.assertNotIn('if role != "rep" and "rep" not in categories:', RECAP_SRC)


class ContractGuardTests(unittest.TestCase):
    def test_does_not_change_company_sales_or_sc_overview_pie(self):
        self.assertIn("normalize_completed_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("is_completed_sale_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("sold_date", SALES_SRC.lower())
        self.assertNotIn("identity_name_keys", SC_OVERVIEW_SRC)
        self.assertNotIn("identity_name_keys", SALES_SRC)


if __name__ == "__main__":
    unittest.main()
