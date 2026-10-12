"""Regression guard: the quick date preset buttons must stay on the Data Center filter bars.

They were dropped when the Operations Control redesign (#63) replaced the old
Company Overview period pills, and went missing again after later filter-bar rewrites.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "api" / "dashboard_nav.py").read_text(encoding="utf-8")
OPS = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
LABELS = ["Today", "Yesterday", "This week", "Last week", "MTD", "Last month", "Last 30", "YTD"]


class DatePresetsTest(unittest.TestCase):
    def test_shared_presets_defined(self):
        self.assertIn("window.hsOpsDatePresets", NAV)
        self.assertIn("window.hsOpsPresetRange", NAV)
        for label in LABELS:
            self.assertIn("'" + label + "'", NAV, label)

    def test_injected_filterbar_renders_presets(self):
        self.assertIn("window.hsOpsPresetButtons(f)", NAV)
        self.assertIn("[data-preset]", NAV)

    def test_ops_overview_filterbar_renders_presets(self):
        self.assertIn('class="date-presets"', OPS)
        self.assertIn("data-preset", OPS)
        self.assertIn("#filterHost [data-preset]", OPS)
        for label in LABELS:
            self.assertIn('"' + label + '"', OPS, label)


if __name__ == "__main__":
    unittest.main()
