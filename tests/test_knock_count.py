# -*- coding: utf-8 -*-

"""Knock totals count visit history. Fake ids and timestamps only."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from knock_count import (  # noqa: E402
    EXCLUDED_KNOCK_KEYS,
    NON_KNOCK_KEYS,
    collect_knock_events,
    count_knocks,
    is_counted_knock,
    knock_events,
    knocks_by_day,
    knocks_by_user,
    normalize_dispo_key,
    raydar_lead_query,
    to_millis,
)

# Prod-shaped catalog. countsAsDoorKnock false is exactly the four ownership /
# non-knock ids. "Spoke with Non Homeowner " keeps the trailing space.
PROD_DISPOSITIONS = [
    {"id": "unclaimed", "name": "Available", "countsAsDoorKnock": False},
    {"id": "claimed", "name": "My Targets", "countsAsDoorKnock": False},
    {"id": "shade-dq", "name": "Shade DQ", "countsAsDoorKnock": False},
    {"id": "has-solar", "name": "Has Solar", "countsAsDoorKnock": False},
    {"id": "not-home", "name": "Not Home", "countsAsDoorKnock": True},
    {"id": "interested", "name": "Interested", "countsAsDoorKnock": True},
    {"id": "not-interested", "name": "Not Interested", "countsAsDoorKnock": True},
    {"id": "appointment", "name": "Appointment", "countsAsDoorKnock": True},
    {"id": "call-scheduling-manager", "name": "Call Scheduling Manager", "countsAsDoorKnock": True},
    {"id": "sale", "name": "Sale", "countsAsDoorKnock": True},
    {"id": "go-back", "name": "Go Back", "countsAsDoorKnock": True},
    {"id": "dq-credit", "name": "DQ Credit", "countsAsDoorKnock": True},
    {"id": "house-for-sale", "name": "House For Sale", "countsAsDoorKnock": True},
    {"id": "renter", "name": "Renter", "countsAsDoorKnock": True},
    {"id": "golden-home", "name": "Golden Home", "countsAsDoorKnock": True},
    {"id": "top-10", "name": "Top 10", "countsAsDoorKnock": True},
    {"id": "spoke-with-non-homeowner", "name": "Spoke with Non Homeowner ", "countsAsDoorKnock": True},
]
COUNTED_IDS = [
    "not-home",
    "interested",
    "not-interested",
    "appointment",
    "call-scheduling-manager",
    "sale",
    "go-back",
    "dq-credit",
    "house-for-sale",
    "renter",
    "golden-home",
    "top-10",
    "spoke-with-non-homeowner",
]

MON = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
TUE = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
U1 = "u1"
U2 = "u2"


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _lead(lead_id: str, history: list[dict], **extra) -> dict:
    row = {"id": lead_id, "dispositionHistory": history}
    row.update(extra)
    return row


def _entry(disposition: str, user_id: str = U1, when: datetime = MON, **extra) -> dict:
    row = {"disposition": disposition, "userId": user_id, "timestamp": when}
    row.update(extra)
    return row


class KnockRuleTests(unittest.TestCase):
    def test_each_counted_dispo_is_one_and_the_exclusions_are_zero(self):
        for disposition_id in COUNTED_IDS:
            lead = _lead(disposition_id, [_entry(disposition_id)])
            self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 1, disposition_id)
        for blocked in ("shade-dq", "has-solar", "Shade DQ", "Has Solar", "Already Has Solar"):
            lead = _lead(blocked, [_entry(blocked)])
            self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 0, blocked)
        for ownership in ("", "claimed", "unclaimed", "available", "my-targets", "Available", "My Targets"):
            lead = _lead(ownership or "blank", [_entry(ownership)])
            self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 0, repr(ownership))
        # Unknown legacy strings count. Only the excluded and non-knock sets drop.
        mystery = _lead("mystery", [_entry("mystery-outcome")])
        self.assertEqual(count_knocks([mystery], PROD_DISPOSITIONS), 1)

    def test_matches_id_and_name_including_trailing_space(self):
        catalog = PROD_DISPOSITIONS
        self.assertEqual(normalize_dispo_key("not-home", catalog), "not-home")
        self.assertEqual(normalize_dispo_key("Not Home", catalog), "not-home")
        self.assertEqual(normalize_dispo_key("Spoke with Non Homeowner ", catalog), "spoke-with-non-homeowner")
        for raw in ("Not Home", "not-home", "Spoke with Non Homeowner "):
            self.assertEqual(count_knocks([_lead(raw, [_entry(raw)])], catalog), 1, raw)
        self.assertTrue(is_counted_knock("not-home"))
        self.assertFalse(is_counted_knock("shade-dq"))
        self.assertFalse(is_counted_knock("already-has-solar"))

    def test_later_non_knock_does_not_subtract(self):
        shade = _lead(
            "L1",
            [_entry("Shade DQ", when=TUE), _entry("Not Home", when=MON)],
        )
        solar = _lead(
            "L2",
            [_entry("Has Solar", when=TUE), _entry("Not Interested", when=MON)],
        )
        self.assertEqual(count_knocks([shade, solar], PROD_DISPOSITIONS), 2)
        self.assertEqual(count_knocks([shade], PROD_DISPOSITIONS, user_id=U1), 1)

    def test_counted_then_excluded_then_counted_is_two(self):
        lead = _lead(
            "L1",
            [
                _entry("Go Back", when=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)),
                _entry("Has Solar", when=TUE),
                _entry("Not Home", when=MON),
            ],
        )
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 2)

    def test_excluded_first_then_counted_is_one(self):
        lead = _lead("L1", [_entry("Not Home", when=TUE), _entry("Shade DQ", when=MON)])
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 1)

    def test_claim_and_unclaim_do_not_change_the_knock(self):
        knocked = _lead(
            "L1",
            [_entry("Not Home")],
            status="not-home",
            claimedBy=U1,
            dispositionedAt=MON,
        )
        claimed = dict(knocked)
        claimed["status"] = "claimed"
        unclaimed = dict(knocked)
        unclaimed["status"] = "unclaimed"
        self.assertEqual(count_knocks([knocked], PROD_DISPOSITIONS), 1)
        self.assertEqual(count_knocks([claimed], PROD_DISPOSITIONS), 1)
        self.assertEqual(count_knocks([unclaimed], PROD_DISPOSITIONS), 1)

    def test_repeat_visits_stay_on_their_own_days(self):
        lead = _lead("L1", [_entry("Not Home", when=TUE), _entry("Not Home", when=MON)])
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS, start=MON, end=TUE), 1)
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS, start=TUE, end=datetime(2026, 10, 7, tzinfo=timezone.utc)), 1)
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 2)
        days = knocks_by_day([lead], PROD_DISPOSITIONS)
        self.assertEqual(days["2026-10-05"], 1)
        self.assertEqual(days["2026-10-06"], 1)

    def test_two_reps_each_keep_their_knock(self):
        lead = _lead(
            "L1",
            [_entry("Interested", user_id=U2, when=TUE), _entry("Not Home", user_id=U1, when=MON)],
        )
        self.assertEqual(knocks_by_user([lead], PROD_DISPOSITIONS), {U1: 1, U2: 1})

    def test_same_event_id_counts_once_and_a_late_older_event_counts(self):
        first = _entry("Not Home", when=MON, eventId="evt-1")
        replay = _entry("Not Home", when=MON, eventId="evt-1")
        older = _entry("Go Back", when=datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc), eventId="evt-0")
        self.assertEqual(count_knocks([_lead("L1", [first, replay])], PROD_DISPOSITIONS), 1)
        self.assertEqual(count_knocks([_lead("L1", [first, older])], PROD_DISPOSITIONS), 2)
        days = knocks_by_day([_lead("L1", [first, older])], PROD_DISPOSITIONS)
        self.assertEqual(days, {"2026-10-04": 1, "2026-10-05": 1})

    def test_duplicate_snapshots_union_and_a_shorter_one_cannot_lower_the_count(self):
        full = _lead(
            "L1",
            [_entry("Not Home", when=MON), _entry("Go Back", when=TUE)],
        )
        trimmed = _lead("L1", [_entry("Go Back", when=TUE)])
        ack = _lead("L1", [_entry("Not Home", when=MON, eventId="ack-1")])
        # ack has a different dedupe key (eventId) than the history row, so it
        # is a second recording of the same visit only when the keys match.
        # The trimmed snapshot must not drop the Monday knock from the full one.
        self.assertEqual(count_knocks([full, trimmed], PROD_DISPOSITIONS), 2)
        self.assertEqual(count_knocks([trimmed, full], PROD_DISPOSITIONS), 2)
        same_ack = _lead("L1", [_entry("Not Home", when=MON)])
        self.assertEqual(count_knocks([full, trimmed, same_ack], PROD_DISPOSITIONS), 2)
        self.assertEqual(count_knocks([trimmed], PROD_DISPOSITIONS), 1)
        # Two devices, same eventId, even if the lead id differs: one knock.
        device_a = _lead("L1", [_entry("Not Home", eventId="same-evt")])
        device_b = _lead("L1-copy", [_entry("Not Home", eventId="same-evt")])
        self.assertEqual(count_knocks([device_a, device_b], PROD_DISPOSITIONS), 1)
        other = _lead("L2", [_entry("Interested", eventId="other-evt")])
        self.assertEqual(count_knocks([device_a, other], PROD_DISPOSITIONS), 2)
        self.assertEqual(len(collect_knock_events([full, ack], PROD_DISPOSITIONS)), 3)

    def test_notes_only_and_empty_history_fallback(self):
        base = _lead("L1", [_entry("Not Home")], notes="first")
        edited = dict(base)
        edited["notes"] = "added a note"
        self.assertEqual(count_knocks([base], PROD_DISPOSITIONS), count_knocks([edited], PROD_DISPOSITIONS))
        legacy = {
            "id": "old",
            "dispositionHistory": [],
            "status": "not-home",
            "dispositionedAt": MON,
            "claimedBy": U1,
        }
        self.assertEqual(count_knocks([legacy], PROD_DISPOSITIONS), 1)
        no_history = dict(legacy)
        del no_history["dispositionHistory"]
        no_history["assignedTo"] = U2
        no_history["claimedBy"] = ""
        self.assertEqual(knocks_by_user([no_history], PROD_DISPOSITIONS), {U2: 1})
        solar = dict(legacy)
        solar["status"] = "has-solar"
        self.assertEqual(count_knocks([solar], PROD_DISPOSITIONS), 0)
        # A non-empty history of unusable entries does not fall back to status.
        broken = {
            "id": "broken",
            "dispositionHistory": [{"userId": U1, "disposition": "Not Home", "timestamp": "not-a-time"}],
            "status": "not-home",
            "dispositionedAt": MON,
            "claimedBy": U1,
        }
        self.assertEqual(count_knocks([broken], PROD_DISPOSITIONS), 0)

    def test_timestamp_types_parse_and_invalid_is_skipped(self):
        class Stamp:
            def __init__(self, seconds: int, nanoseconds: int = 0):
                self.seconds = seconds
                self.nanoseconds = nanoseconds

        expected = _ms(MON)
        self.assertEqual(to_millis(MON), expected)
        self.assertEqual(to_millis(MON.isoformat().replace("+00:00", "Z")), expected)
        self.assertEqual(to_millis("2026-10-05 15:00:00+00:00"), expected)
        seconds = int(MON.timestamp())
        self.assertEqual(to_millis({"seconds": seconds, "nanoseconds": 0}), seconds * 1000)
        self.assertEqual(to_millis({"_seconds": seconds, "_nanoseconds": 0}), seconds * 1000)
        self.assertEqual(to_millis(Stamp(seconds, 0)), seconds * 1000)
        self.assertIsNone(to_millis("not-a-time"))
        self.assertIsNone(to_millis(None))
        self.assertIsNone(to_millis(""))
        lead = _lead("L1", [_entry("Not Home", timestamp="2026-10-05 15:00:00.240000+00:00")])
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 1)

    def test_prod_config_false_set_matches_evans_rule(self):
        false_ids = {row["id"] for row in PROD_DISPOSITIONS if row["countsAsDoorKnock"] is False}
        self.assertEqual(false_ids, {"claimed", "unclaimed", "shade-dq", "has-solar"})
        self.assertEqual(EXCLUDED_KNOCK_KEYS, frozenset({"shade-dq", "has-solar", "already-has-solar"}))
        self.assertTrue({"claimed", "unclaimed", "available", "my-targets"} <= NON_KNOCK_KEYS)
        # countsAsDoorKnock is not the gate. A catalog flag cannot hide a counted id.
        flipped = [{"id": "not-home", "name": "Not Home", "countsAsDoorKnock": False}]
        self.assertEqual(count_knocks([_lead("L1", [_entry("Not Home")])], flipped), 1)

    def test_new_york_day_not_phoenix(self):
        # 2026-11-03 05:30 UTC is 00:30 EST (Nov 3) and 22:30 MST (Nov 2).
        # Reporting stays on America/New_York. The app uses Phoenix.
        moment = datetime(2026, 11, 3, 5, 30, tzinfo=timezone.utc)
        lead = _lead("L1", [_entry("Not Home", when=moment)])
        self.assertEqual(knocks_by_day([lead], PROD_DISPOSITIONS), {"2026-11-03": 1})

    def test_missing_user_or_time_is_skipped(self):
        lead = _lead(
            "L1",
            [
                {"disposition": "Not Home", "timestamp": MON},
                {"disposition": "Not Home", "userId": "", "timestamp": MON},
                _entry("Not Home"),
            ],
        )
        self.assertEqual(count_knocks([lead], PROD_DISPOSITIONS), 1)
        self.assertEqual(knock_events(None, PROD_DISPOSITIONS), [])
        self.assertEqual(knock_events("nope", PROD_DISPOSITIONS), [])  # type: ignore[arg-type]


class _Query:
    def __init__(self, ops: list[tuple]):
        self.ops = ops

    def where(self, field, op, value):
        self.ops.append(("where", field, op, value))
        return self

    def order_by(self, field):
        self.ops.append(("order_by", field))
        return self


class _Collection:
    def __init__(self):
        self.ops: list[tuple] = []

    def where(self, field, op, value):
        query = _Query(self.ops)
        return query.where(field, op, value)


class LeadQueryShapeTests(unittest.TestCase):
    def test_lower_bound_only_on_dispositioned_at(self):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        query = raydar_lead_query(_Collection(), start, order=True)
        self.assertEqual(
            query.ops,
            [
                ("where", "dispositionedAt", ">=", start),
                ("order_by", "dispositionedAt"),
            ],
        )
        plain = raydar_lead_query(_Collection(), start)
        self.assertEqual(plain.ops, [("where", "dispositionedAt", ">=", start)])

    def test_call_sites_use_the_shared_query(self):
        for relative in (
            "api/metrics/raydar_doors_knocked.py",
            "api/metrics/fma_weekly_review.py",
            "api/rep_daily_recap.py",
        ):
            src = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("raydar_lead_query", src, relative)
            self.assertIn("knock_events", src, relative)
            self.assertNotIn('.where("dispositionedAt", "<"', src, relative)
            self.assertNotIn(".where('dispositionedAt', '<'", src, relative)


def _load(name: str, path: Path):
    if "google.cloud" not in sys.modules:
        cloud = types.ModuleType("google.cloud")
        cloud.firestore = MagicMock()
        google_mod = sys.modules.get("google") or types.ModuleType("google")
        google_mod.cloud = cloud
        oauth2 = types.ModuleType("google.oauth2")
        oauth2.service_account = MagicMock()
        sys.modules["google"] = google_mod
        sys.modules["google.cloud"] = cloud
        sys.modules["google.cloud.firestore"] = cloud.firestore
        sys.modules["google.oauth2"] = oauth2
        sys.modules["google.oauth2.service_account"] = oauth2.service_account
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Snap:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Col:
    def __init__(self, docs: list[_Snap]):
        self.docs = docs
        self.ops: list[tuple] = []

    def where(self, *args, **_kwargs):
        self.ops.append(("where", args))
        return self

    def order_by(self, *args, **_kwargs):
        self.ops.append(("order_by", args))
        return self

    def limit(self, count: int):
        return _Col(self.docs[:count])

    def stream(self):
        return iter(self.docs)


class _Db:
    def __init__(self, collections: dict[str, list[_Snap]]):
        self.collections = {name: _Col(docs) for name, docs in collections.items()}

    def collection(self, name: str):
        return self.collections.setdefault(name, _Col([]))


class DoorsKnockedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(METRICS) not in sys.path:
            sys.path.insert(0, str(METRICS))
        cls.doors = _load("raydar_doors_knocked_history", METRICS / "raydar_doors_knocked.py")

    def test_shade_dq_after_a_knock_still_counts_and_query_has_no_upper_bound(self):
        when = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        later = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
        dispositions = [
            _Snap("not-home", {"name": "Not Home", "countsAsDoorKnock": True}),
            _Snap("shade-dq", {"name": "Shade DQ", "countsAsDoorKnock": False}),
            _Snap("has-solar", {"name": "Has Solar", "countsAsDoorKnock": False}),
        ]
        leads = [
            _Snap(
                "kept",
                {
                    "status": "shade-dq",
                    "dispositionedAt": later,
                    "claimedBy": U1,
                    "dispositionHistory": [
                        {"userId": U1, "disposition": "Shade DQ", "timestamp": later},
                        {"userId": U1, "disposition": "Not Home", "timestamp": when},
                    ],
                },
            ),
            _Snap(
                "solar-only",
                {
                    "status": "has-solar",
                    "dispositionedAt": when,
                    "claimedBy": U2,
                    "dispositionHistory": [
                        {"userId": U2, "disposition": "Already Has Solar", "timestamp": when},
                    ],
                },
            ),
            _Snap(
                "two-visits",
                {
                    "status": "not-home",
                    "dispositionedAt": TUE,
                    "claimedBy": U2,
                    "dispositionHistory": [
                        {"userId": U2, "disposition": "Not Home", "timestamp": TUE},
                        {"userId": U1, "disposition": "Not Home", "timestamp": MON},
                    ],
                },
            ),
        ]
        db = _Db(
            {
                "raydar_leads_v1": leads,
                "raydar_users_v1": [
                    _Snap(U1, {"name": "Rep One"}),
                    _Snap(U2, {"name": "Rep Two"}),
                ],
                "raydar_dispositions_v1": dispositions,
            }
        )
        payload = self.doors.build_payload(db, 2026, 10, start="2026-10-01", end="2026-10-31")
        self.assertEqual(payload["breakdowns"]["knocks_by_actor"], {U1: 2, U2: 1})
        self.assertEqual(payload["result"], 3)
        self.assertEqual(payload["breakdowns"]["time_on_doors_by_actor"][U1]["knocks"], 2)
        lead_ops = db.collections["raydar_leads_v1"].ops
        wheres = [op[1] for op in lead_ops if op[0] == "where"]
        self.assertEqual([item[1] for item in wheres], [">="])
        self.assertEqual(wheres[0][0], "dispositionedAt")
        self.assertTrue(any(op[0] == "order_by" and op[1] == ("dispositionedAt",) for op in lead_ops))


if __name__ == "__main__":
    unittest.main()
