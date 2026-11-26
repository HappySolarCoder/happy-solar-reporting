# -*- coding: utf-8 -*-

"""POST /api/empower_daily_digest

Builds the Resend digest. dry_run returns the payloads and does not send.
A real send requires EMPOWER_ALERTS_ENABLED=true and RESEND_API_KEY, and
fails closed when the key is missing. Text alerts stay behind
EMPOWER_INTERNAL_TEXTS_ENABLED, which defaults off.
"""

from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from metrics.empower_alerts import alerts_enabled, deliver_digest, evaluate_jobs, recipient_map
from metrics.nyhep_stage_events import snapshot_day


PHOENIX = ZoneInfo("America/Phoenix")


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length_raw = handler.headers.get("Content-Length") if handler.headers else "0"
    try:
        length = int(length_raw or "0")
    except ValueError:
        length = 0
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(payload, dict):
        raise ValueError("invalid_body")
    return payload


def _write(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _flag(path: str, body: dict, name: str) -> bool:
    query = parse_qs(urlparse(path).query)
    raw = query.get(name, [""])[0] or body.get(name) or ""
    return str(raw).strip().lower() in {"1", "true", "yes"}


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        from empower_portal import view_identity

        if view_identity(self.headers) is None:
            _write(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            body = _read_json(self)
        except Exception:
            _write(self, 400, {"ok": False, "error": "invalid_body"})
            return
        dry_run = _flag(self.path, body, "dry_run") or _flag(self.path, body, "dryRun") or body.get("dry_run") is True
        send = _flag(self.path, body, "send") or body.get("send") is True
        if not send:
            dry_run = True
        try:
            if isinstance(body.get("alerts"), list):
                alerts = body["alerts"]
                as_of = snapshot_day(body.get("asOf") or body.get("as_of")) or datetime.now(PHOENIX).date()
                stage_counts = body.get("stageCounts") if isinstance(body.get("stageCounts"), dict) else {}
            else:
                from empower_portal_ingest import get_db, load_latest
                from metrics.empower_ghl_events import load_open_ghl_events
                from metrics.empower_linker import load_empower_opps, load_links
                from metrics.nyhep_stage_events import load_open_events

                db = get_db()
                latest = load_latest(db) or {}
                projects = latest.get("projects") or []
                snapshot_as_of = snapshot_day(latest.get("snapshot"))
                as_of = snapshot_as_of or datetime.now(PHOENIX).date()
                link_rows = []
                seen = set()
                for row in load_links(db).values():
                    marker = id(row)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    link_rows.append(row)
                alerts = evaluate_jobs(
                    projects,
                    load_empower_opps(db),
                    link_rows,
                    [row[1] for row in load_open_events(db).values() if isinstance(row, tuple)],
                    [row[1] for row in load_open_ghl_events(db).values() if isinstance(row, tuple)],
                    as_of,
                    snapshot_day=snapshot_as_of,
                    today=datetime.now(PHOENIX).date(),
                )
                stage_counts = {}
                for project in projects:
                    if isinstance(project, dict) and str(project.get("status") or "").lower() in {"open", "active"}:
                        step = str(project.get("step") or "").strip() or "Unknown"
                        stage_counts[step] = stage_counts.get(step, 0) + 1
            result = deliver_digest(
                alerts,
                as_of=as_of,
                recipients=recipient_map(),
                stage_counts=stage_counts,
                dry_run=dry_run or not alerts_enabled(),
                send=send and alerts_enabled() and not dry_run,
            )
        except Exception:
            _write(self, 500, {"ok": False, "error": "digest_unavailable"})
            return
        status = 200 if result.get("ok") or result.get("dryRun") else 500
        if result.get("error") == "missing_env":
            status = 500
        _write(self, status, result)


Handler = handler
