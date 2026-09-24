# -*- coding: utf-8 -*-

"""Installer-tag parsing, reply rule, public JSON feed, and Enerflo GET client."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
PRIVATE = API / "private"
FIXTURES = ROOT / "tests" / "fixtures"
USERS_FIXTURE = FIXTURES / "enerflo_installer_users.json"
NOTES_FIXTURE = FIXTURES / "enerflo_installer_notes.json"
INSTALL_FIXTURE = FIXTURES / "enerflo_installer_install.json"

if str(API) not in sys.path:
    sys.path.insert(0, str(API))

HS_COMPANY_ID = 8253
INSTALLER_COMPANY_ID = 8090
NOW = datetime(2026, 9, 24, 21, 18, tzinfo=timezone.utc)

NEW_FILES = [
    API / "enerflo_installer_logic.py",
    API / "enerflo_installer_client.py",
    API / "enerflo_installer.py",
    API / "enerflo_installer_page.py",
]

FIXTURE_NAMES = (
    "Tom Dunne",
    "Ian C",
    "Mark Sato",
    "Tara Diaz",
    "Adam Fox",
    "Adam Reed",
    "Jake Moreno",
    "Casey Example",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


logic = load_module("enerflo_installer_logic_under_test", API / "enerflo_installer_logic.py")
client = load_module("enerflo_installer_client_under_test", API / "enerflo_installer_client.py")
api = load_module("enerflo_installer_api_under_test", API / "enerflo_installer.py")
page = load_module("enerflo_installer_page_under_test", API / "enerflo_installer_page.py")


def users() -> list[dict]:
    return json.loads(USERS_FIXTURE.read_text())


def notes() -> list[dict]:
    return json.loads(NOTES_FIXTURE.read_text())


def resolved_ids(text: str) -> list[int]:
    return [tag.user_id for tag in logic.parse_tags(text, users()) if tag.user_id is not None]


def unresolved_raws(text: str) -> list[str]:
    return [tag.raw for tag in logic.parse_tags(text, users()) if tag.user_id is None]


def make_note(note_id: int, install_id: int, text: str, created: datetime, deleted_at: str | None = None) -> dict:
    return {
        "note_id": note_id,
        "id": install_id,
        "epc_install_id": install_id,
        "author_id": 145285,
        "note": text,
        "created_at": created.strftime("%Y-%m-%d %H:%M:%S"),
        "deleted_at": deleted_at,
    }


def at_hours_ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


def classify(rows: list[dict], *, rule: str = "any_later_note"):
    return logic.classify(
        rows,
        users(),
        NOW,
        rule=rule,
        hs_company_id=HS_COMPANY_ID,
        installer_company_id=INSTALLER_COMPANY_ID,
        days=60,
        created_after="2026-07-26T21:18:00Z",
    )


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


def invoke(module, url: str, *, method: str = "GET", headers=None):
    captured = {"headers": {}}
    stream = Body()
    inst = module.handler.__new__(module.handler)
    inst.path = url
    inst.headers = HeaderMap(headers)
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
    return captured, stream.out.getvalue()


class FakeResp:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def http_error(status: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://enerflo.io/api/v3/users",
        status,
        "error",
        headers,
        BytesIO(b""),
    )


class ParseTests(unittest.TestCase):
    def test_two_installer_tags_and_a_survey_line(self):
        text = "@Tom Dunne @Ian C \n\nRoof - PASS - roof is very new, one ridge fix…"
        self.assertEqual(resolved_ids(text), [1, 2])

    def test_single_tag_with_a_question(self):
        text = "@Tom Dunne whats the relationship between [CUSTOMER] and [CUSTOMER]?"
        self.assertEqual(resolved_ids(text), [1])
        self.assertEqual(unresolved_raws(text), [])

    def test_dash_form_and_unknown_name(self):
        text = "@Tom Dunne HO cancelled with Enfin\n\n@Mark - Sato Essential Power @Jake Moreno cancel the SS"
        self.assertEqual(resolved_ids(text), [1, 3])
        self.assertEqual(unresolved_raws(text), ["@Jake Moreno"])

    def test_tag_at_the_end_of_the_sentence(self):
        text = "I am missing the full UB, you all uploaded a blank page. @Tom Dunne"
        self.assertEqual(resolved_ids(text), [1])

    def test_tag_glued_to_a_preceding_letter(self):
        text = "i@Tom Dunne f we do not have an update on how to move forward I am moving to hold"
        self.assertEqual(resolved_ids(text), [1])

    def test_first_name_only_is_unresolved_when_two_adams_exist(self):
        tags = logic.parse_tags("@Adam please check", users())
        self.assertEqual(resolved_ids("@Adam please check"), [])
        self.assertEqual([tag.raw for tag in tags], ["@Adam please"])
        self.assertEqual(resolved_ids("@Adam Fox please"), [5])
        self.assertEqual(resolved_ids("@Adam Reed please"), [6])

    def test_email_single_letter_last_name_and_duplicate(self):
        self.assertEqual(logic.parse_tags("bob@example.com", users()), [])
        self.assertEqual(resolved_ids("@Ian C. please"), [2])
        self.assertEqual(resolved_ids("@Tom Dunne and again @Tom Dunne"), [1])

    def test_norm_collapses_punctuation(self):
        self.assertEqual(logic.norm("Mark - Sato Essential Power"), "mark sato essential power")
        self.assertEqual(logic.norm("Ian C."), "ian c")


class SurveyTests(unittest.TestCase):
    def test_all_pass_note_goes_to_survey_passed(self):
        text = "@Tom Dunne\n\nRoof - PASS - roof is very new\nElectrical - PASS"
        payload = classify([make_note(1, 10, text, at_hours_ago(48))])
        self.assertEqual(payload["counts"]["survey_passed"], 1)
        self.assertEqual(payload["counts"]["open"], 0)
        self.assertEqual(payload["survey_passed"][0]["note_id"], 1)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(logic.survey_results(text), ["PASS", "PASS"])

    def test_pass_and_fail_stays_open(self):
        text = "@Tom Dunne\n\nRoof - PASS\nElectrical - FAIL - panel is full"
        payload = classify([make_note(1, 10, text, at_hours_ago(30))])
        self.assertEqual([row["note_id"] for row in payload["rows"]], [1])
        self.assertEqual(payload["survey_passed"], [])
        self.assertEqual(payload["counts"]["open"], 1)

    def test_note_without_survey_lines_is_unaffected(self):
        plain = "@Tom Dunne whats the relationship between [CUSTOMER] and [CUSTOMER]?"
        fresh = "@Ian C checking in"
        payload = classify(
            [
                make_note(1, 10, plain, at_hours_ago(30)),
                make_note(2, 11, fresh, at_hours_ago(2)),
            ]
        )
        self.assertEqual([row["note_id"] for row in payload["rows"]], [1])
        self.assertEqual([row["note_id"] for row in payload["pending"]], [2])
        self.assertEqual(payload["survey_passed"], [])
        self.assertEqual(logic.survey_results(plain), [])

    def test_recent_all_pass_is_not_left_in_pending(self):
        text = "@Mark Sato\n\nRoof - PASS\nElectrical - PASS"
        payload = classify([make_note(1, 10, text, at_hours_ago(3))])
        self.assertEqual(payload["pending"], [])
        self.assertEqual(payload["counts"]["survey_passed"], 1)

    def test_answered_all_pass_stays_answered(self):
        survey = "@Tom Dunne\n\nRoof - PASS\nElectrical - PASS"
        later = "system notice with no tags"
        payload = classify(
            [
                make_note(1, 10, survey, at_hours_ago(50)),
                make_note(2, 10, later, at_hours_ago(40)),
            ]
        )
        self.assertEqual(payload["survey_passed"], [])
        self.assertEqual(payload["counts"]["answered"], 1)
        self.assertEqual(payload["recently_answered"][0]["reply_kind"], "untagged")


class RuleTests(unittest.TestCase):
    def test_later_installer_note_is_a_followup_and_a_chaser(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne first ask", at_hours_ago(50)),
                make_note(2, 10, "@Ian C sending the roof quote", at_hours_ago(40)),
            ]
        )
        self.assertEqual(payload["counts"]["answered_by_kind"]["followup"], 1)
        self.assertEqual(payload["recently_answered"][0]["reply_kind"], "followup")
        self.assertEqual(payload["recently_answered"][0]["confidence"], "medium")
        self.assertEqual(payload["recently_answered"][0]["reply_note_id"], 2)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["note_id"], 2)
        self.assertEqual(payload["rows"][0]["chaser_count"], 1)
        self.assertEqual(payload["counts"]["chasers"], 1)

    def test_later_happy_solar_tag_is_reply_inferred_and_not_a_row(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne @Ian C need an update", at_hours_ago(50)),
                make_note(
                    2,
                    10,
                    "i@Tara Diaz f we do not have an update on how to move forward I am moving to hold",
                    at_hours_ago(40),
                ),
            ]
        )
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pending"], [])
        self.assertEqual(payload["recently_answered"][0]["reply_kind"], "reply_inferred")
        self.assertEqual(payload["recently_answered"][0]["confidence"], "medium")
        self.assertEqual(payload["counts"]["answered"], 1)

    def test_later_unresolved_note_is_untagged_low_confidence(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne status?", at_hours_ago(50)),
                make_note(2, 10, "@Jake Moreno please cancel", at_hours_ago(30)),
            ]
        )
        self.assertEqual(payload["recently_answered"][0]["reply_kind"], "untagged")
        self.assertEqual(payload["recently_answered"][0]["confidence"], "low")
        self.assertEqual(payload["needs_mapping"][0]["raw"], "@Jake Moreno")

    def test_later_note_on_another_install_does_not_close(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne status?", at_hours_ago(50)),
                make_note(2, 99, "@Tara Diaz moving to hold", at_hours_ago(10)),
            ]
        )
        self.assertEqual([row["note_id"] for row in payload["rows"]], [1])
        self.assertEqual(payload["counts"]["answered"], 0)

    def test_pending_before_24h_and_open_after(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne soon", at_hours_ago(23)),
                make_note(2, 11, "@Ian C late", at_hours_ago(25)),
            ]
        )
        self.assertEqual([row["note_id"] for row in payload["pending"]], [1])
        self.assertEqual([row["note_id"] for row in payload["rows"]], [2])

    def test_equal_timestamps_are_not_a_reply(self):
        created = at_hours_ago(30)
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne one", created),
                make_note(2, 10, "@Ian C two", created),
            ]
        )
        self.assertEqual(payload["counts"]["answered"], 0)
        self.assertEqual(sorted(row["note_id"] for row in payload["rows"]), [1, 2])
        by_id = {row["note_id"]: row["chaser_count"] for row in payload["rows"]}
        self.assertEqual(by_id[1], 0)
        self.assertEqual(by_id[2], 1)

    def test_deleted_notes_are_neither_rows_nor_replies(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne still waiting", at_hours_ago(50)),
                make_note(2, 10, "@Tara Diaz this was removed", at_hours_ago(40), deleted_at="2026-09-22 00:00:00"),
                make_note(3, 11, "@Ian C deleted ask", at_hours_ago(50), deleted_at="2026-09-22 00:00:00"),
            ]
        )
        self.assertEqual([row["note_id"] for row in payload["rows"]], [1])
        self.assertEqual(payload["counts"]["answered"], 0)
        self.assertEqual(payload["counts"]["installer_tagged"], 1)

    def test_et_display_and_waiting_label(self):
        created = logic.parse_created_at("2026-09-24 02:30:00")
        self.assertIsNotNone(created)
        self.assertEqual(logic.format_et(created), "Wed 09/23 10:30 PM ET")
        self.assertEqual(logic.format_et(NOW), "Thu 09/24 5:18 PM ET")
        self.assertEqual(logic.waiting_label(53.5), "2d 5h")
        self.assertEqual(logic.waiting_label(5.9), "5h")
        payload = classify([make_note(1, 10, "@Tom Dunne wait", NOW - timedelta(hours=53.5))])
        self.assertEqual(payload["rows"][0]["waiting_label"], "2d 5h")
        self.assertEqual(payload["rows"][0]["created_at_et"], logic.format_et(NOW - timedelta(hours=53.5)))

    def test_needs_mapping_counts_and_last_seen(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne @Jake Moreno once", at_hours_ago(50)),
                make_note(2, 11, "@Jake Moreno @Jake Moreno twice in one note", at_hours_ago(30)),
            ]
        )
        mapping = payload["needs_mapping"]
        self.assertEqual(len(mapping), 1)
        self.assertEqual(mapping[0]["raw"], "@Jake Moreno")
        self.assertEqual(mapping[0]["count"], 2)
        self.assertEqual(mapping[0]["note_ids"], [1, 2])
        self.assertEqual(mapping[0]["last_seen_et"], logic.format_et(at_hours_ago(30)))
        self.assertEqual(payload["counts"]["needs_mapping"], 1)

    def test_empty_deal_template_leaves_the_url_null(self):
        self.assertEqual(logic.ENERFLO_DEAL_URL_TEMPLATE, "")
        self.assertIsNone(logic.deal_url(5010))
        self.assertEqual(
            logic.deal_url(5010, "v1-example", template="https://example.test/installs/{install_id}"),
            "https://example.test/installs/5010",
        )

    def test_open_rows_sort_longest_wait_first(self):
        payload = classify(
            [
                make_note(1, 10, "@Tom Dunne shorter", at_hours_ago(30)),
                make_note(2, 11, "@Ian C longer", at_hours_ago(80)),
            ]
        )
        self.assertEqual([row["note_id"] for row in payload["rows"]], [2, 1])


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self._prior = os.environ.get("ENERFLO_API_KEY")
        os.environ["ENERFLO_API_KEY"] = "test-key"

    def tearDown(self):
        if self._prior is None:
            os.environ.pop("ENERFLO_API_KEY", None)
        else:
            os.environ["ENERFLO_API_KEY"] = self._prior

    def _stubs(self, installs=None, warnings=None, notes_rows=None, users_rows=None):
        install_map = installs if installs is not None else {}
        warning_rows = warnings if warnings is not None else []
        return (
            patch.object(api, "clock", return_value=NOW),
            patch.object(api, "fetch_notes", return_value=notes() if notes_rows is None else notes_rows),
            patch.object(api, "fetch_users", return_value=users() if users_rows is None else users_rows),
            patch.object(api, "fetch_installs", return_value=(install_map, warning_rows)),
        )

    def test_unauthenticated_get_returns_200(self):
        installs = {
            5010: {
                "customer_name": "Casey Example",
                "rep_name": "Ada Rep",
                "rep_id": 5,
                "status": "In progress",
                "milestone": "Survey",
            }
        }
        stubs = self._stubs(installs=installs)
        with stubs[0], stubs[1], stubs[2], stubs[3] as fetch_installs:
            captured, raw = invoke(
                api,
                "/api/enerflo_installer",
                headers={"X-Payroll-Gate": "ignored", "Cookie": "hs_payroll=ignored"},
            )
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Cache-Control"], ["private, no-store"])
        self.assertEqual(captured["headers"]["X-Robots-Tag"], ["noindex, nofollow"])
        payload = json.loads(raw)
        self.assertEqual(payload["rule"], "any_later_note")
        self.assertEqual(payload["generated_at_et"], "Thu 09/24 5:18 PM ET")
        self.assertEqual(payload["window"]["days"], 60)
        self.assertEqual(payload["counts"]["open"], 3)
        self.assertEqual(payload["counts"]["survey_passed"], 1)
        self.assertEqual(payload["counts"]["pending"], 1)
        self.assertEqual(payload["counts"]["answered"], 2)
        self.assertEqual({row["note_id"] for row in payload["rows"]}, {101, 105, 106})
        self.assertEqual(payload["survey_passed"][0]["note_id"], 102)
        self.assertEqual(payload["pending"][0]["note_id"], 103)
        chaser_row = next(row for row in payload["rows"] if row["note_id"] == 105)
        self.assertEqual(chaser_row["chaser_count"], 1)
        self.assertEqual(payload["counts"]["chasers"], 1)
        named = next(row for row in payload["rows"] if row["install_id"] == 5010)
        self.assertEqual(named["customer_name"], "Casey Example")
        self.assertEqual(named["sales_rep"], "Ada Rep")
        self.assertIsNone(named["enerflo_url"])
        fetched = set(fetch_installs.call_args[0][1])
        self.assertEqual(fetched, {5010, 5011, 5012, 5013, 5014})
        answered_only = next(row for row in payload["recently_answered"] if row["note_id"] == 107)
        self.assertEqual(answered_only["customer_name"], "")
        self.assertEqual(answered_only["reply_kind"], "untagged")

    def test_missing_key_is_503_without_a_gate(self):
        os.environ.pop("ENERFLO_API_KEY", None)
        captured, raw = invoke(
            api,
            "/api/enerflo_installer",
            headers={"X-Payroll-Gate": "anything"},
        )
        self.assertEqual(captured["code"], 503)
        self.assertEqual(json.loads(raw), {"error": "enerflo_key_missing"})
        self.assertEqual(captured["headers"]["Cache-Control"], ["private, no-store"])
        self.assertEqual(captured["headers"]["X-Robots-Tag"], ["noindex, nofollow"])

    def test_notes_failure_is_502(self):
        with patch.object(api, "clock", return_value=NOW), patch.object(
            api, "fetch_notes", side_effect=api.EnerfloError("notes: HTTP 500")
        ):
            captured, raw = invoke(api, "/api/enerflo_installer")
        self.assertEqual(captured["code"], 502)
        self.assertEqual(json.loads(raw), {"error": "enerflo_unavailable", "detail": "notes: HTTP 500"})

    def test_failed_install_fetch_still_returns_200_with_a_warning(self):
        warning = [{"install_id": 5010, "detail": "install: HTTP 500"}]
        stubs = self._stubs(installs={}, warnings=warning)
        with stubs[0], stubs[1], stubs[2], stubs[3]:
            captured, raw = invoke(api, "/api/enerflo_installer?days=10")
        self.assertEqual(captured["code"], 200)
        payload = json.loads(raw)
        self.assertEqual(payload["window"]["days"], 10)
        self.assertTrue(payload["warnings"])
        self.assertEqual(payload["warnings"][0]["detail"], "install: HTTP 500")
        self.assertTrue(payload["rows"])
        self.assertEqual(payload["rows"][0]["customer_name"], "")

    def test_days_are_clamped(self):
        stubs = self._stubs(notes_rows=[], users_rows=[])
        with stubs[0], stubs[1], stubs[2], stubs[3]:
            _low, low_raw = invoke(api, "/api/enerflo_installer?days=0")
            _high, high_raw = invoke(api, "/api/enerflo_installer?days=999")
        self.assertEqual(json.loads(low_raw)["window"]["days"], 1)
        self.assertEqual(json.loads(high_raw)["window"]["days"], 180)

    def test_page_shell_has_no_note_data(self):
        captured, raw = invoke(page, "/enerflo-installer")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Cache-Control"], ["private, no-store"])
        self.assertEqual(captured["headers"]["X-Robots-Tag"], ["noindex, nofollow"])
        text = raw.decode("utf-8")
        self.assertIn('<meta name="robots" content="noindex"', text)
        self.assertIn("/api/enerflo_installer", text)
        self.assertIn("Survey passed (reply probably not needed)", text)
        self.assertIn("Recently answered (14d)", text)
        self.assertIn("Needs mapping", text)
        self.assertIn('id="error"', text)
        self.assertNotIn("type=\"password\"", text)
        for name in FIXTURE_NAMES:
            self.assertNotIn(name, text)

    def test_request_does_not_construct_firestore(self):
        firestore = importlib.util.find_spec("google.cloud.firestore")
        if firestore is None:
            self.skipTest("google.cloud.firestore is not installed")
        import google.cloud.firestore as firestore_mod

        stubs = self._stubs(notes_rows=[], users_rows=[])
        with patch.object(firestore_mod, "Client") as mocked, stubs[0], stubs[1], stubs[2], stubs[3]:
            captured, raw = invoke(api, "/api/enerflo_installer")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(json.loads(raw)["counts"]["open"], 0)
        self.assertFalse(mocked.called)


class ClientTests(unittest.TestCase):
    def setUp(self):
        client.clear_caches()

    def tearDown(self):
        client.clear_caches()

    def test_users_cached_for_a_day_and_personal_fields_dropped(self):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=10):
            calls["n"] += 1
            self.assertEqual(timeout, 10)
            self.assertEqual(req.get_method(), "GET")
            self.assertIn("/v3/users", req.full_url)
            return FakeResp(
                {
                    "success": True,
                    "page": 1,
                    "totalPages": 1,
                    "results": [
                        {
                            "id": 1,
                            "first_name": "Tom",
                            "last_name": "Dunne",
                            "company_id": 8090,
                            "active": 1,
                            "email": "tom@example.com",
                            "intercom_user_jwt": "secret-jwt",
                        }
                    ],
                }
            )

        with patch.object(client, "urlopen", fake_urlopen), patch.object(client, "MIN_INTERVAL", 0):
            first = client.fetch_users("test-key")
            second = client.fetch_users("test-key")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(first, second)
        self.assertEqual(set(first[0]), {"id", "first_name", "last_name", "company_id", "active"})
        self.assertNotIn("email", first[0])
        self.assertNotIn("intercom_user_jwt", first[0])

    def test_installs_cached_and_limited_to_requested_ids(self):
        calls = []

        def fake_urlopen(req, timeout=10):
            calls.append(req.full_url)
            payload = json.loads(INSTALL_FIXTURE.read_text())
            return FakeResp(payload)

        with patch.object(client, "urlopen", fake_urlopen), patch.object(client, "MIN_INTERVAL", 0):
            first, warnings = client.fetch_installs("test-key", [5010, 5010])
            second, _again = client.fetch_installs("test-key", [5010])
        self.assertEqual(warnings, [])
        self.assertEqual(len(calls), 1)
        self.assertIn("/v3/installs/5010", calls[0])
        slim = first[5010]
        self.assertEqual(
            set(slim),
            {"customer_name", "rep_name", "rep_id", "status", "milestone"},
        )
        self.assertEqual(slim["customer_name"], "Casey Example")
        self.assertEqual(slim["rep_name"], "Ada Rep")
        self.assertEqual(slim["milestone"], "Survey")
        self.assertNotIn("email", slim)
        self.assertNotIn("agreement_url", slim)
        self.assertEqual(second[5010], slim)

    def test_concurrency_cap_and_budget(self):
        state = {"in": 0, "max": 0}
        lock = threading.Lock()

        def fake_urlopen(req, timeout=10):
            with lock:
                state["in"] += 1
                state["max"] = max(state["max"], state["in"])
            time.sleep(0.15)
            with lock:
                state["in"] -= 1
            return FakeResp(json.loads(INSTALL_FIXTURE.read_text()))

        with patch.object(client, "urlopen", fake_urlopen), patch.object(client, "MIN_INTERVAL", 0):
            results, warnings = client.fetch_installs("test-key", [1, 2, 3, 4, 5, 6])
        self.assertEqual(warnings, [])
        self.assertEqual(set(results), {1, 2, 3, 4, 5, 6})
        self.assertGreaterEqual(state["max"], 2)
        self.assertLessEqual(state["max"], 4)

        def fail_open(req, timeout=10):
            raise AssertionError("budget should not start a request")

        with patch.object(client, "urlopen", fail_open), patch.object(client, "INSTALL_BUDGET_S", 0):
            _none, budget_warnings = client.fetch_installs("test-key", [7, 8, 9])
        self.assertEqual(len(budget_warnings), 3)
        self.assertTrue(all(item["detail"] == "install: budget" for item in budget_warnings))

    def test_429_retries_once_and_caps_retry_after(self):
        calls = {"n": 0}
        slept = []

        def fake_urlopen(req, timeout=10):
            calls["n"] += 1
            if calls["n"] == 1:
                raise http_error(429, "30")
            return FakeResp({"success": True, "page": 1, "totalPages": 1, "notes": []})

        def fake_sleep(seconds):
            slept.append(seconds)

        with patch.object(client, "urlopen", fake_urlopen), patch.object(client, "MIN_INTERVAL", 0), patch.object(
            client.time, "sleep", fake_sleep
        ):
            rows = client.fetch_notes("test-key", "2026-07-26T21:18:00Z")
        self.assertEqual(rows, [])
        self.assertEqual(calls["n"], 2)
        self.assertEqual(slept, [5.0])

    def test_second_429_gives_up(self):
        def fake_urlopen(req, timeout=10):
            raise http_error(429, "1")

        with patch.object(client, "urlopen", fake_urlopen), patch.object(client, "MIN_INTERVAL", 0), patch.object(
            client.time, "sleep", lambda _seconds: None
        ):
            with self.assertRaises(client.EnerfloError) as caught:
                client.fetch_users("test-key")
        self.assertEqual(caught.exception.detail, "users: HTTP 429")


class SafetyTests(unittest.TestCase):
    def test_new_modules_do_not_touch_firestore_or_the_payroll_gate(self):
        forbidden = (
            "firestore",
            "google.cloud",
            "get_db",
            "demo_rate",
            "payroll_gate",
            "PAYROLL_GATE",
            "hs_payroll",
            "X-Payroll-Gate",
        )
        for path in NEW_FILES:
            text = path.read_text()
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{path.name} contains {needle}")
        logic_src = (API / "enerflo_installer_logic.py").read_text()
        self.assertNotIn("os.environ", logic_src)
        self.assertNotIn("urllib", logic_src)
        client_src = (API / "enerflo_installer_client.py").read_text()
        self.assertIn('method="GET"', client_src)
        for bad in (
            'method="POST"',
            "method='POST'",
            'method="PUT"',
            "method='PUT'",
            'method="PATCH"',
            "method='PATCH'",
            'method="DELETE"',
            "method='DELETE'",
            "data=",
        ):
            self.assertNotIn(bad, client_src)
        self.assertFalse((API / "enerflo_installer_login.py").exists())
        self.assertFalse((API / "enerflo_installer_logout.py").exists())
        self.assertFalse((PRIVATE / "enerflo_installer.py").exists())

    def test_loading_modules_does_not_import_google_cloud(self):
        code = """
import importlib.util
import sys
from pathlib import Path
root = Path(%r)
api = root / "api"
sys.path.insert(0, str(api))
before = set(sys.modules)
for name in (
    "enerflo_installer_logic",
    "enerflo_installer_client",
    "enerflo_installer",
    "enerflo_installer_page",
):
    path = api / (name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_fresh_import", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name + "_fresh_import"] = module
    spec.loader.exec_module(module)
added = sorted(
    name for name in sys.modules
    if name not in before and (name == "google.cloud" or name.startswith("google.cloud."))
)
if added:
    raise SystemExit("imported " + ",".join(added))
""" % (str(ROOT),)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_no_inbound_links(self):
        needles = ("enerflo-installer", "enerflo_installer")
        allowed = {
            "api/enerflo_installer_logic.py",
            "api/enerflo_installer_client.py",
            "api/enerflo_installer.py",
            "api/enerflo_installer_page.py",
            "tests/test_enerflo_installer.py",
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
        self.assertNotIn("enerflo-installer", nav)
        self.assertNotIn("enerflo_installer", nav)

    def test_rewrites_are_public_and_existing_vercel_config_stays(self):
        vercel = json.loads((ROOT / "vercel.json").read_text())
        rewrites = vercel["rewrites"]
        sources = [item["source"] for item in rewrites]
        self.assertLess(sources.index("/enerflo-installer"), sources.index("/api/:path*"))
        self.assertLess(sources.index("/enerflo-installer/"), sources.index("/api/:path*"))
        page_rewrite = next(item for item in rewrites if item["source"] == "/enerflo-installer")
        slash_rewrite = next(item for item in rewrites if item["source"] == "/enerflo-installer/")
        self.assertEqual(page_rewrite["destination"], "/api?hs=enerflo_installer_page")
        self.assertEqual(slash_rewrite["destination"], "/api?hs=enerflo_installer_page")
        api_rewrite = next(item for item in rewrites if item["source"] == "/api/:path*")
        self.assertEqual(api_rewrite["destination"], "/api?hs=:path*")
        self.assertEqual(len(vercel["crons"]), 1)
        self.assertEqual(vercel["crons"][0]["path"], "/api/warm_cache")
        self.assertEqual(vercel["functions"]["api/index.py"]["includeFiles"], "api/**")


if __name__ == "__main__":
    unittest.main()
