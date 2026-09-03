from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence


def managed_python_command(python_executable: str | Path, argv: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """Return the platform-safe command/env for a managed interpreter.

    On Windows virtual environments use redirector executables. Mirror CPython's
    multiprocessing launcher pattern: execute the base interpreter and pass the
    managed interpreter through __PYVENV_LAUNCHER__.
    """
    target = str(Path(python_executable))
    env = os.environ.copy()
    env["JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE"] = "1"
    if os.name == "nt":
        base = str(getattr(sys, "_base_executable", "") or sys.executable)
        env["__PYVENV_LAUNCHER__"] = target
        return [base, *argv], env
    return [target, *argv], env


def handoff_to_managed_python(python_executable: str | Path, argv: Sequence[str], *, replace_process: bool = True) -> int:
    command, env = managed_python_command(python_executable, argv)
    if os.name != "nt" and replace_process:
        os.execve(command[0], command, env)
        raise AssertionError("os.execve returned unexpectedly")
    completed = subprocess.run(command, env=env, stdin=None, stdout=None, stderr=None, check=False)
    return int(completed.returncode)
