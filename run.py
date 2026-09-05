from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from latka_jazn.version import PACKAGE_VERSION_FULL


def _configure_utf8_stdio() -> None:
    """Keep direct entrypoint diagnostics machine-readable across platforms."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _version_fast_path_requested(argv: list[str]) -> bool:
    """Return whether the canonical entrypoint should answer --version directly."""

    return bool(argv and argv[0] == "--version")


_configure_utf8_stdio()

# Version discovery is a dependency-free operator contract. Keep it ahead of
# Dependency Studio bootstrap so diagnostics and package-smoke can always read
# the identity of the exact run.py tree they launched, including on Windows.
if __name__ == "__main__" and _version_fast_path_requested(sys.argv[1:]):
    print(PACKAGE_VERSION_FULL)
    raise SystemExit(0)

from latka_jazn.dependencies.runtime import (
    DependencyStudioError,
    handoff_to_managed_python,
    prepare_entrypoint_environment,
)


_ACTIVATION_COMMANDS = {
    "start",
    "restart",
    "chat",
    "chat-gpt",
    "runtime-bootstrap",
}


def _requested_command(argv: list[str]) -> str:
    if not argv:
        return "chat"
    return str(argv[0]).strip()


def _dependency_bootstrap() -> None:
    root = Path(__file__).resolve().parent
    command = _requested_command(sys.argv[1:])
    try:
        result = prepare_entrypoint_environment(root, auto_install=True)
    except DependencyStudioError as exc:
        result = {
            "ok": False,
            "state": "dependency_bootstrap_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "reexec_python": None,
        }

    target = str(result.get("reexec_python") or "").strip()
    if target:
        exit_code = handoff_to_managed_python(
            target,
            [str(Path(__file__).resolve()), *sys.argv[1:]],
            replace_process=True,
        )
        raise SystemExit(exit_code)

    if result.get("ok") is True:
        return

    os.environ["JAZN_DEPENDENCY_BOOTSTRAP_ERROR"] = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if command not in _ACTIVATION_COMMANDS:
        return

    payload = {
        "ok": False,
        "error_code": "required_python_dependencies_not_ready",
        "command": command,
        "dependency_bootstrap": result,
        "recovery_hint": (
            "Uruchom tools/Start-JaznDependencyStudio.ps1 audit, następnie download/verify/install -Offline. "
            "Automatyczny bootstrap runtime nigdy nie pobiera pakietów z sieci."
        ),
        "truth_boundary": (
            "Runtime activation is blocked because required core+archive Python dependencies are not verified. "
            "Diagnostic/operator commands remain available."
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    raise SystemExit(78)


_dependency_bootstrap()

from latka_jazn.cli import main


if __name__ == "__main__":
    argv = sys.argv[1:] or ["chat"]
    raise SystemExit(main(argv))
