# -*- coding: utf-8 -*-
"""Turn lifecycle. Numbers in the reply are rendered from tool payloads."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from copilot import dictionary as dictionary_mod
from copilot import knowledge as knowledge_mod
from copilot.auth import chat_allowed, identity_from_headers
from copilot.config import CopilotConfig, configuration_problems, rate_card_for
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
    SIGN_IN_REQUIRED,
    TIMEZONE_UNCONFIRMED,
    WELCOME,
    WHY_UNKNOWN,
)
from copilot.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from copilot.rates import INPUT_TOKEN_CEILING, max_affordable_calls, reservation_micro
from copilot.scope import classify
from copilot.store import BudgetExceeded, LedgerUnavailable, QuotaExceeded
from copilot.tools import ToolContext, ToolRejected, execute

_DIGIT = re.compile(r"\d")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")


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
    return {"start": start, "end": end, "sources": sources}


def _render_definition(payload: dict[str, Any]) -> str:
    if payload.get("reason") == "unknown_term":
        return (
            "I do not have an approved definition for that yet. "
            "Tell me which term you mean, such as Opp2Prelim, Demo Rate, or a lead source."
        )
    name = payload.get("display_name") or payload.get("term_id")
    if not payload.get("official"):
        return (
            f"{NO_APPROVED_DEFINITION} {name} is still a draft observation, not company policy. "
            "An owner has to approve it before I treat it as official."
        )
    text = (payload.get("definition") or "").strip()
    if not text:
        return f"{name} is approved, but that record does not include a plain-language definition yet."
    return f"{name}: {text}"


def _render_summary(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return (
            f"{NO_APPROVED_DEFINITION} I have not reported a figure. "
            "The dashboard is unchanged."
        )
    lines = []
    period = payload["period"]
    lines.append(f"Company totals for {period['start']} to {period['end']} ({period['timezone']}).")
    for metric in payload["metrics"]:
        if metric["value"] is None:
            shown = "N/A" if "zero_denominator" in (metric.get("incomplete") or []) else "unavailable"
        else:
            shown = str(metric["value"])
        unit = metric.get("unit") or ""
        lines.append(f"{metric['metric_id']}: {shown} {unit}".rstrip())
    if period.get("partial"):
        lines.append("This is a partial period.")
    return " ".join(lines)


def _rate_text(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


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


def _render_sources(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return f"{NO_APPROVED_DEFINITION} Source totals stay unavailable until those drafts are approved."
    lines = [payload.get("note") or "Source performance."]
    if payload["period"].get("partial"):
        lines.append("Partial period.")
    for row in payload["rows"]:
        lines.append(
            f"{row['label']}: sales {row['sales']}, ran {row['opps_ran']}, "
            f"demo rate {_rate_text(row['demo_rate'])}, opp2prelim {_rate_text(row['opp2prelim'])}."
        )
    return " ".join(lines)


def _render_compare(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return (
            f"{NO_APPROVED_DEFINITION} I have not calculated a change. "
            + str(payload.get("statement") or "")
        ).strip()
    lines = [payload.get("statement") or "Comparison."]
    if payload["period"].get("partial") or payload["comparison_period"].get("partial"):
        lines.append("Partial-period comparison.")
    for row in payload["rows"]:
        pp = row.get("percentage_points")
        pct = row.get("percent_change")
        extra = ""
        if pp is not None:
            extra = f" ({pp} percentage points)"
        elif pct is None:
            extra = " (percent change omitted; baseline is zero or missing)"
        else:
            extra = f" ({pct}% change)"
        lines.append(
            f"{row['metric_id']}: {row['current']} versus {row['prior']}, "
            f"absolute change {row['absolute_change']}{extra}."
        )
    return " ".join(lines)


def _evidence_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = []
    if not isinstance(payload, dict):
        return evidence
    link = payload.get("source_link")
    if link:
        evidence.append({"source_link": link, "data_as_of": payload.get("data_as_of"), "kind": "report"})
    for link in payload.get("source_links") or []:
        evidence.append({"source_link": link, "data_as_of": payload.get("data_as_of"), "kind": "report"})
    for metric in payload.get("metrics") or []:
        if metric.get("source_link"):
            evidence.append(
                {
                    "metric_id": metric.get("metric_id"),
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
                "Server tool payload follows. Add one short interpretation with no numerals. "
                "If you cannot, return an empty string.\n"
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
    identity = identity_from_headers(headers, settings_password=settings_password)
    if not chat_allowed(identity, config.allowed_roles):
        return _response(401, ok=False, code="unauthorized", answer=SIGN_IN_REQUIRED)
    assert identity is not None
    remembered = store.remembered_response(request_id, identity.actor_id)
    if remembered is not None:
        return {"status": 200, "body": remembered}
    lowered = " ".join(text.lower().split())
    if lowered in {"be concise", "answer briefly"}:
        store.set_preference(identity.actor_id, True)
        answer = "I will keep later answers short. Say forget my preferences to remove that."
        return _response(200, ok=True, code="preference", answer=answer)
    if lowered == "forget my preferences":
        store.set_preference(identity.actor_id, None)
        return _response(200, ok=True, code="preference", answer="I removed your display preferences.")
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
            if not filters["start"] or not filters["end"]:
                answer = "Which start and end dates should I use? The company overview chips can set them."
                code = "clarify"
            else:
                name = {
                    "company_summary": "get_company_summary",
                    "compare": "compare_periods",
                    "source_performance": "get_source_performance",
                }[decision_intent]
                args = {"start": filters["start"], "end": filters["end"], "sources": filters["sources"]}
                if decision_intent == "compare" and decision.matched_term in {"sales", "demo_rate", "opp2prelim", "ran", "created"}:
                    mapped = {"ran": "opps_ran", "created": "opps_created"}.get(decision.matched_term, decision.matched_term)
                    args["metric_ids"] = [mapped]
                if metrics is None:
                    answer = NO_APPROVED_DEFINITION + " Reporting functions are not available to this turn."
                    code = "metrics_unavailable"
                else:
                    tool_payload = execute(name, args, ctx)
                    if decision_intent == "company_summary":
                        answer = _render_summary(tool_payload)
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
    answer = _public_labels(answer)
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
                interpretation = _public_labels(interpretation)
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
            "definition_status": "approved" if tool_payload.get("official") else "not_approved",
        },
        "conversation_id": conversation,
        "request_id": request_id,
        "display_name": "Goose",
        "role_name": "Happy Solar Data Copilot",
        "prompt_version": PROMPT_VERSION,
        "dashboard_unaffected": True,
    }
    if code == "budget_limit":
        body["reset_date"] = model_note
        body["ok"] = False
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
