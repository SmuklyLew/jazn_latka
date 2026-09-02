from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
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


def test_v87_generator_has_no_legacy_helper_files() -> None:
    for filename in LEGACY_HELPERS:
        assert not (ROOT / "tools" / filename).exists(), filename


def test_v87_generator_uses_bundled_modules_without_static_legacy_imports() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "from tools import _jazn_pack_generator_memory_v2" not in source
    assert "from tools._jazn_pack_generator_" not in source
    assert "-> types.ModuleType" not in source
    assert "-> _bundle_types.ModuleType" in source

    for module_name in BUNDLED_MODULE_NAMES:
        assert module_name in source


def test_v87_generator_imports_from_two_file_bundle() -> None:
    module = importlib.import_module("tools.jazn_pack_generator")

    assert module.GENERATOR_VERSION == "8.8"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.8"
    assert callable(module.main)
