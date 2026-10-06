# -*- coding: utf-8 -*-
"""Sales Dashboard header stays in normal flow so wide viewports cannot overlap it."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH_PATH = ROOT / "api" / "sales_dashboard.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dash = load_module("sales_dashboard_header", DASH_PATH)


class SalesDashboardHeaderTests(unittest.TestCase):
    def test_header_controls_are_in_flow(self):
        html = dash.render_html(2026, 10)
        self.assertIn('class="topbar-title"', html)
        self.assertIn('class="header-actions"', html)
        actions = html.find('class="header-actions"')
        filters = html.find('class="filters"')
        self.assertLess(actions, filters)
        self.assertLess(html.find("Missing Dispos"), filters)
        self.assertLess(html.find("Admin Settings"), filters)
        self.assertIn("position: static", html)
        brand = html.find(".brandCenter {")
        self.assertNotEqual(brand, -1)
        brand_rule = html[brand:html.find("}", brand)]
        self.assertNotIn("position: absolute", brand_rule)
        self.assertNotIn("left: 50%", brand_rule)
        actions_rule_at = html.find(".adminSettings,")
        actions_rule = html[actions_rule_at:html.find("}", actions_rule_at)]
        self.assertIn("position: static", actions_rule)
        self.assertNotIn("right: 158px", html)
        self.assertNotIn("right: 18px", html)
