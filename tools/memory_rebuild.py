#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Sequence
import importlib.util
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


def _legacy_path() -> Path:
    return Path(__file__).with_name("memory_rebuild_legacy_v24.py")


def _load_legacy_module():
    module_name = "_jazn_memory_rebuild_legacy_v24_compat"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    path = _legacy_path()
    if not path.is_file():
        raise FileNotFoundError(f"Brak zgodnościowego narzędzia: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nie można wczytać zgodnościowego narzędzia: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_LEGACY_MODULE = _load_legacy_module()

# Zachowaj publiczny i historycznie testowany kontrakt modułu starego narzędzia.
# Nowy launcher nie nadpisuje własnego main/ROOT, ale udostępnia m.in.
# TOOL_VERSION, ToolState, _ordered_restore_sources i _memory_boundary_rows.
for _name in dir(_LEGACY_MODULE):
    if _name.startswith("__") or _name in {"main", "ROOT", "self_test"}:
        continue
    globals().setdefault(_name, getattr(_LEGACY_MODULE, _name))


def self_test(state):
    """Uruchom historyczny autotest, zachowując kanoniczną nazwę launchera."""
    report = _LEGACY_MODULE.self_test(state)
    for check in report.get("checks", []):
        if check.get("name") == "canonical_filename":
            check["ok"] = Path(__file__).name == "memory_rebuild.py"
            check["value"] = Path(__file__).name
            break
    report["ok"] = all(bool(item.get("ok")) for item in report.get("checks", []))
    return report


def _legacy_requested(args: list[str]) -> bool:
    if args and args[0] == "legacy":
        return True
    return any(item in _LEGACY_FLAGS for item in args)


def _run_legacy(args: list[str]) -> int:
    cleaned = [item for item in args if item != "--legacy-five-db"]
    if cleaned and cleaned[0] == "legacy":
        cleaned = cleaned[1:]
    if "--self-test" in cleaned:
        parsed_args = _LEGACY_MODULE.build_parser().parse_args(cleaned)
        state = _LEGACY_MODULE._settings_from_args(
            parsed_args,
            _LEGACY_MODULE.load_state(parsed_args.config),
        )
        state.ui_mode = "text"
        return 0 if self_test(state).get("ok") else 2
    return int(_LEGACY_MODULE.main(cleaned))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _legacy_requested(args):
        return _run_legacy(args)
    from latka_jazn.tools.memory_rebuild_app.cli import main as app_main
    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
