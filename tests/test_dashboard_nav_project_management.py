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
        self.assertIn("PROJECT MANAGEMENT", html)
        self.assertIn(PM_HUB_URL, html)
        self.assertIn(HOLD_CANCELLED_URL, html)
        daily = html.find("Daily Dashboard")
        project = html.find("PROJECT MANAGEMENT")
        self.assertNotEqual(daily, -1)
        self.assertNotEqual(project, -1)
        self.assertLess(daily, project)
        bot = html.find("Bot KPI")
        website = html.find("Website Funnel")
        self.assertNotEqual(bot, -1)
        self.assertLess(project, bot)
        self.assertIn("/api/bot_kpi_scorecard", html)
        self.assertNotEqual(website, -1)
        self.assertLess(website, bot)
        self.assertIn("/api/website_funnel", html)
        self.assertIn("/api/website_traffic", html)
        self.assertLess(website, html.find("Website Traffic"))
        self.assertNotIn("/api/inbound_cac", html)
        self.assertNotIn("Inbound CAC", html)

    def test_project_management_dropdown_is_active_for_either_child(self):
        hub_html = render_dashboard_nav("project_management_hub")
        hold_html = render_dashboard_nav("hold_cancelled")
        self.assertIn("PROJECT MANAGEMENT", hub_html)
        self.assertIn(PM_HUB_URL, hub_html)
        self.assertIn(HOLD_CANCELLED_URL, hold_html)
        self.assertIn('class="navlink active"', hub_html)
        self.assertIn('class="navlink active"', hold_html)
        self.assertNotIn("navbtn", hub_html)
        self.assertIn(f'href="{PM_HUB_URL}"', hub_html)
        self.assertIn("Project Hub", hub_html)
        self.assertIn("Hold / Cancelled", hold_html)

    def test_sidebar_links_beat_legacy_navbtn_pills(self):
        css = nav.dashboard_nav_css()
        override = css.find("#sidebar a.navlink {")
        theme_link = css.find(".navlink{display:flex")
        self.assertGreater(theme_link, -1)
        self.assertGreater(override, theme_link)
        self.assertIn("background: transparent !important", css[override:])
        self.assertIn("color: #a7bfd2 !important", css[override:])
        html = render_dashboard_nav("sales_dashboard")
        self.assertIn('class="navlink active" href="/api/sales_dashboard"', html)
        self.assertNotIn("navbtn", html)
        self.assertIn("body.menu-open #sidebar { transform: translateX(0); }", css)
        self.assertIn("button.mobile-menu.oc-menu-btn", css)

    def test_ops_nav_collapse_control_is_accessible_and_persistent(self):
        html = render_dashboard_nav("company_overview")
        css = nav.dashboard_nav_css()
        self.assertIn('id="ocNavToggle"', html)
        self.assertIn('aria-controls="sidebar"', html)
        self.assertIn('aria-expanded="true"', html)
        self.assertIn('aria-label="Collapse navigation"', html)
        self.assertIn("Expand navigation", html)
        self.assertIn("hsOpsNavCollapsed", html)
        self.assertIn("localStorage.getItem('hsOpsNavCollapsed')", css)
        self.assertIn("oc-nav-collapsed", css)
        self.assertIn("html.oc-nav-collapsed #sidebar { width: 64px; }", css)
        self.assertIn("margin-left: 64px !important;", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("transition: none !important;", css)
        self.assertIn("hsOpsReflowCharts", html)
        self.assertIn("dispatchEvent(new Event('resize'))", html)
        self.assertIn('<div class="navgroup">COMPANY</div>', html)
        self.assertIn('<span class="navlabel">Company Overview</span>', html)
        self.assertIn('class="navlink active" href="/api/company_overview"', html)
        self.assertIn("box-shadow: inset 2px 0 #26d9eb !important", css)
        self.assertIn("@media (max-width: 800px)", css)
        self.assertNotIn(">Collapse navigation<", html)
        self.assertNotRegex(html, r"\bsits\b")


if __name__ == "__main__":
    unittest.main()
