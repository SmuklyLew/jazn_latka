"""Read-only, fail-closed selection of the repo-owned Python virtual environment.

The selected interpreter belongs to this checkout only.  This module neither
creates a venv nor installs packages, starts a daemon, or touches MEMORY.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def _path_key(path: str | Path) -> str:
    # Do not resolve a POSIX venv/bin/python symlink to its base interpreter.
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def private_python_path(root: Path | str) -> Path:
    directory = Path(root).resolve() / ".venv"
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def private_python_status(root: Path | str) -> dict[str, Any]:
    """Validate interpreter ownership before handoff, without any installation.

    No .venv is an ordinary compatibility case. A *present but broken* .venv
    must not silently fall back to a different interpreter.
    """
    directory = Path(root).resolve() / ".venv"
    python = private_python_path(root)
    result: dict[str, Any] = {
        "present": False,
        "ready": False,
        "current": False,
        "state": "absent",
        "python_executable": None,
    }
    if not directory.exists() and not directory.is_symlink():
        return result
    result["present"] = True
    if (not directory.is_dir() or directory.is_symlink()
            or (hasattr(directory, "is_junction") and directory.is_junction())):
        result["state"] = "unsafe_private_venv_root"
        return result
    config = directory / "pyvenv.cfg"
    if (not config.is_file() or config.is_symlink()
            or not python.is_file() or python.parent.is_symlink()):
        result["state"] = "private_venv_incomplete"
        return result

    result["python_executable"] = str(python)
    current = _path_key(sys.executable) == _path_key(python)
    result["current"] = current
    if current:
        if (_path_key(sys.prefix) != _path_key(directory)
                or _path_key(sys.base_prefix) == _path_key(directory)
                or sys.version_info < (3, 12)):
            result["state"] = "private_venv_identity_mismatch"
            return result
    else:
        probe = (
            "import json,sys;"
            "print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
            "'executable':sys.executable,'major':sys.version_info.major,"
            "'minor':sys.version_info.minor}))"
        )
        try:
            completed = subprocess.run(
                [str(python), "-I", "-X", "utf8", "-c", probe],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=10, check=False,
            )
            if completed.returncode or len(completed.stdout) > 2048:
                result["state"] = "private_venv_probe_failed"
                return result
            payload = json.loads(completed.stdout)
            if (not isinstance(payload, dict)
                    or _path_key(str(payload.get("prefix") or "")) != _path_key(directory)
                    or _path_key(str(payload.get("executable") or "")) != _path_key(python)
                    or _path_key(str(payload.get("base_prefix") or "")) == _path_key(directory)
                    or (int(payload.get("major", 0)), int(payload.get("minor", 0))) < (3, 12)):
                result["state"] = "private_venv_identity_mismatch"
                return result
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            result["state"] = "private_venv_probe_failed"
            return result
    result["state"] = "ready"
    result["ready"] = True
    return result


def selected_private_python(root: Path | str) -> str | None:
    """Return the validated private interpreter, or fail for a broken venv."""
    status = private_python_status(root)
    if status["present"] and not status["ready"]:
        raise RuntimeError(str(status["state"]))
    return str(status["python_executable"]) if status["ready"] else None
