#!/usr/bin/env python3
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


_impl = _load("_jazn_pack_generator_v89", _ROOT / "jazn_pack_generator_v89.py")
_ui = _load("_jazn_pack_generator_v89_ui", _ROOT / "jazn_pack_generator_v89_ui.py")
_ui.bind(_impl)

GENERATOR_VERSION = _impl.GENERATOR_VERSION
SETTINGS_SCHEMA = _impl.SETTINGS_SCHEMA
main = _ui.main


def __getattr__(name: str) -> Any:
    if hasattr(_ui, name):
        return getattr(_ui, name)
    return getattr(_impl, name)


class _PublicModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name not in {"_impl", "_ui"}:
            if hasattr(_ui, name):
                setattr(_ui, name, value)
            if hasattr(_impl, name):
                setattr(_impl, name, value)


_current = sys.modules.get(__name__)
if _current is not None and not isinstance(_current, _PublicModule):
    _current.__class__ = _PublicModule


if __name__ == "__main__":
    raise SystemExit(main())
