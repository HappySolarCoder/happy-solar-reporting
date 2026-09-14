# -*- coding: utf-8 -*-

"""Website Traffic Dashboard v1 — wireframe stub. No live metric wiring."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


page = load_module("website_traffic_page", API / "website_traffic.py")
nav = load_module("dashboard_nav_website_traffic", API / "dashboard_nav.py")
index = load_module("hs_index_website_traffic", API / "index.py")

PAGE_SRC = (API / "website_traffic.py").read_text()
NAV_SRC = (API / "dashboard_nav.py").read_text()
WARM_SRC = (API / "warm_cache.py").read_text()
VERCEL_TEXT = (ROOT / "vercel.json").read_text()

FORBIDDEN_LIVE = (
    "get_db",
    "from google.cloud",
    "import firestore",
    "analyticsdata",
    "runReport",
    "GA4_SERVICE_ACCOUNT",
    "google.analytics",
    ".collection(",
    "run_report",
)

EXCLUDE_TOKENS = (
    "Hawkstone Way",
    "313 E Stonebridge Gilbert",
    "Test Test",
    "Evan Day",
    "adchday@gmail.com",
    "evanrday23@gmail.com",
    "preview/debug/internal",
)


def invoke_get(url: str):
    cls = page.handler
    captured = {}

    class _W:
        def __init__(self):
            self.buf = BytesIO()

        def write(self, data):
            self.buf.write(data)

    inst = cls.__new__(cls)
    inst.path = url
    inst.wfile = _W()
    inst.send_response = lambda code: captured.__setitem__("code", code)
    inst.send_header = lambda key, value: captured.setdefault("headers", {}).__setitem__(
        key, value
    )
    inst.end_headers = lambda: captured.__setitem__("ended", True)
    inst.do_GET()
    return captured, inst.wfile.buf.getvalue()


class WebsiteTrafficNavTests(unittest.TestCase):
    def test_nav_lists_website_traffic_next_to_funnel(self):
        html = nav.render_dashboard_nav("website_traffic")
        self.assertIn('href="/api/website_funnel"', html)
        self.assertIn('href="/api/website_traffic"', html)
        self.assertLess(html.find("Website Funnel"), html.find("Website Traffic"))
        self.assertIn('class="navbtn active" href="/api/website_traffic"', html)
        self.assertNotIn('class="navbtn active" href="/api/website_funnel"', html)

    def test_funnel_page_does_not_mark_traffic_active(self):
        html = nav.render_dashboard_nav("website_funnel")
        self.assertIn('class="navbtn active" href="/api/website_funnel"', html)
        self.assertIn('href="/api/website_traffic"', html)
        self.assertNotIn('class="navbtn active" href="/api/website_traffic"', html)


class WebsiteTrafficHtmlTests(unittest.TestCase):
    def test_html_has_wireframe_chrome_and_six_tabs(self):
        html = page.render_html(datetime(2026, 9, 14, tzinfo=ZoneInfo("America/New_York")))
        self.assertIn("WIREFRAME / EXAMPLE DATA", html)
        self.assertIn("not live metrics", html)
        self.assertIn("Date range ET", html)
        self.assertIn('value="2026-09-07"', html)
        self.assertIn('value="2026-09-13"', html)
        self.assertIn("happyslr.com", html)
        self.assertIn("wny.happyslr.com", html)
        self.assertIn("Test filter ON", html)
        self.assertIn('id="testFilter" type="checkbox" checked', html)
        self.assertIn("Compare prior", html)
        for label in (
            "Overview",
            "Acquisition",
            "Content/LPs",
            "Funnel",
            "Audience",
            "Named fills",
        ):
            self.assertIn(label, html)
        self.assertIn('data-tab="overview"', html)
        self.assertIn('data-tab="acquisition"', html)
        self.assertIn('data-tab="content"', html)
        self.assertIn('data-tab="funnel"', html)
        self.assertIn('data-tab="audience"', html)
        self.assertIn('data-tab="named"', html)
        self.assertIn("class=\"tabpanel active\"", html)

    def test_overview_kpis_and_ga4_labels(self):
        html = page.render_html()
        for label in (
            "Sessions",
            "Users",
            "New / returning",
            "Pageviews",
            "Pages / session",
            "Bounce / engaged",
            "Avg engagement",
            "Vs prior",
            "Brand site sessions",
            "Estimate / calc sessions",
        ):
            self.assertIn(label, html)
        self.assertIn("GA4 bounce + engaged session rate", html)
        self.assertIn('class="card span-3 vs-prior"', html)
        self.assertIn("classList.toggle('is-off', !compare)", html)
        self.assertIn("CTA taps → /estimate", html)
        self.assertIn("Organic FB post → sessions", html)

    def test_acquisition_content_funnel_audience_named(self):
        html = page.render_html()
        self.assertIn("Channel + source / medium", html)
        self.assertIn("FB organic vs Meta paid", html)
        self.assertIn("Landing × source — top 10", html)
        self.assertIn("/estimate", html)
        self.assertIn("legacy wny", html.lower())
        self.assertIn("estimate/LP visits → start → address → bill → contact → submit → named fill", html)
        self.assertIn("Estimate / LP visits", html)
        self.assertIn("Brand-site sessions", html)
        self.assertIn("not all-site sessions", html)
        self.assertIn("not funnel step 1", html)
        self.assertIn("23.2% of estimate/LP", html)
        self.assertIn("Test filter ON — excluded: Hawkstone / Stonebridge / Test Test / Evan Day / test emails / preview", html)
        self.assertIn("id=\"excludeChip\"", html)
        self.assertIn("Paid landing mismatch", html)
        self.assertIn("www-without-estimate_start", html)
        self.assertIn("Instant Form / 3PL are NOT website leads", html)
        self.assertIn("WNY metros", html)
        self.assertIn("<td>Buffalo</td>", html)
        self.assertIn("<td>Rochester</td>", html)
        self.assertIn("<td>Syracuse</td>", html)
        self.assertIn("<td>Niagara-area</td>", html)
        self.assertIn("Device / browser", html)
        self.assertIn("Role-gated", html)
        self.assertIn("Marketing sees aggregates only", html)
        self.assertIn("PII table is gated for sales", html)
        self.assertIn("Blurred / disabled PII mock", html)
        self.assertIn("pii-mock", html)

    def test_strips_footer_and_cta(self):
        html = page.render_html()
        self.assertIn("when Ads ACTIVE", html)
        self.assertIn("Meta is not wired", html)
        self.assertIn("Named fills · session→submit", html)
        self.assertIn("CPA when paid", html)
        self.assertIn("estimate/LP visits ↑ · starts → 0", html)
        self.assertIn("408492342", html)
        self.assertIn("G-V02RZFR4SZ", html)
        self.assertIn("source=new-site-estimate", html)
        self.assertIn("www.happyslr.com/estimate", html)
        self.assertIn("Dual-domain history", html)
        self.assertIn("/api/website_traffic?format=json", html)
        self.assertIn('href="/api/website_traffic"', html)
        self.assertIn("Website Traffic", html)

    def test_page_handler_uses_traffic_nav(self):
        html = page.render_html()
        self.assertIn('class="navbtn active" href="/api/website_traffic"', html)


class WebsiteTrafficIsolationTests(unittest.TestCase):
    def test_no_live_ga4_firestore_or_meta_claims(self):
        for token in FORBIDDEN_LIVE:
            self.assertNotIn(token, PAGE_SRC)
        self.assertNotIn("website_traffic", WARM_SRC)
        self.assertNotIn("website_traffic", VERCEL_TEXT)
        self.assertIn("Meta is not wired", PAGE_SRC)

    def test_exclude_list_is_documented_in_comment(self):
        for token in EXCLUDE_TOKENS:
            self.assertIn(token, PAGE_SRC)
        self.assertTrue(PAGE_SRC.strip().startswith("#") or '"""' in PAGE_SRC[:800])

    def test_instant_form_3pl_are_not_website_leads(self):
        self.assertIn("Instant Form / 3PL are NOT website leads", PAGE_SRC)
        self.assertIn("Form freeze", PAGE_SRC)

    def test_funnel_top_is_not_all_site_sessions(self):
        html = page.render_html()
        self.assertNotIn('<div class="name">Visits</div>', html)
        self.assertIn("Funnel step 1", html)
        self.assertIn("Dual top — not funnel step 1", html)


class WebsiteTrafficHandlerTests(unittest.TestCase):
    def test_html_default_and_json_stub(self):
        captured, raw = invoke_get("/api/website_traffic")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Content-Type"], "text/html; charset=utf-8")
        html = raw.decode("utf-8")
        self.assertIn("WIREFRAME / EXAMPLE DATA", html)
        self.assertIn("Overview", html)

        captured, raw = invoke_get("/api/website_traffic?format=json")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Content-Type"], "application/json")
        self.assertEqual(json.loads(raw.decode("utf-8")), {"stub": True, "example": True})

    def test_dispatch_resolves_website_traffic(self):
        self.assertEqual(index.dispatch_route("/api/website_traffic"), "website_traffic")
        self.assertEqual(
            index.dispatch_file("website_traffic"), API / "website_traffic.py"
        )
        self.assertEqual(
            index.dispatch_route("/api", "hs=website_traffic&format=json"),
            "website_traffic",
        )


if __name__ == "__main__":
    unittest.main()
