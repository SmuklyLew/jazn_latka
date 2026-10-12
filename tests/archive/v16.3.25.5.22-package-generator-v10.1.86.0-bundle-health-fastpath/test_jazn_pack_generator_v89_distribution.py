from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def generator():
    return importlib.import_module("tools.jazn_pack_generator")


def test_v1001_public_entrypoint_and_request_contract() -> None:
    module = generator()
    assert module.GENERATOR_VERSION == "10.1.86.0"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v10.1.86.0"
    plan = module.distribution_request_plan(
        content="system+memory", layout="single", archive_format="zip"
    )
    assert plan["jobs"] == [
        {"role": "system+memory", "distribution_mode": "system+memory+dependencies"}
    ]
    assert plan["system_dependencies_included"] is True
    assert plan["local_private_canon_extension_in_system"] is False


def test_v1001_separate_system_memory_is_two_canonical_jobs() -> None:
    module = generator()
    plan = module.distribution_request_plan(
        content="system+memory", layout="separate", archive_format="split-zip"
    )
    assert plan["jobs"] == [
        {"role": "system", "distribution_mode": "system-portable"},
        {"role": "memory", "distribution_mode": "memory-only"},
    ]


def test_v1001_hard_excludes_private_runtime_and_managed_resources() -> None:
    module = generator()
    assert "latka_jazn/core/canon/local_private_canon_extension.py" in module.HARD_EXCLUDE_GLOBS
    assert "latka_jazn/local_resources/**" in module.HARD_EXCLUDE_GLOBS
    assert "workspace_runtime/**" in module.HARD_EXCLUDE_GLOBS
    assert module.MANAGED_PYTHON_RESOURCE_EXCLUDE == "latka_jazn/local_resources/python/**"


def test_v101860_dependency_bundle_discovery_uses_canonical_verified_wheelhouse(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = generator()
    wheelhouse = tmp_path / "workspace_runtime/local_resources/python/wheelhouse"
    bundle = wheelhouse / "arbitrary-cache-name"
    bundle.mkdir(parents=True)
    captured = {}

    def fake_discover(root, **kwargs):
        captured["root"] = Path(root)
        captured.update(kwargs)
        return [{"bundle_dir": str(bundle), "verification": {"ok": True}}]

    monkeypatch.setattr(module._impl, "dependency_wheelhouse_root", lambda _root: wheelhouse)
    monkeypatch.setattr(module._impl, "discover_bundles", fake_discover)
    assert module.find_matching_dependency_bundle(tmp_path, "linux-x64", "3.13.5") == bundle.resolve()
    assert captured["wheelhouse_root"] == wheelhouse
    assert captured["required_profiles"] == ("core", "archive")
    assert captured["verify"] is True


def test_v1001_distribution_pack_calls_canonical_package_distribution(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    source = tmp_path / "root"
    source.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    captured = {}

    def fake_run(command, *, cwd, env):
        captured["command"] = list(command)
        return {"ok": True, "package_set": {"schema_version": "jazn_package_set/v3"}}

    monkeypatch.setattr(module._impl, "_run_json", fake_run)
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


def test_v101860_cross_target_materialization_requires_canonical_lock(tmp_path: Path) -> None:
    module = generator()
    current = "windows-x64" if module.os.name == "nt" else "linux-x64"
    other = "linux-x64" if current == "windows-x64" else "windows-x64"
    with pytest.raises(RuntimeError, match="kanonicznego locka cross-target"):
        module.materialize_dependency_bundle(
            tmp_path,
            target_alias=other,
            python_version="3.13",
        )


def test_v101860_cross_target_materialization_replays_lock(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    current = "windows-x64" if module.os.name == "nt" else "linux-x64"
    other = "linux-x64" if current == "windows-x64" else "windows-x64"
    lock = module.canonical_dependency_lock_path(tmp_path, other, "3.13")
    lock.parent.mkdir(parents=True)
    lock.write_text("example==1 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")
    wheelhouse = tmp_path / "workspace_runtime/local_resources/python/wheelhouse"
    bundle = wheelhouse / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "JAZN_WHEELHOUSE_MANIFEST.json").write_text(
        json.dumps({"target": {"alias": other, "python_version": "3.13"}}),
        encoding="utf-8",
    )
    captured = {}

    def fake_run(command, *, cwd, env):
        captured["command"] = list(command)
        return {"ok": True, "bundle_dir": str(bundle)}

    monkeypatch.setattr(module._impl, "dependency_wheelhouse_root", lambda _root: wheelhouse)
    monkeypatch.setattr(module._impl, "_run_json", fake_run)
    result = module.materialize_dependency_bundle(
        tmp_path,
        target_alias=other,
        python_version="3.13",
    )
    assert result == bundle.resolve()
    command = captured["command"]
    assert command[command.index("--platform") + 1] == other
    assert command[command.index("--lock-file") + 1] == str(lock.resolve())
    assert command[command.index("--wheelhouse-root") + 1] == str(wheelhouse)


def test_v1001_exposes_only_three_terminal_ui_modes() -> None:
    module = generator()
    assert module.UI_MODE_CHOICES == ("tekstowy", "kursorowy", "studio-terminal")
    assert module.UI_MODE_LABELS["studio-terminal"] == "Jaźń Pack Studio w terminalu"
    assert "studio-windows" not in module.UI_MODE_CHOICES
    assert "studio-linux" not in module.UI_MODE_CHOICES


def test_v1001_ui_mode_dispatch_is_explicit(monkeypatch) -> None:
    module = generator()
    seen = []
    monkeypatch.setattr(module._ui, "run_text_ui", lambda: seen.append("tekstowy") or 0)
    monkeypatch.setattr(module._ui, "run_cursor_ui", lambda: seen.append("kursorowy") or 0)
    monkeypatch.setattr(module._ui, "run_terminal_studio", lambda: seen.append("studio-terminal") or 0)
    assert module.run_ui_mode("tekstowy") == 0
    assert module.run_ui_mode("kursorowy") == 0
    assert module.run_ui_mode("studio-terminal") == 0
    assert seen == ["tekstowy", "kursorowy", "studio-terminal"]


def test_v1001_settings_persist_distribution_preferences(monkeypatch, tmp_path: Path) -> None:
    module = generator()
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(module._impl, "_settings_path", lambda: settings)
    saved = module.save_settings(
        ui_mode="studio-terminal",
        source=str(tmp_path / "repo"),
        out_dir=str(tmp_path / "packages"),
        content="system+memory",
        layout="separate",
        archive_format="split-zip",
        split_size_mib=512,
        target_alias="linux-x64",
        python_version="3.13.5",
        dependency_bundle="/tmp/bundle",
        materialize_dependencies=False,
    )
    assert saved["layout"] == "separate"
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "jazn_pack_generator_settings/v10.1.86.0"
    assert payload["archive_format"] == "split-zip"
    assert payload["split_size_mib"] == 512


def test_v1001_default_windows_output_contract() -> None:
    module = generator()
    if module.os.name == "nt":
        assert str(module.default_output_dir()) == r"D:\.AI\jazn_packages"


def test_v1001_split_zip_roundtrip(tmp_path: Path) -> None:
    module = generator()
    source = tmp_path / "sample.zip"
    source.write_bytes((b"0123456789" * 1000) + b"END")
    original_sha = module.sha256_file(source)
    split = module._split_binary_file(source, 777, remove_original=True)
    assert source.exists() is False
    assert len(split["parts"]) > 1
    joined = module.join_split_zip(tmp_path / "sample.zip.001")
    assert module.sha256_file(joined) == original_sha


def test_v1001_backend_matrix_includes_zip_7z_tar_and_optional_rar() -> None:
    module = generator()
    status = module.archive_backend_status()
    assert status["zip"]["create"] is True
    assert status["split-zip"]["create"] is True
    assert status["tar"]["create"] is True
    assert "7z" in status
    assert "rar" in status


def test_v1001_current_target_resolves_to_native_release_alias() -> None:
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


def test_v1001_linux_py313_canonical_lock_contains_required_archive_backends() -> None:
    module = generator()
    root = Path(__file__).resolve().parents[1]
    lock = module.canonical_dependency_lock_path(root, "linux-x64", "3.13.5")
    text = lock.read_text(encoding="utf-8")
    assert "py7zr==1.1.3" in text
    assert "pyzipper==0.4.0" in text
    assert "rarfile==4.5 --hash=sha256:c74341f4b9a3a3ebb35ef396d59daf059eb028f34995a7162950a41d97b84de9" in text
    assert "pycryptodomex==3.23.0" in text
    assert "pypdf==6.16.2" in text
    for line in text.splitlines():
        if line and not line.startswith("#"):
            assert "==" in line and " --hash=sha256:" in line


def test_v1001_native_materialization_uses_canonical_lock_when_present(monkeypatch, tmp_path: Path) -> None:
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

    monkeypatch.setattr(module._impl, "_run_json", fake_run)
    result = module.materialize_native_dependency_bundle(
        tmp_path, target_alias="current", python_version="3.13.5"
    )
    assert result == bundle.resolve()
    command = captured["command"]
    assert command[command.index("--python-version") + 1] == "3.13"
    assert command[command.index("--lock-file") + 1] == str(lock.resolve())
