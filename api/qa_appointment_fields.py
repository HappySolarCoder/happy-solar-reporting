# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from google.cloud import firestore
from google.oauth2 import service_account


def get_db() -> firestore.Client:
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project = os.environ.get("GCP_PROJECT_ID")
    dbid = os.environ.get("FIRESTORE_DATABASE_ID")
    if not (raw and project and dbid):
        missing = [k for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID") if not os.environ.get(k)]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    creds = service_account.Credentials.from_service_account_info(json.loads(raw))
    return firestore.Client(project=project, database=dbid, credentials=creds)


def iso(v: Any) -> str | None:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def esc(x: Any) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            year = int((qs.get("year", [str(datetime.utcnow().year)])[0] or datetime.utcnow().year))
            month = int((qs.get("month", [str(datetime.utcnow().month)])[0] or datetime.utcnow().month))
            limit = int((qs.get("limit", ["10"])[0] or "10"))
            want_json = (qs.get("format", [""])[0] or "").lower() == "json"

            db = get_db()
            rows = []
            contact_cache: dict[str, str] = {}

            for snap in db.collection("ghl_opportunities_v2").stream():
                o = snap.to_dict() or {}
                created = iso(o.get("createdAt"))
                if not created or created[:7] != f"{year}-{str(month).zfill(2)}":
                    continue

                cid = str(o.get("contactId") or "")
                if cid in contact_cache:
                    last = contact_cache[cid]
                else:
                    cdocs = list(db.collection("ghl_contacts_v2").where("id", "==", cid).limit(1).stream()) if cid else []
                    c = cdocs[0].to_dict() if cdocs else {}
                    last = str((c or {}).get("lastName") or "")
                    contact_cache[cid] = last

                rows.append({
                    "opportunityId": str(o.get("id") or snap.id),
                    "contactLastName": last,
                    "createdAt": created,
                    "appointmentDateTime": iso(o.get("appointmentDateTime")),
                    "startTime": iso(o.get("startTime")),
                    "appointmentTime": iso(o.get("appointmentTime")),
                    "scheduledAt": iso(o.get("scheduledAt")),
                    "scheduledFor": iso(o.get("scheduledFor")),
                    "appointmentOccurredAt": iso(o.get("appointmentOccurredAt")),
                })
                if len(rows) >= max(1, min(limit, 100)):
                    break

            payload = {
                "metric": "QA Appointment Field Candidates",
                "query": {"year": year, "month": month, "limit": limit},
                "count": len(rows),
                "rows": rows,
            }

            if want_json:
                b = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
                self.end_headers()
                self.wfile.write(b)
                return

            trs = "".join(
                "<tr>"
                f"<td><code>{esc(r['opportunityId'])}</code></td>"
                f"<td>{esc(r['contactLastName'])}</td>"
                f"<td>{esc(r['appointmentDateTime'])}</td>"
                f"<td>{esc(r['startTime'])}</td>"
                f"<td>{esc(r['appointmentTime'])}</td>"
                f"<td>{esc(r['scheduledAt'])}</td>"
                f"<td>{esc(r['scheduledFor'])}</td>"
                f"<td>{esc(r['appointmentOccurredAt'])}</td>"
                "</tr>"
                for r in rows
            ) or '<tr><td colspan="8">No rows</td></tr>'

            html = f"""<!doctype html><html><head><meta charset='utf-8'><title>QA Appointment Fields</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0b1220;color:#e5edf8;margin:0}}.wrap{{padding:16px}}.card{{background:#111b2e;border:1px solid #22324f;border-radius:12px;padding:14px;margin-top:10px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #263754;padding:8px;text-align:left;font-size:12px}}th{{color:#9bb0d1}}</style></head>
<body><div class='wrap'><h2 style='margin:0 0 8px 0'>QA — Appointment Datetime Candidate Fields</h2>
<div style='color:#9bb0d1'>Rows: {len(rows)} | year={year} month={month}</div>
<div class='card'><table><thead><tr><th>Opportunity ID</th><th>Contact Last Name</th><th>appointmentDateTime</th><th>startTime</th><th>appointmentTime</th><th>scheduledAt</th><th>scheduledFor</th><th>appointmentOccurredAt</th></tr></thead><tbody>{trs}</tbody></table></div>
</div></body></html>"""
            b = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "public, s-maxage=60, stale-while-revalidate=120")
            self.end_headers()
            self.wfile.write(b)
        except Exception as e:
            b = ("ERROR: " + str(e)).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b)
