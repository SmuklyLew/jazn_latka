"""Regression coverage for opt-in Qt dependency recovery (no network)."""
from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import qt_recovery as recovery


def missing(name: str = "PySide6") -> ModuleNotFoundError:
    return ModuleNotFoundError("missing " + name, name=name)


def test_unrelated_import_error_never_offers_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    assert recovery.offer_qt_install(missing("unrelated_library"), allow_install=True) is False
    assert recovery.offer_qt_install(ImportError("DLL failure"), allow_install=True) is False


def test_ci_and_smoke_never_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery, "_interactive", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda _prompt: pytest.fail("unexpected prompt"))
    assert recovery.offer_qt_install(missing(), allow_install=True) is False
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    assert recovery.offer_qt_install(missing(), allow_install=False) is False


def test_cancel_never_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "0")
    monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_kw: pytest.fail("pip ran"))
    assert recovery.offer_qt_install(missing(), allow_install=True) is False


def test_no_virtualenv_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    monkeypatch.setattr(recovery, "_virtualenv", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "1")
    monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_kw: pytest.fail("pip ran"))
    assert recovery.offer_qt_install(missing(), allow_install=True) is False


def test_approved_install_uses_pypi_and_same_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    profile = tmp_path / recovery.REQUIREMENTS
    profile.parent.mkdir(parents=True)
    profile.write_text(".[run-studio]\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='latka-jazn'\n", encoding="utf-8")
    monkeypatch.setattr(recovery, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    monkeypatch.setattr(recovery, "_virtualenv", lambda: True)
    answers = iter(("1", "TAK"))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        seen["argv"] = argv
        seen.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(recovery.subprocess, "run", fake_run)
    monkeypatch.setattr(recovery.importlib, "import_module", lambda _name: object())
    assert recovery.offer_qt_install(missing(), allow_install=True) is True
    cmd = seen["argv"]
    assert isinstance(cmd, list)
    assert cmd[0] == recovery.sys.executable
    assert "--isolated" in cmd and "--require-virtualenv" in cmd
    assert recovery.PYPI_INDEX == cmd[cmd.index("--index-url") + 1]
    assert "--only-binary=:all:" in cmd
    assert seen["cwd"] == tmp_path
    assert seen["shell"] is False
    assert isinstance((env := seen["env"]), dict) and env["PIP_CONFIG_FILE"] == recovery.os.devnull


def test_explicit_denial_never_installs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    profile = tmp_path / recovery.REQUIREMENTS
    profile.parent.mkdir(parents=True)
    profile.write_text(".[run-studio]\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='latka-jazn'\n", encoding="utf-8")
    monkeypatch.setattr(recovery, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    monkeypatch.setattr(recovery, "_virtualenv", lambda: True)
    choices = iter(("2", "1", "NIE"))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(choices))
    monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_kw: pytest.fail("pip ran"))
    assert recovery.offer_qt_install(missing(), allow_install=True) is False


def test_qt_installer_accepts_tak_without_uppercase(monkeypatch, tmp_path: Path):
    profile = tmp_path / recovery.REQUIREMENTS
    profile.parent.mkdir(parents=True)
    profile.write_text(".[run-studio]\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='latka-jazn'\n", encoding="utf-8")
    monkeypatch.setattr(recovery, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "_interactive", lambda: True)
    monkeypatch.setattr(recovery, "_virtualenv", lambda: True)
    replies = iter(("1", "Tak"))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(replies))
    monkeypatch.setattr(recovery.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(recovery.importlib, "import_module", lambda _name: object())
    assert recovery.offer_qt_install(missing(), allow_install=True) is True
