# -*- coding: utf-8 -*-

"""Website Funnel metric family.

North star: session → estimate start → submit → GHL contact + website-attributed
opportunity. CRM (GHL) is the source of truth for “lead”.

This is NOT Opportunities Created. That contract excludes Inbound/Lead Locker,
where website leads land. Do not read or write lead-gen field
hd5QqHEOVSsPom5bJ32P. Do not use Sold Date P9oBjgbZjJdeE0OkBj9T.

Warehouse: Firestore DB happy-solar (FIRESTORE_DATABASE_ID) collection
web_funnel_daily_v1 — one doc per America/New_York date (id YYYY-MM-DD).

Cost rules:
- Dashboard month view reads ≤31 daily docs. Never streams ghl_*.
- Rollup uses a createdAt range query on ghl_opportunities_v2, then get_all
  contacts for that website-opp set only (same bound pattern as compute_sales).
- If a createdAt range query is impossible (missing index / type mismatch),
  GHL lead counts are taken only from daily warehouse docs — no 4k+ scan.
- Not on warm_cache. Not hourly.

GA4 (optional):
- Measurement ID G-V02RZFR4SZ (locked).
- Env GA4_PROPERTY_ID = numeric GA4 property id (required to pull traffic).
- Env GA4_SERVICE_ACCOUNT_JSON optional; else FIREBASE_SERVICE_ACCOUNT_JSON.
- If creds/property are missing, write nulls for session/start/submit and
  set ga4="not_configured". Do not fake traffic.

Charles lock (2026-08-19): website field constants are names-only
(Website Landing Page, Website Page Group, Website UTM, GA Client ID).
Do not invent IDs. Do not call GHL to create fields. Do not use Secret
Manager or any API key. Real IDs arrive in a later follow-up.
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

# --- Locked contract constants ------------------------------------------------

METRIC_NAME = "Website Funnel"
TIMEZONE_NAME = "America/New_York"
DAILY_COLLECTION = "web_funnel_daily_v1"
OPP_COLLECTION = "ghl_opportunities_v2"
CONTACT_COLLECTION = "ghl_contacts_v2"

GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID_ENV = "GA4_PROPERTY_ID"
GA4_SERVICE_ACCOUNT_JSON_ENV = "GA4_SERVICE_ACCOUNT_JSON"
FIREBASE_SERVICE_ACCOUNT_JSON_ENV = "FIREBASE_SERVICE_ACCOUNT_JSON"

# Charles lock 2026-08-19: names-only. Do not invent IDs. Do not call GHL to
# create fields. Do not use Secret Manager or any API key. Real IDs arrive
# in a later follow-up. Until then, match contact/opportunity customFields
# by these names, plus opportunity.source == "website".
WEBSITE_LANDING_PAGE_FIELD_NAME = "Website Landing Page"
WEBSITE_PAGE_GROUP_FIELD_NAME = "Website Page Group"
WEBSITE_UTM_FIELD_NAME = "Website UTM"
GA_CLIENT_ID_FIELD_NAME = "GA Client ID"
WEBSITE_FIELD_NAMES: tuple[str, ...] = (
    WEBSITE_LANDING_PAGE_FIELD_NAME,
    WEBSITE_PAGE_GROUP_FIELD_NAME,
    WEBSITE_UTM_FIELD_NAME,
    GA_CLIENT_ID_FIELD_NAME,
)

WEBSITE_SOURCE_VALUE = "website"

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

PAGE_TABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("home", "home"),
    ("city_buffalo", "buffalo"),
    ("city_rochester", "rochester"),
    ("city_syracuse", "syracuse"),
    ("ny_incentives", "ny-incentives"),
    ("calculator", "calculator"),
    ("contact_me", "contact-me"),
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
    "estimate_submit": "submits",
    "wix_form_submit": "wix_form_submits",
}

# Locked scoreboard goals (America/New_York).
GOAL_SESSION_TO_GHL = 0.015
GOAL_SUBMIT_TO_GHL = 0.95
GOAL_START_TO_SUBMIT = 0.25
GOAL_SESSION_TO_START_SITE = 0.08
GOAL_SESSION_TO_START_HOME = 0.06
GOAL_SESSION_TO_START_CITY = 0.12
GOAL_SESSION_TO_START_NY_INCENTIVES = 0.10
GOAL_SESSION_TO_START_CALCULATOR = 0.70
GOAL_ORPHANS = 0
GOAL_ATTRIBUTED_COVERAGE = 0.90

KPI_NAMES: tuple[str, ...] = (
    "GHL website leads",
    "Session → GHL lead",
    "Submit → GHL lead",
    "Estimate start → submit",
    "Session → estimate start",
    "Page contribution",
    "Orphan Wix submits",
    "Attributed source coverage",
)

EMPTY_PAGE_BUCKET = {
    "sessions": 0,
    "starts": 0,
    "submits": 0,
    "ghl_leads": 0,
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


def ny_day_window(date_ymd: str) -> tuple[datetime, datetime, str, str]:
    parsed = parse_date_ymd(date_ymd)
    if not parsed:
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    year, month, day = parsed
    tz = ZoneInfo(TIMEZONE_NAME)
    start_local = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local, start_local.isoformat(), end_local.isoformat()


def month_dates(year: int, month: int) -> list[str]:
    last = monthrange(year, month)[1]
    return [f"{year:04d}-{month:02d}-{day:02d}" for day in range(1, last + 1)]


def parse_iso_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


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


def _cf_name(cf: dict[str, Any]) -> str:
    for key in ("name", "key", "fieldName", "field", "label"):
        text = compact_str(cf.get(key))
        if text:
            return text
    return ""


def custom_field_value(entity: dict[str, Any] | None, *, field_name: str) -> Any:
    """Match customFields by locked field name only. No invented IDs."""
    if not isinstance(entity, dict):
        return None
    want_name = compact_str(field_name).casefold()
    if not want_name:
        return None
    for cf in entity.get("customFields") or []:
        if not isinstance(cf, dict):
            continue
        if _cf_name(cf).casefold() != want_name:
            continue
        value = cf.get("value")
        if value in (None, ""):
            value = cf.get("fieldValueString")
        return value
    return None


def is_website_attributed(
    opportunity: dict[str, Any] | None,
    contact: dict[str, Any] | None,
) -> bool:
    opp = opportunity if isinstance(opportunity, dict) else {}
    source = compact_str(opp.get("source")).casefold()
    if source == WEBSITE_SOURCE_VALUE:
        return True
    for field_name in WEBSITE_FIELD_NAMES:
        if is_filled(custom_field_value(contact, field_name=field_name)):
            return True
        if is_filled(custom_field_value(opp, field_name=field_name)):
            return True
    return False


def lead_attribution(
    opportunity: dict[str, Any] | None,
    contact: dict[str, Any] | None,
) -> dict[str, Any]:
    landing = custom_field_value(contact, field_name=WEBSITE_LANDING_PAGE_FIELD_NAME)
    if not is_filled(landing):
        landing = custom_field_value(opportunity, field_name=WEBSITE_LANDING_PAGE_FIELD_NAME)
    page_group_raw = custom_field_value(contact, field_name=WEBSITE_PAGE_GROUP_FIELD_NAME)
    if is_filled(page_group_raw):
        page_group = normalize_page_group(page_group_raw)
    else:
        page_group = page_group_from_landing(landing)
    utm = custom_field_value(contact, field_name=WEBSITE_UTM_FIELD_NAME)
    if not is_filled(utm):
        utm = custom_field_value(opportunity, field_name=WEBSITE_UTM_FIELD_NAME)
    source = compact_str((opportunity or {}).get("source")) or compact_str(utm) or "unknown"
    return {
        "landing_page": compact_str(landing),
        "page_group": page_group,
        "utm": compact_str(utm),
        "source": source,
        "attributed": is_filled(landing) and is_filled(utm),
    }


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


def ga4_credentials_available() -> bool:
    property_id = compact_str(os.environ.get(GA4_PROPERTY_ID_ENV))
    creds_json = os.environ.get(GA4_SERVICE_ACCOUNT_JSON_ENV) or os.environ.get(FIREBASE_SERVICE_ACCOUNT_JSON_ENV)
    return bool(property_id and creds_json)


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
        return {
            "ga4": "not_configured",
            "sessions": None,
            "cta_clicks": None,
            "starts": None,
            "address_complete": None,
            "bill_complete": None,
            "submits": None,
            "wix_form_submits": None,
            "by_page": empty_by_page(),
            "error": None,
            "env": {
                "property_id_env": GA4_PROPERTY_ID_ENV,
                "service_account_env": GA4_SERVICE_ACCOUNT_JSON_ENV,
                "service_account_fallback_env": FIREBASE_SERVICE_ACCOUNT_JSON_ENV,
                "measurement_id": GA4_MEASUREMENT_ID,
            },
        }

    property_id = compact_str(os.environ.get(GA4_PROPERTY_ID_ENV))
    token = _ga4_access_token()
    if not token:
        return {
            "ga4": "not_configured",
            "sessions": None,
            "cta_clicks": None,
            "starts": None,
            "address_complete": None,
            "bill_complete": None,
            "submits": None,
            "wix_form_submits": None,
            "by_page": empty_by_page(),
            "error": "ga4_token_refresh_failed",
            "env": {
                "property_id_env": GA4_PROPERTY_ID_ENV,
                "service_account_env": GA4_SERVICE_ACCOUNT_JSON_ENV,
                "service_account_fallback_env": FIREBASE_SERVICE_ACCOUNT_JSON_ENV,
                "measurement_id": GA4_MEASUREMENT_ID,
            },
        }

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
        return {
            "ga4": "not_configured",
            "sessions": None,
            "cta_clicks": None,
            "starts": None,
            "address_complete": None,
            "bill_complete": None,
            "submits": None,
            "wix_form_submits": None,
            "by_page": empty_by_page(),
            "error": f"ga4_run_report_failed: {exc}",
            "env": {
                "property_id_env": GA4_PROPERTY_ID_ENV,
                "service_account_env": GA4_SERVICE_ACCOUNT_JSON_ENV,
                "service_account_fallback_env": FIREBASE_SERVICE_ACCOUNT_JSON_ENV,
                "measurement_id": GA4_MEASUREMENT_ID,
            },
        }

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
        elif field == "submits":
            bucket["submits"] += count

    return {
        "ga4": "ok",
        "sessions": totals.get("sessions", 0),
        "cta_clicks": totals.get("cta_clicks", 0),
        "starts": totals.get("starts", 0),
        "address_complete": totals.get("address_complete", 0),
        "bill_complete": totals.get("bill_complete", 0),
        "submits": totals.get("submits", 0),
        "wix_form_submits": totals.get("wix_form_submits", 0),
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


def _query_opps_created_in_window(db: firestore.Client, start_local: datetime, end_local: datetime) -> list[Any] | None:
    """Bounded createdAt range query. Never a full ghl_opportunities_v2 stream.

    Returns None when Firestore cannot bound by date (missing index / type).
    """
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    start_iso = start_utc.isoformat().replace("+00:00", "Z")
    end_iso = end_utc.isoformat().replace("+00:00", "Z")
    col = db.collection(OPP_COLLECTION)

    attempts = (
        (start_iso, end_iso),
        (start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
        (start_utc, end_utc),
    )
    last_error: Exception | None = None
    last_empty: list[Any] | None = None
    for lower, upper in attempts:
        try:
            snaps = list(col.where("createdAt", ">=", lower).where("createdAt", "<", upper).stream())
            if snaps:
                return snaps
            last_empty = snaps
        except Exception as exc:
            last_error = exc
            continue
    if last_empty is not None:
        return last_empty
    if last_error is not None:
        return None
    return []


def fetch_contacts_by_ids(db: firestore.Client, contact_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Bounded get_all by contactId from the website-opp set only."""
    needed = list(dict.fromkeys(cid for cid in (compact_str(x) for x in contact_ids) if cid))
    contacts: dict[str, dict[str, Any]] = {}
    refs = [db.collection(CONTACT_COLLECTION).document(cid) for cid in needed]
    for i in range(0, len(refs), 300):
        for snap in db.get_all(refs[i : i + 300]):
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            cid = compact_str(data.get("id") or snap.id)
            if cid:
                contacts[cid] = data
            contacts[compact_str(snap.id)] = data
    for cid in needed:
        if cid in contacts:
            continue
        misses = list(db.collection(CONTACT_COLLECTION).where("id", "==", cid).limit(1).stream())
        if misses:
            data = misses[0].to_dict() or {}
            contacts[cid] = data
    return contacts


def compute_ghl_website_leads_for_day(db: firestore.Client, date_ymd: str) -> dict[str, Any]:
    start_local, end_local, start_iso, end_iso = ny_day_window(date_ymd)
    snaps = _query_opps_created_in_window(db, start_local, end_local)
    if snaps is None:
        return {
            "ghl": "warehouse_only",
            "ghl_leads": None,
            "attributed_leads": None,
            "by_page": empty_by_page(),
            "by_source": {},
            "contact_me_leads": None,
            "note": (
                "Could not bound ghl_opportunities_v2 by createdAt without a full "
                "collection stream. GHL lead counts come only from daily warehouse docs."
            ),
            "window_start_local": start_iso,
            "window_end_local": end_iso,
        }

    needed_ids: list[str] = []
    opp_rows: list[dict[str, Any]] = []
    for snap in snaps:
        opp = snap.to_dict() or {}
        created = parse_iso_dt(opp.get("createdAt"))
        if created is None:
            continue
        created_local = created.astimezone(start_local.tzinfo)
        if not (start_local <= created_local < end_local):
            continue
        cid = compact_str(opp.get("contactId"))
        opp_rows.append({"opp": opp, "contactId": cid})
        if cid:
            needed_ids.append(cid)

    contacts = fetch_contacts_by_ids(db, needed_ids)
    leads: dict[str, dict[str, Any]] = {}
    for row in opp_rows:
        contact = contacts.get(row["contactId"]) if row["contactId"] else None
        if not is_website_attributed(row["opp"], contact):
            continue
        cid = row["contactId"] or compact_str((row["opp"] or {}).get("id"))
        if not cid or cid in leads:
            continue
        leads[cid] = lead_attribution(row["opp"], contact)

    by_page = empty_by_page()
    by_source: dict[str, int] = {}
    attributed = 0
    contact_me = 0
    for lead in leads.values():
        group = lead.get("page_group") if lead.get("page_group") in PAGE_GROUPS else "other"
        by_page[group]["ghl_leads"] += 1
        if group == "contact_me":
            contact_me += 1
        if lead.get("attributed"):
            attributed += 1
        source = compact_str(lead.get("source")) or "unknown"
        by_source[source] = by_source.get(source, 0) + 1

    return {
        "ghl": "createdAt_range",
        "ghl_leads": len(leads),
        "attributed_leads": attributed,
        "by_page": by_page,
        "by_source": by_source,
        "contact_me_leads": contact_me,
        "note": "Distinct contactId with a website-attributed opportunity created in the NY day.",
        "window_start_local": start_iso,
        "window_end_local": end_iso,
        "field_names": list(WEBSITE_FIELD_NAMES),
    }


def merge_by_page(
    ga4_by_page: dict[str, dict[str, Any]] | None,
    ghl_by_page: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, int | None]]:
    out = empty_by_page()
    for group in PAGE_GROUPS:
        ga_bucket = (ga4_by_page or {}).get(group) or {}
        ghl_bucket = (ghl_by_page or {}).get(group) or {}
        out[group] = {
            "sessions": ga_bucket.get("sessions"),
            "starts": ga_bucket.get("starts"),
            "submits": ga_bucket.get("submits"),
            "ghl_leads": int(ghl_bucket.get("ghl_leads") or 0) if ghl_bucket.get("ghl_leads") is not None else ghl_bucket.get("ghl_leads"),
        }
        if out[group]["ghl_leads"] is None:
            out[group]["ghl_leads"] = 0
        for key in ("sessions", "starts", "submits"):
            if out[group][key] is None:
                continue
            out[group][key] = int(out[group][key] or 0)
    return out


def compute_orphans(wix_form_submits: int | None, contact_me_leads: int | None, ga4_status: str) -> int:
    if ga4_status != "ok" or wix_form_submits is None:
        return 0
    leads = int(contact_me_leads or 0)
    return max(int(wix_form_submits) - leads, 0)


def build_daily_doc(date_ymd: str, ga4: dict[str, Any], ghl: dict[str, Any]) -> dict[str, Any]:
    ga4_status = compact_str(ga4.get("ga4")) or "not_configured"
    orphans = compute_orphans(ga4.get("wix_form_submits"), ghl.get("contact_me_leads"), ga4_status)
    return {
        "date": date_ymd,
        "sessions": ga4.get("sessions"),
        "cta_clicks": ga4.get("cta_clicks"),
        "starts": ga4.get("starts"),
        "address_complete": ga4.get("address_complete"),
        "bill_complete": ga4.get("bill_complete"),
        "submits": ga4.get("submits"),
        "wix_form_submits": ga4.get("wix_form_submits"),
        "ghl_leads": ghl.get("ghl_leads"),
        "orphans": orphans,
        "attributed_leads": ghl.get("attributed_leads"),
        "by_page": merge_by_page(ga4.get("by_page"), ghl.get("by_page")),
        "by_source": ghl.get("by_source") or {},
        "ga4": ga4_status,
        "ghl": ghl.get("ghl"),
        "ghl_note": ghl.get("note"),
        "ga4_error": ga4.get("error"),
        "measurement_id": GA4_MEASUREMENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def rollup_day(db: firestore.Client, date_ymd: str | None = None) -> dict[str, Any]:
    date_key = date_ymd or yesterday_ny_date()
    if not parse_date_ymd(date_key):
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    ga4 = fetch_ga4_event_counts(date_key)
    ghl = compute_ghl_website_leads_for_day(db, date_key)
    doc = build_daily_doc(date_key, ga4, ghl)
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

    totals = {
        "sessions": _sum_optional([row.get("sessions") for row in docs]),
        "cta_clicks": _sum_optional([row.get("cta_clicks") for row in docs]),
        "starts": _sum_optional([row.get("starts") for row in docs]),
        "address_complete": _sum_optional([row.get("address_complete") for row in docs]),
        "bill_complete": _sum_optional([row.get("bill_complete") for row in docs]),
        "submits": _sum_optional([row.get("submits") for row in docs]),
        "wix_form_submits": _sum_optional([row.get("wix_form_submits") for row in docs]),
        "ghl_leads": _sum_optional([row.get("ghl_leads") for row in docs]),
        "orphans": _sum_optional([row.get("orphans") for row in docs]) or 0,
        "attributed_leads": _sum_optional([row.get("attributed_leads") for row in docs]),
    }

    by_page = empty_by_page()
    by_source: dict[str, int] = {}
    for row in docs:
        page_map = row.get("by_page") or {}
        for group in PAGE_GROUPS:
            bucket = page_map.get(group) or {}
            for key in ("sessions", "starts", "submits", "ghl_leads"):
                if bucket.get(key) is None:
                    continue
                by_page[group][key] += int(bucket.get(key) or 0)
        source_map = row.get("by_source") or {}
        if isinstance(source_map, dict):
            for source, count in source_map.items():
                try:
                    by_source[str(source)] = by_source.get(str(source), 0) + int(count or 0)
                except Exception:
                    continue

    session_to_ghl = ratio(totals["ghl_leads"], totals["sessions"])
    submit_to_ghl = ratio(totals["ghl_leads"], totals["submits"])
    start_to_submit = ratio(totals["submits"], totals["starts"])
    session_to_start = ratio(totals["starts"], totals["sessions"])
    attributed_coverage = ratio(totals["attributed_leads"], totals["ghl_leads"])

    def group_rate(group: str) -> float | None:
        bucket = by_page.get(group) or {}
        return ratio(bucket.get("starts"), bucket.get("sessions"))

    city_starts = sum(int((by_page[g].get("starts") or 0)) for g in CITY_LANDER_GROUPS)
    city_sessions = sum(int((by_page[g].get("sessions") or 0)) for g in CITY_LANDER_GROUPS)
    city_rate = ratio(city_starts, city_sessions)

    page_share: dict[str, float | None] = {}
    lead_total = totals["ghl_leads"] or 0
    for group in PAGE_GROUPS:
        leads = int((by_page[group].get("ghl_leads") or 0))
        page_share[group] = (leads / lead_total) if lead_total > 0 else None

    notes = [
        "/contact-me submits are orphans until wired; do not count as leads.",
        "CRM is the source of truth for lead. This family is not Opportunities Created.",
        "Volume goal for GHL website leads is baseline pending until a 14-day baseline exists.",
    ]
    if not docs:
        notes.append("No daily warehouse docs for this month. Run /api/web_funnel_rollup.")
    elif missing:
        notes.append(f"Missing {len(missing)} daily warehouse doc(s): {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}.")
    if ga4_status == "not_configured":
        notes.append("GA4 is not_configured. Session/start/submit are null — traffic was not faked.")
    elif ga4_status == "partial":
        notes.append("Some daily docs have ga4=not_configured or are incomplete.")
    if any(compact_str(row.get("ghl")) == "warehouse_only" for row in docs):
        notes.append("Some days stored GHL counts as warehouse_only because opportunities could not be date-bounded without a stream.")

    kpis = {
        "ghl_website_leads": {
            "name": "GHL website leads",
            "value": totals["ghl_leads"],
            "goal": None,
            "goal_label": "baseline pending",
            "status": "baseline_pending",
        },
        "session_to_ghl_lead": {
            "name": "Session → GHL lead",
            "value": session_to_ghl,
            "goal": GOAL_SESSION_TO_GHL,
            "goal_label": "1.5%",
            "status": score_vs_goal(session_to_ghl, GOAL_SESSION_TO_GHL),
        },
        "submit_to_ghl_lead": {
            "name": "Submit → GHL lead",
            "value": submit_to_ghl,
            "goal": GOAL_SUBMIT_TO_GHL,
            "goal_label": "≥95%",
            "status": score_vs_goal(submit_to_ghl, GOAL_SUBMIT_TO_GHL),
        },
        "estimate_start_to_submit": {
            "name": "Estimate start → submit",
            "value": start_to_submit,
            "goal": GOAL_START_TO_SUBMIT,
            "goal_label": "25%",
            "status": score_vs_goal(start_to_submit, GOAL_START_TO_SUBMIT),
        },
        "session_to_estimate_start": {
            "name": "Session → estimate start",
            "value": session_to_start,
            "goal": GOAL_SESSION_TO_START_SITE,
            "goal_label": "site 8%",
            "status": score_vs_goal(session_to_start, GOAL_SESSION_TO_START_SITE),
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
        "page_contribution": {
            "name": "Page contribution",
            "value": page_share,
            "goal": None,
            "goal_label": "no % goal",
            "status": "informational",
        },
        "orphan_wix_submits": {
            "name": "Orphan Wix submits",
            "value": totals["orphans"],
            "goal": GOAL_ORPHANS,
            "goal_label": "0",
            "status": score_vs_goal(float(totals["orphans"]), float(GOAL_ORPHANS), higher_is_better=False),
        },
        "attributed_source_coverage": {
            "name": "Attributed source coverage",
            "value": attributed_coverage,
            "goal": GOAL_ATTRIBUTED_COVERAGE,
            "goal_label": "≥90%",
            "status": score_vs_goal(attributed_coverage, GOAL_ATTRIBUTED_COVERAGE),
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
        "by_page": by_page,
        "by_source": dict(sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0]))),
        "notes": notes,
        "goals": {
            "ghl_website_leads": "baseline pending",
            "session_to_ghl_lead": "1.5%",
            "submit_to_ghl_lead": "≥95%",
            "estimate_start_to_submit": "25%",
            "session_to_estimate_start": {
                "site": "8%",
                "home": "6%",
                "city_landers": "12%",
                "ny_incentives": "10%",
                "calculator_direct": "70%",
            },
            "page_contribution": "no % goal",
            "orphan_wix_submits": 0,
            "attributed_source_coverage": "≥90%",
        },
        "contract": {
            "lead_definition": (
                "Distinct contactId with a new website-attributed opportunity. "
                "Time = ghl_opportunities_v2.createdAt (America/New_York)."
            ),
            "website_attribution": (
                "opportunity.source == 'website' (case-insensitive) OR any of "
                "Website Landing Page / Website Page Group / Website UTM / GA Client ID is non-empty."
            ),
            "field_names": list(WEBSITE_FIELD_NAMES),
            "field_ids": "pending Charles follow-up — names-only until then",
            "excluded": {
                "lead_gen_source_field": "hd5QqHEOVSsPom5bJ32P not read or written",
                "sold_date_field": "P9oBjgbZjJdeE0OkBj9T not used",
                "opportunities_created": "Inbound/Lead Locker excluded there; website leads land there",
            },
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
    @media (max-width:980px) { .span-3,.span-4,.span-6,.span-12 { grid-column:span 12; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .kpi { font-size:28px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Website Funnel</div>
        <div class="subtitle">Session → estimate start → submit → GHL contact + website-attributed opportunity. CRM is the source of truth for lead. /contact-me submits are orphans until wired; do not count as leads.</div>
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

      <div class="card span-3">
        <div class="card-title">GHL website leads</div>
        <div class="kpi" id="kpiLeads">—</div>
        <div class="goal">Volume goal: baseline pending</div>
        <div class="meta">Distinct contactId · createdAt NY day</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Session → GHL lead</div>
        <div class="kpi" id="kpiSessionLead">—</div>
        <div class="goal">Goal 1.5%</div>
        <div class="meta" id="kpiSessionLeadStatus"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Submit → GHL lead</div>
        <div class="kpi" id="kpiSubmitLead">—</div>
        <div class="goal">Goal ≥95% · below 95% is a wiring incident</div>
        <div class="meta" id="kpiSubmitLeadStatus"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Estimate start → submit</div>
        <div class="kpi" id="kpiStartSubmit">—</div>
        <div class="goal">Goal 25%</div>
        <div class="meta" id="kpiStartSubmitStatus"></div>
      </div>
      <div class="card span-6">
        <div class="card-title">Session → estimate start</div>
        <div class="kpi" id="kpiSessionStart">—</div>
        <div class="goal">Goals: site 8%, home 6%, city landers 12%, /ny-incentives 10%, calculator-direct 70%</div>
        <div class="meta" id="kpiSessionStartDetail"></div>
      </div>
      <div class="card span-3">
        <div class="card-title">Orphan Wix submits</div>
        <div class="kpi" id="kpiOrphans">—</div>
        <div class="goal">Goal 0</div>
        <div class="meta">/contact-me (or other Wix forms) with no GHL contact in 24h. Not leads.</div>
      </div>
      <div class="card span-3">
        <div class="card-title">Attributed source coverage</div>
        <div class="kpi" id="kpiCoverage">—</div>
        <div class="goal">Goal ≥90%</div>
        <div class="meta">Website leads with landing page + utm filled</div>
      </div>

      <div class="card span-12">
        <div class="card-title">Page contribution</div>
        <div class="meta" style="margin-bottom:10px">Share of leads by first page_group. No % goal. Rows: home / buffalo / rochester / syracuse / ny-incentives / calculator / contact-me. <a class="jsonlink" id="jsonLink" href="#">JSON</a></div>
        <table id="pageTable">
          <thead>
            <tr><th>Page</th><th>Sessions</th><th>Starts</th><th>Submits</th><th>GHL leads</th><th>Lead share</th></tr>
          </thead>
          <tbody></tbody>
        </table>
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
  paintKpi('kpiLeads', num((k.ghl_website_leads || {}).value), 'baseline_pending');
  paintKpi('kpiSessionLead', pct((k.session_to_ghl_lead || {}).value), (k.session_to_ghl_lead || {}).status);
  setStatus(document.getElementById('kpiSessionLeadStatus'), (k.session_to_ghl_lead || {}).status, 'Goal 1.5%');
  paintKpi('kpiSubmitLead', pct((k.submit_to_ghl_lead || {}).value), (k.submit_to_ghl_lead || {}).status);
  setStatus(document.getElementById('kpiSubmitLeadStatus'), (k.submit_to_ghl_lead || {}).status, 'Goal ≥95%');
  paintKpi('kpiStartSubmit', pct((k.estimate_start_to_submit || {}).value), (k.estimate_start_to_submit || {}).status);
  setStatus(document.getElementById('kpiStartSubmitStatus'), (k.estimate_start_to_submit || {}).status, 'Goal 25%');
  paintKpi('kpiSessionStart', pct((k.session_to_estimate_start || {}).value), (k.session_to_estimate_start || {}).status);
  var surfaces = ((k.session_to_estimate_start || {}).by_surface) || {};
  document.getElementById('kpiSessionStartDetail').textContent =
    'site ' + pct((surfaces.site || {}).value) +
    ' · home ' + pct((surfaces.home || {}).value) +
    ' · city landers ' + pct((surfaces.city_landers || {}).value) +
    ' · /ny-incentives ' + pct((surfaces.ny_incentives || {}).value) +
    ' · calculator-direct ' + pct((surfaces.calculator_direct || {}).value);
  paintKpi('kpiOrphans', num((k.orphan_wix_submits || {}).value), (k.orphan_wix_submits || {}).status);
  paintKpi('kpiCoverage', pct((k.attributed_source_coverage || {}).value), (k.attributed_source_coverage || {}).status);

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
  var share = ((k.page_contribution || {}).value) || {};
  var tbody = document.querySelector('#pageTable tbody');
  tbody.innerHTML = rows.map(function(pair) {
    var g = pair[0], label = pair[1], b = byPage[g] || {};
    return '<tr><td>' + label + '</td><td>' + num(b.sessions) + '</td><td>' + num(b.starts) +
      '</td><td>' + num(b.submits) + '</td><td>' + num(b.ghl_leads) + '</td><td>' + pct(share[g]) + '</td></tr>';
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
