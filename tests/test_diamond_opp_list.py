# -*- coding: utf-8 -*-
"""Diamond opportunity list: Diamond created opps, excluding the Sweeper pipeline."""

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
        self.fetched_collections: list[str] = []

    def collection(self, name: str):
        return _Coll(self, name)

    def get_all(self, refs):
        self.get_all_calls += 1
        refs = list(refs)
        self.batch_sizes.append(len(refs))
        if refs:
            self.fetched_collections.append(refs[0].collection)
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


class FrozenCycleLinkTests(unittest.TestCase):
    def test_frozen_cycle_row_links_to_the_real_opp(self):
        opp = "h0HzaCdAJ5iXujzn6RGF"
        url = f"https://app.gohighlevel.com/v2/location/{LOCATION}/opportunities/list/{opp}?tab=OpportunityDetails"
        self.assertEqual(metrics.opportunity_url(LOCATION, f"{opp}~cycle2"), url)
        self.assertEqual(metrics.opportunity_url(LOCATION, opp), url)
        self.assertEqual(metrics.opportunity_url(LOCATION, ""), "")


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
        self.assertEqual(listing["rows"][0]["appointmentAtIso"], "2026-10-02T18:30:00Z")
        self.assertEqual(listing["rows"][0]["pipeline"], "Virtual")
        self.assertEqual(listing["rows"][1]["appointmentAt"], "")
        self.assertEqual(listing["rows"][1]["appointmentAtIso"], "")
        self.assertEqual(listing["rows"][1]["pipeline"], "Rehash")
        self.assertEqual(
            listing["rows"][0]["opportunityUrl"],
            "https://app.gohighlevel.com/v2/location/"
            + LOCATION
            + "/opportunities/list/o-late?tab=OpportunityDetails",
        )
        self.assertEqual(listing["rows"][0]["phone"], PHONE)

    def test_sweeper_pipeline_is_excluded_from_the_list_only(self):
        sweeper_id = metrics.SWEEPER_PIPELINE_ID
        created = {
            "window_start_local": "2026-10-01T00:00:00-04:00",
            "window_end_local": "2026-10-16T00:00:00-04:00",
            "sample_rows": [
                {
                    "opportunityId": "by-id",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Stale",
                    "pipelineId": sweeper_id,
                    "pipelineStageName": "New Appointment",
                    "createdAt": "2026-10-02T12:00:00Z",
                },
                {
                    "opportunityId": "id-on-opp",
                    "sweeperRehashLastName": "Diamond",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-02T13:00:00Z",
                },
                {
                    "opportunityId": "by-name",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Sweeper",
                    "pipelineStageName": "New Appointment",
                    "createdAt": "2026-10-03T12:00:00Z",
                },
                {
                    "opportunityId": "by-case",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "  SWEEPER  ",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-03T13:00:00Z",
                },
                {
                    "opportunityId": "by-directory",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Old Label",
                    "pipelineId": "alias-sweep",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-04T12:00:00Z",
                },
                {
                    "opportunityId": "rehash",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Rehash",
                    "pipelineId": "rehash-id",
                    "pipelineStageName": "New Appointment",
                    "createdAt": "2026-10-05T12:00:00Z",
                },
                {
                    "opportunityId": "rochester",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Rochester",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-01T12:00:00Z",
                },
                {
                    "opportunityId": "buffalo",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Buffalo",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-06T12:00:00Z",
                },
                {
                    "opportunityId": "syracuse",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Syracuse",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-07T12:00:00Z",
                },
                {
                    "opportunityId": "virtual",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Virtual",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-08T12:00:00Z",
                },
                {
                    "opportunityId": "slash",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Sweeper/Rehash",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-08T13:00:00Z",
                },
                {
                    "opportunityId": "virtual-sweep",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Virtual/Sweeper",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-08T14:00:00Z",
                },
                {
                    "opportunityId": "team",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Sweeper Team",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-08T15:00:00Z",
                },
                {
                    "opportunityId": "stale-keep",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Sweeper",
                    "pipelineId": "p-buf",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-08T16:00:00Z",
                },
            ],
        }
        docs = {
            ("ghl_opportunities_v2", "id-on-opp"): {"pipelineId": sweeper_id},
            ("ghl_opportunities_v2", "rochester"): {"appointmentStartTime": "2026-10-10T16:00:00Z"},
            ("ghl_opportunities_v2", "virtual"): {"appointmentStartTime": "2026-10-09T16:00:00Z"},
            ("ghl_pipelines_v2", sweeper_id): {"id": sweeper_id, "name": "Not Sweeper", "stages": []},
            ("ghl_pipelines_v2", "alias-sweep"): {"id": "alias-sweep", "name": "Sweeper", "stages": []},
            ("ghl_pipelines_v2", "rehash-id"): {"id": "rehash-id", "name": "Rehash", "stages": []},
            ("ghl_pipelines_v2", "p-buf"): {"id": "p-buf", "name": "Buffalo", "stages": []},
        }
        with (
            mock.patch("opportunities_created.compute", return_value=created),
            mock.patch("demo_rate.build_payload", return_value={"rows": []}),
            mock.patch("sales.compute_sales", return_value={}),
        ):
            sweeper_out = sweeper.compute_diamond_sweeper(
                object(), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
            listing = metrics.compute_diamond_opp_list(
                _Db(docs), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
        self.assertEqual(sweeper_out["opps_created"], 14)
        self.assertEqual(listing["row_count"], 9)
        self.assertEqual(len(listing["rows"]), 9)
        self.assertEqual(
            [row["opportunityId"] for row in listing["rows"]],
            [
                "rochester",
                "virtual",
                "buffalo",
                "rehash",
                "slash",
                "stale-keep",
                "syracuse",
                "team",
                "virtual-sweep",
            ],
        )
        self.assertEqual(
            [row["pipeline"] for row in listing["rows"]],
            [
                "Rochester",
                "Virtual",
                "Buffalo",
                "Rehash",
                "Sweeper/Rehash",
                "Buffalo",
                "Syracuse",
                "Sweeper Team",
                "Virtual/Sweeper",
            ],
        )
        self.assertEqual(listing["rows"][0]["appointmentAt"], "Oct 10, 2026, 12:00 PM ET")
        kept = {row["opportunityId"] for row in listing["rows"]}
        for dropped in ("by-id", "id-on-opp", "by-name", "by-case", "by-directory"):
            self.assertNotIn(dropped, kept)
        self.assertIn(sweeper_id, listing["contract"]["population"])
        sweeper_src = (METRICS / "diamond_sweeper.py").read_text(encoding="utf-8")
        self.assertNotIn("is_sweeper_pipeline", sweeper_src)
        self.assertNotIn("SWEEPER_PIPELINE_ID", sweeper_src)
        recap = (API / "rep_daily_recap.py").read_text(encoding="utf-8")
        ads = (METRICS / "ads_dashboard.py").read_text(encoding="utf-8")
        needle = f'SWEEPER_PIPELINE_ID = "{sweeper_id}"'
        self.assertIn(needle, recap)
        self.assertIn(needle, ads)

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

    def test_default_sort_is_appointment_time_latest_first_not_the_display_string(self):
        created = {
            "sample_rows": [
                {
                    "opportunityId": "no-appt",
                    "sweeperRehashLastName": "Diamond",
                    "createdAt": "2026-10-09T00:00:00Z",
                    "pipeline": "Rehash",
                },
                {
                    "opportunityId": "nine-am",
                    "sweeperRehashLastName": "Diamond",
                    "createdAt": "2026-10-08T00:00:00Z",
                    "pipelineStageName": "New Appointment",
                },
                {
                    "opportunityId": "ten-am",
                    "sweeperRehashLastName": "Diamond",
                    "createdAt": "2026-10-01T00:00:00Z",
                    "pipelineStageName": "New Appointment",
                },
            ]
        }
        docs = {
            ("ghl_opportunities_v2", "nine-am"): {"appointmentStartTime": "2026-10-02T13:00:00Z"},
            ("ghl_opportunities_v2", "ten-am"): {"appointmentStartTime": "2026-10-02T14:00:00Z"},
            ("ghl_opportunities_v2", "no-appt"): {},
        }
        with (
            mock.patch("opportunities_created.compute", return_value=created),
            mock.patch("demo_rate.build_payload", return_value={"rows": []}),
            mock.patch("sales.compute_sales", return_value={}),
        ):
            sweeper_out = sweeper.compute_diamond_sweeper(
                object(), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
            listing = metrics.compute_diamond_opp_list(
                _Db(docs), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
        self.assertEqual(listing["row_count"], sweeper_out["opps_created"])
        self.assertEqual(listing["date_field"], "createdAt")
        self.assertEqual(
            [row["opportunityId"] for row in listing["rows"]],
            ["ten-am", "nine-am", "no-appt"],
        )
        self.assertEqual(listing["rows"][0]["appointmentAt"], "Oct 2, 2026, 10:00 AM ET")
        self.assertEqual(listing["rows"][1]["appointmentAt"], "Oct 2, 2026, 9:00 AM ET")
        self.assertEqual(listing["rows"][2]["appointmentAt"], "")
        self.assertGreater(listing["rows"][0]["appointmentAtIso"], listing["rows"][1]["appointmentAtIso"])

    def test_pipeline_name_comes_from_ghl_pipelines_by_id(self):
        created = {
            "sample_rows": [
                {
                    "opportunityId": "o-dir",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Stale Name",
                    "pipelineId": "p-buf",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-02T12:00:00Z",
                },
                {
                    "opportunityId": "o-from-opp",
                    "sweeperRehashLastName": "Diamond",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-03T12:00:00Z",
                },
                {
                    "opportunityId": "o-named",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Virtual",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-04T12:00:00Z",
                },
            ]
        }
        db = _Db(
            {
                ("ghl_opportunities_v2", "o-dir"): {"pipelineId": "p-buf", "appointmentStartTime": "2026-10-06T15:00:00Z"},
                ("ghl_opportunities_v2", "o-from-opp"): {"pipelineId": "p-roc", "appointmentStartTime": "2026-10-05T15:00:00Z"},
                ("ghl_opportunities_v2", "o-named"): {},
                ("ghl_pipelines_v2", "p-buf"): {"id": "p-buf", "name": "Buffalo", "stages": [{"id": "s1", "name": "Demo"}]},
                ("ghl_pipelines_v2", "p-roc"): {"id": "p-roc", "name": "Rochester", "stages": []},
            }
        )
        with mock.patch("opportunities_created.compute", return_value=created):
            listing = metrics.compute_diamond_opp_list(
                db, year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
        by_id = {row["opportunityId"]: row for row in listing["rows"]}
        self.assertEqual(by_id["o-dir"]["pipeline"], "Buffalo")
        self.assertEqual(by_id["o-from-opp"]["pipeline"], "Rochester")
        self.assertEqual(by_id["o-named"]["pipeline"], "Virtual")
        self.assertIn("ghl_pipelines_v2", db.fetched_collections)
        self.assertEqual(listing["row_count"], 3)

    def test_pipeline_lookup_failure_keeps_the_row_and_the_name_already_on_it(self):
        created = {
            "sample_rows": [
                {
                    "opportunityId": "o-keep",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Virtual",
                    "pipelineId": "missing-pipe",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-02T12:00:00Z",
                }
            ]
        }
        with (
            mock.patch("opportunities_created.compute", return_value=created),
            mock.patch("sold_date_gaps.load_pipelines_by_ids", side_effect=RuntimeError("lookup failed")),
        ):
            listing = metrics.compute_diamond_opp_list(
                _Db({}), year=2026, month=10, start="2026-10-01", end="2026-10-15"
            )
        self.assertEqual(listing["row_count"], 1)
        self.assertEqual(listing["rows"][0]["pipeline"], "Virtual")
        self.assertEqual(listing["rows"][0]["pipelineStage"], "Demo")

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

    def test_every_date_window_drops_the_sweeper_pipeline_from_the_count(self):
        sweeper_id = metrics.SWEEPER_PIPELINE_ID
        created = {
            "sample_rows": [
                {
                    "opportunityId": "keep-rehash",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Rehash",
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-02T12:00:00Z",
                },
                {
                    "opportunityId": "drop-sweeper",
                    "sweeperRehashLastName": "Diamond",
                    "pipeline": "Sweeper",
                    "pipelineId": sweeper_id,
                    "pipelineStageName": "Demo",
                    "createdAt": "2026-10-03T12:00:00Z",
                },
            ]
        }
        paths = (
            "/api/metrics/diamond_opp_list",
            "/api/metrics/diamond_opp_list?start=2026-10-01&end=2026-10-17",
            "/api/metrics/diamond_opp_list?start=2026-10-06&end=2026-10-10",
            "/api/metrics/diamond_opp_list?year=2026&month=10",
        )
        with (
            mock.patch("sales.get_db", return_value=_Db({})),
            mock.patch("opportunities_created.compute", return_value=created),
        ):
            for path in paths:
                req = _Request(path)
                metrics.handler.do_GET(req)
                payload = json.loads(req.wfile.buf.decode("utf-8"))
                self.assertEqual(req.status, 200, path)
                self.assertEqual(payload["row_count"], 1, path)
                self.assertEqual(payload["rows"][0]["opportunityId"], "keep-rehash")
                self.assertEqual(payload["rows"][0]["pipeline"], "Rehash")

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
        self.assertIn('label: "Name"', html)
        self.assertIn('label: "Pipeline"', html)
        self.assertIn('label: "Appointment outcome"', html)
        self.assertIn('label: "Appointment date and time"', html)
        self.assertIn('label: "Phone"', html)
        self.assertIn('data-sort="', html)
        self.assertIn('class="sortable"', html)
        self.assertIn('class="sort-ind"', html)
        self.assertIn("▲", html)
        self.assertIn("▼", html)
        self.assertIn('aria-sort="', html)
        self.assertIn("Date.parse", html)
        self.assertIn("appointmentAtIso", html)
        self.assertIn('sortKey = "appointment"', html)
        self.assertIn('sortDir = "desc"', html)
        self.assertIn('kind: "date"', html)
        self.assertIn("Sorted by appointment date and time, latest first", html)
        self.assertNotIn("Newest created date first", html)
        self.assertIn("Opportunities on the Sweeper pipeline are left off this list.", html)
        self.assertNotIn("row count matches Diamond Sweeper", html)
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
