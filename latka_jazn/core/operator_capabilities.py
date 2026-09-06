from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence


def _bounded(command: Sequence[str], *, cwd: Path | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def git_operator_capability(root: Path | str) -> dict[str, Any]:
    project_root = Path(root).resolve()
    executable = shutil.which("git")
    probe = _bounded([executable, "-C", str(project_root), "rev-parse", "--is-inside-work-tree"]) if executable else {"ok": False}
    return {
        "schema_version": "jazn_operator_capability/v1",
        "capability": "git",
        "available": bool(executable),
        "repository_detected": probe.get("ok") is True and probe.get("stdout") == "true",
        "executable": executable,
        "probe": probe,
        "operator_only": True,
        "live_daemon_mutation_allowed": False,
        "automatic_mutation_allowed": False,
        "allowed_operator_roles": ["provenance", "release_staging", "explicit_update_staging"],
        "forbidden_live_daemon_actions": ["pull", "checkout", "reset", "merge", "push"],
        "truth_boundary": "Git is an explicit operator/release capability; a live Jaźń daemon is not authorized to mutate its source tree automatically.",
    }


def pip_operator_capability() -> dict[str, Any]:
    probe = _bounded([sys.executable, "-m", "pip", "--version"])
    return {
        "schema_version": "jazn_operator_capability/v1",
        "capability": "pip",
        "available": probe.get("ok") is True,
        "probe": probe,
        "operator_only": True,
        "delegated_to": "latka_jazn.tools.dependency_studio",
        "live_daemon_mutation_allowed": False,
        "runtime_network_allowed": False,
        "runtime_install_policy": "verified_local_wheelhouse_hash_locked_binary_only",
        "operator_network_actions": ["dependency-studio download", "dependency-studio update"],
        "forbidden_runtime_inputs": ["arbitrary requirement string", "git+ URL", "editable install", "sdist fallback", "extra index"],
        "truth_boundary": "pip is a bounded Dependency Studio backend, not a raw command capability exposed to the live daemon.",
    }


def operator_capability_report(root: Path | str) -> dict[str, Any]:
    return {
        "schema_version": "jazn_operator_capabilities/v1",
        "git": git_operator_capability(root),
        "pip": pip_operator_capability(),
        "blocks_runtime_core": False,
    }
