# -*- coding: utf-8 -*-

"""Pure FMA payroll rules. Sit selection stays in demo_rate."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TIMEZONE = "America/New_York"

SETTER_LAST_NAME_CF = "Eq4NLTSkJ56KTxbxypuE"
SETTER_NAME_CF = "Xhy6k4xfHRJ6s5IbfA5x"
LEAD_GEN_SOURCE_CF = "hd5QqHEOVSsPom5bJ32P"
SCHEDULING_MANAGER_CF = "6QmaNZha745jNHnh3U86"

SELF_GEN_KEYS = frozenset({"selfgen", "selfgenerated"})
BLANK_TOKENS = frozenset({"", "none", "null", "n/a", "na", "unknown", "unassigned", "-", "—"})

DEFINITION = {
    "demo": "opportunity dispositionValue == Sit",
    "disposition_field": "GYGpLKBPfMpiBqyU2ogQ",
    "warehouse_field": "ghl_opportunities_v2.dispositionValue",
    "timestamp": "frozen_sit_timestamp = min(appointmentOccurredAt, dispositionDate)",
    "pipelines_included": ["buffalo", "rochester", "virtual", "syracuse", "rehash", "sweeper"],
    "pipelines_excluded": ["inbound/lead locker"],
    "follow_up": "not a second sit",
    "setter": "contact Setter Last Name Eq4NLTSkJ56KTxbxypuE, else opportunity same field, else last token of Setter Name Xhy6k4xfHRJ6s5IbfA5x",
    "lead_gen_source": "contact hd5QqHEOVSsPom5bJ32P",
    "scheduling_manager": "contact 6QmaNZha745jNHnh3U86",
    "owner": "ghl_opportunities_v2.assignedTo via ghl_users_v2",
    "fma_exclusions": ["self_gen", "owner_matches_setter", "no_setter"],
    "scheduling_manager_exclusions": ["self_gen"],
    "not_used": "ghl_opportunities_v2.source",
}


def compact(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if str(item).strip())
    return " ".join(str(value or "").strip().split())


def is_blank_token(value: Any) -> bool:
    return compact(value).casefold() in BLANK_TOKENS


def last_token(value: Any) -> str:
    parts = compact(value).split(" ")
    return parts[-1] if parts else ""


def display_casing(value: Any) -> str:
    text = compact(value)
    if not text:
        return ""
    if text.islower() or text.isupper():
        return " ".join(part[:1].upper() + part[1:].lower() for part in text.split(" ") if part)
    return text


def prefer_label(current: str, raw_value: Any) -> str:
    candidate = display_casing(raw_value)
    if not current:
        return candidate
    if current == candidate:
        return current

    def score(label: str) -> tuple[int, int]:
        return (
            0 if label == label.lower() else 1,
            sum(1 for idx, ch in enumerate(label) if idx and ch.isupper()),
        )

    return candidate if score(candidate) > score(current) else current


def normalize_self_gen_key(value: Any) -> str:
    return re.sub(r"[\s\-_]+", "", compact(value).casefold())


def is_self_gen(value: Any) -> bool:
    if is_blank_token(value):
        return False
    return normalize_self_gen_key(value) in SELF_GEN_KEYS


def resolve_setter_last_name(last_name_values: Any, name_values: Any) -> str:
    """Contact/opportunity Setter Last Name, else last token of Setter Name."""
    for raw in last_name_values or []:
        text = compact(raw)
        if text and not is_blank_token(text):
            return text
    for raw in name_values or []:
        text = compact(raw)
        if text and not is_blank_token(text):
            return last_token(text)
    return ""


def today_et(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(NY)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=NY)
    else:
        now = now.astimezone(NY)
    return now.date()


def last_completed_payroll_week(today: date) -> tuple[date, date]:
    """Last Thu–Wed week whose Wednesday is already over in ET.

    On Thursday the week that ended yesterday is complete.
    On Wednesday the current week is not complete, so use the prior Wednesday.
    """
    days_since_wednesday = (today.weekday() - 2) % 7
    last_wednesday = today - timedelta(days=days_since_wednesday)
    if last_wednesday == today:
        last_wednesday = today - timedelta(days=7)
    start = last_wednesday - timedelta(days=6)
    return start, last_wednesday


def parse_ymd(value: str) -> date:
    year, month, day = [int(part) for part in value.strip().split("-")]
    return date(year, month, day)


def resolve_week(week_start: str | None, today: date) -> tuple[date, date]:
    if week_start is None or not str(week_start).strip():
        return last_completed_payroll_week(today)
    try:
        start = parse_ymd(str(week_start))
    except Exception as exc:
        raise ValueError("week_start must be a Thursday (YYYY-MM-DD)") from exc
    if start.weekday() != 3:
        raise ValueError("week_start must be a Thursday (YYYY-MM-DD)")
    return start, start + timedelta(days=6)


def format_week_label(start: date, end: date) -> str:
    left = f"{start.strftime('%a %b')} {start.day}"
    right = f"{end.strftime('%a %b')} {end.day}, {end.year}"
    return f"{left} – {right} (ET)"


def exclusion_reasons(sit: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    setter = compact(sit.get("setter_last_name"))
    setter_blank = is_blank_token(setter)
    lead = sit.get("lead_source")
    if is_self_gen(lead):
        reasons.append(f"self-gen lead source: '{compact(lead)}'")
    if setter_blank:
        reasons.append("missing setter")
    else:
        owner_last = last_token(sit.get("owner_name"))
        setter_last = last_token(setter)
        if owner_last and setter_last and owner_last.casefold() == setter_last.casefold():
            reasons.append(
                "owner last name equals setter last name ('" + display_casing(setter_last) + "')"
            )
    return reasons


def _demo_sort_key(demo: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(demo.get("sat_date") or ""),
        compact(demo.get("customer_name")).casefold(),
        str(demo.get("opportunity_id") or ""),
    )


def public_demo(sit: dict[str, Any]) -> dict[str, Any]:
    setter_raw = sit.get("setter_last_name")
    manager_raw = sit.get("scheduling_manager")
    lead = sit.get("lead_source")
    owner = sit.get("owner_name")
    return {
        "customer_name": compact(sit.get("customer_name")) or None,
        "sat_date": compact(sit.get("sat_date")) or None,
        "pipeline": compact(sit.get("pipeline")) or None,
        "lead_source": None if is_blank_token(lead) else compact(lead),
        "opportunity_owner": compact(owner) or None,
        "setter": None if is_blank_token(setter_raw) else display_casing(setter_raw),
        "scheduling_manager": None if is_blank_token(manager_raw) else display_casing(manager_raw),
        "opportunity_id": compact(sit.get("opportunity_id")) or None,
        "contact_id": compact(sit.get("contact_id")) or None,
        "ghl_opportunity_url": sit.get("ghl_opportunity_url") or None,
        "ghl_contact_url": sit.get("ghl_contact_url") or None,
        "self_gen": is_self_gen(lead),
    }


def build_payroll_payload(
    sits: list[dict[str, Any]],
    week_start: date,
    week_end: date,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    if today is None:
        today = today_et()
    last_start, last_end = last_completed_payroll_week(today)

    fma_groups: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    sm_groups: dict[str, dict[str, Any]] = {}

    for sit in sits:
        reasons = exclusion_reasons(sit)
        demo = public_demo(sit)
        if reasons:
            excluded_demo = dict(demo)
            excluded_demo["reasons"] = reasons
            excluded.append(excluded_demo)
        else:
            setter_raw = sit.get("setter_last_name")
            key = compact(setter_raw).casefold()
            bucket = fma_groups.setdefault(key, {"label": "", "demos": []})
            bucket["label"] = prefer_label(bucket["label"], setter_raw)
            bucket["demos"].append(demo)

        manager_raw = sit.get("scheduling_manager")
        if is_blank_token(manager_raw):
            sm_key = ""
            sm_label = "(blank)"
        else:
            sm_key = compact(manager_raw).casefold()
            sm_label = display_casing(manager_raw)
        sm = sm_groups.setdefault(
            sm_key,
            {"label": sm_label, "demos": [], "counted": 0, "excluded_self_gen": 0},
        )
        if sm_key:
            sm["label"] = prefer_label(sm["label"], manager_raw)
        sm_demo = dict(demo)
        sm["demos"].append(sm_demo)
        if demo["self_gen"]:
            sm["excluded_self_gen"] += 1
        else:
            sm["counted"] += 1

    fma_rows = []
    for bucket in fma_groups.values():
        for demo in bucket["demos"]:
            demo["setter"] = bucket["label"]
        bucket["demos"].sort(key=_demo_sort_key)
        fma_rows.append(
            {"setter": bucket["label"], "count": len(bucket["demos"]), "demos": bucket["demos"]}
        )
    fma_rows.sort(key=lambda row: (-row["count"], row["setter"].casefold()))

    excluded.sort(key=_demo_sort_key)

    sm_rows = []
    for bucket in sm_groups.values():
        bucket["demos"].sort(key=_demo_sort_key)
        total = bucket["counted"] + bucket["excluded_self_gen"]
        sm_rows.append(
            {
                "manager": bucket["label"],
                "counted": bucket["counted"],
                "excluded_self_gen": bucket["excluded_self_gen"],
                "total": total,
                "demos": bucket["demos"],
            }
        )
    sm_rows.sort(key=lambda row: (-row["counted"], row["manager"].casefold()))

    sm_grand = {
        "counted": sum(row["counted"] for row in sm_rows),
        "excluded_self_gen": sum(row["excluded_self_gen"] for row in sm_rows),
        "total": sum(row["total"] for row in sm_rows),
    }

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "week_label": format_week_label(week_start, week_end),
        "last_completed_week_start": last_start.isoformat(),
        "last_completed_week_end": last_end.isoformat(),
        "timezone": TIMEZONE,
        "definition": DEFINITION,
        "fma": {
            "rows": fma_rows,
            "grand_total": sum(row["count"] for row in fma_rows),
            "excluded": excluded,
            "excluded_count": len(excluded),
        },
        "scheduling_manager": {
            "rows": sm_rows,
            "grand_total": sm_grand,
        },
        "source_sit_count": len(sits),
        "source_opportunity_ids": sorted(
            compact(sit.get("opportunity_id")) for sit in sits if compact(sit.get("opportunity_id"))
        ),
    }
