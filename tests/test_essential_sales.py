# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.append(path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sales = load_module("sales", METRICS / "sales.py")
essential = load_module("essential_sales_metric", METRICS / "essential_sales.py")
nav = load_module("dashboard_nav", API / "dashboard_nav.py")

ASI_FIELD_ID = essential.ASI_FIELD_ID
CLIENT_FIELD_ID = essential.CLIENT_FIELD_ID
ESSENTIAL_COLUMNS = essential.ESSENTIAL_COLUMNS
FINANCE_TYPE_FIELD_ID = essential.FINANCE_TYPE_FIELD_ID
INSTALLER_FIELD_ID = essential.INSTALLER_FIELD_ID
NOTES_FIELD_ID = essential.NOTES_FIELD_ID
SIZE_FIELD_ID = essential.SIZE_FIELD_ID
build_essential_row = essential.build_essential_row
address_display = essential.address_display
client_display = essential.client_display
custom_field_raw = essential.custom_field_raw
raw_text = essential.raw_text
compute_sales = sales.compute_sales
render_dashboard_nav = nav.render_dashboard_nav
page = load_module("essential_sales_page", API / "essential_sales.py")


class EssentialSalesMappingTests(unittest.TestCase):
    def test_columns_include_address_and_installer(self):
        labels = [label for _, label in ESSENTIAL_COLUMNS]
        self.assertEqual(
            labels[:16],
            [
                "Submission Date",
                "Finance type",
                "Cient",
                "Salesperson",
                "WC",
                "ASI",
                "ESCO",
                "CDG",
                "Size",
                "Phone",
                "Email",
                "Address",
                "Notes",
                "Retention Rep",
                "System Checks",
                "QP",
            ],
        )
        self.assertEqual(ESSENTIAL_COLUMNS[11], ("address", "Address"))
        self.assertEqual(ESSENTIAL_COLUMNS[16], ("installer", "Installer"))
        self.assertEqual(len(ESSENTIAL_COLUMNS), 17)
        self.assertEqual(INSTALLER_FIELD_ID, "JbTL2wtTiUUZ5wPZswDn")

    def test_custom_field_prefers_value_then_field_value_string(self):
        contact = {
            "customFields": [
                {"id": FINANCE_TYPE_FIELD_ID, "value": "", "fieldValueString": "Lease"},
                {"id": ASI_FIELD_ID, "value": "Yes"},
            ]
        }
        self.assertEqual(custom_field_raw(contact, FINANCE_TYPE_FIELD_ID), "Lease")
        self.assertEqual(custom_field_raw(contact, ASI_FIELD_ID), "Yes")
        self.assertIsNone(custom_field_raw(contact, "missing"))

    def test_client_uses_custom_field_else_last_first(self):
        contact = {"firstName": "Ada", "lastName": "Lovelace", "customFields": []}
        self.assertEqual(client_display(contact, None), "Lovelace, Ada")
        self.assertEqual(client_display(contact, "  Custom Client  "), "Custom Client")
        self.assertEqual(client_display({"firstName": "Ada"}, None), "Ada")
        self.assertEqual(client_display({"lastName": "Lovelace"}, None), "Lovelace")

    def test_size_stays_raw(self):
        self.assertEqual(raw_text(8.40), "8.4")
        self.assertEqual(raw_text("8.400"), "8.400")
        self.assertEqual(raw_text(None), "")

    def test_address_combines_standard_ghl_contact_fields(self):
        self.assertEqual(
            address_display(
                {
                    "address1": "123 Solar Way",
                    "city": "Buffalo",
                    "state": "NY",
                    "postalCode": "14201",
                }
            ),
            "123 Solar Way, Buffalo, NY 14201",
        )
        self.assertEqual(address_display({"address1": "123 Solar Way", "postalCode": "14201"}), "123 Solar Way, 14201")
        self.assertEqual(address_display(None), "")

    def test_notes_are_appointment_notes_only(self):
        contact = {
            "firstName": "Pat",
            "lastName": "Lee",
            "phone": "555-0100",
            "email": "pat@example.com",
            "address1": "10 Main St",
            "city": "Rochester",
            "state": "NY",
            "postalCode": "14604",
            "customFields": [
                {"id": NOTES_FIELD_ID, "value": "Appointment only"},
                {"id": "submission-checklist-id", "value": "DO NOT USE"},
                {"id": CLIENT_FIELD_ID, "value": "Lee Household"},
                {"id": FINANCE_TYPE_FIELD_ID, "value": "Loan"},
                {"id": ASI_FIELD_ID, "value": "No"},
                {"id": SIZE_FIELD_ID, "value": "9.12"},
            ],
        }
        row = build_essential_row(
            contact=contact,
            contact_id="c1",
            sold_date="2026-08-02",
            salesperson="William Breen",
        )
        self.assertEqual(row["notes"], "Appointment only")
        self.assertNotIn("DO NOT USE", row["notes"])
        self.assertEqual(row["systemChecks"], "")
        self.assertEqual(row["wc"], "")
        self.assertEqual(row["esco"], "")
        self.assertEqual(row["cdg"], "")
        self.assertEqual(row["retentionRep"], "")
        self.assertEqual(row["qp"], "")
        self.assertEqual(row["client"], "Lee Household")
        self.assertEqual(row["financeType"], "Loan")
        self.assertEqual(row["asi"], "No")
        self.assertEqual(row["size"], "9.12")
        self.assertEqual(row["phone"], "555-0100")
        self.assertEqual(row["email"], "pat@example.com")
        self.assertEqual(row["address"], "10 Main St, Rochester, NY 14604")
        self.assertEqual(row["salesperson"], "William Breen")
        self.assertEqual(row["submissionDate"], "2026-08-02")
        self.assertEqual(row["installer"], "")

    def test_installer_maps_from_ghl_field_and_blank_when_missing(self):
        contact = {
            "customFields": [
                {"id": INSTALLER_FIELD_ID, "value": "  Momentum  "},
                {"id": "other-installer-id", "value": "DO NOT USE"},
            ]
        }
        row = build_essential_row(
            contact=contact,
            contact_id="c-installer",
            sold_date="2026-08-04",
            salesperson="Alex",
        )
        self.assertEqual(row["installer"], "Momentum")
        self.assertTrue(all(row[k] == "" for k in ("wc", "esco", "cdg", "retentionRep", "systemChecks", "qp")))

        missing = build_essential_row(
            contact={"customFields": []},
            contact_id="c-missing",
            sold_date="2026-08-05",
            salesperson="Alex",
        )
        self.assertEqual(missing["installer"], "")

        via_string = build_essential_row(
            contact={
                "customFields": [
                    {"id": INSTALLER_FIELD_ID, "value": "", "fieldValueString": "3rd Roc"},
                ]
            },
            contact_id="c-string",
            sold_date="2026-08-06",
            salesperson="Alex",
        )
        self.assertEqual(via_string["installer"], "3rd Roc")
        self.assertEqual(custom_field_raw(contact, INSTALLER_FIELD_ID), "  Momentum  ")

    def test_sales_hook_is_optional_and_after_counts(self):
        params = inspect.signature(compute_sales).parameters
        self.assertEqual(params["on_sale"].default, None)
        source = inspect.getsource(compute_sales)
        self.assertIn('if cache_key in unique_contact_ids:', source)
        self.assertLess(source.find("unique_contact_ids.add"), source.find("if on_sale is not None"))
        self.assertIn("if len(contrib_rows) < 50:", source)

    def test_nav_includes_essential_sales(self):
        html = render_dashboard_nav("essential_sales")
        self.assertIn('href="/api/essential_sales"', html)
        self.assertIn("Essential Sales", html)
        self.assertIn("navmenu-item active", html)

    def test_result_comes_from_sales_payload(self):
        captured = {}

        def fake_compute_sales(db, contract, **kwargs):
            captured["on_sale"] = kwargs.get("on_sale")
            on_sale = kwargs.get("on_sale")
            if on_sale:
                on_sale(
                    opp={"assignedTo": "u1"},
                    contact={
                        "firstName": "Sam",
                        "lastName": "River",
                        "phone": "555",
                        "email": "sam@example.com",
                        "customFields": [],
                    },
                    contact_id="c-1",
                    sold_date="2026-08-03",
                    salesperson="Alex",
                )
            return {
                "year": 2026,
                "month": 8,
                "timezone": "America/New_York",
                "window_start_local": "2026-08-01T00:00:00-04:00",
                "window_end_local": "2026-09-01T00:00:00-04:00",
                "result": 31,
                "count_method": "locked",
                "debug": {
                    "opportunities_scanned": 703,
                    "distinct_contact_ids": 31,
                    "join": "ghl_opportunities_v2.contactId -> ghl_contacts_v2.id",
                },
                "breakdowns": {"sales_by_owner": {"Alex": 31}},
                "contract": {"base_collection": "ghl_opportunities_v2"},
            }

        original = essential.compute_sales
        essential.compute_sales = fake_compute_sales
        try:
            payload = essential.compute_essential_sales(
                db=None,
                contract=sales.SalesMetricContract(),
                year=2026,
                month=8,
                tz="America/New_York",
            )
        finally:
            essential.compute_sales = original

        self.assertIsNotNone(captured["on_sale"])
        self.assertEqual(payload["result"], 31)
        self.assertEqual(payload["debug"]["sales_result"], 31)
        self.assertEqual(payload["debug"]["opportunities_scanned"], 703)
        self.assertEqual(payload["debug"]["distinct_contact_ids"], 31)
        self.assertEqual(payload["debug"]["owner_sum"], 31)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["client"], "River, Sam")
        self.assertEqual(payload["rows"][0]["salesperson"], "Alex")
        self.assertEqual(payload["rows"][0]["installer"], "")
        self.assertEqual(payload["rows"][0]["address"], "")
        self.assertTrue(all(payload["rows"][0][k] == "" for k in ("wc", "esco", "cdg", "retentionRep", "systemChecks", "qp")))
        self.assertIsNone(payload["contract"]["installer_filter"])
        self.assertEqual(
            payload["contract"]["fields"]["installer"],
            "ghl_contacts_v2.customFields[JbTL2wtTiUUZ5wPZswDn]",
        )
        self.assertEqual(
            payload["contract"]["fields"]["address"],
            "ghl_contacts_v2.address1 + city + state + postalCode",
        )
        self.assertEqual([c["key"] for c in payload["columns"]][-1], "installer")

    def test_dashboard_renders_columns_from_payload(self):
        html = page.render_html(2026, 8)
        self.assertIn("renderTable(document.getElementById('salesTable'), data.columns || [], data.rows || [])", html)
        self.assertIn("Installer is not filtered.", html)


if __name__ == "__main__":
    unittest.main()
