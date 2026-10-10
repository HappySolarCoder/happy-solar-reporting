"""Sweeper credit endpoint: rows carry Sweeper/Rehash Last Name; sales stays locked."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "metrics"))

import sweeper_credit  # noqa: E402

FIELD = "HWfjOp8MvE6soxBAL75f"


class SweeperCreditTest(unittest.TestCase):
    def test_created_rows_expose_field(self):
        created = (ROOT / "api/metrics/opportunities_created.py").read_text()
        self.assertIn('"sweeperRehashLastName": sweeper_last or None', created)

    def test_appointment_rows_match_name_and_dedupe(self):
        payload = {"sample_rows": [
            {"opportunityId": "o1", "sweeperRehashLastName": "Diamond", "pipeline": "Rehash"},
            {"opportunityId": "o1", "sweeperRehashLastName": "diamond "},
            {"opportunityId": "o2", "sweeperRehashLastName": "Other"},
            {"opportunityId": "o3", "sweeperRehashLastName": None, "setterLastName": "Diamond"},
            {"opportunityId": "o4", "sweeperRehashLastName": "DIAMOND", "pipeline": "Virtual"},
        ]}
        rows = sweeper_credit.appointment_rows(payload, "Diamond")
        self.assertEqual([r["opportunityId"] for r in rows], ["o1", "o4"])

    def test_compute_counts_sales_by_field_distinct_contact(self):
        created = {"sample_rows": [{"opportunityId": "o1", "sweeperRehashLastName": "Diamond"}]}
        tagged = {"customFields": [{"id": FIELD, "value": "Diamond"}]}

        def fake_sales(db, contract, **kw):
            hook = kw["on_sale"]
            hook(opp={"id": "a"}, contact=tagged, contact_id="c1", sold_date="2026-10-02", salesperson="x")
            hook(opp={"id": "b"}, contact=tagged, contact_id="c1", sold_date="2026-10-02", salesperson="x")
            hook(opp={"id": "c"}, contact={}, contact_id="c2", sold_date="2026-10-03", salesperson="x")
            hook(opp={"id": "d", "customFields": [{"id": FIELD, "value": "Diamond"}]}, contact={}, contact_id="c3", sold_date="2026-10-04", salesperson="x")
            return {"window_start_local": "s", "window_end_local": "e"}

        with mock.patch("opportunities_created.compute", return_value=created), mock.patch("sales.compute_sales", side_effect=fake_sales):
            out = sweeper_credit.compute_sweeper_credit(object(), year=2026, month=10, last_name="Diamond")
        self.assertEqual(out["appointments_set"], 1)
        self.assertEqual(out["sales"], 2)

    def test_sales_contract_untouched(self):
        self.assertNotIn(FIELD, (ROOT / "api/metrics/sales.py").read_text())


if __name__ == "__main__":
    unittest.main()
