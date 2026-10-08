# -*- coding: utf-8 -*-
"""Durable ledger operations. MemoryStore is the test double. Firestore is production.

Fail closed: missing identity, pricing, or ledger blocks a reservation.
Client disconnects and unknown usage do not release an open reservation.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from copilot.messages import QUOTA_ACTIVE, QUOTA_COMPANY, QUOTA_DAY, QUOTA_MINUTE, QUOTA_MONTH


class LedgerUnavailable(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    def __init__(self, reset_date: str):
        super().__init__("monthly model allowance reached")
        self.reset_date = reset_date


class TurnTooExpensive(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Reservation:
    request_id: str
    actor_id: str
    month_key: str
    amount_micro: int
    status: str
    created_at: str
    actual_micro: int | None = None
    model_id: str | None = None
    rate_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    dispatched: bool = False


@dataclass
class MemoryStore:
    months: dict[str, dict[str, int]] = field(default_factory=dict)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    quota_days: dict[tuple[str, str], int] = field(default_factory=dict)
    quota_months: dict[tuple[str, str], int] = field(default_factory=dict)
    minute_hits: dict[str, list[datetime]] = field(default_factory=dict)
    active_users: dict[str, str] = field(default_factory=dict)
    conversations: dict[str, dict[str, Any]] = field(default_factory=dict)
    revisions: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)
    paused: bool = False
    company_active: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def month_view(self, month_key: str) -> dict[str, int]:
        row = self.months.get(month_key) or {"spent": 0, "reserved": 0}
        return {"spent": row["spent"], "reserved": row["reserved"]}

    def begin_turn(
        self,
        *,
        actor_id: str,
        turn_id: str,
        month_key: str,
        now: datetime,
        limits: dict[str, int],
    ) -> None:
        with self._lock:
            if self.active_users.get(actor_id):
                raise QuotaExceeded(QUOTA_ACTIVE)
            if self.company_active >= limits["max_active_company"]:
                raise QuotaExceeded(QUOTA_COMPANY)
            day_key = now.date().isoformat()
            day = self.quota_days.get((actor_id, day_key), 0)
            month = self.quota_months.get((actor_id, month_key), 0)
            if day >= limits["max_turns_per_day"]:
                raise QuotaExceeded(QUOTA_DAY)
            if month >= limits["max_turns_per_month"]:
                raise QuotaExceeded(QUOTA_MONTH)
            hits = [stamp for stamp in self.minute_hits.get(actor_id, []) if (now - stamp).total_seconds() < 60]
            if len(hits) >= limits["max_requests_per_minute"]:
                raise QuotaExceeded(QUOTA_MINUTE)
            hits.append(now)
            self.minute_hits[actor_id] = hits
            self.quota_days[(actor_id, day_key)] = day + 1
            self.quota_months[(actor_id, month_key)] = month + 1
            self.active_users[actor_id] = turn_id
            self.company_active += 1

    def end_turn(self, actor_id: str, turn_id: str) -> None:
        with self._lock:
            if self.active_users.get(actor_id) == turn_id:
                self.active_users.pop(actor_id, None)
                self.company_active = max(0, self.company_active - 1)

    def reserve(
        self,
        *,
        request_id: str,
        actor_id: str,
        month_key: str,
        amount_micro: int,
        monthly_cap_micro: int,
        reset_date: str,
        now: datetime,
    ) -> Reservation:
        if amount_micro < 0:
            raise LedgerUnavailable("reservation amount is invalid")
        with self._lock:
            existing = self.reservations.get(request_id)
            if existing is not None:
                return existing
            row = self.months.setdefault(month_key, {"spent": 0, "reserved": 0})
            if row["spent"] + row["reserved"] + amount_micro > monthly_cap_micro:
                raise BudgetExceeded(reset_date)
            row["reserved"] += amount_micro
            reservation = Reservation(
                request_id=request_id,
                actor_id=actor_id,
                month_key=month_key,
                amount_micro=amount_micro,
                status="open",
                created_at=now.isoformat(),
            )
            self.reservations[request_id] = reservation
            return reservation

    def mark_dispatched(self, request_id: str) -> None:
        with self._lock:
            reservation = self.reservations.get(request_id)
            if reservation is None or reservation.status != "open":
                raise LedgerUnavailable("reservation is not open")
            reservation.dispatched = True

    def release_if_not_dispatched(self, request_id: str) -> None:
        with self._lock:
            reservation = self.reservations.get(request_id)
            if reservation is None or reservation.status != "open":
                return
            if reservation.dispatched:
                return
            row = self.months[reservation.month_key]
            row["reserved"] -= reservation.amount_micro
            reservation.status = "released"

    def retain(self, request_id: str) -> None:
        """Keep the full reservation. Used after dispatch when usage is unknown."""
        with self._lock:
            reservation = self.reservations.get(request_id)
            if reservation is None or reservation.status != "open":
                return
            reservation.status = "unresolved"

    def settle(
        self,
        request_id: str,
        *,
        actual_micro: int,
        model_id: str,
        rate_version: str,
        input_tokens: int,
        output_tokens: int,
        thoughts_tokens: int,
    ) -> None:
        with self._lock:
            reservation = self.reservations.get(request_id)
            if reservation is None:
                raise LedgerUnavailable("reservation missing")
            if reservation.status == "settled":
                return
            if reservation.status != "open":
                raise LedgerUnavailable("reservation is not open")
            if actual_micro < 0:
                raise LedgerUnavailable("actual cost is invalid")
            row = self.months[reservation.month_key]
            row["reserved"] -= reservation.amount_micro
            if row["reserved"] < 0:
                raise LedgerUnavailable("reserved balance went negative")
            row["spent"] += actual_micro
            reservation.status = "settled"
            reservation.actual_micro = actual_micro
            reservation.model_id = model_id
            reservation.rate_version = rate_version
            reservation.input_tokens = input_tokens
            reservation.output_tokens = output_tokens
            reservation.thoughts_tokens = thoughts_tokens

    def fits_remaining(self, request_id: str, additional_micro: int) -> bool:
        with self._lock:
            reservation = self.reservations.get(request_id)
            if reservation is None or reservation.status != "open":
                return False
            return additional_micro <= reservation.amount_micro

    def list_revisions(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is None:
            return list(self.revisions)
        return [item for item in self.revisions if item.get("kind") == kind]

    def add_revision(self, revision: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            stored = dict(revision)
            stored.setdefault("revision_id", str(uuid.uuid4()))
            self.revisions.append(stored)
            self.audit.append({"type": "revision", "revision_id": stored["revision_id"], "actor": stored.get("actor")})
            return stored

    def add_audit(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.audit.append(dict(event))

    def get_conversation(self, conversation_id: str, actor_id: str) -> dict[str, Any] | None:
        row = self.conversations.get(conversation_id)
        if row is None or row.get("actor_id") != actor_id:
            return None
        return row

    def save_conversation(self, conversation: dict[str, Any]) -> None:
        with self._lock:
            self.conversations[conversation["conversation_id"]] = conversation

    def prune_conversations(self, *, now: datetime, retention_days: int) -> None:
        cutoff = now - timedelta(days=retention_days)
        with self._lock:
            doomed = []
            for key, row in self.conversations.items():
                updated = datetime.fromisoformat(row["updated_at"])
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if updated < cutoff:
                    doomed.append(key)
            for key in doomed:
                # Keep a stub so financial audit is not the conversation text.
                self.conversations[key]["messages"] = []
                self.conversations[key]["pruned"] = True

    def set_paused(self, paused: bool, *, actor: str) -> None:
        with self._lock:
            self.paused = paused
            self.audit.append({"type": "pause", "paused": paused, "actor": actor})

    def preference(self, actor_id: str) -> dict[str, Any]:
        return dict(self.preferences.get(actor_id) or {})

    def set_preference(self, actor_id: str, concise: bool | None) -> None:
        with self._lock:
            if concise is None:
                self.preferences.pop(actor_id, None)
            else:
                self.preferences[actor_id] = {"concise": concise}

    def remember_response(self, request_id: str, actor_id: str, response: dict[str, Any]) -> None:
        with self._lock:
            self.idempotency[request_id] = {"actor_id": actor_id, "body": response}

    def remembered_response(self, request_id: str, actor_id: str) -> dict[str, Any] | None:
        row = self.idempotency.get(request_id)
        if not row or row.get("actor_id") != actor_id:
            return None
        return row.get("body")

    def add_feedback(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            stored = dict(item)
            stored.setdefault("feedback_id", str(uuid.uuid4()))
            self.feedback.append(stored)
            return stored

    def add_suggestion(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            stored = dict(item)
            stored.setdefault("suggestion_id", str(uuid.uuid4()))
            self.suggestions.append(stored)
            return stored
