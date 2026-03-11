# -*- coding: utf-8 -*-

"""Vercel Python function: /api/settings_api

JSON API backing /api/settings.

Actions:
- bootstrap: returns raydar_users, ghl_users, roster_people, goals_for_month
- setter_last_names: returns cached GHL setter last names dropdown options (can force refresh)
- upsert_roster: create/update roster_people_v1/<person_key>
- upsert_goal: upsert a single goal into goals_monthly_v1/<month>
- upsert_roster_and_goals: upsert roster mapping + multiple goals in one call

Firestore (happy-solar):
- roster_people_v1
- goals_monthly_v1
- settings_cache_v1/ghl_setter_last_names

Notes
- No auth in v1.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

import base64


def _unauthorized(h: BaseHTTPRequestHandler):
    h.send_response(401)
    h.send_header('WWW-Authenticate', 'Basic realm="Happy Solar Settings"')
    h.send_header('Content-Type', 'application/json; charset=utf-8')
    h.end_headers()
    h.wfile.write(b'{"error":"Unauthorized"}')


def _check_auth(h: BaseHTTPRequestHandler) -> bool:
    pw = os.environ.get('SETTINGS_PASSWORD')
    if not pw:
        return False
    auth = h.headers.get('Authorization') or ''
    if not auth.startswith('Basic '):
        return False
    try:
        raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
        _user, pwd = raw.split(':', 1)
        return pwd == pw
    except Exception:
        return False

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
        out.append({"value": str(snap.id), "label": str(d.get("name") or snap.id)})
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
    """Return distinct GHL setter last names observed on ran opps.

    NOTE: This can be expensive; do not call from bootstrap.
    Prefer using get_cached_ghl_setter_last_names().

    Implementation uses recent opps (appointmentOccurredAt) + pipeline scope + Sit/No Sit,
    then joins to contacts for setter last name.
    """

    since = datetime.now(timezone.utc) - timedelta(days=30)

    included = {"buffalo", "rochester", "virtual", "syracuse"}
    excluded = {"rehash", "sweeper", "inbound/lead locker"}

    pipe: dict[str, str] = {}
    for snap in db.collection("ghl_pipelines_v2").stream():
        d = snap.to_dict() or {}
        pid = str(d.get("id") or snap.id)
        nm = str(d.get("name") or "").strip()
        if pid and nm:
            pipe[pid] = nm

    def contact_lookup(contact_id: str) -> dict | None:
        if not contact_id:
            return None
        snap = db.collection("ghl_contacts_v2").document(str(contact_id)).get()
        if snap.exists:
            return snap.to_dict() or {}
        q = db.collection("ghl_contacts_v2").where("id", "==", str(contact_id)).limit(1)
        docs = list(q.stream())
        return (docs[0].to_dict() or {}) if docs else None

    def contact_custom_field(contact: dict | None, cf_id: str):
        if not isinstance(contact, dict):
            return None
        for cf in (contact.get("customFields") or []):
            if isinstance(cf, dict) and cf.get("id") == cf_id:
                return cf.get("value")
        return None

    setter_cf = "Eq4NLTSkJ56KTxbxypuE"

    q = (
        db.collection("ghl_opportunities_v2")
        .where("appointmentOccurredAt", ">=", since)
        .order_by("appointmentOccurredAt")
    )

    names: set[str] = set()
    contact_cache: dict[str, dict] = {}
    scanned = 0

    for snap in q.stream():
        scanned += 1
        if scanned > 600:
            break

        opp = snap.to_dict() or {}

        dispo = opp.get("dispositionValue")
        if dispo not in ("Sit", "No Sit"):
            continue

        pid = str(opp.get("pipelineId") or "")
        pname = (pipe.get(pid) or "").strip().lower()
        if not pname:
            continue
        if pname in excluded:
            continue
        if pname not in included:
            continue

        cid = str(opp.get("contactId") or "")
        if cid in contact_cache:
            contact = contact_cache[cid]
        else:
            contact = contact_lookup(cid) or {}
            contact_cache[cid] = contact

        setter = contact_custom_field(contact, setter_cf)
        setter_s = str(setter).strip() if setter not in (None, "") else "none"
        names.add(setter_s)

    out = [{"value": n, "label": n} for n in sorted(names, key=lambda x: x.lower())]
    return out


def get_cached_ghl_setter_last_names(db: firestore.Client) -> list[dict[str, str]]:
    """Cached dropdown options for GHL setter last names.

    Stored in Firestore to keep Settings UI snappy.
    """

    cache_ref = db.collection("settings_cache_v1").document("ghl_setter_last_names")
    snap = cache_ref.get()

    if snap.exists:
        d = snap.to_dict() or {}
        updated_at = str(d.get("updatedAt") or "")
        values = d.get("values")

        # 6-hour TTL
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else None
        except Exception:
            dt = None

        if dt and (datetime.now(timezone.utc) - dt) < timedelta(hours=6) and isinstance(values, list):
            return values

    values = list_ghl_setter_last_names(db)
    cache_ref.set({"updatedAt": datetime.now(timezone.utc).isoformat(), "values": values}, merge=True)
    return values


def list_roster(db: firestore.Client) -> list[dict[str, Any]]:
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

    rows.sort(key=lambda r: (str(r.get("role") or "").lower(), str(r.get("display_name") or "").lower()))
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


def _coerce_number(v: Any) -> int | float:
    value = float(str(v).replace(",", "").strip())
    if value.is_integer():
        return int(value)
    return value


def delete_goal(db: firestore.Client, payload: dict) -> dict:
    month = str(payload.get("month") or "").strip()
    person_key = str(payload.get("person_key") or "").strip()
    metric = str(payload.get("metric") or "").strip()

    if not month or len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    if not person_key:
        raise ValueError("person_key is required")
    if not metric:
        raise ValueError("metric is required")

    ref = db.collection("goals_monthly_v1").document(month)

    # Remove the specific field
    ref.set({"updatedAt": datetime.now(timezone.utc).isoformat()}, merge=True)
    ref.update({f"goals.{person_key}.{metric}": firestore.DELETE_FIELD})

    return {"ok": True, "month": month, "person_key": person_key, "metric": metric, "deleted": True}



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

    try:
        value = _coerce_number(value_raw)
    except Exception:
        raise ValueError("value must be numeric")

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


def upsert_roster_and_goals(db: firestore.Client, payload: dict) -> dict:
    """Write roster mapping and multiple goals in one round-trip."""

    # 1) roster
    roster_payload = {
        "person_key": payload.get("person_key"),
        "display_name": payload.get("display_name"),
        "role": payload.get("role"),
        "ghl_setter_last_name": payload.get("ghl_setter_last_name"),
        "raydar_user_id": payload.get("raydar_user_id"),
        "ghl_user_id": payload.get("ghl_user_id"),
    }
    upsert_roster(db, roster_payload)

    # 2) goals
    month = str(payload.get("month") or "").strip()
    if not month or len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")

    goals_list = payload.get("goals")
    if not isinstance(goals_list, list) or not goals_list:
        raise ValueError("goals must be a non-empty list")

    person_key = str(payload.get("person_key") or "").strip()
    goal_map: dict[str, dict[str, int | float]] = {}
    goal_map[person_key] = {}

    for g in goals_list:
        if not isinstance(g, dict):
            continue
        metric = str(g.get("metric") or "").strip()
        if not metric:
            continue
        try:
            value = _coerce_number(g.get("value"))
        except Exception:
            raise ValueError(f"Invalid numeric value for metric {metric}")
        goal_map[person_key][metric] = value

    ref = db.collection("goals_monthly_v1").document(month)
    ref.set(
        {
            "month": month,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "goals": goal_map,
        },
        merge=True,
    )

    return {"ok": True, "person_key": person_key, "month": month, "goals_written": list(goal_map[person_key].keys())}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not _check_auth(self):
            return _unauthorized(self)

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
                    "goals_for_month": goals_for_month(db, month),
                }
                write_json(self, 200, out)
                return

            if action == "setter_last_names":
                force = bool(payload.get("force"))
                if force:
                    values = list_ghl_setter_last_names(db)
                    db.collection("settings_cache_v1").document("ghl_setter_last_names").set(
                        {"updatedAt": datetime.now(timezone.utc).isoformat(), "values": values},
                        merge=True,
                    )
                else:
                    values = get_cached_ghl_setter_last_names(db)

                write_json(self, 200, {"ghl_setter_last_names": values, "forced": force})
                return

            if action == "upsert_roster":
                out = upsert_roster(db, payload)
                write_json(self, 200, out)
                return

            if action == "upsert_goal":
                out = upsert_goal(db, payload)
                write_json(self, 200, out)
                return

            if action == "delete_goal":
                out = delete_goal(db, payload)
                write_json(self, 200, out)
                return

            if action == "upsert_roster_and_goals":
                out = upsert_roster_and_goals(db, payload)
                write_json(self, 200, out)
                return

            write_json(self, 400, {"error": f"Unknown action: {action}"})

        except Exception as e:
            write_json(self, 500, {"error": str(e)})
