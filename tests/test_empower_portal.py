# -*- coding: utf-8 -*-

"""EmPower+ Portal nav, metrics, ingest, and role gate. No live Firestore."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "nyhep_empower_portal.json"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))


def load_from_path(name: str, path: Path):
    """Load this file even when api/metrics is ahead of api on sys.path."""
    resolved = path.resolve()
    cached = sys.modules.get(name)
    cached_file = Path(getattr(cached, "__file__", "") or "")
    if cached is not None and cached_file.resolve() != resolved:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Older suites insert api/metrics at sys.path[0], where a module named
# empower_portal used to shadow api/empower_portal.py. Bind the page from
# its path so this file cannot pick up that collision.
empower_portal = load_from_path("hs_empower_portal_page", API / "empower_portal.py")
ingest = load_from_path("hs_empower_portal_ingest", API / "empower_portal_ingest.py")
metrics = load_from_path("hs_empower_portal_metrics", API / "metrics" / "empower_portal_metrics.py")
bloom_frame_probe = load_from_path("bloom_frame_probe", ROOT / "tests" / "bloom_frame_probe.py")
# The page imports the ingest by its path name inside load_view.
sys.modules["empower_portal_ingest"] = ingest

import dashboard_nav as nav
from copilot.auth import identity_for_chat, sign_bloom_token


FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
INGEST_SECRET = "ingest-test-secret"
BLOOM_SECRET = "bloom-test-secret"
SETTINGS_PASSWORD = "settings-test-password"
FRAME_ANCESTORS = (
    "frame-ancestors 'self' https://bloom.happyslr.com "
    "https://*.happyslr.com https://happy-solar-bloom-portal.vercel.app"
)
BLOOM_TWO = "https://happy-solar-bloom-portal.vercel.app,https://bloom.happyslr.com"
BLOOM_VERCEL = "https://happy-solar-bloom-portal.vercel.app"
BLOOM_PROD = "https://bloom.happyslr.com"
REPORTING_REFERRER = "https://database-migration-chi.vercel.app/api/company_overview"
SHELL_TOKEN = "abcdefghij.klmnopqrstuvwxyz"
CUSTOMERS = [row["customer"] for row in FIXTURE["projects"]]
WAITING_DUE_ORDER = [
    "E-1001",
    "E-1004",
    "E-1002",
    "E-1005",
    "E-1006",
    "E-1007",
    "E-1003",
    "E-1009",
    "E-1008",
]


def invoke(module, method: str, path: str, headers=None, body: bytes = b""):
    cls = module.handler
    inst = cls.__new__(cls)
    inst.path = path
    inst.headers = headers or {}
    inst.rfile = BytesIO(body)
    inst.wfile = BytesIO()
    captured = {}

    def send_header(key, value, captured=captured):
        captured.setdefault("headers", {})[key] = value

    inst.send_response = lambda status, captured=captured: captured.__setitem__("status", status)
    inst.send_header = send_header
    inst.end_headers = lambda: None
    getattr(inst, f"do_{method}")()
    return captured["status"], captured.get("headers", {}), inst.wfile.getvalue()


def _now_claims(role: str) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "aud": "goose-copilot",
        "exp": now + 300,
        "iat": now - 10,
        "iss": "happy-solar-bloom",
        "role": role,
        "status": "active",
        "sub": "user_test",
        "v": 1,
    }


def bloom_headers(role: str, *, secret: str = BLOOM_SECRET, claims: dict | None = None) -> dict:
    token = sign_bloom_token(claims or _now_claims(role), secret)
    return {"Authorization": f"Bearer {token}"}


def basic_headers(password: str = SETTINGS_PASSWORD, user: str = "qa") -> dict:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class FakeDb:
    def __init__(self):
        self.docs = {}
        self.writes = []

    def collection(self, name):
        return _FakeCollection(self, name)


class _FakeCollection:
    def __init__(self, db: FakeDb, name: str):
        self.db = db
        self.name = name

    def document(self, doc_id):
        return _FakeDoc(self.db, self.name, doc_id)


class _FakeDoc:
    def __init__(self, db: FakeDb, collection: str, doc_id: str):
        self.db = db
        self.key = (collection, doc_id)

    def get(self):
        return _FakeSnap(self.db.docs.get(self.key))

    def set(self, payload, merge=False):
        self.db.writes.append({"key": self.key, "merge": merge})
        if merge and isinstance(self.db.docs.get(self.key), dict):
            stored = dict(self.db.docs[self.key])
            stored.update(payload)
            self.db.docs[self.key] = stored
        else:
            self.db.docs[self.key] = json.loads(json.dumps(payload))


class _FakeSnap:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        if not isinstance(self._data, dict):
            return {}
        return json.loads(json.dumps(self._data))


class NavTests(unittest.TestCase):
    def test_empower_portal_is_in_other_and_embed_labels_stay(self):
        labels = [label for label, _slug, _keys in nav.EMBED_MENUS]
        self.assertEqual(labels, ["Company", "Sales", "Lead Gen", "Proj. Man.", "Contests", "Other"])
        other_nav = next(items for label, items in nav.NAV_GROUPS if label == "OTHER")
        other_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Other")
        entry = ("empower_portal", "EmPower+ Portal", "/api/empower_portal")
        self.assertIn(entry, other_nav)
        self.assertIn("empower_portal", other_keys)
        plan = nav.embed_menu_plan()
        other_rows = next(rows for label, _slug, rows in plan if label == "Other")
        self.assertIn(entry, other_rows)
        html = nav.render_dashboard_nav("empower_portal")
        self.assertIn('class="navlink active" href="/api/empower_portal"', html)
        self.assertIn("EmPower+ Portal", html)
        self.assertIn('aria-current="true"', _group_button(html, "Other"))
        self.assertIn(
            'class="oc-embed-link active" href="/api/empower_portal" aria-current="page"',
            html,
        )


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.view = metrics.build_portal_view(FIXTURE)

    def test_fixture_counts_and_overdue_uses_as_of(self):
        self.assertEqual(len(FIXTURE["projects"]), 16)
        metrics_row = self.view["metrics"]
        self.assertEqual(metrics_row["total"], 16)
        self.assertEqual(metrics_row["open"], 13)
        self.assertEqual(metrics_row["closed"], 1)
        self.assertEqual(metrics_row["cancelled"], 2)
        self.assertEqual(metrics_row["waitingOnUs"], 9)
        self.assertEqual(metrics_row["overdue"], 1)
        self.assertEqual(metrics_row["overdueTone"], "danger")
        self.assertEqual(self.view["asOf"], "2026-11-17")
        self.assertEqual(self.view["timezone"], "America/Phoenix")
        overdue = next(row for row in self.view["waiting"] if row["tone"] == "danger")
        self.assertEqual(overdue["id"], "E-1001")
        self.assertEqual(overdue["due"], "11/4/2026")
        self.assertEqual(overdue["dueLabel"], "11/4/2026 overdue")
        self.assertEqual(self.view["filters"], {"Open": 13, "Closed": 1, "Cancelled": 2, "All": 16})

        before_today = {
            "snapshot": "2026-11-01_am",
            "checkedAt": "Sat Nov 1, 9:00 AM Phoenix",
            "projects": [
                {
                    "id": "E-1",
                    "customer": "Future Due",
                    "status": "Open",
                    "step": "Contractor Assignment",
                    "onTodo": True,
                    "due": "11/4/2026",
                }
            ],
        }
        early = metrics.build_portal_view(before_today)
        self.assertEqual(early["asOf"], "2026-11-01")
        self.assertEqual(early["metrics"]["overdue"], 0)
        self.assertEqual(early["waiting"][0]["tone"], "warning")

        after_today = {
            "snapshot": "2026-12-01_pm",
            "checkedAt": "Tue Dec 1, 9:00 AM Phoenix",
            "projects": [
                {
                    "id": "E-9",
                    "customer": "Was Future",
                    "status": "Open",
                    "step": "Contractor Assignment",
                    "onTodo": True,
                    "due": "11/20/2026",
                }
            ],
        }
        later = metrics.build_portal_view(after_today)
        self.assertEqual(later["metrics"]["overdue"], 1)
        self.assertEqual(later["waiting"][0]["dueLabel"], "11/20/2026 overdue")
        self.assertEqual(metrics.snapshot_as_of("2026-12-01_pm"), metrics.parse_due("12/1/2026"))

    def test_pipeline_sort_due_sort_tiers_and_history_counts(self):
        steps = [row["step"] for row in self.view["stages"]]
        self.assertEqual(steps, list(metrics.PIPELINE) + ["Portal Exception"])
        self.assertEqual(self.view["metrics"]["pastWorkscope"], 6)
        self.assertEqual([row["id"] for row in self.view["waiting"]], WAITING_DUE_ORDER)
        tones = {row["id"]: row["tone"] for row in self.view["waiting"]}
        self.assertEqual(tones["E-1001"], "danger")
        self.assertEqual(tones["E-1004"], "warning")
        self.assertEqual(tones["E-1006"], "warning")
        self.assertEqual(tones["E-1007"], "")
        self.assertEqual(self.view["waiting"][0]["stepLabel"], "Contractor Assignment (Pending)")
        by_id = {row["id"]: row for row in self.view["enrollments"]}
        self.assertEqual(by_id["E-1005"]["stepLabel"], "Workscope Submission (Submitted)")
        self.assertEqual(by_id["E-1014"]["status"], "Closed")
        self.assertEqual(by_id["E-1014"]["statusTone"], "success")
        self.assertEqual(by_id["E-1014"]["installer"], "Not assigned")
        self.assertEqual(by_id["E-1014"]["tier"], "EmPower+")
        self.assertEqual(by_id["E-1016"]["tier"], "EmPower+")
        self.assertEqual(by_id["E-1003"]["tier"], "Market Rate")
        self.assertEqual(by_id["E-1008"]["installer"], "Not assigned")
        self.assertEqual(
            [row["snapshot"] for row in self.view["history"]],
            ["2026-11-17_pm", "2026-11-16_pm"],
        )
        self.assertEqual([row["changeCount"] for row in self.view["history"]], [3, 1])
        self.assertEqual(metrics.history_change_count([{"id": "E-1"}, {"id": "E-2"}]), 2)
        self.assertEqual(metrics.history_change_count(3), 3)
        self.assertEqual(metrics.normalize_status("completed"), "Closed")
        self.assertEqual(metrics.normalize_status("canceled"), "Cancelled")
        encoded = json.dumps(self.view).lower()
        self.assertNotIn("phone", encoded)
        self.assertNotIn("email", encoded)

    def test_enrollment_stage_is_step_and_status(self):
        view = metrics.build_portal_view(
            {
                "snapshot": "2026-11-17_am",
                "checkedAt": "check",
                "projects": [
                    {
                        "id": "E-20",
                        "customer": "Stage Example",
                        "status": "Open",
                        "step": "Workscope Submission",
                        "stepStatus": "New",
                        "onTodo": True,
                    },
                    {
                        "id": "E-21",
                        "customer": "No Status",
                        "status": "Open",
                        "step": "Install Started",
                        "stepStatus": "",
                    },
                ],
            }
        )
        by_id = {row["id"]: row for row in view["enrollments"]}
        self.assertEqual(by_id["E-20"]["stepLabel"], "Workscope Submission (New)")
        self.assertEqual(by_id["E-21"]["stepLabel"], "Install Started")
        self.assertEqual(view["waiting"][0]["stepLabel"], "Workscope Submission (New)")


class IngestTests(unittest.TestCase):
    def _post(self, payload, headers):
        raw = json.dumps(payload).encode("utf-8")
        sent = dict(headers)
        sent["Content-Length"] = str(len(raw))
        return invoke(ingest, "POST", "/api/empower_portal_ingest", sent, raw)

    def test_missing_secret_is_500_and_bad_secret_is_401(self):
        db = FakeDb()
        env = os.environ.copy()
        env.pop("NYHEP_INGEST_SECRET", None)
        env["UNRELATED_SECRET"] = "do-not-leak"
        with patch.dict(os.environ, env, clear=True):
            with patch.object(ingest, "get_db", return_value=db):
                status, _headers, raw = self._post(FIXTURE, {})
        self.assertEqual(status, 500)
        body = json.loads(raw.decode())
        self.assertEqual(body["error"], "missing_env")
        self.assertEqual(body["missing"], ["NYHEP_INGEST_SECRET"])
        self.assertNotIn("do-not-leak", raw.decode())
        self.assertEqual(db.writes, [])

        db = FakeDb()
        with patch.dict(os.environ, {"NYHEP_INGEST_SECRET": INGEST_SECRET}):
            with patch.object(ingest, "get_db", side_effect=AssertionError("no write")):
                missing, _, missing_raw = self._post(FIXTURE, {})
                wrong, _, wrong_raw = self._post(
                    FIXTURE, {"Authorization": "Bearer not-the-secret"}
                )
        self.assertEqual(missing, 401)
        self.assertEqual(wrong, 401)
        self.assertEqual(json.loads(missing_raw.decode())["error"], "unauthorized")
        self.assertEqual(json.loads(wrong_raw.decode())["error"], "unauthorized")
        self.assertNotIn(INGEST_SECRET, missing_raw.decode())
        self.assertNotIn(INGEST_SECRET, wrong_raw.decode())

    def test_upsert_is_idempotent_for_bearer_and_webhook_secret(self):
        db = FakeDb()
        with patch.dict(os.environ, {"NYHEP_INGEST_SECRET": INGEST_SECRET}):
            with patch.object(ingest, "get_db", return_value=db):
                first, _, first_raw = self._post(
                    FIXTURE, {"Authorization": f"Bearer {INGEST_SECRET}"}
                )
                second, _, second_raw = self._post(
                    FIXTURE, {"X-Webhook-Secret": INGEST_SECRET}
                )
        self.assertEqual(first, 200)
        self.assertEqual(second, 200)
        self.assertTrue(json.loads(first_raw.decode())["ok"])
        self.assertTrue(json.loads(second_raw.decode())["ok"])
        latest = db.docs[(ingest.LATEST_COLLECTION, ingest.LATEST_DOC_ID)]
        self.assertEqual(len(latest["history"]), 2)
        self.assertEqual(
            [row["snapshot"] for row in latest["history"]],
            ["2026-11-16_pm", "2026-11-17_pm"],
        )
        self.assertIn("updatedAt", latest)
        self.assertNotIn(INGEST_SECRET, json.dumps(list(db.docs.values())))
        snapshot_keys = [key for key in db.docs if key[0] == ingest.SNAPSHOT_COLLECTION]
        self.assertEqual(snapshot_keys, [(ingest.SNAPSHOT_COLLECTION, "2026-11-17_pm")])
        self.assertEqual(len(db.writes), 4)

    def test_phone_email_and_contact_are_rejected(self):
        db = FakeDb()
        bodies = [
            {**FIXTURE, "projects": [{**FIXTURE["projects"][0], "phone": "555-0100"}]},
            {**FIXTURE, "changes": [{"id": "E-1", "customer": "A", "email": "a@example.com"}]},
            {**FIXTURE, "projects": [{**FIXTURE["projects"][0], "contact": "Pat"}]},
        ]
        with patch.dict(os.environ, {"NYHEP_INGEST_SECRET": INGEST_SECRET}):
            with patch.object(ingest, "get_db", return_value=db):
                for body in bodies:
                    status, _, raw = self._post(body, {"X-Webhook-Secret": INGEST_SECRET})
                    self.assertEqual(status, 400, raw)
                    self.assertEqual(json.loads(raw.decode())["error"], "forbidden_fields")
        self.assertEqual(db.writes, [])

    def test_get_does_not_write(self):
        with patch.object(ingest, "get_db", side_effect=AssertionError("get_db")):
            with patch.object(ingest, "upsert_snapshot", side_effect=AssertionError("write")):
                status, headers, raw = invoke(ingest, "GET", "/api/empower_portal_ingest")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw.decode())["method"], "POST")
        self.assertEqual(headers["Cache-Control"], "no-store")


class PageTests(unittest.TestCase):
    def _env(self):
        return patch.dict(
            os.environ,
            {
                "COPILOT_BLOOM_TOKEN_SECRET": BLOOM_SECRET,
                "SETTINGS_PASSWORD": SETTINGS_PASSWORD,
            },
        )

    def test_html_has_no_customers_and_asks_bloom_for_a_token(self):
        with patch.object(empower_portal, "load_view", side_effect=AssertionError("html reads data")):
            status, headers, raw = invoke(empower_portal, "GET", "/api/empower_portal")
        html = raw.decode()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Security-Policy"], FRAME_ANCESTORS)
        self.assertNotIn("*.vercel.app", headers["Content-Security-Policy"])
        self.assertIn("https://happy-solar-bloom-portal.vercel.app", headers["Content-Security-Policy"])
        self.assertIn(metrics.TITLE, html)
        self.assertIn(metrics.SUBTITLE_LEAD, html)
        self.assertIn("Last check:", html)
        self.assertIn(metrics.SOURCE_LINE, html)
        self.assertIn(metrics.VENDOR_WARNING, html)
        self.assertIn(metrics.WAITING_DETAIL, html)
        self.assertIn("Sign in through Bloom Data Center", html)
        self.assertIn('type: "happy-solar-goose", action: "request-token"', html)
        self.assertIn('data.action !== "token"', html)
        self.assertIn('data.action === "token-unavailable"', html)
        self.assertIn('data-default="Open"', html)
        self.assertIn("Changed since the last check", html)
        self.assertIn("Open projects by stage", html)
        self.assertIn("Waiting on us, by due date", html)
        self.assertIn("All enrollments", html)
        self.assertIn("Check history", html)
        self.assertIn('href="/api/empower_portal"', html)
        self.assertIn("esc(row.stepLabel || row.step)", html)
        self.assertEqual(
            Path(empower_portal.__file__).resolve(),
            (API / "empower_portal.py").resolve(),
        )
        self.assertEqual(
            Path(metrics.__file__).resolve(),
            (API / "metrics" / "empower_portal_metrics.py").resolve(),
        )
        for name in CUSTOMERS:
            self.assertNotIn(name, html)
        page_src = (API / "empower_portal.py").read_text(encoding="utf-8")
        self.assertNotIn("identity_for_chat", page_src)
        warm = (API / "warm_cache.py").read_text(encoding="utf-8")
        self.assertNotIn("empower_portal", warm)

    def test_json_role_gate_and_headers(self):
        db = FakeDb()
        db.docs[(ingest.LATEST_COLLECTION, ingest.LATEST_DOC_ID)] = FIXTURE

        def allowed(headers):
            with self._env():
                with patch.object(ingest, "get_db", return_value=db):
                    return invoke(empower_portal, "GET", "/api/empower_portal?format=json", headers)

        status, headers, raw = allowed({})
        self.assertEqual(status, 401)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Security-Policy"], FRAME_ANCESTORS)
        self.assertNotIn("*.vercel.app", headers["Content-Security-Policy"])
        self.assertEqual(json.loads(raw.decode()), {"ok": False, "error": "unauthorized"})
        for name in CUSTOMERS:
            self.assertNotIn(name, raw.decode())

        status, _, raw = allowed({"Authorization": "Bearer not-a-token"})
        self.assertEqual(status, 401)
        self.assertNotIn("Ada Marin", raw.decode())

        expired = _now_claims("manager")
        expired["iat"] = expired["iat"] - 900
        expired["exp"] = expired["iat"] + 300
        status, _, _raw = allowed(bloom_headers("manager", claims=expired))
        self.assertEqual(status, 401)

        mapped = identity_for_chat(
            bloom_headers("closer"),
            settings_password=SETTINGS_PASSWORD,
            allowed_roles=frozenset({"settings_admin"}),
            token_secret=BLOOM_SECRET,
        )
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped.role, "settings_admin")
        for role in ("closer", "fma", "inbound"):
            status, _, raw = allowed(bloom_headers(role))
            self.assertEqual(status, 401, role)
            self.assertNotIn("projects", raw.decode())
            self.assertNotIn("E-1001", raw.decode())

        for role in ("manager", "coach"):
            status, headers, raw = allowed(bloom_headers(role))
            self.assertEqual(status, 200, role)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["Content-Security-Policy"], FRAME_ANCESTORS)
            body = json.loads(raw.decode())
            self.assertEqual(body["metrics"]["overdue"], 1)
            self.assertEqual(body["metrics"]["open"], 13)
            self.assertIn("Ada Marin", raw.decode())
            lowered = raw.decode().lower()
            self.assertNotIn("phone", lowered)
            self.assertNotIn("email", lowered)
            self.assertNotIn("@", raw.decode())

        status, _, raw = allowed(basic_headers())
        self.assertEqual(status, 200)
        body = json.loads(raw.decode())
        self.assertTrue(body["ok"])
        self.assertEqual(body["filters"]["All"], 16)
        self.assertNotIn("phone", raw.decode().lower())
        self.assertNotIn("email", raw.decode().lower())
        self.assertNotIn(SETTINGS_PASSWORD, raw.decode())
        self.assertEqual(db.writes, [])

    def _framed_html(self) -> str:
        with patch.dict(os.environ, {"COPILOT_BLOOM_ORIGINS": BLOOM_TWO}):
            with patch.object(empower_portal, "load_view", side_effect=AssertionError("html reads data")):
                status, headers, raw = invoke(empower_portal, "GET", "/api/empower_portal")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Security-Policy"], FRAME_ANCESTORS)
        html = raw.decode()
        script = html[html.rfind("<script>") :]
        self.assertIn("location.ancestorOrigins", script)
        self.assertIn("window.parent === window", script)
        self.assertIn("2500", script)
        self.assertNotIn("new URL(document.referrer)", script)
        self.assertNotIn("bloomParents.size === 1", script)
        for name in CUSTOMERS:
            self.assertNotIn(name, html)
        return html

    def _probe(self, html: str, **scenario) -> dict:
        return bloom_frame_probe.probe_bloom_frame(html, scenario, "empower")

    def test_reporting_referrer_still_requests_bloom_token(self):
        html = self._framed_html()
        result = self._probe(
            html,
            topLevel=False,
            referrer=REPORTING_REFERRER,
            ancestorOrigins=[],
        )
        self.assertEqual(
            bloom_frame_probe.request_origins(result),
            [BLOOM_VERCEL, BLOOM_PROD],
        )
        self.assertEqual(result["timeouts"], [2500])
        self.assertEqual(result["fetches"], [])
        self.assertTrue(result["dashboardHidden"])

    def test_empty_referrer_with_two_bloom_origins_still_requests(self):
        html = self._framed_html()
        result = self._probe(html, topLevel=False, referrer="", ancestorOrigins=[])
        self.assertEqual(
            bloom_frame_probe.request_origins(result),
            [BLOOM_VERCEL, BLOOM_PROD],
        )
        self.assertEqual(result["timeouts"], [2500])
        self.assertEqual(result["fetches"], [])

    def test_ancestor_origins_prefer_bloom_then_every_allowlisted_parent(self):
        html = self._framed_html()
        result = self._probe(
            html,
            topLevel=False,
            referrer=REPORTING_REFERRER,
            ancestorOrigins=["https://database-migration-chi.vercel.app", BLOOM_PROD],
            messages=[
                {
                    "origin": "https://evil.example",
                    "data": {"type": "happy-solar-goose", "action": "token", "token": SHELL_TOKEN},
                },
                {
                    "origin": "https://evil.example",
                    "data": {"type": "happy-solar-goose", "action": "token-unavailable"},
                },
            ],
        )
        self.assertEqual(
            bloom_frame_probe.request_origins(result),
            [BLOOM_PROD, BLOOM_VERCEL],
        )
        self.assertEqual(result["fetches"], [])
        self.assertTrue(result["dashboardHidden"])

        unlocked = self._probe(
            html,
            topLevel=False,
            referrer=REPORTING_REFERRER,
            ancestorOrigins=["https://database-migration-chi.vercel.app", BLOOM_PROD],
            messages=[
                {
                    "origin": BLOOM_PROD,
                    "data": {"type": "happy-solar-goose", "action": "token", "token": SHELL_TOKEN},
                }
            ],
        )
        self.assertEqual(len(unlocked["fetches"]), 1)
        self.assertEqual(unlocked["fetches"][0]["url"], "/api/empower_portal?format=json")
        self.assertEqual(unlocked["fetches"][0]["authorization"], "Bearer " + SHELL_TOKEN)
        self.assertFalse(unlocked["dashboardHidden"])

        denied = self._probe(
            html,
            topLevel=False,
            referrer="",
            ancestorOrigins=[BLOOM_PROD],
            messages=[
                {
                    "origin": BLOOM_PROD,
                    "data": {"type": "happy-solar-goose", "action": "token-unavailable"},
                }
            ],
        )
        self.assertEqual(denied["fetches"], [])
        self.assertEqual(denied["locked"]["text"], "Sign in through Bloom Data Center")
        self.assertFalse(denied["locked"]["hidden"])
        self.assertTrue(denied["dashboardHidden"])

    def test_top_level_empower_portal_stays_locked(self):
        html = self._framed_html()
        result = self._probe(
            html,
            topLevel=True,
            referrer="https://bloom.happyslr.com/data",
            ancestorOrigins=[BLOOM_PROD, BLOOM_VERCEL],
        )
        self.assertEqual(result["posts"], [])
        self.assertEqual(result["fetches"], [])
        self.assertEqual(result["timeouts"], [])
        self.assertEqual(result["locked"]["text"], "Sign in through Bloom Data Center")
        self.assertFalse(result["locked"]["hidden"])
        self.assertTrue(result["dashboardHidden"])


def _group_button(html: str, label: str) -> str:
    token = f'class="oc-embed-group-label">{label}</span>'
    idx = html.find(token)
    if idx < 0:
        raise AssertionError(f"missing group label {label}")
    start = html.rfind("<button", 0, idx)
    end = html.find("</button>", idx)
    return html[start:end]


if __name__ == "__main__":
    unittest.main()
