"""Canonical <SYSTEM>/memory regression tests: path identity, fallback and safety."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from latka_jazn.memory.availability import build_memory_availability_status
from latka_jazn.memory.memory_root import (
    default_memory_root,
    previous_host_memory_root,
    resolve_memory_root,
    resolve_memory_root_diagnostic,
)
from latka_jazn.packaging import memory_package_attach as attach_module
from tools.jazn_pack_generator_app.scanner import _is_system_excluded


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runtime = tmp_path / "runtime_roots" / "installed_jazn"
    runtime.mkdir(parents=True)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    return runtime


def _payload(path: Path) -> None:
    (path / "sqlite").mkdir(parents=True, exist_ok=True)
    (path / "sqlite" / "memory_jazn.sqlite3").write_bytes(b"synthetic")


def test_default_is_direct_system_child_independent_of_cwd(root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    expected = (root / "memory").resolve()
    assert default_memory_root(root) == expected
    assert resolve_memory_root(root) == expected
    assert build_memory_availability_status(root).memory_root == str(expected)
    assert not expected.exists()


def test_new_memory_does_not_get_shadowed_by_old_host_payload(root: Path) -> None:
    old = previous_host_memory_root(root)
    _payload(old)
    assert resolve_memory_root(root) == old
    (root / "memory").mkdir()
    assert resolve_memory_root(root) == old
    _payload(root / "memory")
    assert resolve_memory_root(root) == (root / "memory").resolve()
    assert resolve_memory_root(root, prefer_existing_legacy=False) == (root / "memory").resolve()


def test_explicit_relative_memory_is_system_relative(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JAZN_MEMORY_ROOT", "./memory")
    assert resolve_memory_root(root) == (root / "memory").resolve()
    monkeypatch.setenv("JAZN_MEMORY_ROOT", "other-private-memory")
    assert resolve_memory_root(root) == (root / "other-private-memory").resolve()


def test_explicit_absolute_memory_remains_authoritative(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "user-private"
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(outside))
    assert resolve_memory_root(root) == outside.resolve()


@pytest.mark.parametrize("bad", ["../secrets", "memory/../../outside", r"memory\..\outside", "memory/../memory"])
def test_relative_traversal_rejected(root: Path, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("JAZN_MEMORY_ROOT", bad)
    with pytest.raises(ValueError):
        resolve_memory_root(root)


@pytest.mark.skipif(os.name == "nt", reason="Windows drive paths are host-native")
def test_windows_absolute_override_rejected_on_posix(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_ROOT", r"C:\private\memory")
    with pytest.raises(ValueError):
        resolve_memory_root(root)


def test_readonly_diagnostic_exposes_old_root_without_claiming_migration(root: Path) -> None:
    _payload(previous_host_memory_root(root))
    result = resolve_memory_root_diagnostic(root)
    assert result["selection_source"] == "previous_host_memory_compatibility"
    assert result["selected"] == str(previous_host_memory_root(root))
    assert result["canonical"] == str((root / "memory").resolve())
    assert result["private_content_read"] is False
    assert not (root / "memory").exists()


def test_attach_rollback_backup_never_written_into_system_tree(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = root / "memory"
    _payload(current)
    (current / "old.txt").write_text("keep", encoding="utf-8")
    workspace = tmp_path / "workspace_runtime"
    source = tmp_path / "candidate" / "memory"
    source.mkdir(parents=True)
    (source / "new.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(
        attach_module,
        "initialize_transactional_memory_store",
        lambda runtime_root: {"ok": True},
    )
    backup, had_previous = attach_module._install_memory_tree(root, workspace, source, {})
    assert had_previous
    assert backup.is_relative_to(workspace)
    assert (backup / "old.txt").read_text(encoding="utf-8") == "keep"
    assert (root / "memory" / "new.txt").is_file()
    assert not (root / ".memory-backups").exists()


def test_system_pack_excludes_private_memory_and_backups() -> None:
    from pathlib import PurePosixPath
    assert _is_system_excluded(PurePosixPath("memory"), "memory", True) == "system-memory-boundary"
    assert _is_system_excluded(PurePosixPath(".memory-backups"), ".memory-backups", True) is not None
    assert _is_system_excluded(PurePosixPath(".memory-failed"), ".memory-failed", True) is not None

def test_failed_backup_never_erases_existing_memory(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import errno

    memory = root / "memory"
    _payload(memory)
    marker = memory / "keep.txt"
    marker.write_text("original", encoding="utf-8")
    source = tmp_path / "incoming" / "memory"
    source.mkdir(parents=True)
    (source / "new.txt").write_text("candidate", encoding="utf-8")
    move = attach_module.os.replace

    def reject_backup(src: Path, dst: Path) -> None:
        if Path(src).resolve() == memory.resolve():
            raise OSError(errno.EXDEV, "synthetic cross-filesystem backup rejection")
        move(src, dst)

    monkeypatch.setattr(attach_module.os, "replace", reject_backup)
    with pytest.raises(OSError, match="different filesystems"):
        attach_module._install_memory_tree(root, tmp_path / "workspace_runtime", source, {})
    assert marker.read_text(encoding="utf-8") == "original"
    assert (source / "new.txt").is_file()
    assert not (root / ".memory-backups").exists()

def test_generator_selects_same_legacy_host_fallback_as_runtime(root: Path) -> None:
    from tools.jazn_pack_generator_app.scanner import resolve_memory_root as generator_root
    older = previous_host_memory_root(root)
    _payload(older)
    assert generator_root(root, None) == resolve_memory_root(root) == older
    _payload(root / "memory")
    assert generator_root(root, None) == resolve_memory_root(root) == (root / "memory").resolve()
