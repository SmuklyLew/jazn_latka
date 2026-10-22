#!/usr/bin/env python3
"""Small operator entrypoint, never a second Jaźń CLI control plane."""
from __future__ import annotations

from pathlib import Path
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from latka_jazn.tools.minimal_setup import main
    raise SystemExit(main())
