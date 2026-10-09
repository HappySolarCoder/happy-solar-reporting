# -*- coding: utf-8 -*-
"""Estimate submits from the server-side lead record, on Evan's Phoenix day.

Evan 2026-10-09: "We shouldn't be having to check the inbox to know who
clicked submit on the form we built."

The marketing site (happy-solar-website src/lib/named-fill.ts) merge-writes
every live calculator submit to Firestore web_funnel_named_fills_v1 when it
sends the leads@ email. That collection is the submit record. GA4 is only
used for sessions / starts.

- Day = America/Phoenix calendar day (no DST, UTC-7), on received_at.
- One bounded range query on received_at (single-field index). Read-only.
- Dedupe: one submit per person per day (email, else leadId). A second
  create or an "UPDATE existing lead" refine does not count twice.
- Locked test traffic (Hawkstone, Stonebridge, Test Test, Evan Day, the two
  test emails) is excluded.
- On a store read failure the count is None, never invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

SUBMITS_TIMEZONE = "America/Phoenix"
PHX_TZ = ZoneInfo(SUBMITS_TIMEZONE)
SUBMITS_COLLECTION = "web_funnel_named_fills_v1"
SUBMITS_QUERY_LIMIT = 300
SUBMITS_SOURCE = "server_lead_store"


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def phoenix_now() -> datetime:
    return datetime.now(PHX_TZ)


def yesterday_phoenix_date() -> str:
    return (phoenix_now().date() - timedelta(days=1)).isoformat()


def resolve_phoenix_date(value: str | None) -> str:
    text = _compact(value).casefold()
    if not text or text == "yesterday":
        return yesterday_phoenix_date()
    try:
        y, m, d = [int(p) for p in text.split("-")]
        return datetime(y, m, d).date().isoformat()
    except Exception as exc:
        raise ValueError("Invalid date; expected YYYY-MM-DD or yesterday") from exc


def phoenix_day_window(date_ymd: str) -> dict[str, str]:
    y, m, d = [int(p) for p in date_ymd.split("-")]
    start = datetime(y, m, d, tzinfo=PHX_TZ)
    end = start + timedelta(days=1)
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    return {
        "start": start.isoformat(),
        "end": (end - timedelta(microseconds=1)).isoformat(),
        "timezone": SUBMITS_TIMEZONE,
        "kind": "calendar_day",
        # received_at is an ISO-8601 UTC string. Bounds omit the trailing Z so
        # "...T07:00:00.123Z" and "...T07:00:00Z" both sort inside the range.
        "query_start_utc": start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        "query_end_utc": end_utc.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def parse_received_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = _compact(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _range_query(db: Any, lo: str, hi: str):
    col = db.collection(SUBMITS_COLLECTION)
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = col.where(filter=FieldFilter("received_at", ">=", lo)).where(
            filter=FieldFilter("received_at", "<", hi)
        )
    except ImportError:
        query = col.where("received_at", ">=", lo).where("received_at", "<", hi)
    return query.limit(SUBMITS_QUERY_LIMIT)


def fetch_store_rows(db: Any, date_ymd: str) -> list[dict[str, Any]]:
    """Bounded received_at range read for one Phoenix day. Raises on failure."""
    window = phoenix_day_window(date_ymd)
    query = _range_query(db, window["query_start_utc"], window["query_end_utc"])
    rows: list[dict[str, Any]] = []
    for snap in query.get():
        data = snap.to_dict() if hasattr(snap, "to_dict") else snap
        if isinstance(data, dict) and data:
            rows.append(data)
    return rows


def dedupe_submits(
    rows: list[dict[str, Any]], date_ymd: str, is_test
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """One submit per person on the Phoenix day. Returns (submits, dropped)."""
    dropped = {"test": 0, "duplicate": 0, "outside_day": 0, "no_identity": 0}
    kept: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        received = parse_received_at(row.get("received_at"))
        if received is None or received.astimezone(PHX_TZ).date().isoformat() != date_ymd:
            dropped["outside_day"] += 1
            continue
        if is_test(row):
            dropped["test"] += 1
            continue
        email = _compact(row.get("email")).casefold()
        lead_id = _compact(row.get("leadId"))
        key = email or lead_id
        if not key:
            dropped["no_identity"] += 1
            continue
        prev = kept.get(key)
        if prev is not None:
            dropped["duplicate"] += 1
            if received >= prev["_received"]:
                continue
        kept[key] = {"_received": received, "leadId": lead_id or None}
    submits = [
        {
            "lead_id": item["leadId"],
            "received_at_phoenix": item["_received"].astimezone(PHX_TZ).isoformat(),
        }
        for item in sorted(kept.values(), key=lambda it: it["_received"])
    ]
    return submits, dropped


def count_estimate_submits(db: Any, date_ymd: str, is_test) -> dict[str, Any]:
    """Server-side submit count for one Phoenix day. count=None if the read fails."""
    window = phoenix_day_window(date_ymd)
    base = {
        "source": SUBMITS_SOURCE,
        "collection": SUBMITS_COLLECTION,
        "timezone": SUBMITS_TIMEZONE,
        "date": date_ymd,
        "window": {k: window[k] for k in ("start", "end", "timezone", "kind")},
        "dedupe": "one per person per day (email, else leadId); updates and repeat creates do not add",
    }
    try:
        rows = fetch_store_rows(db, date_ymd)
    except Exception as exc:
        return {**base, "ok": False, "count": None, "error": type(exc).__name__, "submits": []}
    submits, dropped = dedupe_submits(rows, date_ymd, is_test)
    return {
        **base,
        "ok": True,
        "count": len(submits),
        "rows_read": len(rows),
        "dropped": dropped,
        "submits": submits,
    }
