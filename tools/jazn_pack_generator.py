#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import Any

_SOURCE = Path(__file__).resolve().parent / "pack_generator_sources" / "jazn_pack_generator_v89.py"
_spec = importlib.util.spec_from_file_location("_jazn_pack_generator_v89", _SOURCE)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load Jaźń Pack Generator 8.9 source: {_SOURCE}")
_impl = importlib.util.module_from_spec(_spec)
sys.modules.setdefault(_spec.name, _impl)
_spec.loader.exec_module(_impl)

GENERATOR_VERSION = _impl.GENERATOR_VERSION
SETTINGS_SCHEMA = _impl.SETTINGS_SCHEMA
main = _impl.main


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


class _PublicModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name not in {"_impl"} and hasattr(_impl, name):
            setattr(_impl, name, value)


_current = sys.modules.get(__name__)
if _current is not None and not isinstance(_current, _PublicModule):
    _current.__class__ = _PublicModule


if __name__ == "__main__":
    raise SystemExit(main())
