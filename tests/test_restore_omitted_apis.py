# -*- coding: utf-8 -*-

"""Restore omitted Vercel /api handlers via /api dispatch. No new contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))


def load_index():
    spec = importlib.util.spec_from_file_location("hs_index_restore", API / "index.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index = load_index()
VERCEL = json.loads((ROOT / "vercel.json").read_text())


class RestoreDispatchTests(unittest.TestCase):
    def test_charles_funnel_and_cac_routes_resolve_to_existing_handlers(self):
        expected = {
            "/api/web_funnel_rollup?date=2026-08-25": (
                "web_funnel_rollup",
                API / "web_funnel_rollup.py",
            ),
            "/api/website_funnel_yesterday": (
                "website_funnel_yesterday",
                API / "website_funnel_yesterday.py",
            ),
            "/api/website_funnel?format=json": (
                "website_funnel",
                API / "website_funnel.py",
            ),
            "/api/inbound_cac": ("inbound_cac", API / "inbound_cac.py"),
            "/api/metrics/inbound_cac?timeframe=ytd": (
                "metrics/inbound_cac",
                API / "metrics" / "inbound_cac.py",
            ),
            "/api?hs=web_funnel_rollup&date=2026-08-25": (
                "web_funnel_rollup",
                API / "web_funnel_rollup.py",
            ),
            "/api?hs=metrics/inbound_cac&timeframe=ytd": (
                "metrics/inbound_cac",
                API / "metrics" / "inbound_cac.py",
            ),
        }
        for path, (route, file_path) in expected.items():
            resolved = index.dispatch_route(path)
            self.assertEqual(resolved, route, path)
            self.assertEqual(index.dispatch_file(resolved), file_path)
            self.assertTrue(file_path.is_file())
            module = index._load_api_module(file_path)
            self.assertIsNotNone(index._handler_class(module), file_path.name)

    def test_qa_root_and_helpers_are_not_dispatched(self):
        self.assertIsNone(index.dispatch_route("/api"))
        self.assertIsNone(index.dispatch_route("/api?format=json"))
        self.assertIsNone(index.dispatch_route("/api/index"))
        self.assertIsNone(index.dispatch_file("../secrets"))
        self.assertIsNone(index.dispatch_file("/etc/passwd"))
        nav = index._load_api_module(API / "dashboard_nav.py")
        self.assertIsNone(index._handler_class(nav))
        sit = index._load_api_module(API / "metrics" / "sit_timestamp.py")
        self.assertIsNone(index._handler_class(sit))

    def test_delegate_rebuilds_original_path_without_hs(self):
        self.assertEqual(
            index.handler_path_for_delegate(
                "/api?hs=web_funnel_rollup&date=2026-08-25",
                "web_funnel_rollup",
            ),
            "/api/web_funnel_rollup?date=2026-08-25",
        )
        self.assertEqual(
            index.handler_path_for_delegate(
                "/api?hs=website_funnel&format=json",
                "website_funnel",
            ),
            "/api/website_funnel?format=json",
        )
        self.assertEqual(
            index.handler_path_for_delegate(
                "/api?hs=metrics/inbound_cac&timeframe=ytd",
                "metrics/inbound_cac",
            ),
            "/api/metrics/inbound_cac?timeframe=ytd",
        )

    def test_delegate_invokes_existing_handler_do_get(self):
        called = {}
        funnel_mod = index._load_api_module(API / "web_funnel_rollup.py")
        orig = funnel_mod.handler.do_GET

        def _capture(self):
            called["path"] = self.path

        funnel_mod.handler.do_GET = _capture
        try:
            req = MagicMock()
            req.path = "/api?hs=web_funnel_rollup&date=2026-08-25"
            self.assertTrue(index.delegate_to_api_module(req, "web_funnel_rollup"))
            self.assertEqual(called["path"], "/api/web_funnel_rollup?date=2026-08-25")
        finally:
            funnel_mod.handler.do_GET = orig
            index._MODULE_CACHE.pop(str(API / "web_funnel_rollup.py"), None)


    def test_unknown_or_helper_route_is_not_a_handler_file(self):
        self.assertIsNone(index.dispatch_file("not_a_real_route"))
        self.assertFalse(index.delegate_to_api_module(MagicMock(path="/api?hs=dashboard_nav"), "dashboard_nav"))
        self.assertFalse(index.delegate_to_api_module(MagicMock(path="/api?hs=missing"), "missing"))


class RestoreConfigTests(unittest.TestCase):
    def test_rewrite_is_filesystem_fallback_and_cron_is_unchanged(self):
        rewrites = VERCEL.get("rewrites") or []
        self.assertEqual(len(rewrites), 1)
        self.assertEqual(rewrites[0]["source"], "/api/:path*")
        self.assertEqual(rewrites[0]["destination"], "/api?hs=:path*")
        crons = VERCEL.get("crons") or []
        self.assertEqual(len(crons), 1)
        self.assertEqual(crons[0]["path"], "/api/warm_cache")
        include = ((VERCEL.get("functions") or {}).get("api/index.py") or {}).get(
            "includeFiles"
        )
        self.assertEqual(include, "api/**")
        vercel_text = (ROOT / "vercel.json").read_text()
        self.assertNotIn("web_funnel", vercel_text)
        self.assertNotIn("website_funnel", vercel_text)
        self.assertNotIn("website_funnel_yesterday", vercel_text)
        self.assertNotIn("inbound_cac", vercel_text)


if __name__ == "__main__":
    unittest.main()
