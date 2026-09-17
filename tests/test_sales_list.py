# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.append(path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sales = load_module("sales", METRICS / "sales.py")
essential = load_module("essential_sales", METRICS / "essential_sales.py")
sales_list = load_module("sales_list", METRICS / "sales_list.py")
notes_handler = load_module("sales_list_notes", METRICS / "sales_list_notes.py")
nav = load_module("dashboard_nav_sales_list", API / "dashboard_nav.py")
page = load_module("sales_list_page", API / "sales_list.py")
index = load_module("hs_index_sales_list", API / "index.py")


class FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDoc:
    def __init__(self, store, doc_id):
        self.id = doc_id
        self._store = store

    def get(self):
        return FakeSnap(self.id, self._store.get(self.id))

    def set(self, data, merge=True):
        current = dict(self._store.get(self.id) or {})
        incoming = dict(data)
        if merge:
            current.update(incoming)
            self._store[self.id] = current
        else:
            self._store[self.id] = incoming


class FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return FakeDoc(self._store, doc_id)


class FakeDb:
    def __init__(self, notes=None):
        self.notes = notes if notes is not None else {}

    def collection(self, name):
        if name != "sales_list_notes_v1":
            raise AssertionError(f"unexpected collection {name}")
        return FakeCollection(self.notes)

    def get_all(self, refs):
        return [ref.get() for ref in refs]


def sample_rows():
    return [
        {
            "contactId": "c-ess",
            "submissionDate": "2026-08-01",
            "client": "Essential Client",
            "salesperson": "Alex Rivera",
            "installer": "Essential",
            "notes": "GHL appointment note",
        },
        {
            "contactId": "c-mom",
            "submissionDate": "2026-08-02",
            "client": "Momentum Client",
            "salesperson": "Alex Rivera",
            "installer": "Momentum Solar",
            "notes": "",
        },
        {
            "contactId": "c-roc",
            "submissionDate": "2026-08-03",
            "client": "Roc Client",
            "salesperson": "Pat Lee",
            "installer": "3rd Roc",
            "notes": "",
        },
        {
            "contactId": "c-other",
            "submissionDate": "2026-08-04",
            "client": "Other Client",
            "salesperson": "Jordan",
            "installer": "Unknown Shop",
            "notes": "",
        },
    ]


def sample_essential_payload(rows=None, result=4):
    return {
        "year": 2026,
        "month": 8,
        "timezone": "America/New_York",
        "window_start_local": "2026-08-01T00:00:00-04:00",
        "window_end_local": "2026-09-01T00:00:00-04:00",
        "result": result,
        "count_method": "locked",
        "rows": rows if rows is not None else sample_rows(),
        "debug": {
            "opportunities_scanned": 80,
            "distinct_contact_ids": result,
            "join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
        },
        "contract": {
            "base_collection": "ghl_opportunities_v2",
            "fields": {
                "notes": "ghl_contacts_v2.customFields[Q2NUde7fCBQWp7GU76ca] Appointment Notes only",
                "installer": "ghl_contacts_v2.customFields[JbTL2wtTiUUZ5wPZswDn]",
            },
        },
    }


class InstallerFilterTests(unittest.TestCase):
    def test_normalizes_common_aliases(self):
        self.assertEqual(sales_list.normalize_installer_tab("Essential"), "essential")
        self.assertEqual(sales_list.normalize_installer_tab("  ESSENTIAL SOLAR "), "essential")
        self.assertEqual(sales_list.normalize_installer_tab("Momentum"), "momentum")
        self.assertEqual(sales_list.normalize_installer_tab("momentum-solar"), "momentum")
        self.assertEqual(sales_list.normalize_installer_tab("3rd Roc"), "3rd_roc")
        self.assertEqual(sales_list.normalize_installer_tab("3rdROC"), "3rd_roc")
        self.assertEqual(sales_list.normalize_installer_tab("Third Rock"), "3rd_roc")
        self.assertEqual(sales_list.normalize_installer_tab("3rd Rochester"), "3rd_roc")
        self.assertIsNone(sales_list.normalize_installer_tab(""))
        self.assertIsNone(sales_list.normalize_installer_tab("Unknown Shop"))

    def test_parse_installer_filter_defaults_to_all(self):
        self.assertEqual(sales_list.parse_installer_filter(""), "all")
        self.assertEqual(sales_list.parse_installer_filter("ALL"), "all")
        self.assertEqual(sales_list.parse_installer_filter("Essential"), "essential")
        self.assertEqual(sales_list.parse_installer_filter("not-a-tab"), "all")

    def test_apply_installer_filter_keeps_matching_aliases(self):
        apply = sales_list.apply_sales_list_filters(sample_rows(), installer="essential")
        self.assertEqual([r["contactId"] for r in apply], ["c-ess"])
        momentum = sales_list.apply_sales_list_filters(sample_rows(), installer="momentum")
        self.assertEqual([r["contactId"] for r in momentum], ["c-mom"])
        roc = sales_list.apply_sales_list_filters(sample_rows(), installer="3rd Roc")
        self.assertEqual([r["contactId"] for r in roc], ["c-roc"])
        everyone = sales_list.apply_sales_list_filters(sample_rows(), installer="all")
        self.assertEqual(len(everyone), 4)


class SalespersonFilterTests(unittest.TestCase):
    def test_casefold_match_and_all(self):
        alex = sales_list.apply_sales_list_filters(sample_rows(), salesperson="alex rivera")
        self.assertEqual([r["contactId"] for r in alex], ["c-ess", "c-mom"])
        all_rows = sales_list.apply_sales_list_filters(sample_rows(), salesperson="All")
        self.assertEqual(len(all_rows), 4)
        none = sales_list.apply_sales_list_filters(sample_rows(), salesperson="Nobody")
        self.assertEqual(none, [])

    def test_installer_and_salesperson_compose(self):
        rows = sales_list.apply_sales_list_filters(
            sample_rows(),
            installer="momentum",
            salesperson="Alex Rivera",
        )
        self.assertEqual([r["contactId"] for r in rows], ["c-mom"])

    def test_unique_salespeople_sorted_casefold(self):
        self.assertEqual(
            sales_list.unique_salespeople(sample_rows()),
            ["Alex Rivera", "Jordan", "Pat Lee"],
        )


class NotesMergeUpsertTests(unittest.TestCase):
    def test_merge_uses_stored_note_or_empty_string(self):
        merged = sales_list.merge_dashboard_notes(
            sample_rows(),
            {"c-ess": "Follow up Friday", "c-mom": ""},
        )
        by_id = {row["contactId"]: row["dashboardNote"] for row in merged}
        self.assertEqual(by_id["c-ess"], "Follow up Friday")
        self.assertEqual(by_id["c-mom"], "")
        self.assertEqual(by_id["c-roc"], "")
        self.assertEqual(by_id["c-other"], "")
        self.assertNotIn("EXAMPLE", "".join(by_id.values()))
        self.assertEqual(merged[0]["notes"], "GHL appointment note")

    def test_load_and_upsert_round_trip(self):
        db = FakeDb()
        saved = sales_list.upsert_sales_list_note(db, contact_id="c-ess", note="Site check")
        self.assertEqual(saved["contactId"], "c-ess")
        self.assertEqual(saved["note"], "Site check")
        self.assertTrue(saved["updated_at"].endswith("Z"))
        self.assertEqual(db.notes["c-ess"]["contactId"], "c-ess")
        self.assertEqual(db.notes["c-ess"]["note"], "Site check")

        loaded = sales_list.load_notes_by_contact_ids(db, ["c-ess", "missing", ""])
        self.assertEqual(loaded, {"c-ess": "Site check"})

        cleared = sales_list.upsert_sales_list_note(db, contact_id="c-ess", note="")
        self.assertEqual(cleared["note"], "")
        self.assertEqual(sales_list.load_notes_by_contact_ids(db, ["c-ess"])["c-ess"], "")

    def test_upsert_requires_contact_id(self):
        with self.assertRaises(ValueError):
            sales_list.upsert_sales_list_note(FakeDb(), contact_id="  ", note="x")

    def test_notes_collection_is_sales_list_notes_v1(self):
        self.assertEqual(sales_list.NOTES_COLLECTION, "sales_list_notes_v1")
        self.assertEqual(notes_handler.NOTES_COLLECTION, "sales_list_notes_v1")


class SalesGrainParityTests(unittest.TestCase):
    def _compute(self, **filters):
        captured = {}

        def fake_compute_essential_sales(db, contract, **kwargs):
            captured["db"] = db
            captured["contract"] = contract
            captured["kwargs"] = kwargs
            return sample_essential_payload()

        original = sales_list.compute_essential_sales
        sales_list.compute_essential_sales = fake_compute_essential_sales
        try:
            payload = sales_list.compute_sales_list(
                db=FakeDb(),
                contract=sales.SalesMetricContract(),
                year=2026,
                month=8,
                tz="America/New_York",
                timeframe="month",
                start=None,
                end=None,
                notes_by_contact={"c-ess": "Keep this"},
                **filters,
            )
        finally:
            sales_list.compute_essential_sales = original
        return payload, captured

    def test_all_no_salesperson_matches_essential_sales_grain(self):
        payload, captured = self._compute(installer="all", salesperson="")
        self.assertEqual(captured["kwargs"]["year"], 2026)
        self.assertEqual(captured["kwargs"]["month"], 8)
        self.assertEqual(captured["kwargs"]["tz"], "America/New_York")
        self.assertIsNone(captured["kwargs"]["start"])
        self.assertIsNone(captured["kwargs"]["end"])
        self.assertEqual(payload["timeframe"], "month")
        self.assertEqual(captured["contract"].stage_ids, sales.SalesMetricContract().stage_ids)
        self.assertEqual(payload["result"], 4)
        self.assertEqual(payload["debug"]["sales_result"], 4)
        self.assertEqual(payload["sales_count"], 4)
        self.assertEqual(payload["filtered_row_count"], 4)
        self.assertEqual(len(payload["rows"]), 4)
        self.assertEqual(
            payload["filters"],
            {"installer": "all", "salesperson": "", "timeframe": "month", "start": None, "end": None},
        )
        self.assertIsNone(payload["contract"]["installer_filter"])
        self.assertEqual(
            payload["contract"]["dashboard_notes"]["collection"],
            "sales_list_notes_v1",
        )
        self.assertFalse(payload["contract"]["dashboard_notes"]["ghl_writeback"])
        self.assertEqual(payload["rows"][0]["dashboardNote"], "Keep this")
        self.assertEqual(payload["rows"][1]["dashboardNote"], "")

        essential_payload = sample_essential_payload()
        self.assertEqual(payload["result"], essential_payload["result"])
        self.assertEqual(
            [row["contactId"] for row in payload["rows"]],
            [row["contactId"] for row in essential_payload["rows"]],
        )

    def test_filters_do_not_change_locked_debug_grain(self):
        payload, captured = self._compute(installer="essential", salesperson="Alex Rivera")
        self.assertEqual(captured["kwargs"]["year"], 2026)
        self.assertEqual(payload["debug"]["sales_result"], 4)
        self.assertEqual(payload["result"], 1)
        self.assertEqual(payload["sales_count"], 1)
        self.assertEqual(payload["filtered_row_count"], 1)
        self.assertEqual(payload["rows"][0]["contactId"], "c-ess")
        self.assertEqual(payload["filters"]["installer"], "essential")
        self.assertEqual(payload["filters"]["salesperson"], "Alex Rivera")
        self.assertIn("dashboardNote", [c["key"] for c in payload["columns"]])
        self.assertEqual(payload["columns"][12]["key"], "notes")
        self.assertEqual(payload["columns"][13]["key"], "dashboardNote")

    def test_start_end_pass_through_to_compute_sales(self):
        captured = {}

        def fake_compute_essential_sales(db, contract, **kwargs):
            captured.update(kwargs)
            return sample_essential_payload(rows=[], result=0)

        original = sales_list.compute_essential_sales
        sales_list.compute_essential_sales = fake_compute_essential_sales
        try:
            sales_list.compute_sales_list(
                db=FakeDb(),
                contract=sales.SalesMetricContract(),
                year=2026,
                month=8,
                tz="America/New_York",
                start="2026-08-01",
                end="2026-08-15",
                notes_by_contact={},
            )
        finally:
            sales_list.compute_essential_sales = original
        self.assertEqual(captured["start"], "2026-08-01")
        self.assertEqual(captured["end"], "2026-08-15")


class TimeframeWindowTests(unittest.TestCase):
    def test_default_timeframe_is_all_time(self):
        now = datetime(2026, 9, 17, 15, 0, tzinfo=ZoneInfo("America/New_York"))
        window = sales_list.resolve_sales_list_window(now=now)
        self.assertEqual(window["timeframe"], "all")
        self.assertEqual(window["start"], "2018-01-01")
        self.assertEqual(window["end"], "2026-09-18")

        captured = {}

        def fake_compute_essential_sales(db, contract, **kwargs):
            captured.update(kwargs)
            return sample_essential_payload()

        original = sales_list.compute_essential_sales
        sales_list.compute_essential_sales = fake_compute_essential_sales
        try:
            payload = sales_list.compute_sales_list(
                db=FakeDb(),
                contract=sales.SalesMetricContract(),
                tz="America/New_York",
                now=now,
                notes_by_contact={},
            )
        finally:
            sales_list.compute_essential_sales = original

        self.assertEqual(payload["timeframe"], "all")
        self.assertEqual(payload["filters"]["timeframe"], "all")
        self.assertEqual(payload["filters"]["installer"], "all")
        self.assertEqual(captured["start"], "2018-01-01")
        self.assertEqual(captured["end"], "2026-09-18")
        self.assertEqual(payload["debug"]["resolved_start"], "2018-01-01")
        self.assertEqual(payload["debug"]["resolved_end"], "2026-09-18")

    def test_month_still_uses_year_month_without_start_end(self):
        window = sales_list.resolve_sales_list_window(timeframe="month", year=2026, month=8)
        self.assertEqual(window["timeframe"], "month")
        self.assertEqual(window["year"], 2026)
        self.assertEqual(window["month"], 8)
        self.assertIsNone(window["start"])
        self.assertIsNone(window["end"])

    def test_quarter_window_maps_to_start_end(self):
        q1 = sales_list.resolve_sales_list_window(timeframe="quarter", year=2026, quarter=1)
        self.assertEqual(q1["start"], "2026-01-01")
        self.assertEqual(q1["end"], "2026-03-31")
        q2 = sales_list.quarter_date_bounds(2026, 2)
        self.assertEqual(q2, ("2026-04-01", "2026-06-30"))
        q3 = sales_list.quarter_date_bounds(2026, 3)
        self.assertEqual(q3, ("2026-07-01", "2026-09-30"))
        q4 = sales_list.quarter_date_bounds(2026, 4)
        self.assertEqual(q4, ("2026-10-01", "2026-12-31"))

        captured = {}

        def fake_compute_essential_sales(db, contract, **kwargs):
            captured.update(kwargs)
            captured["stages"] = contract.stage_ids
            return sample_essential_payload()

        original = sales_list.compute_essential_sales
        sales_list.compute_essential_sales = fake_compute_essential_sales
        try:
            payload = sales_list.compute_sales_list(
                db=FakeDb(),
                contract=sales.SalesMetricContract(),
                timeframe="quarter",
                year=2026,
                quarter=3,
                tz="America/New_York",
                notes_by_contact={},
            )
        finally:
            sales_list.compute_essential_sales = original

        self.assertEqual(payload["timeframe"], "quarter")
        self.assertEqual(payload["quarter"], 3)
        self.assertEqual(captured["start"], "2026-07-01")
        self.assertEqual(captured["end"], "2026-09-30")
        self.assertEqual(captured["stages"], sales.SalesMetricContract().stage_ids)

    def test_all_all_time_grain_matches_essential_sales_same_window(self):
        now = datetime(2026, 9, 17, tzinfo=ZoneInfo("America/New_York"))
        window = sales_list.resolve_sales_list_window(timeframe="all", now=now)
        captured = {}

        def fake_compute_essential_sales(db, contract, **kwargs):
            captured["kwargs"] = kwargs
            captured["stages"] = contract.stage_ids
            return sample_essential_payload(result=12)

        original = sales_list.compute_essential_sales
        sales_list.compute_essential_sales = fake_compute_essential_sales
        try:
            payload = sales_list.compute_sales_list(
                db=FakeDb(),
                contract=sales.SalesMetricContract(),
                timeframe="all",
                installer="all",
                salesperson="",
                tz="America/New_York",
                now=now,
                notes_by_contact={},
            )
        finally:
            sales_list.compute_essential_sales = original

        self.assertEqual(captured["kwargs"]["start"], window["start"])
        self.assertEqual(captured["kwargs"]["end"], window["end"])
        self.assertEqual(captured["stages"], sales.SalesMetricContract().stage_ids)
        self.assertEqual(payload["result"], 12)
        self.assertEqual(payload["debug"]["sales_result"], 12)
        self.assertEqual(payload["filters"]["installer"], "all")
        self.assertEqual(payload["timeframe"], "all")


class NavAndPageTests(unittest.TestCase):
    def test_nav_includes_sales_list_and_keeps_essential_sales(self):
        html = nav.render_dashboard_nav("sales_list")
        self.assertIn('href="/api/sales_list"', html)
        self.assertIn("Sales List", html)
        self.assertIn('href="/api/essential_sales"', html)
        self.assertIn("Essential Sales", html)
        self.assertIn("navmenu-item active", html)
        self.assertIn('summary class="navbtn active"', html)
        self.assertLess(html.find("Sales List"), html.find("Essential Sales"))

    def test_page_defaults_to_all_time_and_all_installers(self):
        html = page.render_html()
        self.assertIn('var defaultTimeframe = "all";', html)
        self.assertIn('var defaultInstaller = "all";', html)
        self.assertIn('data-timeframe="all"', html)
        self.assertIn('data-timeframe="month"', html)
        self.assertIn('data-timeframe="quarter"', html)
        self.assertIn("params.set('year'", html)
        self.assertIn("timeframe: timeframe", html)
        self.assertIn("if (timeframe === 'month')", html)
        self.assertNotIn("year: yearSel.value,\n    month: monthSel.value,\n    installer: installer", html)

    def test_page_wires_metrics_and_notes_write(self):
        html = page.render_html(
            timeframe="month",
            year=2026,
            month=8,
            installer="essential",
            salesperson="Alex Rivera",
        )
        self.assertIn("/api/metrics/sales_list?", html)
        self.assertIn("/api/metrics/sales_list_notes", html)
        self.assertIn('data-installer="3rd_roc"', html)
        self.assertIn("Dashboard notes", html)
        self.assertIn("var defaultInstaller = \"essential\";", html)
        self.assertIn('var defaultTimeframe = "month";', html)
        self.assertIn("Alex Rivera", html)
        self.assertIn("renderTable(document.getElementById('salesTable'), data.columns || [], data.rows || [])", html)


class DispatchTests(unittest.TestCase):
    def test_index_dispatches_sales_list_routes(self):
        self.assertEqual(index.dispatch_route("/api/sales_list"), "sales_list")
        self.assertEqual(index.dispatch_file("sales_list"), API / "sales_list.py")
        self.assertEqual(index.dispatch_route("/api/metrics/sales_list"), "metrics/sales_list")
        self.assertEqual(index.dispatch_file("metrics/sales_list"), METRICS / "sales_list.py")
        self.assertEqual(
            index.dispatch_route("/api/metrics/sales_list_notes"),
            "metrics/sales_list_notes",
        )
        self.assertEqual(
            index.dispatch_file("metrics/sales_list_notes"),
            METRICS / "sales_list_notes.py",
        )

    def test_index_delegates_post_to_notes_handler(self):
        called = {}
        notes_mod = index._load_api_module(METRICS / "sales_list_notes.py")
        orig = notes_mod.handler.do_POST

        def _capture(self):
            called["path"] = self.path
            called["command"] = self.command

        notes_mod.handler.do_POST = _capture
        try:
            req = MagicMock()
            req.path = "/api?hs=metrics/sales_list_notes"
            req.command = "POST"
            self.assertTrue(index.delegate_to_api_module(req, "metrics/sales_list_notes"))
            self.assertEqual(called["path"], "/api/metrics/sales_list_notes")
            self.assertEqual(called["command"], "POST")
        finally:
            notes_mod.handler.do_POST = orig
            index._MODULE_CACHE.pop(str(METRICS / "sales_list_notes.py"), None)


if __name__ == "__main__":
    unittest.main()
