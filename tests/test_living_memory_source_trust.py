from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.tools.memory_rebuild_app import UnifiedMemoryDatabase


def _native_database(tmp_path: Path) -> Path:
    database = tmp_path / "source" / "memory_jazn.sqlite3"
    UnifiedMemoryDatabase(database).initialize()
    return database


def _write_registry(
    workspace: Path,
    database: Path,
    *,
    trusted: bool | None = None,
    trust_basis: str | None = None,
) -> None:
    entry: dict[str, object] = {
        "path": str(database),
        "enabled": True,
        "read_only": True,
    }
    if trusted is not None:
        entry["trusted"] = trusted
    if trust_basis is not None:
        entry["trust_basis"] = trust_basis
    workspace.mkdir(parents=True)
    (workspace / "memory_source_registry.json").write_text(
        json.dumps({"sources": [entry]}),
        encoding="utf-8",
    )


def test_structurally_valid_untrusted_registry_source_is_discovered_but_not_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    workspace = tmp_path / "isolated-workspace"
    database = _native_database(tmp_path)
    _write_registry(workspace, database)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_SOURCE_ROOTS", raising=False)

    readiness = LivingMemoryGateway(runtime).readiness()
    source = next(
        item for item in readiness["sources"]
        if item["origin"] == "workspace_registry"
    )

    assert source["native_structurally_ready"] is True
    assert source["source_trusted"] is False
    assert source["trust_basis"] is None
    assert source["trust_issue"] == "workspace_registry_explicit_trust_required"
    assert source["memory_search_ready"] is False
    assert source["recall_ready"] is False
    assert source["selected_canonical"] is False
    assert source["ignored_reason"] == "source_not_trusted"
    assert readiness["status"] == "no_ready_memory_source"
    assert readiness["memory_search_ready"] is False
    assert readiness["selected_source_count"] == 0


@pytest.mark.parametrize(
    ("trusted", "trust_basis"),
    [(True, None), (False, "operator_reviewed")],
)
def test_registry_trust_requires_both_true_flag_and_nonempty_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trusted: bool,
    trust_basis: str | None,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    workspace = tmp_path / "isolated-workspace"
    database = _native_database(tmp_path)
    _write_registry(
        workspace,
        database,
        trusted=trusted,
        trust_basis=trust_basis,
    )
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_SOURCE_ROOTS", raising=False)

    source = next(
        item for item in LivingMemoryGateway(runtime).discover()
        if item["origin"] == "workspace_registry"
    )

    assert source["source_trusted"] is False
    assert source["recall_ready"] is False
    assert source["selected_canonical"] is False


def test_explicitly_trusted_registry_source_is_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    workspace = tmp_path / "isolated-workspace"
    database = _native_database(tmp_path)
    _write_registry(
        workspace,
        database,
        trusted=True,
        trust_basis="operator_validated_private_memory",
    )
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_SOURCE_ROOTS", raising=False)

    readiness = LivingMemoryGateway(runtime).readiness()
    source = next(
        item for item in readiness["sources"]
        if item["origin"] == "workspace_registry"
    )

    assert source["source_trusted"] is True
    assert source["trust_basis"] == "operator_validated_private_memory"
    assert source["memory_search_ready"] is True
    assert source["recall_ready"] is True
    assert source["selected_canonical"] is True
    assert readiness["status"] == "ready_native_unified"
    assert readiness["memory_search_ready"] is True
    assert readiness["selected_source_count"] == 1
