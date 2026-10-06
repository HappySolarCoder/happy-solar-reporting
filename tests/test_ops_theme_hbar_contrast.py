# -*- coding: utf-8 -*-
"""Website Traffic tab bar-chart labels/values meet WCAG AA on the Ops Control navy cards.

These rows live in tabs (Acquisition, Funnel, Named fills) that are hidden on first
load, so a visible-text sweep at page load never sees them.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = (ROOT / "api" / "ops_theme.css").read_text(encoding="utf-8")
TRAFFIC = (ROOT / "api" / "website_traffic.py").read_text(encoding="utf-8")

# Ops Control card / panel backgrounds the bars sit on.
BACKGROUNDS = ("#0d293f", "#0c253b", "#102c42")


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _theme_color(cls: str) -> str:
    m = re.search(r"body\.oc-root \." + re.escape(cls) + r"\s*\{\s*color:\s*(#[0-9a-fA-F]{6})\s*!important", THEME)
    if not m:
        raise AssertionError(f"no body.oc-root .{cls} color override in ops_theme.css")
    return m.group(1)


class TrafficHbarContrastTests(unittest.TestCase):
    def test_hbar_classes_still_rendered(self):
        self.assertIn('class="hbar-label"', TRAFFIC)
        self.assertIn('class="hbar-val"', TRAFFIC)

    def test_hbar_label_and_value_meet_aa_on_navy(self):
        for cls in ("hbar-label", "hbar-val"):
            color = _theme_color(cls)
            for bg in BACKGROUNDS:
                self.assertGreaterEqual(_ratio(color, bg), 4.5, f".{cls} {color} on {bg}")


if __name__ == "__main__":
    unittest.main()
