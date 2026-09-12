from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
V89_CORE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v89.py"
V88_BUNDLE = ROOT / "tools" / "pack_generator_sources" / "jazn_pack_generator_v88.py"
LEGACY_HELPERS = (
    "_jazn_pack_generator_core.py",
    "_jazn_pack_generator_memory_v2.py",
    "_jazn_pack_generator_v1601_policy.py",
    "_jazn_pack_generator_v1638_archive_io.py",
    "_jazn_pack_generator_v16311_profiles.py",
)
BUNDLED_MODULE_NAMES = (
    "tools._jazn_pack_generator_memory_v2",
    "tools._jazn_pack_generator_v1601_policy",
    "tools._jazn_pack_generator_v1638_archive_io",
    "tools._jazn_pack_generator_v16311_profiles",
)


def test_v89_generator_has_no_legacy_helper_files() -> None:
    for filename in LEGACY_HELPERS:
        assert not (ROOT / "tools" / filename).exists(), filename


def test_v89_launcher_delegates_to_repository_native_core_and_private_v88_bundle() -> None:
    launcher = GENERATOR.read_text(encoding="utf-8")
    core = V89_CORE.read_text(encoding="utf-8")
    legacy = V88_BUNDLE.read_text(encoding="utf-8")

    assert "jazn_pack_generator_v89.py" in launcher
    assert "jazn_pack_generator_v89_ui.py" in launcher
    assert "jazn_pack_generator_v88.py" in core
    assert "from tools import _jazn_pack_generator_memory_v2" not in legacy
    assert "from tools._jazn_pack_generator_" not in legacy
    assert "-> types.ModuleType" not in legacy
    assert "-> _bundle_types.ModuleType" in legacy
    for module_name in BUNDLED_MODULE_NAMES:
        assert module_name in legacy


def test_v89_generator_imports_from_public_launcher() -> None:
    module = importlib.import_module("tools.jazn_pack_generator")

    assert module.GENERATOR_VERSION == "8.9"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.9"
    assert callable(module.main)
