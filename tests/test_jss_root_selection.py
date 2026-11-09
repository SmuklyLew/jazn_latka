"""JSS must never silently cross from one source checkout to another ROOT."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import app, dependency_preflight


def _stub_headless_studio(monkeypatch: pytest.MonkeyPatch, observed: list[tuple[Path, str | None]]) -> None:
    @contextmanager
    def acceptance(root: Path):
        observed.append((root, os.environ.get("JAZN_ROOT")))
        yield SimpleNamespace()

    def controller(root: Path):
        observed.append((root, os.environ.get("JAZN_ROOT")))
        return SimpleNamespace(settings=SimpleNamespace())

    monkeypatch.setattr(app, "acceptance_environment", acceptance)
    monkeypatch.setattr(app, "apply_system_config", lambda root, env: None)
    monkeypatch.setattr(app, "Controller", controller)
    monkeypatch.setattr(app, "discovery", lambda settings: {"ok": True})


def test_source_launch_ignores_stale_inherited_root_for_preflight_and_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = Path(app.__file__).resolve().parents[2]
    foreign = tmp_path / "foreign-master"
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("JAZN_ROOT", str(foreign))
    observed: list[tuple[Path, str | None]] = []
    _stub_headless_studio(monkeypatch, observed)

    assert dependency_preflight._root(["--isolated-acceptance"]) == source_root
    assert app.main(["--isolated-acceptance", "--check"]) == 0
    assert observed == [(source_root, str(source_root)), (source_root, str(source_root))]
    assert os.environ["JAZN_ROOT"] == str(foreign)


def test_explicit_root_overrides_inherited_root_in_both_entrypoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = tmp_path / "foreign-master"
    chosen = tmp_path / "chosen-operator-root"
    monkeypatch.setenv("JAZN_ROOT", str(foreign))
    observed: list[tuple[Path, str | None]] = []
    _stub_headless_studio(monkeypatch, observed)

    assert dependency_preflight._root(["--root", str(chosen)]) == chosen
    assert app.main(["--isolated-acceptance", "--root", str(chosen), "--check"]) == 0
    assert observed == [(chosen, str(chosen)), (chosen, str(chosen))]
    assert os.environ["JAZN_ROOT"] == str(foreign)


def test_root_scope_restores_environment_even_when_studio_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = tmp_path / "foreign-master"
    monkeypatch.setenv("JAZN_ROOT", str(foreign))

    def refuse(_: Path):
        assert os.environ["JAZN_ROOT"] == str(Path(app.__file__).resolve().parents[2])
        raise ValueError("synthetic refusal")

    monkeypatch.setattr(app, "Controller", refuse)
    monkeypatch.setattr(app, "apply_system_config", lambda root, env: None)
    assert app.main(["--check"]) == 2
    assert os.environ["JAZN_ROOT"] == str(foreign)


def test_root_scope_does_not_leave_new_environment_variable(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JAZN_ROOT", raising=False)
    root = Path(app.__file__).resolve().parents[2]
    with app._selected_root_environment(root):
        assert os.environ.get("JAZN_ROOT") == str(root)
    assert "JAZN_ROOT" not in os.environ


def test_frozen_preflight_and_gui_keep_explicit_environment_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = tmp_path / "frozen-selected-root"
    monkeypatch.setenv("JAZN_ROOT", str(foreign))
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    observed: list[tuple[Path, str | None]] = []
    _stub_headless_studio(monkeypatch, observed)
    assert dependency_preflight._root(["--isolated-acceptance"]) == foreign
    assert app.main(["--isolated-acceptance", "--check"]) == 0
    assert observed == [(foreign, str(foreign)), (foreign, str(foreign))]
