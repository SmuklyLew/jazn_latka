from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core import host_operations
from latka_jazn.core.host_operation_retry import (
    MEMORY_CONVERGE_MAX_ATTEMPTS,
    classify_host_operation_retry,
    retry_policy_for_kind,
)


def test_memory_converge_pending_retries_are_bounded() -> None:
    policy = retry_policy_for_kind("memory-converge")
    assert policy.max_attempts == MEMORY_CONVERGE_MAX_ATTEMPTS == 3
    assert policy.backoff_seconds == (1.0, 2.0)

    first = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=1,
    )
    assert first.retry_allowed is True
    assert first.error_code == "memory_converge_pending"
    assert first.backoff_seconds == 1.0

    second = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=2,
    )
    assert second.retry_allowed is True
    assert second.backoff_seconds == 2.0

    exhausted = classify_host_operation_retry(
        kind="memory-converge",
        returncode=75,
        attempt=3,
    )
    assert exhausted.retry_allowed is False
    assert exhausted.error_code == "memory_converge_pending_retry_exhausted"


def test_memory_converge_terminal_failure_is_never_blindly_retried() -> None:
    decision = classify_host_operation_retry(
        kind="memory-converge",
        returncode=17,
        attempt=1,
    )
    assert decision.retry_allowed is False
    assert decision.error_code is None
    assert decision.backoff_seconds is None


def test_other_host_operations_never_inherit_memory_converge_retry() -> None:
    decision = classify_host_operation_retry(
        kind="daemon-start",
        returncode=75,
        attempt=1,
    )
    assert decision.retry_allowed is False
    assert retry_policy_for_kind("daemon-start").max_attempts == 1


def test_memory_converge_worker_retries_same_operation_id_until_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "jazn"
    root.mkdir()
    (root / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    class SubmitPopen:
        def __init__(self, _argv: list[str], **_kwargs: Any) -> None:
            self.pid = 41001

    monkeypatch.setattr(host_operations.subprocess, "Popen", SubmitPopen)
    submitted = host_operations.submit_host_operation(
        root,
        operation_id="memory-converge-retry-001",
        kind="memory-converge",
        remainder=["--parts-dir", "parts"],
    )
    assert submitted["accepted"] is True

    returncodes = [75, 75, 0]
    pids: list[int] = []
    sleeps: list[float] = []

    class TargetPopen:
        def __init__(self, _argv: list[str], **_kwargs: Any) -> None:
            self.pid = 42000 + len(pids) + 1
            pids.append(self.pid)

        def wait(self, timeout: float | None = None) -> int:
            assert timeout is None
            return returncodes.pop(0)

    monkeypatch.setattr(host_operations.subprocess, "Popen", TargetPopen)
    monkeypatch.setattr(host_operations.time, "sleep", lambda seconds: sleeps.append(float(seconds)))

    rc = host_operations.run_host_operation_worker(
        root,
        operation_id="memory-converge-retry-001",
    )
    persisted = host_operations.read_host_operation(
        root,
        "memory-converge-retry-001",
    )

    assert rc == 0
    assert persisted is not None
    assert persisted["operation_id"] == "memory-converge-retry-001"
    assert persisted["status"] == "completed"
    assert persisted["phase"] == "target_completed"
    assert persisted["attempt"] == 3
    assert persisted["last_returncode"] == 0
    assert persisted["max_attempts"] == 3
    assert len(pids) == 3
    assert sleeps == [1.0, 2.0]
