# -*- coding: utf-8 -*-
"""Empower+ pipeline id never counts in sales-funnel metrics.

The fixture pipeline is named Buffalo, not Empower+, so a name denylist or a
core-name allowlist would keep it. Only the pipeline id 5hPKCGzAskcC6LEZuc1H
drops it. A Buffalo control opportunity in the same window still counts.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
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


if __name__ == "__main__":
    unittest.main()
