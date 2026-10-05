# -*- coding: utf-8 -*-

"""Read path for Bloom company and territory goals.

Bloom stores those goals in the portal database
(portal_goal_documents, subjects scope:company and scope:territory:*),
behind a signed-in manager session on /api/goals and /api/account-goals.
This reporting app has no Bloom database credential, so it returns an
explicit unavailable payload instead of a guessed target.
"""

from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo


BLOCKER = (
    "Bloom company and territory sales goals, channel opportunity goals, "
    "and Demo % / Opp2Prelim targets live in HappySolarCoder/happy-solar-bloom-portal "
    "portal_goal_documents (scope:company and scope:territory:*). "
    "The Bloom routes /api/goals and /api/account-goals require a Bloom manager session. "
    "This reporting app has no Bloom database credential or service token, so those goals "
    "cannot be read from here."
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "available": False,
            "goals": None,
            "blocker": BLOCKER,
            "checked_at": datetime.now(ZoneInfo("America/New_York")).isoformat(),
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
