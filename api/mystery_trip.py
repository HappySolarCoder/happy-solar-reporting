# -*- coding: utf-8 -*-

"""Vercel Python function: /api/mystery_trip

Mystery Trip contest board (ClickUp 86bccr3du). Lives in the Data Center
"Contests" section. Oct 1 – Dec 23, 2026. FMA and Closer paths from the
contest graphic; the middle Self-Gen column is left out on purpose.

Read-only. Numbers come from the canonical metric endpoints, fetched in the
browser the same way the Scottsdale incentive page does it:
- /api/metrics/fma_weekly_review  FMA roster (name + setter last name)
- /api/metrics/demo_rate          per-setter demos (Sweeper/Rehash credit applied)
- /api/metrics/sales              sales by setter and by owner (sold date)
- /api/metrics/sales_cancellations cancellation rate by owner
- /api/metrics/bloom_goals        monthly demo and sales goals set in Bloom

Rules live in mystery_trip_logic.txt (pure JS, tested in Node).
Recruiting credits have no data source yet. RECRUIT_CREDITS is the list a
manager confirms; each entry is one qualifying-month credit for the recruiter.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav

# One row per successful recruit, confirmed by a manager:
# {"recruiter": "Full Name", "recruit": "Full Name", "month": "2026-10"}
# The recruit earned their full stipend in their first full month.
RECRUIT_CREDITS: tuple[dict[str, str], ...] = ()


def logic_js() -> str:
    return API_DIR.joinpath("mystery_trip_logic.txt").read_text(encoding="utf-8")


PALM_SVG = (
    '<svg class="mt-palm" viewBox="0 0 120 160" aria-hidden="true" focusable="false">'
    '<path d="M62 158c-2-38 0-74 8-104" stroke="currentColor" stroke-width="6" fill="none" stroke-linecap="round"/>'
    '<path d="M70 54c-14-20-38-26-62-18 20 2 36 10 46 24z"/>'
    '<path d="M70 54c4-24 22-40 46-42-16 10-26 24-30 42z"/>'
    '<path d="M70 54c-22-6-44 4-56 22 16-8 34-12 50-8z"/>'
    '<path d="M70 54c18-12 40-10 50 4-16-4-32-2-46 6z"/>'
    '<path d="M70 54c-6-20-2-40 12-52-4 16-4 34-6 50z"/>'
    "</svg>"
)

PLANE_SVG = (
    '<svg class="mt-plane" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
    '<path d="M60 30c0-2-2-4-5-4H40L24 4h-7l8 22H12l-5-7H2l3 13-3 13h5l5-7h13l-8 22h7l16-22h15c3 0 5-2 5-4z"/>'
    "</svg>"
)

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Mystery Trip</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap" />
  <style>
__DASHBOARD_NAV_CSS__

    .mt {
      --ink: #10233a;
      --ink2: #3b4f66;
      --coral: #e4572e;
      --coral-ink: #b83a16;
      --teal: #0f7c7e;
      --teal-ink: #0b6163;
      --gold: #f6b94a;
      --sand: #f7dcae;
      --green-ink: #0c6b4f;
      --amber-ink: #9a5a00;
      --gray-ink: #5b6472;
      font-family: "DM Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #fff;
    }
    .mt * { box-sizing: border-box; }
    body.oc-root .wrap.mt { padding: 18px 22px 40px; }

    .mt-hero {
      position: relative;
      overflow: hidden;
      border-radius: 22px;
      padding: 28px 28px 26px;
      background:
        radial-gradient(circle at 78% 92%, rgba(255, 214, 120, 0.95) 0 9%, rgba(255, 214, 120, 0) 10%),
        linear-gradient(180deg, #0b2547 0%, #234c7a 34%, #b6566b 64%, #f0874f 82%, #f8c36a 100%);
      min-height: 280px;
      box-shadow: 0 18px 40px rgba(2, 10, 24, 0.45);
    }
    .mt-hero::after {
      content: "";
      position: absolute;
      left: 0; right: 0; bottom: 0;
      height: 46px;
      background: linear-gradient(180deg, rgba(10, 54, 74, 0) 0%, rgba(8, 44, 62, 0.85) 100%);
      pointer-events: none;
    }
    .mt-palm { position: absolute; bottom: -6px; width: 120px; height: 160px; fill: #0b1e2e; color: #0b1e2e; opacity: 0.92; z-index: 1; }
    .mt-palm.left { left: -14px; transform: scaleX(-1); }
    .mt-palm.right { right: 6px; width: 96px; height: 128px; }
    .mt-hero-inner { position: relative; z-index: 2; max-width: 760px; }
    .mt-kicker {
      display: inline-flex; gap: 8px; align-items: center;
      font-size: 12px; font-weight: 800; letter-spacing: 0.18em; text-transform: uppercase;
      color: #fff; background: rgba(8, 24, 44, 0.55); border: 1px solid rgba(255,255,255,0.35);
      padding: 6px 12px; border-radius: 999px;
    }
    .mt-title {
      margin: 14px 0 4px;
      font-family: "Permanent Marker", "Marker Felt", "Comic Sans MS", cursive;
      font-size: 64px; line-height: 0.98; letter-spacing: 0.01em;
      color: #fff7e8;
      text-shadow: 0 3px 0 rgba(120, 40, 20, 0.55), 0 10px 24px rgba(0, 0, 0, 0.35);
      transform: rotate(-2deg);
      transform-origin: left center;
    }
    .mt-tagline { font-size: 16px; font-weight: 700; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.45); margin: 8px 0 0; }
    .mt-facts { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
    .mt-fact {
      background: rgba(8, 24, 44, 0.62); border: 1px solid rgba(255,255,255,0.28);
      border-radius: 14px; padding: 9px 13px; min-width: 150px;
    }
    .mt-fact b { display: block; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #ffe2b0; font-weight: 800; }
    .mt-fact span { display: block; font-size: 16px; font-weight: 800; color: #fff; margin-top: 2px; }

    .mt-route { position: relative; z-index: 2; margin-top: 22px; max-width: 900px; }
    .mt-route-line { position: relative; height: 44px; }
    .mt-route-line::before {
      content: ""; position: absolute; left: 10px; right: 10px; top: 21px;
      border-top: 3px dashed rgba(255, 255, 255, 0.75);
    }
    .mt-route-done { position: absolute; left: 10px; top: 20px; height: 5px; border-radius: 4px; background: #fff3d6; box-shadow: 0 0 10px rgba(255, 233, 180, 0.9); }
    .mt-plane { position: absolute; top: 4px; width: 38px; height: 38px; fill: #fff; filter: drop-shadow(0 2px 3px rgba(0,0,0,0.4)); transform: translateX(-50%); }
    .mt-route-stops { display: flex; justify-content: space-between; margin-top: 2px; font-size: 12px; font-weight: 800; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
    .mt-route-stops span:last-child { text-align: right; }

    .mt-bar {
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px;
      margin: 18px 0 6px;
    }
    .mt-tabs { display: inline-flex; background: #0d2a42; border: 1px solid #2b4e66; border-radius: 999px; padding: 4px; }
    .mt-tab {
      appearance: none; border: 0; background: transparent; color: #d5e3ec; cursor: pointer;
      font: inherit; font-size: 14px; font-weight: 800; padding: 9px 16px; border-radius: 999px;
    }
    .mt-tab[aria-selected="true"] { background: var(--gold); color: #10233a; }
    .mt-tab:focus-visible, .mt-find select:focus-visible { outline: 3px solid #8fe3ff; outline-offset: 2px; }
    .mt-find { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: #d5e3ec; }
    body.oc-root .mt-find select {
      background: #0d2a42; color: #f1f6ff; border: 1px solid #3b6680; border-radius: 10px;
      padding: 8px 10px; font: inherit; font-size: 14px; font-weight: 700; max-width: 220px;
    }
    .mt-status { font-size: 13px; color: #c5d7e6; margin: 4px 0 0; }
    .mt-status.alert { color: #ffd2c4; }

    .mt-board { display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 16px; margin-top: 12px; }
    .mt-mine-wrap { margin-top: 14px; }
    .mt-mine-label { font-family: "Permanent Marker", cursive; font-size: 22px; color: var(--gold); margin: 0 0 8px; }

    .mt-pass {
      position: relative; display: grid; grid-template-columns: 1fr 156px;
      background: #ffffff; color: var(--ink); border-radius: 18px; overflow: hidden;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28);
    }
    .mt-pass.is-mine { outline: 4px solid var(--gold); outline-offset: 0; }
    .mt-pass-main { padding: 14px 16px 14px 18px; min-width: 0; }
    .mt-pass-top { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
    .mt-airline { font-size: 11px; font-weight: 800; letter-spacing: 0.16em; color: var(--teal-ink); text-transform: uppercase; }
    .mt-seat { font-size: 11px; font-weight: 800; color: var(--ink2); letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap; }
    .mt-name { font-size: 21px; font-weight: 900; letter-spacing: -0.01em; margin: 4px 0 2px; overflow-wrap: anywhere; }
    .mt-sub { font-size: 12.5px; color: var(--ink2); font-weight: 600; }
    .mt-stamps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    .mt-stamp {
      border: 2.5px solid currentColor; border-radius: 14px; padding: 8px 6px 7px; text-align: center;
      min-height: 92px; display: flex; flex-direction: column; justify-content: center; gap: 2px;
    }
    .mt-stamp .m { font-size: 11px; font-weight: 900; letter-spacing: 0.14em; text-transform: uppercase; }
    .mt-stamp .v { font-size: 19px; font-weight: 900; line-height: 1.1; }
    .mt-stamp .d { font-size: 11.5px; font-weight: 700; line-height: 1.25; }
    .mt-stamp.hit { color: var(--green-ink); background: #e9f7f1; transform: rotate(-2.5deg); }
    .mt-stamp.live { color: var(--amber-ink); background: #fff6e5; border-style: dashed; }
    .mt-stamp.missed { color: var(--gray-ink); background: #f1f3f5; }
    .mt-stamp.upcoming { color: #6b7684; background: #f6f8fa; border-style: dotted; }
    .mt-stamp.nogoal { color: var(--coral-ink); background: #fff0eb; border-style: dashed; }
    .mt-meter { height: 6px; border-radius: 999px; background: rgba(16, 35, 58, 0.12); overflow: hidden; margin: 4px 6px 0; }
    .mt-meter i { display: block; height: 100%; background: currentColor; border-radius: 999px; }
    .mt-note { font-size: 12px; color: var(--ink2); margin-top: 10px; line-height: 1.4; }
    .mt-note strong { color: var(--ink); }

    .mt-stub {
      position: relative; padding: 14px 12px; display: flex; flex-direction: column; gap: 8px;
      background: linear-gradient(180deg, #fff7ea 0%, #ffe9c7 100%);
      border-left: 2px dashed rgba(16, 35, 58, 0.35);
    }
    .mt-stub::before, .mt-stub::after {
      content: ""; position: absolute; left: -11px; width: 20px; height: 20px; border-radius: 50%; background: #061727;
    }
    .mt-stub::before { top: -10px; }
    .mt-stub::after { bottom: -10px; }
    .mt-perk { display: flex; flex-direction: column; gap: 1px; }
    .mt-perk b { font-size: 10.5px; font-weight: 900; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink2); }
    .mt-perk span { font-size: 13.5px; font-weight: 900; }
    .mt-perk.earned span { color: var(--green-ink); }
    .mt-perk.in-reach span { color: var(--teal-ink); }
    .mt-perk.needs span { color: var(--amber-ink); }
    .mt-perk.missed span { color: var(--gray-ink); }
    .mt-credit { margin-top: auto; font-size: 11.5px; font-weight: 800; color: var(--coral-ink); }

    .mt-panels { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 26px; }
    .mt-panel {
      background: #0d2a42; border: 1px solid #2b4e66; border-radius: 18px; padding: 16px 18px; color: #e7f1f8;
    }
    .mt-panel h2 { margin: 0 0 10px; font-family: "Permanent Marker", cursive; font-weight: 400; font-size: 24px; color: var(--gold); letter-spacing: 0.01em; }
    .mt-panel ul { margin: 0; padding-left: 18px; }
    .mt-panel li { margin: 0 0 8px; font-size: 14px; line-height: 1.45; color: #e7f1f8; }
    .mt-panel li b { color: #fff; }
    .mt-panel p { font-size: 13.5px; line-height: 1.5; color: #d5e3ec; margin: 0 0 8px; }
    .mt-credit-list { margin-top: 6px; font-size: 13px; color: #d5e3ec; }
    .mt-empty { padding: 22px; border: 2px dashed #2b4e66; border-radius: 16px; color: #d5e3ec; text-align: center; font-size: 14px; }
    #asOf { font-size: 12px; color: #c5d7e6; }

    @media (max-width: 1100px) {
      .mt-panels { grid-template-columns: 1fr; }
    }
    @media (max-width: 640px) {
      body.oc-root .wrap.mt { padding: 10px 10px 28px; }
      .mt-hero { padding: 20px 16px 18px; border-radius: 18px; min-height: 0; }
      .mt-title { font-size: 44px; }
      .mt-tagline { font-size: 14px; }
      .mt-fact { min-width: 0; flex: 1 1 calc(50% - 10px); padding: 8px 10px; }
      .mt-fact span { font-size: 14px; }
      .mt-palm.left { width: 80px; height: 110px; left: -20px; opacity: 0.6; }
      .mt-palm.right { width: 64px; height: 88px; opacity: 0.6; }
      .mt-board { grid-template-columns: 1fr; }
      .mt-pass { grid-template-columns: 1fr; }
      .mt-stub { border-left: 0; border-top: 2px dashed rgba(16, 35, 58, 0.35); flex-direction: row; flex-wrap: wrap; gap: 10px 16px; }
      .mt-stub::before, .mt-stub::after { display: none; }
      .mt-perk { min-width: 120px; }
      .mt-credit { margin-top: 0; width: 100%; }
      .mt-stamp { min-height: 86px; padding: 7px 4px; }
      .mt-stamp .v { font-size: 17px; }
      .mt-bar { flex-direction: column; align-items: stretch; }
      .mt-tabs { width: 100%; }
      .mt-tab { flex: 1 1 0; padding: 9px 8px; }
      .mt-find { justify-content: space-between; }
      body.oc-root .mt-find select { max-width: 60%; flex: 1 1 auto; }
    }
    @media (prefers-reduced-motion: no-preference) {
      .mt-plane { transition: left 600ms ease; }
    }
  </style>
</head>
<body data-oc-native-filters="1">
__DASHBOARD_NAV_HTML__
  <main class="wrap mt" id="mysteryTrip">
    <section class="mt-hero" aria-labelledby="mtTitle">
      __PALM_LEFT__
      __PALM_RIGHT__
      <div class="mt-hero-inner">
        <span class="mt-kicker">Contest · Oct 1 – Dec 23</span>
        <h1 class="mt-title" id="mtTitle">Mystery Trip</h1>
        <p class="mt-tagline">Work hard. Earn it. See you there. Where is there? That part is a secret.</p>
        <div class="mt-facts">
          <div class="mt-fact"><b>Destination</b><span>??? Revealed later</span></div>
          <div class="mt-fact"><b>Departs</b><span>Sometime in February</span></div>
          <div class="mt-fact"><b>Boarding closes</b><span id="mtDaysLeft">Dec 23</span></div>
        </div>
      </div>
      <div class="mt-route" aria-hidden="true">
        <div class="mt-route-line">
          <div class="mt-route-done" id="mtRouteDone" style="width:0"></div>
          <span id="mtPlane" style="position:absolute;left:10px;top:0;">__PLANE__</span>
        </div>
        <div class="mt-route-stops"><span>Oct 1</span><span>Nov 1</span><span>Dec 1</span><span>Dec 23</span></div>
      </div>
    </section>

    <div class="mt-bar">
      <div class="mt-tabs" role="tablist" aria-label="Contest path">
        <button class="mt-tab" type="button" role="tab" id="tabFma" aria-selected="true" aria-controls="mtBoard" data-path="fma">Field Marketing Agents</button>
        <button class="mt-tab" type="button" role="tab" id="tabCloser" aria-selected="false" aria-controls="mtBoard" data-path="closer">Closers</button>
      </div>
      <label class="mt-find" for="mtFind">Find your boarding pass
        <select id="mtFind"><option value="">Everyone</option></select>
      </label>
    </div>
    <p class="mt-status" id="mtStatus" role="status">Loading the boarding list…</p>
    <div id="asOf"></div>

    <div class="mt-mine-wrap" id="mtMineWrap" hidden>
      <p class="mt-mine-label">Your boarding pass</p>
      <div id="mtMine"></div>
    </div>

    <div class="mt-board" id="mtBoard" role="tabpanel" aria-labelledby="tabFma" aria-live="polite"></div>

    <div class="mt-panels">
      <section class="mt-panel" aria-labelledby="rulesFma">
        <h2 id="rulesFma">FMA path</h2>
        <ul>
          <li><b>Steak Dinner month:</b> hit your full monthly stipend requirement one week early. Deadlines: Oct 24, Nov 23, Dec 23.</li>
          <li><b>Trip paid for:</b> Steak Dinner 2 of 3 months.</li>
          <li><b>Flight paid for:</b> Steak Dinner 3 of 3 months.</li>
          <li><b>Plus one:</b> 24 total sales Oct 1 – Dec 23 (about 8 a month), on top of earning the trip.</li>
        </ul>
      </section>
      <section class="mt-panel" aria-labelledby="rulesCloser">
        <h2 id="rulesCloser">Closer path</h2>
        <ul>
          <li><b>Goal month:</b> hit the monthly sales goal the company set for you in Bloom.</li>
          <li><b>Trip paid for:</b> goal 2 of 3 months.</li>
          <li><b>Flight paid for:</b> goal 3 of 3 months.</li>
          <li><b>Plus one:</b> keep your cancellation rate under 30% every month, on top of earning the trip.</li>
        </ul>
      </section>
      <section class="mt-panel" aria-labelledby="rulesRecruit">
        <h2 id="rulesRecruit">Recruiting bonus</h2>
        <p>Recruit a new rep who earns their full stipend in their first full month and you get 1 qualifying-month credit for each one. Credits stack.</p>
        <p>A credit can turn a missed month into a qualifying month for the trip or the flight. It does not replace the FMA 24-sale or the Closer under-30% rule for the plus one.</p>
        <p>A manager confirms each recruit, then the credit shows here.</p>
        <div class="mt-credit-list" id="mtCredits"></div>
      </section>
    </div>

    <section class="mt-panels" style="grid-template-columns:1fr;margin-top:16px">
      <div class="mt-panel">
        <h2>How we count</h2>
        <ul>
          <li><b>Demos</b> are the same count as the Demo % dashboards: appointments marked Demo, credited to the setter (Sweeper/Rehash credit included), counted by the Steak Dinner deadline.</li>
          <li><b>Stipend requirement</b> is your monthly demo goal in Bloom. If no goal is set, it is the standard 15 demos.</li>
          <li><b>FMA sales</b> are sales credited to you as the setter, by sold date. <b>Closer sales</b> are credited to the opportunity owner, by sold date.</li>
          <li><b>Cancellation rate</b> is sales you closed that month that are now cancelled, divided by sales you closed that month. A later cancellation can still change a month.</li>
          <li>Dates follow Eastern time, like the rest of the Data Center. Standings are final after Dec 23.</li>
        </ul>
      </div>
    </section>
  </main>

  <script>
__LOGIC_JS__
  </script>
  <script>
    (function () {
      var MT = MysteryTrip;
      var CREDITS = __CREDITS_JSON__;
      var STORE_KEY = "hsMysteryTripTraveler";
      var state = { path: "fma", fma: [], closer: [], traveler: "" };

      function esc(value) {
        return String(value == null ? "" : value)
          .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
      }

      function nyToday() {
        var parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
        var get = function (type) { return (parts.filter(function (p) { return p.type === type; })[0] || {}).value; };
        return get("year") + "-" + get("month") + "-" + get("day");
      }

      function nyClock() {
        return new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }).format(new Date());
      }

      async function getJson(url, optional) {
        var response = await fetch(url, optional ? { hsOptional: true } : {});
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      }

      function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

      function perk(label, status, detail) {
        var map = {
          "earned": ["earned", "Earned"],
          "in-reach": ["in-reach", "In reach"],
          "needs-credit": ["needs", "Needs a recruiting credit"],
          "needs-trip": ["needs", "Sales done, needs the trip"],
          "at-risk": ["needs", "Over 30% this month"],
          "missed": ["missed", "Missed"],
        };
        var pick = map[status] || ["in-reach", "In reach"];
        return '<div class="mt-perk ' + pick[0] + '"><b>' + esc(label) + '</b><span>' + esc(detail || pick[1]) + '</span></div>';
      }

      function fmaStamp(m) {
        if (m.status === "upcoming") {
          return '<div class="mt-stamp upcoming"><span class="m">' + esc(m.short) + '</span><span class="v">Soon</span><span class="d">Starts ' + esc(MT.shortDate(m.id + "-01")) + '</span></div>';
        }
        var pct = m.requirement ? Math.min(100, Math.round((m.demos / m.requirement) * 100)) : 0;
        var label = m.status === "hit" ? "Steak Dinner" : m.status === "missed" ? "Missed" : plural(m.daysLeft, "day", "days") + " left";
        var cls = m.status === "hit" ? "hit" : m.status === "missed" ? "missed" : "live";
        return '<div class="mt-stamp ' + cls + '"><span class="m">' + esc(m.short) + '</span>' +
          '<span class="v">' + esc(m.demos) + ' / ' + esc(m.requirement) + '</span>' +
          '<span class="d">demos by ' + esc(MT.shortDate(m.deadline)) + '</span>' +
          (m.status === "live" ? '<div class="mt-meter"><i style="width:' + pct + '%"></i></div>' : '') +
          '<span class="d">' + esc(label) + '</span></div>';
      }

      function closerStamp(m) {
        if (m.status === "upcoming") {
          return '<div class="mt-stamp upcoming"><span class="m">' + esc(m.short) + '</span><span class="v">Soon</span><span class="d">Starts ' + esc(MT.shortDate(m.id + "-01")) + '</span></div>';
        }
        if (m.goal == null) {
          return '<div class="mt-stamp ' + (m.status === "missed" ? "missed" : "nogoal") + '"><span class="m">' + esc(m.short) + '</span>' +
            '<span class="v">' + esc(m.sales) + ' sales</span><span class="d">No Bloom goal set</span>' +
            '<span class="d">' + esc(m.cancelRate) + '% cancelled</span></div>';
        }
        var pct = Math.min(100, Math.round((m.sales / m.goal) * 100));
        var label = m.status === "hit" ? "Goal hit" : m.status === "missed" ? "Missed" : plural(m.daysLeft, "day", "days") + " left";
        var cls = m.status === "hit" ? "hit" : m.status === "missed" ? "missed" : "live";
        return '<div class="mt-stamp ' + cls + '"><span class="m">' + esc(m.short) + '</span>' +
          '<span class="v">' + esc(m.sales) + ' / ' + esc(m.goal) + '</span>' +
          '<span class="d">sales · ' + esc(label) + '</span>' +
          (m.status === "live" ? '<div class="mt-meter"><i style="width:' + pct + '%"></i></div>' : '') +
          '<span class="d">' + esc(m.cancelRate) + '% cancelled</span></div>';
      }

      function monthsLine(p) {
        var text = plural(p.qualifyingMonths, "qualifying month", "qualifying months");
        if (p.creditMonthsUsed) text += " + " + plural(p.creditMonthsUsed, "recruiting credit", "recruiting credits");
        return text + " of 3";
      }

      function passHtml(p, mine) {
        var stamps = p.months.map(p.role === "fma" ? fmaStamp : closerStamp).join("");
        var plusDetail;
        if (p.role === "fma") {
          plusDetail = p.plusOne === "earned" ? "Earned" : p.plusOne === "missed" ? "Missed" : p.plusOne === "needs-trip" ? "Sales done, needs the trip" : p.totalSales + " of 24 sales";
        } else {
          plusDetail = p.plusOne === "earned" ? "Earned" : p.plusOne === "missed" ? "Missed" : p.plusOne === "at-risk" ? "Over 30% this month" : p.plusOne === "needs-trip" ? "Needs the trip" : "Under 30% so far";
        }
        var notes = [];
        if (p.role === "fma") {
          var live = MT.currentMonth(p);
          if (live && live.requirementSource === "standard") notes.push("No Bloom demo goal for " + live.label + ", so the standard " + live.requirement + " demos apply.");
          if (p.sharedLastName) notes.push("Another FMA has the same last name, so demo and sales counts may include theirs.");
        } else {
          var noGoal = p.months.filter(function (m) { return m.status === "no-goal-yet"; })[0];
          if (noGoal) notes.push("No Bloom sales goal for " + noGoal.label + " yet. A manager sets it in Bloom Goal setting.");
        }
        return '<article class="mt-pass' + (mine ? ' is-mine' : '') + '" aria-label="' + esc(p.name) + ' boarding pass">' +
          '<div class="mt-pass-main">' +
            '<div class="mt-pass-top"><span class="mt-airline">Happy Solar Air · Mystery Trip</span><span class="mt-seat">' + (p.role === "fma" ? "FMA" : "Closer") + '</span></div>' +
            '<div class="mt-name">' + esc(p.name) + '</div>' +
            '<div class="mt-sub">' + esc(monthsLine(p)) + (p.role === "fma" ? " · " + esc(plural(p.totalSales, "sale", "sales")) + " so far" : "") + '</div>' +
            '<div class="mt-stamps">' + stamps + '</div>' +
            (notes.length ? '<div class="mt-note">' + notes.map(esc).join(" ") + '</div>' : '') +
          '</div>' +
          '<div class="mt-stub">' +
            perk("Trip", p.trip) +
            perk("Flight", p.flight) +
            perk("Plus one", p.plusOne, plusDetail) +
            '<div class="mt-credit">' + (p.credits ? esc(plural(p.credits, "recruiting credit", "recruiting credits")) : "No recruiting credits yet") + '</div>' +
          '</div>' +
        '</article>';
      }

      function renderFind() {
        var select = document.getElementById("mtFind");
        var people = state.fma.concat(state.closer).map(function (p) { return p.name; }).sort(function (a, b) { return a.localeCompare(b); });
        var seen = {};
        var options = ['<option value="">Everyone</option>'];
        people.forEach(function (name) {
          if (seen[name]) return;
          seen[name] = true;
          options.push('<option value="' + esc(name) + '">' + esc(name) + '</option>');
        });
        select.innerHTML = options.join("");
        var match = MT.findTraveler(state.fma.concat(state.closer), state.traveler);
        select.value = match ? match.name : "";
      }

      function render() {
        var board = document.getElementById("mtBoard");
        var people = MT.sortBoard(state.path === "fma" ? state.fma : state.closer);
        var all = state.fma.concat(state.closer);
        var mine = MT.findTraveler(all, state.traveler);
        var mineWrap = document.getElementById("mtMineWrap");
        if (mine) {
          mineWrap.hidden = false;
          document.getElementById("mtMine").innerHTML = passHtml(mine, true);
        } else {
          mineWrap.hidden = true;
          document.getElementById("mtMine").innerHTML = "";
        }
        document.getElementById("tabFma").setAttribute("aria-selected", state.path === "fma" ? "true" : "false");
        document.getElementById("tabCloser").setAttribute("aria-selected", state.path === "closer" ? "true" : "false");
        board.setAttribute("aria-labelledby", state.path === "fma" ? "tabFma" : "tabCloser");
        if (!people.length) {
          board.innerHTML = '<div class="mt-empty">No one on this path yet.</div>';
          return;
        }
        board.innerHTML = people.map(function (p) { return passHtml(p, mine && mine.name === p.name); }).join("");
      }

      function renderCredits() {
        var host = document.getElementById("mtCredits");
        if (!CREDITS.length) { host.textContent = "No recruiting credits yet."; return; }
        host.innerHTML = "<ul>" + CREDITS.map(function (c) {
          return "<li><b>" + esc(c.recruiter) + "</b> recruited " + esc(c.recruit) + " (" + esc(c.month_label || c.month) + ")</li>";
        }).join("") + "</ul>";
      }

      function renderRoute(today) {
        var share = MT.contestProgress(today);
        var line = document.querySelector(".mt-route-line");
        var width = line ? line.clientWidth - 20 : 0;
        var x = 10 + Math.round(width * share);
        document.getElementById("mtPlane").style.left = x + "px";
        document.getElementById("mtRouteDone").style.width = Math.max(0, x - 10) + "px";
        var left = MT.daysLeftInContest(today);
        document.getElementById("mtDaysLeft").textContent = today > MT.CONTEST.end ? "Closed Dec 23" : "Dec 23 · " + plural(left, "day", "days") + " left";
      }

      async function load() {
        var today = nyToday();
        var status = document.getElementById("mtStatus");
        status.classList.remove("alert");
        status.textContent = "Loading the boarding list…";
        renderRoute(today);
        renderCredits();
        var rosterDay = today < MT.CONTEST.start ? MT.CONTEST.start : today > MT.CONTEST.end ? MT.CONTEST.end : today;
        var windows = MT.windowsFor(today);
        var problems = [];
        // oc_raw=1 keeps the Data Center territory and lead source filters off every contest count.
        var rosterJob = getJson("/api/metrics/fma_weekly_review?oc_raw=1&format=json&start=" + rosterDay + "&end=" + rosterDay);
        var monthJobs = windows.map(function (w) {
          var range = "oc_raw=1&format=json&start=" + w.start + "&end=" + w.end;
          return Promise.allSettled([
            getJson("/api/metrics/demo_rate?oc_raw=1&format=json&start=" + w.start + "&end=" + w.steakEnd),
            getJson("/api/metrics/sales?" + range),
            getJson("/api/metrics/sales_cancellations?" + range, true),
            getJson("/api/metrics/bloom_goals?oc_raw=1&period=" + w.id, true),
          ]);
        });
        var rosterResult = await Promise.allSettled([rosterJob]);
        var monthResults = await Promise.all(monthJobs);
        var roster = [];
        if (rosterResult[0].status === "fulfilled") {
          roster = ((rosterResult[0].value || {}).people || []).map(function (row) {
            return { name: row.display_name || row.name || "", setterLastName: row.ghl_setter_last_name || "" };
          }).filter(function (row) { return row.name; });
        } else {
          problems.push("the FMA roster");
        }
        var feeds = {};
        windows.forEach(function (w, index) {
          var r = monthResults[index];
          var demo = r[0].status === "fulfilled" ? r[0].value : null;
          var sales = r[1].status === "fulfilled" ? r[1].value : null;
          var cancels = r[2].status === "fulfilled" ? r[2].value : null;
          var goals = r[3].status === "fulfilled" ? r[3].value : null;
          var label = MT.MONTHS.filter(function (m) { return m.id === w.id; })[0].label;
          if (!demo) problems.push(label + " demos");
          if (!sales) problems.push(label + " sales");
          if (!cancels) problems.push(label + " cancellations");
          if (!goals || goals.available === false) problems.push(label + " Bloom goals");
          feeds[w.id] = {
            loaded: Boolean(demo && sales),
            steakDemos: ((demo || {}).breakdowns || {}).sit_by_setter_last_name || {},
            salesBySetter: ((sales || {}).breakdowns || {}).sales_by_setter_last_name || {},
            salesByOwner: ((sales || {}).breakdowns || {}).sales_by_owner || {},
            cancelByOwner: (((cancels || {}).tables || {}).by_owner) || [],
            goals: (goals && goals.person_goals) || [],
          };
        });
        state.fma = MT.buildFma({ today: today, roster: roster, feeds: feeds, credits: CREDITS });
        state.closer = MT.buildClosers({ today: today, feeds: feeds, credits: CREDITS });
        renderFind();
        render();
        document.getElementById("asOf").textContent = "Updated " + nyClock() + " ET";
        if (problems.length) {
          status.classList.add("alert");
          status.textContent = "Some numbers did not load (" + problems.join(", ") + "), so a few counts may be low. Refresh to try again.";
        } else {
          status.textContent = state.fma.length + " FMAs and " + state.closer.length + " closers on the boarding list. Numbers through " + MT.shortDate(today > MT.CONTEST.end ? MT.CONTEST.end : today) + ".";
        }
      }

      function boot() {
        var params = new URLSearchParams(window.location.search);
        var fromUrl = (params.get("traveler") || "").trim().slice(0, 80);
        var saved = "";
        try { saved = window.localStorage.getItem(STORE_KEY) || ""; } catch (err) {}
        state.traveler = fromUrl || saved;
        var startPath = (params.get("path") || "").toLowerCase();
        if (startPath === "closer" || startPath === "closers") state.path = "closer";
        document.querySelectorAll(".mt-tab").forEach(function (tab) {
          tab.addEventListener("click", function () {
            state.path = tab.getAttribute("data-path") === "closer" ? "closer" : "fma";
            render();
          });
        });
        document.getElementById("mtFind").addEventListener("change", function (event) {
          state.traveler = event.target.value || "";
          try {
            if (state.traveler) window.localStorage.setItem(STORE_KEY, state.traveler);
            else window.localStorage.removeItem(STORE_KEY);
          } catch (err) {}
          var mine = MT.findTraveler(state.closer, state.traveler);
          if (mine) state.path = "closer";
          else if (MT.findTraveler(state.fma, state.traveler)) state.path = "fma";
          render();
        });
        window.addEventListener("resize", function () { renderRoute(nyToday()); });
        window.hsOpsReload = load;
        load().then(function () {
          var mine = MT.findTraveler(state.closer, state.traveler);
          if (mine && !startPath) { state.path = "closer"; render(); }
        }).catch(function (err) {
          var status = document.getElementById("mtStatus");
          status.classList.add("alert");
          status.textContent = "The boarding list did not load. Refresh to try again.";
          document.getElementById("mtBoard").innerHTML = '<div class="mt-empty">The boarding list did not load. Refresh to try again.</div>';
        });
      }

      boot();
    })();
  </script>
</body>
</html>
"""


def credits_payload() -> list[dict[str, str]]:
    labels = {"2026-10": "October", "2026-11": "November", "2026-12": "December"}
    rows = []
    for row in RECRUIT_CREDITS:
        recruiter = str(row.get("recruiter") or "").strip()
        recruit = str(row.get("recruit") or "").strip()
        month = str(row.get("month") or "").strip()
        if not recruiter or not recruit:
            continue
        rows.append({"recruiter": recruiter, "recruit": recruit, "month": month, "month_label": labels.get(month, month)})
    return rows


def render_page() -> str:
    credits = json.dumps(credits_payload()).replace("</", "<\\/")
    return (
        HTML.replace("__DASHBOARD_NAV_CSS__", dashboard_nav_css())
        .replace("__DASHBOARD_NAV_HTML__", render_dashboard_nav("mystery_trip"))
        .replace("__PALM_LEFT__", PALM_SVG.replace('class="mt-palm"', 'class="mt-palm left"'))
        .replace("__PALM_RIGHT__", PALM_SVG.replace('class="mt-palm"', 'class="mt-palm right"'))
        .replace("__PLANE__", PLANE_SVG)
        .replace("__LOGIC_JS__", logic_js())
        .replace("__CREDITS_JSON__", credits)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = parse_qs(urlparse(self.path).query)
            if (query.get("format") or [""])[0] == "json":
                body = json.dumps({"recruit_credits": credits_payload()}).encode("utf-8")
                content_type = "application/json"
            else:
                body = render_page().encode("utf-8")
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=300")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = ("ERROR: " + type(exc).__name__).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
