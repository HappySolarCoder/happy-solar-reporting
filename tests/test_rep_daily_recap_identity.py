# -*- coding: utf-8 -*-

"""Rep Daily Recap identity join — April 8/24 warehouse lock.

Warehouse + live chi 2026-08-24:
- Owner IJrbhufMjsmwdxf252sb April Cornell-DeAngelis: Sit 1, powerline 0, doors 0.
- Unmapped Powerline "April Cornell-DeAngelis" 40.
- Unmapped Raydar "April Cornell" 17 (10 not-home, 5 not-interested,
  2 spoke-with-non-homeowner). Not pins. Not Jeff's ~20.
- April is NOT in roster_people_v1 (23 rows: 9 rep / 14 setter).
- ghl_users_v2 IJrbhufMjsmwdxf252sb email april@happyslr.com.
- raydar_users_v1 jLZoREmBADZmWjoUIiwdAf2BnsE3 name April Cornell,
  same email, role closer.

Do not invent 20 doors. Do not dump setters onto owner rows.
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
WILLIAM_OWNER_ID = "0fhsjcmlntce0cpjyfhj"
WILLIAM_LABEL = "William Breen"
RUEBEN_OWNER_ID = "f4udrh1LuU0TEkF4ZFSj"
POWERLINE_APRIL_DIALS = 40
RAYDAR_APRIL_KNOCKS = 17
POWERLINE_WILLIAM_DIALS = 56
RAYDAR_SAWYER_KNOCKS = 125


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
    }


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

    def test_source_keeps_role_rep_filter_and_on_page_join(self):
        self.assertIn('if role != "rep" and "rep" not in categories:', RECAP_SRC)
        self.assertIn("build_raydar_to_owner", RECAP_SRC)
        self.assertIn("normalize_email", RECAP_SRC)
        self.assertIn("identity_name_keys", RECAP_SRC)
        self.assertIn("owners already on the page", RECAP_SRC)


class ContractGuardTests(unittest.TestCase):
    def test_does_not_change_company_sales_or_sc_overview_pie(self):
        self.assertIn("normalize_completed_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("is_completed_sale_outcome_bucket", SC_OVERVIEW_SRC)
        self.assertIn("sold_date", SALES_SRC.lower())
        self.assertNotIn("identity_name_keys", SC_OVERVIEW_SRC)
        self.assertNotIn("identity_name_keys", SALES_SRC)


if __name__ == "__main__":
    unittest.main()
