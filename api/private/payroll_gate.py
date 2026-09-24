# -*- coding: utf-8 -*-

"""Shared password gate for /private/fma-payroll.

PAYROLL_GATE_SECRET is set on Vercel. This module never embeds a secret.
The cookie stores an HMAC of a fixed string, not the secret itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qs

COOKIE_NAME = "hs_payroll"
COOKIE_MAX_AGE = 12 * 60 * 60
HMAC_MESSAGE = b"hs-payroll-gate-v1"


def gate_secret() -> str:
    import os

    return os.environ.get("PAYROLL_GATE_SECRET") or ""


def cookie_token(secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), HMAC_MESSAGE, hashlib.sha256).hexdigest()


def const_eq(left: str, right: str) -> bool:
    try:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
    except Exception:
        return False


def _header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name)
    if value is None:
        return ""
    return str(value)


def cookie_from_headers(headers: Any, name: str = COOKIE_NAME) -> str:
    raw = _header(headers, "Cookie")
    if not raw:
        return ""
    for part in raw.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key.strip() == name:
            return value.strip()
    return ""


def access_decision(headers: Any) -> str:
    """Return ok, unset, or unauthorized. Unset never falls open."""
    secret = gate_secret()
    if not secret:
        return "unset"
    presented = _header(headers, "X-Payroll-Gate")
    if presented and const_eq(presented, secret):
        return "ok"
    cookie = cookie_from_headers(headers)
    if cookie and const_eq(cookie, cookie_token(secret)):
        return "ok"
    return "unauthorized"


def set_cookie_header(secret: str) -> str:
    token = cookie_token(secret)
    return (
        f"{COOKIE_NAME}={token}; HttpOnly; Secure; SameSite=Strict; "
        f"Path=/; Max-Age={COOKIE_MAX_AGE}"
    )


def clear_cookie_header() -> str:
    return f"{COOKIE_NAME}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0"


def read_body(handler: Any) -> bytes:
    try:
        length = int(_header(handler.headers, "Content-Length") or "0")
    except Exception:
        length = 0
    if length <= 0:
        return b""
    return handler.rfile.read(length)


def parse_password(handler: Any, raw: bytes) -> str:
    ctype = _header(handler.headers, "Content-Type").lower()
    if "application/json" in ctype:
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return ""
        if not isinstance(data, dict):
            return ""
        return str(data.get("password") or "")
    form = parse_qs(raw.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return str((form.get("password") or [""])[0])


def send_body(handler: Any, status: int, content_type: str, body: bytes, extra: list[tuple[str, str]] | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "private, no-store")
    handler.send_header("X-Robots-Tag", "noindex")
    for key, value in extra or []:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def send_json(handler: Any, status: int, payload: dict, extra: list[tuple[str, str]] | None = None) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    send_body(handler, status, "application/json; charset=utf-8", body, extra)


def send_html(handler: Any, status: int, html: str, extra: list[tuple[str, str]] | None = None) -> None:
    send_body(handler, status, "text/html; charset=utf-8", html.encode("utf-8"), extra)
