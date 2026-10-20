from __future__ import annotations

"""Bounded, local-only operator subprocess execution through Jaźń main.py.

This capability does not create a process executor inside ChatGPT.  It executes
only predefined, read-only public commands on a host that *already* permits
child processes.  It is deliberately not registered as a remote MCP tool.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Final

from latka_jazn.version import PACKAGE_VERSION_FULL

SCHEMA_VERSION: Final = "jazn_operator_executor/v1"
# Argument vectors, not shell fragments. Never append untrusted arguments.
READ_ONLY_ACTIONS: Final[dict[str, tuple[str, ...]]] = {
    "version": ("--version",),
    "status": ("status", "--json"),
    "doctor": ("doctor", "--json"),
    "model-status": ("model-status", "--json"),
}
MAX_TIMEOUT_SECONDS: Final = 30.0
MAX_VISIBLE_OUTPUT_BYTES: Final = 32 * 1024


def _capture(handle: Any, *, include_output: bool) -> dict[str, Any]:
    handle.flush()
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    handle.seek(0)
    digest = hashlib.sha256()
    sample = bytearray()
    while data := handle.read(64 * 1024):
        digest.update(data)
        if include_output and len(sample) < MAX_VISIBLE_OUTPUT_BYTES:
            sample.extend(data[: MAX_VISIBLE_OUTPUT_BYTES - len(sample)])
    return {
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "truncated": bool(include_output and size > MAX_VISIBLE_OUTPUT_BYTES),
        "text": sample.decode("utf-8", errors="replace") if include_output else None,
    }


def execute_operator_action(
    action: str,
    *,
    timeout_seconds: float = 10.0,
    include_output: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Run a fixed read-only Jaźń CLI action using a bounded child process.

    A successful child is evidence only for local process execution and the
    selected command's exit code. It is not evidence of MCP connectivity,
    activated MEMORY, daemon readiness or accepted visible turn finalization.
    """
    if action not in READ_ONLY_ACTIONS:
        raise ValueError("operator_executor_action_not_allowlisted")
    if not (0.1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise ValueError("operator_executor_timeout_out_of_bounds")

    system_root = (root or Path(__file__).resolve().parents[2]).resolve()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "action": action,
        "process_created": False,
        "command_completed": False,
        "ok": False,
        "returncode": None,
        "error_code": None,
        "stdout": None,
        "stderr": None,
        "truth_boundary": (
            "Local executor and command result only; no ChatGPT host capability, "
            "runtime readiness, MEMORY recall, or accepted visible turn is inferred."
        ),
    }
    launcher = system_root / "run.py"
    if not launcher.is_file():
        result["error_code"] = "canonical_launcher_missing"
        return result

    argv = [sys.executable, "-X", "utf8", str(launcher), *READ_ONLY_ACTIONS[action]]
    creationflags = 0
    popen_kwargs: dict[str, Any] = {"start_new_session": True}
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        popen_kwargs = {}

    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(system_root),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=creationflags,
                **popen_kwargs,
            )
        except OSError as exc:
            result["error_code"] = "host_process_spawn_failed"
            result["spawn_error_type"] = type(exc).__name__
            return result
        result["process_created"] = True
        result["child_pid"] = proc.pid
        try:
            result["returncode"] = proc.wait(timeout=timeout_seconds)
            result["command_completed"] = True
            if result["returncode"] == 0:
                result["ok"] = True
            else:
                result["error_code"] = "operator_action_failed"
        except subprocess.TimeoutExpired:
            result["error_code"] = "operator_action_timeout"
            proc.kill()
            proc.wait()
        result["stdout"] = _capture(stdout, include_output=include_output)
        result["stderr"] = _capture(stderr, include_output=include_output)
    return result


def run_operator_executor_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py operator-exec", allow_abbrev=False)
    parser.add_argument("--action", choices=sorted(READ_ONLY_ACTIONS), required=True)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--include-output", action="store_true")
    parser.add_argument("--json", action="store_true", help="Machine-readable result (always JSON).")
    ns = parser.parse_args(argv)
    try:
        payload = execute_operator_action(
            ns.action, timeout_seconds=ns.timeout_seconds, include_output=ns.include_output
        )
    except ValueError as exc:
        payload = {"ok": False, "schema_version": SCHEMA_VERSION, "error_code": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(run_operator_executor_cli())
