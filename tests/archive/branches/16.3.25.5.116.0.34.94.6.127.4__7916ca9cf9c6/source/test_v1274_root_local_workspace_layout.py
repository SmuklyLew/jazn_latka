"""V127.4 ROOT-contained workspace regression tests; never start or stop daemons."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from latka_jazn.core.acceptance_layout import acceptance_temp_parent, resolve_acceptance_layout
from latka_jazn.core.runtime_root import (
    active_runtime_marker_path, default_runtime_workspace_path, workspace_runtime_path,
)


def prepared(tmp_path: Path, name: str = "jazn_latka_v127_4") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    (root / "local_resources").mkdir()
    return root


def test_modern_versioned_roots_never_adopt_sibling_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    a = prepared(tmp_path, "jazn_latka_v127_4_a")
    b = prepared(tmp_path, "jazn_latka_v127_4_b")
    sibling = tmp_path / "workspace_runtime"
    sibling.mkdir()
    (sibling / "JAZN_ACTIVE_RUNTIME.json").write_text("leave untouched")
    assert default_runtime_workspace_path(a) == a / "workspace_runtime"
    assert workspace_runtime_path(a) == a / "workspace_runtime"
    assert workspace_runtime_path(b) == b / "workspace_runtime"
    assert active_runtime_marker_path(a) != active_runtime_marker_path(b)
    assert not (a / "workspace_runtime").exists()
    assert (sibling / "JAZN_ACTIVE_RUNTIME.json").read_text() == "leave untouched"


@pytest.mark.parametrize("name", ["jazn_latka_v127_4", "jazn_latka_master", "runtime"])
def test_modern_managed_layout_is_root_local(tmp_path, monkeypatch, name):
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root = prepared(tmp_path / "runtime_roots", name)
    assert workspace_runtime_path(root) == root / "workspace_runtime"


@pytest.mark.parametrize("value", ["../outside", "$ROOT/../outside",
                                    "$" + "{ROOT}/../outside", "$ROOT/C:/escape", "."])
def test_modern_explicit_escape_is_denied(tmp_path, monkeypatch, value):
    root = prepared(tmp_path)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    with pytest.raises(ValueError):
        workspace_runtime_path(root, value)


def test_modern_absolute_external_override_cannot_adopt_old_marker(tmp_path, monkeypatch):
    root = prepared(tmp_path)
    outside = tmp_path / "old_state"
    outside.mkdir()
    (outside / "JAZN_ACTIVE_RUNTIME.json").write_text("old daemon state")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(outside))
    with pytest.raises(ValueError, match="workspace_escapes_root"):
        workspace_runtime_path(root)
    assert (outside / "JAZN_ACTIVE_RUNTIME.json").read_text() == "old daemon state"


def test_root_local_explicit_workspace_supported(tmp_path, monkeypatch):
    root = prepared(tmp_path)
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    expected = root / "workspace_runtime"
    assert workspace_runtime_path(root, "$ROOT/workspace_runtime") == expected
    assert workspace_runtime_path(root, expected) == expected
    assert workspace_runtime_path(root, "workspace_runtime") == expected


@pytest.mark.parametrize("name", ["workspace_runtime", "local_resources"])
def test_modern_redirected_workspace_or_resources_is_rejected(tmp_path, monkeypatch, name):
    root = prepared(tmp_path)
    link = root / name
    if name == "local_resources":
        link.rmdir()
    outside = tmp_path / "external"
    outside.mkdir()
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not support directory symlinks")
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    with pytest.raises(ValueError):
        workspace_runtime_path(root)


def test_bare_legacy_root_keeps_existing_layout(tmp_path, monkeypatch):
    root = tmp_path / "old-version"
    root.mkdir()
    shared = tmp_path / "workspace_runtime"
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    assert workspace_runtime_path(root) == shared
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(shared))
    assert workspace_runtime_path(root) == shared


def test_modern_acceptance_runtime_is_inside_local_settings(tmp_path, monkeypatch):
    root = prepared(tmp_path)
    (root / ".settings").mkdir()
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    layout = resolve_acceptance_layout(root)
    assert layout.runtime.is_relative_to(root / ".settings_local" / "acceptance")
    assert layout.operator.is_relative_to(root)
    assert layout.memory.is_relative_to(root)
    assert layout.runtime != workspace_runtime_path(root)


def test_nested_tpa_acceptance_base_is_owned_and_external_base_denied(tmp_path, monkeypatch):
    root = prepared(tmp_path)
    (root / ".settings").mkdir()
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    parent = acceptance_temp_parent(root)
    assert parent == root / ".settings_local" / "acceptance"
    nested = parent / "jazn_tpa_fixture"
    nested.mkdir()
    layout = resolve_acceptance_layout(root, base=nested)
    assert layout.runtime == nested / "runtime"
    assert layout.operator == nested / "operator"
    with pytest.raises(ValueError, match="acceptance_runtime_outside_root"):
        resolve_acceptance_layout(root, base=tmp_path / "outside")


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows PowerShell")
def test_windows_launcher_matches_python_for_modern_root(tmp_path, monkeypatch):
    shell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell unavailable")
    root = prepared(tmp_path)
    launcher = Path(__file__).resolve().parents[1] / "tools/Start-JaznPythonRuntime.ps1"
    text = launcher.read_text(encoding="utf-8")
    definition = text[text.index("function Get-WorkspaceRoot("):
                      text.index("\nfunction Assert-RuntimeSetIntegrity")]
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    for configured, allowed in [("", True), ("$ROOT/workspace_runtime", True),
                                (str(tmp_path / "external"), False)]:
        env = dict(os.environ, JAZN_RUNTIME_WORKSPACE_DIR=configured)
        command = definition + "\nGet-WorkspaceRoot -AppRoot '" + str(root).replace("'", "''") + "'"
        run = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                             capture_output=True, text=True, timeout=30, env=env)
        if allowed:
            assert run.returncode == 0, run.stderr
            assert Path(run.stdout.strip()).resolve() == workspace_runtime_path(root)
        else:
            assert run.returncode != 0
            assert "workspace_escapes_root" in run.stderr
