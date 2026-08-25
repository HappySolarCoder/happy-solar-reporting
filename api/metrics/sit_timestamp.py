# -*- coding: utf-8 -*-

"""First-write-wins sit/no-sit timestamp for FMA Demo Rate.

Warehouse fields (ghl-firestore-sync-v2, do not invent new ones):
- dispositionValue from GHL custom field GYGpLKBPfMpiBqyU2ogQ (Sit / No Sit)
- appointmentOccurredAt — intended stable slot; first-written from current
  appointmentStartTime when Sit/No Sit is first marked, then preserved
- dispositionDate — written once when Sit/No Sit is first marked, then preserved

Locked warehouse example (do not invent another; not 2025 PDDpxi8LpSVc4j3FTb50):
Joanne Miechowski OF48x1PrhxehlJS3ReMc / vPLhdbmd9ggy9d0i0GTY
- CURRENT appointmentOccurredAt 2026-08-26T18:00:00Z (bug; copied from follow-up start)
- FREEZE dispositionDate 2026-08-20T20:45:48.990Z (first Sit write; lastStageChangeAt
  2026-08-20T20:45:46.331Z New Appointment → Demo-Negotiating)
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
