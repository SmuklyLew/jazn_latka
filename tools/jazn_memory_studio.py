#!/usr/bin/env python3
"""Operator launcher for Jaźń - Studio Pamięci."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from latka_jazn.tools.memory_rebuild_app.memory_studio import main

if __name__ == '__main__':
    raise SystemExit(main())
