#!/usr/bin/env python3
"""Jaźń / Łatka Pack Generator v8.9 public launcher.

Canonical CLI entrypoint examples::

    py -X utf8 .\tools\jazn_pack_generator.py

The historical two-file v8.8 implementation remains bundled privately behind
the v8.9 repository-native distribution layer. The default Windows package
output remains D:\.AI\.packages when the launcher is started from D:\.AI\jazn_latka.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import Any

_ROOT = Path(__file__).resolve().parent / "pack_generator_sources"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Jaźń Pack Generator source: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


# A direct spec load of this launcher does not import the real ``tools``
# namespace package first. The historical v8.8 standalone bundle creates a
# synthetic ``tools`` package while initializing its embedded helpers. Remember
# the pre-load state so that synthetic package cannot shadow the repository's
# real ``tools.jazn_pack_generator`` on the next ordinary import.
_tools_module_before_impl_load = sys.modules.get("tools")
_impl = _load("_jazn_pack_generator_v89", _ROOT / "jazn_pack_generator_v89.py")
if _tools_module_before_impl_load is None:
    sys.modules.pop("tools", None)

_ui = _load("_jazn_pack_generator_v89_ui", _ROOT / "jazn_pack_generator_v89_ui.py")
_ui.bind(_impl)

GENERATOR_VERSION = _impl.GENERATOR_VERSION
SETTINGS_SCHEMA = _impl.SETTINGS_SCHEMA
main = _ui.main


def __getattr__(name: str) -> Any:
    if hasattr(_ui, name):
        return getattr(_ui, name)
    return getattr(_impl, name)


def _public_override_targets(name: str) -> tuple[object, ...]:
    """Return the concrete modules that own globals used by public functions.

    Generator 8.9 intentionally delegates the mature packaging implementation
    to the private v8.8 bundle. Functions obtained through ``__getattr__`` keep
    the globals of that legacy module, so a public monkeypatch must reach that
    owner as well as the v8.9 facade. This is also the compatibility contract
    used by embedders that replace filesystem/archive primitives for testing.
    """

    targets: list[object] = [_ui, _impl]
    legacy = getattr(_impl, "legacy", None)
    if legacy is not None:
        targets.append(legacy)
        legacy_impl = getattr(legacy, "_impl", None)
        if legacy_impl is not None:
            targets.append(legacy_impl)
            legacy_core = getattr(legacy_impl, "_core", None)
            if legacy_core is not None:
                targets.append(legacy_core)
    unique: list[object] = []
    seen: set[int] = set()
    for target in targets:
        marker = id(target)
        if marker in seen or not hasattr(target, name):
            continue
        seen.add(marker)
        unique.append(target)
    return tuple(unique)


class _PublicModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in {"_impl", "_ui"}:
            return
        for target in _public_override_targets(name):
            setattr(target, name, value)


_current = sys.modules.get(__name__)
if _current is not None and not isinstance(_current, _PublicModule):
    _current.__class__ = _PublicModule


if __name__ == "__main__":
    raise SystemExit(main())
