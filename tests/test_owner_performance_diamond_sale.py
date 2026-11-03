# -*- coding: utf-8 -*-
"""Owner Performance credits a Diamond sweeper sale to the opportunity owner.

Evan, 2026-11-03: Dennis Tybor's October sale (opp knhobAHXETc715nEUkai,
Lead Gen Source Sweeper, Sweeper/Rehash Last Name Diamond, owner Jeff Salas)
counts for Jeff in Owner Performance. The 2026-10-20 rule still removes every
other Sweeper/Rehash sale, and every Sweeper/Rehash ran row, from that table.
Default /api/metrics/sales callers are unchanged.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import sales  # noqa: E402
from sweeper_rehash_attribution import (  # noqa: E402
    excluded_from_owner_performance,
    owner_performance_credits_sweeper_sale,
)

SOLD = "P9oBjgbZjJdeE0OkBj9T"
LEAD = "hd5QqHEOVSsPom5bJ32P"
SWEEPER = "HWfjOp8MvE6soxBAL75f"
BUFFALO_SOLD = "7981f111-73f2-4593-9662-6b95d99bf51a"
VIRTUAL_SOLD = "45acf2ef-ac72-4aa3-a327-7ed37c54b4ad"
JEFF = "b4SOGTyK8QCfQFJfsMtb"
QUINCY = "u-quincy"


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Ref:
    def __init__(self, store, doc_id):
        self._store, self.id = store, doc_id

    def get(self):
        return _Snap(self.id, self._store.get(self.id))


class _Query:
    def __init__(self, store, filters=()):
        self._store, self._filters = store, tuple(filters)

    def where(self, field, op, value):
        return _Query(self._store, self._filters + ((field, op, value),))

    def limit(self, _n):
        return self

    def stream(self):
        for doc_id, data in self._store.items():
            ok = True
            for field, op, value in self._filters:
                have = data.get(field)
                ok = ok and (have in value if op == "in" else have == value)
            if ok:
                yield _Snap(doc_id, data)


class _Collection(_Query):
    def document(self, doc_id):
        return _Ref(self._store, doc_id)


class FakeDb:
    def __init__(self, collections):
        self._c = collections

    def collection(self, name):
        return _Collection(self._c.setdefault(name, {}))

    def get_all(self, refs):
        return [ref.get() for ref in refs]


def _contact(cid, sold, lead, sweeper=""):
    fields = [{"id": SOLD, "value": f"{sold}T00:00:00.000Z"}, {"id": LEAD, "value": lead}]
    if sweeper:
        fields.append({"id": SWEEPER, "value": sweeper})
    return {"id": cid, "customFields": fields}


def _opp(oid, cid, owner, stage, pipeline):
    return {"id": oid, "contactId": cid, "assignedTo": owner, "pipelineStageId": stage, "pipelineId": pipeline}


def october_db():
    """Jeff's three October sales after the Cotoia contact move, plus guards."""
    contacts = {
        "c-penner": _contact("c-penner", "2026-10-19", ""),
        "c-tybor": _contact("c-tybor", "2026-10-20", "Sweeper", "Diamond"),
        "c-cotoia": _contact("c-cotoia", "2026-10-29", "Inbound"),
        # Guard: a non-Diamond sweeper sale stays out of Owner Performance.
        "c-other-sweeper": _contact("c-other-sweeper", "2026-10-12", "Rehash", "Smith"),
        # Guard: a Sweeper lead source with a blank last name stays out.
        "c-blank-sweeper": _contact("c-blank-sweeper", "2026-10-13", "Sweeper"),
        "c-quincy": _contact("c-quincy", "2026-10-05", "Doors"),
        # Guard: Sold Date in September (ET date only) is outside October.
        "c-sept": _contact("c-sept", "2026-09-30", "Doors"),
    }
    opps = {
        "o-penner": _opp("o-penner", "c-penner", JEFF, VIRTUAL_SOLD, "p-virtual"),
        "o-tybor": _opp("o-tybor", "c-tybor", JEFF, BUFFALO_SOLD, "p-buffalo"),
        "o-cotoia": _opp("o-cotoia", "c-cotoia", JEFF, VIRTUAL_SOLD, "p-virtual"),
        "o-other-sweeper": _opp("o-other-sweeper", "c-other-sweeper", QUINCY, BUFFALO_SOLD, "p-buffalo"),
        "o-blank-sweeper": _opp("o-blank-sweeper", "c-blank-sweeper", QUINCY, BUFFALO_SOLD, "p-buffalo"),
        "o-quincy": _opp("o-quincy", "c-quincy", QUINCY, BUFFALO_SOLD, "p-buffalo"),
        # Distinct contactId: a second sold opp on the Tybor contact counts once.
        "o-tybor-dup": _opp("o-tybor-dup", "c-tybor", JEFF, BUFFALO_SOLD, "p-buffalo"),
        "o-sept": _opp("o-sept", "c-sept", QUINCY, BUFFALO_SOLD, "p-buffalo"),
    }
    return FakeDb({
        "ghl_opportunities_v2": opps,
        "ghl_contacts_v2": contacts,
        "ghl_pipelines_v2": {"p-virtual": {"id": "p-virtual", "name": "Virtual"}, "p-buffalo": {"id": "p-buffalo", "name": "Buffalo"}},
        "roster_people_v1": {
            JEFF: {"ghl_user_id": JEFF, "display_name": "Jeff Salas"},
            QUINCY: {"ghl_user_id": QUINCY, "display_name": "Quincy Sermons"},
        },
        "ghl_users_v2": {},
    })


def _run(db, **kw):
    return sales.compute_sales(db, sales.SalesMetricContract(), year=2026, month=10, tz="America/New_York", **kw)


class DiamondSaleRuleTests(unittest.TestCase):
    def test_only_diamond_is_credited(self):
        self.assertTrue(owner_performance_credits_sweeper_sale("Diamond"))
        self.assertTrue(owner_performance_credits_sweeper_sale("  diamond "))
        for name in ("", "none", "n/a", "Smith", "Diamonds", None):
            self.assertFalse(owner_performance_credits_sweeper_sale(name))

    def test_october_20_rule_itself_is_unchanged(self):
        self.assertTrue(excluded_from_owner_performance("Sweeper", "Diamond"))
        self.assertTrue(excluded_from_owner_performance("Sweeper", ""))
        self.assertFalse(excluded_from_owner_performance("Doors", ""))


class OwnerPerformanceSalesTests(unittest.TestCase):
    def test_owner_performance_credits_tybor_to_jeff(self):
        out = _run(october_db(), exclude_sweeper_rehash=True)
        owners = out["breakdowns"]["sales_by_owner"]
        self.assertEqual(owners.get("Jeff Salas"), 3)
        # Rehash/Smith and Sweeper/blank stay out; only Quincy's Doors sale is left.
        self.assertEqual(owners.get("Quincy Sermons"), 1)
        self.assertEqual(out["result"], 4)

    def test_default_sales_contract_is_unchanged(self):
        out = _run(october_db())
        owners = out["breakdowns"]["sales_by_owner"]
        # Distinct contactId: the duplicate Tybor opp counts once. September Sold Date is out.
        self.assertEqual(out["result"], 6)
        self.assertEqual(owners.get("Jeff Salas"), 3)
        self.assertEqual(owners.get("Quincy Sermons"), 3)

    def test_ran_gate_is_untouched(self):
        ran_src = (METRICS / "opportunities_ran.py").read_text(encoding="utf-8")
        self.assertNotIn("owner_performance_credits_sweeper_sale", ran_src)
        self.assertIn("if exclude_sweeper_rehash and excluded_from_owner_performance(lead, sweeper_last):", ran_src)


if __name__ == "__main__":
    unittest.main()
