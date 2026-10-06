# -*- coding: utf-8 -*-

"""Goals Dashboard. Company and territory sales goals come from Bloom portal_goal_documents."""

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
    nav_html = render_dashboard_nav("goals_dashboard")
    return f"""<!doctype html>
<html class="oc-root" lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Goals Dashboard</title>
  <style>{nav_css}</style>
</head>
<body class="oc-root" data-oc-native-filters="1">
  {nav_html}
  <div class="workspace oc-page">
    <header class="topbar"><div class="crumb">WORKSPACE <span>/</span> <strong>Goals dashboard</strong></div><div class="top-right"><span id="asOf">Checking Bloom</span></div></header>
    <main>
      <div id="filterHost"></div>
      <div class="goals-connection"><div><strong>Bloom goals</strong><p id="bloomStatus">Checking whether company and territory goals can be read.</p></div><span class="badge warn" id="bloomBadge">Needs Data</span></div>
      <div class="goal-period"><span>Period <b id="periodLabel">—</b></span><span>Actuals as of <b id="actualsAsOf">—</b></span><span>Pacing <b>Calendar days, only after a Bloom goal is present</b></span></div>
      <div class="section-break"><div class="section-number">01</div><div><h2>Company scorecard</h2><p>Volume pace is not prorated onto Demo % or Opp2Prelim.</p></div><div class="section-rule"></div></div>
      <div class="goal-sales-grid" id="scorecard"></div>
      <div class="section-break"><div class="section-number">02</div><div><h2>Person goals in this data center</h2><p>These rows are goals_monthly_v1 from Admin Settings. They are not Bloom company or territory sales goals.</p></div><div class="section-rule"></div></div>
      <section class="panel"><div class="panel-head"><h2>Roster goals</h2></div><div class="panel-body tablewrap" id="rosterGoals">Loading roster goals…</div></section>
    </main>
  </div>
  <script>
    let requestToken = 0;
    const cards = [
      ["Company sales", "sales"],
      ["Territory sales", "territory"],
      ["Opportunities created", "created"],
      ["Demo %", "demo"],
      ["Opp2Prelim", "opp2"]
    ];
    function esc(v) {{ return String(v == null ? "" : v).replace(/[&<>]/g, function(c) {{ return {{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c]; }}); }}
    function nyToday() {{
      return new Intl.DateTimeFormat("en-CA", {{ timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }}).format(new Date());
    }}
    function filters() {{ return window.hsOpsReadFilters ? window.hsOpsReadFilters() : {{ start: nyToday().slice(0, 8) + "01", end: nyToday(), territory: "All", source: "All" }}; }}
    function renderFilters() {{
      const f = filters();
      document.getElementById("periodLabel").textContent = f.start + " – " + f.end + " America/New_York";
      document.getElementById("filterHost").innerHTML = '<div class="global-filterbar"><div class="filter-controls"><label>From<input id="gStart" type="date" value="'+f.start+'"></label><label>To<input id="gEnd" type="date" value="'+f.end+'"></label><label>Territory<select id="gTerritory">'+["All","Buffalo","Rochester","Syracuse","Virtual"].map(function(x){{return '<option'+(f.territory===x?' selected':'')+'>'+x+'</option>';}}).join('')+'</select></label><label>Lead source<select id="gSource">'+["All","Doors","Self gen","Sweeper","Inbound","3PL"].map(function(x){{return '<option'+(f.source===x?' selected':'')+'>'+x+'</option>';}}).join('')+'</select></label><button type="button" class="filter-reset" id="gReset">Reset filters</button></div></div>';
      function apply() {{
        const today = nyToday();
        const next = {{ start: document.getElementById("gStart").value || today.slice(0,8)+"01", end: document.getElementById("gEnd").value || today, territory: document.getElementById("gTerritory").value, source: document.getElementById("gSource").value }};
        if (window.hsOpsWriteFilters) window.hsOpsWriteFilters(next);
        const url = new URL(location.href);
        url.searchParams.set("start", next.start); url.searchParams.set("end", next.end);
        if (next.territory === "All") url.searchParams.delete("territory"); else url.searchParams.set("territory", next.territory);
        if (next.source === "All") url.searchParams.delete("source"); else url.searchParams.set("source", next.source);
        history.replaceState(null, "", url.toString());
        load();
      }}
      ["gStart","gEnd","gTerritory","gSource"].forEach(function(id) {{ document.getElementById(id).addEventListener("change", apply); }});
      document.getElementById("gReset").addEventListener("click", function() {{
        const today = nyToday();
        if (window.hsOpsWriteFilters) window.hsOpsWriteFilters({{ start: today.slice(0,8)+"01", end: today, territory: "All", source: "All" }});
        renderFilters(); load();
      }});
    }}
    function daysInMonth(period) {{
      return new Date(Date.UTC(Number(period.slice(0, 4)), Number(period.slice(5, 7)), 0)).getUTCDate();
    }}
    function elapsedDays(period) {{
      const today = nyToday();
      if (today.slice(0, 7) < period) return 0;
      if (today.slice(0, 7) > period) return daysInMonth(period);
      return Number(today.slice(8, 10));
    }}
    function goalCard(title, actual, detail, goal) {{
      const unset = !goal || goal.target == null;
      if (unset) {{
        return '<article class="goal-tile"><div class="goal-tile-head"><h3>'+esc(title)+'</h3><span class="badge warn">Goal Not Set</span></div><div class="goal-actual">'+esc(actual)+' <span>actual</span></div><div class="goal-meter"><i style="width:0%"></i></div><div class="goal-tile-foot"><span>Goal Not Set</span><span>'+esc(detail)+'</span></div><p>No matching Bloom target for this scope, so pace is not scored On Track or Behind.</p></article>';
      }}
      const target = Number(goal.target);
      const actualNumber = actual == null || actual === "—" || Number.isNaN(Number(actual)) ? null : Number(actual);
      const width = actualNumber == null || !target ? 0 : Math.max(0, Math.min(100, 100 * actualNumber / target));
      const period = goal.period_id;
      const days = daysInMonth(period);
      const elapsed = elapsedDays(period);
      const expected = target * elapsed / days;
      let status = "Needs Data";
      let badge = "warn";
      if (actualNumber != null && elapsed === 0) {{ status = "Not started"; badge = "cyan"; }}
      else if (actualNumber != null) {{
        status = actualNumber + 1e-9 >= expected ? "On Track" : "Behind";
        badge = status === "On Track" ? "good" : "warn";
      }}
      const marker = days ? Math.max(0, Math.min(100, 100 * elapsed / days)) : 0;
      const locked = goal.locked_default ? " · locked default" : "";
      return '<article class="goal-tile"><div class="goal-tile-head"><h3>'+esc(title)+'</h3><span class="badge '+badge+'">'+esc(status)+'</span></div><div class="goal-actual">'+esc(actual)+' <span>actual</span></div><div class="goal-meter"><i style="width:'+width.toFixed(1)+'%"></i><span style="left:'+marker.toFixed(1)+'%"></span></div><div class="goal-tile-foot"><span>Goal '+esc(target)+esc(locked)+'</span><span>day '+elapsed+' of '+days+'</span></div><p>'+esc(detail)+'</p></article>';
    }}
    function territoryRow(bloom, name) {{
      const rows = (bloom && bloom.territory_sales) || [];
      for (let i = 0; i < rows.length; i += 1) if (rows[i].territory === name) return rows[i];
      return null;
    }}
    function territoryListCard(actual, bloom) {{
      const rows = (bloom && bloom.territory_sales) || [];
      const known = rows.filter(function (row) {{ return row.target != null; }});
      if (!known.length) return goalCard("Territory sales", actual, "No territory sales goals for this month.", null);
      const body = rows.map(function (row) {{
        const value = row.target == null ? "Goal Not Set" : ("Goal " + row.target + (row.locked_default ? " locked" : ""));
        return '<div class="statrow"><div><strong>' + esc(row.territory) + '</strong></div><div class="value">' + esc(value) + '</div></div>';
      }}).join("");
      return '<article class="goal-tile"><div class="goal-tile-head"><h3>Territory sales</h3><span class="badge good">Synced</span></div><div class="goal-actual">' + esc(actual) + ' <span>actual</span></div>' + body + '<p>Stored Bloom territory sales goals. They are not added into a company goal.</p></article>';
    }}
    function markPageUnavailable() {{
      const asOf = document.getElementById("asOf");
      if (asOf && /^(loading|checking)\b/i.test((asOf.textContent || "").trim())) asOf.textContent = "Unavailable";
      const bloomStatus = document.getElementById("bloomStatus");
      if (bloomStatus && /^(loading|checking)\b/i.test((bloomStatus.textContent || "").trim())) bloomStatus.textContent = "Bloom goal status unavailable.";
      const roster = document.getElementById("rosterGoals");
      if (roster && /^(loading|checking)\b/i.test((roster.textContent || "").trim())) roster.textContent = "Roster goals unavailable.";
    }}
    function paint(snap, bloom, bloomState, f) {{
      const data = (snap && snap.data) || {{}};
      const sales = data.sales && !data.sales.error ? data.sales.result : null;
      const created = data.created && !data.created.error ? data.created.result : null;
      const demo = data.demo && !data.demo.error ? data.demo : null;
      const demoText = demo && demo.ran_count ? (Number(demo.result).toFixed(1) + "%") : "—";
      const oppText = demo && demo.ran_count && sales != null ? ((100 * Number(sales) / Number(demo.ran_count)).toFixed(1) + "%") : "—";
      const pipe = (data.sales && data.sales.breakdowns && data.sales.breakdowns.sales_by_pipeline) || {{}};
      const territoryName = f.territory === "Virtual" ? "Virtual/Sweeper" : f.territory;
      const territoryActual = f.territory === "All" ? (sales == null ? "—" : sales) : (pipe[f.territory] == null ? "—" : pipe[f.territory]);
      const territoryGoal = f.territory === "All" ? null : territoryRow(bloom, territoryName);
      const territoryDetail = f.territory === "All"
        ? ((bloom && bloom.territory_sales) || []).map(function (row) {{ return row.territory + " " + (row.target == null ? "Goal Not Set" : row.target); }}).join(" · ") || "No territory sales goals"
        : territoryName + " sales goal";
      const unset = (bloom && bloom.unset) || {{}};
      document.getElementById("scorecard").innerHTML = [
        goalCard("Company sales", sales == null ? "—" : sales, "Distinct-contact sales. " + (unset.company_sales || ""), bloom && bloom.company_sales),
        (f.territory === "All" ? territoryListCard(territoryActual, bloom) : goalCard("Territory sales", territoryActual, territoryDetail, territoryGoal)),
        goalCard("Opportunities created", created == null ? "—" : created, unset.opportunities_created || "Created in the selected dates", null),
        goalCard("Demo %", demoText, (demo ? (demo.sit_count + " demos / " + demo.ran_count + " ran. ") : "") + (unset.demo_pct || ""), null),
        goalCard("Opp2Prelim", oppText, "Sales / ran. " + (unset.opp2prelim || "Not prorated by days elapsed."), null)
      ].join("");
      document.getElementById("actualsAsOf").textContent = (data.sales && data.sales.generated_at) || "unavailable";
      document.getElementById("bloomStatus").textContent = bloomState === "pending"
        ? "Loading Bloom sales goals…"
        : bloom && bloom.available
        ? ("Read portal_goal_documents for " + bloom.period_id + ". " + (bloom.company_sales ? ("Company sales goal " + bloom.company_sales.target + ". ") : (unset.company_sales || "")) + territoryDetail)
        : ((bloom && bloom.blocker) || "Bloom goal status unavailable.");
      document.getElementById("bloomBadge").textContent = bloom && bloom.available ? "Synced" : "Goal Not Set";
      document.getElementById("asOf").textContent = bloom && bloom.checked_at ? ("Bloom check " + bloom.checked_at) : (bloomState === "pending" ? "Checking Bloom" : "Bloom unread");
    }}
    async function load() {{
      const token = ++requestToken;
      const f = filters();
      if (window.HappySolarLoading) window.HappySolarLoading.begin("view");
      const rosterHost = document.getElementById("rosterGoals");
      if (rosterHost) rosterHost.textContent = "Loading roster goals…";
      const params = new URLSearchParams();
      params.set("year", f.start.slice(0, 4));
      params.set("month", String(Number(f.start.slice(5, 7))));
      params.set("start", f.start);
      params.set("end", f.end);
      if (f.territory !== "All") params.set("pipeline", f.territory);
      if (f.source === "Sweeper") params.set("sweeper", "1");
      else if (f.source !== "All") params.set("lead_source", f.source === "Self gen" ? "Self Gen" : f.source);
      let snapRes;
      try {{
        snapRes = await fetch("/api/metrics/company_snapshot?" + params.toString());
      }} catch (error) {{
        if (error && error.name === "AbortError") return;
        if (token !== requestToken) return;
        markPageUnavailable();
        return;
      }}
      if (token !== requestToken) return;
      if (!snapRes.ok) {{
        markPageUnavailable();
        return;
      }}
      let snap;
      try {{
        snap = await snapRes.json();
      }} catch (error) {{
        if (error && error.name === "AbortError") return;
        if (token !== requestToken) return;
        var generation = window.HappySolarLoading && window.HappySolarLoading.currentGeneration;
        if (generation && !generation.settled) generation.failed = true;
        markPageUnavailable();
        return;
      }}
      if (token !== requestToken) return;
      paint(snap, null, "pending", f);
      let bloom = null;
      try {{
        const bloomRes = await fetch("/api/metrics/bloom_goals?oc_raw=1&period=" + encodeURIComponent(f.start.slice(0, 7)), {{ hsOptional: true }});
        if (token !== requestToken) return;
        if (bloomRes.ok) bloom = await bloomRes.json();
      }} catch (error) {{
        if (error && error.name === "AbortError") return;
        if (token !== requestToken) return;
      }}
      if (token !== requestToken) return;
      paint(snap, bloom, bloom ? "ready" : "missing", f);
      const month = f.start.slice(0, 7);
      let roster;
      try {{
        roster = await fetch("/api/settings_api", {{ method: "POST", hsOptional: true, headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{ action: "bootstrap", month: month }}) }});
      }} catch (error) {{
        if (error && error.name === "AbortError") return;
        document.getElementById("rosterGoals").textContent = "Roster goals unavailable.";
        return;
      }}
      if (token !== requestToken) return;
      const host = document.getElementById("rosterGoals");
      if (!roster.ok) {{ host.textContent = "Roster goals unavailable."; return; }}
      let payload;
      try {{
        payload = await roster.json();
      }} catch (error) {{
        if (error && error.name === "AbortError") return;
        host.textContent = "Roster goals unavailable.";
        return;
      }}
      if (!payload) {{ host.textContent = "Roster goals unavailable."; return; }}
      const rows = payload.goals_for_month || [];
      const bloomPeople = (bloom && bloom.person_goals) || [];
      if (!rows.length && !bloomPeople.length) {{ host.innerHTML = '<p class="chart-note">No goals_monthly_v1 rows for ' + esc(month) + '. Bloom has no person goals for this month either.</p>'; return; }}
      const firestoreTable = rows.length
        ? '<table><thead><tr><th>Person</th><th>Metric</th><th>Target</th></tr></thead><tbody>' + rows.map(function(row) {{
            return '<tr><td>' + esc(row.person_key) + '</td><td>' + esc(row.metric) + '</td><td>' + esc(row.value) + '</td></tr>';
          }}).join("") + '</tbody></table>'
        : '<p class="chart-note">No goals_monthly_v1 rows for ' + esc(month) + '.</p>';
      const bloomTable = bloomPeople.length
        ? '<p class="chart-note">Bloom person goals from portal_goal_documents.</p><table><thead><tr><th>Person</th><th>Role</th><th>Metric</th><th>Target</th></tr></thead><tbody>' + bloomPeople.map(function(row) {{
            return '<tr><td>' + esc(row.name || row.assignee_user_id) + '</td><td>' + esc(row.role) + '</td><td>' + esc(row.metric) + '</td><td>' + esc(row.target) + '</td></tr>';
          }}).join("") + '</tbody></table>'
        : '';
      host.innerHTML = firestoreTable + bloomTable;
    }}
    window.hsOpsReload = load;
    window.hsOpsRerenderFilters = renderFilters;
    renderFilters();
    load();
  </script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
