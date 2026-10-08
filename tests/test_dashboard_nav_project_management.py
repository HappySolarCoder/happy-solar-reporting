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
        self.assertIn("html.oc-nav-collapsed #sidebar { width: 64px; box-sizing: border-box; }", css)
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

    def test_embedded_shell_keeps_section_switcher_and_standalone_rail(self):
        html = render_dashboard_nav("company_overview")
        css = nav.dashboard_nav_css()
        self.assertIn('id="sidebar"', html)
        self.assertIn('class="oc-embed-bar"', html)
        self.assertIn('aria-label="Data Center sections"', html)
        self.assertIn(
            'class="oc-embed-link active" href="/api/company_overview" aria-current="page"',
            html,
        )
        self.assertIn('class="oc-embed-link" href="/api/sales_dashboard"', html)
        self.assertIn('class="oc-embed-link" href="/api/website_funnel"', html)
        self.assertIn(f'href="{PM_HUB_URL}" target="_blank"', html)
        self.assertIn(".oc-embed-bar { display: none; }", css)
        self.assertIn("html.oc-embedded .oc-embed-bar {", css)
        self.assertIn("html.oc-embedded #sidebar,", css)
        self.assertIn("display: none !important;", css)
        self.assertIn("html.oc-embedded .workspace,", css)
        self.assertIn("margin-left: 0 !important;", css)
        self.assertIn("html.oc-embedded .oc-page .topbar {", css)
        self.assertIn("html.oc-embedded .oc-page .global-filterbar {", css)
        self.assertIn("window.self!==window.top", css)
        self.assertIn("embed=1", css)
        self.assertIn("searchParams.set('embed', '1')", html)
        self.assertIn("html.oc-nav-collapsed #sidebar { width: 64px; box-sizing: border-box; }", css)
        self.assertNotRegex(html, r"\b(sit|sits|sat)\b")
        self.assertNotRegex(css, r"\b(sit|sits|sat)\b")

    def test_embedded_row_uses_six_menus_and_keeps_the_rail(self):
        html = render_dashboard_nav("sales_list")
        css = nav.dashboard_nav_css()
        labels = [label for label, _slug, _keys in nav.EMBED_MENUS]
        self.assertEqual(labels, ["Company", "Sales", "Lead Gen", "Proj. Man.", "Contests", "Other"])
        for label in labels:
            self.assertEqual(html.count(f'class="oc-embed-group-label">{label}</span>'), 1)
        self.assertEqual(html.count('aria-haspopup="menu"'), 6)
        self.assertEqual(html.count('class="oc-embed-group-btn"'), 6)
        self.assertEqual(html.count('class="oc-embed-menu"'), 6)
        self.assertIn('type="button"', html)
        self.assertIn("ArrowDown", html)
        self.assertIn("ArrowUp", html)
        self.assertIn("Escape", html)
        self.assertIn("aria-expanded", html)
        self.assertIn("position: fixed", css)
        self.assertIn("overflow: visible", css)
        self.assertNotIn("overflow-x: auto", css)
        sidebar_labels = [label for label, _items in nav.NAV_GROUPS]
        self.assertEqual(
            sidebar_labels,
            ["COMPANY", "SALES", "LEAD GENERATION", "PROJECT MANAGEMENT", "INBOUND", "CONTESTS", "OTHER"],
        )
        menu_count = html.count('role="menuitem" class="oc-embed-link')
        sidebar_count = sum(len(items) for _label, items in nav.NAV_GROUPS)
        self.assertEqual(menu_count, sidebar_count)
        for _label, items in nav.NAV_GROUPS:
            for _key, title, href in items:
                self.assertIn(
                    f'role="menuitem" class="oc-embed-link" href="{href}"',
                    html.replace(
                        'role="menuitem" class="oc-embed-link active"',
                        'role="menuitem" class="oc-embed-link"',
                    ),
                )
                self.assertIn(title, html)
        sales_btn = _group_button(html, "Sales")
        company_btn = _group_button(html, "Company")
        self.assertIn('aria-current="true"', sales_btn)
        self.assertNotIn('aria-current="true"', company_btn)
        self.assertIn('class="oc-embed-group is-current"', html)
        self.assertEqual(html.count('class="oc-embed-group is-current"'), 1)
        self.assertIn(
            'class="oc-embed-link active" href="/api/sales_list" aria-current="page"',
            html,
        )
        self.assertGreaterEqual(_contrast("#a7bfd2", "#081e31"), 4.5)
        self.assertGreaterEqual(_contrast("#26d9eb", "#081e31"), 4.5)
        self.assertGreaterEqual(_contrast("#d5e6f2", "#0c253b"), 4.5)
        self.assertGreaterEqual(_contrast("#26d9eb", "#123e52"), 4.5)
        self.assertGreaterEqual(_contrast("#ffffff", "#102e46"), 4.5)
        lead = render_dashboard_nav("website_traffic")
        self.assertIn('aria-current="true"', _group_button(lead, "Lead Gen"))
        self.assertNotIn('aria-current="true"', _group_button(lead, "Sales"))
        self.assertIn(
            'class="oc-embed-link active" href="/api/website_traffic" aria-current="page"',
            lead,
        )
        project = render_dashboard_nav("hold_cancelled")
        self.assertIn('aria-current="true"', _group_button(project, "Proj. Man."))
        contests = render_dashboard_nav("mystery_trip")
        self.assertIn('aria-current="true"', _group_button(contests, "Contests"))
        self.assertIn(
            'class="oc-embed-link active" href="/api/mystery_trip" aria-current="page"',
            contests,
        )
        other = render_dashboard_nav("settings")
        self.assertIn('aria-current="true"', _group_button(other, "Other"))
        self.assertNotRegex(html, r"\b(sit|sits|sat)\b")

    def test_embed_section_row_is_available_without_the_operations_rail(self):
        html = nav.render_embed_section_row("paid_social_funnel")
        css = nav.embed_section_row_css()
        self.assertIn('class="oc-embed-bar"', html)
        self.assertIn('aria-current="true"', _group_button(html, "Lead Gen"))
        self.assertNotIn('aria-current="true"', _group_button(html, "Company"))
        self.assertIn(
            'class="oc-embed-link active" href="/api/paid_social_funnel" aria-current="page"',
            html,
        )
        self.assertIn("ArrowDown", html)
        self.assertIn("Escape", html)
        self.assertNotIn('id="sidebar"', html)
        self.assertIn(".oc-embed-bar { display: none; }", css)
        self.assertIn("html.oc-embedded .oc-embed-bar {", css)
        self.assertIn("window.self!==window.top", css)
        self.assertNotRegex(html, r"\b(sit|sits|sat)\b")
        self.assertNotRegex(css, r"\b(sit|sits|sat)\b")


def _group_button(html: str, label: str) -> str:
    token = f'class="oc-embed-group-label">{label}</span>'
    idx = html.find(token)
    if idx < 0:
        raise AssertionError(f"missing group label {label}")
    start = html.rfind("<button", 0, idx)
    end = html.find("</button>", idx)
    return html[start:end]


def _contrast(fg: str, bg: str) -> float:
    def channel(hexpair: str) -> float:
        value = int(hexpair, 16) / 255
        if value <= 0.04045:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    def lum(color: str) -> float:
        color = color.lstrip("#")
        red, green, blue = channel(color[0:2]), channel(color[2:4]), channel(color[4:6])
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter, darker = sorted((lum(fg), lum(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


if __name__ == "__main__":
    unittest.main()
