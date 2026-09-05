from __future__ import annotations

import importlib
from pathlib import Path

def test_public_launcher_exports_new_archiver_contract() -> None:
    generator = importlib.import_module("tools.jazn_pack_generator")
    required = {
        "GENERATOR_VERSION", "GENERATOR_TITLE", "SETTINGS_SCHEMA", "UI_MODE_CHOICES",
        "ContentMode", "PackRequest", "TransportMode", "run_pack_request",
        "plan_pack", "pack", "verify_package", "join_parts", "unpack_package",
        "config_report", "load_settings", "save_settings", "main",
    }
    missing = sorted(name for name in required if not hasattr(generator, name))
    assert missing == []
    assert generator.GENERATOR_VERSION == "10.1.86.0.113"
    assert generator.UI_MODE_CHOICES == ("text", "tui", "studio")

def test_config_explicitly_declares_distribution_features_out_of_scope() -> None:
    generator = importlib.import_module("tools.jazn_pack_generator")
    report = generator.config_report()
    assert report["scope"] == "folder-snapshot:system-memory-system+memory;single-or-binary-split"
    assert set(report["not_in_scope"]) == {
        "dependency-bundle", "wheelhouse", "python-runtime", "target-platform"
    }

def test_cli_parser_disables_abbreviations() -> None:
    generator = importlib.import_module("tools.jazn_pack_generator")
    parser = generator._parser()
    assert parser.allow_abbrev is False
