#!/usr/bin/env python3
from __future__ import annotations

"""Compatibility launcher; Memory Rebuild v16.3.11 lives in memory_rebuild_app."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from latka_jazn.tools.memory_rebuild_app.config import TOOL_VERSION
from latka_jazn.tools.memory_rebuild_app.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main(entrypoint=__file__))
