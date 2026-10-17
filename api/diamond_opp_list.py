# -*- coding: utf-8 -*-

"""Vercel Python function: /api/diamond_opp_list

Diamond — Opportunity List. Open in the Data Center with no password gate,
same as Diamond Sweeper. Rows come from /api/metrics/diamond_opp_list.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


def render_html() -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("diamond_opp_list")
    html = """<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Diamond — Opportunity List</title>
  <style>__NAV_CSS__</style>
</head>
<body class="oc-root" data-oc-native-filters="1">
  __NAV_HTML__
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>Diamond — Opportunity List</strong></div>
      <div class="top-right"><span id="asOf">Loading</span></div>
    </header>
    <main>
      <div id="filterHost"></div>
      <p class="chart-note" id="dateNote">Dates filter on the opportunity created date (ET).</p>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Sales · Sweeper/Rehash</div>
          <h1>Diamond — Opportunity List</h1>
          <p class="subtitle">One row per opportunity on a contact whose Sweeper/Rehash Last Name is Diamond. Newest created date first. The row count matches Diamond Sweeper Opps created for the same dates. <a class="link" href="/api/diamond_sweeper">Diamond Sweeper</a></p>
        </div>
      </div>
      <section class="panel">
        <div class="panel-head"><h2>Opportunities</h2><div class="meta" id="listMeta"></div></div>
        <div class="panel-body tablewrap" id="listTable"><p class="chart-note">Loading…</p></div>
      </section>
    </main>
    <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span>America/New_York</span></footer>
  </div>
  <script>
    const ALL_TIME_START = "2025-01-01";
    let requestToken = 0;
    function esc(value) {
      return String(value == null ? "" : value).replace(/[&<>"]/g, function (ch) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch];
      });
    }
    function nyToday() {
      return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    }
    function isAllTime(start, end) {
      return start === ALL_TIME_START && end === nyToday();
    }
    function readRange() {
      const params = new URLSearchParams(location.search);
      const start = params.get("start") || "";
      const end = params.get("end") || "";
      if (!start && !end) return { allTime: true, start: ALL_TIME_START, end: nyToday() };
      const nextStart = start || ALL_TIME_START;
      const nextEnd = end || nyToday();
      return { allTime: isAllTime(nextStart, nextEnd), start: nextStart, end: nextEnd };
    }
    function renderFilters() {
      const range = readRange();
      const host = document.getElementById("filterHost");
      const presetRange = range.allTime ? { start: "", end: "" } : { start: range.start, end: range.end };
      let presets = window.hsOpsPresetButtons ? window.hsOpsPresetButtons(presetRange) : "";
      const allPressed = range.allTime ? "true" : "false";
      const allBtn = '<button type="button" class="date-preset' + (range.allTime ? " active" : "") + '" data-preset="alltime" aria-pressed="' + allPressed + '">All time</button>';
      if (presets.indexOf('class="date-presets"') !== -1) {
        presets = presets.replace(">", ">" + allBtn);
      } else {
        presets = '<div class="date-presets" role="group" aria-label="Quick date ranges">' + allBtn + "</div>";
      }
      host.innerHTML = '<div class="global-filterbar"><div class="filter-controls">' +
        '<label>From<input id="dStart" type="date" aria-label="Start date" value="' + esc(range.start) + '"></label>' +
        '<label>To<input id="dEnd" type="date" aria-label="End date" value="' + esc(range.end) + '"></label>' +
        "</div>" + presets +
        '<div class="filter-chips"><span>' + (range.allTime ? "All time" : esc(range.start) + " – " + esc(range.end)) + " · opportunity created date (ET)</span></div></div>";
      document.getElementById("dStart").addEventListener("change", function () { applyDates(false); });
      document.getElementById("dEnd").addEventListener("change", function () { applyDates(false); });
      host.querySelectorAll("[data-preset]").forEach(function (button) {
        button.addEventListener("click", function () {
          const preset = button.getAttribute("data-preset");
          if (preset === "alltime") {
            applyDates(true);
            return;
          }
          const next = window.hsOpsPresetRange(preset);
          document.getElementById("dStart").value = next.start;
          document.getElementById("dEnd").value = next.end;
          applyDates(false);
        });
      });
    }
    function applyDates(allTime) {
      const today = nyToday();
      const start = allTime ? "" : (document.getElementById("dStart").value || today);
      const end = allTime ? "" : (document.getElementById("dEnd").value || today);
      const url = new URL(location.href);
      if (!start || !end || isAllTime(start, end)) {
        url.searchParams.delete("start");
        url.searchParams.delete("end");
      } else {
        url.searchParams.set("start", start);
        url.searchParams.set("end", end);
      }
      history.replaceState(null, "", url.toString());
      renderFilters();
      load();
    }
    function nameCell(row) {
      const name = row.name || "—";
      if (!row.opportunityUrl) return esc(name);
      return '<a href="' + esc(row.opportunityUrl) + '" target="_blank" rel="noopener noreferrer">' + esc(name) + "</a>";
    }
    function paint(payload) {
      const start = payload.start || "";
      const end = payload.end || "";
      document.getElementById("asOf").textContent = (start && end ? start + " – " + end + " · " : "") + "America/New_York";
      const rows = payload.rows || [];
      document.getElementById("listMeta").textContent = String(payload.row_count == null ? rows.length : payload.row_count) + " opportunities";
      if (!rows.length) {
        document.getElementById("listTable").innerHTML = '<p class="chart-note">No Diamond opportunities created in this range.</p>';
        return;
      }
      const body = rows.map(function (row) {
        return "<tr><td>" + nameCell(row) + "</td><td>" + esc(row.appointmentOutcome || "—") + "</td><td>" + esc(row.appointmentAt || "") + "</td><td>" + esc(row.phone || "") + "</td></tr>";
      }).join("");
      document.getElementById("listTable").innerHTML = "<table><thead><tr><th>Name</th><th>Appointment outcome</th><th>Appointment date and time</th><th>Phone</th></tr></thead><tbody>" + body + "</tbody></table>";
    }
    function showUnavailable() {
      document.getElementById("asOf").textContent = "Unavailable";
      document.getElementById("listMeta").textContent = "";
      document.getElementById("listTable").innerHTML = '<p class="chart-note">Diamond opportunity list could not be read.</p>';
    }
    async function load() {
      const token = ++requestToken;
      const range = readRange();
      if (window.HappySolarLoading) window.HappySolarLoading.begin("view");
      const params = new URLSearchParams();
      params.set("start", range.start);
      params.set("end", range.end);
      params.set("pipeline_scope", "all");
      let response;
      try {
        response = await fetch("/api/metrics/diamond_opp_list?" + params.toString(), { credentials: "same-origin" });
      } catch (error) {
        if (error && error.name === "AbortError") return;
        if (token !== requestToken) return;
        showUnavailable();
        return;
      }
      if (token !== requestToken) return;
      if (!response.ok) {
        showUnavailable();
        return;
      }
      let payload;
      try {
        payload = await response.json();
      } catch (error) {
        if (error && error.name === "AbortError") return;
        if (token !== requestToken) return;
        showUnavailable();
        return;
      }
      if (token !== requestToken) return;
      paint(payload);
    }
    renderFilters();
    load();
  </script>
</body>
</html>"""
    return html.replace("__NAV_CSS__", nav_css).replace("__NAV_HTML__", nav_html)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
