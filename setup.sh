#!/usr/bin/env sh
# Jaźń operator setup; no daemon/tunnel lifecycle and no implicit network.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  printf '%s\n' "Python not found: $PY. Install a supported Python 3.12-3.14 first." >&2
  exit 2
fi
export PYTHONUTF8=1
cd "$ROOT"
exec "$PY" -X utf8 "$ROOT/tools/jazn_setup.py" "$@"
