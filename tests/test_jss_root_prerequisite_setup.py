"""Fail-closed, no-network tests for JSS ROOT-local prerequisite operations."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from latka_jazn.tools import jss_prerequisite_setup as setup


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "run.py").write_text("# fixture\n", encoding="utf-8")
    (tmp_path / "latka_jazn").mkdir()
    return tmp_path


def test_layout_is_root_local_not_host_workspace(root: Path) -> None:
    paths = setup.root_paths(root)
    assert paths["venv"] == root / ".venv"
    assert paths["wheelhouse"] == root / "local_resources" / "wheelhouse"
    assert paths["models"] == root / "local_resources" / "models"
    assert "workspace_runtime" not in str(paths["wheelhouse"])
    assert not paths["resources"].exists()


def test_invalid_root_rejected_without_writes(tmp_path: Path) -> None:
    with pytest.raises(setup.ProvisioningError, match="not_a_jazn_system_root"):
        setup.root_paths(tmp_path)
    assert not (tmp_path / ".venv").exists()


def test_inspect_never_installs_or_creates_paths(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "detect_ollama", lambda: "")
    monkeypatch.setattr(setup, "ollama_api", lambda *a, **k: {"ok": False})
    result = setup.inspect(root)
    assert result["python_314_ready"] is False
    assert result["default_model"] == "gemma3:latest"
    assert result["runtime_ready"] is None
    assert not (root / ".venv").exists()
    assert not (root / "local_resources").exists()


def test_venv_creation_requires_approval(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "python_314", lambda _: True)
    with pytest.raises(setup.ProvisioningError, match="approval_required"):
        setup.prepare_venv(root, base_python="python314", approved=False)
    assert not (root / ".venv").exists()


def test_invalid_existing_venv_is_preserved(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / ".venv").mkdir()
    (root / ".venv" / "important.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(setup, "python_314", lambda _: False)
    with pytest.raises(setup.ProvisioningError, match="manual_recovery"):
        setup.prepare_venv(root, base_python="python314", approved=True)
    assert (root / ".venv" / "important.txt").read_text(encoding="utf-8") == "keep"


def test_venv_creation_uses_python_314_and_root_path(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        destination = Path(command[-1])
        destination.mkdir()
        (destination / "pyvenv.cfg").write_text("home=test\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(setup, "python_314", lambda _: True)
    monkeypatch.setattr(setup.subprocess, "run", fake_run)
    response = setup.prepare_venv(root, base_python="python314", approved=True)
    assert response["state"] == "created"
    assert commands == [["python314", "-I", "-m", "venv", str(root / ".venv")]]


def test_dependency_download_requires_approval(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "python_314", lambda _: True)
    with pytest.raises(setup.ProvisioningError, match="approval_required"):
        setup.download_dependencies(root, base_python="python314", approved=False)
    assert not (root / "local_resources").exists()


def test_offline_install_never_runs_without_approval(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup.subprocess, "run",
                        lambda *_args, **_kwargs: pytest.fail("unexpected subprocess"))
    with pytest.raises(setup.ProvisioningError, match="approval_required"):
        setup.install_offline(root, bundle=root / "bad", approved=False)


def test_model_name_rejected_before_any_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "urlopen",
                        lambda *_args, **_kwargs: pytest.fail("unexpected network"))
    for model in ("", "../evil", "model\r\n", "--help", "gemma3;rm -rf /"):
        with pytest.raises(setup.ProvisioningError, match="invalid_model_name"):
            setup.ollama_pull(model=model, approved=True)


def test_ollama_windows_install_requires_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup.subprocess, "run",
                        lambda *_args, **_kwargs: pytest.fail("unexpected install"))
    with pytest.raises(setup.ProvisioningError, match="approval_required"):
        setup.install_ollama_windows(approved=False)


def test_cli_inspect_returns_json(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(setup, "detect_ollama", lambda: "")
    monkeypatch.setattr(setup, "ollama_api", lambda *a, **k: {"ok": False})
    assert setup.main(["--root", str(root), "inspect"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["schema_version"] == "jazn_jss_prerequisites/v1"
    assert parsed["default_model"] == "gemma3:latest"
