# -*- coding: utf-8 -*-

"""Rep Daily Recap counts only territory-pipeline appointments.

ClickUp 86bc7a8zw / 86bc7ahnt. Fixture is the 2026-09-24 ET warehouse
snapshot (2026-09-24 15:37 MST). Sweeper, Rehash, Inbound/Lead Locker,
Recruiting, All, and unknown pipelines stay off owner cards.
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
INBOUND_CAC_SRC = (API / "metrics" / "inbound_cac.py").read_text(encoding="utf-8")
DEMO_RATE_SRC = (API / "metrics" / "demo_rate.py").read_text(encoding="utf-8")
OPPS_RAN_SRC = (API / "metrics" / "opportunities_ran.py").read_text(encoding="utf-8")
OPPS_CREATED_SRC = (API / "metrics" / "opportunities_created.py").read_text(encoding="utf-8")
SC_OVERVIEW_SRC = (API / "sc_overview.py").read_text(encoding="utf-8")
SALES_SRC = (API / "metrics" / "sales.py").read_text(encoding="utf-8")
FMA_PAYROLL_SRC = (API / "private" / "fma_payroll_logic.py").read_text(encoding="utf-8")

TZ = ZoneInfo("America/New_York")
WINDOW_START = datetime(2026, 9, 24, 0, 0, tzinfo=TZ)
WINDOW_END = datetime(2026, 9, 25, 0, 0, tzinfo=TZ)
LEAD_SOURCE_FIELD_ID = "hd5QqHEOVSsPom5bJ32P"
ALL_PIPELINE_ID = "q9XavHDlkN27aavOLfkI"

ALLEN_ID = "YYkIcdAiCtNFR1pgOarJ"
QUINCY_ID = "zmEOiiPp5wpwjjgxhlo6"
RUEBEN_ID = "f4udrh1LuU0TEkF4ZFSj"
ZACH_ID = "nFf2FIr40kvWRCVaMej2"
BROOKE_ID = "XI56R86CcRMeIAwrVdvI"
BRIAN_ID = "xOY6fGHE392ePCZJ8wFd"
ETHAN_ID = "tpN9angVQz6IlTdK01v3"
JOSHUA_ID = "x694XBRmSdI9aNL2aTUw"
ROSS_ID = "p9VZOZ317DEax3wMa66h"
TOM_ID = "Z13gVOSSVftw051ffhJy"
OFF_ROSTER_ID = "offRosterOnlyRehash1"

ROSTER = (
    (ALLEN_ID, "Allen Frazier"),
    (QUINCY_ID, "Quincy Sermons"),
    (RUEBEN_ID, "Rueben Hand"),
    (ZACH_ID, "Zachary Maecker"),
    (BROOKE_ID, "Brooke Simpson"),
    (BRIAN_ID, "Brian Grim"),
    (ETHAN_ID, "Ethan Sauriol"),
    (JOSHUA_ID, "Joshua Merkel"),
    (ROSS_ID, "Ross Williamson"),
    (TOM_ID, "Tom Sisson"),
)

STAGE_DEMO = "stage-demo-negotiating"
STAGE_NEW = "stage-new-appointment"
STAGE_SOLD = "stage-sold"
STAGE_RESCHEDULE_3 = "stage-reschedule-attempt-3"
STAGE_REHASH_1 = "stage-rehash-attempt-1"
STAGE_RESCHEDULE_NEEDED = "stage-reschedule-needed"

DROPPED_OPP_IDS = ("5bImGQGn3XqdFSzBVfKd", "Oax8bux3oTSotLK2Lr6s")


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
    spec = importlib.util.spec_from_file_location("rep_daily_recap_pipelines", API / "rep_daily_recap.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load api/rep_daily_recap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rep_daily_recap_pipelines"] = module
    spec.loader.exec_module(module)
    return module


recap = load_recap()


def _et(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 24, hour, minute, tzinfo=TZ).astimezone(timezone.utc)


def _contact(name: str, lead_source: str) -> dict:
    return {
        "contactName": name,
        "customFields": [{"id": LEAD_SOURCE_FIELD_ID, "value": lead_source}],
    }


def _opp(
    opp_id: str,
    owner_id: str,
    pipeline_id: str,
    stage_id: str,
    lead_source: str,
    disposition: str | None,
    hour: int,
    minute: int,
    contact_name: str,
) -> tuple[dict, dict]:
    contact_id = f"contact-{opp_id}"
    row = {
        "id": opp_id,
        "assignedTo": owner_id,
        "pipelineId": pipeline_id,
        "pipelineStageId": stage_id,
        "contactId": contact_id,
        "name": contact_name,
        "appointmentStartTime": _et(hour, minute),
    }
    if disposition:
        row["dispositionValue"] = disposition
    return row, _contact(contact_name, lead_source)


# Live warehouse rows for 2026-09-24 ET. Customer names are placeholders.
FIXTURE_ROWS = (
    ("vU8vy8bbA8scuyxTalUk", ALLEN_ID, recap.ROCHESTER_PIPELINE_ID, STAGE_DEMO, "Self Gen", "Sit", 15, 0, "Allen Sit"),
    ("S55FWrr6Jqm72V2oySMM", ALLEN_ID, recap.ROCHESTER_PIPELINE_ID, STAGE_NEW, "Self Gen", None, 11, 30, "Allen Pending"),
    ("dX9uCiU3D9TvOXDe7F2e", QUINCY_ID, recap.ROCHESTER_PIPELINE_ID, STAGE_NEW, "Doors", None, 15, 0, "Quincy A"),
    ("xc3xaOkD0jLHZVUS8KAf", QUINCY_ID, recap.ROCHESTER_PIPELINE_ID, STAGE_NEW, "Doors", None, 16, 30, "Quincy B"),
    ("FxBxOZccRiMVgbstxilo", QUINCY_ID, recap.ROCHESTER_PIPELINE_ID, STAGE_SOLD, "Doors", "Sit", 10, 30, "Quincy Sit"),
    ("5bImGQGn3XqdFSzBVfKd", RUEBEN_ID, recap.REHASH_PIPELINE_ID, STAGE_RESCHEDULE_3, "Doors", "No Sit", 18, 30, "Tim M."),
    ("rGpYVXuzIWZZAtpQFwjO", RUEBEN_ID, recap.BUFFALO_PIPELINE_ID, STAGE_NEW, "Doors", None, 18, 30, "Tim M. Buffalo"),
    ("yVjDm6fzGMxEhsYcuRUs", RUEBEN_ID, recap.BUFFALO_PIPELINE_ID, STAGE_NEW, "Doors", None, 10, 30, "Rueben Pending"),
    ("Oax8bux3oTSotLK2Lr6s", ZACH_ID, recap.REHASH_PIPELINE_ID, STAGE_REHASH_1, "Self Gen", "No Sit", 15, 30, "Wiley M."),
    ("RTg0ukowA7gWc1kTmTc8", ZACH_ID, recap.BUFFALO_PIPELINE_ID, STAGE_NEW, "Self Gen", None, 15, 30, "Wiley M. Buffalo"),
    ("s0aai4qAm5QUNpoAo0lP", ZACH_ID, recap.BUFFALO_PIPELINE_ID, STAGE_NEW, "Self Gen", None, 17, 30, "Zach Pending"),
    ("GQANKYafuuuw5GZdG72o", BROOKE_ID, recap.BUFFALO_PIPELINE_ID, STAGE_RESCHEDULE_NEEDED, "Doors", "No Sit", 17, 0, "Brooke No Sit"),
    ("V93eVyyMb2frGq5FgP6b", BROOKE_ID, recap.BUFFALO_PIPELINE_ID, STAGE_NEW, "Doors", None, 18, 30, "Brooke Pending"),
)


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


def _pipeline_docs() -> dict[str, dict]:
    buffalo_stages = [
        {"id": STAGE_NEW, "name": "New Appointment"},
        {"id": STAGE_RESCHEDULE_NEEDED, "name": "Reschedule Needed"},
    ]
    rochester_stages = [
        {"id": STAGE_DEMO, "name": "Demo-Negotiating"},
        {"id": STAGE_NEW, "name": "New Appointment"},
        {"id": STAGE_SOLD, "name": "Sold"},
    ]
    rehash_stages = [
        {"id": STAGE_RESCHEDULE_3, "name": "Reschedule Attempt 3"},
        {"id": STAGE_REHASH_1, "name": "Rehash Attempt 1"},
    ]
    sweeper_stages = [{"id": STAGE_NEW, "name": "New Appointment"}]
    return {
        recap.BUFFALO_PIPELINE_ID: {"id": recap.BUFFALO_PIPELINE_ID, "name": "Buffalo", "stages": buffalo_stages},
        recap.ROCHESTER_PIPELINE_ID: {"id": recap.ROCHESTER_PIPELINE_ID, "name": "Rochester", "stages": rochester_stages},
        recap.REHASH_PIPELINE_ID: {"id": recap.REHASH_PIPELINE_ID, "name": "Rehash", "stages": rehash_stages},
        recap.SWEEPER_PIPELINE_ID: {"id": recap.SWEEPER_PIPELINE_ID, "name": "Sweeper", "stages": sweeper_stages},
    }


def _collections(extra_opps: tuple[tuple, ...] = ()) -> dict[str, dict[str, dict]]:
    opportunities: dict[str, dict] = {}
    contacts: dict[str, dict] = {}
    for spec in FIXTURE_ROWS + extra_opps:
        opp, contact = _opp(*spec)
        opportunities[opp["id"]] = opp
        contacts[opp["contactId"]] = contact
    roster = {
        f"roster-{owner_id}": {
            "display_name": label,
            "ghl_user_id": owner_id,
            "person_key": f"person-{owner_id}",
            "role": "rep",
        }
        for owner_id, label in ROSTER
    }
    users = {
        owner_id: {"id": owner_id, "name": label, "email": f"{label.split()[0].lower()}@happyslr.com"}
        for owner_id, label in ROSTER
    }
    users[OFF_ROSTER_ID] = {"id": OFF_ROSTER_ID, "name": "Casey Outsider", "email": "casey@happyslr.com"}
    return {
        "ghl_pipelines_v2": _pipeline_docs(),
        "roster_people_v1": roster,
        "ghl_users_v2": users,
        "ghl_opportunities_v2": opportunities,
        "ghl_contacts_v2": contacts,
        "raydar_leads_v1": {},
        "raydar_users_v1": {},
    }


def _build(extra_opps: tuple[tuple, ...] = ()) -> dict:
    db = DB(_collections(extra_opps))
    original_get_db = recap.get_db
    original_powerline = recap.get_powerline_db

    def _get_db():
        return db

    def _powerline():
        raise RuntimeError("Powerline skipped")

    recap.get_db = _get_db
    recap.get_powerline_db = _powerline
    try:
        return recap.build_payload(WINDOW_START, WINDOW_END)
    finally:
        recap.get_db = original_get_db
        recap.get_powerline_db = original_powerline


def _owner(payload: dict, label: str) -> dict:
    matches = [row for row in payload["owners"] if row["owner_label"] == label]
    if len(matches) != 1:
        labels = [row["owner_label"] for row in payload["owners"]]
        raise AssertionError(f"expected one owner {label}, found {labels}")
    return matches[0]


def _opp_ids(payload: dict) -> set[str]:
    found: set[str] = set()
    for owner in payload["owners"]:
        for row in owner.get("appointments") or []:
            found.add(row.get("opportunity_id") or "")
    return found


class PipelinePredicateTests(unittest.TestCase):
    def test_territory_ids_including_whitespace(self):
        for pipeline_id in recap.TERRITORY_PIPELINE_IDS:
            self.assertTrue(recap.is_recap_appointment_pipeline(pipeline_id))
            self.assertTrue(recap.is_recap_appointment_pipeline(f"  {pipeline_id}  "))
        self.assertEqual(
            set(recap.TERRITORY_PIPELINE_IDS),
            {
                recap.BUFFALO_PIPELINE_ID,
                recap.ROCHESTER_PIPELINE_ID,
                recap.SYRACUSE_PIPELINE_ID,
                recap.VIRTUAL_PIPELINE_ID,
            },
        )

    def test_non_territory_ids_are_excluded(self):
        for pipeline_id in (
            recap.SWEEPER_PIPELINE_ID,
            recap.REHASH_PIPELINE_ID,
            recap.INBOUND_LEAD_LOCKER_PIPELINE_ID,
            recap.RECRUITING_PIPELINE_ID,
            ALL_PIPELINE_ID,
            "",
            None,
        ):
            self.assertFalse(recap.is_recap_appointment_pipeline(pipeline_id))


class BuildPayloadTerritoryFilterTests(unittest.TestCase):
    def test_2026_09_24_drops_rehash_and_keeps_territory_rows(self):
        payload = _build()
        summary = payload["summary"]
        self.assertEqual(summary["appointments_total"], 11)
        self.assertEqual(summary["self_gen_appointments_total"], 4)
        self.assertEqual(summary["completed_outcomes_total"], 3)
        self.assertEqual(summary["pending_outcomes_total"], 8)
        self.assertEqual(summary["excluded_non_territory_appointments_total"], 2)
        self.assertEqual(payload["appointment_pipeline_scope"], "territory")
        self.assertEqual(
            payload["excluded_non_territory_appointments"],
            [{"pipeline": "Rehash", "count": 2}],
        )

        expected = {
            "Allen Frazier": (2, 2, 1, 1),
            "Quincy Sermons": (3, 0, 1, 2),
            "Rueben Hand": (2, 0, 0, 2),
            "Zachary Maecker": (2, 2, 0, 2),
            "Brooke Simpson": (2, 0, 1, 1),
            "Brian Grim": (0, 0, 0, 0),
            "Ethan Sauriol": (0, 0, 0, 0),
            "Joshua Merkel": (0, 0, 0, 0),
            "Ross Williamson": (0, 0, 0, 0),
            "Tom Sisson": (0, 0, 0, 0),
        }
        self.assertEqual(summary["owners_total"], 10)
        self.assertEqual(summary["owners_with_activity"], 5)
        for label, (appointments, self_gen, completed, pending) in expected.items():
            owner = _owner(payload, label)
            self.assertEqual(owner["appointment_total"], appointments, label)
            self.assertEqual(owner["self_gen_appointment_total"], self_gen, label)
            self.assertEqual(owner["completed_total"], completed, label)
            self.assertEqual(owner["pending_total"], pending, label)

        listed = _opp_ids(payload)
        for dropped in DROPPED_OPP_IDS:
            self.assertNotIn(dropped, listed)
        rueben_ids = {row["opportunity_id"] for row in _owner(payload, "Rueben Hand")["appointments"]}
        self.assertIn("rGpYVXuzIWZZAtpQFwjO", rueben_ids)
        self.assertEqual(_owner(payload, "Rueben Hand")["owner_id"], RUEBEN_ID)
        zach_sources = [row["lead_source"] for row in _owner(payload, "Zachary Maecker")["appointments"]]
        allen_sources = [row["lead_source"] for row in _owner(payload, "Allen Frazier")["appointments"]]
        self.assertEqual(zach_sources.count("Self Gen"), 2)
        self.assertEqual(allen_sources.count("Self Gen"), 2)
        self.assertEqual(
            {row["opportunity_id"] for row in _owner(payload, "Zachary Maecker")["appointments"]},
            {"RTg0ukowA7gWc1kTmTc8", "s0aai4qAm5QUNpoAo0lP"},
        )
        self.assertEqual(
            {row["opportunity_id"] for row in _owner(payload, "Allen Frazier")["appointments"]},
            {"vU8vy8bbA8scuyxTalUk", "S55FWrr6Jqm72V2oySMM"},
        )

        html = recap.render_html(payload, "2026-09-24")
        self.assertIn(
            "Territory-pipeline (Buffalo/Rochester/Syracuse/Virtual) appointments scheduled in the selected ET day",
            html,
        )
        self.assertIn("Excluded non-territory appointments (Sweeper/Rehash/other): 2", html)
        self.assertIn(
            "Self Gen = contact lead source Self Gen (hd5QqHEOVSsPom5bJ32P) on appointments scheduled that ET day.",
            html,
        )

    def test_extra_sweeper_row_is_excluded_under_sweeper(self):
        sweeper = (
            (
                "sweeperSyntheticQuincy1",
                QUINCY_ID,
                recap.SWEEPER_PIPELINE_ID,
                STAGE_NEW,
                "Doors",
                "No Sit",
                12,
                0,
                "Sweeper Extra",
            ),
        )
        payload = _build(sweeper)
        self.assertEqual(payload["summary"]["appointments_total"], 11)
        self.assertEqual(_owner(payload, "Quincy Sermons")["appointment_total"], 3)
        self.assertEqual(payload["summary"]["excluded_non_territory_appointments_total"], 3)
        self.assertEqual(
            payload["excluded_non_territory_appointments"],
            [{"pipeline": "Rehash", "count": 2}, {"pipeline": "Sweeper", "count": 1}],
        )
        self.assertNotIn("sweeperSyntheticQuincy1", _opp_ids(payload))


class OwnerMappingTests(unittest.TestCase):
    def test_roster_rep_with_only_rehash_still_renders_at_zero(self):
        extra = (
            (
                "brianOnlyRehashOpp1",
                BRIAN_ID,
                recap.REHASH_PIPELINE_ID,
                STAGE_REHASH_1,
                "Doors",
                "No Sit",
                9,
                0,
                "Brian Rehash",
            ),
            (
                "offRosterSweeperOpp1",
                OFF_ROSTER_ID,
                recap.SWEEPER_PIPELINE_ID,
                STAGE_NEW,
                "Doors",
                None,
                13,
                0,
                "Off Roster Sweeper",
            ),
        )
        payload = _build(extra)
        brian = _owner(payload, "Brian Grim")
        self.assertEqual(brian["appointment_total"], 0)
        self.assertEqual(brian["owner_id"], BRIAN_ID)
        labels = {row["owner_label"] for row in payload["owners"]}
        self.assertNotIn("Casey Outsider", labels)
        self.assertNotIn(OFF_ROSTER_ID, {row["owner_id"] for row in payload["owners"]})
        self.assertNotIn("brianOnlyRehashOpp1", _opp_ids(payload))
        self.assertNotIn("offRosterSweeperOpp1", _opp_ids(payload))
        excluded = {row["pipeline"]: row["count"] for row in payload["excluded_non_territory_appointments"]}
        self.assertEqual(excluded["Rehash"], 3)
        self.assertEqual(excluded["Sweeper"], 1)


class TerritoryConstantSyncTests(unittest.TestCase):
    def test_ids_match_inbound_cac_text(self):
        for pipeline_id in recap.TERRITORY_PIPELINE_IDS:
            self.assertIn(pipeline_id, INBOUND_CAC_SRC)
        self.assertEqual(
            set(recap.TERRITORY_PIPELINE_IDS),
            {
                "GQtUlcTmLJ61HZjrGEPC",
                "qJNvqKWp8Xc7DaBr8QYc",
                "etLURrEVxupngZZRlISG",
                "r1b9pwgliYj7WyWBchTV",
            },
        )
        self.assertIn("TERRITORY_PIPELINE_IDS", INBOUND_CAC_SRC)


class OtherReportsUnchangedTests(unittest.TestCase):
    def test_demo_rate_and_opportunities_ran_contracts(self):
        self.assertIn(
            'included_pipeline_names: tuple[str, ...] = ("buffalo", "rochester", "virtual", "syracuse", "rehash", "sweeper")',
            DEMO_RATE_SRC,
        )
        self.assertIn("excluded_pipeline_names: tuple[str, ...] = ()", OPPS_RAN_SRC)

    def test_other_modules_do_not_reference_recap_pipeline_filter(self):
        for src in (OPPS_CREATED_SRC, SC_OVERVIEW_SRC, SALES_SRC, FMA_PAYROLL_SRC):
            self.assertNotIn("is_recap_appointment_pipeline", src)
            self.assertNotIn("excluded_non_territory_appointments", src)


if __name__ == "__main__":
    unittest.main()
