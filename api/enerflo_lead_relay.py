# -*- coding: utf-8 -*-

"""Vercel Python function: /api/enerflo_lead_relay

Receives the standard GHL webhook payload, remaps it into Enerflo's lead/add
shape, and forwards it with the Enerflo API key kept server-side.

Expected request headers from GHL:
- Content-Type: application/json
- X-Webhook-Secret: shared secret configured in GHL

Required env vars:
- ENERFLO_API_KEY
- ENERFLO_WEBHOOK_SECRET

Optional env vars:
- ENERFLO_LEAD_ADD_URL
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler
from typing import Any


ENERFLO_LEAD_ADD_URL = os.environ.get(
    "ENERFLO_LEAD_ADD_URL",
    "https://enerflo.io/api/v1/partner/action/lead/add",
).strip()
ENERFLO_USERS_URL = os.environ.get(
    "ENERFLO_USERS_URL",
    "https://enerflo.io/api/v3/users",
).strip()
ENERFLO_COMPANY_ID = os.environ.get("ENERFLO_COMPANY_ID", "").strip()
EXCLUDED_PIPELINE_NAMES = {
    "inbound lead locker",
    "inbound/lead locker",
    "rehash",
}

REQUIRED_FIELDS = ("first_name", "last_name", "address", "city", "state", "zip")
STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def read_json(req: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(req.headers.get("Content-Length", "0") or "0")
    raw = req.rfile.read(length) if length else b"{}"
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_json(req: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    req.send_response(status)
    req.send_header("Content-Type", "application/json; charset=utf-8")
    req.send_header("Cache-Control", "no-store")
    req.send_header("Content-Length", str(len(body)))
    req.end_headers()
    req.wfile.write(body)


def normalize_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", normalize_str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_state(value: Any) -> str:
    state = normalize_str(value)
    if not state:
        return ""
    if len(state) == 2 and state.isalpha():
        return state.upper()
    return STATE_ABBREVIATIONS.get(state.lower(), state)


def generate_placeholder_email(first_name: str, last_name: str, phone: str) -> str:
    seed = phone[-4:] if phone else uuid.uuid4().hex[:6]
    suffix = uuid.uuid4().hex[:4]
    return f"needemail{seed}{suffix}@example.com"


def normalize_name(value: Any) -> str:
    name = normalize_str(value).lower()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def name_parts(value: Any) -> list[str]:
    return [part for part in normalize_name(value).split(" ") if part]


def extract_pipeline_name(payload: dict[str, Any]) -> str:
    candidate_paths = (
        ("pipeline",),
        ("pipeline_name",),
        ("pipelineName",),
        ("opportunity", "pipeline"),
        ("opportunity", "pipeline_name"),
        ("opportunity", "pipelineName"),
    )
    for path in candidate_paths:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            name = normalize_str(
                value.get("name")
                or value.get("title")
                or value.get("pipeline")
                or value.get("pipeline_name")
                or value.get("pipelineName")
            )
            if name:
                return name
        else:
            name = normalize_str(value)
            if name:
                return name
    return ""


def is_excluded_pipeline(payload: dict[str, Any]) -> tuple[bool, str]:
    pipeline_name = extract_pipeline_name(payload)
    if normalize_name(pipeline_name) in EXCLUDED_PIPELINE_NAMES:
        return True, pipeline_name
    return False, pipeline_name


def extract_rep_identity(payload: dict[str, Any]) -> dict[str, str]:
    candidate_paths = (
        ("assigned_to",),
        ("assignedTo",),
        ("assigned_user",),
        ("assignedUser",),
        ("assigned_user_name",),
        ("assignedUserName",),
        ("contact_owner",),
        ("contactOwner",),
        ("owner",),
        ("owner_name",),
        ("ownerName",),
        ("sales_rep",),
        ("salesRep",),
        ("user",),
        ("user_name",),
        ("userName",),
        ("opportunity", "assigned_to"),
        ("opportunity", "assignedTo"),
        ("opportunity", "assigned_user_name"),
        ("opportunity", "assignedUserName"),
        ("opportunity", "owner"),
        ("opportunity", "owner_name"),
        ("contact", "assigned_to"),
        ("contact", "assignedTo"),
        ("contact", "contact_owner"),
        ("contact", "contactOwner"),
        ("contact", "owner"),
    )
    email_keys = ("email", "user_email", "userEmail", "assigned_to_email", "assignedToEmail")
    for path in candidate_paths:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            name = normalize_str(
                value.get("name")
                or value.get("full_name")
                or value.get("fullName")
                or value.get("display_name")
                or value.get("displayName")
            )
            email = ""
            for key in email_keys:
                email = normalize_str(value.get(key))
                if email:
                    break
            if name or email:
                return {"name": name, "email": email}
        elif isinstance(value, str):
            stripped = normalize_str(value)
            if stripped:
                if "@" in stripped:
                    return {"name": "", "email": stripped}
                return {"name": stripped, "email": ""}
    return {"name": "", "email": ""}


def fetch_enerflo_users(api_key: str) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    page = 1
    while True:
        query: dict[str, str | int] = {"user_role": "agent", "pageSize": 200, "page": page}
        if ENERFLO_COMPANY_ID:
            query["company_id"] = ENERFLO_COMPANY_ID
        url = f"{ENERFLO_USERS_URL}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "api-key": api_key,
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw) if raw else {}
        batch = parsed.get("results") if isinstance(parsed, dict) else None
        if not isinstance(batch, list) or not batch:
            break
        users.extend(item for item in batch if isinstance(item, dict))
        total_pages = int(parsed.get("totalPages") or 1) if isinstance(parsed, dict) else 1
        if page >= total_pages:
            break
        page += 1
    return users


def score_user_match(rep_name: str, rep_email: str, user: dict[str, Any]) -> float:
    user_email = normalize_str(user.get("email")).lower()
    if rep_email and user_email and rep_email.lower() == user_email:
        return 10.0

    user_name = normalize_str(user.get("name"))
    rep_norm = normalize_name(rep_name)
    user_norm = normalize_name(user_name)
    if not rep_norm or not user_norm:
        return 0.0
    if rep_norm == user_norm:
        return 5.0

    rep_tokens = name_parts(rep_name)
    user_tokens = name_parts(user_name)
    if rep_tokens and user_tokens:
        if rep_tokens[-1] == user_tokens[-1] and rep_tokens[0] == user_tokens[0]:
            return 4.5
        if set(rep_tokens).issubset(set(user_tokens)) or set(user_tokens).issubset(set(rep_tokens)):
            return 4.0

    return SequenceMatcher(None, rep_norm, user_norm).ratio()


def match_enerflo_rep(payload: dict[str, Any], api_key: str) -> dict[str, str]:
    rep = extract_rep_identity(payload)
    rep_name = rep["name"]
    rep_email = rep["email"]
    if not rep_name and not rep_email:
        return {}

    users = fetch_enerflo_users(api_key)
    if not users:
        return {}

    active_users = [user for user in users if str(user.get("active", 1)) not in {"0", "false", "False"}]
    scored = sorted(
        (
            (score_user_match(rep_name, rep_email, user), user)
            for user in (active_users or users)
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return {}

    best_score, best_user = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 0.88:
        return {}
    if best_score < 4.0 and (best_score - second_score) < 0.08:
        return {}

    matched_email = normalize_str(best_user.get("email"))
    if not matched_email:
        return {}
    return {"assign_to_email": matched_email}


def map_ghl_to_enerflo(payload: dict[str, Any], api_key: str) -> dict[str, str]:
    first_name = normalize_str(payload.get("first_name") or payload.get("firstName"))
    last_name = normalize_str(payload.get("last_name") or payload.get("lastName"))
    email = normalize_str(payload.get("email"))
    phone = normalize_phone(payload.get("phone"))
    address = normalize_str(payload.get("address") or payload.get("address1"))
    city = normalize_str(payload.get("city"))
    state = normalize_state(payload.get("state"))
    postal_code = normalize_str(payload.get("zip") or payload.get("postal_code") or payload.get("postalCode"))
    if not email:
        email = generate_placeholder_email(first_name, last_name, phone)

    out = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "mobile": phone,
        "address": address,
        "city": city,
        "state": state,
        "zip": postal_code,
    }
    out.update(match_enerflo_rep(payload, api_key))
    return {k: v for k, v in out.items() if v != ""}


def validate_required(mapped: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_FIELDS:
        if not normalize_str(mapped.get(key)):
            missing.append(key)
    return missing


def masked_payload(mapped: dict[str, str]) -> dict[str, str]:
    safe = dict(mapped)
    if safe.get("email"):
        safe["email"] = "***"
    if safe.get("mobile"):
        safe["mobile"] = "***"
    if safe.get("assign_to_email"):
        safe["assign_to_email"] = "***"
    return safe


def forward_to_enerflo(mapped: dict[str, str], api_key: str) -> tuple[int, dict[str, Any]]:
    body = json.dumps({"lead": mapped}).encode("utf-8")
    req = urllib.request.Request(
        ENERFLO_LEAD_ADD_URL,
        data=body,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw}
            return int(resp.status), parsed if isinstance(parsed, dict) else {"raw": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return int(exc.code), parsed if isinstance(parsed, dict) else {"raw": parsed}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        write_json(
            self,
            200,
            {
                "ok": True,
                "route": "/api/enerflo_lead_relay",
                "method": "POST",
                "required_headers": ["Content-Type: application/json", "X-Webhook-Secret: <secret>"],
                "maps": {
                    "address1": "address",
                    "postal_code": "zip",
                },
            },
        )

    def do_POST(self) -> None:
        api_key = normalize_str(os.environ.get("ENERFLO_API_KEY"))
        secret = normalize_str(os.environ.get("ENERFLO_WEBHOOK_SECRET"))

        if not api_key or not secret:
            write_json(
                self,
                500,
                {
                    "ok": False,
                    "error": "missing_env",
                    "missing": [
                        key
                        for key, value in (
                            ("ENERFLO_API_KEY", api_key),
                            ("ENERFLO_WEBHOOK_SECRET", secret),
                        )
                        if not value
                    ],
                },
            )
            return

        provided_secret = normalize_str(
            self.headers.get("X-Webhook-Secret") or self.headers.get("x-webhook-secret")
        )
        if provided_secret != secret:
            write_json(self, 401, {"ok": False, "error": "unauthorized"})
            return

        incoming = read_json(self)
        blocked, pipeline_name = is_excluded_pipeline(incoming)
        if blocked:
            write_json(
                self,
                200,
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "excluded_pipeline",
                    "pipeline": pipeline_name,
                },
            )
            return

        mapped = map_ghl_to_enerflo(incoming, api_key)
        missing = validate_required(mapped)
        if missing:
            write_json(
                self,
                400,
                {
                    "ok": False,
                    "error": "missing_required_fields",
                    "missing": missing,
                    "received": masked_payload(mapped),
                },
            )
            return

        status, enerflo_response = forward_to_enerflo(mapped, api_key)
        ok = 200 <= status < 300
        write_json(
            self,
            200 if ok else 502,
            {
                "ok": ok,
                "forward_status": status,
                "sent": masked_payload(mapped),
                "enerflo_response": enerflo_response,
                "forwarded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
