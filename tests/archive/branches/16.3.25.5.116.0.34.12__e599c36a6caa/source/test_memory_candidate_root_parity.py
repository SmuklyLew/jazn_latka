"""No false private-memory selection from operational/placeholder artifacts."""
from pathlib import Path

import pytest

from latka_jazn.memory.availability import build_memory_availability_status
from latka_jazn.memory.memory_root import (
    memory_root_has_payload,
    resolve_memory_root,
    resolve_memory_root_diagnostic,
)


def test_shallow_candidate_and_availability_agree_on_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    canonical = root / "memory"
    (canonical / "layered").mkdir(parents=True)
    (canonical / "layered" / "cache.json").write_text("{}")
    (canonical / "sqlite" / "runtime_write_v1").mkdir(parents=True)
    (canonical / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3").write_bytes(b"operational")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    assert not memory_root_has_payload(canonical)
    assert resolve_memory_root(root) == canonical.resolve()
    status = build_memory_availability_status(root)
    assert status.persistent_memory_present is False
    assert status.recall_candidate_present is False
    assert resolve_memory_root_diagnostic(root)["selected_has_payload"] is False


def test_real_legacy_candidate_survives_canonical_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    (root / "memory" / "layered").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    actual = workspace / "memory" / "raw" / "chat.html"
    actual.parent.mkdir(parents=True)
    actual.write_text("legacy recall", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    assert memory_root_has_payload(actual.parent.parent)
    assert resolve_memory_root(root) == actual.parent.parent.resolve()
    availability = build_memory_availability_status(root)
    assert availability.persistent_memory_present is True
    assert availability.source == "previous_host_memory_compatibility"
    assert resolve_memory_root_diagnostic(root)["empty_canonical_placeholder_detected"] is True


def test_zero_byte_manifest_and_explicit_empty_path_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    candidate = root / "memory"
    candidate.mkdir()
    (candidate / "MEMORY_PACKAGE_MANIFEST.json").touch()
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    assert memory_root_has_payload(candidate) is False
    assert build_memory_availability_status(root, mode="required").ok is False
    assert resolve_memory_root(root, configured="memory") == candidate.resolve()
