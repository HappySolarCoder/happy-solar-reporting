# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from datetime import datetime, timezone
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


pm = load_module("project_management_metrics", METRICS / "project_management.py")
pages = load_module("pm_pages_under_test", API / "pm_pages.py")
hub_page = load_module("project_management_hub_page", API / "project_management_hub.py")
hold_page = load_module("hold_cancelled_page", API / "hold_cancelled.py")
nav = load_module("dashboard_nav_pm_pages", API / "dashboard_nav.py")

OPPORTUNITY_URL = (
    "https://app.gohighlevel.com/v2/location/{location_id}/opportunities/list/{opp_id}?tab=OpportunityDetails"
)
CONTACT_URL = "https://app.gohighlevel.com/v2/location/{location_id}/contacts/detail/{contact_id}"


def row(**overrides):
    base = {
        "project_id": "p1",
        "display_name": "Sample Job",
        "pm_bucket": "Site Review",
        "section": "onboarding",
        "assigned_rep": "Alex Rivera",
        "address": "1 Main St",
        "created_at_iso": "2026-08-15T12:00:00Z",
        "created_at_display": "2026-08-15",
        "days_in_bucket": 3,
        "is_over_sla": False,
        "install_cycle_days": "",
        "permit_phone": "",
        "permit_email": "",
        "cancel_source_stage": "",
        "board_url": "https://enerflo.example/installs/1",
    }
    base.update(overrides)
    return base


SNAPSHOT = """
const rows = [{"project_id":"1","display_name":"A","pm_bucket":"Project Verification","section":"onboarding","assigned_rep":"Alex","created_at_iso":"2026-03-02T00:00:00Z","is_over_sla":false,"install_cycle_days":"10","permit_phone":"5550100000","ghl":{"locationId":"loc-1","opportunityId":"opp-1"}},{"project_id":"2","display_name":"B","pm_bucket":"Cancelled","section":"hold_cancel","assigned_rep":"Pat","created_at_iso":"2026-03-18T00:00:00Z","is_over_sla":true,"install_cycle_days":"","permit_phone":"5550100002","contactId":"contact-2"},{"project_id":"3","display_name":"C","pm_bucket":"ENG/FIN/PERM","section":"ep_ops","assigned_rep":"Alex","created_at_iso":"2026-04-01T00:00:00Z","is_over_sla":false,"install_cycle_days":"30"}];
const stageCards = [{"stage":"Project Verification","section":"onboarding","display_label":"Project Verification","sla_days":null},{"stage":"ENG/FIN/PERM","section":"ep_ops","display_label":"ENG/FIN/PERM","sla_days":null},{"stage":"Cancelled","section":"hold_cancel","display_label":"Cancelled","sla_days":null}];
const generatedAt = "2026-10-16 03:59 PM AZ";
"""


class SnapshotAndLinksTests(unittest.TestCase):
    def test_parse_snapshot_without_embedding_customer_text_in_errors(self):
        parsed = pm.parse_hub_snapshot(SNAPSHOT)
        self.assertEqual(len(parsed["rows"]), 3)
        self.assertEqual(parsed["generated_at"], "2026-10-16 03:59 PM AZ")
        self.assertEqual(parsed["stage_cards"][0]["stage"], "Project Verification")
        with self.assertRaises(ValueError) as raised:
            pm.parse_hub_snapshot("const rows = not-json 5550109999")
        self.assertEqual(str(raised.exception), "Project management snapshot could not be read")
        self.assertNotIn("555", str(raised.exception))

    def test_opportunity_url_matches_repo_format_and_falls_back(self):
        self.assertEqual(
            pm.GHL_OPPORTUNITY_URL,
            OPPORTUNITY_URL,
        )
        linked = pm.attach_ghl_links(
            {"opportunityId": "opp-9", "locationId": "loc-9", "contactId": "contact-9", "permit_phone": "5550100001"}
        )
        self.assertEqual(
            linked["ghlOpportunityUrl"],
            OPPORTUNITY_URL.format(location_id="loc-9", opp_id="opp-9"),
        )
        self.assertEqual(linked["phoneHref"], linked["ghlOpportunityUrl"])
        self.assertEqual(linked["ghlContactUrl"], "")
        self.assertNotIn("555", linked["ghlOpportunityUrl"])

        contact_only = pm.attach_ghl_links(
            {"contact_id": "contact-2"},
            default_location="loc-default",
        )
        self.assertEqual(contact_only["ghlOpportunityUrl"], "")
        self.assertEqual(
            contact_only["phoneHref"],
            CONTACT_URL.format(location_id="loc-default", contact_id="contact-2"),
        )

        nested = pm.attach_ghl_links({"ghl": {"locationId": "loc-n", "opportunityId": "opp-n"}})
        self.assertEqual(
            nested["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-n", opp_id="opp-n"),
        )

        plain = pm.attach_ghl_links({"display_name": "No ids", "permit_phone": "5550100003"})
        self.assertEqual(plain["phoneHref"], "")
        self.assertEqual(plain["ghlOpportunityUrl"], "")
        self.assertEqual(plain["ghlContactUrl"], "")

        bad_opp = pm.attach_ghl_links(
            {"opportunityId": "not an id", "contactId": "contact-ok", "locationId": "loc-ok"}
        )
        self.assertEqual(bad_opp["ghlOpportunityUrl"], "")
        self.assertEqual(
            bad_opp["phoneHref"],
            CONTACT_URL.format(location_id="loc-ok", contact_id="contact-ok"),
        )

    def test_summary_keeps_active_held_and_median(self):
        rows = [
            row(section="onboarding", install_cycle_days="10"),
            row(project_id="2", section="ep_ops", install_cycle_days="30"),
            row(project_id="3", section="ep_installation", install_cycle_days=""),
            row(project_id="4", section="hold_cancel", pm_bucket="Cancelled", is_over_sla=True),
        ]
        summary = pm.summarize_rows(rows)
        self.assertEqual(summary["active_jobs"], 3)
        self.assertEqual(summary["held_jobs"], 1)
        self.assertEqual(summary["overdue_jobs"], 1)
        self.assertEqual(summary["median_install_days"], 20)
        self.assertEqual(summary["install_sample_size"], 2)

    def test_filters_and_hold_view(self):
        rows = [
            row(),
            row(project_id="2", display_name="Held", section="hold_cancel", pm_bucket="Cancelled", assigned_rep="Pat", created_at_iso="2026-03-04T00:00:00Z", cancel_source_stage="Site Review"),
            row(project_id="3", display_name="Other hold", section="hold_cancel", pm_bucket="HOLD", created_at_iso="2026-03-09T00:00:00Z"),
            row(project_id="4", section="ep_installation", pm_bucket="PTO", created_at_iso="2025-12-01T00:00:00Z"),
        ]
        march = pm.filter_hub_rows(rows, start="2026-03-01", end="2026-03-31")
        self.assertEqual({item["project_id"] for item in march}, {"2", "3"})
        overdue = pm.filter_hub_rows(rows, overdue_only=True)
        self.assertEqual(overdue, [])
        named = pm.filter_hub_rows(rows, search="Held", reps=["Pat"])
        self.assertEqual([item["project_id"] for item in named], ["2"])

        all_hold = pm.hold_cancel_view(rows)
        self.assertEqual(all_hold["month_label"], "All months")
        self.assertEqual([item["project_id"] for item in all_hold["listed"]], ["2", "3"])
        self.assertEqual(all_hold["cancelled_count"], 1)
        self.assertEqual(all_hold["created_count"], 2)

        month = pm.hold_cancel_view(rows, created_month="2026-03", reps=["Pat"])
        self.assertEqual(month["month_label"], "03/26")
        self.assertEqual([item["project_id"] for item in month["listed"]], ["2"])
        self.assertEqual(month["cancelled_count"], 1)
        self.assertEqual(month["created_count"], 1)
        self.assertEqual(month["start"], "2026-03-01")
        self.assertEqual(month["end"], "2026-03-31")

        ranged = pm.hold_cancel_view(rows, start="2026-03-01", end="2026-03-31")
        self.assertEqual({item["project_id"] for item in ranged["listed"]}, {"2", "3"})
        self.assertEqual(ranged["created_count"], 2)

    def test_cancellation_series_starts_in_2026(self):
        rows = [
            row(created_at_iso="2025-12-01T00:00:00Z", pm_bucket="Cancelled", section="hold_cancel"),
            row(project_id="2", created_at_iso="2026-01-15T00:00:00Z", pm_bucket="Cancelled", section="hold_cancel"),
            row(project_id="3", created_at_iso="2026-01-20T00:00:00Z", pm_bucket="Site Review"),
        ]
        series = pm.cancellation_series(rows, now=datetime(2026, 2, 2, tzinfo=timezone.utc))
        self.assertEqual([item["monthKey"] for item in series], ["2026-01", "2026-02"])
        self.assertEqual(series[0]["created"], 2)
        self.assertEqual(series[0]["cancelled"], 1)
        self.assertEqual(series[0]["rate"], 50)
        stages = pm.cancellation_stages(rows)
        self.assertEqual(stages[0]["stage"], "Unknown prior stage")


class PageShellTests(unittest.TestCase):
    def test_nav_keys_and_paths(self):
        groups = dict(nav.NAV_GROUPS)
        items = dict((key, href) for key, _title, href in groups["PROJECT MANAGEMENT"])
        self.assertEqual(items["project_management_hub"], "/api/project_management_hub")
        self.assertEqual(items["hold_cancelled"], "/api/hold_cancelled")

    def test_pages_are_iframe_safe_and_use_ops_shell(self):
        hub_html = pages.render_project_management_hub_html()
        hold_html = pages.render_hold_cancelled_html()
        for html in (hub_html, hold_html):
            self.assertIn('class="oc-root"', html)
            self.assertIn("data-oc-native-filters", html)
            self.assertIn("hsOpsPresetButtons", html)
            self.assertIn('data-preset="alltime"', html)
            self.assertIn("/api/metrics/project_management", html)
            self.assertNotIn("top.location", html)
            self.assertNotIn("parent.location", html)
            self.assertNotIn("X-Frame-Options", html)
            self.assertNotIn("happy-solar-monday-pm.vercel.app", html)
        self.assertIn('id="holdLink" href="/api/hold_cancelled"', hub_html)
        self.assertNotIn('id="holdLink" href="/api/hold_cancelled" target="_blank"', hub_html)
        self.assertIn('id="hubLink" href="/api/project_management_hub"', hold_html)
        self.assertNotIn('href="/api/project_management_hub" target="_blank"', hold_html)
        self.assertIn('target="_blank" rel="noopener"', hold_html)
        self.assertIn("opportunities\\/list\\/", hold_html)
        self.assertIn("tab=OpportunityDetails", hold_html)
        self.assertIn("ghlContactUrl", hold_html)

    def test_handlers_allow_bloom_framing(self):
        for page in (hub_page, hold_page):
            inst = page.handler.__new__(page.handler)
            inst.wfile = io.BytesIO()
            sent = {}

            def send_header(key, value, sent=sent):
                sent.setdefault("headers", []).append((key, value))

            inst.send_response = lambda status, sent=sent: sent.setdefault("status", status)
            inst.send_header = send_header
            inst.end_headers = lambda: None
            inst.do_GET()
            headers = dict(sent["headers"])
            self.assertEqual(sent["status"], 200)
            self.assertNotIn("X-Frame-Options", headers)
            policy = headers["Content-Security-Policy"]
            self.assertIn("frame-ancestors", policy)
            self.assertIn("https://bloom.happyslr.com", policy)
            self.assertNotIn("DENY", policy)
            body = inst.wfile.getvalue().decode()
            self.assertIn("oc-root", body)

    def test_metrics_handler_does_not_echo_failures(self):
        original = pm.load_project_management

        def explode(**_kwargs):
            raise RuntimeError("5550100000 should stay out of the response")

        pm.load_project_management = explode
        try:
            inst = pm.handler.__new__(pm.handler)
            inst.path = "/api/metrics/project_management"
            inst.wfile = io.BytesIO()
            inst.send_response = lambda status: setattr(inst, "status", status)
            inst.send_header = lambda *_args: None
            inst.end_headers = lambda: None
            inst.do_GET()
        finally:
            pm.load_project_management = original
        self.assertEqual(inst.status, 502)
        raw = inst.wfile.getvalue().decode()
        self.assertNotIn("555", raw)
        self.assertEqual(json.loads(raw)["error"], "Project management data is unavailable")

    def test_hold_view_endpoint_uses_phone_href(self):
        payload = pm.build_payload(pm.parse_hub_snapshot(SNAPSHOT), default_location="loc-default")
        first = payload["rows"][0]
        self.assertEqual(
            first["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-1", opp_id="opp-1"),
        )
        second = payload["rows"][1]
        self.assertEqual(
            second["phoneHref"],
            CONTACT_URL.format(location_id="loc-default", contact_id="contact-2"),
        )
        third = payload["rows"][2]
        self.assertEqual(third["phoneHref"], "")
        self.assertEqual(payload["summary"]["active_jobs"], 2)
        self.assertEqual(payload["summary"]["held_jobs"], 1)
        self.assertEqual(payload["summary"]["median_install_days"], 20)


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.field = None
        self.values = None

    def where(self, field, op, values):
        if op != "in":
            raise AssertionError(op)
        query = _Query(self.db, self.name)
        query.field = field
        query.values = list(values)
        return query

    def select(self, _fields):
        return self

    def stream(self):
        self.db.streams.append((self.name, self.field, len(self.values or [])))
        docs = self.db.docs.get(self.name) or []
        if self.field is None:
            return list(docs)
        wanted = set(self.values or [])
        return [snap for snap in docs if snap.to_dict().get(self.field) in wanted]


class _DB:
    def __init__(self, docs):
        self.docs = docs
        self.streams = []

    def collection(self, name):
        return _Query(self, name)


class GhlIndexTests(unittest.TestCase):
    def test_phone_then_email_then_name_and_stage_preference(self):
        sold = "7981f111-73f2-4593-9662-6b95d99bf51a"
        contacts = [
            {
                "id": "contact-phone",
                "phone": "+15550100001",
                "email": "phone@example.com",
                "firstName": "Ada",
                "lastName": "Sample",
                "locationId": "loc-phone",
            },
            {
                "id": "contact-email",
                "phone": "+15550100002",
                "email": "email@example.com",
                "firstName": "Bea",
                "lastName": "Sample",
                "locationId": "loc-email",
            },
            {
                "id": "contact-name",
                "email": "name@example.com",
                "contactName": "Cy Sample",
                "locationId": "loc-name",
            },
        ]
        opportunities = [
            {
                "id": "opp-new",
                "contactId": "contact-phone",
                "locationId": "loc-phone",
                "pipelineStageName": "New Appointment",
                "updatedAt": "2026-10-01T00:00:00Z",
            },
            {
                "id": "opp-sold",
                "contactId": "contact-phone",
                "locationId": "loc-phone",
                "pipelineStageId": sold,
                "updatedAt": "2026-01-01T00:00:00Z",
            },
            {
                "id": "opp-email",
                "contactId": "contact-email",
                "locationId": "loc-email",
                "pipelineStageName": "Install",
                "updatedAt": "2026-05-01T00:00:00Z",
            },
            {
                "id": "opp-name",
                "contactId": "contact-name",
                "locationId": "loc-name",
                "pipelineStageName": "Project",
                "updatedAt": "2026-04-01T00:00:00Z",
            },
        ]
        index = pm.build_ghl_link_index(contacts, opportunities, sold_ids={sold})

        phone_row = pm.apply_ghl_index(
            {"permit_phone": "1 (555) 010-0001", "permit_email": "email@example.com", "display_name": "Sample, Cy"},
            index,
        )
        self.assertEqual(
            phone_row["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-phone", opp_id="opp-sold"),
        )
        self.assertNotIn("555", phone_row["phoneHref"])

        newer_sold = pm.build_ghl_link_index(
            contacts[:1],
            [
                opportunities[1],
                {
                    "id": "opp-sold-new",
                    "contactId": "contact-phone",
                    "locationId": "loc-phone",
                    "pipelineStageName": "Sold",
                    "updatedAt": "2026-08-01T00:00:00Z",
                },
            ],
            sold_ids={sold},
        )
        preferred = pm.apply_ghl_index({"permit_phone": "5550100001"}, newer_sold)
        self.assertTrue(preferred["phoneHref"].endswith("opp-sold-new?tab=OpportunityDetails"))

        email_row = pm.apply_ghl_index(
            {"permit_phone": "5550100099", "permit_email": "Email@Example.com", "display_name": "Sample, Cy"},
            index,
        )
        self.assertEqual(
            email_row["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-email", opp_id="opp-email"),
        )

        name_row = pm.apply_ghl_index({"display_name": "Sample, Cy", "section": "hold_cancel"}, index)
        self.assertEqual(
            name_row["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-name", opp_id="opp-name"),
        )

        contact_only = pm.build_ghl_link_index(contacts[:1], [], sold_ids=set())
        linked = pm.apply_ghl_index({"permit_phone": "+1-555-010-0001"}, contact_only, default_location="loc-default")
        self.assertEqual(
            linked["phoneHref"],
            CONTACT_URL.format(location_id="loc-phone", contact_id="contact-phone"),
        )

        plain = pm.apply_ghl_index(
            {"display_name": "Nobody Here", "permit_phone": "5550100088", "phoneHref": ""},
            index,
        )
        self.assertEqual(plain["phoneHref"], "")

        kept = pm.build_payload(
            {"rows": [{"opportunityId": "opp-keep", "locationId": "loc-keep", "permit_phone": "5550100001", "section": "hold_cancel"}]},
            ghl_index=index,
        )
        self.assertEqual(
            kept["rows"][0]["phoneHref"],
            OPPORTUNITY_URL.format(location_id="loc-keep", opp_id="opp-keep"),
        )
        self.assertEqual(kept["hold_ghl_links"]["opportunity"], 1)
        self.assertEqual(kept["hold_ghl_links"]["plain"], 0)

    def test_queries_are_batched_and_skip_name_after_a_phone_hit(self):
        contacts = []
        rows = []
        for number in range(31):
            key = f"555010{number:04d}"
            contact_id = f"contact-{number}"
            contacts.append(_Snap(contact_id, {"id": contact_id, "phone": f"+1{key}", "locationId": "loc-batch"}))
            rows.append({"permit_phone": key, "display_name": f"Person, Number{number}", "section": "hold_cancel"})
        rows.append({"display_name": "Sample, Only", "section": "hold_cancel", "permit_email": ""})
        contacts.append(
            _Snap("contact-name", {"id": "contact-name", "contactName": "Only Sample", "lastName": "Sample", "locationId": "loc-name"})
        )
        db = _DB({pm.CONTACT_COLLECTION: contacts, pm.OPP_COLLECTION: [], pm.PIPELINE_COLLECTION: []})
        index = pm.query_ghl_link_index(db, rows)
        phone_streams = [call for call in db.streams if call[0] == pm.CONTACT_COLLECTION and call[1] == "phone"]
        self.assertEqual(len(phone_streams), 4)
        self.assertTrue(all(size <= 30 for _name, _field, size in phone_streams))
        self.assertEqual(sum(size for _name, _field, size in phone_streams), 31 * 3)
        self.assertEqual(
            [call[1] for call in db.streams if call[0] == pm.CONTACT_COLLECTION and call[1] in {"contactName", "lastName"}],
            ["contactName", "lastName"],
        )
        opp_streams = [call for call in db.streams if call[0] == pm.OPP_COLLECTION and call[1] == "contactId"]
        self.assertEqual(len(opp_streams), 2)
        self.assertLess(len(db.streams), 20)
        linked = pm.apply_ghl_index(rows[0], index, default_location="loc-default")
        self.assertIn("/contacts/detail/contact-0", linked["phoneHref"])
        named = pm.apply_ghl_index(rows[-1], index)
        self.assertIn("/contacts/detail/contact-name", named["phoneHref"])

    def test_index_failure_leaves_the_snapshot_response_generic(self):
        class Boom:
            def collection(self, _name):
                raise RuntimeError("555019999 lookup failed")

        payload = pm.load_project_management(fetch=lambda: SNAPSHOT, db=Boom(), now=10)
        self.assertTrue(payload["ok"])
        self.assertNotIn("lookup failed", json.dumps(payload["hold_ghl_links"]))
        self.assertEqual(payload["rows"][2]["phoneHref"], "")

    def test_cached_index_is_reused(self):
        pm.clear_snapshot_cache()
        rows = [{"permit_phone": "5550100001", "display_name": "Sample, Ada"}]
        cached = {"by_phone": {}, "by_email": {}, "by_name": {}, "contacts": {}, "opps_by_contact": {}}
        pm._GHL_CACHE["index"] = cached
        pm._GHL_CACHE["key"] = pm._lookup_signature(rows)
        pm._GHL_CACHE["at"] = 1000
        self.assertIs(pm.load_ghl_link_index(rows, now=1200), cached)
        pm.clear_snapshot_cache()
