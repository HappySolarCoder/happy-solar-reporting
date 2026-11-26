# -*- coding: utf-8 -*-

"""GET /api/empower_portal

EmPower+ Portal shell for the Bloom Data Center. The HTML has no project
rows. It asks the Bloom parent for a Goose token, then renders
GET /api/empower_portal?format=json.

JSON auth uses the Bloom bearer and the settings basic header on their
own. The chat identity helper is intentionally not used: it can remap a
closer onto settings_admin. Manager, coach, and the settings password are
the only viewers.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from copilot.auth import (
    SETTINGS_ADMIN_ROLE,
    bloom_parent_origins,
    identity_from_bloom_bearer,
    identity_from_headers,
)
from copilot.bloom_frame import bloom_frame_script
from dashboard_nav import dashboard_nav_css, render_dashboard_nav
from metrics.empower_portal_metrics import (
    SOURCE_LINE,
    SUBTITLE_LEAD,
    TITLE,
    VENDOR_WARNING,
    WAITING_DETAIL,
    build_portal_view,
)


FRAME_ANCESTORS = (
    "frame-ancestors 'self' https://bloom.happyslr.com "
    "https://*.happyslr.com https://happy-solar-bloom-portal.vercel.app"
)
BLOOM_VIEW_ROLES = frozenset({"manager", "coach"})
_LOCKED = "Sign in through Bloom Data Center"


def wants_json(path: str) -> bool:
    query = parse_qs(urlparse(path).query)
    return (query.get("format", [""])[0] or "").strip().lower() == "json"


def view_identity(headers):
    """Manager, coach, or settings basic auth. Closers stay unauthorized."""
    basic = identity_from_headers(headers)
    if basic is not None and basic.role == SETTINGS_ADMIN_ROLE:
        return basic
    bloom = identity_from_bloom_bearer(headers)
    if bloom is not None and bloom.role in BLOOM_VIEW_ROLES:
        return bloom
    return None


def load_view() -> dict:
    from empower_portal_ingest import get_db, load_latest
    from metrics.nyhep_stage_events import load_recent_events

    db = get_db()
    payload = load_latest(db) or {}
    return build_portal_view(payload, load_recent_events(db, payload))


def _send(handler, status: int, body: bytes, content_type: str, cache_control: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("Content-Security-Policy", FRAME_ANCESTORS)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_json(handler, status: int, payload: dict) -> None:
    _send(
        handler,
        status,
        json.dumps(payload, default=str).encode("utf-8"),
        "application/json; charset=utf-8",
        "s-maxage=300",
    )


def send_html(handler, html: str) -> None:
    _send(handler, 200, html.encode("utf-8"), "text/html; charset=utf-8", "no-store")


def render_empower_portal_html() -> str:
    origins = json.dumps(bloom_parent_origins())
    frame_script = bloom_frame_script(indent="      ")
    page = """<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>__NAV_CSS__</style>
  <style>
    .ep-dashboard[hidden], .ep-panel[hidden], #locked[hidden] { display: none !important; }
    .ep-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
    .ep-filter { min-height: 36px; }
    .ep-filter.active { color: var(--cyan); border-color: var(--cyan); background: #123e52; }
    .ep-lock { margin: 0 0 18px; }
    .ep-history { min-height: 32px; }
    .ep-timeline-row[hidden] { display: none !important; }
    #stageBars:empty::before { content: "No open projects."; color: var(--muted); }
  </style>
</head>
<body class="oc-root" data-oc-native-filters="1">
  __NAV_HTML__
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>EmPower+ Portal</strong></div>
      <div class="top-right"><span id="asOf">Sign in required</span></div>
    </header>
    <main>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Other</div>
          <h1>__TITLE__</h1>
          <p class="subtitle">__SUBTITLE_LEAD__ Last check: <span id="checkedAt">—</span>.</p>
          <p class="subtitle">__SOURCE_LINE__</p>
        </div>
      </div>
      <p id="locked" class="notice ep-lock" role="status">__LOCKED__</p>
      <div id="dashboard" class="ep-dashboard" hidden>
        <div class="notice warn" role="note"><span>__VENDOR_WARNING__</span></div>
        <div class="kpis" style="--n:4">
          <div class="kpi"><div class="label">Total enrollments</div><div class="number" id="totalValue">—</div></div>
          <div class="kpi"><div class="label">Open</div><div class="number" id="openValue">—</div></div>
          <div class="kpi"><div class="label">Closed (completed)</div><div class="number" id="closedValue">—</div></div>
          <div class="kpi"><div class="label">Cancelled</div><div class="number" id="cancelledValue">—</div></div>
        </div>
        <div class="kpis" style="--n:3">
          <div class="kpi"><div class="label">Waiting on us</div><div class="number" id="waitingValue">—</div><div class="sub">__WAITING_DETAIL__</div></div>
          <div class="kpi"><div class="label">Past workscope</div><div class="number" id="pastValue">—</div><div class="sub">Open projects after Workscope Submission</div></div>
          <div class="kpi"><div class="label">Overdue</div><div class="number" id="overdueValue">—</div><div class="sub">Waiting on us, due before the snapshot date</div></div>
        </div>
        <section class="panel ep-panel" id="changesPanel" hidden>
          <div class="panel-head"><h2>Changed since the last check</h2></div>
          <div class="panel-body tablewrap">
            <table>
              <thead><tr><th>Enroll #</th><th>Customer</th><th>Change</th></tr></thead>
              <tbody id="changesBody"></tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Open projects by stage</h2></div>
          <div class="panel-body" id="stageBars"></div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>With the program</h2></div>
          <div class="panel-body tablewrap">
            <table>
              <thead><tr><th>Enroll #</th><th>Customer</th><th>Stage</th><th>Days</th><th>Since</th><th>Flag</th></tr></thead>
              <tbody id="programBody"></tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Waiting on us, by due date</h2></div>
          <div class="panel-body tablewrap">
            <table>
              <thead><tr><th>Enroll #</th><th>Customer</th><th>Step</th><th>Due</th></tr></thead>
              <tbody id="waitingBody"></tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>All enrollments</h2></div>
          <div class="panel-body">
            <div class="ep-filters" id="statusFilters" data-default="Open" role="group" aria-label="Enrollment status"></div>
            <div class="tablewrap">
              <table>
                <thead><tr><th>Enroll #</th><th>Customer</th><th>City</th><th>Enrolled</th><th>Status</th><th>Stage</th><th>Installer</th><th>Tier</th><th>History</th></tr></thead>
                <tbody id="enrollmentBody"></tbody>
              </table>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Check history</h2></div>
          <div class="panel-body tablewrap">
            <table>
              <thead><tr><th>Checked</th><th>Total</th><th>Open</th><th>Closed</th><th>Cancelled</th><th>Changes</th></tr></thead>
              <tbody id="historyBody"></tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
    <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span>NYHEP read only</span></footer>
  </div>
  <script>
    (function () {
      const bloomParents = new Set(__BLOOM_ORIGINS__);
      const locked = document.getElementById("locked");
      const dashboard = document.getElementById("dashboard");
      let statusFilter = document.getElementById("statusFilters").getAttribute("data-default") || "Open";
      let latest = null;

      function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
          return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
        });
      }

__BLOOM_FRAME__

      function showLocked() {
        locked.hidden = false;
        locked.textContent = "__LOCKED__";
        dashboard.hidden = true;
      }

      function rememberToken(data) {
        if (!data || data.type !== "happy-solar-goose" || data.action !== "token") return "";
        if (typeof data.token !== "string") return "";
        const token = data.token;
        if (token.length < 20 || token.length > 4000 || token.indexOf(" ") !== -1 || token.indexOf(".") < 1) return "";
        return token;
      }

      function requestBloomToken() {
        const targets = bloomFrameTargets();
        if (!targets.length) return Promise.resolve("");
        return new Promise(function (resolve) {
          const timer = window.setTimeout(function () {
            window.removeEventListener("message", onMessage);
            resolve("");
          }, 2500);
          function onMessage(event) {
            if (!bloomParents.has(event.origin)) return;
            const data = event.data;
            if (data && data.type === "happy-solar-goose" && data.action === "token-unavailable") {
              window.clearTimeout(timer);
              window.removeEventListener("message", onMessage);
              resolve("");
              return;
            }
            const token = rememberToken(data);
            if (!token) return;
            window.clearTimeout(timer);
            window.removeEventListener("message", onMessage);
            resolve(token);
          }
          window.addEventListener("message", onMessage);
          targets.forEach(function (origin) {
            window.parent.postMessage({ type: "happy-solar-goose", action: "request-token" }, origin);
          });
        });
      }

      function cell(value, tone) {
        const text = esc(value == null || value === "" ? "—" : value);
        if (tone === "danger") return '<span class="danger">' + text + "</span>";
        if (tone === "warning") return '<span class="warning">' + text + "</span>";
        if (tone === "success") return '<span class="positive">' + text + "</span>";
        return text;
      }

      function fill(bodyId, rows, cells) {
        document.getElementById(bodyId).innerHTML = rows.length
          ? rows.map(function (row) {
              return "<tr>" + cells(row).map(function (item) { return "<td>" + item + "</td>"; }).join("") + "</tr>";
            }).join("")
          : '<tr><td colspan="8">Nothing to show.</td></tr>';
      }

      function renderFilters() {
        const filters = (latest && latest.filters) || {};
        const host = document.getElementById("statusFilters");
        host.innerHTML = ["Open", "Closed", "Cancelled", "All"].map(function (name) {
          const count = filters[name] == null ? 0 : filters[name];
          const active = name === statusFilter;
          return '<button type="button" class="ep-filter' + (active ? " active" : "") + '" data-status="' + name + '" aria-pressed="' + active + '">' + name + " (" + esc(count) + ")</button>";
        }).join("");
        host.querySelectorAll("button").forEach(function (button) {
          button.addEventListener("click", function () {
            statusFilter = button.getAttribute("data-status") || "Open";
            renderFilters();
            renderEnrollments();
          });
        });
      }

      function timelineHtml(row) {
        const items = row.timeline || [];
        if (!items.length) return "<p>No stage events in the last 120 days.</p>";
        return "<ul>" + items.map(function (item) {
          const todo = item.todoStage ? " To-Do " + esc(item.todoStage) + "." : "";
          const ended = item.ended ? " Ended." : " Current.";
          return "<li><b>" + esc(item.stage || "—") + "</b> " + esc(item.enrollmentStatus || "") + todo + " " + esc(item.since || "") + "." + ended + "</li>";
        }).join("") + "</ul>";
      }

      function renderEnrollments() {
        const rows = ((latest && latest.enrollments) || []).filter(function (row) {
          return statusFilter === "All" || row.status === statusFilter;
        });
        const body = document.getElementById("enrollmentBody");
        body.innerHTML = rows.length ? rows.map(function (row) {
          const cells = [
            esc(row.id),
            esc(row.customer),
            esc(row.city),
            esc(row.enrolled),
            cell(row.status, row.statusTone),
            esc(row.stepLabel || row.step),
            esc(row.installer),
            esc(row.tier),
            '<button type="button" class="ep-history" data-enroll="' + esc(row.id) + '" aria-expanded="false">History</button>'
          ].map(function (item) { return "<td>" + item + "</td>"; }).join("");
          const detail = '<tr class="ep-timeline-row" hidden data-for="' + esc(row.id) + '"><td colspan="9">' + timelineHtml(row) + "</td></tr>";
          return "<tr>" + cells + "</tr>" + detail;
        }).join("") : '<tr><td colspan="9">Nothing to show.</td></tr>';
        body.querySelectorAll(".ep-history").forEach(function (button) {
          button.addEventListener("click", function () {
            const enroll = button.getAttribute("data-enroll");
            const detail = body.querySelector('.ep-timeline-row[data-for="' + enroll + '"]');
            if (!detail) return;
            const open = detail.hidden;
            detail.hidden = !open;
            button.setAttribute("aria-expanded", open ? "true" : "false");
          });
        });
      }

      function render(data) {
        latest = data || {};
        locked.hidden = true;
        dashboard.hidden = false;
        const checked = latest.checkedAt || "—";
        document.getElementById("checkedAt").textContent = checked;
        document.getElementById("asOf").textContent = latest.asOf ? ("As of " + latest.asOf) : "No snapshot yet";
        const metrics = latest.metrics || {};
        document.getElementById("totalValue").textContent = metrics.total == null ? "—" : String(metrics.total);
        document.getElementById("openValue").textContent = metrics.open == null ? "—" : String(metrics.open);
        document.getElementById("closedValue").textContent = metrics.closed == null ? "—" : String(metrics.closed);
        document.getElementById("cancelledValue").textContent = metrics.cancelled == null ? "—" : String(metrics.cancelled);
        document.getElementById("waitingValue").textContent = metrics.waitingOnUs == null ? "—" : String(metrics.waitingOnUs);
        document.getElementById("pastValue").textContent = metrics.pastWorkscope == null ? "—" : String(metrics.pastWorkscope);
        const overdue = document.getElementById("overdueValue");
        overdue.textContent = metrics.overdue == null ? "—" : String(metrics.overdue);
        overdue.classList.toggle("danger", Number(metrics.overdue) > 0);

        const changes = latest.changes || [];
        const changesPanel = document.getElementById("changesPanel");
        changesPanel.hidden = changes.length === 0;
        fill("changesBody", changes, function (row) {
          return [esc(row.id), esc(row.customer), esc(row.change)];
        });
        fill("programBody", latest.withProgram || [], function (row) {
          const flag = row.flag ? '<span class="danger">' + esc(row.flag) + "</span>" : "—";
          return [esc(row.id), esc(row.customer), esc(row.stage), esc(row.daysInStage), esc(row.since), flag];
        });

        const stages = latest.stages || [];
        let max = 1;
        stages.forEach(function (row) { if (Number(row.count) > max) max = Number(row.count); });
        document.getElementById("stageBars").innerHTML = stages.map(function (row) {
          const width = Math.max(4, Math.round(100 * Number(row.count || 0) / max));
          return '<div class="barrow"><div class="barlabel"><span>' + esc(row.step) + "</span><span>" + esc(row.count) + '</span></div><div class="track" role="img" aria-label="' + esc(row.step) + " " + esc(row.count) + '"><i style="width:' + width + '%"></i></div></div>';
        }).join("");

        fill("waitingBody", latest.waiting || [], function (row) {
          return [esc(row.id), esc(row.customer), esc(row.stepLabel), cell(row.dueLabel || row.due, row.tone)];
        });
        renderFilters();
        renderEnrollments();
        fill("historyBody", latest.history || [], function (row) {
          return [esc(row.checkedAt), esc(row.total), esc(row.open), esc(row.closed), esc(row.cancelled), esc(row.changeCount)];
        });
      }

      requestBloomToken().then(function (token) {
        if (!token) {
          showLocked();
          return null;
        }
        return fetch("/api/empower_portal?format=json", {
          headers: { Authorization: "Bearer " + token, Accept: "application/json" },
          cache: "no-store"
        });
      }).then(function (response) {
        if (!response) return null;
        if (!response.ok) {
          showLocked();
          return null;
        }
        return response.json();
      }).then(function (data) {
        if (!data) return;
        render(data);
      }).catch(function () {
        showLocked();
      });
    })();
  </script>
</body>
</html>"""
    return (
        page.replace("__TITLE__", TITLE)
        .replace("__SUBTITLE_LEAD__", SUBTITLE_LEAD)
        .replace("__SOURCE_LINE__", SOURCE_LINE)
        .replace("__VENDOR_WARNING__", VENDOR_WARNING)
        .replace("__WAITING_DETAIL__", WAITING_DETAIL)
        .replace("__LOCKED__", _LOCKED)
        .replace("__NAV_CSS__", dashboard_nav_css())
        .replace("__NAV_HTML__", render_dashboard_nav("empower_portal"))
        .replace("__BLOOM_ORIGINS__", origins)
        .replace("__BLOOM_FRAME__", frame_script)
    )


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if not wants_json(self.path):
            send_html(self, render_empower_portal_html())
            return
        if view_identity(self.headers) is None:
            send_json(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            view = load_view()
        except Exception:
            send_json(self, 502, {"ok": False, "error": "unavailable"})
            return
        body = {"ok": True}
        body.update(view)
        send_json(self, 200, body)


Handler = handler
