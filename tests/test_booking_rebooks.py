# -*- coding: utf-8 -*-
"""Booking-date credits inside Opportunities Created.

John Pinkham (contact Wfxt7jcW4vh4LwqWYKwq) was booked by Ollie Calabrese
through the Happy Solar Booking Hub on Wed Nov 11 2026 at 2:44 PM Phoenix
(4:44 PM ET) on the Virtual calendar, assigned to Jeff Salas. He already had
April Virtual opportunity EKnVtmggYlnwfj7KvX8e, so the hub did not create a
new regional opportunity. Inbound/Lead Locker opportunity ptni8KkJRP8Isydm5qoO
was created that day and stays excluded. The set counts on Nov 11 against the
April opportunity.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import booking_rebooks as br  # noqa: E402
from opportunities_created import MetricContract, compute  # noqa: E402

PINKHAM = "Wfxt7jcW4vh4LwqWYKwq"
APRIL_OPP = "EKnVtmggYlnwfj7KvX8e"
LOCKER_OPP = "ptni8KkJRP8Isydm5qoO"
NEW_OPP = "newVirtualNov11aaaa"
VIRTUAL = "r1b9pwgliYj7WyWBchTV"
LOCKER = "7nSEgeoBYXZiIS7x41Jy"
JEFF = "jeffSalasUser0001"
OLD_OWNER = "formerCloser0001"
LEAD = "hd5QqHEOVSsPom5bJ32P"
SETTER = "Eq4NLTSkJ56KTxbxypuE"
SWEEPER = "HWfjOp8MvE6soxBAL75f"
# 2:44 PM Phoenix on Nov 11 2026 is 4:44 PM ET / 21:44 UTC.
BOOKED_NOV_11 = "2026-11-11T21:44:00.000Z"
BOOKED_NOV_12 = "2026-11-12T18:00:00.000Z"


class Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._d = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._d or {})


class Query:
    def __init__(self, db, name, filters=()):
        self.db, self.name, self.filters = db, name, list(filters)

    def where(self, field, op, value):
        return Query(self.db, self.name, self.filters + [(field, op, value)])

    def limit(self, _n):
        return self

    def document(self, doc_id):
        return (self.name, str(doc_id))

    def stream(self):
        self.db.queries.append((self.name, tuple(self.filters)))
        for doc_id, data in list(self.db.data.get(self.name, {}).items()):
            if all(_match(data.get(f), op, v) for f, op, v in self.filters):
                yield Snap(doc_id, data)


def _match(actual, op, value):
    if op == "in":
        return actual in value
    if actual is None:
        return False
    try:
        if op == "==":
            return actual == value
        if op == ">=":
            return actual >= value
        if op == "<":
            return actual < value
    except TypeError:
        return False
    raise AssertionError(op)


class FakeDB:
    def __init__(self, data):
        self.data = data
        self.queries = []

    def collection(self, name):
        return Query(self, name)

    def get_all(self, refs):
        for coll, doc_id in refs:
            yield Snap(doc_id, self.data.get(coll, {}).get(doc_id))


def cf(field_id, value):
    return {"id": field_id, "value": value}


def contact(sweeper=None, setter="Calabrese", lead="Inbound", last="Pinkham"):
    fields = [cf(LEAD, lead), cf(SETTER, setter)]
    if sweeper:
        fields.append(cf(SWEEPER, sweeper))
    return {"id": PINKHAM, "lastName": last, "customFields": fields}


def april_opp(**over):
    d = {
        "id": APRIL_OPP,
        "contactId": PINKHAM,
        "pipelineId": VIRTUAL,
        "pipelineStageId": "sale-cancelled",
        "pipelineStageName": "Sale Cancelled",
        "assignedTo": OLD_OWNER,
        "createdAt": "2026-04-06T15:00:00.000Z",
        "customFields": [],
    }
    d.update(over)
    return d


def locker_opp():
    return {
        "id": LOCKER_OPP,
        "contactId": PINKHAM,
        "pipelineId": LOCKER,
        "assignedTo": JEFF,
        "createdAt": "2026-11-11T21:44:30.000Z",
        "customFields": [],
    }


def appointment(**over):
    d = {
        "id": "appt-pinkham-nov11",
        "contactId": PINKHAM,
        "calendarId": "virtual-calendar",
        "assignedUserId": JEFF,
        "dateAdded": BOOKED_NOV_11,
        "startTime": "2026-11-15T19:00:00.000Z",
        "appointmentStatus": "confirmed",
        "status": "booked",
    }
    d.update(over)
    return d


def make_db(*, opps=None, appointments=None, contact_doc=None, events_raise=False):
    data = {
        "ghl_pipelines_v2": {
            VIRTUAL: {"id": VIRTUAL, "name": "Virtual"},
            LOCKER: {"id": LOCKER, "name": "Inbound/Lead Locker"},
        },
        "roster_people_v1": {
            "jeff": {"display_name": "Jeff Salas", "ghl_user_id": JEFF},
            "old": {"display_name": "Former Closer", "ghl_user_id": OLD_OWNER},
        },
        "ghl_users_v2": {},
        "ghl_opportunities_v2": {},
        "ghl_contacts_v2": {PINKHAM: contact_doc if contact_doc is not None else contact()},
        "ghl_appointment_events_v2": {},
        "ghl_calendar_events_v2": {},
        "ghl_appointments_v2": {},
    }
    for opp in opps or []:
        data["ghl_opportunities_v2"][opp["id"]] = opp
    for ev in appointments or []:
        data["ghl_appointment_events_v2"][ev["id"]] = ev
    db = FakeDB(data)
    if events_raise:
        real = db.collection

        def broken(name):
            if name == "ghl_appointment_events_v2":
                raise RuntimeError("index missing")
            return real(name)

        db.collection = broken
    return db


def november(db, **kw):
    br._CACHE.clear()
    return compute(db, MetricContract(), year=2026, month=11, pipeline_scope="all", **kw)


def on_day(db, day, **kw):
    br._CACHE.clear()
    return compute(db, MetricContract(), year=2026, month=11, start=day, end=day, pipeline_scope="all", **kw)


class PinkhamBookingTests(unittest.TestCase):
    def test_pinkham_counts_on_nov_11_against_the_april_opp(self):
        db = make_db(opps=[april_opp(), locker_opp()], appointments=[appointment()])
        day = on_day(db, "2026-11-11")
        month = november(make_db(opps=[april_opp(), locker_opp()], appointments=[appointment()]))
        for out in (day, month):
            self.assertEqual(out["result"], 1)
            self.assertEqual([r["opportunityId"] for r in out["sample_rows"]], [APRIL_OPP])
            row = out["sample_rows"][0]
            self.assertTrue(row["bookingRebook"])
            self.assertEqual(row["bookingDate"], "2026-11-11")
            self.assertEqual(row["createdAt"], "2026-11-11T21:44:00Z")
            self.assertEqual(row["contactId"], PINKHAM)
            self.assertEqual(row["contactLastName"], "Pinkham")
            self.assertEqual(row["pipeline"], "Virtual")
            self.assertEqual(row["owner"], "Jeff Salas")
            self.assertEqual(row["setterLastName"], "Calabrese")
            self.assertEqual(row["leadGenSource"], "Inbound")
            self.assertNotEqual(row["opportunityId"], LOCKER_OPP)
            self.assertEqual(out["breakdowns"]["created_by_setter_last_name"], {"Calabrese": 1})
            self.assertEqual(out["breakdowns"]["created_by_owner"], {"Jeff Salas": 1})
            self.assertEqual(out["breakdowns"]["created_by_lead_gen_source"], {"Inbound": 1})
            self.assertEqual(out["breakdowns"]["created_by_pipeline"], {"Virtual": 1})
            self.assertEqual(out["breakdowns"]["created_by_leadgen_bucket"]["3PL/Inbound"], 1)

    def test_two_appointments_the_same_day_count_once(self):
        later = appointment(id="appt-later", dateAdded="2026-11-11T22:10:00.000Z", assignedUserId="")
        db = make_db(opps=[april_opp(), locker_opp()], appointments=[later, appointment()])
        out = on_day(db, "2026-11-11")
        self.assertEqual(out["result"], 1)
        self.assertEqual(out["sample_rows"][0]["owner"], "Jeff Salas")

    def test_same_day_new_regional_opp_counts_once(self):
        fresh = {
            "id": NEW_OPP,
            "contactId": PINKHAM,
            "pipelineId": VIRTUAL,
            "assignedTo": JEFF,
            "createdAt": "2026-11-11T16:00:00.000Z",
            "customFields": [],
        }
        db = make_db(
            opps=[april_opp(), locker_opp(), fresh],
            appointments=[appointment()],
        )
        out = on_day(db, "2026-11-11")
        self.assertEqual(out["result"], 1)
        self.assertEqual(out["sample_rows"][0]["opportunityId"], NEW_OPP)
        self.assertNotIn("bookingRebook", out["sample_rows"][0])
        self.assertEqual(out["debug"]["booking_rebooks"]["booking_credits"], 0)
        self.assertGreaterEqual(out["debug"]["booking_rebooks"]["booking_selection"]["same_day_opportunity"], 1)

    def test_rebook_on_a_different_day_than_the_older_opp(self):
        # Booked Nov 12. The appointment itself is scheduled Nov 18. The only
        # regional opp was created April 6. No assignee, so the opp owner is used.
        ev = appointment(
            id="appt-nov12",
            dateAdded=BOOKED_NOV_12,
            startTime="2026-11-18T19:00:00.000Z",
            assignedUserId="",
        )
        owned = april_opp(assignedTo=JEFF)
        db = make_db(opps=[owned], appointments=[ev])
        booked = on_day(db, "2026-11-12")
        self.assertEqual(booked["result"], 1)
        row = booked["sample_rows"][0]
        self.assertEqual(row["bookingDate"], "2026-11-12")
        self.assertEqual(row["opportunityId"], APRIL_OPP)
        self.assertEqual(row["owner"], "Jeff Salas")
        self.assertEqual(row["setterLastName"], "Calabrese")
        scheduled = on_day(make_db(opps=[owned], appointments=[ev]), "2026-11-18")
        self.assertEqual(scheduled["result"], 0)
        self.assertEqual(scheduled["sample_rows"], [])

    def test_cancelled_deleted_and_invalid_appointments_do_not_count(self):
        for status in ("cancelled", "canceled", "invalid", "deleted"):
            db = make_db(
                opps=[april_opp(), locker_opp()],
                appointments=[appointment(id=f"appt-{status}", appointmentStatus=status)],
            )
            out = on_day(db, "2026-11-11")
            self.assertEqual(out["result"], 0, status)
            self.assertEqual(out["sample_rows"], [])
        deleted_flag = appointment(id="appt-flag", appointmentStatus="confirmed", deleted=True)
        out = on_day(make_db(opps=[april_opp()], appointments=[deleted_flag]), "2026-11-11")
        self.assertEqual(out["result"], 0)

    def test_sweeper_rehash_name_still_takes_the_setter_credit(self):
        db = make_db(
            opps=[april_opp()],
            appointments=[appointment()],
            contact_doc=contact(sweeper="Diamond"),
        )
        out = on_day(db, "2026-11-11")
        self.assertEqual(out["result"], 1)
        self.assertEqual(out["sample_rows"][0]["setterLastName"], "Diamond")
        self.assertEqual(out["sample_rows"][0]["sweeperRehashLastName"], "Diamond")
        self.assertEqual(out["breakdowns"]["created_by_setter_last_name"], {"Diamond": 1})

    def test_appointment_query_failure_keeps_created_opps(self):
        fresh = {
            "id": NEW_OPP,
            "contactId": PINKHAM,
            "pipelineId": VIRTUAL,
            "assignedTo": JEFF,
            "createdAt": "2026-11-11T16:00:00.000Z",
            "customFields": [],
        }
        db = make_db(opps=[fresh], events_raise=True)
        out = on_day(db, "2026-11-11")
        self.assertEqual(out["result"], 1)
        self.assertEqual(out["sample_rows"][0]["opportunityId"], NEW_OPP)
        self.assertIn("ghl_appointment_events_v2", out["debug"]["booking_rebooks"]["query_errors"])

    def test_ignored_status_helper(self):
        self.assertTrue(br.appointment_status_ignored({"appointmentStatus": "cancelled"}))
        self.assertTrue(br.appointment_status_ignored({"status": "invalid"}))
        self.assertTrue(br.appointment_status_ignored({"deleted": True, "appointmentStatus": "confirmed"}))
        self.assertFalse(br.appointment_status_ignored({"appointmentStatus": "confirmed"}))
        self.assertFalse(br.appointment_status_ignored({"appointmentStatus": "noshow"}))
        self.assertFalse(br.appointment_status_ignored({"appointmentStatus": "showed"}))


if __name__ == "__main__":
    unittest.main()
