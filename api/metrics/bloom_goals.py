# -*- coding: utf-8 -*-

"""Read Bloom company and territory sales goals.

happy-solar-bloom-portal stores those goals in portal_goal_documents
(scope:company and scope:territory:*). lib/account-goals.ts reads them
with DATABASE_URL. This route uses that same env var (POSTGRES_URL is
the fallback). Person goals are a second select of the company, team,
and user documents. It does not read portal_users.

Account goals are sales counts. The company sales goal for a month is the
scope:company accountGoals row (metricKey sales, unit count, periodId
YYYY-MM). It is not the sum of territory goals. A missing scope:company
row, and missing Demo % / Opp2Prelim / opportunities-created targets, stay
unset. Virtual/Sweeper uses the portal's locked default of 7 when that month has no
stored goal (mergeLockedTerritoryGoals). Person goals are the company,
team, and user documents (door knocks, appointments, demos, sales).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
COMPANY_SUBJECT = "scope:company"
TERRITORY_PREFIX = "scope:territory:"
VIRTUAL_SWEEPER = "Virtual/Sweeper"
VIRTUAL_SWEEPER_SALES_GOAL = 7
BLOOM_TERRITORIES = ("Buffalo", "Rochester", "Syracuse", "Other", "Virtual/Sweeper")
OPS_NAME = {
    "Buffalo": "Buffalo",
    "Rochester": "Rochester",
    "Syracuse": "Syracuse",
    "Other": "Other",
    "Virtual/Sweeper": "Virtual",
}
SCOPE_SQL = (
    "SELECT subject_id, document FROM portal_goal_documents "
    "WHERE subject_id = 'scope:company' OR subject_id LIKE 'scope:territory:%'"
)
PERSON_SQL = (
    "SELECT subject_id, document FROM portal_goal_documents "
    "WHERE subject_id = 'company' OR subject_id LIKE 'team:%' OR subject_id LIKE 'user:%'"
)
PERSON_SETTINGS_METRIC = {
    "door-knocks": "doors_goal",
    "appointments-set": "appts_goal",
    "demos": "demos_goal",
    "sales": "sales_goal",
    "self-gen-opps": "self_gen_opps_goal",
}
UNSET = {
    "company_sales": "No scope:company sales goal is stored for this month.",
    "opportunities_created": (
        "Bloom account goals store sales counts only. "
        "No opportunities-created target is in portal_goal_documents."
    ),
    "demo_pct": "No company Demo % target is stored in portal_goal_documents.",
    "opp2prelim": "No company Opp2Prelim target is stored in portal_goal_documents.",
}


def period_from_parts(period: str = "", year: str = "", month: str = "", start: str = "", now: datetime | None = None) -> str:
    period = (period or "").strip()
    if PERIOD_RE.match(period):
        return period
    if (year or "").isdigit() and (month or "").isdigit():
        month_n = int(month)
        if 1 <= month_n <= 12:
            return f"{int(year):04d}-{month_n:02d}"
    start = (start or "").strip()
    if PERIOD_RE.match(start[:7]):
        return start[:7]
    clock = now or datetime.now(ZoneInfo("America/New_York"))
    return f"{clock.year:04d}-{clock.month:02d}"


def _finite_target(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value <= 0 or value > 1_000_000:
        return None
    return float(value)


def parse_account_goals(subject_id: str, raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, dict):
        return []
    goals = []
    for item in raw.get("accountGoals") or []:
        if not isinstance(item, dict):
            continue
        if item.get("metricKey") != "sales" or item.get("unit") != "count":
            continue
        target = _finite_target(item.get("target"))
        period_id = item.get("periodId")
        if target is None or not isinstance(period_id, str) or not PERIOD_RE.match(period_id):
            continue
        if float(target).is_integer():
            target = int(target)
        scope = item.get("scope")
        territory = item.get("territory")
        if subject_id == COMPANY_SUBJECT:
            if scope not in (None, "company"):
                continue
            territory_name = None
            scope_name = "company"
        elif subject_id.startswith(TERRITORY_PREFIX):
            territory_name = subject_id[len(TERRITORY_PREFIX) :]
            if territory not in (None, territory_name):
                continue
            if territory_name not in BLOOM_TERRITORIES:
                continue
            scope_name = "territory"
        else:
            continue
        goals.append(
            {
                "scope": scope_name,
                "territory": territory_name,
                "period_id": period_id,
                "target": target,
                "unit": "count",
                "metric": "sales",
                "stored": True,
                "locked_default": False,
            }
        )
    return goals


def parse_person_goals(documents: list[tuple[str, Any]], period_id: str) -> list[dict[str, Any]]:
    """Monthly person goals copied onto company, team, and user documents.

    The portal writes the same goal to the assignee document and, for a
    production person, the company document. The newest version wins.
    """
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for subject_id, raw in documents:
        subject = str(subject_id or "")
        if subject != "company" and not subject.startswith(("team:", "user:")):
            continue
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if not isinstance(raw, dict):
            continue
        for item in raw.get("goals") or []:
            if not isinstance(item, dict):
                continue
            if item.get("periodId") != period_id:
                continue
            metric = item.get("metricKey")
            assignee = item.get("assigneeUserId")
            if not isinstance(metric, str) or not isinstance(assignee, str) or not assignee:
                continue
            target = _finite_target(item.get("target"))
            if target is None:
                continue
            if float(target).is_integer():
                target = int(target)
            version = item.get("version")
            version_n = int(version) if isinstance(version, int) and version > 0 else 1
            row = {
                "assignee_user_id": assignee,
                "name": item.get("assigneeNameSnapshot") if isinstance(item.get("assigneeNameSnapshot"), str) else "",
                "role": item.get("role") if item.get("role") in {"fma", "closer", "manager"} else "",
                "metric": metric,
                "settings_metric": PERSON_SETTINGS_METRIC.get(metric),
                "target": target,
                "period_id": period_id,
                "version": version_n,
            }
            key = (assignee, metric)
            current = chosen.get(key)
            if current is None or version_n >= int(current.get("version") or 0):
                chosen[key] = row
    rows = list(chosen.values())
    rows.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("metric") or "")))
    for row in rows:
        row.pop("version", None)
    return rows


def rows_from_neon(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows") or []
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [row for row in rows if isinstance(row, dict)]
    names = [field.get("name") for field in payload.get("fields") or [] if isinstance(field, dict)]
    out = []
    for row in rows:
        if isinstance(row, list):
            out.append({name: row[index] if index < len(row) else None for index, name in enumerate(names)})
    return out


def _goal_row(territory: str, period_id: str, target: float | None, *, stored: bool, locked_default: bool) -> dict[str, Any]:
    return {
        "territory": territory,
        "ops_territory": OPS_NAME.get(territory, territory),
        "period_id": period_id,
        "target": target,
        "unit": "count",
        "metric": "sales",
        "stored": stored,
        "locked_default": locked_default,
    }


def build_payload(period_id: str, documents: list[tuple[str, Any]]) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for subject_id, raw in documents:
        parsed.extend(parse_account_goals(str(subject_id), raw))
    company = next((goal for goal in parsed if goal["scope"] == "company" and goal["period_id"] == period_id), None)
    by_territory = {
        goal["territory"]: goal
        for goal in parsed
        if goal["scope"] == "territory" and goal["period_id"] == period_id and goal.get("territory")
    }
    territories = []
    for name in BLOOM_TERRITORIES:
        found = by_territory.get(name)
        if found:
            stored_target = found["target"]
            if isinstance(stored_target, float) and stored_target.is_integer():
                stored_target = int(stored_target)
            territories.append(
                _goal_row(name, period_id, stored_target, stored=True, locked_default=False)
            )
            continue
        if name == VIRTUAL_SWEEPER:
            territories.append(
                _goal_row(
                    name,
                    period_id,
                    float(VIRTUAL_SWEEPER_SALES_GOAL),
                    stored=False,
                    locked_default=True,
                )
            )
            continue
        territories.append(_goal_row(name, period_id, None, stored=False, locked_default=False))
    return {
        "available": True,
        "source": "portal_goal_documents",
        "period_id": period_id,
        "company_sales": None
        if company is None
        else {
            "target": company["target"],
            "period_id": period_id,
            "unit": "count",
            "metric": "sales",
            "stored": True,
        },
        "territory_sales": territories,
        "opportunities_created": None,
        "demo_pct": None,
        "opp2prelim": None,
        "unset": dict(UNSET),
        "blocker": None,
    }


def database_url() -> str:
    return (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()


class _RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("neon_redirect")


def _neon_documents(url: str, query: str, opener=None) -> list[tuple[str, Any]]:
    host = urlparse(url).hostname
    if not host:
        raise RuntimeError("database_url_host")
    request = Request(
        f"https://{host}/sql",
        data=json.dumps({"query": query, "params": []}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Neon-Connection-String": url},
        method="POST",
    )
    open_fn = opener or build_opener(_RefuseRedirect).open
    with open_fn(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    documents = []
    for row in rows_from_neon(payload):
        documents.append((str(row.get("subject_id") or ""), row.get("document")))
    return documents


def fetch_scope_documents(url: str, opener=None) -> list[tuple[str, Any]]:
    documents = []
    for subject_id, raw in _neon_documents(url, SCOPE_SQL, opener=opener):
        if subject_id == COMPANY_SUBJECT or subject_id.startswith(TERRITORY_PREFIX):
            documents.append((subject_id, raw))
    return documents


def fetch_person_documents(url: str, opener=None) -> list[tuple[str, Any]]:
    documents = []
    for subject_id, raw in _neon_documents(url, PERSON_SQL, opener=opener):
        if subject_id == "company" or subject_id.startswith(("team:", "user:")):
            documents.append((subject_id, raw))
    return documents


def read_bloom_goals(period_id: str, opener=None) -> dict[str, Any]:
    url = database_url()
    checked_at = datetime.now(ZoneInfo("America/New_York")).isoformat()
    if not url:
        return {
            "available": False,
            "goals": None,
            "source": None,
            "period_id": period_id,
            "blocker": (
                "Bloom sales goals are in portal_goal_documents on the Bloom Neon database. "
                "This app reads them with DATABASE_URL, the same variable happy-solar-bloom-portal uses. "
                "DATABASE_URL is not set here."
            ),
            "person_goals": [],
            "checked_at": checked_at,
        }
    try:
        documents = fetch_scope_documents(url, opener=opener)
        payload = build_payload(period_id, documents)
        try:
            payload["person_goals"] = parse_person_goals(fetch_person_documents(url, opener=opener), period_id)
        except Exception:
            payload["person_goals"] = []
    except Exception as exc:
        return {
            "available": False,
            "goals": None,
            "source": "portal_goal_documents",
            "period_id": period_id,
            "blocker": "Bloom sales goals could not be read from portal_goal_documents (" + type(exc).__name__ + ").",
            "person_goals": [],
            "checked_at": checked_at,
        }
    payload["checked_at"] = checked_at
    return payload


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import parse_qs, urlparse as parse_url

        qs = parse_qs(parse_url(self.path).query)
        period_id = period_from_parts(
            (qs.get("period") or [""])[0],
            (qs.get("year") or [""])[0],
            (qs.get("month") or [""])[0],
            (qs.get("start") or [""])[0],
        )
        body = json.dumps(read_bloom_goals(period_id)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
