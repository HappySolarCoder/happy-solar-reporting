# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (creds_json and project_id and database_id):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def to_iso_utc(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str) and dt.strip():
        return dt.strip()
    return None


def contact_doc(db: firestore.Client, contact_id: str, cache: dict[str, dict]) -> dict:
    if not contact_id:
        return {}
    if contact_id in cache:
        return cache[contact_id]
    snaps = list(db.collection("ghl_contacts_v2").where("id", "==", contact_id).limit(1).stream())
    d = snaps[0].to_dict() if snaps else {}
    cache[contact_id] = d or {}
    return cache[contact_id]


def setter_from_contact(c: dict) -> str:
    for cf in (c.get("customFields") or []):
        if isinstance(cf, dict) and str(cf.get("id") or "") == "Eq4NLTSkJ56KTxbxypuE":
            return str(cf.get("value") or "")
    return ""


def custom_datetime_candidates(opportunity: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for cf in (opportunity.get("customFields") or []):
        if not isinstance(cf, dict):
            continue
        cid = str(cf.get("id") or "")
        val = cf.get("value") if "value" in cf else cf.get("fieldValueString")
        sval = str(val or "")
        if not sval:
            continue
        if re.search(r"\d{4}-\d{2}-\d{2}", sval) or re.search(r"time|date|appoint|sched", cid, re.I):
            out.append({"id": cid, "value": sval})
    return out[:10]


def related_event_hits(db: firestore.Client, opp_id: str, contact_id: str) -> dict[str, Any]:
    cols = [
        "ghl_calendar_events_v2",
        "ghl_appointments_v2",
        "ghl_events_v2",
        "ghl_calendar_events",
        "ghl_appointments",
        "ghl_tasks_v2",
        "ghl_notes_v2",
    ]
    hits: dict[str, Any] = {}

    def pick_datetime_fields(doc: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in doc.items():
            lk = str(k).lower()
            if any(t in lk for t in ["date", "time", "start", "end", "sched", "appoint", "occurred"]):
                out[k] = to_iso_utc(v) if isinstance(v, datetime) else v
        return out

    for col in cols:
        try:
            docs = []
            if contact_id:
                docs = list(db.collection(col).where("contactId", "==", contact_id).limit(3).stream())
            if (not docs) and opp_id:
                docs = list(db.collection(col).where("opportunityId", "==", opp_id).limit(3).stream())
            if docs:
                rows = []
                for d in docs:
                    x = d.to_dict() or {}
                    rows.append({
                        "id": str(x.get("id") or d.id),
                        "status": str(x.get("status") or ""),
                        "calendarId": str(x.get("calendarId") or ""),
                        "datetimeFields": pick_datetime_fields(x),
                    })
                hits[col] = rows
        except Exception as e:
            hits[col] = [{"error": str(e)}]
    return hits


def esc(x: Any) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            want_json = (qs.get("format", [""])[0] or "").lower() == "json"
            year = int((qs.get("year", [str(datetime.utcnow().year)])[0] or datetime.utcnow().year))
            month = int((qs.get("month", [str(datetime.utcnow().month)])[0] or datetime.utcnow().month))
            setter = (qs.get("setter_last_name", [""])[0] or "").strip() or None
            limit = int((qs.get("limit", ["500"])[0] or "500"))
            include_all = (qs.get("all", [""])[0] or "").lower() in {"1", "true", "yes", "all"}
            include_events = (qs.get("events", [""])[0] or "").lower() in {"1", "true", "yes", "all"}

            db = get_db()
            rows = []
            ccache: dict[str, dict] = {}
            for snap in db.collection("ghl_opportunities_v2").stream():
                o = snap.to_dict() or {}
                created = to_iso_utc(o.get("createdAt"))
                if not created or created[:7] != f"{year}-{str(month).zfill(2)}":
                    continue
                cid = str(o.get("contactId") or "")
                c = contact_doc(db, cid, ccache)
                last = str(c.get("lastName") or "")
                setter_contact = setter_from_contact(c)
                if setter and setter_contact.lower() != setter.lower():
                    continue
                opp_id = str(o.get("id") or snap.id)
                rows.append({
                    "opportunityId": opp_id,
                    "contactId": cid,
                    "contactLastName": last,
                    "setterLastName_contact": setter_contact,
                    "createdAt": created,
                    "appointmentDateTime": to_iso_utc(o.get("appointmentDateTime")),
                    "appointmentOccurredAt": to_iso_utc(o.get("appointmentOccurredAt")),
                    "startTime": to_iso_utc(o.get("startTime")),
                    "appointmentTime": to_iso_utc(o.get("appointmentTime")),
                    "scheduledAt": to_iso_utc(o.get("scheduledAt")),
                    "scheduledFor": to_iso_utc(o.get("scheduledFor")),
                    "customDateCandidates": custom_datetime_candidates(o),
                    "relatedEventHits": related_event_hits(db, opp_id, cid) if include_events else {},
                })
                if (not include_all) and len(rows) >= max(1, min(limit, 5000)):
                    break

            payload = {
                "metric": "QA — Appointment Datetime Audit",
                "query": {"year": year, "month": month, "setter_last_name": setter, "limit": limit, "all": include_all, "events": include_events},
                "count": len(rows),
                "rows": rows,
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }

            if want_json:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
                self.end_headers()
                self.wfile.write(body)
                return

            table = "".join(
                "<tr>"
                f"<td><code>{esc(r['opportunityId'])}</code></td>"
                f"<td>{esc(r['contactLastName'])}</td>"
                f"<td>{esc(r['setterLastName_contact'])}</td>"
                f"<td>{esc(r['appointmentDateTime'])}</td>"
                f"<td>{esc(r['startTime'])}</td>"
                f"<td>{esc(r['scheduledAt'])}</td>"
                f"<td>{esc(r['appointmentOccurredAt'])}</td>"
                "</tr>"
                for r in rows
            ) or '<tr><td colspan="7">No rows</td></tr>'

            html = f"""<!doctype html><html><head><meta charset='utf-8'><title>QA Appointment Datetime Audit</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0b1220;color:#e5edf8;margin:0}}.wrap{{padding:16px}}.card{{background:#111b2e;border:1px solid #22324f;border-radius:12px;padding:14px;margin-top:10px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #263754;padding:8px;text-align:left;font-size:12px}}th{{color:#9bb0d1}}</style></head>
<body><div class='wrap'><h2 style='margin:0 0 8px 0'>QA — Appointment Datetime Audit</h2>
<div style='color:#9bb0d1'>Rows: {len(rows)} | year={year} month={month} setter={esc(setter or 'all')}</div>
<div class='card'><table><thead><tr><th>Opportunity ID</th><th>Contact Last Name</th><th>Setter(contact)</th><th>appointmentDateTime</th><th>startTime</th><th>scheduledAt</th><th>appointmentOccurredAt</th></tr></thead><tbody>{table}</tbody></table></div>
</div></body></html>"""
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            body = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
