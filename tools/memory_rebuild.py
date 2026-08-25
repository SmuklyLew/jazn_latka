#!/usr/bin/env python3
from __future__ import annotations

"""Jaźń Memory Rebuild v16.0 launcher.

The launcher is intentionally thin.  Mutating Stage4/sync operations live in
``latka_jazn.tools.memory_rebuild_stage4_v16``; read-only Test 01-03/final
profiles live in ``memory_rebuild_app.test_profiles``; canonical full Test 04
lives in ``latka_jazn.tools.memory_sqlite_test04``.
"""

from pathlib import Path
from typing import Sequence
import argparse
import importlib.util
import json
import os
import sys

TOOL_VERSION = "memory-rebuild/v16.0"
_STAGE4_COMMAND = "stage4"
_TEST04_COMMAND = "test04"
_PROFILE_ALIASES = {"test01", "test02", "test03", "final"}
_LEGACY_FLAGS = {
    "--legacy-five-db", "--config", "--write-example-config", "--no-ui",
    "--plan-only", "--all-discovered", "--source", "--self-test", "--confirm",
}


def _candidate_repo_roots() -> list[Path]:
    result: list[Path] = []
    env = os.environ.get("JAZN_ROOT", "").strip()
    if env:
        result.append(Path(env).expanduser())
    here = Path(__file__).resolve()
    result.extend([here.parent, here.parent.parent, Path.cwd(), Path.cwd().parent])
    seen: set[str] = set()
    unique: list[Path] = []
    for raw in result:
        try:
            path = raw.resolve()
        except OSError:
            path = raw.absolute()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _ensure_repo_root() -> Path:
    for root in _candidate_repo_roots():
        if (root / "latka_jazn" / "__init__.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root
    raise RuntimeError(
        "Nie znaleziono repozytorium Jaźni (latka_jazn/__init__.py). "
        "Uruchom narzędzie z katalogu repo, umieść je w tools/ albo ustaw JAZN_ROOT."
    )


ROOT = _ensure_repo_root()


def _legacy_path() -> Path:
    candidates = [
        Path(__file__).with_name("memory_rebuild_legacy_v24.py"),
        ROOT / "tools" / "memory_rebuild_legacy_v24.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def _load_legacy_module():
    path = _legacy_path()
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
    return bool(args and args[0] == "legacy") or any(item in _LEGACY_FLAGS for item in args)


def _run_legacy(args: list[str]) -> int:
    module = _load_legacy_module()
    cleaned = [item for item in args if item != "--legacy-five-db"]
    if cleaned and cleaned[0] == "legacy":
        cleaned = cleaned[1:]
    return int(module.main(cleaned))


def _profile_parser(profile: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"memory_rebuild.py {profile}",
        description=f"Read-only profile {profile.upper()} for one memory_jazn.sqlite3.",
        allow_abbrev=False,
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--baseline", action="append", type=Path, default=[])
    parser.add_argument("--acceptance-report", type=Path, help="Private/sanitized final report from canonical Test04 protocol.")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--system-acceptance", action="store_true")
    return parser


def _run_profile(profile: str, args: list[str]) -> int:
    from latka_jazn.tools.memory_rebuild_app.test_profiles import run_test_profile

    ns = _profile_parser(profile).parse_args(args)
    payload = run_test_profile(
        ns.database,
        profile,
        baselines=ns.baseline,
        full_validation=not ns.quick,
        acceptance_report=ns.acceptance_report, system_acceptance=ns.system_acceptance,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("ok") else 2


def _help() -> str:
    return f"""Jaźń Memory Rebuild {TOOL_VERSION}

Najważniejsze wejścia:
  memory_rebuild.py studio|...       główna aplikacja unified-memory
  memory_rebuild.py test01 ...       read-only Test 01
  memory_rebuild.py test02 ...       read-only Test 02
  memory_rebuild.py test03 ...       read-only Test 03
  memory_rebuild.py test04 ...       pełny kanoniczny Test 04 acceptance
  memory_rebuild.py final ...        read-only final + dowód Test04 + ledger L2/L3
  memory_rebuild.py stage4 ...       staging build/validate/sync-runtime/affect
  memory_rebuild.py legacy ...       zgodność ze starym pięciobazowym narzędziem

Test 04 jest celowo osobnym pełnym protokołem. Profil test04/final nie może
zaliczyć się wyłącznie na podstawie COUNT(*) albo deklaracji automatic_l2/l3.
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(_help())
        return 0
    if args[0] == "--version":
        print(TOOL_VERSION)
        return 0
    if args[0] == _STAGE4_COMMAND:
        from latka_jazn.tools.memory_rebuild_stage4_v16 import main as stage4_main
        return int(stage4_main(args))
    if args[0] == _TEST04_COMMAND:
        from latka_jazn.tools.memory_sqlite_test04 import main as test04_main
        return int(test04_main(args[1:]))
    if args[0] in _PROFILE_ALIASES:
        return _run_profile(args[0], args[1:])
    if _legacy_requested(args):
        return _run_legacy(args)
    from latka_jazn.tools.memory_rebuild_app.cli import main as app_main
    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
