# -*- coding: utf-8 -*-

"""Vercel Python function: /api/settings

Settings UI (v2):
- Combined workflow: map person (Raydar + GHL) then add 1+ goals and save once.

Backend API:
- /api/settings_api

Notes
- This is a production admin surface; keep it simple.
- Auth is not implemented in this v2.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

import base64
import os


def _unauthorized(h: BaseHTTPRequestHandler):
    h.send_response(401)
    h.send_header('WWW-Authenticate', 'Basic realm="Happy Solar Settings"')
    h.send_header('Content-Type', 'text/plain; charset=utf-8')
    h.end_headers()
    h.wfile.write(b'Unauthorized')


def _check_auth(h: BaseHTTPRequestHandler) -> bool:
    # Password is stored in Vercel env var (do NOT hardcode)
    pw = os.environ.get('SETTINGS_PASSWORD')
    if not pw:
        # if not set, block by default
        return False

    auth = h.headers.get('Authorization') or ''
    if not auth.startswith('Basic '):
        return False
    try:
        raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
        user, pwd = raw.split(':', 1)
        return (pwd == pw)
    except Exception:
        return False



HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Happy Solar — Settings</title>
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
      --shadow: 0 1px 3px rgba(17,24,39,0.06);
      --danger: #ef4444;
    }

    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background: var(--bg); color: var(--text); }
    .wrap { padding: 22px; max-width: 1180px; margin: 0 auto; }

    .topbar {
      display:flex; align-items:flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap;
      padding: 18px 20px; border-radius: 14px; background: var(--card);
      border: 1px solid var(--border); box-shadow: var(--shadow);
    }

    .title { font-size: 22px; font-weight: 950; color: #1a2b4a; letter-spacing: -0.02em; }
    .subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }

    .pinkline {
      height: 3px; width: 200px; border-radius: 999px;
      background: linear-gradient(90deg, var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%);
      margin-top: 10px;
    }

    .nav { margin-top: 12px; display:flex; gap: 10px; flex-wrap: wrap; }
    .navbtn {
      display:inline-flex; align-items:center; padding: 9px 12px;
      border-radius: 12px; border: 1px solid var(--border);
      background: #fff; color: #1f2937; font-size: 13px; font-weight: 800; text-decoration:none;
    }
    .navbtn.active { background: rgba(236,72,153,0.10); border-color: rgba(236,72,153,0.45); color: #b80b66; }

    .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap: 14px; margin-top: 14px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow); }
    .span-12 { grid-column: span 12; }

    .card-header { display:flex; align-items:flex-start; justify-content: space-between; gap: 10px; }
    .card-title { font-size: 13px; font-weight: 900; color: var(--muted); }
    .meta { margin-top: 6px; color: var(--muted2); font-size: 12px; }

    label { display:block; font-size: 12px; font-weight: 900; color: var(--muted); margin-top: 10px; }
    input, select {
      width: 100%; box-sizing: border-box;
      border: 1px solid var(--border); border-radius: 10px; padding: 9px 10px;
      font-size: 13px; font-weight: 900; background: #fff;
    }

    .row { display:grid; grid-template-columns: repeat(12, 1fr); gap: 10px; }
    .col-4 { grid-column: span 4; }
    .col-6 { grid-column: span 6; }
    .col-8 { grid-column: span 8; }
    .col-12 { grid-column: span 12; }
    @media (max-width: 980px) { .col-4,.col-6,.col-8 { grid-column: span 12; } }

    .btn {
      display:inline-flex; align-items:center; justify-content:center;
      background: var(--pink); border: 1px solid var(--pink);
      color:#fff; border-radius: 10px; padding: 9px 12px;
      font-size: 13px; font-weight: 950; cursor:pointer;
    }
    .btn.secondary { background:#fff; border: 1px solid var(--border); color:#334155; }
    .btn.danger { background: var(--danger); border-color: var(--danger); }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom: 1px solid var(--border); padding: 8px 10px; font-size: 12px; text-align:left; }
    th { color: var(--muted); font-weight: 950; }
    td { color: #0f172a; font-weight: 800; }

    .pill { display:inline-flex; align-items:center; padding: 6px 10px; border-radius: 999px; border:1px solid var(--border); background:#fff; font-size: 12px; font-weight: 950; color:#334155; }

    code { background:#f1f5f9; padding: 2px 6px; border-radius: 8px; }

    .stack { display:flex; flex-direction: column; gap: 12px; }
    .hgroup { display:flex; gap: 10px; align-items:center; flex-wrap:wrap; }

    @media (max-width: 820px) {
      .wrap { padding: 12px; }
      .topbar { padding: 12px; gap: 10px; }
      .title { font-size: 20px; }
      .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; -webkit-overflow-scrolling:touch; }
      .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; }
      .card { padding: 12px; }
      th, td { font-size: 11px; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div>
        <div class=\"title\">Settings</div>
        <div class=\"subtitle\">Map person → add goals → save once</div>
        <div class=\"pinkline\"></div>
        <div class=\"nav\">
          <a class=\"navbtn\" href=\"/api/company_overview\">Company Overview</a>
          <a class=\"navbtn\" href=\"/api/sales_dashboard\">Sales Dashboard</a>
          <a class=\"navbtn\" href=\"/api/fma_dashboard\">FMA Dashboard</a>
          <a class=\"navbtn\" href=\"/api/leadership_dashboard\">Leadership Dashboard</a>
          <a class=\"navbtn\" href=\"/api/daily_update\">Daily Dashboard</a>
          <a class=\"navbtn active\" href=\"/api/settings\">Settings</a>
          <a class=\"navbtn\" href=\"/api/data_cleanup\">Data Cleanup</a>
        </div>
      </div>
      <div style=\"min-width:320px\">
        <div class=\"card-title\">Status</div>
        <div class=\"meta\" id=\"status\">Loading…</div>
      </div>
    </div>

    <div class=\"grid\">
      <div class=\"card span-12\">
        <div class=\"card-header\">
          <div>
            <div class=\"card-title\">Roster + Goals (combined)</div>
            <div class=\"meta\">Select Role + Raydar → select GHL mapping → add goals → Save</div>
          </div>
          <div class=\"hgroup\">
            <span class=\"pill\" id=\"currentMonthPill\">Month: —</span>
            <button class=\"btn secondary\" id=\"refreshAll\">Refresh</button>
          </div>
        </div>

        <div class=\"row\" style=\"margin-top:8px\">
          <div class=\"col-4\">
            <label>Role</label>
            <select id=\"role\">
              <option value=\"setter\">setter</option>
              <option value=\"rep\">rep</option>
              <option value=\"team\">team</option>
            </select>
          </div>

          <div class=\"col-4\" id=\"wrapRaydarUser\">
            <label>Raydar User</label>
            <select id=\"raydarUser\"></select>
          </div>

          <div class=\"col-4\" id=\"wrapGhlSetterLast\">
            <label>GHL Setter Last Name (optional for reps; required for setters)</label>
            <div style=\"display:flex; gap:8px; align-items:center\">
              <select id=\"ghlSetterLastName\"></select>
              <button class=\"btn secondary\" id=\"refreshSetterNames\" title=\"Force refresh setter last names\" style=\"width:auto; padding:9px 10px;\">↻</button>
            </div>
          </div>

          <div class=\"col-4\" id=\"wrapGhlUser\">
            <label>GHL Owner User</label>
            <select id=\"ghlUser\"></select>
          </div>

          <div class=\"col-4\">
            <label>Display Name</label>
            <input id=\"displayName\" placeholder=\"Auto from Raydar…\" />
          </div>

          <div class=\"col-4\">
            <label>Person Key (auto)</label>
            <input id=\"personKey\" readonly />
          </div>

          <div class=\"col-12\" style=\"border-top:1px solid var(--border); margin-top:6px; padding-top:12px\">
            <div class=\"card-title\">Goals to Save (for this person)</div>
            <div class=\"meta\">Add one or multiple goals, then click Save All once.</div>

            <div class=\"row\" style=\"margin-top:8px\">
              <div class=\"col-4\">
                <label>Month (YYYY-MM)</label>
                <input id=\"goalMonth\" placeholder=\"2026-03\" />
              </div>
              <div class=\"col-4\">
                <label>Metric</label>
                <select id=\"goalMetric\">
                  <option value=\"sales_goal\">sales_goal</option>
                  <option value=\"doors_goal\">doors_goal</option>
                  <option value=\"appts_goal\">appts_goal</option>
                  <option value=\"demos_goal\">demos_goal</option>
                </select>
              </div>
              <div class=\"col-4\">
                <label>Value</label>
                <input id=\"goalValue\" placeholder=\"1500\" />
              </div>
              <div class=\"col-12\" style=\"display:flex; gap:10px; flex-wrap:wrap; align-items:center\">
                <button class=\"btn secondary\" id=\"addGoal\">Add Goal</button>
                <button class=\"btn danger\" id=\"clearGoals\">Clear Goals</button>
                <button class=\"btn\" id=\"saveAll\">Save Mapping + Goals</button>
              </div>
            </div>

            <div id=\"pendingToast\" class=\"meta\"></div>

            <div style=\"margin-top:10px; overflow:auto\">
              <table>
                <thead>
                  <tr>
                    <th>metric</th>
                    <th style=\"text-align:right\">value</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody id=\"pendingGoalsRows\"><tr><td colspan=\"3\" style=\"color:var(--muted2)\">No goals added yet</td></tr></tbody>
              </table>
            </div>

            <div style=\"margin-top:14px\">
              <div class=\"card-title\">Existing goals for selected month</div>
              <table>
                <thead>
                  <tr>
                    <th>person_key</th>
                    <th>metric</th>
                    <th style=\"text-align:right\">value</th>
                  </tr>
                </thead>
                <tbody id=\"goalRows\"><tr><td colspan=\"3\" style=\"color:var(--muted2)\">Loading…</td></tr></tbody>
              </table>
            </div>

          </div>

        </div>

        <div class=\"meta\" id=\"toast\" style=\"margin-top:10px\"></div>

      </div>
    </div>
  </div>

<script>
  const api = '/api/settings_api';

  function nowMonth() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2,'0');
    return `${d.getFullYear()}-${m}`;
  }

  function esc(s) {
    return String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  }

  async function postJson(body) {
    const res = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!res.ok) throw new Error(data?.error || text || 'Request failed');
    return data;
  }

  function setStatus(t) { document.getElementById('status').textContent = t; }

  function fillSelect(el, options, placeholder) {
    el.innerHTML = '';
    if (placeholder) {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = placeholder;
      el.appendChild(o);
    }
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      el.appendChild(o);
    }
  }

  function slugify(s) {
    return String(s || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g,'_')
      .replace(/^_+|_+$/g,'')
      .slice(0, 48);
  }

  function applyRoleUI() {
    const role = String(document.getElementById('role').value || 'setter');
    const wrapSetterLast = document.getElementById('wrapGhlSetterLast');
    const wrapRaydar = document.getElementById('wrapRaydarUser');
    const wrapGhlUser = document.getElementById('wrapGhlUser');

    if (role === 'setter') {
      wrapSetterLast.style.display = '';
      wrapRaydar.style.display = '';
      wrapGhlUser.style.display = 'none';
      loadSetterLastNames();
    } else if (role === 'rep') {
      wrapSetterLast.style.display = '';  // optional
      wrapRaydar.style.display = '';
      wrapGhlUser.style.display = '';
    } else {
      wrapSetterLast.style.display = 'none';
      wrapRaydar.style.display = 'none';
      wrapGhlUser.style.display = 'none';
    }
  }

  function autoDisplayNameFromRaydar() {
    const raySel = document.getElementById('raydarUser');
    const label = raySel && raySel.selectedOptions && raySel.selectedOptions[0]
      ? raySel.selectedOptions[0].textContent
      : '';
    if (label) {
      document.getElementById('displayName').value = label.trim();
    }
  }

  function autoPersonKey() {
    const role = String(document.getElementById('role').value || 'setter');
    const name = (document.getElementById('displayName').value || '').trim();
    const slug = slugify(name);

    let prefix = role + ':';
    if (role === 'rep') prefix = 'rep:';
    if (role === 'setter') prefix = 'setter:';
    if (role === 'team') prefix = 'team:';

    document.getElementById('personKey').value = prefix + (slug || 'unknown');
  }

  let pendingGoals = [];

  function renderPendingGoals() {
    const tb = document.getElementById('pendingGoalsRows');
    if (!pendingGoals.length) {
      tb.innerHTML = '<tr><td colspan="3" style="color:var(--muted2)">No goals added yet</td></tr>';
      document.getElementById('pendingToast').textContent = '';
      return;
    }

    tb.innerHTML = pendingGoals.map((g, idx) => `
      <tr>
        <td><code>${esc(g.metric)}</code></td>
        <td style="text-align:right; font-variant-numeric: tabular-nums;">${esc(g.value)}</td>
        <td style="text-align:right"><button class="btn secondary" data-idx="${idx}" style="padding:6px 10px; width:auto">Remove</button></td>
      </tr>
    `).join('');

    document.getElementById('pendingToast').textContent = `Pending goals: ${pendingGoals.length}`;

    tb.querySelectorAll('button[data-idx]').forEach(btn => {
      btn.addEventListener('click', () => {
        const i = Number(btn.getAttribute('data-idx'));
        pendingGoals = pendingGoals.filter((_, j) => j !== i);
        renderPendingGoals();
      });
    });
  }

  function renderGoalsTable(rows) {
    const tb = document.getElementById('goalRows');
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="3" style="color:var(--muted2)">No goals</td></tr>';
      return;
    }

    tb.innerHTML = rows.map((r, idx) => {
      const id = `g_${idx}`;
      return `
        <tr>
          <td><code>${esc(r.person_key)}</code></td>
          <td><code>${esc(r.metric)}</code></td>
          <td style="text-align:right; font-variant-numeric: tabular-nums;">
            <div style="display:flex; gap:8px; justify-content:flex-end; align-items:center; flex-wrap:wrap;">
              <input id="${id}" value="${esc(r.value)}" style="max-width:140px; text-align:right;" />
              <button class="btn secondary" data-save="${idx}" style="padding:6px 10px; width:auto">Save</button>
              <button class="btn danger" data-del="${idx}" style="padding:6px 10px; width:auto">Delete</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    // bind actions
    tb.querySelectorAll('button[data-save]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const i = Number(btn.getAttribute('data-save'));
        const row = rows[i];
        const inp = document.getElementById(`g_${i}`);
        const value = inp ? String(inp.value || '').trim() : '';
        try {
          document.getElementById('toast').textContent = 'Saving goal…';
          await postJson({ action: 'upsert_goal', month: document.getElementById('goalMonth').value, person_key: row.person_key, metric: row.metric, value });
          document.getElementById('toast').textContent = 'Saved.';
          await refreshAll();
        } catch (e) {
          document.getElementById('toast').textContent = `Error: ${String(e)}`;
        }
      });
    });

    tb.querySelectorAll('button[data-del]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const i = Number(btn.getAttribute('data-del'));
        const row = rows[i];
        if (!confirm(`Delete goal ${row.person_key} ${row.metric}?`)) return;
        try {
          document.getElementById('toast').textContent = 'Deleting goal…';
          await postJson({ action: 'delete_goal', month: document.getElementById('goalMonth').value, person_key: row.person_key, metric: row.metric });
          document.getElementById('toast').textContent = 'Deleted.';
          await refreshAll();
        } catch (e) {
          document.getElementById('toast').textContent = `Error: ${String(e)}`;
        }
      });
    });
  }

  async function loadSetterLastNames() {
    try {
      const el = document.getElementById('ghlSetterLastName');
      if (!el) return;
      if (el.options && el.options.length > 1) return;
      const res = await postJson({ action: 'setter_last_names' });
      fillSelect(el, res.ghl_setter_last_names || [], 'Select setter last name…');
    } catch {
      const el = document.getElementById('ghlSetterLastName');
      if (el) fillSelect(el, [], 'Error loading setters');
    }
  }

  async function refreshAll() {
    setStatus('Loading…');
    const month = (document.getElementById('goalMonth').value || nowMonth()).trim();
    document.getElementById('goalMonth').value = month;
    document.getElementById('currentMonthPill').textContent = `Month: ${month}`;

    const data = await postJson({ action: 'bootstrap', month });

    fillSelect(document.getElementById('raydarUser'), data.raydar_users, 'Select Raydar user…');
    fillSelect(document.getElementById('ghlUser'), data.ghl_users, 'Select GHL owner…');

    renderGoalsTable(data.goals_for_month || []);

    setStatus('Ready');
  }

  // Events
  document.getElementById('role').addEventListener('change', () => {
    applyRoleUI();
    autoPersonKey();
  });

  document.getElementById('raydarUser').addEventListener('change', () => {
    autoDisplayNameFromRaydar();
    autoPersonKey();
  });

  document.getElementById('displayName').addEventListener('blur', () => {
    autoPersonKey();
  });

  document.getElementById('refreshAll').addEventListener('click', refreshAll);
  document.getElementById('goalMonth').addEventListener('change', refreshAll);

  const refreshBtn = document.getElementById('refreshSetterNames');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      try {
        const res = await postJson({ action: 'setter_last_names', force: true });
        fillSelect(document.getElementById('ghlSetterLastName'), res.ghl_setter_last_names || [], 'Select setter last name…');
      } catch (e) {
        document.getElementById('toast').textContent = `Error refreshing setters: ${String(e)}`;
      } finally {
        refreshBtn.disabled = false;
      }
    });
  }

  document.getElementById('addGoal').addEventListener('click', () => {
    const metric = String(document.getElementById('goalMetric').value || '').trim();
    const value = String(document.getElementById('goalValue').value || '').trim();
    if (!metric || !value) return;

    // Replace if metric already exists
    const filtered = pendingGoals.filter(g => g.metric !== metric);
    filtered.push({ metric, value });
    pendingGoals = filtered;

    document.getElementById('goalValue').value = '';
    renderPendingGoals();
  });

  document.getElementById('clearGoals').addEventListener('click', () => {
    pendingGoals = [];
    renderPendingGoals();
  });

  document.getElementById('saveAll').addEventListener('click', async () => {
    const role = String(document.getElementById('role').value || '').trim();
    const raydar_user_id = String(document.getElementById('raydarUser').value || '').trim();
    const ghl_setter_last_name = String(document.getElementById('ghlSetterLastName').value || '').trim();
    const ghl_user_id = String(document.getElementById('ghlUser').value || '').trim();

    const person_key = String(document.getElementById('personKey').value || '').trim();
    const display_name = String(document.getElementById('displayName').value || '').trim();

    const month = String(document.getElementById('goalMonth').value || '').trim();

    const payload = {
      action: 'upsert_roster_and_goals',
      month,
      person_key,
      display_name,
      role,
      raydar_user_id,
      ghl_setter_last_name,
      ghl_user_id,
      goals: pendingGoals,
    };

    try {
      document.getElementById('toast').textContent = 'Saving…';
      const res = await postJson(payload);
      pendingGoals = [];
      renderPendingGoals();
      document.getElementById('toast').textContent = `Saved: ${res.person_key} (${res.goals_written?.length || 0} goals)`;
      await refreshAll();
    } catch (e) {
      document.getElementById('toast').textContent = `Error: ${String(e)}`;
    }
  });

  // Init
  document.getElementById('goalMonth').value = nowMonth();
  applyRoleUI();
  renderPendingGoals();
  refreshAll();
</script>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _check_auth(self):
            return _unauthorized(self)

        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
