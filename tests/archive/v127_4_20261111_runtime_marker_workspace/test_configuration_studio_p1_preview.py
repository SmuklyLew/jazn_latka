from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.tools.configuration_studio import (
    ConfigValidationError, preview_profile_changes, profile_file,
    profile_snapshot, save_profile,
)


def fake_system(tmp_path: Path) -> Path:
    root = tmp_path / "system"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "main.py").write_text("# main\n", encoding="utf-8")
    (root / "latka_jazn" / "version.py").write_text("# version\n", encoding="utf-8")
    return root


def test_dry_run_does_not_create_profile_or_apply_daemon(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    preview = preview_profile_changes(
        root, {"JAZN_MEMORY_MODE": "optional"},
        workspace=workspace, expected_sha256=None,
    )
    assert preview["schema"] == "jazn_config_profile_preview/v1"
    assert preview["changed_keys"] == ["JAZN_MEMORY_MODE"]
    assert preview["changes_count"] == 1
    assert preview["read_only"] is True
    assert preview["applied_to_running_daemon"] is False
    assert preview["runtime_effective_values_verified"] is False
    assert preview["future_launch_only"] is True
    assert not profile_file(root, workspace=workspace).exists()
    assert not workspace.exists()
    assert not (root / "memory").exists()
    value = next(x for x in preview["rows"] if x["key"] == "JAZN_MEMORY_MODE")
    assert value["default_verified"] is False
    assert value["future_override_source"] == "draft_profile"


def test_preview_differentiates_saved_and_proposed_without_writes(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    saved_path = save_profile(root, {"JAZN_MEMORY_MODE": "off"}, workspace=workspace)
    original = saved_path.read_bytes()
    _, digest = profile_snapshot(root, workspace=workspace)
    preview = preview_profile_changes(
        root, {"JAZN_MEMORY_MODE": "required", "JAZN_LLM_ROUTE": "local"},
        workspace=workspace, expected_sha256=digest,
    )
    assert preview["changed_keys"] == ["JAZN_MEMORY_MODE", "JAZN_LLM_ROUTE"]
    assert preview["saved_overrides"] == {"JAZN_MEMORY_MODE": "off"}
    assert preview["proposed_overrides"]["JAZN_MEMORY_MODE"] == "required"
    assert saved_path.read_bytes() == original
    assert profile_snapshot(root, workspace=workspace)[1] == digest


def test_stale_profile_preview_fails_closed(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    save_profile(root, {"JAZN_MEMORY_MODE": "optional"}, workspace=workspace)
    with pytest.raises(ConfigValidationError, match="zmieniony"):
        preview_profile_changes(
            root, {"JAZN_MEMORY_MODE": "required"},
            workspace=workspace, expected_sha256=None,
        )


def test_dry_run_rejects_unknown_and_unsafe_configuration(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    for entry in (
        {"OPENAI_API_KEY": "secret"},
        {"JAZN_MEMORY_MODE": "invalid"},
        {"JAZN_MEMORY_ROOT": str(root / "latka_jazn" / "private")},
    ):
        with pytest.raises(ConfigValidationError):
            preview_profile_changes(root, entry, expected_sha256=None)
    # The dedicated canonical SYSTEM/memory folder is permitted by the
    # runtime and validation contract; preview must not contradict it.
    preview = preview_profile_changes(
        root, {"JAZN_MEMORY_ROOT": str(root / "memory")},
        expected_sha256=None,
    )
    assert preview["proposed_overrides"]["JAZN_MEMORY_ROOT"] == str(root / "memory")


def test_marker_cannot_be_mistaken_for_runtime_readiness(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace_runtime"
    workspace.mkdir()
    (workspace / "JAZN_ACTIVE_RUNTIME.json").write_text('{"stale":true}', encoding="utf-8")
    preview = preview_profile_changes(
        root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(tmp_path / "new_workspace")},
        expected_sha256=None,
    )
    assert preview["runtime_marker_present"] is True
    assert preview["location_change_requires_runtime_verification"] is True
    assert preview["applied_to_running_daemon"] is False
    assert preview["runtime_effective_values_verified"] is False
