from __future__ import annotations

"""Thin user launcher for the Jaźń system.

All runtime, command and conversation control belongs to ``main.py``.  This
file intentionally owns only the dependency-free ``--version`` fast path and
then executes ``main.py`` with the original argument vector unchanged.
"""

from pathlib import Path
import runpy
import sys

from latka_jazn.version import PACKAGE_VERSION_FULL


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_utf8_stdio()
    if sys.argv[1:] == ["--version"]:
        print(PACKAGE_VERSION_FULL)
        return 0

    main_path = Path(__file__).resolve().with_name("main.py")
    runpy.run_path(str(main_path), run_name="__main__")
    return 0  # ``main.py`` exits through SystemExit; kept for type checkers.


if __name__ == "__main__":
    raise SystemExit(main())
