# -*- coding: utf-8 -*-
"""Company overview chat panel. The dashboard keeps working when this is hidden."""

from __future__ import annotations

import json

from copilot.auth import bloom_parent_origins
from copilot.messages import UI_TITLE, WELCOME


def render_panel() -> str:
    welcome = WELCOME.replace("'", "\\'")
    title = UI_TITLE
    origins_json = json.dumps(bloom_parent_origins())
    return f"""
<script>document.documentElement.classList.add('goose-dock');</script>
<button type="button" id="gooseOpen" class="goose-open" aria-label="Ask about our data" title="Ask about our data"><img src="/goose-headset.png" alt="" width="56" height="56" /></button>
<div id="goosePanel" class="goose-panel" hidden>
  <div class="goose-head">
    <div>
      <div class="goose-title">{title}</div>
      <div class="goose-sub">Read-only. Draft definitions are not company policy.</div>
    </div>
    <button type="button" id="gooseClose" class="goose-close">Close</button>
  </div>
  <p id="gooseIdentity" class="goose-note" hidden></p>
  <p id="gooseAuth" class="goose-auth" role="alert" hidden></p>
  <div class="goose-chips" id="gooseChips"></div>
  <div class="goose-suggest">
    <button type="button" data-goose-q="Explain Opp2Prelim">Explain Opp2Prelim</button>
    <button type="button" data-goose-q="Compare source performance">Compare source performance</button>
    <button type="button" data-goose-q="What changed versus the same period last month?">What changed versus the same period last month?</button>
  </div>
  <div id="gooseLog" class="goose-log"></div>
  <form id="gooseForm" class="goose-form">
    <textarea id="gooseInput" maxlength="2000" placeholder="Ask about Happy Solar data"></textarea>
    <button type="submit">Send</button>
  </form>
  <button type="button" id="gooseIssue" class="goose-issue">Report an issue</button>
</div>
<style>
  .goose-open {{ position: fixed; left: 16px; bottom: 16px; z-index: 10000; width: 56px; height: 56px; padding: 0; border: 2px solid #fff; border-radius: 50%; background: #fff; color: #1a2b4a; box-shadow: 0 6px 18px rgba(17,24,39,.22); cursor: pointer; overflow: hidden; line-height: 0; box-sizing: border-box; }}
  .goose-open img {{ width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 50%; pointer-events: none; }}
  .goose-panel {{ position: fixed; top: 0; right: 0; height: 100%; width: min(420px, 100%); background: #fff; color: #1a2b4a; border-left: 1px solid #e8ecf0; z-index: 10001; display: flex; flex-direction: column; padding: 16px; box-shadow: -8px 0 24px rgba(17,24,39,.08); box-sizing: border-box; }}
  .goose-panel[hidden] {{ display: none !important; }}
  .goose-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
  .goose-title {{ font-weight: 900; color: #1a2b4a; }}
  .goose-sub {{ color: #3d4c63; font-size: 12px; margin-top: 4px; }}
  .goose-note, .goose-auth {{ margin: 8px 0 0; padding: 8px 10px; border-radius: 10px; color: #1a2b4a; font-size: 13px; font-weight: 700; line-height: 1.35; }}
  .goose-note {{ border: 1px solid #e4c56a; background: #fff8e1; }}
  .goose-auth {{ border: 1px solid #c5ced6; background: #fff; }}
  .goose-note[hidden], .goose-auth[hidden] {{ display: none !important; }}
  .goose-close, .goose-suggest button, .goose-issue {{ border: 1px solid #c5ced6; background: #fff; color: #1a2b4a; border-radius: 10px; padding: 8px 10px; font-weight: 800; cursor: pointer; }}
  .goose-suggest button {{ max-width: 100%; white-space: normal; text-align: left; }}
  .goose-form button {{ border: 1px solid #0a7a34; background: #0a7a34; color: #fff; border-radius: 10px; padding: 8px 14px; font-weight: 800; cursor: pointer; }}
  .goose-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; color: #1a2b4a; }}
  .goose-chips span, .goose-chips label {{ color: #1a2b4a; background: #fff; font-size: 12px; border: 1px solid #c5ced6; border-radius: 999px; padding: 4px 8px; }}
  .goose-suggest {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .goose-log {{ flex: 1; overflow: auto; margin: 12px 0; font-size: 14px; color: #1a2b4a; }}
  .goose-msg {{ margin: 0 0 10px; padding: 10px; border-radius: 12px; background: #f5f7fa; color: #1a2b4a; white-space: pre-wrap; }}
  .goose-msg a {{ color: #075e28; }}
  .goose-form {{ display: flex; gap: 8px; }}
  .goose-form textarea {{ flex: 1; border: 1px solid #c5ced6; border-radius: 10px; padding: 8px; font: inherit; color: #1a2b4a; background: #fff; }}
  .goose-form textarea::placeholder {{ color: #3d4c63; opacity: 1; }}
  .goose-issue {{ margin-top: 8px; }}
  @media (max-width: 720px) {{ .goose-panel {{ width: 100%; }} }}
  /* Keep the round launcher in a clear strip. Report text scrolls above it.
     Bloom's Data Center iframe already ends above the portal bottom nav, so this
     frame does not lift the launcher by another 64px. Default z-index stays under
     the loading overlay rule (body.loading-open .goose-open). */
  html.goose-dock #sidebar {{ box-sizing: border-box; padding-bottom: 88px; }}
  @media (min-width: 801px) {{
    html.oc-nav-collapsed.goose-dock .goose-open {{ left: 4px; }}
    html.oc-embedded.goose-dock .goose-open {{ left: 16px; }}
  }}
  @media (max-width: 800px) {{
    html.goose-dock, html.goose-dock body.oc-root {{ height: 100dvh; overflow: hidden; }}
    html.goose-dock .workspace {{ height: calc(100dvh - 68px - env(safe-area-inset-bottom, 0px)); max-height: calc(100dvh - 68px - env(safe-area-inset-bottom, 0px)); overflow: auto; }}
    html.goose-dock .goose-open {{ width: 44px; height: 44px; left: 12px; bottom: calc(12px + env(safe-area-inset-bottom, 0px)); }}
  }}
</style>
<script>
(function() {{
  document.documentElement.classList.add('goose-dock');
  const panel = document.getElementById('goosePanel');
  const log = document.getElementById('gooseLog');
  const chips = document.getElementById('gooseChips');
  const input = document.getElementById('gooseInput');
  const sources = ['doors','self_gen','phones','inbound','3pl'];
  const labels = {{doors:'Doors', self_gen:'Self Gen', phones:'Phones', inbound:'Inbound', '3pl':'3PL'}};
  const bloomParents = new Set({origins_json});
  let bloomBearer = '';
  let bloomBearerExp = 0;
  let bloomBlockReason = '';
  const bloomWaiters = [];

  function parentOrigin() {{
    if (window.parent === window) return '';
    try {{
      if (document.referrer) {{
        const origin = new URL(document.referrer).origin;
        return bloomParents.has(origin) ? origin : '';
      }}
    }} catch (err) {{
      return '';
    }}
    return bloomParents.size === 1 ? Array.from(bloomParents)[0] : '';
  }}

  function tokenStillFresh() {{
    return Boolean(bloomBearer) && bloomBearerExp - Date.now() > 15000;
  }}

  function rememberToken(data) {{
    if (!data || data.type !== 'happy-solar-goose' || data.action !== 'token') return false;
    if (typeof data.token !== 'string') return false;
    const token = data.token;
    if (token.length < 20 || token.length > 4000 || token.indexOf(' ') !== -1 || token.indexOf('.') < 1) return false;
    let exp = Number(data.expiresAt);
    try {{
      let body = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
      while (body.length % 4) body += '=';
      const claims = JSON.parse(atob(body));
      if (!claims || claims.aud !== 'goose-copilot' || typeof claims.exp !== 'number') return false;
      exp = claims.exp * 1000;
    }} catch (err) {{
      return false;
    }}
    if (!Number.isFinite(exp)) return false;
    bloomBearer = token;
    bloomBearerExp = exp;
    return true;
  }}

  function releaseWaiters(token) {{
    const waiters = bloomWaiters.splice(0, bloomWaiters.length);
    waiters.forEach((resolve) => resolve(token));
  }}

  function showGooseNote(note) {{
    const el = document.getElementById('gooseIdentity');
    if (!el) return;
    if (typeof note !== 'string' || !note.trim()) {{
      el.hidden = true;
      el.textContent = '';
      return;
    }}
    el.hidden = false;
    el.textContent = note.trim();
  }}

  function showGooseAuth(reason) {{
    const el = document.getElementById('gooseAuth');
    if (!el) return;
    el.hidden = false;
    el.textContent = reason;
  }}

  function clearGooseAuth() {{
    bloomBlockReason = '';
    const el = document.getElementById('gooseAuth');
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
  }}

  window.addEventListener('message', (event) => {{
    if (!bloomParents.has(event.origin)) return;
    const data = event.data;
    if (data && data.type === 'happy-solar-goose' && data.action === 'token-unavailable') {{
      const reason = data && typeof data.reason === 'string' ? data.reason.trim() : '';
      if (reason) {{
        bloomBlockReason = reason.slice(0, 500);
        showGooseAuth(bloomBlockReason);
        showGooseNote('');
      }}
      releaseWaiters('');
      return;
    }}
    if (!rememberToken(data)) return;
    clearGooseAuth();
    showGooseNote(data && data.note);
    releaseWaiters(tokenStillFresh() ? bloomBearer : '');
  }});

  function tellParent(action) {{
    const origin = parentOrigin();
    if (!origin) return;
    window.parent.postMessage({{ type: 'happy-solar-goose', action: action }}, origin);
  }}

  function requestBloomToken() {{
    const origin = parentOrigin();
    if (!origin) return Promise.resolve('');
    if (tokenStillFresh()) return Promise.resolve(bloomBearer);
    return new Promise((resolve) => {{
      const timer = window.setTimeout(() => resolve(tokenStillFresh() ? bloomBearer : ''), 2500);
      bloomWaiters.push((token) => {{
        window.clearTimeout(timer);
        resolve(token);
      }});
      window.parent.postMessage({{ type: 'happy-solar-goose', action: 'request-token' }}, origin);
    }});
  }}

  async function authHeaders() {{
    const headers = {{ 'Content-Type': 'application/json' }};
    const token = await requestBloomToken();
    if (token) headers.Authorization = 'Bearer ' + token;
    return headers;
  }}
  function selectedDates() {{
    const start = document.getElementById('ocStart') || document.getElementById('startDate');
    const end = document.getElementById('ocEnd') || document.getElementById('endDate');
    return {{
      start: start ? start.value : '',
      end: end ? end.value : ''
    }};
  }}
  function selectedSources() {{
    return Array.from(chips.querySelectorAll('input:checked')).map(el => el.value);
  }}
  function drawChips() {{
    const dates = selectedDates();
    chips.innerHTML = '';
    const dateChip = document.createElement('span');
    dateChip.textContent = (dates.start || 'start') + ' → ' + (dates.end || 'end');
    chips.appendChild(dateChip);
    sources.forEach(id => {{
      const label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" value="' + id + '"> ' + labels[id];
      chips.appendChild(label);
    }});
  }}
  function add(text, evidence) {{
    const div = document.createElement('div');
    div.className = 'goose-msg';
    div.textContent = text;
    (evidence || []).forEach(item => {{
      if (!item.source_link) return;
      const link = document.createElement('a');
      link.href = item.source_link;
      link.textContent = item.metric_id ? (' ' + item.metric_id + ' source') : ' source';
      div.appendChild(link);
    }});
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }}
  async function send(message) {{
    const dates = selectedDates();
    add(message, []);
    if (bloomBlockReason) return;
    const headers = await authHeaders();
    if (bloomBlockReason) return;
    const response = await fetch('/api/copilot/chat', {{
      method: 'POST',
      headers: headers,
      body: JSON.stringify({{
        message: message,
        filters: {{start: dates.start, end: dates.end, sources: selectedSources()}},
        request_id: 'ui_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      }})
    }});
    const payload = await response.json();
    let text = payload.answer || 'Goose is unavailable.';
    if (payload.interpretation) text += '\\n' + payload.interpretation;
    if (payload.footnote && payload.footnote.data_as_of) text += '\\nData as of ' + payload.footnote.data_as_of;
    if (payload.reset_date) text += '\\nNext reset ' + payload.reset_date;
    add(text, payload.evidence || []);
  }}
  document.getElementById('gooseOpen').addEventListener('click', () => {{
    panel.hidden = false;
    drawChips();
    tellParent('panel-open');
    requestBloomToken();
    if (!log.dataset.welcomed) {{
      add('{welcome}', []);
      log.dataset.welcomed = '1';
    }}
  }});
  document.getElementById('gooseClose').addEventListener('click', () => {{
    panel.hidden = true;
    tellParent('panel-closed');
  }});
  document.querySelectorAll('[data-goose-q]').forEach(btn => btn.addEventListener('click', () => send(btn.getAttribute('data-goose-q'))));
  document.getElementById('gooseForm').addEventListener('submit', (event) => {{
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    send(message);
  }});
  document.getElementById('gooseIssue').addEventListener('click', async () => {{
    const note = window.prompt('What looks wrong?');
    if (!note) return;
    const response = await fetch('/api/copilot/feedback', {{
      method: 'POST',
      headers: await authHeaders(),
      body: JSON.stringify({{message: note}})
    }});
    const payload = await response.json();
    add(payload.answer || 'Feedback was not saved.', []);
  }});
}})();
</script>
"""
