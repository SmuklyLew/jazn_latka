from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"
PROFILES_PATH = ROOT / "latka_jazn" / "resources" / "dependencies" / "profiles.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"


def _load_generator():
    name = "jazn_pack_generator_v1001_public_api_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_public_launcher_exports_complete_compatibility_contract() -> None:
    generator = _load_generator()
    required = {
        "parser",
        "VersionInfo",
        "PlanEntry",
        "PackPlan",
        "PackOptions",
        "GeneratorArchiveSettings",
        "archive_settings_override",
        "package_one",
        "extract_package_sidecar",
        "compose_package_version_full",
        "manifest_version_matches",
        "validate_release_provenance_payload",
        "validate_system_plan_release_metadata",
        "virtual_entry",
        "build_plan",
        "build_plans_for_options",
        "build_memory_plan",
        "sidecar_payload",
        "PROFILE_CHOICES",
        "PACK_PROFILE_CHOICES",
        "MEMORY_RAW_SEGMENT_TARGET_BYTES",
        "MEMORY_RAW_SEGMENT_MAX_BYTES",
        "MEMORY_SQLITE_MEMBER_MAX_BYTES",
        "_dashboard_available",
    }
    missing = sorted(name for name in required if not hasattr(generator, name))
    assert missing == []
    assert generator.PROFILE_CHOICES == ("system", "dual", "memory")
    assert generator.PACK_PROFILE_CHOICES == ("system", "dual", "memory", "combined")
    assert generator._dashboard_available() is False


def test_compatibility_parser_keeps_old_archive_flags_without_weakening_v10_parser() -> None:
    generator = _load_generator()
    parsed = generator.parser().parse_args(
        [
            "pack",
            ".",
            "--profile",
            "memory",
            "--container-format",
            "7z",
            "--encrypt-7z",
            "--password-env",
            "JAZN_TEST_PASSWORD",
            "--extract-max-ratio",
            "250",
        ]
    )
    assert parsed.profile == "memory"
    assert parsed.container_format == "7z"
    assert parsed.encrypt_7z is True
    assert parsed.archive_password_env == "JAZN_TEST_PASSWORD"
    assert parsed.archive_max_ratio == 250.0

    native = generator._impl._parser().parse_args(
        ["pack", "--source", ".", "--content", "system"]
    )
    assert native.content == "system"


def test_release_parser_accepts_python_single_and_double_quoted_constants(tmp_path: Path) -> None:
    generator = _load_generator()
    root = tmp_path / "repo"
    version_dir = root / "latka_jazn"
    version_dir.mkdir(parents=True)

    (version_dir / "version.py").write_text(
        "PACKAGE_VERSION = '16.3.25.5.14'\n"
        "PACKAGE_RELEASE_NAME = \"pack-generator-v1001-rar-ci-hardening\"\n",
        encoding="utf-8",
    )
    assert generator._impl._parse_release(root) == (
        "16.3.25.5.14",
        "pack-generator-v1001-rar-ci-hardening",
    )


def test_rarfile_is_core_runtime_dependency_not_duplicated_archive_requirement() -> None:
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    core = profiles["profiles"]["core"]
    archive = profiles["profiles"]["archive"]
    assert "rarfile" not in core["exclude_distributions"]
    assert archive["requirements"] == ["py7zr>=1.1.3,<2", "pyzipper>=0.4.0,<1"]

    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
    assert '"rarfile>=4.5,<5"' in pyproject


def test_source_set_validator_covers_native_compatibility_module() -> None:
    validator = (ROOT / "tools" / "build_jazn_pack_generator_bundle.py").read_text(encoding="utf-8")
    assert "jazn_pack_generator_v1001_compat.py" in validator
    assert "COMPAT_SOURCE" in validator
