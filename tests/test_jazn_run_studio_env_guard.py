from pathlib import Path

import pytest

from tools.jazn_run_studio.core import Controller, Settings, StudioError


def system(tmp_path: Path) -> Path:
    root = tmp_path / "system"
    root.mkdir()
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").touch()
    (root / "main.py").touch()
    (root / "run.py").touch()
    return root


def test_external_secret_file_only_enters_child_environment_and_redactor(tmp_path: Path) -> None:
    root = system(tmp_path)
    secret = tmp_path / "private.json"
    secret.write_text('{"TUNNEL_TOKEN":"private-test-secret"}', encoding="utf-8")
    core = Controller(root, Settings(secrets_file=str(secret)))
    env = core.child_environment()
    assert env["TUNNEL_TOKEN"] == "private-test-secret"
    assert "private-test-secret" not in core.redactor.text("private-test-secret")
    assert "private-test-secret" not in str(core.report())


def test_secret_file_cannot_override_paths_or_arbitrary_environment(tmp_path: Path) -> None:
    root = system(tmp_path)
    secret = tmp_path / "private.json"
    secret.write_text('{"PATH":"untrusted-executable-directory"}', encoding="utf-8")
    core = Controller(root, Settings(secrets_file=str(secret)))
    with pytest.raises(StudioError):
        core.child_environment()


def test_nonignored_secret_inside_system_is_rejected(tmp_path: Path) -> None:
    root = system(tmp_path)
    secret = root / "tracked-secret.json"
    secret.write_text('{"TUNNEL_TOKEN":"must-not-load"}', encoding="utf-8")
    core = Controller(root, Settings(secrets_file=str(secret)))
    with pytest.raises(StudioError):
        core.child_environment()
