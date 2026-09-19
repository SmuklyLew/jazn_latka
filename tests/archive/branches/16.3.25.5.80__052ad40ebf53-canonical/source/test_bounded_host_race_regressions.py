from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core import host_operations, runtime_supervisor


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "jazn"
    root.mkdir()
    (root / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    return root


def test_submit_does_not_clobber_worker_state_if_worker_advances_before_popen_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)

    class RacingPopen:
        def __init__(self, argv: list[str], **_kwargs: Any) -> None:
            self.pid = 41001
            operation_id = argv[argv.index("--operation-id") + 1]
            worker_root = Path(argv[argv.index("--root") + 1])
            host_operations._worker_update(
                worker_root,
                operation_id,
                status="running",
                phase="target_spawned",
                worker_pid=41001,
                command_pid=41002,
            )

    monkeypatch.setattr(host_operations.subprocess, "Popen", RacingPopen)

    result = host_operations.submit_host_operation(
        root,
        operation_id="race-op-001",
        kind="daemon-start",
    )
    persisted = host_operations.read_host_operation(root, "race-op-001")

    assert result["status"] == "running"
    assert result["phase"] == "target_spawned"
    assert result["command_pid"] == 41002
    assert result["spawned_worker_pid"] == 41001
    assert persisted is not None
    assert persisted["status"] == "running"
    assert persisted["phase"] == "target_spawned"
    assert persisted["command_pid"] == 41002


def test_duplicate_supervisor_start_does_not_overwrite_live_owner_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    state_path = runtime_supervisor.supervisor_state_path(root)
    original = {
        "state": "daemon_live",
        "supervisor_pid": 777,
        "heartbeat_at_utc": "2026-09-15T16:00:00+00:00",
    }
    runtime_supervisor._write_json_atomic(state_path, original)
    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", lambda _root: (False, 777))

    returncode = runtime_supervisor.run_supervisor(root)
    persisted = runtime_supervisor._read_json(state_path)

    assert returncode == 41
    assert persisted == original
