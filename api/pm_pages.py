# -*- coding: utf-8 -*-

"""Shared Operations Control pages for Project Management hub and Hold / Cancelled.

Both pages use the same shell as Diamond — Opportunity List: navy theme,
dashboard nav, and the shared date presets. They stay inside a Bloom iframe.
GoHighLevel is the only target=_blank navigation, and only on Hold / Cancelled
phone numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav

FRAME_ANCESTORS = "frame-ancestors 'self' https://bloom.happyslr.com https://*.happyslr.com"


def send_dashboard_html(handler, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Security-Policy", FRAME_ANCESTORS)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _shell(nav_key: str, title: str, body: str, script: str) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav(nav_key)
    html = """<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>__NAV_CSS__</style>
  <style>
    .lane-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 10px; }
    .stage.active { border-color: var(--cyan); box-shadow: inset 0 0 0 1px var(--cyan); }
    .stage small { display: block; margin-top: 6px; }
    .note-cell { white-space: normal; min-width: 200px; max-width: 320px; }
    .rep-menu { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
    .rep-menu label { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #b9cbd9; }
    tr.overdue-row td { background: #3b2b3a !important; }
    .chart-svg { width: 100%; height: auto; }
    .chart-svg a { cursor: pointer; }
  </style>
</head>
<body class="oc-root" data-oc-native-filters="1">
  __NAV_HTML__
  __BODY__
  <script>
    __SCRIPT__
  </script>
</body>
</html>"""
    return (
        html.replace("__TITLE__", title)
        .replace("__NAV_CSS__", nav_css)
        .replace("__NAV_HTML__", nav_html)
        .replace("__BODY__", body)
        .replace("__SCRIPT__", script)
    )


_SHARED_JS = r"""
    function esc(value) {
      return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
      });
    }
    function nyToday() {
      return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    }
    function monthEnd(monthKey) {
      const parts = String(monthKey || "").split("-");
      if (parts.length !== 2) return "";
      const year = Number(parts[0]);
      const month = Number(parts[1]);
      if (!year || month < 1 || month > 12) return "";
      const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
      return parts[0] + "-" + String(month).padStart(2, "0") + "-" + String(last).padStart(2, "0");
    }
    function readRange() {
      const params = new URLSearchParams(location.search);
      const start = params.get("start") || "";
      const end = params.get("end") || "";
      const createdMonth = params.get("createdMonth") || "";
      if (!start && !end && /^\d{4}-\d{2}$/.test(createdMonth)) {
        return { allTime: false, start: createdMonth + "-01", end: monthEnd(createdMonth), createdMonth: createdMonth };
      }
      if (!start && !end) return { allTime: true, start: "", end: "", createdMonth: "" };
      return { allTime: false, start: start, end: end || nyToday(), createdMonth: "" };
    }
    function sameOriginPath(path, params) {
      const url = new URL(path, location.origin);
      Object.keys(params || {}).forEach(function (key) {
        if (params[key]) url.searchParams.set(key, params[key]);
      });
      if (document.documentElement.classList.contains("oc-embedded")) url.searchParams.set("embed", "1");
      return url.pathname + url.search;
    }
    function renderDateFilters(note) {
      const range = readRange();
      const host = document.getElementById("filterHost");
      const presetRange = range.allTime ? { start: "", end: "" } : { start: range.start, end: range.end };
      let presets = window.hsOpsPresetButtons ? window.hsOpsPresetButtons(presetRange) : "";
      const allBtn = '<button type="button" class="date-preset' + (range.allTime ? " active" : "") + '" data-preset="alltime" aria-pressed="' + (range.allTime ? "true" : "false") + '">All time</button>';
      if (presets.indexOf('class="date-presets"') !== -1) presets = presets.replace(">", ">" + allBtn);
      else presets = '<div class="date-presets" role="group" aria-label="Quick date ranges">' + allBtn + "</div>";
      const chip = range.allTime ? "All time" : (esc(range.start) + " – " + esc(range.end));
      host.innerHTML = '<div class="global-filterbar"><div class="filter-controls">' +
        '<label>From<input id="dStart" type="date" aria-label="Start date" value="' + esc(range.start) + '"></label>' +
        '<label>To<input id="dEnd" type="date" aria-label="End date" value="' + esc(range.end) + '"></label>' +
        "</div>" + presets +
        '<div class="filter-chips"><span>' + chip + " · " + note + "</span></div></div>";
      document.getElementById("dStart").addEventListener("change", function () { applyDates(false); });
      document.getElementById("dEnd").addEventListener("change", function () { applyDates(false); });
      host.querySelectorAll("[data-preset]").forEach(function (button) {
        button.addEventListener("click", function () {
          const preset = button.getAttribute("data-preset");
          if (preset === "alltime") { applyDates(true); return; }
          const next = window.hsOpsPresetRange(preset);
          document.getElementById("dStart").value = next.start;
          document.getElementById("dEnd").value = next.end;
          applyDates(false);
        });
      });
    }
    function applyDates(allTime) {
      const url = new URL(location.href);
      url.searchParams.delete("createdMonth");
      if (allTime) {
        url.searchParams.delete("start");
        url.searchParams.delete("end");
      } else {
        const today = nyToday();
        url.searchParams.set("start", document.getElementById("dStart").value || today);
        url.searchParams.set("end", document.getElementById("dEnd").value || today);
      }
      history.replaceState(null, "", url.pathname + url.search + url.hash);
      renderDateFilters(window.pmDateNote || "project created date");
      if (window.pmRender) window.pmRender();
    }
    function createdDay(row) {
      const iso = String((row && row.created_at_iso) || "");
      return iso.length >= 10 ? iso.slice(0, 10) : "";
    }
    function inRange(row, range) {
      if (!range || range.allTime) return true;
      const day = createdDay(row);
      if (!day) return false;
      if (range.start && day < range.start) return false;
      if (range.end && day > range.end) return false;
      return true;
    }
"""


def render_project_management_hub_html() -> str:
    body = """
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>Project Hub</strong></div>
      <div class="top-right"><span id="asOf">Loading</span></div>
    </header>
    <main>
      <div id="filterHost"></div>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Project management</div>
          <h1>Project Management Hub</h1>
          <p class="subtitle" id="pageSub">Live Monday Process Board - NY. Funnel stages are Essential View Pipeline Phase. Cancelled comes from the Cancelled and Cancellation Queue groups. Assigned rep comes from Essential View S-Rep, then the board Sales Rep field.</p>
        </div>
        <div class="headbuttons">
          <button type="button" id="openCancellationModal">Cancellation trends</button>
          <a class="link" id="holdLink" href="/api/hold_cancelled">Hold / Cancelled</a>
        </div>
      </div>
      <div class="kpis" style="--n:4">
        <div class="kpi"><div class="label">Active jobs</div><div class="number" id="activeJobsValue">—</div><div class="sub" id="activeJobsDetail">Onboarding, EP Ops, and EP Installation. Hold/cancel excluded.</div></div>
        <div class="kpi"><div class="label">Held or cancelled</div><div class="number" id="heldJobsValue">—</div><div class="sub" id="heldJobsDetail">Validation Hold, HOLD, HOLD 2026, and Cancelled.</div></div>
        <div class="kpi"><div class="label">Jobs over SLA</div><div class="number" id="overSlaValue">—</div><div class="sub" id="overSlaDetail">Days in bucket come from Date moved to Phase.</div></div>
        <div class="kpi"><div class="label">Median install time</div><div class="number" id="installTimeValue">—</div><div class="sub" id="installTimeDetail">Days from project creation to the earliest install date.</div></div>
      </div>
      <div id="laneHost"></div>
      <section class="panel" style="margin-bottom:18px">
        <div class="panel-head"><h2>Filters</h2><div class="panel-actions"><button type="button" id="overdueToggle">Show overdue only</button><button type="button" id="resetFilters">Reset</button></div></div>
        <div class="panel-body">
          <div class="filter-controls">
            <label>Search<input id="searchFilter" type="search" placeholder="Name, address, status, notes" aria-label="Search"></label>
            <label>Bucket<select id="stageFilter" aria-label="Bucket"><option value="">All buckets</option></select></label>
          </div>
          <div class="rep-menu" id="repMenu"></div>
          <p class="chart-note" id="stageDetail"></p>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Project list</h2><div class="meta" id="tableMeta"></div></div>
        <div class="panel-body tablewrap" id="tableHost"><p class="chart-note">Loading…</p></div>
      </section>
    </main>
    <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span id="generatedAt">Monday Process Board NY</span></footer>
  </div>
  <div class="overlay" id="cancellationModal" hidden>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="cancellationTitle">
      <div class="modal-head">
        <h2 id="cancellationTitle">Cancellation percentage</h2>
        <button type="button" id="closeCancellationModal" aria-label="Close cancellation trends">Close</button>
      </div>
      <div class="modal-body">
        <p>Monthly cancellation rate by project created month. Cancelled jobs created that month, divided by every project created that month. Month labels open Hold / Cancelled in this window.</p>
        <div class="rep-menu" id="cancelRepMenu"></div>
        <svg id="cancellationChart" class="chart-svg" viewBox="0 0 900 320" role="img" aria-label="Cancellation percentage by month"></svg>
        <div class="kpis" style="--n:3">
          <div class="kpi"><div class="label">Latest month</div><div class="number" id="cancellationLatestMonth">—</div></div>
          <div class="kpi"><div class="label">Latest cancel %</div><div class="number" id="cancellationLatestRate">—</div></div>
          <div class="kpi"><div class="label">Latest counts</div><div class="number" id="cancellationLatestCounts">—</div></div>
        </div>
        <h3>Stage before cancellation</h3>
        <div id="cancellationStageList"></div>
      </div>
    </div>
  </div>
"""
    script = _SHARED_JS + r"""
    window.pmDateNote = "project created date (ET)";
    const ACTIVE = { onboarding: 1, ep_ops: 1, ep_installation: 1 };
    const LANES = [
      ["onboarding", "Onboarding", "Project Verification → Site Evaluation → Site Review."],
      ["ep_ops", "EP Ops", "ENG/FIN/PERM, ESOW / Final Approval, Install Ready."],
      ["ep_installation", "EP Installation", "Being Installed → Build / Elec Inspection → Post Install → PTO → Finalized."],
      ["hold_cancel", "Hold / Cancel", "Validation Hold, HOLD / HOLD 2026, and Cancelled."]
    ];
    let allRows = [];
    let stageCards = [];
    let filterState = { overdueOnly: false };
    function selectedReps(menuId) {
      const menu = document.getElementById(menuId);
      return Array.prototype.map.call(menu.querySelectorAll("input:checked"), function (input) {
        return String(input.value || "").trim().toLowerCase();
      });
    }
    function repOk(row, menuId) {
      const reps = selectedReps(menuId);
      if (!reps.length) return true;
      return reps.indexOf(String(row.assigned_rep || "").trim().toLowerCase()) !== -1;
    }
    function filteredRows(ignoreStage) {
      const range = readRange();
      const search = String(document.getElementById("searchFilter").value || "").trim().toLowerCase();
      const stage = ignoreStage ? "" : String(document.getElementById("stageFilter").value || "").trim().toLowerCase();
      return allRows.filter(function (row) {
        if (filterState.overdueOnly && !row.is_over_sla) return false;
        if (stage && String(row.pm_bucket || "").trim().toLowerCase() !== stage) return false;
        if (!repOk(row, "repMenu")) return false;
        if (!inRange(row, range)) return false;
        if (search) {
          const hay = [row.pm_bucket, row.process_bucket, row.display_name, row.assigned_rep, row.address, row.zip_code, row.permit_ahj, row.permit_phone, row.permit_tat, row.site_survey_date, row.first_installed_on, row.task_status, row.calc_status, row.finance_status, row.permit_status, row.interconnection_status, row.monitoring_approval, row.monitoring_status, row.process_board_note, row.essential_view_note].join(" ").toLowerCase();
          if (hay.indexOf(search) === -1) return false;
        }
        return true;
      });
    }
    function summarize(list) {
      const cycles = list.map(function (row) {
        const raw = String(row.install_cycle_days == null ? "" : row.install_cycle_days).trim();
        if (!raw) return null;
        const value = Number(raw);
        return Number.isFinite(value) ? value : null;
      }).filter(function (value) { return value != null; }).sort(function (a, b) { return a - b; });
      let median = null;
      if (cycles.length) {
        const middle = Math.floor(cycles.length / 2);
        median = cycles.length % 2 ? cycles[middle] : Math.round(((cycles[middle - 1] + cycles[middle]) / 2) * 10) / 10;
      }
      return {
        active: list.filter(function (row) { return ACTIVE[String(row.section || "")]; }).length,
        held: list.filter(function (row) { return String(row.section || "") === "hold_cancel"; }).length,
        overdue: list.filter(function (row) { return row.is_over_sla; }).length,
        median: median,
        sample: cycles.length
      };
    }
    function cardsFor(list) {
      const counts = {};
      const overdue = {};
      list.forEach(function (row) {
        const bucket = String(row.pm_bucket || "");
        counts[bucket] = (counts[bucket] || 0) + 1;
        if (row.is_over_sla) overdue[bucket] = (overdue[bucket] || 0) + 1;
      });
      return stageCards.map(function (card) {
        return Object.assign({}, card, { count: counts[card.stage] || 0, overdue_count: overdue[card.stage] || 0 });
      });
    }
    function renderReps(reps) {
      const html = (reps || []).map(function (name) {
        return '<label><input type="checkbox" value="' + esc(name) + '"> ' + esc(name) + "</label>";
      }).join("");
      document.getElementById("repMenu").innerHTML = html || '<span class="chart-note">No assigned reps</span>';
      document.getElementById("cancelRepMenu").innerHTML = html;
      document.querySelectorAll("#repMenu input, #cancelRepMenu input").forEach(function (input) {
        input.addEventListener("change", function () {
          if (input.closest("#cancelRepMenu")) renderCancellation();
          else window.pmRender();
        });
      });
    }
    function renderOverview() {
      const summary = summarize(filteredRows(true));
      document.getElementById("activeJobsValue").textContent = String(summary.active);
      document.getElementById("activeJobsDetail").textContent = "Happy Slr jobs in Onboarding, EP Ops, and EP Installation. Hold/cancel excluded. Based on " + String(filteredRows(true).length) + " filtered project(s).";
      document.getElementById("heldJobsValue").textContent = String(summary.held);
      document.getElementById("heldJobsDetail").textContent = "Jobs in the hold/cancel lane. Based on " + String(filteredRows(true).length) + " filtered project(s).";
      document.getElementById("overSlaValue").textContent = String(summary.overdue);
      document.getElementById("installTimeValue").textContent = summary.median == null ? "—" : String(summary.median);
      document.getElementById("installTimeDetail").textContent = "Median days from project creation to the earliest Essential View install date across " + String(summary.sample) + " filtered project(s) with an install date.";
    }
    function renderLanes() {
      const cards = cardsFor(filteredRows(true));
      const selected = document.getElementById("stageFilter").value;
      const prior = selected;
      const options = ['<option value="">All buckets</option>'].concat(cards.map(function (card) {
        return '<option value="' + esc(card.stage) + '">' + esc(card.stage) + " (" + esc(card.count) + ")</option>";
      }));
      const stageFilter = document.getElementById("stageFilter");
      stageFilter.innerHTML = options.join("");
      if (cards.some(function (card) { return card.stage === prior; })) stageFilter.value = prior;
      document.getElementById("laneHost").innerHTML = LANES.map(function (lane) {
        const laneCards = cards.filter(function (card) { return card.section === lane[0]; });
        const buttons = laneCards.map(function (card) {
          const active = selected === card.stage ? " active" : "";
          const sla = card.sla_days ? ("SLA: " + card.sla_days + "d") : "SLA: not set";
          return '<button type="button" class="stage' + active + '" data-stage="' + esc(card.stage) + '"><span>' + esc(card.display_label || card.stage) + '</span><b>' + esc(card.count) + '</b><small>' + esc(sla) + " · " + esc(card.overdue_count || 0) + " overdue</small></button>";
        }).join("");
        return '<section class="panel" style="margin-bottom:14px"><div class="panel-head"><h2>' + esc(lane[1]) + '</h2><div class="meta">' + esc(lane[2]) + '</div></div><div class="panel-body"><div class="lane-grid">' + buttons + "</div></div></section>";
      }).join("");
      document.querySelectorAll("#laneHost .stage").forEach(function (button) {
        button.addEventListener("click", function () {
          const stage = button.getAttribute("data-stage") || "";
          stageFilter.value = stageFilter.value === stage ? "" : stage;
          filterState.overdueOnly = false;
          const slug = stageFilter.value ? "#" + stageFilter.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") : "";
          history.replaceState(null, "", location.pathname + location.search + slug);
          window.pmRender();
        });
      });
    }
    function slaText(row) {
      if (row.sla_days === "" || row.sla_days == null) return "—";
      return String(row.sla_days) + " day" + (Number(row.sla_days) === 1 ? "" : "s") + (row.uses_default_permit_sla ? " (default)" : "");
    }
    function renderTable() {
      const list = filteredRows(false).slice().sort(function (a, b) {
        const stageCmp = String(a.pm_bucket || "").localeCompare(String(b.pm_bucket || ""), undefined, { sensitivity: "base" });
        if (stageCmp) return stageCmp;
        const dayCmp = Number(b.days_in_bucket || 0) - Number(a.days_in_bucket || 0);
        if (dayCmp) return dayCmp;
        return String(a.display_name || "").localeCompare(String(b.display_name || ""), undefined, { sensitivity: "base", numeric: true });
      });
      const overdueShown = list.filter(function (row) { return row.is_over_sla; }).length;
      document.getElementById("tableMeta").textContent = String(list.length) + " of " + String(allRows.length) + " jobs shown · " + String(overdueShown) + " overdue";
      const host = document.getElementById("tableHost");
      if (!list.length) {
        host.innerHTML = '<p class="chart-note">No jobs match the selected filters.</p>';
        return;
      }
      const headers = ["Pipeline Phase", "Name", "Assigned Rep", "Address", "ZIP", "Permit AHJ", "AHJ Phone", "Permit TAT", "Site Survey", "Install Date", "Intake NTP", "Building Status", "Electrical Status", "Permit Status", "Interconnection Status", "Monitoring Approval", "Monitoring Status", "Notes", "Pipeline (source)", "Last Updated", "Days In Bucket", "SLA", "Overdue"];
      const body = list.map(function (row) {
        const name = row.board_url
          ? '<a href="' + esc(row.board_url) + '" target="_blank" rel="noopener">' + esc(row.display_name || "") + "</a>"
          : esc(row.display_name || "");
        const cells = [row.pm_bucket, null, row.assigned_rep, row.address, row.zip_code, row.permit_ahj, row.permit_phone, row.permit_tat, row.site_survey_date, row.first_installed_on, row.task_status, row.calc_status, row.finance_status, row.permit_status, row.interconnection_status, row.monitoring_approval, row.monitoring_status, row.process_board_note, row.essential_view_note, row.created_at_display, row.days_in_bucket || 0, slaText(row), row.is_over_sla ? "Flagged" : "On Time"];
        return '<tr class="' + (row.is_over_sla ? "overdue-row" : "") + '">' + cells.map(function (value, index) {
          const cls = index === 17 || index === 18 ? ' class="note-cell"' : "";
          const html = index === 1 ? name : esc(value);
          return "<td" + cls + ">" + html + "</td>";
        }).join("") + "</tr>";
      }).join("");
      host.innerHTML = "<table><thead><tr>" + headers.map(function (header) { return "<th>" + esc(header) + "</th>"; }).join("") + "</tr></thead><tbody>" + body + "</tbody></table>";
    }
    function renderDetail() {
      const stage = document.getElementById("stageFilter").value;
      const base = filteredRows(true);
      const detail = document.getElementById("stageDetail");
      if (!stage) {
        const overdue = base.filter(function (row) { return row.is_over_sla; }).length;
        detail.textContent = "All buckets. " + String(overdue) + " overdue project(s) across the filtered set.";
        return;
      }
      const rows = base.filter(function (row) { return row.pm_bucket === stage; });
      const overdue = rows.filter(function (row) { return row.is_over_sla; }).length;
      detail.textContent = stage + ": " + String(rows.length) + " job(s), " + String(overdue) + " over SLA.";
    }
    function holdHref() {
      const range = readRange();
      const params = {};
      if (!range.allTime) {
        params.start = range.start;
        params.end = range.end;
      }
      return sameOriginPath("/api/hold_cancelled", params);
    }
    window.pmRender = function () {
      document.getElementById("overdueToggle").classList.toggle("active", filterState.overdueOnly);
      document.getElementById("holdLink").setAttribute("href", holdHref());
      renderOverview();
      renderLanes();
      renderDetail();
      renderTable();
    };
    function percentText(value) {
      return (Math.round(value * 10) / 10).toFixed(1) + "%";
    }
    function cancellationRows() {
      const reps = selectedReps("cancelRepMenu");
      if (!reps.length) return allRows;
      return allRows.filter(function (row) {
        return reps.indexOf(String(row.assigned_rep || "").trim().toLowerCase()) !== -1;
      });
    }
    function cancellationSeries() {
      const monthly = {};
      cancellationRows().forEach(function (row) {
        const monthKey = createdDay(row).slice(0, 7);
        if (!monthKey || monthKey < "2026-01") return;
        if (!monthly[monthKey]) monthly[monthKey] = { monthKey: monthKey, created: 0, cancelled: 0 };
        monthly[monthKey].created += 1;
        if (String(row.pm_bucket || "").trim().toLowerCase() === "cancelled") monthly[monthKey].cancelled += 1;
      });
      const now = new Date();
      const endKey = now.toISOString().slice(0, 7);
      const series = [];
      let year = 2026;
      let month = 1;
      const endYear = Number(endKey.slice(0, 4));
      const endMonth = Number(endKey.slice(5, 7));
      while (year < endYear || (year === endYear && month <= endMonth)) {
        const monthKey = String(year) + "-" + String(month).padStart(2, "0");
        const item = monthly[monthKey] || { monthKey: monthKey, created: 0, cancelled: 0 };
        series.push({ monthKey: monthKey, created: item.created, cancelled: item.cancelled, rate: item.created ? (item.cancelled / item.created) * 100 : 0, label: monthKey.slice(5) + "/" + monthKey.slice(2, 4) });
        month += 1;
        if (month === 13) { month = 1; year += 1; }
      }
      return series;
    }
    function renderCancellation() {
      const series = cancellationSeries();
      const svg = document.getElementById("cancellationChart");
      if (!series.length) { svg.innerHTML = ""; return; }
      const width = 900;
      const height = 320;
      const margin = { top: 28, right: 24, bottom: 42, left: 36 };
      const maxRate = Math.max(10, Math.max.apply(null, series.map(function (point) { return point.rate; })));
      const step = series.length === 1 ? 0 : (width - margin.left - margin.right) / (series.length - 1);
      function x(index) { return margin.left + step * index; }
      function y(rate) { return margin.top + (height - margin.top - margin.bottom) * (1 - rate / maxRate); }
      const path = series.map(function (point, index) { return (index ? "L" : "M") + x(index) + " " + y(point.rate); }).join(" ");
      const reps = selectedReps("cancelRepMenu");
      const marks = series.map(function (point, index) {
        const href = sameOriginPath("/api/hold_cancelled", { createdMonth: point.monthKey, bucket: "Cancelled", reps: reps.join(",") });
        return '<a href="' + esc(href) + '"><circle cx="' + x(index) + '" cy="' + y(point.rate) + '" r="6" fill="#26d9eb"></circle></a>' +
          '<text x="' + x(index) + '" y="' + (y(point.rate) - 10) + '" text-anchor="middle" fill="#d5e8f4" font-size="11">' + esc(percentText(point.rate)) + "</text>" +
          '<a href="' + esc(href) + '"><text x="' + x(index) + '" y="' + (height - 16) + '" text-anchor="middle" fill="#8ef0c8" font-size="11">' + esc(point.label) + "</text></a>";
      }).join("");
      svg.innerHTML = '<path d="' + path + '" fill="none" stroke="#26d9eb" stroke-width="2"></path>' + marks;
      const latest = series.slice().reverse().find(function (point) { return point.created > 0; }) || series[series.length - 1];
      document.getElementById("cancellationLatestMonth").textContent = latest.label;
      document.getElementById("cancellationLatestRate").textContent = percentText(latest.rate);
      document.getElementById("cancellationLatestCounts").textContent = String(latest.cancelled) + " / " + String(latest.created);
      const counts = {};
      cancellationRows().forEach(function (row) {
        if (String(row.pm_bucket || "").trim().toLowerCase() !== "cancelled") return;
        const stage = String(row.cancel_source_stage || "").trim() || "Unknown prior stage";
        counts[stage] = (counts[stage] || 0) + 1;
      });
      const ranked = Object.keys(counts).map(function (stage) { return { stage: stage, count: counts[stage] }; }).sort(function (a, b) { return b.count - a.count || a.stage.localeCompare(b.stage); });
      const total = ranked.reduce(function (sum, item) { return sum + item.count; }, 0);
      const list = document.getElementById("cancellationStageList");
      if (!total) { list.innerHTML = '<p class="chart-note">No cancellation transition history available.</p>'; return; }
      const top = ranked.slice(0, 10);
      const other = ranked.slice(10).reduce(function (sum, item) { return sum + item.count; }, 0);
      if (other) top.push({ stage: "Other historical stages", count: other });
      list.innerHTML = top.map(function (item) {
        const share = ((item.count / total) * 100).toFixed(1);
        return '<div class="statrow"><div><strong>' + esc(item.stage) + '</strong><p>' + share + "%</p></div><div class=\"value\">" + esc(item.count) + "</div></div>";
      }).join("");
    }
    document.getElementById("searchFilter").addEventListener("input", function () { window.pmRender(); });
    document.getElementById("stageFilter").addEventListener("change", function () { window.pmRender(); });
    document.getElementById("overdueToggle").addEventListener("click", function () {
      filterState.overdueOnly = !filterState.overdueOnly;
      window.pmRender();
    });
    document.getElementById("resetFilters").addEventListener("click", function () {
      document.getElementById("searchFilter").value = "";
      document.getElementById("stageFilter").value = "";
      document.querySelectorAll("#repMenu input").forEach(function (input) { input.checked = false; });
      filterState.overdueOnly = false;
      const url = new URL(location.href);
      url.searchParams.delete("start");
      url.searchParams.delete("end");
      url.searchParams.delete("createdMonth");
      history.replaceState(null, "", url.pathname + url.search);
      renderDateFilters(window.pmDateNote);
      window.pmRender();
    });
    document.getElementById("openCancellationModal").addEventListener("click", function () {
      renderCancellation();
      document.getElementById("cancellationModal").hidden = false;
    });
    document.getElementById("closeCancellationModal").addEventListener("click", function () {
      document.getElementById("cancellationModal").hidden = true;
    });
    document.getElementById("cancellationModal").addEventListener("click", function (event) {
      if (event.target.id === "cancellationModal") document.getElementById("cancellationModal").hidden = true;
    });
    async function load() {
      renderDateFilters(window.pmDateNote);
      let response;
      try {
        response = await fetch("/api/metrics/project_management", { credentials: "same-origin" });
      } catch (error) {
        document.getElementById("tableHost").innerHTML = '<p class="chart-note">Project management data is unavailable.</p>';
        document.getElementById("asOf").textContent = "Unavailable";
        return;
      }
      if (!response.ok) {
        document.getElementById("tableHost").innerHTML = '<p class="chart-note">Project management data is unavailable.</p>';
        document.getElementById("asOf").textContent = "Unavailable";
        return;
      }
      const payload = await response.json();
      allRows = payload.rows || [];
      stageCards = payload.stage_cards || [];
      document.getElementById("asOf").textContent = payload.generated_at || "Monday Process Board NY";
      document.getElementById("generatedAt").textContent = payload.generated_at || "Monday Process Board NY";
      renderReps(payload.reps || []);
      window.pmRender();
    }
    renderDateFilters(window.pmDateNote);
    load();
"""
    return _shell("project_management_hub", "Happy Solar — Project Management Hub", body, script)


def render_hold_cancelled_html() -> str:
    body = """
  <div class="workspace oc-page">
    <header class="topbar">
      <div class="crumb">WORKSPACE <span>/</span> <strong>Hold / Cancelled</strong></div>
      <div class="top-right"><span id="asOf">Loading</span></div>
    </header>
    <main>
      <div id="filterHost"></div>
      <div class="pagehead">
        <div>
          <div class="eyebrow">Project management</div>
          <h1 id="pageTitle">Hold / Cancelled</h1>
          <p class="subtitle" id="pageSub">Current hold and cancelled Happy Slr jobs from Monday Process Board NY.</p>
        </div>
        <div class="headbuttons">
          <a class="link" id="hubLink" href="/api/project_management_hub">Project Hub</a>
        </div>
      </div>
      <div class="kpis" style="--n:3">
        <div class="kpi"><div class="label">Month</div><div class="number" id="monthValue">—</div><div class="sub">Created date</div></div>
        <div class="kpi"><div class="label">Cancelled</div><div class="number" id="cancelValue">—</div><div class="sub">Currently cancelled</div></div>
        <div class="kpi"><div class="label" id="createdLabel">Created that month</div><div class="number" id="createdValue">—</div><div class="sub" id="createdSub">Projects created in the window</div></div>
      </div>
      <section class="panel" style="margin-bottom:18px">
        <div class="panel-head"><h2>Sales rep</h2></div>
        <div class="panel-body"><div class="rep-menu" id="repMenu"></div></div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Jobs</h2><div class="meta" id="tableMeta"></div></div>
        <div class="panel-body tablewrap" id="tableHost"><p class="chart-note">Loading…</p></div>
      </section>
    </main>
    <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span id="generatedAt">Monday Process Board NY</span></footer>
  </div>
"""
    script = _SHARED_JS + r"""
    window.pmDateNote = "project created date (ET)";
    let allRows = [];
    function selectedReps() {
      return Array.prototype.map.call(document.querySelectorAll("#repMenu input:checked"), function (input) {
        return String(input.value || "").trim().toLowerCase();
      });
    }
    function monthLabel(monthKey) {
      if (!monthKey) return "All months";
      const parts = String(monthKey).split("-");
      if (parts.length !== 2) return monthKey;
      return String(parts[1]).padStart(2, "0") + "/" + String(parts[0]).slice(-2);
    }
    function viewRows() {
      const params = new URLSearchParams(location.search);
      const range = readRange();
      const bucket = (params.get("bucket") || "Cancelled").trim().toLowerCase();
      const reps = selectedReps();
      const useMonth = !range.allTime && range.createdMonth && !params.get("start") && !params.get("end");
      function repOk(row) {
        if (!reps.length) return true;
        return reps.indexOf(String(row.assigned_rep || "").trim().toLowerCase()) !== -1;
      }
      if (useMonth) {
        const created = allRows.filter(function (row) {
          return repOk(row) && createdDay(row).slice(0, 7) === range.createdMonth;
        });
        const listed = created.filter(function (row) {
          return String(row.pm_bucket || "").trim().toLowerCase() === bucket;
        });
        return {
          listed: listed,
          cancelled: bucket === "cancelled" ? listed.length : created.filter(function (row) { return String(row.pm_bucket || "").trim().toLowerCase() === "cancelled"; }).length,
          created: created.length,
          month: monthLabel(range.createdMonth),
          title: "Cancellations · " + monthLabel(range.createdMonth),
          sub: "Jobs created in " + range.createdMonth + " that are currently " + bucket + "."
        };
      }
      const created = allRows.filter(function (row) { return repOk(row) && inRange(row, range); });
      const listed = created.filter(function (row) { return String(row.section || "") === "hold_cancel"; });
      const cancelled = created.filter(function (row) { return String(row.pm_bucket || "").trim().toLowerCase() === "cancelled"; }).length;
      return {
        listed: listed,
        cancelled: cancelled,
        created: range.allTime ? listed.length : created.length,
        month: range.allTime ? "All months" : (range.start + " – " + range.end),
        title: "Hold / Cancelled",
        sub: range.allTime ? "Current hold and cancelled Happy Slr jobs." : "Hold and cancelled jobs created in the selected dates."
      };
    }
    function phoneCell(row) {
      const text = String(row.permit_phone || "").trim();
      if (!text) return "—";
      const href = String(row.phoneHref || row.ghlOpportunityUrl || row.ghlContactUrl || "");
      const safe = /^https:\/\/app\.gohighlevel\.com\/v2\/location\/[A-Za-z0-9_-]+\/(?:opportunities\/list\/[A-Za-z0-9_-]+\?tab=OpportunityDetails|contacts\/detail\/[A-Za-z0-9_-]+)$/.test(href);
      if (!safe) return esc(text);
      return '<a class="phone-link" href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(text) + "</a>";
    }
    function emailCell(row) {
      const text = String(row.permit_email || "").trim();
      if (!text || text.indexOf("@") < 1) return text ? esc(text) : "—";
      return '<a href="mailto:' + esc(text) + '">' + esc(text) + "</a>";
    }
    function ghlTag(source) {
      return source === "ghl" ? ' <span class="badge warn">from GHL</span>' : "";
    }
    window.pmRender = function () {
      const view = viewRows();
      const generated = document.getElementById("generatedAt").textContent || "";
      document.getElementById("pageTitle").textContent = view.title;
      document.getElementById("pageSub").textContent = view.sub + (generated ? " Generated " + generated + "." : "");
      document.getElementById("monthValue").textContent = view.month;
      document.getElementById("cancelValue").textContent = String(view.cancelled);
      document.getElementById("createdValue").textContent = String(view.created);
      document.getElementById("createdLabel").textContent = readRange().allTime ? "Listed" : "Created in window";
      document.getElementById("hubLink").setAttribute("href", sameOriginPath("/api/project_management_hub", readRange().allTime ? {} : { start: readRange().start, end: readRange().end }));
      document.getElementById("tableMeta").textContent = String(view.listed.length) + " jobs";
      const host = document.getElementById("tableHost");
      if (!view.listed.length) {
        host.innerHTML = '<p class="chart-note">No matching jobs.</p>';
        return;
      }
      const headers = ["Name", "Phone", "Email", "Sales Rep", "Current bucket", "Stage before cancel", "Created"];
      const body = view.listed.map(function (row) {
        const name = row.board_url
          ? '<a href="' + esc(row.board_url) + '" target="_blank" rel="noopener">' + esc(row.display_name || "") + "</a>"
          : esc(row.display_name || "");
        return "<tr><td>" + name + "</td><td>" + phoneCell(row) + ghlTag(row.permit_phone_source) + "</td><td>" +
          emailCell(row) + ghlTag(row.permit_email_source) + "</td><td>" + esc(row.assigned_rep || "") +
          "</td><td>" + esc(row.pm_bucket || "") + "</td><td>" + esc(row.cancel_source_stage || "—") +
          "</td><td>" + esc(row.created_at_display || "") + "</td></tr>";
      }).join("");
      host.innerHTML = "<table><thead><tr>" + headers.map(function (header) { return "<th>" + esc(header) + "</th>"; }).join("") + "</tr></thead><tbody>" + body + "</tbody></table>";
    };
    async function load() {
      renderDateFilters(window.pmDateNote);
      let response;
      try {
        response = await fetch("/api/metrics/project_management", { credentials: "same-origin" });
      } catch (error) {
        document.getElementById("tableHost").innerHTML = '<p class="chart-note">Hold / Cancelled data is unavailable.</p>';
        document.getElementById("asOf").textContent = "Unavailable";
        return;
      }
      if (!response.ok) {
        document.getElementById("tableHost").innerHTML = '<p class="chart-note">Hold / Cancelled data is unavailable.</p>';
        document.getElementById("asOf").textContent = "Unavailable";
        return;
      }
      const payload = await response.json();
      allRows = payload.rows || [];
      document.getElementById("asOf").textContent = payload.generated_at || "Monday Process Board NY";
      document.getElementById("generatedAt").textContent = payload.generated_at || "";
      const reps = payload.reps || [];
      const params = new URLSearchParams(location.search);
      const preset = new Set((params.get("reps") || "").split(",").map(function (item) { return item.trim().toLowerCase(); }).filter(Boolean));
      document.getElementById("repMenu").innerHTML = reps.map(function (name) {
        const checked = preset.has(String(name).trim().toLowerCase()) ? " checked" : "";
        return '<label><input type="checkbox" value="' + esc(name) + '"' + checked + "> " + esc(name) + "</label>";
      }).join("");
      document.querySelectorAll("#repMenu input").forEach(function (input) {
        input.addEventListener("change", function () { window.pmRender(); });
      });
      window.pmRender();
    }
    renderDateFilters(window.pmDateNote);
    load();
"""
    return _shell("hold_cancelled", "Happy Solar — Hold / Cancelled", body, script)
