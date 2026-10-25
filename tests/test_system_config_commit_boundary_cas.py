"""Preserve existing ROOT config and backup when operator source CAS fails."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.core import system_config
from latka_jazn.tools import configuration_studio


def test_changed_profile_does_not_modify_root_or_previous_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "latka_jazn" / "version.py").write_text("", encoding="utf-8")
    initial = system_config.write_system_config(
        root, {"JAZN_LLM_ROUTE": "none"}, {}, expected_digest=None,
    )
    original_content = system_config.config_path(root).read_bytes()
    backup = root / "jazn_system_config.previous.json"
    assert not backup.exists()

    configuration_studio.save_profile(root, {"JAZN_MEMORY_MODE": "off"}, expected_sha256=None)
    _, accepted_sha256 = configuration_studio.profile_snapshot(root)
    assert accepted_sha256 is not None
    snapshot = configuration_studio.profile_snapshot
    count = 0

    def race_on_second_snapshot(candidate: str | Path):
        nonlocal count
        values = snapshot(candidate)
        count += 1
        if count == 2:
            profile_path = configuration_studio.profile_file(root)
            profile_path.write_text(
                json.dumps({"schema": configuration_studio.SCHEMA,
                            "values": {"JAZN_MEMORY_MODE": "required"}}),
                encoding="utf-8",
            )
        return values

    monkeypatch.setattr(configuration_studio, "profile_snapshot", race_on_second_snapshot)
    with pytest.raises(system_config.SystemConfigError, match="zmieniono"):
        system_config.migrate_operator_profile(root, expected_sha256=accepted_sha256)

    assert count == 2
    assert system_config.config_path(root).read_bytes() == original_content
    assert not backup.exists()
    assert system_config.read_system_config(root).digest == initial.digest
