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
    "reload",
    "chat",
    "chat-gpt",
    "chat-ollama",
    "runtime-bootstrap",
    "__daemon-run-hotfix",
}


def _requested_command(argv: list[str]) -> str:
    if not argv:
        return "chat"
    return str(argv[0]).strip()


def _normalize_operator_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == "chat-ollama":
        return ["--chat-ollama", *argv[1:]]
    return list(argv)


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


if __name__ == "__main__" and _requested_command(sys.argv[1:]) == "host-preflight":
    from latka_jazn.bootstrap.chatgpt_host_preflight import run_host_preflight_cli

    raise SystemExit(run_host_preflight_cli(sys.argv[2:]))


_dependency_bootstrap()

if __name__ == "__main__" and _requested_command(sys.argv[1:]) in {"status", "doctor"}:
    from latka_jazn.cli_commands.cognitive_status_overlay import install_cognitive_status_overlay

    install_cognitive_status_overlay()

from latka_jazn.core.runtime_daemon_lifecycle_hotfix import install_runtime_daemon_lifecycle_hotfix

install_runtime_daemon_lifecycle_hotfix()

if __name__ == "__main__" and _requested_command(sys.argv[1:]) == "__daemon-run-hotfix":
    from main import main as _legacy_runtime_main

    raise SystemExit(_legacy_runtime_main(sys.argv[2:]))

if __name__ == "__main__" and _requested_command(sys.argv[1:]) in {"restart", "reload"}:
    import argparse
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.runtime_lifecycle import reload_daemon, restart_daemon

    _parser = argparse.ArgumentParser(prog=f"run.py {sys.argv[1]}", allow_abbrev=False)
    _parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    if sys.argv[1] == "reload":
        _parser.add_argument("--target-root", type=Path, required=True)
    _parser.add_argument("--daemon-host", default="127.0.0.1")
    _parser.add_argument("--daemon-port", type=int, default=8787)
    _parser.add_argument("--startup-timeout", type=float, default=12.0)
    _parser.add_argument("--stop-timeout", type=float, default=5.0)
    _parser.add_argument("--json", action="store_true")
    _ns = _parser.parse_args(sys.argv[2:])
    _cfg = JaznConfig(root=_ns.root.resolve())
    if sys.argv[1] == "restart":
        _payload = restart_daemon(_cfg, host=_ns.daemon_host, port=_ns.daemon_port, startup_timeout=_ns.startup_timeout, stop_timeout=_ns.stop_timeout)
    else:
        _payload = reload_daemon(_cfg, target_root=_ns.target_root.resolve(), host=_ns.daemon_host, port=_ns.daemon_port, startup_timeout=_ns.startup_timeout, stop_timeout=_ns.stop_timeout)
    print(json.dumps(_payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if _payload.get("ok") else 1)

if __name__ == "__main__" and _requested_command(sys.argv[1:]) == "runtime-bootstrap":
    from latka_jazn.cli import build_parser as _build_cli_parser
    from latka_jazn.bootstrap.runtime_bootstrap_v50 import bootstrap_and_reload

    _ns = _build_cli_parser().parse_args(sys.argv[1:])
    _payload = bootstrap_and_reload(
        operator_root=Path(__file__).resolve().parent,
        parts_dir=_ns.parts_dir, destination=_ns.destination, zip_name=_ns.zip_name,
        memory_zip_name=_ns.memory_zip_name, no_auto_memory=bool(_ns.no_auto_memory),
        work_dir=_ns.work_dir, time_budget_seconds=float(_ns.time_budget_seconds),
        no_crc=bool(_ns.no_crc), force_reextract=bool(_ns.force_reextract),
        no_start_daemon=bool(_ns.no_start_daemon),
    )
    print(json.dumps(_payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(int(_payload.get("exit_code", 0 if _payload.get("ok") else 1)))

if __name__ == "__main__" and _requested_command(sys.argv[1:]) == "host-finalize":
    from latka_jazn.cli_commands.host import run_host_finalize_cli

    raise SystemExit(
        run_host_finalize_cli(
            sys.argv[2:],
            default_root=Path(__file__).resolve().parent,
        )
    )

from latka_jazn.core.turn_authority_runtime_overlay import install_turn_authority_runtime_overlay

install_turn_authority_runtime_overlay()

from latka_jazn.cli import main


if __name__ == "__main__":
    argv = _normalize_operator_argv(sys.argv[1:] or ["chat"])
    raise SystemExit(main(argv))
