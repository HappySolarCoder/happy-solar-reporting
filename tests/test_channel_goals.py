# -*- coding: utf-8 -*-
"""Company Overview channel goals: config, sweeper any-name, lead split."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
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
        # A set lead source wins over the setter/owner match.
        assert self_gen_reason("Doors", "Frazier", "Allen Frazier") is None
        assert self_gen_reason(None, "Hill", "Allen Frazier") is None
        assert self_gen_reason(None, "", "unassigned") is None


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
        out = self_gen_actuals(created, demo, {"k1": "lead_source"})
        assert (out["appointments"], out["ran"], out["demos"], out["sales"]) == (2, 1, 1, 1)
        assert out["from_fallback"] == {"appointments": 1, "ran": 1, "demos": 1, "sales": 0}


if __name__ == "__main__":
    unittest.main()
