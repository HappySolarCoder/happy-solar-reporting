"""Cycle-aware view of GHL opportunities for historical reporting.

A consultant Self Gen rebook revives an old opportunity in place: the GHL
workflow moves it back to New Appointment, may change the owner and clears the
outcome. The sync (ghl-firestore-sync-v2) first freezes the ended cycle into
``ghl_opportunity_cycles_v1/{oppId}~cycle{n}``: an exact copy of the opp as it
stood, append-only.

``cycle_aware(client)`` wraps a Firestore client so every reader of
``ghl_opportunities_v2`` and ``ghl_opportunity_stage_history_v1`` sees each
revived opp as separate rows, one per cycle:

- each ended cycle is its frozen copy (id ``{oppId}~cycle{n}``; ``cycleOf`` holds
  the real id). It carries the original ``createdAt``, stage, owner, outcome,
  appointment and dispo dates and setter, so a window the old cycle was active
  in reads exactly what it read before the revive;
- the live opp keeps its real id and current state but drops ``createdAt``
  (kept as ``cycleOriginalCreatedAt``): creation belongs to cycle 1, so a revive
  never adds a company "opp created" and never moves the May one;
- stage-history rows dated before a cycle ended are re-keyed to that cycle.

Opps that were never revived pass through untouched, and so does every other
collection. With no frozen cycles at all, the wrapper adds one small read and
changes nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

OPP_COLLECTION = "ghl_opportunities_v2"
HISTORY_COLLECTION = "ghl_opportunity_stage_history_v1"
CYCLE_COLLECTION = "ghl_opportunity_cycles_v1"
CREATED_FIELD = "createdAt"


def cycle_doc_id(opp_id: str, n: int) -> str:
    return f"{opp_id}~cycle{int(n)}"


def split_cycle_id(doc_id: str) -> tuple[str, int | None]:
    if "~cycle" in str(doc_id):
        base, _, n = str(doc_id).rpartition("~cycle")
        try:
            return base, int(n)
        except ValueError:
            pass
    return str(doc_id), None


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


class ViewSnap:
    """Minimal DocumentSnapshot stand-in."""

    def __init__(self, doc_id: str, data: dict[str, Any] | None, reference: Any = None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference
        self.create_time = None
        self.update_time = None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None

    def get(self, field: str) -> Any:
        cur: Any = self._data or {}
        for part in str(field).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur


def live_view(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    out = dict(data)
    out["cycleOriginalCreatedAt"] = out.get(CREATED_FIELD)
    out[CREATED_FIELD] = None
    return out


# ---- filter emulation (only used on the few rows the view rewrites) ----------

def _field(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _cmp(a: Any, op: str, b: Any) -> bool:
    if isinstance(a, datetime) or isinstance(b, datetime):
        a2, b2 = _as_utc(a) if isinstance(a, datetime) else a, _as_utc(b) if isinstance(b, datetime) else b
        a, b = a2, b2
    try:
        if op == "==":
            return a == b
        if op == "!=":
            return a is not None and a != b
        if op == "in":
            return a in (b or [])
        if op == "not-in":
            return a is not None and a not in (b or [])
        if op == "array_contains":
            return isinstance(a, list) and b in a
        if op == "array_contains_any":
            return isinstance(a, list) and any(x in a for x in (b or []))
        if a is None:
            return False
        if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
            if not (isinstance(a, datetime) and isinstance(b, datetime)):
                return False
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        if op == ">=":
            return a >= b
    except TypeError:
        return False
    return False


def _parse_where(args: tuple, kwargs: dict) -> tuple[str, str, Any] | None:
    if len(args) >= 3:
        return str(args[0]), str(args[1]), args[2]
    f = kwargs.get("filter") if kwargs else None
    if f is None and args:
        f = args[0]
    if f is not None and hasattr(f, "field_path") and hasattr(f, "op_string"):
        return str(f.field_path), str(f.op_string), getattr(f, "value", None)
    if "field_path" in kwargs:
        return str(kwargs["field_path"]), str(kwargs.get("op_string")), kwargs.get("value")
    return None


def _matches(data: dict[str, Any], filters: Iterable[tuple[str, str, Any]]) -> bool:
    return all(_cmp(_field(data, f), op, v) for f, op, v in filters)


# ---- cycle index ----------------------------------------------------------------

class CycleIndex:
    def __init__(self, docs: list[dict[str, Any]]):
        self.by_opp: dict[str, list[dict[str, Any]]] = {}
        for d in docs:
            opp = str(d.get("cycleOf") or split_cycle_id(d.get("id") or "")[0] or "")
            if opp:
                self.by_opp.setdefault(opp, []).append(d)
        for rows in self.by_opp.values():
            rows.sort(key=lambda r: int(r.get("cycleNumber") or 0))

    def __bool__(self) -> bool:
        return bool(self.by_opp)

    def snapshots(self) -> Iterable[dict[str, Any]]:
        for rows in self.by_opp.values():
            yield from rows

    def snapshot(self, doc_id: str) -> dict[str, Any] | None:
        base, n = split_cycle_id(doc_id)
        for row in self.by_opp.get(base, []):
            if int(row.get("cycleNumber") or 0) == n:
                return row
        return None

    def history_owner(self, opp_id: str, effective_at: Any) -> str:
        """Which cycle a stage-history row belongs to."""
        rows = self.by_opp.get(opp_id)
        ts = _as_utc(effective_at)
        if not rows or ts is None:
            return opp_id
        for row in rows:
            ended = _as_utc(row.get("cycleEndedAt"))
            if ended and ts < ended:
                return cycle_doc_id(opp_id, int(row.get("cycleNumber") or 0))
        return opp_id


class CycleAwareClient:
    def __init__(self, client: Any):
        self._client = client
        self._index: CycleIndex | None = None
        self.cycle_view_error: str | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def cycle_index(self) -> CycleIndex:
        if self._index is None:
            try:
                docs = [{**(s.to_dict() or {}), "id": (s.to_dict() or {}).get("id") or s.id}
                        for s in self._client.collection(CYCLE_COLLECTION).stream()]
            except Exception as exc:  # pragma: no cover - permissions / offline
                self.cycle_view_error = f"{type(exc).__name__}: {exc}"
                docs = []
            self._index = CycleIndex(docs)
        return self._index

    def collection(self, name: str, *rest: Any) -> Any:
        real = self._client.collection(name, *rest)
        if rest:
            return real
        if name == OPP_COLLECTION:
            return OppQuery(self, real, real)
        if name == HISTORY_COLLECTION:
            return HistoryQuery(self, real, real)
        return real

    def get_all(self, refs: Iterable[Any], *args: Any, **kwargs: Any) -> Iterable[Any]:
        refs = list(refs)
        idx = None
        real_refs = []
        opp_ids: set[str] = set()
        for r in refs:
            if isinstance(r, OppDocRef):
                idx = idx or self.cycle_index()
                if split_cycle_id(r.id)[1] is not None:
                    continue
                opp_ids.add(r.id)
                real_refs.append(r._ref)
            else:
                real_refs.append(r)
        for snap in self._client.get_all(real_refs, *args, **kwargs) if real_refs else []:
            sid = getattr(snap, "id", None)
            if idx and sid in opp_ids and sid in idx.by_opp and getattr(snap, "exists", True):
                yield ViewSnap(snap.id, live_view(snap.to_dict()), getattr(snap, "reference", None))
            else:
                yield snap
        for r in refs:
            if isinstance(r, OppDocRef) and split_cycle_id(r.id)[1] is not None:
                yield r.get()


class OppDocRef:
    def __init__(self, owner: CycleAwareClient, ref: Any, doc_id: str):
        self._owner, self._ref, self.id = owner, ref, doc_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ref, name)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        idx = self._owner.cycle_index()
        if split_cycle_id(self.id)[1] is not None:
            return ViewSnap(self.id, idx.snapshot(self.id))
        snap = self._ref.get(*args, **kwargs)
        if idx and self.id in idx.by_opp and getattr(snap, "exists", False):
            return ViewSnap(self.id, live_view(snap.to_dict()), self._ref)
        return snap


class _Query:
    def __init__(self, owner: CycleAwareClient, real: Any, collection: Any, filters=None, orders=None, limit=None, rest=False):
        self._owner, self._real, self._collection = owner, real, collection
        self._filters: list[tuple[str, str, Any]] = list(filters or [])
        self._orders: list[tuple[str, Any]] = list(orders or [])
        self._limit = limit
        self._unsupported = rest

    def _next(self, real: Any, **changes: Any) -> "_Query":
        q = type(self)(self._owner, real, self._collection, self._filters, self._orders, self._limit, self._unsupported)
        for k, v in changes.items():
            setattr(q, k, v)
        return q

    def where(self, *args: Any, **kwargs: Any) -> "_Query":
        parsed = _parse_where(args, kwargs)
        q = self._next(self._real.where(*args, **kwargs))
        if parsed:
            q._filters.append(parsed)
        else:
            q._unsupported = True
        return q

    def order_by(self, field: Any, *args: Any, **kwargs: Any) -> "_Query":
        q = self._next(self._real.order_by(field, *args, **kwargs))
        q._orders.append((str(field), kwargs.get("direction", args[0] if args else "ASCENDING")))
        return q

    def limit(self, n: int) -> "_Query":
        return self._next(self._real.limit(n), _limit=n)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._real, name)
        if callable(attr) and name in {"select", "offset", "start_at", "start_after", "end_at", "end_before", "limit_to_last"}:
            def wrapped(*a: Any, **k: Any) -> "_Query":
                return self._next(attr(*a, **k), _unsupported=self._unsupported or name != "select")
            return wrapped
        return attr

    def get(self, *args: Any, **kwargs: Any) -> list[Any]:
        return list(self.stream(*args, **kwargs))

    def _finish(self, rows: list[Any], changed: bool) -> Iterable[Any]:
        if changed and self._orders:
            for field, direction in reversed(self._orders):
                desc = "DESC" in str(direction).upper()
                rows.sort(key=lambda s: (_sort_key((s.to_dict() or {}).get(field))), reverse=desc)
        if changed and self._limit is not None:
            rows = rows[: self._limit]
        return rows


def _sort_key(v: Any) -> tuple:
    if v is None:
        return (0, "")
    if isinstance(v, datetime):
        return (1, _as_utc(v).isoformat())
    return (2, str(v))


class OppQuery(_Query):
    def document(self, doc_id: str | None = None) -> Any:
        ref = self._collection.document(doc_id) if doc_id is not None else self._collection.document()
        return OppDocRef(self._owner, ref, ref.id if doc_id is None else str(doc_id))

    def stream(self, *args: Any, **kwargs: Any) -> Iterable[Any]:
        idx = self._owner.cycle_index()
        if not idx:
            yield from self._real.stream(*args, **kwargs)
            return
        created_filtered = any(f == CREATED_FIELD for f, _op, _v in self._filters)
        rows: list[Any] = []
        changed = False
        for snap in self._real.stream(*args, **kwargs):
            if snap.id in idx.by_opp:
                changed = True
                if created_filtered:
                    continue  # creation belongs to the frozen first cycle
                rows.append(ViewSnap(snap.id, live_view(snap.to_dict()), getattr(snap, "reference", None)))
            else:
                rows.append(snap)
        if not self._unsupported:
            for data in idx.snapshots():
                if _matches(data, self._filters):
                    changed = True
                    rows.append(ViewSnap(str(data.get("id")), data))
        yield from self._finish(rows, changed)


class HistoryQuery(_Query):
    def stream(self, *args: Any, **kwargs: Any) -> Iterable[Any]:
        idx = self._owner.cycle_index()
        if not idx:
            yield from self._real.stream(*args, **kwargs)
            return
        id_filters = [(f, op, v) for f, op, v in self._filters if f == "opportunityId"]
        real = self._real
        if id_filters and any(
            split_cycle_id(x)[1] is not None
            for _f, _op, v in id_filters
            for x in (v if isinstance(v, (list, tuple, set)) else [v])
        ):
            # Pseudo ids live only in the view: query their real opp, re-key below.
            real = self._collection
            for f, op, v in self._filters:
                if f == "opportunityId":
                    vals = v if isinstance(v, (list, tuple, set)) else [v]
                    base = sorted({split_cycle_id(x)[0] for x in vals})
                    real = real.where(f, "==", base[0]) if op == "==" or len(base) == 1 and op != "in" else real.where(f, "in", base)
                else:
                    real = real.where(f, op, v)
        rows: list[Any] = []
        changed = False
        for snap in real.stream(*args, **kwargs):
            data = snap.to_dict() or {}
            opp_id = str(data.get("opportunityId") or "")
            if opp_id in idx.by_opp:
                owner = idx.history_owner(opp_id, data.get("effectiveAt"))
                if owner != opp_id:
                    changed = True
                    data = {**data, "opportunityId": owner, "cycleOf": opp_id}
                    if id_filters and not _matches(data, id_filters):
                        continue
                    rows.append(ViewSnap(snap.id, data, getattr(snap, "reference", None)))
                    continue
                if id_filters and not _matches(data, id_filters):
                    changed = True
                    continue
            rows.append(snap)
        yield from self._finish(rows, changed)


def cycle_aware(client: Any) -> Any:
    """Wrap a Firestore client (idempotent; None passes through)."""
    if client is None or isinstance(client, CycleAwareClient):
        return client
    return CycleAwareClient(client)
