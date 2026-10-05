# -*- coding: utf-8 -*-
"""GET/POST /api/copilot/admin — settings password, same gate as /api/settings."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from copilot.admin_actions import (
    approve_document,
    approve_term,
    deprecate_document,
    deprecate_term,
    save_definition,
    snapshot,
    suggest_term,
)
from copilot.auth import identity_from_headers
from copilot.config import config_from_env
from copilot.firestore_store import open_store
from copilot.launch import launch_checks
from copilot.store import LedgerUnavailable


def _unauthorized(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", 'Basic realm="Happy Solar Copilot Admin"')
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(b"Unauthorized")


HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Goose admin</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 24px; background: #f5f7fa; color: #111827; }
h1 { font-size: 22px; }
section { background: #fff; border: 1px solid #e8ecf0; border-radius: 12px; padding: 16px; margin: 12px 0; }
table { width: 100%; border-collapse: collapse; }
td, th { text-align: left; border-bottom: 1px solid #e8ecf0; padding: 6px; font-size: 13px; }
button { margin-right: 6px; }
</style></head>
<body>
<h1>Goose · Happy Solar Data Copilot</h1>
<p>Dictionary edits are revisions. Chat cannot approve them. The copilot stays off until launch checks pass.</p>
<section id="checks">Loading checks…</section>
<section id="ledger">Loading usage…</section>
<section>
  <h2>Terminology</h2>
  <p>Save draft writes a revision and leaves the term unapproved. Approve publishes the current text, including any unresolved ambiguities still in that revision.</p>
  <table id="terms"></table>
</section>
<section>
  <h2>Knowledge</h2>
  <table id="docs"></table>
</section>
<section>
  <h2>Pause</h2>
  <button id="pause" type="button">Pause copilot</button>
  <button id="resume" type="button">Clear pause flag</button>
  <p>Clearing the pause flag does not set COPILOT_ENABLED. The environment flag still defaults to false.</p>
</section>
<script>
async function api(action, extra) {
  const response = await fetch(location.pathname + location.search, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({action: action}, extra || {}))
  });
  return response.json();
}
function draw(data) {
  document.getElementById('checks').textContent = JSON.stringify(data.checks, null, 2);
  document.getElementById('ledger').textContent = JSON.stringify({ledger: data.ledger, ledger_error: data.ledger_error, paused: data.paused, enabled: data.enabled}, null, 2);
  const table = document.getElementById('terms');
  table.innerHTML = '<tr><th>Term</th><th>Status</th><th>Observed text</th><th></th></tr>';
  (data.terms || []).forEach(term => {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = term.display_name;
    const status = document.createElement('td');
    status.textContent = term.governance.status;
    const observed = document.createElement('td');
    observed.textContent = term.definition || term.observation || '';
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    edit.textContent = 'Save draft';
    edit.onclick = async () => {
      const text = window.prompt('Plain-language definition', term.definition || term.observation || '');
      if (!text) return;
      await api('save_definition', {term_id: term.term_id, definition: text});
      load();
    };
    const approve = document.createElement('button');
    approve.textContent = 'Approve';
    approve.onclick = async () => { await api('approve_term', {term_id: term.term_id}); load(); };
    const deprecate = document.createElement('button');
    deprecate.textContent = 'Deprecate';
    deprecate.onclick = async () => { await api('deprecate_term', {term_id: term.term_id}); load(); };
    actions.appendChild(edit);
    actions.appendChild(approve);
    actions.appendChild(deprecate);
    row.appendChild(name);
    row.appendChild(status);
    row.appendChild(observed);
    row.appendChild(actions);
    table.appendChild(row);
  });
  const docs = document.getElementById('docs');
  docs.innerHTML = '<tr><th>Document</th><th>Status</th><th></th></tr>';
  (data.documents || []).forEach(doc => {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = doc.title;
    const status = document.createElement('td');
    status.textContent = doc.approval_status;
    const actions = document.createElement('td');
    const approve = document.createElement('button');
    approve.textContent = 'Approve';
    approve.onclick = async () => { await api('approve_document', {document_id: doc.document_id}); load(); };
    const deprecate = document.createElement('button');
    deprecate.textContent = 'Deprecate';
    deprecate.onclick = async () => { await api('deprecate_document', {document_id: doc.document_id}); load(); };
    actions.appendChild(approve);
    actions.appendChild(deprecate);
    row.appendChild(name);
    row.appendChild(status);
    row.appendChild(actions);
    docs.appendChild(row);
  });
}
async function load() {
  const response = await fetch(location.pathname + '?format=json');
  draw(await response.json());
}
document.getElementById('pause').onclick = async () => { await api('pause', {paused: true}); load(); };
document.getElementById('resume').onclick = async () => { await api('pause', {paused: false}); load(); };
load();
</script>
</body></html>
"""


class handler(BaseHTTPRequestHandler):
    def _identity(self):
        return identity_from_headers(self.headers)

    def do_GET(self):
        if self._identity() is None:
            return _unauthorized(self)
        config = config_from_env()
        store = open_store()
        now = datetime.now(timezone.utc)
        if "format=json" in (self.path or ""):
            data = snapshot(store, config=config, now=now)
            data["checks"] = launch_checks(config, store, today=now.date())
            # Do not send full document bodies twice; terms are the editor payload.
            payload = json.dumps(data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        identity = self._identity()
        if identity is None:
            return _unauthorized(self)
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length < 20000 else b""
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}
        store = open_store()
        now = datetime.now(timezone.utc)
        action = data.get("action")
        try:
            if action == "approve_term":
                result = approve_term(store, term_id=str(data.get("term_id") or ""), actor=identity.actor_id, now=now)
            elif action == "save_definition":
                result = save_definition(
                    store,
                    term_id=str(data.get("term_id") or ""),
                    actor=identity.actor_id,
                    definition=str(data.get("definition") or ""),
                    now=now,
                )
            elif action == "deprecate_term":
                result = deprecate_term(store, term_id=str(data.get("term_id") or ""), actor=identity.actor_id, now=now)
            elif action == "approve_document":
                result = approve_document(
                    store, document_id=str(data.get("document_id") or ""), actor=identity.actor_id, now=now
                )
            elif action == "deprecate_document":
                result = deprecate_document(
                    store, document_id=str(data.get("document_id") or ""), actor=identity.actor_id, now=now
                )
            elif action == "pause":
                store.set_paused(bool(data.get("paused")), actor=identity.actor_id)
                result = {"paused": bool(data.get("paused"))}
            elif action == "suggest":
                result = suggest_term(store, actor=identity.actor_id, message=str(data.get("message") or ""), now=now)
            else:
                result = {"error": "unknown action"}
            status = 200
        except LedgerUnavailable as exc:
            result = {"error": str(exc)}
            status = 503
        except ValueError as exc:
            result = {"error": str(exc)}
            status = 400
        payload = json.dumps(result, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        return
