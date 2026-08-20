# -*- coding: utf-8 -*-

"""Weekly bot KPI scoring (Data owns this contract).

Lead = completed calculator (`estimate_submit`) or `/contact-me` submit
(`wix_form_submit`). Not a GHL contact. Not Facebook reach.

Lanes: Designer / Social / Boris / Data. No Charles widget.

Designer conversion is live (calculator GA4 shipped 2026-08-20,
wny-savings-calculator squash 6e299f58). Score sessions→form and
start→form against 2% / 25% when warehouse numbers exist. Null +
not_wired/unknown if missing. Never invent traffic.

Volume stays baseline_pending until 14 instrumented days exist.

Bounded warehouse reads only. No full-collection streams. No GHL join.
Not on warm_cache.
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TIMEZONE_NAME = "America/New_York"
METRIC_NAME = "Weekly Bot KPI Scorecard"

FUNNEL_COLLECTION = "web_funnel_daily_v1"
SOCIAL_COLLECTION = "bot_kpi_social_week_v1"
RAYDAR_WEEK_COLLECTION = "bot_kpi_raydar_week_v1"
COST_COLLECTION = "bot_kpi_cost_week_v1"

GOAL_SESSION_TO_FORM = 0.02
GOAL_START_TO_FORM = 0.25
INSTRUMENTED_DAYS_REQUIRED = 14
FUNNEL_LOOKBACK_DAYS = 14
OPPS_SCAN_THOUSANDS_FLOOR = 1000
WNY_SITE = "https://wny.happyslr.com"

BORIS_KNOCK_PIN_PR = "129"
BORIS_KNOCK_PIN_SHA = "270e335"

ALLOWED_STATUSES = (
    "hit",
    "miss",
    "baseline_pending",
    "not_live_yet",
    "pending",
    "not_wired",
    "later",
    "informational",
    "unknown",
)

LEAD_DEFINITION = (
    "Completed calculator (estimate_submit) or /contact-me submit (wix_form_submit). "
    "Not a GHL contact. Not Facebook reach."
)


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def get_db():
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [
            key
            for key in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(key)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    from google.cloud import firestore
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def ny_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE_NAME))


def parse_date_ymd(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        year, month, day = [int(part) for part in value.strip().split("-")]
        return date(year, month, day)
    except Exception:
        return None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def iso_week_id(year: int, week: int) -> str:
    return f"{int(year):04d}-W{int(week):02d}"


def dates_inclusive(start: date, end: date) -> list[str]:
    if end < start:
        start, end = end, start
    out: list[str] = []
    cursor = start
    while cursor <= end:
        out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def last_n_dates(n: int, *, as_of: date | None = None) -> list[str]:
    end = as_of or ny_now().date()
    start = end - timedelta(days=max(int(n) - 1, 0))
    return dates_inclusive(start, end)


@dataclass(frozen=True)
class WeekWindow:
    timezone: str
    iso_year: int
    iso_week: int
    week_id: str
    start: str
    end: str
    dates: list[str]
    created_year: int
    created_month: int
    source: str


def resolve_week(
    *,
    year: int | None = None,
    week: int | None = None,
    start: str | None = None,
    end: str | None = None,
    as_of: datetime | None = None,
) -> WeekWindow:
    """America/New_York week. Default = current NY ISO week (Mon–Sun)."""
    now = as_of or ny_now()
    start_d = parse_date_ymd(start)
    end_d = parse_date_ymd(end)
    source = "current"

    if start_d and end_d:
        source = "start_end"
        iso = start_d.isocalendar()
        iso_year, iso_week = int(iso.year), int(iso.week)
    elif year and week:
        source = "year_week"
        iso_year, iso_week = int(year), int(week)
        start_d = date.fromisocalendar(iso_year, iso_week, 1)
        end_d = start_d + timedelta(days=6)
    else:
        today = now.astimezone(ZoneInfo(TIMEZONE_NAME)).date()
        start_d = today - timedelta(days=today.weekday())
        end_d = start_d + timedelta(days=6)
        iso = start_d.isocalendar()
        iso_year, iso_week = int(iso.year), int(iso.week)

    week_id = iso_week_id(iso_year, iso_week)
    return WeekWindow(
        timezone=TIMEZONE_NAME,
        iso_year=iso_year,
        iso_week=iso_week,
        week_id=week_id,
        start=start_d.isoformat(),
        end=end_d.isoformat(),
        dates=dates_inclusive(start_d, end_d),
        created_year=start_d.year,
        created_month=start_d.month,
        source=source,
    )


def previous_week_id(window: WeekWindow) -> str:
    prev = parse_date_ymd(window.start)
    if prev is None:
        return window.week_id
    prev = prev - timedelta(days=7)
    iso = prev.isocalendar()
    return iso_week_id(int(iso.year), int(iso.week))


def metric_row(
    name: str,
    value: Any,
    goal: Any,
    status: str,
    notes: str = "",
    **extra: Any,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        status = "unknown"
    row: dict[str, Any] = {
        "name": name,
        "value": value,
        "goal": goal,
        "status": status,
        "notes": notes,
    }
    row.update(extra)
    return row


def ratio(numerator: int | None, denominator: int | None) -> float | None:
    funnel = _website_funnel_module()
    if funnel is not None and hasattr(funnel, "ratio"):
        return funnel.ratio(numerator, denominator)
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def score_vs_goal(value: float | None, goal: float | None) -> str:
    funnel = _website_funnel_module()
    if funnel is not None and hasattr(funnel, "score_vs_goal"):
        return funnel.score_vs_goal(value, goal)
    if value is None or goal is None:
        return "unknown"
    return "hit" if value + 1e-12 >= goal else "miss"


def sum_completed_forms(estimate_submit: int | None, wix_form_submits: int | None) -> int | None:
    funnel = _website_funnel_module()
    if funnel is not None and hasattr(funnel, "sum_completed_forms"):
        return funnel.sum_completed_forms(estimate_submit, wix_form_submits)
    if estimate_submit is None and wix_form_submits is None:
        return None
    return int(estimate_submit or 0) + int(wix_form_submits or 0)


def _website_funnel_module():
    """Reuse PR 6 helpers only when that file is already on this branch."""
    path = Path(__file__).resolve().parent / "website_funnel.py"
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("website_funnel_for_bot_kpi", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def completed_forms_of(doc: dict[str, Any] | None) -> int | None:
    if not isinstance(doc, dict):
        return None
    if doc.get("completed_forms") is not None:
        try:
            return int(doc.get("completed_forms"))
        except (TypeError, ValueError):
            return None
    return sum_completed_forms(
        _as_optional_int(doc.get("estimate_submit")),
        _as_optional_int(doc.get("wix_form_submits")),
    )


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sum_optional(values: list[int | None]) -> int | None:
    present = [int(v) for v in values if v is not None]
    if not present and all(v is None for v in values):
        return None
    return sum(present)


def is_instrumented_day(doc: dict[str, Any] | None) -> bool:
    """A warehouse day counts once it has a real number — never a faked 0."""
    if not isinstance(doc, dict):
        return False
    if compact_str(doc.get("ga4")).casefold() == "ok":
        return True
    for key in (
        "sessions",
        "starts",
        "estimate_submit",
        "wix_form_submits",
        "completed_forms",
    ):
        if doc.get(key) is not None:
            return True
    return False


def get_docs_by_ids(db: Any, collection: str, ids: list[str]) -> list[dict[str, Any]]:
    """Bounded get_all of known document ids. Never stream the collection."""
    if db is None or not ids:
        return []
    wanted = [compact_str(doc_id) for doc_id in ids if compact_str(doc_id)]
    refs = [db.collection(collection).document(doc_id) for doc_id in wanted]
    docs: list[dict[str, Any]] = []
    for index in range(0, len(refs), 300):
        for snap in db.get_all(refs[index : index + 300]):
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            data["_id"] = snap.id
            docs.append(data)
    return docs


def get_week_doc(db: Any, collection: str, week_id: str) -> dict[str, Any] | None:
    docs = get_docs_by_ids(db, collection, [week_id])
    return docs[0] if docs else None


def inspect_warm_cache() -> dict[str, Any]:
    """Read warm_cache source. Do not HTTP-hit created/ran/demo/sales."""
    path = Path(__file__).resolve().parents[1] / "warm_cache.py"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    urls_empty = "urls = []" in text
    forbidden = ("bot_kpi", "website_funnel", "opportunities_created", "opportunities_ran", "demo_rate", "metrics/sales")
    mentions = [needle for needle in forbidden if needle in text]
    return {
        "urls_empty": urls_empty,
        "mentions": mentions,
        "path": str(path.name),
    }


def score_designer(
    week_docs: list[dict[str, Any]],
    lookback_docs: list[dict[str, Any]],
    *,
    week_dates: list[str],
) -> dict[str, Any]:
    """Designer: volume + live conversion against goals when numbers exist."""
    week_by_date = {compact_str(doc.get("date") or doc.get("_id")): doc for doc in week_docs}
    week_rows = [week_by_date.get(day) for day in week_dates]
    present_week_docs = [doc for doc in week_rows if isinstance(doc, dict)]

    instrumented = sum(1 for doc in lookback_docs if is_instrumented_day(doc))
    volume_ready = instrumented >= INSTRUMENTED_DAYS_REQUIRED

    completed = _sum_optional([completed_forms_of(doc) for doc in present_week_docs])
    sessions = _sum_optional([_as_optional_int((doc or {}).get("sessions")) for doc in present_week_docs])
    starts = _sum_optional([_as_optional_int((doc or {}).get("starts")) for doc in present_week_docs])
    estimate_submit = _sum_optional(
        [_as_optional_int((doc or {}).get("estimate_submit")) for doc in present_week_docs]
    )

    session_to_form = ratio(completed, sessions)
    start_to_form = ratio(estimate_submit, starts)

    if volume_ready:
        volume_status = "informational" if completed is not None else "unknown"
        volume_notes = (
            f"{instrumented} instrumented days in last {FUNNEL_LOOKBACK_DAYS}. "
            "No numeric volume goal yet — reporting the week count."
        )
    else:
        volume_status = "baseline_pending"
        volume_notes = (
            f"{instrumented}/{INSTRUMENTED_DAYS_REQUIRED} instrumented days in last "
            f"{FUNNEL_LOOKBACK_DAYS} NY dates. Volume goal stays baseline pending. "
            "A lead is estimate_submit or wix_form_submit — not a GHL contact."
        )

    if not present_week_docs:
        session_status = "not_wired"
        start_status = "not_wired"
        conversion_notes = (
            "No web_funnel_daily_v1 docs for this NY week. Calculator GA4 is live "
            "(G-V02RZFR4SZ / estimate_start / estimate_submit) but warehouse numbers "
            "are missing. Traffic was not invented."
        )
    else:
        session_status = (
            "unknown" if session_to_form is None else score_vs_goal(session_to_form, GOAL_SESSION_TO_FORM)
        )
        start_status = (
            "unknown" if start_to_form is None else score_vs_goal(start_to_form, GOAL_START_TO_FORM)
        )
        conversion_notes = (
            "Calculator GA4 is live. Sessions→form uses completed forms "
            "(estimate_submit + wix_form_submit) / sessions. Start→form is "
            "calculator-only: estimate_submit / estimate_start. /contact-me is in "
            "volume and sessions→form only. Null stays null."
        )

    return {
        "label": "Designer",
        "kind": "website_funnel",
        "instrumented_days": instrumented,
        "instrumented_days_required": INSTRUMENTED_DAYS_REQUIRED,
        "week_docs_present": len(present_week_docs),
        "rows": [
            metric_row(
                "Completed form volume",
                completed,
                "baseline pending",
                volume_status,
                volume_notes,
            ),
            metric_row(
                "Sessions → completed form",
                session_to_form,
                GOAL_SESSION_TO_FORM,
                session_status,
                conversion_notes,
                goal_label="2%",
                formula="completed_forms / sessions",
            ),
            metric_row(
                "Start → completed form",
                start_to_form,
                GOAL_START_TO_FORM,
                start_status,
                conversion_notes,
                goal_label="25%",
                formula="estimate_submit / estimate_start",
                scope="calculator_only",
            ),
        ],
    }


def _permalinks_from_social_doc(doc: dict[str, Any] | None) -> list[str]:
    if not isinstance(doc, dict):
        return []
    raw = doc.get("permalinks")
    if raw is None:
        raw = doc.get("posts")
    found: list[str] = []
    if isinstance(raw, dict):
        for key in ("monday", "wednesday", "friday", "education", "local_proof", "cta", "mon", "wed", "fri"):
            value = compact_str(raw.get(key))
            if value:
                found.append(value)
        if not found:
            found = [compact_str(v) for v in raw.values() if compact_str(v)]
    elif isinstance(raw, list):
        found = [compact_str(item) for item in raw if compact_str(item)]
    elif compact_str(raw):
        found = [compact_str(raw)]
    # de-dupe, keep order
    seen: set[str] = set()
    out: list[str] = []
    for item in found:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def score_social(week_doc: dict[str, Any] | None) -> dict[str, Any]:
    """Cadence + WNY clicks. Never invent reach or impressions."""
    if not isinstance(week_doc, dict):
        posts = metric_row(
            "3 weekday posts shipped (Mon education / Wed local proof / Fri CTA)",
            None,
            3,
            "pending",
            "bot_kpi_social_week_v1/{YYYY-Www} is missing. Charles collects permalinks; "
            "no cadence number until that weekly doc exists.",
        )
        clicks = metric_row(
            f"Clicks to {WNY_SITE}",
            None,
            None,
            "not_wired",
            "Optional warehouse field wny_clicks is not present (doc missing).",
        )
    else:
        permalinks = _permalinks_from_social_doc(week_doc)
        post_count = len(permalinks) if permalinks else _as_optional_int(week_doc.get("posts_shipped"))
        if post_count is None:
            posts = metric_row(
                "3 weekday posts shipped (Mon education / Wed local proof / Fri CTA)",
                None,
                3,
                "pending",
                "Weekly social doc exists but has no permalinks / posts_shipped.",
            )
        else:
            posts = metric_row(
                "3 weekday posts shipped (Mon education / Wed local proof / Fri CTA)",
                post_count,
                3,
                "hit" if post_count >= 3 else "miss",
                "Counted from bot_kpi_social_week_v1 permalinks (or posts_shipped). "
                "Reach/impressions are ignored even if present on the doc.",
                permalinks=permalinks,
            )
        clicks_value = _as_optional_int(week_doc.get("wny_clicks"))
        clicks = metric_row(
            f"Clicks to {WNY_SITE}",
            clicks_value,
            None,
            "unknown" if clicks_value is None else "informational",
            "Optional wny_clicks on the weekly social doc. Facebook reach is not read.",
        )

    attributed = metric_row(
        "Attributed completed forms (UTMs)",
        None,
        None,
        "later",
        "Attributed forms later via UTMs. Not scored this week. No GHL join.",
    )
    return {
        "label": "Social",
        "kind": "weekly_doc",
        "collection": SOCIAL_COLLECTION,
        "doc_present": isinstance(week_doc, dict),
        "rows": [posts, clicks, attributed],
    }


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = compact_str(value).casefold()
    if text in {"true", "yes", "1", "pass", "hit"}:
        return True
    if text in {"false", "no", "0", "fail", "miss"}:
        return False
    return None


def _boris_checklist_row(
    name: str,
    doc: dict[str, Any] | None,
    field: str,
    *,
    fallback_status: str,
    fallback_notes: str,
    value_if_known: Any = None,
) -> dict[str, Any]:
    if isinstance(doc, dict) and field in doc and doc.get(field) is not None:
        flag = _optional_bool(doc.get(field))
        if flag is True:
            return metric_row(name, True, True, "hit", f"From {RAYDAR_WEEK_COLLECTION}. {fallback_notes}")
        if flag is False:
            return metric_row(name, False, True, "miss", f"From {RAYDAR_WEEK_COLLECTION}. {fallback_notes}")
        return metric_row(
            name,
            doc.get(field),
            True,
            compact_str(doc.get(field)) if compact_str(doc.get(field)) in ALLOWED_STATUSES else "informational",
            f"From {RAYDAR_WEEK_COLLECTION}. {fallback_notes}",
        )
    return metric_row(name, value_if_known, True, fallback_status, fallback_notes)


def score_boris(week_doc: dict[str, Any] | None) -> dict[str, Any]:
    """Contract checklist only. No Raydar live probe. No getAllLeads scan."""
    map_row = _boris_checklist_row(
        "Knocking map not hanging",
        week_doc,
        "map_not_hanging",
        fallback_status="pending" if week_doc is None else "informational",
        fallback_notes=(
            "Contract checklist — not a live hang probe. Optional weekly doc "
            f"{RAYDAR_WEEK_COLLECTION}/{{YYYY-Www}}. Do not scan Raydar collections."
        ),
    )
    pin_row = _boris_checklist_row(
        "Knock pin + count immediate",
        week_doc,
        "knock_pin_immediate",
        fallback_status="informational",
        fallback_notes=(
            f"Known fact: PR {BORIS_KNOCK_PIN_PR} shipped sha {BORIS_KNOCK_PIN_SHA}. "
            "Not a live field-path probe. Status is informational unless the weekly doc scores it."
        ),
        value_if_known=None,
    )
    reads_row = _boris_checklist_row(
        "Raydar Firestore reads bounded",
        week_doc,
        "reads_bounded",
        fallback_status="informational" if week_doc is None else "pending",
        fallback_notes=(
            "Contract: reads on gen-lang-client-0395385938 stay bounded; no unbounded "
            "getAllLeads on field paths. This page does not read Raydar users/leads/"
            "dispositions/territories and does not scan getAllLeads."
        ),
    )
    return {
        "label": "Boris",
        "kind": "contract_checklist",
        "collection": RAYDAR_WEEK_COLLECTION,
        "doc_present": isinstance(week_doc, dict),
        "note": (
            "Checklist only. No Raydar feature work. No live hang probe. "
            "No scan of Raydar collections on gen-lang-client-0395385938."
        ),
        "rows": [map_row, pin_row, reads_row],
    }


def score_opps_scanned(scanned: int | None, in_window: int | None, *, error: str | None = None) -> dict[str, Any]:
    notes = []
    if error:
        notes.append(error)
    if scanned is None:
        notes.append("opportunities_created.compute did not return debug.opps_scanned.")
        return metric_row(
            "Daily/FMA opps_scanned stays bounded",
            None,
            "hundreds-scale, near the month window (not thousands)",
            "not_wired",
            " ".join(notes),
        )
    notes.append(f"opps_scanned={scanned}; opps_in_time_window={in_window}.")
    notes.append("Aug 2026 lock after PR 7: result 132 / Buffalo 53, scanned ~264 not ~4545.")
    if scanned >= OPPS_SCAN_THOUSANDS_FLOOR:
        return metric_row(
            "Daily/FMA opps_scanned stays bounded",
            scanned,
            "hundreds-scale, near the month window (not thousands)",
            "miss",
            " ".join(notes) + " Thousands-scale scan looks like an unbounded leak.",
        )
    if in_window is not None and in_window > 0 and scanned > max(in_window * 5, 800):
        return metric_row(
            "Daily/FMA opps_scanned stays bounded",
            scanned,
            "hundreds-scale, near the month window (not thousands)",
            "miss",
            " ".join(notes) + " Scanned is far from the in-window count.",
        )
    return metric_row(
        "Daily/FMA opps_scanned stays bounded",
        scanned,
        "hundreds-scale, near the month window (not thousands)",
        "hit",
        " ".join(notes) + " Bounded neighborhood of the window.",
    )


def score_data(
    *,
    scanned: int | None,
    in_window: int | None,
    created_error: str | None,
    warm: dict[str, Any],
    cost_doc: dict[str, Any] | None,
    prev_cost_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    scan_row = score_opps_scanned(scanned, in_window, error=created_error)

    urls_empty = bool(warm.get("urls_empty"))
    mentions = warm.get("mentions") or []
    if urls_empty and not mentions:
        warm_row = metric_row(
            "Hourly warm_cache does not stream opps/contacts",
            True,
            True,
            "hit",
            "Inspected api/warm_cache.py: urls = []. This page does not HTTP-hit created/ran/demo/sales.",
        )
    elif urls_empty:
        warm_row = metric_row(
            "Hourly warm_cache does not stream opps/contacts",
            True,
            True,
            "miss",
            f"urls = [] but source mentions {mentions}. Keep those off the hourly warm list.",
        )
    else:
        warm_row = metric_row(
            "Hourly warm_cache does not stream opps/contacts",
            False,
            True,
            "miss",
            "api/warm_cache.py no longer has urls = []. Do not add bot_kpi or funnel URLs.",
        )

    this_scan = scanned if scanned is not None else _as_optional_int((cost_doc or {}).get("opps_scanned"))
    prev_scan = _as_optional_int((prev_cost_doc or {}).get("opps_scanned"))
    if this_scan is None or prev_scan is None:
        wow_row = metric_row(
            "happy-solar week-over-week reads flat or down",
            None,
            "flat or down vs prior week opps_scanned snapshot",
            "pending" if prev_cost_doc is None else "unknown",
            "WoW compare uses bot_kpi_cost_week_v1/{YYYY-Www}. "
            "Missing prior-week snapshot — not a fake pass.",
        )
    else:
        wow_row = metric_row(
            "happy-solar week-over-week reads flat or down",
            this_scan,
            prev_scan,
            "hit" if this_scan <= prev_scan else "miss",
            f"This week opps_scanned={this_scan}; prior week={prev_scan}. Named DB happy-solar.",
        )

    bill = None
    if isinstance(cost_doc, dict):
        raw_bill = cost_doc.get("bill_usd")
        if raw_bill is None:
            raw_bill = cost_doc.get("bill")
        if raw_bill is not None:
            try:
                bill = float(raw_bill)
            except (TypeError, ValueError):
                bill = None
    if bill is None:
        bill_row = metric_row(
            "Named DB happy-solar bill $",
            None,
            "flat or down (billing export)",
            "not_wired",
            "No billing export on bot_kpi_cost_week_v1. GCP billing API is not required for v1. "
            "Do not invent a dollar amount.",
        )
    else:
        prev_bill = None
        if isinstance(prev_cost_doc, dict) and prev_cost_doc.get("bill_usd") is not None:
            try:
                prev_bill = float(prev_cost_doc.get("bill_usd"))
            except (TypeError, ValueError):
                prev_bill = None
        if prev_bill is None:
            bill_status = "informational"
            bill_notes = f"This week bill_usd={bill}. No prior-week bill to compare."
        else:
            bill_status = "hit" if bill <= prev_bill else "miss"
            bill_notes = f"This week bill_usd={bill}; prior week={prev_bill}."
        bill_row = metric_row(
            "Named DB happy-solar bill $",
            bill,
            "flat or down (billing export)",
            bill_status,
            bill_notes,
        )

    return {
        "label": "Data",
        "kind": "self_score",
        "rows": [scan_row, warm_row, wow_row, bill_row],
    }


def maybe_write_cost_snapshot(
    db: Any,
    week_id: str,
    *,
    opps_scanned: int | None,
    warm_cache_empty: bool,
) -> bool:
    if db is None:
        return False
    try:
        db.collection(COST_COLLECTION).document(week_id).set(
            {
                "week_id": week_id,
                "opps_scanned": opps_scanned,
                "warm_cache_empty": bool(warm_cache_empty),
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            merge=True,
        )
        return True
    except Exception:
        return False


def _created_scan(db: Any, year: int, month: int) -> tuple[int | None, int | None, str | None]:
    if db is None:
        return None, None, "No Firestore client — opportunities_created.compute was not run."
    try:
        from opportunities_created import MetricContract, compute as compute_created

        payload = compute_created(db, MetricContract(), year=year, month=month)
        debug = payload.get("debug") or {}
        return (
            _as_optional_int(debug.get("opps_scanned")),
            _as_optional_int(debug.get("opps_in_time_window")),
            None,
        )
    except Exception as exc:
        return None, None, f"opportunities_created.compute failed: {exc}"


def compute(
    db: Any,
    *,
    year: int | None = None,
    week: int | None = None,
    start: str | None = None,
    end: str | None = None,
    as_of: datetime | None = None,
    write_cost_snapshot: bool = True,
    created_scan: tuple[int | None, int | None, str | None] | None = None,
    funnel_docs: list[dict[str, Any]] | None = None,
    social_doc: dict[str, Any] | None = None,
    raydar_doc: dict[str, Any] | None = None,
    cost_doc: dict[str, Any] | None = None,
    prev_cost_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the weekly scorecard. Missing numbers stay null."""
    window = resolve_week(year=year, week=week, start=start, end=end, as_of=as_of)
    lookback_dates = last_n_dates(FUNNEL_LOOKBACK_DAYS, as_of=(as_of or ny_now()).date())
    funnel_ids = list(dict.fromkeys([*window.dates, *lookback_dates]))

    if funnel_docs is None:
        funnel_docs = get_docs_by_ids(db, FUNNEL_COLLECTION, funnel_ids)

    loaded_social = get_week_doc(db, SOCIAL_COLLECTION, window.week_id) if social_doc is None else social_doc
    loaded_raydar = get_week_doc(db, RAYDAR_WEEK_COLLECTION, window.week_id) if raydar_doc is None else raydar_doc
    loaded_cost = get_week_doc(db, COST_COLLECTION, window.week_id) if cost_doc is None else cost_doc
    loaded_prev = (
        get_week_doc(db, COST_COLLECTION, previous_week_id(window)) if prev_cost_doc is None else prev_cost_doc
    )

    lookback_docs = [
        doc
        for doc in funnel_docs
        if compact_str(doc.get("date") or doc.get("_id")) in set(lookback_dates)
    ]
    week_funnel_docs = [
        doc
        for doc in funnel_docs
        if compact_str(doc.get("date") or doc.get("_id")) in set(window.dates)
    ]

    designer = score_designer(week_funnel_docs, lookback_docs, week_dates=window.dates)
    social = score_social(loaded_social if isinstance(loaded_social, dict) else None)
    boris = score_boris(loaded_raydar if isinstance(loaded_raydar, dict) else None)

    if created_scan is None:
        created_scan = _created_scan(db, window.created_year, window.created_month)
    scanned, in_window, created_error = created_scan
    warm = inspect_warm_cache()
    data = score_data(
        scanned=scanned,
        in_window=in_window,
        created_error=created_error,
        warm=warm,
        cost_doc=loaded_cost if isinstance(loaded_cost, dict) else None,
        prev_cost_doc=loaded_prev if isinstance(loaded_prev, dict) else None,
    )

    wrote_cost = False
    if write_cost_snapshot:
        wrote_cost = maybe_write_cost_snapshot(
            db,
            window.week_id,
            opps_scanned=scanned,
            warm_cache_empty=bool(warm.get("urls_empty")),
        )

    return {
        "metric": METRIC_NAME,
        "timezone": TIMEZONE_NAME,
        "week": {
            "id": window.week_id,
            "iso_year": window.iso_year,
            "iso_week": window.iso_week,
            "start": window.start,
            "end": window.end,
            "dates": window.dates,
            "source": window.source,
            "created_month": {
                "year": window.created_year,
                "month": window.created_month,
            },
        },
        "lead_definition": LEAD_DEFINITION,
        "lanes": {
            "designer": designer,
            "social": social,
            "boris": boris,
            "data": data,
        },
        "not_scored": ["Charles"],
        "constraints": {
            "no_ghl_join": True,
            "no_facebook_reach": True,
            "not_on_warm_cache": True,
            "no_charles_widget": True,
            "calculator_ga4": "live",
            "calculator_ga4_ship": "wny-savings-calculator PR 1 + PR 2 merged to main (squash 6e299f58)",
            "ga4_measurement_id": "G-V02RZFR4SZ",
        },
        "warehouse": {
            "project": "gemini-assistant-bot",
            "database": "happy-solar",
            "bounded_reads": [
                f"{FUNNEL_COLLECTION}/{{YYYY-MM-DD}} get_all of known ids (week dates + last {FUNNEL_LOOKBACK_DAYS})",
                f"{SOCIAL_COLLECTION}/{window.week_id} get",
                f"{RAYDAR_WEEK_COLLECTION}/{window.week_id} get",
                f"{COST_COLLECTION}/{window.week_id} and prior week get",
                "opportunities_created.compute month range query (not a full stream)",
            ],
            "optional_write": f"{COST_COLLECTION}/{window.week_id} (opps_scanned + warm_cache_empty)",
            "cost_snapshot_written": wrote_cost,
            "funnel_ids_requested": funnel_ids,
            "funnel_docs_returned": len(funnel_docs),
        },
        "warm_cache": warm,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
