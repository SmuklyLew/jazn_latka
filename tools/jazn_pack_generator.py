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
import types
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
_compat = _load(
    "_jazn_pack_generator_v1001_compat",
    _SOURCE_ROOT / "jazn_pack_generator_v1001_compat.py",
)
_compat.install(_impl)
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
    if hasattr(_impl, name):
        return getattr(_impl, name)
    return getattr(_compat, name)


class _PublicModule(types.ModuleType):
    """Keep monkeypatch/backward-compatibility overrides visible to v10 internals.

    Historical generator tests and external callers patch public launcher
    attributes.  The v10 split-source launcher therefore mirrors writes into
    the native implementation/compatibility modules when those attributes are
    defined there, without loading any retired v8/v9 runtime implementation.
    """

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name.startswith("__") or name in {
            "_impl", "_compat", "_ui", "GENERATOR_VERSION", "GENERATOR_TITLE",
            "SETTINGS_SCHEMA", "UI_MODE_CHOICES", "UI_MODE_LABELS", "main",
        }:
            return
        for target in (_impl, _compat, _ui):
            if hasattr(target, name):
                setattr(target, name, value)


sys.modules[__name__].__class__ = _PublicModule


if __name__ == "__main__":
    raise SystemExit(main())
