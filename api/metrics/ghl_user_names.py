# -*- coding: utf-8 -*-
"""Batched ghl_users_v2 name reads.

One `in` query per 30 ids, then a 60-second in-memory cache. Callers that
already missed roster and a document get_all must not fall back to one query
per user.
"""

from __future__ import annotations

import time
from typing import Any, Callable

_IN_CHUNK = 30
_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX = 16
_cache: dict[tuple, tuple[float, dict[str, str]]] = {}


def _cache_get(key: tuple) -> dict[str, str] | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored, value = hit
    if time.monotonic() - stored > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return dict(value)


def _cache_put(key: tuple, value: dict[str, str]) -> None:
    _cache[key] = (time.monotonic(), dict(value))
    if len(_cache) <= _CACHE_MAX:
        return
    oldest = min(_cache, key=lambda item: _cache[item][0])
    _cache.pop(oldest, None)


def _query_in(db, collection: str, field: str, values: list[str]):
    """One bounded `in` read per chunk. Firestore allows 30 values per query."""
    found = []
    for start in range(0, len(values), _IN_CHUNK):
        chunk = values[start : start + _IN_CHUNK]
        if not chunk:
            continue
        found.extend(db.collection(collection).where(field, "in", chunk).stream())
    return found


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def load_ghl_user_names(db, user_ids, name_from_doc: Callable[[dict], str | None], *, namespace: str) -> dict[str, str]:
    """id, userId, and document id to display name.

    Document get_all first, then `in` queries of 30 on id and userId for whoever
    is still missing. Repeated asks for the same ids reuse the short cache.
    The returned dict is a copy.
    """
    needed: list[str] = []
    seen: set[str] = set()
    for raw in user_ids:
        uid = _compact(raw)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        needed.append(uid)
    if not needed:
        return {}
    key = (namespace, tuple(sorted(needed)))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    found: dict[str, str] = {}

    def take(snap) -> None:
        data = snap.to_dict() or {}
        if not isinstance(data, dict):
            return
        name = _compact(name_from_doc(data))
        if not name:
            return
        for item in (
            _compact(data.get("id")),
            _compact(data.get("userId")),
            _compact(getattr(snap, "id", "")),
        ):
            if item:
                found[item] = name

    refs = [db.collection("ghl_users_v2").document(uid) for uid in needed]
    for start in range(0, len(refs), 300):
        for snap in db.get_all(refs[start : start + 300]):
            if getattr(snap, "exists", False):
                take(snap)
    for field in ("id", "userId"):
        pending = [uid for uid in needed if uid not in found]
        if not pending:
            break
        for snap in _query_in(db, "ghl_users_v2", field, pending):
            take(snap)
    _cache_put(key, found)
    return dict(found)
