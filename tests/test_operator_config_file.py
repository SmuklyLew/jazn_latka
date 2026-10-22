from __future__ import annotations

from pathlib import Path
import os

import pytest

from latka_jazn.operator_config import OperatorConfigError, load_operator_configuration


def _write(root: Path, filename: str, content: str) -> Path:
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_empty_files_keep_existing_code_defaults(tmp_path: Path) -> None:
    env = {}
    result = load_operator_configuration(tmp_path, environ=env)
    assert env == {}
    assert not result["defaults_file_present"]
    assert not result["secrets_file_present"]


def test_minimal_defaults_and_explicit_environment_wins(tmp_path: Path) -> None:
    _write(tmp_path, "config/jazn.toml", 'schema_version = 1\n[environment]\nJAZN_LLM_ROUTE="auto"\nJAZN_MEMORY_MODE="optional"\n')
    env = {"JAZN_LLM_ROUTE": "local"}
    result = load_operator_configuration(tmp_path, environ=env)
    assert env == {"JAZN_LLM_ROUTE": "local", "JAZN_MEMORY_MODE": "optional"}
    assert result["default_keys_applied"] == ["JAZN_MEMORY_MODE"]


def test_secret_file_loaded_only_if_missing_without_leaking(tmp_path: Path) -> None:
    _write(tmp_path, "config/jazn.toml", 'schema_version = 1\n[environment]\nJAZN_LLM_ROUTE="auto"\n')
    secret = _write(tmp_path, "config/jazn.secrets.env", "OPENAI_API_KEY=private-test-value\nJAZN_MCP_PROBE_TOKEN=another-private-value\n")
    if os.name != "nt":
        secret.chmod(0o600)
    env = {"OPENAI_API_KEY": "already-from-host"}
    result = load_operator_configuration(tmp_path, environ=env)
    assert env["OPENAI_API_KEY"] == "already-from-host"
    assert env["JAZN_MCP_PROBE_TOKEN"] == "another-private-value"
    assert "private-test-value" not in str(result)
    assert result["secret_count_applied"] == 1


@pytest.mark.parametrize("bad_line", ["JAZN_ROOT=/tmp/elsewhere", "KEYVALUE", "OPENAI_API_KEY=", "FOO_TOKEN=no", "OPENAI_API_KEY=x\nOPENAI_API_KEY=y"])
def test_rejects_bad_secret_file_without_mutating_environment(tmp_path: Path, bad_line: str) -> None:
    _write(tmp_path, "config/jazn.toml", 'schema_version = 1\n[environment]\nJAZN_LLM_ROUTE="auto"\n')
    secret = _write(tmp_path, "config/jazn.secrets.env", bad_line)
    if os.name != "nt":
        secret.chmod(0o600)
    env = {"ORIGINAL": "safe"}
    with pytest.raises(OperatorConfigError):
        load_operator_configuration(tmp_path, environ=env)
    assert env == {"ORIGINAL": "safe"}


def test_disallow_credentials_in_tracked_toml(tmp_path: Path) -> None:
    _write(tmp_path, "config/jazn.toml", 'schema_version = 1\n[environment]\nOPENAI_API_KEY="secret-accident"\n')
    with pytest.raises(OperatorConfigError, match="Niedozwolone klucze"):
        load_operator_configuration(tmp_path, environ={})


def test_rejects_symlink_secret(tmp_path: Path) -> None:
    actual = _write(tmp_path, "private.txt", "OPENAI_API_KEY=secret")
    secret = tmp_path / "config/jazn.secrets.env"
    secret.parent.mkdir()
    try:
        secret.symlink_to(actual)
    except (OSError, NotImplementedError):
        pytest.skip("system nie zezwala na symlinki")
    with pytest.raises(OperatorConfigError, match="link"):
        load_operator_configuration(tmp_path, environ={})


def test_rejects_world_readable_secret_on_posix(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX only")
    secret = _write(tmp_path, "config/jazn.secrets.env", "OPENAI_API_KEY=private")
    secret.chmod(0o644)
    with pytest.raises(OperatorConfigError, match="0600"):
        load_operator_configuration(tmp_path, environ={})
