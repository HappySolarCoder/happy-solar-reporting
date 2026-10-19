# -*- coding: utf-8 -*-

"""Company Overview Self gen card follows the selected dates, not the calendar month."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompanyOverviewSelfGenRangeTests(unittest.TestCase):
    def test_cards_follow_the_selected_range(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "company_overview_selfgen_range.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("company overview self gen range ok", completed.stdout)


if __name__ == "__main__":
    unittest.main()
