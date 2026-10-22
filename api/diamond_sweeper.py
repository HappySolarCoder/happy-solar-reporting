# -*- coding: utf-8 -*-

"""Vercel Python function: /api/diamond_sweeper

Diamond — Sweeper/Rehash. Open in the Data Center with no password gate,
same as Solar Consultant Overview and Company Overview.

Month-to-date America/New_York by default, using the shared date controls.
Numbers come from /api/metrics/diamond_sweeper.
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
    nav_html = render_dashboard_nav("diamond_sweeper")
    html = """<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Diamond — Sweeper/Rehash</title>
  <style>__NAV_CSS__</style>
</head>
<body class="oc-root" data-oc-native-filters="1">
  __NAV_HTML__
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>Diamond — Sweeper/Rehash</strong></div>
      <div class="top-right"><span id="asOf">Loading</span></div>
    </header>
    <main>
      <div id="filterHost"></div>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Sales · Sweeper/Rehash</div>
          <h1>Diamond — Sweeper/Rehash</h1>
          <p class="subtitle">Tyler Diamond. Opportunities on contacts whose Sweeper/Rehash Last Name is Diamond. Dates are America/New_York. Territory and lead source filters from other pages do not change these counts.</p>
          <p class="chart-note"><a class="link" id="oppListLink" href="/api/diamond_opp_list">Diamond — Opportunity List</a></p>
        </div>
      </div>
      <div class="kpis" style="--n:4" id="scorecard" aria-live="polite">
        <div class="kpi"><div class="label">Opps created</div><div class="number" id="oppsCreated">—</div><div class="sub" id="oppsSub">Appointments set</div></div>
        <div class="kpi"><div class="label">Demos</div><div class="number" id="demos">—</div><div class="sub" id="demosSub">Demo appointments</div></div>
        <div class="kpi"><div class="label">Demo %</div><div class="number" id="demoPct">—</div><div class="sub" id="demoSub">Demos / appointments ran</div></div>
        <div class="kpi"><div class="label">Opp2Prelim</div><div class="number" id="opp2">—</div><div class="sub" id="opp2Sub">Sales / appointments ran</div></div>
      </div>
      <section class="panel">
        <div class="panel-head"><h2>How these numbers are counted</h2></div>
        <div class="panel-body">
          <p class="chart-note">Opps created are opportunities created in the selected dates on a contact whose Sweeper/Rehash Last Name is Diamond. That is the appointment-set credit for this sweeper. Demos are appointments in that window marked as a demo on a contact with the same name. Demo % is demos divided by appointments ran. Opp2Prelim is sales divided by appointments ran. Both rates match Company Overview Sweeper/Rehash and are blank when no appointments ran. Setter last name alone does not count.</p>
          <p class="chart-note">Source: Firestore <code>ghl_opportunities_v2</code>, <code>ghl_contacts_v2</code>, and <code>ghl_pipelines_v2</code> from the GoHighLevel sync. Sweeper/Rehash Last Name is contact custom field HWfjOp8MvE6soxBAL75f, then the same field on the opportunity. Appointments use opportunities created across pipelines, including Virtual. A demo is Appointment Outcome Sit, any Demo stage, or Sold. One Legger is not a demo. New Appointment has not run. An earlier FMA sit on the contact does not hide the later sweeper demo. Sales use the locked sales grain, one contact each, filtered to this name.</p>
        </div>
      </section>
      <div class="grid equal" style="margin-top:18px">
        <section class="panel">
          <div class="panel-head"><h2>Opportunities created</h2><div class="meta" id="createdMeta"></div></div>
          <div class="panel-body tablewrap" id="createdTable"><p class="chart-note">Loading…</p></div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Appointments ran</h2><div class="meta" id="demoMeta"></div></div>
          <div class="panel-body tablewrap" id="demoTable"><p class="chart-note">Loading…</p></div>
        </section>
      </div>
    </main>
    <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span>America/New_York</span></footer>
  </div>
  <script>
    let requestToken = 0;
    function esc(value) {
      return String(value == null ? "" : value).replace(/[&<>"]/g, function (ch) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch];
      });
    }
    function nyToday() {
      return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    }
    function filters() {
      const today = nyToday();
      const fallback = { start: today.slice(0, 8) + "01", end: today, territory: "All", source: "All" };
      return window.hsOpsReadFilters ? window.hsOpsReadFilters() : fallback;
    }
    function renderFilters() {
      const f = filters();
      const host = document.getElementById("filterHost");
      const presets = window.hsOpsPresetButtons ? window.hsOpsPresetButtons(f) : "";
      host.innerHTML = '<div class="global-filterbar"><div class="filter-controls">' +
        '<label>From<input id="dStart" type="date" aria-label="Start date" value="' + esc(f.start) + '"></label>' +
        '<label>To<input id="dEnd" type="date" aria-label="End date" value="' + esc(f.end) + '"></label>' +
        '<button type="button" class="filter-reset" id="dReset">This month</button></div>' +
        presets +
        '<div class="filter-chips"><span>' + esc(f.start) + " – " + esc(f.end) + " · America/New_York · Sweeper/Rehash Last Name = Diamond</span></div></div>";
      document.getElementById("dStart").addEventListener("change", function () { applyDates(); });
      document.getElementById("dEnd").addEventListener("change", function () { applyDates(); });
      document.getElementById("dReset").addEventListener("click", function () {
        const today = nyToday();
        document.getElementById("dStart").value = today.slice(0, 8) + "01";
        document.getElementById("dEnd").value = today;
        applyDates();
      });
      const listLink = document.getElementById("oppListLink");
      if (listLink) {
        const current = filters();
        listLink.href = "/api/diamond_opp_list?start=" + encodeURIComponent(current.start) + "&end=" + encodeURIComponent(current.end);
      }
      host.querySelectorAll("[data-preset]").forEach(function (button) {
        button.addEventListener("click", function () {
          const range = window.hsOpsPresetRange(button.getAttribute("data-preset"));
          document.getElementById("dStart").value = range.start;
          document.getElementById("dEnd").value = range.end;
          applyDates();
        });
      });
    }
    function applyDates() {
      const today = nyToday();
      const current = filters();
      const start = document.getElementById("dStart").value || today.slice(0, 8) + "01";
      const end = document.getElementById("dEnd").value || today;
      const next = { start: start, end: end, territory: current.territory || "All", source: current.source || "All" };
      if (window.hsOpsWriteFilters) window.hsOpsWriteFilters(next);
      const url = new URL(location.href);
      url.searchParams.set("start", start);
      url.searchParams.set("end", end);
      history.replaceState(null, "", url.toString());
      renderFilters();
      load();
    }
    function pct(value) {
      return value == null || value === "" ? "—" : Number(value).toFixed(1) + "%";
    }
    function outcomeLabel(row) {
      if (row && typeof row === "object") {
        if (row.countsAsDemo) return "Demo";
        if (row.disposition === "Sit" || row.disposition === "No Sit") return "No demo";
        return "Not ran";
      }
      if (row === "Sit") return "Demo";
      if (row === "No Sit") return "No demo";
      return row || "—";
    }
    function table(headers, rowsHtml, empty) {
      if (!rowsHtml) return '<p class="chart-note">' + empty + "</p>";
      return "<table><thead><tr>" + headers.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>" + rowsHtml + "</tbody></table>";
    }
    function paint(payload) {
      document.getElementById("oppsCreated").textContent = payload.opps_created == null ? "—" : String(payload.opps_created);
      document.getElementById("demos").textContent = payload.demos == null ? "—" : String(payload.demos);
      document.getElementById("demoPct").textContent = pct(payload.demo_pct);
      document.getElementById("opp2").textContent = pct(payload.opp2prelim);
      const ran = payload.ran == null ? "—" : String(payload.ran);
      const sales = payload.sales == null ? "—" : String(payload.sales);
      document.getElementById("oppsSub").textContent = "Appointments set for Diamond";
      document.getElementById("demosSub").textContent = payload.demos + " demos · " + ran + " appointments ran";
      document.getElementById("demoSub").textContent = payload.demos + " demos / " + ran + " ran";
      document.getElementById("opp2Sub").textContent = sales + " sales / " + ran + " ran";
      const start = payload.start || "";
      const end = payload.end || "";
      document.getElementById("asOf").textContent = (start && end ? start + " – " + end + " · " : "") + "America/New_York";
      const created = payload.created_rows || [];
      const demos = payload.demo_rows || [];
      document.getElementById("createdMeta").textContent = created.length + " opportunities";
      document.getElementById("demoMeta").textContent = demos.length + " ran";
      document.getElementById("createdTable").innerHTML = table(
        ["Opportunity", "Pipeline", "Pipeline stage", "Created"],
        created.slice(0, 200).map(function (row) {
          return "<tr><td><code>" + esc(String(row.opportunityId || "").replace(/~cycle[0-9]+$/, "")) + "</code></td><td>" + esc(row.pipeline || "—") + "</td><td>" + esc(row.pipelineStage || "—") + "</td><td>" + esc(row.createdAt || "—") + "</td></tr>";
        }).join(""),
        "No Diamond opportunities created in this range."
      );
      document.getElementById("demoTable").innerHTML = table(
        ["Opportunity", "Pipeline", "Demo rate", "Pipeline stage", "Appointment"],
        demos.slice(0, 200).map(function (row) {
          return "<tr><td><code>" + esc(String(row.opportunityId || "").replace(/~cycle[0-9]+$/, "")) + "</code></td><td>" + esc(row.pipeline || "—") + "</td><td>" + esc(outcomeLabel(row)) + "</td><td>" + esc(row.pipelineStage || "—") + "</td><td>" + esc(row.occurredAt || "—") + "</td></tr>";
        }).join(""),
        "No Diamond appointments ran in this range."
      );
    }
    function showUnavailable() {
      ["oppsCreated", "demos", "demoPct", "opp2"].forEach(function (id) {
        document.getElementById(id).textContent = "—";
      });
      document.getElementById("asOf").textContent = "Unavailable";
      document.getElementById("createdTable").innerHTML = '<p class="chart-note">Diamond sweeper metrics could not be read.</p>';
      document.getElementById("demoTable").innerHTML = '<p class="chart-note">Diamond sweeper metrics could not be read.</p>';
    }
    async function load() {
      const token = ++requestToken;
      const f = filters();
      if (window.HappySolarLoading) window.HappySolarLoading.begin("view");
      const params = new URLSearchParams();
      params.set("start", f.start);
      params.set("end", f.end);
      params.set("pipeline_scope", "all");
      let response;
      try {
        response = await fetch("/api/metrics/diamond_sweeper?" + params.toString());
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
