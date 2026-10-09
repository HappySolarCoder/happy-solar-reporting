# -*- coding: utf-8 -*-
"""Submits come from the server-side lead store on the Phoenix day (Evan 2026-10-09)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
if str(METRICS) not in sys.path:
    sys.path.append(str(METRICS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


subs = _load("hs_estimate_submits", METRICS / "estimate_submits.py")
base = _load("hs_wf_for_submits", METRICS / "website_funnel.py")
patch_mod = _load("hs_fta_for_submits", METRICS / "funnel_test_address.py")
funnel = patch_mod.install(base)

MELISSA = [
    # Two creates (sub_c442..., then sub_1ce2...) merge into one doc per NY date.
    {
        "name": "Melissa Wannemacher",
        "email": "mmw15@msn.com",
        "address": "583 77th St, Niagara Falls, NY 14304, USA",
        "date": "2026-10-09",
        "received_at": "2026-10-09T06:52:35.120Z",
        "leadId": "sub_1ce247dd-2ff3-40c8-9c71-09fd63aa150e",
        "source": "new-site-estimate",
    },
]


class _Snap:
    def __init__(self, exists, doc_id, data=None):
        self.exists = exists
        self.id = doc_id
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, db, rows):
        self.db = db
        self.rows = rows
        self.filters = []

    def where(self, *args, **kwargs):
        f = kwargs.get("filter")
        if f is not None:
            self.filters.append((f.field_path, f.op_string, f.value))
        else:
            self.filters.append(tuple(args))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def get(self):
        self.db.range_queries.append(list(self.filters))
        if self.db.fail_store:
            raise RuntimeError("store down")
        out = []
        for row in self.rows:
            ok = True
            for field, op, value in self.filters:
                v = row.get(field)
                if not isinstance(v, str):
                    ok = False
                elif op == ">=" and not v >= value:
                    ok = False
                elif op == "<" and not v < value:
                    ok = False
            if ok:
                out.append(_Snap(True, "x", row))
        return out[: self.limit_n]

    def stream(self):  # pragma: no cover - must never be used
        raise AssertionError("no collection stream")


class _Col:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def document(self, doc_id):
        return ("ref", self.name, doc_id)

    def where(self, *args, **kwargs):
        assert self.name == "web_funnel_named_fills_v1"
        return _Query(self.db, self.db.fills).where(*args, **kwargs)


class _Db:
    def __init__(self, daily, fills, fail_store=False):
        self.daily = daily
        self.fills = fills
        self.fail_store = fail_store
        self.range_queries = []
        self.writes = []

    def collection(self, name):
        return _Col(self, name)

    def get_all(self, refs):
        out = []
        for _, _, doc_id in refs:
            data = self.daily.get(doc_id)
            out.append(_Snap(data is not None, doc_id, data))
        return out


def _daily(date, **kw):
    doc = {"date": date, "ga4": "ok", "sessions": 132, "starts": 2, "address_complete": 0,
           "bill_complete": 0, "estimate_submit": 0}
    doc.update(kw)
    return doc


class PhoenixWindowTests(unittest.TestCase):
    def test_oct8_phoenix_window(self):
        w = subs.phoenix_day_window("2026-10-08")
        self.assertEqual(w["query_start_utc"], "2026-10-08T07:00:00")
        self.assertEqual(w["query_end_utc"], "2026-10-09T07:00:00")
        self.assertTrue(w["start"].startswith("2026-10-08T00:00:00-07:00"))

    def test_default_is_yesterday_phoenix(self):
        # 8:00 AM ET Oct 9 = 5:00 AM Phoenix Oct 9 -> Oct 8.
        now = datetime(2026, 10, 9, 5, 0, tzinfo=ZoneInfo("America/Phoenix"))
        with patch.object(subs, "phoenix_now", return_value=now):
            self.assertEqual(subs.resolve_phoenix_date(None), "2026-10-08")
            self.assertEqual(subs.resolve_phoenix_date("yesterday"), "2026-10-08")
        self.assertEqual(subs.resolve_phoenix_date("2026-10-08"), "2026-10-08")
        with self.assertRaises(ValueError):
            subs.resolve_phoenix_date("10/08")


class StoreCountTests(unittest.TestCase):
    def test_melissa_counts_on_oct8_phoenix_not_oct9(self):
        db = _Db({}, MELISSA)
        r8 = subs.count_estimate_submits(db, "2026-10-08", patch_mod.fill_is_test)
        r9 = subs.count_estimate_submits(db, "2026-10-09", patch_mod.fill_is_test)
        self.assertTrue(r8["ok"])
        self.assertEqual(r8["count"], 1)
        self.assertEqual(r8["submits"][0]["lead_id"], "sub_1ce247dd-2ff3-40c8-9c71-09fd63aa150e")
        self.assertEqual(r9["count"], 0)

    def test_dedupes_same_person_and_updates(self):
        rows = MELISSA + [
            # Same person, second NY-date doc (crossed ET midnight) same Phoenix day.
            dict(MELISSA[0], date="2026-10-08", received_at="2026-10-09T03:10:00Z",
                 leadId="sub_c442a981-0b22-49d4-a696-57ee05c8e518", email="MMW15@msn.com "),
            {"email": "other@example.com", "received_at": "2026-10-08T15:00:00Z", "leadId": "sub_x"},
        ]
        r = subs.count_estimate_submits(_Db({}, rows), "2026-10-08", patch_mod.fill_is_test)
        self.assertEqual(r["count"], 2)
        self.assertEqual(r["dropped"]["duplicate"], 1)
        self.assertEqual(r["submits"][0]["lead_id"], "sub_x")
        self.assertEqual(r["submits"][1]["lead_id"], "sub_c442a981-0b22-49d4-a696-57ee05c8e518")

    def test_tests_excluded(self):
        rows = [
            {"email": "adchday@gmail.com", "received_at": "2026-10-08T15:00:00Z"},
            {"name": "Test Test", "email": "t@x.com", "received_at": "2026-10-08T15:00:00Z"},
            {"email": "a@x.com", "address": "24 Hawkstone Way", "received_at": "2026-10-08T16:00:00Z"},
        ]
        r = subs.count_estimate_submits(_Db({}, rows), "2026-10-08", patch_mod.fill_is_test)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["dropped"]["test"], 3)

    def test_boundary_strings(self):
        rows = [
            {"email": "a@x.com", "received_at": "2026-10-08T07:00:00.000Z"},  # 00:00 PHX in
            {"email": "b@x.com", "received_at": "2026-10-09T06:59:59.999Z"},  # 23:59 PHX in
            {"email": "c@x.com", "received_at": "2026-10-09T07:00:00.000Z"},  # next day out
            {"email": "d@x.com", "received_at": "2026-10-08T06:59:59Z"},      # prev day out
        ]
        r = subs.count_estimate_submits(_Db({}, rows), "2026-10-08", patch_mod.fill_is_test)
        self.assertEqual(r["count"], 2)

    def test_store_failure_is_none_not_invented(self):
        r = subs.count_estimate_submits(_Db({}, MELISSA, fail_store=True), "2026-10-08",
                                        patch_mod.fill_is_test)
        self.assertFalse(r["ok"])
        self.assertIsNone(r["count"])


class SnapshotTests(unittest.TestCase):
    def test_snapshot_oct8_reports_melissa(self):
        db = _Db({"2026-10-08": _daily("2026-10-08")}, MELISSA)
        payload = funnel.compute_day_snapshot(db, "2026-10-08")
        self.assertEqual(payload["estimate_submit"], 1)
        self.assertEqual(payload["lead"], 1)
        self.assertEqual(payload["ga4_estimate_submit"], 0)
        self.assertEqual(payload["lead_source"], "server_lead_store")
        self.assertEqual(payload["timezone"], "America/Phoenix")
        self.assertEqual(payload["sessions"], 132)
        self.assertAlmostEqual(payload["start_to_submit"], 0.5)
        self.assertEqual(payload["start→submit"], payload["start_to_submit"])
        self.assertFalse(payload["auto_rollup"])
        self.assertNotIn("Melissa", str(payload))
        self.assertNotIn("mmw15", str(payload))

    def test_default_date_is_phoenix_yesterday(self):
        db = _Db({"2026-10-08": _daily("2026-10-08")}, MELISSA)
        with patch.object(sys.modules["hs_estimate_submits"], "phoenix_now",
                          return_value=datetime(2026, 10, 9, 5, 0, tzinfo=ZoneInfo("America/Phoenix"))):
            payload = funnel.compute_day_snapshot(db, None)
        self.assertEqual(payload["date"], "2026-10-08")
        self.assertEqual(payload["estimate_submit"], 1)

    def test_store_failure_reports_unavailable(self):
        db = _Db({"2026-10-08": _daily("2026-10-08")}, MELISSA, fail_store=True)
        payload = funnel.compute_day_snapshot(db, "2026-10-08")
        self.assertIsNone(payload["estimate_submit"])
        self.assertEqual(payload["lead_source"], "unavailable")
        self.assertEqual(payload["ga4_estimate_submit"], 0)

    def test_no_autorollup_for_unfinished_ny_day(self):
        db = _Db({}, [])
        now = datetime(2026, 10, 9, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        with patch.object(base, "ny_now", return_value=now), \
                patch.object(base, "rollup_day") as rollup:
            payload = funnel.compute_day_snapshot(db, "2026-10-09")
        rollup.assert_not_called()
        self.assertFalse(payload["auto_rollup"])
        self.assertEqual(payload["auto_rollup_reason"], "day_not_over")


if __name__ == "__main__":
    unittest.main()
