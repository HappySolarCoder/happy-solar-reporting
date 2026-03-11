# -*- coding: utf-8 -*-

"""Vercel Python function: /api/settings_api

JSON API backing /api/settings.

Actions:
- bootstrap: returns raydar_users, ghl_users, roster_people, goals_for_month
- upsert_roster: create/update roster_people_v1/<person_key>
- upsert_goal: write goals_monthly_v1/<month> (sub-map by person_key + metric)

Firestore (happy-solar):
- roster_people_v1
- goals_monthly_v1

Notes
- No auth in v1.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any

from google.cloud import firestore
from google.oauth2 import service_account


def get_db() -> firestore.Client:
    creds_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    project_id = os.environ.get("GCP_PROJECT_ID")
    database_id = os.environ.get("FIRESTORE_DATABASE_ID")

    if not (creds_json and project_id and database_id):
        missing = [
            k
            for k in ("FIREBASE_SERVICE_ACCOUNT_JSON", "GCP_PROJECT_ID", "FIRESTORE_DATABASE_ID")
            if not os.environ.get(k)
        ]
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(project=project_id, database=database_id, credentials=creds)


def read_json(req: BaseHTTPRequestHandler) -> dict:
    n = int(req.headers.get("Content-Length", "0") or "0")
    raw = req.rfile.read(n) if n else b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def write_json(req: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload, default=str).encode("utf-8")
    req.send_response(status)
    req.send_header("Content-Type", "application/json; charset=utf-8")
    req.send_header("Cache-Control", "no-store")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def list_raydar_users(db: firestore.Client) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for snap in db.collection("raydar_users_v1").stream():
        d = snap.to_dict() or {}
        out.append(
            {
                "value": str(snap.id),
                "label": str(d.get("name") or snap.id),
            }
        )
    out.sort(key=lambda x: x["label"].lower())
    return out


def list_ghl_users(db: firestore.Client) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for snap in db.collection("ghl_users_v2").stream():
        d = snap.to_dict() or {}
        uid = str(d.get("id") or snap.id)
        nm = str(d.get("name") or uid)
        out.append({"value": uid, "label": nm})
    out.sort(key=lambda x: x["label"].lower())
    return out


def list_ghl_setter_last_names(db: firestore.Client) -> list[dict[str, str]]:
    """Return distinct GHL setter last names observed on ran opps (last ~180 days).

    This drives a dropdown so users do not have to type the setter last name manually.
    """

    # Lookback window (avoid full contact scan)
    since = datetime.now(timezone.utc) - timedelta(days=180)

    # Use the same base filters as demo_rate/opps_ran:
    included = {"buffalo", "rochester", "virtual", "syracuse"}
    excluded = {"rehash", "sweeper", "inbound/lead locker"}

    # Pipeline name lookup
    pipe = {}
    for snap in db.collection('ghl_pipelines_v2').stream():
        d = snap.to_dict() or {}
        pid = str(d.get('id') or snap.id)
        nm = str(d.get('name') or '').strip()
        if pid and nm:
            pipe[pid] = nm

    # Helper: contact lookup (doc id fallback by id field)
    def contact_lookup(contact_id: str) -> dict | None:
        if not contact_id:
            return None
        snap = db.collection('ghl_contacts_v2').document(str(contact_id)).get()
        if snap.exists:
            return snap.to_dict() or {}
        q = db.collection('ghl_contacts_v2').where('id','==',str(contact_id)).limit(1)
        docs = list(q.stream())
        return (docs[0].to_dict() or {}) if docs else None

    def contact_custom_field(contact: dict | None, cf_id: str):
        if not isinstance(contact, dict):
            return None
        for cf in (contact.get('customFields') or []):
            if isinstance(cf, dict) and cf.get('id') == cf_id:
                return cf.get('value')
        return None

    setter_cf = 'Eq4NLTSkJ56KTxbxypuE'

    q = (
        db.collection('ghl_opportunities_v2')
          .where('appointmentOccurredAt','>=', since)
          .order_by('appointmentOccurredAt')
    )

    names = set()
    for snap in q.stream():
        opp = snap.to_dict() or {}

        dispo = opp.get('dispositionValue')
        if dispo not in ('Sit','No Sit'):
            continue

        pid = str(opp.get('pipelineId') or '')
        pname = (pipe.get(pid) or '').strip().lower()
        if not pname:
            continue
        if pname in excluded:
            continue
        if pname not in included:
            continue

        cid = str(opp.get('contactId') or '')
        contact = contact_lookup(cid)
        setter = contact_custom_field(contact, setter_cf)
        setter_s = str(setter).strip() if setter not in (None,'') else 'none'
        names.add(setter_s)

    out = [{"value": n, "label": n} for n in sorted(names, key=lambda x: x.lower())]
    return out



def list_roster(db: firestore.Client) -> list[dict[str, Any]]:
    # Build name maps for enrichment
    raydar_map = {u["value"]: u["label"] for u in list_raydar_users(db)}
    ghl_map = {u["value"]: u["label"] for u in list_ghl_users(db)}

    rows: list[dict[str, Any]] = []
    for snap in db.collection("roster_people_v1").stream():
        d = snap.to_dict() or {}
        pk = str(d.get("person_key") or snap.id)
        ray_id = str(d.get("raydar_user_id") or "")
        ghl_id = str(d.get("ghl_user_id") or "")

        rows.append(
            {
                "person_key": pk,
                "display_name": d.get("display_name") or "",
                "role": d.get("role") or "",
                "ghl_setter_last_name": d.get("ghl_setter_last_name") or "",
                "raydar_user_id": ray_id or "",
                "raydar_user_name": raydar_map.get(ray_id, "") if ray_id else "",
                "ghl_user_id": ghl_id or "",
                "ghl_user_name": ghl_map.get(ghl_id, "") if ghl_id else "",
                "updatedAt": d.get("updatedAt"),
            }
        )

    rows.sort(key=lambda r: (str(r.get("role") or ""), str(r.get("display_name") or "")).lower())
    return rows


def goals_for_month(db: firestore.Client, month: str) -> list[dict[str, Any]]:
    snap = db.collection("goals_monthly_v1").document(month).get()
    if not snap.exists:
        return []
    d = snap.to_dict() or {}
    goals = d.get("goals") or {}

    out: list[dict[str, Any]] = []
    if isinstance(goals, dict):
        for person_key, metrics in goals.items():
            if not isinstance(metrics, dict):
                continue
            for metric, value in metrics.items():
                out.append({"person_key": person_key, "metric": metric, "value": value})

    out.sort(key=lambda r: (str(r.get("person_key") or ""), str(r.get("metric") or "")))
    return out


def upsert_roster(db: firestore.Client, payload: dict) -> dict:
    person_key = str(payload.get("person_key") or "").strip()
    role = str(payload.get("role") or "setter").strip()

    if not person_key:
        raise ValueError("person_key is required")

    display_name = str(payload.get("display_name") or "").strip()
    ghl_setter_last_name = str(payload.get("ghl_setter_last_name") or "").strip()
    raydar_user_id = str(payload.get("raydar_user_id") or "").strip()
    ghl_user_id = str(payload.get("ghl_user_id") or "").strip()

    # Role-based requirements
    if role in ("setter", "rep") and not raydar_user_id:
        raise ValueError("raydar_user_id is required for setter/rep")
    if role == "setter" and not ghl_setter_last_name:
        raise ValueError("ghl_setter_last_name is required for setter")
    if role == "rep" and not ghl_user_id:
        raise ValueError("ghl_user_id (GHL owner) is required for rep")

    doc = {
        "person_key": person_key,
        "display_name": display_name,
        "role": role,
        "ghl_setter_last_name": ghl_setter_last_name,
        "raydar_user_id": raydar_user_id,
        "ghl_user_id": ghl_user_id,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    db.collection("roster_people_v1").document(person_key).set(doc, merge=True)
    return {"ok": True, "person_key": person_key}


def upsert_goal(db: firestore.Client, payload: dict) -> dict:
    month = str(payload.get("month") or "").strip()
    person_key = str(payload.get("person_key") or "").strip()
    metric = str(payload.get("metric") or "").strip()
    value_raw = payload.get("value")

    if not month or len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    if not person_key:
        raise ValueError("person_key is required")
    if not metric:
        raise ValueError("metric is required")

    # numeric coercion
    try:
        value = float(str(value_raw).replace(",", "").strip())
        if value.is_integer():
            value = int(value)
    except Exception:
        raise ValueError("value must be numeric")

    # goals doc structure:
    # goals_monthly_v1/<month> {
    #   month,
    #   goals: { person_key: { metric: value } },
    #   updatedAt
    # }

    ref = db.collection("goals_monthly_v1").document(month)
    ref.set(
        {
            "month": month,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "goals": {person_key: {metric: value}},
        },
        merge=True,
    )

    return {"ok": True, "month": month, "person_key": person_key, "metric": metric, "value": value}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            db = get_db()
            payload = read_json(self)
            action = str(payload.get("action") or "").strip()

            if action == "bootstrap":
                month = str(payload.get("month") or "").strip()
                if not month:
                    now = datetime.now(timezone.utc)
                    month = f"{now.year}-{str(now.month).zfill(2)}"

                out = {
                    "raydar_users": list_raydar_users(db),
                    "ghl_users": list_ghl_users(db),
                    "roster_people": list_roster(db),
                    "ghl_setter_last_names": list_ghl_setter_last_names(db),
                    "goals_for_month": goals_for_month(db, month),
                }
                write_json(self, 200, out)
                return

            if action == "upsert_roster":
                out = upsert_roster(db, payload)
                write_json(self, 200, out)
                return

            if action == "upsert_goal":
                out = upsert_goal(db, payload)
                write_json(self, 200, out)
                return

            write_json(self, 400, {"error": f"Unknown action: {action}"})

        except Exception as e:
            write_json(self, 500, {"error": str(e)})


