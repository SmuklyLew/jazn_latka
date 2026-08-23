from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.core.runtime_daemon import daemon_auth_token_path, daemon_pid_path
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.session_continuity import SessionContinuityManager
from latka_jazn.tools import active_extraction_cache as active_cache
from latka_jazn.tools import release_metadata_sync
from latka_jazn.tools.memory_rebuild_common import DATABASE_FILENAMES
from latka_jazn.tools.memory_sqlite_test04 import write_templates
from latka_jazn.tools.package_export import build_package_plan
from latka_jazn.version import DISTRIBUTION_VERSION, PACKAGE_RELEASE_NAME, PACKAGE_VERSION


def test_v1604_release_identity_and_release_metadata_accept_unprefixed_version() -> None:
    assert DISTRIBUTION_VERSION == "16.0.4"
    assert PACKAGE_VERSION == "16.0.4"
    assert PACKAGE_RELEASE_NAME == "runtime-turn-liveness-ci-hardening"
    assert release_metadata_sync._impl._schema_version_for_runtime("release_test", PACKAGE_VERSION) == "release_test/16.0.4"
    assert release_metadata_sync._impl._schema_version_for_runtime("release_test", "v15.4.3.1") == "release_test/v15.4.3.1"


def test_bootstrap_marker_adapter_migrates_legacy_workspace_before_publish(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "jazn_latka_v15.4.3.1"
    legacy = runtime / "workspace_runtime"
    legacy.mkdir(parents=True)
    (legacy / "runtime_session_state.json").write_text('{"legacy":true}\n', encoding="utf-8")

    def fake_write(root: Path, **_kwargs):
        return {"active_root": str(Path(root).resolve()), "ok": True}

    monkeypatch.setattr(active_cache._impl, "write_active_runtime_marker", fake_write)
    result = active_cache.write_active_runtime_marker(runtime, action="v16-test")

    canonical = tmp_path / "workspace_runtime"
    assert result["single_canonical_runtime_workspace"] is True
    assert result["runtime_workspace_migration"]["ok"] is True
    assert (canonical / "runtime_session_state.json").is_file()
    assert not legacy.exists()


def test_daemon_security_paths_are_singletons_across_versioned_runtime_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root_a = tmp_path / "jazn_latka_v15.4.3.1"
    root_b = tmp_path / "jazn_latka_v16.0.0"
    root_a.mkdir()
    root_b.mkdir()

    assert daemon_pid_path(root_a) == daemon_pid_path(root_b) == tmp_path / "workspace_runtime" / "jazn_daemon.pid"
    assert daemon_auth_token_path(root_a) == daemon_auth_token_path(root_b) == tmp_path / "workspace_runtime" / "daemon" / "capability.token"


def test_restart_continuity_reads_runtime_state_from_host_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root = tmp_path / "jazn_latka_v16.0.0"
    root.mkdir()
    canonical = workspace_runtime_path(root)
    canonical.mkdir()
    state = canonical / "runtime_state.json"
    state.write_text('{"state":"active"}\n', encoding="utf-8")

    manager = SessionContinuityManager(root, version="16.0.0")
    file_state = manager._file_state("workspace_runtime/runtime_state.json")
    assert file_state.exists is True
    assert file_state.size_bytes == state.stat().st_size
    assert not (root / "workspace_runtime" / "runtime_state.json").exists()


def test_living_memory_registry_uses_host_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    runtime = tmp_path / "jazn_latka_v16.0.0"
    runtime.mkdir()
    source = tmp_path / "historical-memory"
    sqlite_dir = source / "memory" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    (sqlite_dir / DATABASE_FILENAMES["memory_jazn"]).touch()

    workspace = workspace_runtime_path(runtime)
    workspace.mkdir()
    (workspace / "memory_source_registry.json").write_text(
        json.dumps({"sources": [{"path": str(source), "enabled": True, "read_only": True}]}),
        encoding="utf-8",
    )

    discovered = LivingMemoryGateway(runtime).discover()
    assert any(item["origin"] == "workspace_registry" and item["root"] == str(source.resolve()) for item in discovered)
    assert not (runtime / "workspace_runtime" / "memory_source_registry.json").exists()


def test_test04_private_workspace_is_host_level(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    runtime = tmp_path / "jazn_latka_v16.0.0"
    templates = runtime / "docs" / "templates" / "memory_sqlite_test_04"
    templates.mkdir(parents=True)
    (templates / "settings.template.json").write_text("{}\n", encoding="utf-8")

    written = write_templates(runtime)
    expected = tmp_path / "workspace_runtime" / "memory_sqlite_test_04" / "settings.template.json"
    assert written == [expected]
    assert expected.is_file()
    assert not (runtime / "workspace_runtime" / "memory_sqlite_test_04").exists()


def test_memory_package_never_contains_runtime_workspace(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    (root / "memory").mkdir(parents=True)
    (root / "memory" / "keep.json").write_text("{}\n", encoding="utf-8")
    (root / "workspace_runtime").mkdir()
    (root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json").write_text("{}\n", encoding="utf-8")

    rels = [rel for _path, rel in build_package_plan(root, "memory")]
    assert "memory/keep.json" in rels
    assert all(not rel.startswith("workspace_runtime/") for rel in rels)
