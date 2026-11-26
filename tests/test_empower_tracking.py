# -*- coding: utf-8 -*-

"""EmPower+ link layer, shadow sync, and alerts. Synthetic fixtures only.

Funnel-count exclusion of pipeline 5hPKCGzAskcC6LEZuc1H is a separate change.
These tests prove this tracking path does not write the collections those
metrics read, and that auto-create stays off unless the env flag is true.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import sys
import unittest
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from metrics.empower_alerts import (  # noqa: E402
    alert_doc_id,
    apply_alerts,
    build_digest_messages,
    deliver_digest,
    evaluate_jobs,
)
from metrics.empower_ghl_events import diff_ghl_stage_events, event_doc_id, open_map_from_docs  # noqa: E402
import empower_ghl_sync  # noqa: E402

auto_create_enabled = empower_ghl_sync.auto_create_enabled
run_shadow_sync = empower_ghl_sync.run_shadow_sync
from metrics.empower_ids import (  # noqa: E402
    EMPOWER_PIPELINE_ID,
    FIELD_ENROLLMENT_ID,
    FIELD_PROGRAM,
    FIELD_TRADE_ALLY,
    FUNNEL_COLLECTIONS,
    GHL_STAGE_ID_BY_NAME,
)
from metrics.empower_linker import (  # noqa: E402
    build_link_health,
    guarded_set,
    match_job,
)
from metrics.empower_portal_metrics import contains_forbidden_keys, strip_portal_fields  # noqa: E402
from copilot.auth import sign_bloom_token  # noqa: E402


PHOENIX = ZoneInfo("America/Phoenix")
BUFFALO = "GQtUlcTmLJ61HZjrGEPC"
BLOOM_SECRET = "bloom-test-secret"
SETTINGS_PASSWORD = "settings-test-password"


def load_handler(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def invoke(module, method: str, path: str, headers=None, body: bytes = b""):
    cls = module.handler
    inst = cls.__new__(cls)
    inst.path = path
    inst.headers = headers or {}
    inst.rfile = BytesIO(body)
    inst.wfile = BytesIO()
    captured = {}

    def send_header(key, value, captured=captured):
        captured.setdefault("headers", {})[key] = value

    inst.send_response = lambda status, captured=captured: captured.__setitem__("status", status)
    inst.send_header = send_header
    inst.end_headers = lambda: None
    getattr(inst, f"do_{method}")()
    return captured["status"], captured.get("headers", {}), inst.wfile.getvalue()


def bloom_headers(role: str) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    token = sign_bloom_token(
        {
            "aud": "goose-copilot",
            "exp": now + 300,
            "iat": now - 10,
            "iss": "happy-solar-bloom",
            "role": role,
            "status": "active",
            "sub": "user_test",
            "v": 1,
        },
        BLOOM_SECRET,
    )
    return {"Authorization": f"Bearer {token}"}


def basic_headers() -> dict:
    token = base64.b64encode(f"qa:{SETTINGS_PASSWORD}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


class FakeDb:
    def __init__(self):
        self.docs = {}
        self.writes = []

    def collection(self, name):
        return _FakeCollection(self, name)


class _FakeCollection:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def document(self, doc_id):
        return _FakeDoc(self.db, self.name, doc_id)

    def where(self, field, op, value):
        return _FakeQuery(self.db, self.name, [(field, op, value)])


class _FakeQuery:
    def __init__(self, db, name, filters):
        self.db = db
        self.name = name
        self.filters = filters

    def order_by(self, field, direction=None):
        return self

    def stream(self):
        rows = []
        for (collection, doc_id), data in self.db.docs.items():
            if collection != self.name or not isinstance(data, dict):
                continue
            if all(_match(data.get(field), op, value) for field, op, value in self.filters):
                rows.append(_FakeSnap(data, doc_id))
        return rows


def _match(stored, op, value):
    if op == "==":
        return stored == value
    if op == ">=":
        return stored is not None and stored >= value
    return False


class _FakeDoc:
    def __init__(self, db, collection, doc_id):
        self.db = db
        self.id = doc_id
        self.key = (collection, doc_id)

    def get(self):
        return _FakeSnap(self.db.docs.get(self.key), self.id)

    def set(self, payload, merge=False):
        self.db.writes.append({"key": self.key, "merge": merge})
        self.db.docs[self.key] = json.loads(json.dumps(payload))


class _FakeSnap:
    def __init__(self, data, doc_id=None):
        self.exists = data is not None
        self.id = doc_id
        self._data = data

    def to_dict(self):
        if not isinstance(self._data, dict):
            return {}
        return json.loads(json.dumps(self._data))


def _opp(opp_id, pipeline, contact_id, **extra):
    row = {
        "id": opp_id,
        "pipelineId": pipeline,
        "contactId": contact_id,
        "status": "open",
        "pipelineStageId": GHL_STAGE_ID_BY_NAME["Audit Confirmed"],
        "customFields": [],
        "pipeline_name": "Empower+" if pipeline == EMPOWER_PIPELINE_ID else "Buffalo",
    }
    row.update(extra)
    return row


def _contact(contact_id, **extra):
    row = {"id": contact_id}
    row.update(extra)
    return row


class MatcherTests(unittest.TestCase):
    def _world(self):
        contacts = {
            "c-id": _contact("c-id"),
            "c-phone": _contact("c-phone", phone="(555) 111-2222"),
            "c-mail": _contact("c-mail", email="pat.sample@example.com"),
            "c-addr": _contact("c-addr", address1="10 Oak Street", postalCode="14201-0000"),
            "c-name": _contact("c-name", firstName="Quinn", lastName="Audit"),
            "c-buf": _contact("c-buf", phone="5553334444"),
        }
        opps = [
            _opp(
                "opp-id",
                EMPOWER_PIPELINE_ID,
                "c-id",
                customFields=[{"id": FIELD_ENROLLMENT_ID, "value": "E-ALL"}],
            ),
            _opp("opp-line", EMPOWER_PIPELINE_ID, "c-phone"),
            _opp("opp-note", EMPOWER_PIPELINE_ID, "c-mail"),
            _opp("opp-addr", EMPOWER_PIPELINE_ID, "c-addr"),
            _opp("opp-name", EMPOWER_PIPELINE_ID, "c-name"),
            _opp("opp-buf", BUFFALO, "c-buf", pipeline_name="Buffalo"),
        ]
        return opps, contacts

    def test_match_priority_and_portal_fields_stay_clean(self):
        opps, contacts = self._world()
        project = {
            "id": "E-ALL",
            "customer": "Audit, Quinn",
            "status": "Open",
            "step": "Workscope Review",
        }
        match = {
            "id": "E-ALL",
            "phone": "5551112222",
            "email": "PAT.SAMPLE@example.com",
            "street": "10 Oak Ave",
            "zip": "14201",
        }
        winner = match_job(project, match, opps, contacts)
        self.assertEqual(winner["method"], "id")
        self.assertEqual(winner["opp_id"], "opp-id")
        self.assertEqual(winner["confidence"], "exact")
        self.assertEqual(winner["status"], "linked")
        self.assertNotIn("phone", winner)
        self.assertNotIn("email", winner)

        phone = match_job(
            {"id": "E-PHONE", "customer": "Nia Sample", "status": "Open"},
            {"phone": "1-555-111-2222"},
            opps,
            contacts,
        )
        self.assertEqual((phone["method"], phone["opp_id"], phone["confidence"], phone["status"]), ("phone", "opp-line", "exact", "linked"))
        self.assertTrue(phone["phone_sha256"])
        self.assertNotIn("5551112222", json.dumps(phone))

        mail = match_job(
            {"id": "E-MAIL", "customer": "Nia Sample", "status": "Open"},
            {"email": "pat.sample@example.com"},
            opps,
            contacts,
        )
        self.assertEqual(mail["method"], "email")
        self.assertEqual(mail["opp_id"], "opp-note")
        self.assertEqual(mail["status"], "linked")

        address = match_job(
            {"id": "E-ADDR", "customer": "Someone Else", "status": "Open"},
            {"street": "10 Oak Ave", "zip": "14201"},
            opps,
            contacts,
        )
        self.assertEqual(address["method"], "address")
        self.assertEqual(address["confidence"], "suggested")
        self.assertEqual(address["status"], "needs_confirmation")
        self.assertIsNone(address["opp_id"])
        self.assertEqual(address["suggested_opp_id"], "opp-addr")

        named = match_job(
            {"id": "E-NAME", "customer": "Audit, Quinn", "status": "Open"},
            {},
            opps,
            contacts,
        )
        self.assertEqual(named["method"], "name")
        self.assertEqual(named["confidence"], "suggested")
        self.assertIsNone(named["opp_id"])
        self.assertEqual(named["suggested_opp_id"], "opp-name")

        other = match_job(
            {"id": "E-BUF", "customer": "Nia Sample", "status": "Open"},
            {"phone": "555-333-4444"},
            opps,
            contacts,
        )
        self.assertTrue(other["other_pipeline"])
        self.assertEqual(other["confidence"], "exact")
        self.assertEqual(other["status"], "linked")
        self.assertEqual(other["pipeline_name"], "Buffalo")

        dirty = {
            "id": "E-CLEAN",
            "customer": "Nia Sample",
            "phone": "555-0100",
            "email": "a@example.com",
            "address": "1 Main",
            "contact": "hidden",
        }
        cleaned = strip_portal_fields({"projects": [dirty], "changes": [], "history": []})
        self.assertFalse(contains_forbidden_keys(cleaned["projects"]))
        self.assertFalse(contains_forbidden_keys(cleaned))
        encoded = json.dumps(cleaned).lower()
        self.assertNotIn("phone", encoded)
        self.assertNotIn("email", encoded)
        self.assertNotIn("address", encoded)

        payload = {
            "snapshot": "2026-11-17_pm",
            "checkedAt": "check",
            "projects": [{"id": "E-CLEAN", "customer": "Nia Sample", "status": "Open", "step": "Workscope Review"}],
            "changes": [],
            "history": [],
            "matches": [{"id": "E-CLEAN", "phone": "5551112222", "email": "a@example.com", "street": "10 Oak", "zip": "14201"}],
        }
        stored = portal_metrics_validate(payload)
        self.assertNotIn("matches", stored)
        self.assertFalse(contains_forbidden_keys(stored["projects"]))
        self.assertFalse(contains_forbidden_keys(stored["changes"]))

        health = build_link_health(
            [{"id": "E-BUF", "customer": "Nia Sample", "status": "Open", "step": "Workscope Review", "city": "Buffalo"}],
            [other],
            opps,
            as_of=date(2026, 11, 17),
            today=date(2026, 11, 18),
        )
        public = json.dumps(health).lower()
        self.assertNotIn("phone", public)
        self.assertNotIn("email", public)
        self.assertEqual(health["otherPipeline"][0]["pipelineName"], "Buffalo")
        self.assertEqual(health["suggested"], [])


def portal_metrics_validate(payload):
    from empower_portal_ingest import validate_payload

    return validate_payload(payload)


class LinkEndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.module = load_handler("hs_empower_portal_link_test", API / "empower_portal_link.py")
        self.env = patch.dict(
            os.environ,
            {"COPILOT_BLOOM_TOKEN_SECRET": BLOOM_SECRET, "SETTINGS_PASSWORD": SETTINGS_PASSWORD},
        )

    def _post(self, headers, body):
        raw = json.dumps(body).encode("utf-8")
        sent = dict(headers)
        sent["Content-Length"] = str(len(raw))
        with self.env:
            with patch("empower_portal_ingest.get_db", return_value=self.db):
                return invoke(self.module, "POST", "/api/empower_portal_link", sent, raw)

    def test_confirm_reject_and_role_gate(self):
        self.db.docs[("empower_links", "E-1")] = {
            "enrollment_id": "E-1",
            "suggested_opp_id": "opp-addr",
            "status": "needs_confirmation",
            "confidence": "suggested",
            "method": "address",
        }
        status, _, raw = self._post(bloom_headers("closer"), {"action": "confirm", "enrollmentId": "E-1", "oppId": "opp-addr"})
        self.assertEqual(status, 401)
        self.assertEqual(self.db.writes, [])

        status, _, raw = self._post(bloom_headers("manager"), {"action": "confirm", "enrollmentId": "E-1", "oppId": "opp-addr"})
        self.assertEqual(status, 200, raw)
        saved = self.db.docs[("empower_links", "E-1")]
        self.assertEqual(saved["confidence"], "confirmed")
        self.assertEqual(saved["status"], "linked")
        self.assertEqual(saved["confirmed_by"], "bloom:user_test")
        self.assertTrue(saved["confirmed_at"])

        self.db.docs[("empower_links", "E-2")] = {
            "enrollment_id": "E-2",
            "suggested_opp_id": "opp-addr",
            "status": "needs_confirmation",
            "confidence": "suggested",
            "method": "address",
        }
        status, _, raw = self._post(bloom_headers("coach"), {"action": "reject", "enrollmentId": "E-2"})
        self.assertEqual(status, 200, raw)
        saved = self.db.docs[("empower_links", "E-2")]
        self.assertEqual(saved["confidence"], "rejected")
        self.assertIsNone(saved["suggested_opp_id"])
        self.assertIn("opp-addr", saved["rejected_opp_ids"])

        status, _, raw = self._post(basic_headers(), {"action": "manual_link", "enrollmentId": "E-9", "oppId": "opp-manual"})
        self.assertEqual(status, 200, raw)
        saved = self.db.docs[("empower_links", "E-9")]
        self.assertEqual(saved["opp_id"], "opp-manual")
        self.assertEqual(saved["method"], "manual")
        self.assertEqual(saved["confidence"], "confirmed")
        self.assertEqual(saved["confirmed_by"], "settings_admin")


class ShadowSyncTests(unittest.TestCase):
    def test_field_diff_is_idempotent_and_never_moves_stage(self):
        os.environ.pop("EMPOWER_AUTO_CREATE_OPPS", None)
        self.assertFalse(auto_create_enabled())
        project = {
            "id": "E-SYNC",
            "customer": "Nia Sample",
            "status": "Open",
            "step": "Assessment Review",
            "stepStatus": "Waiting",
            "onTodo": False,
            "due": "12/1/2026",
            "tier": "EmPower+ - Low Income",
            "installer": "Happy Home",
            "program": "EmPower+",
        }
        orphan = {
            "id": "E-NEW",
            "customer": "Remy Review",
            "status": "Open",
            "step": "Contractor Assignment",
        }
        opp = _opp("opp-sync", EMPOWER_PIPELINE_ID, "c-sync", customFields=[])
        link = {
            "enrollment_id": "E-SYNC",
            "opp_id": "opp-sync",
            "pipeline_id": EMPOWER_PIPELINE_ID,
            "status": "linked",
            "confidence": "exact",
            "method": "id",
            "other_pipeline": False,
        }
        event = {
            "enrollment_id": "E-SYNC",
            "stage": "Assessment Review",
            "ended_at": None,
            "first_seen_at": "2026-11-20T09:00:00-07:00",
            "on_todo": False,
            "enrollment_status": "Open",
        }
        now = datetime(2026, 11, 25, 9, 0, tzinfo=PHOENIX)
        writes = []

        def client(method, path, body):
            writes.append((method, path, body))
            if method == "PUT":
                opp["customFields"] = body["customFields"]
            if method == "POST":
                raise AssertionError(path)
            return {"ok": True}

        db = FakeDb()
        first = run_shadow_sync(
            [project, orphan],
            [opp],
            links=[link],
            nyhep_events=[event],
            existing_links={"E-SYNC": link},
            now=now,
            dry_run=False,
            client=client,
            db=db,
            as_of=date(2026, 11, 25),
        )
        self.assertEqual(len(first["puts"]), 1)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][0], "PUT")
        body = writes[0][2]
        self.assertEqual(set(body), {"customFields"})
        encoded = json.dumps(body)
        self.assertNotIn("pipelineStageId", encoded)
        sent = {row["id"]: row["field_value"] for row in body["customFields"]}
        self.assertEqual(sent[FIELD_ENROLLMENT_ID], "E-SYNC")
        self.assertEqual(sent[FIELD_PROGRAM], "EmPower+")
        self.assertEqual(sent[FIELD_TRADE_ALLY], "A Happy Day LLC")
        self.assertEqual(first["autoCreates"], [])
        self.assertIn("E-NEW", {row["enrollmentId"] for row in first["skippedAutoCreates"]})
        collections = {key[0] for key in db.docs}
        self.assertTrue(collections)
        self.assertTrue(collections.isdisjoint(FUNNEL_COLLECTIONS))

        second = run_shadow_sync(
            [project, orphan],
            [opp],
            links=[link],
            nyhep_events=[event],
            existing_links={"E-SYNC": link, "E-NEW": {"enrollment_id": "E-NEW", "status": "unmatched_nyhep"}},
            now=now,
            dry_run=False,
            client=client,
            db=FakeDb(),
            as_of=date(2026, 11, 25),
        )
        self.assertEqual(second["puts"], [])
        self.assertEqual(len(writes), 1)
        self.assertEqual([item[0] for item in writes], ["PUT"])

        with self.assertRaises(RuntimeError):
            guarded_set(FakeDb(), "ghl_opportunities_v2", "opp-sync", {"id": "opp-sync"})


class StageEventTests(unittest.TestCase):
    def test_open_close_and_stable_doc_id(self):
        stage_a = GHL_STAGE_ID_BY_NAME["Audit Confirmed"]
        stage_b = GHL_STAGE_ID_BY_NAME["Awaiting Results"]
        now = "2026-11-25T09:00:00-07:00"
        opp = _opp("opp-1", EMPOWER_PIPELINE_ID, "c-1", pipelineStageId=stage_a, assignedTo="owner-1")
        first = diff_ghl_stage_events({}, [opp], {"opp-1": "E-1"}, now_iso=now)
        self.assertEqual(len(first), 1)
        doc_id, body = first[0]
        self.assertEqual(doc_id, event_doc_id("opp-1", stage_a, now))
        self.assertEqual(doc_id, hashlib.sha1(f"opp-1|{stage_a}|{now}".encode("utf-8")).hexdigest()[:20])
        self.assertFalse(body["first_seen_is_start"])
        self.assertIsNone(body["ended_at"])
        self.assertEqual(body["enrollment_id"], "E-1")
        self.assertEqual(body["source"], "sync")

        again = diff_ghl_stage_events(open_map_from_docs(first), [opp], {"opp-1": "E-1"}, now_iso=now)
        self.assertEqual(again, [])

        later = "2026-11-26T09:00:00-07:00"
        moved = dict(opp)
        moved["pipelineStageId"] = stage_b
        changed = diff_ghl_stage_events(open_map_from_docs(first), [moved], {"opp-1": "E-1"}, now_iso=later)
        ended = [row for row in changed if row[1].get("ended_at")]
        opened = [row for row in changed if row[1].get("ended_at") is None]
        self.assertEqual(len(ended), 1)
        self.assertEqual(len(opened), 1)
        self.assertEqual(ended[0][0], doc_id)
        self.assertTrue(opened[0][1]["first_seen_is_start"])
        self.assertEqual(opened[0][0], event_doc_id("opp-1", stage_b, later))


class AlertTests(unittest.TestCase):
    def _jobs(self):
        projects = [
            {
                "id": "E-AUDIT",
                "customer": "Quinn Audit",
                "status": "Open",
                "step": "Workscope Submission",
                "stepStatus": "New",
                "onTodo": True,
                "due": "11/20/2026",
                "auditDate": "12/2/2026",
            },
            {
                "id": "E-REVIEW",
                "customer": "Remy Review",
                "status": "Open",
                "step": "Workscope Review",
                "onTodo": False,
            },
            {
                "id": "E-ASSIGN",
                "customer": "Casey Assign",
                "status": "Open",
                "step": "Contractor Assignment",
                "onTodo": False,
            },
            {
                "id": "E-SCOPE",
                "customer": "Wynn Scope",
                "status": "Open",
                "step": "Workscope Submission",
                "stepStatus": "Submitted",
                "onTodo": True,
                "enrolled": "9/1/2026",
            },
            {
                "id": "E-FPS",
                "customer": "Finn Submit",
                "status": "Open",
                "step": "Final Project Submission",
                "stepStatus": "Unscheduled",
                "onTodo": True,
                "enrolled": "8/1/2026",
            },
        ]
        events = [
            {"enrollment_id": "E-REVIEW", "ended_at": None, "first_seen_at": "2026-11-02T09:00:00-07:00", "stage": "Workscope Review"},
            {"enrollment_id": "E-ASSIGN", "ended_at": None, "first_seen_at": "2026-10-01T09:00:00-07:00", "stage": "Contractor Assignment"},
        ]
        return projects, events

    def test_stall_rules_dedup_and_resolution(self):
        projects, events = self._jobs()
        audit = evaluate_jobs([projects[0]], [], [], [], [], date(2026, 11, 18))
        self.assertEqual([row["rule_id"] for row in audit], ["audit_after_due"])
        self.assertEqual(audit[0]["owner_role"], "steven")
        self.assertEqual(audit[0]["severity"], "red")
        self.assertIn("text", audit[0]["channels"])

        review = evaluate_jobs([projects[1]], [], [], [events[0]], [], date(2026, 11, 10))
        self.assertEqual(review[0]["rule_id"], "workscope_review")
        self.assertGreater(review[0]["summary"].find("5"), -1)

        assign = evaluate_jobs([projects[2]], [], [], [events[1]], [], date(2026, 10, 16))
        self.assertEqual(assign[0]["rule_id"], "contractor_assignment")

        scope = evaluate_jobs([projects[3]], [], [], [], [], date(2026, 10, 2))
        self.assertEqual(scope[0]["rule_id"], "workscope_submitted")
        self.assertEqual(scope[0]["severity"], "red")

        final = evaluate_jobs([projects[4]], [], [], [], [], date(2026, 10, 16))
        self.assertEqual(final[0]["rule_id"], "install_scheduled")
        self.assertEqual(final[0]["severity"], "red")

        calls = []

        def creator(alert):
            calls.append(alert["rule_id"])
            return "task-1"

        open_alerts = {}
        changed = apply_alerts(open_alerts, scope, "2026-10-02T09:00:00-07:00", task_creator=creator, texts_on=False)
        self.assertEqual(calls, ["workscope_submitted"])
        doc_id, body = changed[0]
        self.assertEqual(doc_id, alert_doc_id("workscope_submitted", "E-SCOPE"))
        self.assertEqual(body["ghl_task_id"], "task-1")
        self.assertIsNone(body["resolved_at"])
        open_alerts = {doc_id: (doc_id, body)}
        apply_alerts(open_alerts, scope, "2026-10-03T09:00:00-07:00", task_creator=creator, texts_on=False)
        self.assertEqual(calls, ["workscope_submitted"])
        cleared = apply_alerts(open_alerts, [], "2026-10-04T09:00:00-07:00", task_creator=creator, texts_on=False)
        self.assertEqual(cleared[0][1]["resolved_at"], "2026-10-04T09:00:00-07:00")
        self.assertEqual(calls, ["workscope_submitted"])


class DigestTests(unittest.TestCase):
    def test_digest_filters_people_and_resend_payload(self):
        alerts = [
            {
                "rule_id": "audit_after_due",
                "severity": "red",
                "entity_key": "E-AUDIT",
                "customer": "Quinn Audit",
                "owner_role": "steven",
                "summary": "Booked audit date is after the NYHEP workscope due date",
                "resolved_at": None,
            },
            {
                "rule_id": "workscope_review",
                "severity": "warn",
                "entity_key": "E-REVIEW",
                "customer": "Remy Review",
                "owner_role": "brooke",
                "summary": "Workscope review is past 5 business days",
                "resolved_at": None,
            },
        ]
        recipients = {
            "steven": ["steven.synthetic@example.com"],
            "brooke": ["brooke.synthetic@example.com"],
            "tyler": ["tyler.synthetic@example.com"],
            "evan": ["evan.synthetic@example.com"],
            "adam": ["adam.synthetic@example.com"],
        }
        monday = date(2026, 11, 23)
        messages = build_digest_messages(
            alerts,
            as_of=monday,
            recipients=recipients,
            stage_counts={"Workscope Review": 2, "Payment": 1},
        )
        by_role = {row["role"]: row for row in messages}
        self.assertIn("Quinn Audit", by_role["steven"]["html"])
        self.assertNotIn("Remy Review", by_role["steven"]["html"])
        self.assertIn("Remy Review", by_role["brooke"]["html"])
        self.assertNotIn("Quinn Audit", by_role["brooke"]["html"])
        self.assertIn("Quinn Audit", by_role["tyler"]["html"])
        self.assertIn("Remy Review", by_role["evan"]["html"])
        self.assertIn("Workscope Review: 2", by_role["adam"]["html"])
        self.assertNotIn("Quinn Audit", by_role["adam"]["html"])
        tuesday = build_digest_messages(alerts, as_of=date(2026, 11, 24), recipients=recipients, stage_counts={"Payment": 1})
        self.assertNotIn("adam", {row["role"] for row in tuesday})

        sent = []

        def transport(payload):
            sent.append(payload)
            return {"id": "email_test"}

        dry = deliver_digest(alerts, as_of=monday, recipients=recipients, stage_counts={"Payment": 1}, dry_run=True, send=True)
        self.assertEqual(dry["sent"], 0)
        self.assertTrue(dry["payloads"])
        self.assertEqual(dry["payloads"][0]["to"], ["steven.synthetic@example.com"])
        self.assertIn("html", dry["payloads"][0])
        self.assertEqual(sent, [])

        with patch.dict(os.environ, {"EMPOWER_ALERTS_ENABLED": "true"}, clear=False):
            os.environ.pop("RESEND_API_KEY", None)
            missing = deliver_digest(
                alerts,
                as_of=monday,
                recipients=recipients,
                dry_run=False,
                send=True,
                transport=transport,
            )
        self.assertEqual(missing["error"], "missing_env")
        self.assertEqual(missing["missing"], ["RESEND_API_KEY"])
        self.assertEqual(sent, [])

        with patch.dict(os.environ, {"EMPOWER_ALERTS_ENABLED": "true", "RESEND_API_KEY": "test-key"}):
            sent_result = deliver_digest(
                alerts,
                as_of=date(2026, 11, 24),
                recipients=recipients,
                dry_run=False,
                send=True,
                transport=transport,
            )
        self.assertEqual(sent_result["sent"], 4)
        self.assertEqual(sent[0]["to"], ["steven.synthetic@example.com"])
        self.assertIn("subject", sent[0])
        self.assertIn("from", sent[0])
        self.assertNotIn("test-key", json.dumps(sent))


if __name__ == "__main__":
    unittest.main()
