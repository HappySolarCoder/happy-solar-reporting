# -*- coding: utf-8 -*-

"""Enerflo GET client for installer tags.

In-process TTL caches, a process-wide rate limit, and bounded install lookups.
This module has no HTTP handler.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.request import Request, urlopen

BASE = "https://enerflo.io/api"
NOTES_URL = BASE + "/v3/installs/notes"
USERS_URL = BASE + "/v3/users"
INSTALL_URL = BASE + "/v3/installs/{install_id}"

REQUEST_TIMEOUT = 10
NOTES_PAGE_SIZE = 100
USERS_PAGE_SIZE = 100
USERS_TTL = 24 * 60 * 60
INSTALL_TTL = 6 * 60 * 60
MAX_WORKERS = 4
MIN_INTERVAL = 0.25
INSTALL_BUDGET_S = 8.0
_MAX_PAGES = 20

_users_lock = threading.Lock()
_users_cache: dict = {"expires": 0.0, "value": None}
_install_lock = threading.Lock()
_install_cache: dict[int, dict] = {}
_rate_lock = threading.Lock()
_next_allowed = 0.0


class EnerfloError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def clear_caches() -> None:
    global _next_allowed
    with _users_lock:
        _users_cache["expires"] = 0.0
        _users_cache["value"] = None
    with _install_lock:
        _install_cache.clear()
    with _rate_lock:
        _next_allowed = 0.0


def _acquire() -> None:
    global _next_allowed
    with _rate_lock:
        now = time.monotonic()
        wait_for = _next_allowed - now
        if wait_for < 0:
            wait_for = 0.0
        scheduled = now if wait_for == 0 else _next_allowed
        _next_allowed = scheduled + MIN_INTERVAL
    if wait_for:
        time.sleep(wait_for)


def _retry_delay(exc: urllib.error.HTTPError) -> float:
    header = ""
    headers = getattr(exc, "headers", None)
    if headers is not None:
        try:
            header = headers.get("Retry-After") or ""
        except Exception:
            header = ""
    try:
        delay = float(str(header).strip())
    except (TypeError, ValueError):
        delay = 1.0
    if delay < 0:
        delay = 0.0
    if delay > 5:
        delay = 5.0
    return delay


def _get_json(url: str, api_key: str, what: str, *, retried: bool = False) -> dict:
    _acquire()
    req = Request(
        url,
        headers={"api-key": api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if getattr(exc, "code", None) == 429 and not retried:
            time.sleep(_retry_delay(exc))
            return _get_json(url, api_key, what, retried=True)
        code = getattr(exc, "code", "error")
        raise EnerfloError(f"{what}: HTTP {code}") from None
    except urllib.error.URLError:
        raise EnerfloError(f"{what}: timeout") from None
    try:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw or "")
        parsed = json.loads(text) if text else {}
    except (json.JSONDecodeError, UnicodeError):
        raise EnerfloError(f"{what}: bad JSON") from None
    if not isinstance(parsed, dict):
        raise EnerfloError(f"{what}: bad JSON")
    if parsed.get("success") is False:
        raise EnerfloError(f"{what}: HTTP 200")
    return parsed


def _list_from(payload: dict, keys: tuple[str, ...]) -> list | None:
    for key in keys:
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return candidate
    return None


def _collect_pages(api_key: str, url_for_page, what: str, keys: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        payload = _get_json(url_for_page(page), api_key, what)
        batch = _list_from(payload, keys)
        if not batch:
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        try:
            total_pages = int(payload.get("totalPages") or 1)
        except (TypeError, ValueError):
            total_pages = 1
        if page >= max(total_pages, 1):
            break
        page += 1
    return rows


def fetch_notes(api_key: str, created_after: str) -> list[dict]:
    def url_for_page(page: int) -> str:
        query = urllib.parse.urlencode(
            {
                "page": page,
                "pageSize": NOTES_PAGE_SIZE,
                "created_after": created_after,
                "orderDir": "asc",
            }
        )
        return f"{NOTES_URL}?{query}"

    return _collect_pages(api_key, url_for_page, "notes", ("notes",))


def _slim_user(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "first_name": raw.get("first_name") or "",
        "last_name": raw.get("last_name") or "",
        "company_id": raw.get("company_id"),
        "active": raw.get("active"),
    }


def fetch_users(api_key: str) -> list[dict]:
    now = time.monotonic()
    with _users_lock:
        cached = _users_cache.get("value")
        expires = float(_users_cache.get("expires") or 0)
        if cached is not None and expires > now:
            return cached

    def url_for_page(page: int) -> str:
        query = urllib.parse.urlencode({"pageSize": USERS_PAGE_SIZE, "page": page})
        return f"{USERS_URL}?{query}"

    rows = _collect_pages(api_key, url_for_page, "users", ("results", "users", "data"))
    slim = [_slim_user(row) for row in rows]
    with _users_lock:
        _users_cache["value"] = slim
        _users_cache["expires"] = time.monotonic() + USERS_TTL
    return slim


def slim_install(payload: dict) -> dict:
    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    agent = payload.get("agent_user") if isinstance(payload.get("agent_user"), dict) else {}
    milestone = payload.get("current_milestone") if isinstance(payload.get("current_milestone"), dict) else {}
    rep = str(agent.get("name") or "").strip()
    if not rep:
        first = str(agent.get("first_name") or "").strip()
        last = str(agent.get("last_name") or "").strip()
        rep = " ".join(part for part in (first, last) if part)
    return {
        "customer_name": str(customer.get("name") or "").strip(),
        "rep_name": rep,
        "rep_id": agent.get("id"),
        "status": str(payload.get("status_name") or "").strip(),
        "milestone": str(milestone.get("title") or "").strip(),
    }


def _fetch_one_install(api_key: str, install_id: int) -> dict:
    url = INSTALL_URL.format(install_id=int(install_id))
    payload = _get_json(url, api_key, "install")
    return slim_install(payload)


def _store_install(install_id: int, value: dict) -> None:
    with _install_lock:
        _install_cache[install_id] = {"expires": time.monotonic() + INSTALL_TTL, "value": value}


def fetch_installs(api_key: str, install_ids: list) -> tuple[dict[int, dict], list[dict]]:
    results: dict[int, dict] = {}
    warnings: list[dict] = []
    missing: list[int] = []
    seen: set[int] = set()
    now = time.monotonic()
    with _install_lock:
        for raw in install_ids:
            try:
                install_id = int(raw)
            except (TypeError, ValueError):
                continue
            if install_id in seen:
                continue
            seen.add(install_id)
            cached = _install_cache.get(install_id)
            if cached and float(cached.get("expires") or 0) > now:
                results[install_id] = cached["value"]
            else:
                missing.append(install_id)
    if not missing:
        return results, warnings

    deadline = time.monotonic() + INSTALL_BUDGET_S
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    in_flight: dict = {}
    pending = list(missing)
    try:
        while pending or in_flight:
            while pending and len(in_flight) < MAX_WORKERS and time.monotonic() < deadline:
                install_id = pending.pop(0)
                in_flight[pool.submit(_fetch_one_install, api_key, install_id)] = install_id
            if not in_flight:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, _still = wait(set(in_flight), timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                install_id = in_flight.pop(future)
                try:
                    value = future.result()
                except EnerfloError as exc:
                    warnings.append({"install_id": install_id, "detail": exc.detail})
                    continue
                except Exception:
                    warnings.append({"install_id": install_id, "detail": "install: unavailable"})
                    continue
                results[install_id] = value
                _store_install(install_id, value)
        for future, install_id in list(in_flight.items()):
            future.cancel()
            warnings.append({"install_id": install_id, "detail": "install: budget"})
        for install_id in pending:
            warnings.append({"install_id": install_id, "detail": "install: budget"})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results, warnings
