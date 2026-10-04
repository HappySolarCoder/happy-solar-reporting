# -*- coding: utf-8 -*-
"""Pinned Gemini Flash price card.

Verified 2026-10-04 against Google Cloud Agent Platform pricing:
https://cloud.google.com/vertex-ai/generative-ai/pricing

Model page:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-lite

Standard global price (not priority, flex, batch, or promotional credit):
- gemini-3.1-flash-lite input text/image/video/audio: USD 0.25 / 1M tokens
- text output, including response and reasoning: USD 1.50 / 1M tokens

Documented maximum output tokens: 65,536.
thinking_level MINIMAL is the lowest supported setting. Google describes it as
a relative allowance, not a hard token guarantee. thinking_budget is not used
on Gemini 3; Google documents that parameter as unsupported for these models.

Until an owner verifies that max_output_tokens hard-caps response plus
reasoning, reservations use the documented 65,536 output ceiling. At these
rates that ceiling fits one model call under the USD 0.15 turn cap and does
not fit three. Paid calls stay inside that computed call limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


PINNED_MODEL_ID = "gemini-3.1-flash-lite"
PINNED_LOCATION = "global"
THINKING_LEVEL = "MINIMAL"
RATE_VERSION = "vertex-gemini-3.1-flash-lite-global-2026-10-04"
RATE_VERIFIED_ON = date(2026, 10, 4)
RATE_REVIEW_EXPIRES = date(2026, 11, 3)
PRICING_SOURCE = "https://cloud.google.com/vertex-ai/generative-ai/pricing"
MODEL_SOURCE = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-lite"

# Micro-USD per 1,000,000 tokens. 1 USD = 1_000_000 micro-USD.
INPUT_MICRO_PER_MILLION = 250_000
OUTPUT_MICRO_PER_MILLION = 1_500_000
DOCUMENTED_MAX_OUTPUT_TOKENS = 65_536
INPUT_TOKEN_CEILING = 12_000
REQUESTED_OUTPUT_CEILING = 2_048

TURN_CAP_MICRO = 150_000  # USD 0.15
MONTHLY_MODEL_CAP_MICRO = 15_000_000  # USD 15
INCREMENTAL_TARGET_MICRO = 20_000_000  # USD 20
WARN_MICRO = (10_000_000, 12_000_000)
SAFETY_MARGIN_NUMERATOR = 125
SAFETY_MARGIN_DENOMINATOR = 100


@dataclass(frozen=True)
class RateCard:
    model_id: str
    location: str
    thinking_level: str
    rate_version: str
    verified_on: date
    review_expires: date
    input_micro_per_million: int
    output_micro_per_million: int
    documented_max_output_tokens: int
    output_cap_enforced: bool
    max_output_tokens: int
    pricing_source: str

    def expired(self, today: date) -> bool:
        return today > self.review_expires

    def billable_output_tokens(self) -> int:
        if self.output_cap_enforced:
            return self.max_output_tokens
        return self.documented_max_output_tokens


def build_rate_card(*, output_cap_enforced: bool, max_output_tokens: int) -> RateCard:
    cap = max_output_tokens if output_cap_enforced else DOCUMENTED_MAX_OUTPUT_TOKENS
    if output_cap_enforced:
        cap = max(1, min(max_output_tokens, DOCUMENTED_MAX_OUTPUT_TOKENS))
    return RateCard(
        model_id=PINNED_MODEL_ID,
        location=PINNED_LOCATION,
        thinking_level=THINKING_LEVEL,
        rate_version=RATE_VERSION,
        verified_on=RATE_VERIFIED_ON,
        review_expires=RATE_REVIEW_EXPIRES,
        input_micro_per_million=INPUT_MICRO_PER_MILLION,
        output_micro_per_million=OUTPUT_MICRO_PER_MILLION,
        documented_max_output_tokens=DOCUMENTED_MAX_OUTPUT_TOKENS,
        output_cap_enforced=output_cap_enforced,
        max_output_tokens=cap,
        pricing_source=PRICING_SOURCE,
    )


def call_micro(input_tokens: int, output_tokens: int, card: RateCard) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    numerator = (
        input_tokens * card.input_micro_per_million
        + output_tokens * card.output_micro_per_million
    )
    return (numerator + 1_000_000 - 1) // 1_000_000


def reservation_micro(input_tokens: int, output_tokens: int, calls: int, card: RateCard) -> int:
    if calls < 1:
        raise ValueError("calls must be positive")
    base = call_micro(input_tokens, output_tokens, card) * calls
    return (base * SAFETY_MARGIN_NUMERATOR + SAFETY_MARGIN_DENOMINATOR - 1) // SAFETY_MARGIN_DENOMINATOR


def max_affordable_calls(input_tokens: int, card: RateCard, *, turn_cap_micro: int, call_ceiling: int = 3) -> int:
    """How many worst-case calls fit under the turn cap. Zero disables paid calls."""
    output_tokens = card.billable_output_tokens()
    affordable = 0
    for calls in range(1, call_ceiling + 1):
        if reservation_micro(input_tokens, output_tokens, calls, card) <= turn_cap_micro:
            affordable = calls
        else:
            break
    return affordable
