# -*- coding: utf-8 -*-

"""First-write-wins sit/no-sit timestamp for FMA Demo Rate.

Warehouse fields (ghl-firestore-sync-v2, do not invent new ones):
- dispositionValue from GHL custom field GYGpLKBPfMpiBqyU2ogQ (Sit / No Sit)
- appointmentOccurredAt — intended stable slot; first-written from current
  appointmentStartTime when Sit/No Sit is first marked, then preserved
- dispositionDate — written once when Sit/No Sit is first marked, then preserved

If the rep moves the GHL appointment to a follow-up *before* marking Sit/No Sit,
the first appointmentOccurredAt write is already the follow-up. dispositionDate
still records the first outcome write. Use the earlier stamp so the sit stays on
the original appointment day and a later follow-up is not a second sit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def as_aware_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def frozen_sit_timestamp(
    appointment_occurred_at: Any = None,
    disposition_date: Any = None,
) -> datetime | None:
    """First Sit/No Sit write wins. Earlier of occurred-at and dispositionDate."""
    occurred = as_aware_utc(appointment_occurred_at)
    first_write = as_aware_utc(disposition_date)
    if occurred and first_write:
        return occurred if occurred <= first_write else first_write
    return occurred or first_write
