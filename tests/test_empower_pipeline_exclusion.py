# -*- coding: utf-8 -*-
"""Empower+ pipeline id never counts in sales-funnel metrics.

The fixture pipeline is named Buffalo, not Empower+, so a name denylist or a
core-name allowlist would keep it. Only the pipeline id 5hPKCGzAskcC6LEZuc1H
drops it. A Buffalo control opportunity in the same window still counts.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import booking_rebooks as booking_rebooks  # noqa: E402
import sc_overview  # noqa: E402
from demo_rate import build_payload as build_demo_rate  # noqa: E402
from opportunities_created import MetricContract, compute as compute_created  # noqa: E402
from opportunities_ran import MetricContract as RanContract  # noqa: E402
from opportunities_ran import compute as compute_ran  # noqa: E402
from pipeline_scope import NON_FUNNEL_PIPELINE_IDS, is_non_funnel_pipeline  # noqa: E402
from sales import SalesMetricContract, compute_sales  # noqa: E402

EMPOWER_PIPELINE_ID = "5hPKCGzAskcC6LEZuc1H"
BUFFALO_PIPELINE_ID = "GQtUlcTmLJ61HZjrGEPC"
SOLD_STAGE_ID = "7981f111-73f2-4593-9662-6b95d99bf51a"
SOLD_DATE_FIELD = "P9oBjgbZjJdeE0OkBj9T"
OWNER = "rep-closer-1"
OCCURRED = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
CREATED_AT = "2026-11-10T15:00:00.000Z"


class Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class Ref:
    def __init__(self, db, name, doc_id):
        self.db = db
        self.name = name
        self.id = str(doc_id)

    def get(self):
        return Snap(self.id, self.db.data.get(self.name, {}).get(self.id))


def _as_dt(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _match(actual, op, expected):
    if op == "in":
        return actual in expected
    if op == "==":
        return actual == expected
    left = actual
    right = expected
    if isinstance(left, str) and isinstance(right, datetime):
        left = _as_dt(left)
    if isinstance(right, str) and isinstance(left, datetime):
        right = _as_dt(right)
    if left is None or right is None:
        return False
    try:
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
    except TypeError:
        return False
    raise AssertionError(op)


class Query:
    def __init__(self, db, name, filters=()):
        self.db = db
        self.name = name
        self.filters = tuple(filters)

    def where(self, field, op, value):
        return Query(self.db, self.name, self.filters + ((field, op, value),))

    def limit(self, _count):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def document(self, doc_id):
        return Ref(self.db, self.name, doc_id)

    def stream(self):
        for doc_id, data in list(self.db.data.get(self.name, {}).items()):
            if all(_match(data.get(field), op, value) for field, op, value in self.filters):
                yield Snap(doc_id, data)


class FakeDB:
    def __init__(self, data):
        self.data = data

    def collection(self, name):
        self.data.setdefault(name, {})
        return Query(self, name)

    def get_all(self, refs):
        for ref in refs:
            yield Snap(ref.id, self.data.get(ref.name, {}).get(ref.id))


def _contact(contact_id, last_name):
    return {
        "id": contact_id,
        "firstName": "Test",
        "lastName": last_name,
        "customFields": [{"id": SOLD_DATE_FIELD, "value": "2026-11-10T00:00:00.000Z"}],
    }


def _opp(opp_id, contact_id, pipeline_id):
    return {
        "id": opp_id,
        "contactId": contact_id,
        "pipelineId": pipeline_id,
        "pipelineStageId": SOLD_STAGE_ID,
        "assignedTo": OWNER,
        "createdAt": CREATED_AT,
        "dispositionValue": "Sit",
        "appointmentOccurredAt": OCCURRED,
        "dispositionDate": OCCURRED,
        "customFields": [],
    }


def make_db():
    return FakeDB(
        {
            "ghl_opportunities_v2": {
                "empower-opp": _opp("empower-opp", "contact-empower", EMPOWER_PIPELINE_ID),
                "buffalo-opp": _opp("buffalo-opp", "contact-buffalo", BUFFALO_PIPELINE_ID),
            },
            "ghl_contacts_v2": {
                "contact-empower": _contact("contact-empower", "Nimbus"),
                "contact-buffalo": _contact("contact-buffalo", "Alden"),
            },
            "ghl_pipelines_v2": {
                EMPOWER_PIPELINE_ID: {
                    "id": EMPOWER_PIPELINE_ID,
                    "name": "Buffalo",
                    "stages": [{"id": SOLD_STAGE_ID, "name": "Sold"}],
                },
                BUFFALO_PIPELINE_ID: {
                    "id": BUFFALO_PIPELINE_ID,
                    "name": "Buffalo",
                    "stages": [{"id": SOLD_STAGE_ID, "name": "Sold"}],
                },
            },
            "roster_people_v1": {
                OWNER: {
                    "ghl_user_id": OWNER,
                    "display_name": "Casey Closer",
                    "role": "rep",
                    "team": "buffalo",
                }
            },
            "ghl_users_v2": {},
            "ghl_appointment_events_v2": {},
            "ghl_opportunity_stage_history_v1": {},
        }
    )


class EmpowerPipelineIdTests(unittest.TestCase):
    def test_id_match_ignores_surrounding_space(self):
        self.assertIn(EMPOWER_PIPELINE_ID, NON_FUNNEL_PIPELINE_IDS)
        self.assertTrue(is_non_funnel_pipeline(EMPOWER_PIPELINE_ID))
        self.assertTrue(is_non_funnel_pipeline("  5hPKCGzAskcC6LEZuc1H  "))
        self.assertFalse(is_non_funnel_pipeline(BUFFALO_PIPELINE_ID))
        self.assertFalse(is_non_funnel_pipeline("Empower+"))

    def test_created_core_and_all_keep_buffalo_only(self):
        booking_rebooks._CACHE.clear()
        core = compute_created(make_db(), MetricContract(), year=2026, month=11, pipeline_scope="core")
        booking_rebooks._CACHE.clear()
        every = compute_created(make_db(), MetricContract(), year=2026, month=11, pipeline_scope="all")
        for payload in (core, every):
            self.assertEqual(payload["result"], 1)
            self.assertEqual([row["opportunityId"] for row in payload["sample_rows"]], ["buffalo-opp"])
            self.assertEqual(payload["breakdowns"]["created_by_pipeline"], {"Buffalo": 1})
            self.assertEqual(payload["contract"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
            self.assertEqual(payload["debug"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
            self.assertNotIn("empower-opp", [row["opportunityId"] for row in payload["sample_rows"]])

    def test_ran_keeps_buffalo_only(self):
        payload = compute_ran(make_db(), RanContract(), year=2026, month=11)
        self.assertEqual(payload["result"], 1)
        self.assertEqual([row["opportunityId"] for row in payload["sample_rows"]], ["buffalo-opp"])
        self.assertEqual(payload["contract"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])

    def test_demo_rate_numerator_and_denominator_keep_buffalo_only(self):
        payload = build_demo_rate(make_db(), 2026, 11, {})
        self.assertEqual(payload["sit_count"], 1)
        self.assertEqual(payload["ran_count"], 1)
        self.assertEqual(payload["result"], 100.0)
        self.assertEqual([row["opportunityId"] for row in payload["rows"]], ["buffalo-opp"])
        self.assertEqual(payload["contract"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
        self.assertEqual(payload["debug"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
        self.assertIn("demo", payload["count_method"].lower())
        self.assertNotIn(" sit", payload["count_method"].lower())

    def test_sales_keeps_buffalo_contact_only(self):
        payload = compute_sales(
            make_db(),
            SalesMetricContract(),
            year=2026,
            month=11,
            tz="America/New_York",
        )
        self.assertEqual(payload["result"], 1)
        self.assertEqual(payload["debug"]["distinct_contact_ids"], 1)
        self.assertEqual(payload["breakdowns"]["sales_by_pipeline"], {"Buffalo": 1})
        self.assertEqual(payload["contract"]["sold_date_field"], f"ghl_contacts_v2.customFields[{SOLD_DATE_FIELD}] (ISO)")
        self.assertIn("contactId", payload["count_method"])
        self.assertEqual(payload["contract"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
        self.assertNotIn("empower-opp", [row.get("opportunityId") for row in payload["sample_rows"]])

    def test_sc_overview_completed_count_keeps_buffalo_only(self):
        payload = sc_overview.build_payload(
            make_db(),
            year=2026,
            month=11,
            start=None,
            end=None,
            touch_year=2026,
            touch_month=11,
            touch_start=None,
            touch_end=None,
            owner_id="",
            team="",
            lead_source="",
        )
        self.assertEqual(payload["totals"]["completed"], 1)
        self.assertEqual(payload["debug"]["completed_rows"], 1)
        self.assertEqual(payload["totals"]["opps_ran"], 1)
        self.assertEqual(payload["totals"]["demos"], 1)
        self.assertEqual(payload["totals"]["sales"], 1)
        self.assertEqual(payload["contract"]["excluded_pipeline_ids"], [EMPOWER_PIPELINE_ID])
        details = []
        for rows in (payload.get("pie_details") or {}).values():
            details.extend(rows)
        names = [row.get("name") for row in details]
        self.assertIn("Alden", " ".join(names))
        self.assertNotIn("Nimbus", " ".join(names))

    def test_empower_opp_created_today_including_auto_create_does_not_change_counts(self):
        ny = ZoneInfo("America/New_York")
        moment = datetime.now(ny) - timedelta(minutes=1)
        created = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        sold = moment.date().isoformat() + "T00:00:00.000Z"

        def database(extra_opps):
            db = make_db()
            db.data["ghl_opportunities_v2"].pop("empower-opp")
            db.data["ghl_contacts_v2"].pop("contact-empower")
            buffalo = db.data["ghl_opportunities_v2"]["buffalo-opp"]
            buffalo["createdAt"] = created
            buffalo["appointmentOccurredAt"] = moment
            buffalo["dispositionDate"] = moment
            db.data["ghl_contacts_v2"]["contact-buffalo"]["customFields"] = [
                {"id": SOLD_DATE_FIELD, "value": sold}
            ]
            for opp_id, opp in extra_opps.items():
                db.data["ghl_opportunities_v2"][opp_id] = opp
                contact_id = opp["contactId"]
                db.data["ghl_contacts_v2"][contact_id] = _contact(contact_id, "Nimbus")
                db.data["ghl_contacts_v2"][contact_id]["customFields"] = [{"id": SOLD_DATE_FIELD, "value": sold}]
            return db

        auto_created = _opp("auto-empower", "contact-auto", EMPOWER_PIPELINE_ID)
        auto_created.update(
            {
                "createdAt": created,
                "appointmentOccurredAt": moment,
                "dispositionDate": moment,
                "source": "NYHEP",
                "name": "E-AUTO",
                "status": "open",
                "customFields": [{"id": "Anddcx3E00WOhrNyD9mX", "field_value": "E-AUTO"}],
            }
        )
        mirrored = _opp("empower-today", "contact-today", EMPOWER_PIPELINE_ID)
        mirrored.update(
            {
                "createdAt": created,
                "appointmentOccurredAt": moment,
                "dispositionDate": moment,
                "source": "NYHEP",
            }
        )
        baseline = database({})
        with_auto = database({"auto-empower": auto_created, "empower-today": mirrored})
        year, month = moment.year, moment.month

        def created_count(db, scope):
            booking_rebooks._CACHE.clear()
            return compute_created(db, MetricContract(), year=year, month=month, pipeline_scope=scope)

        for scope in ("core", "all"):
            before = created_count(baseline, scope)
            after = created_count(with_auto, scope)
            self.assertEqual(after["result"], before["result"])
            self.assertEqual(after["result"], 1)
            self.assertEqual([row["opportunityId"] for row in after["sample_rows"]], ["buffalo-opp"])

        ran_before = compute_ran(baseline, RanContract(), year=year, month=month)
        ran_after = compute_ran(with_auto, RanContract(), year=year, month=month)
        self.assertEqual(ran_after["result"], ran_before["result"])
        self.assertEqual([row["opportunityId"] for row in ran_after["sample_rows"]], ["buffalo-opp"])

        demo_before = build_demo_rate(baseline, year, month, {})
        demo_after = build_demo_rate(with_auto, year, month, {})
        self.assertEqual(demo_after["ran_count"], demo_before["ran_count"])
        self.assertEqual(demo_after["sit_count"], demo_before["sit_count"])
        self.assertEqual([row["opportunityId"] for row in demo_after["rows"]], ["buffalo-opp"])

        sales_before = compute_sales(baseline, SalesMetricContract(), year=year, month=month, tz="America/New_York")
        sales_after = compute_sales(with_auto, SalesMetricContract(), year=year, month=month, tz="America/New_York")
        self.assertEqual(sales_after["result"], sales_before["result"])
        self.assertEqual(sales_after["result"], 1)
        self.assertNotIn("auto-empower", [row.get("opportunityId") for row in sales_after["sample_rows"]])
        self.assertNotIn("empower-today", [row.get("opportunityId") for row in sales_after["sample_rows"]])


if __name__ == "__main__":
    unittest.main()
