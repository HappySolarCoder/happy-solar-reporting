# -*- coding: utf-8 -*-

"""HTML shell for /enerflo-installer.

The shell has no note text. The browser fetches /api/enerflo_installer.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from typing import Any

PAGE_CSS = """
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f4f6f8;
      color: #1c2430;
      font: 15px/1.45 "Segoe UI", ui-sans-serif, system-ui, sans-serif;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 28px 20px 48px; }
    h1 { font-size: 28px; margin: 0 0 6px; letter-spacing: -0.02em; }
    h2 { font-size: 18px; margin: 28px 0 10px; }
    p { margin: 0; }
    .muted { color: #5c6b7a; }
    .lede { margin-top: 4px; }
    .banner { margin-top: 16px; padding: 12px 14px; border-radius: 10px; }
    .banner.error { background: #fee2e2; color: #9f1239; }
    .banner.warn { background: #fef3c7; color: #92400e; }
    .counts { display: flex; flex-wrap: wrap; gap: 10px; align-items: stretch; margin-top: 18px; }
    .chip {
      background: #fff;
      border: 1px solid #d8e0e8;
      border-radius: 12px;
      padding: 10px 12px;
      min-width: 128px;
    }
    .chip-label { display: block; color: #5c6b7a; font-size: 12px; }
    .chip-value { display: block; font-size: 22px; font-weight: 750; margin-top: 2px; }
    .meta { flex: 1 1 220px; align-self: center; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e4ebf2; vertical-align: top; }
    th { font-size: 12px; letter-spacing: 0.03em; text-transform: uppercase; color: #526273; background: #f8fafc; }
    a { color: #0f6b4c; }
    details { background: #fff; border: 1px solid #d8e0e8; border-radius: 12px; padding: 12px 14px; margin-top: 14px; }
    summary { cursor: pointer; font-weight: 700; }
    .scroll { overflow-x: auto; border: 1px solid #d8e0e8; border-radius: 12px; }
    .badge {
      display: inline-block;
      background: #fff7ed;
      color: #9a3412;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .snippet { margin-bottom: 4px; }
    details.note-details { margin-top: 4px; padding: 6px 8px; }
    pre.note { white-space: pre-wrap; font: inherit; margin: 8px 0 0; }
    ul { margin: 8px 0 0; padding-left: 18px; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
"""

APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex" />
  <title>Installer tags</title>
  <style>__CSS__</style>
</head>
<body>
  <main>
    <h1>Installer tags</h1>
    <p class="muted lede">Essential Power install notes with no reply yet.</p>
    <p id="error" class="banner error" hidden role="alert"></p>
    <p id="warn" class="banner warn" hidden></p>
    <div id="content" hidden>
      <div id="counts" class="counts"></div>
      <h2>Open</h2>
      <div id="open-body" class="scroll"></div>
      <details id="pending">
        <summary>Pending (&lt; 24h) (<span id="pending-count">0</span>)</summary>
        <div id="pending-body" class="scroll"></div>
      </details>
      <details id="survey">
        <summary>Survey passed (reply probably not needed) (<span id="survey-count">0</span>)</summary>
        <div id="survey-body" class="scroll"></div>
      </details>
      <details id="answered">
        <summary>Recently answered (14d) (<span id="answered-count">0</span>)</summary>
        <div id="answered-body" class="scroll"></div>
      </details>
      <h2>Needs mapping</h2>
      <div id="mapping"></div>
    </div>
  </main>
  <script>
    function esc(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function projectCell(row) {
      var parts = [];
      if (row.customer_name) parts.push(esc(row.customer_name));
      parts.push("Install #" + esc(row.install_id));
      var label = parts.join(" ");
      if (row.enerflo_url) {
        return '<a href="' + esc(row.enerflo_url) + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
      }
      return label;
    }

    function noteCell(row) {
      return '<div class="snippet">' + esc(row.snippet) + "</div>"
        + '<details class="note-details"><summary>Full note</summary><pre class="note">'
        + esc(row.text) + "</pre></details>";
    }

    function badgeCell(row) {
      if (!row.chaser_count) return "";
      return '<span class="badge">chased ' + esc(row.chaser_count) + "×</span>";
    }

    function people(tagged) {
      return esc((tagged || []).map(function (item) {
        return item && item.name ? item.name : "";
      }).filter(Boolean).join(", "));
    }

    function dataTable(rows) {
      if (!rows || !rows.length) {
        return '<p class="muted">None in this window.</p>';
      }
      var html = '<table><thead><tr>'
        + "<th>Customer / project</th><th>Waiting</th><th>Sales rep</th><th>Tagged</th><th>Note</th><th></th>"
        + "</tr></thead><tbody>";
      rows.forEach(function (row) {
        html += "<tr>";
        html += "<td>" + projectCell(row) + "</td>";
        html += "<td>" + esc(row.waiting_label) + "</td>";
        html += "<td>" + esc(row.sales_rep) + "</td>";
        html += "<td>" + people(row.tagged) + "</td>";
        html += "<td>" + noteCell(row) + "</td>";
        html += "<td>" + badgeCell(row) + "</td>";
        html += "</tr>";
      });
      html += "</tbody></table>";
      return html;
    }

    function countChip(label, value) {
      return '<div class="chip"><span class="chip-label">' + esc(label)
        + '</span><span class="chip-value">' + esc(value) + "</span></div>";
    }

    function answeredTable(rows) {
      if (!rows || !rows.length) return '<p class="muted">None in the last 14 days.</p>';
      var html = "<table><thead><tr><th>Customer / project</th><th>Tagged at</th><th>Replied</th><th>Reply kind</th><th>Confidence</th></tr></thead><tbody>";
      rows.forEach(function (row) {
        var who = row.customer_name ? esc(row.customer_name) + " " : "";
        html += "<tr><td>" + who + "Install #" + esc(row.install_id) + "</td>";
        html += "<td>" + esc(row.created_at_et) + "</td>";
        html += "<td>" + esc(row.replied_at_et) + "</td>";
        html += "<td>" + esc(row.reply_kind) + "</td>";
        html += "<td>" + esc(row.confidence) + "</td></tr>";
      });
      return html + "</tbody></table>";
    }

    function mappingList(items) {
      if (!items || !items.length) return '<p class="muted">None.</p>';
      var html = "<ul>";
      items.forEach(function (item) {
        html += "<li><code>" + esc(item.raw) + "</code> · " + esc(item.count)
          + " · last seen " + esc(item.last_seen_et) + "</li>";
      });
      return html + "</ul>";
    }

    function showError(message) {
      var banner = document.getElementById("error");
      banner.hidden = false;
      banner.textContent = message;
      document.getElementById("content").hidden = true;
    }

    function render(data) {
      var counts = data.counts || {};
      document.getElementById("counts").innerHTML =
        countChip("Open (> 24h)", counts.open || 0)
        + countChip("Pending (< 24h)", counts.pending || 0)
        + countChip("Survey passed", counts.survey_passed || 0)
        + countChip("Chasers", counts.chasers || 0)
        + '<p class="muted meta">Rule ' + esc(data.rule) + " · Generated " + esc(data.generated_at_et) + "</p>";
      document.getElementById("open-body").innerHTML = dataTable(data.rows || []);
      document.getElementById("pending-count").textContent = String(counts.pending || 0);
      document.getElementById("pending-body").innerHTML = dataTable(data.pending || []);
      document.getElementById("survey-count").textContent = String(counts.survey_passed || 0);
      document.getElementById("survey-body").innerHTML = dataTable(data.survey_passed || []);
      var recent = data.recently_answered || [];
      document.getElementById("answered-count").textContent = String(recent.length);
      document.getElementById("answered-body").innerHTML = answeredTable(recent);
      document.getElementById("mapping").innerHTML = mappingList(data.needs_mapping || []);
      var warnings = data.warnings || [];
      var warn = document.getElementById("warn");
      if (warnings.length) {
        warn.hidden = false;
        warn.textContent = "Some install details are unavailable (" + warnings.length + "). Rows still show Install #id.";
      } else {
        warn.hidden = true;
      }
      document.getElementById("content").hidden = false;
    }

    fetch("/api/enerflo_installer", {headers: {"Accept": "application/json"}})
      .then(function (res) {
        return res.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (err) { body = null; }
          return {ok: res.ok, status: res.status, body: body};
        });
      })
      .then(function (result) {
        if (!result.ok) {
          var detail = (result.body && (result.body.detail || result.body.error)) || ("HTTP " + result.status);
          showError("Installer tags could not be loaded (" + detail + ").");
          return;
        }
        render(result.body || {});
      })
      .catch(function () {
        showError("Installer tags could not be loaded.");
      });
  </script>
</body>
</html>"""


def app_html() -> str:
    return APP_HTML.replace("__CSS__", PAGE_CSS)


def send_html(handler: Any, status: int, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "private, no-store")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send_html(self, 200, app_html())

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
