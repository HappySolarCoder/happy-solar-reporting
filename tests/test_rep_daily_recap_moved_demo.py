# -*- coding: utf-8 -*-

"""Marked Sit stays on the ET day it was marked after the follow-up moves.

ClickUp 86bcarfdp. Live warehouse lock (do not invent a second example):
Kacia Coscia contact nmTZEuyWhg7MPZPUJ8QK / opportunity 7OZrKQbkBBx2oF7V1zbu.
Allen Frazier marked Sit on 2026-09-29 16:00:02.609 ET (dispositionDate).
The follow-up appointmentStartTime and appointmentOccurredAt were then
rewritten to 2026-10-01 14:00 ET. Demo Rate already freezes the sit on
9/29 via min(appointmentOccurredAt, dispositionDate). Rep Daily Recap
was still bucketing only on appointmentStartTime, so 9/29 dropped her.

Elizabeth Johnston (hwLzQcdV78REdUg7IHqB) is the same-day control: her
start is still 2026-09-29 17:00 ET, so she must appear once, not twice.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
RECAP_SRC = (API / "rep_daily_recap.py").read_text(encoding="utf-8")

TZ = ZoneInfo("America/New_York")
DAY_D = datetime(2026, 9, 29, 0, 0, tzinfo=TZ)
DAY_D_END = datetime(2026, 9, 30, 0, 0, tzinfo=TZ)
DAY_D2 = datetime(2026, 10, 1, 0, 0, tzinfo=TZ)
DAY_D2_END = datetime(2026, 10, 2, 0, 0, tzinfo=TZ)
# After the 9/29 mark and before the 10/01 2:00 PM follow-up.
NOW_UTC = datetime(2026, 10, 1, 15, 26, tzinfo=timezone.utc)

ALLEN_ID = "YYkIcdAiCtNFR1pgOarJ"
KACIA_OPP_ID = "7OZrKQbkBBx2oF7V1zbu"
KACIA_CONTACT_ID = "nmTZEuyWhg7MPZPUJ8QK"
ELIZABETH_OPP_ID = "hwLzQcdV78REdUg7IHqB"
ELIZABETH_CONTACT_ID = "contact-elizabeth-johnston"
STAGE_DEMO = "stage-demo-negotiating"
STAGE_SOLD = "stage-sold"
STAGE_RESCHEDULED = "stage-rescheduled"
LEAD_SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"
SETTER_FIELD_ID = "Eq4NLTSkJ56KTxbxypuE"

# Live stamps from /api/metrics/demo_rate on 2026-10-01.
KACIA_DISPOSITION_DATE = datetime(2026, 9, 29, 16, 0, 2, 609000, tzinfo=TZ)
KACIA_FOLLOW_UP = datetime(2026, 10, 1, 14, 0, tzinfo=TZ)
ELIZABETH_START = datetime(2026, 9, 29, 17, 0, tzinfo=TZ)
ELIZABETH_DISPOSITION_DATE = datetime(2026, 9, 29, 18, 55, 57, 221000, tzinfo=TZ)


def _install_google_stubs() -> None:
    google = sys.modules.setdefault("google", MagicMock())
    cloud = sys.modules.setdefault("google.cloud", MagicMock())
    oauth2 = sys.modules.setdefault("google.oauth2", MagicMock())
    sys.modules.setdefault("google.cloud.firestore", MagicMock())
    sys.modules.setdefault("google.oauth2.service_account", MagicMock())
    google.cloud = cloud
    google.oauth2 = oauth2


def load_recap():
    _install_google_stubs()
    if str(API) not in sys.path:
        sys.path.insert(0, str(API))
    spec = importlib.util.spec_from_file_location("rep_daily_recap_moved_demo", API / "rep_daily_recap.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/rep_daily_recap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rep_daily_recap_moved_demo"] = module
    spec.loader.exec_module(module)
    return module


recap = load_recap()


class Snap:
    def __init__(self, doc_id: str, data: dict | None, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class Query:
    def __init__(self, docs: list[Snap], filters: list[tuple[str, str, object]] | None = None, limit: int | None = None):
        self._docs = docs
        self._filters = list(filters or [])
        self._limit = limit

    def where(self, field: str, op: str, value: object) -> "Query":
        return Query(self._docs, self._filters + [(field, op, value)], self._limit)

    def limit(self, count: int) -> "Query":
        return Query(self._docs, self._filters, count)

    def stream(self):
        matched: list[Snap] = []
        for snap in self._docs:
            row = snap.to_dict() or {}
            if all(self._matches(row.get(field), op, value) for field, op, value in self._filters):
                matched.append(snap)
        if self._limit is not None:
            return matched[: self._limit]
        return matched

    @staticmethod
    def _matches(actual: object, op: str, value: object) -> bool:
        if op == ">=":
            return actual is not None and actual >= value
        if op == "<":
            return actual is not None and actual < value
        if op == "==":
            return actual == value
        raise AssertionError(f"unsupported fake Firestore op {op}")


class DocumentRef:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data

    def get(self) -> Snap:
        if self._data is None:
            return Snap(self.id, None, exists=False)
        return Snap(self.id, self._data, exists=True)


class Collection:
    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    def _snaps(self) -> list[Snap]:
        return [Snap(doc_id, data) for doc_id, data in self._docs.items()]

    def stream(self):
        return self._snaps()

    def where(self, field: str, op: str, value: object) -> Query:
        return Query(self._snaps()).where(field, op, value)

    def document(self, doc_id: str) -> DocumentRef:
        return DocumentRef(doc_id, self._docs.get(doc_id))


class DB:
    def __init__(self, collections: dict[str, dict[str, dict]]):
        self._collections = collections

    def collection(self, name: str) -> Collection:
        return Collection(self._collections.get(name, {}))


def _contact(contact_id: str, name: str, lead_source: str, setter: str) -> dict:
    return {
        "id": contact_id,
        "contactName": name,
        "customFields": [
            {"id": LEAD_SOURCE_FIELD_ID, "value": lead_source},
            {"id": SETTER_FIELD_ID, "value": setter},
        ],
    }


def _collections() -> dict[str, dict[str, dict]]:
    rochester_stages = [
        {"id": STAGE_DEMO, "name": "Demo-Negotiating"},
        {"id": STAGE_SOLD, "name": "Sold"},
        {"id": STAGE_RESCHEDULED, "name": "Rescheduled"},
    ]
    opportunities = {
        KACIA_OPP_ID: {
            "id": KACIA_OPP_ID,
            "assignedTo": ALLEN_ID,
            "pipelineId": recap.ROCHESTER_PIPELINE_ID,
            "pipelineStageId": STAGE_DEMO,
            "contactId": KACIA_CONTACT_ID,
            "name": "Kacia Coscia",
            "dispositionValue": "Sit",
            "dispositionDate": KACIA_DISPOSITION_DATE,
            "appointmentOccurredAt": KACIA_FOLLOW_UP,
            "appointmentStartTime": KACIA_FOLLOW_UP,
        },
        ELIZABETH_OPP_ID: {
            "id": ELIZABETH_OPP_ID,
            "assignedTo": ALLEN_ID,
            "pipelineId": recap.ROCHESTER_PIPELINE_ID,
            "pipelineStageId": STAGE_SOLD,
            "contactId": ELIZABETH_CONTACT_ID,
            "name": "Elizabeth Johnston",
            "dispositionValue": "Sit",
            "dispositionDate": ELIZABETH_DISPOSITION_DATE,
            "appointmentOccurredAt": ELIZABETH_START,
            "appointmentStartTime": ELIZABETH_START,
        },
        "movedNoSitControl1": {
            "id": "movedNoSitControl1",
            "assignedTo": ALLEN_ID,
            "pipelineId": recap.ROCHESTER_PIPELINE_ID,
            "pipelineStageId": STAGE_RESCHEDULED,
            "contactId": "contact-moved-no-sit",
            "name": "Moved No Sit",
            "dispositionValue": "No Sit",
            "dispositionDate": datetime(2026, 9, 29, 15, 0, tzinfo=TZ),
            "appointmentOccurredAt": datetime(2026, 10, 1, 11, 0, tzinfo=TZ),
            "appointmentStartTime": datetime(2026, 10, 1, 11, 0, tzinfo=TZ),
        },
        "movedSweeperSit1": {
            "id": "movedSweeperSit1",
            "assignedTo": ALLEN_ID,
            "pipelineId": recap.SWEEPER_PIPELINE_ID,
            "pipelineStageId": STAGE_DEMO,
            "contactId": "contact-moved-sweeper",
            "name": "Moved Sweeper Sit",
            "dispositionValue": "Sit",
            "dispositionDate": datetime(2026, 9, 29, 12, 0, tzinfo=TZ),
            "appointmentOccurredAt": datetime(2026, 10, 1, 9, 0, tzinfo=TZ),
            "appointmentStartTime": datetime(2026, 10, 1, 9, 0, tzinfo=TZ),
        },
    }
    contacts = {
        KACIA_CONTACT_ID: _contact(KACIA_CONTACT_ID, "Kacia Coscia", "Self Gen", "Frazier"),
        ELIZABETH_CONTACT_ID: _contact(ELIZABETH_CONTACT_ID, "Elizabeth Johnston", "Doors", "Hill"),
        "contact-moved-no-sit": _contact("contact-moved-no-sit", "Moved No Sit", "Doors", "Frazier"),
        "contact-moved-sweeper": _contact("contact-moved-sweeper", "Moved Sweeper Sit", "Doors", "Frazier"),
    }
    return {
        "ghl_pipelines_v2": {
            recap.ROCHESTER_PIPELINE_ID: {
                "id": recap.ROCHESTER_PIPELINE_ID,
                "name": "Rochester",
                "stages": rochester_stages,
            },
            recap.SWEEPER_PIPELINE_ID: {
                "id": recap.SWEEPER_PIPELINE_ID,
                "name": "Sweeper",
                "stages": [{"id": STAGE_DEMO, "name": "Demo-Negotiating"}],
            },
        },
        "roster_people_v1": {
            "roster-allen": {
                "display_name": "Allen Frazier",
                "ghl_user_id": ALLEN_ID,
                "person_key": "person-allen",
                "role": "rep",
            }
        },
        "ghl_users_v2": {
            ALLEN_ID: {"id": ALLEN_ID, "name": "Allen Frazier", "email": "allen@happyslr.com"},
        },
        "ghl_opportunities_v2": opportunities,
        "ghl_contacts_v2": contacts,
        "raydar_leads_v1": {},
        "raydar_users_v1": {},
    }


def _build(start: datetime, end: datetime) -> dict:
    db = DB(_collections())
    original_get_db = recap.get_db
    original_powerline = recap.get_powerline_db

    def _powerline():
        raise RuntimeError("Powerline skipped")

    recap.get_db = lambda: db
    recap.get_powerline_db = _powerline
    try:
        return recap.build_payload(start, end)
    finally:
        recap.get_db = original_get_db
        recap.get_powerline_db = original_powerline


def _allen(payload: dict) -> dict:
    matches = [row for row in payload["owners"] if row["owner_label"] == "Allen Frazier"]
    if len(matches) != 1:
        raise AssertionError(matches)
    return matches[0]


def _row(owner: dict, opportunity_id: str) -> dict:
    matches = [row for row in owner["appointments"] if row["opportunity_id"] == opportunity_id]
    if len(matches) != 1:
        raise AssertionError(matches)
    return matches[0]


class MarkedDemoLocalTests(unittest.TestCase):
    def test_kacia_freezes_on_mark_day_not_follow_up_start(self):
        opp = {
            "dispositionValue": "Sit",
            "dispositionDate": KACIA_DISPOSITION_DATE,
            "appointmentOccurredAt": KACIA_FOLLOW_UP,
            "appointmentStartTime": KACIA_FOLLOW_UP,
        }
        local = recap.marked_demo_local(opp, DAY_D, DAY_D_END, now_utc=NOW_UTC)
        self.assertEqual(local, KACIA_DISPOSITION_DATE)
        self.assertEqual(local.astimezone(TZ).date().isoformat(), "2026-09-29")
        self.assertIsNone(recap.marked_demo_local(opp, DAY_D2, DAY_D2_END, now_utc=NOW_UTC))

    def test_preserved_occurred_at_keeps_the_demo_when_disposition_date_is_missing(self):
        opp = {
            "dispositionValue": "Sit",
            "appointmentOccurredAt": ELIZABETH_START,
            "appointmentStartTime": KACIA_FOLLOW_UP,
        }
        local = recap.marked_demo_local(opp, DAY_D, DAY_D_END, now_utc=NOW_UTC)
        self.assertEqual(local, ELIZABETH_START)
        self.assertIsNone(recap.marked_demo_local(opp, DAY_D2, DAY_D2_END, now_utc=NOW_UTC))

    def test_no_sit_is_not_a_marked_demo(self):
        opp = {
            "dispositionValue": "No Sit",
            "dispositionDate": datetime(2026, 9, 29, 15, 0, tzinfo=TZ),
            "appointmentOccurredAt": datetime(2026, 10, 1, 11, 0, tzinfo=TZ),
        }
        self.assertIsNone(recap.marked_demo_local(opp, DAY_D, DAY_D_END, now_utc=NOW_UTC))

    def test_future_stamp_is_ignored(self):
        future = datetime(2026, 10, 2, 15, 0, tzinfo=TZ)
        opp = {
            "dispositionValue": "Sit",
            "dispositionDate": future,
            "appointmentOccurredAt": future,
        }
        self.assertIsNone(recap.marked_demo_local(opp, DAY_D2, DAY_D2_END, now_utc=NOW_UTC))


class MovedFollowUpRecapTests(unittest.TestCase):
    def test_mark_day_still_lists_kacia_after_follow_up_moves_to_d_plus_2(self):
        payload = _build(DAY_D, DAY_D_END)
        allen = _allen(payload)
        ids = [row["opportunity_id"] for row in allen["appointments"]]
        self.assertEqual(ids.count(KACIA_OPP_ID), 1)
        self.assertEqual(ids.count(ELIZABETH_OPP_ID), 1)
        self.assertNotIn("movedNoSitControl1", ids)
        self.assertNotIn("movedSweeperSit1", ids)

        kacia = _row(allen, KACIA_OPP_ID)
        self.assertEqual(kacia["contact_name"], "Kacia Coscia")
        self.assertEqual(kacia["outcome"], "Sit")
        self.assertEqual(kacia["outcome_class"], "good")
        self.assertEqual(kacia["pipeline"], "Rochester")
        self.assertEqual(kacia["stage"], "Demo-Negotiating")
        self.assertEqual(kacia["lead_source"], "Self Gen")
        self.assertEqual(kacia["setter_last_name"], "Frazier")
        self.assertEqual(kacia["attribution"], "frozen_demo")
        self.assertEqual(kacia["time_local"], "4:00 PM")
        self.assertEqual(kacia["appointment_at"], "2026-09-29 04:00 PM")

        elizabeth = _row(allen, ELIZABETH_OPP_ID)
        self.assertEqual(elizabeth["attribution"], "appointment_start")
        self.assertEqual(elizabeth["time_local"], "5:00 PM")
        self.assertEqual(elizabeth["outcome"], "Sit")

        self.assertEqual(allen["appointment_total"], 2)
        self.assertEqual(allen["sit_total"], 2)
        self.assertEqual(allen["self_gen_appointment_total"], 1)
        self.assertEqual(allen["completed_total"], 2)
        self.assertEqual(payload["summary"]["appointments_total"], 2)
        self.assertEqual(payload["summary"]["self_gen_appointments_total"], 1)
        self.assertEqual(payload["summary"]["excluded_non_territory_appointments_total"], 0)
        self.assertEqual(payload["appointment_pipeline_scope"], "territory")

        html = recap.render_html(payload, "2026-09-29")
        self.assertIn("Kacia Coscia", html)
        self.assertIn("Elizabeth Johnston", html)
        self.assertNotIn("Moved Sweeper Sit", html)
        self.assertNotIn("Moved No Sit", html)

    def test_follow_up_day_still_lists_current_start_once(self):
        payload = _build(DAY_D2, DAY_D2_END)
        allen = _allen(payload)
        ids = [row["opportunity_id"] for row in allen["appointments"]]
        self.assertEqual(ids.count(KACIA_OPP_ID), 1)
        self.assertNotIn(ELIZABETH_OPP_ID, ids)
        self.assertIn("movedNoSitControl1", ids)
        self.assertNotIn("movedSweeperSit1", ids)

        kacia = _row(allen, KACIA_OPP_ID)
        self.assertEqual(kacia["attribution"], "appointment_start")
        self.assertEqual(kacia["time_local"], "2:00 PM")
        self.assertEqual(kacia["outcome"], "Sit")
        self.assertEqual(kacia["appointment_at"], "2026-10-01 02:00 PM")

        no_sit = _row(allen, "movedNoSitControl1")
        self.assertEqual(no_sit["outcome"], "No Sit")
        self.assertEqual(no_sit["attribution"], "appointment_start")

        self.assertEqual(allen["appointment_total"], 2)
        self.assertEqual(allen["sit_total"], 1)
        self.assertEqual(allen["no_sit_total"], 1)
        self.assertEqual(payload["summary"]["excluded_non_territory_appointments_total"], 1)
        self.assertEqual(
            payload["excluded_non_territory_appointments"],
            [{"pipeline": "Sweeper", "count": 1}],
        )


class RecapContractTests(unittest.TestCase):
    def test_uses_frozen_sit_timestamp_without_full_stream(self):
        self.assertIn("frozen_sit_timestamp", RECAP_SRC)
        self.assertIn('dispositionDate', RECAP_SRC)
        self.assertIn('appointmentOccurredAt', RECAP_SRC)
        self.assertIn('appointmentStartTime', RECAP_SRC)
        self.assertIn("is_recap_appointment_pipeline", RECAP_SRC)
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', RECAP_SRC)

    def test_extra_window_query_failure_does_not_raise(self):
        class RaisingCollection:
            def where(self, *_args, **_kwargs):
                raise RuntimeError("missing index")

        class RaisingDB:
            def collection(self, _name):
                return RaisingCollection()

        snaps = recap.stream_opportunity_window(
            RaisingDB(),
            "dispositionDate",
            DAY_D.astimezone(timezone.utc),
            DAY_D_END.astimezone(timezone.utc),
        )
        self.assertEqual(snaps, [])


if __name__ == "__main__":
    unittest.main()
