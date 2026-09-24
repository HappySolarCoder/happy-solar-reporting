# -*- coding: utf-8 -*-

"""Pure installer-tag parsing and the any_later_note reply rule.

No I/O, no environment, no HTTP handler. Company ids are passed in.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DEFAULT_LOOKBACK_DAYS = 60
RULE_ANY_LATER_NOTE = "any_later_note"
OPEN_AFTER = timedelta(hours=24)
RECENT_ANSWER_WINDOW = timedelta(days=14)

# Intentionally empty. A Python format string with {install_id} and
# optional {v1_deal_id}. When empty, the page shows plain text.
ENERFLO_DEAL_URL_TEMPLATE = ""

_EMAIL_RE = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_NON_WORD_RE = re.compile(r"[\W_]+", flags=re.UNICODE)
# A survey-result line is a category, a hyphen, then PASS or FAIL.
# "Roof - PASS - roof is very new" and "Electrical - FAIL" both match.
_SURVEY_LINE_RE = re.compile(
    r"(?im)^[ \t]*([A-Za-z][A-Za-z0-9 /&+]{0,80}?)[ \t]*-[ \t]*(PASS|FAIL)\b(?!/)"
)


@dataclass(frozen=True)
class Tag:
    user_id: int | None
    raw: str


def norm(value: str) -> str:
    text = (value or "").casefold()
    text = _NON_WORD_RE.sub(" ", text)
    return " ".join(text.split())


def survey_results(text: str) -> list[str]:
    """PASS/FAIL tokens from survey-result lines, in order."""
    if not text:
        return []
    return [match.group(2).upper() for match in _SURVEY_LINE_RE.finditer(text)]


def is_all_pass_survey(text: str) -> bool:
    """True when the note has survey-result lines and every one is PASS."""
    results = survey_results(text)
    return bool(results) and all(item == "PASS" for item in results)


def parse_created_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        if "T" in text:
            parsed = datetime.fromisoformat(text)
        else:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_et(moment: datetime) -> str:
    local = moment.astimezone(ET)
    hour = str(int(local.strftime("%I")))
    return f"{local.strftime('%a')} {local.strftime('%m/%d')} {hour}:{local.strftime('%M %p')} ET"


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def waiting_label(hours: float) -> str:
    whole = max(0, int(math.floor(hours)))
    days, remainder = divmod(whole, 24)
    if days:
        return f"{days}d {remainder}h"
    return f"{remainder}h"


def snippet(text: str, limit: int = 140) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed[:limit]


def deal_url(install_id: int, v1_deal_id: str = "", template: str | None = None) -> str | None:
    chosen = ENERFLO_DEAL_URL_TEMPLATE if template is None else template
    if not str(chosen).strip():
        return None
    return str(chosen).format(install_id=install_id, v1_deal_id=v1_deal_id or "")


def _as_int(value: object) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _display_name(user: dict) -> str:
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    return " ".join(part for part in (first, last) if part)


def _name_index(users: list[dict]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = {}
    for user in users:
        user_id = _as_int(user.get("id"))
        if user_id is None:
            continue
        key = norm(f"{user.get('first_name') or ''} {user.get('last_name') or ''}")
        if len(key.split()) < 2:
            continue
        index.setdefault(key, set()).add(user_id)
    return index


def _unresolved_raw(seg: str) -> str:
    tokens: list[str] = []
    for token in seg.split():
        if token == "-":
            continue
        cleaned = token.strip(".,;:!?\"'()[]{}")
        if not cleaned or cleaned == "-":
            continue
        tokens.append(cleaned)
        if len(tokens) == 2:
            break
    if not tokens:
        return ""
    return "@" + " ".join(tokens)


def parse_tags(text: str, users: list[dict]) -> list[Tag]:
    """Resolve @Name tags. Unresolved tags have user_id None."""
    source = text or ""
    index = _name_index(users)
    found: list[Tag] = []
    seen_ids: set[int] = set()
    seen_raw: set[str] = set()
    cursor = 0
    length = len(source)
    while cursor < length:
        at = source.find("@", cursor)
        if at < 0:
            break
        token_start = at
        while token_start > 0 and not source[token_start - 1].isspace():
            token_start -= 1
        token_end = at + 1
        while token_end < length and not source[token_end].isspace():
            token_end += 1
        token = source[token_start:token_end]
        if _EMAIL_RE.search(token):
            cursor = token_end
            continue
        seg_end = length
        newline = source.find("\n", at + 1)
        nxt = source.find("@", at + 1)
        if newline >= 0:
            seg_end = min(seg_end, newline)
        if nxt >= 0:
            seg_end = min(seg_end, nxt)
        seg = source[at + 1 : seg_end]
        cursor = seg_end
        if not seg or not seg[0].isalpha():
            continue
        toks = norm(seg).split()[:6]
        matched: int | None = None
        upper = min(len(toks), 5)
        for size in range(upper, 1, -1):
            key = " ".join(toks[:size])
            ids = index.get(key)
            if ids and len(ids) == 1:
                matched = next(iter(ids))
                break
        if matched is not None:
            if matched in seen_ids:
                continue
            seen_ids.add(matched)
            found.append(Tag(user_id=matched, raw=""))
            continue
        raw = _unresolved_raw(seg)
        if not raw or raw in seen_raw:
            continue
        seen_raw.add(raw)
        found.append(Tag(user_id=None, raw=raw))
    return found


def _users_by_id(users: list[dict]) -> dict[int, dict]:
    by_id: dict[int, dict] = {}
    for user in users:
        user_id = _as_int(user.get("id"))
        if user_id is None:
            continue
        by_id[user_id] = user
    return by_id


def _company_id(user: dict | None) -> int | None:
    if not user:
        return None
    return _as_int(user.get("company_id"))


@dataclass
class _Note:
    note_id: int
    install_id: int
    text: str
    created_at: datetime
    tags: list[Tag]
    installer_ids: list[int]


def _prepare_notes(
    notes: list[dict],
    users: list[dict],
    installer_company_id: int,
) -> list[_Note]:
    by_id = _users_by_id(users)
    prepared: list[_Note] = []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        if raw.get("deleted_at"):
            continue
        note_id = _as_int(raw.get("note_id"))
        install_id = _as_int(raw.get("epc_install_id"))
        if install_id is None:
            install_id = _as_int(raw.get("id"))
        created = parse_created_at(raw.get("created_at"))
        if note_id is None or install_id is None or created is None:
            continue
        text = raw.get("note")
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        tags = parse_tags(text, users)
        installer_ids: list[int] = []
        for tag in tags:
            if tag.user_id is None:
                continue
            if _company_id(by_id.get(tag.user_id)) == installer_company_id:
                installer_ids.append(tag.user_id)
        prepared.append(
            _Note(
                note_id=note_id,
                install_id=install_id,
                text=text,
                created_at=created,
                tags=tags,
                installer_ids=installer_ids,
            )
        )
    return prepared


def _reply_kind(
    reply: _Note,
    by_id: dict[int, dict],
    hs_company_id: int,
    installer_company_id: int,
) -> tuple[str, str]:
    companies = [
        company
        for company in (_company_id(by_id.get(tag.user_id)) for tag in reply.tags if tag.user_id is not None)
        if company is not None
    ]
    if any(company == hs_company_id for company in companies):
        return "reply_inferred", "medium"
    if companies and all(company == installer_company_id for company in companies):
        return "followup", "medium"
    return "untagged", "low"


def _first_later(note: _Note, siblings: list[_Note]) -> _Note | None:
    later = [item for item in siblings if item.note_id != note.note_id and item.created_at > note.created_at]
    if not later:
        return None
    later.sort(key=lambda item: (item.created_at, item.note_id))
    return later[0]


def _row(note: _Note, by_id: dict[int, dict], now: datetime, chaser_count: int) -> dict:
    hours = (now - note.created_at).total_seconds() / 3600.0
    tagged = [
        {"id": user_id, "name": _display_name(by_id.get(user_id) or {})}
        for user_id in note.installer_ids
    ]
    return {
        "note_id": note.note_id,
        "install_id": note.install_id,
        "customer_name": "",
        "enerflo_url": deal_url(note.install_id),
        "created_at_utc": iso_z(note.created_at),
        "created_at_et": format_et(note.created_at),
        "waiting_hours": round(hours, 1),
        "waiting_label": waiting_label(hours),
        "sales_rep": "",
        "tagged": tagged,
        "text": note.text,
        "snippet": snippet(note.text),
        "chaser_count": chaser_count,
        "status": "",
        "milestone": "",
    }


def _needs_mapping(notes: list[_Note]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for note in notes:
        seen_in_note: set[str] = set()
        for tag in note.tags:
            if tag.user_id is not None or not tag.raw or tag.raw in seen_in_note:
                continue
            seen_in_note.add(tag.raw)
            slot = grouped.get(tag.raw)
            if slot is None:
                slot = {"raw": tag.raw, "count": 0, "last_seen": note.created_at, "note_ids": []}
                grouped[tag.raw] = slot
            slot["count"] += 1
            slot["note_ids"].append(note.note_id)
            if note.created_at >= slot["last_seen"]:
                slot["last_seen"] = note.created_at
    rows = []
    for slot in grouped.values():
        rows.append(
            {
                "raw": slot["raw"],
                "count": slot["count"],
                "last_seen_et": format_et(slot["last_seen"]),
                "note_ids": slot["note_ids"],
            }
        )
    rows.sort(key=lambda item: (-item["count"], item["raw"]))
    return rows


def classify(
    notes: list[dict],
    users: list[dict],
    now: datetime,
    rule: str = RULE_ANY_LATER_NOTE,
    *,
    hs_company_id: int,
    installer_company_id: int,
    days: int = DEFAULT_LOOKBACK_DAYS,
    created_after: str = "",
) -> dict:
    """Classify installer-tagged notes. rule is kept so a stricter rule can replace it."""
    if rule != RULE_ANY_LATER_NOTE:
        raise ValueError(f"unsupported rule: {rule}")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    by_id = _users_by_id(users)
    prepared = _prepare_notes(notes, users, installer_company_id)
    by_install: dict[int, list[_Note]] = {}
    for note in prepared:
        by_install.setdefault(note.install_id, []).append(note)

    open_rows: list[dict] = []
    pending_rows: list[dict] = []
    survey_rows: list[dict] = []
    answered: list[dict] = []
    kind_counts = {"reply_inferred": 0, "followup": 0, "untagged": 0}
    installer_tagged = 0

    for note in prepared:
        if not note.installer_ids:
            continue
        installer_tagged += 1
        siblings = by_install.get(note.install_id) or []
        earlier = [
            item
            for item in siblings
            if item.installer_ids and (item.created_at, item.note_id) < (note.created_at, note.note_id)
        ]
        chaser_count = len(earlier)
        reply = _first_later(note, siblings)
        row = _row(note, by_id, now, chaser_count)
        if reply is not None:
            kind, confidence = _reply_kind(reply, by_id, hs_company_id, installer_company_id)
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            answered.append(
                {
                    "note_id": note.note_id,
                    "install_id": note.install_id,
                    "customer_name": "",
                    "created_at": note.created_at,
                    "created_at_et": format_et(note.created_at),
                    "reply_note_id": reply.note_id,
                    "replied_at": reply.created_at,
                    "replied_at_et": format_et(reply.created_at),
                    "reply_kind": kind,
                    "confidence": confidence,
                }
            )
            continue
        # All-PASS survey notes are not waiting on a reply, at any age.
        # A FAIL, or a note with no survey-result lines, stays open/pending.
        if is_all_pass_survey(note.text):
            survey_rows.append(row)
        elif now - note.created_at > OPEN_AFTER:
            open_rows.append(row)
        else:
            pending_rows.append(row)

    open_rows.sort(key=lambda item: (-item["waiting_hours"], item["note_id"]))
    pending_rows.sort(key=lambda item: (-item["waiting_hours"], item["note_id"]))
    survey_rows.sort(key=lambda item: (-item["waiting_hours"], item["note_id"]))

    recent_cutoff = now - RECENT_ANSWER_WINDOW
    recent = [item for item in answered if item["replied_at"] >= recent_cutoff]
    recent.sort(key=lambda item: (item["replied_at"], item["note_id"]), reverse=True)
    recently_answered = [
        {
            "note_id": item["note_id"],
            "install_id": item["install_id"],
            "customer_name": "",
            "created_at_et": item["created_at_et"],
            "reply_note_id": item["reply_note_id"],
            "replied_at_et": item["replied_at_et"],
            "reply_kind": item["reply_kind"],
            "confidence": item["confidence"],
        }
        for item in recent
    ]
    mapping = _needs_mapping(prepared)
    if not created_after:
        created_after = iso_z(now - timedelta(days=days))
    return {
        "rule": rule,
        "generated_at": iso_z(now),
        "generated_at_et": format_et(now),
        "window": {"days": days, "created_after": created_after},
        "counts": {
            "installer_tagged": installer_tagged,
            "open": len(open_rows),
            "pending": len(pending_rows),
            "survey_passed": len(survey_rows),
            "answered": len(answered),
            "answered_by_kind": {
                "reply_inferred": kind_counts["reply_inferred"],
                "followup": kind_counts["followup"],
                "untagged": kind_counts["untagged"],
            },
            "chasers": sum(item["chaser_count"] for item in open_rows),
            "needs_mapping": len(mapping),
        },
        "rows": open_rows,
        "pending": pending_rows,
        "survey_passed": survey_rows,
        "recently_answered": recently_answered,
        "needs_mapping": mapping,
        "warnings": [],
    }


def install_ids_to_fetch(payload: dict) -> list[int]:
    """Open, pending, and survey-passed rows. Answered rows are not fetched."""
    ids: list[int] = []
    seen: set[int] = set()
    for key in ("rows", "pending", "survey_passed"):
        for row in payload.get(key) or []:
            install_id = _as_int(row.get("install_id"))
            if install_id is None or install_id in seen:
                continue
            seen.add(install_id)
            ids.append(install_id)
    return ids


def apply_install_details(payload: dict, installs: dict, warnings: list[dict] | None = None) -> dict:
    """Fill cached install fields. Missing installs stay as Install #id plus a warning."""
    merged = list(payload.get("warnings") or [])
    seen_warning: set[int] = set()
    for item in warnings or []:
        if not isinstance(item, dict):
            continue
        merged.append(item)
        install_id = _as_int(item.get("install_id"))
        if install_id is not None:
            seen_warning.add(install_id)

    def fill_row(row: dict, *, warn: bool) -> None:
        install_id = _as_int(row.get("install_id"))
        info = installs.get(install_id) if install_id is not None else None
        if isinstance(info, dict) and info:
            row["customer_name"] = info.get("customer_name") or ""
            row["sales_rep"] = info.get("rep_name") or ""
            row["status"] = info.get("status") or ""
            row["milestone"] = info.get("milestone") or ""
            row["enerflo_url"] = deal_url(install_id or 0, str(info.get("v1_deal_id") or ""))
            return
        row["enerflo_url"] = deal_url(install_id or 0)
        if warn and install_id is not None and install_id not in seen_warning:
            seen_warning.add(install_id)
            merged.append({"install_id": install_id, "detail": "install: unavailable"})

    for key in ("rows", "pending", "survey_passed"):
        for row in payload.get(key) or []:
            fill_row(row, warn=True)
    for row in payload.get("recently_answered") or []:
        install_id = _as_int(row.get("install_id"))
        info = installs.get(install_id) if install_id is not None else None
        if isinstance(info, dict) and info.get("customer_name"):
            row["customer_name"] = info.get("customer_name") or ""
    payload["warnings"] = merged
    return payload
