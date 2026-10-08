# -*- coding: utf-8 -*-

"""Daily Dashboard no longer shows or requests the Kixie call metric."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_PATH = ROOT / "api" / "daily_update.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


daily = load_module("daily_update_no_kixie", DAILY_PATH)


class DailyUpdateNoKixieTests(unittest.TestCase):
    def test_daily_dashboard_omits_kixie_call_metric(self):
        html = daily.HTML
        lowered = html.lower()
        self.assertNotIn("kixie", lowered)
        self.assertNotIn("tblkixie", lowered)
        self.assertNotIn("kixie_calls_summary", lowered)
        self.assertNotIn("activity-stack", html)
        self.assertIn("Morning meeting snapshot across GHL and Raydar", html)
        self.assertIn("Door Knocks by Raydar User", html)
        self.assertIn("Powerline Calls by User", html)
        self.assertIn('class="card span-6 accent-powerline"', html)
        self.assertIn("Sales (GHL)", html)
        self.assertIn("Opportunities Created", html)
        self.assertIn("/api/metrics/sales?", html)
        self.assertIn("/api/metrics/opportunities_created?", html)
        self.assertIn("/api/metrics/raydar_doors_knocked?", html)
        self.assertIn("/api/powerline_dashboard?", html)
        self.assertIn("pipeline_scope=all&lead_source=", html)
        knocks = html.find("Door Knocks by Raydar User")
        powerline = html.find("Powerline Calls by User")
        self.assertGreater(knocks, -1)
        self.assertGreater(powerline, knocks)
        self.assertLess(html.find('id="tblKnocks"'), html.find('id="tblPowerline"'))


if __name__ == "__main__":
    unittest.main()
