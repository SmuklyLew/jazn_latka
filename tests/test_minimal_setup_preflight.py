"""Isolated first-run preflight tests without a live model or private memory."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from latka_jazn.tools.minimal_setup import (
    FUTURE_PROFILE, _probe_ollama, inspect_minimal_setup, main,
)
from latka_jazn.tools.configuration_studio import read_profile


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "main.py").write_text("# test only\n", encoding="utf-8")
    (tmp_path / "latka_jazn" / "version.py").write_text("# test only\n", encoding="utf-8")
    return tmp_path


def test_read_only_default_never_claims_activation(root: Path) -> None:
    result = inspect_minimal_setup(root)
    assert result["read_only"] is True
    assert result["ollama"]["status"] == "not_probed"
    for key in ("daemon_ready_verified", "mcp_tools_verified", "oauth_ready_verified",
                "memory_continuity_verified", "accepted_turn_verified"):
        assert result[key] is False
    assert not (root / "workspace_runtime").exists()


def test_explicit_creation_only_sets_future_process_profile(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(root), "--json", "--create-profile"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["future_profile_present"] is True
    assert result["profile_created"] is True
    assert result["daemon_ready_verified"] is False
    assert read_profile(root) == FUTURE_PROFILE
    with pytest.raises(SystemExit):
        main(["--root", str(root), "--create-profile"])
    assert read_profile(root) == FUTURE_PROFILE


def test_ollama_probe_refuses_any_non_loopback_target() -> None:
    with pytest.raises(ValueError, match="only_allows"):
        _probe_ollama("https://somewhere.example")


def test_ollama_probe_missing_server_never_means_model_failure() -> None:
    result = _probe_ollama(timeout=0.5)
    assert result["status"] in {"observed", "probe_failed"}
    if result["status"] == "probe_failed":
        assert result["loaded_models"] is None
    assert "generation_verified" not in result or result["generation_verified"] is False
