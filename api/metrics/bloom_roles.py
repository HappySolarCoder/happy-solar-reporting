# -*- coding: utf-8 -*-

"""Bloom account names and roles, read-only.

The Mystery Trip board keeps only people who have a Bloom account with the
matching role (FMA path: fma, Closers path: closer, shown in Bloom as Solar
Consultant). This reads portal_users with one SELECT through the same Neon
HTTP path as bloom_goals. Demo accounts are left out. Only name and role are
returned: no email, phone, or other account fields.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_METRICS_DIR = Path(__file__).resolve().parent
if str(_METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(_METRICS_DIR))

from urllib.parse import urlparse
from urllib.request import Request, build_opener

from bloom_goals import _RefuseRedirect, database_url, rows_from_neon

BOARD_ROLES = ("fma", "closer")
ROLES_SQL = (
    "SELECT name, role FROM portal_users "
    "WHERE role IN ('fma', 'closer') AND COALESCE(is_demo, false) = false"
)


def parse_people(rows: list[dict]) -> list[dict]:
    people = []
    for row in rows:
        name = row.get("name")
        role = row.get("role")
        if not isinstance(name, str) or not name.strip() or role not in BOARD_ROLES:
            continue
        people.append({"name": name.strip(), "role": role})
    people.sort(key=lambda item: (item["role"], item["name"].lower()))
    return people


def read_bloom_roles(opener=None) -> dict:
    url = database_url()
    if not url:
        return {"available": False, "people": [], "blocker": "not_connected"}
    try:
        host = urlparse(url).hostname
        if not host:
            raise RuntimeError("database_url_host")
        request = Request(
            f"https://{host}/sql",
            data=json.dumps({"query": ROLES_SQL, "params": []}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Neon-Connection-String": url},
            method="POST",
        )
        open_fn = opener or build_opener(_RefuseRedirect).open
        with open_fn(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"available": True, "people": parse_people(rows_from_neon(payload))}
    except Exception as exc:
        return {"available": False, "people": [], "blocker": type(exc).__name__}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(read_bloom_roles()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
