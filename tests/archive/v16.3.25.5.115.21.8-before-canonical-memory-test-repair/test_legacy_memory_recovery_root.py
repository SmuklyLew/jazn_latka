from __future__ import annotations

from pathlib import Path

from latka_jazn.memory.legacy_memory_recovery import LegacyMemoryRecovery
from latka_jazn.memory.memory_root import MEMORY_ROOT_ENV, default_memory_root


def test_legacy_memory_recovery_uses_canonical_host_memory_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "active-root" / "jazn-v82"
    runtime_root.mkdir(parents=True)
    canonical = default_memory_root(runtime_root)
    canonical.mkdir(parents=True)

    recovery = LegacyMemoryRecovery(runtime_root)

    assert recovery.memory_root == canonical.resolve()
    assert recovery.archive_manifest == (
        canonical / "sqlite" / "conversation_archive_v1" / "conversation_archive_manifest.sqlite3"
    ).resolve()
    assert recovery.legacy_database == (
        canonical / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3"
    ).resolve()
    assert recovery.journal_path == (canonical / "raw" / "dziennik.json").resolve()
    assert recovery.output_path.is_relative_to(canonical.resolve())
    assert not (runtime_root / "memory").exists()


def test_legacy_memory_recovery_respects_explicit_memory_root_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_root = tmp_path / "active-root" / "jazn-v82"
    runtime_root.mkdir(parents=True)
    external = tmp_path / "private-memory"
    external.mkdir(parents=True)
    monkeypatch.setenv(MEMORY_ROOT_ENV, str(external))

    recovery = LegacyMemoryRecovery(runtime_root)

    assert recovery.memory_root == external.resolve()
    assert recovery.archive_manifest.is_relative_to(external.resolve())
    assert recovery.journal_path.is_relative_to(external.resolve())
    assert recovery.output_path.is_relative_to(external.resolve())
