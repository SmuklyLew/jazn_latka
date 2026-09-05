from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
V1001_CORE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v1001.py"
V1001_UI = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v1001_ui.py"
LEGACY_HELPERS = (
    "_jazn_pack_generator_core.py",
    "_jazn_pack_generator_memory_v2.py",
    "_jazn_pack_generator_v1601_policy.py",
    "_jazn_pack_generator_v1638_archive_io.py",
    "_jazn_pack_generator_v16311_profiles.py",
)


def test_v1001_generator_has_no_legacy_helper_files() -> None:
    for filename in LEGACY_HELPERS:
        assert not (ROOT / "tools" / filename).exists(), filename


def test_v1001_launcher_loads_only_v1001_runtime_sources() -> None:
    launcher = GENERATOR.read_text(encoding="utf-8")
    core = V1001_CORE.read_text(encoding="utf-8")
    ui = V1001_UI.read_text(encoding="utf-8")

    assert "jazn_pack_generator_v1001.py" in launcher
    assert "jazn_pack_generator_v1001_ui.py" in launcher
    assert "jazn_pack_generator_v89.py" not in launcher
    assert "jazn_pack_generator_v88.py" not in launcher
    assert "tkinter" not in launcher
    assert "tkinter" not in ui
    assert "GENERATOR_VERSION = \"10.0.1\"" in core


def test_v1001_generator_imports_from_public_launcher() -> None:
    module = importlib.import_module("tools.jazn_pack_generator")

    assert module.GENERATOR_VERSION == "10.0.1"
    assert module.GENERATOR_TITLE == "Naprawiony generator dystrybucji Jaźni"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v10.0.1"
    assert callable(module.main)
