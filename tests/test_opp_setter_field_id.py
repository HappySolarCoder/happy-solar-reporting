# -*- coding: utf-8 -*-
"""Opportunity Setter Last Name is GHL opp field 6yC1MxhJn9AkVMbAYAUU, not the contact id.

With the contact id (Eq4NLTSkJ56KTxbxypuE) the opp-level read always missed, so the
contact value won. A later booking form that overwrote the contact then relabeled the
original opp in its old month (September 2026: opp 4EKb8KQk721Z5ecAiaJb moved from
Calabrese to Sermons). The opp field now wins; the contact is the fallback.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "api", ROOT / "api" / "metrics"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import demo_rate  # noqa: E402
import opportunities_created  # noqa: E402
import opportunities_ran  # noqa: E402

OPP_FIELD = "6yC1MxhJn9AkVMbAYAUU"
CONTACT_FIELD = "Eq4NLTSkJ56KTxbxypuE"


class OppSetterFieldIdTests(unittest.TestCase):
    def test_contracts_point_at_the_opportunity_field(self):
        for mod in (opportunities_created, demo_rate, opportunities_ran):
            c = mod.MetricContract()
            self.assertEqual(c.setter_last_name_opportunity_cf_id, OPP_FIELD, mod.__name__)
            self.assertEqual(c.setter_last_name_contact_cf_id, CONTACT_FIELD, mod.__name__)

    def test_opp_value_wins_and_contact_is_fallback(self):
        opp = {"customFields": [{"id": OPP_FIELD, "type": "string", "fieldValueString": "Calabrese"}]}
        for mod in (opportunities_created, demo_rate, opportunities_ran):
            c = mod.MetricContract()
            self.assertEqual(mod.opportunity_custom_field(opp, c.setter_last_name_opportunity_cf_id), "Calabrese")
            self.assertIsNone(mod.opportunity_custom_field({"customFields": []}, c.setter_last_name_opportunity_cf_id))
            # The contact id never matches an opportunity custom field.
            self.assertIsNone(mod.opportunity_custom_field(opp, CONTACT_FIELD))


if __name__ == "__main__":
    unittest.main()
