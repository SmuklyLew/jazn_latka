from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def generator():
    return importlib.import_module("tools.jazn_pack_generator")


def test_v89_public_entrypoint_and_v3_distribution_contract() -> None:
    module = generator()
    assert module.GENERATOR_VERSION == "8.9"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.9"
    plan = module.distribution_mode_plan("system-portable", target_alias="linux-x64", python_version="3.13.5")
    assert plan["dependencies"] is True
    assert plan["target_runtime"]["python_version"] == "3.13"
    assert plan["target_runtime"]["requested_python_version"] == "3.13.5"


def test_v89_legacy_plan_hard_excludes_managed_python_resources() -> None:
    module = generator()
    assert module.MANAGED_PYTHON_RESOURCE_EXCLUDE == "latka_jazn/local_resources/python/**"
    assert getattr(module._legacy_core().build_plan, "_jazn_v89_safe", False) is True


def test_v89_dependency_bundle_discovery_uses_manifest_not_directory_name(tmp_path: Path) -> None:
    module = generator()
    bundle = tmp_path / "latka_jazn/local_resources/python/wheelhouse/arbitrary-cache-name"
    bundle.mkdir(parents=True)
    (bundle / "JAZN_WHEELHOUSE_MANIFEST.json").write_text(json.dumps({
        "target": {"alias": "linux-x64", "python_version": "3.13"}
    }), encoding="utf-8")
    assert module.find_matching_dependency_bundle(tmp_path, "linux-x64", "3.13.5") == bundle.resolve()


def test_v89_distribution_pack_calls_canonical_package_distribution(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    source = tmp_path / "root"
    source.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    captured = {}

    def fake_run(command, *, cwd, env):
        captured["command"] = list(command)
        return {"ok": True, "package_set": {"schema_version": "jazn_package_set/v3"}}

    monkeypatch.setattr(module, "_run_json", fake_run)
    result = module.run_distribution_pack(
        source=source,
        out_dir=tmp_path / "out",
        mode="system-portable",
        target_alias="linux-x64",
        python_version="3.13.5",
        dependency_bundle=bundle,
    )
    assert result["ok"] is True
    command = captured["command"]
    assert "latka_jazn.tools.package_distribution" in command
    assert command[command.index("--python-version") + 1] == "3.13"
    assert command[command.index("--target") + 1] == "linux-x64"


def test_v89_rejects_cross_target_materialization(tmp_path: Path) -> None:
    module = generator()
    current = "windows-x64" if module.os.name == "nt" else "linux-x64"
    other = "linux-x64" if current == "windows-x64" else "windows-x64"
    with pytest.raises(RuntimeError, match="Cross-target"):
        module.materialize_native_dependency_bundle(tmp_path, target_alias=other, python_version="3.13")
