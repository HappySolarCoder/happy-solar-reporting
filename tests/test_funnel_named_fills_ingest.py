# -*- coding: utf-8 -*-
"""Standing leads@ ingest into web_funnel_named_fills_v1."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.insert(0, path)

TEST_NOTIFY = """First name: Test
Last name: Test
Email: adchday@gmail.com
Phone: (585) 281-5811
Address: 313 E Stonebridge Dr, Gilbert, AZ 85234, USA
Monthly electric bill: $200
Utility: RG&E
Estimated solar payment: $160
Monthly savings: $40
Annual savings: $480
10-year savings: $15,568
25-year savings: $127,454
Credit score above 650: Yes
No tall trees around the home: Yes
Owns the home: Yes
Pool: No
Hot tub: No
Electric heat: No
EV car: No
Electric bill uploaded: No
"""

EVAN_NOTIFY = """First name: Evan
Last name: Day
Email: evanrday23@gmail.com
Phone: (585) 000-0000
Address: 24 Hawkstone Way, Pittsford, NY 14534
"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ingest = load_module("hs_funnel_named_fills_ingest", METRICS / "funnel_named_fills_ingest.py")
index = load_module("hs_index_named_fills_ingest", API / "index.py")


def _load_installed():
    metric = load_module("hs_website_funnel_named_fill_rollup", METRICS / "website_funnel.py")
    patch_mod = load_module("hs_funnel_test_address_named_fill_rollup", METRICS / "funnel_test_address.py")
    return patch_mod.install(metric), patch_mod


def _fake_db():
    sets = []

    class FakeDoc:
        def __init__(self, doc_id):
            self.doc_id = doc_id

        def set(self, payload, merge=True):
            sets.append({"id": self.doc_id, "payload": payload, "merge": merge})

    class FakeCol:
        def document(self, doc_id):
            return FakeDoc(doc_id)

    class FakeDb:
        def __init__(self):
            self.sets = sets
            self.collection_names = []

        def collection(self, name):
            self.collection_names.append(name)
            return FakeCol()

    return FakeDb()


class ParseNotifyTests(unittest.TestCase):
    def test_parse_test_test_body(self):
        parsed = ingest.parse_wny_calculator_notify(TEST_NOTIFY)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["name"], "Test Test")
        self.assertEqual(parsed["email"], "adchday@gmail.com")
        self.assertIn("313 E Stonebridge", parsed["address"])
        fill = ingest.fill_from_notify(TEST_NOTIFY, received_at="2026-08-28T13:55:58Z")
        self.assertEqual(fill["name"], "Test Test")
        self.assertEqual(fill["email"], "adchday@gmail.com")
        self.assertIn("313 E Stonebridge", fill["address"])
        self.assertEqual(fill["phone"], "(585) 281-5811")
        self.assertEqual(fill["source"], "leads@")
        self.assertEqual(fill["date"], "2026-08-28")
        self.assertEqual(fill["received_at"], "2026-08-28T13:55:58Z")

    def test_doc_id_adchday(self):
        self.assertEqual(
            ingest.named_fill_doc_id("2026-08-28", "adchday@gmail.com"),
            "2026-08-28_adchday_gmail_com",
        )
        self.assertEqual(ingest.email_slug("adchday@gmail.com"), "adchday_gmail_com")

    def test_evan_day_slug(self):
        parsed = ingest.parse_wny_calculator_notify(EVAN_NOTIFY)
        self.assertEqual(parsed["name"], "Evan Day")
        self.assertEqual(parsed["email"], "evanrday23@gmail.com")
        self.assertEqual(
            ingest.named_fill_doc_id("2026-08-28", "evanrday23@gmail.com"),
            "2026-08-28_evanrday23_gmail_com",
        )
        fill = ingest.fill_from_notify(EVAN_NOTIFY, received_at="2026-08-28T14:10:00Z")
        self.assertEqual(
            ingest.named_fill_doc_id(fill["date"], fill["email"]),
            "2026-08-28_evanrday23_gmail_com",
        )

    def test_missing_email_returns_none(self):
        body = "First name: Test\nLast name: Test\nAddress: 313 E Stonebridge Dr\n"
        self.assertIsNone(ingest.parse_wny_calculator_notify(body))
        self.assertIsNone(ingest.fill_from_notify(body, received_at="2026-08-28T13:55:58Z"))

    def test_date_only_received_at_is_not_shifted(self):
        self.assertEqual(ingest.ny_date_from_received_at("2026-08-28"), "2026-08-28")


class UpsertAndIngestTests(unittest.TestCase):
    def test_upsert_merge_is_idempotent(self):
        db = _fake_db()
        fill = ingest.fill_from_notify(TEST_NOTIFY, received_at="2026-08-28T13:55:58Z")
        first = ingest.upsert_named_fills(db, [fill])
        second = ingest.upsert_named_fills(db, [fill])
        self.assertEqual(first["wrote"], 1)
        self.assertEqual(second["wrote"], 1)
        self.assertEqual(first["ids"], ["2026-08-28_adchday_gmail_com"])
        self.assertEqual(second["ids"], ["2026-08-28_adchday_gmail_com"])
        self.assertEqual(len(db.sets), 2)
        self.assertTrue(db.sets[0]["merge"])
        self.assertTrue(db.sets[1]["merge"])
        self.assertEqual(db.sets[0]["id"], db.sets[1]["id"])
        self.assertEqual(db.collection_names[0], "web_funnel_named_fills_v1")

    def test_upsert_skips_missing_email_or_date(self):
        db = _fake_db()
        out = ingest.upsert_named_fills(
            db,
            [
                {"date": "2026-08-28", "name": "No Email"},
                {"email": "x@y.com", "name": "No Date"},
            ],
        )
        self.assertEqual(out["wrote"], 0)
        self.assertEqual(out["skipped"], 2)
        self.assertEqual(out["ids"], [])
        self.assertEqual(db.sets, [])

    def test_live_wny_fills_are_exactly_charles_four_no_invented_names(self):
        fills = ingest.LIVE_WNY_CALCULATOR_FILLS
        self.assertEqual(len(fills), 4)
        names = [row["name"] for row in fills]
        self.assertEqual(
            names,
            ["Phil Pyrce", "Bob Goodrich", "Art Sieczkarek", "Richard Wooliver"],
        )
        expected_ids = [
            "2026-08-31_pyrce_verizon_net",
            "2026-08-31_bggoodrich_gmail_com",
            "2026-09-01_sieart_msn_com",
            "2026-09-01_rwooliver_gmail_com",
        ]
        self.assertEqual(
            [ingest.named_fill_doc_id(row["date"], row["email"]) for row in fills],
            expected_ids,
        )
        self.assertEqual(fills[0]["email"], "pyrce@verizon.net")
        self.assertEqual(fills[1]["email"], "bggoodrich@gmail.com")
        self.assertEqual(fills[2]["email"], "Sieart@msn.com")
        self.assertEqual(fills[3]["email"], "rwooliver@gmail.com")
        self.assertEqual(fills[0]["received_at"], "2026-08-31T13:26:56Z")
        self.assertEqual(fills[1]["received_at"], "2026-08-31T16:45:53Z")
        self.assertEqual(fills[2]["received_at"], "2026-09-01T19:13:56Z")
        self.assertEqual(fills[3]["received_at"], "2026-09-01T21:29:02Z")
        for row in fills:
            self.assertNotIn(row["email"].casefold(), {"adchday@gmail.com", "evanrday23@gmail.com"})
            self.assertNotIn(row["name"].casefold(), {"test test", "evan day"})
        db = _fake_db()
        out = ingest.upsert_live_wny_calculator_fills(db)
        self.assertEqual(out["wrote"], 4)
        self.assertEqual(out["skipped"], 0)
        self.assertEqual(out["ids"], expected_ids)
        fixture = json.loads((API / "data" / "web_funnel_named_fills_live.json").read_text())
        self.assertEqual([row["name"] for row in fixture], names)
        self.assertEqual([row["id"] for row in fixture], expected_ids)

    def test_live_fills_are_not_test_address(self):
        patch_mod = load_module(
            "hs_funnel_test_address_live_fills", METRICS / "funnel_test_address.py"
        )
        for fill in ingest.LIVE_WNY_CALCULATOR_FILLS:
            self.assertFalse(patch_mod.fill_is_test(fill), fill["name"])
        self.assertEqual(len(patch_mod.live_named_fills(ingest.LIVE_WNY_CALCULATOR_FILLS)), 4)

    def test_gmail_configured_false_when_env_unset(self):
        keys = (
            "GMAIL_ACCESS_TOKEN",
            "GMAIL_REFRESH_TOKEN",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        env = {k: v for k, v in os.environ.items() if k not in keys}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(ingest.gmail_configured())

    def test_ingest_without_gmail_does_not_write(self):
        db = _fake_db()
        keys = (
            "GMAIL_ACCESS_TOKEN",
            "GMAIL_REFRESH_TOKEN",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        env = {k: v for k, v in os.environ.items() if k not in keys}
        with patch.dict(os.environ, env, clear=True):
            out = ingest.ingest_leads_at(db)
        self.assertEqual(out["reason"], "gmail_not_configured")
        self.assertFalse(out["attempted"])
        self.assertEqual(out["wrote"], 0)
        self.assertEqual(db.sets, [])
        self.assertEqual(db.collection_names, [])

    def test_ingest_with_injected_messages_writes(self):
        db = _fake_db()
        out = ingest.ingest_leads_at(
            db,
            messages=[
                {
                    "plaintext": TEST_NOTIFY,
                    "received_at": "2026-08-28T13:55:58Z",
                }
            ],
        )
        self.assertTrue(out["attempted"])
        self.assertEqual(out["wrote"], 1)
        self.assertEqual(out["ids"], ["2026-08-28_adchday_gmail_com"])
        self.assertEqual(db.sets[0]["payload"]["source"], "leads@")
        self.assertIsNone(out["reason"])


class RollupIngestHookTests(unittest.TestCase):
    def test_rollup_calls_ingest_before_fetch_named_fills_when_gmail_configured(self):
        funnel, patch_mod = _load_installed()
        order = []

        def fake_ingest(db, messages=None, date_ymd=None):
            order.append(("ingest", date_ymd))
            return {"attempted": True, "wrote": 1, "reason": None}

        def fake_fills(db, date_ymd):
            order.append(("fetch_named_fills", date_ymd))
            return [
                {
                    "date": date_ymd,
                    "name": "Test Test",
                    "email": "adchday@gmail.com",
                    "address": "313 E Stonebridge Dr",
                }
            ]

        ga4 = {
            "ga4": "ok",
            "estimate_submit": 2,
            "wix_form_submits": 0,
            "completed_forms": 2,
            "starts": 2,
            "sessions": 10,
            "dropped": {"test_address": 0},
            "filters": {},
        }

        class FakeDoc:
            def set(self, payload, merge=True):
                return None

        class FakeCol:
            def document(self, _id):
                return FakeDoc()

        class FakeDb:
            def collection(self, name):
                return FakeCol()

        with patch.object(ingest, "gmail_configured", return_value=True), patch.object(
            ingest, "ingest_leads_at", side_effect=fake_ingest
        ), patch.object(funnel, "fetch_ga4_event_counts", return_value=ga4), patch.object(
            patch_mod, "fetch_named_fills", side_effect=fake_fills
        ):
            out = funnel.rollup_day(FakeDb(), "2026-08-28")
        self.assertEqual(order[0][0], "ingest")
        self.assertEqual(order[0][1], "2026-08-28")
        self.assertIn("fetch_named_fills", [item[0] for item in order])
        self.assertLess(
            [item[0] for item in order].index("ingest"),
            [item[0] for item in order].index("fetch_named_fills"),
        )
        self.assertEqual(out["ingest"]["attempted"], True)
        self.assertEqual(out["ingest"]["wrote"], 1)
        self.assertEqual(out["doc"]["estimate_submit"], 0)
        self.assertEqual(out["doc"]["completed_forms"], 0)

    def test_rollup_without_gmail_does_not_require_gmail(self):
        funnel, patch_mod = _load_installed()
        called = {"ingest": 0}

        def fake_ingest(*args, **kwargs):
            called["ingest"] += 1
            raise AssertionError("ingest_leads_at should not run when gmail is off")

        ga4 = {
            "ga4": "ok",
            "estimate_submit": 1,
            "wix_form_submits": 0,
            "completed_forms": 1,
            "sessions": 5,
            "dropped": {},
            "filters": {},
        }

        class FakeDoc:
            def set(self, payload, merge=True):
                return None

        class FakeCol:
            def document(self, _id):
                return FakeDoc()

        class FakeDb:
            def collection(self, name):
                return FakeCol()

        keys = (
            "GMAIL_ACCESS_TOKEN",
            "GMAIL_REFRESH_TOKEN",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        env = {k: v for k, v in os.environ.items() if k not in keys}
        with patch.dict(os.environ, env, clear=True), patch.object(
            ingest, "ingest_leads_at", side_effect=fake_ingest
        ), patch.object(funnel, "fetch_ga4_event_counts", return_value=ga4), patch.object(
            patch_mod, "fetch_named_fills", return_value=[]
        ):
            out = funnel.rollup_day(FakeDb(), "2026-08-28")
        self.assertEqual(called["ingest"], 0)
        self.assertFalse(out["ingest"]["attempted"])
        self.assertEqual(out["ingest"]["wrote"], 0)
        self.assertEqual(out["ingest"]["reason"], "gmail_not_configured")
        self.assertEqual(out["doc"]["estimate_submit"], 1)


class DispatchTests(unittest.TestCase):
    def test_named_fills_ingest_route_resolves(self):
        path = "/api/web_funnel_named_fills_ingest"
        route = index.dispatch_route(path)
        self.assertEqual(route, "web_funnel_named_fills_ingest")
        file_path = index.dispatch_file(route)
        self.assertEqual(file_path, API / "web_funnel_named_fills_ingest.py")
        self.assertTrue(file_path.is_file())
        module = index._load_api_module(file_path)
        self.assertIsNotNone(index._handler_class(module), file_path.name)

    def test_get_gmail_not_configured_is_200(self):
        handler_mod = index._load_api_module(API / "web_funnel_named_fills_ingest.py")
        keys = (
            "GMAIL_ACCESS_TOKEN",
            "GMAIL_REFRESH_TOKEN",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        env = {k: v for k, v in os.environ.items() if k not in keys}

        class _W:
            def __init__(self):
                self.buf = BytesIO()

            def write(self, data):
                self.buf.write(data)

        captured = {}

        def send_response(self, code):
            captured["code"] = code

        def send_header(self, key, value):
            captured.setdefault("headers", {})[key] = value

        def end_headers(self):
            captured["ended"] = True

        inst = handler_mod.handler.__new__(handler_mod.handler)
        inst.path = "/api/web_funnel_named_fills_ingest?date=2026-08-28"
        inst.wfile = _W()
        inst.send_response = send_response.__get__(inst)
        inst.send_header = send_header.__get__(inst)
        inst.end_headers = end_headers.__get__(inst)
        with patch.dict(os.environ, env, clear=True):
            inst.do_GET()
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Cache-Control"], "no-store")
        import json

        body = json.loads(inst.wfile.buf.getvalue().decode("utf-8"))
        self.assertFalse(body["ready"])
        self.assertEqual(body["reason"], "gmail_not_configured")
        self.assertEqual(body["collection"], "web_funnel_named_fills_v1")

    def test_handler_has_no_public_post(self):
        handler_mod = index._load_api_module(API / "web_funnel_named_fills_ingest.py")
        self.assertFalse(hasattr(handler_mod.handler, "do_POST"))

    def test_get_without_gmail_does_not_write(self):
        handler_mod = index._load_api_module(API / "web_funnel_named_fills_ingest.py")
        keys = (
            "GMAIL_ACCESS_TOKEN",
            "GMAIL_REFRESH_TOKEN",
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
        )
        env = {k: v for k, v in os.environ.items() if k not in keys}

        class _W:
            def __init__(self):
                self.buf = BytesIO()

            def write(self, data):
                self.buf.write(data)

        captured = {}

        def send_response(self, code):
            captured["code"] = code

        def send_header(self, key, value):
            captured.setdefault("headers", {})[key] = value

        def end_headers(self):
            captured["ended"] = True

        inst = handler_mod.handler.__new__(handler_mod.handler)
        inst.path = "/api/web_funnel_named_fills_ingest?date=2026-08-28"
        inst.wfile = _W()
        inst.send_response = send_response.__get__(inst)
        inst.send_header = send_header.__get__(inst)
        inst.end_headers = end_headers.__get__(inst)
        with patch.dict(os.environ, env, clear=True), patch.object(
            handler_mod.funnel, "get_db", side_effect=AssertionError("GET without Gmail must not write")
        ), patch.object(
            handler_mod.ingest, "ingest_leads_at", side_effect=AssertionError("GET without Gmail must not ingest")
        ):
            inst.do_GET()
        self.assertEqual(captured["code"], 200)
        import json

        body = json.loads(inst.wfile.buf.getvalue().decode("utf-8"))
        self.assertFalse(body["ready"])
        self.assertEqual(body["reason"], "gmail_not_configured")


if __name__ == "__main__":
    unittest.main()
