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

Yesterday snapshot (8:00 America/New_York routine):
- GET /api/website_funnel_yesterday reads one daily doc.
- Optional write first: GET /api/web_funnel_rollup (yesterday NY).
- The yesterday read does not auto-rollup.
- Lead for that payload is estimate_submit only (calculator / wny).
- Monthly scoreboard still includes /contact-me wix_form_submit.
- Missing doc or ga4 not_configured/failed → ready=false and nulls.
  Do not invent counts. Do not treat a missing source as 0 traffic.

Cost rules:
- Dashboard month view reads ≤31 daily docs.
- Yesterday read is one document get / get_all. No collection stream.
- Rollup pulls optional GA4 event counts for one NY day.
- Does not read CRM opportunity or contact collections.
- Not on warm_cache. Not hourly.

GA4 (optional):
- Measurement ID G-V02RZFR4SZ (locked). Property 408492342 / stream G-V02RZFR4SZ.
- Yadmada G-VTL7ZW6NPN is on the same property; host allowlist drops it.
- Env GA4_PROPERTY_ID = numeric property id (required to pull traffic).
- Env GA4_SERVICE_ACCOUNT_JSON optional; else FIREBASE_SERVICE_ACCOUNT_JSON.
- If creds/property are missing, write nulls and set ga4="not_configured".
  Do not fake traffic.
- Hold page_view (do not switch sessions to session_start).
- One runReport per day. Dimensions: eventName + pagePath + hostName + pageLocation.

Host / QA exclusions (lock):
- Allowlist only: www.happyslr.com, happyslr.com, wny.happyslr.com.
  Drop Vercel preview hosts, localhost, yadmada.com, gtm-msr.appspot.com,
  everything else.
- Drop events where debug_mode is true (dimension or pageLocation).
- Drop events where traffic_type=internal or URL/session flag internal=1
  (pageLocation query or dimension, if present).
- Drop events at 24 Hawkstone Way (standing lock Evan 2026-08-26).
  Reason test_address. Evan testing, not a live lead. Event-level grain
  matches debug/internal (no sessionId). Case-insensitive, collapsed
  whitespace; extra city/state/zip after the street still matches.
  124 Hawkstone Way is not a match. Scan address, estimate_address,
  customEvent:address, pageLocation, and pagePath. Do not add a second
  runReport. Do not invent a GTM parameter as a new Data API dimension.
- debug_mode and traffic_type are not standard Data API dimensions.
  pageLocation can see ?internal=1 when Designer adds that live flag.
  Do not invent a tester IP list.
- visits_total = page_view on www.happyslr.com + happyslr.com.
- visits_wny = page_view on wny.happyslr.com.
- sessions is kept equal to visits_total (scoreboard / yesterday).
- completed_forms = estimate_submit + wix_form_submit after those filters.
  Preview-host QA forms (Aug 19 estimate_* on *.vercel.app) do not count.
  24 Hawkstone Way rows never count in visits/sessions, estimate_start,
  estimate_address_complete, estimate_bill_complete, estimate_submit,
  wix_form_submit, completed_forms, or the 2-week form-goal score.
"""

from __future__ import annotations

import json
import os
import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

METRIC_NAME = "Website Funnel"
TIMEZONE_NAME = "America/New_York"
DAILY_COLLECTION = "web_funnel_daily_v1"

GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID = "408492342"
GA4_PROPERTY_ID_ENV = "GA4_PROPERTY_ID"
GA4_SERVICE_ACCOUNT_JSON_ENV = "GA4_SERVICE_ACCOUNT_JSON"
FIREBASE_SERVICE_ACCOUNT_JSON_ENV = "FIREBASE_SERVICE_ACCOUNT_JSON"

HOST_WWW = "www.happyslr.com"
HOST_APEX = "happyslr.com"
HOST_WNY = "wny.happyslr.com"
LIVE_TOTAL_HOSTS = frozenset({HOST_WWW, HOST_APEX})
LIVE_WNY_HOSTS = frozenset({HOST_WNY})
LIVE_FORM_HOSTS = LIVE_TOTAL_HOSTS | LIVE_WNY_HOSTS
EXCLUDED_HOST_EXAMPLES = (
    "yadmada.com",
    "www.yadmada.com",
    "vercel.app",
    "localhost",
    "gtm-msr.appspot.com",
)
GA4_REPORT_DIMENSIONS = ("eventName", "pagePath", "hostName", "pageLocation")
# Not standard Data API dimensions today. pageLocation can see ?internal=1.
GA4_MISSING_EXCLUSION_DIMENSIONS = ("debug_mode", "traffic_type")
TEST_ADDRESS_STREET = "24 hawkstone way"
TEST_ADDRESS_LOCK_DATE = "2026-08-26"
TEST_ADDRESS_PATTERN = re.compile(r"(?<!\d)24 hawkstone way")

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

YESTERDAY_NOT_READY_REASON = "source isn't ready"
YESTERDAY_LEAD_FIELD = "estimate_submit"
YESTERDAY_SCOPE = "calculator"
YESTERDAY_SITE = "wny.happyslr.com"
YESTERDAY_METRIC_FIELDS = (
    "sessions",
    "estimate_start",
    "address_complete",
    "bill_complete",
    "estimate_submit",
    "session_to_submit",
    "start_to_submit",
)
YESTERDAY_READY_GA4 = frozenset({"ok"})

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
        datetime(year, month, day)
        return year, month, day
    except Exception:
        return None


def resolve_query_date(value: str | None) -> str:
    text = compact_str(value).casefold()
    if not text or text == "yesterday":
        return yesterday_ny_date()
    parsed = parse_date_ymd(value)
    if not parsed:
        raise ValueError("Invalid date; expected YYYY-MM-DD or yesterday")
    year, month, day = parsed
    return f"{year:04d}-{month:02d}-{day:02d}"


def ny_calendar_day_window(date_ymd: str) -> dict[str, str]:
    parsed = parse_date_ymd(date_ymd)
    if not parsed:
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    year, month, day = parsed
    tz = ZoneInfo(TIMEZONE_NAME)
    start = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
    end = datetime(year, month, day, 23, 59, 59, 999999, tzinfo=tz)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": TIMEZONE_NAME,
        "kind": "calendar_day",
    }


def month_dates(year: int, month: int) -> list[str]:
    last = monthrange(year, month)[1]
    return [f"{year:04d}-{month:02d}-{day:02d}" for day in range(1, last + 1)]


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_host_name(raw: Any) -> str:
    text = compact_str(raw).casefold()
    if not text:
        return ""
    if "://" in text or text.startswith("//"):
        try:
            parsed = urlparse(text if "://" in text else f"https:{text}")
            text = compact_str(parsed.hostname).casefold()
        except Exception:
            text = text.split("/")[0]
    text = text.split("/")[0]
    if "@" in text:
        text = text.split("@")[-1]
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    else:
        text = text.split(":")[0]
    if text.startswith("www.") and text not in LIVE_TOTAL_HOSTS:
        # keep www.happyslr.com as-is; do not promote other www hosts
        pass
    return text.rstrip(".")


def classify_host(raw: Any) -> str:
    """Return total | wny | excluded. Allowlist only — everything else is dropped."""
    host = normalize_host_name(raw)
    if host in LIVE_TOTAL_HOSTS:
        return "total"
    if host in LIVE_WNY_HOSTS:
        return "wny"
    return "excluded"


def _flag_true(values: Any) -> bool:
    if values is None:
        return False
    if isinstance(values, (list, tuple)):
        parts = values
    else:
        parts = [values]
    for raw in parts:
        text = compact_str(raw).casefold()
        if text in {"1", "true", "yes", "on"}:
            return True
    return False


def _is_internal_traffic_type(value: Any) -> bool:
    return compact_str(value).casefold() == "internal"


def path_from_page_location(raw: Any) -> str:
    text = compact_str(raw)
    if not text:
        return ""
    try:
        parsed = urlparse(text if "://" in text else f"https://dummy{text if text.startswith('/') else '/' + text}")
        return parsed.path or "/"
    except Exception:
        return text


def page_location_flags(raw: Any) -> dict[str, bool]:
    """Read URL/session flags from pageLocation. Missing param is not a flag."""
    text = compact_str(raw)
    out = {"internal": False, "debug_mode": False, "traffic_type_internal": False}
    if not text:
        return out
    try:
        parsed = urlparse(text if "://" in text else f"https://dummy{text if text.startswith('/') else '/' + text}")
        query = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return out
    if _flag_true(query.get("internal")):
        out["internal"] = True
    if _flag_true(query.get("debug_mode")) or _flag_true(query.get("debugMode")):
        out["debug_mode"] = True
    traffic = compact_str((query.get("traffic_type") or query.get("trafficType") or [""])[0])
    if _is_internal_traffic_type(traffic):
        out["traffic_type_internal"] = True
    return out


def _normalize_address_haystack(value: Any) -> str:
    """Collapse whitespace/punctuation and URL encoding for address matching."""
    text = compact_str(value)
    if not text:
        return ""
    try:
        text = unquote(text.replace("+", " "))
    except Exception:
        text = text.replace("+", " ")
    cleaned = []
    for ch in text:
        cleaned.append(ch if ch.isalnum() or ch.isspace() else " ")
    return compact_str("".join(cleaned)).casefold()


def is_test_address(value: Any) -> bool:
    """True for 24 Hawkstone Way; 124 Hawkstone Way is not a match."""
    haystack = _normalize_address_haystack(value)
    if not haystack:
        return False
    return bool(TEST_ADDRESS_PATTERN.search(haystack))


def exclusion_reason(
    *,
    host_name: Any,
    page_location: Any = None,
    debug_mode: Any = None,
    traffic_type: Any = None,
    internal: Any = None,
    address: Any = None,
    estimate_address: Any = None,
    page_path: Any = None,
    custom_event_address: Any = None,
) -> str | None:
    """Why a row is dropped. Host allowlist first (drops the known Aug 19 preview form)."""
    if classify_host(host_name) == "excluded":
        return "host"
    if _flag_true(debug_mode):
        return "debug_mode"
    if _is_internal_traffic_type(traffic_type) or _flag_true(internal):
        return "internal"
    flags = page_location_flags(page_location)
    if flags["debug_mode"]:
        return "debug_mode"
    if flags["internal"] or flags["traffic_type_internal"]:
        return "internal"
    for candidate in (address, estimate_address, custom_event_address, page_location, page_path):
        if is_test_address(candidate):
            return "test_address"
    return None


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
