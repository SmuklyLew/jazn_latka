"""Fail-closed operator profile migration with version-bound CAS evidence.

All tests use an ephemeral SYSTEM and never open real Jaźń MEMORY or daemon.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.core import system_config
from latka_jazn.tools import configuration_studio
from tools.jazn_run_studio import studio_worker


@pytest.fixture
def root(tmp_path: Path) -> Path:
    source = tmp_path / "SYSTEM"
    (source / "latka_jazn").mkdir(parents=True)
    (source / "main.py").write_text("", encoding="utf-8")
    (source / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    return source


def _seed(root: Path, mode: str = "off") -> str:
    configuration_studio.save_profile(
        root, {"JAZN_MEMORY_MODE": mode}, expected_sha256=None,
    )
    _, digest = configuration_studio.profile_snapshot(root)
    assert digest is not None
    return digest


def _replace_profile(root: Path, mode: str) -> None:
    path = configuration_studio.profile_file(root)
    path.write_text(
        json.dumps({
            "schema": configuration_studio.SCHEMA,
            "values": {"JAZN_MEMORY_MODE": mode},
        }),
        encoding="utf-8",
    )


def test_worker_aborts_if_file_changes_after_gui_sha_validation(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = _seed(root)
    original = configuration_studio.profile_snapshot
    seen = 0

    def changing_profile_snapshot(path: str | Path):
        nonlocal seen
        result = original(path)
        seen += 1
        if seen == 1:
            # Change the file after studio_worker checks the accepted digest
            # but before the canonical migrator reads the source.
            _replace_profile(root, "required")
        return result

    monkeypatch.setattr(configuration_studio, "profile_snapshot", changing_profile_snapshot)
    monkeypatch.chdir(root)
    with pytest.raises(system_config.SystemConfigError, match="zmieniono"):
        studio_worker.profile("profile-migrate", {"digest": accepted})

    assert seen >= 2
    assert not system_config.config_path(root).exists()
    assert not (root / "jazn_system_config.previous.json").exists()
    assert original(root)[0]["JAZN_MEMORY_MODE"] == "required"


def test_canonical_migrator_aborts_if_profile_changes_during_migration(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = _seed(root)
    original = configuration_studio.profile_snapshot
    seen = 0

    def changing_profile_snapshot(path: str | Path):
        nonlocal seen
        seen += 1
        values = original(path)
        if seen == 1:
            _replace_profile(root, "required")
        return values

    monkeypatch.setattr(configuration_studio, "profile_snapshot", changing_profile_snapshot)
    with pytest.raises(system_config.SystemConfigError, match="zmieniono"):
        system_config.migrate_operator_profile(root, expected_sha256=accepted)

    assert seen >= 2
    assert not system_config.config_path(root).exists()


def test_canonical_migrator_checks_digest_again_before_write(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = _seed(root)
    original = configuration_studio.profile_snapshot
    seen = 0

    def changing_profile_snapshot(path: str | Path):
        nonlocal seen
        result = original(path)
        seen += 1
        if seen == 2:
            # Another writer did not participate in the Jaźń file guard.
            _replace_profile(root, "required")
        return result

    monkeypatch.setattr(configuration_studio, "profile_snapshot", changing_profile_snapshot)
    with pytest.raises(system_config.SystemConfigError, match="zmieniono"):
        system_config.migrate_operator_profile(root, expected_sha256=accepted)

    assert seen == 2
    assert not system_config.config_path(root).exists()


def test_approved_profile_migrates_without_modifying_live_runtime(root: Path) -> None:
    accepted = _seed(root)
    config = system_config.migrate_operator_profile(root, expected_sha256=accepted)
    assert config.values["JAZN_MEMORY_MODE"] == "off"
    assert system_config.read_system_config(root).digest == config.digest
    assert system_config.config_path(root).exists()
    assert not (root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json").exists()


def test_old_digest_is_rejected_and_root_is_unchanged(root: Path) -> None:
    original = _seed(root)
    initial = system_config.migrate_operator_profile(root, expected_sha256=original)
    stored = system_config.config_path(root).read_bytes()
    profile_sha = configuration_studio.profile_digest(root)
    configuration_studio.save_profile(
        root, {"JAZN_MEMORY_MODE": "required"}, expected_sha256=profile_sha,
    )
    with pytest.raises(system_config.SystemConfigError, match="zmieniono"):
        system_config.migrate_operator_profile(root, expected_sha256=original)
    assert system_config.config_path(root).read_bytes() == stored
    assert system_config.read_system_config(root).digest == initial.digest
