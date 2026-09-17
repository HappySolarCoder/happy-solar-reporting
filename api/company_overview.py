# -*- coding: utf-8 -*-
"""Company Overview dashboard — assembled from _co_chunks (Lead Gen Inbound/3PL split)."""
from __future__ import annotations

from pathlib import Path

_CHUNKS = Path(__file__).resolve().parent / "_co_chunks"
_N = 45
_src = "".join((_CHUNKS / f"c{i:02d}.txt").read_text() for i in range(_N))
exec(compile(_src, str(Path(__file__).resolve()), "exec"), globals())
