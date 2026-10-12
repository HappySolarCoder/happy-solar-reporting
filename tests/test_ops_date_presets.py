"""Regression guard: the quick date preset buttons must stay on the Data Center filter bars.

They were dropped when the Operations Control redesign (#63) replaced the old
Company Overview period pills, and went missing again after later filter-bar rewrites.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "api" / "dashboard_nav.py").read_text(encoding="utf-8")
OPS = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
LABELS = ["Today", "Yesterday", "This week", "Last week", "This month", "Last month", "Last 30", "YTD"]


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



GOALS = (ROOT / "api" / "goals_dashboard.py").read_text(encoding="utf-8")
THEME = (ROOT / "api" / "ops_theme.css").read_text(encoding="utf-8")


class EveryDashboardTest(unittest.TestCase):
    def test_own_dates_pages_still_get_presets(self):
        self.assertNotIn("(ownDates ? '' : window.hsOpsPresetButtons", NAV)
        self.assertIn("'+window.hsOpsPresetButtons(f)+'", NAV)

    def test_goals_native_bar_has_presets(self):
        self.assertIn("window.hsOpsPresetButtons(f)", GOALS)
        self.assertIn("[data-preset]", GOALS)

    def test_mtd_is_labeled_this_month(self):
        self.assertNotIn("label: 'MTD'", NAV)
        self.assertNotIn('label: "MTD"', OPS)

    def test_calendar_icon_high_contrast(self):
        self.assertIn("::-webkit-calendar-picker-indicator", NAV)
        self.assertIn("::-webkit-calendar-picker-indicator", THEME)


if __name__ == "__main__":
    unittest.main()


class ServerRenderedPresetsTest(unittest.TestCase):
    def test_paid_social_has_presets(self):
        import sys
        sys.path.insert(0, str(ROOT / "api"))
        import paid_social_funnel
        html = paid_social_funnel.render_html()
        self.assertGreaterEqual(html.count('data-preset="'), 8)
        self.assertIn(">This month</a>", html)

    def test_server_ranges_match(self):
        import sys
        from datetime import date
        sys.path.insert(0, str(ROOT / "api"))
        from dashboard_nav import date_preset_range
        t = date(2026, 10, 12)
        self.assertEqual(date_preset_range("lastweek", t), ("2026-10-05", "2026-10-11"))
        self.assertEqual(date_preset_range("lastmonth", t), ("2026-09-01", "2026-09-30"))
        self.assertEqual(date_preset_range("last30", t), ("2026-09-13", "2026-10-12"))
