# -*- coding: utf-8 -*-
"""Appointment Outcomes logo is self-hosted; Website pages scroll tables inside cards on phone."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"


class AppointmentOutcomesLogoTests(unittest.TestCase):
    def test_logo_is_self_hosted(self):
        src = (API / "appointment_outcomes.py").read_text(encoding="utf-8")
        self.assertNotIn("zyrosite", src)
        self.assertIn('src=\\"/happy-solar-logo.png\\"', src)
        logo = ROOT / "public" / "happy-solar-logo.png"
        self.assertTrue(logo.is_file())
        self.assertEqual(logo.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


class WebsitePhoneOverflowTests(unittest.TestCase):
    def _assert_tables_wrapped(self, src: str):
        self.assertIn(".table-scroll {", src)
        self.assertIn(".grid > * { min-width:0; }", src)
        tables = re.findall(r"<table[ >]", src)
        wrapped = re.findall(r'<div class="table-scroll"><table[ >]', src)
        self.assertTrue(tables)
        self.assertEqual(len(tables), len(wrapped))

    def test_website_traffic_tables_scroll_in_place(self):
        src = (API / "website_traffic.py").read_text(encoding="utf-8")
        self._assert_tables_wrapped(src)
        self.assertIn('.filters input[type="date"] { min-width:0; max-width:100%; }', src)

    def test_website_funnel_tables_scroll_in_place(self):
        src = (API / "metrics" / "website_funnel.py").read_text(encoding="utf-8")
        self._assert_tables_wrapped(src)


if __name__ == "__main__":
    unittest.main()
