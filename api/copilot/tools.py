# -*- coding: utf-8 -*-
"""Read-only tools. Arguments are validated here. Authorization is checked again here."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from copilot.dictionary import is_official, lookup
from copilot.formulas import (
    ALLOWED_METRIC_IDS,
    ALLOWED_SOURCE_IDS,
    OBSERVED_SOURCE_ALIASES,
    SOURCE_LABELS,
    absolute_change,
    demo_rate_percent,
    opp2prelim_percent,
    percent_change,
    sum_aliases,
    unmapped_labels,
)
from copilot.knowledge import search as search_documents
from copilot.periods import Period, TimezoneUnconfirmed, equivalent_prior_period, period_from_dates
from copilot.pii import scrub_rows

TOOL_NAMES = frozenset(
    {
        "get_metric_definition",
        "get_company_summary",
        "compare_periods",
        "get_source_performance",
        "get_supporting_records",
        "search_company_knowledge",
    }
)

METRIC_PATHS = {
    "sales": "/api/metrics/sales",
    "opps_created": "/api/metrics/opportunities_created",
    "opps_ran": "/api/metrics/opportunities_ran",
    "demo_rate": "/api/metrics/demo_rate",
    "opp2prelim": "/api/company_overview",
}

NUMERIC_METRICS = ("sales", "opps_created", "opps_ran", "demo_rate", "opp2prelim")


class ToolRejected(Exception):
    pass


@dataclass
class ToolContext:
    actor_id: str
    role: str
    config: Any
    entries: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    metrics: Any
    now: datetime
    ranking_allowed: bool
    issued_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: int = 0


def _require_period(args: dict, config, now: datetime) -> Period:
    start = str(args.get("start") or "")
    end = str(args.get("end") or "")
    if len(start) != 10 or len(end) != 10:
        raise ToolRejected("start and end must be YYYY-MM-DD")
    try:
        return period_from_dates(start, end, config.company_timezone, now)
    except TimezoneUnconfirmed as exc:
        raise ToolRejected(str(exc)) from exc
    except ValueError as exc:
        raise ToolRejected(str(exc)) from exc


def _sources(args: dict) -> tuple[str, ...]:
    raw = args.get("sources") or []
    if raw in ("", None):
        raw = []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ToolRejected("sources must be a list")
    cleaned = []
    for item in raw:
        token = str(item).strip().lower().replace(" ", "_").replace("-", "_")
        if token in {"selfgen", "self_gen"}:
            token = "self_gen"
        if token == "three_pl":
            token = "3pl"
        if token not in ALLOWED_SOURCE_IDS:
            raise ToolRejected("source is not allowlisted")
        cleaned.append(token)
    return tuple(dict.fromkeys(cleaned))


def report_link(metric_id: str, period: Period) -> str:
    if metric_id not in METRIC_PATHS:
        raise ToolRejected("metric link is not allowlisted")
    if metric_id == "opp2prelim":
        query = urlencode({"start": period.start, "end": period.end})
        return f"/api/company_overview?{query}"
    query = urlencode(
        {
            "format": "json",
            "year": period.start[0:4],
            "month": str(int(period.start[5:7])),
            "start": period.start,
            "end": period.end,
        }
    )
    return f"{METRIC_PATHS[metric_id]}?{query}"


def _definition_payload(entry: dict[str, Any] | None, term_id: str) -> dict[str, Any]:
    if entry is None:
        return {
            "available": False,
            "official": False,
            "term_id": term_id,
            "reason": "unknown_term",
        }
    governance = entry["governance"]
    official = is_official(entry)
    return {
        "available": official,
        "official": official,
        "term_id": entry["term_id"],
        "display_name": entry["display_name"],
        "status": governance.get("status"),
        "version": governance.get("version"),
        "approved_by": governance.get("approved_by"),
        "approved_at": governance.get("approved_at"),
        "definition": entry.get("definition") if official else None,
        "observation": entry.get("observation"),
        "policy": False if not official else True,
        "ambiguities": entry.get("ambiguities") or [],
        "metric_id": (entry.get("calculation") or {}).get("metric_id"),
    }


def _official_map(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found = {}
    for metric_id in NUMERIC_METRICS:
        entry = lookup(entries, metric_id)
        found[metric_id] = entry
    return found


def _missing_official(entries: list[dict[str, Any]], metric_ids: tuple[str, ...] | list[str]) -> list[str]:
    missing = []
    for metric_id in metric_ids:
        if not is_official(lookup(entries, metric_id)):
            missing.append(metric_id)
    return missing


def _clean_metric_ids(raw: Any) -> list[str]:
    metric_ids = raw or list(NUMERIC_METRICS)
    if isinstance(metric_ids, str):
        metric_ids = [metric_ids]
    if not isinstance(metric_ids, list) or len(metric_ids) > len(ALLOWED_METRIC_IDS):
        raise ToolRejected("metric_ids are not allowlisted")
    cleaned: list[str] = []
    for metric_id in metric_ids:
        token = str(metric_id).strip()
        if token not in ALLOWED_METRIC_IDS:
            raise ToolRejected("metric_ids are not allowlisted")
        cleaned.append(token)
    return cleaned


def _value_bundle(bundle: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    sales = bundle.get("sales")
    ran = bundle.get("ran")
    sits = bundle.get("sits")
    created = bundle.get("created")
    demo_ran = bundle.get("demo_ran")
    demo_entry = lookup(entries, "demo_rate")
    opp_entry = lookup(entries, "opp2prelim")
    demo_policy = ((demo_entry or {}).get("calculation") or {}).get("zero_denominator_policy")
    opp_policy = ((opp_entry or {}).get("calculation") or {}).get("zero_denominator_policy")
    if demo_policy == "null_when_denominator_zero":
        if not demo_ran or sits is None:
            demo = None
        else:
            demo = round((sits / demo_ran) * 100, 1)
        demo_zero = bool(demo_ran == 0)
    else:
        demo = demo_rate_percent(sits, demo_ran)
        demo_zero = bool(demo_ran == 0)
    if opp_policy == "zero_when_denominator_zero":
        opp = 0.0 if ran == 0 else round((sales / ran) * 100, 1)
        opp_zero = bool(ran == 0)
    else:
        opp = opp2prelim_percent(sales, ran)
        opp_zero = bool(ran == 0 and opp is None)
    return {
        "sales": sales,
        "opps_created": created,
        "opps_ran": ran,
        "sits": sits,
        "demo_ran": demo_ran,
        "demo_rate": demo,
        "opp2prelim": opp,
        "demo_rate_zero_denominator": demo_zero,
        "opp2prelim_zero_denominator": opp_zero,
        "generated_at": bundle.get("generated_at"),
    }


def _metric_result(metric_id: str, values: dict[str, Any], period: Period, entries: list[dict[str, Any]], filters: dict) -> dict[str, Any]:
    entry = lookup(entries, metric_id)
    governance = (entry or {}).get("governance") or {}
    numerator = None
    denominator = None
    value = values.get(metric_id)
    if metric_id == "demo_rate":
        numerator = values.get("sits")
        denominator = values.get("demo_ran")
    elif metric_id == "opp2prelim":
        numerator = values.get("sales")
        denominator = values.get("opps_ran")
    incomplete = []
    if metric_id == "demo_rate" and values.get("demo_rate_zero_denominator"):
        incomplete.append("zero_denominator")
    if metric_id == "opp2prelim" and values.get("opp2prelim_zero_denominator"):
        incomplete.append("zero_denominator")
    if period.partial:
        incomplete.append("partial_period")
    return {
        "metric_id": metric_id,
        "display_name": (entry or {}).get("display_name") or metric_id,
        "definition_version": governance.get("version"),
        "official": True,
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "unit": ((entry or {}).get("calculation") or {}).get("unit"),
        "period": period.as_dict(),
        "timezone": period.timezone,
        "filters": filters,
        "source_link": report_link(metric_id, period),
        "data_as_of": values.get("generated_at"),
        "incomplete": incomplete,
        "missing": value is None and "zero_denominator" not in incomplete,
        "zero": value == 0,
        "unavailable": False,
    }


def execute(name: str, args: dict | None, ctx: ToolContext) -> dict[str, Any]:
    if name not in TOOL_NAMES:
        raise ToolRejected("tool is not allowlisted")
    if ctx.calls >= ctx.config.max_tools_per_turn:
        raise ToolRejected("tool execution limit")
    ctx.calls += 1
    args = dict(args or {})
    for banned in ("user_id", "role", "permission", "sql"):
        if banned in args:
            raise ToolRejected("tool argument is not allowlisted")
    if "query" in args and name != "search_company_knowledge":
        raise ToolRejected("tool argument is not allowlisted")
    if name == "get_metric_definition":
        term_id = str(args.get("metric_id") or args.get("term_id") or "")
        return _definition_payload(lookup(ctx.entries, term_id), term_id)
    if name == "search_company_knowledge":
        query = str(args.get("query") or "")[:200]
        hits = search_documents(ctx.documents, query, now=ctx.now, limit=4)
        return {"available": bool(hits), "results": hits, "official_only": True}
    if name == "get_supporting_records":
        return _supporting(args, ctx)
    if name == "get_company_summary":
        return _summary(args, ctx)
    if name == "get_source_performance":
        return _sources_tool(args, ctx)
    if name == "compare_periods":
        return _compare(args, ctx)
    raise ToolRejected("tool is not allowlisted")


def _supporting(args: dict, ctx: ToolContext) -> dict[str, Any]:
    evidence_id = str(args.get("evidence_id") or "")
    issued = ctx.issued_evidence.get(evidence_id)
    if not issued:
        raise ToolRejected("evidence id was not issued for this turn")
    try:
        limit = int(args.get("limit") or ctx.config.default_rows)
    except (TypeError, ValueError):
        raise ToolRejected("limit is invalid")
    limit = max(1, min(limit, min(50, ctx.config.max_rows_per_tool)))
    cursor = args.get("cursor")
    start = int(cursor or 0)
    rows = issued["rows"][start : start + limit]
    next_cursor = start + limit if start + limit < len(issued["rows"]) else None
    return {
        "available": True,
        "evidence_id": evidence_id,
        "rows": rows,
        "row_count": len(rows),
        "next_cursor": next_cursor,
        "pii_removed": True,
    }


def _load_bundle(period: Period, ctx: ToolContext) -> dict[str, Any]:
    try:
        bundle = ctx.metrics.bundle(period)
    except TimezoneUnconfirmed:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "timezone" in message or "america/new_york" in message:
            raise ToolRejected("company timezone is not confirmed for the reporting modules") from exc
        raise ToolRejected("reporting functions failed") from exc
    if not ctx.ranking_allowed:
        for key in ("sales_by_owner", "ran_by_owner", "ran_by_setter", "sales_by_setter"):
            bundle.pop(key, None)
    rows = scrub_rows(list(bundle.get("rows") or []), limit=ctx.config.max_rows_per_tool)
    evidence_id = "ev_" + uuid.uuid4().hex[:16]
    ctx.issued_evidence[evidence_id] = {"rows": rows, "period": period.as_dict()}
    bundle = dict(bundle)
    bundle["rows"] = rows
    bundle["evidence_id"] = evidence_id
    return bundle


def _bundle_for_sources(bundle: dict[str, Any], sources: tuple[str, ...]) -> dict[str, Any]:
    """Sum allowlisted lead-source aliases. An empty selection stays company-wide."""
    if not sources:
        return bundle
    scoped = dict(bundle)

    def total(key: str) -> int:
        amount = 0
        for source_id in sources:
            amount += sum_aliases(bundle.get(key), OBSERVED_SOURCE_ALIASES[source_id])
        return amount

    scoped["sales"] = total("sales_by_source")
    scoped["ran"] = total("ran_by_source")
    scoped["created"] = total("created_by_source")
    scoped["sits"] = total("sit_by_source")
    scoped["demo_ran"] = total("demo_ran_by_source")
    return scoped


def _summary(args: dict, ctx: ToolContext) -> dict[str, Any]:
    requested = _clean_metric_ids(args.get("metric_ids"))
    missing = _missing_official(ctx.entries, requested)
    period = _require_period(args, ctx.config, ctx.now)
    if missing:
        return {
            "available": False,
            "official": False,
            "reason": "definition_not_approved",
            "missing_metric_ids": missing,
            "period": period.as_dict(),
        }
    bundle = _load_bundle(period, ctx)
    selected = _sources(args)
    values = _value_bundle(_bundle_for_sources(bundle, selected), ctx.entries)
    filters = {"sources": list(selected)}
    metrics = [
        _metric_result(metric_id, values, period, ctx.entries, filters)
        for metric_id in requested
    ]
    return {
        "available": True,
        "official": True,
        "period": period.as_dict(),
        "filters": filters,
        "metrics": metrics,
        "evidence_id": bundle.get("evidence_id"),
        "data_as_of": values.get("generated_at"),
        "aggregation": "shared_reporting_functions",
    }


def _sources_tool(args: dict, ctx: ToolContext) -> dict[str, Any]:
    needed = ("sales", "opps_ran", "opps_created", "demo_rate", "opp2prelim", "phones", "self_gen", "doors", "inbound", "three_pl")
    missing = [term_id for term_id in needed if not is_official(lookup(ctx.entries, term_id))]
    period = _require_period(args, ctx.config, ctx.now)
    if missing:
        return {
            "available": False,
            "official": False,
            "reason": "definition_not_approved",
            "missing_metric_ids": missing,
            "period": period.as_dict(),
        }
    selected = _sources(args)
    bundle = _load_bundle(period, ctx)
    rows = []
    for source_id, aliases in OBSERVED_SOURCE_ALIASES.items():
        if selected and source_id not in selected:
            continue
        sales = sum_aliases(bundle.get("sales_by_source"), aliases)
        opps_ran = sum_aliases(bundle.get("ran_by_source"), aliases)
        created = sum_aliases(bundle.get("created_by_source"), aliases)
        sits = sum_aliases(bundle.get("sit_by_source"), aliases)
        demo_ran = sum_aliases(bundle.get("demo_ran_by_source"), aliases)
        rows.append(
            {
                "source_id": source_id,
                "label": SOURCE_LABELS[source_id],
                "aliases_observed": list(aliases),
                "sales": sales,
                "opps_ran": opps_ran,
                "opps_created": created,
                "sits": sits,
                "demo_rate": demo_rate_percent(sits, demo_ran),
                "opp2prelim": opp2prelim_percent(sales, opps_ran),
                "demo_rate_zero_denominator": demo_ran == 0,
                "opp2prelim_zero_denominator": opps_ran == 0,
            }
        )
    return {
        "available": True,
        "official": True,
        "period": period.as_dict(),
        "rows": rows,
        "unmapped_sales_labels": unmapped_labels(bundle.get("sales_by_source")),
        "unmapped_ran_labels": unmapped_labels(bundle.get("ran_by_source")),
        "aggregation": "company_overview_card_alias_sum",
        "source_link": report_link("sales", period),
        "data_as_of": bundle.get("generated_at"),
        "evidence_id": bundle.get("evidence_id"),
        "note": "Alias groups match the company overview cards. They are not a separate cohort conversion.",
    }


def _compare(args: dict, ctx: ToolContext) -> dict[str, Any]:
    cleaned = _clean_metric_ids(args.get("metric_ids"))
    missing = _missing_official(ctx.entries, cleaned)
    period = _require_period(args, ctx.config, ctx.now)
    explicit_start = str(args.get("comparison_start") or "")
    explicit_end = str(args.get("comparison_end") or "")
    if len(explicit_start) == 10 and len(explicit_end) == 10:
        try:
            prior = period_from_dates(explicit_start, explicit_end, ctx.config.company_timezone, ctx.now)
        except (TimezoneUnconfirmed, ValueError) as exc:
            raise ToolRejected(str(exc)) from exc
    else:
        prior = equivalent_prior_period(period)
    if missing:
        return {
            "available": False,
            "official": False,
            "reason": "definition_not_approved",
            "missing_metric_ids": missing,
            "period": period.as_dict(),
            "comparison_period": prior.as_dict(),
            "comparison_basis": prior.basis,
        }
    selected = _sources(args)
    current_bundle = _bundle_for_sources(_load_bundle(period, ctx), selected)
    prior_bundle = _bundle_for_sources(_load_bundle(prior, ctx), selected)
    current_values = _value_bundle(current_bundle, ctx.entries)
    prior_values = _value_bundle(prior_bundle, ctx.entries)
    rows = []
    for metric_id in cleaned:
        current = current_values.get(metric_id)
        previous = prior_values.get(metric_id)
        zero_key = {
            "demo_rate": "demo_rate_zero_denominator",
            "opp2prelim": "opp2prelim_zero_denominator",
        }.get(metric_id)
        row = {
            "metric_id": metric_id,
            "current": current,
            "prior": previous,
            "absolute_change": absolute_change(current, previous),
            "percent_change": percent_change(current, previous),
            "percentage_points": absolute_change(current, previous) if metric_id in {"demo_rate", "opp2prelim"} else None,
            "partial_period": period.partial or prior.partial,
            "zero_baseline": previous == 0,
            # N/A from a zero denominator is an exact result, not a missing count.
            "current_zero_denominator": bool(zero_key and current_values.get(zero_key)),
            "prior_zero_denominator": bool(zero_key and prior_values.get(zero_key)),
        }
        rows.append(row)
    return {
        "available": True,
        "official": True,
        "comparison_basis": prior.basis,
        "period": period.as_dict(),
        "comparison_period": prior.as_dict(),
        "rows": rows,
        "source_links": [report_link(metric_id, period) for metric_id in cleaned],
        "data_as_of": current_values.get("generated_at"),
        "statement": (
            "Month-to-date is compared with the equivalent elapsed period."
            if prior.basis == "month_to_date_equivalent_elapsed"
            else "The comparison uses the prior window described in comparison_basis."
        ),
    }
