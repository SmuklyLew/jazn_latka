"""Stable contract: local bounded actions, evidence and fail-closed behavior."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.runtime import operator_executor as executor

ROOT = Path(__file__).resolve().parents[1]


def test_allowlist_rejects_shell_and_unknown_action() -> None:
    with pytest.raises(ValueError, match="not_allowlisted"):
        executor.execute_operator_action("status; rm -rf /", root=ROOT)
    assert set(executor.READ_ONLY_ACTIONS) == {"version", "status", "doctor", "model-status"}


def test_timeout_bounds_fail_closed() -> None:
    for timeout in (-1, 0, 0.09, 31, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="timeout_out_of_bounds"):
            executor.execute_operator_action("version", timeout_seconds=timeout, root=ROOT)


def test_missing_launcher_is_not_spawned(tmp_path: Path) -> None:
    result = executor.execute_operator_action("version", root=tmp_path)
    assert result["ok"] is False
    assert result["process_created"] is False
    assert result["error_code"] == "canonical_launcher_missing"


def test_canonical_version_executes_on_current_host() -> None:
    result = executor.execute_operator_action("version", include_output=True, root=ROOT)
    assert result["ok"] is True
    assert result["process_created"] is True
    assert result["command_completed"] is True
    assert result["returncode"] == 0
    assert result["stdout"]["text"].strip() == executor.PACKAGE_VERSION_FULL
    assert "ChatGPT" in result["truth_boundary"]


def test_main_first_public_dispatch_with_fixed_action() -> None:
    process = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "run.py"), "operator-exec", "--action", "version", "--json"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["process_created"] is True
    assert result["ok"] is True
    assert result["action"] == "version"


def test_spawn_failure_does_not_promote_executor_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("no host permission")

    monkeypatch.setattr(executor.subprocess, "Popen", fail)
    result = executor.execute_operator_action("version", root=ROOT)
    assert result["error_code"] == "host_process_spawn_failed"
    assert result["spawn_error_type"] == "OSError"
    assert result["process_created"] is False


def test_failed_subprocess_is_spawned_but_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenProcess:
        pid = 42
        def wait(self, *, timeout: float | None = None) -> int:
            return 13
    monkeypatch.setattr(executor.subprocess, "Popen", lambda *a, **kw: BrokenProcess())
    result = executor.execute_operator_action("version", root=ROOT)
    assert result["process_created"] is True
    assert result["command_completed"] is True
    assert result["ok"] is False
    assert result["returncode"] == 13


def test_timed_out_subprocess_is_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowProcess:
        pid = 43
        killed = False
        def wait(self, *, timeout: float | None = None) -> int:
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="python", timeout=timeout)
            return -9
        def kill(self) -> None:
            self.killed = True
    proc = SlowProcess()
    monkeypatch.setattr(executor.subprocess, "Popen", lambda *a, **kw: proc)
    result = executor.execute_operator_action("version", root=ROOT)
    assert result["error_code"] == "operator_action_timeout"
    assert result["process_created"] is True
    assert result["command_completed"] is False
    assert proc.killed is True


def test_capture_is_bounded_and_hashes_full_data() -> None:
    import hashlib
    import io
    payload = b"x" * (executor.MAX_VISIBLE_OUTPUT_BYTES + 1024)
    with io.BytesIO(payload) as stream:
        result = executor._capture(stream, include_output=True)
    assert result["size_bytes"] == len(payload)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["truncated"] is True
    assert len(result["text"]) == executor.MAX_VISIBLE_OUTPUT_BYTES
