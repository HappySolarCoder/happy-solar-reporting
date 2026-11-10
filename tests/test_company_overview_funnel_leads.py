# -*- coding: utf-8 -*-

"""Company Overview funnel Leads reuse channel_goals.compute_leads."""

from __future__ import annotations

import inspect
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import channel_goals as cg  # noqa: E402
import ops_overview  # noqa: E402


class FunnelLeadsReuseTests(unittest.TestCase):
    def test_only_defined_lead_channels_get_a_funnel_tier(self):
        self.assertEqual(ops_overview.LEAD_FUNNEL_CHANNELS, set(cg.LEADS_CHANNELS))
        self.assertEqual(set(cg.LEADS_CHANNELS), {"Inbound", "3PL"})
        for name, goal in cg.CHANNEL_GOALS.items():
            if name not in cg.LEADS_CHANNELS:
                self.assertIsNone(goal["leads"], name)

    def test_funnel_reads_the_channel_goals_lead_actual(self):
        script = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
        start = script.index("function leadCount")
        body = script[start : script.index("function withLeads")]
        self.assertIn("channelGoals.leads", body)
        self.assertIn('name !== "Inbound" && name !== "3PL"', body)
        self.assertIn("channelGoalsMatch()", body)
        self.assertNotIn("Facebook", body)
        self.assertNotIn("fetch(", body)
        self.assertNotIn("GOAL_INBOUND_KEYS", body)
        source = inspect.getsource(cg.compute_leads)
        self.assertIn("split_leads", source)
        split = inspect.getsource(cg.split_leads)
        self.assertIn("is_inbound_lead_source", split)
        self.assertIn("not raw.refunded", split)

    def test_five_tier_funnels_share_the_four_tier_height(self):
        css = (ROOT / "api" / "ops_theme.css").read_text(encoding="utf-8")
        self.assertIn(".oc-page .source-funnel .compact-funnel{height:357px}", css)
        self.assertIn(".oc-page .source-funnel .compact-funnel>.compact-stage{flex:1 1 0;height:auto;min-height:0;gap:2px}", css)
        self.assertIn("font:700 19px Manrope,sans-serif", css)
        self.assertNotIn("font:700 23px Manrope,sans-serif", css)

    def test_selected_range_drives_the_displayed_count(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "company_overview_funnel_leads.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("company overview funnel leads ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()
