# -*- coding: utf-8 -*-

"""JSON feed for /api/enerflo_installer.

Live Enerflo GETs only. No password gate. Customer names stay in the
response, so the body is private and not stored.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from enerflo_installer_client import (  # noqa: E402
    EnerfloError,
    fetch_installs,
    fetch_notes,
    fetch_users,
)
from enerflo_installer_logic import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    apply_install_details,
    classify,
    install_ids_to_fetch,
    iso_z,
)


def clock() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    if not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def hs_company_id() -> int:
    return _env_int("ENERFLO_COMPANY_ID", 8253)


def installer_company_id() -> int:
    return _env_int("ENERFLO_INSTALLER_COMPANY_ID", 8090)


def parse_days(path: str) -> int:
    raw = (parse_qs(urlparse(path).query).get("days") or [None])[0]
    if raw is None or str(raw).strip() == "":
        return DEFAULT_LOOKBACK_DAYS
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_LOOKBACK_DAYS
    if days < 1:
        return 1
    if days > 180:
        return 180
    return days


def send_json(handler: Any, status: int, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    # Notes include customer names. Do not store this response in a shared cache.
    handler.send_header("Cache-Control", "private, no-store")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = (os.environ.get("ENERFLO_API_KEY") or "").strip()
        if not key:
            send_json(self, 503, {"error": "enerflo_key_missing"})
            return
        days = parse_days(self.path)
        now = clock()
        created_after = iso_z(now - timedelta(days=days))
        try:
            notes = fetch_notes(key, created_after)
            users = fetch_users(key)
        except EnerfloError as exc:
            send_json(self, 502, {"error": "enerflo_unavailable", "detail": exc.detail})
            return
        except Exception:
            send_json(self, 502, {"error": "enerflo_unavailable", "detail": "notes: unavailable"})
            return
        try:
            payload = classify(
                notes,
                users,
                now,
                days=days,
                created_after=created_after,
                hs_company_id=hs_company_id(),
                installer_company_id=installer_company_id(),
            )
        except Exception:
            send_json(self, 502, {"error": "enerflo_unavailable", "detail": "notes: unavailable"})
            return
        try:
            installs, warnings = fetch_installs(key, install_ids_to_fetch(payload))
        except Exception:
            installs = {}
            warnings = [{"detail": "install: unavailable"}]
        apply_install_details(payload, installs, warnings)
        send_json(self, 200, payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
