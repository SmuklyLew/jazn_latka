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
    modes.add_argument("--cognitive-audit", action="store_true",
                       help="Read-only synthetic evaluation of P0B/P1/P2/P3/P4")
    modes.add_argument("--cognitive-cases", metavar="JSON_FILE",
                       help="Read-only evaluation of a bounded operator-labeled intent set")
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
        if args.cognitive_audit:
            from latka_jazn.core.cognitive_development_evaluation import synthetic_operator_report
            print(json.dumps(synthetic_operator_report(), ensure_ascii=False, indent=2))
            return 0
        if args.cognitive_cases:
            from latka_jazn.core.cognitive_development_evaluation import (
                evaluate_intents, parse_labeled_cases,
            )
            case_path = Path(args.cognitive_cases).expanduser()
            if case_path.is_symlink() or not case_path.is_file():
                raise ValueError("Benchmark must be a regular local JSON file (not symlink)")
            if case_path.stat().st_size > 262144:
                raise ValueError("Benchmark exceeds 256 KiB read limit")
            def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate JSON field: " + key)
                    result[key] = value
                return result
            payload = json.loads(case_path.read_text(encoding="utf-8"),
                                 object_pairs_hook=no_duplicates)
            evaluation = evaluate_intents(parse_labeled_cases(payload))
            evaluation["origin"] = "operator_supplied_unverified"
            evaluation["source_data_saved"] = False
            evaluation["live_runtime_verified"] = False
            print(json.dumps(evaluation, ensure_ascii=False, indent=2))
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
