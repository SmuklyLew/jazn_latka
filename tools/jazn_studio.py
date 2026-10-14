#!/usr/bin/env python3
"""Jaźń Studio standalone operator launcher (SYSTEM runtime is not replaced)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def _root(explicit: str | None = None) -> Path:
    selected = explicit or os.environ.get("JAZN_ROOT")
    locations = [Path(selected)] if selected else [Path.cwd(), Path(__file__).resolve().parent.parent]
    for candidate in locations:
        resolved = candidate.expanduser().resolve()
        if (resolved / "run.py").is_file() and (resolved / "main.py").is_file():
            if str(resolved) not in sys.path:
                sys.path.insert(0, str(resolved))
            return resolved
    raise ValueError("Brak SYSTEM. Uruchom Studio z katalogu Jaźni lub użyj --root / JAZN_ROOT.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jazn_studio",
        description="Jaźń Studio — runtime, MCP, konfiguracja, diagnostyka, aktualizacje",
        allow_abbrev=False)
    parser.add_argument("--root", help="Ścieżka do SYSTEM Jaźni (alternatywnie JAZN_ROOT)")
    parser.add_argument("--ui", choices=["window", "text", "tui"], default="window")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke", action="store_true")
    modes.add_argument("--gui-smoke", action="store_true")
    modes.add_argument("--json", action="store_true", help="Snapshot tylko do odczytu")
    modes.add_argument("--plan-update", action="store_true", help="Bez zmian w Git")
    modes.add_argument("--diagnose", choices=["status", "doctor", "model", "memory", "mcp_catalog"])
    args = parser.parse_args(argv)
    try:
        root = _root(args.root)
        from latka_jazn.tools.jazn_studio.core import (
            STUDIO_VERSION, load_settings, run_diagnostic, studio_snapshot,
            update_plan, verified_root,
        )
        root = verified_root(root)
        if args.smoke:
            settings, _ = load_settings(root)
            assert settings.timeout_seconds >= 2
            print("JaznStudio " + STUDIO_VERSION + " smoke OK")
            return 0
        if args.gui_smoke:
            from latka_jazn.tools.jazn_studio.ui import run_window
            result = run_window(root, smoke=True)
            print("JaznStudio " + STUDIO_VERSION + " GUI smoke OK")
            return result
        if args.json:
            print(json.dumps(studio_snapshot(root), ensure_ascii=False, indent=2))
            return 0
        if args.plan_update:
            print(json.dumps(update_plan(root), ensure_ascii=False, indent=2))
            return 0
        if args.diagnose:
            result = run_diagnostic(root, args.diagnose, timeout=30)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1
        if args.ui in ("text", "tui"):
            snapshot = studio_snapshot(root)
            print("JAŹŃ STUDIO", STUDIO_VERSION)
            print("Runtime:", snapshot["system_package"])
            print("Root:", root)
            print("Git:", json.dumps(snapshot["git"], ensure_ascii=False))
            print("Dostępne tryby: --diagnose status|doctor|memory|model|mcp_catalog")
            print("Edytor profili: python -X utf8 tools/jazn_config_studio.py")
            print("Interfejs okienkowy: --ui window")
            return 0
        from latka_jazn.tools.jazn_studio.ui import run_window
        return run_window(root)
    except (OSError, ValueError, RuntimeError) as exc:
        print("Jaźń Studio: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
