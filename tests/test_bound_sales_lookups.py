# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SALES = (ROOT / "api" / "metrics" / "sales.py").read_text()
WARM = (ROOT / "api" / "warm_cache.py").read_text()
CREATED = (ROOT / "api" / "metrics" / "opportunities_created.py").read_text()
RAN = (ROOT / "api" / "metrics" / "opportunities_ran.py").read_text()
DEMO = (ROOT / "api" / "metrics" / "demo_rate.py").read_text()
GAPS = (ROOT / "api" / "metrics" / "sold_date_gaps.py").read_text()
INBOUND_CAC = (ROOT / "api" / "metrics" / "inbound_cac.py").read_text()

UNFILTERED_OPP_STREAMS = (
    'db.collection("ghl_opportunities_v2").stream()',
    "db.collection('ghl_opportunities_v2').stream()",
    "db.collection(c.opp_collection).stream()",
    "db.collection(MetricContract.opp_collection).stream()",
)
UNFILTERED_CONTACT_STREAMS = (
    'db.collection("ghl_contacts_v2").stream()',
    "db.collection('ghl_contacts_v2').stream()",
    "db.collection(c.contact_collection).stream()",
    "db.collection(MetricContract.contact_collection).stream()",
    "db.collection(contract.contact_collection).stream()",
)


class BoundLookupTests(unittest.TestCase):
    def test_compute_sales_does_not_stream_roster_or_pipelines(self):
        self.assertNotIn('db.collection("ghl_pipelines_v2").stream()', SALES)
        self.assertNotIn('db.collection("roster_people_v1").stream()', SALES)
        self.assertIn('db.collection("ghl_pipelines_v2").document', SALES)
        self.assertIn('db.collection("roster_people_v1").document', SALES)
        self.assertIn('where("ghl_user_id", "in", chunk)', SALES)
        self.assertIn('where("id", "==", pid).limit(1)', SALES)

    def test_warm_cache_has_no_metric_urls(self):
        self.assertIn("urls = []", WARM)
        self.assertNotIn("opportunities_created", WARM)
        self.assertNotIn("opportunities_ran", WARM)
        self.assertNotIn("demo_rate", WARM)
        self.assertNotIn("company_snapshot", WARM)
        self.assertNotIn("metrics/sales", WARM)
        self.assertNotIn("essential_sales", WARM)
        self.assertNotIn("sold_date_gaps", WARM)
        self.assertNotIn("inbound_cac", WARM)

    def test_created_ran_demo_do_not_full_stream_opps_or_contacts(self):
        for name, src in (("created", CREATED), ("ran", RAN), ("demo", DEMO)):
            for needle in UNFILTERED_OPP_STREAMS:
                self.assertNotIn(needle, src, f"{name} still has {needle}")
            for needle in UNFILTERED_CONTACT_STREAMS:
                self.assertNotIn(needle, src, f"{name} still has {needle}")

    def test_created_ran_demo_use_time_where_and_contact_get_all(self):
        self.assertIn(".where(c.created_at_field,", CREATED)
        self.assertIn("db.get_all(", CREATED)
        self.assertIn('db.collection("ghl_contacts_v2").document', CREATED)

        self.assertIn(".where(c.appointment_occurred_at_field,", RAN)
        self.assertIn("db.get_all(", RAN)
        self.assertIn('db.collection("ghl_contacts_v2").document', RAN)

        self.assertIn(".where(c.appointment_occurred_at_field,", DEMO)
        self.assertIn("db.get_all(", DEMO)
        self.assertIn('db.collection("ghl_contacts_v2").document', DEMO)

    def test_created_resolves_pipeline_name_with_compact_and_raw_keys(self):
        self.assertIn("def pipeline_id_keys", CREATED)
        self.assertIn("def resolve_pipeline_name", CREATED)
        self.assertIn('resolve_pipeline_name(pipe_names, opp.get("pipelineId"))', CREATED)
        self.assertNotIn('pname = pipe_names.get(pid) or pid or "unknown"', CREATED)
        self.assertNotIn('db.collection("ghl_pipelines_v2").stream()', CREATED)
        self.assertIn(".where(c.created_at_field,", CREATED)

    def test_pipeline_id_alias_resolves_whitespace_raw_str(self):
        """Charles: compact_str key vs filter raw str(pipelineId) dropped one Buffalo row."""
        ns: dict = {}
        exec(
            "from typing import Any\n"
            "def compact_str(value):\n"
            "    return ' '.join(str(value or '').strip().split())\n"
            "def pipeline_id_keys"
            + CREATED.split("def pipeline_id_keys", 1)[1].split("def load_contacts_by_ids", 1)[0],
            ns,
        )
        remember = ns["remember_pipeline_name"]
        resolve = ns["resolve_pipeline_name"]
        m = {}
        remember(m, "Buffalo", "buffalo-pipe-id")
        self.assertEqual(resolve(m, "buffalo-pipe-id"), "Buffalo")
        self.assertEqual(resolve(m, "  buffalo-pipe-id  "), "Buffalo")
        compact_only = {"buffalo-pipe-id": "Buffalo"}
        self.assertEqual(resolve(compact_only, "  buffalo-pipe-id  "), "Buffalo")
        self.assertEqual(resolve(compact_only, "buffalo-pipe-id"), "Buffalo")

    def test_sold_date_gaps_uses_sold_stage_query_and_contact_get_all(self):
        self.assertIn("P9oBjgbZjJdeE0OkBj9T", GAPS)
        self.assertIn('.where(contract.stage_field, "in", stage_ids)', GAPS)
        self.assertIn("db.get_all(", GAPS)
        self.assertIn('db.collection("ghl_contacts_v2").document', GAPS)
        self.assertNotIn('db.collection("ghl_contacts_v2").stream()', GAPS)
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', GAPS)
        self.assertNotIn("db.collection(c.opp_collection).stream()", GAPS)
        self.assertNotIn("db.collection(c.contact_collection).stream()", GAPS)
        self.assertNotIn(".set(", GAPS)
        self.assertNotIn(".update(", GAPS)
        self.assertNotIn(".delete(", GAPS)

    def test_inbound_cac_uses_pipeline_and_stage_bounds(self):
        self.assertIn('.where("pipelineId", "==", INBOUND_PIPELINE_ID)', INBOUND_CAC)
        self.assertIn('.where(STAGE_FIELD, "in", stage_ids)', INBOUND_CAC)
        self.assertIn("db.get_all(", INBOUND_CAC)
        self.assertIn("P9oBjgbZjJdeE0OkBj9T", INBOUND_CAC)
        self.assertIn("appointmentOccurredAt", INBOUND_CAC)
        self.assertNotIn('db.collection("ghl_contacts_v2").stream()', INBOUND_CAC)
        self.assertNotIn('db.collection("ghl_opportunities_v2").stream()', INBOUND_CAC)
        self.assertNotIn("db.collection(OPP_COLLECTION).stream()", INBOUND_CAC)
        self.assertNotIn("db.collection(CONTACT_COLLECTION).stream()", INBOUND_CAC)
        self.assertNotIn(".set(", INBOUND_CAC)
        self.assertNotIn(".update(", INBOUND_CAC)
        self.assertNotIn(".delete(", INBOUND_CAC)


if __name__ == "__main__":
    unittest.main()
