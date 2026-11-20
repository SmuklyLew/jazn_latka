"""Opt-in-by-interactive-launch, fail-open GUI observer of a verified Jaźń start.

The daemon itself NEVER owns or starts an interactive monitor. Headless CI and
non-interactive automation leave GUI processes untouched. No runtime stop/restart.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping


def may_autostart_monitor(
    root: Path,
    *,
    daemon_host: str,
    daemon_port: int,
    env: Mapping[str, str] | None = None,
    interactive: bool | None = None,
    gui_available: bool | None = None,
    spawn: Callable[..., Any] | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Start one visible GUI client; its own QLockFile prevents duplicates.

    The returned process PID proves a launch attempt, not successful Qt display.
    Absence of GUI capability never changes the daemon's successful exit code.
    """
    environment = os.environ if env is None else env
    platform_name = os.name if platform is None else platform
    if environment.get("JAZN_MONITOR_AUTOSTART", "").lower() in {"off", "false", "0"}:
        return {"state": "disabled", "reason": "operator_preference"}
    if (environment.get("CI") or environment.get("GITHUB_ACTIONS")
            or environment.get("PYTEST_CURRENT_TEST")
            or environment.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}):
        return {"state": "skipped", "reason": "headless_or_test"}
    if interactive is None:
        interactive = bool(sys.stdin.isatty() and sys.stdout.isatty())
    if not interactive:
        return {"state": "skipped", "reason": "non_interactive"}
    if platform_name == "nt":
        # Only desktop user-mode processes create a visible Qt window.
        pass
    elif not (environment.get("DISPLAY") or environment.get("WAYLAND_DISPLAY")):
        return {"state": "skipped", "reason": "no_desktop"}
    if daemon_host not in {"127.0.0.1", "localhost"} or type(daemon_port) is not int or not 1 <= daemon_port <= 65535:
        return {"state": "skipped", "reason": "nonlocal_or_invalid_daemon"}
    if gui_available is None:
        gui_available = importlib.util.find_spec("PySide6") is not None
    if not gui_available:
        return {"state": "unavailable", "reason": "pyside6_not_installed"}

    verified_root = root.resolve()
    if not (verified_root / "run.py").is_file():
        return {"state": "unavailable", "reason": "root_without_launcher"}
    script = verified_root / "jazn_monitor.py"
    if not script.is_file():
        return {"state": "unavailable", "reason": "monitor_entrypoint_missing"}
    python_bin = Path(sys.executable)
    if platform_name == "nt":
        pythonw = python_bin.with_name("pythonw.exe")
        if pythonw.is_file():
            python_bin = pythonw
    command = [
        str(python_bin), "-B", "-X", "utf8", str(script),
        "--root", str(verified_root), "--daemon-port", str(daemon_port),
    ]
    options: dict[str, Any] = {
        "cwd": str(verified_root), "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if platform_name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        spawned = (spawn or subprocess.Popen)(command, **options)
    except (OSError, ValueError) as exc:
        return {"state": "unavailable", "reason": type(exc).__name__}
    return {
        "state": "spawned", "pid": getattr(spawned, "pid", None),
        "visible_window_verified": False, "singleton_owned_by_gui": True,
    }
