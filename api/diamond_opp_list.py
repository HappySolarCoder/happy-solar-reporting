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
  <style>
    .list-table { width: 100%; border-collapse: collapse; }
    .list-table th, .list-table td { text-align: left; padding: 9px 10px; border-bottom: 1px solid #1b384c; vertical-align: top; }
    .list-table th { background: #0a2236; white-space: nowrap; }
    .list-table th.sortable button {
      appearance: none;
      background: transparent;
      border: 0;
      padding: 0;
      margin: 0;
      color: inherit;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .list-table th.sortable button:hover,
    .list-table th.sortable button:focus-visible { color: #d8ffe8; }
    .list-table .sort-ind { color: #3ddc84; font-weight: 900; }
  </style>
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
          <p class="subtitle">One row per opportunity on a contact whose Sweeper/Rehash Last Name is Diamond. Sorted by appointment date and time, latest first. Opportunities with no appointment are at the bottom. Opportunities on the Sweeper pipeline are left off this list. <a class="link" href="/api/diamond_sweeper">Diamond Sweeper</a></p>
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
    let currentRows = [];
    let sortKey = "appointment";
    let sortDir = "desc";
    const COLUMNS = [
      { key: "name", label: "Name" },
      { key: "pipeline", label: "Pipeline" },
      { key: "appointmentOutcome", label: "Appointment outcome" },
      { key: "appointment", label: "Appointment date and time", kind: "date" },
      { key: "phone", label: "Phone" }
    ];
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
    function columnRaw(row, key) {
      if (key === "appointment") {
        const iso = row.appointmentAtIso || "";
        if (!iso) return null;
        const ms = Date.parse(iso);
        return Number.isNaN(ms) ? null : ms;
      }
      if (key === "name") return row.name || "";
      if (key === "pipeline") return row.pipeline || "";
      if (key === "appointmentOutcome") return row.appointmentOutcome || "";
      if (key === "phone") return row.phone || "";
      return "";
    }
    function compareRows(a, b) {
      const col = COLUMNS.filter(function (item) { return item.key === sortKey; })[0] || COLUMNS[3];
      const av = columnRaw(a, col.key);
      const bv = columnRaw(b, col.key);
      const aEmpty = av == null || av === "";
      const bEmpty = bv == null || bv === "";
      if (aEmpty !== bEmpty) return aEmpty ? 1 : -1;
      let cmp = 0;
      if (!aEmpty) {
        if (col.kind === "date") cmp = av - bv;
        else cmp = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
      }
      if (cmp !== 0) return sortDir === "asc" ? cmp : -cmp;
      return String(a.opportunityId || "").localeCompare(String(b.opportunityId || ""));
    }
    function headerCell(col) {
      const active = col.key === sortKey;
      const arrow = active ? (sortDir === "asc" ? "▲" : "▼") : "";
      const aria = active ? (sortDir === "asc" ? "ascending" : "descending") : "none";
      const mark = arrow ? ' <span class="sort-ind" aria-hidden="true">' + arrow + "</span>" : "";
      return '<th class="sortable" aria-sort="' + aria + '"><button type="button" data-sort="' + esc(col.key) + '">' + esc(col.label) + mark + "</button></th>";
    }
    function cellHtml(row, key) {
      if (key === "name") return nameCell(row);
      if (key === "appointment") return esc(row.appointmentAt || "");
      if (key === "pipeline") return esc(row.pipeline || "");
      if (key === "appointmentOutcome") return esc(row.appointmentOutcome || "—");
      if (key === "phone") return esc(row.phone || "");
      return "";
    }
    function paintTable() {
      const rows = currentRows.slice().sort(compareRows);
      const table = document.getElementById("listTable");
      if (!rows.length) {
        table.innerHTML = '<p class="chart-note">No Diamond opportunities created in this range.</p>';
        return;
      }
      const head = COLUMNS.map(headerCell).join("");
      const body = rows.map(function (row) {
        return "<tr>" + COLUMNS.map(function (col) { return "<td>" + cellHtml(row, col.key) + "</td>"; }).join("") + "</tr>";
      }).join("");
      table.innerHTML = '<table class="list-table"><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table>";
      table.querySelectorAll("button[data-sort]").forEach(function (button) {
        button.addEventListener("click", function () {
          const key = button.getAttribute("data-sort");
          if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
          else {
            sortKey = key;
            sortDir = key === "appointment" ? "desc" : "asc";
          }
          paintTable();
        });
      });
    }
    function paint(payload) {
      const start = payload.start || "";
      const end = payload.end || "";
      document.getElementById("asOf").textContent = (start && end ? start + " – " + end + " · " : "") + "America/New_York";
      const rows = payload.rows || [];
      document.getElementById("listMeta").textContent = String(payload.row_count == null ? rows.length : payload.row_count) + " opportunities";
      currentRows = rows.slice();
      sortKey = "appointment";
      sortDir = "desc";
      paintTable();
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
