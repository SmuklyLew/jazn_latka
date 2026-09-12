#!/usr/bin/env python3
"""Compatibility entrypoint for Jaźń - Studio Testów.

The application implementation lives in ``tools/jazn_tests_studio/`` so CLI,
TUI and Windows GUI share one domain core and one lifecycle contract.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jazn_tests_studio.app import main


if __name__ == "__main__":
    raise SystemExit(main())
