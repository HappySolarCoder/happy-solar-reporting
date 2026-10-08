# -*- coding: utf-8 -*-
"""Created, ran, and sales resolve missed user names with batched `in` reads."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
sys.path.insert(0, str(METRICS))

import ghl_user_names
import opportunities_created
import opportunities_ran
import sales

SALES = (METRICS / "sales.py").read_text()
CREATED = (METRICS / "opportunities_created.py").read_text()
RAN = (METRICS / "opportunities_ran.py").read_text()


class _Snap:
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, docs):
        self._docs = list(docs)

    def where(self, field, op, value):
        picked = []
        for doc in self._docs:
            current = (doc.to_dict() or {}).get(field)
            if op == "==" and current == value:
                picked.append(doc)
            elif op == "in" and current in list(value):
                picked.append(doc)
        return _Query(picked)

    def limit(self, count):
        return _Query(self._docs[:count])

    def stream(self):
        return iter(self._docs)


class _Ref:
    def __init__(self, doc_id, snap):
        self.id = doc_id
        self._snap = snap


class _Collection:
    def __init__(self, docs):
        self._docs = {doc.id: doc for doc in docs}
        self._queries = None
        self._name = ""

    def document(self, doc_id):
        return _Ref(doc_id, self._docs.get(doc_id))

    def where(self, field, op, value):
        if self._queries is not None:
            self._queries.append((self._name, field, op, list(value) if op == "in" else value))
        return _Query(self._docs.values()).where(field, op, value)


class _Db:
    def __init__(self, docs):
        self.queries = []
        self._users = _Collection(docs)

    def collection(self, name):
        self._users._queries = self.queries
        self._users._name = name
        return self._users

    def get_all(self, refs):
        found = []
        for ref in refs:
            if ref._snap is None:
                found.append(_Snap(ref.id, {}, exists=False))
            else:
                found.append(ref._snap)
        return found


def _users(count):
    return [
        _Snap(
            f"doc-{index}",
            {"userId": f"user{index}", "name": f"Closer {index}", "email": f"c{index}@happyslr.com"},
        )
        for index in range(count)
    ]


class UserNameBatchTests(unittest.TestCase):
    def test_sources_batch_user_lookups(self):
        for src in (SALES, CREATED, RAN):
            self.assertNotIn('.where(field, "==", uid)', src)
            self.assertNotIn('db.collection("ghl_users_v2").stream()', src)
        self.assertIn('where("ghl_user_id", "in", chunk)', SALES)
        self.assertIn("range(0, len(still_missing_roster), 30)", SALES)
        self.assertEqual(ghl_user_names._IN_CHUNK, 30)
        self.assertEqual(ghl_user_names._CACHE_TTL_SECONDS, 60.0)

    def test_created_ran_and_sales_name_lookups_are_bounded_and_cached(self):
        fillers = (
            ("sales", sales.fill_missing_ghl_user_names),
            ("ran", opportunities_ran.fill_missing_user_names),
            ("created", opportunities_created.fill_missing_user_names),
        )
        ids = [f"user{index}" for index in range(31)]
        for _name, fill in fillers:
            ghl_user_names._cache.clear()
            db = _Db(_users(31))
            names = {}
            fill(db, names, ids)
            queries = [query for query in db.queries if query[0] == "ghl_users_v2"]
            self.assertTrue(queries)
            self.assertTrue(all(query[2] == "in" for query in queries))
            self.assertTrue(all(len(query[3]) <= 30 for query in queries))
            self.assertGreaterEqual(len(queries), 2)
            self.assertLessEqual(len(queries), 4)
            self.assertEqual(names["user0"], "Closer 0")
            self.assertEqual(names["user30"], "Closer 30")
            names["user0"] = "hacked"
            before = len(db.queries)
            again = {}
            fill(db, again, list(reversed(ids)))
            self.assertEqual(len(db.queries), before)
            self.assertEqual(again["user0"], "Closer 0")
            self.assertEqual(again["user30"], "Closer 30")


if __name__ == "__main__":
    unittest.main()
