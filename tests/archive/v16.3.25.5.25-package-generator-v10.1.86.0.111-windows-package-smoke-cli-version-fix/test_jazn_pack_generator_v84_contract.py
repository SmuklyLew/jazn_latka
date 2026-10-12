from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    module_name = "jazn_pack_generator_v101860111_architecture_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _root(tmp_path: Path, *, quotes: str = '"') -> Path:
    root = tmp_path / "repo"
    (root / "latka_jazn" / "core" / "canon").mkdir(parents=True)
    (root / "latka_jazn" / "local_resources").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        f"PACKAGE_VERSION = {quotes}16.3.25.5.23{quotes}\n"
        f"PACKAGE_RELEASE_NAME = {quotes}package-generator-v10.1.86.0.111-clean-rewrite{quotes}\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    return root


def test_generator_identity_and_small_public_launcher() -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "10.1.86.0.111"
    assert generator.GENERATOR_TITLE == "Jaźń Pack Generator"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v1"
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "_BUNDLED_MODULES" not in source
    assert "b85decode" not in source
    assert "package_distribution" not in source
    assert "jazn_pack_generator_app" in source


def test_cli_rejects_abbreviated_long_options() -> None:
    generator = _load_generator()
    parser = generator._parser()
    exact = parser.parse_args(["pack", "--source", ".", "--out-dir", "out", "--content", "system"])
    assert exact.content == "system"
    with pytest.raises(SystemExit):
        parser.parse_args(["pack", "--source", ".", "--out-dir", "out", "--cont", "system"])
    with pytest.raises(SystemExit):
        parser.parse_args(["unpack", "archive.zip", "--dest", "out"])


def test_output_inside_repository_is_rejected(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    request = generator.PackRequest(
        source_root=root,
        output_root=root / "packages",
        content=generator.ContentMode.SYSTEM,
    )
    with pytest.raises(Exception, match="wewnątrz folderu Jaźni"):
        generator.plan_pack(request)


def test_system_plan_excludes_private_and_mutable_inputs(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    private_canon = root / "latka_jazn" / "core" / "canon" / "local_private_canon_extension.py"
    private_canon.write_text("PRIVATE = True\n", encoding="utf-8")
    (root / "latka_jazn" / "local_resources" / "secret.bin").write_bytes(b"private")
    (root / "private.sqlite3").write_bytes(b"sqlite")
    (root / "workspace_runtime").mkdir()
    (root / "workspace_runtime" / "state.json").write_text("{}", encoding="utf-8")
    request = generator.PackRequest(
        source_root=root,
        output_root=tmp_path / "packages",
        content=generator.ContentMode.SYSTEM,
    )
    plan = generator.plan_pack(request)
    names = {entry.archive_path for entry in plan.entries}
    assert "latka_jazn/core/canon/local_private_canon_extension.py" not in names
    assert not any(name.startswith("latka_jazn/local_resources/") for name in names)
    assert "private.sqlite3" not in names
    assert not any(name.startswith("workspace_runtime/") for name in names)


def test_release_parser_accepts_single_and_double_quotes(tmp_path: Path) -> None:
    generator = _load_generator()
    double_root = _root(tmp_path / "double", quotes='"')
    single_root = _root(tmp_path / "single", quotes="'")
    from tools.jazn_pack_generator_app.scanner import parse_package_version
    assert parse_package_version(double_root).startswith("16.3.25.5.23-")
    assert parse_package_version(single_root).startswith("16.3.25.5.23-")


def test_configuration_reports_only_archiver_scope() -> None:
    generator = _load_generator()
    payload = generator.config_report()
    assert payload["ok"] is True
    assert payload["generator_version"] == "10.1.86.0.111"
    assert payload["features"]["zip"] is True
    assert payload["features"]["zip64"] is True
    assert payload["features"]["split_transport"] is True
    assert set(payload["not_in_scope"]) == {
        "dependency-bundle", "wheelhouse", "python-runtime", "target-platform"
    }


def test_settings_are_json_and_versioned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    generator = _load_generator()
    settings_path = tmp_path / "settings.json"
    monkeypatch.setenv("JAZN_PACK_GENERATOR_SETTINGS", str(settings_path))
    saved = generator.save_settings(
        {
            "ui_mode": "tui",
            "source_root": str(tmp_path / "repo"),
            "memory_root": str(tmp_path / "memory"),
            "output_root": str(tmp_path / "packages"),
            "part_size_mib": 480,
            "compression_level": 7,
        }
    )
    assert saved["schema_version"] == "jazn_pack_generator_settings/v1"
    assert saved["generator_version"] == "10.1.86.0.111"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["ui_mode"] == "tui"
    assert payload["part_size_mib"] == 480
