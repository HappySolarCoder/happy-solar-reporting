# -*- coding: utf-8 -*-

"""Website Funnel — completed-form contract. Isolated from sales/demo/opps."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
METRICS = API / "metrics"
for path in (str(API), str(METRICS)):
    if path not in sys.path:
        sys.path.append(path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


funnel = load_module("website_funnel_metric", METRICS / "website_funnel.py")
page = load_module("website_funnel_page", API / "website_funnel.py")
nav = load_module("dashboard_nav_website_funnel", API / "dashboard_nav.py")

WARM = (API / "warm_cache.py").read_text()
SALES = (METRICS / "sales.py").read_text()
ESSENTIAL = (METRICS / "essential_sales.py").read_text()
CREATED = (METRICS / "opportunities_created.py").read_text()
DEMO = (METRICS / "demo_rate.py").read_text()
FUNNEL_SRC = (METRICS / "website_funnel.py").read_text()
PAGE_SRC = (API / "website_funnel.py").read_text()
ROLLUP_SRC = (API / "web_funnel_rollup.py").read_text()
YESTERDAY_SRC = (API / "website_funnel_yesterday.py").read_text()

FAMILY_PATHS = (
    METRICS / "website_funnel.py",
    API / "website_funnel.py",
    API / "web_funnel_rollup.py",
    API / "website_funnel_yesterday.py",
)
FAMILY_TEXT = FUNNEL_SRC + "\n" + PAGE_SRC + "\n" + ROLLUP_SRC + "\n" + YESTERDAY_SRC

FORBIDDEN_GHL = (
    "ghl_contacts_v2",
    "ghl_opportunities_v2",
    "ghl_custom_fields_v2",
    "Website Landing Page",
    "Website Page Group",
    "Website UTM",
    "Website GA Client ID",
    "GA Client ID",
    "ghl_leads",
    "attributed_leads",
    "orphan",
    "Submit → GHL",
    "GHL website leads",
    "opportunity.source",
    "hd5QqHEOVSsPom5bJ32P",
    "P9oBjgbZjJdeE0OkBj9T",
)

DROPPED_HELPERS = (
    "compute_ghl_website_leads_for_day",
    "_query_opps_created_in_window",
    "fetch_contacts_by_ids",
    "compute_orphans",
    "is_website_attributed",
    "lead_attribution",
    "custom_field_value",
    "WEBSITE_FIELD_NAMES",
    "WEBSITE_LANDING_PAGE_FIELD_NAME",
    "WEBSITE_PAGE_GROUP_FIELD_NAME",
    "WEBSITE_UTM_FIELD_NAME",
    "GA_CLIENT_ID_FIELD_NAME",
    "OPP_COLLECTION",
    "CONTACT_COLLECTION",
    "GHL_LEAD_GOAL",
    "SUBMIT_TO_GHL_GOAL",
    "SESSION_TO_LEAD_GOAL",
)
