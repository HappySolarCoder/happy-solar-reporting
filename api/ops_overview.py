# -*- coding: utf-8 -*-

"""Company Overview markup for Operations Control."""

from __future__ import annotations

from pathlib import Path

JS = Path(__file__).with_name("ops_overview.js").read_text(encoding="utf-8")

FUNNELS = (
    ("Company", "Company", "Company"),
    ("Doors", "Doors", "Doors"),
    ("Self gen", "SelfGen", "Self gen"),
    ("Sweeper", "Sweeper", "Sweeper"),
    ("Inbound", "Inbound", "Inbound"),
    ("3PL", "3pl", "3PL"),
)


def _funnel(channel: str, prefix: str, label: str) -> str:
    return f"""
        <section class="panel source-funnel{' company-funnel' if channel == 'Company' else ''}" data-channel="{channel}">
          <div class="panel-head"><h2><button type="button" class="funnel-title-button" data-open-funnel="{channel}">{label} Funnel</button></h2>
            <button type="button" class="expand-btn" aria-label="Expand {label} funnel" data-open-funnel="{channel}">⤢</button></div>
          <div class="panel-body compact-funnel">
            <button type="button" class="compact-stage" data-open-funnel="{channel}" aria-label="{label}: opportunities created, view funnel and monthly trend" style="--inset:0%;--next:4%;--stage-color:#125975"><span>Opps created</span><strong id="lg{prefix}Created">—</strong><small>Created in range <span class="stage-arrow">↗</span></small></button>
            <button type="button" class="compact-stage" data-open-funnel="{channel}" aria-label="{label}: Demo percent, view funnel and monthly trend" style="--inset:4%;--next:8%;--stage-color:#124962"><span>Demo %</span><strong id="lg{prefix}Demo">—</strong><small id="lg{prefix}DemoCounts">Demos — / ran — <span class="stage-arrow">↗</span></small></button>
            <button type="button" class="compact-stage" data-open-funnel="{channel}" aria-label="{label}: Opp2Prelim, view funnel and monthly trend" style="--inset:8%;--next:12%;--stage-color:#123e54"><span>Opp2Prelim</span><strong id="lg{prefix}Opp2">—</strong><small id="lg{prefix}Opp2Counts">Sales — / ran — <span class="stage-arrow">↗</span></small></button>
            <button type="button" class="compact-stage" data-open-funnel="{channel}" aria-label="{label}: sales, view funnel and monthly trend" style="--inset:12%;--next:16%;--stage-color:#104d48"><span>Sales</span><strong id="lg{prefix}Sales">—</strong><small>Sold in range <span class="stage-arrow">↗</span></small></button>
          </div>
        </section>"""


def render_body(nav_html: str) -> str:
    funnels = "".join(_funnel(*item) for item in FUNNELS)
    dots = "".join(
        f'<button type="button" class="carousel-dot{" active" if i == 0 else ""}" data-index="{i}" aria-label="Show {label} funnel" aria-pressed="{str(i == 0).lower()}"></button>'
        for i, (_channel, _prefix, label) in enumerate(FUNNELS)
    )
    return f"""
    {nav_html}
    <div class="workspace oc-page">
      <header class="topbar">
        <div class="crumb">WORKSPACE <span>/</span> <strong>Company overview</strong></div>
        <div class="top-right"><span id="asOf">Loading live metrics</span></div>
      </header>
      <main id="main">
        <div id="filterHost"></div>
        <div id="attentionHost"></div>
        <section class="mobile-summary" aria-label="Company at a glance">
          <div><span>COMPANY AT A GLANCE</span><strong id="mobileSales">— sales</strong></div>
          <div id="mobilePace">Goal Not Set</div>
          <a href="/api/missing_dispos">Review missing dispositions →</a>
        </section>
        <div class="section-break"><div class="section-number">01</div><div><h2>Company pulse</h2><p>Filtered results · goal pace appears only when Bloom provides a matching target</p></div><div class="section-rule"></div></div>
        <div class="kpis overview-pulse">
          <div class="kpi primary-mobile"><div class="label">Total sales</div><div class="number" id="totalSales">—</div><div id="sparkSales"></div><div class="pace-caption" id="salesPace">Goal Not Set</div></div>
          <div class="kpi territory-kpi"><div class="label">Territory sales</div><div id="territoryDonut"><div class="pace-caption">Loading territory split</div></div></div>
          <div class="kpi"><div class="label">Opportunities created</div><div class="number" id="oppsCreated">—</div><div id="sparkCreated"></div><div class="pace-caption" id="createdPace">Goal Not Set</div></div>
          <div class="kpi"><div class="label">Demo %</div><div class="number" id="demoRate">—</div><div class="sub" id="demoSub">Demos / ran</div><div class="pace-caption" id="demoGoal">Goal Not Set</div></div>
          <div class="kpi"><div class="label">Opp2Prelim</div><div class="number" id="opp2">—</div><div class="sub" id="opp2Sub">Sales / ran</div><div class="pace-caption" id="opp2Goal">Goal Not Set</div></div>
        </div>
        <div class="section-break"><div class="section-number">02</div><div><h2>Lead-generation funnels</h2><p>Select a funnel to see it enlarged with month-to-month performance</p></div><div class="section-rule"></div></div>
        <div class="funnel-grid" id="funnelCarousel">{funnels}</div>
        <div class="carousel-controls"><button type="button" id="funnelPrev" aria-label="Previous funnel">←</button><div>{dots}</div><button type="button" id="funnelNext" aria-label="Next funnel">→</button></div>
        <p class="funnel-footnote" id="pageNote">Widths organize stages rather than encode volume. Created and ran counts use separate reporting populations.</p>
        <div class="section-break"><div class="section-number">03</div><div><h2>Performance trends</h2><p>Monthly cumulative progress. Not a fabricated daily series.</p></div><div class="section-rule"></div></div>
        <div class="grid equal"><section class="panel"><div class="panel-head"><h2>Sales progress</h2></div><div class="panel-body" id="trendSales"></div></section><section class="panel"><div class="panel-head"><h2>Opportunity progress</h2></div><div class="panel-body" id="trendCreated"></div></section></div>
        <div class="section-break"><div class="section-number">04</div><div><h2>Next actions</h2><p>Exceptions stay attached to the queues that already own them</p></div><div class="section-rule"></div></div>
        <div class="grid equal">
          <section class="panel"><div class="panel-head"><h2>Outcome completeness</h2></div><div class="panel-body"><p class="chart-note">Incomplete outcomes and overdue missing dispositions are different queues.</p><a class="link" href="/api/missing_dispos">Review missing dispositions →</a></div></section>
          <section class="panel"><div class="panel-head"><h2>Company goals</h2></div><div class="panel-body"><p class="chart-note">Bloom company and territory goals are not readable from this app yet.</p><a class="link" href="/api/goals_dashboard">Open Goals dashboard →</a></div></section>
        </div>
      </main>
      <footer><span>HAPPY SOLAR <b>/</b> OPERATIONS CONTROL</span><span id="footerScope">America/New_York</span></footer>
    </div>
    <div id="overlay" class="overlay" hidden></div>
    <script>
      const INBOUND_KEYS = ['Inbound'];
      const THREE_PL_KEYS = ['3PL'];
      /* lead_source=Inbound and lead_source=3PL are requested as separate filters. */
    </script>
    <script>{JS}</script>
    <script>
      const salesNode = document.getElementById('totalSales');
      const mobileNode = document.getElementById('mobileSales');
      if (salesNode && mobileNode) {{
        new MutationObserver(function() {{ mobileNode.textContent = salesNode.textContent + ' sales'; }}).observe(salesNode, {{ childList: true }});
      }}
    </script>
    """
