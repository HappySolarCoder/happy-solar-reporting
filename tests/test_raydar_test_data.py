# -*- coding: utf-8 -*-

"""App Review test data is left out of every Raydar metric."""

from __future__ import annotations

import ast
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
APP_REVIEW_UID = "ayuRSQAI8Tckd7HfFCr96rdBd633"
PROBE_ROLES = ("admin", "closer", "deactivated", "manager", "setter")
WHEN = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
USER_OR_LEAD_COLLECTIONS = frozenset({"raydar_users_v1", "raydar_leads_v1"})
FILTER_CALLS = frozenset({"is_raydar_test_record", "is_excluded_raydar_record"})
RAYDAR_READERS = (
    "api/metrics/fma_weekly_review.py",
    "api/metrics/raydar_doors_knocked.py",
    "api/metrics/raydar_user_roles.py",
    "api/raydar/leads.py",
    "api/raydar/stats.py",
    "api/rep_daily_recap.py",
    "api/settings_api.py",
)


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

    def test_setter_id_of_app_review_user_is_excluded(self):
        lead = {
            "id": "live-lead",
            "source": "doors",
            "team": "Buffalo",
            "claimedBy": REAL_USER,
            "setterId": APP_REVIEW_UID,
        }
        self.assertFalse(is_raydar_test_record(lead))
        self.assertTrue(
            is_excluded_raydar_record(lead, doc_id="live-lead", test_user_ids={APP_REVIEW_UID})
        )

    def test_territory_field_excludes_app_review_user(self):
        user = {"name": "App Review TEST", "territory": "TEST-appreview-territory"}
        self.assertTrue(is_raydar_test_record(user))
        self.assertTrue(is_excluded_raydar_record(user))

    def test_loose_team_source_and_numeric_flags_are_excluded(self):
        self.assertTrue(is_raydar_test_record({"team": "test"}))
        self.assertTrue(is_raydar_test_record({"team": " Test "}))
        self.assertTrue(is_raydar_test_record({"source": "Test-AppReview"}))
        self.assertTrue(is_raydar_test_record({"source": " test-appreview "}))
        self.assertTrue(is_raydar_test_record({"testData": 1}))
        self.assertTrue(is_raydar_test_record({"testData": "1"}))
        self.assertTrue(is_raydar_test_record({"isTestAccount": "yes"}))
        self.assertTrue(is_raydar_test_record({"isTestAccount": "YES"}))
        self.assertTrue(is_raydar_test_record({"isTestAccount": 1}))
        self.assertTrue(is_raydar_test_record({"isTestAccount": "true"}))
        self.assertTrue(is_raydar_test_record({"testData": {"isTestAccount": "yes"}}))
        self.assertTrue(is_raydar_test_record({"testData": {"testData": 1}}))
        self.assertTrue(is_raydar_test_record({"testData": {"testData": "1"}}))

    def test_real_lead_testing_team_and_false_flags_stay(self):
        real_lead = {
            "id": "lead-100",
            "leadId": "lead-100",
            "setterId": REAL_USER,
            "claimedBy": REAL_USER,
            "team": "Buffalo",
            "source": "doors",
            "territory": "buffalo-1",
            "isTestAccount": False,
            "testData": None,
        }
        self.assertFalse(is_raydar_test_record(real_lead))
        self.assertFalse(
            is_excluded_raydar_record(real_lead, doc_id="lead-100", test_user_ids={APP_REVIEW_UID})
        )
        self.assertFalse(is_raydar_test_record({"team": "Testing", "name": "Testing crew"}))
        self.assertFalse(is_raydar_test_record({"testData": False}))
        self.assertFalse(is_raydar_test_record({"testData": 0}))
        self.assertFalse(is_raydar_test_record({"testData": None}))
        self.assertFalse(is_raydar_test_record({"isTestAccount": False}))
        self.assertFalse(is_raydar_test_record({"isTestAccount": 0}))
        self.assertFalse(is_raydar_test_record({"isTestAccount": "no"}))
        self.assertFalse(is_raydar_test_record({"testData": {"isTestAccount": False, "testData": 0}}))

    def test_six_test_users_leave_the_average(self):
        rows = [
            {"display_name": "Sam", "raydar_user_id": REAL_USER, "knocks": 20, "team": "Buffalo"},
            {
                "display_name": "App Review TEST",
                "raydar_user_id": APP_REVIEW_UID,
                "userId": APP_REVIEW_UID,
                "knocks": 8,
                "team": " test ",
                "isTestAccount": "yes",
                "testData": True,
                "role": "setter",
            },
        ]
        probe_flags = (
            {"testData": 1},
            {"testData": "1"},
            {"isTestAccount": True, "testData": True},
            {"team": "Test", "testData": {"isTestAccount": "yes"}},
            {"team": "TEST", "isTestAccount": 1, "testData": {"testData": "1"}},
        )
        test_ids = {APP_REVIEW_UID}
        for role, flags in zip(PROBE_ROLES, probe_flags):
            uid = f"TEST-probe-{role}"
            test_ids.add(uid)
            rows.append(
                {
                    "display_name": uid,
                    "raydar_user_id": uid,
                    "userId": uid,
                    "knocks": 4,
                    "role": role,
                    **flags,
                }
            )
        self.assertEqual(len(test_ids), 6)
        kept = [row for row in rows if not setter_excluded_from_metrics(row, test_ids)]
        self.assertEqual([row["display_name"] for row in kept], ["Sam"])
        self.assertEqual(average_knocks_per_setter(rows, test_ids), 20.0)


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


def _bound_collection_names(tree: ast.AST) -> set[str]:
    """Names whose value is raydar_users_v1 or raydar_leads_v1."""

    bound: set[str] = set()

    def take(target: ast.AST, value: ast.AST | None) -> None:
        if not isinstance(value, ast.Constant) or value.value not in USER_OR_LEAD_COLLECTIONS:
            return
        if isinstance(target, ast.Name):
            bound.add(target.id)
        elif isinstance(target, ast.Attribute):
            bound.add(target.attr)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                take(target, node.value)
        elif isinstance(node, ast.AnnAssign):
            take(node.target, node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional = list(args.posonlyargs) + list(args.args)
            defaults = list(args.defaults)
            for arg, default in zip(positional[-len(defaults):], defaults):
                take(ast.Name(id=arg.arg, ctx=ast.Load()), default)
            for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                take(ast.Name(id=arg.arg, ctx=ast.Load()), default)
    return bound


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _reads_raydar_users_or_leads(tree: ast.AST) -> bool:
    """True when the file queries raydar_users_v1 or raydar_leads_v1.

    raydar_dispositions_v1 is the disposition-type catalog. Reading that list
    does not count.
    """

    bound = _bound_collection_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _call_name(node.func) != "collection":
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and arg.value in USER_OR_LEAD_COLLECTIONS:
            return True
        if isinstance(arg, ast.Name) and arg.id in bound:
            return True
        if isinstance(arg, ast.Attribute) and arg.attr in bound:
            return True
    return False


def _calls_test_filter(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in FILTER_CALLS:
            return True
    return False


class RaydarReaderGuardTests(unittest.TestCase):
    def test_disposition_list_is_exempt(self):
        source = 'def load(db):\n    return list(db.collection("raydar_dispositions_v1").stream())\n'
        self.assertFalse(_reads_raydar_users_or_leads(ast.parse(source)))

    def test_every_user_or_lead_reader_filters_test_data(self):
        readers: list[str] = []
        missing: list[str] = []
        for path in sorted(API.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if not _reads_raydar_users_or_leads(tree):
                continue
            relative = path.relative_to(ROOT).as_posix()
            readers.append(relative)
            if not _calls_test_filter(tree):
                missing.append(relative)
        self.assertEqual(missing, [])
        for expected in RAYDAR_READERS:
            self.assertIn(expected, readers)
        self.assertNotIn("api/time_on_doors.py", readers)
        self.assertNotIn("api/fma_dashboard.py", readers)


if __name__ == "__main__":
    unittest.main()
