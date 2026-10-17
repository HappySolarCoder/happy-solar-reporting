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

    def test_sales_menu_includes_sc_overview(self):
        html = render_dashboard_nav("sc_overview")
        sales_items = next(items for label, items in nav.NAV_GROUPS if label == "SALES")
        sales_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Sales")
        self.assertIn(
            ("sc_overview", "Solar Consultant Overview", "/api/sc_overview"),
            sales_items,
        )
        self.assertIn("sc_overview", sales_keys)
        self.assertIn('class="navlink active" href="/api/sc_overview"', html)
        self.assertIn("Solar Consultant Overview", html)
        self.assertIn('aria-current="true"', _group_button(html, "Sales"))
        self.assertNotIn('aria-current="true"', _group_button(html, "Company"))
        self.assertIn(
            'class="oc-embed-link active" href="/api/sc_overview" aria-current="page"',
            html,
        )
        self.assertLess(html.find("Sales Dashboard"), html.find("Solar Consultant Overview"))
        self.assertLess(html.find("Solar Consultant Overview"), html.find("Sales List"))

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
        # diamond_opp_list and sales_list are listed under Sales and Proj. Man.
        self.assertEqual(menu_count, sidebar_count + 2)
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
        project_btn = _group_button(html, "Proj. Man.")
        self.assertIn('aria-current="true"', sales_btn)
        self.assertIn('aria-current="true"', project_btn)
        self.assertNotIn('aria-current="true"', company_btn)
        self.assertIn('class="oc-embed-group is-current"', html)
        self.assertEqual(html.count('class="oc-embed-group is-current"'), 2)
        self.assertEqual(
            html.count('class="oc-embed-link active" href="/api/sales_list" aria-current="page"'),
            2,
        )
        self.assertGreaterEqual(_contrast("#a7bfd2", "#081e31"), 4.5)
        self.assertGreaterEqual(_contrast("#26d9eb", "#081e31"), 4.5)
        self.assertGreaterEqual(_contrast("#d5e6f2", "#0c253b"), 4.5)
        self.assertGreaterEqual(_contrast("#26d9eb", "#123e52"), 4.5)
        self.assertGreaterEqual(_contrast("#ffffff", "#102e46"), 4.5)
        lead = render_dashboard_nav("website_traffic")
        self.assertEqual(lead.count('class="oc-embed-group is-current"'), 1)
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

    def test_project_management_menu_shares_diamond_and_sales_list(self):
        sales_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Sales")
        pm_keys = next(keys for label, _slug, keys in nav.EMBED_MENUS if label == "Proj. Man.")
        self.assertEqual(
            sales_keys,
            (
                "sales_dashboard",
                "sc_overview",
                "diamond_sweeper",
                "diamond_opp_list",
                "sales_list",
                "rep_daily_recap",
                "missing_dispos",
            ),
        )
        self.assertEqual(
            pm_keys,
            (
                "project_management_hub",
                "hold_cancelled",
                "diamond_opp_list",
                "sales_list",
            ),
        )
        sidebar_pm = next(items for label, items in nav.NAV_GROUPS if label == "PROJECT MANAGEMENT")
        self.assertEqual(
            [key for key, _title, _href in sidebar_pm],
            ["project_management_hub", "hold_cancelled"],
        )
        plan = nav.embed_menu_plan()
        pm_rows = next(rows for label, _slug, rows in plan if label == "Proj. Man.")
        sales_rows = next(rows for label, _slug, rows in plan if label == "Sales")
        self.assertEqual(
            pm_rows[-2:],
            (
                ("diamond_opp_list", "Diamond — Opportunity List", "/api/diamond_opp_list"),
                ("sales_list", "Sales List", "/api/sales_list"),
            ),
        )
        self.assertIn(("sales_list", "Sales List", "/api/sales_list"), sales_rows)
        self.assertIn(
            ("diamond_opp_list", "Diamond — Opportunity List", "/api/diamond_opp_list"),
            sales_rows,
        )
        for current, href in (
            ("diamond_opp_list", "/api/diamond_opp_list"),
            ("sales_list", "/api/sales_list"),
        ):
            html = render_dashboard_nav(current)
            row_html = nav.render_embed_section_row(current)
            active = f'class="oc-embed-link active" href="{href}" aria-current="page"'
            for rendered in (html, row_html):
                self.assertEqual(rendered.count('class="oc-embed-group is-current"'), 2)
                self.assertIn('aria-current="true"', _group_button(rendered, "Sales"))
                self.assertIn('aria-current="true"', _group_button(rendered, "Proj. Man."))
                self.assertNotIn('aria-current="true"', _group_button(rendered, "Company"))
                self.assertNotIn('aria-current="true"', _group_button(rendered, "Lead Gen"))
                self.assertEqual(rendered.count(active), 2)
                self.assertIn(active, _menu_html(rendered, "sales"))
                self.assertIn(active, _menu_html(rendered, "proj-man"))
                embed_ids = [item for item in _html_ids(rendered) if item.startswith("oc-embed-")]
                self.assertEqual(embed_ids, [
                    "oc-embed-btn-company",
                    "oc-embed-menu-company",
                    "oc-embed-btn-sales",
                    "oc-embed-menu-sales",
                    "oc-embed-btn-lead-gen",
                    "oc-embed-menu-lead-gen",
                    "oc-embed-btn-proj-man",
                    "oc-embed-menu-proj-man",
                    "oc-embed-btn-contests",
                    "oc-embed-menu-contests",
                    "oc-embed-btn-other",
                    "oc-embed-menu-other",
                ])
            self.assertEqual(html.count('id="oc-embed-btn-sales"'), 1)
            self.assertEqual(html.count('id="oc-embed-menu-sales"'), 1)
            self.assertEqual(html.count('id="oc-embed-btn-proj-man"'), 1)
            self.assertEqual(html.count('id="oc-embed-menu-proj-man"'), 1)
            self.assertEqual(html.count('class="navlink active"'), 1)
        solo = render_dashboard_nav("hold_cancelled")
        self.assertEqual(solo.count('class="oc-embed-group is-current"'), 1)
        self.assertIn('aria-current="true"', _group_button(solo, "Proj. Man."))
        self.assertNotIn('aria-current="true"', _group_button(solo, "Sales"))
        self.assertEqual(
            solo.count(
                'class="oc-embed-link active" href="'
                + HOLD_CANCELLED_URL
                + '" aria-current="page"'
            ),
            1,
        )


def _menu_html(html: str, slug: str) -> str:
    token = f'id="oc-embed-menu-{slug}"'
    start = html.find(token)
    if start < 0:
        raise AssertionError(f"missing menu {slug}")
    open_end = html.find(">", start)
    close = html.find("</div>", open_end)
    return html[open_end + 1:close]


def _html_ids(html: str) -> list[str]:
    ids: list[str] = []
    needle = 'id="'
    start = 0
    while True:
        idx = html.find(needle, start)
        if idx < 0:
            return ids
        end = html.find('"', idx + len(needle))
        ids.append(html[idx + len(needle):end])
        start = end + 1


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
