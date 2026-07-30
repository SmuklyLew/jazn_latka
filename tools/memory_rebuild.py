#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Sequence
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_LEGACY_FLAGS = {
    "--legacy-five-db",
    "--config",
    "--write-example-config",
    "--no-ui",
    "--plan-only",
    "--all-discovered",
    "--source",
    "--self-test",
    "--confirm",
}


def _legacy_requested(args: list[str]) -> bool:
    if args and args[0] == "legacy":
        return True
    return any(item in _LEGACY_FLAGS for item in args)


def _run_legacy(args: list[str]) -> int:
    legacy = Path(__file__).with_name("memory_rebuild_legacy_v24.py")
    if not legacy.is_file():
        raise FileNotFoundError(f"Brak zgodnościowego narzędzia: {legacy}")
    cleaned = [item for item in args if item != "--legacy-five-db"]
    if cleaned and cleaned[0] == "legacy":
        cleaned = cleaned[1:]
    previous = list(sys.argv)
    sys.argv = [str(legacy), *cleaned]
    try:
        try:
            runpy.run_path(str(legacy), run_name="__main__")
        except SystemExit as exc:
            value = exc.code
            return int(value) if isinstance(value, int) else (0 if value in {None, ""} else 1)
        return 0
    finally:
        sys.argv = previous


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _legacy_requested(args):
        return _run_legacy(args)
    from latka_jazn.tools.memory_rebuild_app.cli import main as app_main
    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
