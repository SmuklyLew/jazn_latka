from __future__ import annotations

"""Bootstrap package without eager runtime imports.

``chatgpt_recovery`` depends on the runtime daemon. Importing it eagerly from
this package initializer creates a cycle when ``runtime_daemon`` reaches
``runtime_status -> bootstrap.contract_loader`` during its own import.  Keep
package initialization side-effect-light and wrap only the recovery submodule
loader.  The convergence overlay is installed after that submodule has fully
executed, so direct ``latka_jazn.bootstrap.chatgpt_recovery`` imports and
package-level imports receive the same behavior without observing a partially
initialized daemon module.
"""

import importlib.abc
import importlib.machinery
import sys
from types import ModuleType
from typing import Any

_TARGET = f"{__name__}.chatgpt_recovery"
_FINDER_MARKER = "_jazn_chatgpt_recovery_convergence_finder"


def _install_recovery_convergence(module: ModuleType) -> None:
    from .recovery_convergence import install

    install(module)


class _ConvergingLoader(importlib.abc.Loader):
    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped

    def create_module(self, spec: Any) -> ModuleType | None:
        create = getattr(self._wrapped, "create_module", None)
        if callable(create):
            return create(spec)
        return None

    def exec_module(self, module: ModuleType) -> None:
        execute = getattr(self._wrapped, "exec_module", None)
        if not callable(execute):
            raise ImportError("chatgpt_recovery_loader_missing_exec_module")
        execute(module)
        _install_recovery_convergence(module)
        for finder in tuple(sys.meta_path):
            if getattr(finder, _FINDER_MARKER, False):
                try:
                    sys.meta_path.remove(finder)
                except ValueError:
                    pass


class _ConvergenceFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != _TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None:
            return spec
        if not isinstance(spec.loader, _ConvergingLoader):
            spec.loader = _ConvergingLoader(spec.loader)
        return spec


_existing = sys.modules.get(_TARGET)
if isinstance(_existing, ModuleType):
    _install_recovery_convergence(_existing)
elif not any(getattr(finder, _FINDER_MARKER, False) for finder in sys.meta_path):
    _finder = _ConvergenceFinder()
    setattr(_finder, _FINDER_MARKER, True)
    sys.meta_path.insert(0, _finder)


__all__: list[str] = []
