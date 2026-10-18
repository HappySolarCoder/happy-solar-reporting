# -*- coding: utf-8 -*-

"""Vercel Python function: /api/project_management_hub

Project Management hub in the Operations Control shell. Data:
/api/metrics/project_management. Safe to frame from bloom.happyslr.com.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from pm_pages import render_project_management_hub_html, send_dashboard_html


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send_dashboard_html(self, render_project_management_hub_html())
