# -*- coding: utf-8 -*-

"""Vercel Python function: /api/metrics/diamond_sweeper

Tyler Diamond sweeper/rehash performance. Reads only.

Appointments created, appointments ran, and demos use the same populations
as Company Overview Sweeper/Rehash (channel_goals), filtered to contacts
whose Sweeper/Rehash Last Name equals Diamond. Sales use the locked sales
grain with that same name filter (sweeper_credit).

Demo % and Opp2Prelim use appointments ran as the denominator, matching
Company Overview and the channel goals table:

- Demo % = demos / appointments ran
- Opp2Prelim = sales / appointments ran

Both rates are blank when ran is 0.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

METRICS_DIR = Path(__file__).resolve().parent
if str(METRICS_DIR) not in sys.path:
    sys.path.insert(0, str(METRICS_DIR))

from sweeper_credit import appointment_rows, same_name
from sweeper_rehash_attribution import SWEEPER_REHASH_LAST_NAME_FIELD_ID, sweeper_rehash_last_name

NY = ZoneInfo("America/New_York")
DIAMOND_LAST_NAME = "Diamond"
TITLE = "Diamond — Sweeper/Rehash"


def month_to_date(now: datetime | None = None) -> tuple[str, str]:
    """America/New_York month-to-date, inclusive calendar dates."""
    clock = now or datetime.now(NY)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=NY)
    else:
        clock = clock.astimezone(NY)
    return clock.date().replace(day=1).isoformat(), clock.date().isoformat()


def resolve_window(qs: dict[str, list[str]], now: datetime | None = None) -> tuple[int, int, str | None, str | None]:
    """start/end wins. year/month is a full calendar month. Otherwise month-to-date."""
    start = (qs.get("start") or [""])[0].strip()
    end = (qs.get("end") or [""])[0].strip()
    year_raw = (qs.get("year") or [""])[0].strip()
    month_raw = (qs.get("month") or [""])[0].strip()
    if start or end:
        if not (start and end):
            raise ValueError("start and end are both required (YYYY-MM-DD)")
        from opportunities_created import parse_date_ymd

        sp = parse_date_ymd(start)
        ep = parse_date_ymd(end)
        if not (sp and ep):
            raise ValueError("Invalid start/end date; expected YYYY-MM-DD")
        if sp > ep:
            raise ValueError("start must be on or before end")
        return sp[0], sp[1], start, end
    if year_raw or month_raw:
        try:
            year = int(year_raw)
            month = int(month_raw)
        except ValueError as exc:
            raise ValueError("valid year and month are required") from exc
        if not (1 <= month <= 12 and 2020 <= year <= 2100):
            raise ValueError("valid year and month are required")
        return year, month, None, None
    start_ymd, end_ymd = month_to_date(now)
    year, month, _day = (int(part) for part in start_ymd.split("-"))
    return year, month, start_ymd, end_ymd


def share_percent(numerator: int, denominator: int) -> float | None:
    """Blank when the denominator is 0. Same rule as Company Overview rates."""
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def compact_stage(value: Any) -> str:
    return " ".join(str(value or "").split())


def pipeline_stage_name(record: dict | None, stage_names: dict[str, str] | None = None) -> str:
    """GHL pipeline stage name. Sit / No Sit is a separate demo-rate flag.

    Prefer a name already on the row, then the pipeline stage directory,
    then pipelineStageName / stageName copied from the opportunity.
    """
    if not isinstance(record, dict):
        return ""
    names = stage_names or {}
    stage_id = compact_stage(record.get("pipelineStageId") or record.get("pipelineStageUId"))
    for candidate in (
        record.get("pipelineStage"),
        names.get(stage_id) if stage_id else None,
        record.get("pipelineStageName"),
        record.get("stageName"),
    ):
        text = compact_stage(candidate)
        if text:
            return text
    return ""


def created_rows(created_payload: dict[str, Any], last_name: str = DIAMOND_LAST_NAME) -> list[dict[str, Any]]:
    """Distinct opportunities_created rows for this Sweeper/Rehash Last Name."""
    rows = appointment_rows(created_payload, last_name)
    for row in rows:
        row["pipelineStage"] = pipeline_stage_name(row)
    return rows


def demo_rows(demo_payload: dict[str, Any], last_name: str = DIAMOND_LAST_NAME) -> list[dict[str, Any]]:
    """Distinct demo_rate rows whose Sweeper/Rehash Last Name matches.

    Same population as channel_goals.sweeper_ran, limited to one last name.
    demo_rate already keeps one outcome per opportunity (a follow-up is not
    a second demo).
    """
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in demo_payload.get("rows") or []:
        if not isinstance(row, dict) or not same_name(row.get("sweeperRehashLastName"), last_name):
            continue
        opp_id = str(row.get("opportunityId") or "")
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        rows.append(
            {
                "opportunityId": opp_id,
                "pipeline": row.get("pipeline"),
                "pipelineId": row.get("pipelineId"),
                "pipelineStageId": row.get("pipelineStageId"),
                "pipelineStageName": row.get("pipelineStageName"),
                "pipelineStage": pipeline_stage_name(row),
                "disposition": row.get("disposition"),
                "occurredAt": row.get("frozenAppointmentOccurredAt"),
                "setter": row.get("setter"),
            }
        )
    return rows


def fill_pipeline_stages(db, rows: list[dict[str, Any]]) -> None:
    """Fill a blank pipeline stage from ghl_pipelines_v2.stages when the id is known.

    Uses sold_date_gaps.load_pipelines_by_ids. A lookup failure leaves the
    name blank and does not change demo-rate counts.
    """
    pending = [
        row
        for row in rows
        if isinstance(row, dict)
        and not pipeline_stage_name(row)
        and compact_stage(row.get("pipelineStageId"))
        and compact_stage(row.get("pipelineId"))
    ]
    if not pending:
        return
    try:
        from sold_date_gaps import load_pipelines_by_ids

        _pipeline_names, stage_names = load_pipelines_by_ids(
            db, [row.get("pipelineId") for row in pending]
        )
    except Exception:
        return
    if not isinstance(stage_names, dict):
        return
    for row in pending:
        name = pipeline_stage_name(row, stage_names)
        if name:
            row["pipelineStage"] = name


def ran_and_demos(demo_payload: dict[str, Any], last_name: str = DIAMOND_LAST_NAME) -> tuple[int, int]:
    rows = demo_rows(demo_payload, last_name)
    demos = sum(1 for row in rows if row.get("disposition") == "Sit")
    return len(rows), demos


def name_matches(contact: dict | None, opp: dict | None, last_name: str = DIAMOND_LAST_NAME) -> bool:
    return same_name(sweeper_rehash_last_name(contact, opp), last_name)


def summarize(*, opps_created: int, ran: int, demos: int, sales: int) -> dict[str, Any]:
    return {
        "opps_created": opps_created,
        "ran": ran,
        "demos": demos,
        "sales": sales,
        "demo_pct": share_percent(demos, ran),
        "opp2prelim": share_percent(sales, ran),
    }


def compute_diamond_sweeper(
    db,
    *,
    year: int,
    month: int,
    start: str | None = None,
    end: str | None = None,
    last_name: str = DIAMOND_LAST_NAME,
) -> dict[str, Any]:
    import demo_rate
    from opportunities_created import MetricContract, compute
    from sales import SalesMetricContract, compute_sales

    sales_rows: dict[str, dict[str, Any]] = {}

    def on_sale(*, opp, contact, contact_id, sold_date, salesperson):
        if not name_matches(contact, opp, last_name):
            return
        key = str(contact_id or "")
        if not key or key in sales_rows:
            return
        sales_rows[key] = {
            "contactId": key,
            "opportunityId": (opp or {}).get("id"),
            "soldDate": sold_date,
        }

    with ThreadPoolExecutor(max_workers=3) as pool:
        created_job = pool.submit(
            compute,
            db,
            MetricContract(),
            year=year,
            month=month,
            start=start,
            end=end,
            pipeline_scope="all",
        )
        demo_job = pool.submit(demo_rate.build_payload, db, year, month, {}, start, end)
        sales_job = pool.submit(
            compute_sales,
            db,
            SalesMetricContract(),
            year=year,
            month=month,
            tz="America/New_York",
            start=start,
            end=end,
            on_sale=on_sale,
        )
        created = created_job.result()
        demo_payload = demo_job.result()
        sales_payload = sales_job.result()

    appointments = created_rows(created, last_name)
    outcomes = demo_rows(demo_payload, last_name)
    fill_pipeline_stages(db, appointments + outcomes)
    ran = len(outcomes)
    demos = sum(1 for row in outcomes if row.get("disposition") == "Sit")
    metrics = summarize(
        opps_created=len(appointments),
        ran=ran,
        demos=demos,
        sales=len(sales_rows),
    )
    return {
        "metric": "diamond_sweeper",
        "title": TITLE,
        "last_name": last_name,
        "timezone": "America/New_York",
        "year": year,
        "month": month,
        "start": start,
        "end": end,
        "window_start_local": created.get("window_start_local") or sales_payload.get("window_start_local"),
        "window_end_local": created.get("window_end_local") or sales_payload.get("window_end_local"),
        **metrics,
        "created_rows": appointments,
        "demo_rows": outcomes,
        "sale_rows": sorted(sales_rows.values(), key=lambda row: str(row.get("soldDate") or "")),
        "contract": {
            "field": (
                f"ghl_contacts_v2.customFields[{SWEEPER_REHASH_LAST_NAME_FIELD_ID}] "
                "then the same id on the opportunity"
            ),
            "opps_created": (
                "COUNT_DISTINCT opportunity id from opportunities_created pipeline_scope=all "
                "whose Sweeper/Rehash Last Name equals Diamond (case-insensitive)"
            ),
            "ran": "demo_rate rows in the window with that name, distinct opportunity id",
            "demos": "those ran rows whose disposition is Sit",
            "pipeline_stage": (
                "ghl_opportunities_v2.pipelineStageId -> ghl_pipelines_v2.stages[].name, "
                "or pipelineStageName / stageName already on the opportunity. "
                "Displayed beside Sit / No Sit. It does not change demo rate or Opp2Prelim."
            ),
            "demo_pct": "demos / appointments ran (Company Overview Sweeper/Rehash). Blank when ran is 0",
            "opp2prelim": "locked sales grain filtered to this name / appointments ran. Blank when ran is 0",
            "sales": "Locked Sales grain (sales.py), distinct contact, filtered by the field",
            "fma_demo_rule": (
                "demo_rate keeps one outcome per opportunity, so a follow-up is not a second demo. "
                "Diamond is credited when Sweeper/Rehash Last Name is Diamond and the appointment is a demo. "
                "Setter last name alone does not credit Diamond."
            ),
            "deleted_opps": (
                "Counts come from ghl_opportunities_v2, the same collections as Sweeper/Rehash channel "
                "goals. Deleted opportunities are not in that collection. The Ads Dashboard 10-minute "
                "deleted-opportunity rule belongs to that lead set and is not applied here."
            ),
            "collections": ["ghl_opportunities_v2", "ghl_contacts_v2", "ghl_pipelines_v2"],
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            year, month, start, end = resolve_window(qs)
            from sales import get_db

            payload = compute_diamond_sweeper(get_db(), year=year, month=month, start=start, end=end)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=3600")
            self.end_headers()
            self.wfile.write(body)
        except ValueError as exc:
            self._err(400, "ERROR: " + str(exc))
        except Exception:
            self._err(500, "ERROR: diamond sweeper unavailable")

    def _err(self, code: int, text: str):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
