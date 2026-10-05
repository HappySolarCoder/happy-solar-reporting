# -*- coding: utf-8 -*-

"""Goals Dashboard. Bloom targets stay Goal Not Set until a read path exists."""

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
    function goalCard(title, actual, detail) {{
      return '<article class="goal-tile"><div class="goal-tile-head"><h3>'+esc(title)+'</h3><span class="badge warn">Needs Data</span></div><div class="goal-actual">'+esc(actual)+' <span>actual</span></div><div class="goal-meter"><i style="width:0%"></i></div><div class="goal-tile-foot"><span>Goal Not Set</span><span>'+esc(detail)+'</span></div><p>No matching Bloom target for this scope, so pace is not scored On Track or Behind.</p></article>';
    }}
    async function load() {{
      const f = filters();
      const params = new URLSearchParams();
      params.set("year", f.start.slice(0, 4));
      params.set("month", String(Number(f.start.slice(5, 7))));
      params.set("start", f.start);
      params.set("end", f.end);
      if (f.territory !== "All") params.set("pipeline", f.territory);
      if (f.source === "Sweeper") params.set("sweeper", "1");
      else if (f.source !== "All") params.set("lead_source", f.source === "Self gen" ? "Self Gen" : f.source);
      const snapRes = await fetch("/api/metrics/company_snapshot?" + params.toString());
      const bloomRes = await fetch("/api/metrics/bloom_goals?oc_raw=1");
      const snap = snapRes.ok ? await snapRes.json() : null;
      const bloom = bloomRes.ok ? await bloomRes.json() : null;
      const data = (snap && snap.data) || {{}};
      const sales = data.sales && !data.sales.error ? data.sales.result : null;
      const created = data.created && !data.created.error ? data.created.result : null;
      const demo = data.demo && !data.demo.error ? data.demo : null;
      const demoText = demo && demo.ran_count ? (Number(demo.result).toFixed(1) + "%") : "—";
      const oppText = demo && demo.ran_count && sales != null ? ((100 * Number(sales) / Number(demo.ran_count)).toFixed(1) + "%") : "—";
      const pipe = (data.sales && data.sales.breakdowns && data.sales.breakdowns.sales_by_pipeline) || {{}};
      const territoryActual = f.territory === "All" ? (sales == null ? "—" : sales) : (pipe[f.territory] == null ? "—" : pipe[f.territory]);
      document.getElementById("scorecard").innerHTML = [
        goalCard("Company sales", sales == null ? "—" : sales, "Distinct-contact sales"),
        goalCard("Territory sales", territoryActual, f.territory === "All" ? "Sum of pipeline sales" : f.territory),
        goalCard("Opportunities created", created == null ? "—" : created, "Created in the selected dates"),
        goalCard("Demo %", demoText, demo ? (demo.sit_count + " demos / " + demo.ran_count + " ran") : "Demo rate unavailable"),
        goalCard("Opp2Prelim", oppText, "Sales / ran. Not prorated by days elapsed.")
      ].join("");
      document.getElementById("actualsAsOf").textContent = (data.sales && data.sales.generated_at) || "unavailable";
      document.getElementById("bloomStatus").textContent = (bloom && bloom.blocker) || "Bloom goal status unavailable.";
      document.getElementById("bloomBadge").textContent = bloom && bloom.available ? "Synced" : "Goal Not Set";
      document.getElementById("asOf").textContent = bloom && bloom.checked_at ? ("Bloom check " + bloom.checked_at) : "Bloom unread";
      const month = f.start.slice(0, 7);
      const roster = await fetch("/api/settings_api", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{ action: "bootstrap", month: month }}) }});
      const host = document.getElementById("rosterGoals");
      if (!roster.ok) {{ host.textContent = "Roster goals unavailable."; return; }}
      const payload = await roster.json();
      const rows = payload.goals_for_month || [];
      if (!rows.length) {{ host.innerHTML = '<p class="chart-note">No goals_monthly_v1 rows for ' + esc(month) + '.</p>'; return; }}
      host.innerHTML = '<table><thead><tr><th>Person</th><th>Metric</th><th>Target</th></tr></thead><tbody>' + rows.map(function(row) {{
        return '<tr><td>' + esc(row.person_key) + '</td><td>' + esc(row.metric) + '</td><td>' + esc(row.value) + '</td></tr>';
      }}).join("") + '</tbody></table>';
    }}
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
