"""Desktop and headless entrypoints use the same operator controller."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import sys

from .core import ACTION_BY_KEY, Controller, discovery, load_settings
from latka_jazn.core.system_config import apply_system_config
from latka_jazn.core.acceptance_layout import (
    acceptance_environment, validate_resumed_daemon, validate_isolated_daemon_start,
)

ISOLATED_DIAGNOSTIC_ACTIONS = frozenset({
    "version", "preflight", "status", "doctor", "model", "memory", "supervisor",
})


@contextmanager
def _selected_root_environment(root: Path):
    """Pass the verified selected SYSTEM to child tools, restoring caller ENV."""
    previous = os.environ.get("JAZN_ROOT")
    os.environ["JAZN_ROOT"] = str(root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("JAZN_ROOT", None)
        else:
            os.environ["JAZN_ROOT"] = previous


def main(argv: list[str] | None = None) -> int:
    # Frozen console builds do not necessarily honor Python's UTF-8 startup mode.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description="Jaźń — Serce Systemu", allow_abbrev=False)
    from latka_jazn.version import PACKAGE_VERSION_FULL
    parser.add_argument("--version", action="version", version=PACKAGE_VERSION_FULL)
    # Source checkouts own their code root. An inherited JAZN_ROOT pointing to
    # another installation must never silently redirect this source launcher.
    # For frozen builds retain the explicit ENV/CWD selection contract.
    default_root = (Path(os.environ.get("JAZN_ROOT") or Path.cwd())
                    if getattr(sys, "frozen", False)
                    else Path(__file__).resolve().parents[2])
    parser.add_argument("--root", type=Path, default=default_root)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Odczyt zależności; bez startu usług")
    mode.add_argument("--run", choices=sorted(ACTION_BY_KEY), help="Wykonaj komendę wspólnym backendem")
    mode.add_argument("--probe", choices=["ollama", "gateway", "cloudflare", "tunnel_service"], help="Odczyt rzeczywistej usługi wspólnym backendem")
    mode.add_argument("--gui-smoke", action="store_true", help="Test okna i zamknięcia; bez startu usług")
    parser.add_argument("--isolated-acceptance", action="store_true",
                        help="Izolowany runtime, MEMORY off, trwałe wyniki TPA poza SYSTEM")
    parser.add_argument("--report", type=Path, help="Zapis raportu do nowego pliku")
    args = parser.parse_args(argv)
    args.root = args.root.expanduser().resolve()
    try:
        scope = acceptance_environment(args.root) if args.isolated_acceptance else nullcontext()
        with _selected_root_environment(args.root), scope as layout:
            apply_system_config(args.root, os.environ)
            core = Controller(args.root)
            if args.isolated_acceptance:
                assert layout is not None
                if args.run == "start":
                    # Explicit operator intent: only own verified/dead instance.
                    # Do not delete the marker or replay pending requests.
                    validate_isolated_daemon_start(layout, core.settings.daemon_url)
                elif not args.check and args.run not in ISOLATED_DIAGNOSTIC_ACTIONS:
                    validate_resumed_daemon(layout, core.settings.daemon_url)
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
                from .qt_recovery import offer_qt_install
                if offer_qt_install(exc, allow_install=not (args.gui_smoke or args.isolated_acceptance)):
                    try:
                        from .window import run_window
                    except ImportError as retry_error:
                        print("Qt nadal nie działa: " + str(retry_error), file=sys.stderr)
                        return 2
                else:
                    print("Brak zależności GUI Qt: " + str(exc) + "\nZainstaluj opcjonalny profil run-studio; instrukcja w tools/jazn_run_studio/README.md.", file=sys.stderr)
                    return 2
            return run_window(core, smoke=args.gui_smoke)
    except (OSError, ValueError, RuntimeError) as exc:
        print("Studio Jaźni: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2
