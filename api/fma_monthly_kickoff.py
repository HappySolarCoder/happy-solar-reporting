# -*- coding: utf-8 -*-

"""Vercel Python function: /api/fma_monthly_kickoff

Monthly kickoff dashboard for FMAs.

Purpose:
- Review prior-month FMA production in one table
- Allow month switching
- Keep metric wiring aligned to canonical Raydar + GHL endpoints
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


def previous_month_key() -> str:
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}-{month:02d}"


def render_html(default_month: str) -> str:
    nav_html = render_dashboard_nav("fma_monthly_kickoff")
    return (
        r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — FMA Monthly Kickoff</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --card: #ffffff;
      --border: #e8ecf0;
      --text: #111827;
      --muted: #6b7280;
      --muted2: #9ca3af;
      --pink: #ec4899;
      --pink2: #f472b6;
      --orange: #f59e0b;
      --orange2: #fbbf24;
      --cream: #fff7e8;
      --cream2: #fffdf8;
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    .wrap {
      max-width: 1240px;
      margin: 0 auto;
      padding: 22px;
    }

    .topbar {
      padding: 18px 20px;
      border-radius: 14px;
      background: var(--card);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
    }

    .title {
      font-size: 24px;
      font-weight: 950;
      letter-spacing: -0.02em;
      color: #1a2b4a;
    }

    .subtitle {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }

    .pinkline {
      height: 3px;
      width: 240px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

__DASHBOARD_NAV_CSS__

    .navbtn {
      display: inline-flex;
      align-items: center;
      padding: 9px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      color: #1f2937;
      font-size: 13px;
      font-weight: 800;
      text-decoration: none;
    }

    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .dashboardSwitch {
      margin-top: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .dashboardSwitch label {
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .dashboardSwitch select,
    .monthSelect {
      min-width: 220px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: #fff;
      color: #1f2937;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 800;
      box-shadow: var(--shadow);
    }

    .toolbar {
      margin-top: 14px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }

    .toolbarLeft {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }

    .helper {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--pink);
      border: 1px solid var(--pink);
      color: #fff;
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 13px;
      font-weight: 900;
      cursor: pointer;
      text-decoration: none;
    }

    .btn.secondary {
      background: #fff;
      border-color: var(--border);
      color: #334155;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 16px 18px;
    }

    .cardTitle {
      font-size: 12px;
      font-weight: 900;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .kpi {
      margin-top: 10px;
      font-size: 34px;
      font-weight: 950;
      line-height: 1;
      color: #0f172a;
      letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums;
    }

    .meta {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted2);
      font-weight: 700;
    }

    .panel {
      margin-top: 16px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .panelHead {
      padding: 16px 18px 10px 18px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(251,191,36,0.08) 0%, rgba(255,255,255,0.92) 100%);
    }

    .panelTitle {
      font-size: 18px;
      font-weight: 950;
      color: #1f2937;
      letter-spacing: -0.02em;
    }

    .panelSub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .tableWrap {
      overflow: auto;
      background: #fff;
    }

    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      min-width: 1080px;
    }

    thead th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: linear-gradient(180deg, var(--orange2) 0%, var(--orange) 100%);
      color: #fff;
      padding: 14px 14px;
      font-size: 13px;
      font-weight: 950;
      text-align: center;
      border-bottom: 1px solid rgba(255,255,255,0.22);
      white-space: nowrap;
    }

    tbody td {
      padding: 18px 14px;
      text-align: center;
      font-size: 18px;
      color: #1f2937;
      border-bottom: 1px solid #f2f4f7;
      font-variant-numeric: tabular-nums;
      background: #fff;
    }

    tbody tr:nth-child(even) td {
      background: var(--cream);
    }

    tbody tr:nth-child(odd) td {
      background: var(--cream2);
    }

    td.teamCell {
      text-align: left;
      font-size: 20px;
      font-weight: 950;
      color: #1f2a44;
      min-width: 180px;
    }

    .winner {
      box-shadow: inset 0 0 0 4px #111827;
      border-radius: 2px;
      font-weight: 950;
      background-clip: padding-box;
    }

    .accent {
      color: #f97316;
      font-weight: 950;
    }

    .empty,
    .status {
      padding: 18px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }

    .footnote {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    @media (max-width: 1024px) {
      .grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 640px) {
      .wrap {
        padding: 12px;
      }

      .grid {
        grid-template-columns: 1fr;
      }

      .title {
        font-size: 20px;
      }

      tbody td {
        padding: 14px 10px;
        font-size: 16px;
      }

      td.teamCell {
        font-size: 18px;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="title">FMA Monthly Kickoff</div>
      <div class="subtitle">Prior-month FMA scoreboard for kickoff review</div>
      <div class="pinkline"></div>

__DASHBOARD_NAV_HTML__
      <div class="nav" style="justify-content:flex-start;">
        <a class="navbtn active" href="/api/fma_monthly_kickoff">FMA Monthly Kickoff</a>
        <a class="navbtn" href="/api/fma_commissions">FMA Commissions</a>
      </div>

      <div class="dashboardSwitch">
        <label for="fmaViewSelect">FMA View</label>
        <select id="fmaViewSelect" onchange="if (this.value) window.location.href = this.value;">
          <option value="/api/fma_dashboard">Data Dashboard</option>
          <option value="/api/fma_monthly_kickoff" selected>Monthly Kickoff</option>
          <option value="/api/appointment_outcomes">Appointment Outcomes</option>
          <option value="/api/fma_commissions">Commissions Dashboard</option>
        </select>
      </div>

      <div class="toolbar">
        <div class="toolbarLeft">
          <select id="monthSelect" class="monthSelect"></select>
          <button id="reloadBtn" class="btn">Load Month</button>
          <a id="openMonthMetrics" class="btn secondary" href="#" target="_blank" rel="noreferrer">Open Sales JSON</a>
        </div>
        <div class="helper">Default month: previous completed month</div>
      </div>
    </div>

    <div id="summaryGrid" class="grid"></div>

    <div class="panel">
      <div class="panelHead">
        <div class="panelTitle" id="panelTitle">Monthly FMA Table</div>
        <div class="panelSub" id="panelSub">Loading monthly scoreboard...</div>
      </div>
      <div class="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Team</th>
              <th>Knocks</th>
              <th>Appts Set</th>
              <th>Opps Ran</th>
              <th>Demos</th>
              <th>Sale %</th>
              <th>Demo %</th>
              <th>Sales</th>
            </tr>
          </thead>
          <tbody id="tableBody">
            <tr><td colspan="8" class="status">Loading monthly scoreboard...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="footnote">
      Metric wiring:
      Knocks come from Raydar monthly activity.
      Appts Set comes from the canonical GHL Opportunities Created endpoint.
      Opps Ran + Demos come from the canonical GHL Demo Rate endpoint.
      Sales come from the canonical GHL Sales endpoint.
      Sale % = Sales / Opps Ran.
      Demo % = Demos / Opps Ran.
    </div>
  </div>

  <script>
    const DEFAULT_MONTH = "__DEFAULT_MONTH__";
    const MONTH_START = "2025-08";

    function escapeHtml(value) {
      return String(value == null ? "" : value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function normKey(value) {
      return String(value || "").trim().toLowerCase();
    }

    function titleCaseLast(value) {
      const raw = String(value || "").trim();
      if (!raw) return "";
      return raw
        .split(/\s+/)
        .map((part) => part ? (part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()) : "")
        .join(" ");
    }

    function formatMonthLabel(monthKey) {
      const [year, month] = String(monthKey).split("-").map(Number);
      const dt = new Date(Date.UTC(year, month - 1, 1));
      return dt.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
    }

    function monthRange(monthKey) {
      const [year, month] = String(monthKey).split("-").map(Number);
      const start = `${year}-${String(month).padStart(2, "0")}-01`;
      const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
      const end = `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
      return { start, end };
    }

    function buildMonthOptions(selectEl) {
      const now = new Date();
      const currentMonthKey = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
      const months = [];

      let cursor = MONTH_START;
      while (cursor <= currentMonthKey) {
        months.push(cursor);
        const [y, m] = cursor.split("-").map(Number);
        const next = new Date(Date.UTC(y, m, 1));
        cursor = `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}`;
      }

      months.reverse().forEach((monthKey) => {
        const option = document.createElement("option");
        option.value = monthKey;
        option.textContent = formatMonthLabel(monthKey);
        if (monthKey === DEFAULT_MONTH) option.selected = true;
        selectEl.appendChild(option);
      });
    }

    function pct(numerator, denominator) {
      if (!denominator) return 0;
      return (Number(numerator || 0) / Number(denominator || 0)) * 100;
    }

    function fmtInt(value) {
      return Number(value || 0).toLocaleString("en-US");
    }

    function fmtPct(value) {
      const num = Number(value || 0);
      if (!isFinite(num)) return "0%";
      const rounded = Math.round(num * 10) / 10;
      return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
    }

    function normalizeBreakdownMap(raw) {
      const out = {};
      Object.entries(raw || {}).forEach(([key, value]) => {
        const norm = normKey(key);
        if (!norm) return;
        out[norm] = (out[norm] || 0) + Number(value || 0);
      });
      return out;
    }

    function buildGoalMap(goalRows) {
      const out = {};
      (goalRows || []).forEach((row) => {
        const pk = String(row.person_key || "").trim();
        const metric = String(row.metric || "").trim();
        if (!pk || !metric) return;
        if (!out[pk]) out[pk] = {};
        out[pk][metric] = Number(row.value || 0);
      });
      return out;
    }

    function isFmaRosterRow(row, goalMap, roleUsers) {
      const personKey = String(row.person_key || "").trim();
      const role = String(row.role || "").trim().toLowerCase();
      const goals = goalMap[personKey] || {};
      const hasFmaGoals = ["doors_goal", "appts_goal", "demos_goal"].some((metric) => Number(goals[metric] || 0) > 0);
      const cats = (((roleUsers || {})[String(row.raydar_user_id || "").trim()] || {}).categories) || [];
      const roleIsFma = role === "setter" || cats.includes("fma");
      const hasAnyMapping = String(row.ghl_setter_last_name || "").trim() || String(row.raydar_user_id || "").trim();
      return Boolean(hasAnyMapping && (roleIsFma || hasFmaGoals));
    }

    function buildRows({ roster, goalMap, roleUsers, rayData, oppData, demoData, salesData }) {
      const knocksByActor = (rayData && rayData.breakdowns && rayData.breakdowns.knocks_by_actor) || {};
      const apptsBySetter = normalizeBreakdownMap(oppData && oppData.breakdowns ? oppData.breakdowns.created_by_setter_last_name : {});
      const ranBySetter = normalizeBreakdownMap(demoData && demoData.breakdowns ? demoData.breakdowns.ran_by_setter_last_name : {});
      const sitBySetter = normalizeBreakdownMap(demoData && demoData.breakdowns ? demoData.breakdowns.sit_by_setter_last_name : {});
      const salesBySetter = normalizeBreakdownMap(salesData && salesData.breakdowns ? salesData.breakdowns.sales_by_setter_last_name : {});

      return (roster || [])
        .filter((row) => isFmaRosterRow(row, goalMap, roleUsers))
        .map((row) => {
          const lastName = String(row.ghl_setter_last_name || "").trim();
          const lastKey = normKey(lastName);
          const raydarId = String(row.raydar_user_id || "").trim();
          const knocks = Number(knocksByActor[raydarId] || 0);
          const appts = Number(apptsBySetter[lastKey] || 0);
          const oppsRan = Number(ranBySetter[lastKey] || 0);
          const demos = Number(sitBySetter[lastKey] || 0);
          const sales = Number(salesBySetter[lastKey] || 0);
          const displayName = String(row.display_name || row.raydar_user_name || titleCaseLast(lastName) || "Unknown").trim();
          return {
            personKey: String(row.person_key || "").trim(),
            team: displayName,
            knocks,
            appts,
            oppsRan,
            demos,
            sales,
            salePct: pct(sales, oppsRan),
            demoPct: pct(demos, oppsRan),
          };
        })
        .sort((a, b) =>
          (b.sales - a.sales) ||
          (b.demos - a.demos) ||
          (b.oppsRan - a.oppsRan) ||
          (b.appts - a.appts) ||
          (b.knocks - a.knocks) ||
          a.team.localeCompare(b.team)
        );
    }

    function computeWinners(rows) {
      const eligibleRows = rows.filter((row) => Number(row.knocks || 0) >= 500);
      const maxFor = (key) => {
        const values = eligibleRows.map((row) => Number(row[key] || 0)).filter((value) => value > 0);
        return values.length ? Math.max(...values) : 0;
      };
      return {
        knocks: maxFor("knocks"),
        appts: maxFor("appts"),
        oppsRan: maxFor("oppsRan"),
        demos: maxFor("demos"),
        salePct: maxFor("salePct"),
        demoPct: maxFor("demoPct"),
        sales: maxFor("sales"),
      };
    }

    function winnerClass(value, maxValue) {
      return maxValue > 0 && Number(value || 0) === Number(maxValue || 0) ? "winner" : "";
    }

    function renderSummary(monthKey, rows) {
      const totals = rows.reduce((acc, row) => {
        acc.knocks += row.knocks;
        acc.appts += row.appts;
        acc.oppsRan += row.oppsRan;
        acc.demos += row.demos;
        acc.sales += row.sales;
        return acc;
      }, { knocks: 0, appts: 0, oppsRan: 0, demos: 0, sales: 0 });

      const cards = [
        { title: "Month", value: formatMonthLabel(monthKey), meta: "Kickoff review window" },
        { title: "Total Knocks", value: fmtInt(totals.knocks), meta: "Raydar dispositioned leads" },
        { title: "Total Appts Set", value: fmtInt(totals.appts), meta: "GHL opportunities created by setter" },
        { title: "Total Opps Ran", value: fmtInt(totals.oppsRan), meta: "GHL opportunities ran" },
        { title: "Total Demos / Sales", value: `${fmtInt(totals.demos)} / ${fmtInt(totals.sales)}`, meta: "GHL sit demos and sales" },
      ];

      document.getElementById("summaryGrid").innerHTML = cards.map((card) => `
        <div class="card">
          <div class="cardTitle">${escapeHtml(card.title)}</div>
          <div class="kpi">${escapeHtml(card.value)}</div>
          <div class="meta">${escapeHtml(card.meta)}</div>
        </div>
      `).join("");
    }

    function renderTable(monthKey, rows) {
      const tbody = document.getElementById("tableBody");
      const titleEl = document.getElementById("panelTitle");
      const subEl = document.getElementById("panelSub");

      titleEl.textContent = `${formatMonthLabel(monthKey)} FMA Scoreboard`;
      subEl.textContent = `Monthly kickoff view. Sale % = Sales / Opps Ran. Demo % = Demos / Opps Ran.`;

      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">No FMA roster rows matched this month.</td></tr>`;
        renderSummary(monthKey, rows);
        return;
      }

      const winners = computeWinners(rows);
      tbody.innerHTML = rows.map((row) => `
        <tr>
          <td class="teamCell">${escapeHtml(row.team)}</td>
          <td class="${winnerClass(row.knocks, winners.knocks)}">${escapeHtml(fmtInt(row.knocks))}</td>
          <td class="${winnerClass(row.appts, winners.appts)}">${escapeHtml(fmtInt(row.appts))}</td>
          <td class="${winnerClass(row.oppsRan, winners.oppsRan)}">${escapeHtml(fmtInt(row.oppsRan))}</td>
          <td class="${winnerClass(row.demos, winners.demos)}">${escapeHtml(fmtInt(row.demos))}</td>
          <td class="${winnerClass(row.salePct, winners.salePct)}">${escapeHtml(fmtPct(row.salePct))}</td>
          <td class="${winnerClass(row.demoPct, winners.demoPct)}">${escapeHtml(fmtPct(row.demoPct))}</td>
          <td class="${winnerClass(row.sales, winners.sales)} accent">${escapeHtml(fmtInt(row.sales))}</td>
        </tr>
      `).join("");

      renderSummary(monthKey, rows);
    }

    async function loadDashboard(monthKey) {
      const tbody = document.getElementById("tableBody");
      const panelSub = document.getElementById("panelSub");
      const openMonthMetrics = document.getElementById("openMonthMetrics");
      const range = monthRange(monthKey);
      const oppJsonHref = `/api/metrics/opportunities_created?format=json&start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}&pipeline_scope=all`;
      const salesJsonHref = `/api/metrics/sales?format=json&start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`;

      openMonthMetrics.href = oppJsonHref;
      tbody.innerHTML = `<tr><td colspan="8" class="status">Loading ${escapeHtml(formatMonthLabel(monthKey))}...</td></tr>`;
      panelSub.textContent = `Pulling Raydar + GHL metrics for ${formatMonthLabel(monthKey)}...`;

      try {
        const settingsReq = fetch("/api/settings_api", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "bootstrap", month: monthKey }),
        });

        const roleReq = fetch("/api/metrics/raydar_user_roles?format=json");
        const rayReq = fetch(`/api/metrics/raydar_doors_knocked?format=json&start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`);
        const oppReq = fetch(oppJsonHref);
        const demoReq = fetch(`/api/metrics/demo_rate?format=json&start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`);
        const salesReq = fetch(salesJsonHref);

        const [settingsRes, roleRes, rayRes, oppRes, demoRes, salesRes] = await Promise.all([settingsReq, roleReq, rayReq, oppReq, demoReq, salesReq]);

        if (!settingsRes.ok) throw new Error(`settings_api ${settingsRes.status}`);
        if (!roleRes.ok) throw new Error(`raydar_user_roles ${roleRes.status}`);
        if (!rayRes.ok) throw new Error(`raydar_doors_knocked ${rayRes.status}`);
        if (!oppRes.ok) throw new Error(`opportunities_created ${oppRes.status}`);
        if (!demoRes.ok) throw new Error(`demo_rate ${demoRes.status}`);
        if (!salesRes.ok) throw new Error(`sales ${salesRes.status}`);

        const [settings, roleData, rayData, oppData, demoData, salesData] = await Promise.all([
          settingsRes.json(),
          roleRes.json(),
          rayRes.json(),
          oppRes.json(),
          demoRes.json(),
          salesRes.json(),
        ]);

        const rows = buildRows({
          roster: settings.roster_people || [],
          goalMap: buildGoalMap(settings.goals_for_month || []),
          roleUsers: roleData.users || {},
          rayData,
          oppData,
          demoData,
          salesData,
        });

        renderTable(monthKey, rows);
      } catch (error) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">Error loading kickoff dashboard: ${escapeHtml(error && error.message ? error.message : String(error))}</td></tr>`;
        panelSub.textContent = "The monthly scoreboard failed to load.";
        document.getElementById("summaryGrid").innerHTML = "";
      }
    }

    const monthSelect = document.getElementById("monthSelect");
    buildMonthOptions(monthSelect);

    const params = new URLSearchParams(window.location.search);
    const monthFromUrl = params.get("month");
    if (monthFromUrl) monthSelect.value = monthFromUrl;

    document.getElementById("reloadBtn").addEventListener("click", () => {
      const monthKey = monthSelect.value || DEFAULT_MONTH;
      const url = new URL(window.location.href);
      url.searchParams.set("month", monthKey);
      window.history.replaceState({}, "", url.toString());
      loadDashboard(monthKey);
    });

    monthSelect.addEventListener("change", () => {
      const monthKey = monthSelect.value || DEFAULT_MONTH;
      const url = new URL(window.location.href);
      url.searchParams.set("month", monthKey);
      window.history.replaceState({}, "", url.toString());
    });

    loadDashboard(monthSelect.value || DEFAULT_MONTH);
  </script>
</body>
</html>
"""
        .replace("__DEFAULT_MONTH__", default_month)
        .replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css())
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            month = (qs.get("month", [""])[0] or "").strip() or previous_month_key()
            body = render_html(month).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
