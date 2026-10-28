"""3F: cooperative transaction locks, stale write protection and isolation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.jazn_run_studio import core as studio
from tools.jazn_run_studio.core import Settings, StudioError, save_settings, settings_path
from latka_jazn.core.operator_settings_transaction import (
    SettingsLockError, exclusive_settings_lock,
)


@pytest.fixture
def local_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "system"
    (root / ".settings").mkdir(parents=True)
    for key in ("JAZN_STUDIO_ACCEPTANCE_PROFILE", "JAZN_OPERATOR_STATE_ROOT",
                "JAZN_MEMORY_ROOT", "JAZN_RUNTIME_WORKSPACE_DIR"):
        monkeypatch.delenv(key, raising=False)
    return root


def test_serial_writes_reject_stale_digest(local_root: Path) -> None:
    first = save_settings(local_root, Settings(mcp_port="8081"), None)
    with pytest.raises(StudioError, match="zmieniły"):
        save_settings(local_root, Settings(mcp_port="8082"), None)
    with pytest.raises(StudioError, match="zmieniły"):
        save_settings(local_root, Settings(mcp_port="8082"), "0" * 64)
    second = save_settings(local_root, Settings(mcp_port="8082"), first)
    assert second != first
    assert json.loads(settings_path(local_root).read_text(encoding="utf-8"))["mcp_port"] == "8082"


def test_two_processes_cannot_both_commit_stale_none(local_root: Path) -> None:
    worker = """
import sys
from pathlib import Path
from tools.jazn_run_studio.core import Settings, StudioError, save_settings
try:
    save_settings(Path(sys.argv[1]), Settings(mcp_port=sys.argv[2]), None)
except StudioError:
    raise SystemExit(9)
"""
    cwd = Path(__file__).resolve().parents[1]
    processes = [
        subprocess.Popen(
            [sys.executable, "-X", "utf8", "-c", worker, str(local_root), str(port)],
            cwd=cwd, env=os.environ.copy(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        for port in (8081, 8082)
    ]
    outcomes = [p.communicate(timeout=30) for p in processes]
    codes = sorted(p.returncode for p in processes)
    assert codes == [0, 9], (codes, outcomes)


def test_replace_failure_does_not_corrupt_previous_file(local_root: Path, monkeypatch):
    current = save_settings(local_root, Settings(mcp_port="8081"), None)
    target = settings_path(local_root)
    old = target.read_bytes()

    def fail_replace(_src, _dst):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(studio.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        save_settings(local_root, Settings(mcp_port="8082"), current)
    assert target.read_bytes() == old
    assert not list(target.parent.glob(".settings-*"))


def test_lock_symlink_refused(local_root: Path, tmp_path: Path):
    target = settings_path(local_root)
    target.parent.mkdir(parents=True)
    external = tmp_path / "external.lock"
    external.write_bytes(b"UNTOUCHED")
    lock = target.with_name(target.name + ".lock")
    try:
        lock.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted")
    with pytest.raises(SettingsLockError):
        with exclusive_settings_lock(target):
            pytest.fail("Unsafe lock accepted")
    assert external.read_bytes() == b"UNTOUCHED"


def test_lock_sidecar_is_not_deleted_after_save(local_root: Path):
    save_settings(local_root, Settings(mcp_port="8081"), None)
    lock = settings_path(local_root).with_name("settings.json.lock")
    assert lock.is_file()
    before = lock.stat().st_ino
    digest = studio.load_settings(local_root)[1]
    save_settings(local_root, Settings(mcp_port="8082"), digest)
    assert lock.stat().st_ino == before


def test_distinct_worktrees_use_distinct_locks(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", raising=False)
    a, b = tmp_path / "left", tmp_path / "right"
    (a / ".settings").mkdir(parents=True)
    (b / ".settings").mkdir(parents=True)
    save_settings(a, Settings(mcp_port="8081"), None)
    save_settings(b, Settings(mcp_port="8082"), None)
    assert settings_path(a).parent != settings_path(b).parent
    assert settings_path(a).read_bytes() != settings_path(b).read_bytes()
