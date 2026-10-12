# -*- coding: utf-8 -*-

"""Lead Gen FMA dashboard uses the production Bloom goal when a demo login shares the name."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FmaDashboardBloomGoalTests(unittest.TestCase):
    def test_production_goal_wins_over_a_same_name_demo_login(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "fma_dashboard_bloom_goals.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("fma dashboard bloom goals ok", completed.stdout)
