# -*- coding: utf-8 -*-

"""FMA Weekly Review demos use Demo Rate's first Sit, not the current appointment.

A closer moving the appointment onto a follow-up rewrites appointmentOccurredAt.
The sit stays on the day Sit was first entered (min of that field and
dispositionDate). Conti, Fairclough, and Culver are that bug.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for _path in (str(API), str(METRICS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import demo_rate  # noqa: E402
import fma_weekly_review as weekly  # noqa: E402

TZ = ZoneInfo("America/New_York")

SETTER_FIELD = "Eq4NLTSkJ56KTxbxypuE"
LEAD_FIELD = "hd5QqHEOVSsPom5bJ32P"
SWEEPER_FIELD = "HWfjOp8MvE6soxBAL75f"
SOLD_DATE_FIELD = "P9oBjgbZjJdeE0OkBj9T"
SOLD_STAGE = "7981f111-73f2-4593-9662-6b95d99bf51a"

BUFFALO = "pipe-buffalo"
ROCHESTER = "pipe-rochester"
LOCKER = "pipe-locker"
TRAINING = "pipe-training"

FILTERS = {"pipeline": None, "setter": None, "lead_source": None, "sweeper": None}

PAYLOAD_KEYS = {
    "metric",
    "timezone",
    "start",
    "end",
    "window_start_local",
    "window_end_local",
    "day_count",
    "totals",
    "daily_averages",
    "outcome_totals",
    "people",
    "daily_series",
    "ran_appointments",
    "generated_at",
    "notes",
    "debug",
}
PERSON_KEYS = {
    "person_key",
    "display_name",
    "ghl_setter_last_name",
    "raydar_user_id",
    "knocks",
    "appointments",
    "demos",
    "ran",
    "no_sit",
    "sales",
    "daily",
}
RAN_KEYS = {
    "person_key",
    "display_name",
    "setter_last_name",
    "appointment_occurred_at",
    "outcome",
    "contact",
    "owner",
    "pipeline",
    "pipeline_stage",
    "opportunity_id",
    "disposition_notes",
    "is_sale_stage",
}


def _at(year: int, month: int, day: int, hour: int = 15) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=TZ)


def _fields(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"id": field_id, "value": value} for field_id, value in pairs]


class Snap:
    def __init__(self, doc_id: str, data: dict | None, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class Query:
    def __init__(self, docs: list[Snap], filters: list[tuple[str, str, object]] | None = None, limit: int | None = None):
        self._docs = docs
        self._filters = list(filters or [])
        self._limit = limit

    def where(self, field: str, op: str, value: object) -> "Query":
        return Query(self._docs, self._filters + [(field, op, value)], self._limit)

    def limit(self, count: int) -> "Query":
        return Query(self._docs, self._filters, count)

    def order_by(self, *_args, **_kwargs) -> "Query":
        return self

    def stream(self):
        matched = [snap for snap in self._docs if self._matches(snap)]
        if self._limit is not None:
            return matched[: self._limit]
        return matched

    def _matches(self, snap: Snap) -> bool:
        row = snap.to_dict() or {}
        return all(self._compare(row.get(field), op, value) for field, op, value in self._filters)

    @staticmethod
    def _compare(actual: object, op: str, value: object) -> bool:
        if op == "==":
            return actual == value
        if op == "in":
            return actual in list(value)
        if actual is None:
            return False
        if op == ">=":
            return actual >= value
        if op == "<":
            return actual < value
        raise AssertionError(f"unsupported fake Firestore op {op}")


class DocRef:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data

    def get(self) -> Snap:
        if self._data is None:
            return Snap(self.id, None, exists=False)
        return Snap(self.id, self._data)


class Collection:
    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    def _snaps(self) -> list[Snap]:
        return [Snap(doc_id, data) for doc_id, data in self._docs.items()]

    def stream(self):
        return self._snaps()

    def where(self, field: str, op: str, value: object) -> Query:
        return Query(self._snaps()).where(field, op, value)

    def limit(self, count: int) -> Query:
        return Query(self._snaps()).limit(count)

    def document(self, doc_id: str) -> DocRef:
        return DocRef(doc_id, self._docs.get(doc_id))


class DB:
    def __init__(self, collections: dict[str, dict[str, dict]]):
        self._collections = collections

    def collection(self, name: str) -> Collection:
        return Collection(self._collections.get(name, {}))

    def get_all(self, refs: list[DocRef]) -> list[Snap]:
        found = []
        for ref in refs:
            if ref._data is None:
                found.append(Snap(ref.id, None, exists=False))
            else:
                found.append(Snap(ref.id, ref._data))
        return found


def _person(key: str, display: str, last: str) -> dict:
    return {
        "role": "setter",
        "person_key": key,
        "display_name": display,
        "ghl_setter_last_name": last,
        "raydar_user_id": f"raydar-{key}",
    }


def _contact(contact_id: str, name: str, setter: str, *, sweeper: str = "", lead: str = "Doors", sold: str = "") -> dict:
    pairs = [(SETTER_FIELD, setter), (LEAD_FIELD, lead)]
    if sweeper:
        pairs.append((SWEEPER_FIELD, sweeper))
    if sold:
        pairs.append((SOLD_DATE_FIELD, sold))
    return {
        "id": contact_id,
        "contactName": name,
        "customFields": _fields(*pairs),
    }


def _opp(
    opp_id: str,
    contact_id: str,
    pipeline_id: str,
    setter: str,
    disposition: str,
    occurred_at: datetime,
    disposition_date: datetime,
    *,
    created_at: datetime | None = None,
    stage_id: str = "stage-demo",
) -> dict:
    opp = {
        "id": opp_id,
        "pipelineId": pipeline_id,
        "pipelineStageId": stage_id,
        "contactId": contact_id,
        "dispositionValue": disposition,
        "appointmentOccurredAt": occurred_at,
        "dispositionDate": disposition_date,
        "customFields": _fields((SETTER_FIELD, setter)),
    }
    if created_at is not None:
        opp["createdAt"] = created_at
    return opp


def _pipelines() -> dict[str, dict]:
    def pipe(doc_id: str, name: str) -> dict:
        return {"id": doc_id, "name": name, "stages": [{"id": "stage-demo", "name": "Demo-Negotiating"}, {"id": SOLD_STAGE, "name": "Sold"}]}

    return {
        BUFFALO: pipe(BUFFALO, "Buffalo"),
        ROCHESTER: pipe(ROCHESTER, "Rochester"),
        LOCKER: pipe(LOCKER, "Inbound/Lead Locker"),
        TRAINING: pipe(TRAINING, "Training"),
    }


def _db(opps: dict[str, dict], contacts: dict[str, dict], people: dict[str, dict]) -> DB:
    return DB(
        {
            "ghl_opportunities_v2": opps,
            "ghl_contacts_v2": contacts,
            "ghl_pipelines_v2": _pipelines(),
            "ghl_users_v2": {},
            "roster_people_v1": people,
            "raydar_users_v1": {},
            "raydar_dispositions_v1": {},
            "raydar_leads_v1": {},
        }
    )


HILL = _person("setter:hill", "Bo Hill", "Hill")
VERMEESCH = _person("setter:vermeesch", "Sawyer Vermeesch", "Vermeesch")
MANCINI = _person("setter:mancini", "Marissa Mancini", "Mancini")
ROSTER = {
    "setter:hill": HILL,
    "setter:vermeesch": VERMEESCH,
    "setter:mancini": MANCINI,
}


def _conti() -> tuple[dict, dict]:
    """Sit Oct 27. The closer then moved the appointment to Nov 9."""
    contact = _contact("contact-conti", "Conti", "Hill")
    opp = _opp(
        "opp-conti",
        "contact-conti",
        BUFFALO,
        "Hill",
        "Sit",
        _at(2026, 11, 9),
        _at(2026, 10, 27),
        created_at=_at(2026, 10, 20, 11),
    )
    return opp, contact


def _fairclough() -> tuple[dict, dict]:
    """Sit Nov 16. The follow-up appointment is Nov 18, which was still ahead on Nov 17."""
    contact = _contact("contact-fairclough", "Fairclough", "Vermeesch")
    opp = _opp(
        "opp-fairclough",
        "contact-fairclough",
        BUFFALO,
        "Vermeesch",
        "Sit",
        _at(2026, 11, 18),
        _at(2026, 11, 16),
    )
    return opp, contact


def _culver() -> tuple[dict, dict]:
    """Sit Nov 10. The appointment was moved to Dec 1."""
    contact = _contact("contact-culver", "Culver", "Mancini")
    opp = _opp(
        "opp-culver",
        "contact-culver",
        ROCHESTER,
        "Mancini",
        "Sit",
        _at(2026, 12, 1),
        _at(2026, 11, 10),
    )
    return opp, contact


def _store(*pairs: tuple[dict, dict], extra_opps: dict[str, dict] | None = None, extra_contacts: dict[str, dict] | None = None) -> DB:
    opps: dict[str, dict] = {}
    contacts: dict[str, dict] = {}
    for opp, contact in pairs:
        opps[opp["id"]] = opp
        contacts[contact["id"]] = contact
    opps.update(extra_opps or {})
    contacts.update(extra_contacts or {})
    return _db(opps, contacts, ROSTER)


def review(db: DB, start: str, end: str) -> dict:
    return weekly.build_payload(db, start=start, end=end)


def rate(db: DB, start: str, end: str) -> dict:
    return demo_rate.build_payload(db, 2026, 11, FILTERS, start, end)


def _person_row(payload: dict, last: str) -> dict:
    for row in payload["people"]:
        if row["ghl_setter_last_name"] == last:
            return row
    raise AssertionError(last)


def _day(payload: dict, day: str) -> dict:
    for row in payload["daily_series"]:
        if row["date"] == day:
            return row
    raise AssertionError(day)


class MovedDemoTests(unittest.TestCase):
    def test_conti_counts_in_october_only(self):
        opp, contact = _conti()
        db = _store((opp, contact))

        october = review(db, "2026-10-01", "2026-10-31")
        hill = _person_row(october, "Hill")
        self.assertEqual(hill["demos"], 1)
        self.assertEqual(hill["ran"], 1)
        self.assertEqual(hill["no_sit"], 0)
        self.assertEqual(hill["appointments"], 1)
        self.assertEqual(_day(october, "2026-10-27")["demos"], 1)
        self.assertEqual(_day(october, "2026-10-27")["sit"], 1)
        self.assertEqual(october["totals"]["demos"], 1)
        self.assertEqual(len(october["ran_appointments"]), 1)
        ran = october["ran_appointments"][0]
        self.assertEqual(ran["contact"], "Conti")
        self.assertEqual(ran["outcome"], "Sit")
        self.assertTrue(ran["appointment_occurred_at"].startswith("2026-10-27"))
        self.assertEqual(set(october), PAYLOAD_KEYS)
        self.assertEqual(set(hill), PERSON_KEYS)
        self.assertEqual(set(ran), RAN_KEYS)

        november = review(db, "2026-11-01", "2026-11-30")
        self.assertEqual(_person_row(november, "Hill")["demos"], 0)
        self.assertEqual(_person_row(november, "Hill")["ran"], 0)
        self.assertEqual(_day(november, "2026-11-09")["demos"], 0)
        self.assertEqual(november["totals"]["demos"], 0)
        self.assertEqual(november["ran_appointments"], [])

    def test_fairclough_future_follow_up_counts_on_nov_16(self):
        opp, contact = _fairclough()
        db = _store((opp, contact))
        payload = review(db, "2026-11-01", "2026-11-30")

        vermeesch = _person_row(payload, "Vermeesch")
        self.assertEqual(vermeesch["demos"], 1)
        self.assertEqual(vermeesch["ran"], 1)
        self.assertEqual(vermeesch["daily"]["2026-11-16"]["demos"], 1)
        self.assertNotIn("2026-11-18", vermeesch["daily"])
        self.assertEqual(_day(payload, "2026-11-16")["demos"], 1)
        self.assertEqual(_day(payload, "2026-11-16")["ran"], 1)
        self.assertEqual(_day(payload, "2026-11-18")["demos"], 0)
        self.assertEqual(payload["totals"]["demos"], 1)
        self.assertEqual(len(payload["ran_appointments"]), 1)
        ran = payload["ran_appointments"][0]
        self.assertEqual(ran["contact"], "Fairclough")
        self.assertEqual(ran["setter_last_name"], "Vermeesch")
        self.assertTrue(ran["appointment_occurred_at"].startswith("2026-11-16"))

    def test_culver_counts_in_november_not_december(self):
        opp, contact = _culver()
        db = _store((opp, contact))

        november = review(db, "2026-11-01", "2026-11-30")
        mancini = _person_row(november, "Mancini")
        self.assertEqual(mancini["demos"], 1)
        self.assertEqual(mancini["ran"], 1)
        self.assertEqual(mancini["daily"]["2026-11-10"]["demos"], 1)
        self.assertEqual(_day(november, "2026-11-10")["demos"], 1)
        self.assertEqual(november["totals"]["demos"], 1)
        self.assertTrue(november["ran_appointments"][0]["appointment_occurred_at"].startswith("2026-11-10"))

        december = review(db, "2026-12-01", "2026-12-31")
        self.assertEqual(_person_row(december, "Mancini")["demos"], 0)
        self.assertEqual(_person_row(december, "Mancini")["ran"], 0)
        self.assertEqual(_day(december, "2026-12-01")["demos"], 0)
        self.assertEqual(december["totals"]["demos"], 0)
        self.assertEqual(december["ran_appointments"], [])


class EndpointAgreementTests(unittest.TestCase):
    def _shared(self) -> DB:
        conti_opp, conti_contact = _conti()
        fairclough_opp, fairclough_contact = _fairclough()
        culver_opp, culver_contact = _culver()
        steady_contact = _contact("contact-steady", "Steady", "Hill", sold="2026-11-03")
        steady_opp = _opp(
            "opp-steady",
            "contact-steady",
            BUFFALO,
            "Hill",
            "Sit",
            _at(2026, 11, 4),
            _at(2026, 11, 4, 16),
            stage_id=SOLD_STAGE,
        )
        nosit_contact = _contact("contact-nosit", "No Sit", "Hill")
        nosit_opp = _opp(
            "opp-nosit",
            "contact-nosit",
            BUFFALO,
            "Hill",
            "No Sit",
            _at(2026, 11, 5),
            _at(2026, 11, 5, 18),
        )
        sweeper_contact = _contact(
            "contact-sweeper",
            "Sweeper Sit",
            "Hill",
            sweeper="Vermeesch",
            lead="Self Gen",
        )
        sweeper_opp = _opp(
            "opp-sweeper",
            "contact-sweeper",
            BUFFALO,
            "Hill",
            "Sit",
            _at(2026, 11, 12),
            _at(2026, 11, 12, 16),
        )
        future_contact = _contact("contact-future", "Future Sit", "Hill")
        future_opp = _opp(
            "opp-future",
            "contact-future",
            BUFFALO,
            "Hill",
            "Sit",
            _at(2099, 1, 15),
            _at(2099, 1, 15, 16),
        )
        training_contact = _contact("contact-training", "Training Sit", "Hill")
        training_opp = _opp(
            "opp-training",
            "contact-training",
            TRAINING,
            "Hill",
            "Sit",
            _at(2026, 11, 8),
            _at(2026, 11, 8, 16),
            created_at=_at(2026, 11, 1, 9),
        )
        locker_contact = _contact("contact-locker", "Locker Sit", "Hill")
        locker_opp = _opp(
            "opp-locker",
            "contact-locker",
            LOCKER,
            "Hill",
            "Sit",
            _at(2026, 11, 8, 12),
            _at(2026, 11, 8, 12),
            created_at=_at(2026, 11, 2, 9),
        )
        return _store(
            (conti_opp, conti_contact),
            (fairclough_opp, fairclough_contact),
            (culver_opp, culver_contact),
            (steady_opp, steady_contact),
            (nosit_opp, nosit_contact),
            (sweeper_opp, sweeper_contact),
            (future_opp, future_contact),
            (training_opp, training_contact),
            (locker_opp, locker_contact),
        )

    def _assert_same_counts(self, db: DB, start: str, end: str) -> tuple[dict, dict]:
        weekly_payload = review(db, start, end)
        rate_payload = rate(db, start, end)
        sit_by = rate_payload["breakdowns"]["sit_by_setter_last_name"]
        ran_by = rate_payload["breakdowns"]["ran_by_setter_last_name"]
        weekly_sit = {}
        weekly_ran = {}
        for row in weekly_payload["people"]:
            last = row["ghl_setter_last_name"]
            self.assertEqual(row["demos"], sit_by.get(last, 0), last)
            self.assertEqual(row["ran"], ran_by.get(last, 0), last)
            self.assertEqual(row["no_sit"], row["ran"] - row["demos"], last)
            if row["demos"]:
                weekly_sit[last] = row["demos"]
            if row["ran"]:
                weekly_ran[last] = row["ran"]
        self.assertEqual(weekly_sit, sit_by)
        self.assertEqual(weekly_ran, ran_by)
        self.assertEqual(weekly_payload["totals"]["demos"], rate_payload["sit_count"])
        self.assertEqual(weekly_payload["totals"]["ran"], rate_payload["ran_count"])
        self.assertEqual(weekly_payload["outcome_totals"]["sit"], rate_payload["sit_count"])
        self.assertEqual(set(weekly_payload), PAYLOAD_KEYS)
        return weekly_payload, rate_payload

    def test_weekly_review_and_demo_rate_agree(self):
        db = self._shared()

        october, _october_rate = self._assert_same_counts(db, "2026-10-01", "2026-10-31")
        self.assertEqual(_person_row(october, "Hill")["demos"], 1)
        self.assertEqual(_day(october, "2026-10-27")["demos"], 1)
        self.assertTrue(october["ran_appointments"][0]["appointment_occurred_at"].startswith("2026-10-27"))

        november, _november_rate = self._assert_same_counts(db, "2026-11-01", "2026-11-30")
        self.assertEqual(_person_row(november, "Hill")["demos"], 1)
        self.assertEqual(_person_row(november, "Hill")["ran"], 2)
        self.assertEqual(_person_row(november, "Hill")["no_sit"], 1)
        self.assertEqual(_person_row(november, "Hill")["sales"], 1)
        self.assertEqual(_person_row(november, "Hill")["appointments"], 1)
        self.assertEqual(_person_row(november, "Vermeesch")["demos"], 2)
        self.assertEqual(_person_row(november, "Mancini")["demos"], 1)
        self.assertEqual(_day(november, "2026-11-16")["demos"], 1)
        self.assertEqual(_day(november, "2026-11-18")["demos"], 0)
        self.assertEqual(_day(november, "2026-11-10")["demos"], 1)
        self.assertEqual(november["totals"]["demos"], 4)
        self.assertEqual(november["totals"]["ran"], 5)
        counted_days = {row["appointment_occurred_at"][:10] for row in november["ran_appointments"]}
        self.assertEqual(counted_days, {"2026-11-04", "2026-11-05", "2026-11-10", "2026-11-12", "2026-11-16"})
        self.assertNotIn("2026-11-09", counted_days)
        self.assertNotIn("2026-11-18", counted_days)
        self.assertNotIn("2099-01-15", counted_days)

        december, _december_rate = self._assert_same_counts(db, "2026-12-01", "2026-12-31")
        self.assertEqual(december["totals"]["demos"], 0)
        self.assertEqual(december["totals"]["ran"], 0)
        self.assertEqual(december["ran_appointments"], [])

        far_future, _far_rate = self._assert_same_counts(db, "2099-01-01", "2099-01-31")
        self.assertEqual(far_future["totals"]["demos"], 0)
        self.assertEqual(far_future["totals"]["ran"], 0)


if __name__ == "__main__":
    unittest.main()
