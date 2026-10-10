from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from latka_jazn.tools.application_shell import DiagnosticsHub, ShellSettings
from latka_jazn.tools.application_shell.operator_paths import (
    OperatorPathError, operator_file, operator_state_dir,
)


def _snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def layout(tmp_path, monkeypatch):
    system = tmp_path / "SYSTEM"
    (system / "latka_jazn").mkdir(parents=True)
    (system / "latka_jazn" / "version.py").write_text('VERSION = "1.2.3"\n', encoding="utf-8")
    (system / "run.py").write_text("pass\n", encoding="utf-8")
    (system / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (system / "tests").mkdir()
    (system / "tests" / "test_demo.py").write_text("def test_demo():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    support = system / "tools" / "jazn_tests_studio"
    support.mkdir(parents=True)
    (support / "test_contracts.json").write_text(json.dumps({"contracts": {"tests/test_demo.py::test_demo": {"status": "current"}}}), encoding="utf-8")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(tmp_path / "operator"))
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_PACK_GENERATOR_SETTINGS", raising=False)
    return system


def test_defaults_are_external_and_discovery_does_not_create_directories(layout, tmp_path, monkeypatch):
    monkeypatch.delenv("JAZN_OPERATOR_STATE_ROOT")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    path = operator_state_dir("example", layout)
    assert path == tmp_path / "home" / ".jazn" / "tools" / "example"
    assert not path.exists()


def test_test_studio_roundtrip_and_log_preserve_system_bytes(layout):
    from tools.jazn_tests_studio import core, app
    before = _snapshot(layout)
    core.save_ui_settings(layout, ShellSettings(ui_mode="text", log_level="DEBUG"))
    assert core.load_ui_settings(layout).ui_mode == "text"
    core.set_review(layout, "tests/test_demo.py::test_demo", "review_required", notes="Synthetic review")
    assert core.load_reviews(layout)["reviews"]["tests/test_demo.py::test_demo"]["notes"] == "Synthetic review"
    assert app.main(["--root", str(layout), "audit"]) == 0
    hub = DiagnosticsHub("jazn-tests-studio", core.state_dir(layout))
    assert hub.log_path.is_file()
    assert _snapshot(layout) == before


def test_reviews_are_isolated_by_system(layout, tmp_path):
    from tools.jazn_tests_studio import core
    other = tmp_path / "SYSTEM-other"
    other.mkdir()
    core.save_reviews(layout, {"reviews": {"synthetic": {"status": "obsolete"}}})
    assert core.reviews_path(layout) != core.reviews_path(other)
    assert core.load_reviews(other)["reviews"] == {}


def test_legacy_test_state_is_read_only_until_explicit_save(layout):
    from tools.jazn_tests_studio import core
    support = core.support_dir(layout)
    (support / "local_settings.json").write_text('{"ui_mode":"text"}', encoding="utf-8")
    (support / "reviews.json").write_text('{"reviews":{"old":{"status":"obsolete"}}}', encoding="utf-8")
    before = _snapshot(layout)
    assert core.load_ui_settings(layout).ui_mode == "text"
    assert core.load_reviews(layout)["reviews"]["old"]["status"] == "obsolete"
    assert not core.state_dir(layout).exists()
    core.save_ui_settings(layout, ShellSettings(ui_mode="tui"))
    core.save_reviews(layout, {"reviews": {}})
    assert core.load_ui_settings(layout).ui_mode == "tui"
    assert core.load_reviews(layout)["reviews"] == {}
    assert _snapshot(layout) == before


def test_pack_configuration_legacy_fallback_and_new_save_leave_system_unchanged(layout, monkeypatch):
    from tools.jazn_pack_generator_app import settings
    from tools import jazn_pack_generator as launcher
    old = layout / "tools" / "jazn_pack_generator_app"
    old.mkdir()
    monkeypatch.setattr(settings, "__file__", str(old / "settings.py"))
    monkeypatch.setattr(launcher, "ROOT", layout)
    (old / settings.SETTINGS_FILENAME).write_text('{"ui_mode":"text"}', encoding="utf-8")
    before = _snapshot(layout)
    assert settings.load_settings()["ui_mode"] == "text"
    assert not settings.settings_path().exists()
    settings.save_settings({"ui_mode": "tui"})
    assert settings.load_settings()["ui_mode"] == "tui"
    assert launcher.main(["config"]) == 0
    assert (operator_state_dir("jazn-pack-generator", layout) / "runtime" / "jazn-pack-generator.jsonl").is_file()
    assert _snapshot(layout) == before


def test_version_settings_and_diff_backup_preserve_system(layout, monkeypatch):
    from tools import jazn_version_rebuild as version
    monkeypatch.setattr(version, "app_dir", lambda: layout / "tools")
    before = _snapshot(layout)
    path = version.default_settings_path()
    defaults = version.load_settings(path)
    assert Path(defaults.root) == layout
    version.save_settings(path, defaults)
    assert version.load_settings(path) == defaults
    folder = operator_state_dir("jazn-version-rebuild", layout, per_system=True)
    backup = version.diff_backup(folder, "synthetic", "version", "1.2.3", "1.2.4", {Path("version.py"): b"before\n"}, {Path("version.py"): b"after\n"})
    assert "-before" in backup.read_text(encoding="utf-8")
    assert "+after" in backup.read_text(encoding="utf-8")
    assert _snapshot(layout) == before


@pytest.mark.parametrize("kind", ["system", "memory", "workspace", "relative", "traversal", "file"])
def test_explicit_operator_root_rejects_protected_and_invalid_paths(layout, tmp_path, monkeypatch, kind):
    memory = tmp_path / "private-memory"
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory))
    bad_file = tmp_path / "not-a-directory"
    bad_file.write_text("data", encoding="utf-8")
    values = {"system": layout / "state", "memory": memory / "state", "workspace": tmp_path / "workspace_runtime" / "state", "relative": Path("relative-state"), "traversal": tmp_path / "x" / ".." / "state", "file": bad_file}
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(values[kind]))
    with pytest.raises(OperatorPathError):
        operator_state_dir("example", layout)


def test_pack_explicit_settings_cannot_write_to_system(layout, monkeypatch):
    from tools.jazn_pack_generator_app import settings
    monkeypatch.setattr(settings, "__file__", str(layout / "tools" / "jazn_pack_generator_app" / "settings.py"))
    monkeypatch.setenv("JAZN_PACK_GENERATOR_SETTINGS", str(layout / "operator.json"))
    before = _snapshot(layout)
    with pytest.raises(OperatorPathError):
        settings.save_settings({})
    assert _snapshot(layout) == before


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("destination", ["system", "external"])
def test_redirected_state_children_are_rejected(layout, tmp_path, destination):
    state = operator_state_dir("example", layout)
    state.mkdir(parents=True)
    target = layout if destination == "system" else tmp_path / "external"
    target.mkdir(exist_ok=True)
    _directory_link(state / "runtime", target)
    with pytest.raises(OperatorPathError):
        operator_state_dir("example", layout)


def test_redirected_operator_root_into_system_is_rejected(layout, tmp_path, monkeypatch):
    alias = tmp_path / "alias"
    _directory_link(alias, layout)
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(alias))
    with pytest.raises(OperatorPathError):
        operator_state_dir("example", layout)


def test_invalid_filenames_and_directory_leaf_are_rejected(layout):
    for filename in ("../settings.json", "a/b", "a\\b", ".."):
        with pytest.raises(OperatorPathError):
            operator_file("example", layout, filename)
    path = operator_file("example", layout, "settings.json")
    path.mkdir(parents=True)
    with pytest.raises(OperatorPathError):
        operator_file("example", layout, "settings.json")


def test_real_pytest_run_keeps_cache_and_bytecode_outside_system(layout, monkeypatch):
    from tools.jazn_tests_studio.runner import PytestRun
    from tools.jazn_tests_studio import core
    tools_root = Path(core.__file__).resolve().parents[1]
    # The plugin is shipped alongside the launcher; synthetic SYSTEM contains
    # only the test under execution, not another copy of the application.
    monkeypatch.setenv("PYTHONPATH", str(tools_root) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    before = _snapshot(layout)
    run = PytestRun(layout, ["tests/test_demo.py"], timeout=30).start()
    result = run.wait(timeout=40)
    assert result["returncode"] == 0, result
    assert (core.state_dir(layout) / "pytest_cache").is_dir()
    assert _snapshot(layout) == before
    assert not list(layout.rglob("__pycache__"))
    assert not (layout / ".pytest_cache").exists()


def test_runner_reports_invalid_state_destination_without_hanging(layout, monkeypatch):
    from tools.jazn_tests_studio.runner import PytestRun
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(layout / "invalid-state"))
    before = _snapshot(layout)
    run = PytestRun(layout, ["tests/test_demo.py"], timeout=30).start()
    result = run.wait(timeout=5)
    assert result["ok"] is False
    assert result["outcome"] == "error"
    assert "OperatorPathError" in result["error"]
    assert _snapshot(layout) == before


def test_pack_explicit_external_settings_roundtrip_does_not_read_legacy(layout, tmp_path, monkeypatch):
    from tools.jazn_pack_generator_app import settings
    old = layout / "tools" / "jazn_pack_generator_app"
    old.mkdir()
    monkeypatch.setattr(settings, "__file__", str(old / "settings.py"))
    (old / settings.SETTINGS_FILENAME).write_text('{"ui_mode":"text"}', encoding="utf-8")
    explicit = tmp_path / "custom" / "settings.json"
    monkeypatch.setenv("JAZN_PACK_GENERATOR_SETTINGS", str(explicit))
    before = _snapshot(layout)
    assert settings.load_settings()["ui_mode"] == settings.DEFAULT_UI_MODE
    settings.save_settings({"ui_mode": "tui"})
    assert explicit.is_file()
    assert settings.load_settings()["ui_mode"] == "tui"
    assert _snapshot(layout) == before


def test_relative_memory_override_uses_workspace_even_when_junction_points_outside(layout, tmp_path, monkeypatch):
    workspace = tmp_path / "host" / "workspace_runtime"
    workspace.mkdir(parents=True)
    memory = tmp_path / "detached-private-memory"
    memory.mkdir()
    _directory_link(workspace / "relative-memory", memory)
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_ROOT", "relative-memory")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(memory / "operator"))
    with pytest.raises(OperatorPathError):
        operator_state_dir("example", layout)
    assert not (memory / "operator").exists()


def test_version_legacy_backups_remain_readable_without_migration(layout, monkeypatch):
    from tools import jazn_version_rebuild as version
    monkeypatch.setattr(version, "app_dir", lambda: layout / "tools")
    old = layout / "tools" / "legacy.diff"
    old.write_text("synthetic legacy diff\n", encoding="utf-8")
    before = _snapshot(layout)
    folder = operator_state_dir("jazn-version-rebuild", layout, per_system=True)
    assert version.backup_paths(folder) == [old]
    assert not folder.exists()
    assert _snapshot(layout) == before
