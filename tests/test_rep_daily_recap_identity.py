# -*- coding: utf-8 -*-

"""Rep Daily Recap identity join — April 8/24 lock.

Live chi 2026-08-24: owner IJrbhufMjsmwdxf252sb April Cornell-DeAngelis had
powerline_dials 0 / doors_knocked 0. unmapped_activity.powerline had
April Cornell-DeAngelis 40. unmapped_activity.raydar had April Cornell 17.

Do not invent Jeff's ~20 doors. doors_knocked is the mapped Raydar grain.
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
WILLIAM_OWNER_ID = "0fhsjcmlntce0cpjyfhj"
WILLIAM_LABEL = "William Breen"
RUEBEN_OWNER_ID = "f4udrh1LuU0TEkF4ZFSj"
POWERLINE_APRIL_DIALS = 40
RAYDAR_APRIL_KNOCKS = 17
POWERLINE_WILLIAM_DIALS = 56


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
    row = {
        "owner_id": owner_id,
        "label": label,
        "team": extra.get("team", ""),
        "person_key": extra.get("person_key", ""),
        "raydar_user_id": extra.get("raydar_user_id", ""),
        "ghl_user_name": extra.get("ghl_user_name", ""),
    }
    return row


def _attribute(identities, alias_index, powerline_rows, raydar_rows):
    owners: dict[str, dict[str, int]] = {}
    unmapped_powerline: dict[str, int] = {}
    unmapped_raydar: dict[str, int] = {}

    def bump(bucket: dict[str, int], owner_id: str, field: str, count: int) -> None:
        row = bucket.setdefault(owner_id, {"powerline_dials": 0, "doors_knocked": 0})
        row[field] += count

    for label, count in powerline_rows:
        owner_id = recap.map_label_to_owner_fuzzy(label, alias_index, identities)
        if owner_id:
            bump(owners, owner_id, "powerline_dials", count)
        else:
            unmapped_powerline[label] = unmapped_powerline.get(label, 0) + count

    raydar_to_owner = {
        row["raydar_user_id"]: owner_id
        for owner_id, row in identities.items()
        if row.get("raydar_user_id")
    }
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
    def test_ghl_owner_bucket_joins_powerline_exact_and_raydar_short_name(self):
        """Live bug: Powerline label equals owner_label but join only searched roster."""
        user_names = {
            APRIL_OWNER_ID: APRIL_OWNER_LABEL,
            RUEBEN_OWNER_ID: "Rueben Hand",
        }
        # Rueben is on roster (8/25 mapped). April is not.
        roster = {
            RUEBEN_OWNER_ID: _roster_row(RUEBEN_OWNER_ID, "Rueben Hand", raydar_user_id="ray-rueben"),
        }
        extra_labels = {APRIL_OWNER_ID: APRIL_OWNER_LABEL}
        identities = recap.collect_owner_identities(roster, user_names, extra_labels)
        alias_index = recap.build_owner_alias_index(identities)

        owners, unmapped_pl, unmapped_rd = _attribute(
            identities,
            alias_index,
            [
                (APRIL_OWNER_LABEL, POWERLINE_APRIL_DIALS),
                (WILLIAM_LABEL, POWERLINE_WILLIAM_DIALS),
            ],
            [
                (APRIL_RAYDAR_LABEL, RAYDAR_APRIL_KNOCKS, "ray-april-short"),
                ("Sawyer Vermeesch", 125, "ray-sawyer"),
            ],
        )

        april = owners[APRIL_OWNER_ID]
        self.assertEqual(april["powerline_dials"], POWERLINE_APRIL_DIALS)
        self.assertEqual(april["doors_knocked"], RAYDAR_APRIL_KNOCKS)
        self.assertNotIn(APRIL_OWNER_LABEL, unmapped_pl)
        self.assertNotIn(APRIL_RAYDAR_LABEL, unmapped_rd)

        william = owners[WILLIAM_OWNER_ID]
        self.assertEqual(william["powerline_dials"], POWERLINE_WILLIAM_DIALS)
        self.assertNotIn(WILLIAM_LABEL, unmapped_pl)

        self.assertEqual(unmapped_rd.get("Sawyer Vermeesch"), 125)

    def test_roster_without_role_rep_still_joins_raydar_user_id(self):
        roster = {
            APRIL_OWNER_ID: _roster_row(
                APRIL_OWNER_ID,
                APRIL_OWNER_LABEL,
                raydar_user_id="ray-april",
            ),
        }
        identities = recap.collect_owner_identities(roster, {}, None)
        alias_index = recap.build_owner_alias_index(identities)
        owners, unmapped_pl, unmapped_rd = _attribute(
            identities,
            alias_index,
            [(APRIL_OWNER_LABEL, POWERLINE_APRIL_DIALS)],
            [(APRIL_RAYDAR_LABEL, RAYDAR_APRIL_KNOCKS, "ray-april")],
        )
        april = owners[APRIL_OWNER_ID]
        self.assertEqual(april["powerline_dials"], POWERLINE_APRIL_DIALS)
        self.assertEqual(april["doors_knocked"], RAYDAR_APRIL_KNOCKS)
        self.assertEqual(unmapped_pl, {})
        self.assertEqual(unmapped_rd, {})

    def test_short_name_stays_unmapped_when_two_hyphenated_matches(self):
        other_id = "otherAprilId00000001"
        identities = recap.collect_owner_identities(
            {
                APRIL_OWNER_ID: _roster_row(APRIL_OWNER_ID, APRIL_OWNER_LABEL),
                other_id: _roster_row(other_id, "April Cornell"),
            },
            {},
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


class RosterLoadTests(unittest.TestCase):
    def test_load_rep_roster_keeps_closer_without_role_rep(self):
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
                            "raydar_user_id": "ray-april",
                            "role": "closer",
                        },
                    )
                ]

        class DB:
            def __init__(self):
                self.collection_name = ""

            def collection(self, name: str):
                self.collection_name = name
                return Collection()

        db = DB()
        loaded = recap.load_rep_roster(db, {})
        self.assertEqual(db.collection_name, "roster_people_v1")
        self.assertEqual(loaded[APRIL_OWNER_ID]["label"], APRIL_OWNER_LABEL)
        self.assertEqual(loaded[APRIL_OWNER_ID]["raydar_user_id"], "ray-april")

    def test_source_does_not_require_role_rep_for_identity(self):
        self.assertNotIn('if role != "rep" and "rep" not in categories:', RECAP_SRC)
        self.assertIn("ghl_user_id", RECAP_SRC)
        self.assertIn("raydar_user_id", RECAP_SRC)
        self.assertIn("identity_name_keys", RECAP_SRC)


class ContractGuardTests(unittest.TestCase):
    def test_does_not_change_company_sales_or_sc_overview_pie(self):
        self.assertIn("normalize_completed_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("is_completed_sale_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("sold_date", SALES_SRC.lower())
        self.assertNotIn("identity_name_keys", SC_OVERVIEW_SRC)
        self.assertNotIn("identity_name_keys", SALES_SRC)


if __name__ == "__main__":
    unittest.main()
