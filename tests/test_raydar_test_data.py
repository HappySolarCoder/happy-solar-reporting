# -*- coding: utf-8 -*-

"""App Review test data is left out of every Raydar metric."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from raydar_test_data import (  # noqa: E402
    average_knocks_per_setter,
    is_excluded_raydar_record,
    is_raydar_test_record,
    setter_excluded_from_metrics,
)

if "google.cloud" not in sys.modules:
    cloud = types.ModuleType("google.cloud")
    cloud.firestore = MagicMock()
    google_mod = types.ModuleType("google")
    google_mod.cloud = cloud
    oauth2 = types.ModuleType("google.oauth2")
    oauth2.service_account = MagicMock()
    sys.modules["google"] = google_mod
    sys.modules["google.cloud"] = cloud
    sys.modules["google.cloud.firestore"] = cloud.firestore
    sys.modules["google.oauth2"] = oauth2
    sys.modules["google.oauth2.service_account"] = oauth2.service_account


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


doors = load_module("raydar_doors_knocked_test_data", METRICS / "raydar_doors_knocked.py")
weekly = load_module("fma_weekly_review_test_data", METRICS / "fma_weekly_review.py")


class Snap:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class Col:
    def __init__(self, docs: list[Snap]):
        self.docs = docs

    def where(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, count: int):
        return Col(self.docs[:count])

    def stream(self):
        return iter(self.docs)


class Db:
    def __init__(self, collections: dict[str, list[Snap]]):
        self.collections = collections

    def collection(self, name: str):
        return Col(self.collections.get(name, []))


REAL_USER = "real-setter"
TEST_USER = "app-review-setter"
WHEN = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


def _doors_db(leads: list[Snap], users: list[Snap]) -> Db:
    return Db(
        {
            "raydar_leads_v1": leads,
            "raydar_users_v1": users,
            "raydar_dispositions_v1": [
                Snap("door", {"name": "Not Home", "countsAsDoorKnock": True}),
            ],
        }
    )


def _lead(doc_id: str, actor: str, **extra) -> Snap:
    data = {
        "status": "door",
        "dispositionedAt": WHEN,
        "dispositionHistory": [{"userId": actor}],
        "claimedBy": actor,
    }
    data.update(extra)
    return Snap(doc_id, data)


def _user(doc_id: str, name: str, **extra) -> Snap:
    data = {"name": name}
    data.update(extra)
    return Snap(doc_id, data)


class RaydarTestRecordTests(unittest.TestCase):
    def test_is_test_account_true(self):
        self.assertTrue(is_raydar_test_record({"isTestAccount": True, "name": "App Review TEST"}))

    def test_test_data_true(self):
        self.assertTrue(is_raydar_test_record({"testData": True}))

    def test_nested_test_data_is_test_account(self):
        self.assertTrue(is_raydar_test_record({"testData": {"isTestAccount": True}, "name": "App Review TEST"}))

    def test_team_test(self):
        self.assertTrue(is_raydar_test_record({"team": "TEST", "name": "App Review TEST"}))

    def test_id_prefix(self):
        self.assertTrue(is_raydar_test_record({"id": "TEST-appreview-lead-1"}))
        self.assertTrue(is_raydar_test_record({}, doc_id="TEST-appreview-lead-1"))

    def test_lead_id_prefix(self):
        self.assertTrue(is_raydar_test_record({"leadId": "TEST-appreview-lead-8"}))

    def test_territory_id_prefix(self):
        self.assertTrue(is_raydar_test_record({"territoryId": "TEST-appreview-territory"}))

    def test_user_id_prefix(self):
        self.assertTrue(is_raydar_test_record({"userId": "TEST-appreview-user"}))

    def test_source_test_appreview(self):
        self.assertTrue(is_raydar_test_record({"source": "test-appreview"}))

    def test_real_record_stays(self):
        self.assertFalse(
            is_raydar_test_record(
                {
                    "id": "lead-100",
                    "leadId": "lead-100",
                    "territoryId": "buffalo-1",
                    "userId": REAL_USER,
                    "team": "Buffalo",
                    "source": "doors",
                    "isTestAccount": False,
                    "testData": False,
                }
            )
        )

    def test_knock_by_test_setter_drops(self):
        lead = {
            "id": "live-lead",
            "source": "doors",
            "claimedBy": REAL_USER,
            "dispositionHistory": [{"userId": TEST_USER}, {"userId": REAL_USER}],
        }
        self.assertFalse(is_raydar_test_record(lead))
        self.assertTrue(
            is_excluded_raydar_record(lead, doc_id="live-lead", test_user_ids={TEST_USER})
        )

    def test_denominator_excludes_test_setter(self):
        rows = [
            {"display_name": "Sam", "raydar_user_id": REAL_USER, "knocks": 10, "team": "Buffalo"},
            {"display_name": "App Review TEST", "raydar_user_id": TEST_USER, "knocks": 8},
        ]
        # 10 / 1. Counting the TEST setter would make the denominator 2 and the average 9.
        self.assertTrue(setter_excluded_from_metrics(rows[1], {TEST_USER}))
        self.assertEqual(average_knocks_per_setter(rows, {TEST_USER}), 10.0)
        self.assertEqual(len([row for row in rows if not setter_excluded_from_metrics(row, {TEST_USER})]), 1)


class DoorsKnockedFilterTests(unittest.TestCase):
    def test_test_setter_knocks_leave_totals_and_leaderboard(self):
        db = _doors_db(
            [
                _lead("live-1", REAL_USER),
                _lead("TEST-appreview-lead-1", TEST_USER, source="test-appreview"),
                _lead("live-touched-by-reviewer", TEST_USER),
            ],
            [
                _user(REAL_USER, "Sam"),
                _user(TEST_USER, "App Review TEST", team="TEST", isTestAccount=True),
            ],
        )
        payload = doors.build_payload(db, 2026, 10, start="2026-10-01", end="2026-10-01")
        knocks = payload["breakdowns"]["knocks_by_actor"]
        self.assertEqual(payload["result"], 1)
        self.assertEqual(knocks, {REAL_USER: 1})
        self.assertEqual([row["userId"] for row in payload["top_knockers"]], [REAL_USER])
        self.assertNotIn(TEST_USER, payload["users"])
        ranked = [{"userId": uid, "knocks": count} for uid, count in knocks.items()]
        self.assertEqual(average_knocks_per_setter(ranked), 1.0)


class WeeklyReviewDenominatorTests(unittest.TestCase):
    def test_test_setter_is_out_of_the_people_denominator(self):
        db = Db(
            {
                "ghl_contacts_v2": [],
                "ghl_pipelines_v2": [],
                "ghl_users_v2": [],
                "ghl_opportunities_v2": [],
                "raydar_dispositions_v1": [
                    Snap("door", {"name": "Not Home", "countsAsDoorKnock": True}),
                ],
                "raydar_users_v1": [
                    _user(REAL_USER, "Sam"),
                    _user(TEST_USER, "App Review TEST", team="TEST", testData={"isTestAccount": True}),
                ],
                "roster_people_v1": [
                    Snap(
                        "setter:sam",
                        {
                            "role": "setter",
                            "person_key": "setter:sam",
                            "display_name": "Sam",
                            "ghl_setter_last_name": "Sam",
                            "raydar_user_id": REAL_USER,
                        },
                    ),
                    Snap(
                        "setter:app-review",
                        {
                            "role": "setter",
                            "person_key": "setter:app-review",
                            "display_name": "App Review TEST",
                            "ghl_setter_last_name": "Test",
                            "raydar_user_id": TEST_USER,
                            "team": "TEST",
                        },
                    ),
                ],
                "raydar_leads_v1": [
                    _lead("live-1", REAL_USER),
                    _lead("TEST-appreview-lead-2", REAL_USER, source="test-appreview", territoryId="TEST-appreview-territory"),
                    _lead("live-2", TEST_USER),
                ],
            }
        )
        payload = weekly.build_payload(db, start="2026-10-01", end="2026-10-01")
        people = payload["people"]
        self.assertEqual([person["display_name"] for person in people], ["Sam"])
        self.assertEqual(payload["totals"]["knocks"], 1)
        self.assertEqual(people[0]["knocks"], 1)
        averaged = average_knocks_per_setter(
            [{"raydar_user_id": person["raydar_user_id"], "knocks": person["knocks"]} for person in people]
        )
        self.assertEqual(averaged, 1.0)


if __name__ == "__main__":
    unittest.main()
