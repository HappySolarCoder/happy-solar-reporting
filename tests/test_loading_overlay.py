# -*- coding: utf-8 -*-

"""The Happy Solar loading overlay is mounted once and stays on the real pages."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


company_overview = load_module("company_overview_overlay", API / "company_overview.py")
goals_dashboard = load_module("goals_dashboard_overlay", API / "goals_dashboard.py")
nav = load_module("dashboard_nav_overlay", API / "dashboard_nav.py")


class LoadingOverlayWiringTests(unittest.TestCase):
    def test_lifecycle_script_passes(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "loading_overlay_lifecycle.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + "\n" + completed.stderr,
        )
        self.assertIn("loading overlay lifecycle checks passed", completed.stdout)

    def _assert_overlay(self, html: str):
        self.assertEqual(html.count("LOADING REQUESTED DATA"), 1)
        self.assertIn("Updating your dashboard", html)
        self.assertIn("A CLEARER VIEW IS ON ITS WAY", html)
        self.assertIn("Bringing your numbers into focus.", html)
        self.assertIn("HAPPY SOLAR", html)
        self.assertIn("OPERATIONS CONTROL", html)
        self.assertIn("solar-satellite", html)
        self.assertIn("solar-rays", html)
        self.assertIn("SHOW_DELAY_MS = 150", html)
        self.assertIn("new AbortController", html)
        self.assertIn('role", "dialog"', html)
        self.assertIn('aria-modal", "true"', html)
        self.assertIn("We couldn’t refresh this view", html)
        self.assertIn("Your previous view is still available.", html)
        self.assertIn("We couldn’t load this view. Try again.", html)
        self.assertIn("Try again", html)
        self.assertIn("Back to dashboard", html)
        self.assertNotIn("Preview loading", html)
        self.assertNotIn("previewDashboardLoading", html)
        self.assertNotIn("<!-- HAPPY_SOLAR_LOADING -->", html)
        self.assertNotIn("shouldTrackFetch", html)
        self.assertIn('class="hs-loader is-hidden"', html)
        self.assertIn("z-index:150", html)
        self.assertIn("prefers-reduced-motion:reduce", html)
        self.assertIn("max-width:800px", html)
        self.assertLess(html.find(".navlink{display:flex"), html.find("#sidebar a.navlink {"))

    def test_company_overview_mounts_the_shared_overlay(self):
        html = company_overview.render_html(2026, 10)
        self._assert_overlay(html)
        self.assertIn('HappySolarLoading.begin("view")', html)
        self.assertIn("window.hsOpsReload = load", html)
        self.assertIn('id="lgCompanyCreated">—', html)
        self.assertEqual(html.count("function showError()"), 1)

    def test_goals_dashboard_mounts_the_same_overlay(self):
        html = goals_dashboard.render_html()
        self._assert_overlay(html)
        self.assertIn('HappySolarLoading.begin("view")', html)
        self.assertIn("window.hsOpsReload = load", html)
        self.assertIn("hsOptional: true", html)

    def test_nav_css_appends_overlay_without_replacing_the_theme(self):
        css = nav.dashboard_nav_css()
        self.assertIn(".dashboard-loading", css)
        self.assertIn("font-family:'DM Sans'", css)
        self.assertIn("@import url('https://fonts.googleapis.com/css2?family=DM+Sans", css)
        theme_link = css.find(".navlink{display:flex")
        override = css.find("#sidebar a.navlink {")
        overlay = css.find(".dashboard-loading")
        self.assertGreater(theme_link, -1)
        self.assertGreater(override, theme_link)
        self.assertGreater(overlay, override)


if __name__ == "__main__":
    unittest.main()
