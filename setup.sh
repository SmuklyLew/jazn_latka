#!/usr/bin/env sh
set -eu
MODE="${1:-preflight}"
PY="${PYTHON:-python}"
case "$MODE" in
  preflight) exec "$PY" -X utf8 tools/local_runtime_preflight.py --root . --json ;;
  venv) "$PY" -m venv .venv; echo "venv created; no network install performed" ;;
  online)
    [ -d .venv ] || "$PY" -m venv .venv
    if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python.exe; fi
    "$VPY" -m pip install --upgrade pip
    "$VPY" -m pip install -e .
    ;;
  *) echo "usage: ./setup.sh [preflight|venv|online]" >&2; exit 2 ;;
esac
