# -*- coding: utf-8 -*-
"""Firestore ledger. Missing credentials fail closed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from copilot.store import BudgetExceeded, LedgerUnavailable, MemoryStore, QuotaExceeded


class UnavailableStore(MemoryStore):
    """In-memory reads of nothing. Every paid or quota operation fails closed."""

    def __init__(self):
        super().__init__()
        self.reason = "ledger unavailable"

    def begin_turn(self, **kwargs):
        raise LedgerUnavailable(self.reason)

    def reserve(self, **kwargs):
        raise LedgerUnavailable(self.reason)

    def add_revision(self, revision):
        raise LedgerUnavailable(self.reason)

    def set_paused(self, paused: bool, *, actor: str) -> None:
        raise LedgerUnavailable(self.reason)

    def add_feedback(self, item):
        raise LedgerUnavailable(self.reason)

    def add_suggestion(self, item):
        raise LedgerUnavailable(self.reason)


def firestore_client():
    import json
    import os

    from google.cloud import firestore
    from google.oauth2 import service_account

    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        return None
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


class FirestoreStore:
    """Atomic monthly ledger on the existing Firestore database."""

    def __init__(self, client):
        self.client = client
        self.paused = False

    def _refresh_pause(self) -> None:
        snap = self.client.collection("copilot_config").document("runtime").get()
        data = snap.to_dict() or {}
        self.paused = bool(data.get("paused"))

    def month_view(self, month_key: str) -> dict[str, int]:
        snap = self.client.collection("copilot_ledger").document(month_key).get()
        data = snap.to_dict() or {}
        return {"spent": int(data.get("spent") or 0), "reserved": int(data.get("reserved") or 0)}

    def reserve(self, *, request_id: str, actor_id: str, month_key: str, amount_micro: int, monthly_cap_micro: int, reset_date: str, now: datetime):
        from google.cloud import firestore

        month_ref = self.client.collection("copilot_ledger").document(month_key)
        res_ref = self.client.collection("copilot_reservations").document(request_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def _run(transaction):
            existing = res_ref.get(transaction=transaction)
            if existing.exists:
                return existing.to_dict()
            month = month_ref.get(transaction=transaction)
            data = month.to_dict() or {"spent": 0, "reserved": 0}
            spent = int(data.get("spent") or 0)
            reserved = int(data.get("reserved") or 0)
            if spent + reserved + amount_micro > monthly_cap_micro:
                raise BudgetExceeded(reset_date)
            transaction.set(
                month_ref,
                {"spent": spent, "reserved": reserved + amount_micro, "month_key": month_key},
                merge=True,
            )
            body = {
                "request_id": request_id,
                "actor_id": actor_id,
                "month_key": month_key,
                "amount_micro": amount_micro,
                "status": "open",
                "created_at": now.isoformat(),
                "dispatched": False,
            }
            transaction.set(res_ref, body)
            return body

        try:
            return _SimpleReservation(_run(transaction))
        except BudgetExceeded:
            raise
        except Exception as exc:
            raise LedgerUnavailable("ledger transaction failed") from exc

    def mark_dispatched(self, request_id: str) -> None:
        ref = self.client.collection("copilot_reservations").document(request_id)
        snap = ref.get()
        if not snap.exists or (snap.to_dict() or {}).get("status") != "open":
            raise LedgerUnavailable("reservation is not open")
        ref.set({"dispatched": True}, merge=True)

    def release_if_not_dispatched(self, request_id: str) -> None:
        self._move(request_id, "released", release=True, only_if_not_dispatched=True)

    def retain(self, request_id: str) -> None:
        ref = self.client.collection("copilot_reservations").document(request_id)
        snap = ref.get()
        data = snap.to_dict() or {}
        if data.get("status") == "open":
            ref.set({"status": "unresolved"}, merge=True)

    def settle(self, request_id: str, *, actual_micro: int, model_id: str, rate_version: str, input_tokens: int, output_tokens: int, thoughts_tokens: int) -> None:
        from google.cloud import firestore

        month_key = (self.client.collection("copilot_reservations").document(request_id).get().to_dict() or {}).get("month_key")
        if not month_key:
            raise LedgerUnavailable("reservation missing")
        month_ref = self.client.collection("copilot_ledger").document(month_key)
        res_ref = self.client.collection("copilot_reservations").document(request_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def _run(transaction):
            res = res_ref.get(transaction=transaction).to_dict() or {}
            if res.get("status") == "settled":
                return
            if res.get("status") != "open":
                raise LedgerUnavailable("reservation is not open")
            month = month_ref.get(transaction=transaction).to_dict() or {"spent": 0, "reserved": 0}
            reserved = int(month.get("reserved") or 0) - int(res.get("amount_micro") or 0)
            if reserved < 0:
                raise LedgerUnavailable("reserved balance went negative")
            spent = int(month.get("spent") or 0) + int(actual_micro)
            transaction.set(month_ref, {"spent": spent, "reserved": reserved}, merge=True)
            transaction.set(
                res_ref,
                {
                    "status": "settled",
                    "actual_micro": actual_micro,
                    "model_id": model_id,
                    "rate_version": rate_version,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "thoughts_tokens": thoughts_tokens,
                },
                merge=True,
            )

        try:
            _run(transaction)
        except LedgerUnavailable:
            raise
        except Exception as exc:
            raise LedgerUnavailable("settle failed") from exc

    def fits_remaining(self, request_id: str, additional_micro: int) -> bool:
        data = self.client.collection("copilot_reservations").document(request_id).get().to_dict() or {}
        return data.get("status") == "open" and additional_micro <= int(data.get("amount_micro") or 0)

    def _move(self, request_id: str, status: str, *, release: bool, only_if_not_dispatched: bool) -> None:
        from google.cloud import firestore

        res_ref = self.client.collection("copilot_reservations").document(request_id)
        snap = res_ref.get()
        data = snap.to_dict() or {}
        if data.get("status") != "open":
            return
        if only_if_not_dispatched and data.get("dispatched"):
            return
        month_key = data.get("month_key")
        transaction = self.client.transaction()
        month_ref = self.client.collection("copilot_ledger").document(month_key)

        @firestore.transactional
        def _run(transaction):
            month = month_ref.get(transaction=transaction).to_dict() or {"spent": 0, "reserved": 0}
            reserved = int(month.get("reserved") or 0)
            if release:
                reserved -= int(data.get("amount_micro") or 0)
            transaction.set(month_ref, {"reserved": reserved}, merge=True)
            transaction.set(res_ref, {"status": status}, merge=True)

        _run(transaction)

    def begin_turn(self, *, actor_id: str, turn_id: str, month_key: str, now: datetime, limits: dict[str, int]) -> None:
        from google.cloud import firestore

        self._refresh_pause()
        ref = self.client.collection("copilot_quota").document(f"{actor_id}_{now.date().isoformat()}")
        active_ref = self.client.collection("copilot_active").document("company")
        transaction = self.client.transaction()

        @firestore.transactional
        def _run(transaction):
            quota = ref.get(transaction=transaction).to_dict() or {"day": 0, "months": {}, "minute": []}
            active = active_ref.get(transaction=transaction).to_dict() or {"users": {}, "count": 0}
            users = dict(active.get("users") or {})
            if users.get(actor_id):
                raise QuotaExceeded("one active turn per user")
            if int(active.get("count") or 0) >= limits["max_active_company"]:
                raise QuotaExceeded("company concurrency limit")
            day = int(quota.get("day") or 0)
            months = dict(quota.get("months") or {})
            month_count = int(months.get(month_key) or 0)
            if day >= limits["max_turns_per_day"]:
                raise QuotaExceeded("daily turn limit")
            if month_count >= limits["max_turns_per_month"]:
                raise QuotaExceeded("monthly turn limit")
            months[month_key] = month_count + 1
            users[actor_id] = turn_id
            transaction.set(ref, {"day": day + 1, "months": months}, merge=True)
            transaction.set(active_ref, {"users": users, "count": int(active.get("count") or 0) + 1})

        try:
            _run(transaction)
        except QuotaExceeded:
            raise
        except Exception as exc:
            raise LedgerUnavailable("quota transaction failed") from exc

    def end_turn(self, actor_id: str, turn_id: str) -> None:
        from google.cloud import firestore

        active_ref = self.client.collection("copilot_active").document("company")
        transaction = self.client.transaction()

        @firestore.transactional
        def _run(transaction):
            active = active_ref.get(transaction=transaction).to_dict() or {"users": {}, "count": 0}
            users = dict(active.get("users") or {})
            if users.get(actor_id) == turn_id:
                users.pop(actor_id, None)
                transaction.set(active_ref, {"users": users, "count": max(0, int(active.get("count") or 0) - 1)})

        try:
            _run(transaction)
        except Exception as exc:
            raise LedgerUnavailable("could not release turn slot") from exc

    def list_revisions(self, kind: str | None = None) -> list[dict[str, Any]]:
        try:
            docs = self.client.collection("copilot_revisions").stream()
        except Exception as exc:
            raise LedgerUnavailable("revisions unavailable") from exc
        rows = []
        for doc in docs:
            data = doc.to_dict() or {}
            if kind is None or data.get("kind") == kind:
                rows.append(data)
        return rows

    def add_revision(self, revision: dict[str, Any]) -> dict[str, Any]:
        try:
            self.client.collection("copilot_revisions").document(revision["revision_id"]).set(revision)
            self.add_audit({"type": "revision", "revision_id": revision["revision_id"], "actor": revision.get("actor")})
            return revision
        except Exception as exc:
            raise LedgerUnavailable("could not save revision") from exc

    def add_audit(self, event: dict[str, Any]) -> None:
        self.client.collection("copilot_audit").add(event)

    def get_conversation(self, conversation_id: str, actor_id: str):
        snap = self.client.collection("copilot_conversations").document(conversation_id).get()
        data = snap.to_dict() if snap.exists else None
        if not data or data.get("actor_id") != actor_id:
            return None
        return data

    def save_conversation(self, conversation: dict[str, Any]) -> None:
        self.client.collection("copilot_conversations").document(conversation["conversation_id"]).set(conversation)

    def prune_conversations(self, *, now: datetime, retention_days: int) -> None:
        from datetime import timedelta

        cutoff = (now - timedelta(days=retention_days)).isoformat()
        for doc in self.client.collection("copilot_conversations").stream():
            data = doc.to_dict() or {}
            if (data.get("updated_at") or "") < cutoff:
                doc.reference.set({"messages": [], "pruned": True}, merge=True)

    def set_paused(self, paused: bool, *, actor: str) -> None:
        self.client.collection("copilot_config").document("runtime").set({"paused": paused}, merge=True)
        self.paused = paused
        self.add_audit({"type": "pause", "paused": paused, "actor": actor})

    def preference(self, actor_id: str) -> dict[str, Any]:
        snap = self.client.collection("copilot_preferences").document(actor_id).get()
        return snap.to_dict() or {}

    def set_preference(self, actor_id: str, concise: bool | None) -> None:
        ref = self.client.collection("copilot_preferences").document(actor_id)
        if concise is None:
            ref.delete()
        else:
            ref.set({"concise": concise})

    def remember_response(self, request_id: str, actor_id: str, response: dict[str, Any]) -> None:
        self.client.collection("copilot_idempotency").document(request_id).set({"actor_id": actor_id, "body": response})

    def remembered_response(self, request_id: str, actor_id: str):
        snap = self.client.collection("copilot_idempotency").document(request_id).get()
        data = snap.to_dict() if snap.exists else None
        if not data or data.get("actor_id") != actor_id:
            return None
        return data.get("body")

    def add_feedback(self, item: dict[str, Any]) -> dict[str, Any]:
        self.client.collection("copilot_feedback").document(item["feedback_id"]).set(item)
        return item

    def add_suggestion(self, item: dict[str, Any]) -> dict[str, Any]:
        self.client.collection("copilot_suggestions").document(item["suggestion_id"]).set(item)
        return item


class _SimpleReservation:
    def __init__(self, data: dict[str, Any]):
        self.request_id = data.get("request_id")
        self.actor_id = data.get("actor_id")
        self.month_key = data.get("month_key")
        self.amount_micro = int(data.get("amount_micro") or 0)
        self.status = data.get("status")
        self.created_at = data.get("created_at")
        self.dispatched = bool(data.get("dispatched"))
        self.actual_micro = data.get("actual_micro")


def open_store():
    import os

    if os.environ.get("COPILOT_STORE") == "memory":
        return MemoryStore()
    try:
        client = firestore_client()
    except Exception:
        return UnavailableStore()
    if client is None:
        return UnavailableStore()
    store = FirestoreStore(client)
    try:
        store._refresh_pause()
    except Exception:
        return UnavailableStore()
    return store
