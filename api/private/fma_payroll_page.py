# -*- coding: utf-8 -*-

"""HTML shell for /private/fma-payroll. No payroll rows are rendered here."""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

PRIVATE_DIR = Path(__file__).resolve().parent
if str(PRIVATE_DIR) not in sys.path:
    sys.path.insert(0, str(PRIVATE_DIR))

from payroll_gate import access_decision, send_html

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
    .card {
      background: #fff;
      border: 1px solid #d8e0e8;
      border-radius: 12px;
      padding: 18px;
    }
    label { display: block; font-weight: 650; margin-bottom: 6px; }
    input[type="password"], input[type="date"] {
      font: inherit;
      padding: 8px 10px;
      border: 1px solid #c5d0db;
      border-radius: 8px;
      background: #fff;
    }
    button, .btn {
      font: inherit;
      font-weight: 650;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid #b7c3cf;
      background: #fff;
      cursor: pointer;
    }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    button.primary { background: #0f6b4c; color: #fff; border-color: #0f6b4c; }
    .gate { max-width: 420px; display: grid; gap: 12px; }
    .error { color: #9f1239; min-height: 1.2em; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin-top: 14px; }
    .toolbar label { margin: 0 0 4px; font-size: 12px; color: #5c6b7a; }
    .top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e4ebf2; vertical-align: top; }
    th { font-size: 12px; letter-spacing: 0.03em; text-transform: uppercase; color: #526273; background: #f8fafc; }
    tr.click { cursor: pointer; }
    tr.click:hover { background: #f3faf6; }
    tr.total td { font-weight: 750; background: #f8fafc; }
    tr.detail td { background: #fbfcfd; }
    table.demos { font-size: 13px; }
    table.demos th { text-transform: none; letter-spacing: 0; }
    a { color: #0f6b4c; }
    details { background: #fff; border: 1px solid #d8e0e8; border-radius: 12px; padding: 12px 14px; }
    summary { cursor: pointer; font-weight: 700; }
    .scroll { overflow-x: auto; border: 1px solid #d8e0e8; border-radius: 12px; }
    .status { margin-top: 12px; }
"""


def login_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex, nofollow" />
  <title>FMA payroll</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <main>
    <h1>FMA payroll</h1>
    <p class="muted">Private Thursday payroll. Enter the password to continue.</p>
    <form id="gate" class="card gate" style="margin-top:18px" method="post" action="/api/private/fma_payroll_login">
      <div>
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required autofocus />
      </div>
      <div><button class="primary" type="submit">Continue</button></div>
      <p id="gate-error" class="error" role="alert"></p>
    </form>
  </main>
  <script>
    document.getElementById("gate").addEventListener("submit", function (ev) {{
      ev.preventDefault();
      var error = document.getElementById("gate-error");
      error.textContent = "";
      var password = document.getElementById("password").value;
      fetch("/api/private/fma_payroll_login", {{
        method: "POST",
        headers: {{"Content-Type": "application/json", "Accept": "application/json"}},
        credentials: "same-origin",
        body: JSON.stringify({{password: password}})
      }}).then(function (res) {{
        if (res.ok) {{
          window.location.reload();
          return;
        }}
        if (res.status === 503) {{
          error.textContent = "Payroll gate is not configured.";
          return;
        }}
        error.textContent = "That password was not accepted.";
      }}).catch(function () {{
        error.textContent = "Could not reach the payroll gate.";
      }});
    }});
  </script>
</body>
</html>"""


def unavailable_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex, nofollow" />
  <title>FMA payroll</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <main>
    <h1>FMA payroll</h1>
    <p class="muted">Payroll gate is not configured.</p>
  </main>
</body>
</html>"""


def app_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="robots" content="noindex, nofollow" />
  <title>FMA payroll</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>FMA payroll</h1>
        <p id="week-label" class="muted">Loading the week…</p>
      </div>
      <form method="post" action="/api/private/fma_payroll_logout">
        <button type="submit">Log out</button>
      </form>
    </div>
    <div class="toolbar">
      <button type="button" id="prev">Previous week</button>
      <button type="button" id="next">Next week</button>
      <div>
        <label for="week">Thursday</label>
        <input id="week" type="date" />
      </div>
    </div>
    <p id="status" class="status muted"></p>
    <h2>FMA (setter) credit</h2>
    <div id="fma" class="scroll"></div>
    <h2>Scheduling manager payout</h2>
    <div id="scheduling" class="scroll"></div>
    <h2>Excluded</h2>
    <details id="excluded">
      <summary>Excluded (<span id="excluded-count">0</span>)</summary>
      <div id="excluded-body" class="scroll" style="margin-top:10px"></div>
    </details>
  </main>
  <script>
    var payload = null;

    function esc(value) {{
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }}

    function idCell(id, url) {{
      if (!id) return "";
      if (!url) return esc(id);
      return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(id) + "</a>";
    }}

    function demoTable(demos, opts) {{
      opts = opts || {{}};
      var html = "<table class=\\"demos\\"><thead><tr>";
      html += "<th>Customer</th><th>Sat (ET)</th><th>Pipeline</th><th>Lead source</th><th>Owner</th><th>Setter</th><th>Scheduling manager</th>";
      if (opts.selfGen) html += "<th>Self-gen</th>";
      if (opts.reasons) html += "<th>Reasons</th>";
      html += "<th>Opportunity</th><th>Contact</th></tr></thead><tbody>";
      (demos || []).forEach(function (demo) {{
        html += "<tr>";
        html += "<td>" + esc(demo.customer_name) + "</td>";
        html += "<td>" + esc(demo.sat_date) + "</td>";
        html += "<td>" + esc(demo.pipeline) + "</td>";
        html += "<td>" + esc(demo.lead_source) + "</td>";
        html += "<td>" + esc(demo.opportunity_owner) + "</td>";
        html += "<td>" + esc(demo.setter) + "</td>";
        html += "<td>" + esc(demo.scheduling_manager) + "</td>";
        if (opts.selfGen) html += "<td>" + (demo.self_gen ? "Yes" : "") + "</td>";
        if (opts.reasons) html += "<td>" + esc((demo.reasons || []).join("; ")) + "</td>";
        html += "<td>" + idCell(demo.opportunity_id, demo.ghl_opportunity_url) + "</td>";
        html += "<td>" + idCell(demo.contact_id, demo.ghl_contact_url) + "</td>";
        html += "</tr>";
      }});
      html += "</tbody></table>";
      return html;
    }}

    function renderFma(fma) {{
      var html = "<table><thead><tr><th>Setter</th><th>Counted demos</th></tr></thead><tbody>";
      (fma.rows || []).forEach(function (row, index) {{
        var id = "fma-row-" + index;
        html += '<tr class="click" data-target="' + id + '" aria-expanded="false">';
        html += "<td>" + esc(row.setter) + "</td><td>" + esc(row.count) + "</td></tr>";
        html += '<tr class="detail" id="' + id + '" hidden><td colspan="2">' + demoTable(row.demos) + "</td></tr>";
      }});
      html += '<tr class="total"><td>GRAND TOTAL</td><td>' + esc(fma.grand_total) + "</td></tr>";
      html += "</tbody></table>";
      return html;
    }}

    function renderScheduling(section) {{
      var html = "<table><thead><tr><th>Scheduling Manager</th><th>Counted (excl. self-gen)</th><th>Excluded self-gen</th><th>Total sits</th></tr></thead><tbody>";
      (section.rows || []).forEach(function (row, index) {{
        var id = "sm-row-" + index;
        html += '<tr class="click" data-target="' + id + '" aria-expanded="false">';
        html += "<td>" + esc(row.manager) + "</td>";
        html += "<td>" + esc(row.counted) + "</td>";
        html += "<td>" + esc(row.excluded_self_gen) + "</td>";
        html += "<td>" + esc(row.total) + "</td></tr>";
        html += '<tr class="detail" id="' + id + '" hidden><td colspan="4">' + demoTable(row.demos, {{selfGen: true}}) + "</td></tr>";
      }});
      var grand = section.grand_total || {{}};
      html += '<tr class="total"><td>GRAND TOTAL</td><td>' + esc(grand.counted) + "</td><td>" + esc(grand.excluded_self_gen) + "</td><td>" + esc(grand.total) + "</td></tr>";
      html += "</tbody></table>";
      return html;
    }}

    function ymd(date) {{
      var month = String(date.getMonth() + 1).padStart(2, "0");
      var day = String(date.getDate()).padStart(2, "0");
      return date.getFullYear() + "-" + month + "-" + day;
    }}

    function shiftDays(ymdText, days) {{
      var date = new Date(ymdText + "T12:00:00");
      date.setDate(date.getDate() + days);
      return ymd(date);
    }}

    function thursdayOnOrBefore(ymdText) {{
      var date = new Date(ymdText + "T12:00:00");
      var back = (date.getDay() + 3) % 7;
      date.setDate(date.getDate() - back);
      return ymd(date);
    }}

    function goToWeek(weekStart) {{
      var url = new URL(window.location.href);
      url.searchParams.set("week_start", weekStart);
      window.location.href = url.pathname + "?" + url.searchParams.toString();
    }}

    function bindRows(root) {{
      root.querySelectorAll("tr.click").forEach(function (row) {{
        row.addEventListener("click", function () {{
          var detail = document.getElementById(row.getAttribute("data-target"));
          if (!detail) return;
          var willOpen = detail.hasAttribute("hidden");
          if (willOpen) detail.removeAttribute("hidden");
          else detail.setAttribute("hidden", "");
          row.setAttribute("aria-expanded", willOpen ? "true" : "false");
        }});
      }});
    }}

    function render(data) {{
      payload = data;
      document.getElementById("week-label").textContent = data.week_label || "";
      document.getElementById("week").value = data.week_start || "";
      var nextStart = shiftDays(data.week_start, 7);
      document.getElementById("next").disabled = nextStart > data.last_completed_week_start;
      document.getElementById("fma").innerHTML = renderFma(data.fma || {{}});
      document.getElementById("scheduling").innerHTML = renderScheduling(data.scheduling_manager || {{}});
      var excluded = (data.fma && data.fma.excluded) || [];
      document.getElementById("excluded-count").textContent = String((data.fma && data.fma.excluded_count) || excluded.length);
      document.getElementById("excluded-body").innerHTML = demoTable(excluded, {{reasons: true, selfGen: true}});
      bindRows(document.getElementById("fma"));
      bindRows(document.getElementById("scheduling"));
      document.getElementById("status").textContent = "";
    }}

    document.getElementById("prev").addEventListener("click", function () {{
      if (!payload) return;
      goToWeek(shiftDays(payload.week_start, -7));
    }});
    document.getElementById("next").addEventListener("click", function () {{
      if (!payload || document.getElementById("next").disabled) return;
      goToWeek(shiftDays(payload.week_start, 7));
    }});
    document.getElementById("week").addEventListener("change", function (ev) {{
      if (!payload || !ev.target.value) return;
      var thursday = thursdayOnOrBefore(ev.target.value);
      if (thursday > payload.last_completed_week_start) thursday = payload.last_completed_week_start;
      goToWeek(thursday);
    }});

    var params = new URLSearchParams(window.location.search);
    var week = params.get("week_start");
    var api = "/api/private/fma_payroll" + (week ? ("?week_start=" + encodeURIComponent(week)) : "");
    fetch(api, {{credentials: "same-origin", headers: {{"Accept": "application/json"}}}})
      .then(function (res) {{
        if (res.status === 401) {{
          window.location.reload();
          return null;
        }}
        if (!res.ok) {{
          document.getElementById("status").textContent = "Payroll data is unavailable (" + res.status + ").";
          return null;
        }}
        return res.json();
      }})
      .then(function (data) {{
        if (data) render(data);
      }})
      .catch(function () {{
        document.getElementById("status").textContent = "Could not load payroll data.";
      }});
  </script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        decision = access_decision(self.headers)
        if decision == "unset":
            send_html(self, 503, unavailable_html())
            return
        if decision != "ok":
            send_html(self, 200, login_html())
            return
        send_html(self, 200, app_html())

    def log_message(self, fmt: str, *args: Any) -> None:
        return


Handler = handler
