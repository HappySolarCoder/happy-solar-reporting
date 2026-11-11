# -*- coding: utf-8 -*-

"""Consultant Overview Summary Sales use the locked Sold Date contract.

Evan, 2026-11-11 (ticket 86bd1yacq): Summary Sales go through
metrics.sales.compute_sales, the same contract as the Sales Dashboard owner
table. The August Maecker "pie 36" appointment-date lock is retired. Opps Ran,
Demos, and the pie stay on appointmentOccurredAt.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
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


class OverviewContractTests(unittest.TestCase):
    def test_summary_sales_use_compute_sales_not_pie_buckets(self):
        self.assertIn("from sales import SalesMetricContract, compute_sales", SC_OVERVIEW_SRC)
        self.assertIn("exclude_sweeper_rehash=True,", SC_OVERVIEW_SRC)
        self.assertIn('owner_rows[owner]["sales"] = int(count)', SC_OVERVIEW_SRC)
        self.assertIn('"sales": sum(int(r["sales"]) for r in rows),', SC_OVERVIEW_SRC)
        self.assertNotIn("if is_completed_sale_outcome_bucket(outcome_bucket):", SC_OVERVIEW_SRC)
        self.assertNotIn('"sales": completed_sale_count(stage_counts),', SC_OVERVIEW_SRC)
        self.assertIn(
            "Sales by Sold Date (same count as the Sales Dashboard); Ran/Demos by appointment date.",
            SC_OVERVIEW_SRC,
        )
        self.assertIn("Close rate mixes the two bases.", SC_OVERVIEW_SRC)
        self.assertNotIn("same grain as the pie", SC_OVERVIEW_SRC)

    def test_sold_date_loop_still_feeds_only_two_touch(self):
        sold_date_loop = SC_OVERVIEW_SRC.split("if not sold_date_in_window(contact, touch_start_local, touch_end_local):", 1)[1]
        sold_date_loop = sold_date_loop.split("for doc in db.collection", 1)[0]
        self.assertNotIn('owner_rows[owner]["sales"]', sold_date_loop)
        self.assertIn('touch_rows[owner]["sales_total"] += 1', sold_date_loop)

    def test_company_sold_date_sales_contract_is_untouched(self):
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_SRC)
        self.assertIn("Time filter is based on Contact Sold Date", SALES_SRC)
        self.assertIn('sold_date_custom_field_id: str = "P9oBjgbZjJdeE0OkBj9T"', SALES_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SC_OVERVIEW_SRC)
        self.assertIn(SOLD_DATE_FIELD_ID, SALES_CANCELLATIONS_SRC)
        self.assertNotIn("completed_sale_count", SALES_SRC)
        self.assertNotIn("is_completed_sale_outcome_bucket", SALES_SRC)
        self.assertIn("exclude_sweeper_rehash: bool = False", SALES_SRC)

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

        payload = {"owner_options": [], "totals": {"sales": 4}}
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


# ---------------------------------------------------------------- fixture

from datetime import datetime, timezone  # noqa: E402

RUEBEN = "u-rueben"
JEFF = "u-jeff"
QUINCY = "u-quincy"
LEAD_FIELD = "hd5QqHEOVSsPom5bJ32P"
SWEEPER_FIELD = "HWfjOp8MvE6soxBAL75f"
BUFFALO_SOLD = "7981f111-73f2-4593-9662-6b95d99bf51a"
BUFFALO_CANCELLED = "adf3106e-d371-47ff-ab9e-6f7f33ecf415"


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Ref:
    def __init__(self, store, doc_id):
        self._store, self.id = store, doc_id

    def get(self):
        return _Snap(self.id, self._store.get(self.id))


_OPS = {
    "in": lambda have, want: have in want,
    "==": lambda have, want: have == want,
    ">=": lambda have, want: have is not None and have >= want,
    "<": lambda have, want: have is not None and have < want,
}


class _Query:
    def __init__(self, store, filters=()):
        self._store, self._filters = store, tuple(filters)

    def where(self, field, op, value):
        return _Query(self._store, self._filters + ((field, op, value),))

    def limit(self, _n):
        return self

    def stream(self):
        for doc_id, data in list(self._store.items()):
            if all(_OPS[op](data.get(field), value) for field, op, value in self._filters):
                yield _Snap(doc_id, data)


class _Collection(_Query):
    def document(self, doc_id):
        return _Ref(self._store, doc_id)


class FakeDb:
    def __init__(self, collections):
        self._c = collections

    def collection(self, name):
        return _Collection(self._c.setdefault(name, {}))

    def get_all(self, refs):
        return [ref.get() for ref in refs]


def _contact(cid, sold, lead="Doors", sweeper=""):
    fields = [{"id": LEAD_FIELD, "value": lead}]
    if sold:
        fields.append({"id": SOLD_DATE_FIELD_ID, "value": f"{sold}T00:00:00.000Z"})
    if sweeper:
        fields.append({"id": SWEEPER_FIELD, "value": sweeper})
    return {"id": cid, "firstName": "T", "lastName": cid, "customFields": fields}


def _opp(oid, cid, owner, stage, appt):
    return {
        "id": oid,
        "contactId": cid,
        "assignedTo": owner,
        "pipelineId": "p-buffalo",
        "pipelineStageId": stage,
        "appointmentOccurredAt": datetime(*appt, 17, 0, tzinfo=timezone.utc),
        "dispositionValue": "Sit",
    }


def five_case_db():
    contacts = {
        # 1. Appointment in September, sold in October: October only.
        "c1": _contact("c1", "2026-10-29"),
        # 2. Appointment in October, sold in November: November only.
        "c2": _contact("c2", "2026-11-04"),
        # 3. Sale Cancelled with a blank Sold Date: excluded from both months.
        "c3": _contact("c3", ""),
        # 4. Diamond sweeper sale: credited to the owner (Jeff). Other sweepers stay out.
        "c4": _contact("c4", "2026-10-20", "Sweeper", "Diamond"),
        "c4b": _contact("c4b", "2026-10-21", "Rehash", "Smith"),
        # 5. Duplicate contact: two sold opps, counted once.
        "c5": _contact("c5", "2026-10-12"),
        # Controls: appointment and Sold Date both in October, and a dated Sale Cancelled.
        "c6": _contact("c6", "2026-10-12"),
        "c7": _contact("c7", "2026-10-14"),
    }
    opps = {
        "o1": _opp("o1", "c1", RUEBEN, BUFFALO_SOLD, (2026, 9, 25)),
        "o2": _opp("o2", "c2", RUEBEN, BUFFALO_SOLD, (2026, 10, 20)),
        "o3": _opp("o3", "c3", QUINCY, BUFFALO_CANCELLED, (2026, 10, 22)),
        "o4": _opp("o4", "c4", JEFF, BUFFALO_SOLD, (2026, 10, 5)),
        "o4b": _opp("o4b", "c4b", QUINCY, BUFFALO_SOLD, (2026, 10, 6)),
        "o5a": _opp("o5a", "c5", QUINCY, BUFFALO_SOLD, (2026, 10, 9)),
        "o5b": _opp("o5b", "c5", QUINCY, BUFFALO_SOLD, (2026, 10, 10)),
        "o6": _opp("o6", "c6", RUEBEN, BUFFALO_SOLD, (2026, 10, 9)),
        "o7": _opp("o7", "c7", QUINCY, BUFFALO_CANCELLED, (2026, 10, 14)),
    }
    names = {RUEBEN: "Rueben Hand", JEFF: "Jeff Salas", QUINCY: "Quincy Sermons"}
    return FakeDb(
        {
            "ghl_opportunities_v2": opps,
            "ghl_contacts_v2": contacts,
            "ghl_pipelines_v2": {
                "p-buffalo": {
                    "id": "p-buffalo",
                    "name": "Buffalo",
                    "stages": [
                        {"id": BUFFALO_SOLD, "name": "Sold"},
                        {"id": BUFFALO_CANCELLED, "name": "Sale Cancelled"},
                    ],
                }
            },
            "roster_people_v1": {
                uid: {"ghl_user_id": uid, "display_name": name, "role": "rep", "team": "buffalo"}
                for uid, name in names.items()
            },
            "ghl_users_v2": {},
            "ghl_opportunity_stage_history_v1": {},
        }
    )


def _payload(db, month, **kwargs):
    args = dict(
        year=2026, month=month, start=None, end=None,
        touch_year=2026, touch_month=month, touch_start=None, touch_end=None,
        owner_id="", team="", lead_source="",
    )
    args.update(kwargs)
    return sc_overview.build_payload(db, **args)


def _sales_by_name(payload):
    return {row["owner"]: row["sales"] for row in payload["rows"] if row["sales"]}


class SoldDateSalesFixtureTests(unittest.TestCase):
    def test_case1_sept_appointment_sold_in_october_counts_in_october_only(self):
        db = five_case_db()
        oct_payload, nov_payload = _payload(db, 10), _payload(db, 11)
        rueben_oct = next(r for r in oct_payload["rows"] if r["owner_id"] == RUEBEN)
        rueben_nov = next(r for r in nov_payload["rows"] if r["owner_id"] == RUEBEN)
        # c1 (Sep appointment, Oct 29 sale) + c6 control in October; c2 only in November.
        self.assertEqual(rueben_oct["sales"], 2)
        self.assertEqual(rueben_oct["ran"], 2)  # c1 ran in Sep: not an October ran row
        self.assertEqual(rueben_nov["sales"], 1)

    def test_case2_october_appointment_sold_in_november_counts_in_november_only(self):
        db = five_case_db()
        oct_by = sc_overview.sold_date_sales_by_owner(
            db, start_local=datetime(2026, 10, 1, tzinfo=sc_overview.TZ),
            end_local=datetime(2026, 11, 1, tzinfo=sc_overview.TZ),
            allowed_owner_ids={RUEBEN, JEFF, QUINCY}, lead_source="")
        nov_by = sc_overview.sold_date_sales_by_owner(
            db, start_local=datetime(2026, 11, 1, tzinfo=sc_overview.TZ),
            end_local=datetime(2026, 12, 1, tzinfo=sc_overview.TZ),
            allowed_owner_ids={RUEBEN, JEFF, QUINCY}, lead_source="")
        self.assertEqual(nov_by, {RUEBEN: 1})
        self.assertEqual(oct_by.get(RUEBEN), 2)

    def test_case3_sale_cancelled_with_blank_sold_date_is_excluded(self):
        payload = _payload(five_case_db(), 10)
        # Quincy: c5 (once) + c7 dated Sale Cancelled. o3 (blank Sold Date) adds nothing.
        self.assertEqual(_sales_by_name(payload)["Quincy Sermons"], 2)
        self.assertEqual(_sales_by_name(_payload(five_case_db(), 11)).get("Quincy Sermons"), None)

    def test_case4_diamond_sweeper_sale_is_credited_to_the_owner(self):
        by_name = _sales_by_name(_payload(five_case_db(), 10))
        self.assertEqual(by_name["Jeff Salas"], 1)
        # The non-Diamond Rehash sale (o4b, Quincy) stays out.
        self.assertEqual(by_name["Quincy Sermons"], 2)

    def test_case5_duplicate_contact_is_counted_once(self):
        by_name = _sales_by_name(_payload(five_case_db(), 10))
        self.assertEqual(by_name["Quincy Sermons"], 2)  # c5 once, not twice

    def test_totals_equal_owner_rows_and_pie_is_unchanged(self):
        payload = _payload(five_case_db(), 10)
        self.assertEqual(payload["sales_basis"], "sold_date")
        self.assertEqual(payload["totals"]["sales"], 5)  # Rueben 2 + Jeff 1 + Quincy 2
        self.assertEqual(payload["totals"]["sales"], sum(r["sales"] for r in payload["rows"]))
        # Pie is still the appointment-date outcome list (Oct appointments with a disposition).
        self.assertEqual(payload["totals"]["completed"], 8)
        self.assertEqual(payload["totals"]["opps_ran"], 8)

    def test_summary_sales_equal_sales_dashboard_owner_counts(self):
        import sales as sales_mod

        for month in (10, 11):
            db = five_case_db()
            dash = sales_mod.compute_sales(
                db, sales_mod.SalesMetricContract(), year=2026, month=month,
                tz="America/New_York", exclude_sweeper_rehash=True,
            )
            dash_by_owner = dash["breakdowns"]["sales_by_owner"]
            payload = _payload(db, month)
            self.assertEqual(_sales_by_name(payload), dict(dash_by_owner))
            self.assertEqual(payload["totals"]["sales"], dash["result"])
