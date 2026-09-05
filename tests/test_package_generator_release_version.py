from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"
FIXTURE_VERSION_NUMBER = "91.82.73.64"
FIXTURE_RELEASE_NAME = "fixture-release"


def _load_generator():
    module_name = "jazn_pack_generator_release_version_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _root(tmp_path: Path, quote: str) -> Path:
    root = tmp_path / f"root-{ord(quote)}"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        f"PACKAGE_VERSION = {quote}{FIXTURE_VERSION_NUMBER}{quote}\n"
        f"PACKAGE_RELEASE_NAME = {quote}{FIXTURE_RELEASE_NAME}{quote}\n",
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    return root


def test_release_version_is_read_from_canonical_version_file(tmp_path: Path) -> None:
    generator = _load_generator()
    from tools.jazn_pack_generator_app.scanner import parse_package_version
    assert parse_package_version(_root(tmp_path, '"')) == f"{FIXTURE_VERSION_NUMBER}-{FIXTURE_RELEASE_NAME}"
    assert parse_package_version(_root(tmp_path, "'")) == f"{FIXTURE_VERSION_NUMBER}-{FIXTURE_RELEASE_NAME}"


def test_package_basename_uses_full_release_once(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path, '"')
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "packages",
            content=generator.ContentMode.SYSTEM,
        )
    )
    assert plan.package_version == f"{FIXTURE_VERSION_NUMBER}-{FIXTURE_RELEASE_NAME}"
    assert plan.package_basename == (
        f"jazn_latka_v{FIXTURE_VERSION_NUMBER}-{FIXTURE_RELEASE_NAME}.system.zip"
    )
    assert plan.package_basename.count(FIXTURE_RELEASE_NAME) == 1
