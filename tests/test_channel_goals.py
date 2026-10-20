# -*- coding: utf-8 -*-
"""Company Overview channel goals: config, sweeper any-name, lead split."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import channel_goals as cg  # noqa: E402

NY = ZoneInfo("America/New_York")


class ChannelGoalsTests(unittest.TestCase):
    def test_goals_match_evan_oct_9(self):
        g = cg.CHANNEL_GOALS
        self.assertEqual(list(g), ["Doors", "Self Gen", "3PL", "Inbound", "Sweeper/Rehash"])
        self.assertEqual(g["Doors"], {"sales": 34, "opp2prelim_pct": 23, "appointments": 148, "leads": None, "demo_rate_pct": 45, "demos": 67})
        self.assertEqual(g["3PL"]["leads"], 108)
        self.assertEqual(g["Inbound"]["leads"], 30)
        self.assertEqual(g["Sweeper/Rehash"]["opp2prelim_pct"], 50)
        for name, row in g.items():
            if name not in cg.LEADS_CHANNELS:
                self.assertIsNone(row["leads"])

    def test_sweeper_any_name(self):
        created = {"sample_rows": [
            {"opportunityId": "a", "sweeperRehashLastName": "Diamond"},
            {"opportunityId": "a", "sweeperRehashLastName": "Diamond"},
            {"opportunityId": "b", "sweeperRehashLastName": "Smith"},
            {"opportunityId": "c", "sweeperRehashLastName": ""},
            {"opportunityId": "d", "sweeperRehashLastName": "N/A"},
        ]}
        self.assertEqual(cg.sweeper_created(created), 2)
        demo = {"rows": [
            {"opportunityId": "a", "sweeperRehashLastName": "Diamond", "disposition": "Sit"},
            {"opportunityId": "b", "sweeperRehashLastName": "Smith", "disposition": "No Sit"},
            {"opportunityId": "c", "sweeperRehashLastName": None, "disposition": "Sit"},
        ]}
        self.assertEqual(cg.sweeper_ran(demo), (2, 1))

    def test_lead_split(self):
        s = datetime(2026, 10, 1, tzinfo=NY)
        e = datetime(2026, 11, 1, tzinfo=NY)
        inside = datetime(2026, 10, 5, tzinfo=NY)

        def raw(oid, bucket="Lead Locker", refunded=False, when=inside):
            return SimpleNamespace(opportunity_id=oid, bucket=bucket, refunded=refunded, created_local=when)

        raws = [raw("1"), raw("2", refunded=True), raw("3", bucket=None), raw("4"), raw("5", when=datetime(2026, 9, 30, tzinfo=NY)), raw("6", bucket=None)]
        sources = {"3": "Inbound", "4": "Facebook Quick Form", "1": "3PL", "6": "Doors"}
        self.assertEqual(cg.split_leads(raws, sources, s, e), {"Inbound": 2, "3PL": 1})
        sources["7"] = "FB Quick Form"
        raws.append(raw("7", bucket=None))
        self.assertEqual(cg.split_leads(raws, sources, s, e), {"Inbound": 3, "3PL": 1})
        self.assertIsNone(cg.self_gen_reason("FB Quick Form", "", "Anyone"))
        self.assertEqual(cg.self_gen_reason("Facebook Quick Form", "Frazier", "Allen Frazier"), "override")

    def test_overview_has_channel_goals_section(self):
        import company_overview
        html = company_overview.render_html(2026, 10)
        self.assertIn('id="channelGoalsBody"', html)
        self.assertIn("/api/metrics/channel_goals", html)
        self.assertIn("Facebook Quick Form", html)


class SelfGenTests(unittest.TestCase):

    def test_self_gen_reason_lead_source_and_fallback(self):
        from channel_goals import self_gen_reason

        assert self_gen_reason("Self Gen", "", "Anyone") == "lead_source"
        assert self_gen_reason(" self gen ", "x", "Allen Frazier") == "lead_source"
        assert self_gen_reason(None, "frazier", "Allen Frazier") == "fallback"
        assert self_gen_reason("none", " Frazier ", "allen frazier") == "fallback"
        assert self_gen_reason("CRM UI", "FRAZIER", "Allen Frazier") == "fallback"
        # The setter/owner match overrides another lead source.
        assert self_gen_reason("Doors", "Frazier", "Allen Frazier") == "override"
        assert self_gen_reason("Doors", "Meehan", "Zachary Maecker") is None
        assert self_gen_reason(None, "Hill", "Allen Frazier") is None
        assert self_gen_reason(None, "", "unassigned") is None
        # Filled Sweeper/Rehash Last Name blocks lead source and the setter/owner override.
        assert self_gen_reason("Self Gen", "Diamond", "Jeff Salas", "Diamond") is None
        assert self_gen_reason("Doors", "Diamond", "Tyler Diamond", "Diamond") is None
        assert self_gen_reason("Self Gen", "Frazier", "Allen Frazier", "") == "lead_source"
        assert self_gen_reason("Self Gen", "Frazier", "Allen Frazier", "none") == "lead_source"


    def test_self_gen_actuals_split(self):
        from channel_goals import self_gen_actuals

        created = {"sample_rows": [
            {"opportunityId": "a", "leadGenSource": "Self Gen", "setterLastName": "x", "owner": "Y Z"},
            {"opportunityId": "b", "leadGenSource": "none", "setterLastName": "frazier", "owner": "Allen Frazier"},
            {"opportunityId": "c", "leadGenSource": "Doors", "setterLastName": "frazier", "owner": "Allen Frazier"},
        ]}
        demo = {"rows": [
            {"opportunityId": "b", "lead_source": "none", "setter": "Frazier", "closer": "Allen Frazier", "disposition": "Sit"},
            {"opportunityId": "b", "lead_source": "none", "setter": "Frazier", "closer": "Allen Frazier", "disposition": "Sit"},
        ]}
        out = self_gen_actuals(created, demo, {"k1": ("lead_source", "Self Gen"), "k2": ("override", "Doors")})
        assert (out["appointments"], out["ran"], out["demos"], out["sales"]) == (3, 1, 1, 2)
        assert out["moved_from"] == {"Doors": {"appointments": 1, "ran": 0, "demos": 0, "sales": 1}}
        assert out["from_fallback"] == {"appointments": 1, "ran": 1, "demos": 1, "sales": 0}

    def test_filled_sweeper_name_is_not_self_gen(self):
        from channel_goals import self_gen_actuals

        created = {"sample_rows": [
            {"opportunityId": "nix", "leadGenSource": "Self Gen", "setterLastName": "Sauriol", "owner": "Jeff Salas", "sweeperRehashLastName": "Diamond"},
            {"opportunityId": "plain", "leadGenSource": "Self Gen", "setterLastName": "x", "owner": "Y Z"},
        ]}
        demo = {"rows": [
            {"opportunityId": "nix", "lead_source": "Self Gen", "setter": "Diamond", "closer": "Jeff Salas", "disposition": "Sit", "sweeperRehashLastName": "Diamond", "pipeline": "Syracuse"},
            {"opportunityId": "plain", "lead_source": "Self Gen", "setter": "x", "closer": "Y Z", "disposition": "Sit"},
        ]}
        out = self_gen_actuals(created, demo, {})
        self.assertEqual(out["appointments"], 1)
        self.assertEqual(out["ran"], 1)
        self.assertEqual(out["demos"], 1)

    def test_week_fixture_drops_sweeper_name_and_month_keeps_doors_move(self):
        week_rows = [
            {"opportunityId": "w%s" % i, "leadGenSource": "Self Gen", "setterLastName": "x", "owner": "Y Z"}
            for i in range(12)
        ]
        week_rows.append({
            "opportunityId": "beatrice",
            "leadGenSource": "Self Gen",
            "setterLastName": "Sauriol",
            "owner": "Jeff Salas",
            "sweeperRehashLastName": "Diamond",
        })
        week = cg.self_gen_actuals({"sample_rows": week_rows}, {"rows": []}, {})
        self.assertEqual(week["appointments"], 12)
        self.assertNotIn("Doors", week["moved_from"])

        month_rows = week_rows + [{
            "opportunityId": "t1vz",
            "leadGenSource": "Doors",
            "setterLastName": "Frazier",
            "owner": "Allen Frazier",
        }]
        month = cg.self_gen_actuals({"sample_rows": month_rows}, {"rows": []}, {})
        self.assertIn("Doors", month["moved_from"])
        self.assertEqual(month["moved_from"]["Doors"]["appointments"], 1)
        self.assertNotIn("Doors", week["moved_from"])


def _invoke(path: str):
    captured = {}

    class _W:
        def __init__(self):
            self.buf = BytesIO()

        def write(self, data):
            self.buf.write(data)

    inst = cg.handler.__new__(cg.handler)
    inst.path = path
    inst.wfile = _W()
    inst.send_response = lambda code: captured.__setitem__("code", code)
    inst.send_header = lambda *_a, **_k: None
    inst.end_headers = lambda: None
    inst.do_GET()
    return captured["code"], inst.wfile.buf.getvalue()


class ChannelGoalsRangeTests(unittest.TestCase):
    def test_range_is_passed_through_and_echoed(self):
        from opportunities_created import date_range_window

        start, end = "2026-10-12", "2026-10-18"
        window = date_range_window(start, end, "America/New_York")
        with (
            mock.patch("opportunities_created.compute", return_value={"sample_rows": []}) as compute,
            mock.patch("demo_rate.build_payload", return_value={"rows": []}) as demo,
            mock.patch("sales.compute_sales", return_value={}) as sales_fn,
            mock.patch.object(cg, "compute_leads", return_value={"Inbound": 0, "3PL": 0}) as leads,
        ):
            out = cg.compute_channel_goals(object(), year=2026, month=10, start=start, end=end)

        self.assertEqual(compute.call_args.kwargs["start"], start)
        self.assertEqual(compute.call_args.kwargs["end"], end)
        self.assertEqual(compute.call_args.kwargs["pipeline_scope"], "all")
        self.assertEqual(compute.call_args.kwargs["year"], 2026)
        self.assertEqual(compute.call_args.kwargs["month"], 10)
        self.assertEqual(demo.call_args.kwargs["start"], start)
        self.assertEqual(demo.call_args.kwargs["end"], end)
        self.assertEqual(demo.call_args.args[1:], (2026, 10, {}))
        self.assertEqual(sales_fn.call_args.kwargs["start"], start)
        self.assertEqual(sales_fn.call_args.kwargs["end"], end)
        self.assertEqual(sales_fn.call_args.kwargs["tz"], "America/New_York")
        self.assertTrue(callable(sales_fn.call_args.kwargs["on_sale"]))
        self.assertEqual(leads.call_args.args[1:], (window[0], window[1]))
        self.assertEqual(out["start"], start)
        self.assertEqual(out["end"], end)
        self.assertEqual(out["window_start_local"], window[2])
        self.assertEqual(out["window_end_local"], window[3])
        self.assertEqual(out["goals"], cg.CHANNEL_GOALS)

    def test_month_path_is_unchanged_without_dates(self):
        from opportunities_created import month_window

        window = month_window(2026, 10, "America/New_York")
        with (
            mock.patch("opportunities_created.compute", return_value={"sample_rows": []}) as compute,
            mock.patch("demo_rate.build_payload", return_value={"rows": []}) as demo,
            mock.patch("sales.compute_sales", return_value={}) as sales_fn,
            mock.patch.object(cg, "compute_leads", return_value={"Inbound": 0, "3PL": 0}) as leads,
        ):
            out = cg.compute_channel_goals(object(), year=2026, month=10)

        self.assertNotIn("start", compute.call_args.kwargs)
        self.assertNotIn("end", compute.call_args.kwargs)
        self.assertEqual(compute.call_args.kwargs["pipeline_scope"], "all")
        self.assertNotIn("start", demo.call_args.kwargs)
        self.assertNotIn("end", demo.call_args.kwargs)
        self.assertEqual(demo.call_args.args[1:], (2026, 10, {}))
        self.assertNotIn("start", sales_fn.call_args.kwargs)
        self.assertNotIn("end", sales_fn.call_args.kwargs)
        self.assertEqual(sales_fn.call_args.kwargs["tz"], "America/New_York")
        self.assertTrue(callable(sales_fn.call_args.kwargs["on_sale"]))
        self.assertEqual(leads.call_args.args[1:], (window[0], window[1]))
        self.assertIsNone(out["start"])
        self.assertIsNone(out["end"])
        self.assertEqual(out["window_start_local"], window[2])
        self.assertEqual(out["window_end_local"], window[3])
        self.assertEqual(out["goals"], cg.CHANNEL_GOALS)

    def test_handler_rejects_partial_bad_and_long_ranges(self):
        self.assertEqual((date(2026, 4, 5) - date(2026, 1, 1)).days, 94)
        self.assertEqual((date(2026, 4, 4) - date(2026, 1, 1)).days, 93)
        rejected = [
            "/api/metrics/channel_goals?year=2026&month=10&start=2026-10-12",
            "/api/metrics/channel_goals?year=2026&month=10&end=2026-10-18",
            "/api/metrics/channel_goals?year=2026&month=10&start=2026-02-31&end=2026-10-18",
            "/api/metrics/channel_goals?year=2026&month=10&start=10/12/2026&end=2026-10-18",
            "/api/metrics/channel_goals?year=2026&month=10&start=2026-10-18&end=2026-10-12",
            "/api/metrics/channel_goals?year=2026&month=10&start=2026-01-01&end=2026-04-05",
        ]
        for path in rejected:
            with mock.patch("sales.get_db", return_value=object()) as get_db, mock.patch.object(cg, "compute_channel_goals", return_value={"ok": True}) as compute:
                code, body = _invoke(path)
            self.assertEqual(code, 400, path + " " + body.decode())
            self.assertIn(b"ERROR:", body)
            get_db.assert_not_called()
            compute.assert_not_called()

        with mock.patch("sales.get_db", return_value=object()), mock.patch.object(cg, "compute_channel_goals", return_value={"ok": True, "start": "2026-01-01", "end": "2026-04-04"}) as compute:
            code, body = _invoke("/api/metrics/channel_goals?year=2026&month=1&start=2026-01-01&end=2026-04-04")
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["start"], "2026-01-01")
        self.assertEqual(compute.call_args.kwargs["start"], "2026-01-01")
        self.assertEqual(compute.call_args.kwargs["end"], "2026-04-04")


if __name__ == "__main__":
    unittest.main()
