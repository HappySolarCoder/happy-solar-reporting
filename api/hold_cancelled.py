# -*- coding: utf-8 -*-

"""Vercel Python function: /api/hold_cancelled

Hold / Cancelled board in the Operations Control shell. Phone numbers open
the GoHighLevel opportunity when the row has a location id and opportunity
id, otherwise the contact page. Safe to frame from bloom.happyslr.com.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from pm_pages import render_hold_cancelled_html, send_dashboard_html


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send_dashboard_html(self, render_hold_cancelled_html())
