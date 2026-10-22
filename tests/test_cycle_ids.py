# -*- coding: utf-8 -*-
"""Frozen cycle rows ({opp}~cycle{n}) never leak into GHL links and never double count.

- Every GHL opportunity link built from a view row uses the real opp id.
- Opps Created counts a revived opp once, in its original month, even after a
  second revive (every frozen copy carries the opp's GHL createdAt; only the
  first cycle is the creation).
- A window that holds both a frozen cycle and the live opp still counts the
  opp once as created; ran / demos stay one per appointment cycle, the same
  as month-by-month sums.
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cycle_view as cv  # noqa: E402
import demo_rate  # noqa: E402
import opportunities_created as oc  # noqa: E402
import project_management as pm  # noqa: E402
import test_cycle_view as tcv  # noqa: E402

UTC = timezone.utc
OPP = tcv.OPP
LOC = "MMKRDviKggXzlcHQTnvZ"
OPP_URL = f"https://app.gohighlevel.com/v2/location/{LOC}/opportunities/list/{OPP}?tab=OpportunityDetails"


def revived_with_oct_sit():
    data = tcv.revive(tcv.book())
    data["ghl_opportunities_v2"][OPP].update({
        "dispositionValue": "Sit", "pipelineStageId": "demo-neg",
        "appointmentOccurredAt": datetime(2026, 10, 23, 17, tzinfo=UTC),
        "dispositionDate": datetime(2026, 10, 23, 19, tzinfo=UTC),
    })
    return data


def revived_twice():
    """Second revive on Dec 10: the sync freezes the Oct cycle as ~cycle2 (an exact copy, createdAt included)."""
    data = revived_with_oct_sit()
    prev = data["ghl_opportunities_v2"][OPP]
    snap = copy.deepcopy(prev)
    snap.update({"id": f"{OPP}~cycle2", "cycleOf": OPP, "cycleNumber": 2, "cycleEndedOn": "2026-12-10",
                 "cycleEndedAt": datetime(2026, 12, 10, 17, tzinfo=UTC)})
    data["ghl_opportunity_cycles_v1"][snap["id"]] = snap
    live = dict(prev)
    live.update({"pipelineStageId": tcv.NEW_APPT, "dispositionValue": None, "dispositionDate": None,
                 "appointmentOccurredAt": None, "appointmentCycle": 3, "selfGenRebookDate": "2026-12-10"})
    data["ghl_opportunities_v2"][OPP] = live
    return data


def created(db, **kw):
    return oc.compute(db, oc.MetricContract(), year=2026, month=5, pipeline_scope="all", **kw)


def zach_created_rows(payload):
    return [r for r in payload.get("sample_rows") or [] if cv.base_opp_id(r.get("opportunityId")) == OPP]


def ran_rows(db, start, end):
    s, e, _a, _b = demo_rate.date_range_window(start, end, "America/New_York") if hasattr(demo_rate, "date_range_window") else (None, None, None, None)
    snaps = demo_rate.load_demo_rate_snaps(db, demo_rate.MetricContract(), s, e)
    return sorted(
        (snap.id, (snap.to_dict() or {}).get("dispositionValue"))
        for snap in snaps
        if cv.base_opp_id(snap.id) == OPP and (snap.to_dict() or {}).get("dispositionValue") in ("Sit", "No Sit")
    )


class CycleIdHelpers(unittest.TestCase):
    def test_base_opp_id(self):
        self.assertEqual(cv.base_opp_id(f"{OPP}~cycle1"), OPP)
        self.assertEqual(cv.base_opp_id(f"{OPP}~cycle12"), OPP)
        self.assertEqual(cv.base_opp_id(OPP), OPP)
        self.assertEqual(cv.base_opp_id(None), "")
        self.assertEqual(cv.strip_cycle_suffix(f"/opportunities/list/{OPP}~cycle1?tab=OpportunityDetails"),
                         f"/opportunities/list/{OPP}?tab=OpportunityDetails")

    def test_view_rows_carry_the_real_ghl_id(self):
        db = tcv.world(revived_twice())
        rows = {s.id: s.to_dict() for s in db.collection("ghl_opportunities_v2").stream()}
        for rid in (OPP, f"{OPP}~cycle1", f"{OPP}~cycle2"):
            self.assertEqual(rows[rid]["ghlOpportunityId"], OPP)


class GhlLinksUseTheRealOpp(unittest.TestCase):
    def test_project_management_links(self):
        self.assertEqual(pm.ghl_opportunity_url(LOC, f"{OPP}~cycle1"), OPP_URL)
        item = pm.attach_ghl_links({"opportunityId": f"{OPP}~cycle1", "contactId": tcv.CONTACT}, default_location=LOC)
        self.assertEqual(item["ghlOpportunityUrl"], OPP_URL)
        self.assertEqual(item["ghlOpportunityId"], OPP)

    def test_company_overview_drawer_label(self):
        js = (ROOT / "api" / "ops_overview_script.txt").read_text(encoding="utf-8")
        self.assertIn("oppLabel(row.opportunityId)", js)
        self.assertNotIn("return [row.opportunityId,", js)


class NoDoubleCountAcrossCycles(unittest.TestCase):
    def test_second_revive_does_not_add_a_second_may_created(self):
        before = created(tcv.world(tcv.book()))
        after = created(tcv.world(revived_twice()))
        self.assertEqual(after["result"], before["result"])
        self.assertEqual(after["breakdowns"], before["breakdowns"])
        rows = zach_created_rows(after)
        self.assertEqual([r["opportunityId"] for r in rows], [f"{OPP}~cycle1"])

    def test_window_holding_frozen_and_live_rows_counts_created_once(self):
        db = tcv.world(revived_twice())
        payload = oc.compute(db, oc.MetricContract(), year=2026, month=5, start="2026-05-01", end="2026-12-31",
                             pipeline_scope="all")
        self.assertEqual(len(zach_created_rows(payload)), 1)
        ids = [cv.base_opp_id(r.get("opportunityId")) for r in payload.get("sample_rows") or []]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(payload["result"], len(ids))

    def test_rebook_credit_is_separate_from_created(self):
        db = tcv.world(revived_with_oct_sit())
        oct_ = oc.compute(db, oc.MetricContract(), year=2026, month=10, pipeline_scope="all", include_rebooks=True)
        self.assertEqual(zach_created_rows(oct_), [])
        self.assertEqual(oct_.get("self_gen_rebooks_count"), 1)

    def test_ran_is_one_per_cycle_and_months_add_up(self):
        db = tcv.world(revived_twice())
        may = ran_rows(db, "2026-05-01", "2026-05-31")
        oct_ = ran_rows(db, "2026-10-01", "2026-10-31")
        both = ran_rows(db, "2026-05-01", "2026-12-31")
        self.assertEqual(may, [(f"{OPP}~cycle1", "No Sit")])
        self.assertEqual(oct_, [(f"{OPP}~cycle2", "Sit")])
        self.assertEqual(both, sorted(may + oct_))  # the live cycle 3 has no outcome yet


if __name__ == "__main__":
    unittest.main()
