# -*- coding: utf-8 -*-

"""Website Traffic Dashboard v1 — live tiles + EXAMPLE locks."""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import types
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
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
traffic = load_module("website_traffic_metric", METRICS / "website_traffic.py")
nav = load_module("dashboard_nav_website_traffic", API / "dashboard_nav.py")
index = load_module("hs_index_website_traffic", API / "index.py")

PAGE_SRC = (API / "website_traffic.py").read_text()
METRIC_SRC = (METRICS / "website_traffic.py").read_text()
NAV_SRC = (API / "dashboard_nav.py").read_text()
WARM_SRC = (API / "warm_cache.py").read_text()
VERCEL_TEXT = (ROOT / "vercel.json").read_text()

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


def sample_docs():
    return [
        {
            "date": "2026-09-07",
            "ga4": "ok",
            "visits_total": 80,
            "visits_wny": 9,
            "starts": 3,
            "address_complete": 2,
            "bill_complete": 2,
            "estimate_submit": 1,
            "wix_form_submits": 4,
            "cta_clicks": 5,
        },
        {
            "date": "2026-09-08",
            "ga4": "ok",
            "visits_total": 20,
            "visits_wny": 1,
            "starts": 1,
            "address_complete": 1,
            "bill_complete": 0,
            "estimate_submit": 1,
            "wix_form_submits": 0,
            "cta_clicks": 1,
        },
    ]


def sample_path_rows():
    return [
        {"host_name": "www.happyslr.com", "page_path": "/", "count": 70},
        {"host_name": "www.happyslr.com", "page_path": "/buffalo", "count": 10},
        {"host_name": "www.happyslr.com", "page_path": "/estimate", "count": 20},
        {"host_name": "wny.happyslr.com", "page_path": "/calculator", "count": 10},
        {"host_name": "yadmada.com", "page_path": "/", "count": 999},
        {
            "host_name": "www.happyslr.com",
            "page_path": "/estimate",
            "page_location": "https://www.happyslr.com/estimate?internal=1",
            "count": 50,
        },
    ]


def sample_dated_path_rows():
    return [
        {"host_name": "www.happyslr.com", "page_path": "/", "date": "20260907", "count": 70},
        {"host_name": "www.happyslr.com", "page_path": "/estimate", "date": "20260907", "count": 20},
        {"host_name": "wny.happyslr.com", "page_path": "/calculator", "date": "20260907", "count": 10},
        {"host_name": "www.happyslr.com", "page_path": "/", "date": "2026-09-08", "count": 10},
        {"host_name": "www.happyslr.com", "page_path": "/estimate", "date": "2026-09-08", "count": 5},
        {
            "host_name": "www.happyslr.com",
            "page_path": "/estimate",
            "date": "2026-09-07",
            "page_location": "https://www.happyslr.com/estimate?internal=1",
            "count": 50,
        },
        {
            "host_name": "www.happyslr.com",
            "page_path": "/",
            "date": "2026-08-31",
            "date_range": "prior",
            "count": 30,
        },
        {
            "host_name": "www.happyslr.com",
            "page_path": "/estimate",
            "date": "2026-08-31",
            "date_range": "prior",
            "count": 8,
        },
    ]


def sample_fills():
    return [
        {
            "date": "2026-09-07",
            "name": "Phil Pyrce",
            "email": "pyrce@verizon.net",
            "address": "Getzville",
            "source": "leads@",
        },
        {
            "date": "2026-09-07",
            "name": "Test Test",
            "email": "adchday@gmail.com",
            "address": "313 E Stonebridge Dr, Gilbert, AZ",
            "source": "leads@",
        },
        {
            "date": "2026-09-08",
            "name": "Evan Day",
            "email": "evanrday23@gmail.com",
            "address": "24 Hawkstone Way",
            "source": "leads@",
        },
        {
            "date": "2026-09-08",
            "name": "Art Sieczkarek",
            "email": "Sieart@msn.com",
            "source": "new-site-estimate",
        },
    ]


def live_payload(**overrides):
    kwargs = {
        "start": "2026-09-07",
        "end": "2026-09-08",
        "daily_docs": sample_docs(),
        "named_fills": sample_fills(),
        "ga4_paths": {"ga4": "ok", "rows": sample_path_rows()},
        "ga4_overview": {
            "ga4": "ok",
            "current": {
                "sessions": 110,
                "totalUsers": 90,
                "newUsers": 70,
                "screenPageViews": 200,
                "bounceRate": 0.41,
                "engagementRate": 0.59,
                "averageSessionDuration": 72,
            },
            "prior": {"sessions": 100},
        },
        "ga4_acquisition": {
            "ga4": "ok",
            "rows": [
                {
                    "sessionDefaultChannelGroup": "Organic Search",
                    "sessionSource": "google",
                    "sessionMedium": "organic",
                    "sessions": 40,
                    "totalUsers": 36,
                },
                {
                    "sessionDefaultChannelGroup": "Paid Social",
                    "sessionSource": "facebook",
                    "sessionMedium": "paid",
                    "sessions": 12,
                    "totalUsers": 10,
                },
                {
                    "sessionDefaultChannelGroup": "Organic Social",
                    "sessionSource": "facebook",
                    "sessionMedium": "organic",
                    "sessions": 8,
                    "totalUsers": 7,
                },
            ],
        },
        "fetch_remote": False,
    }
    kwargs.update(overrides)
    return traffic.compute_website_traffic(None, **kwargs)


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
    def test_html_has_chrome_and_six_tabs(self):
        html = page.render_html(datetime(2026, 9, 14, tzinfo=ZoneInfo("America/New_York")))
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
        self.assertIn("EXAMPLE", html)
        self.assertIn("Charles QA", html)

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
        self.assertIn("Test filter ON — excluded: Hawkstone / Stonebridge / Test Test / Evan Day / test emails / preview", html)
        self.assertIn('id="excludeChip"', html)
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
        self.assertIn("estimate/LP visits ↑ · starts → 0", html)
        self.assertIn("408492342", html)
        self.assertIn("G-V02RZFR4SZ", html)
        self.assertIn("source=new-site-estimate", html)
        self.assertIn("www.happyslr.com/estimate", html)
        self.assertIn("Dual-domain history", html)
        self.assertIn("/api/website_traffic?format=json", html)
        self.assertIn("Website Traffic", html)

    def test_page_handler_uses_traffic_nav(self):
        html = page.render_html()
        self.assertIn('class="navbtn active" href="/api/website_traffic"', html)

    def test_html_first_paint_shows_live_numbers_not_example_tags(self):
        payload = live_payload(
            ga4_paths={
                "ga4": "ok",
                "rows": [
                    {"host_name": "www.happyslr.com", "page_path": "/", "count": 80},
                    {"host_name": "www.happyslr.com", "page_path": "/estimate", "count": 400},
                ],
            }
        )
        self.assertEqual(payload["funnel"]["estimate_lp_visits"], 400)
        self.assertEqual(payload["named_fills"]["live_count"], 2)
        for name in ("acquisition", "funnel", "named_fills", "overview"):
            self.assertEqual(payload["tiles"][name]["status"], "live", name)

        html = page.render_html(payload=payload)
        markup = html.split("var initialPayload")[0]
        self.assertIn('id="funnelTop">400<', markup)
        self.assertIn('id="stepLp">400<', markup)
        self.assertIn('id="kpiEstimate">400<', markup)
        self.assertIn('id="stepNamed">2<', markup)
        self.assertIn('id="namedKpi">2<', markup)
        self.assertIn('id="scoreboardKpi">2<', markup)
        self.assertIn("Organic Search", markup)
        self.assertIn("google / organic", markup)
        self.assertIn("<td>/estimate</td>", markup)
        self.assertIn("<td>400</td>", markup)

        for name in ("acquisition", "funnel", "named_fills", "overview"):
            labels = re.findall(rf'data-tile="{name}">([^<]+)<', markup)
            self.assertTrue(labels, name)
            for text in labels:
                self.assertEqual(text, "LIVE", name)
                self.assertNotEqual(text, "EXAMPLE", name)

        self.assertNotIn("STEP % STUBS", html)
        self.assertIn('data-tile="audience">EXAMPLE<', markup)
        self.assertIn('data-tile="paid_mismatch">EXAMPLE<', markup)
        self.assertIn('data-tile="meta_spend">NOT WIRED<', markup)
        self.assertIn("EXAMPLE — no contact event", markup)
        self.assertIn('id="titleTag" class="example-tag live">LIVE + EXAMPLE<', markup)
        banner = markup.split('id="statusBanner"', 1)[1].split("</div>", 1)[0]
        self.assertIn("LIVE:", banner)
        self.assertIn("named_fills", banner)
        self.assertIn("audience", banner)
        self.assertIn("function paint(", html)
        self.assertIn("var initialPayload", html)
        self.assertIn('"estimate_lp_visits": 400', html)
        self.assertNotIn("__TAG_", markup)
        self.assertNotIn("__KPI_", markup)
        self.assertIn('id="trendChart"', markup)
        self.assertIn('id="funnelBars"', markup)
        self.assertIn('id="acqBars"', markup)
        self.assertIn('id="namedBars"', markup)
        self.assertIn("Daily trend", markup)
        self.assertIn("<td>2026-09-07</td>", markup)
        self.assertIn("<td>89</td>", markup)
        self.assertIn("google / organic", markup)
        self.assertIn("Estimate / LP visits", markup)
        self.assertIn("function paintCharts(", html)
        self.assertIn('"daily"', html)
        self.assertNotIn("__TREND_", markup)
        self.assertNotIn("__FUNNEL_BARS__", markup)

    def test_html_first_paint_keeps_example_when_tile_not_live(self):
        payload = live_payload(
            ga4_overview={"ga4": "not_configured", "current": {}, "prior": {}}
        )
        self.assertEqual(payload["tiles"]["overview_users"]["status"], "example")
        self.assertEqual(payload["tiles"]["audience"]["status"], "example")
        self.assertEqual(payload["tiles"]["paid_mismatch"]["status"], "example")
        self.assertEqual(payload["tiles"]["meta_spend"]["status"], "not_wired")
        self.assertEqual(payload["tiles"]["contact_step"]["status"], "example")
        html = page.render_html(payload=payload)
        markup = html.split("var initialPayload")[0]
        for name in ("overview_users", "audience", "paid_mismatch"):
            labels = re.findall(rf'data-tile="{name}">([^<]+)<', markup)
            self.assertTrue(labels, name)
            for text in labels:
                self.assertEqual(text, "EXAMPLE", name)
        self.assertIn('data-tile="meta_spend">NOT WIRED<', markup)
        self.assertIn("EXAMPLE — no contact event", markup)
        self.assertEqual(payload["tiles"]["overview"]["status"], "live")
        self.assertIn('data-tile="overview">LIVE<', markup)


class WebsiteTrafficIsolationTests(unittest.TestCase):
    def test_not_on_warm_cache_or_vercel_cron(self):
        self.assertNotIn("website_traffic", WARM_SRC)
        self.assertNotIn("website_traffic", VERCEL_TEXT)
        self.assertIn("Meta is not wired", PAGE_SRC)
        self.assertIn("do_not_invent_meta_spend", METRIC_SRC)
        self.assertNotIn(".stream(", inspect.getsource(traffic.read_daily_docs))

    def test_exclude_list_is_documented(self):
        for token in EXCLUDE_TOKENS:
            self.assertIn(token, PAGE_SRC)
        self.assertIn("Hawkstone", METRIC_SRC)

    def test_instant_form_3pl_are_not_website_leads(self):
        self.assertIn("Instant Form / 3PL are NOT website leads", PAGE_SRC)
        self.assertIn("Form freeze", PAGE_SRC)
        self.assertFalse(traffic.compute_website_traffic(None, fetch_remote=False)["filters"]["instant_form_3pl_are_website_leads"])

    def test_funnel_top_is_not_all_site_sessions(self):
        html = page.render_html()
        self.assertNotIn('<div class="name">Visits</div>', html)
        self.assertIn("Funnel step 1", html)
        self.assertIn("Dual top — not funnel step 1", html)


class WebsiteTrafficFunnelTopTests(unittest.TestCase):
    def test_funnel_top_is_estimate_lp_not_all_site(self):
        payload = live_payload()
        funnel = payload["funnel"]
        self.assertEqual(funnel["brand_site_sessions"], 80)
        self.assertEqual(funnel["estimate_lp_visits"], 30)
        self.assertEqual(funnel["all_site_sessions"], 110)
        self.assertEqual(funnel["funnel_top"], 30)
        self.assertNotEqual(funnel["funnel_top"], funnel["all_site_sessions"])
        self.assertFalse(funnel["funnel_top_is_all_site"])
        self.assertEqual(payload["overview"]["brand_site_sessions"], 80)
        self.assertEqual(payload["overview"]["estimate_calc_sessions"], 30)
        self.assertIn("overview_brand_vs_estimate", payload["live_fields"])
        self.assertEqual(payload["tiles"]["overview_brand_vs_estimate"]["status"], "live")

    def test_warehouse_fallback_still_splits_brand_from_wny(self):
        payload = live_payload(ga4_paths={"ga4": "not_configured", "rows": []})
        funnel = payload["funnel"]
        self.assertEqual(funnel["brand_site_sessions"], 100)
        self.assertEqual(funnel["estimate_lp_visits"], 10)
        self.assertEqual(funnel["all_site_sessions"], 110)
        self.assertNotEqual(funnel["funnel_top"], funnel["all_site_sessions"])

    def test_alert_uses_estimate_lp_not_all_site(self):
        leak = live_payload(
            daily_docs=[
                {
                    "date": "2026-09-07",
                    "ga4": "ok",
                    "visits_total": 80,
                    "visits_wny": 9,
                    "starts": 0,
                    "address_complete": 0,
                    "bill_complete": 0,
                    "estimate_submit": 0,
                    "cta_clicks": 0,
                }
            ],
            ga4_paths={
                "ga4": "ok",
                "rows": [
                    {"host_name": "www.happyslr.com", "page_path": "/", "count": 80},
                    {"host_name": "wny.happyslr.com", "page_path": "/calculator", "count": 9},
                ],
            },
        )
        self.assertTrue(leak["funnel"]["alert_visits_up_starts_zero"])
        quiet = live_payload(
            daily_docs=[
                {
                    "date": "2026-09-07",
                    "ga4": "ok",
                    "visits_total": 80,
                    "visits_wny": 0,
                    "starts": 0,
                    "address_complete": 0,
                    "bill_complete": 0,
                    "estimate_submit": 0,
                    "cta_clicks": 0,
                }
            ],
            ga4_paths={
                "ga4": "ok",
                "rows": [{"host_name": "www.happyslr.com", "page_path": "/", "count": 80}],
            },
        )
        self.assertEqual(quiet["funnel"]["all_site_sessions"], 80)
        self.assertEqual(quiet["funnel"]["estimate_lp_visits"], 0)
        self.assertFalse(quiet["funnel"]["alert_visits_up_starts_zero"])

    def test_submit_is_estimate_submit_not_wix_or_instant_form(self):
        payload = live_payload()
        self.assertEqual(payload["funnel"]["submit"], 2)
        self.assertNotEqual(payload["funnel"]["submit"], 6)
        self.assertIsNone(payload["funnel"]["contact"])
        self.assertEqual(payload["tiles"]["contact_step"]["status"], "example")


class WebsiteTrafficExclusionTests(unittest.TestCase):
    def test_host_debug_internal_and_test_rows_drop(self):
        out = traffic.summarize_path_rows(sample_path_rows(), test_filter=True)
        self.assertEqual(out["brand_site_sessions"], 80)
        self.assertEqual(out["estimate_lp_visits"], 30)
        self.assertGreater(out["dropped"]["host"], 0)
        self.assertGreater(out["dropped"]["internal"], 0)
        preview = traffic.summarize_path_rows(
            [
                {
                    "host_name": "happy-solar-git-qa.vercel.app",
                    "page_path": "/estimate",
                    "count": 12,
                }
            ],
            test_filter=True,
        )
        self.assertEqual(preview["estimate_lp_visits"], 0)
        self.assertEqual(preview["dropped"]["host"], 12)

    def test_named_fill_test_emails_excluded_when_filter_on(self):
        on = traffic.aggregate_named_fills(sample_fills(), test_filter=True)
        off = traffic.aggregate_named_fills(sample_fills(), test_filter=False)
        self.assertEqual(on["live_count"], 2)
        self.assertEqual(on["excluded_count"], 2)
        self.assertEqual(off["live_count"], 4)
        self.assertEqual(off["excluded_count"], 0)
        payload = live_payload(test_filter=True)
        self.assertEqual(payload["named_fills"]["live_count"], 2)
        self.assertEqual(payload["named_fills"]["excluded_count"], 2)
        blob = json.dumps(payload["named_fills"])
        self.assertNotIn("adchday@gmail.com", blob)
        self.assertNotIn("evanrday23@gmail.com", blob)
        self.assertNotIn("pyrce@verizon.net", blob)
        self.assertTrue(payload["named_fills"]["pii_gated"])
        self.assertTrue(traffic.named_fill_payload_is_clean(payload))


class WebsiteTrafficJsonFieldTests(unittest.TestCase):
    def test_live_and_stub_fields(self):
        payload = live_payload()
        self.assertFalse(payload["stub"])
        self.assertIn("live_fields", payload)
        self.assertIn("stub_fields", payload)
        for name in ("overview", "overview_brand_vs_estimate", "acquisition", "funnel", "named_fills"):
            self.assertEqual(payload["tiles"][name]["status"], "live", name)
            self.assertIn(name, payload["live_fields"])
        self.assertEqual(payload["tiles"]["meta_spend"]["status"], "not_wired")
        self.assertEqual(payload["tiles"]["audience"]["status"], "example")
        self.assertEqual(payload["tiles"]["paid_mismatch"]["status"], "example")
        self.assertIn("meta_spend", payload["stub_fields"])
        self.assertIn("audience", payload["stub_fields"])
        self.assertEqual(payload["overview"]["cta_taps"], 6)
        self.assertEqual(payload["tiles"]["cta_taps"]["status"], "live")
        self.assertEqual(payload["overview"]["fb_organic_sessions"], 8)
        self.assertEqual(payload["tiles"]["fb_post_sessions"]["status"], "live")
        self.assertEqual(payload["acquisition"]["fb_paid"], 12)
        self.assertEqual(payload["acquisition"]["fb_organic"], 8)

    def test_empty_sources_are_stub_not_invented(self):
        payload = traffic.compute_website_traffic(
            None, start="2026-09-07", end="2026-09-08", fetch_remote=False
        )
        self.assertTrue(payload["stub"])
        self.assertTrue(payload["example"])
        self.assertIsNone(payload["overview"]["brand_site_sessions"])
        self.assertIsNone(payload["funnel"]["estimate_lp_visits"])
        self.assertIsNone(payload["named_fills"]["live_count"])
        self.assertEqual(payload["tiles"]["meta_spend"]["status"], "not_wired")
        self.assertNotIn("spend", payload.get("overview", {}))

    def test_visit_bucket_helpers(self):
        self.assertTrue(traffic.is_estimate_lp_path("/estimate"))
        self.assertTrue(traffic.is_estimate_lp_path("/calculator"))
        self.assertFalse(traffic.is_estimate_lp_path("/"))
        self.assertFalse(traffic.is_estimate_lp_path("/buffalo"))
        self.assertEqual(traffic.visit_bucket("www.happyslr.com", "/"), "brand")
        self.assertEqual(traffic.visit_bucket("www.happyslr.com", "/estimate"), "estimate_lp")
        self.assertEqual(traffic.visit_bucket("wny.happyslr.com", "/"), "estimate_lp")
        self.assertIsNone(traffic.visit_bucket("yadmada.com", "/estimate"))
        self.assertFalse(traffic.visits_up_starts_zero(0, 0))
        self.assertTrue(traffic.visits_up_starts_zero(4, 0))
        self.assertFalse(traffic.visits_up_starts_zero(4, 1))


class WebsiteTrafficHandlerTests(unittest.TestCase):
    def test_html_default_and_json_live_stub_fields(self):
        captured, raw = invoke_get("/api/website_traffic")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Content-Type"], "text/html; charset=utf-8")
        html = raw.decode("utf-8")
        self.assertIn("Overview", html)
        self.assertIn("EXAMPLE", html)
        self.assertIn("live_fields", html)

        captured, raw = invoke_get("/api/website_traffic?format=json")
        self.assertEqual(captured["code"], 200)
        self.assertEqual(captured["headers"]["Content-Type"], "application/json")
        body = json.loads(raw.decode("utf-8"))
        self.assertIn("tiles", body)
        self.assertIn("live_fields", body)
        self.assertIn("stub_fields", body)
        self.assertIn("overview", body)
        self.assertIn("funnel", body)
        self.assertIn("named_fills", body)
        self.assertEqual(body["tiles"]["meta_spend"]["status"], "not_wired")
        self.assertFalse(body["funnel"]["funnel_top_is_all_site"])

    def test_dispatch_resolves_website_traffic(self):
        self.assertEqual(index.dispatch_route("/api/website_traffic"), "website_traffic")
        self.assertEqual(
            index.dispatch_file("website_traffic"), API / "website_traffic.py"
        )
        self.assertEqual(
            index.dispatch_route("/api", "hs=website_traffic&format=json"),
            "website_traffic",
        )


def _stub_funnel_without_exclusion_reason():
    def classify_host(host_name):
        text = " ".join(str(host_name or "").split()).casefold()
        if text in {"www.happyslr.com", "happyslr.com"}:
            return "total"
        if text == "wny.happyslr.com":
            return "wny"
        return "excluded"

    stub = types.ModuleType("hs_website_funnel_metric_incomplete")
    stub.classify_host = classify_host
    stub.compact_str = lambda value: " ".join(str(value or "").split())
    return stub


class WebsiteTrafficRaceDegradeTests(unittest.TestCase):
    def tearDown(self):
        traffic._FUNNEL = None
        traffic._TEST = None
        sys.modules.pop("hs_website_funnel_metric", None)
        traffic.funnel_mod()

    def test_incomplete_module_in_sys_modules_recovers(self):
        incomplete = types.ModuleType("hs_website_funnel_metric")
        self.assertFalse(hasattr(incomplete, "exclusion_reason"))
        traffic._FUNNEL = None
        sys.modules["hs_website_funnel_metric"] = incomplete
        loaded = traffic._load_module(
            "hs_website_funnel_metric", METRICS / "website_funnel.py"
        )
        self.assertIsNot(loaded, incomplete)
        self.assertTrue(callable(getattr(loaded, "exclusion_reason", None)))

        traffic._FUNNEL = None
        sys.modules["hs_website_funnel_metric"] = types.ModuleType("hs_website_funnel_metric")
        funnel = traffic.funnel_mod()
        self.assertTrue(callable(funnel.exclusion_reason))
        self.assertIsNot(funnel, sys.modules.get("hs_website_funnel_metric_incomplete"))

        out = traffic.summarize_path_rows(sample_path_rows(), test_filter=True)
        self.assertEqual(out["brand_site_sessions"], 80)
        self.assertEqual(out["estimate_lp_visits"], 30)
        self.assertGreater(out["dropped"]["host"], 0)

    def test_summarize_path_rows_missing_exclusion_reason_does_not_raise(self):
        broken = _stub_funnel_without_exclusion_reason()
        orig = traffic.funnel_mod
        traffic.funnel_mod = lambda: broken
        try:
            out = traffic.summarize_path_rows(sample_path_rows(), test_filter=True)
        finally:
            traffic.funnel_mod = orig
        self.assertNotIn("exclusion_reason", dir(broken))
        self.assertEqual(out["dropped"].get("host"), 999)
        self.assertLess(out["brand_site_sessions"] + out["estimate_lp_visits"], 999)
        self.assertGreater(out["brand_site_sessions"], 0)

    def test_html_handler_returns_200_when_exclusion_reason_attributeerror(self):
        err = AttributeError(
            "module 'hs_website_funnel_metric' has no attribute 'exclusion_reason'"
        )
        orig = page.build_payload

        def boom(qs=None, now=None):
            raise err

        page.build_payload = boom
        try:
            captured, raw = invoke_get("/api/website_traffic")
        finally:
            page.build_payload = orig
        self.assertEqual(captured["code"], 200)
        self.assertNotEqual(captured["code"], 500)
        self.assertIn("text/html", captured["headers"]["Content-Type"])
        html = raw.decode("utf-8")
        markup = html.split("var initialPayload")[0]
        self.assertIn("EXAMPLE", markup)
        self.assertIn("EXAMPLE DATA", markup)
        self.assertNotIn("500", str(captured["code"]))

        page.build_payload = boom
        try:
            captured_json, raw_json = invoke_get("/api/website_traffic?format=json")
        finally:
            page.build_payload = orig
        self.assertEqual(captured_json["code"], 200)
        body = json.loads(raw_json.decode("utf-8"))
        self.assertTrue(body.get("example") or body.get("stub"))
        self.assertIn("exclusion_reason", str(body.get("error") or body.get("notes") or ""))


class WebsiteTrafficChartTests(unittest.TestCase):
    def test_series_prefers_ga4_path_split_not_visits_wny(self):
        payload = live_payload(
            ga4_paths={"ga4": "ok", "rows": sample_dated_path_rows()},
            compare_prior=True,
        )
        self.assertEqual(payload["series"]["source"], "ga4_page_path")
        daily = payload["series"]["daily"]
        self.assertEqual(daily[0]["date"], "2026-09-07")
        self.assertEqual(daily[0]["estimate_lp_visits"], 30)
        self.assertEqual(daily[0]["brand_site_sessions"], 70)
        self.assertEqual(daily[0]["sessions"], 100)
        self.assertNotEqual(daily[0]["estimate_lp_visits"], 9)
        self.assertEqual(daily[1]["estimate_lp_visits"], 5)
        self.assertEqual(daily[1]["sessions"], 15)
        self.assertEqual(payload["funnel"]["estimate_lp_visits"], 35)
        self.assertEqual(payload["funnel"]["brand_site_sessions"], 80)
        self.assertFalse(payload["funnel"]["funnel_top_is_all_site"])
        prior = payload["series"]["prior_daily"]
        self.assertEqual(prior[0]["date"], "2026-09-05")
        self.assertIsNone(prior[0]["estimate_lp_visits"])
        self.assertEqual(prior[-1]["date"], "2026-09-06")
        # prior 2026-08-31 is outside this prior window; no invented overlay
        self.assertFalse(any(row.get("estimate_lp_visits") == 8 for row in prior))

    def test_series_from_warehouse_days_not_invented_zeros(self):
        payload = live_payload(end="2026-09-09")
        daily = payload["series"]["daily"]
        self.assertEqual(payload["series"]["source"], "warehouse")
        self.assertEqual([row["date"] for row in daily], ["2026-09-07", "2026-09-08", "2026-09-09"])
        self.assertEqual(daily[0]["sessions"], 89)
        self.assertEqual(daily[0]["estimate_lp_visits"], 9)
        self.assertEqual(daily[0]["brand_site_sessions"], 80)
        self.assertEqual(daily[1]["sessions"], 21)
        self.assertEqual(daily[1]["estimate_lp_visits"], 1)
        self.assertIsNone(daily[2]["sessions"])
        self.assertIsNone(daily[2]["estimate_lp_visits"])
        self.assertNotEqual(daily[2]["sessions"], 0)
        self.assertFalse(payload["funnel"]["funnel_top_is_all_site"])

    def test_prior_series_only_when_docs_exist(self):
        prior = [
            {
                "date": "2026-09-05",
                "ga4": "ok",
                "visits_total": 40,
                "visits_wny": 4,
                "starts": 1,
                "address_complete": 1,
                "bill_complete": 1,
                "estimate_submit": 0,
                "cta_clicks": 0,
            }
        ]
        on = live_payload(prior_docs=prior, compare_prior=True)
        self.assertEqual(len(on["series"]["prior_daily"]), 2)
        self.assertEqual(on["series"]["prior_daily"][0]["sessions"], 44)
        self.assertEqual(on["series"]["prior_daily"][0]["estimate_lp_visits"], 4)
        self.assertIsNone(on["series"]["prior_daily"][1]["sessions"])
        off = live_payload(prior_docs=prior, compare_prior=False)
        self.assertEqual(off["series"]["prior_daily"], [])

    def test_ga4_not_ok_day_is_gap_not_zero(self):
        payload = live_payload(
            daily_docs=[
                {
                    "date": "2026-09-07",
                    "ga4": "not_configured",
                    "visits_total": 80,
                    "visits_wny": 9,
                },
                sample_docs()[1],
            ]
        )
        daily = payload["series"]["daily"]
        self.assertIsNone(daily[0]["sessions"])
        self.assertIsNone(daily[0]["estimate_lp_visits"])
        self.assertEqual(daily[1]["sessions"], 21)

    def test_funnel_and_acquisition_series_are_live_counts(self):
        payload = live_payload()
        steps = payload["series"]["funnel"]
        keys = [row["key"] for row in steps]
        self.assertEqual(
            keys,
            ["estimate_lp", "start", "address", "bill", "contact", "submit", "named_fill"],
        )
        self.assertEqual(steps[0]["value"], 30)
        self.assertNotEqual(steps[0]["value"], payload["funnel"]["all_site_sessions"])
        contact = next(row for row in steps if row["key"] == "contact")
        self.assertFalse(contact["wired"])
        self.assertIsNone(contact["value"])
        self.assertEqual(contact["status"], "example")
        acq = payload["series"]["acquisition"]
        self.assertEqual(acq[0]["label"], "google / organic")
        self.assertEqual(acq[0]["sessions"], 40)
        self.assertLessEqual(len(acq), 10)
        named = payload["series"]["named_fills_by_day"]
        self.assertEqual(named, payload["named_fills"]["by_day"])
        self.assertTrue(traffic.named_fill_payload_is_clean(payload))
        blob = json.dumps(payload["series"])
        self.assertNotIn("adchday@gmail.com", blob)
        self.assertNotIn("pyrce@verizon.net", blob)

    def test_example_tiles_do_not_invent_series(self):
        payload = traffic.compute_website_traffic(
            None, start="2026-09-07", end="2026-09-08", fetch_remote=False
        )
        series = payload["series"]
        self.assertEqual(series["daily"], [])
        self.assertEqual(series["prior_daily"], [])
        self.assertEqual(series["funnel"], [])
        self.assertEqual(series["acquisition"], [])
        self.assertEqual(series["named_fills_by_day"], [])
        self.assertIsNone(series["source"])
        html = page.render_html(payload=payload)
        markup = html.split("var initialPayload")[0]
        self.assertIn("EXAMPLE — no daily series", markup)
        self.assertIn("EXAMPLE — funnel chart waits on live counts", markup)
        self.assertIn("EXAMPLE — acquisition chart waits on live GA4 rows", markup)
        self.assertIn("EXAMPLE — named-fill chart waits on live warehouse counts", markup)
        self.assertNotIn("<td>89</td>", markup)
        self.assertNotIn("google / organic", markup)

    def test_html_first_paint_charts_use_fixture_series(self):
        payload = live_payload()
        html = page.render_html(payload=payload)
        markup = html.split("var initialPayload")[0]
        self.assertIn('aria-label="Daily sessions and estimate/LP trend"', markup)
        self.assertIn("<td>2026-09-07</td>", markup)
        self.assertIn("<td>89</td>", markup)
        self.assertIn("<td>9</td>", markup)
        self.assertIn("Estimate / LP visits", markup)
        self.assertIn("google / organic", markup)
        self.assertIn("2026-09-08", markup)
        funnel_bars = markup.split('id="funnelBars"', 1)[1].split('id="funnelChartBody"', 1)[0]
        self.assertIn("hbar-fill", funnel_bars)
        self.assertIn("Estimate / LP visits", funnel_bars)
        self.assertIn("EXAMPLE", funnel_bars)
        self.assertIn("Contact", funnel_bars)
        self.assertIn("—", funnel_bars)
        named_bars = markup.split('id="namedBars"', 1)[1].split('id="namedDayBody"', 1)[0]
        self.assertIn("2026-09-07", named_bars)
        self.assertNotIn("Phil Pyrce", named_bars)
        self.assertNotIn("@", named_bars)

    def test_json_handler_includes_series(self):
        captured, raw = invoke_get("/api/website_traffic?format=json")
        self.assertEqual(captured["code"], 200)
        body = json.loads(raw.decode("utf-8"))
        self.assertIn("series", body)
        self.assertEqual(body["series"]["funnel"], [])
        self.assertEqual(body["series"]["daily"], [])
        self.assertFalse(body["funnel"]["funnel_top_is_all_site"])


if __name__ == "__main__":
    unittest.main()
