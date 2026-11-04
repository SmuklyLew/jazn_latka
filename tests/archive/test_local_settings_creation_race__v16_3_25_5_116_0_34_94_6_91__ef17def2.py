"""Deterministic directory-creation races and settings transaction stress."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from latka_jazn.core.local_settings_layout import (
    LocalSettingsLayout, resolve_local_settings_layout, verify_local_descendant,
)
from tools.jazn_run_studio.core import load_settings, settings_path


@pytest.mark.skipif(os.name != "nt", reason="Native Windows realpath interleaving")
@pytest.mark.parametrize("created", ["local", "operator"])
def test_directory_created_after_initial_lookup(tmp_path, monkeypatch, created):
    import ntpath

    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    system = system.resolve()
    local = system / ".settings_local"
    operator = local / "operator"
    target = operator / "jazn_run_studio"
    layout = LocalSettingsLayout(system, system / ".settings", local,
                                 operator, local / "acceptance")
    original = getattr(ntpath, "_getfinalpathname")
    injected = False
    errors = []

    def lookup(path):
        nonlocal injected
        try:
            return original(path)
        except FileNotFoundError as exc:
            if Path(path) == target and not injected:
                errors.append(exc.winerror)
                injected = True
                # A distinct process creates only the missing parent, after
                # the OS lookup failed and before realpath handles its error.
                parent = local if created == "local" else operator
                subprocess.run(
                    [sys.executable, "-I", "-c",
                     "import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)",
                     str(parent)], check=True, capture_output=True, text=True,
                    timeout=20,
                )
            raise

    monkeypatch.setattr(ntpath, "_getfinalpathname", lookup)
    actual = verify_local_descendant(target, layout)
    assert injected and errors == [3]
    assert actual == target
    assert not target.exists()
    assert actual.is_relative_to(local)


def test_permission_error_is_not_treated_as_missing(tmp_path, monkeypatch):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    layout = resolve_local_settings_layout(system)
    target = layout.operator / "settings.json"
    original = type(target).resolve

    def resolve(path, *args, **kwargs):
        if path == target:
            raise PermissionError("access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(target), "resolve", resolve)
    with pytest.raises(PermissionError, match="access denied"):
        verify_local_descendant(target, layout)


@pytest.mark.parametrize("suffix", ["../outside", "operator/../../outside"])
def test_traversal_still_refused(tmp_path, suffix):
    system = tmp_path / "system"
    (system / ".settings").mkdir(parents=True)
    layout = resolve_local_settings_layout(system)
    with pytest.raises(ValueError, match="escapes"):
        verify_local_descendant(layout.local / suffix, layout)
    with pytest.raises(ValueError, match="escapes"):
        verify_local_descendant(tmp_path / "outside", layout)


@pytest.mark.parametrize("iteration", range(20))
def test_simultaneous_first_writes_are_serialized(tmp_path, monkeypatch, iteration):
    system = tmp_path / f"system-{iteration}"
    (system / ".settings").mkdir(parents=True)
    for key in ("JAZN_STUDIO_ACCEPTANCE_PROFILE", "JAZN_OPERATOR_STATE_ROOT",
                "JAZN_MEMORY_ROOT", "JAZN_RUNTIME_WORKSPACE_DIR"):
        monkeypatch.delenv(key, raising=False)
    worker = """
import sys
from pathlib import Path
from tools.jazn_run_studio.core import Settings, StudioError, save_settings
print('READY', flush=True)
assert sys.stdin.readline().strip() == 'GO'
try:
    save_settings(Path(sys.argv[1]), Settings(mcp_port=sys.argv[2]), None)
except StudioError as exc:
    print(str(exc), flush=True)
    raise SystemExit(9)
"""
    processes = [subprocess.Popen(
        [sys.executable, "-X", "utf8", "-c", worker, str(system), str(port)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    ) for port in (8081, 8082)]
    try:
        for process in processes:
            assert process.stdout is not None
            assert process.stdout.readline().strip() == "READY"
        for process in processes:
            assert process.stdin is not None
            process.stdin.write("GO\n")
            process.stdin.flush()
        outcomes = [process.communicate(timeout=30) for process in processes]
        codes = sorted(process.returncode for process in processes)
        assert codes == [0, 9], (codes, outcomes)
        assert all("Traceback" not in stderr for _, stderr in outcomes)
        loaded, digest = load_settings(system)
        assert loaded.mcp_port in {"8081", "8082"} and digest is not None
        assert settings_path(system).with_suffix(".json.lock").is_file()
        assert not list(settings_path(system).parent.glob(".settings-*"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate()
