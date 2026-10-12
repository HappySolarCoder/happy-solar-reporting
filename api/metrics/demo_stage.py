# -*- coding: utf-8 -*-

"""Shared demo-stage check.

A Demo-* stage, Sold, or Sale Cancelled is a demo. Sold and Sale
Cancelled imply a demo. Sale Cancelled counts exactly like Sold: it is
a demo only when the contact has no earlier Demo-* stage, and otherwise
it attaches to that earlier demo. One Legger (only one spouse present)
is not a demo and gets no demo credit.
"""

from __future__ import annotations

from typing import Any


def fold_stage(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    return " ".join(text.split())


def stage_is_demo_star(stage_name: Any) -> bool:
    """A Demo-* stage. Sold, Sale Cancelled, and One Legger are not Demo-*."""
    folded = fold_stage(stage_name)
    return folded == "demo" or folded.startswith("demo ")


def stage_is_sold(stage_name: Any) -> bool:
    folded = fold_stage(stage_name)
    return folded == "sold" or folded.startswith("sold ")


def stage_is_sale_cancelled(stage_name: Any) -> bool:
    folded = fold_stage(stage_name)
    return folded in {"sale cancelled", "sale canceled"} or folded.startswith("sale cancelled ") or folded.startswith("sale canceled ")


def stage_is_demo(stage_name: Any) -> bool:
    """A Demo-* stage, Sold, or Sale Cancelled is a demo. One Legger is not.

    Sale Cancelled matches Sold. The contact-level rule — count it only
    when there is no earlier Demo-* stage, otherwise attach it to that
    demo — lives with the FMA helper that sees the whole contact.
    """
    if not fold_stage(stage_name):
        return False
    return (
        stage_is_sold(stage_name)
        or stage_is_sale_cancelled(stage_name)
        or stage_is_demo_star(stage_name)
    )


def stage_is_one_legger(stage_name: Any) -> bool:
    folded = fold_stage(stage_name)
    return bool(folded) and "one legger" in folded


def stage_is_new_appointment(stage_name: Any) -> bool:
    """An opportunity still on New Appointment has not run."""
    return fold_stage(stage_name) == "new appointment"
