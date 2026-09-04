from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from .contract import PythonRuntimeContractError


def sanitized_runtime_environment(
    runtime_root: Path | str,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(base if base is not None else os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    ):
        environment.pop(name, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["JAZN_PYTHON_RUNTIME_ACTIVE"] = "1"
    environment["JAZN_PYTHON_RUNTIME_ROOT"] = str(Path(runtime_root).resolve())
    return environment


def build_runtime_launch_command(
    python_executable: Path | str,
    app_root: Path | str,
    runtime_root: Path | str,
    argv: Sequence[str] = (),
    *,
    packages_relative_path: str = "packages",
) -> list[str]:
    interpreter = Path(python_executable).resolve()
    runtime = Path(runtime_root).resolve()
    app = Path(app_root).resolve()
    try:
        interpreter.relative_to(runtime)
    except ValueError as exc:
        raise PythonRuntimeContractError("runtime_python_outside_materialized_runtime") from exc
    bootstrap = app / "jazn_runtime_bootstrap.py"
    if not bootstrap.is_file():
        raise PythonRuntimeContractError(f"jazn_runtime_bootstrap_missing:{bootstrap}")
    return [
        str(interpreter),
        "-I",
        "-X",
        "utf8",
        str(bootstrap),
        "--app-root",
        str(app),
        "--runtime-root",
        str(runtime),
        "--packages-relative-path",
        str(packages_relative_path),
        "--",
        *[str(item) for item in argv],
    ]
