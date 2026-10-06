from __future__ import annotations

from pathlib import Path


def _loading_overlay_css() -> str:
    return Path(__file__).with_name("loading_overlay.css").read_text(encoding="utf-8")


def dashboard_nav_css() -> str:
    theme = Path(__file__).with_name("ops_theme.css").read_text(encoding="utf-8")
    return (
        _legacy_nav_css()
        + "\n"
        + theme
        + "\n"
        + _sidebar_link_css()
        + "\n"
        + _nav_collapse_css()
        + "\n"
        + _nav_state_boot()
        + "\n"
        + _embed_chrome_css()
        + "\n"
        + _loading_overlay_css()
    )


def _sidebar_link_css() -> str:
    """Lock Operations sidebar anchors to the Company Overview link look.

    Legacy pages append `.navbtn { background:#fff; border-radius:12px }` after
    this sheet. Sidebar anchors are `navlink` only, and these declarations use
    !important so a later page rule cannot paint them as pills.
    """
    return """
    #sidebar a.navlink {
      display: flex !important;
      align-items: center;
      gap: 10px;
      width: auto;
      margin: 2px 0 !important;
      padding: 11px 12px !important;
      border: 0 !important;
      border-radius: 6px !important;
      background: transparent !important;
      background-color: transparent !important;
      box-shadow: none !important;
      color: #a7bfd2 !important;
      font-size: 12px !important;
      font-weight: 400 !important;
      line-height: 1.3;
      letter-spacing: 0;
      text-decoration: none !important;
      text-transform: none;
      white-space: normal !important;
      flex: none !important;
    }
    #sidebar a.navlink:hover {
      background: #102e46 !important;
      background-color: #102e46 !important;
      color: #fff !important;
      border-color: transparent !important;
      box-shadow: none !important;
      text-decoration: none !important;
      transform: translateX(2px);
    }
    #sidebar a.navlink.active {
      background: #123e52 !important;
      background-color: #123e52 !important;
      color: #26d9eb !important;
      border-color: transparent !important;
      box-shadow: inset 2px 0 #26d9eb !important;
      text-decoration: none !important;
    }
    @media (prefers-reduced-motion: reduce) {
      #sidebar a.navlink:hover { transform: none; }
    }
    button.mobile-menu.oc-menu-btn {
      display: none;
      align-items: center;
      justify-content: center;
      background: #102d43;
      color: #f1f6ff;
      border: 1px solid #2b4c63;
      border-radius: 7px;
      font-weight: 600;
      line-height: 1;
      cursor: pointer;
    }
    @media (max-width: 800px) {
      #sidebar { transform: translateX(-100%); width: 222px; }
      body.menu-open #sidebar { transform: translateX(0); }
      button.mobile-menu.oc-menu-btn {
        display: inline-flex;
        position: fixed;
        top: 10px;
        left: 10px;
        z-index: 40;
        padding: 8px 10px;
      }
    }
    """


def _nav_mark(title: str) -> str:
    """Two-letter rail mark. Acronyms keep their first two letters."""
    cleaned = title.replace("&", " ").replace("/", " ")
    words = [word for word in cleaned.split() if any(ch.isalnum() for ch in word)]
    if not words:
        return "•"
    first = "".join(ch for ch in words[0] if ch.isalnum())
    if len(words) == 1 or (first.isupper() and len(first) >= 3):
        return first[:2].upper()
    second = "".join(ch for ch in words[1] if ch.isalnum())
    return (first[:1] + (second[:1] or first[1:2])).upper()


def _nav_collapse_css() -> str:
    """Desktop/tablet rail. Mobile keeps the existing off-canvas drawer."""
    return """
    .oc-nav-tools {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      padding: 10px 10px 0;
      flex: none;
    }
    #sidebar .navmark { display: none; }
    #ocNavToggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      min-width: 28px;
      padding: 0;
      margin: 0;
      border: 1px solid #2b4c63;
      border-radius: 7px;
      background: #102d43;
      color: #f1f6ff;
      box-shadow: none;
      cursor: pointer;
      line-height: 1;
      font-weight: 600;
      flex: none;
    }
    #ocNavToggle:hover {
      background: #193c54;
      border-color: #40657d;
      color: #fff;
    }
    #ocNavToggle:focus-visible {
      outline: 2px solid #26d9eb;
      outline-offset: 2px;
    }
    .oc-nav-chevron {
      display: block;
      width: 8px;
      height: 8px;
      border-right: 2px solid currentColor;
      border-bottom: 2px solid currentColor;
      transform: rotate(135deg);
      margin-left: 3px;
    }
    html.oc-nav-collapsed .oc-nav-chevron {
      transform: rotate(-45deg);
      margin-left: 0;
      margin-right: 3px;
    }
    @media (min-width: 801px) {
      html.oc-nav-collapsed #sidebar { width: 64px; box-sizing: border-box; }
      html.oc-nav-collapsed #sidebar .oc-nav-tools {
        justify-content: center;
        padding: 10px 6px 0;
      }
      html.oc-nav-collapsed #sidebar .brand {
        height: auto;
        padding: 8px 6px 10px;
        justify-content: center;
        gap: 0;
      }
      html.oc-nav-collapsed #sidebar .brand-copy,
      html.oc-nav-collapsed #sidebar .navlabel,
      html.oc-nav-collapsed #sidebar .sidebottom > div {
        position: absolute !important;
        width: 1px !important;
        height: 1px !important;
        padding: 0 !important;
        margin: -1px !important;
        overflow: hidden !important;
        clip: rect(0, 0, 0, 0) !important;
        white-space: nowrap !important;
        border: 0 !important;
      }
      html.oc-nav-collapsed #sidebar .navgroup {
        height: 0;
        margin: 8px 12px 4px;
        padding: 0;
        overflow: hidden;
        color: transparent;
        font-size: 0;
        letter-spacing: 0;
        border-top: 1px solid #234358;
      }
      html.oc-nav-collapsed #sidebar .navgroup:first-child {
        height: 0;
        margin-top: 4px;
        padding: 0;
        border-top: 0;
      }
      html.oc-nav-collapsed #sidebar .navmark {
        display: inline-flex !important;
        align-items: center;
        justify-content: center;
        min-width: 1.6em;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.04em;
        color: inherit;
      }
      html.oc-nav-collapsed #sidebar a.navlink {
        justify-content: center !important;
        gap: 0 !important;
        margin: 2px 6px !important;
        padding: 8px 4px !important;
      }
      html.oc-nav-collapsed #sidebar a.navlink:hover { transform: none !important; }
      html.oc-nav-collapsed #sidebar .sidebottom {
        min-height: 72px;
        padding: 10px 6px;
        justify-content: center;
      }
      html.oc-nav-collapsed .workspace,
      html.oc-nav-collapsed body.oc-root .wrap,
      html.oc-nav-collapsed .wrap {
        margin-left: 64px !important;
        max-width: calc(100% - 64px);
        min-width: 0;
        box-sizing: border-box;
      }
      html.oc-nav-collapsed body:not(:has(.wrap)):not(:has(.workspace)) {
        padding-left: 64px !important;
      }
    }
    @media (min-width: 801px) and (prefers-reduced-motion: no-preference) {
      #sidebar { transition: width .18s ease; }
      .workspace,
      body.oc-root .wrap,
      html.oc-nav-collapsed .wrap {
        transition: margin-left .18s ease;
      }
      body.oc-root:not(:has(.wrap)):not(:has(.workspace)) {
        transition: padding-left .18s ease;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      #sidebar,
      .workspace,
      .wrap,
      .oc-nav-chevron {
        transition: none !important;
      }
    }
    @media (max-width: 800px) {
      .oc-nav-tools { display: none !important; }
      html.oc-nav-collapsed #sidebar { width: 222px; }
      html.oc-nav-collapsed .workspace,
      html.oc-nav-collapsed .wrap,
      html.oc-nav-collapsed body.oc-root .wrap {
        margin-left: 0 !important;
        max-width: none;
      }
      html.oc-nav-collapsed body:not(:has(.wrap)):not(:has(.workspace)) {
        padding-left: 0 !important;
      }
    }
    """


def _nav_state_boot() -> str:
    """Apply saved rail state, and the embedded shell, before first paint.

    Callers place dashboard_nav_css() inside a <style> block in the document
    head. Closing that block here lets the class land on <html> before the
    body is parsed.

    A framed page, or `?embed=1`, is `html.oc-embedded`. That shell hides the
    sidebar and the operations top bar and shows the section switcher.
    Standalone pages keep the rail. A framed viewer with no saved choice still
    starts collapsed, which only shows when the rail itself is shown.
    """
    return (
        "</style><script>(function(){var d=document.documentElement,f=false,q=false;"
        "try{f=window.self!==window.top;}catch(e){f=true;}"
        "try{q=/(?:^|[?&])embed=1(?:&|$)/.test(location.search);}catch(e){}"
        "if(f||q){d.classList.add('oc-embedded');}"
        "try{var s=localStorage.getItem('hsOpsNavCollapsed');"
        "if(s==='1'||(f&&s===null)){d.classList.add('oc-nav-collapsed');}}catch(e){}})();"
        "</script><style>"
    )


def _embed_chrome_css() -> str:
    """One section row when Bloom frames the app, or when `?embed=1` is set.

    The rail and the operations crumb bar are the duplicate chrome. The
    switcher keeps every section reachable. Standalone pages never match
    `html.oc-embedded`, so their rail and top bar stay put.
    """
    return """
    .oc-embed-bar { display: none; }
    html.oc-embedded {
      --oc-embed-bar: 44px;
      scroll-padding-top: var(--oc-embed-bar);
    }
    html.oc-embedded .oc-embed-bar {
      display: flex;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: var(--oc-embed-bar);
      z-index: 30;
      box-sizing: border-box;
      max-width: 100%;
      background: #081e31;
      border-bottom: 1px solid #203e54;
      align-items: stretch;
      overflow: hidden;
    }
    html.oc-embedded .oc-embed-nav {
      display: flex;
      flex: 1 1 auto;
      align-items: stretch;
      min-width: 0;
      margin: 0;
      padding: 0 4px;
      overflow-x: auto;
      overflow-y: hidden;
      overscroll-behavior-x: contain;
      scrollbar-width: thin;
      scrollbar-color: #29475c transparent;
    }
    html.oc-embedded .oc-embed-nav a {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      box-sizing: border-box;
      margin: 0;
      padding: 0 12px;
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      background: transparent !important;
      color: #a7bfd2 !important;
      font: 12px/1.2 'DM Sans', Arial, sans-serif;
      text-decoration: none !important;
      white-space: nowrap;
    }
    html.oc-embedded .oc-embed-nav a:hover {
      background: #102e46 !important;
      color: #fff !important;
      text-decoration: none !important;
    }
    html.oc-embedded .oc-embed-nav a.active {
      background: transparent !important;
      color: #26d9eb !important;
      border-bottom-color: #26d9eb;
    }
    html.oc-embedded .oc-embed-nav a:focus-visible {
      outline: 2px solid #26d9eb;
      outline-offset: -2px;
    }
    html.oc-embedded .oc-embed-sep {
      flex: 0 0 auto;
      align-self: center;
      width: 1px;
      height: 16px;
      margin: 0 4px;
      background: #234358;
    }
    html.oc-embedded .oc-embed-status {
      flex: 0 1 auto;
      align-self: center;
      max-width: 34%;
      margin-left: 8px;
      padding: 0 12px 0 8px;
      overflow: hidden;
      color: #91abc0;
      font: 11px/1.2 'DM Sans', Arial, sans-serif;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    html.oc-embedded #sidebar,
    html.oc-embedded .oc-menu-btn,
    html.oc-embedded button.mobile-menu {
      display: none !important;
    }
    html.oc-embedded .workspace,
    html.oc-embedded body.oc-root .wrap,
    html.oc-embedded .wrap {
      margin-left: 0 !important;
      margin-right: 0 !important;
      max-width: 100% !important;
      min-width: 0 !important;
      box-sizing: border-box;
      padding-top: var(--oc-embed-bar) !important;
    }
    html.oc-embedded body,
    html.oc-embedded body.oc-root,
    html.oc-embedded body.oc-root:not(:has(.wrap)):not(:has(.workspace)) {
      padding-left: 0 !important;
    }
    html.oc-embedded body:not(:has(.wrap)):not(:has(.workspace)) {
      padding-top: var(--oc-embed-bar) !important;
    }
    html.oc-embedded .oc-page .topbar {
      display: none !important;
    }
    html.oc-embedded .oc-page .global-filterbar {
      top: var(--oc-embed-bar);
    }
    @media (max-width: 800px) {
      html.oc-embedded .oc-embed-status { display: none; }
      html.oc-embedded .oc-embed-nav a { padding: 0 10px; }
    }
    @media (prefers-reduced-motion: reduce) {
      html.oc-embedded .oc-embed-nav { scroll-behavior: auto; }
    }
    """


def _render_embed_nav(current: str) -> str:
    parts: list[str] = []
    for index, (_label, items) in enumerate(NAV_GROUPS):
        if index:
            parts.append('<span class="oc-embed-sep" aria-hidden="true"></span>')
        for key, title, href in items:
            active = " active" if current == key else ""
            current_attr = ' aria-current="page"' if current == key else ""
            external = ' target="_blank" rel="noopener noreferrer"' if href.startswith("http") else ""
            parts.append(
                f'<a class="oc-embed-link{active}" href="{href}"{current_attr}{external}>{title}</a>'
            )
    links = "".join(parts)
    return (
        '<div class="oc-embed-bar">'
        f'<nav class="oc-embed-nav" aria-label="Data Center sections">{links}</nav>'
        "</div>"
    )


def _legacy_nav_css() -> str:
    return """
    .hs-loader {
      position: fixed;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 12px;
      background: transparent;
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      z-index: 9998;
      opacity: 1;
      visibility: visible;
      pointer-events: none;
      transition: opacity 0.22s ease, visibility 0.22s ease;
    }

    .hs-loader.is-hidden {
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
    }

    .hs-loader-card {
      min-width: 0;
      width: min(168px, 62vw);
      padding: 10px 12px 10px;
      border-radius: 16px;
      border: 1px solid rgba(232,236,240,0.92);
      background: rgba(255,255,255,0.96);
      box-shadow: 0 8px 18px rgba(17,24,39,0.06);
      text-align: center;
    }

    .hs-loader-mark {
      position: relative;
      width: 52px;
      height: 38px;
      margin: 0 auto 10px;
      animation: hs-loader-spin 1.45s linear infinite;
      transform-origin: 50% 58%;
    }

    .hs-loader-top,
    .hs-loader-bottom {
      position: absolute;
      left: 50%;
    }

    .hs-loader-top {
      top: 0;
      width: 16px;
      height: 8px;
      margin-left: -8px;
      border: 4px solid #f97344;
      border-bottom: 0;
      border-radius: 16px 16px 0 0;
    }

    .hs-loader-bottom {
      bottom: 0;
      width: 36px;
      height: 18px;
      margin-left: -18px;
      border: 5px solid #f7a90b;
      border-top: 0;
      border-radius: 0 0 36px 36px;
    }

    .hs-loader-wordmark {
      color: #f7a90b;
      font-size: clamp(12px, 1.8vw, 16px);
      font-weight: 900;
      line-height: 1;
      letter-spacing: -0.05em;
    }

    .hs-loader-caption {
      margin-top: 5px;
      color: #64748b;
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    .hs-loader-subcaption {
      margin-top: 3px;
      color: #94a3b8;
      font-size: 8px;
    }

    @keyframes hs-loader-spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .nav {
      margin-top: 12px;
      display:flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: center;
      width: 100%;
    }

    .navmenu {
      position: relative;
    }

    .navmenu summary {
      list-style: none;
      cursor: pointer;
    }

    .navmenu summary::-webkit-details-marker {
      display: none;
    }

    .navmenu summary.navbtn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .navmenu-caret {
      font-size: 10px;
      line-height: 1;
      transition: transform 0.15s ease;
    }

    .navmenu[open] .navmenu-caret {
      transform: rotate(180deg);
    }

    .navmenu-list {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      min-width: 220px;
      max-width: min(280px, calc(100vw - 24px));
      padding: 8px;
      border-radius: 14px;
      border: 1px solid var(--border, #e8ecf0);
      background: #fff;
      box-shadow: 0 10px 24px rgba(17,24,39,0.10);
      display: flex;
      flex-direction: column;
      gap: 6px;
      z-index: 30;
    }

    .navmenu-item {
      display: block;
      padding: 9px 12px;
      border-radius: 10px;
      border: 1px solid transparent;
      color: #1f2937;
      font-size: 13px;
      font-weight: 800;
      text-decoration: none;
      white-space: nowrap;
    }

    .navmenu-item:hover {
      background: #f8fafc;
      border-color: var(--border, #e8ecf0);
    }

    .navmenu-item.active {
      background: rgba(16,185,129,0.10);
      border-color: rgba(16,185,129,0.35);
      color: #0f766e;
    }

    @media (max-width: 640px) {
      .nav {
        flex-wrap: wrap !important;
        justify-content: flex-start !important;
        overflow: visible !important;
      }

      .navmenu {
        flex: 0 0 auto;
      }

      .navmenu-list {
        left: 0;
        right: auto;
        min-width: min(220px, calc(100vw - 24px));
      }

      .navmenu:last-child .navmenu-list {
        left: auto;
        right: 0;
      }

      .navmenu-list {
        min-width: 200px;
      }
    }

    body.oc-root {
      background: #061727 !important;
      color: #f1f6ff;
      font-family: "DM Sans", Arial, sans-serif;
    }
    body.oc-root .wrap {
      margin-left: 222px;
      max-width: 1800px;
    }
    body.oc-root .card,
    body.oc-root .topbar,
    body.oc-root .panel {
      background: #0d293f !important;
      color: #f1f6ff !important;
      border-color: #2b4e66 !important;
      box-shadow: none;
    }
    body.oc-root .title,
    body.oc-root .card-title,
    body.oc-root h1,
    body.oc-root h2 {
      color: #f1f6ff;
    }
    body.oc-root .subtitle,
    body.oc-root .meta,
    body.oc-root .section-title {
      color: #91abc0 !important;
    }
    body.oc-root .pinkline { display: none; }
    body.oc-root table { color: #d5e3ec; }
    body.oc-root th { color: #91abc0 !important; background: #0a2236; }
    body.oc-root td { color: #d5e3ec; border-color: #1b384c; }
    body.oc-root .wrap a.navbtn,
    body.oc-root .wrap .navbtn { color: #1f2937 !important; }
    body.oc-root .wrap a.navbtn.active,
    body.oc-root .wrap .navbtn.active { color: #0a7a34 !important; }
    body.oc-root input,
    body.oc-root select {
      background: #091e30;
      color: #bed1df;
      border-color: #29485e;
    }
    .oc-menu-btn { display: none; }
    @media (max-width: 1100px) and (min-width: 801px) {
      body.oc-root .wrap { margin-left: 194px; }
    }
    @media (max-width: 800px) {
      body.oc-root .wrap { margin-left: 0; }
      .oc-menu-btn { display: inline-flex; position: fixed; top: 10px; left: 10px; z-index: 40; }
    }
    .oc-injected-filters { margin: 12px 16px 16px; }
    .oc-injected-filters .global-filterbar,
    .oc-injected-filters.global-filterbar {
      background: #0a2438;
      border: 1px solid #31566f;
      border-radius: 10px;
      padding: 12px 15px;
    }
    .oc-injected-filters .filter-controls {
      display: flex;
      align-items: end;
      gap: 12px;
      flex-wrap: wrap;
    }
    .oc-injected-filters label {
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex: 1;
      min-width: 140px;
      font-size: 11px;
      color: #82a9c0;
    }
    .oc-injected-filters input,
    .oc-injected-filters select {
      height: 35px;
      border-radius: 7px;
      padding: 0 8px;
    }
    .oc-injected-filters .filter-reset {
      height: 35px;
      border: 1px solid #2b4c63;
      background: #102d43;
      color: #f1f6ff;
      border-radius: 7px;
      padding: 0 12px;
    }
    .oc-injected-filters .filter-chips {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
      color: #91abc0;
      font-size: 12px;
    }
    .oc-injected-filters .filter-chips button {
      border: 1px solid #2b4c63;
      background: #102d43;
      color: #f1f6ff;
      border-radius: 999px;
      padding: 4px 10px;
    }
    @media (min-width: 1101px) {
      body.oc-root:not(:has(.wrap)):not(:has(.workspace)) { padding-left: 222px; }
    }
    @media (max-width: 1100px) and (min-width: 801px) {
      body.oc-root:not(:has(.wrap)):not(:has(.workspace)) { padding-left: 194px; }
    }
    """


def render_dashboard_loader() -> str:
    return """
        <div id="hsDashboardLoader" class="hs-loader is-hidden" aria-hidden="true">
          <div class="hs-loader-card">
            <div class="hs-loader-mark" aria-hidden="true">
              <div class="hs-loader-top"></div>
              <div class="hs-loader-bottom"></div>
            </div>
            <div class="hs-loader-wordmark">Happy Solar</div>
            <div class="hs-loader-caption">Loading Dashboard</div>
            <div class="hs-loader-subcaption">Pulling live metrics and rep breakdowns</div>
          </div>
        </div>
    """




NAV_GROUPS = (
    (
        "COMPANY",
        (
            ("company_overview", "Company Overview", "/api/company_overview"),
            ("goals_dashboard", "Goals Dashboard", "/api/goals_dashboard"),
            ("daily_update", "Daily Dashboard", "/api/daily_update"),
            ("morning_brief", "Morning Brief", "/api/morning_brief"),
        ),
    ),
    (
        "SALES",
        (
            ("sales_dashboard", "Sales Dashboard", "/api/sales_dashboard"),
            ("sales_list", "Sales List", "/api/sales_list"),
            ("rep_daily_recap", "Rep Daily Recap", "/api/rep_daily_recap"),
            ("missing_dispos", "Missing Dispositions", "/api/missing_dispos"),
        ),
    ),
    (
        "LEAD GENERATION",
        (
            ("fma_dashboard", "FMA Dashboard", "/api/fma_dashboard"),
            ("appointment_outcomes", "Appointment Outcomes", "/api/appointment_outcomes"),
            ("fma_commissions", "FMA Commissions", "/api/fma_commissions"),
        ),
    ),
    (
        "PROJECT MANAGEMENT",
        (
            (
                "project_management_hub",
                "Project Hub",
                "https://happy-solar-monday-pm.vercel.app/project-management-hub.html",
            ),
            (
                "hold_cancelled",
                "Hold / Cancelled",
                "https://happy-solar-monday-pm.vercel.app/happy-slr-hold-cancelled.html",
            ),
        ),
    ),
    (
        "INBOUND",
        (
            ("paid_social_funnel", "Ads & Inbound Funnel", "/api/paid_social_funnel"),
            ("website_funnel", "Website Funnel", "/api/website_funnel"),
            ("website_traffic", "Website Traffic", "/api/website_traffic"),
        ),
    ),
    (
        "OTHER",
        (
            ("sale_cancellation_report", "Sale Cancellations", "/api/sale_cancellation_report"),
            ("bot_kpi_scorecard", "Bot KPI Scorecard", "/api/bot_kpi_scorecard"),
            ("settings", "Admin Settings", "/api/settings"),
        ),
    ),
)


def render_dashboard_nav(current: str) -> str:
    groups = []
    for label, items in NAV_GROUPS:
        links = []
        for key, title, href in items:
            active = " active" if current == key else ""
            external = ""
            if href.startswith("http"):
                external = ' target="_blank" rel="noopener noreferrer"'
            mark = _nav_mark(title)
            links.append(
                f'<a class="navlink{active}" href="{href}" aria-label="{title}"{external}>'
                f'<span class="navmark" aria-hidden="true">{mark}</span>'
                f'<span class="navlabel">{title}</span></a>'
            )
        groups.append(
            f'<div class="navgroup">{label}</div>' + "".join(links)
        )
    menu = "".join(groups)
    embed_nav = _render_embed_nav(current)
    html = f"""
        {render_dashboard_loader()}
        <button type="button" class="mobile-menu oc-menu-btn" aria-label="Toggle navigation" onclick="document.body.classList.toggle('menu-open')">☰</button>
        <aside id="sidebar">
          <div class="oc-nav-tools">
            <button type="button" id="ocNavToggle" class="oc-nav-toggle" aria-controls="sidebar" aria-expanded="true" aria-label="Collapse navigation">
              <span class="oc-nav-chevron" aria-hidden="true"></span>
            </button>
          </div>
          <script>
            (function() {{
              var toggle = document.getElementById('ocNavToggle');
              if (!toggle) return;
              var collapsed = document.documentElement.classList.contains('oc-nav-collapsed');
              toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
              toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
            }})();
          </script>
          <div class="brand"><span class="brandmark" aria-hidden="true">☀</span><div class="brand-copy">HAPPY SOLAR<small>OPERATIONS</small></div></div>
          <nav class="navscroll" aria-label="Operations">{menu}</nav>
          <div class="sidebottom"><div><b>Operations control</b>America/New_York</div></div>
        </aside>
        {embed_nav}
        <!-- HAPPY_SOLAR_LOADING -->
        <script>
          (function() {{
            document.documentElement.classList.add('oc-root');
            document.body.classList.add('oc-root');
            (function prepareEmbedNav() {{
              if (!document.documentElement.classList.contains('oc-embedded')) return;
              var bar = document.querySelector('.oc-embed-bar');
              var sectionNav = document.querySelector('.oc-embed-nav');
              if (bar && bar.parentElement !== document.body) document.body.insertBefore(bar, document.body.firstChild);
              if (!sectionNav) return;
              try {{
                var params = new URLSearchParams(window.location.search);
                if (params.get('embed') === '1') {{
                  var sectionLinks = sectionNav.querySelectorAll('a[href^="/"]');
                  for (var s = 0; s < sectionLinks.length; s++) {{
                    var sectionUrl = new URL(sectionLinks[s].getAttribute('href'), window.location.href);
                    sectionUrl.searchParams.set('embed', '1');
                    sectionLinks[s].setAttribute('href', sectionUrl.pathname + sectionUrl.search + sectionUrl.hash);
                  }}
                }}
              }} catch (err) {{}}
              function scrollActiveSection() {{
                var activeSection = sectionNav.querySelector('a.active');
                if (!activeSection || !sectionNav.clientWidth) return;
                var nextLeft = activeSection.offsetLeft - Math.max(0, (sectionNav.clientWidth - activeSection.offsetWidth) / 2);
                if (nextLeft > 0) sectionNav.scrollLeft = nextLeft;
              }}
              scrollActiveSection();
              window.requestAnimationFrame(scrollActiveSection);
              function placeEmbedStatus() {{
                var status = document.getElementById('asOf');
                if (!bar || !status || bar.contains(status)) return;
                status.classList.add('oc-embed-status');
                bar.appendChild(status);
              }}
              if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', placeEmbedStatus);
              else placeEmbedStatus();
            }})();
            var NAV_COLLAPSE_KEY = 'hsOpsNavCollapsed';
            function navIsCollapsed() {{
              return document.documentElement.classList.contains('oc-nav-collapsed');
            }}
            function syncNavToggle() {{
              var toggle = document.getElementById('ocNavToggle');
              var collapsed = navIsCollapsed();
              if (toggle) {{
                toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
              }}
              var links = document.querySelectorAll('#sidebar a.navlink');
              for (var i = 0; i < links.length; i++) {{
                var label = links[i].getAttribute('aria-label') || '';
                if (collapsed && label) links[i].setAttribute('title', label);
                else links[i].removeAttribute('title');
              }}
            }}
            function remeasureCharts() {{
              var root = document.querySelector('.workspace') || document.querySelector('.wrap') || document.body;
              if (root) void root.offsetWidth;
              var nodes = document.querySelectorAll('svg.chart, svg.history-chart, svg.lineChart, svg.sparkline, .chart svg, .chartBox svg, .vchart, canvas');
              for (var n = 0; n < nodes.length; n++) {{
                var node = nodes[n];
                if (!node || !node.getBoundingClientRect) continue;
                var parent = node.parentElement;
                var parentW = parent ? parent.clientWidth : 0;
                if (node.tagName === 'SVG' && parentW) {{
                  var attr = node.getAttribute('width');
                  var vb = node.viewBox && node.viewBox.baseVal;
                  if (attr && /^[0-9]+(\\.[0-9]+)?$/.test(attr) && vb && vb.width > 0) {{
                    var next = Math.floor(parentW);
                    if (Math.abs(parseFloat(attr) - next) > 1) {{
                      node.setAttribute('width', String(next));
                      var heightAttr = node.getAttribute('height');
                      if (heightAttr && /^[0-9]+(\\.[0-9]+)?$/.test(heightAttr) && vb.height > 0) {{
                        node.setAttribute('height', String(Math.max(1, Math.round(next * (vb.height / vb.width)))));
                      }}
                    }}
                  }}
                }}
                if (node.tagName === 'CANVAS') {{
                  var chart = null;
                  if (window.Chart && typeof window.Chart.getChart === 'function') chart = window.Chart.getChart(node);
                  if (!chart) chart = node.chart || null;
                  if (chart && typeof chart.resize === 'function') chart.resize();
                }}
                node.getBoundingClientRect();
              }}
              window.dispatchEvent(new Event('resize'));
            }}
            function scheduleChartRemeasure() {{
              remeasureCharts();
              window.requestAnimationFrame(function() {{
                remeasureCharts();
                window.setTimeout(remeasureCharts, 240);
              }});
            }}
            function setNavCollapsed(collapsed) {{
              document.documentElement.classList.toggle('oc-nav-collapsed', !!collapsed);
              try {{ localStorage.setItem(NAV_COLLAPSE_KEY, collapsed ? '1' : '0'); }} catch (err) {{}}
              syncNavToggle();
              scheduleChartRemeasure();
            }}
            try {{
              var savedNav = localStorage.getItem(NAV_COLLAPSE_KEY);
              var framedNav = document.documentElement.classList.contains('oc-embedded');
              if (savedNav === '1' || (framedNav && savedNav === null)) {{
                document.documentElement.classList.add('oc-nav-collapsed');
              }}
            }} catch (err) {{}}
            syncNavToggle();
            window.hsOpsReflowCharts = remeasureCharts;
            var navToggle = document.getElementById('ocNavToggle');
            if (navToggle) {{
              navToggle.addEventListener('click', function(event) {{
                event.stopPropagation();
                setNavCollapsed(!navIsCollapsed());
              }});
            }}
            var navSide = document.getElementById('sidebar');
            if (navSide) {{
              navSide.addEventListener('transitionend', function(event) {{
                if (event.propertyName === 'width') remeasureCharts();
              }});
            }}
            window.HSDashboardLoader = {{
              show: function() {{ if (window.HappySolarLoading) window.HappySolarLoading.begin('manual'); }},
              hide: function() {{}},
            }};
            var FILTER_KEY = 'hsOpsFilters';
            function readStored() {{
              try {{ return JSON.parse(localStorage.getItem(FILTER_KEY) || '{{}}') || {{}}; }} catch (e) {{ return {{}}; }}
            }}
            function nyToday() {{
              return new Intl.DateTimeFormat('en-CA', {{ timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }}).format(new Date());
            }}
            window.hsOpsReadFilters = function() {{
              var params = new URLSearchParams(window.location.search);
              var stored = readStored();
              var today = nyToday();
              return {{
                start: params.get('start') || stored.start || (today.slice(0, 8) + '01'),
                end: params.get('end') || stored.end || today,
                territory: params.get('territory') || stored.territory || 'All',
                source: params.get('source') || stored.source || 'All'
              }};
            }};
            window.hsOpsWriteFilters = function(filters) {{
              localStorage.setItem(FILTER_KEY, JSON.stringify(filters));
            }};
            if (window.fetch && !window.__hsOpsFetchPatched) {{
              window.__hsOpsFetchPatched = true;
              var originalFetch = window.fetch.bind(window);
              window.fetch = function(input, init) {{
                var next = input;
                try {{
                  var raw = typeof input === 'string' ? input : (input && input.url) || '';
                  var url = new URL(raw, window.location.href);
                  if (url.origin === window.location.origin && url.pathname.indexOf('/api/metrics/') === 0 && !url.searchParams.has('oc_raw')) {{
                    var f = window.hsOpsReadFilters();
                    var ownsDates = url.searchParams.has('start') || url.searchParams.has('end') || url.searchParams.has('year') || url.searchParams.has('month');
                    if (!ownsDates && f.start && f.end) {{
                      url.searchParams.set('start', f.start);
                      url.searchParams.set('end', f.end);
                    }}
                    var specialized = url.searchParams.has('lead_source') || url.searchParams.has('pipeline') || url.searchParams.has('sweeper') || url.searchParams.has('pipeline_scope');
                    if (!specialized) {{
                      if (f.territory && f.territory !== 'All') url.searchParams.set('pipeline', f.territory);
                      if (f.source === 'Sweeper') url.searchParams.set('sweeper', '1');
                      else if (f.source && f.source !== 'All') {{
                        url.searchParams.set('lead_source', f.source === 'Self gen' ? 'Self Gen' : f.source);
                      }}
                    }}
                    next = url.toString();
                  }}
                }} catch (_err) {{}}
                if (window.HappySolarLoading) return window.HappySolarLoading.fetch(originalFetch, next, init);
                return originalFetch(next, init);
              }};
            }}
            document.addEventListener('keydown', function(event) {{
              if (event.key === 'Escape') document.body.classList.remove('menu-open');
            }});
            document.addEventListener('click', function(event) {{
              var side = document.getElementById('sidebar');
              var btn = document.querySelector('.oc-menu-btn');
              if (!document.body.classList.contains('menu-open')) return;
              if (side && (side.contains(event.target) || (btn && btn.contains(event.target)))) return;
              document.body.classList.remove('menu-open');
            }});
            if (document.body.getAttribute('data-oc-native-filters') === '1') return;
            var host = document.querySelector('.wrap') || document.body;
            var f = window.hsOpsReadFilters();
            var ownDates = document.body.getAttribute('data-oc-own-dates') === '1';
            var bar = document.createElement('div');
            bar.className = 'global-filterbar oc-injected-filters' + (ownDates ? ' oc-own-dates' : '');
            var dateControls = ownDates
              ? '<input id="ocStart" type="hidden" value="'+f.start+'"><input id="ocEnd" type="hidden" value="'+f.end+'">'
              : '<label>Dates from<input id="ocStart" type="date" aria-label="Start date" value="'+f.start+'"></label><label>Dates to<input id="ocEnd" type="date" aria-label="End date" value="'+f.end+'"></label>';
            bar.innerHTML = '<div class="filter-controls">'+dateControls+'<label>Territory<select id="ocTerritory" aria-label="Territory">'+['All','Buffalo','Rochester','Syracuse','Virtual'].map(function(x){{return '<option'+(f.territory===x?' selected':'')+'>'+x+'</option>';}}).join('')+'</select></label><label>Lead source<select id="ocSource" aria-label="Lead source">'+['All','Doors','Self gen','Sweeper','Inbound','3PL'].map(function(x){{return '<option'+(f.source===x?' selected':'')+'>'+x+'</option>';}}).join('')+'</select></label><button type="button" class="filter-reset" id="ocReset">Reset filters</button></div><div class="filter-chips" id="ocChips"></div>';
            host.insertBefore(bar, host.firstChild);
            function chips() {{
              var cur = window.hsOpsReadFilters();
              var html = '';
              if (cur.territory !== 'All') html += '<button type="button" data-k="territory">'+cur.territory+' <span>×</span></button>';
              if (cur.source !== 'All') html += '<button type="button" data-k="source">'+cur.source+' <span>×</span></button>';
              html += ownDates
                ? '<span>This page sets its own dates below, so the shared date filter is hidden here. Territory and lead source apply to cards that have no filter of their own.</span>'
                : '<span>Filters apply to metric requests. Pages with their own date control still show that control.</span>';
              document.getElementById('ocChips').innerHTML = html;
            }}
            function apply(partial) {{
              var cur = window.hsOpsReadFilters();
              var next = {{
                start: document.getElementById('ocStart').value || cur.start,
                end: document.getElementById('ocEnd').value || cur.end,
                territory: document.getElementById('ocTerritory').value,
                source: document.getElementById('ocSource').value
              }};
              if (partial) Object.assign(next, partial);
              window.hsOpsWriteFilters(next);
              var u = new URL(window.location.href);
              u.searchParams.set('start', next.start);
              u.searchParams.set('end', next.end);
              if (next.territory === 'All') u.searchParams.delete('territory'); else u.searchParams.set('territory', next.territory);
              if (next.source === 'All') u.searchParams.delete('source'); else u.searchParams.set('source', next.source);
              window.location.href = u.toString();
            }}
            ['ocStart','ocEnd','ocTerritory','ocSource'].forEach(function(id) {{
              document.getElementById(id).addEventListener('change', function() {{ apply(); }});
            }});
            document.getElementById('ocReset').addEventListener('click', function() {{
              var today = nyToday();
              document.getElementById('ocStart').value = today.slice(0, 8) + '01';
              document.getElementById('ocEnd').value = today;
              document.getElementById('ocTerritory').value = 'All';
              document.getElementById('ocSource').value = 'All';
              apply();
            }});
            document.getElementById('ocChips').addEventListener('click', function(event) {{
              var b = event.target.closest('button');
              if (!b) return;
              var patch = {{}};
              patch[b.getAttribute('data-k')] = 'All';
              apply(patch);
            }});
            window.hsOpsRerenderFilters = function() {{
              var cur = window.hsOpsReadFilters();
              var start = document.getElementById('ocStart');
              if (!start) return;
              start.value = cur.start;
              document.getElementById('ocEnd').value = cur.end;
              document.getElementById('ocTerritory').value = cur.territory;
              document.getElementById('ocSource').value = cur.source;
              chips();
            }};
            chips();
          }})();
        </script>
    """
    overlay = Path(__file__).with_name("loading_overlay_script.txt").read_text(encoding="utf-8")
    return html.replace(
        "<!-- HAPPY_SOLAR_LOADING -->",
        "<script>\n" + overlay + "\n</script>",
    )
