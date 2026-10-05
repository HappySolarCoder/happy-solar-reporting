# -*- coding: utf-8 -*-
"""Identity comes from the existing settings password gate. Usernames are not trusted."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass


SETTINGS_ADMIN_ROLE = "settings_admin"


@dataclass(frozen=True)
class Identity:
    actor_id: str
    role: str

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


def chat_allowed(identity: Identity | None, allowed_roles: frozenset[str]) -> bool:
    if identity is None:
        return False
    return identity.role in allowed_roles
