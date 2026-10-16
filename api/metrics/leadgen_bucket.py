# -*- coding: utf-8 -*-
"""Daily dashboard Lead Generation buckets.

Every opportunity lands in exactly one bucket so the buckets add up to
Opportunities Created. Sweeper/Rehash/Virtual wins first:
- contact Lead Gen Source is Sweeper, Rehash, Phones, or Virtual
- Sweeper/Rehash Last Name is filled (contact, then opportunity)
- pipeline is Sweeper or Rehash
Then Doors, Self Gen, 3PL/Inbound (Inbound uses lead_gen_source rules,
including Facebook Quick Form), and Other for anything left.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_D = Path(__file__).resolve().parent
if str(_D) not in sys.path:
    sys.path.insert(0, str(_D))

from lead_gen_source import is_inbound_lead_source
from pipeline_scope import SWEEPER_PIPELINES, normalize_pipeline_name
from sweeper_rehash_attribution import is_blank_last_name

SWEEPER_VIRTUAL = "Sweeper/Rehash/Virtual"
DOORS = "Doors"
SELF_GEN = "Self Gen"
THREE_PL_INBOUND = "3PL/Inbound"
OTHER = "Other"
BUCKETS = (DOORS, SELF_GEN, THREE_PL_INBOUND, SWEEPER_VIRTUAL, OTHER)

_SV_SOURCES = frozenset({"sweeper", "rehash", "phones", "virtual"})


def _key(value: Any) -> str:
    return "".join(str(value or "").strip().casefold().replace("-", " ").replace("_", " ").split())


def leadgen_bucket(lead_source: Any, sweeper_last_name: Any, pipeline_name: Any) -> str:
    k = _key(lead_source)
    if (
        k in _SV_SOURCES
        or not is_blank_last_name(sweeper_last_name)
        or normalize_pipeline_name(pipeline_name) in SWEEPER_PIPELINES
    ):
        return SWEEPER_VIRTUAL
    if k == "doors":
        return DOORS
    if k in {"selfgen", "selfgenerated"}:
        return SELF_GEN
    if k == "3pl" or is_inbound_lead_source(lead_source):
        return THREE_PL_INBOUND
    return OTHER
