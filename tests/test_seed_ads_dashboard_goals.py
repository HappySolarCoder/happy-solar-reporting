# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.append(path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


seed = load_module("seed_ads_dashboard_goals", ROOT / "scripts" / "seed_ads_dashboard_goals.py")
metric = load_module("ads_dashboard_metric_for_seed", METRICS / "ads_dashboard.py")


def _deep_merge(base: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        current = base.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            _deep_merge(current, value)
        else:
            base[key] = value


def _apply_dotted(document: dict, updates: dict) -> None:
    for key, value in updates.items():
        cursor = document
        parts = key.split(".")
        for part in parts[:-1]:
            nxt = cursor.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cursor[part] = nxt
            cursor = nxt
        cursor[parts[-1]] = value


class Snap:
    def __init__(self, data, exists: bool):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class Doc:
    def __init__(self, store: "FakeDB", month: str):
        self.store = store
        self.month = month

    def get(self):
        if self.month not in self.store.docs:
            return Snap(None, False)
        return Snap(self.store.docs[self.month], True)

    def set(self, data, merge=False):
        self.store.sets.append(data)
        self.store.merges.append(merge)
        incoming = json.loads(json.dumps(data))
        if merge and self.month in self.store.docs:
            _deep_merge(self.store.docs[self.month], incoming)
        else:
            self.store.docs[self.month] = incoming

    def update(self, data):
        self.store.updates.append(dict(data))
        current = self.store.docs.setdefault(self.month, {})
        _apply_dotted(current, data)


class FakeDB:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.sets: list[dict] = []
        self.merges: list[bool] = []
        self.updates: list[dict] = []
        self.collections: list[str] = []

    def collection(self, name):
        self.collections.append(name)
        return self

    def document(self, month):
        return Doc(self, month)


class SeedAdsDashboardGoalsTests(unittest.TestCase):
    def test_dry_run_prints_october_doc_and_does_not_connect(self):
        buf = io.StringIO()
        with patch.object(seed, "get_db", side_effect=AssertionError("connected")):
            with redirect_stdout(buf):
                code = seed.main([])
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Dry run only", text)
        payload = json.loads(text.split("Dry run only", 1)[0])
        self.assertEqual(payload["month"], "2026-10")
        goals = payload["goals"]["ads_dashboard"]
        self.assertEqual(goals["leads"], 30)
        self.assertEqual(goals["opps"], 10)
        self.assertEqual(goals["demos"], 6)
        self.assertEqual(goals["sales"], 3)
        self.assertEqual(goals["spend"], 1800)
        self.assertEqual(goals["budget"], 1800)
        self.assertEqual(goals["cost_per_lead"], metric.COST_PER_LEAD_GOAL)
        self.assertEqual(goals["cost_per_opp"], metric.COST_PER_OPP_GOAL)
        self.assertEqual(goals["cost_per_demo"], metric.COST_PER_DEMO_GOAL)
        self.assertEqual(goals["cost_per_sale"], metric.COST_PER_SALE_GOAL)
        parsed = metric.goals_from_doc(payload, "2026-10")
        self.assertEqual(parsed["spend"], 1800)
        self.assertEqual(parsed["leads"], 30)
        self.assertEqual(parsed["opps"], 10)
        self.assertEqual(parsed["demos"], 6)
        self.assertEqual(parsed["sales"], 3)
        self.assertEqual(parsed["cost_per_lead"], 25)
        self.assertEqual(parsed["cost_per_opp"], 100)
        self.assertEqual(parsed["cost_per_demo"], 300)
        self.assertEqual(parsed["cost_per_sale"], 600)

    def test_apply_refuses_without_admin_env_and_hides_secrets(self):
        secret = "super-secret-token"
        env = {key: "" for key in seed._ADMIN_ENV}
        env["FIREBASE_SERVICE_ACCOUNT_JSON"] = json.dumps({"private_key": secret})
        buf = io.StringIO()
        err = io.StringIO()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(seed, "get_db", side_effect=AssertionError("connected")):
                with redirect_stdout(buf), redirect_stderr(err):
                    code = seed.main(["--apply"])
        self.assertEqual(code, 2)
        combined = buf.getvalue() + err.getvalue()
        self.assertNotIn(secret, combined)
        self.assertNotIn("private_key", combined)
        self.assertIn("SETTINGS_PASSWORD", combined)

    def test_apply_is_idempotent_and_keeps_other_people(self):
        db = FakeDB()
        db.docs["2026-10"] = {
            "month": "2026-10",
            "goals": {"setter:jane": {"sales_goal": 3}},
        }
        self.assertEqual(seed.apply_document(db), "updated")
        self.assertEqual(db.docs["2026-10"]["goals"]["setter:jane"]["sales_goal"], 3)
        written = db.docs["2026-10"]["goals"]["ads_dashboard"]
        self.assertEqual(written["leads"], 30)
        self.assertEqual(written["spend"], 1800)
        self.assertEqual(seed.apply_document(db), "unchanged")
        self.assertEqual(len(db.updates), 1)
        self.assertEqual(db.collections, ["goals_monthly_v1", "goals_monthly_v1"])

    def test_apply_creates_a_missing_doc_once(self):
        db = FakeDB()
        self.assertEqual(seed.apply_document(db), "created")
        self.assertEqual(len(db.sets), 1)
        self.assertEqual(db.merges, [True])
        self.assertEqual(db.docs["2026-10"]["goals"]["ads_dashboard"]["opps"], 10)
        self.assertEqual(seed.apply_document(db), "unchanged")
        self.assertEqual(len(db.sets), 1)

    def test_missing_doc_set_merges_with_an_admin_settings_write(self):
        class RacingDoc(Doc):
            def get(self):
                missing = self.month not in self.store.docs
                snap = Snap(None, False) if missing else Snap(self.store.docs[self.month], True)
                if missing:
                    self.store.docs[self.month] = {
                        "month": self.month,
                        "note": "from admin",
                        "goals": {"setter:jane": {"sales_goal": 9}},
                    }
                return snap

        class RacingDB(FakeDB):
            def document(self, month):
                return RacingDoc(self, month)

        racing = RacingDB()
        self.assertEqual(seed.apply_document(racing), "created")
        self.assertEqual(racing.merges, [True])
        goals = racing.docs["2026-10"]["goals"]
        self.assertEqual(goals["setter:jane"]["sales_goal"], 9)
        self.assertEqual(goals["ads_dashboard"]["leads"], 30)
        self.assertEqual(goals["ads_dashboard"]["cost_per_opp"], 100)
        self.assertEqual(racing.docs["2026-10"]["note"], "from admin")

    def test_apply_writes_through_get_db_without_printing_secrets(self):
        db = FakeDB()
        secret = "do-not-print"
        env = {
            "SETTINGS_PASSWORD": secret,
            "FIREBASE_SERVICE_ACCOUNT_JSON": json.dumps({"private_key": secret}),
            "GCP_PROJECT_ID": "proj",
            "FIRESTORE_DATABASE_ID": "happy-solar",
        }
        buf = io.StringIO()
        err = io.StringIO()
        with patch.dict(os.environ, env, clear=False):
            with patch.object(seed, "get_db", return_value=db) as get_db:
                with redirect_stdout(buf), redirect_stderr(err):
                    code = seed.main(["--apply"])
        self.assertEqual(code, 0)
        get_db.assert_called_once()
        self.assertIn("created goals_monthly_v1/2026-10", buf.getvalue())
        combined = buf.getvalue() + err.getvalue()
        self.assertNotIn(secret, combined)
        self.assertNotIn("private_key", combined)


if __name__ == "__main__":
    unittest.main()
