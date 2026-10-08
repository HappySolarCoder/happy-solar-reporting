# -*- coding: utf-8 -*-

"""FMA Demo Rate — Sit / Ran with first-write-wins sit timestamp."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "api" / "metrics"
DEMO_SRC = (METRICS / "demo_rate.py").read_text()
INBOUND_SRC = (METRICS / "inbound_cac.py").read_text()
FMA_SRC = (ROOT / "api" / "fma_dashboard.py").read_text()

import sys

sys.path.insert(0, str(METRICS))
from sit_timestamp import as_aware_utc, frozen_sit_timestamp

NY = ZoneInfo("America/New_York")

# Warehouse lock — Joanne Miechowski / 113 Arend Ave only. Do not invent
# another example. Do not use 2025 duplicate PDDpxi8LpSVc4j3FTb50 / Mayer.
JOANNE_OPP_ID = "OF48x1PrhxehlJS3ReMc"
JOANNE_CONTACT_ID = "vPLhdbmd9ggy9d0i0GTY"
JOANNE_PIPELINE_ID = "GQtUlcTmLJ61HZjrGEPC"
JOANNE_STAGE_ID = "d22673c6-28aa-48c8-821b-8a8573d498da"
# Bug: current appointmentOccurredAt copied from appointmentStartTime follow-up.
JOANNE_OCCURRED_AT = datetime(2026, 8, 26, 18, 0, 0, tzinfo=timezone.utc)
# First Sit write / stage mark (New Appointment → Demo-Negotiating).
JOANNE_DISPOSITION_DATE = datetime(2026, 8, 20, 20, 45, 48, 990000, tzinfo=timezone.utc)
JOANNE_LAST_STAGE_CHANGE_AT = datetime(2026, 8, 20, 20, 45, 46, 331000, tzinfo=timezone.utc)
NOT_THE_TARGET_2025_OPP_ID = "PDDpxi8LpSVc4j3FTb50"


class SitTimestampFreezeTests(unittest.TestCase):
    def test_joanne_follow_up_does_not_move_sit_off_aug_20(self):
        frozen = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        self.assertEqual(frozen, JOANNE_DISPOSITION_DATE)
        self.assertEqual(frozen.astimezone(NY).date().isoformat(), "2026-08-20")
        self.assertEqual(frozen.astimezone(NY).strftime("%I:%M:%S %p"), "04:45:48 PM")
        self.assertNotEqual(frozen, JOANNE_OCCURRED_AT)

    def test_does_not_use_2025_duplicate(self):
        self.assertNotIn(NOT_THE_TARGET_2025_OPP_ID, DEMO_SRC)
        self.assertNotIn("ouBVilRfFMFr71ae7usF", DEMO_SRC)
        self.assertIn(JOANNE_OPP_ID, DEMO_SRC)
        self.assertIn(JOANNE_CONTACT_ID, DEMO_SRC)
        self.assertIn(JOANNE_PIPELINE_ID, DEMO_SRC)
        self.assertLess(JOANNE_LAST_STAGE_CHANGE_AT, JOANNE_DISPOSITION_DATE)
        self.assertLess(JOANNE_DISPOSITION_DATE, JOANNE_OCCURRED_AT)
        self.assertEqual(JOANNE_STAGE_ID, "d22673c6-28aa-48c8-821b-8a8573d498da")

    def test_first_write_wins_when_occurred_is_already_the_original_slot(self):
        occurred = datetime(2026, 8, 20, 17, 0, 0, tzinfo=NY)
        marked = datetime(2026, 8, 20, 18, 30, 0, tzinfo=NY)
        frozen = frozen_sit_timestamp(occurred, marked)
        self.assertEqual(frozen, occurred.astimezone(timezone.utc))

    def test_missing_disposition_date_falls_back_to_occurred(self):
        frozen = frozen_sit_timestamp(JOANNE_OCCURRED_AT, None)
        self.assertEqual(frozen, JOANNE_OCCURRED_AT)

    def test_missing_occurred_falls_back_to_disposition_date(self):
        frozen = frozen_sit_timestamp(None, JOANNE_DISPOSITION_DATE)
        self.assertEqual(frozen, JOANNE_DISPOSITION_DATE.astimezone(timezone.utc))

    def test_follow_up_is_not_a_second_sit(self):
        first = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        again = frozen_sit_timestamp(JOANNE_OCCURRED_AT, JOANNE_DISPOSITION_DATE)
        self.assertEqual(first, again)

    def test_iso_strings_parse(self):
        frozen = frozen_sit_timestamp(
            "2026-08-26T18:00:00Z",
            "2026-08-20T20:45:48.990Z",
        )
        self.assertEqual(frozen, JOANNE_DISPOSITION_DATE)

    def test_as_aware_utc_none(self):
        self.assertIsNone(as_aware_utc(None))
        self.assertIsNone(as_aware_utc(""))


class DemoRateContractTests(unittest.TestCase):
    def test_live_fma_formula_stays_sit_over_ran(self):
        self.assertIn('Opps Ran / Demos / Demo % (Demos / Ran)', FMA_SRC)
        self.assertIn("sit_by_setter_last_name", FMA_SRC)
        self.assertIn("/api/metrics/demo_rate", FMA_SRC)
        self.assertNotIn("Sit / (Sit + No Sit)", DEMO_SRC)
        self.assertIn('if dispo == "Sit":', DEMO_SRC)
        self.assertIn("sit / ran", DEMO_SRC)

    def test_uses_existing_dispo_contract_not_a_new_field(self):
        self.assertIn("GYGpLKBPfMpiBqyU2ogQ", DEMO_SRC)
        self.assertIn('appointment_occurred_at_field: str = "appointmentOccurredAt"', DEMO_SRC)
        self.assertIn('disposition_date_field: str = "dispositionDate"', DEMO_SRC)
        self.assertIn('disposition_value_field: str = "dispositionValue"', DEMO_SRC)
        self.assertIn("frozen_sit_timestamp", DEMO_SRC)
        self.assertIn("load_demo_rate_snaps", DEMO_SRC)

    def test_does_not_full_stream_opps(self):
        self.assertNotIn('db.collection(c.opp_collection).stream()', DEMO_SRC)
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', DEMO_SRC)
        self.assertIn(".where(c.appointment_occurred_at_field, \">=\", start_utc)", DEMO_SRC)
        self.assertIn(".where(c.disposition_date_field, \">=\", start_utc)", DEMO_SRC)

    def test_does_not_change_inbound_cac_sit_query(self):
        self.assertIn('APPOINTMENT_OCCURRED_AT_FIELD = "appointmentOccurredAt"', INBOUND_SRC)
        self.assertNotIn("frozen_sit_timestamp", INBOUND_SRC)
        self.assertNotIn("dispositionDate", INBOUND_SRC)
        self.assertIn("Bounded appointmentOccurredAt range; Sit only", INBOUND_SRC)

    def test_sale_contract_untouched(self):
        self.assertNotIn("P9oBjgbZjJdeE0OkBj9T", DEMO_SRC)

    def test_joanne_case_is_named_in_metric(self):
        self.assertIn(JOANNE_OPP_ID, DEMO_SRC)
        self.assertIn(JOANNE_CONTACT_ID, DEMO_SRC)
        self.assertIn("2026-08-20T20:45:48.990Z", DEMO_SRC)
        self.assertIn("Joanne Miechowski", DEMO_SRC)
        self.assertNotIn(NOT_THE_TARGET_2025_OPP_ID, DEMO_SRC)

    def test_closer_directory_is_bounded_and_emails_stay_off_the_public_payload(self):
        self.assertNotIn('db.collection("ghl_users_v2").stream()', DEMO_SRC)
        self.assertNotIn('db.collection("roster_people_v1").stream()', DEMO_SRC)
        self.assertIn('public.pop("owner_profiles", None)', DEMO_SRC)
        self.assertIn('where("ghl_user_id", "in", chunk)', DEMO_SRC)
        self.assertIn('.where(field, "==", uid).limit(1)', DEMO_SRC)


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

    def document(self, doc_id):
        return _Ref(doc_id, self._docs.get(doc_id))

    def where(self, field, op, value):
        return _Query(self._docs.values()).where(field, op, value)


class _Db:
    def __init__(self, **collections):
        self._collections = collections

    def collection(self, name):
        return self._collections[name]

    def get_all(self, refs):
        found = []
        for ref in refs:
            if ref._snap is None:
                found.append(_Snap(ref.id, {}, exists=False))
            else:
                found.append(ref._snap)
        return found


class CloserAttributionTests(unittest.TestCase):
    """assignedTo is the closer. Names come from roster, then the synced GHL user directory."""

    def _opp(self, doc_id, *, assigned=None, name=None, dispo="Sit", setter="Hill"):
        occurred = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
        opp = {
            "id": doc_id,
            "pipelineId": "pipe-buffalo",
            "contactId": "contact-" + doc_id,
            "dispositionValue": dispo,
            "appointmentOccurredAt": occurred,
            "dispositionDate": occurred,
            "customFields": [{"id": "Eq4NLTSkJ56KTxbxypuE", "value": setter}],
        }
        if assigned is not None:
            opp["assignedTo"] = assigned
        if name is not None:
            opp["assignedToName"] = name
        return _Snap(doc_id, opp)

    def _directory(self):
        return _Db(
            roster_people_v1=_Collection(
                [
                    _Snap(
                        "roster-evan",
                        {"display_name": "Evan R Day", "ghl_user_id": "userEvan"},
                    )
                ]
            ),
            ghl_users_v2=_Collection(
                [
                    _Snap(
                        "ghl-doc-evan",
                        {"userId": "userEvan", "name": "Evan Day", "email": "Evan@HappySLR.com"},
                    ),
                    _Snap(
                        "userPat",
                        {"id": "userPat", "name": "Pat Smith", "emailAddress": "pat@happyslr.com"},
                    ),
                    _Snap(
                        "0fhsjcmlntce0cpjyfhj",
                        {"id": "0fhsjcmlntce0cpjyfhj", "name": "Wrong Name", "email": "william@happyslr.com"},
                    ),
                ]
            ),
        )

    def _payload(self, snaps, db):
        from unittest.mock import patch

        import demo_rate

        filters = {"pipeline": None, "setter": None, "lead_source": None, "sweeper": None}
        with (
            patch.object(demo_rate, "load_demo_rate_snaps", return_value=snaps),
            patch.object(demo_rate, "pipeline_name_lookup", return_value={"pipe-buffalo": "Buffalo"}),
            patch.object(demo_rate, "load_contacts_by_ids", return_value={}),
        ):
            return demo_rate.build_payload(db, 2026, 10, filters, "2026-10-01", "2026-10-07")

    def test_assigned_to_resolves_to_the_closer_name(self):
        snaps = [
            self._opp("sit-evan", assigned="userEvan", dispo="Sit", setter="Day"),
            self._opp("nosit-evan", assigned="userEvan", dispo="No Sit", setter="Day"),
            self._opp("sit-pat", assigned="userPat", dispo="Sit"),
            self._opp("nosit-missing", assigned="unknownABCDEF", dispo="No Sit"),
            self._opp("sit-casey", name="Casey Lane", dispo="Sit"),
            self._opp("nosit-dict", assigned={"id": "dictUser123456", "name": "Dict Closer"}, dispo="No Sit"),
            self._opp("sit-breen", assigned="0fhsjcmlntce0cpjyfhj", dispo="Sit"),
            self._opp("ignored", assigned="userEvan", dispo="Cancelled", setter="Day"),
        ]
        payload = self._payload(snaps, self._directory())
        breakdowns = payload["breakdowns"]
        self.assertEqual(payload["ran_count"], 7)
        self.assertEqual(payload["sit_count"], 4)
        self.assertEqual(payload["result"], 57.1)
        self.assertEqual(
            breakdowns["ran_by_owner"],
            {
                "Evan R Day": 2,
                "Casey Lane": 1,
                "Dict Closer": 1,
                "Pat Smith": 1,
                "Unknown User (ABCDEF)": 1,
                "William Breen": 1,
            },
        )
        self.assertEqual(
            breakdowns["sit_by_owner"],
            {"Casey Lane": 1, "Evan R Day": 1, "Pat Smith": 1, "William Breen": 1},
        )
        self.assertEqual(breakdowns["sit_by_setter_last_name"], {"Day": 1, "Hill": 3})
        profiles = {row["name"]: row for row in payload["owner_profiles"]}
        self.assertEqual(profiles["Evan R Day"]["ghl_user_id"], "userEvan")
        self.assertEqual(profiles["Evan R Day"]["email"], "evan@happyslr.com")
        self.assertEqual(profiles["Pat Smith"]["ghl_user_id"], "userPat")
        self.assertEqual(profiles["Pat Smith"]["email"], "pat@happyslr.com")
        self.assertEqual(profiles["William Breen"]["email"], "william@happyslr.com")
        self.assertEqual(profiles["Casey Lane"]["ghl_user_id"], "")
        self.assertNotIn("evan@happyslr.com", str(payload["rows"]))

    def test_directory_failure_does_not_change_the_demo_total(self):
        from unittest.mock import patch

        import demo_rate

        snaps = [self._opp("sit-evan", assigned="userEvan", dispo="Sit")]
        filters = {"pipeline": None, "setter": None, "lead_source": None, "sweeper": None}
        with (
            patch.object(demo_rate, "load_demo_rate_snaps", return_value=snaps),
            patch.object(demo_rate, "pipeline_name_lookup", return_value={"pipe-buffalo": "Buffalo"}),
            patch.object(demo_rate, "load_contacts_by_ids", return_value={}),
            patch.object(demo_rate, "load_closer_directory", side_effect=RuntimeError("directory down")),
        ):
            payload = demo_rate.build_payload(object(), 2026, 10, filters, "2026-10-01", "2026-10-07")
        self.assertEqual(payload["sit_count"], 1)
        self.assertEqual(payload["ran_count"], 1)
        self.assertEqual(payload["breakdowns"]["sit_by_owner"], {"Unknown User (erEvan)": 1})


if __name__ == "__main__":
    unittest.main()
