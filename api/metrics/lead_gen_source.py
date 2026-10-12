# -*- coding: utf-8 -*-
"""One rule for when a Lead Gen Source counts as Inbound.

Inbound is the word Inbound, or a Facebook Quick Form variant such as
"Facebook Quick Form" and "FB Quick Form". Matching is case-insensitive
and ignores spaces, hyphens, and underscores. "3PL/Inbound" is not Inbound.
"""

from __future__ import annotations

from typing import Any

INBOUND_LABEL = "Inbound"
_QUICK_FORM_COMPACT = frozenset({"facebookquickform", "fbquickform"})


def _compact(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold()
    text = text.replace("-", " ").replace("_", " ").replace("/", " ")
    return "".join(text.split())


def is_facebook_quick_form_source(value: Any) -> bool:
    """True for Facebook Quick Form and FB Quick Form, including spacing variants."""
    return _compact(value) in _QUICK_FORM_COMPACT


def is_inbound_lead_source(value: Any) -> bool:
    """True for Inbound and for a Facebook Quick Form variant. 3PL does not match."""
    compact = _compact(value)
    return compact == "inbound" or compact in _QUICK_FORM_COMPACT


def inbound_source_label(value: Any) -> str | None:
    """'Inbound' when this source counts as Inbound. Otherwise None."""
    if is_inbound_lead_source(value):
        return INBOUND_LABEL
    return None
