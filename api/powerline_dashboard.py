# -*- coding: utf-8 -*-

"""Vercel Python function: /api/powerline_dashboard

Powerline outbound calling dashboard.

Primary data source:
- Firestore project `gen-lang-client-0395385938`
- Collections:
  - `powerline_agents`
  - `powerline_call_history`
  - `powerline_leads`
  - `powerline_lists`

Window semantics:
- Lead KPIs filter by `powerline_leads.createdAt`
- Call KPIs filter by `powerline_call_history.timestamp`
- Lead stage counts reflect current lead state for leads created in the window

Required env:
- POWERLINE_FIREBASE_SERVICE_ACCOUNT_JSON
- Optional: POWERLINE_GCP_PROJECT_ID (defaults to `gen-lang-client-0395385938`)
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dashboard_nav import dashboard_nav_css, render_dashboard_nav


POWERLINE_DEFAULT_PROJECT_ID = "gen-lang-client-0395385938"
ET = ZoneInfo("America/New_York")


def html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def compact_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def looks_like_identifier(value: Any) -> bool:
    text = compact_str(value)
    if not text or " " in text or len(text) < 12:
        return False
    return all(ch.isalnum() or ch in {"-", "_"} for ch in text)


def best_person_name(record: dict[str, Any] | None, *, fallback: str = "") -> str:
    if not isinstance(record, dict):
        return fallback
    candidates = [
        record.get("name"),
        record.get("displayName"),
        record.get("fullName"),
        " ".join(part for part in (compact_str(record.get("firstName")), compact_str(record.get("lastName"))) if part),
        record.get("firstName"),
        record.get("lastName"),
        record.get("userName"),
        record.get("agentName"),
    ]
    for candidate in candidates:
        text = compact_str(candidate)
        if text and not looks_like_identifier(text):
            return text
    email = compact_str(record.get("email"))
    if "@" in email:
        return email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
    return fallback


def parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_date_ymd(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    try:
        year, month, day = [int(part) for part in str(value).strip().split("-")]
        return year, month, day
    except Exception:
        return None


def get_powerline_db() -> firestore.Client:
    creds_json = os.environ.get("POWERLINE_FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("POWERLINE_GCP_PROJECT_ID") or POWERLINE_DEFAULT_PROJECT_ID

    if not creds_json:
        raise RuntimeError("Missing required env var: POWERLINE_FIREBASE_SERVICE_ACCOUNT_JSON")

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, credentials=creds)


def resolve_window(qs: dict[str, list[str]]) -> tuple[datetime, datetime, str, str, int, int]:
    now_local = datetime.now(ET)
    start_q = (qs.get("start", [""])[0] or "").strip()
    end_q = (qs.get("end", [""])[0] or "").strip()

    if start_q and end_q:
        start_parts = parse_date_ymd(start_q)
        end_parts = parse_date_ymd(end_q)
        if not (start_parts and end_parts):
            raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
        start_local = datetime(start_parts[0], start_parts[1], start_parts[2], 0, 0, 0, tzinfo=ET)
        end_local_excl = datetime(end_parts[0], end_parts[1], end_parts[2], 0, 0, 0, tzinfo=ET) + timedelta(days=1)
        year = start_local.year
        month = start_local.month
        return start_local, end_local_excl, start_q, end_q, year, month

    default_day = now_local.date() - timedelta(days=1)
    year = default_day.year
    month = default_day.month
    start_local = datetime(default_day.year, default_day.month, default_day.day, 0, 0, 0, tzinfo=ET)
    end_local_excl = start_local + timedelta(days=1)
    return (
        start_local,
        end_local_excl,
        start_local.strftime("%Y-%m-%d"),
        (end_local_excl - timedelta(days=1)).strftime("%Y-%m-%d"),
        year,
        month,
    )


def build_payload(start_local: datetime, end_local_excl: datetime) -> dict[str, Any]:
    db = get_powerline_db()

    agents: dict[str, dict[str, str]] = {}
    for snap in db.collection("powerline_agents").stream():
        row = snap.to_dict() or {}
        agent = {
            "name": best_person_name(row, fallback="Unknown Agent"),
            "email": compact_str(row.get("email")),
            "role": compact_str(row.get("role")) or "unknown",
        }
        for key in {compact_str(row.get("id")), compact_str(row.get("userId")), compact_str(row.get("agentId")), compact_str(snap.id)}:
            if key:
                agents[key] = agent

    lists: dict[str, dict[str, Any]] = {}
    for snap in db.collection("powerline_lists").stream():
        row = snap.to_dict() or {}
        list_id = str(row.get("id") or snap.id)
        lists[list_id] = row

    lead_total = 0
    queued_total = 0
    dialed_total = 0
    skipped_total = 0
    callbacks_scheduled_total = 0
    claimed_total = 0
    with_source_total = 0
    stage_counts = Counter()
    campaign_counts = Counter()
    state_counts = Counter()
    source_counts = Counter()
    dial_count_distribution = Counter()
    assigned_agent_lead_counts = Counter()
    list_rows: dict[str, dict[str, Any]] = {}
    lead_map: dict[str, dict[str, Any]] = {}
    queue_age_buckets = Counter({"0-1d": 0, "2-3d": 0, "4-7d": 0, "8d+": 0})
    leads_created_by_day = Counter()
    now_utc = datetime.now(timezone.utc)

    for snap in db.collection("powerline_leads").stream():
        row = snap.to_dict() or {}
        created_dt = parse_iso_dt(row.get("createdAt"))
        if not created_dt:
            continue
        created_local = created_dt.astimezone(ET)
        if not (start_local <= created_local < end_local_excl):
            continue

        lead_total += 1
        lead_id = str(row.get("id") or snap.id)
        stage = str(row.get("stage") or "unknown").strip() or "unknown"
        assigned_agent = str(row.get("assignedAgent") or "").strip()
        list_id = str(row.get("listId") or "").strip()
        campaign_name = str(row.get("campaignName") or "").strip() or "Unknown"
        state = str(row.get("state") or "").strip() or "Unknown"
        source = str(row.get("source") or "").strip()
        dial_count = int(row.get("dialCount") or 0)
        last_dialed_dt = parse_iso_dt(row.get("lastDialedAt"))

        lead_map[lead_id] = {
            "listId": list_id,
            "assignedAgent": assigned_agent,
            "stage": stage,
            "campaignName": campaign_name,
        }
        leads_created_by_day[created_local.strftime("%Y-%m-%d")] += 1
        stage_counts[stage] += 1
        campaign_counts[campaign_name] += 1
        state_counts[state] += 1
        if source:
            source_counts[source] += 1
            with_source_total += 1
        dial_count_distribution[dial_count] += 1

        if stage == "queued":
            queued_total += 1
            age_days = max((now_utc - created_dt.astimezone(timezone.utc)).days, 0)
            if age_days <= 1:
                queue_age_buckets["0-1d"] += 1
            elif age_days <= 3:
                queue_age_buckets["2-3d"] += 1
            elif age_days <= 7:
                queue_age_buckets["4-7d"] += 1
            else:
                queue_age_buckets["8d+"] += 1

        if dial_count > 0 or last_dialed_dt is not None:
            dialed_total += 1
        if row.get("skippedAt"):
            skipped_total += 1
        if row.get("callbackTime"):
            callbacks_scheduled_total += 1
        if row.get("claimedAt"):
            claimed_total += 1
        if assigned_agent:
            assigned_agent_lead_counts[assigned_agent] += 1

        list_entry = list_rows.setdefault(
            list_id or "unassigned",
            {
                "listId": list_id or "unassigned",
                "label": str((lists.get(list_id) or {}).get("name") or "Unassigned"),
                "lead_total": 0,
                "queued": 0,
                "dialed": 0,
                "interested": 0,
                "no_answer": 0,
                "not_interested": 0,
                "callback": 0,
                "wrong_number": 0,
                "dnc": 0,
            },
        )
        list_entry["lead_total"] += 1
        if stage in list_entry:
            list_entry[stage] += 1
        if dial_count > 0 or last_dialed_dt is not None:
            list_entry["dialed"] += 1

    call_attempts = 0
    interested_calls = 0
    callback_calls = 0
    dnc_calls = 0
    total_duration = 0
    nonzero_duration_calls = 0
    gt60_duration_calls = 0
    result_counts = Counter()
    calls_by_day = Counter()
    interested_by_day = Counter()
    agent_call_counts = Counter()
    agent_rows: dict[str, dict[str, Any]] = {}
    distinct_leads_called = set()

    for snap in db.collection("powerline_call_history").stream():
        row = snap.to_dict() or {}
        call_dt = parse_iso_dt(row.get("timestamp"))
        if not call_dt:
            continue
        call_local = call_dt.astimezone(ET)
        if not (start_local <= call_local < end_local_excl):
            continue

        call_attempts += 1
        lead_id = str(row.get("leadId") or "").strip()
        agent_id = str(row.get("agentId") or "").strip()
        result = str(row.get("result") or "unknown").strip() or "unknown"
        duration = int(row.get("duration") or 0)
        day_key = call_local.strftime("%Y-%m-%d")

        total_duration += duration
        if duration > 0:
            nonzero_duration_calls += 1
        if duration > 60:
            gt60_duration_calls += 1
        if lead_id:
            distinct_leads_called.add(lead_id)

        result_counts[result] += 1
        calls_by_day[day_key] += 1
        agent_call_counts[agent_id] += 1

        if result == "interested":
            interested_calls += 1
            interested_by_day[day_key] += 1
        elif result == "callback":
            callback_calls += 1
        elif result == "dnc":
            dnc_calls += 1

        list_id = str((lead_map.get(lead_id) or {}).get("listId") or "").strip()
        agent_entry = agent_rows.setdefault(
            agent_id or "unassigned",
            {
                "agentId": agent_id or "unassigned",
                "label": agents.get(agent_id, {}).get("name") or (f"Unknown Agent ({agent_id[-6:]})" if agent_id else "Unassigned"),
                "call_attempts": 0,
                "interested": 0,
                "callback": 0,
                "dnc": 0,
                "not_interested": 0,
                "no_answer": 0,
                "wrong_number": 0,
                "distinct_leads": set(),
                "list_ids": set(),
            },
        )
        agent_entry["call_attempts"] += 1
        if result in agent_entry:
            agent_entry[result] += 1
        if lead_id:
            agent_entry["distinct_leads"].add(lead_id)
        if list_id:
            agent_entry["list_ids"].add(list_id)

    trend_rows = []
    trend_days = sorted(set(leads_created_by_day.keys()) | set(calls_by_day.keys()) | set(interested_by_day.keys()))
    for day in trend_days:
        attempts = calls_by_day.get(day, 0)
        interested = interested_by_day.get(day, 0)
        trend_rows.append(
            {
                "date": day,
                "leads_loaded": leads_created_by_day.get(day, 0),
                "call_attempts": attempts,
                "interested": interested,
                "interested_rate": round((interested / attempts) * 100.0, 1) if attempts else 0.0,
            }
        )

    by_agent = []
    for row in agent_rows.values():
        distinct_count = len(row.pop("distinct_leads"))
        list_count = len(row.pop("list_ids"))
        attempts = int(row["call_attempts"])
        interested = int(row["interested"])
        row["distinct_leads"] = distinct_count
        row["list_count"] = list_count
        row["interested_rate"] = round((interested / attempts) * 100.0, 1) if attempts else 0.0
        by_agent.append(row)
    by_agent.sort(key=lambda row: (-int(row["call_attempts"]), -int(row["interested"]), row["label"]))

    by_list = list(list_rows.values())
    for row in by_list:
        total = int(row["lead_total"])
        dialed = int(row["dialed"])
        interested = int(row["interested"])
        row["dial_coverage_rate"] = round((dialed / total) * 100.0, 1) if total else 0.0
        row["interested_rate"] = round((interested / total) * 100.0, 1) if total else 0.0
    by_list.sort(key=lambda row: (-int(row["lead_total"]), row["label"]))

    stage_table = [{"label": label, "count": count} for label, count in stage_counts.most_common()]
    queue_age_table = [{"label": label, "count": queue_age_buckets[label]} for label in ("0-1d", "2-3d", "4-7d", "8d+")]

    dialed_leads = dialed_total
    distinct_called_total = len(distinct_leads_called)
    payload = {
        "window_start_local": start_local.isoformat(),
        "window_end_local_exclusive": end_local_excl.isoformat(),
        "window_semantics": (
            "Lead KPIs use powerline_leads.createdAt in America/New_York. "
            "Call KPIs use powerline_call_history.timestamp in America/New_York. "
            "Lead stage counts reflect current stage for leads created in the selected window."
        ),
        "data_quality": {
            "call_duration_populated": nonzero_duration_calls > 0,
            "calls_with_nonzero_duration": nonzero_duration_calls,
            "calls_with_duration_gt_60": gt60_duration_calls,
            "lead_source_populated_rate": round((with_source_total / lead_total) * 100.0, 1) if lead_total else 0.0,
        },
        "kpis": {
            "leads_loaded": lead_total,
            "queued_leads": queued_total,
            "dialed_leads": dialed_leads,
            "dial_coverage_rate": round((dialed_leads / lead_total) * 100.0, 1) if lead_total else 0.0,
            "call_attempts": call_attempts,
            "distinct_leads_called": distinct_called_total,
            "avg_attempts_per_called_lead": round((call_attempts / distinct_called_total), 2) if distinct_called_total else 0.0,
            "interested_calls": interested_calls,
            "interested_rate": round((interested_calls / call_attempts) * 100.0, 1) if call_attempts else 0.0,
            "callback_rate": round((callback_calls / call_attempts) * 100.0, 1) if call_attempts else 0.0,
            "dnc_rate": round((dnc_calls / call_attempts) * 100.0, 1) if call_attempts else 0.0,
        },
        "tables": {
            "by_agent": by_agent,
            "by_list": by_list,
            "by_stage": stage_table,
            "queue_age": queue_age_table,
            "trend": trend_rows,
            "campaigns": [{"label": label, "count": count} for label, count in campaign_counts.most_common(12)],
            "states": [{"label": label, "count": count} for label, count in state_counts.most_common(12)],
            "call_results": [{"label": label, "count": count} for label, count in result_counts.most_common()],
            "assigned_agent_leads": [
                {"label": agents.get(agent_id, {}).get("name") or (f"Unknown Agent ({agent_id[-6:]})" if agent_id else "Unassigned"), "count": count}
                for agent_id, count in assigned_agent_lead_counts.most_common(12)
            ],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def render_html(year: int, month: int, default_start: str, default_end: str) -> str:
    nav_css = dashboard_nav_css()
    nav_html = render_dashboard_nav("powerline_dashboard")
    html = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Happy Solar — Powerline Dashboard</title>
  <style>
    :root {
      --bg:#f6f7fb; --card:#ffffff; --border:#e7ebf0; --text:#142033; --muted:#66758a; --muted2:#94a3b8;
      --pink:#ec4899; --pink2:#f472b6; --blue:#1d9bf0; --cyan:#06b6d4; --green:#10b981; --amber:#f59e0b; --slate:#475569; --red:#ef4444;
    }
    body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:var(--text); }
    .wrap { max-width:1280px; margin:0 auto; padding:22px; }
    .topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:18px 20px; border-radius:16px; background:var(--card); border:1px solid var(--border); box-shadow:0 2px 8px rgba(17,24,39,.05); }
    .title { font-size:24px; font-weight:950; letter-spacing:-.03em; color:#182338; }
    .subtitle { margin-top:4px; color:var(--muted); font-size:13px; max-width:760px; }
    .pinkline { height:3px; width:240px; border-radius:999px; background:linear-gradient(90deg,var(--pink) 0%, var(--pink2) 45%, rgba(244,114,182,0) 100%); margin-top:10px; }
__DASHBOARD_NAV_CSS__
    .navbtn { display:inline-flex; align-items:center; padding:9px 12px; border-radius:12px; border:1px solid var(--border); background:#fff; color:#1f2937; font-size:13px; font-weight:800; text-decoration:none; }
    .navbtn.active { background:rgba(236,72,153,.10); border-color:rgba(236,72,153,.45); color:#b80b66; }
    .filters { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .filter { display:flex; align-items:center; gap:8px; }
    .filter-label { font-size:12px; color:var(--muted); background:#f0f3f7; padding:9px 10px; border-radius:10px; border:1px solid var(--border); }
    select, button, input[type=date] { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:9px 12px; font-size:13px; }
    button { background:var(--pink); border-color:var(--pink); color:#fff; font-weight:900; cursor:pointer; }
    .ghost { background:#fff; color:#1f2937; border-color:var(--border); }
    .grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; margin-top:14px; }
    .card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:16px 18px; box-shadow:0 1px 3px rgba(17,24,39,.05); min-height:120px; }
    .span-3 { grid-column:span 3; } .span-4 { grid-column:span 4; } .span-6 { grid-column:span 6; } .span-8 { grid-column:span 8; } .span-12 { grid-column:span 12; }
    .card-title { font-size:12px; font-weight:900; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
    .kpi { margin-top:10px; font-size:40px; font-weight:950; letter-spacing:-.03em; }
    .meta { margin-top:6px; color:var(--muted2); font-size:12px; }
    .bars { margin-top:12px; display:flex; flex-direction:column; gap:10px; }
    .barrow { display:grid; grid-template-columns:170px 1fr 84px; gap:10px; align-items:center; }
    .barlabel { font-size:12px; font-weight:800; color:#334155; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .bartrack { width:100%; height:12px; border-radius:999px; background:#eef2f7; overflow:hidden; }
    .barfill { height:100%; border-radius:999px; }
    .barvalue { text-align:right; font-size:12px; font-weight:900; color:#475569; }
    .trend { margin-top:12px; display:flex; align-items:flex-end; gap:10px; min-height:260px; overflow-x:auto; padding-bottom:8px; }
    .trendcol { width:56px; min-width:56px; display:flex; flex-direction:column; align-items:center; gap:8px; }
    .stack { width:100%; height:180px; display:flex; flex-direction:column; justify-content:flex-end; gap:4px; }
    .seg { width:100%; border-radius:10px 10px 4px 4px; }
    .seg.leads { background:#dbeafe; } .seg.calls { background:var(--blue); } .seg.interested { background:var(--green); }
    .trendlabel { font-size:11px; color:#64748b; white-space:nowrap; transform:rotate(-30deg); transform-origin:center top; }
    .note { font-size:12px; color:#64748b; line-height:1.5; }
    .warn { color:#b45309; }
    .good { color:#047857; }
    .tableWrap { overflow:auto; max-height:420px; border:1px solid var(--border); border-radius:12px; margin-top:12px; }
    table { width:100%; border-collapse:collapse; }
    th, td { border-bottom:1px solid var(--border); padding:10px 8px; text-align:left; font-size:13px; vertical-align:top; }
    th { color:#64748b; font-weight:900; background:#fafbfc; position:sticky; top:0; }
    @media (max-width:980px) { .span-3,.span-4,.span-6,.span-8,.span-12 { grid-column:span 12; } .barrow { grid-template-columns:120px 1fr 70px; } }
    @media (max-width:640px) { .wrap { padding:12px; } .topbar { padding:12px; } .title { font-size:20px; } .nav { display:flex; flex-wrap:nowrap; overflow-x:auto; gap:8px; padding-bottom:4px; } .navbtn { white-space:nowrap; flex:0 0 auto; padding:8px 10px; font-size:12px; } .kpi { font-size:34px; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <div class="title">Powerline Dashboard</div>
        <div class="subtitle">Outbound phone performance across lead imports, agent activity, call outcomes, and queued backlog.</div>
        <div class="pinkline"></div>
__DASHBOARD_NAV_HTML__
      </div>
      <div class="filters">
        <div class="filter"><div class="filter-label">Year</div><select id="year"></select></div>
        <div class="filter"><div class="filter-label">Month</div><select id="month"></select></div>
        <button id="apply">Apply</button>
        <div class="filter"><div class="filter-label">Start</div><input id="startDate" type="date" /></div>
        <div class="filter"><div class="filter-label">End</div><input id="endDate" type="date" /></div>
        <button id="clearRange" class="ghost">Clear</button>
      </div>
    </div>

    <div class="grid">
      <div class="card span-3"><div class="card-title">Leads Loaded</div><div class="kpi" id="leadsLoaded">—</div><div class="meta">Leads created in selected window</div></div>
      <div class="card span-3"><div class="card-title">Queued Leads</div><div class="kpi" id="queuedLeads">—</div><div class="meta">Current stage = queued</div></div>
      <div class="card span-3"><div class="card-title">Dialed Leads</div><div class="kpi" id="dialedLeads">—</div><div class="meta">Dial count &gt; 0 or last dialed present</div></div>
      <div class="card span-3"><div class="card-title">Dial Coverage</div><div class="kpi" id="dialCoverage">—</div><div class="meta">Dialed leads / leads loaded</div></div>

      <div class="card span-3"><div class="card-title">Call Attempts</div><div class="kpi" id="callAttempts">—</div><div class="meta">Calls in selected window</div></div>
      <div class="card span-3"><div class="card-title">Distinct Leads Called</div><div class="kpi" id="distinctCalled">—</div><div class="meta">Unique lead ids touched by calls</div></div>
      <div class="card span-3"><div class="card-title">Interested Rate</div><div class="kpi" id="interestedRate">—</div><div class="meta">Interested calls / call attempts</div></div>
      <div class="card span-3"><div class="card-title">Callback / DNC</div><div class="kpi" id="callbackDnc">—</div><div class="meta">Callback rate and DNC rate</div></div>

      <div class="card span-8"><div class="card-title">Daily Leads vs Calls vs Interested</div><div id="trend" class="trend"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">Metric Semantics & Data Quality</div><div class="note" id="qualityNote">Loading…</div></div>

      <div class="card span-4"><div class="card-title">Lead Stage Breakdown</div><div id="stageBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">Queued Backlog Aging</div><div id="queueAgeBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-4"><div class="card-title">Assigned Lead Volume</div><div id="assignedLeadBars" class="bars"><div class="meta">Loading…</div></div></div>

      <div class="card span-6"><div class="card-title">Agent Call Leaderboard</div><div id="agentBars" class="bars"><div class="meta">Loading…</div></div></div>
      <div class="card span-6"><div class="card-title">List / Campaign Lead Volume</div><div id="listBars" class="bars"><div class="meta">Loading…</div></div></div>

      <div class="card span-12"><div class="card-title">Agent Performance Table</div><div class="tableWrap"><table id="agentTable"></table></div></div>
      <div class="card span-12"><div class="card-title">List Performance Table</div><div class="tableWrap"><table id="listTable"></table></div></div>
    </div>
  </div>
<script>
var defaultYear = __YEAR__;
var defaultMonth = __MONTH__;
var defaultStart = "__DEFAULT_START__";
var defaultEnd = "__DEFAULT_END__";
var yearSel = document.getElementById('year');
var monthSel = document.getElementById('month');
var startDate = document.getElementById('startDate');
var endDate = document.getElementById('endDate');
function setOptions(sel, options, value) {
  sel.innerHTML = '';
  options.forEach(function(opt) {
    var o = document.createElement('option');
    o.value = String(opt.value);
    o.textContent = opt.label;
    if (String(opt.value) === String(value)) o.selected = true;
    sel.appendChild(o);
  });
}
var years = [];
for (var y = defaultYear - 2; y <= defaultYear + 1; y++) years.push({value: y, label: y});
var months = [];
for (var i = 0; i < 12; i++) months.push({value: i + 1, label: new Date(2000, i, 1).toLocaleString('en-US', {month: 'long'})});
setOptions(yearSel, years, defaultYear);
setOptions(monthSel, months, defaultMonth);
startDate.value = defaultStart;
endDate.value = defaultEnd;
function fmtNum(v) { return new Intl.NumberFormat('en-US').format(Number(v || 0)); }
function fmtPct(v) { return Number(v || 0).toFixed(1) + '%'; }
function renderBars(el, rows, valueKey, color, isPct) {
  if (!rows || !rows.length) { el.innerHTML = '<div class="meta">No data.</div>'; return; }
  var max = 1;
  rows.forEach(function(r) { max = Math.max(max, Number(r[valueKey] || 0)); });
  var html = '';
  rows.slice(0, 12).forEach(function(r) {
    var val = Number(r[valueKey] || 0);
    var width = Math.max((val / max) * 100, val > 0 ? 3 : 0);
    html += '<div class="barrow"><div class="barlabel" title="' + r.label + '">' + r.label + '</div><div class="bartrack"><div class="barfill" style="width:' + width + '%; background:' + color + ';"></div></div><div class="barvalue">' + (isPct ? fmtPct(val) : fmtNum(val)) + '</div></div>';
  });
  el.innerHTML = html;
}
function renderTrend(el, rows) {
  if (!rows || !rows.length) { el.innerHTML = '<div class="meta">No trend data.</div>'; return; }
  var max = 1;
  rows.forEach(function(r) {
    max = Math.max(max, Number(r.leads_loaded || 0), Number(r.call_attempts || 0), Number(r.interested || 0));
  });
  var html = '';
  rows.slice(-24).forEach(function(r) {
    var leadsH = Math.round((Number(r.leads_loaded || 0) / max) * 160);
    var callsH = Math.round((Number(r.call_attempts || 0) / max) * 160);
    var interestedH = Math.round((Number(r.interested || 0) / max) * 160);
    html += '<div class="trendcol"><div class="stack"><div class="seg leads" style="height:' + leadsH + 'px"></div><div class="seg calls" style="height:' + callsH + 'px"></div><div class="seg interested" style="height:' + interestedH + 'px"></div></div><div class="trendlabel">' + String(r.date || '').slice(5) + '</div></div>';
  });
  el.innerHTML = html;
}
function renderAgentTable(el, rows) {
  var html = '<thead><tr><th>Agent</th><th>Calls</th><th>Distinct Leads</th><th>Interested</th><th>Interested %</th><th>Callbacks</th><th>DNC</th><th>No Answer</th></tr></thead><tbody>';
  if (!rows || !rows.length) {
    html += '<tr><td colspan="8">No rows.</td></tr>';
  } else {
    rows.forEach(function(r) {
      html += '<tr><td>' + r.label + '</td><td>' + fmtNum(r.call_attempts) + '</td><td>' + fmtNum(r.distinct_leads) + '</td><td>' + fmtNum(r.interested) + '</td><td>' + fmtPct(r.interested_rate) + '</td><td>' + fmtNum(r.callback) + '</td><td>' + fmtNum(r.dnc) + '</td><td>' + fmtNum(r.no_answer) + '</td></tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}
function renderListTable(el, rows) {
  var html = '<thead><tr><th>List</th><th>Leads</th><th>Dialed</th><th>Coverage %</th><th>Queued</th><th>Interested</th><th>Interested %</th><th>No Answer</th><th>Not Interested</th></tr></thead><tbody>';
  if (!rows || !rows.length) {
    html += '<tr><td colspan="9">No rows.</td></tr>';
  } else {
    rows.forEach(function(r) {
      html += '<tr><td>' + r.label + '</td><td>' + fmtNum(r.lead_total) + '</td><td>' + fmtNum(r.dialed) + '</td><td>' + fmtPct(r.dial_coverage_rate) + '</td><td>' + fmtNum(r.queued) + '</td><td>' + fmtNum(r.interested) + '</td><td>' + fmtPct(r.interested_rate) + '</td><td>' + fmtNum(r.no_answer) + '</td><td>' + fmtNum(r.not_interested) + '</td></tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}
function query() {
  var params = new URLSearchParams({ format: 'json', year: yearSel.value, month: monthSel.value });
  if (startDate.value && endDate.value) { params.set('start', startDate.value); params.set('end', endDate.value); }
  return params.toString();
}
async function load() {
  var res = await fetch('/api/powerline_dashboard?' + query());
  var data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
  document.getElementById('leadsLoaded').textContent = fmtNum(data.kpis.leads_loaded);
  document.getElementById('queuedLeads').textContent = fmtNum(data.kpis.queued_leads);
  document.getElementById('dialedLeads').textContent = fmtNum(data.kpis.dialed_leads);
  document.getElementById('dialCoverage').textContent = fmtPct(data.kpis.dial_coverage_rate);
  document.getElementById('callAttempts').textContent = fmtNum(data.kpis.call_attempts);
  document.getElementById('distinctCalled').textContent = fmtNum(data.kpis.distinct_leads_called);
  document.getElementById('interestedRate').textContent = fmtPct(data.kpis.interested_rate);
  document.getElementById('callbackDnc').textContent = fmtPct(data.kpis.callback_rate) + ' / ' + fmtPct(data.kpis.dnc_rate);

  var quality = [];
  quality.push(data.window_semantics);
  quality.push('');
  var windowStart = String(data.window_start_local).slice(0, 10);
  var windowEndExclusive = String(data.window_end_local_exclusive).slice(0, 10);
  var parts = windowEndExclusive.split('-').map(function(v) { return parseInt(v, 10); });
  var windowEndDate = new Date(parts[0], parts[1] - 1, parts[2]);
  windowEndDate.setDate(windowEndDate.getDate() - 1);
  var windowEnd = windowEndDate.getFullYear() + '-' + String(windowEndDate.getMonth() + 1).padStart(2, '0') + '-' + String(windowEndDate.getDate()).padStart(2, '0');
  quality.push('Window: ' + windowStart + ' to ' + windowEnd);
  quality.push('Avg attempts per called lead: ' + String(data.kpis.avg_attempts_per_called_lead));
  if (data.data_quality.call_duration_populated) {
    quality.push('Call duration is populated for some rows. Duration-based metrics can be versioned next.');
  } else {
    quality.push('Call duration is currently zero on all calls in-window, so connection/talk-time KPIs are intentionally excluded.');
  }
  if (Number(data.data_quality.lead_source_populated_rate || 0) > 0) {
    quality.push('Lead source populated rate: ' + fmtPct(data.data_quality.lead_source_populated_rate) + '.');
  } else {
    quality.push('Lead source is effectively blank, so source-performance KPIs are excluded.');
  }
  document.getElementById('qualityNote').textContent = quality.join('\\n');

  renderTrend(document.getElementById('trend'), data.tables.trend);
  renderBars(document.getElementById('stageBars'), data.tables.by_stage, 'count', 'var(--pink)', false);
  renderBars(document.getElementById('queueAgeBars'), data.tables.queue_age, 'count', 'var(--amber)', false);
  renderBars(document.getElementById('assignedLeadBars'), data.tables.assigned_agent_leads, 'count', 'var(--slate)', false);
  renderBars(document.getElementById('agentBars'), data.tables.by_agent, 'call_attempts', 'var(--blue)', false);
  renderBars(document.getElementById('listBars'), data.tables.by_list, 'lead_total', 'var(--green)', false);
  renderAgentTable(document.getElementById('agentTable'), data.tables.by_agent);
  renderListTable(document.getElementById('listTable'), data.tables.by_list);
}
document.getElementById('apply').addEventListener('click', function() { load().catch(renderError); });
document.getElementById('clearRange').addEventListener('click', function() { startDate.value = defaultStart; endDate.value = defaultEnd; load().catch(renderError); });
function renderError(err) {
  var msg = err && err.message ? err.message : String(err || 'Unknown error');
  document.getElementById('qualityNote').textContent = msg;
}
load().catch(renderError);
</script>
</body>
</html>
"""
    return (
        html.replace("__YEAR__", str(year))
        .replace("__MONTH__", str(month))
        .replace("__DEFAULT_START__", default_start)
        .replace("__DEFAULT_END__", default_end)
        .replace("__DASHBOARD_NAV_CSS__", nav_css)
        .replace("__DASHBOARD_NAV_HTML__", nav_html)
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            start_local, end_local_excl, start_q, end_q, year, month = resolve_window(qs)

            if (qs.get("format", ["html"])[0] or "html").lower() == "json":
                payload = build_payload(start_local, end_local_excl)
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_html(year, month, start_q, end_q).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=300, stale-while-revalidate=1800")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
