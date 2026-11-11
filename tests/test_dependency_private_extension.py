"""Regression tests for the single ROOT/.venv Dependency Studio contract.

No network, live daemon, MEMORY, or real installation in these tests.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from latka_jazn.dependencies import private_extension as ext
from latka_jazn.dependencies.common import DependencyStudioError
from latka_jazn.tools import dependency_studio


def test_additive_inventory_never_replaces_installed_versions() -> None:
    resolved = [
        {"name": "packaging", "version": "26.2", "sha256": "a" * 64},
        {"name": "pytest", "version": "9.2.0", "sha256": "b" * 64},
    ]
    assert [row["name"] for row in ext.missing_distributions(
        resolved, {"packaging": "26.2"},
    )] == ["pytest"]
    assert ext.missing_distributions(
        resolved, {"packaging": "26.2", "pytest": "9.2.0"},
    ) == []
    with pytest.raises(DependencyStudioError, match="existing_package_version_drift"):
        ext.missing_distributions(resolved, {"packaging": "25.0"})


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "SYSTEM"
    (root / "local_resources" / "python").mkdir(parents=True)
    python = ext.private_python_path(root)
    python.parent.mkdir(parents=True)
    python.touch()
    marker = root / "local_resources" / "python" / "JAZN_DEPENDENCY_ENVIRONMENT.json"
    bundle = tmp_path / "verified"
    bundle.mkdir()
    (bundle / "JAZN_WHEELHOUSE_MANIFEST.json").write_text("{}", encoding="utf-8")
    (bundle / "JAZN_WHEELHOUSE_REQUIREMENTS.txt").write_text("", encoding="utf-8")
    fingerprint = "a" * 64
    target = {
        "alias": "windows-x64" if sys.platform == "win32" else "linux-x64",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "implementation": "cp",
        "abi": f"cp{sys.version_info.major}{sys.version_info.minor}",
    }
    manifest = {
        "profiles": ["core", "run-studio", "mcp-http", "test-evidence"],
        "resolved_profiles": ["core", "run-studio", "mcp-http", "test-evidence"],
        "target": target,
        "requirements": ["pytest>=8.3,<10"],
        "dependency_contract_fingerprint": fingerprint,
        "resolved_distributions": [
            {"name": "packaging", "version": "26.2", "sha256": "a" * 64},
            {"name": "pytest", "version": "9.2.0", "sha256": "b" * 64},
        ],
    }
    state = {"inspect": 0, "commands": []}
    monkeypatch.setattr(ext, "private_python_status", lambda _root: {"ready": True})
    monkeypatch.setattr(ext, "verify_bundle", lambda _bundle: {"ok": True})
    monkeypatch.setattr(ext, "read_manifest", lambda _path: manifest)
    monkeypatch.setattr(ext, "_probe_python", lambda _exe: {
        "platform": target["alias"],
        "python_version": target["python_version"],
        "implementation": target["implementation"],
        "abi": target["abi"],
        "libc_family": "not-applicable",
    })
    monkeypatch.setattr(ext, "sha256_file", lambda _path: "c" * 64)
    monkeypatch.setattr(ext, "dependency_contract_fingerprint", lambda *_a: fingerprint)
    monkeypatch.setattr(ext, "active_runtime_marker_path",
                        lambda _root: root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json")

    def inspect(_python, **_kw):
        state["inspect"] += 1
        inventory = [("packaging", "26.2")]
        if state["inspect"] > 1:
            inventory.append(("pytest", "9.2.0"))
        return {"installed": [
            {"metadata": {"name": name, "version": version}}
            for name, version in inventory
        ]}
    monkeypatch.setattr(ext, "_pip_inspect", inspect)

    def run(command, **_kw):
        state["commands"].append(command)
        if "-c" in command:
            return SimpleNamespace(stdout=json.dumps({"pytest": True}))
        return SimpleNamespace(stdout="No broken requirements found.")
    monkeypatch.setattr(ext, "_run", run)
    return root, python, marker, bundle, state


def test_extension_adds_only_absent_wheels_to_root_venv(prepared) -> None:
    root, python, marker, bundle, state = prepared
    result = ext.extend_private_environment(root, bundle, python_executable=str(python))
    assert result["ok"] is True
    assert result["state"] == "private_environment_extended"
    assert result["missing_count"] == 1
    assert result["activation_marker_updated"] is True
    assert result["python_executable"] == str(python)
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    assert Path(recorded["environment_root"]) == root / ".venv"
    assert Path(recorded["python_executable"]) == python
    assert recorded["resolved_profiles"] == ["core", "run-studio", "mcp-http", "test-evidence"]
    install = next(command for command in state["commands"] if "install" in command)
    assert "--no-index" in install
    assert "--require-hashes" in install
    assert "--no-deps" in install


def test_extension_refuses_active_runtime_even_if_marker_stale(
    prepared, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, python, marker, bundle, _state = prepared
    active = root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    active.parent.mkdir()
    active.write_text("{}", encoding="utf-8")
    with pytest.raises(DependencyStudioError, match="active_runtime_marker_present"):
        ext.extend_private_environment(root, bundle)
    assert not marker.exists()


def test_extension_rejects_foreign_python(prepared) -> None:
    root, python, marker, bundle, _state = prepared
    with pytest.raises(DependencyStudioError, match="extension_interpreter_must_be_root_private_venv"):
        ext.extend_private_environment(root, bundle, python_executable=str(root / "other" / "python.exe"))
    assert not marker.exists()


def test_extension_dry_run_never_writes_marker_or_installs(prepared) -> None:
    root, python, marker, bundle, state = prepared
    result = ext.extend_private_environment(root, bundle, dry_run=True)
    assert result["state"] == "private_environment_extension_plan"
    assert result["missing_count"] == 1
    assert not marker.exists()
    assert state["commands"] == []


def test_extension_failure_does_not_publish_activation(
    prepared, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, python, marker, bundle, _state = prepared
    marker.write_text("old-active-marker", encoding="utf-8")
    def fail_install(command, **_kw):
        raise DependencyStudioError("simulated_pip_install_failure")
    monkeypatch.setattr(ext, "_run", fail_install)
    with pytest.raises(DependencyStudioError, match="simulated_pip_install_failure"):
        ext.extend_private_environment(root, bundle)
    assert marker.read_text(encoding="utf-8") == "old-active-marker"


def test_extend_cli_requires_explicit_offline_and_uses_single_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "wheelhouse"
    bundle.mkdir()
    monkeypatch.setattr(
        ext, "extend_private_environment", lambda root, bundle, **kw: {
            "ok": True, "state": "private_environment_extended",
            "python_executable": "private-venv-only", "activation_marker_updated": True,
        },
    )
    ns = dependency_studio.build_parser().parse_args([
        "--root", str(tmp_path), "extend", "--bundle", str(bundle),
        "--profile", "core,run-studio,test-evidence",
    ])
    with pytest.raises(DependencyStudioError, match="requires --offline"):
        dependency_studio.execute(ns)
    ns.offline = True
    code, result = dependency_studio.execute(ns)
    assert code == 0
    assert result["command"] == "extend"
    assert result["python_executable"] == "private-venv-only"
