"""F06: canonical startup cannot race verified archive publication."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core import runtime_daemon, runtime_supervisor
from latka_jazn.core.runtime_root import RuntimeWorkspaceBusyError, runtime_memory_transition_lock
from latka_jazn.tools import verified_memory_restore as restore


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic-root"
    (root / "local_resources").mkdir(parents=True)
    (root / "run.py").write_text("# synthetic, never executed", encoding="utf-8")
    return root


def test_maintenance_lock_is_cross_process_and_released(tmp_path: Path) -> None:
    root = _root(tmp_path)
    code = (
        "import sys; from pathlib import Path; "
        "from latka_jazn.core.runtime_root import runtime_memory_transition_lock, RuntimeWorkspaceBusyError\n"
        "try:\n"
        "    with runtime_memory_transition_lock(Path(sys.argv[1])): pass\n"
        "except RuntimeWorkspaceBusyError: sys.exit(42)\n"
    )
    command = [sys.executable, "-X", "utf8", "-c", code, str(root)]
    with runtime_memory_transition_lock(root):
        assert subprocess.run(command, timeout=30, check=False).returncode == 42
    assert subprocess.run(command, timeout=30, check=False).returncode == 0


def test_busy_maintenance_prevents_daemon_boot_and_supervisor_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("busy memory transition must not initialize or claim runtime")

    monkeypatch.setattr(runtime_daemon, "verify_package_integrity_manifest", lambda _root: {"ok": True})
    monkeypatch.setattr(runtime_daemon, "read_source_provenance",
                        lambda *_a, **_k: SimpleNamespace(to_dict=lambda: {"status": "clean_checkout_verified"}))
    monkeypatch.setattr(runtime_daemon, "build_runtime_write_access_status", forbidden)
    monkeypatch.setattr(runtime_supervisor, "_claim_supervisor_pid", forbidden)
    with runtime_memory_transition_lock(root):
        assert runtime_daemon.run_daemon(JaznConfig(root=root)) == 4
        assert runtime_supervisor.run_supervisor(root) == 42


def test_prepare_holds_lock_through_backup_publish_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    events: list[str] = []
    monkeypatch.setattr(restore, "validate_test04_summary", lambda _p: {})
    monkeypatch.setattr(restore, "validate_test04_databases", lambda _p: {})
    monkeypatch.setattr(restore.RuntimeArchiveConverter, "build", lambda _self: {})

    def locked(label: str) -> None:
        with pytest.raises(RuntimeWorkspaceBusyError):
            with runtime_memory_transition_lock(root):
                pytest.fail("maintenance lease was released too early")
        events.append(label)

    def observe(_root: Path) -> dict[str, Any]:
        locked("observe")
        return {"ok": True}

    def backup(_root: Path, _backup: Path) -> dict[str, Any]:
        locked("backup")
        return {"ok": True}

    def publish(_staged: Path, _root: Path) -> dict[str, Any]:
        locked("publish")
        raise restore.VerifiedMemoryRestoreError("synthetic publish failure")

    def rollback(_root: Path, _backup: Path) -> None:
        locked("rollback")

    monkeypatch.setattr(restore, "_require_quiescent_runtime", observe)
    monkeypatch.setattr(restore, "_backup_runtime_memory", backup)
    monkeypatch.setattr(restore, "_publish_staged_archive", publish)
    monkeypatch.setattr(restore, "_restore_runtime_memory", rollback)
    kwargs: dict[str, Any] = dict(test04_root=root / "source", test04_summary=root / "summary.json",
                                  publish=True, stop_daemon=False, l2_limit=1, report_path=None)
    with runtime_memory_transition_lock(root):
        with pytest.raises(restore.VerifiedMemoryRestoreError, match="runtime_memory_transition_busy"):
            restore.prepare(root, **kwargs)
    assert not events
    with pytest.raises(restore.VerifiedMemoryRestoreError, match="synthetic publish failure"):
        restore.prepare(root, **kwargs)
    assert events == ["observe", "backup", "observe", "publish", "observe", "rollback"]
    with runtime_memory_transition_lock(root):
        pass
