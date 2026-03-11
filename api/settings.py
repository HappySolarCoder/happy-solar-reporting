# -*- coding: utf-8 -*-

"""Vercel Python function: /api/settings

Settings UI (v1):
- Roster mapping across systems (GHL + Raydar)
- Monthly goals entry (writes to Firestore)

Backend API:
- /api/settings_api

Notes
- This is a production admin surface; keep it simple.
- Auth is not implemented in this v1.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
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
    .span-6 { grid-column: span 6; }
    @media (max-width: 980px) { .span-6 { grid-column: span 12; } }

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
    .col-3 { grid-column: span 3; }
    .col-12 { grid-column: span 12; }
    @media (max-width: 980px) { .col-4,.col-6,.col-3 { grid-column: span 12; } }

    .btn {
      display:inline-flex; align-items:center; justify-content:center;
      background: var(--pink); border: 1px solid var(--pink);
      color:#fff; border-radius: 10px; padding: 9px 12px;
      font-size: 13px; font-weight: 950; cursor:pointer;
    }
    .btn.secondary { background:#fff; border: 1px solid var(--border); color:#334155; }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border-bottom: 1px solid var(--border); padding: 8px 10px; font-size: 12px; text-align:left; }
    th { color: var(--muted); font-weight: 950; }
    td { color: #0f172a; font-weight: 800; }

    .toast { margin-top: 10px; font-size: 12px; color: var(--muted); }
    code { background:#f1f5f9; padding: 2px 6px; border-radius: 8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Settings</div>
        <div class="subtitle">Roster mapping + monthly goals</div>
        <div class="pinkline"></div>
        <div class="nav">
          <a class="navbtn" href="/api/company_overview">Company overview</a>
          <a class="navbtn" href="/api/sales_dashboard">Sales dashboard</a>
          <a class="navbtn" href="/api/fma_dashboard">FMS dashboard</a>
          <a class="navbtn" href="/api/leadership_dashboard">Leadership dashboard</a>
          <a class="navbtn active" href="/api/settings">Settings</a>
        </div>
      </div>
      <div style="min-width:320px">
        <div class="card-title">Status</div>
        <div class="meta" id="status">Loading…</div>
      </div>
    </div>

    <div class="grid">
      <div class="card span-6">
        <div class="card-header">
          <div>
            <div class="card-title">Roster Mapping</div>
            <div class="meta">Select Raydar + GHL mappings; <code>person_key</code> auto-generates</div>
          </div>
        </div>

        <div class="row">
          <div class="col-6">
            <label>Person Key (stable)</label>
            <input id="personKey" placeholder="setter:devin_plyley" readonly />
          </div>
          <div class="col-6">
            <label>Display Name</label>
            <input id="displayName" placeholder="Devin Plyley" />
          </div>

          <div class="col-4">
            <label>Role</label>
            <select id="role">
              <option value="setter">setter</option>
              <option value="rep">rep</option>
              <option value="team">team</option>
            </select>
          </div>

          <div class="col-4" id="wrapGhlSetterLast">
            <label>GHL Setter Last Name (Setter role only)</label>
            <div style="display:flex; gap:8px; align-items:center;">
              <select id="ghlSetterLastName"></select>
              <button class="btn secondary" id="refreshSetterNames" title="Force refresh setter last names" style="width:auto; padding:9px 10px;">↻</button>
            </div>
          </div>

          <div class="col-4" id="wrapRaydarUser">
            <label>Raydar User (Setter/Rep)</label>
            <select id="raydarUser"></select>
          </div>

          <div class="col-6" id="wrapGhlUser">
            <label>GHL Owner User (Rep role)</label>
            <select id="ghlUser"></select>
          </div>

          <div class="col-6" style="display:flex; gap:10px; align-items:flex-end">
            <button class="btn" id="saveRoster">Save Mapping</button>
            <button class="btn secondary" id="refreshRoster">Refresh</button>
          </div>
        </div>

        <div class="toast" id="rosterToast"></div>

        <div style="margin-top:12px">
          <div class="card-title">Current roster</div>
          <table>
            <thead>
              <tr>
                <th>person_key</th>
                <th>role</th>
                <th>display</th>
                <th>ghl_setter_last_name</th>
                <th>raydar_user</th>
                <th>ghl_user</th>
              </tr>
            </thead>
            <tbody id="rosterRows"><tr><td colspan="6" style="color:var(--muted2)">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>

      <div class="card span-6">
        <div class="card-header">
          <div>
            <div class="card-title">Monthly Goals</div>
            <div class="meta">Set goals for a person_key, per month, per metric</div>
          </div>
        </div>

        <div class="row">
          <div class="col-4">
            <label>Month (YYYY-MM)</label>
            <input id="goalMonth" placeholder="2026-03" />
          </div>
          <div class="col-8">
            <label>Person</label>
            <select id="goalPerson"></select>
          </div>

          <div class="col-6">
            <label>Metric</label>
            <select id="goalMetric">
              <option value="sales_goal">sales_goal</option>
              <option value="doors_goal">doors_goal</option>
              <option value="appts_goal">appts_goal</option>
              <option value="demos_goal">demos_goal</option>
            </select>
          </div>
          <div class="col-6">
            <label>Value</label>
            <input id="goalValue" placeholder="1500" />
          </div>

          <div class="col-6" style="display:flex; gap:10px; align-items:flex-end">
            <button class="btn" id="saveGoal">Save Goal</button>
            <button class="btn secondary" id="refreshGoals">Refresh</button>
          </div>
        </div>

        <div class="toast" id="goalToast"></div>

        <div style="margin-top:12px">
          <div class="card-title">Goals for selected month</div>
          <table>
            <thead>
              <tr>
                <th>person_key</th>
                <th>metric</th>
                <th>value</th>
              </tr>
            </thead>
            <tbody id="goalRows"><tr><td colspan="3" style="color:var(--muted2)">Loading…</td></tr></tbody>
          </table>
        </div>
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

  function slugify(s) {
    return String(s || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g,'_')
      .replace(/^_+|_+$/g,'')
      .slice(0, 48);
  }

  function autoPersonKey() {
    const role = String(document.getElementById('role').value || 'setter');
    const raySel = document.getElementById('raydarUser');
    const rayText = raySel && raySel.selectedOptions && raySel.selectedOptions[0]
      ? raySel.selectedOptions[0].textContent
      : '';
    const name = (document.getElementById('displayName').value || rayText || '').trim();
    const slug = slugify(name || rayText);

    let prefix = role + ':';
    if (role === 'rep') prefix = 'rep:';
    if (role === 'setter') prefix = 'setter:';
    if (role === 'team') prefix = 'team:';

    const pk = prefix + (slug || 'unknown');
    document.getElementById('personKey').value = pk;
  }

  function autoDisplayNameFromRaydar() {
    const raySel = document.getElementById('raydarUser');
    const label = raySel && raySel.selectedOptions && raySel.selectedOptions[0]
      ? raySel.selectedOptions[0].textContent
      : '';
    if (label && !(document.getElementById('displayName').value || '').trim()) {
      document.getElementById('displayName').value = label.trim();
    }
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

  async function loadSetterLastNames() {
    try {
      const el = document.getElementById('ghlSetterLastName');
      if (!el) return;
      // If already populated, skip
      if (el.options && el.options.length > 1) return;

      const res = await postJson({ action: 'setter_last_names' });
      fillSelect(el, res.ghl_setter_last_names || [], 'Select setter last name…');
    } catch (e) {
      // best-effort
      const el = document.getElementById('ghlSetterLastName');
      if (el) fillSelect(el, [], 'Error loading setters');
    }
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

  function renderRosterTable(rows) {
    const tb = document.getElementById('rosterRows');
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="6" style="color:var(--muted2)">No roster rows</td></tr>';
      return;
    }
    tb.innerHTML = rows.map(r => `
      <tr>
        <td><code>${esc(r.person_key)}</code></td>
        <td>${esc(r.role)}</td>
        <td>${esc(r.display_name)}</td>
        <td>${esc(r.ghl_setter_last_name)}</td>
        <td>${esc(r.raydar_user_name || r.raydar_user_id || '')}</td>
        <td>${esc(r.ghl_user_name || r.ghl_user_id || '')}</td>
      </tr>
    `).join('');
  }

  function renderGoalsTable(rows) {
    const tb = document.getElementById('goalRows');
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="3" style="color:var(--muted2)">No goals</td></tr>';
      return;
    }
    tb.innerHTML = rows.map(r => `
      <tr>
        <td><code>${esc(r.person_key)}</code></td>
        <td><code>${esc(r.metric)}</code></td>
        <td style="text-align:right; font-variant-numeric: tabular-nums;">${esc(r.value)}</td>
      </tr>
    `).join('');
  }


  function applyRoleUI() {
    const role = String(document.getElementById('role').value || 'setter');

    const wrapSetterLast = document.getElementById('wrapGhlSetterLast');
    const wrapRaydar = document.getElementById('wrapRaydarUser');
    const wrapGhlUser = document.getElementById('wrapGhlUser');

    // Defaults
    if (wrapSetterLast) wrapSetterLast.style.display = '';
    if (wrapRaydar) wrapRaydar.style.display = '';
    if (wrapGhlUser) wrapGhlUser.style.display = '';

    if (role === 'setter') {
      loadSetterLastNames();
      // Setter: Raydar user + GHL Setter Last Name
      if (wrapSetterLast) wrapSetterLast.style.display = '';
      if (wrapRaydar) wrapRaydar.style.display = '';
      if (wrapGhlUser) wrapGhlUser.style.display = 'none';
    } else if (role === 'rep') {
      // Rep: Raydar user + GHL owner user
      if (wrapSetterLast) wrapSetterLast.style.display = 'none';
      if (wrapRaydar) wrapRaydar.style.display = '';
      if (wrapGhlUser) wrapGhlUser.style.display = '';
    } else {
      // Team: usually no person mapping; hide system-specific fields for now
      if (wrapSetterLast) wrapSetterLast.style.display = 'none';
      if (wrapRaydar) wrapRaydar.style.display = 'none';
      if (wrapGhlUser) wrapGhlUser.style.display = 'none';
    }
  }

  async function refresh() {
    setStatus('Loading…');
    const month = document.getElementById('goalMonth').value || nowMonth();
    document.getElementById('goalMonth').value = month;

    const data = await postJson({ action: 'bootstrap', month });

    fillSelect(document.getElementById('raydarUser'), data.raydar_users, 'Select Raydar user…');
        fillSelect(document.getElementById('ghlUser'), data.ghl_users, 'Select GHL owner…');

    fillSelect(document.getElementById('goalPerson'), data.roster_people.map(p => ({ value: p.person_key, label: `${p.display_name} (${p.person_key})` })), 'Select person…');

    renderRosterTable(data.roster_people);
    renderGoalsTable(data.goals_for_month);

    setStatus('Ready');
  }

  document.getElementById('saveRoster').addEventListener('click', async () => {
    const payload = {
      action: 'upsert_roster',
      person_key: (document.getElementById('personKey').value || '').trim(),
      display_name: (document.getElementById('displayName').value || '').trim(),
      role: (document.getElementById('role').value || 'setter').trim(),
      ghl_setter_last_name: (document.getElementById('ghlSetterLastName').value || '').trim(),
      raydar_user_id: (document.getElementById('raydarUser').value || '').trim(),
      ghl_user_id: (document.getElementById('ghlUser').value || '').trim(),
    };

    try {
      const res = await postJson(payload);
      document.getElementById('rosterToast').textContent = `Saved: ${res.person_key}`;
      await refresh();
    } catch (e) {
      document.getElementById('rosterToast').textContent = `Error: ${String(e)}`;
    }
  });

  document.getElementById('refreshRoster').addEventListener('click', refresh);

  document.getElementById('saveGoal').addEventListener('click', async () => {
    const payload = {
      action: 'upsert_goal',
      month: (document.getElementById('goalMonth').value || '').trim(),
      person_key: (document.getElementById('goalPerson').value || '').trim(),
      metric: (document.getElementById('goalMetric').value || '').trim(),
      value: (document.getElementById('goalValue').value || '').trim(),
    };
    try {
      const res = await postJson(payload);
      document.getElementById('goalToast').textContent = `Saved goal: ${res.month} ${res.person_key} ${res.metric}`;
      await refresh();
    } catch (e) {
      document.getElementById('goalToast').textContent = `Error: ${String(e)}`;
    }
  });

  document.getElementById('refreshGoals').addEventListener('click', refresh);
  document.getElementById('goalMonth').addEventListener('change', refresh);
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

  const refreshBtn = document.getElementById('refreshSetterNames');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      try {
        const res = await postJson({ action: 'setter_last_names', force: true });
        fillSelect(document.getElementById('ghlSetterLastName'), res.ghl_setter_last_names || [], 'Select setter last name…');
      } catch (e) {
        document.getElementById('rosterToast').textContent = `Error refreshing setters: ${String(e)}`;
      } finally {
        refreshBtn.disabled = false;
      }
    });
  }

  const setterSel = document.getElementById('ghlSetterLastName');
  if (setterSel) {
    setterSel.addEventListener('focus', () => {
      loadSetterLastNames();
    });
  }

  applyRoleUI();
  autoPersonKey();
  refresh();
</script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
