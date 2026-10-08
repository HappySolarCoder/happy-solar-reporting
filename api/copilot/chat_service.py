# -*- coding: utf-8 -*-
"""Turn lifecycle. Numbers in the reply are rendered from tool payloads."""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from copilot import dictionary as dictionary_mod
from copilot import knowledge as knowledge_mod
from copilot.auth import identity_for_chat, unauthorized_answer
from copilot.config import CopilotConfig, configuration_problems, rate_card_for
from copilot.formulas import DEMO_RATE_TARGET_PERCENT, SOURCE_LABELS
from copilot.human_dates import format_day, format_range, format_updated, is_stale
from copilot.messages import (
    BUDGET_LIMIT,
    LEDGER_UNAVAILABLE,
    MODEL_UNAVAILABLE,
    NARROW,
    NO_APPROVED_DEFINITION,
    NO_APPROVED_DOCUMENT,
    PAUSED,
    RATES_UNAVAILABLE,
    SCOPE_DENIAL,
    TIMEZONE_UNCONFIRMED,
    WELCOME,
    WHY_UNKNOWN,
    uncertainty_sentence,
)
from copilot.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from copilot.rates import INPUT_TOKEN_CEILING, max_affordable_calls, reservation_micro
from copilot.scope import (
    classify,
    message_source_negated,
    message_sources,
    message_sources_are_exact,
    uncovered_request,
)
from copilot.store import BudgetExceeded, LedgerUnavailable, QuotaExceeded
from copilot.tools import ToolContext, ToolRejected, execute

_DIGIT = re.compile(r"\d")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")
_SUMMARY_METRIC_IDS = {
    "sales": "sales",
    "demo_rate": "demo_rate",
    "opp2prelim": "opp2prelim",
    "ran": "opps_ran",
    "created": "opps_created",
}


def _response(status: int, **body: Any) -> dict[str, Any]:
    body.setdefault("display_name", "Goose")
    body.setdefault("role_name", "Happy Solar Data Copilot")
    body.setdefault("prompt_version", PROMPT_VERSION)
    return {"status": status, "body": body}


def _limits(config: CopilotConfig) -> dict[str, int]:
    return {
        "max_turns_per_day": config.max_turns_per_day,
        "max_turns_per_month": config.max_turns_per_month,
        "max_requests_per_minute": config.max_requests_per_minute,
        "max_active_company": config.max_active_company,
    }


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 2) // 3)


def _prune_history(turns: list[dict[str, str]], budget_tokens: int) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    used = 0
    for turn in reversed(turns):
        cost = _estimate_tokens(turn.get("content") or "")
        if used + cost > budget_tokens:
            break
        kept.append(turn)
        used += cost
    kept.reverse()
    return kept


def _filters(raw: dict | None) -> dict[str, Any]:
    raw = raw or {}
    start = str(raw.get("start") or "").strip()
    end = str(raw.get("end") or "").strip()
    sources = raw.get("sources") or []
    return {
        "start": start,
        "end": end,
        "sources": sources,
        "unrecognized_source": bool(raw.get("unrecognized_source")),
    }


_RATE_IDS = frozenset({"demo_rate", "opp2prelim"})
_TITLES = {
    "sales": "Sales",
    "opps_created": "Opps Created",
    "opps_ran": "Ran",
    "created": "Opps Created",
    "ran": "Ran",
    "demo_rate": "Demo Rate",
    "opp2prelim": "Opp2Prelim",
    "sit": "Demo",
    "phones": "Phones",
    "self_gen": "Self Gen",
    "doors": "Doors",
    "inbound": "Inbound",
    "three_pl": "3PL",
    "3pl": "3PL",
}
_NOT_DOUBT = frozenset({"partial_period", "zero_denominator"})
_SENTENCE_NAME = {
    "sales": "Sales",
    "opps_created": "Opportunities created",
    "opps_ran": "Appointments that ran",
    "demo_rate": "Demo rate",
    "opp2prelim": "Opp2Prelim",
}


def _count(value: Any) -> str:
    if value is None:
        return "an unknown number of"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.1f}%"


def _plain_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _period_label(period: dict | None) -> str:
    period = period or {}
    label = format_range(period.get("start"), period.get("end"))
    return label or "those dates"


def _goal_clause(rate: float) -> str:
    target = float(DEMO_RATE_TARGET_PERCENT)
    goal = f"{int(target)}%" if target.is_integer() else f"{target:.1f}%"
    if float(rate) < target:
        return f"a bit under the {goal} goal"
    if float(rate) > target:
        return f"a bit over the {goal} goal"
    return f"right at the {goal} goal"


def _source_names(sources: Any) -> str | None:
    labels: list[str] = []
    for source_id in sources or []:
        label = SOURCE_LABELS.get(str(source_id))
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def _demo_sentence(metric: dict[str, Any], label: str, source_name: str | None = None) -> str:
    rate = metric.get("value")
    demos = metric.get("numerator")
    ran = metric.get("denominator")
    subject = f"{source_name} demo rate" if source_name else "demo rate"
    if rate is None:
        if _as_int(ran) == 0:
            return f"Your {subject} for {label} is N/A, because no appointments ran."
        return f"Your {subject} for {label} is N/A."
    head = f"Your {subject} for {label} is {_percent(rate)}."
    if demos is None or ran is None:
        return f"{head} That's {_goal_clause(rate)}."
    demo_word = "demo" if _as_int(demos) == 1 else "demos"
    appt_word = "appointment" if _as_int(ran) == 1 else "appointments"
    return (
        f"{head} That's {_count(demos)} {demo_word} out of {_count(ran)} "
        f"{appt_word} that ran, {_goal_clause(rate)}."
    )


def _opp_sentence(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    sales = metric.get("numerator")
    ran = metric.get("denominator")
    if value is None:
        if _as_int(ran) == 0:
            return "Opp2Prelim is N/A, because no appointments ran."
        return "Opp2Prelim is N/A."
    if sales is None or ran is None:
        return f"Opp2Prelim is {_percent(value)}."
    return (
        f"Opp2Prelim is {_percent(value)}, which is {_count(sales)} sales out of "
        f"{_count(ran)} appointments that ran."
    )


def _title_name(metric_id: str | None, display_name: str | None = None) -> str:
    if display_name and "_" not in str(display_name):
        return str(display_name)
    return _TITLES.get(metric_id or "", "Report")


def _source_label(metric_id: str | None, display_name: str | None = None) -> str:
    name = _title_name(metric_id, display_name)
    if name == "Report":
        return "Source"
    return f"Source: {name} definition"


def _label_for_link(link: str) -> str:
    if "demo_rate" in link:
        return _source_label("demo_rate")
    if "opportunities_created" in link:
        return _source_label("opps_created")
    if "opportunities_ran" in link:
        return _source_label("opps_ran")
    if "company_overview" in link:
        return _source_label("opp2prelim")
    if "/metrics/sales" in link or link.startswith("/api/metrics/sales"):
        return _source_label("sales")
    return "Source"


def _render_definition(payload: dict[str, Any]) -> str:
    if payload.get("reason") == "unknown_term":
        return (
            f"{NO_APPROVED_DEFINITION} "
            "Tell me which term you mean, such as Opp2Prelim, demo rate, or a lead source."
        )
    name = _title_name(payload.get("term_id"), payload.get("display_name"))
    if not payload.get("official"):
        return (
            f"{NO_APPROVED_DEFINITION} {name} is still a draft, so it is not company policy. "
            "An owner has to approve it before I treat it as official."
        )
    text = (payload.get("definition") or "").strip()
    if not text:
        return f"{name} is approved, but that record doesn't include a plain-language definition yet."
    return f"{name}: {text}"


def _render_summary(payload: dict[str, Any], focus: str | None = None) -> str:
    if not payload.get("available"):
        return (
            f"{NO_APPROVED_DEFINITION} I have not reported a figure. "
            "The dashboard is unchanged."
        )
    label = _period_label(payload.get("period"))
    source_name = _source_names((payload.get("filters") or {}).get("sources"))
    by_id = {metric["metric_id"]: metric for metric in payload.get("metrics") or []}
    if "demo_rate" in by_id and (focus == "demo_rate" or set(by_id) == {"demo_rate"}):
        return _demo_sentence(by_id["demo_rate"], label, source_name)
    if set(by_id) == {"sales"}:
        return f"For {label}, you had {_count(by_id['sales'].get('value'))} sales."
    if set(by_id) == {"opps_created"}:
        return f"For {label}, {_count(by_id['opps_created'].get('value'))} opportunities were created."
    if set(by_id) == {"opps_ran"}:
        return f"For {label}, {_count(by_id['opps_ran'].get('value'))} appointments ran."
    if set(by_id) == {"opp2prelim"}:
        return _opp_sentence(by_id["opp2prelim"])
    sales = by_id.get("sales") or {}
    created = by_id.get("opps_created") or {}
    ran = by_id.get("opps_ran") or {}
    sentences = [
        f"For {label}, you had {_count(sales.get('value'))} sales.",
        (
            f"{_count(created.get('value'))} opportunities were created, and "
            f"{_count(ran.get('value'))} appointments ran."
        ),
    ]
    if "demo_rate" in by_id:
        sentences.append(_demo_sentence(by_id["demo_rate"], label, source_name))
    if "opp2prelim" in by_id:
        sentences.append(_opp_sentence(by_id["opp2prelim"]))
    return " ".join(sentences)


def _rate_text(value: Any) -> str:
    if value is None:
        return "N/A"
    return _percent(value)


def _public_labels(text: str) -> str:
    """User-facing words are demo, demos, demo rate, or no demo.

    The raw disposition token Sit is left unchanged. Lowercase sit, sits, and sat are not labels.
    """

    def replace(match: re.Match) -> str:
        word = match.group(0)
        if word == "Sit":
            return word
        lowered = word.lower()
        if lowered == "sits":
            return "demos"
        return "demo"

    return re.sub(r"\b(sits|sit|sat)\b", replace, text, flags=re.IGNORECASE)


def _plain_face(text: str) -> str:
    """Hide machine tokens if a template or model line still has them."""
    if not text:
        return text
    for raw, spoken in (
        ("opps_created", "opportunities created"),
        ("opps_ran", "appointments that ran"),
        ("demo_rate", "demo rate"),
        ("opp2prelim", "Opp2Prelim"),
    ):
        text = re.sub(rf"\b{raw}\b", spoken, text)
    text = re.sub(r"\s*\(America/[A-Za-z_]+\)", "", text)
    text = text.replace("America/New_York", "ET")

    def _stamp(match: re.Match) -> str:
        label = format_updated(match.group(0))
        return label or match.group(0)

    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", _stamp, text)


def _change_sentence(row: dict[str, Any]) -> str:
    metric_id = row.get("metric_id") or ""
    name = _SENTENCE_NAME.get(metric_id, "That figure")
    current = _percent(row.get("current")) if metric_id in _RATE_IDS else _count(row.get("current"))
    prior = _percent(row.get("prior")) if metric_id in _RATE_IDS else _count(row.get("prior"))
    change = row.get("absolute_change")
    if row.get("current") is None or row.get("prior") is None or change is None:
        return f"{name} went from {prior} to {current}."
    if change == 0:
        return f"{name} stayed at {current}."
    direction = "up" if change > 0 else "down"
    moved = _plain_number(abs(change))
    if metric_id in _RATE_IDS:
        return f"{name} went from {prior} to {current}, {direction} {abs(float(change)):.1f} percentage points."
    pct = row.get("percent_change")
    if pct is None:
        return (
            f"{name} went from {prior} to {current}, {direction} by {moved}. "
            "I left off the percent change because the earlier number was zero or missing."
        )
    return f"{name} went from {prior} to {current}, {direction} by {moved}, a {abs(float(pct)):.1f}% change."


def _render_sources(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return f"{NO_APPROVED_DEFINITION} Source totals stay unavailable until those drafts are approved."
    lines = [f"Here's how each lead source did for {_period_label(payload.get('period'))}."]
    for row in payload["rows"]:
        lines.append(
            f"{row['label']} had {_count(row['sales'])} sales and {_count(row['opps_ran'])} appointments that ran. "
            f"Demo rate was {_rate_text(row['demo_rate'])}, and Opp2Prelim was {_rate_text(row['opp2prelim'])}."
        )
    return " ".join(lines)


def _render_compare(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return f"{NO_APPROVED_DEFINITION} I have not calculated a change."
    current = _period_label(payload.get("period"))
    prior = _period_label(payload.get("comparison_period"))
    lines = [f"Comparing {current} with {prior}."]
    for row in payload["rows"]:
        lines.append(_change_sentence(row))
    return " ".join(lines)


def _metrics_in_play(payload: dict[str, Any], focus: str | None) -> list[dict[str, Any]]:
    metrics = list(payload.get("metrics") or [])
    if focus == "demo_rate":
        focused = [metric for metric in metrics if metric.get("metric_id") == "demo_rate"]
        return focused or metrics
    return metrics


def _uncertainty_reason(payload: dict[str, Any], decision, now: datetime, focus: str | None = None) -> str | None:
    """One plain reason, or None when the figure is exact for the dates asked.

    A month still in progress is not doubt. The number is exact for that window.
    """
    if not payload.get("available"):
        return None
    reasons: list[str] = []
    if payload.get("unmapped_sales_labels") or payload.get("unmapped_ran_labels"):
        reasons.append("some of the counts didn't line up")
    if is_stale(payload.get("data_as_of"), now):
        reasons.append("the last refresh is more than a day old")
    if payload.get("official") is False:
        reasons.append("that definition is still a draft")
    assumed = payload.get("assumed_filter") or payload.get("assumed_source")
    if assumed:
        reasons.append(str(assumed))
    if getattr(decision, "uncertain", False):
        reasons.append(getattr(decision, "uncertainty_reason", "") or "the question could mean more than one thing")
    for metric in _metrics_in_play(payload, focus):
        if metric.get("missing"):
            reasons.append("some of the data is missing")
        extra = set(metric.get("incomplete") or []) - _NOT_DOUBT
        if extra:
            reasons.append("some of the data is missing")
    for row in payload.get("rows") or []:
        if "current" in row:
            current_missing = row.get("current") is None and not row.get("current_zero_denominator")
            prior_missing = row.get("prior") is None and not row.get("prior_zero_denominator")
            if current_missing or prior_missing:
                reasons.append("some of the data is missing")
        elif "sales" in row and (row.get("sales") is None or row.get("opps_ran") is None):
            reasons.append("some of the data is missing")
    ordered: list[str] = []
    for reason in reasons:
        if reason and reason not in ordered:
            ordered.append(reason)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    if len(ordered) == 2:
        return f"{ordered[0]} and {ordered[1]}"
    return ", ".join(ordered[:-1]) + ", and " + ordered[-1]


def _evidence_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    if not isinstance(payload, dict):
        return evidence
    link = payload.get("source_link")
    if link:
        evidence.append(
            {
                "source_link": link,
                "data_as_of": payload.get("data_as_of"),
                "kind": "report",
                "label": _label_for_link(link),
            }
        )
    for link in payload.get("source_links") or []:
        evidence.append(
            {
                "source_link": link,
                "data_as_of": payload.get("data_as_of"),
                "kind": "report",
                "label": _label_for_link(link),
            }
        )
    for metric in payload.get("metrics") or []:
        if metric.get("source_link"):
            metric_id = metric.get("metric_id")
            evidence.append(
                {
                    "metric_id": metric_id,
                    "label": _source_label(metric_id, metric.get("display_name")),
                    "definition_version": metric.get("definition_version"),
                    "source_link": metric.get("source_link"),
                    "data_as_of": metric.get("data_as_of"),
                    "period": metric.get("period"),
                    "filters": metric.get("filters"),
                    "incomplete": metric.get("incomplete"),
                }
            )
    for hit in payload.get("results") or []:
        evidence.append(
            {
                "document_id": hit.get("document_id"),
                "source_uri": hit.get("source_uri"),
                "version": hit.get("version"),
                "approval_status": hit.get("approval_status"),
            }
        )
    return evidence


def _paid_interpretation(
    *,
    store,
    config: CopilotConfig,
    actor_id: str,
    request_id: str,
    now: datetime,
    model,
    tool_payload: dict[str, Any],
    history: list[dict[str, str]],
) -> str | None:
    """One metered call. Returns None when the model must not run."""
    if model is None or not getattr(model, "configured", True):
        return None
    today = now.astimezone(timezone.utc).date()
    problems = configuration_problems(config, today)
    blocking = [item for item in problems if item != "COPILOT_ENABLED is not true"]
    if blocking:
        return None
    if not config.company_timezone or not config.billing_timezone:
        return None
    card = rate_card_for(config)
    if card.expired(today) or config.model_id != card.model_id:
        return None
    affordable = max_affordable_calls(INPUT_TOKEN_CEILING, card, turn_cap_micro=config.turn_micro)
    if affordable < 1:
        return None
    history_text = " ".join(turn["content"] for turn in history)
    serialized = SYSTEM_PROMPT + "\n" + history_text + "\n" + str(tool_payload)
    input_tokens = min(INPUT_TOKEN_CEILING, _estimate_tokens(serialized))
    if _estimate_tokens(serialized) > INPUT_TOKEN_CEILING:
        return None
    amount = reservation_micro(input_tokens, card.billable_output_tokens(), 1, card)
    if amount > config.turn_micro:
        return None
    from copilot.periods import next_month_start

    try:
        month_key = __import__("copilot.periods", fromlist=["billing_month_key"]).billing_month_key(
            config.billing_timezone, now
        )
        reset_date = next_month_start(config.billing_timezone, now)
        reservation = store.reserve(
            request_id=request_id,
            actor_id=actor_id,
            month_key=month_key,
            amount_micro=amount,
            monthly_cap_micro=config.model_cap_micro(),
            reset_date=reset_date,
            now=now,
        )
    except BudgetExceeded:
        raise
    except LedgerUnavailable:
        raise
    if reservation.status == "unresolved":
        raise LedgerUnavailable("prior dispatch for this request is unresolved")
    if reservation.status == "settled":
        return None
    if reservation.dispatched:
        store.retain(request_id)
        raise LedgerUnavailable("request already dispatched")
    try:
        store.mark_dispatched(request_id)
        result = model.generate(
            system=SYSTEM_PROMPT,
            user=(
                "Server tool payload follows. Add one short plain-English interpretation with no numerals, "
                "no metric ids, and no timezone names. If you cannot, return an empty string.\n"
                + str({k: tool_payload.get(k) for k in ("available", "official", "period", "statement")})
            ),
            max_output_tokens=card.max_output_tokens if card.output_cap_enforced else 256,
        )
    except Exception as exc:
        dispatched = bool(getattr(exc, "dispatched", True))
        if dispatched:
            store.retain(request_id)
        else:
            store.release_if_not_dispatched(request_id)
        raise LedgerUnavailable("model call failed") from exc
    usage_ok = (
        result.input_tokens is not None
        and result.output_tokens is not None
        and result.thoughts_tokens is not None
        and result.total_tokens == result.input_tokens + result.output_tokens + result.thoughts_tokens
    )
    if not usage_ok:
        store.retain(request_id)
        return None
    from copilot.rates import call_micro

    actual = call_micro(result.input_tokens, result.output_tokens + result.thoughts_tokens, card)
    if not store.fits_remaining(request_id, actual):
        store.retain(request_id)
        return None
    store.settle(
        request_id,
        actual_micro=actual,
        model_id=card.model_id,
        rate_version=card.rate_version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        thoughts_tokens=result.thoughts_tokens,
    )
    text = (result.text or "").strip()
    if not text or _DIGIT.search(text):
        return None
    return text


def handle_chat(
    *,
    message: str,
    filters: dict | None,
    conversation_id: str | None,
    request_id: str | None,
    headers,
    now: datetime,
    config: CopilotConfig,
    store,
    settings_password: str | None,
    metrics=None,
    model=None,
    body_identity: dict | None = None,
    bloom_token_secret: str | None = None,
) -> dict[str, Any]:
    del body_identity  # never authorize from the body
    if store.paused or not config.enabled:
        return _response(200, ok=False, code="copilot_disabled", answer=PAUSED, dashboard_unaffected=True)
    if request_id and not _REQUEST_ID.match(request_id):
        return _response(400, ok=False, code="bad_request", answer=NARROW)
    request_id = request_id or ("req_" + uuid.uuid4().hex)
    text = message or ""
    if len(text) > config.max_message_chars:
        return _response(413, ok=False, code="too_large", answer=NARROW)
    identity = identity_for_chat(
        headers,
        settings_password=settings_password,
        allowed_roles=config.allowed_roles,
        token_secret=bloom_token_secret,
        now=now,
    )
    if identity is None:
        return _response(
            401,
            ok=False,
            code="unauthorized",
            answer=unauthorized_answer(
                headers,
                settings_password=settings_password,
                allowed_roles=config.allowed_roles,
                token_secret=bloom_token_secret,
                now=now,
            ),
        )
    assert identity is not None
    remembered = store.remembered_response(request_id, identity.actor_id)
    if remembered is not None:
        return {"status": 200, "body": remembered}
    lowered = " ".join(text.lower().split())
    if lowered in {"be concise", "answer briefly"}:
        store.set_preference(identity.actor_id, True)
        answer = "I'll keep later answers short. Say forget my preferences when you want the usual length again."
        return _response(200, ok=True, code="preference", answer=answer)
    if lowered == "forget my preferences":
        store.set_preference(identity.actor_id, None)
        return _response(200, ok=True, code="preference", answer="I cleared your display preferences.")
    month_key = "unconfirmed"
    quota_now = now
    if config.company_timezone:
        from copilot.periods import TimezoneUnconfirmed, today_in

        try:
            # Daily quotas reset on the company calendar, not the server clock.
            company_day = today_in(config.company_timezone, now)
            quota_now = datetime(
                company_day.year,
                company_day.month,
                company_day.day,
                now.hour,
                now.minute,
                now.second,
                tzinfo=timezone.utc,
            )
        except TimezoneUnconfirmed:
            quota_now = now
    if config.billing_timezone:
        from copilot.periods import TimezoneUnconfirmed, billing_month_key

        try:
            month_key = billing_month_key(config.billing_timezone, now)
        except TimezoneUnconfirmed:
            month_key = "unconfirmed"
    turn_id = "turn_" + request_id
    try:
        store.begin_turn(
            actor_id=identity.actor_id,
            turn_id=turn_id,
            month_key=month_key,
            now=quota_now,
            limits=_limits(config),
        )
    except QuotaExceeded as exc:
        return _response(429, ok=False, code="quota", answer=str(exc))
    except LedgerUnavailable:
        return _response(503, ok=False, code="ledger_unavailable", answer=LEDGER_UNAVAILABLE, dashboard_unaffected=True)
    try:
        return _finish_turn(
            text=text,
            filters=_filters(filters),
            conversation_id=conversation_id,
            request_id=request_id,
            now=now,
            config=config,
            store=store,
            identity=identity,
            metrics=metrics,
            model=model,
            turn_id=turn_id,
        )
    finally:
        store.end_turn(identity.actor_id, turn_id)


def _apply_message_filters(text: str, filters: dict[str, Any], intent: str, config: CopilotConfig, now: datetime) -> dict[str, Any]:
    """Named month and lead source in the message win over the page filters.

    "last month" on a comparison keeps the page window, because that comparison
    already builds the prior period from it. An explicit month name always wins.
    """
    from copilot.periods import (
        TimezoneUnconfirmed,
        implied_current_range,
        message_names_explicit_month,
        named_calendar_range,
        named_period_unserved,
    )

    updated = {
        "start": filters.get("start") or "",
        "end": filters.get("end") or "",
        "sources": list(filters.get("sources") or []),
        "unrecognized_source": bool(filters.get("unrecognized_source")),
    }
    named = None
    unserved = None
    try:
        named = named_calendar_range(text, config.company_timezone, now)
        if named is None:
            unserved = named_period_unserved(text, config.company_timezone, now)
    except TimezoneUnconfirmed:
        named = None
        unserved = None
    # A real comparison keeps the page window unless the message names a month.
    # "last month" on a figure question is the previous full month, already in named.
    use_named = bool(named) and (intent != "compare" or message_names_explicit_month(text))
    if use_named and named is not None:
        updated["start"], updated["end"] = named
    elif not updated["start"] and not updated["end"]:
        implied = None
        try:
            implied = implied_current_range(text, config.company_timezone, now)
        except TimezoneUnconfirmed:
            implied = None
        if implied:
            updated["start"], updated["end"] = implied
    # An exclusion is never applied as a filter TO that source. An "or" between
    # sources is not an exact sum, so the company-wide number is the honest one.
    if message_source_negated(text) or (
        len(message_sources(text)) >= 2 and not message_sources_are_exact(text)
    ):
        updated["sources"] = []
        updated["unrecognized_source"] = False
    else:
        source_ids = message_sources(text)
        if source_ids:
            updated["sources"] = source_ids
            updated["unrecognized_source"] = False
    if unserved and not use_named:
        updated["unserved_period"] = unserved
    return updated


def _finish_turn(*, text, filters, conversation_id, request_id, now, config, store, identity, metrics, model, turn_id):
    decision = classify(text)
    if decision.intent not in {
        "greeting",
        "help",
        "definition",
        "company_summary",
        "compare",
        "source_performance",
        "knowledge",
        "challenge",
        "clarify",
        "deny",
        "mixed",
    }:
        decision_intent = "deny"
    else:
        decision_intent = decision.intent
    entries = dictionary_mod.effective_entries(
        dictionary_mod.apply_revisions(dictionary_mod.load_seed(), store.list_revisions("term"))
    )
    documents = knowledge_mod.apply_revisions(
        knowledge_mod.load_seed()["documents"],
        store.list_revisions("document"),
    )
    ctx = ToolContext(
        actor_id=identity.actor_id,
        role=identity.role,
        config=config,
        entries=entries,
        documents=documents,
        metrics=metrics,
        now=now,
        ranking_allowed=identity.role in config.ranking_roles,
    )
    tool_payload: dict[str, Any] = {}
    answer = ""
    code = decision_intent
    unserved_period = None
    try:
        if decision_intent == "deny":
            answer = SCOPE_DENIAL
        elif decision_intent == "greeting":
            answer = WELCOME
        elif decision_intent == "help":
            answer = WELCOME + " You can ask me to explain Opp2Prelim, compare source performance, or look at a change versus last month."
        elif decision_intent == "clarify":
            answer = decision.clarification
        elif decision_intent in {"definition", "mixed", "challenge"}:
            term = decision.matched_term or "unknown"
            tool_payload = execute("get_metric_definition", {"metric_id": term}, ctx)
            answer = _render_definition(tool_payload)
            if decision_intent == "challenge":
                answer = "I rechecked the definition status before answering. " + answer
            if decision_intent == "mixed":
                answer = answer + " I can't help with the unrelated part of that request."
        elif decision_intent == "knowledge":
            tool_payload = execute("search_company_knowledge", {"query": text}, ctx)
            if tool_payload.get("results"):
                hit = tool_payload["results"][0]
                answer = f"{hit['title']}: {hit['excerpt']}"
            else:
                answer = NO_APPROVED_DOCUMENT + " " + WELCOME
        elif decision_intent in {"company_summary", "compare", "source_performance"}:
            filters = _apply_message_filters(text, filters, decision_intent, config, now)
            unserved_period = filters.pop("unserved_period", None)
            if not filters["start"] or not filters["end"]:
                answer = "Which start and end dates should I use? Set them on the page and I'll use that range."
                code = "clarify"
            else:
                name = {
                    "company_summary": "get_company_summary",
                    "compare": "compare_periods",
                    "source_performance": "get_source_performance",
                }[decision_intent]
                args = {"start": filters["start"], "end": filters["end"], "sources": filters["sources"]}
                mapped = _SUMMARY_METRIC_IDS.get(decision.matched_term or "")
                if decision_intent in {"company_summary", "compare"} and mapped:
                    args["metric_ids"] = [mapped]
                if metrics is None:
                    answer = NO_APPROVED_DEFINITION + " I can't reach the reporting numbers for this question."
                    code = "metrics_unavailable"
                else:
                    tool_payload = execute(name, args, ctx)
                    if decision_intent == "company_summary":
                        answer = _render_summary(tool_payload, focus=decision.matched_term)
                    elif decision_intent == "compare":
                        answer = _render_compare(tool_payload)
                    else:
                        answer = _render_sources(tool_payload)
                    if tool_payload.get("reason") == "definition_not_approved":
                        code = "definition_not_approved"
        else:
            answer = SCOPE_DENIAL
            code = "deny"
    except ToolRejected as exc:
        message = str(exc)
        if "timezone" in message:
            answer = TIMEZONE_UNCONFIRMED
            code = "timezone_unconfirmed"
        else:
            answer = NARROW
            code = "rejected"
    if store.preference(identity.actor_id).get("concise") and len(answer) > 280:
        answer = answer[:277].rstrip() + "..."
    interpretation = None
    model_note = None
    if tool_payload.get("available") and decision_intent in {"company_summary", "compare", "source_performance"}:
        try:
            interpretation = _paid_interpretation(
                store=store,
                config=config,
                actor_id=identity.actor_id,
                request_id=request_id,
                now=now,
                model=model,
                tool_payload=tool_payload,
                history=[],
            )
            if interpretation:
                interpretation = _plain_face(_public_labels(interpretation))
            if interpretation is None and model is not None and getattr(model, "configured", False):
                model_note = MODEL_UNAVAILABLE
        except BudgetExceeded as exc:
            answer = BUDGET_LIMIT
            code = "budget_limit"
            interpretation = None
            model_note = exc.reset_date
        except LedgerUnavailable:
            if code not in {"budget_limit"}:
                model_note = LEDGER_UNAVAILABLE if configuration_problems(config, now.date()) else RATES_UNAVAILABLE
    elif model is not None and not getattr(model, "configured", True):
        model_note = MODEL_UNAVAILABLE
    reason = None
    if code != "budget_limit" and tool_payload.get("available"):
        if filters.get("unrecognized_source"):
            tool_payload = dict(tool_payload)
            tool_payload["assumed_filter"] = "I assumed every lead source"
        if unserved_period and not decision.uncertain:
            used = format_range(filters.get("start"), filters.get("end")) or "the dates on the page"
            decision = replace(
                decision,
                uncertain=True,
                uncertainty_reason=f"I couldn't use {unserved_period}, so this is {used}",
            )
        elif (
            not decision.uncertain
            and decision_intent in {"company_summary", "compare", "source_performance"}
            and code == decision_intent
        ):
            leftover = uncovered_request(
                text,
                filters.get("start") or "",
                filters.get("end") or "",
                filters.get("sources") or [],
                config.company_timezone,
                now,
            )
            if leftover:
                used = format_range(filters.get("start"), filters.get("end")) or "the dates on the page"
                decision = replace(
                    decision,
                    uncertain=True,
                    uncertainty_reason=f"I couldn't use '{leftover}', so this is {used}",
                )
        focus = decision.matched_term if decision_intent == "company_summary" else None
        reason = _uncertainty_reason(tool_payload, decision, now, focus=focus)
        if reason:
            answer = answer.rstrip() + " " + uncertainty_sentence(reason)
    answer = _plain_face(_public_labels(answer))
    updated = format_updated(tool_payload.get("data_as_of"))
    evidence = _evidence_from(tool_payload)
    conversation = conversation_id or ("conv_" + uuid.uuid4().hex[:16])
    existing = store.get_conversation(conversation, identity.actor_id)
    messages = list((existing or {}).get("messages") or [])
    messages.append({"role": "user", "content": text[:500]})
    messages.append({"role": "assistant", "content": answer[:800]})
    messages = messages[-config.max_turns_per_conversation * 2 :]
    messages = _prune_history(messages, 2000)
    store.save_conversation(
        {
            "conversation_id": conversation,
            "actor_id": identity.actor_id,
            "updated_at": now.isoformat(),
            "messages": messages,
        }
    )
    other = store.get_conversation(conversation, "someone-else")
    del other
    body = {
        "ok": code not in {"deny", "budget_limit"},
        "code": code,
        "answer": answer,
        "interpretation": interpretation,
        "hypothesis": False if not interpretation else True,
        "evidence": evidence,
        "footnote": {
            "filters": filters,
            "prompt_version": PROMPT_VERSION,
            "knowledge_version": config.knowledge_version,
            "model_note": model_note,
            "partial": (tool_payload.get("period") or {}).get("partial"),
            "data_as_of": tool_payload.get("data_as_of"),
            "updated_label": updated or None,
            "definition_status": "approved" if tool_payload.get("official") else "not_approved",
        },
        "uncertain": bool(reason),
        "uncertainty_reason": reason,
        "conversation_id": conversation,
        "request_id": request_id,
        "display_name": "Goose",
        "role_name": "Happy Solar Data Copilot",
        "prompt_version": PROMPT_VERSION,
        "dashboard_unaffected": True,
    }
    if code == "budget_limit":
        body["reset_date"] = model_note
        body["reset_label"] = format_day(model_note) or None
        body["ok"] = False
        body["uncertain"] = False
        body["uncertainty_reason"] = None
    store.add_audit(
        {
            "type": "chat",
            "actor": identity.actor_id,
            "request_id": request_id,
            "intent": decision_intent,
            "tool_calls": ctx.calls,
            "code": code,
            "definition_version": (tool_payload.get("metrics") or [{}])[0].get("definition_version")
            if tool_payload.get("metrics")
            else None,
        }
    )
    store.remember_response(request_id, identity.actor_id, body)
    return {"status": 200 if code != "quota" else 429, "body": body}
