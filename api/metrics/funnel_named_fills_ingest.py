# -*- coding: utf-8 -*-
"""Standing ingest of leads@happyslr.com WNY calculator notifies.

Parse Label: value notify bodies and merge-write web_funnel_named_fills_v1.
Id {date}_{email_slug}. Bounded (limit 50). Fail closed without Gmail env.
Does not stream the collection. Isolated from CRM / sales.
ingest_leads_at(messages=) is for unit tests only. The public Vercel
handler is GET-only and must not accept POST writes.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_METRICS_DIR = Path(__file__).resolve().parent
if str(_METRICS_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_METRICS_DIR))

from funnel_test_address import NAMED_FILLS_COLLECTION

NY_TZ = ZoneInfo("America/New_York")
GMAIL_LIST_Q = 'from:leads@happyslr.com subject:"WNY solar lead" newer_than:{days}d'
GMAIL_MAX_RESULTS = 50
WRITE_LIMIT = 50
LABEL_RE = re.compile(r"^([^:]+):\s*(.*)$")
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

GMAIL_ACCESS_TOKEN_ENV = "GMAIL_ACCESS_TOKEN"
GMAIL_REFRESH_TOKEN_ENV = "GMAIL_REFRESH_TOKEN"
GMAIL_CLIENT_ID_ENV = "GMAIL_CLIENT_ID"
GMAIL_CLIENT_SECRET_ENV = "GMAIL_CLIENT_SECRET"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").split())


def parse_wny_calculator_notify(text: str | None) -> dict[str, Any] | None:
    """Read `Label: value` lines. Need at least an email."""
    if not text:
        return None
    fields: dict[str, str] = {}
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LABEL_RE.match(line)
        if not match:
            continue
        key = compact_str(match.group(1)).casefold()
        value = compact_str(match.group(2))
        if key:
            fields[key] = value
    email = compact_str(fields.get("email"))
    if not email or "@" not in email:
        return None
    first = compact_str(fields.get("first name"))
    last = compact_str(fields.get("last name"))
    name = compact_str(f"{first} {last}")
    return {
        "name": name,
        "email": email,
        "address": compact_str(fields.get("address")),
        "phone": compact_str(fields.get("phone")),
    }


def email_slug(email: str) -> str:
    """casefold, `@` and `.` -> `_`. adchday@gmail.com -> adchday_gmail_com."""
    text = compact_str(email).casefold()
    return text.replace("@", "_").replace(".", "_")


def named_fill_doc_id(date_ymd: str, email: str) -> str:
    return f"{compact_str(date_ymd)}_{email_slug(email)}"


def ny_date_from_received_at(received_at: Any) -> str | None:
    """America/New_York calendar day of received_at. Date-only strings are kept."""
    if received_at is None or received_at == "":
        return None
    if isinstance(received_at, datetime):
        dt = received_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(NY_TZ).date().isoformat()
    text = compact_str(received_at)
    if DATE_ONLY_RE.match(text):
        return text
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(NY_TZ).date().isoformat()


def _received_at_iso(received_at: Any) -> str | None:
    if received_at is None or received_at == "":
        return None
    if isinstance(received_at, datetime):
        dt = received_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return compact_str(received_at)


def fill_from_notify(text: str | None, received_at: Any = None) -> dict[str, Any] | None:
    parsed = parse_wny_calculator_notify(text)
    if not parsed:
        return None
    date_ymd = ny_date_from_received_at(received_at)
    return {
        "date": date_ymd,
        "name": parsed["name"],
        "email": parsed["email"],
        "address": parsed["address"],
        "phone": parsed["phone"],
        "source": "leads@",
        "received_at": _received_at_iso(received_at),
    }


def gmail_configured() -> bool:
    if compact_str(os.environ.get(GMAIL_ACCESS_TOKEN_ENV)):
        return True
    return bool(
        compact_str(os.environ.get(GMAIL_REFRESH_TOKEN_ENV))
        and compact_str(os.environ.get(GMAIL_CLIENT_ID_ENV))
        and compact_str(os.environ.get(GMAIL_CLIENT_SECRET_ENV))
    )


def gmail_access_token() -> str | None:
    direct = compact_str(os.environ.get(GMAIL_ACCESS_TOKEN_ENV))
    if direct:
        return direct
    refresh = compact_str(os.environ.get(GMAIL_REFRESH_TOKEN_ENV))
    client_id = compact_str(os.environ.get(GMAIL_CLIENT_ID_ENV))
    client_secret = compact_str(os.environ.get(GMAIL_CLIENT_SECRET_ENV))
    if not (refresh and client_id and client_secret):
        return None
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        token = compact_str(payload.get("access_token"))
        return token or None
    except Exception:
        return None


def _gmail_get(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def _extract_plain(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    mime = compact_str(payload.get("mimeType")).casefold()
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    data = compact_str((body or {}).get("data"))
    if mime.startswith("text/plain") and data:
        return _b64url_decode(data)
    for part in payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        found = _extract_plain(part)
        if found:
            return found
    return ""


def _header(message: dict[str, Any], name: str) -> str:
    want = name.casefold()
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    for header in payload.get("headers") or []:
        if not isinstance(header, dict):
            continue
        if compact_str(header.get("name")).casefold() == want:
            return compact_str(header.get("value"))
    return ""


def _internal_date_iso(internal_date: Any) -> str | None:
    if internal_date is None or internal_date == "":
        return None
    try:
        millis = int(internal_date)
        dt = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return compact_str(internal_date) or None


def fetch_leads_at_messages(newer_than_days: int = 2) -> list[dict[str, Any]]:
    """Gmail users/me/messages.list + get format=full. Fail closed to []."""
    token = gmail_access_token()
    if not token:
        return []
    try:
        days = int(newer_than_days or 2)
        query = GMAIL_LIST_Q.format(days=days)
        list_url = GMAIL_API + "?" + urllib.parse.urlencode(
            {"q": query, "maxResults": GMAIL_MAX_RESULTS}
        )
        listed = _gmail_get(list_url, token)
        out: list[dict[str, Any]] = []
        for item in (listed.get("messages") or [])[:GMAIL_MAX_RESULTS]:
            if not isinstance(item, dict):
                continue
            mid = compact_str(item.get("id"))
            if not mid:
                continue
            get_url = (
                GMAIL_API
                + "/"
                + urllib.parse.quote(mid, safe="")
                + "?"
                + urllib.parse.urlencode({"format": "full"})
            )
            full = _gmail_get(get_url, token)
            payload = full.get("payload") if isinstance(full.get("payload"), dict) else {}
            plaintext = _extract_plain(payload) or compact_str(full.get("snippet"))
            out.append(
                {
                    "plaintext": plaintext or "",
                    "received_at": _internal_date_iso(full.get("internalDate")),
                    "gmail_id": mid,
                    "subject": _header(full, "Subject"),
                }
            )
        return out
    except Exception:
        return []


def upsert_named_fills(db: Any, fills: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Merge-write each valid fill. Skip missing date or email. Limit 50."""
    wrote = 0
    skipped = 0
    ids: list[str] = []
    if db is None:
        return {"wrote": 0, "skipped": len(list(fills or [])), "ids": []}
    col = db.collection(NAMED_FILLS_COLLECTION)
    for fill in list(fills or [])[:WRITE_LIMIT]:
        if not isinstance(fill, dict):
            skipped += 1
            continue
        date_ymd = compact_str(fill.get("date"))
        email = compact_str(fill.get("email"))
        if not date_ymd or not email:
            skipped += 1
            continue
        doc_id = named_fill_doc_id(date_ymd, email)
        col.document(doc_id).set(fill, merge=True)
        wrote += 1
        ids.append(doc_id)
    return {"wrote": wrote, "skipped": skipped, "ids": ids}


def ingest_leads_at(
    db: Any,
    messages: list[dict[str, Any]] | None = None,
    date_ymd: str | None = None,
) -> dict[str, Any]:
    """Parse notifies and upsert. Fetch Gmail when configured; else fail closed.

    messages= is for unit tests only. Do not expose it on a public HTTP POST.
    """
    if messages is None:
        if not gmail_configured():
            return {
                "attempted": False,
                "wrote": 0,
                "skipped": 0,
                "ids": [],
                "reason": "gmail_not_configured",
            }
        messages = fetch_leads_at_messages(newer_than_days=2)
    fills: list[dict[str, Any]] = []
    skipped = 0
    date_key = compact_str(date_ymd) or None
    for msg in list(messages or [])[:WRITE_LIMIT]:
        if not isinstance(msg, dict):
            skipped += 1
            continue
        text = msg.get("plaintext")
        if text is None:
            text = msg.get("text")
        fill = fill_from_notify(text, received_at=msg.get("received_at"))
        if not fill:
            skipped += 1
            continue
        if date_key and compact_str(fill.get("date")) != date_key:
            continue
        fills.append(fill)
    result = upsert_named_fills(db, fills)
    result["attempted"] = True
    result["reason"] = None
    result["skipped"] = int(result.get("skipped") or 0) + skipped
    return result
