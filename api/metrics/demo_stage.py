# -*- coding: utf-8 -*-

"""Shared demo-stage check.

A Demo-* stage or Sold is a demo. Sold implies a demo. One Legger
(only one spouse present) is not a demo and gets no demo credit.
Sale cancelled is not a demo.
"""

from __future__ import annotations

from typing import Any


def fold_stage(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    return " ".join(text.split())


def stage_is_demo(stage_name: Any) -> bool:
    """A Demo-* stage or Sold is a demo. One Legger is not."""
    folded = fold_stage(stage_name)
    if not folded:
        return False
    if folded == "sold" or folded.startswith("sold "):
        return True
    return folded == "demo" or folded.startswith("demo ")


def stage_is_one_legger(stage_name: Any) -> bool:
    folded = fold_stage(stage_name)
    return bool(folded) and "one legger" in folded
