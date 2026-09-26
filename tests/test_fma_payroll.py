# -*- coding: utf-8 -*-

"""FMA payroll gate, week default, and exclusion rules."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "api" / "private"
API = ROOT / "api"
FIXTURE = ROOT / "tests" / "fixtures" / "fma_payroll_week_2026_09_17.json"

for path in (str(PRIVATE), str(API)):
    if path not in sys.path:
        sys.path.insert(0, path)

from fma_payroll_logic import (  # noqa: E402
    build_payroll_payload,
    is_self_gen,
    last_completed_payroll_week,
    resolve_setter_last_name,
    resolve_week,
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payroll_api = load_module("fma_payroll_api_under_test", PRIVATE / "fma_payroll.py")
login_api = load_module("fma_payroll_login_under_test", PRIVATE / "fma_payroll_login.py")
logout_api = load_module("fma_payroll_logout_under_test", PRIVATE / "fma_payroll_logout.py")
page_api = load_module("fma_payroll_page_under_test", PRIVATE / "fma_payroll_page.py")
gate = load_module("payroll_gate_under_test", PRIVATE / "payroll_gate.py")


class HeaderMap:
    def __init__(self, data=None):
        self._data = {str(key).lower(): value for key, value in (data or {}).items()}

    def get(self, key, default=None):
        return self._data.get(str(key).lower(), default)


class Body:
    def __init__(self, raw: bytes = b""):
        self.buf = BytesIO(raw)
        self.out = BytesIO()

    def read(self, n=-1):
        return self.buf.read(n)

    def write(self, data):
        self.out.write(data)


def invoke(module, url: str, *, method: str = "GET", headers=None, body: bytes = b""):
    captured = {"headers": {}}
    stream = Body(body)
    header_map = dict(headers or {})
    if body and "Content-Length" not in header_map and "content-length" not in {k.lower() for k in header_map}:
        header_map["Content-Length"] = str(len(body))
    inst = module.handler.__new__(module.handler)
    inst.path = url
    inst.headers = HeaderMap(header_map)
    inst.rfile = stream
    inst.wfile = stream

    def send_response(code, _message=None):
        captured["code"] = code

    def send_header(key, value):
        captured["headers"].setdefault(key, [])
        captured["headers"][key].append(value)

    inst.send_response = send_response
    inst.send_header = send_header
    inst.end_headers = lambda: captured.__setitem__("ended", True)
    getattr(inst, f"do_{method}")()
    raw = stream.out.getvalue()
    return captured, raw


class WeekDefaultTests(unittest.TestCase):
    def test_thursday_uses_previous_thu_through_yesterday(self):
        start, end = last_completed_payroll_week(date(2026, 9, 24))
        self.assertEqual(start.isoformat(), "2026-09-17")
        self.assertEqual(end.isoformat(), "2026-09-23")
        self.assertEqual(start.strftime("%A"), "Thursday")
        self.assertEqual(end.strftime("%A"), "Wednesday")

    def test_wednesday_uses_the_prior_completed_week(self):
        start, end = last_completed_payroll_week(date(2026, 9, 23))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-09-10", "2026-09-16"))

    def test_midweek_does_not_use_the_in_progress_week(self):
        start, end = last_completed_payroll_week(date(2026, 9, 22))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-09-10", "2026-09-16"))

    def test_explicit_week_must_be_thursday(self):
        start, end = resolve_week("2026-09-17", date(2026, 9, 24))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-09-17", "2026-09-23"))
        with self.assertRaises(ValueError):
            resolve_week("2026-09-18", date(2026, 9, 24))
        with self.assertRaises(ValueError):
            resolve_week("09-17-2026", date(2026, 9, 24))


class ExclusionRuleTests(unittest.TestCase):
    def test_self_gen_normalization_variants(self):
        for raw in (
            "Self Gen",
            "self gen",
            "self-gen",
            "self_gen",
            "SELFGEN",
            "self generated",
            "Self-Generated",
            "self_generated",
            "  Self   Gen  ",
        ):
            self.assertTrue(is_self_gen(raw), raw)
        for raw in ("Doors", "Inbound", "3PL", "Phones", "", None, "none"):
            self.assertFalse(is_self_gen(raw), raw)

    def test_setter_name_fallback_uses_last_token(self):
        self.assertEqual(resolve_setter_last_name([""], ["William Breen"]), "Breen")
        self.assertEqual(resolve_setter_last_name(["Hill"], ["Someone Else"]), "Hill")
        self.assertEqual(resolve_setter_last_name(["none", ""], ["", None]), "")

    def test_owner_match_no_setter_and_blank_manager(self):
        sits = [
            {
                "opportunity_id": "counted-1",
                "customer_name": "Ada Counted",
                "sat_date": "2026-09-17",
                "pipeline": "Buffalo",
                "lead_source": "Doors",
                "owner_name": "Zach Maecker",
                "setter_last_name": "breen",
                "scheduling_manager": "",
            },
            {
                "opportunity_id": "self-and-owner",
                "customer_name": "Bea Match",
                "sat_date": "2026-09-18",
                "pipeline": "Rochester",
                "lead_source": "self-generated",
                "owner_name": "Allen Frazier",
                "setter_last_name": " frazier ",
                "scheduling_manager": "Calabrese",
            },
            {
                "opportunity_id": "missing-setter",
                "customer_name": "Cy Blank",
                "sat_date": "2026-09-19",
                "pipeline": "Virtual",
                "lead_source": None,
                "owner_name": "Jeff Salas",
                "setter_last_name": "  ",
                "scheduling_manager": None,
            },
        ]
        payload = build_payroll_payload(sits, date(2026, 9, 17), date(2026, 9, 23), today=date(2026, 9, 24))
        self.assertEqual(payload["source_sit_count"], 3)
        self.assertEqual(payload["fma"]["grand_total"], 1)
        self.assertEqual(payload["fma"]["rows"][0]["setter"], "Breen")
        self.assertEqual(payload["fma"]["rows"][0]["count"], 1)
        self.assertEqual(payload["fma"]["excluded_count"], 2)
        reasons = {row["opportunity_id"]: row["reasons"] for row in payload["fma"]["excluded"]}
        self.assertEqual(
            reasons["self-and-owner"],
            [
                "self-gen lead source: 'self-generated'",
                "owner last name equals setter last name ('Frazier')",
            ],
        )
        self.assertEqual(reasons["missing-setter"], ["missing setter"])
        blank = next(row for row in payload["scheduling_manager"]["rows"] if row["manager"] == "(blank)")
        self.assertEqual((blank["counted"], blank["excluded_self_gen"], blank["total"]), (2, 0, 2))
        calabrese = next(row for row in payload["scheduling_manager"]["rows"] if row["manager"] == "Calabrese")
        self.assertEqual((calabrese["counted"], calabrese["excluded_self_gen"], calabrese["total"]), (0, 1, 1))
        grand = payload["scheduling_manager"]["grand_total"]
        self.assertEqual((grand["counted"], grand["excluded_self_gen"], grand["total"]), (2, 1, 3))


class WeekEvidenceTests(unittest.TestCase):
    def test_week_of_2026_09_17_matches_expected_credit(self):
        raw = json.loads(FIXTURE.read_text())
        sits = []
        for row in raw:
            item = dict(row)
            item.pop("expected_bucket", None)
            item.pop("expected_reasons", None)
            sits.append(item)
        payload = build_payroll_payload(sits, date(2026, 9, 17), date(2026, 9, 23), today=date(2026, 9, 24))
        self.assertEqual(payload["timezone"], "America/New_York")
        self.assertEqual(payload["week_label"], "Thu Sep 17 – Wed Sep 23, 2026 (ET)")
        self.assertEqual(payload["source_sit_count"], 33)
        self.assertEqual(payload["fma"]["grand_total"], 26)
        self.assertEqual(payload["fma"]["excluded_count"], 7)
        counts = [(row["setter"], row["count"]) for row in payload["fma"]["rows"]]
        self.assertEqual(
            counts,
            [
                ("Hill", 7),
                ("Calabrese", 6),
                ("Mancini", 5),
                ("Emerson", 3),
                ("Meehan", 2),
                ("Vermeesch", 2),
                ("Breen", 1),
            ],
        )
        excluded = {row["opportunity_id"]: row for row in payload["fma"]["excluded"]}
        expected_excluded = {
            row["opportunity_id"]: row["expected_reasons"]
            for row in raw
            if row["expected_bucket"] == "excluded"
        }
        self.assertEqual(set(excluded), set(expected_excluded))
        for opp_id, reasons in expected_excluded.items():
            self.assertEqual(excluded[opp_id]["reasons"], reasons)
        sm = {
            row["manager"]: (row["counted"], row["excluded_self_gen"], row["total"])
            for row in payload["scheduling_manager"]["rows"]
        }
        self.assertEqual(sm["Calabrese"], (13, 2, 15))
        self.assertEqual(sm["Diamond"], (1, 0, 1))
        self.assertEqual(sm["(blank)"], (14, 3, 17))
        grand = payload["scheduling_manager"]["grand_total"]
        self.assertEqual((grand["counted"], grand["excluded_self_gen"], grand["total"]), (28, 5, 33))
        self.assertEqual(set(payload["source_opportunity_ids"]), {row["opportunity_id"] for row in raw})
        breen = next(row for row in payload["fma"]["rows"] if row["setter"] == "Breen")
        self.assertEqual(breen["demos"][0]["customer_name"], "Scott Wagner")
        self.assertEqual(breen["demos"][0]["setter"], "Breen")


class GateTests(unittest.TestCase):
    def setUp(self):
        self._prior = os.environ.get("PAYROLL_GATE_SECRET")

    def tearDown(self):
        if self._prior is None:
            os.environ.pop("PAYROLL_GATE_SECRET", None)
        else:
            os.environ["PAYROLL_GATE_SECRET"] = self._prior

    def test_401_without_cookie_or_header(self):
        os.environ["PAYROLL_GATE_SECRET"] = "unit-secret"
        captured, raw = invoke(payroll_api, "/api/private/fma_payroll?week_start=2026-09-17")
        self.assertEqual(captured["code"], 401)
        self.assertEqual(raw, b'{"error":"unauthorized"}')
        self.assertIn("noindex", captured["headers"]["X-Robots-Tag"][0])
        self.assertIn("private, no-store", captured["headers"]["Cache-Control"][0])

    def test_503_when_secret_unset(self):
        os.environ.pop("PAYROLL_GATE_SECRET", None)
        captured, raw = invoke(
            payroll_api,
            "/api/private/fma_payroll?week_start=2026-09-17",
            headers={"X-Payroll-Gate": "anything"},
        )
        self.assertEqual(captured["code"], 503)
        self.assertEqual(json.loads(raw)["error"], "unavailable")
        page, page_body = invoke(page_api, "/private/fma-payroll")
        self.assertEqual(page["code"], 503)
        self.assertNotIn(b"Matthew Kao", page_body)
        self.assertNotIn(b"<input", page_body)
        self.assertIn(b"not configured", page_body)

    def test_login_sets_hmac_cookie_and_logout_clears_it(self):
        os.environ["PAYROLL_GATE_SECRET"] = "unit-secret"
        bad, bad_body = invoke(
            login_api,
            "/api/private/fma_payroll_login",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=b'{"password":"nope"}',
        )
        self.assertEqual(bad["code"], 401)
        self.assertEqual(bad_body, b'{"error":"unauthorized"}')
        self.assertNotIn("Set-Cookie", bad["headers"])

        ok, ok_body = invoke(
            login_api,
            "/api/private/fma_payroll_login",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=b'{"password":"unit-secret"}',
        )
        self.assertEqual(ok["code"], 200)
        self.assertEqual(json.loads(ok_body)["ok"], True)
        cookie = ok["headers"]["Set-Cookie"][0]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertIn("Max-Age=43200", cookie)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        self.assertNotEqual(token, "unit-secret")
        self.assertEqual(token, gate.cookie_token("unit-secret"))

        logged_out, _ = invoke(logout_api, "/api/private/fma_payroll_logout", method="POST")
        self.assertEqual(logged_out["code"], 303)
        cleared = logged_out["headers"]["Set-Cookie"][0]
        self.assertIn("Max-Age=0", cleared)
        self.assertEqual(logged_out["headers"]["Location"][0], "/private/fma-payroll")

    def test_header_and_cookie_open_the_api_for_an_empty_week(self):
        os.environ["PAYROLL_GATE_SECRET"] = "unit-secret"
        with patch.object(payroll_api, "today_et", return_value=date(2026, 9, 24)), patch.object(
            payroll_api, "collect_sits", return_value=[]
        ), patch.object(payroll_api.demo_rate, "get_db", return_value=object()):
            captured, raw = invoke(
                payroll_api,
                "/api/private/fma_payroll",
                headers={"X-Payroll-Gate": "unit-secret"},
            )
        self.assertEqual(captured["code"], 200)
        payload = json.loads(raw)
        self.assertEqual(payload["week_start"], "2026-09-17")
        self.assertEqual(payload["week_end"], "2026-09-23")
        self.assertEqual(payload["source_sit_count"], 0)

        cookie = f"hs_payroll={gate.cookie_token('unit-secret')}"
        with patch.object(payroll_api, "today_et", return_value=date(2026, 9, 23)), patch.object(
            payroll_api, "collect_sits", return_value=[]
        ), patch.object(payroll_api.demo_rate, "get_db", return_value=object()):
            wed, wed_raw = invoke(
                payroll_api,
                "/api/private/fma_payroll",
                headers={"Cookie": cookie},
            )
        self.assertEqual(wed["code"], 200)
        wed_payload = json.loads(wed_raw)
        self.assertEqual(wed_payload["week_start"], "2026-09-10")
        self.assertEqual(wed_payload["week_end"], "2026-09-16")

    def test_non_thursday_is_400_after_the_gate(self):
        os.environ["PAYROLL_GATE_SECRET"] = "unit-secret"
        captured, raw = invoke(
            payroll_api,
            "/api/private/fma_payroll?week_start=2026-09-18",
            headers={"X-Payroll-Gate": "unit-secret"},
        )
        self.assertEqual(captured["code"], 400)
        self.assertIn("Thursday", json.loads(raw)["error"])

    def test_page_shell_has_no_payroll_rows(self):
        os.environ["PAYROLL_GATE_SECRET"] = "unit-secret"
        captured, raw = invoke(page_api, "/private/fma-payroll")
        self.assertEqual(captured["code"], 200)
        text = raw.decode("utf-8")
        self.assertIn('type="password"', text)
        self.assertIn('name="robots" content="noindex, nofollow"', text)
        self.assertNotIn("Matthew Kao", text)
        self.assertNotIn("Scott Wagner", text)
        self.assertNotIn("source_sit_count", text)
        cookie = f"hs_payroll={gate.cookie_token('unit-secret')}"
        authed, authed_raw = invoke(page_api, "/private/fma-payroll", headers={"Cookie": cookie})
        self.assertEqual(authed["code"], 200)
        shell = authed_raw.decode("utf-8")
        self.assertIn("/api/private/fma_payroll", shell)
        self.assertIn("Previous week", shell)
        self.assertIn("Scheduling manager payout", shell)
        self.assertIn('id="excluded"', shell)
        self.assertNotIn("Matthew Kao", shell)
        self.assertNotIn("Hill", shell)
        self.assertIn("noindex", authed["headers"]["X-Robots-Tag"][0])
        self.assertEqual(authed["headers"]["Cache-Control"][0], "private, no-store")

    def test_login_503_when_secret_missing(self):
        os.environ.pop("PAYROLL_GATE_SECRET", None)
        captured, raw = invoke(
            login_api,
            "/api/private/fma_payroll_login",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=b'{"password":"unit-secret"}',
        )
        self.assertEqual(captured["code"], 503)
        self.assertEqual(json.loads(raw)["error"], "unavailable")
        self.assertNotIn("Set-Cookie", captured["headers"])


class LinkAndQueryTests(unittest.TestCase):
    def test_no_inbound_dashboard_links(self):
        needles = ("/private/fma-payroll", "fma_payroll")
        allowed = {
            "api/private/payroll_gate.py",
            "api/private/fma_payroll_logic.py",
            "api/private/fma_payroll.py",
            "api/private/fma_payroll_login.py",
            "api/private/fma_payroll_logout.py",
            "api/private/fma_payroll_page.py",
            "tests/test_fma_payroll.py",
            "tests/test_sweeper_rehash_attribution.py",
            "tests/test_restore_omitted_apis.py",
            "vercel.json",
        }
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", "__pycache__", "node_modules"} for part in path.parts):
                continue
            if path.suffix not in {".py", ".json", ".html", ".js", ".md"}:
                continue
            text = path.read_text(errors="ignore")
            if any(needle in text for needle in needles):
                hits.append(str(path.relative_to(ROOT)))
        self.assertTrue(set(hits) <= allowed, sorted(set(hits) - allowed))
        nav = (API / "dashboard_nav.py").read_text()
        self.assertNotIn("fma-payroll", nav)
        self.assertNotIn("fma_payroll", nav)

    def test_payroll_reuses_demo_rate_helpers_and_does_not_stream_collections(self):
        src = (PRIVATE / "fma_payroll.py").read_text()
        self.assertIn("pipeline_in_demo_scope", src)
        self.assertIn("frozen_disposition_local", src)
        self.assertIn("load_demo_rate_snaps", src)
        self.assertNotIn('.collection("ghl_opportunities_v2").stream()', src)
        self.assertNotIn('.collection("ghl_contacts_v2").stream()', src)
        self.assertNotIn('.collection("ghl_users_v2").stream()', src)
        self.assertNotIn("opp.get(\"source\")", src)
        demo = (API / "metrics" / "demo_rate.py").read_text()
        self.assertIn("def pipeline_in_demo_scope", demo)
        self.assertIn("def frozen_disposition_local", demo)
        self.assertIn("if not pipeline_in_demo_scope(pname_low, c):", demo)


if __name__ == "__main__":
    unittest.main()
