#!/usr/bin/env python3
"""Public launcher for Studio Jaźni Starter; runtime stays in main.py."""
from tools.jazn_run_studio.dependency_preflight import dispatch

if __name__ == "__main__":
    raise SystemExit(dispatch())
