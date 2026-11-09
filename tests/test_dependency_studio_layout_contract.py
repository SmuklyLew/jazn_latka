"""Synthetic regression for ROOT-local JSS installer and Dependency Studio layout routing.

No wheelhouse is downloaded and no venv is created by these tests.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from latka_jazn.tools import dependency_studio as studio


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, layout: str, *extras: str):
    root.mkdir(parents=True, exist_ok=True)
    (root / "local_resources").mkdir(exist_ok=True)
    observed: list[dict] = []
    def fake_install(*_args, **kwargs):
        observed.append(kwargs)
        return {"ok": True, "state": "synthetic", "python_executable": "not-executed"}
    monkeypatch.setattr(studio, "install_bundle", fake_install)
    monkeypatch.setattr(studio, "activation_profile_names", lambda _: ["core"])
    args = studio.build_parser().parse_args([
        "--root", str(root), "install", "--offline", "--bundle",
        str(root / "synthetic-wheelhouse"), "--layout", layout, *extras,
    ])
    result = studio.execute(args)
    return result, observed


def test_project_layout_preserves_root_local_venv_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_DEPENDENCY_ENVIRONMENTS", raising=False)
    (code, report), observed = _run(tmp_path / "project", monkeypatch, "project")
    assert code == 0 and report["ok"] is True
    assert len(observed) == 1
    assert observed[0]["environments_root"] is None
    assert observed[0]["offline"] is True


def test_managed_layout_uses_distinct_root_local_environment_collection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_DEPENDENCY_ENVIRONMENTS", raising=False)
    root = tmp_path / "managed"
    (code, report), observed = _run(root, monkeypatch, "managed")
    assert code == 0 and report["ok"] is True
    assert observed[0]["environments_root"] == root / "local_resources" / "python" / "environments"
    assert observed[0]["environments_root"] != root / ".venv"


def test_explicit_project_layout_rejects_ambient_managed_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_DEPENDENCY_ENVIRONMENTS", str(tmp_path / "foreign"))
    with pytest.raises(studio.DependencyStudioError, match="project_layout_conflicts"):
        _run(tmp_path / "project", monkeypatch, "project")


def test_explicit_project_layout_rejects_conflicting_custom_root(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_DEPENDENCY_ENVIRONMENTS", raising=False)
    with pytest.raises(studio.DependencyStudioError, match="project_layout_conflicts"):
        _run(tmp_path / "project", monkeypatch, "project", "--environment-root", str(tmp_path / "foreign"))
