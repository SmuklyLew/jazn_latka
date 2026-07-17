from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "_jazn_pack_generator.py"


def _load_generator():
    module_name = "jazn_pack_generator_release_version_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_full_version_includes_release_name() -> None:
    generator = _load_generator()
    assert generator.compose_package_version_full(
        "15.0.3.4.1",
        "release-hardening",
    ) == "15.0.3.4.1-release-hardening"


def test_full_version_does_not_duplicate_release_name() -> None:
    generator = _load_generator()
    assert generator.compose_package_version_full(
        "v15.0.3.4.1-release-hardening",
        "release-hardening",
    ) == "15.0.3.4.1-release-hardening"


def test_manifest_accepts_canonical_full_release_version() -> None:
    generator = _load_generator()
    assert generator.manifest_version_matches(
        "v15.0.3.4.1-release-hardening",
        "15.0.3.4.1",
        "release-hardening",
    )
    assert not generator.manifest_version_matches(
        "v15.0.3.4.1-release-hardening",
        "15.0.3.4.1",
        "",
    )
