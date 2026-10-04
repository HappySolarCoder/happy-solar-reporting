# -*- coding: utf-8 -*-
"""Server-side configuration. Defaults keep the copilot off."""

from __future__ import annotations

import os
from dataclasses import dataclass

from copilot.prompt import PROMPT_VERSION
from copilot.rates import (
    MONTHLY_MODEL_CAP_MICRO,
    PINNED_LOCATION,
    PINNED_MODEL_ID,
    REQUESTED_OUTPUT_CEILING,
    TURN_CAP_MICRO,
    build_rate_card,
)


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def _positive_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class CopilotConfig:
    enabled: bool
    company_timezone: str | None
    billing_timezone: str | None
    allowed_roles: frozenset[str]
    ranking_roles: frozenset[str]
    monthly_model_micro: int
    turn_micro: int
    non_model_micro: int
    output_cap_enforced: bool
    max_output_tokens: int
    prompt_version: str
    knowledge_version: str
    model_id: str
    location: str
    google_cloud_project: str | None
    max_message_chars: int = 2000
    max_turns_per_day: int = 10
    max_turns_per_month: int = 100
    max_turns_per_conversation: int = 10
    max_requests_per_minute: int = 4
    max_active_per_user: int = 1
    max_active_company: int = 3
    max_tools_per_turn: int = 4
    max_rows_per_tool: int = 50
    default_rows: int = 25
    turn_timeout_seconds: int = 45
    conversation_retention_days: int = 30

    def model_cap_micro(self) -> int:
        """Reduce the USD 15 model allocation if non-model incremental cost threatens USD 20."""
        remaining = 20_000_000 - max(0, self.non_model_micro)
        return max(0, min(self.monthly_model_micro, remaining))


def config_from_env(env: dict[str, str] | None = None) -> CopilotConfig:
    source = os.environ if env is None else env
    model_id = (source.get("COPILOT_MODEL_ID") or PINNED_MODEL_ID).strip()
    location = (source.get("GOOGLE_CLOUD_LOCATION") or source.get("COPILOT_LOCATION") or PINNED_LOCATION).strip()
    company_tz = (source.get("COPILOT_COMPANY_TIMEZONE") or "").strip() or None
    billing_tz = (source.get("COPILOT_BILLING_TIMEZONE") or "").strip() or None
    project = (source.get("GOOGLE_CLOUD_PROJECT") or "").strip() or None
    # FIREBASE / GCP_PROJECT_ID belong to the data center. Do not treat them as
    # the inference project. GOOGLE_CLOUD_PROJECT is the copilot inference project.
    monthly = _positive_int(source.get("COPILOT_MONTHLY_MODEL_USD"), 15) * 1_000_000
    if monthly > MONTHLY_MODEL_CAP_MICRO:
        monthly = MONTHLY_MODEL_CAP_MICRO
    turn = _positive_int(source.get("COPILOT_MAX_TURN_MICRO"), TURN_CAP_MICRO)
    if turn > TURN_CAP_MICRO:
        turn = TURN_CAP_MICRO
    non_model_usd = source.get("COPILOT_INCREMENTAL_NON_MODEL_USD") or "0"
    try:
        non_model = int(round(float(non_model_usd) * 1_000_000))
    except ValueError:
        non_model = 0
    if non_model < 0:
        non_model = 0
    return CopilotConfig(
        enabled=_flag(source.get("COPILOT_ENABLED"), False),
        company_timezone=company_tz,
        billing_timezone=billing_tz,
        allowed_roles=_csv(source.get("COPILOT_ALLOWED_ROLES")),
        ranking_roles=_csv(source.get("COPILOT_RANKING_ROLES")),
        monthly_model_micro=monthly,
        turn_micro=turn,
        non_model_micro=non_model,
        output_cap_enforced=_flag(source.get("COPILOT_OUTPUT_CAP_ENFORCED"), False),
        max_output_tokens=_positive_int(source.get("COPILOT_MAX_OUTPUT_TOKENS"), REQUESTED_OUTPUT_CEILING),
        prompt_version=PROMPT_VERSION,
        knowledge_version=(source.get("COPILOT_KNOWLEDGE_VERSION") or "seed-draft-2026-10-04").strip(),
        model_id=model_id,
        location=location,
        google_cloud_project=project,
    )


def rate_card_for(config: CopilotConfig):
    return build_rate_card(
        output_cap_enforced=config.output_cap_enforced,
        max_output_tokens=config.max_output_tokens,
    )


def configuration_problems(config: CopilotConfig, today) -> list[str]:
    """Reasons paid inference must stay off. Empty does not by itself enable the feature."""
    from copilot.rates import PINNED_LOCATION, PINNED_MODEL_ID, max_affordable_calls

    problems: list[str] = []
    if not config.enabled:
        problems.append("COPILOT_ENABLED is not true")
    if not config.company_timezone:
        problems.append("COPILOT_COMPANY_TIMEZONE is unset")
    if not config.billing_timezone:
        problems.append("COPILOT_BILLING_TIMEZONE is unset")
    if not config.allowed_roles:
        problems.append("COPILOT_ALLOWED_ROLES is empty; no application role is authorized to chat")
    if config.model_id != PINNED_MODEL_ID:
        problems.append("COPILOT_MODEL_ID does not match the pinned rate card")
    if config.location != PINNED_LOCATION:
        problems.append("model location does not match the pinned global rate card")
    if not config.google_cloud_project:
        problems.append("GOOGLE_CLOUD_PROJECT is unset")
    card = rate_card_for(config)
    if card.expired(today):
        problems.append("rate card review date has passed")
    if max_affordable_calls(12_000, card, turn_cap_micro=config.turn_micro) < 1:
        problems.append("worst-case model call does not fit the turn cap")
    if config.model_cap_micro() <= 0:
        problems.append("incremental non-model cost consumes the model allocation")
    return problems
