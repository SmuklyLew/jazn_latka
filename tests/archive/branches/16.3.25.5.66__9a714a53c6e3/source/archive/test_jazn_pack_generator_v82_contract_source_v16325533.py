from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def test_v82_contract_is_retired_after_v101860111_clean_rewrite() -> None:
    """The historical v8.2 path remains a migration guard for the active tool."""
    module_name = "jazn_pack_generator_v82_retirement_guard"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    assert module.GENERATOR_VERSION == "10.1.86.0.113"
    assert module.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v1"
    assert module.UI_MODE_CHOICES == ("text", "tui", "studio")
