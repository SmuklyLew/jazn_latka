"""F06: legacy SYSTEM restore must share verified restore/startup authority."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from latka_jazn.core.runtime_root import RuntimeWorkspaceBusyError, runtime_memory_transition_lock
from latka_jazn.tools import verified_memory_restore as verified
from latka_jazn.tools.memory_restore import (
    MemoryRestoreOrchestrator, MemoryRestoreSettings, confirmation_token, target_preflight,
)


def _orchestrator(tmp_path: Path) -> tuple[Path, MemoryRestoreOrchestrator]:
    root = tmp_path / "synthetic-system"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "local_resources").mkdir()
    for path in (root / "run.py", root / "PACKAGE_INTEGRITY_MANIFEST.json",
                 root / "latka_jazn" / "version.py"):
        path.touch()
    settings = MemoryRestoreSettings(
        source_directory=str(tmp_path / "source"), target_root=str(root), mode="system",
    )
    return root, MemoryRestoreOrchestrator(settings, tool_root=tmp_path / "other-repo")


def _assert_locked(root: Path) -> None:
    with pytest.raises(RuntimeWorkspaceBusyError):
        with runtime_memory_transition_lock(root):
            pytest.fail("legacy restore must retain the canonical transition lock")


def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("denied restore must not reach the protected operation")


def test_busy_system_restore_refuses_before_probe_or_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, restore = _orchestrator(tmp_path)
    monkeypatch.setattr(verified, "_require_quiescent_runtime", _forbidden)
    monkeypatch.setattr(restore, "_run_confirmed", _forbidden)
    with runtime_memory_transition_lock(root):
        with pytest.raises(verified.VerifiedMemoryRestoreError, match="runtime_memory_transition_busy"):
            restore.run([], confirmation=confirmation_token(restore.settings))
    assert not (root / "memory").exists()


def test_system_restore_requires_quiescence_inside_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, restore = _orchestrator(tmp_path)

    def refuse(observed_root: Path) -> dict[str, Any]:
        assert observed_root == root
        _assert_locked(root)
        raise verified.VerifiedMemoryRestoreError("synthetic live daemon")

    monkeypatch.setattr(verified, "_require_quiescent_runtime", refuse)
    monkeypatch.setattr(restore, "_run_confirmed", _forbidden)
    with pytest.raises(verified.VerifiedMemoryRestoreError, match="synthetic live daemon"):
        restore.run([], confirmation=confirmation_token(restore.settings))
    assert not (root / "memory").exists()
    with runtime_memory_transition_lock(root):
        pass


@pytest.mark.parametrize("fail", [False, True])
def test_system_restore_retains_lock_through_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool) -> None:
    root, restore = _orchestrator(tmp_path)
    events: list[str] = []

    def observe(observed_root: Path) -> dict[str, Any]:
        assert observed_root == root
        _assert_locked(root)
        events.append("quiescent")
        return {}

    def work(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        _assert_locked(root)
        events.append("work")
        if fail:
            raise RuntimeError("synthetic work failure")
        return {"ok": True}

    monkeypatch.setattr(verified, "_require_quiescent_runtime", observe)
    monkeypatch.setattr(restore, "_run_confirmed", work)
    if fail:
        with pytest.raises(RuntimeError, match="synthetic work failure"):
            restore.run([], confirmation=confirmation_token(restore.settings))
    else:
        assert restore.run([], confirmation=confirmation_token(restore.settings)) == {"ok": True}
    assert events == ["quiescent", "work"]
    with runtime_memory_transition_lock(root):
        pass


def test_wrong_confirmation_refuses_before_maintenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, restore = _orchestrator(tmp_path)
    monkeypatch.setattr(verified, "_exclusive_memory_maintenance", _forbidden)
    monkeypatch.setattr(restore, "_run_confirmed", _forbidden)
    with pytest.raises(PermissionError, match="explicit confirmation"):
        restore.run([], confirmation="RESTORE")
    with runtime_memory_transition_lock(root):
        pass


def test_developer_mode_cannot_target_another_system_checkout(tmp_path: Path) -> None:
    root, _ = _orchestrator(tmp_path)
    settings = MemoryRestoreSettings(
        source_directory=str(tmp_path / "source"), target_root=str(root), mode="developer",
    )
    report = target_preflight(settings, tool_root=tmp_path / "other-repo")
    assert report["ok"] is False
    assert "developer_target_must_not_be_system_root" in report["blocking_errors"]
