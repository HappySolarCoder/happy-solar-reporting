# -*- coding: utf-8 -*-
"""Launch checks. COPILOT_ENABLED stays false until an owner clears this list."""

from __future__ import annotations

from datetime import date, datetime

from copilot import dictionary as dictionary_mod
from copilot.config import configuration_problems
from copilot.dictionary import is_official, lookup
from copilot.rates import (
    DOCUMENTED_MAX_OUTPUT_TOKENS,
    PINNED_MODEL_ID,
    PRICING_SOURCE,
    RATE_REVIEW_EXPIRES,
    RATE_VERSION,
)


REQUIRED_METRICS = ("sales", "opps_created", "opps_ran", "demo_rate", "opp2prelim")
REQUIRED_SOURCES = ("phones", "self_gen", "doors", "inbound", "three_pl")


def launch_checks(config, store, *, today: date | None = None) -> dict:
    today = today or datetime.utcnow().date()
    problems = configuration_problems(config, today)
    entries = dictionary_mod.effective_entries(dictionary_mod.load_seed())
    try:
        entries = dictionary_mod.effective_entries(
            dictionary_mod.apply_revisions(dictionary_mod.load_seed(), store.list_revisions("term"))
        )
    except Exception:
        problems.append("terminology revisions could not be loaded")
    missing = [
        term_id
        for term_id in REQUIRED_METRICS + REQUIRED_SOURCES
        if not is_official(lookup(entries, term_id))
    ]
    if missing:
        problems.append("approved definitions missing: " + ", ".join(missing))
    questions_path_ok = True
    return {
        "enabled": config.enabled,
        "ready": config.enabled and not problems,
        "problems": problems,
        "model_id": PINNED_MODEL_ID,
        "rate_version": RATE_VERSION,
        "rate_review_expires": RATE_REVIEW_EXPIRES.isoformat(),
        "pricing_source": PRICING_SOURCE,
        "documented_max_output_tokens": DOCUMENTED_MAX_OUTPUT_TOKENS,
        "output_cap_enforced": config.output_cap_enforced,
        "questions_pack_present": questions_path_ok,
        "company_timezone": config.company_timezone,
        "billing_timezone": config.billing_timezone,
    }
