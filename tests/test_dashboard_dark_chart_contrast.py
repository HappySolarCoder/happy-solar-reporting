# -*- coding: utf-8 -*-
"""Sales by Pipeline and FMA leftover bars use the navy chart palette at AA contrast."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SALES = (ROOT / "api" / "sales_dashboard.py").read_text(encoding="utf-8")
FMA = (ROOT / "api" / "fma_dashboard.py").read_text(encoding="utf-8")

BAR_COLORS = ("#26d9eb", "#2ea8fa", "#11c99b", "#ffbe45", "#b59bff")
CHART_WELL = "#0b2438"


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class SalesPipelineDarkChartTests(unittest.TestCase):
    def test_pipeline_bars_use_dark_series_not_bright_css_vars(self):
        palette = re.search(r"const palette = \[([^\]]+)\]", SALES)
        self.assertIsNotNone(palette)
        body = palette.group(1)
        for color in BAR_COLORS:
            self.assertIn(color, body)
        self.assertNotIn("var(--green)", body)
        self.assertNotIn("var(--blue)", body)
        self.assertNotIn("#00C853", body)
        self.assertNotIn("#2196F3", body)

    def test_pipeline_well_and_labels_match_newer_charts(self):
        self.assertIn("body.oc-root .vwrap", SALES)
        self.assertIn("background: #0b2438", SALES)
        self.assertIn("#1e3e53", SALES)
        self.assertIn("color: #7898b0", SALES)
        self.assertGreaterEqual(_ratio("#7898b0", CHART_WELL), 4.5)

    def test_pipeline_gridlines_span_the_plot(self):
        overlay = SALES.split("body.oc-root .vwrap::before", 1)[1].split("body.oc-root .vcol", 1)[0]
        self.assertIn("#1e3e53", overlay)
        area = SALES.split("body.oc-root .vbarArea", 1)[1].split("body.oc-root .vval", 1)[0]
        self.assertIn("background-image: none", area)

    def test_pipeline_bar_fills_clear_the_well(self):
        for color in BAR_COLORS:
            self.assertGreaterEqual(_ratio(color, CHART_WELL), 3.0, color)
            self.assertGreaterEqual(_ratio(color, "#0d293f"), 3.0, color)


class FmaDarkSurfaceTests(unittest.TestCase):
    def test_active_date_chip_is_navy_not_pink(self):
        self.assertNotIn("#fde9f3", FMA)
        self.assertIn("body.oc-root .wrap > .pillbar", FMA)
        self.assertIn("background: #0d293f", FMA)
        self.assertIn("color: #b6f6ff !important", FMA)

    def test_page_dates_and_performer_rows_are_dark(self):
        self.assertIn("body.oc-root .scopeNote", FMA)
        self.assertIn("background: #102c42", FMA)
        self.assertIn("body.oc-root .list .row", FMA)
        self.assertIn("background: #163a52", FMA)
        self.assertIn("color: #f1f6ff", FMA)

    def test_text_pairs_meet_aa(self):
        pairs = (
            ("#7898b0", CHART_WELL),
            ("#d5e3ec", "#102d43"),
            ("#b6f6ff", "#123e52"),
            ("#d5e3ec", "#102c42"),
            ("#f1f6ff", "#102c42"),
            ("#f1f6ff", "#163a52"),
            ("#b6f6ff", "#173d52"),
            ("#bed1df", "#091e30"),
        )
        for fg, bg in pairs:
            self.assertGreaterEqual(_ratio(fg, bg), 4.5, f"{fg} on {bg}")


class FmaPolishTests(unittest.TestCase):
    def test_goal_tracks_use_a_dark_groove(self):
        self.assertIn('td div[style*="background:#eef2f7"]', FMA)
        self.assertIn("background: #2b4e66 !important", FMA)
        self.assertIn("box-shadow: inset 0 0 0 1px #5a85a1", FMA)
        track = "#2b4e66"
        for fill in ("#8ef0c8", "#ffbe45", "#ff99a5", "#94a3b8"):
            self.assertGreaterEqual(_ratio(fill, track), 3.0, fill)
        card = "#0d293f"
        cell = "#0b2438"
        self.assertGreaterEqual(_ratio("#5a85a1", card), 3.0)
        self.assertGreaterEqual(_ratio("#5a85a1", cell), 3.0)
        self.assertIn("progressCell(r.sit, r.demosGoal)", FMA)

    def test_tablet_cards_fill_the_explicit_grid(self):
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", FMA)
        self.assertIn(
            ".span-3, .span-4, .span-6, .span-8, .span-9, .span-12 { grid-column: 1 / -1; }",
            FMA,
        )
        phone = FMA.split("@media (max-width: 520px)", 1)[1].split("/* See All modal */", 1)[0]
        self.assertIn("grid-column: 1 / -1", phone)
        self.assertNotIn("grid-column: span 12", phone)

    def test_see_all_control_is_under_the_performer_cards(self):
        html = FMA.split("<script>", 1)[0]
        foot = html.index('id="seeAllBtnContainerTop" class="seeAllFoot span-12"')
        demo = html.index("GHL — Demo Rate by Setter")
        self.assertLess(foot, demo)
        self.assertEqual(html.count('id="seeAllFloatingOpen"'), 1)
        self.assertNotIn('id="seeAllFloatingOpen"', html[demo:])
        self.assertIn("Top 10 of ${n}", FMA)
        self.assertIn('class="seeAllFoot span-12"', FMA)
        self.assertIn('id="seeAllFloatingOpen" type="button"', FMA)
        self.assertNotIn('id="seeAllFloatingOpen" style="position:fixed', FMA)
        self.assertIn("position: static", FMA)
        self.assertIn("padding-bottom: 64px", FMA)
        self.assertIn("font: inherit", FMA)
        self.assertIn("border-radius: 10px", FMA)
        self.assertIn("padding: 7px 14px", FMA)
        self.assertIn("font-weight: 900", FMA)
        self.assertNotIn("seeAllContainer.style.display = 'block'", FMA)
        self.assertNotIn("seeAllTop.style.display = 'block'", FMA)

    def test_see_all_popup_is_dark_with_a_focus_ring(self):
        self.assertIn("body.oc-root #seeAllModal .modal-inner", FMA)
        self.assertIn("background: #0d293f !important", FMA)
        self.assertIn("outline: 2px solid #26d9eb", FMA)
        pairs = (
            ("#f1f6ff", "#0d293f"),
            ("#e7f1f8", "#0d293f"),
            ("#d5e3ec", "#0d293f"),
            ("#d5e3ec", "#102d43"),
            ("#91abc0", "#0a2236"),
        )
        for fg, bg in pairs:
            self.assertGreaterEqual(_ratio(fg, bg), 4.5, f"{fg} on {bg}")


if __name__ == "__main__":
    unittest.main()
