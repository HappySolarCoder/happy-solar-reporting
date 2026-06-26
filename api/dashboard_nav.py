from __future__ import annotations


def dashboard_nav_css() -> str:
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
    """


def render_dashboard_loader() -> str:
    return """
        <div id="hsDashboardLoader" class="hs-loader" aria-hidden="false">
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


def render_dashboard_nav(current: str) -> str:
    sales_active = current in {"sales_dashboard", "sale_cancellation_report"}
    lead_gen_active = current in {
        "fma_dashboard",
        "virtual_team_dashboard",
        "powerline_dashboard",
        "appointment_outcomes",
        "fma_commissions",
        "fma_monthly_kickoff",
    }

    def active(name: str) -> str:
        return " active" if current == name else ""

    return f"""
        {render_dashboard_loader()}
        <div class="nav">
          <a class="navbtn{active('company_overview')}" href="/api/company_overview">Company Overview</a>
          <details class="navmenu">
            <summary class="navbtn{' active' if sales_active else ''}">Sales <span class="navmenu-caret">▾</span></summary>
            <div class="navmenu-list">
              <a class="navmenu-item{active('sales_dashboard')}" href="/api/sales_dashboard">Sales Dashboard</a>
              <a class="navmenu-item{active('sale_cancellation_report')}" href="/api/sale_cancellation_report">Sale Cancellations</a>
            </div>
          </details>
          <details class="navmenu">
            <summary class="navbtn{' active' if lead_gen_active else ''}">Lead Generation <span class="navmenu-caret">▾</span></summary>
            <div class="navmenu-list">
              <a class="navmenu-item{active('fma_dashboard')}" href="/api/fma_dashboard">FMA Dashboard</a>
              <a class="navmenu-item{active('virtual_team_dashboard')}" href="/api/virtual_team_dashboard">Virtual Dashboard</a>
              <a class="navmenu-item{active('powerline_dashboard')}" href="/api/powerline_dashboard">Powerline Dashboard</a>
            </div>
          </details>
          <a class="navbtn{active('daily_update')}" href="/api/daily_update">Daily Dashboard</a>
        </div>
        <script>
          (function() {{
            var loader = document.getElementById('hsDashboardLoader');
            var pendingFetches = 0;
            var hideTimer = null;

            function setLoaderVisible(visible) {{
              if (!loader) return;
              loader.classList.toggle('is-hidden', !visible);
              loader.setAttribute('aria-hidden', visible ? 'false' : 'true');
            }}

            function scheduleLoaderHide() {{
              if (!loader) return;
              if (hideTimer) window.clearTimeout(hideTimer);
              hideTimer = window.setTimeout(function() {{
                if (pendingFetches <= 0) setLoaderVisible(false);
              }}, 180);
            }}

            function shouldTrackFetch(input) {{
              var raw = '';
              if (typeof input === 'string') raw = input;
              else if (input && typeof input.url === 'string') raw = input.url;
              if (!raw) return false;
              try {{
                var url = new URL(raw, window.location.href);
                if (url.origin !== window.location.origin) return false;
                if (!url.pathname.startsWith('/api/')) return false;
                if (url.pathname === '/api/warm_cache') return false;
                return true;
              }} catch (_err) {{
                return false;
              }}
            }}

            window.HSDashboardLoader = {{
              show: function() {{
                if (hideTimer) window.clearTimeout(hideTimer);
                setLoaderVisible(true);
              }},
              hide: function() {{
                pendingFetches = 0;
                scheduleLoaderHide();
              }},
            }};

            if (window.fetch && !window.__hsDashboardLoaderPatched) {{
              window.__hsDashboardLoaderPatched = true;
              var originalFetch = window.fetch.bind(window);
              window.fetch = function(input, init) {{
                var tracked = shouldTrackFetch(input);
                if (tracked) {{
                  pendingFetches += 1;
                  window.HSDashboardLoader.show();
                }}
                return originalFetch(input, init).finally(function() {{
                  if (!tracked) return;
                  pendingFetches = Math.max(0, pendingFetches - 1);
                  if (pendingFetches === 0) scheduleLoaderHide();
                }});
              }};
            }}

            setLoaderVisible(true);
            scheduleLoaderHide();

            var nav = document.currentScript && document.currentScript.parentElement
              ? document.currentScript.parentElement.querySelector('.nav')
              : null;
            if (!nav || !nav.classList || !nav.classList.contains('nav')) return;
            var menus = Array.prototype.slice.call(nav.querySelectorAll('.navmenu'));

            function closeOthers(currentMenu) {{
              menus.forEach(function(menu) {{
                if (menu !== currentMenu) menu.removeAttribute('open');
              }});
            }}

            menus.forEach(function(menu) {{
              menu.addEventListener('toggle', function() {{
                if (menu.hasAttribute('open')) closeOthers(menu);
              }});

              var links = menu.querySelectorAll('.navmenu-item');
              links.forEach(function(link) {{
                link.addEventListener('click', function() {{
                  menu.removeAttribute('open');
                }});
              }});
            }});

            document.addEventListener('click', function(event) {{
              if (!nav.contains(event.target)) {{
                menus.forEach(function(menu) {{ menu.removeAttribute('open'); }});
              }}
            }});

            document.addEventListener('keydown', function(event) {{
              if (event.key === 'Escape') {{
                menus.forEach(function(menu) {{ menu.removeAttribute('open'); }});
              }}
            }});
          }})();
        </script>
    """
