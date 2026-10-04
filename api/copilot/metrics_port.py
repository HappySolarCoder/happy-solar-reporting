# -*- coding: utf-8 -*-
"""Call the existing metric modules. This does not change their formulas."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from copilot.periods import Period

API_DIR = Path(__file__).resolve().parents[1]
_MODULES: dict[str, Any] = {}


def _load(name: str):
    cached = _MODULES.get(name)
    if cached is not None:
        return cached
    path = API_DIR / "metrics" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hs_copilot_metrics_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing metric module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _MODULES[name] = module
    return module


class LiveMetrics:
    """Unfiltered bundle so source cards can sum the same alias keys as the overview."""

    def __init__(self, db=None):
        self._db = db

    def _database(self):
        if self._db is not None:
            return self._db
        sales = _load("sales")
        self._db = sales.get_db()
        return self._db

    def bundle(self, period: Period) -> dict[str, Any]:
        if period.timezone != "America/New_York":
            raise RuntimeError(
                "metric modules hardcode America/New_York; refusing to run them in another zone"
            )
        db = self._database()
        sales_mod = _load("sales")
        ran_mod = _load("opportunities_ran")
        created_mod = _load("opportunities_created")
        demo_mod = _load("demo_rate")
        sales = sales_mod.compute_sales(
            db,
            sales_mod.SalesMetricContract(),
            year=int(period.start[0:4]),
            month=int(period.start[5:7]),
            tz=period.timezone,
            start=period.start,
            end=period.end,
        )
        ran = ran_mod.compute(
            db,
            ran_mod.MetricContract(),
            year=int(period.start[0:4]),
            month=int(period.start[5:7]),
            start=period.start,
            end=period.end,
        )
        created = created_mod.compute(
            db,
            created_mod.MetricContract(),
            year=int(period.start[0:4]),
            month=int(period.start[5:7]),
            start=period.start,
            end=period.end,
            pipeline_scope="all",
        )
        demo = demo_mod.build_payload(
            db,
            int(period.start[0:4]),
            int(period.start[5:7]),
            {},
            start=period.start,
            end=period.end,
        )
        return {
            "sales": sales.get("result"),
            "created": created.get("result"),
            "ran": ran.get("result"),
            "sits": demo.get("sit_count"),
            "sales_by_source": (sales.get("breakdowns") or {}).get("sales_by_lead_gen_source") or {},
            "ran_by_source": (ran.get("breakdowns") or {}).get("ran_by_lead_gen_source") or {},
            "created_by_source": (created.get("breakdowns") or {}).get("created_by_lead_gen_source") or {},
            "sit_by_source": (demo.get("breakdowns") or {}).get("sit_by_lead_gen_source") or {},
            "generated_at": sales.get("generated_at") or ran.get("generated_at"),
            "rows": (ran.get("sample_rows") or [])[:50],
            "timezone": period.timezone,
        }
