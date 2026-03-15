# -*- coding: utf-8 -*-

"""Vercel Python function: /api/leadership_dashboard

Leadership Dashboard (production)

Currently a scaffold page to support top-level navigation across production dashboards.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler


def render_html() -> str:
    return r"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Leadership Dashboard</title>
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
    }

    body {
      font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      margin:0;
      background: var(--bg);
      color: var(--text);
    }

    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar {
      display:flex;
      align-items:flex-start;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
      padding: 18px 20px;
      border-radius: 14px;
      background: var(--card);
      border: 1px solid var(--border);
      box-shadow: 0 1px 3px rgba(17,24,39,0.05);
    }

    .title {
      font-size: 22px;
      font-weight: 900;
      color: #1a2b4a;
      letter-spacing: -0.02em;
    }

    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px;
      width: 180px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

    .nav {
      margin-top: 12px;
      display:flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .navbtn {
      display:inline-flex;
      align-items:center;
      padding: 9px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      color: #1f2937;
      font-size: 13px;
      font-weight: 800;
      text-decoration:none;
    }

    .navbtn:hover {
      border-color: rgba(236,72,153,0.45);
      box-shadow: 0 1px 2px rgba(17,24,39,0.06);
    }

    .navbtn.active {
      background: rgba(236,72,153,0.10);
      border-color: rgba(236,72,153,0.45);
      color: #b80b66;
    }

    .grid {
      display:grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      margin-top: 14px;
      align-content: start;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px 18px;
      box-shadow: 0 1px 3px rgba(17,24,39,0.06);
      min-height: 120px;
    }

    .card-title { font-size: 13px; font-weight: 800; color: var(--muted); }
    .big { font-size: 20px; font-weight: 900; margin-top: 8px; }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    .span-12 { grid-column: span 12; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Leadership Dashboard</div>
        <div class=\"subtitle\">Happy Solar — production navigation scaffold</div>
        <div class=\"pinkline\"></div>
        <div class=\"nav\">
          <a class=\"navbtn\" href=\"/api/company_overview\">Company overview</a>
          <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales dashboard</a>
          <a class=\"navbtn\" href=\"/api/fma_dashboard\">FMA dashboard</a>
          <a class=\"navbtn\" href=\"/api/missing_dispos\">Missing Dispos</a>
          <a class=\"navbtn\" href=\"/api/virtual_team_dashboard\">Virtual Team</a>
          <a class=\"navbtn active\" href=\"/api/leadership_dashboard\">Leadership dashboard</a>
        </div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-12\">
        <div class=\"card-title\">Status</div>
        <div class=\"big\">Coming next: Leadership view KPIs</div>
        <div class=\"meta\">This page exists so the production dashboard has 4 top buttons routing to separate dashboards.</div>
      </div>
    </div>
  </div>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
