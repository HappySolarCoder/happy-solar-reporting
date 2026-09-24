# -*- coding: utf-8 -*-

"""POST /api/private/fma_payroll_login — set the payroll cookie."""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

PRIVATE_DIR = Path(__file__).resolve().parent
if str(PRIVATE_DIR) not in sys.path:
    sys.path.insert(0, str(PRIVATE_DIR))

from payroll_gate import (
    access_decision,
    clear_cookie_header,
    const_eq,
    gate_secret,
    parse_password,
    read_body,
    send_json,
    set_cookie_header,
)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        secret = gate_secret()
        if not secret:
            send_json(self, 503, {"error": "unavailable"})
            return
        raw = read_body(self)
        password = parse_password(self, raw)
        if const_eq(password, secret):
            send_json(self, 200, {"ok": True}, [("Set-Cookie", set_cookie_header(secret))])
            return
        send_json(self, 401, {"error": "unauthorized"})

    def do_GET(self):
        decision = access_decision(self.headers)
        if decision == "unset":
            send_json(self, 503, {"error": "unavailable"})
            return
        if decision != "ok":
            send_json(self, 401, {"error": "unauthorized"})
            return
        send_json(self, 200, {"ok": True})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
