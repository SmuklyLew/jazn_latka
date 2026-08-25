from __future__ import annotations

"""Composition root for both canonical and compatibility launchers."""

from pathlib import Path
from typing import Sequence
import argparse
import importlib.util
import json
import sys

from .config import (
    LEGACY_FLAGS, PROFILE_ALIASES, STAGE4_COMMAND, TEST04_COMMAND, TOOL_VERSION,
    resolve_repo_root,
)


def _legacy_path(root: Path, entrypoint: Path) -> Path:
    candidates = (
        entrypoint.with_name("memory_rebuild_legacy_v24.py"),
        root / "tools" / "memory_rebuild_legacy_v24.py",
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


def _load_legacy_module(root: Path, entrypoint: Path):
    path = _legacy_path(root, entrypoint)
    if not path.is_file():
        raise FileNotFoundError(path)
    name = "_jazn_memory_rebuild_legacy_v24_compat"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nie można wczytać zgodnościowego narzędzia: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _legacy_requested(args: list[str]) -> bool:
    return bool(args and args[0] == "legacy") or any(item in LEGACY_FLAGS for item in args)


def _profile_parser(profile: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"rebuild_memory.py {profile}",
        description=f"Read-only profile {profile.upper()} for one memory_jazn.sqlite3.",
        allow_abbrev=False,
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--baseline", action="append", type=Path, default=[])
    parser.add_argument("--acceptance-report", type=Path)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--system-acceptance", action="store_true")
    return parser


def _run_profile(profile: str, args: list[str]) -> int:
    from .test_profiles import run_test_profile

    ns = _profile_parser(profile).parse_args(args)
    payload = run_test_profile(
        ns.database,
        profile,
        baselines=ns.baseline,
        full_validation=not ns.quick,
        acceptance_report=ns.acceptance_report,
        system_acceptance=ns.system_acceptance,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("ok") else 2


def help_text() -> str:
    return f"""Jaźń Memory Rebuild {TOOL_VERSION}

Kanoniczne uruchomienie: tools/rebuild_memory.py
Zgodność wsteczna:     tools/memory_rebuild.py

Najważniejsze wejścia:
  rebuild_memory.py studio|...       główna aplikacja unified-memory
  rebuild_memory.py unified-import   wspólny model L0 + adaptery formatów
  rebuild_memory.py recall           typowane wyszukiwanie temporalne z proweniencją
  rebuild_memory.py test01..test04   profile walidacyjne
  rebuild_memory.py final            final + dowód Test04 + ledger L2/L3
  rebuild_memory.py stage4           staging build/validate/sync-runtime/affect
  rebuild_memory.py legacy           zgodność ze starym pięciobazowym narzędziem

FTS5 jest obowiązkowe. Embeddingi są opcjonalne. Import nie aktywuje pamięci
i nie promuje automatycznie do L2/L3.
"""


def main(argv: Sequence[str] | None = None, *, entrypoint: str | Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    script = Path(entrypoint or sys.argv[0]).resolve()
    root = resolve_repo_root(script)
    if not args or args[0] in {"-h", "--help"}:
        print(help_text())
        return 0
    if args[0] == "--version":
        print(TOOL_VERSION)
        return 0
    if args[0] == STAGE4_COMMAND:
        from latka_jazn.tools.memory_rebuild_stage4_v16 import main as stage4_main
        return int(stage4_main(args))
    if args[0] == TEST04_COMMAND:
        from latka_jazn.tools.memory_sqlite_test04 import main as test04_main
        return int(test04_main(args[1:]))
    if args[0] in PROFILE_ALIASES:
        return _run_profile(args[0], args[1:])
    if _legacy_requested(args):
        module = _load_legacy_module(root, script)
        cleaned = [item for item in args if item != "--legacy-five-db"]
        if cleaned and cleaned[0] == "legacy":
            cleaned = cleaned[1:]
        return int(module.main(cleaned))
    from .cli import main as app_main
    return int(app_main(args))


__all__ = ["help_text", "main"]
