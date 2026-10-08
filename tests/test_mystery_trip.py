# -*- coding: utf-8 -*-

"""Mystery Trip contest board (ClickUp 86bccr3du)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trip = load_module("mystery_trip_page", API / "mystery_trip.py")
nav = load_module("dashboard_nav_contests", API / "dashboard_nav.py")


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


class MysteryTripTests(unittest.TestCase):
    def test_rules_pass_in_node(self):
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "mystery_trip_rules.mjs")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("mystery trip rules ok", completed.stdout)

    def test_contests_section_lists_mystery_trip(self):
        plan = nav.embed_menu_plan()
        contests = [rows for label, _slug, rows in plan if label == "Contests"]
        self.assertEqual(len(contests), 1)
        self.assertEqual([key for key, _title, _href in contests[0]], ["mystery_trip"])
        html = nav.render_dashboard_nav("mystery_trip")
        self.assertIn("CONTESTS", html)
        self.assertIn('class="navlink active" href="/api/mystery_trip"', html)

    def test_page_renders_with_logic_and_no_placeholders(self):
        html = trip.render_page()
        for marker in ("__DASHBOARD_NAV_CSS__", "__DASHBOARD_NAV_HTML__", "__LOGIC_JS__", "__CREDITS_JSON__", "__PLANE__", "__PALM_LEFT__"):
            self.assertNotIn(marker, html)
        self.assertIn("var MysteryTrip", html)
        self.assertIn("<h1 class=\"mt-title\" id=\"mtTitle\">Mystery Trip</h1>", html)
        self.assertIn("/api/metrics/demo_rate", html)
        self.assertIn("/api/metrics/bloom_goals", html)
        self.assertIn("Oct 1 – Dec 23", html)

    def test_copy_rules(self):
        html = trip.render_page()
        parser = _VisibleText()
        parser.feed(html)
        text = " ".join(parser.parts)
        self.assertNotRegex(text, r"(?i)\b(sit|sits|sat)\b")
        # The destination is a secret and the middle Self-Gen column is left out.
        self.assertNotRegex(html, r"(?i)\b(bali|ubud)\b")
        self.assertNotRegex(text, r"(?i)self-gen")
        self.assertIn("Steak Dinner", text)
        self.assertIn("under 30%", text)
        self.assertIn("24 total sales", text)

    def test_metric_requests_ignore_data_center_filters(self):
        html = trip.render_page()
        self.assertIn('<body data-oc-native-filters="1">', html)
        page_js = html.split("async function load()", 1)[1]
        calls = re.findall(r'"/api/metrics/([a-z_]+)\?([^"]*)"( \+ range)?', page_js)
        self.assertEqual(len(calls), 5)
        for name, query, uses_range in calls:
            self.assertTrue(query.startswith("oc_raw=1") or (query == "" and uses_range), name)
        self.assertIn('var range = "oc_raw=1&format=json', page_js)

    def test_page_is_read_only(self):
        html = trip.render_page()
        page_js = html.split("var MysteryTrip", 1)[1]
        self.assertNotRegex(page_js, r"method:\s*['\"](POST|PUT|PATCH|DELETE)")

    def test_credits_payload_skips_blank_rows(self):
        original = trip.RECRUIT_CREDITS
        try:
            trip.RECRUIT_CREDITS = (
                {"recruiter": "Bo Hill", "recruit": "New Rep", "month": "2026-11"},
                {"recruiter": "", "recruit": "Nobody", "month": "2026-11"},
            )
            rows = trip.credits_payload()
        finally:
            trip.RECRUIT_CREDITS = original
        self.assertEqual(rows, [{"recruiter": "Bo Hill", "recruit": "New Rep", "month": "2026-11", "month_label": "November"}])
        self.assertEqual(trip.credits_payload(), [])

    def test_credits_json_cannot_close_the_script(self):
        original = trip.RECRUIT_CREDITS
        try:
            trip.RECRUIT_CREDITS = ({"recruiter": "</script><b>x", "recruit": "y", "month": "2026-10"},)
            html = trip.render_page()
        finally:
            trip.RECRUIT_CREDITS = original
        self.assertNotIn("</script><b>x", html)


if __name__ == "__main__":
    unittest.main()
