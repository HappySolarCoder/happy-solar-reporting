# -*- coding: utf-8 -*-
"""Idempotent admin seed for the October 2026 Ads Dashboard goals.

The Ads Dashboard reads goals_monthly_v1/<YYYY-MM> when the selected window
stays inside one month. Admin Settings writes that collection for roster
people (sales_goal, doors_goal, appts_goal, demos_goal). Those person rows
are not the company document this dashboard reads.

Dry-run is the default. It does not connect to Firestore.

    python scripts/seed_ads_dashboard_goals.py
    python scripts/seed_ads_dashboard_goals.py --apply

--apply requires the Admin Settings secret (SETTINGS_PASSWORD) and the
Firestore admin env (FIREBASE_SERVICE_ACCOUNT_JSON, GCP_PROJECT_ID,
FIRESTORE_DATABASE_ID). The script never prints those values.

The write merges goals.ads_dashboard on goals_monthly_v1/2026-10 and leaves
other people on that month alone. A second --apply does not write when the
October values already match.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

COLLECTION = "goals_monthly_v1"
MONTH = "2026-10"
PERSON_KEY = "ads_dashboard"
# Budget is stored as spend (what the dashboard reads) and budget (the name
# Evan used). Cost figures match api/metrics/ads_dashboard.py.
METRICS: dict[str, int] = {
    "leads": 30,
    "opps": 10,
    "demos": 6,
    "sales": 3,
    "spend": 1800,
    "budget": 1800,
    "cost_per_lead": 25,
    "cost_per_opp": 100,
    "cost_per_demo": 300,
    "cost_per_sale": 600,
}
_ADMIN_ENV = (
    "SETTINGS_PASSWORD",
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "GCP_PROJECT_ID",
    "FIRESTORE_DATABASE_ID",
)


def planned_document(now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    return {
        "month": MONTH,
        "updatedAt": moment.astimezone(timezone.utc).isoformat(),
        "goals": {PERSON_KEY: dict(METRICS)},
    }


def _same_number(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if left == right:
        return True
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def metrics_match(data: dict[str, Any] | None, person_key: str = PERSON_KEY) -> bool:
    goals = (data or {}).get("goals") if isinstance(data, dict) else None
    current = goals.get(person_key) if isinstance(goals, dict) else None
    if not isinstance(current, dict):
        return False
    return all(_same_number(current.get(key), value) for key, value in METRICS.items())


def apply_document(db: Any, now: datetime | None = None) -> str:
    """Create or merge the October doc. Returns created, updated, or unchanged."""
    ref = db.collection(COLLECTION).document(MONTH)
    snap = ref.get()
    exists = bool(getattr(snap, "exists", False))
    current = snap.to_dict() if exists else None
    if metrics_match(current if isinstance(current, dict) else None):
        return "unchanged"
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not exists:
        ref.set(planned_document(moment))
        return "created"
    updates: dict[str, Any] = {"month": MONTH, "updatedAt": moment.isoformat()}
    for key, value in METRICS.items():
        updates[f"goals.{PERSON_KEY}.{key}"] = value
    ref.update(updates)
    return "updated"


def admin_block_reason() -> str | None:
    missing = [name for name in _ADMIN_ENV if not str(os.environ.get(name) or "").strip()]
    if not missing:
        return None
    return (
        "Refusing to write. An admin shell needs "
        + ", ".join(missing)
        + ". Values are not printed."
    )


def get_db() -> Any:
    from google.cloud import firestore
    from google.oauth2 import service_account

    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON") or ""
    try:
        creds_dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID"),
        database=os.environ.get("FIRESTORE_DATABASE_ID"),
        credentials=creds,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Ads Dashboard goals for 2026-10.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write goals_monthly_v1/2026-10 (default is a dry run)",
    )
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps(planned_document(), indent=2, sort_keys=True))
        print(
            "Dry run only. Nothing was read or written. "
            "Pass --apply to merge goals_monthly_v1/2026-10."
        )
        return 0
    reason = admin_block_reason()
    if reason:
        print(reason, file=sys.stderr)
        return 2
    try:
        db = get_db()
        result = apply_document(db)
    except Exception as exc:
        print(f"Write failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"{result} {COLLECTION}/{MONTH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
