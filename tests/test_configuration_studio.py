from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.tools.configuration_studio import (
    SCHEMA, ConfigValidationError, describe_profile, inspect_system,
    profile_digest, profile_file, read_profile, save_profile, validate_values,
)


def fake_system(tmp_path: Path) -> Path:
    system = tmp_path / "jazn_system"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "main.py").write_text("# main\n", encoding="utf-8")
    (system / "latka_jazn" / "version.py").write_text("# version\n", encoding="utf-8")
    return system


def test_snapshot_is_read_only_and_reports_host_separation(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    data = {row["name"]: row for row in inspect_system(root)}
    assert data["SYSTEM"]["path"] == str(root.resolve())
    assert data["WORKSPACE"]["path"] == str((tmp_path / "workspace_runtime").resolve())
    assert data["MARKER"]["exists"] == "false"
    assert data["PROFILES"]["exists"] == "false"
    assert not (tmp_path / "workspace_runtime").exists()


def test_validated_profile_roundtrip_and_rollback_backup(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    w = tmp_path / "private_workspace"
    values = {"JAZN_MEMORY_MODE": "optional",
              "JAZN_MEMORY_ROOT": str(tmp_path / "external_private_memory"),
              "JAZN_LLM_ROUTE": "local"}
    assert validate_values(root, values)["JAZN_LLM_ROUTE"] == "local"
    path = save_profile(root, values, workspace=w, expected_sha256=None)
    assert path == profile_file(root, workspace=w)
    assert read_profile(root, workspace=w) == values
    first = path.read_bytes()
    digest = profile_digest(root, workspace=w)
    save_profile(root, {"JAZN_MEMORY_MODE": "off"}, workspace=w, expected_sha256=digest)
    assert (path.parent / "operator.previous.json").read_bytes() == first
    assert read_profile(root, workspace=w) == {"JAZN_MEMORY_MODE": "off"}
    assert not (root / "memory").exists()


def test_compare_and_swap_rejects_stale_ui(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    save_profile(root, {"JAZN_MEMORY_MODE": "optional"}, workspace=workspace)
    with pytest.raises(ConfigValidationError, match="zmieniony"):
        save_profile(root, {"JAZN_MEMORY_MODE": "required"}, workspace=workspace,
                     expected_sha256=None)
    assert read_profile(root, workspace=workspace) == {"JAZN_MEMORY_MODE": "optional"}


@pytest.mark.parametrize("invalid", [
    {"OPENAI_API_KEY": "secret"},
    {"JAZN_MEMORY_ROOT": "relative/memory"},
    {"JAZN_LLM_ROUTE": "not-a-valid-route"},
    {"JAZN_MEMORY_MODE": "random"},
    {"JAZN_MEMORY_MODE": "required\nJAZN_TEST_MODE=1"},
])
def test_invalid_values_fail_closed(tmp_path: Path, invalid: dict[str, str]) -> None:
    root = fake_system(tmp_path)
    with pytest.raises(ConfigValidationError):
        validate_values(root, invalid)


def test_no_path_inside_system_or_legacy_workspace(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    for candidate in (root / "memory", root / "workspace_runtime" / "memory",
                      root / "latka_jazn" / "local_resources"):
        with pytest.raises(ConfigValidationError):
            validate_values(root, {"JAZN_MEMORY_ROOT": str(candidate)})


def test_profile_rejects_corruption_and_symlink(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    file = profile_file(root, workspace=workspace)
    file.parent.mkdir(parents=True)
    file.write_text('{"schema":"unexpected","values":{}}', encoding="utf-8")
    with pytest.raises(ConfigValidationError):
        read_profile(root, workspace=workspace)
    with pytest.raises(ConfigValidationError):
        save_profile(root, {}, workspace=workspace, expected_sha256=profile_digest(root, workspace=workspace))
    file.unlink()
    other = tmp_path / "target.json"
    other.write_text(json.dumps({"schema": SCHEMA, "values": {}}), encoding="utf-8")
    try:
        file.symlink_to(other)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable on this Windows runner")
    with pytest.raises(ConfigValidationError):
        read_profile(root, workspace=workspace)


def test_memory_and_workspace_cannot_overlap(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    workspace = tmp_path / "workspace"
    with pytest.raises(ConfigValidationError):
        validate_values(root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(workspace),
                               "JAZN_MEMORY_ROOT": str(workspace / "config")})
    with pytest.raises(ConfigValidationError):
        validate_values(root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(workspace),
                               "JAZN_MEMORY_ROOT": str(tmp_path)})


def test_profile_inspection_does_not_apply_running_config(tmp_path: Path) -> None:
    root = fake_system(tmp_path)
    data = describe_profile(root)
    assert data["applied_to_running_daemon"] is False
    assert data["values"] == {}
    assert not profile_file(root).exists()
