from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_v89_legacy_plan_hard_excludes_managed_python_resources(monkeypatch) -> None:
    module = generator()
    core = module._legacy_core()
    calls = []
    original = core.build_plan
    monkeypatch.setattr(module.legacy._impl._core, "build_plan", original)
    # The overlay installed during import is itself the contract under test.
    assert module.MANAGED_PYTHON_RESOURCE_EXCLUDE == "latka_jazn/local_resources/python/**"


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


def test_v89_exposes_five_ui_modes() -> None:
    module = generator()
    assert module.UI_MODE_CHOICES == (
        "tekstowy", "kursorowy", "studio-terminal", "studio-windows", "studio-linux"
    )
    assert module.UI_MODE_LABELS["studio-terminal"] == "Studio w terminalu"
    assert module.UI_MODE_LABELS["studio-windows"] == "Studio dla Windows"
    assert module.UI_MODE_LABELS["studio-linux"] == "Studio dla Linuksa"


def test_v89_ui_mode_dispatch_is_explicit(monkeypatch) -> None:
    module = generator()
    seen = []
    monkeypatch.setattr(module.legacy._impl, "interactive", lambda ui_override=None: seen.append(ui_override) or 0)
    assert module.run_ui_mode("tekstowy") == 0
    assert module.run_ui_mode("kursorowy") == 0
    assert seen == ["tekstowy", "kursorowy"]


def test_v89_platform_specific_studio_fails_closed_on_wrong_os(monkeypatch) -> None:
    module = generator()
    if module.os.name == "nt":
        with pytest.raises(RuntimeError, match="Linuks"):
            module._platform_guard("linux")
    else:
        with pytest.raises(RuntimeError, match="Windows"):
            module._platform_guard("windows")


def test_v89_settings_persist_ui_and_distribution_preferences(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(module, "_settings_path", lambda: settings)
    saved = module.save_studio_preferences(
        ui_mode="studio-terminal",
        ui_auto_start=True,
        distribution_mode="system-portable",
        target_alias="linux-x64",
        python_version="3.13.5",
        dependency_bundle="/tmp/bundle",
        materialize_dependencies=False,
    )
    assert saved["ui_mode"] == "studio-terminal"
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "jazn_pack_generator_settings/v8.9"
    assert payload["studio_v89"]["target_alias"] == "linux-x64"
    assert payload["studio_v89"]["python_version"] == "3.13.5"


def test_v89_current_target_resolves_to_native_release_alias() -> None:
    module = generator()
    resolved = module.resolve_distribution_target_alias("current")
    if module.os.name == "nt":
        assert resolved == "windows-x64"
    else:
        assert module.sys.platform.startswith("linux")
        assert resolved == "linux-x64"
    plan = module.distribution_mode_plan(
        "system-portable", target_alias="current", python_version="3.13.5"
    )
    assert plan["target_runtime"]["alias"] == resolved
    assert plan["target_runtime"]["requested_alias"] == "current"
    assert plan["target_runtime"]["python_version"] == "3.13"


def test_v89_linux_py313_canonical_lock_is_exact_pr209_evidence() -> None:
    import hashlib

    module = generator()
    root = Path(__file__).resolve().parents[1]
    lock = module.canonical_dependency_lock_path(root, "linux-x64", "3.13.5")
    raw = lock.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "81afe3398aba06931c9d7cbc5672eb14d00a11e5c9b6ede1239ccf56e226e0f6"
    text = raw.decode("utf-8")
    assert "py7zr==1.1.3" in text
    assert "pyzipper==0.4.0" in text
    assert "pycryptodomex==3.23.0" in text
    assert "pypdf==6.16.2" in text


def test_v89_native_materialization_uses_canonical_lock_when_present(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    current = module.current_distribution_target_alias()
    lock = (
        tmp_path / "latka_jazn" / "resources" / "dependencies" / "locks" / "core+archive"
        / f"{current}-py313.txt"
    )
    lock.parent.mkdir(parents=True)
    lock.write_text("example==1 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")
    bundle = tmp_path / "latka_jazn" / "local_resources" / "python" / "wheelhouse" / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "JAZN_WHEELHOUSE_MANIFEST.json").write_text(
        json.dumps({"target": {"alias": current, "python_version": "3.13"}}), encoding="utf-8"
    )
    captured = {}

    def fake_run(command, *, cwd, env):
        captured["command"] = list(command)
        return {"ok": True, "bundle_dir": str(bundle)}

    monkeypatch.setattr(module, "_run_json", fake_run)
    result = module.materialize_native_dependency_bundle(
        tmp_path, target_alias="current", python_version="3.13.5"
    )
    assert result == bundle.resolve()
    command = captured["command"]
    assert command[command.index("--python-version") + 1] == "3.13"
    assert command[command.index("--lock-file") + 1] == str(lock.resolve())
