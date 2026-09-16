from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core import host_operations
from latka_jazn.cli import build_parser


class _FakePopen:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        self.argv = list(argv)
        self.kwargs = dict(kwargs)
        self.pid = 43210
        type(self).calls.append((self.argv, self.kwargs))


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "jazn"
    root.mkdir()
    (root / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    return root


def test_host_operation_target_is_canonical_and_root_override_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    argv = host_operations.build_host_operation_target_argv(
        root,
        kind="daemon-start",
        python_executable="python-test",
    )
    assert argv[:4] == ["python-test", "-X", "utf8", str(root / "run.py")]
    assert argv[4:7] == ["start", "--root", str(root)]

    with pytest.raises(ValueError, match="root_override_forbidden"):
        host_operations.build_host_operation_target_argv(
            root,
            kind="daemon-start",
            remainder=["--root", "elsewhere"],
        )


def test_runtime_bootstrap_operation_requires_explicit_source_and_destination(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(ValueError, match="--parts-dir"):
        host_operations.build_host_operation_target_argv(root, kind="runtime-bootstrap")

    argv = host_operations.build_host_operation_target_argv(
        root,
        kind="runtime-bootstrap",
        remainder=["--", "--parts-dir", "parts", "--destination", "target"],
    )
    assert argv[4] == "runtime-bootstrap"
    assert "--parts-dir" in argv
    assert "--destination" in argv


def test_submit_is_idempotent_and_conflicting_reuse_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    _FakePopen.calls.clear()
    monkeypatch.setattr(host_operations.subprocess, "Popen", _FakePopen)

    first = host_operations.submit_host_operation(
        root,
        operation_id="chatgpt-start-001",
        kind="daemon-start",
    )
    second = host_operations.submit_host_operation(
        root,
        operation_id="chatgpt-start-001",
        kind="daemon-start",
    )
    conflict = host_operations.submit_host_operation(
        root,
        operation_id="chatgpt-start-001",
        kind="daemon-start",
        remainder=["--daemon-port", "9999"],
    )

    assert first["ok"] is True
    assert first["accepted"] is True
    assert first["created"] is True
    assert second["idempotent_replay"] is True
    assert len(_FakePopen.calls) == 1
    assert conflict["ok"] is False
    assert conflict["error_code"] == "host_operation_id_conflict"


def test_status_is_pollable_without_waiting_for_target_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    _FakePopen.calls.clear()
    monkeypatch.setattr(host_operations.subprocess, "Popen", _FakePopen)
    host_operations.submit_host_operation(
        root,
        operation_id="bootstrap-001",
        kind="runtime-bootstrap",
        remainder=["--parts-dir", "parts", "--destination", "target"],
    )

    status = host_operations.host_operation_status(root, operation_id="bootstrap-001")
    assert status["found"] is True
    assert status["pending"] is True
    assert status["terminal"] is False
    assert status["next_action"] == "poll_host_operation"
    assert "target_argv" not in status


def test_posix_detachment_uses_new_session() -> None:
    flags, options = host_operations.detached_process_options(platform="posix")
    assert flags == 0
    assert options == {"start_new_session": True}


def test_cli_exposes_bounded_operation_and_supervisor_commands() -> None:
    parser = build_parser()
    submit = parser.parse_args(
        ["host-op-submit", "--operation-id", "op-1", "--kind", "daemon-start"]
    )
    supervisor = parser.parse_args(["supervisor-plan"])
    assert submit.command == "host-op-submit"
    assert submit.operation_id == "op-1"
    assert supervisor.command == "supervisor-plan"
