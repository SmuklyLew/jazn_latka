from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    name = "jazn_pack_generator_v16311_profile_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_v1001_exposes_exact_three_user_content_choices() -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "10.0.1"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v10.0.1"
    assert generator.CONTENT_CHOICES == ("system", "memory", "system+memory")
    assert generator.LAYOUT_CHOICES == ("single", "separate")


def test_system_always_maps_to_portable_with_dependencies() -> None:
    generator = _load_generator()
    plan = generator.distribution_request_plan(content="system", layout="separate", archive_format="zip")
    assert plan["layout"] == "single"
    assert plan["jobs"] == [{"role": "system", "distribution_mode": "system-portable"}]
    assert plan["system_dependencies_included"] is True


def test_memory_is_independent_canonical_export() -> None:
    generator = _load_generator()
    plan = generator.distribution_request_plan(content="memory", layout="separate", archive_format="zip")
    assert plan["layout"] == "single"
    assert plan["jobs"] == [{"role": "memory", "distribution_mode": "memory-only"}]
    assert plan["memory_export_is_canonical"] is True


def test_combined_single_and_separate_have_distinct_exact_shapes() -> None:
    generator = _load_generator()
    single = generator.distribution_request_plan(
        content="system+memory", layout="single", archive_format="zip"
    )
    separate = generator.distribution_request_plan(
        content="system+memory", layout="separate", archive_format="zip"
    )
    assert single["jobs"] == [
        {"role": "system+memory", "distribution_mode": "system+memory+dependencies"}
    ]
    assert separate["jobs"] == [
        {"role": "system", "distribution_mode": "system-portable"},
        {"role": "memory", "distribution_mode": "memory-only"},
    ]
