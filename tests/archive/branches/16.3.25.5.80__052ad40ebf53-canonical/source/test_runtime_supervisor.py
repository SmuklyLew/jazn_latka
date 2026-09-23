from __future__ import annotations

from pathlib import Path

from latka_jazn.core.runtime_supervisor import (
    bounded_restart_backoff_seconds,
    supervisor_installation_plan,
    supervisor_status,
)


def test_supervisor_backoff_is_bounded_and_increases_before_cap(tmp_path: Path) -> None:
    root = tmp_path / "jazn"
    root.mkdir()
    first = bounded_restart_backoff_seconds(root, 1, base_seconds=2.0, max_seconds=30.0)
    later = bounded_restart_backoff_seconds(root, 4, base_seconds=2.0, max_seconds=30.0)
    capped = bounded_restart_backoff_seconds(root, 100, base_seconds=2.0, max_seconds=30.0)
    assert 0.1 <= first <= 2.4
    assert later > first
    assert capped <= 30.0


def test_windows_supervisor_plan_matches_task_scheduler_recovery_contract(tmp_path: Path) -> None:
    root = tmp_path / "jazn"
    root.mkdir()
    (root / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    plan = supervisor_installation_plan(root, python_executable="python-test")

    assert plan["supervisor_command"][:4] == [
        "python-test",
        "-X",
        "utf8",
        str(root / "run.py"),
    ]
    assert "supervisor-run" in plan["supervisor_command"]
    task = plan["windows_task_scheduler"]
    assert task["StartWhenAvailable"] is True
    assert task["MultipleInstancesPolicy"] == "IgnoreNew"
    assert task["ExecutionTimeLimit"] == "PT0S"
    assert task["RestartOnFailure"] == {"Count": 3, "Interval": "PT1M"}
    assert plan["windows_service"]["not_emulated_by_plain_python_process"] is True


def test_supervisor_status_fails_closed_without_live_pid(tmp_path: Path) -> None:
    root = tmp_path / "jazn"
    root.mkdir()
    status = supervisor_status(root)
    assert status["ok"] is False
    assert status["supervisor_active"] is False
    assert status["supervisor_pid"] is None
