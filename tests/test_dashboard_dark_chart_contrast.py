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


if __name__ == "__main__":
    unittest.main()
