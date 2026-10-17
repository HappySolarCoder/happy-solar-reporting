# -*- coding: utf-8 -*-
"""Diamond opportunity list: same created-opp population as Diamond Sweeper."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (API, METRICS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dashboard_nav import render_dashboard_nav  # noqa: E402
import dashboard_nav as nav  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


page = _load("diamond_opp_list_page", API / "diamond_opp_list.py")
metrics = _load("diamond_opp_list_metrics", METRICS / "diamond_opp_list.py")
sweeper_page = _load("diamond_opp_list_sweeper_page", API / "diamond_sweeper.py")
sweeper = _load("diamond_opp_list_sweeper_metrics", METRICS / "diamond_sweeper.py")
index = _load("diamond_opp_list_index", API / "index.py")

NY = ZoneInfo("America/New_York")
PHONE = "585-555-0199"
LOCATION = "MMKRDviKggXzlcHQTnvZ"


class _Snap:
    def __init__(self, doc_id: str, data: dict | None, exists: bool = True):
        self.id = doc_id
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class _Ref:
    def __init__(self, collection: str, doc_id: str):
        self.collection = collection
        self.id = doc_id


class _Coll:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name

    def document(self, doc_id: str):
        return _Ref(self.name, doc_id)

    def stream(self):
        raise AssertionError("full collection scan")

    def where(self, *args, **kwargs):
        raise AssertionError("collection query")


class _Db:
    def __init__(self, docs: dict[tuple[str, str], dict]):
        self.docs = docs
        self.get_all_calls = 0
        self.batch_sizes: list[int] = []

    def collection(self, name: str):
        return _Coll(self, name)

    def get_all(self, refs):
        self.get_all_calls += 1
        refs = list(refs)
        self.batch_sizes.append(len(refs))
        snaps = []
        for ref in refs:
            data = self.docs.get((ref.collection, ref.id))
            if data is None:
                snaps.append(_Snap(ref.id, {}, exists=False))
            else:
                snaps.append(_Snap(ref.id, data))
        return snaps


class _Body:
    def __init__(self):
        self.buf = bytearray()

    def write(self, data):
        self.buf.extend(data)


class _Request:
    def __init__(self, path: str, headers: dict | None = None):
        self.path = path
        self.headers = headers or {}
        self.wfile = _Body()
        self.status = None
        self.sent = []

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.sent.append((key, value))

    def end_headers(self):
        return None


CREATED = {
    "window_start_local": "2026-10-01T00:00:00-04:00",
    "window_end_local": "2026-10-16T00:00:00-04:00",
    "sample_rows": [
        {
            "opportunityId": "o-early",
            "sweeperRehashLastName": "diamond",
            "contactId": "c1",
            "pipeline": "Rehash",
            "pipelineStageName": "New Appointment",
            "createdAt": "2026-10-02T14:00:00.000Z",
        },
        {
            "opportunityId": "o-late",
            "sweeperRehashLastName": "DIAMOND",
            "contactId": "c1",
            "pipeline": "Virtual",
            "pipelineStageName": "Demo-Negotiating",
            "createdAt": "2026-10-02T14:05:00.000Z",
        },
        {
            "opportunityId": "o-other",
            "sweeperRehashLastName": "Smith",
            "contactId": "c2",
            "createdAt": "2026-10-03T00:00:00.000Z",
        },
        {
            "opportunityId": "o-full",
            "sweeperRehashLastName": "Tyler Diamond",
            "contactId": "c3",
            "createdAt": "2026-10-04T00:00:00.000Z",
        },
    ],
}


def _docs():
    return {
        ("ghl_contacts_v2", "c1"): {
            "id": "c1",
            "firstName": "Ada",
            "lastName": "Lovelace",
            "phone": PHONE,
            "locationId": "contact-loc",
        },
        ("ghl_opportunities_v2", "o-late"): {
            "id": "o-late",
            "locationId": LOCATION,
            "dispositionValue": "Sit",
            "appointmentStartTime": "2026-10-02T18:30:00Z",
        },
        ("ghl_opportunities_v2", "o-early"): {
            "id": "o-early",
            "name": "Should not replace contact",
        },
    }


class PopulationTests(unittest.TestCase):
    def test_row_count_equals_sweeper_opps_created_for_the_same_range(self):
        seen = {}

        def fake_created(db, contract, **kwargs):
            seen["pipeline_scope"] = kwargs.get("pipeline_scope")
            seen["start"] = kwargs.get("start")
            seen["end"] = kwargs.get("end")
            return CREATED

        with (
            mock.patch("opportunities_created.compute", side_effect=fake_created),
            mock.patch("demo_rate.build_payload", return_value={"rows": []}),
            mock.patch("sales.compute_sales", return_value={}),
        ):
            sweeper_out = sweeper.compute_diamond_sweeper(
                object(), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
            listing = metrics.compute_diamond_opp_list(
                _Db(_docs()),
                year=2026,
                month=10,
                start="2026-10-01",
                end="2026-10-15",
                include_phones=True,
            )
        self.assertEqual(seen["pipeline_scope"], "all")
        self.assertEqual(seen["start"], "2026-10-01")
        self.assertEqual(seen["end"], "2026-10-15")
        self.assertEqual(listing["row_count"], sweeper_out["opps_created"])
        self.assertEqual(len(listing["rows"]), sweeper_out["opps_created"])
        self.assertEqual([row["opportunityId"] for row in listing["rows"]], ["o-late", "o-early"])
        self.assertNotIn("o-deleted-within-10-min", [row["opportunityId"] for row in listing["rows"]])
        self.assertEqual(listing["rows"][0]["name"], "Ada Lovelace")
        self.assertEqual(listing["rows"][0]["appointmentOutcome"], "Demo-Negotiating · Sit")
        self.assertEqual(listing["rows"][0]["disposition"], "Sit")
        self.assertEqual(listing["rows"][0]["appointmentAt"], "Oct 2, 2026, 2:30 PM ET")
        self.assertEqual(listing["rows"][1]["appointmentAt"], "")
        self.assertEqual(
            listing["rows"][0]["opportunityUrl"],
            "https://app.gohighlevel.com/v2/location/"
            + LOCATION
            + "/opportunities/list/o-late?tab=OpportunityDetails",
        )
        self.assertEqual(listing["rows"][0]["phone"], PHONE)

    def test_contact_location_is_used_when_the_opportunity_has_none(self):
        created = {
            "sample_rows": [
                {
                    "opportunityId": "o-contact-loc",
                    "sweeperRehashLastName": "Diamond",
                    "contactId": "c9",
                    "pipelineStageName": "Reschedule Needed",
                    "createdAt": "2026-10-02T12:00:00Z",
                }
            ]
        }
        db = _Db(
            {
                ("ghl_contacts_v2", "c9"): {"firstName": "Grace", "lastName": "Hopper", "locationId": "from-contact"},
                ("ghl_opportunities_v2", "o-contact-loc"): {"dispositionValue": "No Sit"},
            }
        )
        with mock.patch("opportunities_created.compute", return_value=created):
            listing = metrics.compute_diamond_opp_list(
                db, year=2026, month=10, start="2026-10-01", end="2026-10-15", include_phones=False
            )
        self.assertEqual(db.get_all_calls, 2)
        self.assertTrue(all(size > 0 for size in db.batch_sizes))
        row = listing["rows"][0]
        self.assertEqual(
            row["opportunityUrl"],
            "https://app.gohighlevel.com/v2/location/from-contact/opportunities/list/o-contact-loc?tab=OpportunityDetails",
        )
        self.assertEqual(row["appointmentOutcome"], "Reschedule Needed · No Sit")
        self.assertNotIn("phone", row)
        encoded = json.dumps(listing)
        self.assertNotIn(PHONE, encoded)

    def test_blank_stage_is_filled_from_the_pipeline_directory(self):
        created = {
            "sample_rows": [
                {
                    "opportunityId": "o-stage",
                    "sweeperRehashLastName": "Diamond",
                    "contactId": "c1",
                    "pipelineId": "pipe-1",
                    "pipelineStageId": "stage-resched",
                    "createdAt": "2026-10-05T00:00:00Z",
                }
            ]
        }
        with (
            mock.patch("opportunities_created.compute", return_value=created),
            mock.patch(
                "sold_date_gaps.load_pipelines_by_ids",
                return_value=({}, {"stage-resched": "Reschedule Needed"}),
            ),
        ):
            listing = metrics.compute_diamond_opp_list(
                _Db({}), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
        self.assertEqual(listing["rows"][0]["pipelineStage"], "Reschedule Needed")
        self.assertEqual(listing["rows"][0]["appointmentOutcome"], "Reschedule Needed")

    def test_phones_can_be_withheld_from_the_payload(self):
        with mock.patch("opportunities_created.compute", return_value=CREATED):
            hidden = metrics.compute_diamond_opp_list(
                _Db(_docs()),
                year=2026,
                month=10,
                start="2026-10-01",
                end="2026-10-15",
                include_phones=False,
            )
        self.assertFalse(hidden["phones_included"])
        self.assertNotIn("phone", hidden["rows"][0])
        self.assertNotIn(PHONE, json.dumps(hidden))


class WindowTests(unittest.TestCase):
    def test_default_is_all_time_from_the_fixed_lower_bound(self):
        now = datetime(2026, 10, 17, 15, tzinfo=NY)
        self.assertEqual(
            metrics.resolve_list_window({}, now),
            (2025, 1, "2025-01-01", "2026-10-17"),
        )

    def test_explicit_dates_and_calendar_month(self):
        self.assertEqual(
            metrics.resolve_list_window({"start": ["2026-10-05"], "end": ["2026-10-11"]}),
            (2026, 10, "2026-10-05", "2026-10-11"),
        )
        self.assertEqual(
            metrics.resolve_list_window({"year": ["2026"], "month": ["9"]}),
            (2026, 9, "2026-09-01", "2026-09-30"),
        )

    def test_rejects_a_backwards_range(self):
        with self.assertRaises(ValueError):
            metrics.resolve_list_window({"start": ["2026-10-15"], "end": ["2026-10-01"]})


class RequestTests(unittest.TestCase):
    def _get(self, path: str, headers: dict | None = None):
        db = _Db(_docs())

        def fake_created(db_arg, contract, **kwargs):
            return CREATED

        with (
            mock.patch("sales.get_db", return_value=db),
            mock.patch("opportunities_created.compute", side_effect=fake_created),
        ):
            req = _Request(path, headers)
            metrics.handler.do_GET(req)
        return req, db

    def test_unauthenticated_request_does_not_return_phone_numbers(self):
        req, db = self._get("/api/metrics/diamond_opp_list?start=2026-10-01&end=2026-10-15")
        body = req.wfile.buf.decode("utf-8")
        self.assertEqual(req.status, 200)
        self.assertGreaterEqual(db.get_all_calls, 1)
        self.assertNotIn("WWW-Authenticate", [key for key, _value in req.sent])
        self.assertIn(("Cache-Control", metrics.SIBLING_CACHE), req.sent)
        self.assertNotIn(PHONE, body)
        payload = json.loads(body)
        self.assertEqual(payload["row_count"], 2)
        self.assertFalse(payload["phones_included"])
        self.assertTrue(all("phone" not in row for row in payload["rows"]))

    def test_same_origin_dashboard_fetch_includes_the_phone(self):
        req, _db = self._get(
            "/api/metrics/diamond_opp_list?start=2026-10-01&end=2026-10-15",
            {"Sec-Fetch-Site": "same-origin"},
        )
        body = req.wfile.buf.decode("utf-8")
        self.assertEqual(req.status, 200)
        self.assertIn(("Cache-Control", metrics.PHONE_CACHE), req.sent)
        self.assertIn(PHONE, body)
        payload = json.loads(body)
        self.assertEqual(payload["rows"][0]["phone"], PHONE)

    def test_settings_password_includes_the_phone_and_a_wrong_password_does_not(self):
        token_ok = __import__("base64").b64encode(b"ada:" + b"secret").decode()
        token_bad = __import__("base64").b64encode(b"ada:" + b"nope").decode()
        with mock.patch.dict("os.environ", {"SETTINGS_PASSWORD": "secret"}):
            allowed, _db = self._get(
                "/api/metrics/diamond_opp_list",
                {"Authorization": "Basic " + token_ok},
            )
            denied, _db = self._get(
                "/api/metrics/diamond_opp_list",
                {"Authorization": "Basic " + token_bad},
            )
        self.assertIn(PHONE, allowed.wfile.buf.decode("utf-8"))
        denied_body = denied.wfile.buf.decode("utf-8")
        self.assertNotIn(PHONE, denied_body)
        self.assertTrue(all("phone" not in row for row in json.loads(denied_body)["rows"]))

    def test_page_is_open_like_diamond_sweeper(self):
        src = (API / "diamond_opp_list.py").read_text(encoding="utf-8")
        metric_src = (METRICS / "diamond_opp_list.py").read_text(encoding="utf-8")
        html = page.render_html()
        self.assertNotIn("SETTINGS_PASSWORD", src)
        self.assertNotIn("def _check_auth", src)
        self.assertNotIn("WWW-Authenticate", src)
        self.assertIn("pipeline_scope=\"all\"", metric_src)
        self.assertIn("created_rows", metric_src)
        req = _Request("/api/diamond_opp_list")
        page.handler.do_GET(req)
        self.assertEqual(req.status, 200)
        self.assertIn(("Cache-Control", "no-store"), req.sent)
        self.assertNotIn("WWW-Authenticate", [key for key, _value in req.sent])
        self.assertIn("<title>Diamond — Opportunity List</title>", html)
        self.assertIn("<h1>Diamond — Opportunity List</h1>", html)
        self.assertNotIn('class="kpis"', html)
        self.assertIn("All time", html)
        self.assertIn("hsOpsPresetButtons", html)
        self.assertIn("hsOpsPresetRange", html)
        self.assertIn('data-preset="alltime"', html)
        self.assertIn("opportunity created date (ET)", html)
        self.assertIn("2025-01-01", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("/api/metrics/diamond_opp_list?", html)
        self.assertIn("pipeline_scope", html)
        self.assertIn('data-oc-native-filters="1"', html)
        self.assertIn(">Name</th>", html)
        self.assertIn(">Appointment outcome</th>", html)
        self.assertIn(">Appointment date and time</th>", html)
        self.assertIn(">Phone</th>", html)
        self.assertIn('class="navlink active" href="/api/diamond_opp_list"', html)

    def test_nav_sits_beside_diamond_sweeper_including_the_embed_menu(self):
        html = render_dashboard_nav("diamond_opp_list")
        sales_items = next(items for label, items in nav.NAV_GROUPS if label == "SALES")
        sales_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Sales")
        keys = [item[0] for item in sales_items]
        self.assertEqual(keys[keys.index("diamond_sweeper") + 1], "diamond_opp_list")
        self.assertEqual(sales_keys[sales_keys.index("diamond_sweeper") + 1], "diamond_opp_list")
        self.assertIn(
            ("diamond_opp_list", "Diamond — Opportunity List", "/api/diamond_opp_list"),
            sales_items,
        )
        self.assertIn('class="navlink active" href="/api/diamond_opp_list"', html)
        self.assertIn(
            'class="oc-embed-link active" href="/api/diamond_opp_list" aria-current="page"',
            html,
        )
        nav.embed_menu_plan()

    def test_sweeper_page_links_to_the_list(self):
        html = sweeper_page.render_html()
        self.assertIn('id="oppListLink"', html)
        self.assertIn('href="/api/diamond_opp_list"', html)
        self.assertIn("/api/diamond_opp_list?start=", html)

    def test_index_dispatches_both_routes(self):
        self.assertEqual(index.dispatch_route("/api/diamond_opp_list"), "diamond_opp_list")
        self.assertEqual(index.dispatch_file("diamond_opp_list"), API / "diamond_opp_list.py")
        self.assertEqual(index.dispatch_route("/api/metrics/diamond_opp_list"), "metrics/diamond_opp_list")
        self.assertEqual(
            index.dispatch_file("metrics/diamond_opp_list"),
            METRICS / "diamond_opp_list.py",
        )


if __name__ == "__main__":
    unittest.main()
