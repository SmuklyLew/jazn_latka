from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    module_name = "jazn_pack_generator_v1001_architecture_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_identity_examples_and_default_output() -> None:
    generator = _load_generator()

    assert generator.GENERATOR_VERSION == "10.1.86.0"
    assert generator.GENERATOR_TITLE == "Generator dystrybucji Jaźni"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v10.1.86.0"
    assert generator.__doc__ is not None
    assert r"py -X utf8 .\tools\jazn_pack_generator.py" in generator.__doc__
    assert "tkinter" not in GENERATOR_PATH.read_text(encoding="utf-8")
    if generator.os.name == "nt":
        assert str(generator.default_output_dir()) == r"D:\.AI\jazn_packages"


def test_cli_rejects_abbreviated_long_options() -> None:
    generator = _load_generator()
    parser = generator._impl._parser()

    exact = parser.parse_args(["pack", "--source", ".", "--content", "system"])
    assert exact.content == "system"

    with pytest.raises(SystemExit):
        parser.parse_args(["pack", "--source", ".", "--cont", "system"])
    with pytest.raises(SystemExit):
        parser.parse_args(["unpack", "archive.zip", "--dest", "out"])


def test_output_inside_repository_is_rejected(tmp_path: Path) -> None:
    generator = _load_generator()
    source = tmp_path / "repo"
    source.mkdir()
    with pytest.raises(generator.PackError, match="wewnątrz repozytorium"):
        generator._validate_output_location(source, source / "packages")


def test_private_and_mutable_paths_are_not_system_inputs() -> None:
    generator = _load_generator()
    hard = set(generator.HARD_EXCLUDE_GLOBS)
    assert "latka_jazn/core/canon/local_private_canon_extension.py" in hard
    assert "latka_jazn/local_resources/**" in hard
    assert "workspace_runtime/**" in hard
    assert "backups/**" in hard
    assert "exports/**" in hard


def test_configuration_reports_all_transport_backends() -> None:
    generator = _load_generator()
    payload = generator.config_report()
    assert payload["ok"] is True
    assert payload["generator_version"] == "10.1.86.0"
    assert set(payload["archive_format_choices"]) == {"zip", "split-zip", "7z", "tar", "rar"}
    backends = payload["archive_backends"]
    assert backends["zip"]["backend"] == "python.stdlib.zipfile"
    assert backends["tar"]["backend"] == "python.stdlib.tarfile"


def test_settings_are_json_and_versioned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    generator = _load_generator()
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(generator._impl, "_settings_path", lambda: settings_path)
    saved = generator.save_settings(
        source=str(tmp_path / "repo"),
        out_dir=str(tmp_path / "packages"),
        content="system+memory",
        layout="separate",
        archive_format="split-zip",
        split_size_mib=480,
        target_alias="current",
        python_version="current",
        dependency_bundle="",
        materialize_dependencies=False,
        ui_mode="studio-terminal",
    )
    assert saved["schema_version"] == "jazn_pack_generator_settings/v10.1.86.0"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["layout"] == "separate"
    assert payload["ui_mode"] == "studio-terminal"
