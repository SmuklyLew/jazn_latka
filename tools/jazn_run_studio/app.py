"""Desktop and headless entrypoints use the same operator controller."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .core import ACTION_BY_KEY, Controller, discovery, load_settings
from latka_jazn.core.system_config import apply_system_config


def main(argv: list[str] | None = None) -> int:
    # Frozen console builds do not necessarily honor Python's UTF-8 startup mode.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description="Studio Jaźni Starter", allow_abbrev=False)
    default_root = Path.cwd() if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("JAZN_ROOT", default_root)))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Odczyt zależności; bez startu usług")
    mode.add_argument("--run", choices=sorted(ACTION_BY_KEY), help="Wykonaj komendę wspólnym backendem")
    mode.add_argument("--probe", choices=["ollama", "gateway", "cloudflare", "tunnel_service"], help="Odczyt rzeczywistej usługi wspólnym backendem")
    mode.add_argument("--gui-smoke", action="store_true", help="Test okna i zamknięcia; bez startu usług")
    parser.add_argument("--report", type=Path, help="Zapis raportu do nowego pliku")
    args = parser.parse_args(argv)
    try:
        apply_system_config(args.root, os.environ)
        core = Controller(args.root)
        if args.check:
            print(json.dumps(discovery(core.settings), ensure_ascii=False, indent=2))
            return 0
        if args.run or args.probe:
            job = core.start_action(args.run) if args.run else core.probe(args.probe)
            job.done.wait()
            for line in core.logs.get(job.key, ()):
                print(line)
            if args.report:
                core.export_report(args.report)
            return 0 if job.state == "succeeded" else 1
        try:
            from .window import run_window
        except ImportError as exc:
            print("Brak zależności GUI Qt: " + str(exc) + "\nZainstaluj opcjonalny profil run-studio; instrukcja w tools/jazn_run_studio/README.md.", file=sys.stderr)
            return 2
        return run_window(core, smoke=args.gui_smoke)
    except (OSError, ValueError, RuntimeError) as exc:
        print("Studio Jaźni: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2
