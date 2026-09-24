# -*- coding: utf-8 -*-

"""POST /api/private/fma_payroll_logout — clear the payroll cookie."""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

PRIVATE_DIR = Path(__file__).resolve().parent
if str(PRIVATE_DIR) not in sys.path:
    sys.path.insert(0, str(PRIVATE_DIR))

from payroll_gate import clear_cookie_header, send_body

PAGE = "/private/fma-payroll"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        send_body(
            self,
            303,
            "text/plain; charset=utf-8",
            b"",
            [("Set-Cookie", clear_cookie_header()), ("Location", PAGE)],
        )

    def do_GET(self):
        self.do_POST()

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
