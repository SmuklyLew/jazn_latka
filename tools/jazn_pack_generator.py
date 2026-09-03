#!/usr/bin/env python3
r"""Jaźń / Łatka Pack Generator v10.0.1 public launcher.

Naprawiony generator dystrybucji Jaźni.

Uruchomienie::

    py -X utf8 .\tools\jazn_pack_generator.py

Tryby interfejsu są wyłącznie terminalowe:
- tekstowy,
- kursorowy,
- studio-terminal.

Domyślny katalog paczek na Windows::

    D:\.AI\jazn_packages
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

_TOOL_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _TOOL_ROOT.parent
_SOURCE_ROOT = _TOOL_ROOT / "pack_generator_sources"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Jaźń Pack Generator source: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


_impl = _load("_jazn_pack_generator_v1001", _SOURCE_ROOT / "jazn_pack_generator_v1001.py")
_ui = _load("_jazn_pack_generator_v1001_ui", _SOURCE_ROOT / "jazn_pack_generator_v1001_ui.py")
_ui.bind(_impl)

GENERATOR_VERSION = _impl.GENERATOR_VERSION
GENERATOR_TITLE = _impl.GENERATOR_TITLE
SETTINGS_SCHEMA = _impl.SETTINGS_SCHEMA
UI_MODE_CHOICES = _ui.UI_MODE_CHOICES
UI_MODE_LABELS = _ui.UI_MODE_LABELS
main = _ui.main


def __getattr__(name: str) -> Any:
    if hasattr(_ui, name):
        return getattr(_ui, name)
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
