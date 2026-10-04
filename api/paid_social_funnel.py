# -*- coding: utf-8 -*-

"""Growth command center.

Dark overview for paid acquisition. The default screen is the live
adapter for the current month through today in America/New_York.
The November sample fixture is only shown for an explicit sample
request (?source=demo). Live mode does not copy sample numbers.
Viewing this page does not change ads or spend.
"""

from __future__ import annotations

import html
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

API_DIR = Path(__file__).resolve().parent
METRICS_DIR = API_DIR / "metrics"
for path in (str(API_DIR), str(METRICS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from growth_command import (  # noqa: E402
    CPL_TARGET,
    DEMO_COST_TARGET,
    LEAD_GOALS,
    SOLD_CPA_TARGET,
    demo_model,
    live_model,
    unavailable_model,
)


SAMPLE_SOURCES = {"demo", "sample", "fixture"}


def render_html(start: str | None = None, end: str | None = None, model: dict | None = None) -> str:
    if model is None:
        query = {"source": ["live"]}
        if start and end:
            query["start"] = [start]
            query["end"] = [end]
        model = model_for_query(query)
    return _document(model)


def model_for_query(qs: dict, live_loader=None) -> dict:
    source = " ".join(str((qs.get("source") or ["live"])[0] or "").split()).lower()
    if source in SAMPLE_SOURCES:
        return demo_model(qs)
    try:
        loader = live_loader or _load_live
        return live_model(loader(qs), qs)
    except Exception:
        return unavailable_model(
            "Live sources could not be read. Sample numbers are not shown."
        )


def _load_live(qs: dict) -> dict:
    import importlib.util
    from datetime import datetime
    from zoneinfo import ZoneInfo

    name = "hs_growth_paid_social_metric"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, METRICS_DIR / "paid_social_funnel.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("missing metric")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    now = datetime.now(ZoneInfo("America/New_York"))
    start, end = module.parse_range(qs, now)
    return module.compute_paid_social_funnel(module.cac.get_db(), start=start, end=end, now=now)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            body = render_html(model=model_for_query(qs)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            body = b"Growth command center could not render."
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
