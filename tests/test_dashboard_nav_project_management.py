# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV_PATH = ROOT / "api" / "dashboard_nav.py"

PM_HUB_URL = "https://happy-solar-monday-pm.vercel.app/project-management-hub.html"
HOLD_CANCELLED_URL = "https://happy-solar-monday-pm.vercel.app/happy-slr-hold-cancelled.html"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nav = load_module("dashboard_nav_pm", NAV_PATH)
render_dashboard_nav = nav.render_dashboard_nav


class DashboardNavProjectManagementTests(unittest.TestCase):
    def test_nav_includes_project_management_and_sibling_urls(self):
        html = render_dashboard_nav("company_overview")
        self.assertIn("Project Management", html)
        self.assertIn(PM_HUB_URL, html)
        self.assertIn(HOLD_CANCELLED_URL, html)
        daily = html.find("Daily Dashboard")
        project = html.find("Project Management")
        self.assertNotEqual(daily, -1)
        self.assertNotEqual(project, -1)
        self.assertLess(daily, project)
        bot = html.find("Bot KPI")
        website = html.find("Website Funnel")
        self.assertNotEqual(bot, -1)
        self.assertLess(project, bot)
        self.assertIn("/api/bot_kpi_scorecard", html)
        self.assertNotEqual(website, -1)
        self.assertLess(bot, website)
        self.assertIn("/api/website_funnel", html)
        self.assertIn("/api/inbound_cac", html)
        self.assertIn("Inbound CAC", html)

    def test_project_management_dropdown_is_active_for_either_child(self):
        hub_html = render_dashboard_nav("project_management_hub")
        hold_html = render_dashboard_nav("hold_cancelled")
        self.assertIn("Project Management", hub_html)
        self.assertIn(PM_HUB_URL, hub_html)
        self.assertIn(HOLD_CANCELLED_URL, hold_html)
        self.assertIn('summary class="navbtn active"', hub_html)
        self.assertIn('summary class="navbtn active"', hold_html)
        self.assertIn(f'href="{PM_HUB_URL}"', hub_html)
        self.assertIn("navmenu-item active", hub_html)
        self.assertIn("navmenu-item active", hold_html)


if __name__ == "__main__":
    unittest.main()
