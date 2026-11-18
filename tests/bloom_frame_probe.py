# -*- coding: utf-8 -*-
"""Run a rendered Bloom frame script in Node and return the messages it posts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "bloom_frame_probe.mjs"


def probe_bloom_frame(html: str, scenario: dict, mode: str) -> dict:
    completed = subprocess.run(
        ["node", str(PROBE)],
        input=json.dumps({"html": html, "scenario": scenario, "mode": mode}),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout or "bloom frame probe failed")
    return json.loads(completed.stdout)


def request_origins(result: dict) -> list[str]:
    origins = []
    for post in result["posts"]:
        data = post.get("data") or {}
        if data.get("type") == "happy-solar-goose" and data.get("action") == "request-token":
            origins.append(post["origin"])
    return origins
