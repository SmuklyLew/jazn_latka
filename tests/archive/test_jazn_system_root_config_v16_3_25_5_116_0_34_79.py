"""Local ROOT config and workspace separation regression."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from latka_jazn.core.system_config import (
    SystemConfigError, apply_system_config, config_path,
    read_system_config, write_system_config,
)
from tools.jazn_run_studio.core import Settings, load_settings, save_settings


def test_root_config_env_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "SYSTEM"
    root.mkdir()
    old = tmp_path / "old"
    write_system_config(root, {"JAZN_RUNTIME_WORKSPACE_DIR": str(old), "JAZN_MEMORY_MODE": "off"},
                        {"model": "gemma3:latest", "daemon_url": "http://127.0.0.1:8878"},
                        expected_digest=None)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "new"))
    env = dict(os.environ)
    provenance = apply_system_config(root, env)
    assert provenance["JAZN_RUNTIME_WORKSPACE_DIR"] == "explicit_env"
    assert env["JAZN_MEMORY_MODE"] == "off"
    settings, _ = load_settings(root)
    assert settings.model == "gemma3:latest"
    assert settings.daemon_url.endswith(":8878")


def test_studio_settings_survive_workspace_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "SYSTEM"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace-one"))
    settings = Settings(model="gemma3:latest", daemon_url="http://127.0.0.1:8878")
    assert save_settings(root, settings, expected=None)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace-two"))
    effective, digest = load_settings(root)
    assert digest is None
    assert effective.daemon_url == settings.daemon_url
    assert effective.model == settings.model


def test_config_rejects_secrets_bad_url_and_duplicates(tmp_path: Path) -> None:
    with pytest.raises(SystemConfigError):
        write_system_config(tmp_path, {"JAZN_MCP_OAUTH_CLIENT_SECRET": "bad"}, {}, expected_digest=None)
    with pytest.raises(SystemConfigError):
        write_system_config(tmp_path, {}, {"daemon_url": "http://not-loopback:8878"}, expected_digest=None)
    config_path(tmp_path).write_text(
        '{"schema_version":"jazn_system_config/v1","schema_version":"jazn_system_config/v1","values":{},"studio":{}}',
        encoding="utf-8",
    )
    with pytest.raises(SystemConfigError, match="Powtórzony"):
        read_system_config(tmp_path)


def test_config_backup_and_compare_and_swap(tmp_path: Path) -> None:
    first = write_system_config(tmp_path, {"JAZN_MEMORY_MODE": "off"}, {}, expected_digest=None)
    before = config_path(tmp_path).read_bytes()
    with pytest.raises(SystemConfigError, match="Konflikt"):
        write_system_config(tmp_path, {"JAZN_MEMORY_MODE": "required"}, {}, expected_digest=None)
    assert config_path(tmp_path).read_bytes() == before
    second = write_system_config(tmp_path, {"JAZN_MEMORY_MODE": "optional"}, {},
                                 expected_digest=first.digest)
    assert second.digest != first.digest
    backup = json.loads((tmp_path / "jazn_system_config.previous.json").read_text(encoding="utf-8"))
    assert backup["values"]["JAZN_MEMORY_MODE"] == "off"
