# -*- coding: utf-8 -*-

"""Counts-only knocks (fieldKnockEvents mirror) join the knock count. Fake ids only."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for _path in (API, ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from knock_count import (  # noqa: E402
    collect_knock_events,
    count_knocks,
    field_event_index,
    knock_events,
    load_field_event_index,
    orphan_ledger_events,
    to_millis,
)
from test_knock_count import _Db, _Snap, _load  # noqa: E402

U1 = "uid-one"
U2 = "uid-two"
T0 = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
DISPOS = [
    {"id": "not-home", "name": "Not Home"},
    {"id": "go-back", "name": "Go Back"},
    {"id": "shade-dq", "name": "Shade DQ"},
    {"id": "has-solar", "name": "Has Solar"},
]


def row(lead="lead-1", uid=U1, dispo="not-home", at=T0, **extra):
    return {"uid": uid, "leadId": lead, "dispositionId": dispo, "actionAt": at, **extra}


def lead_doc(lead_id="lead-1", history=None):
    return {"id": lead_id, "dispositionHistory": history or []}


def entry(dispo="Not Home", uid=U1, at=T0):
    return {"userId": uid, "disposition": dispo, "timestamp": at}


class FieldEventIndexTests(unittest.TestCase):
    def test_no_events_changes_nothing(self):
        lead = lead_doc(history=[entry(), entry("Go Back", at=T0 + timedelta(minutes=5))])
        base = knock_events(lead, DISPOS)
        self.assertEqual(knock_events(lead, DISPOS, ledger=None), base)
        self.assertEqual(knock_events(lead, DISPOS, ledger={}), base)
        self.assertEqual(knock_events(lead, DISPOS, ledger=field_event_index([], DISPOS)), base)
        self.assertEqual(orphan_ledger_events({}, set(), set()), [])
        self.assertEqual(orphan_ledger_events(None, set(), set()), [])

    def test_rows_use_original_action_time_and_skip_unusable_or_excluded(self):
        index = field_event_index(
            [
                row(),
                row(dispo="shade-dq"),
                row(dispo="Has Solar"),
                row(lead=""),
                row(uid=""),
                row(at=None),
                {"uid": U1, "leadId": "lead-9", "status": "go-back", "actionAt": {"seconds": int(T0.timestamp())}},
                "junk",
            ],
            DISPOS,
        )
        self.assertEqual(sorted(index), ["lead-1", "lead-9"])
        self.assertEqual(index["lead-1"][0].at, to_millis(T0))
        self.assertEqual(index["lead-1"][0].dedupe_key, f"lead-1|{U1}|not-home|{to_millis(T0)}")
        self.assertEqual(index["lead-9"][0].disposition_id, "go-back")

    def test_same_draft_counted_only_then_accepted_counts_once(self):
        # Same actionAt: the history entry written later and the event share a ledger key.
        lead = lead_doc(history=[entry(at=T0)])
        index = field_event_index([row(at=T0)], DISPOS)
        events = knock_events(lead, DISPOS, ledger=index)
        self.assertEqual(len(events), 1)
        # Event also streamed again by another snapshot of the lead: still one.
        seen: set[str] = set()
        again = knock_events(lead, DISPOS, seen=seen, ledger=index) + knock_events(lead, DISPOS, seen=seen, ledger=index)
        self.assertEqual(len(again), 1)

    def test_event_within_120_seconds_of_history_collapses_but_later_one_counts(self):
        lead = lead_doc(history=[entry(at=T0)])
        close = field_event_index([row(at=T0 + timedelta(seconds=100))], DISPOS)
        far = field_event_index([row(at=T0 + timedelta(seconds=121))], DISPOS)
        self.assertEqual(len(knock_events(lead, DISPOS, ledger=close)), 1)
        self.assertEqual(len(knock_events(lead, DISPOS, ledger=far)), 2)
        # Another rep or another disposition is never collapsed into it.
        other = field_event_index([row(uid=U2, at=T0 + timedelta(seconds=10)), row(dispo="go-back", at=T0 + timedelta(seconds=10))], DISPOS)
        self.assertEqual(len(knock_events(lead, DISPOS, ledger=other)), 3)

    def test_history_with_an_event_id_still_collapses_with_an_event_inside_120_seconds(self):
        lead = lead_doc(history=[{**entry(at=T0), "eventId": "evt-1"}])
        index = field_event_index([row(at=T0)], DISPOS)
        self.assertEqual(len(knock_events(lead, DISPOS, ledger=index)), 1)

    def test_hotleads_rows_index_by_reason_and_counting_ignores_the_reason(self):
        rows = [
            row(lead="ghl_a", at=T0, collection="hotLeads", reason="in_territory"),
            row(lead="ghl_b", at=T0, collection="hotLeads", reason="staff"),
            row(lead="ghl_c", at=T0, collection="hotLeads", reason="out_of_territory"),
            row(lead="ghl_d", at=T0, dispo="shade-dq", collection="hotLeads", reason="in_territory"),
            row(lead="ghl_e", at=T0, dispo="shade-dq", collection="hotLeads", reason="staff"),
        ]
        index = field_event_index(rows, DISPOS)
        self.assertEqual(sorted(index), ["ghl_a", "ghl_b", "ghl_c"])
        # None of these leads are in the lead query: all three come back through the orphan path, once each.
        seen: set[str] = set()
        out = orphan_ledger_events(index, set(), seen)
        self.assertEqual([e.lead_id for e in out], ["ghl_a", "ghl_b", "ghl_c"])
        self.assertEqual(orphan_ledger_events(index, set(), seen), [])
        # 120 s collapse and the exact same key behave the same for both labels.
        close = field_event_index(
            [
                row(lead="ghl_a", at=T0, collection="hotLeads", reason="in_territory"),
                row(lead="ghl_a", at=T0 + timedelta(seconds=90), collection="hotLeads", reason="staff"),
                row(lead="ghl_a", at=T0, collection="hotLeads", reason="staff"),
            ],
            DISPOS,
        )
        self.assertEqual(len(orphan_ledger_events(close, set(), set())), 1)

    def test_orphan_events_count_only_for_unstreamed_leads_and_skip_test_users(self):
        index = field_event_index(
            [row(lead="lead-1"), row(lead="lead-2", uid=U2), row(lead="lead-3", uid="uid-test"), row(lead="lead-2", uid=U2, at=T0 + timedelta(seconds=30))],
            DISPOS,
        )
        seen: set[str] = set()
        out = orphan_ledger_events(index, {"lead-1"}, seen, exclude_user_ids={"uid-test"})
        self.assertEqual([(e.lead_id, e.user_id) for e in out], [("lead-2", U2)])
        # A second pass over the same seen set adds nothing (idempotent).
        self.assertEqual(orphan_ledger_events(index, {"lead-1"}, seen, exclude_user_ids={"uid-test"}), [])

    def test_union_helpers_are_unchanged_for_history_only(self):
        leads = [lead_doc(history=[entry(), entry(uid=U2)])]
        self.assertEqual(count_knocks(leads, DISPOS), 2)
        self.assertEqual(len(collect_knock_events(leads, DISPOS, user_id=U1)), 1)


class LoadTests(unittest.TestCase):
    def test_absent_collection_is_empty_and_read_is_one_bounded_range(self):
        db = _Db({})
        self.assertEqual(load_field_event_index(db, T0, T0 + timedelta(days=1), DISPOS), {})
        ops = db.collections["raydar_field_knock_events_v1"].ops
        self.assertEqual([(op[1][0], op[1][1]) for op in ops], [("actionAt", ">="), ("actionAt", "<")])

    def test_rows_are_indexed(self):
        db = _Db({"raydar_field_knock_events_v1": [_Snap("a", row()), _Snap("b", row(lead="lead-2", uid=U2))]})
        self.assertEqual(sorted(load_field_event_index(db, T0, None, DISPOS)), ["lead-1", "lead-2"])

    def test_a_failed_read_never_breaks_the_dashboard(self):
        class Broken:
            def collection(self, _name):
                raise RuntimeError("permission denied")

        self.assertEqual(load_field_event_index(Broken(), T0, None, DISPOS), {})


class DoorsKnockedPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(METRICS) not in sys.path:
            sys.path.insert(0, str(METRICS))
        cls.doors = _load("raydar_doors_knocked_field_events", METRICS / "raydar_doors_knocked.py")

    def db(self, events=None):
        when = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
        collections = {
            "raydar_leads_v1": [
                _Snap(
                    "lead-1",
                    {
                        "status": "not-home",
                        "dispositionedAt": when,
                        "claimedBy": U1,
                        "dispositionHistory": [{"userId": U1, "disposition": "Not Home", "timestamp": when}],
                    },
                )
            ],
            "raydar_users_v1": [_Snap(U1, {"name": "Rep One"}), _Snap(U2, {"name": "Rep Two"})],
            "raydar_dispositions_v1": [
                _Snap("not-home", {"name": "Not Home", "countsAsDoorKnock": True}),
                _Snap("go-back", {"name": "Go Back", "countsAsDoorKnock": True}),
                _Snap("shade-dq", {"name": "Shade DQ", "countsAsDoorKnock": False}),
            ],
        }
        if events is not None:
            collections["raydar_field_knock_events_v1"] = [_Snap(f"e{i}", e) for i, e in enumerate(events)]
        return _Db(collections)

    def payload(self, events=None):
        return self.doors.build_payload(self.db(events), 2026, 11, start="2026-11-03", end="2026-11-03")

    def test_absent_or_empty_events_leave_the_payload_identical(self):
        absent = self.payload(None)
        empty = self.payload([])
        self.assertEqual(absent["breakdowns"], empty["breakdowns"])
        self.assertEqual(absent["result"], empty["result"])
        self.assertEqual(absent["knocks_by_time"], empty["knocks_by_time"])
        self.assertEqual(absent["breakdowns"]["knocks_by_actor"], {U1: 1})

    def test_events_add_knocks_for_the_knocker_and_dedupe_against_history(self):
        when = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)
        payload = self.payload(
            [
                row(lead="lead-1", uid=U1, at=when),  # same draft later accepted into history: once
                row(lead="lead-9", uid=U2, at=when + timedelta(hours=1)),  # refused on a pin not in the lead read
                row(lead="lead-9", uid=U2, dispo="shade-dq", at=when + timedelta(hours=2)),  # excluded
                row(lead="lead-8", uid=U2, at=when + timedelta(days=3)),  # outside the window
            ]
        )
        self.assertEqual(payload["breakdowns"]["knocks_by_actor"], {U1: 1, U2: 1})
        self.assertEqual(payload["result"], 2)
        self.assertEqual(payload["breakdowns"]["time_on_doors_by_actor"][U2]["knocks"], 1)

    def test_3pl_hotleads_events_count_through_the_reader(self):
        # 3PL (collection hotLeads) knocks: lead ids like ghl_* are never in the leads query, so they
        # count through the orphan ledger. reason in_territory = a rep's own territory; staff = admin/manager.
        when = datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc)

        def hot(lead, uid, at, reason="in_territory", dispo="not-home"):
            return row(lead=lead, uid=uid, at=at, dispo=dispo, collection="hotLeads", reason=reason, source="live")

        for reason in ("in_territory", "staff"):
            with self.subTest(reason=reason):
                payload = self.payload(
                    [
                        hot("ghl_opp1", U2, when + timedelta(hours=1), reason),
                        # Same rep, lead and dispo 60 s later (a double tap): collapses into the first.
                        hot("ghl_opp1", U2, when + timedelta(hours=1, seconds=60), reason),
                        # Exact replay of the first (same ledger key, e.g. mirror re-sync): once.
                        hot("ghl_opp1", U2, when + timedelta(hours=1), reason),
                        # Excluded dispositions never count, even though the lead id is not in the leads query.
                        hot("ghl_opp2", U2, when + timedelta(hours=2), reason, dispo="shade-dq"),
                        hot("ghl_opp3", U2, when + timedelta(hours=3), reason, dispo="already-has-solar"),
                    ]
                )
                self.assertEqual(payload["breakdowns"]["knocks_by_actor"], {U1: 1, U2: 1})
                self.assertEqual(payload["result"], 2)
                # Past the 120 s window it is a second knock.
                again = self.payload(
                    [
                        hot("ghl_opp1", U2, when + timedelta(hours=1), reason),
                        hot("ghl_opp1", U2, when + timedelta(hours=1, seconds=121), reason),
                    ]
                )
                self.assertEqual(again["breakdowns"]["knocks_by_actor"], {U1: 1, U2: 2})

    def test_every_knock_reader_merges_events(self):
        for relative in (
            "api/metrics/raydar_doors_knocked.py",
            "api/metrics/fma_weekly_review.py",
            "api/rep_daily_recap.py",
        ):
            src = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("load_field_event_index", src, relative)
            self.assertIn("orphan_ledger_events", src, relative)
            self.assertIn("ledger=ledger", src, relative)


if __name__ == "__main__":
    unittest.main()
