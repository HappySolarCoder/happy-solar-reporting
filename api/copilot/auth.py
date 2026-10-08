# -*- coding: utf-8 -*-
"""Chat identity from the settings password or a short-lived Bloom token.

The settings password is HTTP basic auth. The username is ignored, so that
path is always the actor settings_admin. Admin routes use only that path.

Bloom's session cookie is httpOnly and stays on the Bloom origin, so the
Company Overview iframe cannot see it. Bloom signs a short-lived token and
the iframe sends it as Authorization: Bearer. The JSON body cannot supply
user_id or role. A bearer token cannot become the settings admin actor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

SETTINGS_ADMIN_ROLE = "settings_admin"
BLOOM_ISSUER = "happy-solar-bloom"
BLOOM_AUDIENCE = "goose-copilot"
BLOOM_PORTAL_ROLES = frozenset({"fma", "closer", "coach", "manager", "inbound"})
BLOOM_TOKEN_MAX_SECONDS = 600
BLOOM_CLOCK_SKEW_SECONDS = 30
DEFAULT_BLOOM_ORIGIN = "https://happy-solar-bloom-portal.vercel.app"
_BLOOM_KEYS = frozenset({"aud", "exp", "iat", "iss", "role", "status", "sub", "v"})
_OPTIONAL_BLOOM_KEYS = frozenset({"name"})
_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


@dataclass(frozen=True)
class Identity:
    actor_id: str
    role: str
    display_name: str | None = None

    def as_dict(self) -> dict:
        return {"actor_id": self.actor_id, "role": self.role}


def _header(headers, name: str) -> str:
    if headers is None:
        return ""
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return "" if value is None else str(value)
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name)
    return "" if value is None else str(value)


def identity_from_headers(headers, *, settings_password: str | None = None) -> Identity | None:
    """Return the settings admin only when the shared settings password matches.

    The basic-auth username is ignored. Two different usernames with the same
    password are the same actor. A body field cannot supply this identity.
    Bearer tokens are ignored here so admin and the password gate stay separate.
    """
    password = settings_password if settings_password is not None else os.environ.get("SETTINGS_PASSWORD") or ""
    if not password:
        return None
    auth = _header(headers, "Authorization")
    if not auth.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        _user, presented = raw.split(":", 1)
    except Exception:
        return None
    if presented != password:
        return None
    return Identity(actor_id=SETTINGS_ADMIN_ROLE, role=SETTINGS_ADMIN_ROLE)


def bloom_parent_origins(raw: str | None = None) -> list[str]:
    """HTTPS origins allowed to hand Goose a Bloom token. No wildcards."""
    if raw is None:
        raw = os.environ.get("COPILOT_BLOOM_ORIGINS")
    if raw is None or not str(raw).strip():
        return [DEFAULT_BLOOM_ORIGIN]
    origins: list[str] = []
    for part in str(raw).split(","):
        origin = part.strip().rstrip("/")
        if not origin.startswith("https://") or "*" in origin or " " in origin:
            continue
        if origin not in origins:
            origins.append(origin)
    return origins or [DEFAULT_BLOOM_ORIGIN]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    if not text or len(text) > 4000:
        raise ValueError("token part length")
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _claim_keys_ok(keys: set) -> bool:
    if not _BLOOM_KEYS <= keys:
        return False
    return keys <= (_BLOOM_KEYS | _OPTIONAL_BLOOM_KEYS)


def _canonical_claims(claims: dict) -> bytes:
    if not _claim_keys_ok(set(claims)):
        raise ValueError("claims")
    return json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_bloom_token(claims: dict, secret: str) -> str:
    """Test and contract helper. Reporting does not expose a signing route."""
    if not secret:
        raise ValueError("secret")
    body = _canonical_claims(claims)
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return _b64url_encode(body) + "." + _b64url_encode(sig)


def verify_bloom_token(token: str, secret: str, now: datetime) -> dict | None:
    """Return signed claims when the HMAC, audience, lifetime, and role all match."""
    if not secret or not token or len(token) > 4000 or token.count(".") != 1:
        return None
    body_b64, sig_b64 = token.split(".", 1)
    try:
        body = _b64url_decode(body_b64)
        sig = _b64url_decode(sig_b64)
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        if len(sig) != len(expected) or not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not _claim_keys_ok(set(data)):
        return None
    if data.get("v") != 1 or data.get("iss") != BLOOM_ISSUER or data.get("aud") != BLOOM_AUDIENCE:
        return None
    if "name" in data:
        signed_name = data.get("name")
        if not isinstance(signed_name, str) or not signed_name.strip() or len(signed_name) > 80:
            return None
        if re.search(r"[\r\n\x00]", signed_name):
            return None
    if data.get("status") != "active" or data.get("role") not in BLOOM_PORTAL_ROLES:
        return None
    subject = data.get("sub")
    if not isinstance(subject, str) or _SUBJECT.match(subject) is None:
        return None
    if type(data.get("iat")) is not int or type(data.get("exp")) is not int:
        return None
    issued = data["iat"]
    expires = data["exp"]
    if expires <= issued or expires - issued > BLOOM_TOKEN_MAX_SECONDS:
        return None
    current = int(now.timestamp())
    if issued > current + BLOOM_CLOCK_SKEW_SECONDS:
        return None
    if current > expires + BLOOM_CLOCK_SKEW_SECONDS:
        return None
    return data


def _bloom_secret(token_secret: str | None) -> str:
    if token_secret is not None:
        return token_secret
    return os.environ.get("COPILOT_BLOOM_TOKEN_SECRET") or ""


def identity_from_bloom_bearer(
    headers,
    *,
    token_secret: str | None = None,
    now: datetime | None = None,
) -> Identity | None:
    """Identity from a Bloom bearer token. Role is the signed portal role.

    The actor id is the signed subject, prefixed so it cannot collide with
    settings_admin. The token cannot claim the settings_admin role.
    """
    auth = _header(headers, "Authorization")
    if not auth.startswith("Bearer "):
        return None
    presented = auth.split(" ", 1)[1].strip()
    if presented != auth.split(" ", 1)[1] or " " in presented:
        return None
    moment = now or datetime.now(timezone.utc)
    claims = verify_bloom_token(presented, _bloom_secret(token_secret), moment)
    if claims is None:
        return None
    signed_name = claims.get("name")
    display_name = str(signed_name).strip() if isinstance(signed_name, str) and signed_name.strip() else None
    return Identity(actor_id="bloom:" + claims["sub"], role=str(claims["role"]), display_name=display_name)


def identity_for_chat(
    headers,
    *,
    settings_password: str | None,
    allowed_roles: frozenset[str],
    token_secret: str | None = None,
    now: datetime | None = None,
) -> Identity | None:
    """Chat identity. Basic auth stays settings_admin. Bloom maps onto an allowed role.

    A verified portal role is kept when that role is already in
    COPILOT_ALLOWED_ROLES. Otherwise the employee is mapped to settings_admin
    when that role is the one this deployment already allows. No other role is
    invented, and the bearer path never replaces the admin actor id.
    """
    basic = identity_from_headers(headers, settings_password=settings_password)
    if basic is not None:
        if basic.role not in allowed_roles:
            return None
        return basic
    bloom = identity_from_bloom_bearer(headers, token_secret=token_secret, now=now)
    if bloom is None:
        return None
    if bloom.role in allowed_roles:
        return bloom
    if SETTINGS_ADMIN_ROLE in allowed_roles:
        return Identity(actor_id=bloom.actor_id, role=SETTINGS_ADMIN_ROLE)
    return None


def chat_allowed(identity: Identity | None, allowed_roles: frozenset[str]) -> bool:
    if identity is None:
        return False
    return identity.role in allowed_roles


def unauthorized_answer(
    headers,
    *,
    settings_password: str | None,
    allowed_roles: frozenset[str],
    token_secret: str | None = None,
    now: datetime | None = None,
) -> str:
    """Employee-facing copy when identity_for_chat refused the request.

    A verified bearer whose role is outside the allowed list is a role refusal.
    A bearer that was sent but does not verify is a bad or expired signature.
    Anything else never presented a usable credential.
    """
    from copilot.messages import EMPLOYEE_UNCONFIRMED, ROLE_NOT_AUTHORIZED, SESSION_EXPIRED

    moment = now or datetime.now(timezone.utc)
    auth = _header(headers, "Authorization")
    if auth.startswith("Bearer "):
        presented = auth.split(" ", 1)[1]
        if not presented.strip():
            return EMPLOYEE_UNCONFIRMED
        if presented != presented.strip() or " " in presented:
            return SESSION_EXPIRED
        claims = verify_bloom_token(presented, _bloom_secret(token_secret), moment)
        if claims is None:
            return SESSION_EXPIRED
        role = str(claims["role"])
        if role not in allowed_roles and SETTINGS_ADMIN_ROLE not in allowed_roles:
            return ROLE_NOT_AUTHORIZED
        return EMPLOYEE_UNCONFIRMED
    basic = identity_from_headers(headers, settings_password=settings_password)
    if basic is not None and basic.role not in allowed_roles:
        return ROLE_NOT_AUTHORIZED
    return EMPLOYEE_UNCONFIRMED
