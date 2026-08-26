from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_v16311_exposes_exact_four_user_profiles_in_requested_order() -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "8.5"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.5"
    # Historical constants stay source-compatible; this is the new canonical UI order.
    assert generator.USER_PROFILE_CHOICES == ("combined", "system", "memory", "dual")
    assert generator.PROFILE_DISPLAY["combined"] == "SYSTEM + PAMIĘĆ (1 ZIP)"
    assert generator.PROFILE_DISPLAY["dual"] == "SYSTEM + PAMIĘĆ (2 OSOBNE ZIP-y)"

    parser = generator.parser()
    parsed = parser.parse_args(["pack", ".", "--profile", "combined"])
    assert parsed.profile == "combined"


def test_dual_profile_cannot_silently_degrade_to_system_only(tmp_path: Path) -> None:
    generator = _load_generator()
    options = generator.PackOptions(
        source=tmp_path,
        out_dir=tmp_path.parent / "packages",
        profile="dual",
    )
    with pytest.raises(generator.PackError, match="nie został zrealizowany w całości"):
        generator.run_pack_with_plans(options, [SimpleNamespace(profile="system")])


def test_combined_profile_requires_real_memory_payload(tmp_path: Path) -> None:
    generator = _load_generator()
    options = generator.PackOptions(
        source=tmp_path,
        out_dir=tmp_path.parent / "packages",
        profile="combined",
    )
    fake = SimpleNamespace(profile="combined", paths=["run.py", "memory/MEMORY_PACKAGE_MANIFEST.json"])
    with pytest.raises(generator.PackError, match="wymaga rzeczywistych plików pamięci"):
        generator.run_pack_with_plans(options, [fake])


def test_exact_profile_contract_accepts_complete_shapes() -> None:
    generator = _load_generator()
    generator.require_exact_profile_set(
        "combined",
        [SimpleNamespace(profile="combined", paths=["run.py", "memory/sqlite/memory_jazn.sqlite3"])],
    )
    generator.require_exact_profile_set("system", [SimpleNamespace(profile="system", paths=["run.py"])])
    generator.require_exact_profile_set(
        "memory",
        [SimpleNamespace(profile="memory", paths=["memory/sqlite/memory_jazn.sqlite3"])],
    )
    generator.require_exact_profile_set(
        "dual",
        [
            SimpleNamespace(profile="system", paths=["run.py"]),
            SimpleNamespace(profile="memory", paths=["memory/sqlite/memory_jazn.sqlite3"]),
        ],
    )
