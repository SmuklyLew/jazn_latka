"""Acceptance regression: safety, atomicity and launch-snapshot invariants."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from latka_jazn.tools.configuration_studio import (
    ConfigValidationError, profile_digest, profile_file, profile_snapshot,
    read_profile, restore_previous_profile, save_profile,
    validated_launch_values, validate_values, inspect_system,
)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    source = tmp_path / "system"
    (source / "latka_jazn").mkdir(parents=True)
    (source / "main.py").write_text("# synthetic\n", encoding="utf-8")
    (source / "latka_jazn" / "version.py").write_text("# synthetic\n", encoding="utf-8")
    return source


def test_reject_memory_sqlite_cache_collision(root: Path, tmp_path: Path) -> None:
    memory = tmp_path / "personal" / "memory"
    db = memory / "sqlite" / "memory_jazn.sqlite3"
    with pytest.raises(ConfigValidationError, match="kolizja"):
        validate_values(root, {"JAZN_MEMORY_ROOT": str(memory),
                               "JAZN_LEXICAL_RESOURCE_CACHE": str(db)})
    with pytest.raises(ConfigValidationError, match="kolizja"):
        validate_values(root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "state"),
                               "JAZN_LEXICAL_RESOURCE_CACHE": str(tmp_path / "state" / "core_state" / "cache.sqlite3")})


def test_reject_current_memory_root_even_if_changing_memory(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = tmp_path / "existing_memory"
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(old))
    with pytest.raises(ConfigValidationError, match="kolizja"):
        validate_values(root, {"JAZN_MEMORY_ROOT": str(tmp_path / "new_memory"),
                               "JAZN_LEXICAL_RESOURCE_CACHE": str(old / "sqlite" / "memory_jazn.sqlite3")})


def test_profile_single_snapshot_and_rollback(root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    path = save_profile(root, {"JAZN_MEMORY_MODE": "optional"}, workspace=workspace)
    first = profile_digest(root, workspace=workspace)
    save_profile(root, {"JAZN_MEMORY_MODE": "required"}, workspace=workspace, expected_sha256=first)
    second = profile_digest(root, workspace=workspace)
    restore_previous_profile(root, workspace=workspace, expected_sha256=second)
    assert read_profile(root, workspace=workspace) == {"JAZN_MEMORY_MODE": "optional"}
    assert path.is_file()


def test_concurrent_compare_and_swap_allows_only_one_writer(root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    save_profile(root, {"JAZN_MEMORY_MODE": "optional"}, workspace=workspace)
    digest = profile_digest(root, workspace=workspace)
    def writer(mode: str) -> str:
        try:
            save_profile(root, {"JAZN_MEMORY_MODE": mode},
                         workspace=workspace, expected_sha256=digest)
        except ConfigValidationError:
            return "rejected"
        return "saved"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(writer, x) for x in ("off", "required")]
        results = [future.result() for future in futures]
    assert sorted(results) == ["rejected", "saved"]
    assert read_profile(root, workspace=workspace)["JAZN_MEMORY_MODE"] in {"off", "required"}


def test_duplicate_keys_are_rejected(root: Path, tmp_path: Path) -> None:
    path = profile_file(root, workspace=tmp_path / "work")
    path.parent.mkdir(parents=True)
    path.write_text('{"schema":"jazn_configuration_profile/v1","values":'
                    '{"JAZN_MEMORY_MODE":"off","JAZN_MEMORY_MODE":"required"}}', encoding="utf-8")
    with pytest.raises(ConfigValidationError, match="Zduplikowany"):
        profile_snapshot(root, workspace=tmp_path / "work")


def test_launch_rejects_marker_when_changing_critical_paths(root: Path, tmp_path: Path) -> None:
    save_profile(root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "new_state")})
    assert validated_launch_values(root)["JAZN_RUNTIME_WORKSPACE_DIR"] == str(tmp_path / "new_state")
    marker = tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigValidationError, match="znacznik runtime"):
        validated_launch_values(root)


def test_inspection_honors_effective_paths(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "separate_projects"
    nlp_dir = tmp_path / "separate_nlp"
    monkeypatch.setenv("JAZN_MEMORY_REBUILD_PROJECTS", str(project_dir))
    monkeypatch.setenv("LATKA_NLP_DATA_DIR", str(nlp_dir))
    paths = {item["name"]: item["path"] for item in inspect_system(root)}
    assert paths["STUDIO_MEMORY"] == str(project_dir)
    assert paths["NLP_MODELS"] == str(nlp_dir)


def test_validated_launch_is_exact_normalized_snapshot(root: Path) -> None:
    save_profile(root, {"JAZN_MEMORY_MODE": "OPTIONAL", "JAZN_LLM_ROUTE": "local"})
    assert validated_launch_values(root) == {"JAZN_MEMORY_MODE": "optional", "JAZN_LLM_ROUTE": "local"}
    assert json.loads(json.dumps(validated_launch_values(root))) == validated_launch_values(root)
