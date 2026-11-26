# -*- coding: utf-8 -*-

"""Shared pipeline matching for Operations Control filters.

Sweeper is the Sweeper and Rehash pipelines. It is not the Phones lead source.
A territory filter and the Sweeper filter both have to match.
"""

from __future__ import annotations

SWEEPER_PIPELINES = frozenset({"sweeper", "rehash"})

# Empower+ (location MMKRDviKggXzlcHQTnvZ). Never a sales-funnel pipeline.
# Match the id, not the name: the name can change.
NON_FUNNEL_PIPELINE_IDS = frozenset({"5hPKCGzAskcC6LEZuc1H"})


def compact_str(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def is_non_funnel_pipeline(pipeline_id: object) -> bool:
    """True when this pipeline id is outside every sales-funnel metric."""
    return compact_str(pipeline_id).strip() in NON_FUNNEL_PIPELINE_IDS


def normalize_pipeline_name(name: object) -> str:
    return " ".join(str(name or "").strip().lower().split())


def pipeline_in_scope(
    name: object,
    *,
    pipeline: str | None = None,
    sweeper: bool = False,
) -> bool:
    low = normalize_pipeline_name(name)
    if sweeper and low not in SWEEPER_PIPELINES:
        return False
    want = normalize_pipeline_name(pipeline) if pipeline else ""
    if not want:
        return True
    if want in SWEEPER_PIPELINES or want in {"sweeper group", "sweeper/rehash"}:
        return low in SWEEPER_PIPELINES
    return low == want


def truthy_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
