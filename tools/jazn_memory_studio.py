#!/usr/bin/env python3
"""Windows launcher for the canonical Jaźń Memory Studio.

The EXE bundles program code, never private MEMORY. JAZN_ROOT points to an
existing verified Jaźń checkout; the smoke mode never opens a Tk window.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_working_root(value: str | Path | None = None) -> Path:
    explicit = value or os.environ.get("JAZN_ROOT")
    if explicit:
        candidates = (Path(explicit),)
    else:
        candidates = (Path.cwd(), Path(__file__).resolve().parent.parent)
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "latka_jazn" / "__init__.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root
    raise RuntimeError(
        "Brak katalogu Jaźni. Uruchom z repozytorium lub ustaw JAZN_ROOT "
        "na istniejący katalog SYSTEM z latka_jazn/__init__.py."
    )


def main() -> int:
    root = resolve_working_root()
    os.chdir(root)
    from latka_jazn.tools.memory_rebuild_app.cli import main as studio_main

    if "--smoke" in sys.argv[1:]:
        if sys.argv[1:] != ["--smoke"]:
            raise ValueError("--smoke jest samodzielnym trybem testowym.")
        from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace
        assert DesktopWorkspace is not None
        print("JaznMemoryStudio smoke OK")
        return 0
    return int(studio_main(["--ui", "window", "studio"]))


if __name__ == "__main__":
    raise SystemExit(main())
