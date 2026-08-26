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
