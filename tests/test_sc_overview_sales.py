# -*- coding: utf-8 -*-

"""Consultant Overview Summary Sales use Contact Sold Date.

Pie Sold and Sale Cancelled stay on appointment date.
Close rate mixes sold-date sales with appointment-date demos.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

SC_OVERVIEW_SRC = (API / "sc_overview.py").read_text(encoding="utf-8")
SALES_SRC = (METRICS / "sales.py").read_text(encoding="utf-8")
SALES_CANCELLATIONS_SRC = (METRICS / "sales_cancellations.py").read_text(encoding="utf-8")

# Warehouse lock — Zachary Maecker / assignedTo nFf2FIr40kvWRCVaMej2
# Window 2026-06-01 to 2026-08-26 America/New_York. Do not invent another owner.
MAECKER_OWNER_ID = "nFf2FIr40kvWRCVaMej2"
MAECKER_SOLD = 28
MAECKER_SALE_CANCELLED = 8
MAECKER_SALES = 36
MAECKER_DEMOS = 74
MAECKER_CLOSE_RATE = 48.6
MAECKER_COMPLETED = 120
# Pie-bucket math only. Summary Sales use the Sold Date grain instead.
MAECKER_AUGUST_SOLD_DATE = 6
MAECKER_FULL_WINDOW_SOLD_DATE_CONTACTS = 37
SOLD_DATE_FIELD_ID = "P9oBjgbZjJdeE0OkBj9T"


def _install_google_stubs() -> None:
    google = sys.modules.setdefault("google", MagicMock())
    cloud = sys.modules.setdefault("google.cloud", MagicMock())
    oauth2 = sys.modules.setdefault("google.oauth2", MagicMock())
    sys.modules.setdefault("google.cloud.firestore", MagicMock())
    sys.modules.setdefault("google.oauth2.service_account", MagicMock())
    google.cloud = cloud
    google.oauth2 = oauth2


def load_sc_overview():
    _install_google_stubs()
    spec = importlib.util.spec_from_file_location("sc_overview_sales_lock", API / "sc_overview.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/sc_overview.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sc_overview_sales_lock"] = module
    spec.loader.exec_module(module)
    return module


sc_overview = load_sc_overview()


class CompletedSaleBucketTests(unittest.TestCase):
    def test_pie_keeps_sold_and_sale_cancelled_labels(self):
        self.assertEqual(sc_overview.normalize_completed_outcome_bucket("Buffalo", "Sold"), "Sold")
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Virtual", "Sale Cancelled"),
            "Sale Cancelled",
        )
        self.assertEqual(
            sc_overview.normalize_completed_outcome_bucket("Rehash", "Sold"),
            "Sold",
        )

    def test_only_sold_and_sale_cancelled_count(self):
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("Sold"))
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("Sale Cancelled"))
        self.assertTrue(sc_overview.is_completed_sale_outcome_bucket("sale canceled"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Auto Text Sent"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("No Show/Pre-cancelled"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Demo-Negotiating"))
        self.assertFalse(sc_overview.is_completed_sale_outcome_bucket("Rescheduled"))


class MaeckerWindowLockTests(unittest.TestCase):
    def test_pie_sale_buckets_are_sold_plus_sale_cancelled(self):
        stage_counts = {
            "Sold": MAECKER_SOLD,
            "Sale Cancelled": MAECKER_SALE_CANCELLED,
            "Auto Text Sent": 27,
            "No Show/Pre-cancelled": 20,
            "DQ'ed": 14,
            "Rescheduled": 6,
            "Call 1": 5,
            "Not Interested": 3,
            "Demo-Negotiating": 2,
            "Demo-Not Interested": 2,
            "Do not Contact": 2,
            "Reschedule Needed": 2,
            "One Legger": 1,
        }
        self.assertEqual(sum(stage_counts.values()), MAECKER_COMPLETED)
        self.assertEqual(sc_overview.completed_sale_count(stage_counts), MAECKER_SALES)
        self.assertEqual(
            sc_overview.close_rate_on_demos(MAECKER_SALES, MAECKER_DEMOS),
            MAECKER_CLOSE_RATE,
        )
        self.assertNotEqual(
            sc_overview.completed_sale_count(stage_counts),
            MAECKER_AUGUST_SOLD_DATE,
        )
        self.assertNotEqual(
            sc_overview.completed_sale_count(stage_counts),
            MAECKER_FULL_WINDOW_SOLD_DATE_CONTACTS,
        )
        self.assertNotEqual(
            sc_overview.close_rate_on_demos(MAECKER_AUGUST_SOLD_DATE, MAECKER_DEMOS),
            MAECKER_CLOSE_RATE,
        )
        self.assertEqual(
            sc_overview.close_rate_on_demos(MAECKER_FULL_WINDOW_SOLD_DATE_CONTACTS, MAECKER_DEMOS),
            50.0,
        )
        self.assertNotEqual(50.0, MAECKER_CLOSE_RATE)
        self.assertEqual(sc_overview.close_rate_on_demos(28, MAECKER_DEMOS), 37.8)
        self.assertIsNone(sc_overview.close_rate_on_demos(MAECKER_SALES, 0))


class OverviewContractTests(unittest.TestCase):
    def test_summary_sales_use_one_sold_date_compute_sales_pass(self):
        self.assertEqual(SC_OVERVIEW_SRC.count("compute_sales("), 1)
        self.assertIn("exclude_sweeper_rehash=True", SC_OVERVIEW_SRC)
        self.assertNotIn('owner_rows[owner]["sales"] += 1', SC_OVERVIEW_SRC)
        self.assertNotIn('"sales": completed_sale_count(stage_counts),', SC_OVERVIEW_SRC)
        self.assertIn('sum(int(r["sales"]) for r in rows)', SC_OVERVIEW_SRC)
        self.assertIn("totals[\"close_rate_on_demos\"] = close_rate_on_demos(totals[\"sales\"], totals[\"demos\"])", SC_OVERVIEW_SRC)
        self.assertIn("Pie Sold and Sale Cancelled stay on appointment date.", SC_OVERVIEW_SRC)
        self.assertIn("Close rate mixes sold-date sales with appointment-date demos.", SC_OVERVIEW_SRC)
        self.assertIn("Two-Touch stays on Sold Date.", SC_OVERVIEW_SRC)
        self.assertNotIn(
            "Sales are completed-appointment Sold + Sale Cancelled (same grain as the pie).",
            SC_OVERVIEW_SRC,
        )
        self.assertIn(MAECKER_OWNER_ID, "nFf2FIr40kvWRCVaMej2")

    def test_sold_date_loop_no_longer_increments_summary_sales(self):
        sold_date_loop = SC_OVERVIEW_SRC.split("if not sold_date_in_window(contact, touch_start_local, touch_end_local):", 1)[1]
        sold_date_loop = sold_date_loop.split("for doc in db.collection", 1)[0]
        self.assertNotIn('owner_rows[owner]["sales"] += 1', sold_date_loop)
        self.assertIn('touch_rows[owner]["sales_total"] += 1', sold_date_loop)

    def test_company_sold_date_sales_contract_is_untouched(self):
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_SRC)
        self.assertIn("Time filter is based on Contact Sold Date", SALES_SRC)
        self.assertIn('sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"', SALES_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SC_OVERVIEW_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_CANCELLATIONS_SRC)
        self.assertNotIn("completed_sale_count", SALES_SRC)
        self.assertNotIn("is_completed_sale_outcome_bucket", SALES_SRC)

    def test_page_is_open_and_renders_shared_sales_nav(self):
        self.assertNotIn("def _check_auth", SC_OVERVIEW_SRC)
        self.assertNotIn("def _unauthorized", SC_OVERVIEW_SRC)
        self.assertNotIn("SETTINGS_PASSWORD", SC_OVERVIEW_SRC)
        self.assertIn('render_dashboard_nav("sc_overview")', SC_OVERVIEW_SRC)
        settings = (API / "settings.py").read_text(encoding="utf-8")
        self.assertIn("def _check_auth", settings)
        self.assertIn("SETTINGS_PASSWORD", settings)

    def test_get_returns_html_and_json_without_basic_auth(self):
        class _Body:
            def __init__(self):
                self.buf = bytearray()

            def write(self, data):
                self.buf.extend(data)

        class _Request:
            def __init__(self, path):
                self.path = path
                self.headers = {}
                self.wfile = _Body()
                self.status = None
                self.sent = []

            def send_response(self, code):
                self.status = code

            def send_header(self, key, value):
                self.sent.append((key, value))

            def end_headers(self):
                return None

        payload = {"owner_options": [], "totals": {"sales": 36}}
        with patch.object(sc_overview, "get_db", return_value=object()), patch.object(
            sc_overview, "build_payload", return_value=payload
        ):
            html_req = _Request("/api/sc_overview")
            sc_overview.handler.do_GET(html_req)
            self.assertEqual(html_req.status, 200)
            self.assertNotIn("WWW-Authenticate", [key for key, _value in html_req.sent])
            self.assertIn(
                ("Content-Type", "text/html; charset=utf-8"),
                html_req.sent,
            )
            html = html_req.wfile.buf.decode("utf-8")
            self.assertIn('class="navlink active" href="/api/sc_overview"', html)
            self.assertIn("Solar Consultant Overview", html)
            self.assertIn(
                'class="oc-embed-link active" href="/api/sc_overview" aria-current="page"',
                html,
            )
            self.assertIn('id="hsDashboardLoader"', html)

            json_req = _Request("/api/sc_overview?format=json")
            sc_overview.handler.do_GET(json_req)
            self.assertEqual(json_req.status, 200)
            self.assertIn(("Content-Type", "application/json"), json_req.sent)
            self.assertEqual(json.loads(json_req.wfile.buf.decode("utf-8")), payload)

    def test_owner_is_assigned_to_and_occurred_at_is_not_recomputed(self):
        self.assertIn('owner = compact_str(opp.get("assignedTo"))', SC_OVERVIEW_SRC)
        self.assertIn('.where("appointmentOccurredAt", ">=", start_utc)', SC_OVERVIEW_SRC)
        self.assertIn('.where("appointmentOccurredAt", "<", end_utc)', SC_OVERVIEW_SRC)
        self.assertIn('if disposition == "Sit":', SC_OVERVIEW_SRC)
        self.assertNotIn("sit_timestamp", SC_OVERVIEW_SRC)
        self.assertNotIn("frozen_sit", SC_OVERVIEW_SRC)
        self.assertNotIn("dispositionDate", SC_OVERVIEW_SRC)
        self.assertNotIn("appointmentOccurredAt =", SC_OVERVIEW_SRC)


# October 2026. Appointment grain and Sold Date grain disagree on purpose.
RUEBEN_OWNER_ID = "ruebenHandOwner0001"
OTHER_OWNER_ID = "otherRepOwner000001"
BUFFALO_SOLD_STAGE = "7981f111-73f2-4593-9662-6b95d99bf51a"
BUFFALO_CANCELLED_STAGE = "adf3106e-d371-47ff-ab9e-6f7f33ecf415"
DEMO_STAGE = "demo-negotiating-stage"
PIPE_ID = "pipe-buffalo"
IN_WINDOW = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
OUT_OF_WINDOW = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)


class _Snap:
    def __init__(self, data, sid):
        self._data = data
        self.id = sid
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Ref:
    def __init__(self, db, coll, doc_id):
        self.db = db
        self.coll = coll
        self.id = doc_id
        self.doc_id = doc_id


class _Query:
    def __init__(self, db, coll, filters):
        self.db = db
        self.coll = coll
        self.filters = list(filters)

    def where(self, field, op, value):
        return _Query(self.db, self.coll, self.filters + [(field, op, value)])

    def limit(self, count):
        return _Query(self.db, self.coll, self.filters + [("__limit__", "==", count)])

    def stream(self):
        matched = []
        for doc_id, data in self.db.store.get(self.coll, {}).items():
            if self._matches(data):
                matched.append(_Snap(data, doc_id))
        limit = next((value for field, _op, value in self.filters if field == "__limit__"), None)
        if limit is not None:
            matched = matched[: int(limit)]
        return matched

    def _matches(self, data):
        for field, op, value in self.filters:
            if field == "__limit__":
                continue
            actual = data.get(field)
            if op == "==" and actual != value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == ">=" and (actual is None or actual < value):
                return False
            if op == "<" and (actual is None or actual >= value):
                return False
        return True


class _Collection:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def stream(self):
        return [_Snap(data, doc_id) for doc_id, data in self.db.store.get(self.name, {}).items()]

    def where(self, field, op, value):
        return _Query(self.db, self.name, [(field, op, value)])

    def document(self, doc_id):
        return _Ref(self.db, self.name, doc_id)


class _FakeDb:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return _Collection(self, name)

    def get_all(self, refs):
        snaps = []
        for ref in refs:
            data = self.store.get(ref.coll, {}).get(ref.doc_id)
            snaps.append(_Snap(data, ref.doc_id))
        return snaps


def _contact(contact_id: str, sold_date: str | None) -> dict:
    fields = []
    if sold_date:
        fields.append({"id": SOLD_DATE_FIELD_ID, "value": sold_date})
    return {"id": contact_id, "firstName": "Pat", "lastName": contact_id, "customFields": fields}


def _opp(opp_id: str, contact_id: str, owner_id: str, stage_id: str, when: datetime) -> dict:
    return {
        "id": opp_id,
        "contactId": contact_id,
        "assignedTo": owner_id,
        "pipelineId": PIPE_ID,
        "pipelineStageId": stage_id,
        "appointmentOccurredAt": when,
        "dispositionValue": "Sit",
    }


def _roster(owner_id: str, name: str) -> dict:
    return {
        "role": "rep",
        "ghl_user_id": owner_id,
        "display_name": name,
        "team": "buffalo",
        "person_key": owner_id,
    }


def october_sold_date_db() -> _FakeDb:
    """Rueben's October sold-date sales are not his October appointment sales.

    Appointment window (pie, demos, ran):
    - Rueben sat one Demo-Negotiating appointment. It is not a pie sale.
    - Other Rep sat one Sold appointment whose contact sold in September.

    Sold Date window (Sales Dashboard / compute_sales):
    - Rueben has two contacts sold in October. One of those contacts has a
      second sold opportunity and must still count once.
    - Other Rep's September sold date is outside October.
    """
    store = {
        "roster_people_v1": {
            RUEBEN_OWNER_ID: _roster(RUEBEN_OWNER_ID, "Rueben Hand"),
            OTHER_OWNER_ID: _roster(OTHER_OWNER_ID, "Other Rep"),
        },
        "ghl_users_v2": {},
        "ghl_opportunity_stage_history_v1": {},
        "ghl_pipelines_v2": {
            PIPE_ID: {
                "id": PIPE_ID,
                "name": "Buffalo",
                "stages": [
                    {"id": BUFFALO_SOLD_STAGE, "name": "Sold"},
                    {"id": BUFFALO_CANCELLED_STAGE, "name": "Sale Cancelled"},
                    {"id": DEMO_STAGE, "name": "Demo-Negotiating"},
                ],
            }
        },
        "ghl_contacts_v2": {
            "c-demo": _contact("c-demo", None),
            "c-sold-a": _contact("c-sold-a", "2026-10-05T00:00:00.000Z"),
            "c-sold-b": _contact("c-sold-b", "2026-10-12T00:00:00.000Z"),
            "c-other": _contact("c-other", "2026-09-02T00:00:00.000Z"),
        },
        "ghl_opportunities_v2": {
            "opp-demo": _opp("opp-demo", "c-demo", RUEBEN_OWNER_ID, DEMO_STAGE, IN_WINDOW),
            "opp-sold-a": _opp("opp-sold-a", "c-sold-a", RUEBEN_OWNER_ID, BUFFALO_SOLD_STAGE, OUT_OF_WINDOW),
            "opp-sold-b": _opp("opp-sold-b", "c-sold-b", RUEBEN_OWNER_ID, BUFFALO_CANCELLED_STAGE, OUT_OF_WINDOW),
            "opp-sold-b-dup": _opp(
                "opp-sold-b-dup", "c-sold-b", RUEBEN_OWNER_ID, BUFFALO_CANCELLED_STAGE, OUT_OF_WINDOW
            ),
            "opp-other": _opp("opp-other", "c-other", OTHER_OWNER_ID, BUFFALO_SOLD_STAGE, IN_WINDOW),
        },
    }
    return _FakeDb(store)


def _overview_for(db):
    return sc_overview.build_payload(
        db,
        year=2026,
        month=10,
        start=None,
        end=None,
        touch_year=2026,
        touch_month=10,
        touch_start=None,
        touch_end=None,
        owner_id="",
        team="",
        lead_source="",
    )


def _row_by_owner(payload):
    return {row["owner"]: row for row in payload["rows"]}


class SoldDateSalesFixtureTests(unittest.TestCase):
    def test_summary_sales_follow_sold_date_while_pie_stays_on_appointment_date(self):
        payload = _overview_for(october_sold_date_db())
        rows = _row_by_owner(payload)
        pie = {slice_["label"]: slice_["value"] for slice_ in payload["pie"]}

        self.assertEqual(rows["Rueben Hand"]["sales"], 2)
        self.assertEqual(rows["Rueben Hand"]["demos"], 1)
        self.assertEqual(rows["Rueben Hand"]["close_rate_on_demos"], 200.0)
        self.assertEqual(rows["Other Rep"]["sales"], 0)
        self.assertEqual(rows["Other Rep"]["demos"], 1)
        self.assertEqual(rows["Other Rep"]["close_rate_on_demos"], 0.0)
        self.assertEqual(payload["totals"]["sales"], 2)
        self.assertEqual(payload["totals"]["demos"], 2)
        self.assertEqual(payload["totals"]["close_rate_on_demos"], 100.0)
        self.assertEqual(pie.get("Sold"), 1)
        self.assertNotIn("Sale Cancelled", pie)
        self.assertEqual(payload["totals"]["completed"], sum(pie.values()))

    def test_one_compute_sales_pass_per_payload(self):
        self.assertEqual(SC_OVERVIEW_SRC.count("compute_sales("), 1)
        self.assertIn("exclude_sweeper_rehash=True", SC_OVERVIEW_SRC)
        self.assertIn("Pie Sold and Sale Cancelled stay on appointment date.", SC_OVERVIEW_SRC)
        self.assertIn("Close rate mixes sold-date sales with appointment-date demos.", SC_OVERVIEW_SRC)
        db = october_sold_date_db()
        with patch.object(sc_overview, "compute_sales", wraps=sc_overview.compute_sales) as spy:
            payload = _overview_for(db)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(_row_by_owner(payload)["Rueben Hand"]["sales"], 2)
        sales_src = (METRICS / "sales.py").read_text(encoding="utf-8")
        dashboard_src = (API / "sales_dashboard.py").read_text(encoding="utf-8")
        self.assertNotIn("sc_overview", sales_src)
        self.assertIn("exclude_sweeper_rehash=1", dashboard_src)
