# -*- coding: utf-8 -*-

"""Website Traffic Dashboard v1 — live Marketing metrics.

GET /api/website_traffic (HTML + ?format=json).

Sources:
- GA4 Data API property 408492342 / measurement G-V02RZFR4SZ
- Warehouse web_funnel_daily_v1 (≤31 get_all docs, no collection stream)
- Warehouse web_funnel_named_fills_v1 (bounded per-date queries)

Locks:
- Funnel TOP = estimate/LP visits (/estimate + legacy wny calc), NOT all-site.
- Brand site sessions = separate Overview KPI.
- Test filter ON by default (Hawkstone / Stonebridge / Test Test / Evan Day /
  adchday@gmail.com / evanrday23@gmail.com / preview/debug/internal).
- Instant Form / 3PL are not website leads. Submit = estimate_submit only.
- Named fills = Marketing aggregates only. PII stays gated.
- Do not invent Meta spend. Meta strip stays not_wired.
- Form freeze: this module does not change the calculator form.

Reuse website_funnel helpers: host allowlist, SA envs, test exclusions.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

_METRICS_DIR = Path(__file__).resolve().parent
if str(_METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(_METRICS_DIR))

TIMEZONE_NAME = "America/New_York"
METRIC_NAME = "Website Traffic"
MAX_RANGE_DAYS = 31
NAMED_FILLS_RANGE_LIMIT = 200
GA4_REPORT_LIMIT = "10000"
PRIMARY_CTA = "www.happyslr.com/estimate"
NAMED_FILL_SOURCE_NEW_SITE = "new-site-estimate"
ACQUISITION_CHART_LIMIT = 10
PATH_PRIOR_DAY_CAP = 14

TILE_LIVE = "live"
TILE_EXAMPLE = "example"
TILE_NOT_WIRED = "not_wired"

OVERVIEW_METRICS = (
    "sessions",
    "totalUsers",
    "newUsers",
    "screenPageViews",
    "bounceRate",
    "engagementRate",
    "averageSessionDuration",
)
PATH_DIMENSIONS = ("hostName", "pagePath")
ACQUISITION_DIMENSIONS = (
    "sessionDefaultChannelGroup",
    "sessionSource",
    "sessionMedium",
)
FB_SOURCE_TOKENS = ("facebook", "fb.com", "instagram", "ig", "meta")
PAID_MEDIUM_TOKENS = ("cpc", "ppc", "paid", "paidsocial", "paid_social", "cpm", "cpa")

_FUNNEL = None
_TEST = None
FUNNEL_MODULE_NAME = "hs_website_funnel_metric"
_DEGRADE_GA4_PROPERTY_ID = "408492342"
_DEGRADE_GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
_DEGRADE_DAILY_COLLECTION = "web_funnel_daily_v1"
_DEGRADE_NAMED_FILLS_COLLECTION = "web_funnel_named_fills_v1"
_DEGRADE_HOSTS = ("happyslr.com", "wny.happyslr.com", "www.happyslr.com")


def _ready_module(module, name: str | None = None) -> bool:
    """True only for a finished exec. Never treat a loading/partial module as ready."""
    if module is None:
        return False
    if getattr(module, "_hs_loading", False):
        return False
    if name == FUNNEL_MODULE_NAME and not callable(getattr(module, "exclusion_reason", None)):
        return False
    if getattr(module, "_hs_exec_complete", False):
        return True
    return any(not key.startswith("_") for key in vars(module))


def _load_module(name: str, path: Path):
    cached = sys.modules.get(name)
    if _ready_module(cached, name):
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    setattr(module, "_hs_loading", True)
    try:
        spec.loader.exec_module(module)
        setattr(module, "_hs_loading", False)
        setattr(module, "_hs_exec_complete", True)
        sys.modules[name] = module
        return module
    except Exception:
        current = sys.modules.get(name)
        if current is module or not _ready_module(current, name):
            sys.modules.pop(name, None)
        raise


def _funnel_has_exclusion_reason(module) -> bool:
    return callable(getattr(module, "exclusion_reason", None))


def _clear_funnel_load_cache() -> None:
    global _FUNNEL
    _FUNNEL = None
    cached = sys.modules.get(FUNNEL_MODULE_NAME)
    if cached is not None and not _funnel_has_exclusion_reason(cached):
        sys.modules.pop(FUNNEL_MODULE_NAME, None)


def _load_and_install_funnel():
    funnel = _load_module(FUNNEL_MODULE_NAME, _METRICS_DIR / "website_funnel.py")
    if not _funnel_has_exclusion_reason(funnel):
        return funnel
    patch = _load_module("hs_funnel_test_address", _METRICS_DIR / "funnel_test_address.py")
    return patch.install(funnel)


def funnel_mod():
    global _FUNNEL
    if _funnel_has_exclusion_reason(_FUNNEL):
        return _FUNNEL
    funnel = _load_and_install_funnel()
    if _funnel_has_exclusion_reason(funnel):
        _FUNNEL = funnel
        return _FUNNEL
    _clear_funnel_load_cache()
    funnel = _load_and_install_funnel()
    if not _funnel_has_exclusion_reason(funnel):
        _FUNNEL = None
        raise AttributeError(
            f"module '{FUNNEL_MODULE_NAME}' has no attribute 'exclusion_reason'"
        )
    _FUNNEL = funnel
    return _FUNNEL


def test_mod():
    global _TEST
    if _TEST is not None:
        return _TEST
    _TEST = _load_module("hs_funnel_test_address", _METRICS_DIR / "funnel_test_address.py")
    return _TEST


def get_db():
    return funnel_mod().get_db()


def compact_str(value: Any) -> str:
    return funnel_mod().compact_str(value)


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio(numerator: int | None, denominator: int | None) -> float | None:
    return funnel_mod().ratio(numerator, denominator)


def ny_now() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE_NAME))


def parse_date_ymd(value: str | None) -> date | None:
    text = compact_str(value)
    if not text:
        return None
    try:
        year, month, day = [int(part) for part in text.split("-")]
        return date(year, month, day)
    except Exception:
        return None


def default_range(now: datetime | None = None) -> tuple[str, str]:
    today = (now or ny_now()).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def prior_range(start: str, end: str) -> tuple[str, str]:
    start_d = parse_date_ymd(start)
    end_d = parse_date_ymd(end)
    if start_d is None or end_d is None or end_d < start_d:
        raise ValueError("Invalid date range")
    length = (end_d - start_d).days + 1
    prior_end = start_d - timedelta(days=1)
    prior_start = prior_end - timedelta(days=length - 1)
    return prior_start.isoformat(), prior_end.isoformat()


def dates_inclusive(start: str, end: str) -> list[str]:
    start_d = parse_date_ymd(start)
    end_d = parse_date_ymd(end)
    if start_d is None or end_d is None:
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    if (end_d - start_d).days + 1 > MAX_RANGE_DAYS:
        start_d = end_d - timedelta(days=MAX_RANGE_DAYS - 1)
    out: list[str] = []
    cursor = start_d
    while cursor <= end_d:
        out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def resolve_range(start: str | None, end: str | None, now: datetime | None = None) -> tuple[str, str]:
    default_start, default_end = default_range(now)
    start_key = compact_str(start) or default_start
    end_key = compact_str(end) or default_end
    dates = dates_inclusive(start_key, end_key)
    return dates[0], dates[-1]


def normalize_path(raw: Any) -> str:
    text = compact_str(raw)
    if not text:
        return ""
    try:
        parsed = urlparse(text if "://" in text else f"https://x{text if text.startswith('/') else '/' + text}")
        path = parsed.path or "/"
    except Exception:
        path = text
    path = path.split("?")[0].rstrip("/") or "/"
    return path.casefold()


def is_estimate_lp_path(raw: Any) -> bool:
    """/estimate (and nested) plus legacy calculator paths."""
    path = normalize_path(raw)
    if not path:
        return False
    if path == "/estimate" or path.startswith("/estimate/"):
        return True
    if "calculator" in path:
        return True
    return False


def visit_bucket(host_name: Any, page_path: Any) -> str | None:
    """brand | estimate_lp | None (excluded). Funnel top is estimate_lp only."""
    funnel = funnel_mod()
    kind = funnel.classify_host(host_name)
    if kind == "excluded":
        return None
    if kind == "wny":
        return "estimate_lp"
    if is_estimate_lp_path(page_path):
        return "estimate_lp"
    return "brand"


def host_allowed_for_domain(host_name: Any, domain: str) -> bool:
    funnel = funnel_mod()
    kind = funnel.classify_host(host_name)
    domain_key = compact_str(domain).casefold() or "all"
    if kind == "excluded":
        return False
    if domain_key in {"wny", "wny.happyslr.com"}:
        return kind == "wny"
    if domain_key in {"happyslr.com", "www.happyslr.com", "brand"}:
        return kind == "total"
    return kind in {"total", "wny"}


def classify_facebook(source: Any, medium: Any, channel: Any) -> str | None:
    src = compact_str(source).casefold()
    med = compact_str(medium).casefold().replace(" ", "")
    ch = compact_str(channel).casefold()
    is_fb = any(token in src for token in FB_SOURCE_TOKENS)
    if not is_fb:
        if "paid social" in ch or "organic social" in ch:
            is_fb = True
        else:
            return None
    if "paid" in ch or any(token in med for token in PAID_MEDIUM_TOKENS):
        return "paid"
    if "organic" in ch or med in {"organic", "social", "referral", "none", "(none)", ""}:
        return "organic"
    return "other"


def tile(status: str, **extra: Any) -> dict[str, Any]:
    out = {"status": status}
    out.update(extra)
    return out


def _sum_optional(values: list[Any]) -> int | None:
    present = [int(v) for v in values if v is not None]
    if not present and all(v is None for v in values):
        return None
    return sum(present)


def pct_delta(current: int | float | None, prior: int | float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return (float(current) - float(prior)) / float(prior)


def format_seconds(value: float | None) -> str | None:
    if value is None:
        return None
    total = max(int(round(value)), 0)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}m {seconds:02d}s"


def live_host_filter() -> dict[str, Any]:
    funnel = funnel_mod()
    return {
        "filter": {
            "fieldName": "hostName",
            "inListFilter": {"values": sorted(funnel.LIVE_FORM_HOSTS)},
        }
    }


def parse_ga4_generic_rows(
    report: dict[str, Any] | None,
    dimension_names: tuple[str, ...] | list[str],
    metric_names: tuple[str, ...] | list[str],
) -> list[dict[str, Any]]:
    dims = [compact_str(name) for name in dimension_names]
    mets = [compact_str(name) for name in metric_names]
    rows: list[dict[str, Any]] = []
    for row in (report or {}).get("rows") or []:
        dim_vals = [cell.get("value") for cell in (row.get("dimensionValues") or [])]
        met_vals = [cell.get("value") for cell in (row.get("metricValues") or [])]
        item = {dims[i]: compact_str(dim_vals[i]) for i in range(min(len(dims), len(dim_vals)))}
        for i, name in enumerate(mets):
            raw = met_vals[i] if i < len(met_vals) else None
            if name in {"bounceRate", "engagementRate", "averageSessionDuration"}:
                item[name] = optional_float(raw)
            else:
                item[name] = optional_int(raw) if raw not in (None, "") else 0
        rows.append(item)
    return rows


def run_ga4_report(body: dict[str, Any]) -> dict[str, Any]:
    funnel = funnel_mod()
    if not funnel.ga4_credentials_available():
        return {"ga4": "not_configured", "rows": [], "error": None}
    property_id = compact_str(
        __import__("os").environ.get(funnel.GA4_PROPERTY_ID_ENV)
    ) or funnel.GA4_PROPERTY_ID
    token = funnel._ga4_access_token()
    if not token:
        return {"ga4": "not_configured", "rows": [], "error": "ga4_token_refresh_failed"}
    import urllib.request

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
        return {"ga4": "failed", "rows": [], "error": f"ga4_run_report_failed: {exc}"}
    return {"ga4": "ok", "report": report, "error": None}


def fetch_ga4_overview(start: str, end: str, prior_start: str, prior_end: str) -> dict[str, Any]:
    body = {
        "dateRanges": [
            {"startDate": start, "endDate": end, "name": "current"},
            {"startDate": prior_start, "endDate": prior_end, "name": "prior"},
        ],
        "dimensions": [{"name": "hostName"}, {"name": "dateRange"}],
        "metrics": [{"name": name} for name in OVERVIEW_METRICS],
        "limit": "100",
        "dimensionFilter": live_host_filter(),
    }
    raw = run_ga4_report(body)
    if raw.get("ga4") != "ok":
        return {"ga4": raw.get("ga4") or "not_configured", "error": raw.get("error"), "current": {}, "prior": {}}
    parsed = parse_ga4_generic_rows(raw.get("report"), ("hostName", "dateRange"), OVERVIEW_METRICS)
    summarized = summarize_overview_rows(parsed)
    return {"ga4": "ok", "error": None, "rows": parsed, **summarized}


def summarize_overview_rows(rows: list[dict[str, Any]], domain: str = "all") -> dict[str, Any]:
    buckets = {"current": {}, "prior": {}}
    weights = {"current": {}, "prior": {}}
    for row in rows or []:
        if not host_allowed_for_domain(row.get("hostName"), domain):
            continue
        slot = "prior" if compact_str(row.get("dateRange")).casefold() == "prior" else "current"
        sessions = optional_int(row.get("sessions")) or 0
        dest = buckets[slot]
        dest["sessions"] = int(dest.get("sessions") or 0) + sessions
        dest["totalUsers"] = int(dest.get("totalUsers") or 0) + int(row.get("totalUsers") or 0)
        dest["newUsers"] = int(dest.get("newUsers") or 0) + int(row.get("newUsers") or 0)
        dest["screenPageViews"] = int(dest.get("screenPageViews") or 0) + int(row.get("screenPageViews") or 0)
        w = weights[slot]
        for key in ("bounceRate", "engagementRate", "averageSessionDuration"):
            val = optional_float(row.get(key))
            if val is None:
                continue
            w[key] = (w.get(key) or 0.0) + val * sessions
    for slot in ("current", "prior"):
        dest = buckets[slot]
        sess = dest.get("sessions") or 0
        for key in ("bounceRate", "engagementRate", "averageSessionDuration"):
            if sess > 0 and key in weights[slot]:
                dest[key] = weights[slot][key] / sess
            else:
                dest[key] = None
        if sess <= 0 and not dest:
            buckets[slot] = {}
    return {"current": buckets["current"], "prior": buckets["prior"]}


def normalize_series_date(raw: Any) -> str:
    text = compact_str(raw)
    if not text:
        return ""
    digits = text.replace("-", "")
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def path_row_slot(row: dict[str, Any] | None) -> str:
    slot = compact_str((row or {}).get("date_range") or (row or {}).get("dateRange")).casefold()
    return "prior" if slot == "prior" else "current"


def path_rows_for_slot(rows: list[dict[str, Any]] | None, slot: str) -> list[dict[str, Any]]:
    want = "prior" if slot == "prior" else "current"
    return [row for row in list(rows or []) if isinstance(row, dict) and path_row_slot(row) == want]


def fetch_ga4_paths(start: str, end: str) -> dict[str, Any]:
    """Undated host+path report. Used for range KPIs. Do not add date here."""
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": name} for name in PATH_DIMENSIONS],
        "metrics": [{"name": "eventCount"}],
        "limit": GA4_REPORT_LIMIT,
        "dimensionFilter": {
            "andGroup": {
                "expressions": [
                    live_host_filter(),
                    {
                        "filter": {
                            "fieldName": "eventName",
                            "inListFilter": {"values": ["page_view"]},
                        }
                    },
                ]
            }
        },
    }
    raw = run_ga4_report(body)
    if raw.get("ga4") != "ok":
        return {"ga4": raw.get("ga4") or "not_configured", "error": raw.get("error"), "rows": []}
    parsed = []
    for row in (raw.get("report") or {}).get("rows") or []:
        dims = [cell.get("value") for cell in (row.get("dimensionValues") or [])]
        mets = [cell.get("value") for cell in (row.get("metricValues") or [])]
        parsed.append(
            {
                "host_name": compact_str(dims[0] if dims else ""),
                "page_path": compact_str(dims[1] if len(dims) > 1 else ""),
                "count": optional_int(mets[0] if mets else 0) or 0,
            }
        )
    return {"ga4": "ok", "error": None, "rows": parsed}


def fetch_ga4_paths_daily(
    start: str,
    end: str,
    prior_start: str | None = None,
    prior_end: str | None = None,
) -> dict[str, Any]:
    """Optional dated path report for the trend only. Failure must not touch KPIs."""
    date_ranges = [{"startDate": start, "endDate": end, "name": "current"}]
    include_prior = bool(prior_start and prior_end)
    if include_prior:
        date_ranges.append({"startDate": prior_start, "endDate": prior_end, "name": "prior"})
    dimensions = [{"name": "hostName"}, {"name": "pagePath"}, {"name": "date"}]
    if include_prior:
        dimensions.append({"name": "dateRange"})
    body = {
        "dateRanges": date_ranges,
        "dimensions": dimensions,
        "metrics": [{"name": "eventCount"}],
        "limit": GA4_REPORT_LIMIT,
        "dimensionFilter": {
            "andGroup": {
                "expressions": [
                    live_host_filter(),
                    {
                        "filter": {
                            "fieldName": "eventName",
                            "inListFilter": {"values": ["page_view"]},
                        }
                    },
                ]
            }
        },
    }
    raw = run_ga4_report(body)
    if raw.get("ga4") != "ok":
        return {"ga4": raw.get("ga4") or "not_configured", "error": raw.get("error"), "rows": []}
    parsed = []
    for row in (raw.get("report") or {}).get("rows") or []:
        dims = [cell.get("value") for cell in (row.get("dimensionValues") or [])]
        mets = [cell.get("value") for cell in (row.get("metricValues") or [])]
        parsed.append(
            {
                "host_name": compact_str(dims[0] if dims else ""),
                "page_path": compact_str(dims[1] if len(dims) > 1 else ""),
                "date": normalize_series_date(dims[2] if len(dims) > 2 else ""),
                "date_range": compact_str(dims[3] if len(dims) > 3 else "current") or "current",
                "count": optional_int(mets[0] if mets else 0) or 0,
            }
        )
    return {"ga4": "ok", "error": None, "rows": parsed}


def _path_row_exclusion_reason(
    funnel,
    row: dict[str, Any],
    host_name: Any,
    page_path: Any,
    *,
    test_filter: bool,
) -> str | None:
    """Drop reason for a path row. Never raises if exclusion_reason is missing."""
    reason_fn = getattr(funnel, "exclusion_reason", None)
    classify = getattr(funnel, "classify_host", None)
    if test_filter and callable(reason_fn):
        try:
            return reason_fn(
                host_name=host_name,
                page_location=row.get("page_location") or row.get("pageLocation"),
                debug_mode=row.get("debug_mode"),
                traffic_type=row.get("traffic_type"),
                internal=row.get("internal"),
                page_path=page_path,
                address=row.get("address"),
                email=row.get("email"),
                name=row.get("name"),
            )
        except TypeError:
            return reason_fn(
                host_name=host_name,
                page_location=row.get("page_location") or row.get("pageLocation"),
                debug_mode=row.get("debug_mode"),
                traffic_type=row.get("traffic_type"),
                internal=row.get("internal"),
            )
    if callable(classify) and classify(host_name) == "excluded":
        return "host"
    return None


def summarize_path_rows(
    rows: list[dict[str, Any]],
    *,
    domain: str = "all",
    test_filter: bool = True,
) -> dict[str, Any]:
    funnel = funnel_mod()
    brand = 0
    estimate_lp = 0
    dropped = {"host": 0, "debug_mode": 0, "internal": 0, "test_address": 0, "domain": 0}
    landings: dict[str, int] = {}
    for row in rows or []:
        host_name = row.get("host_name") or row.get("hostName")
        page_path = row.get("page_path") or row.get("pagePath")
        count = optional_int(row.get("count") or row.get("eventCount")) or 0
        reason = _path_row_exclusion_reason(
            funnel, row, host_name, page_path, test_filter=test_filter
        )
        if reason:
            dropped[reason] = dropped.get(reason, 0) + count
            continue
        if test_filter and test_mod().row_has_test_address(row):
            dropped["test_address"] = dropped.get("test_address", 0) + count
            continue
        if not host_allowed_for_domain(host_name, domain):
            dropped["domain"] = dropped.get("domain", 0) + count
            continue
        bucket = visit_bucket(host_name, page_path)
        if bucket == "brand":
            brand += count
        elif bucket == "estimate_lp":
            estimate_lp += count
        else:
            dropped["host"] = dropped.get("host", 0) + count
            continue
        label = landing_label(host_name, page_path)
        landings[label] = landings.get(label, 0) + count
    top = sorted(landings.items(), key=lambda item: (-item[1], item[0]))[:10]
    return {
        "brand_site_sessions": brand,
        "estimate_lp_visits": estimate_lp,
        "all_site_sessions": brand + estimate_lp,
        "dropped": dropped,
        "top_landings": [{"page": name, "sessions": count} for name, count in top],
    }


def landing_label(host_name: Any, page_path: Any) -> str:
    funnel = funnel_mod()
    path = normalize_path(page_path) or "/"
    if funnel.classify_host(host_name) == "wny":
        return f"wny {path} (legacy)"
    return path


def fetch_ga4_acquisition(start: str, end: str) -> dict[str, Any]:
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": name} for name in ACQUISITION_DIMENSIONS],
        "metrics": [{"name": "sessions"}, {"name": "totalUsers"}],
        "limit": "50",
        "dimensionFilter": live_host_filter(),
    }
    raw = run_ga4_report(body)
    if raw.get("ga4") != "ok":
        return {"ga4": raw.get("ga4") or "not_configured", "error": raw.get("error"), "rows": []}
    parsed = parse_ga4_generic_rows(
        raw.get("report"),
        ACQUISITION_DIMENSIONS,
        ("sessions", "totalUsers"),
    )
    return {"ga4": "ok", "error": None, "rows": parsed}


def summarize_acquisition_rows(rows: list[dict[str, Any]], domain: str = "all") -> dict[str, Any]:
    out_rows: list[dict[str, Any]] = []
    fb_organic = 0
    fb_paid = 0
    for row in rows or []:
        channel = compact_str(row.get("sessionDefaultChannelGroup") or row.get("channel")) or "(other)"
        source = compact_str(row.get("sessionSource") or row.get("source")) or "(direct)"
        medium = compact_str(row.get("sessionMedium") or row.get("medium")) or "(none)"
        sessions = optional_int(row.get("sessions")) or 0
        users = optional_int(row.get("totalUsers") or row.get("users")) or 0
        if sessions <= 0 and users <= 0:
            continue
        out_rows.append(
            {
                "channel": channel,
                "source": source,
                "medium": medium,
                "source_medium": f"{source} / {medium}",
                "sessions": sessions,
                "users": users,
            }
        )
        kind = classify_facebook(source, medium, channel)
        if kind == "organic":
            fb_organic += sessions
        elif kind == "paid":
            fb_paid += sessions
    out_rows.sort(key=lambda item: (-int(item["sessions"]), item["channel"], item["source_medium"]))
    return {
        "rows": out_rows[:20],
        "fb_organic": fb_organic,
        "fb_paid": fb_paid,
        "has_facebook": (fb_organic + fb_paid) > 0,
    }


def read_daily_docs(db: Any, dates: list[str]) -> list[dict[str, Any]]:
    """Bounded get_all of web_funnel_daily_v1. No collection stream."""
    funnel = funnel_mod()
    if db is None or not dates:
        return []
    refs = [db.collection(funnel.DAILY_COLLECTION).document(day) for day in dates]
    docs: list[dict[str, Any]] = []
    for i in range(0, len(refs), 300):
        snaps = db.get_all(refs[i : i + 300])
        for snap in snaps:
            if not getattr(snap, "exists", False):
                continue
            data = snap.to_dict() if hasattr(snap, "to_dict") else None
            if not isinstance(data, dict):
                continue
            data["date"] = compact_str(data.get("date") or getattr(snap, "id", ""))
            docs.append(data)
    docs.sort(key=lambda row: row.get("date") or "")
    return docs


def fetch_named_fills_range(db: Any, dates: list[str]) -> list[dict[str, Any]]:
    """Bounded per-date named-fill reads. Not a collection stream."""
    patch = test_mod()
    fills: list[dict[str, Any]] = []
    for day in dates[:MAX_RANGE_DAYS]:
        fills.extend(patch.fetch_named_fills(db, day))
        if len(fills) >= NAMED_FILLS_RANGE_LIMIT:
            break
    return fills[:NAMED_FILLS_RANGE_LIMIT]


def aggregate_named_fills(fills: list[dict[str, Any]] | None, *, test_filter: bool = True) -> dict[str, Any]:
    patch = test_mod()
    rows = [fill for fill in list(fills or []) if isinstance(fill, dict)]
    live = patch.live_named_fills(rows) if test_filter else rows
    excluded = [fill for fill in rows if fill not in live]
    by_source: dict[str, int] = {}
    by_day: dict[str, dict[str, int]] = {}
    for fill in live:
        source = compact_str(fill.get("source")) or "unknown"
        by_source[source] = by_source.get(source, 0) + 1
        day = compact_str(fill.get("date")) or "unknown"
        bucket = by_day.setdefault(day, {"date": day, "live": 0, "excluded": 0})
        bucket["live"] += 1
    for fill in excluded:
        day = compact_str(fill.get("date")) or "unknown"
        bucket = by_day.setdefault(day, {"date": day, "live": 0, "excluded": 0})
        bucket["excluded"] += 1
    return {
        "live_count": len(live),
        "excluded_count": len(excluded),
        "total_count": len(rows),
        "by_source": by_source,
        "by_day": [by_day[key] for key in sorted(by_day)],
        "pii_gated": True,
        "new_site_estimate": int(by_source.get(NAMED_FILL_SOURCE_NEW_SITE) or 0),
        "legacy_wny": int(by_source.get("leads@") or 0),
    }


def named_fill_payload_is_clean(payload: dict[str, Any]) -> bool:
    """Marketing JSON must not carry names, emails, phones, or addresses."""
    text = json.dumps(payload.get("named_fills") or {}, default=str).casefold()
    forbidden = ("@", "phone", "address", "hawkstone", "stonebridge")
    # source emails in the exclude *list* are allowed on filters, not named_fills.
    return "gmail.com" not in text and "verizon.net" not in text and "msn.com" not in text


def warehouse_totals(docs: list[dict[str, Any]], domain: str = "all") -> dict[str, Any]:
    domain_key = compact_str(domain).casefold() or "all"
    visits_total = _sum_optional([row.get("visits_total") for row in docs])
    visits_wny = _sum_optional([row.get("visits_wny") for row in docs])
    if domain_key in {"wny", "wny.happyslr.com"}:
        brand = 0 if visits_wny is not None else None
        estimate = visits_wny
        all_site = visits_wny
    elif domain_key in {"happyslr.com", "www.happyslr.com", "brand"}:
        brand = visits_total
        estimate = 0 if visits_total is not None else None
        all_site = visits_total
    else:
        brand = visits_total
        estimate = visits_wny
        if visits_total is None and visits_wny is None:
            all_site = None
        else:
            all_site = int(visits_total or 0) + int(visits_wny or 0)
    starts = _sum_optional([row.get("starts") if row.get("starts") is not None else row.get("estimate_start") for row in docs])
    return {
        "visits_total": visits_total,
        "visits_wny": visits_wny,
        "brand_site_sessions": brand,
        "estimate_lp_visits": estimate,
        "all_site_sessions": all_site,
        "starts": starts,
        "address_complete": _sum_optional([row.get("address_complete") for row in docs]),
        "bill_complete": _sum_optional([row.get("bill_complete") for row in docs]),
        "estimate_submit": _sum_optional([row.get("estimate_submit") for row in docs]),
        "cta_clicks": _sum_optional([row.get("cta_clicks") for row in docs]),
        "days_present": len(docs),
        "ga4_ok_days": sum(1 for row in docs if compact_str(row.get("ga4")).casefold() == "ok"),
    }


def empty_series() -> dict[str, Any]:
    """Chart payload with no invented points. EXAMPLE / degrade uses this."""
    return {
        "daily": [],
        "prior_daily": [],
        "funnel": [],
        "acquisition": [],
        "named_fills_by_day": [],
        "source": None,
        "daily_source": None,
    }


def daily_point_from_doc(
    doc: dict[str, Any] | None,
    date_ymd: str,
    domain: str = "all",
) -> dict[str, Any]:
    """One warehouse day. Missing / not-ok / pre-split docs are nulls, not zeros."""
    date_key = compact_str((doc or {}).get("date") or date_ymd)
    empty = {
        "date": date_key,
        "sessions": None,
        "estimate_lp_visits": None,
        "brand_site_sessions": None,
    }
    if not isinstance(doc, dict):
        return empty
    ga4 = compact_str(doc.get("ga4")).casefold()
    if ga4 and ga4 != "ok":
        return empty
    if doc.get("visits_total") is None and doc.get("visits_wny") is None:
        return empty
    totals = warehouse_totals([doc], domain)
    return {
        "date": date_key,
        "sessions": totals["all_site_sessions"],
        "estimate_lp_visits": totals["estimate_lp_visits"],
        "brand_site_sessions": totals["brand_site_sessions"],
    }


def build_daily_series(
    dates: list[str],
    docs: list[dict[str, Any]] | None,
    domain: str = "all",
) -> list[dict[str, Any]]:
    """Range-aligned warehouse series. No docs → empty (not a fake zero series)."""
    rows = [row for row in list(docs or []) if isinstance(row, dict)]
    if not rows:
        return []
    by_date = {
        compact_str(row.get("date")): row for row in rows if compact_str(row.get("date"))
    }
    return [daily_point_from_doc(by_date.get(day), day, domain) for day in dates]


def empty_daily_point(date_ymd: str) -> dict[str, Any]:
    return {
        "date": date_ymd,
        "sessions": None,
        "estimate_lp_visits": None,
        "brand_site_sessions": None,
    }


def build_daily_series_from_path_rows(
    dates: list[str],
    rows: list[dict[str, Any]] | None,
    *,
    domain: str = "all",
    test_filter: bool = True,
) -> list[dict[str, Any]] | None:
    """Daily brand vs estimate/LP from dated GA4 path rows. None = no dates (use warehouse)."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    dated = False
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day = normalize_series_date(row.get("date") or row.get("date_ymd"))
        if not day:
            continue
        dated = True
        by_date.setdefault(day, []).append(row)
    if not dated:
        return None
    points: list[dict[str, Any]] = []
    for day in dates:
        day_rows = by_date.get(day) or []
        if not day_rows:
            points.append(empty_daily_point(day))
            continue
        summary = summarize_path_rows(day_rows, domain=domain, test_filter=test_filter)
        points.append(
            {
                "date": day,
                "sessions": summary["all_site_sessions"],
                "estimate_lp_visits": summary["estimate_lp_visits"],
                "brand_site_sessions": summary["brand_site_sessions"],
            }
        )
    return points


def series_has_values(points: list[dict[str, Any]] | None, *keys: str) -> bool:
    wanted = keys or ("sessions", "estimate_lp_visits", "brand_site_sessions", "live", "value")
    for row in points or []:
        if not isinstance(row, dict):
            continue
        for key in wanted:
            if row.get(key) is not None:
                return True
    return False


def build_funnel_chart_series(funnel: dict[str, Any] | None, *, live: bool) -> list[dict[str, Any]]:
    """Live funnel counts only. Contact stays unwired — no invented step."""
    if not live:
        return []
    f = funnel or {}
    rates = f.get("rates") or {}
    return [
        {
            "key": "estimate_lp",
            "label": "Estimate / LP visits",
            "value": f.get("estimate_lp_visits"),
            "rate": 1.0 if f.get("estimate_lp_visits") is not None else None,
            "wired": True,
        },
        {
            "key": "start",
            "label": "Start",
            "value": f.get("starts"),
            "rate": rates.get("start_of_estimate_lp"),
            "wired": True,
        },
        {
            "key": "address",
            "label": "Address",
            "value": f.get("address"),
            "rate": rates.get("address_of_start"),
            "wired": True,
        },
        {
            "key": "bill",
            "label": "Bill",
            "value": f.get("bill"),
            "rate": rates.get("bill_of_address"),
            "wired": True,
        },
        {
            "key": "contact",
            "label": "Contact",
            "value": None,
            "rate": None,
            "wired": False,
            "status": TILE_EXAMPLE,
        },
        {
            "key": "submit",
            "label": "Submit",
            "value": f.get("submit"),
            "rate": rates.get("submit_of_bill"),
            "wired": True,
        },
        {
            "key": "named_fill",
            "label": "Named fill",
            "value": f.get("named_fill"),
            "rate": rates.get("named_fill_of_submit"),
            "wired": True,
        },
    ]


def build_acquisition_chart_series(
    rows: list[dict[str, Any]] | None,
    *,
    live: bool,
    limit: int = ACQUISITION_CHART_LIMIT,
) -> list[dict[str, Any]]:
    """Top source/medium bars from live acquisition.rows. No Meta spend."""
    if not live:
        return []
    out: list[dict[str, Any]] = []
    for row in list(rows or [])[: max(int(limit), 0)]:
        if not isinstance(row, dict):
            continue
        sessions = optional_int(row.get("sessions"))
        if sessions is None:
            continue
        source_medium = compact_str(row.get("source_medium"))
        channel = compact_str(row.get("channel"))
        out.append(
            {
                "channel": channel,
                "source_medium": source_medium,
                "label": source_medium or channel or "(other)",
                "sessions": sessions,
                "users": optional_int(row.get("users")),
            }
        )
    return out


def build_named_fills_chart_series(
    by_day: list[dict[str, Any]] | None,
    *,
    live: bool,
) -> list[dict[str, Any]]:
    """Existing named_fills.by_day only. No invented days. No PII."""
    if not live:
        return []
    out: list[dict[str, Any]] = []
    for row in by_day or []:
        if not isinstance(row, dict):
            continue
        day = compact_str(row.get("date"))
        if not day:
            continue
        out.append(
            {
                "date": day,
                "live": optional_int(row.get("live")),
                "excluded": optional_int(row.get("excluded")),
            }
        )
    return out


def build_chart_series(
    *,
    dates: list[str],
    prior_dates: list[str],
    daily_docs: list[dict[str, Any]] | None,
    prior_docs: list[dict[str, Any]] | None,
    domain: str,
    compare_prior: bool,
    funnel: dict[str, Any] | None,
    funnel_live: bool,
    acquisition_rows: list[dict[str, Any]] | None,
    acquisition_live: bool,
    named_by_day: list[dict[str, Any]] | None,
    named_live: bool,
    path_rows: list[dict[str, Any]] | None = None,
    path_ok: bool = False,
    test_filter: bool = True,
    kpi_split: str | None = None,
) -> dict[str, Any]:
    daily = []
    prior_daily: list[dict[str, Any]] = []
    daily_source = None
    path_current = path_rows_for_slot(path_rows, "current") if path_ok else []
    path_prior = path_rows_for_slot(path_rows, "prior") if path_ok else []
    path_daily = build_daily_series_from_path_rows(
        dates, path_current, domain=domain, test_filter=test_filter
    )
    if path_daily is not None and series_has_values(path_daily, "sessions", "estimate_lp_visits"):
        daily = path_daily
        daily_source = "ga4_page_path"
        if compare_prior:
            path_prior_daily = build_daily_series_from_path_rows(
                prior_dates, path_prior, domain=domain, test_filter=test_filter
            )
            if path_prior_daily is not None:
                prior_daily = path_prior_daily
    else:
        daily = build_daily_series(dates, daily_docs, domain)
        daily_source = "warehouse" if daily else None
        if compare_prior:
            prior_daily = build_daily_series(prior_dates, prior_docs, domain)
    source = "ga4_page_path" if kpi_split == "ga4_page_path" else ("warehouse" if daily else None)
    return {
        "daily": daily,
        "prior_daily": prior_daily,
        "funnel": build_funnel_chart_series(funnel, live=funnel_live),
        "acquisition": build_acquisition_chart_series(
            acquisition_rows, live=acquisition_live
        ),
        "named_fills_by_day": build_named_fills_chart_series(
            named_by_day, live=named_live
        ),
        "source": source,
        "daily_source": daily_source,
    }


def visits_up_starts_zero(estimate_lp: int | None, starts: int | None) -> bool:
    """Alert uses estimate/LP visits, never all-site sessions."""
    if estimate_lp is None or starts is None:
        return False
    return estimate_lp > 0 and starts == 0


def empty_overview() -> dict[str, Any]:
    return {
        "sessions": None,
        "users": None,
        "new_users": None,
        "returning_users": None,
        "new_share": None,
        "returning_share": None,
        "pageviews": None,
        "pages_per_session": None,
        "bounce_rate": None,
        "engaged_rate": None,
        "avg_engagement_seconds": None,
        "avg_engagement_label": None,
        "brand_site_sessions": None,
        "estimate_calc_sessions": None,
        "cta_taps": None,
        "fb_organic_sessions": None,
        "vs_prior_sessions": None,
    }


def example_degrade_payload(
    *,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """EXAMPLE stub when live compute fails. Null counts — do not invent traffic."""
    start_key, end_key = default_range(now)
    start_d = date.fromisoformat(start_key)
    end_d = date.fromisoformat(end_key)
    length = (end_d - start_d).days + 1
    prior_end_d = start_d - timedelta(days=1)
    prior_start_d = prior_end_d - timedelta(days=length - 1)
    tiles = {
        "overview": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "overview_users": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "overview_brand_vs_estimate": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "acquisition": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "funnel": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "named_fills": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "content": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "audience": tile(TILE_EXAMPLE, reason="extra_ga4_city_device_report_skipped"),
        "cta_taps": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "fb_post_sessions": tile(TILE_EXAMPLE, reason="compute_degraded"),
        "paid_mismatch": tile(TILE_EXAMPLE, reason="landing_x_source_not_queried"),
        "meta_spend": tile(TILE_NOT_WIRED, reason="do_not_invent_meta_spend"),
        "contact_step": tile(TILE_EXAMPLE, reason="no_contact_event"),
    }
    live_fields: list[str] = []
    stub_fields = sorted(
        name for name, info in tiles.items() if info.get("status") in {TILE_EXAMPLE, TILE_NOT_WIRED}
    )
    notes = [
        "EXAMPLE degrade: live payload compute failed. Counts are null; traffic was not invented.",
        "Funnel top is estimate/LP visits (/estimate + legacy wny calc), not all-site sessions.",
        "Instant Form / 3PL are not website leads.",
        "Named fills are Marketing aggregates only. PII stays gated.",
        "Meta spend is not wired and was not invented.",
    ]
    if error:
        notes.append(f"compute_error: {error}")
    named = {
        "live_count": None,
        "excluded_count": None,
        "total_count": None,
        "by_source": {},
        "by_day": [],
        "pii_gated": True,
        "new_site_estimate": None,
        "legacy_wny": None,
    }
    payload = {
        "metric": METRIC_NAME,
        "stub": True,
        "example": True,
        "timezone": TIMEZONE_NAME,
        "start": start_key,
        "end": end_key,
        "prior_start": prior_start_d.isoformat(),
        "prior_end": prior_end_d.isoformat(),
        "domain": "all",
        "test_filter": True,
        "compare_prior": True,
        "ga4_property_id": _DEGRADE_GA4_PROPERTY_ID,
        "ga4_measurement_id": _DEGRADE_GA4_MEASUREMENT_ID,
        "collection": _DEGRADE_DAILY_COLLECTION,
        "named_fills_collection": _DEGRADE_NAMED_FILLS_COLLECTION,
        "primary_cta": PRIMARY_CTA,
        "tiles": tiles,
        "live_fields": live_fields,
        "stub_fields": stub_fields,
        "overview": empty_overview(),
        "acquisition": {"rows": [], "fb_organic": None, "fb_paid": None},
        "funnel": {
            "brand_site_sessions": None,
            "estimate_lp_visits": None,
            "all_site_sessions": None,
            "funnel_top": None,
            "funnel_top_is_all_site": False,
            "starts": None,
            "address": None,
            "bill": None,
            "contact": None,
            "submit": None,
            "named_fill": None,
            "alert_visits_up_starts_zero": False,
            "rates": {
                "start_of_estimate_lp": None,
                "address_of_start": None,
                "bill_of_address": None,
                "submit_of_bill": None,
                "submit_of_estimate_lp": None,
                "start_to_submit": None,
                "named_fill_of_submit": None,
            },
        },
        "named_fills": named,
        "content": {"top_landings": []},
        "series": empty_series(),
        "filters": {
            "test_filter": True,
            "hosts": list(_DEGRADE_HOSTS),
            "estimate_lp": ["/estimate", "wny.happyslr.com legacy calculator"],
            "test_traffic": [
                "24 Hawkstone Way",
                "313 E Stonebridge Dr / 313 East Stonebridge Drive, Gilbert AZ",
                "Test Test",
                "Evan Day",
                "adchday@gmail.com",
                "evanrday23@gmail.com",
                "preview/debug/internal",
            ],
            "instant_form_3pl_are_website_leads": False,
        },
        "sources": {
            "ga4_overview": "degraded",
            "ga4_paths": "degraded",
            "ga4_paths_daily": "degraded",
            "ga4_acquisition": "degraded",
            "warehouse": "degraded",
            "named_fills": "degraded",
            "split": "degraded",
        },
        "reads": {
            "daily_collection": _DEGRADE_DAILY_COLLECTION,
            "daily_ids": [],
            "method": "get_all",
            "count": 0,
            "named_fills_method": "per_date_where_limit_50",
        },
        "notes": notes,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if error:
        payload["error"] = error
    return payload


def compute_website_traffic(
    db: Any = None,
    *,
    start: str | None = None,
    end: str | None = None,
    domain: str = "all",
    test_filter: bool = True,
    compare_prior: bool = True,
    now: datetime | None = None,
    daily_docs: list[dict[str, Any]] | None = None,
    prior_docs: list[dict[str, Any]] | None = None,
    named_fills: list[dict[str, Any]] | None = None,
    ga4_overview: dict[str, Any] | None = None,
    ga4_paths: dict[str, Any] | None = None,
    ga4_paths_daily: dict[str, Any] | None = None,
    ga4_acquisition: dict[str, Any] | None = None,
    fetch_remote: bool = True,
) -> dict[str, Any]:
    funnel = funnel_mod()
    patch = test_mod()
    start_key, end_key = resolve_range(start, end, now)
    dates = dates_inclusive(start_key, end_key)
    prior_start, prior_end = prior_range(start_key, end_key)
    prior_dates = dates_inclusive(prior_start, prior_end)
    domain_key = compact_str(domain).casefold() or "all"

    named_supplied = named_fills is not None
    if daily_docs is None and fetch_remote and db is not None:
        daily_docs = read_daily_docs(db, dates)
    if prior_docs is None and fetch_remote and db is not None and compare_prior:
        prior_docs = read_daily_docs(db, prior_dates)
    if named_fills is None and fetch_remote and db is not None:
        named_fills = fetch_named_fills_range(db, dates)
        named_supplied = True
    if ga4_overview is None and fetch_remote:
        ga4_overview = fetch_ga4_overview(start_key, end_key, prior_start, prior_end)
    if ga4_paths is None and fetch_remote:
        ga4_paths = fetch_ga4_paths(start_key, end_key)
    if ga4_acquisition is None and fetch_remote:
        ga4_acquisition = fetch_ga4_acquisition(start_key, end_key)

    daily_docs = list(daily_docs or [])
    prior_docs = list(prior_docs or [])
    named_fills = list(named_fills or [])
    warehouse = warehouse_totals(daily_docs, domain_key)
    prior_warehouse = warehouse_totals(prior_docs, domain_key) if compare_prior else {}

    path_status = compact_str((ga4_paths or {}).get("ga4"))
    path_summary = summarize_path_rows(
        (ga4_paths or {}).get("rows") or [],
        domain=domain_key,
        test_filter=test_filter,
    ) if path_status == "ok" else None

    if ga4_paths_daily is None and fetch_remote and path_status == "ok":
        want_prior_paths = compare_prior and len(dates) <= PATH_PRIOR_DAY_CAP
        ga4_paths_daily = fetch_ga4_paths_daily(
            start_key,
            end_key,
            prior_start if want_prior_paths else None,
            prior_end if want_prior_paths else None,
        )
    dated_status = compact_str((ga4_paths_daily or {}).get("ga4"))
    dated_rows = list((ga4_paths_daily or {}).get("rows") or []) if dated_status == "ok" else []

    if path_summary is not None:
        brand = path_summary["brand_site_sessions"]
        estimate_lp = path_summary["estimate_lp_visits"]
        all_site = path_summary["all_site_sessions"]
        split_source = "ga4_page_path"
    else:
        brand = warehouse["brand_site_sessions"]
        estimate_lp = warehouse["estimate_lp_visits"]
        all_site = warehouse["all_site_sessions"]
        split_source = "warehouse_host_split"

    named = aggregate_named_fills(named_fills, test_filter=test_filter)
    starts = warehouse["starts"]
    address = warehouse["address_complete"]
    bill = warehouse["bill_complete"]
    submit = warehouse["estimate_submit"]
    cta = warehouse["cta_clicks"]
    if not named_supplied:
        named = {
            "live_count": None,
            "excluded_count": None,
            "total_count": None,
            "by_source": {},
            "by_day": [],
            "pii_gated": True,
            "new_site_estimate": None,
            "legacy_wny": None,
        }

    overview_status = compact_str((ga4_overview or {}).get("ga4"))
    overview_cur = ((ga4_overview or {}).get("current") or {}) if overview_status == "ok" else {}
    overview_prior = ((ga4_overview or {}).get("prior") or {}) if overview_status == "ok" else {}
    if overview_status == "ok" and domain_key != "all" and (ga4_overview or {}).get("rows"):
        split_ov = summarize_overview_rows((ga4_overview or {}).get("rows") or [], domain_key)
        overview_cur = split_ov.get("current") or {}
        overview_prior = split_ov.get("prior") or {}

    users = optional_int(overview_cur.get("totalUsers"))
    new_users = optional_int(overview_cur.get("newUsers"))
    returning = None
    if users is not None and new_users is not None:
        returning = max(users - new_users, 0)
    pageviews = optional_int(overview_cur.get("screenPageViews"))
    ga4_sessions = optional_int(overview_cur.get("sessions"))
    overview_sessions = ga4_sessions if ga4_sessions is not None else all_site

    acq_status = compact_str((ga4_acquisition or {}).get("ga4"))
    acq = summarize_acquisition_rows((ga4_acquisition or {}).get("rows") or []) if acq_status == "ok" else {
        "rows": [],
        "fb_organic": None,
        "fb_paid": None,
        "has_facebook": False,
    }

    warehouse_ready = warehouse["days_present"] > 0 and warehouse["ga4_ok_days"] > 0
    split_ready = path_summary is not None or warehouse_ready
    named_ready = named_supplied
    cta_ready = warehouse_ready and warehouse["cta_clicks"] is not None
    fb_ready = acq_status == "ok" and bool(acq.get("has_facebook"))
    content_ready = path_summary is not None and bool(path_summary.get("top_landings"))
    users_ready = overview_status == "ok" and users is not None

    tiles = {
        "overview": tile(TILE_LIVE if (split_ready or users_ready) else TILE_EXAMPLE, source="warehouse+ga4" if split_ready else None),
        "overview_users": tile(TILE_LIVE if users_ready else TILE_EXAMPLE, source="ga4" if users_ready else None),
        "overview_brand_vs_estimate": tile(TILE_LIVE if split_ready else TILE_EXAMPLE, source=split_source if split_ready else None),
        "acquisition": tile(TILE_LIVE if acq_status == "ok" else TILE_EXAMPLE, source="ga4" if acq_status == "ok" else None),
        "funnel": tile(TILE_LIVE if (split_ready or warehouse_ready or named_ready) else TILE_EXAMPLE),
        "named_fills": tile(TILE_LIVE if named_ready else TILE_EXAMPLE, source=patch.NAMED_FILLS_COLLECTION if named_ready else None),
        "content": tile(TILE_LIVE if content_ready else TILE_EXAMPLE, source="ga4_page_path" if content_ready else None),
        "audience": tile(TILE_EXAMPLE, reason="extra_ga4_city_device_report_skipped"),
        "cta_taps": tile(TILE_LIVE if cta_ready else TILE_EXAMPLE, source="estimate_cta_click" if cta_ready else None),
        "fb_post_sessions": tile(TILE_LIVE if fb_ready else TILE_EXAMPLE, source="ga4_session_source" if fb_ready else None),
        "paid_mismatch": tile(TILE_EXAMPLE, reason="landing_x_source_not_queried"),
        "meta_spend": tile(TILE_NOT_WIRED, reason="do_not_invent_meta_spend"),
        "contact_step": tile(TILE_EXAMPLE, reason="no_contact_event"),
    }
    live_fields = sorted(name for name, info in tiles.items() if info.get("status") == TILE_LIVE)
    stub_fields = sorted(name for name, info in tiles.items() if info.get("status") in {TILE_EXAMPLE, TILE_NOT_WIRED})

    prior_brand = prior_warehouse.get("brand_site_sessions") if compare_prior else None
    prior_estimate = prior_warehouse.get("estimate_lp_visits") if compare_prior else None
    prior_sessions = optional_int(overview_prior.get("sessions")) if compare_prior else None
    if prior_sessions is None and compare_prior:
        prior_sessions = prior_warehouse.get("all_site_sessions")

    leak = visits_up_starts_zero(estimate_lp, starts)
    overview = empty_overview()
    overview.update(
        {
            "sessions": overview_sessions,
            "users": users,
            "new_users": new_users,
            "returning_users": returning,
            "new_share": ratio(new_users, users),
            "returning_share": ratio(returning, users),
            "pageviews": pageviews,
            "pages_per_session": ratio(pageviews, ga4_sessions),
            "bounce_rate": optional_float(overview_cur.get("bounceRate")),
            "engaged_rate": optional_float(overview_cur.get("engagementRate")),
            "avg_engagement_seconds": optional_float(overview_cur.get("averageSessionDuration")),
            "avg_engagement_label": format_seconds(optional_float(overview_cur.get("averageSessionDuration"))),
            "brand_site_sessions": brand,
            "estimate_calc_sessions": estimate_lp,
            "cta_taps": cta if cta_ready else None,
            "fb_organic_sessions": acq.get("fb_organic") if fb_ready else None,
            "vs_prior_sessions": pct_delta(overview_sessions, prior_sessions) if compare_prior else None,
            "vs_prior_brand": pct_delta(brand, prior_brand) if compare_prior else None,
            "vs_prior_estimate": pct_delta(estimate_lp, prior_estimate) if compare_prior else None,
        }
    )

    notes = [
        "Funnel top is estimate/LP visits (/estimate + legacy wny calc), not all-site sessions.",
        "Brand site sessions are a separate Overview KPI.",
        "Instant Form / 3PL are not website leads.",
        "Named fills are Marketing aggregates only. PII stays gated.",
        "Meta spend is not wired and was not invented.",
        "Charles QA before treating preview numbers as live.",
    ]
    if path_summary is None:
        notes.append(
            "Estimate/LP split falls back to warehouse host fields "
            "(visits_total = brand hosts, visits_wny = legacy calc) when the GA4 path report is missing."
        )
    elif dated_status and dated_status != "ok":
        notes.append(
            "Dated GA4 path report failed; range KPIs still use the undated path split. "
            "Daily trend falls back to warehouse host-split days."
        )
    if overview_status != "ok":
        notes.append("GA4 overview users/bounce/engagement stay EXAMPLE until the Data API report succeeds.")
    if acq_status != "ok":
        notes.append("Acquisition stays EXAMPLE until the GA4 channel/source/medium report succeeds.")
    if not warehouse_ready and db is not None:
        notes.append("No web_funnel_daily_v1 docs in range. Run /api/web_funnel_rollup for those NY dates.")
    if test_filter:
        notes.append("Test filter ON: Hawkstone / Stonebridge / Test Test / Evan Day / test emails / preview/debug/internal excluded.")

    payload = {
        "metric": METRIC_NAME,
        "stub": len(live_fields) == 0,
        "example": len(live_fields) == 0,
        "timezone": TIMEZONE_NAME,
        "start": start_key,
        "end": end_key,
        "prior_start": prior_start,
        "prior_end": prior_end,
        "domain": domain_key,
        "test_filter": bool(test_filter),
        "compare_prior": bool(compare_prior),
        "ga4_property_id": funnel.GA4_PROPERTY_ID,
        "ga4_measurement_id": funnel.GA4_MEASUREMENT_ID,
        "collection": funnel.DAILY_COLLECTION,
        "named_fills_collection": patch.NAMED_FILLS_COLLECTION,
        "primary_cta": PRIMARY_CTA,
        "tiles": tiles,
        "live_fields": live_fields,
        "stub_fields": stub_fields,
        "overview": overview,
        "acquisition": {
            "rows": acq.get("rows") or [],
            "fb_organic": acq.get("fb_organic"),
            "fb_paid": acq.get("fb_paid"),
        },
        "funnel": {
            "brand_site_sessions": brand,
            "estimate_lp_visits": estimate_lp,
            "all_site_sessions": all_site,
            "funnel_top": estimate_lp,
            "funnel_top_is_all_site": False,
            "starts": starts,
            "address": address,
            "bill": bill,
            "contact": None,
            "submit": submit,
            "named_fill": named.get("live_count"),
            "alert_visits_up_starts_zero": leak,
            "rates": {
                "start_of_estimate_lp": ratio(starts, estimate_lp),
                "address_of_start": ratio(address, starts),
                "bill_of_address": ratio(bill, address),
                "submit_of_bill": ratio(submit, bill),
                "submit_of_estimate_lp": ratio(submit, estimate_lp),
                "start_to_submit": ratio(submit, starts),
                "named_fill_of_submit": ratio(named.get("live_count"), submit),
            },
        },
        "named_fills": named,
        "content": {
            "top_landings": (path_summary or {}).get("top_landings") or [],
        },
        "series": empty_series(),
        "filters": {
            "test_filter": bool(test_filter),
            "hosts": sorted(funnel.LIVE_FORM_HOSTS),
            "estimate_lp": ["/estimate", "wny.happyslr.com legacy calculator"],
            "test_traffic": [
                "24 Hawkstone Way",
                "313 E Stonebridge Dr / 313 East Stonebridge Drive, Gilbert AZ",
                "Test Test",
                "Evan Day",
                "adchday@gmail.com",
                "evanrday23@gmail.com",
                "preview/debug/internal",
            ],
            "instant_form_3pl_are_website_leads": False,
        },
        "sources": {
            "ga4_overview": overview_status or "not_configured",
            "ga4_paths": path_status or "not_configured",
            "ga4_paths_daily": dated_status or "not_configured",
            "ga4_acquisition": acq_status or "not_configured",
            "warehouse": "ok" if warehouse_ready else ("missing_docs" if db is not None else "not_configured"),
            "named_fills": "ok" if named_ready else "not_configured",
            "split": split_source,
        },
        "reads": {
            "daily_collection": funnel.DAILY_COLLECTION,
            "daily_ids": dates,
            "method": "get_all",
            "count": len(dates),
            "named_fills_method": "per_date_where_limit_50",
        },
        "notes": notes,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    payload["series"] = build_chart_series(
        dates=dates,
        prior_dates=prior_dates,
        daily_docs=daily_docs,
        prior_docs=prior_docs if compare_prior else [],
        domain=domain_key,
        compare_prior=compare_prior,
        funnel=payload["funnel"],
        funnel_live=bool(tiles["funnel"]["status"] == TILE_LIVE),
        acquisition_rows=acq.get("rows") or [],
        acquisition_live=bool(tiles["acquisition"]["status"] == TILE_LIVE),
        named_by_day=named.get("by_day") or [],
        named_live=bool(tiles["named_fills"]["status"] == TILE_LIVE),
        path_rows=dated_rows,
        path_ok=dated_status == "ok",
        test_filter=bool(test_filter),
        kpi_split=split_source,
    )
    return payload


def parse_bool(value: Any, default: bool = True) -> bool:
    text = compact_str(value).casefold()
    if not text:
        return default
    if text in {"0", "false", "off", "no"}:
        return False
    if text in {"1", "true", "on", "yes"}:
        return True
    return default


def payload_from_query(qs: dict[str, list[str]], db: Any = None, now: datetime | None = None) -> dict[str, Any]:
    start = (qs.get("start") or [""])[0]
    end = (qs.get("end") or [""])[0]
    domain = (qs.get("domain") or ["all"])[0]
    test_filter = parse_bool((qs.get("test_filter") or qs.get("testFilter") or [""])[0], True)
    compare_prior = parse_bool((qs.get("compare_prior") or qs.get("comparePrior") or [""])[0], True)
    return compute_website_traffic(
        db,
        start=start,
        end=end,
        domain=domain,
        test_filter=test_filter,
        compare_prior=compare_prior,
        now=now,
        fetch_remote=db is not None,
    )
