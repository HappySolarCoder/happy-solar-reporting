# -*- coding: utf-8 -*-

"""Website Funnel metric family.

Lead = a completed form submit (America/New_York):
- Calculator: estimate_submit (name/phone/email in contact-complete)
- /contact-me: wix_form_submit (complete Submit)
- /contact-me counts as a completed form.
- Not a CRM contact. Not a pageview.

Scoreboard: sessions → start → completed form.

Primary:
1. Completed form — volume. Goal: baseline pending (14-day).
2. Sessions → completed form — completed_forms / sessions. Goal 2%.
3. Start → completed form — calculator-only:
   estimate_submit / estimate_start. Goal 25%.
   contact-me has no start; it is in volume and sessions→completed form only.
4. Page contribution — share of completed forms by first page_group.
   No % goal.

Secondary (diagnostic only, not scored this week):
- address-complete and bill-complete drop-off
- sessions → start by surface (site 8%, home 6%, city 12%,
  ny-incentives 10%, calculator-direct 70%)

Warehouse: FIRESTORE_DATABASE_ID collection web_funnel_daily_v1,
one doc per America/New_York date (id YYYY-MM-DD).

Cost rules:
- Dashboard month view reads ≤31 daily docs.
- Rollup pulls optional GA4 event counts for one NY day.
- Does not read CRM opportunity or contact collections.
- Not on warm_cache. Not hourly.

GA4 (optional):
- Measurement ID G-V02RZFR4SZ (locked).
- Env GA4_PROPERTY_ID = numeric property id (required to pull traffic).
- Env GA4_SERVICE_ACCOUNT_JSON optional; else FIREBASE_SERVICE_ACCOUNT_JSON.
- If creds/property are missing, write nulls and set ga4="not_configured".
  Do not fake traffic.
"""

from __future__ import annotations

import json
import os
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

METRIC_NAME = "Website Funnel"
TIMEZONE_NAME = "America/New_York"
DAILY_COLLECTION = "web_funnel_daily_v1"

GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID_ENV = "GA4_PROPERTY_ID"
GA4_SERVICE_ACCOUNT_JSON_ENV = "GA4_SERVICE_ACCOUNT_JSON"
FIREBASE_SERVICE_ACCOUNT_JSON_ENV = "FIREBASE_SERVICE_ACCOUNT_JSON"

PAGE_GROUPS: tuple[str, ...] = (
    "home",
    "city_buffalo",
    "city_rochester",
    "city_syracuse",
    "ny_incentives",
    "calculator",
    "contact_me",
    "other",
)

CITY_LANDER_GROUPS = frozenset({"city_buffalo", "city_rochester", "city_syracuse"})

GA4_EVENT_NAMES: tuple[str, ...] = (
    "page_view",
    "estimate_cta_click",
    "estimate_start",
    "estimate_address_complete",
    "estimate_bill_complete",
    "estimate_submit",
    "wix_form_submit",
)

EVENT_COUNT_FIELDS = {
    "page_view": "sessions",
    "estimate_cta_click": "cta_clicks",
    "estimate_start": "starts",
    "estimate_address_complete": "address_complete",
    "estimate_bill_complete": "bill_complete",
    "estimate_submit": "estimate_submit",
    "wix_form_submit": "wix_form_submits",
}

GOAL_SESSION_TO_FORM = 0.02
GOAL_START_TO_FORM = 0.25
GOAL_SESSION_TO_START_SITE = 0.08
GOAL_SESSION_TO_START_HOME = 0.06
GOAL_SESSION_TO_START_CITY = 0.12
GOAL_SESSION_TO_START_NY_INCENTIVES = 0.10
GOAL_SESSION_TO_START_CALCULATOR = 0.70

KPI_NAMES: tuple[str, ...] = (
    "Completed form",
    "Sessions → completed form",
    "Start → completed form",
    "Page contribution",
)
SCOREBOARD = "sessions → start → completed form"

EMPTY_PAGE_BUCKET = {
    "sessions": 0,
    "starts": 0,
    "completed_forms": 0,
}


def get_db() -> firestore.Client:
    creds_json = os.environ.get(FIREBASE_SERVICE_ACCOUNT_JSON_ENV)
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")

    if not (creds_json and project_id and database_id):
        missing = [
            k
            for k in (FIREBASE_SERVICE_ACCOUNT_JSON_ENV, "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(k)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def ny_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE_NAME))


def yesterday_ny_date() -> str:
    return (ny_now().date() - timedelta(days=1)).isoformat()


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value or not isinstance(value, str):
        return None
    try:
        year, month, day = [int(part) for part in value.strip().split("-")]
        return year, month, day
    except Exception:
        return None


def month_dates(year: int, month: int) -> list[str]:
    last = monthrange(year, month)[1]
    return [f"{year:04d}-{month:02d}-{day:02d}" for day in range(1, last + 1)]


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def empty_by_page() -> dict[str, dict[str, int]]:
    return {group: dict(EMPTY_PAGE_BUCKET) for group in PAGE_GROUPS}


def normalize_page_group(raw: Any) -> str:
    text = compact_str(raw).casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "home": "home",
        "/": "home",
        "city_buffalo": "city_buffalo",
        "buffalo": "city_buffalo",
        "city_rochester": "city_rochester",
        "rochester": "city_rochester",
        "city_syracuse": "city_syracuse",
        "syracuse": "city_syracuse",
        "ny_incentives": "ny_incentives",
        "nyincentives": "ny_incentives",
        "calculator": "calculator",
        "calculator_direct": "calculator",
        "contact_me": "contact_me",
        "contactme": "contact_me",
        "other": "other",
    }
    if text in aliases:
        return aliases[text]
    return page_group_from_landing(raw)


def page_group_from_landing(raw: Any) -> str:
    text = compact_str(raw)
    if not text:
        return "other"
    try:
        parsed = urlparse(text if "://" in text else f"https://x{text if text.startswith('/') else '/' + text}")
        path = (parsed.path or "/").casefold()
    except Exception:
        path = text.casefold()
    path = path.split("?")[0].rstrip("/") or "/"
    if path in {"/", "/home", "/index", "/index.html"}:
        return "home"
    if "buffalo" in path:
        return "city_buffalo"
    if "rochester" in path:
        return "city_rochester"
    if "syracuse" in path:
        return "city_syracuse"
    if "ny-incentives" in path or "ny_incentives" in path or "nyincentives" in path:
        return "ny_incentives"
    if "contact-me" in path or "contact_me" in path or path.endswith("/contact"):
        return "contact_me"
    if "calculator" in path:
        return "calculator"
    return "other"


def ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def score_vs_goal(value: float | None, goal: float | None, *, higher_is_better: bool = True) -> str:
    if value is None or goal is None:
        return "unknown"
    if higher_is_better:
        return "hit" if value + 1e-12 >= goal else "miss"
    return "hit" if value - 1e-12 <= goal else "miss"


def drop_off(from_count: int | None, to_count: int | None) -> float | None:
    if from_count is None or to_count is None or from_count <= 0:
        return None
    return max(float(from_count - to_count) / float(from_count), 0.0)


def sum_completed_forms(estimate_submit: int | None, wix_form_submits: int | None) -> int | None:
    if estimate_submit is None and wix_form_submits is None:
        return None
    return int(estimate_submit or 0) + int(wix_form_submits or 0)


def ga4_credentials_available() -> bool:
    property_id = compact_str(os.environ.get(GA4_PROPERTY_ID_ENV))
    creds_json = os.environ.get(GA4_SERVICE_ACCOUNT_JSON_ENV) or os.environ.get(FIREBASE_SERVICE_ACCOUNT_JSON_ENV)
    return bool(property_id and creds_json)


def _ga4_not_configured(error: str | None = None) -> dict[str, Any]:
    return {
        "ga4": "not_configured",
        "sessions": None,
        "cta_clicks": None,
        "starts": None,
        "address_complete": None,
        "bill_complete": None,
        "estimate_submit": None,
        "wix_form_submits": None,
        "completed_forms": None,
        "by_page": empty_by_page(),
        "error": error,
        "env": {
            "property_id_env": GA4_PROPERTY_ID_ENV,
            "service_account_env": GA4_SERVICE_ACCOUNT_JSON_ENV,
            "service_account_fallback_env": FIREBASE_SERVICE_ACCOUNT_JSON_ENV,
            "measurement_id": GA4_MEASUREMENT_ID,
        },
    }


def _ga4_access_token() -> str | None:
    creds_json = os.environ.get(GA4_SERVICE_ACCOUNT_JSON_ENV) or os.environ.get(FIREBASE_SERVICE_ACCOUNT_JSON_ENV)
    if not creds_json:
        return None
    info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    try:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        return creds.token
    except Exception:
        pass
    try:
        import urllib3
        from google.auth.transport.urllib3 import Request as Urllib3Request

        creds.refresh(Urllib3Request(urllib3.PoolManager()))
        return creds.token
    except Exception:
        return None


def fetch_ga4_event_counts(date_ymd: str) -> dict[str, Any]:
    """Pull one NY day's event counts. Never invent traffic if GA4 is missing."""
    if not ga4_credentials_available():
        return _ga4_not_configured()

    property_id = compact_str(os.environ.get(GA4_PROPERTY_ID_ENV))
    token = _ga4_access_token()
    if not token:
        return _ga4_not_configured("ga4_token_refresh_failed")

    import urllib.request

    body = {
        "dateRanges": [{"startDate": date_ymd, "endDate": date_ymd}],
        "dimensions": [{"name": "eventName"}, {"name": "pagePath"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": {
            "filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": list(GA4_EVENT_NAMES)},
            }
        },
    }
    req = urllib.request.Request(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            report = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return _ga4_not_configured(f"ga4_run_report_failed: {exc}")

    totals = {field: 0 for field in EVENT_COUNT_FIELDS.values()}
    by_page = empty_by_page()
    for row in report.get("rows") or []:
        dims = [cell.get("value") for cell in (row.get("dimensionValues") or [])]
        mets = [cell.get("value") for cell in (row.get("metricValues") or [])]
        event_name = compact_str(dims[0] if dims else "")
        page_path = compact_str(dims[1] if len(dims) > 1 else "")
        try:
            count = int(float(mets[0] if mets else 0))
        except Exception:
            count = 0
        field = EVENT_COUNT_FIELDS.get(event_name)
        if not field:
            continue
        totals[field] = totals.get(field, 0) + count
        group = page_group_from_landing(page_path)
        bucket = by_page.setdefault(group, dict(EMPTY_PAGE_BUCKET))
        if field == "sessions":
            bucket["sessions"] += count
        elif field == "starts":
            bucket["starts"] += count
        elif field in {"estimate_submit", "wix_form_submits"}:
            bucket["completed_forms"] += count

    estimate_submit = totals.get("estimate_submit", 0)
    wix_form_submits = totals.get("wix_form_submits", 0)
    return {
        "ga4": "ok",
        "sessions": totals.get("sessions", 0),
        "cta_clicks": totals.get("cta_clicks", 0),
        "starts": totals.get("starts", 0),
        "address_complete": totals.get("address_complete", 0),
        "bill_complete": totals.get("bill_complete", 0),
        "estimate_submit": estimate_submit,
        "wix_form_submits": wix_form_submits,
        "completed_forms": sum_completed_forms(estimate_submit, wix_form_submits),
        "by_page": by_page,
        "error": None,
        "env": {
            "property_id_env": GA4_PROPERTY_ID_ENV,
            "service_account_env": GA4_SERVICE_ACCOUNT_JSON_ENV,
            "service_account_fallback_env": FIREBASE_SERVICE_ACCOUNT_JSON_ENV,
            "measurement_id": GA4_MEASUREMENT_ID,
            "property_id_set": True,
        },
    }


def normalize_by_page(raw: dict[str, Any] | None) -> dict[str, dict[str, int | None]]:
    out = empty_by_page()
    for group in PAGE_GROUPS:
        bucket = (raw or {}).get(group) or {}
        completed = bucket.get("completed_forms")
        if completed is None:
            completed = bucket.get("estimate_submit")
            if completed is None:
                completed = 0
                if bucket.get("wix_form_submits") is not None:
                    completed += int(bucket.get("wix_form_submits") or 0)
        out[group] = {
            "sessions": bucket.get("sessions"),
            "starts": bucket.get("starts"),
            "completed_forms": completed,
        }
        for key in ("sessions", "starts", "completed_forms"):
            if out[group][key] is None:
                continue
            out[group][key] = int(out[group][key] or 0)
    return out


def build_daily_doc(date_ymd: str, ga4: dict[str, Any]) -> dict[str, Any]:
    ga4_status = compact_str(ga4.get("ga4")) or "not_configured"
    estimate_submit = ga4.get("estimate_submit")
    wix_form_submits = ga4.get("wix_form_submits")
    completed = ga4.get("completed_forms")
    if completed is None:
        completed = sum_completed_forms(estimate_submit, wix_form_submits)
    return {
        "date": date_ymd,
        "sessions": ga4.get("sessions"),
        "cta_clicks": ga4.get("cta_clicks"),
        "starts": ga4.get("starts"),
        "address_complete": ga4.get("address_complete"),
        "bill_complete": ga4.get("bill_complete"),
        "estimate_submit": estimate_submit,
        "wix_form_submits": wix_form_submits,
        "completed_forms": completed,
        "by_page": normalize_by_page(ga4.get("by_page")),
        "ga4": ga4_status,
        "ga4_error": ga4.get("error"),
        "measurement_id": GA4_MEASUREMENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def rollup_day(db: firestore.Client, date_ymd: str | None = None) -> dict[str, Any]:
    date_key = date_ymd or yesterday_ny_date()
    if not parse_date_ymd(date_key):
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    ga4 = fetch_ga4_event_counts(date_key)
    doc = build_daily_doc(date_key, ga4)
    db.collection(DAILY_COLLECTION).document(date_key).set(doc, merge=True)
    return {"wrote": True, "collection": DAILY_COLLECTION, "id": date_key, "doc": doc}


def read_month_docs(db: firestore.Client, year: int, month: int) -> list[dict[str, Any]]:
    dates = month_dates(year, month)
    refs = [db.collection(DAILY_COLLECTION).document(day) for day in dates]
    docs: list[dict[str, Any]] = []
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            data["date"] = compact_str(data.get("date") or snap.id)
            docs.append(data)
    docs.sort(key=lambda row: row.get("date") or "")
    return docs


def _sum_optional(values: list[Any]) -> int | None:
    present = [int(v) for v in values if v is not None]
    if not present and all(v is None for v in values):
        return None
    return sum(present)


def aggregate_daily_docs(docs: list[dict[str, Any]], *, year: int, month: int) -> dict[str, Any]:
    dates = month_dates(year, month)
    present = {compact_str(row.get("date")) for row in docs if compact_str(row.get("date"))}
    missing = [day for day in dates if day not in present]
    ga4_statuses = [compact_str(row.get("ga4")) or "unknown" for row in docs]
    if not docs:
        ga4_status = "missing_docs"
    elif all(status == "not_configured" for status in ga4_statuses):
        ga4_status = "not_configured"
    elif any(status == "not_configured" for status in ga4_statuses) or any(status != "ok" for status in ga4_statuses):
        ga4_status = "partial"
    else:
        ga4_status = "ok"

    estimate_submit = _sum_optional([row.get("estimate_submit") for row in docs])
    wix_form_submits = _sum_optional([row.get("wix_form_submits") for row in docs])
    completed_forms = _sum_optional([row.get("completed_forms") for row in docs])
    if completed_forms is None:
        completed_forms = sum_completed_forms(estimate_submit, wix_form_submits)

    totals = {
        "sessions": _sum_optional([row.get("sessions") for row in docs]),
        "cta_clicks": _sum_optional([row.get("cta_clicks") for row in docs]),
        "starts": _sum_optional([row.get("starts") for row in docs]),
        "address_complete": _sum_optional([row.get("address_complete") for row in docs]),
        "bill_complete": _sum_optional([row.get("bill_complete") for row in docs]),
        "estimate_submit": estimate_submit,
        "wix_form_submits": wix_form_submits,
        "completed_forms": completed_forms,
    }

    by_page = empty_by_page()
    for row in docs:
        page_map = normalize_by_page(row.get("by_page"))
        for group in PAGE_GROUPS:
            bucket = page_map.get(group) or {}
            for key in ("sessions", "starts", "completed_forms"):
                if bucket.get(key) is None:
                    continue
                by_page[group][key] += int(bucket.get(key) or 0)

    session_to_form = ratio(totals["completed_forms"], totals["sessions"])
    start_to_form = ratio(totals["estimate_submit"], totals["starts"])
    session_to_start = ratio(totals["starts"], totals["sessions"])

    def group_rate(group: str) -> float | None:
        bucket = by_page.get(group) or {}
        return ratio(bucket.get("starts"), bucket.get("sessions"))

    city_starts = sum(int((by_page[g].get("starts") or 0)) for g in CITY_LANDER_GROUPS)
    city_sessions = sum(int((by_page[g].get("sessions") or 0)) for g in CITY_LANDER_GROUPS)
    city_rate = ratio(city_starts, city_sessions)

    page_share: dict[str, float | None] = {}
    form_total = totals["completed_forms"] or 0
    for group in PAGE_GROUPS:
        count = int((by_page[group].get("completed_forms") or 0))
        page_share[group] = (count / form_total) if form_total > 0 else None

    notes = [
        "A lead is a completed form submit: estimate_submit on the calculator, or wix_form_submit on /contact-me.",
        "Scoreboard is sessions → start → completed form.",
        "/contact-me completed submits count as leads in volume and sessions → completed form.",
        "Start → completed form is calculator-only (estimate_submit / estimate_start). contact-me has no start.",
        "Volume goal for completed form is baseline pending until a 14-day baseline exists.",
        "Sessions → start by surface and address/bill drop-off are diagnostic only and are not scored this week.",
    ]
    if not docs:
        notes.append("No daily warehouse docs for this month. Run /api/web_funnel_rollup.")
    elif missing:
        notes.append(
            f"Missing {len(missing)} daily warehouse doc(s): {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}."
        )
    if ga4_status == "not_configured":
        notes.append("GA4 is not_configured. Session/start/completed-form counts are null — traffic was not faked.")
    elif ga4_status == "partial":
        notes.append("Some daily docs have ga4=not_configured or are incomplete.")

    kpis = {
        "completed_form": {
            "name": "Completed form",
            "value": totals["completed_forms"],
            "goal": None,
            "goal_label": "baseline pending",
            "status": "baseline_pending",
        },
        "sessions_to_completed_form": {
            "name": "Sessions → completed form",
            "value": session_to_form,
            "goal": GOAL_SESSION_TO_FORM,
            "goal_label": "2%",
            "status": score_vs_goal(session_to_form, GOAL_SESSION_TO_FORM),
        },
        "start_to_completed_form": {
            "name": "Start → completed form",
            "value": start_to_form,
            "goal": GOAL_START_TO_FORM,
            "goal_label": "25%",
            "status": score_vs_goal(start_to_form, GOAL_START_TO_FORM),
            "scope": "calculator_only",
            "formula": "estimate_submit / estimate_start",
        },
        "page_contribution": {
            "name": "Page contribution",
            "value": page_share,
            "goal": None,
            "goal_label": "no % goal",
            "status": "informational",
        },
    }

    secondary = {
        "address_complete": {
            "name": "Address complete",
            "value": totals["address_complete"],
            "rate_from_start": ratio(totals["address_complete"], totals["starts"]),
            "drop_off_from_start": drop_off(totals["starts"], totals["address_complete"]),
            "scored": False,
        },
        "bill_complete": {
            "name": "Bill complete",
            "value": totals["bill_complete"],
            "rate_from_start": ratio(totals["bill_complete"], totals["starts"]),
            "drop_off_from_address": drop_off(totals["address_complete"], totals["bill_complete"]),
            "scored": False,
        },
        "sessions_to_start": {
            "name": "Sessions → start",
            "value": session_to_start,
            "scored": False,
            "note": "Diagnostic only. Not scored this week.",
            "by_surface": {
                "site": {"value": session_to_start, "goal": GOAL_SESSION_TO_START_SITE, "goal_label": "8%"},
                "home": {"value": group_rate("home"), "goal": GOAL_SESSION_TO_START_HOME, "goal_label": "6%"},
                "city_landers": {"value": city_rate, "goal": GOAL_SESSION_TO_START_CITY, "goal_label": "12%"},
                "ny_incentives": {
                    "value": group_rate("ny_incentives"),
                    "goal": GOAL_SESSION_TO_START_NY_INCENTIVES,
                    "goal_label": "10%",
                },
                "calculator_direct": {
                    "value": group_rate("calculator"),
                    "goal": GOAL_SESSION_TO_START_CALCULATOR,
                    "goal_label": "70%",
                },
            },
        },
    }

    return {
        "metric": METRIC_NAME,
        "timezone": TIMEZONE_NAME,
        "year": year,
        "month": month,
        "collection": DAILY_COLLECTION,
        "days_requested": len(dates),
        "days_present": len(present),
        "missing_dates": missing,
        "ga4": ga4_status,
        "totals": totals,
        "kpis": kpis,
        "secondary": secondary,
        "by_page": by_page,
        "notes": notes,
        "scoreboard": SCOREBOARD,
        "goals": {
            "completed_form": "baseline pending",
            "sessions_to_completed_form": "2%",
            "start_to_completed_form": "25%",
            "page_contribution": "no % goal",
            "sessions_to_start_diagnostic": {
                "site": "8%",
                "home": "6%",
                "city_landers": "12%",
                "ny_incentives": "10%",
                "calculator_direct": "70%",
            },
        },
        "contract": {
            "lead_definition": (
                "Completed form submit: estimate_submit (calculator contact-complete) "
                "plus wix_form_submit (/contact-me complete Submit)."
            ),
            "contact_me": "Counts as a completed form in volume and sessions → completed form.",
            "scoreboard": SCOREBOARD,
            "start_to_form": "Calculator-only: estimate_submit / estimate_start. contact-me excluded from numerator.",
            "warehouse": DAILY_COLLECTION,
            "ga4_measurement_id": GA4_MEASUREMENT_ID,
            "ga4_env": [GA4_PROPERTY_ID_ENV, GA4_SERVICE_ACCOUNT_JSON_ENV, FIREBASE_SERVICE_ACCOUNT_JSON_ENV],
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def compute_month(db: firestore.Client, *, year: int, month: int) -> dict[str, Any]:
    docs = read_month_docs(db, year, month)
    return aggregate_daily_docs(docs, year=year, month=month)


def render_html(year: int, month: int, nav_css: str = "", nav_html: str = "") -> str:
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Website Funnel</title>
  <style>
    :root {
      --bg:#f5f7fa; --card:#fff; --border:#e8ecf0; --text:#111827; --muted:#6b7280; --muted2:#9ca3af;
      --green:#00C853; --blue:#2196F3; --red:#dc2626; --amber:#d97706;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { padding:22px; max-width:1180px; margin:0 auto; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:14px; background:var(--card); border:1px solid var(--border); box-shadow:0 1px 3px rgba(17,24,39,.05); }
    .title { font-size:22px; font-weight:900; color:#1a2b4a; letter-spacing:-.02em; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:820px; }
    .accentline { height:3px; width:220px; border-radius:999px; background:linear-gradient(90deg,var(--green) 0%, var(--blue) 55%, rgba(33,150,243,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(0,200,83,.10); border-color:rgba(0,200,83,.45); color:#0a7a34; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f2f5; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--green); border-color:var(--green); color:#fff; font-weight:900; cursor:pointer; }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.06); }
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-6 { grid-column:span 6; } .span-12 { grid-column:span 12; }
    .card-title { font-size:13px; font-weight:800; color:var(--muted); }
    .kpi { font-size:36px; font-weight:950; margin-top:8px; letter-spacing:-.02em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .goal { margin-top:6px; font-size:12px; font-weight:800; color:#334155; }
    .status-hit { color:#047857; }
    .status-miss { color:var(--red); }
    .status-baseline_pending, .status-informational, .status-unknown { color:var(--amber); }
    .banner { grid-column:span 12; padding:12px 14px; border-radius:12px; border:1px solid #fde68a; background:#fffbeb; color:#92400e; font-size:13px; font-weight:700; }
    .banner.hidden { display:none; }
    table { width:100%; border-collapse:collapse; }
    th, td { border-bottom:1px solid var(--border); padding:9px 10px; text-align:left; font-size:13px; }
    th { color:#64748b; font-weight:900; background:#fafbfc; }
    .jsonlink { color:#0a7a34; font-weight:800; text-decoration:none; }
    .section-label { grid-column:span 12; margin-top:4px; font-size:12px; font-weight:900; letter-spacing:.04em; text-transform:uppercase; color:#64748b; }
    @media (max-width:980px) { .span-3,.span-4,.span-6,.span-12 { grid-column:span 12; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:28px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Website Funnel</div>
        <div class="subtitle">Scoreboard: sessions → start → completed form. A lead is a completed form submit. Calculator contact-complete and /contact-me Submit both count. Sessions → completed form is site-wide. Start → completed form is calculator-only so /contact-me does not distort it.</div>
        <div class="accentline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter"><div class="filter-label">Month</div><select id="month"></select></div>
        <button id="apply">Apply</button>
      </div>
    </div>

    <div class="grid">
      <div id="statusBanner" class="banner hidden"></div>

      <div class="section-label">Primary — sessions → start → completed form</div>
      <div class="card span-3">
        <div class="card-title">Completed form</div>
        <div class="kpi" id="kpiForms">—</div>
        <div class="goal">Volume goal: baseline pending</div>
        <div class="meta">Calculator + /contact-me completed forms. 14-day baseline pending.</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Sessions → completed form</div>
        <div class="kpi" id="kpiSessionForm">—</div>
        <div class="goal">Goal 2%</div>
        <div class="meta" id="kpiSessionFormStatus">completed form / sessions</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Start → completed form</div>
        <div class="kpi" id="kpiStartForm">—</div>
        <div class="goal">Goal 25%</div>
        <div class="meta" id="kpiStartFormStatus">Calculator-only: start → completed form (estimate_submit / estimate_start)</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Page contribution</div>
        <div class="kpi" id="kpiPageShare">—</div>
        <div class="goal">No % goal</div>
        <div class="meta">Share of completed forms by first page_group</div>
      </div>

      <div class="card span-12">
        <div class="card-title">Page contribution</div>
        <div class="meta" style="margin-bottom:10px">Share of completed forms by first page_group. /contact-me counts. Rows: home / buffalo / rochester / syracuse / ny-incentives / calculator / contact-me. <a class="jsonlink" id="jsonLink" href="#">JSON</a></div>
        <table id="pageTable">
          <thead>
            <tr><th>Page</th><th>Sessions</th><th>Starts</th><th>Completed forms</th><th>Form share</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="section-label">Secondary — diagnostic only, not scored this week</div>
      <div class="card span-4">
        <div class="card-title">Address complete</div>
        <div class="kpi" id="kpiAddress">—</div>
        <div class="meta" id="kpiAddressMeta">Drop-off from start. Not scored.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Bill complete</div>
        <div class="kpi" id="kpiBill">—</div>
        <div class="meta" id="kpiBillMeta">Drop-off from address complete. Not scored.</div>
      </div>
      <div class="card span-4">
        <div class="card-title">Sessions → start</div>
        <div class="kpi" id="kpiSessionStart">—</div>
        <div class="goal">Diagnostic goals: site 8%, home 6%, city 12%, ny-incentives 10%, calculator-direct 70%</div>
        <div class="meta" id="kpiSessionStartDetail">Not scored this week.</div>
      </div>
    </div>
  </div>
<script>
var defaultYear = __YEAR__;
var defaultMonth = __MONTH__;
var yearSel = document.getElementById('year');
var monthSel = document.getElementById('month');
function setOptions(sel, options, value) {
  sel.innerHTML = '';
  options.forEach(function(opt) {
    var o = document.createElement('option');
    o.value = String(opt.value);
    o.textContent = opt.label;
    if (String(opt.value) === String(value)) o.selected = true;
    sel.appendChild(o);
  });
}
var years = [];
for (var y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
var months = [];
for (var i = 0; i < 12; i++) months.push({value: i + 1, label: new Date(2000, i, 1).toLocaleString('en-US', {month: 'long'})});
setOptions(yearSel, years, defaultYear);
setOptions(monthSel, months, defaultMonth);
function query() {
  return new URLSearchParams({ year: yearSel.value, month: monthSel.value, format: 'json' }).toString();
}
function pct(v) {
  if (v == null || v === '') return '—';
  return (Number(v) * 100).toFixed(1) + '%';
}
function num(v) {
  if (v == null || v === '') return '—';
  return String(v);
}
function setStatus(el, status, fallback) {
  if (!el) return;
  el.className = 'meta status-' + (status || 'unknown');
  el.textContent = fallback || status || '';
}
function paintKpi(id, text, status) {
  var el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'kpi status-' + (status || 'unknown');
}
async function load() {
  var q = query();
  document.getElementById('jsonLink').href = '/api/website_funnel?' + q;
  var banner = document.getElementById('statusBanner');
  var res = await fetch('/api/website_funnel?' + q);
  var data = await res.json();
  if (!res.ok) {
    banner.classList.remove('hidden');
    banner.textContent = data.error || 'Failed to load Website Funnel.';
    return;
  }
  var notes = data.notes || [];
  if (!data.days_present || data.ga4 === 'not_configured' || data.ga4 === 'missing_docs' || (data.missing_dates || []).length) {
    banner.classList.remove('hidden');
    banner.textContent = notes.join(' ');
  } else {
    banner.classList.add('hidden');
  }
  var k = data.kpis || {};
  var secondary = data.secondary || {};
  var share = ((k.page_contribution || {}).value) || {};
  paintKpi('kpiForms', num((k.completed_form || {}).value), 'baseline_pending');
  paintKpi('kpiSessionForm', pct((k.sessions_to_completed_form || {}).value), (k.sessions_to_completed_form || {}).status);
  setStatus(document.getElementById('kpiSessionFormStatus'), (k.sessions_to_completed_form || {}).status, 'Goal 2% · completed form / sessions');
  paintKpi('kpiStartForm', pct((k.start_to_completed_form || {}).value), (k.start_to_completed_form || {}).status);
  setStatus(document.getElementById('kpiStartFormStatus'), (k.start_to_completed_form || {}).status, 'Goal 25% · start → completed form');
  var topShare = null;
  Object.keys(share).forEach(function(key) {
    if (share[key] == null) return;
    if (topShare == null || share[key] > topShare) topShare = share[key];
  });
  paintKpi('kpiPageShare', pct(topShare), 'informational');

  paintKpi('kpiAddress', num(((secondary.address_complete || {}).value)), 'informational');
  document.getElementById('kpiAddressMeta').textContent =
    'From start: ' + pct((secondary.address_complete || {}).rate_from_start) +
    ' · drop-off ' + pct((secondary.address_complete || {}).drop_off_from_start) + ' · not scored';
  paintKpi('kpiBill', num(((secondary.bill_complete || {}).value)), 'informational');
  document.getElementById('kpiBillMeta').textContent =
    'From start: ' + pct((secondary.bill_complete || {}).rate_from_start) +
    ' · drop-off from address ' + pct((secondary.bill_complete || {}).drop_off_from_address) + ' · not scored';
  var surfaces = ((secondary.sessions_to_start || {}).by_surface) || {};
  paintKpi('kpiSessionStart', pct((secondary.sessions_to_start || {}).value), 'informational');
  document.getElementById('kpiSessionStartDetail').textContent =
    'site ' + pct((surfaces.site || {}).value) +
    ' · home ' + pct((surfaces.home || {}).value) +
    ' · city ' + pct((surfaces.city_landers || {}).value) +
    ' · ny-incentives ' + pct((surfaces.ny_incentives || {}).value) +
    ' · calculator-direct ' + pct((surfaces.calculator_direct || {}).value) +
    ' · not scored';

  var rows = [
    ['home', 'home'],
    ['city_buffalo', 'buffalo'],
    ['city_rochester', 'rochester'],
    ['city_syracuse', 'syracuse'],
    ['ny_incentives', 'ny-incentives'],
    ['calculator', 'calculator'],
    ['contact_me', 'contact-me']
  ];
  var byPage = data.by_page || {};
  var tbody = document.querySelector('#pageTable tbody');
  tbody.innerHTML = rows.map(function(pair) {
    var g = pair[0], label = pair[1], b = byPage[g] || {};
    return '<tr><td>' + label + '</td><td>' + num(b.sessions) + '</td><td>' + num(b.starts) +
      '</td><td>' + num(b.completed_forms) + '</td><td>' + pct(share[g]) + '</td></tr>';
  }).join('');
}
document.getElementById('apply').addEventListener('click', load);
load();
</script>
</body>
</html>
"""
    return (
        html.replace("__YEAR__", str(year))
        .replace("__MONTH__", str(month))
        .replace("__DASHBOARD_NAV_CSS__", nav_css)
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )
