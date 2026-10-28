#!/usr/bin/env python3
"""Jaźń — Serce Systemu. Thin GUI entry; main.py owns the runtime."""
from tools.jazn_run_studio.dependency_preflight import dispatch

if __name__ == "__main__":
    raise SystemExit(dispatch())
