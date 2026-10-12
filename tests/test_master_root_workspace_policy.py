from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from latka_jazn.core.runtime_root import workspace_runtime_path


def test_master_checkout_uses_root_workspace_without_creating_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    master = tmp_path / "jazn_latka_master"
    master.mkdir()
    sibling = tmp_path / "workspace_runtime"
    assert workspace_runtime_path(master) == master / "workspace_runtime"
    assert not (master / "workspace_runtime").exists()
    assert not sibling.exists()


@pytest.mark.parametrize("name", ["runtime", "jazn_system", "jazn-v82", "jazn_latka_v16.3.25"])
def test_other_runtime_roots_keep_their_previous_workspace(
    tmp_path: Path, monkeypatch, name: str,
) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    runtime = tmp_path / name
    runtime.mkdir()
    assert workspace_runtime_path(runtime) == tmp_path / "workspace_runtime"


@pytest.mark.parametrize("token", ["$ROOT/workspace_runtime", "${ROOT}/workspace_runtime", r"$ROOT\workspace_runtime"])
def test_root_token_is_portable(tmp_path: Path, monkeypatch, token: str) -> None:
    monkeypatch.delenv("JAZN_RUNTIME_WORKSPACE_DIR", raising=False)
    root = tmp_path / "jazn_latka_master"
    root.mkdir()
    assert workspace_runtime_path(root, token) == root / "workspace_runtime"


@pytest.mark.parametrize("bad", ["$ROOT/../escape", "${ROOT}/../escape", "$ROOT/C:/bad", "$ROOT//absolute"])
def test_root_token_rejects_escape(tmp_path: Path, bad: str) -> None:
    root = tmp_path / "jazn_latka_master"
    root.mkdir()
    with pytest.raises(ValueError):
        workspace_runtime_path(root, bad)


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows PowerShell")
def test_windows_launcher_matches_python_root_resolution(tmp_path: Path, monkeypatch) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell, "Windows PowerShell is required for the portable launcher"
    root = tmp_path / "jazn_latka_master"
    root.mkdir()
    launcher = Path(__file__).resolve().parents[1] / "tools" / "Start-JaznPythonRuntime.ps1"
    script = launcher.read_text(encoding="utf-8")
    start = script.index("function Get-WorkspaceRoot(")
    end = script.index("\nfunction Assert-RuntimeSetIntegrity", start)
    definition = script[start:end]
    # Exercise the function without sourcing the launcher (which materializes runtime).
    command = definition + "\nGet-WorkspaceRoot -AppRoot '" + str(root).replace("'", "''") + "'"
    env = dict(os.environ, JAZN_RUNTIME_WORKSPACE_DIR=r"$ROOT\workspace_runtime")
    run = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        text=True, capture_output=True, timeout=20, env=env, check=False,
    )
    assert run.returncode == 0, run.stderr
    assert Path(run.stdout.strip()).resolve() == workspace_runtime_path(root, "$ROOT/workspace_runtime")
