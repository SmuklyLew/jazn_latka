#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the Jaźń package generator.

The public module keeps the historical v8.5 API while the independent memory
package v2 implementation lives in ``_jazn_pack_generator_memory_v2``.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import _jazn_pack_generator_memory_v2 as _impl  # noqa: E402

# Functions defined in the implementation use its module globals. Make reports
# keep the canonical public tool filename rather than the private module name.
_impl.__file__ = __file__

for _name, _value in vars(_impl).items():
    if _name not in {"__name__", "__loader__", "__package__", "__spec__", "__file__"}:
        globals()[_name] = _value

__doc__ = _impl.__doc__


def __getattr__(name: str) -> Any:
    """Preserve the complete historical module API, including private helpers."""

    if hasattr(_impl, name):
        return getattr(_impl, name)
    core = getattr(_impl, "_core", None)
    if core is not None and hasattr(core, name):
        return getattr(core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class _GeneratorPublicModule(types.ModuleType):
    """Forward test/runtime monkeypatches through both implementation layers."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        impl = self.__dict__.get("_impl")
        if impl is None or name == "_impl":
            return
        if hasattr(impl, name):
            setattr(impl, name, value)
        core = getattr(impl, "_core", None)
        if core is not None and hasattr(core, name):
            setattr(core, name, value)


_current_module = sys.modules.get(__name__)
if _current_module is not None and not isinstance(_current_module, _GeneratorPublicModule):
    _current_module.__class__ = _GeneratorPublicModule


def main(argv: Sequence[str] | None = None) -> int:
    return int(_impl.main(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(_impl._paint("\nPrzerwano przez użytkownika.", _impl.ANSI_YELLOW, stream=sys.stderr), file=sys.stderr)
        raise SystemExit(130)
    except _impl.PackError as exc:
        print(_impl._paint(f"BŁĄD: {exc}", _impl.ANSI_RED, _impl.ANSI_BOLD, stream=sys.stderr), file=sys.stderr)
        raise SystemExit(2)
