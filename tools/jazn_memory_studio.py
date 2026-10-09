#!/usr/bin/env python3
"""Windows launcher for canonical Jaźń Memory Studio."""
from __future__ import annotations
import os
from pathlib import Path

def resolve_working_root(value: str | Path | None = None) -> Path:
    root = Path(value or os.environ.get("JAZN_ROOT") or Path.cwd()).expanduser().resolve()
    if not (root / "latka_jazn" / "__init__.py").is_file():
        raise RuntimeError("Brak katalogu Jaźni. Uruchom z repozytorium lub ustaw JAZN_ROOT.")
    return root

def main() -> int:
    root = resolve_working_root()
    os.chdir(root)
    from latka_jazn.tools.memory_rebuild_app.cli import main as studio_main
    return int(studio_main(["--ui", "window", "studio"]))

if __name__ == "__main__":
    raise SystemExit(main())
