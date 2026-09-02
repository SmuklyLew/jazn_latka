from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from latka_jazn.packaging.package_plan import PackagePlanBuilder, package_safety_reason
from latka_jazn.packaging.package_set_contract import CURRENT_SCHEMA, validate_package_set
from latka_jazn.packaging.memory_transaction import promote_memory_tree
from latka_jazn.tools.package_export import export_package
from latka_jazn.tools.safe_paths import UnsafeRelativePathError, validate_safe_path_set, validate_safe_relative_path

ROOT = Path(__file__).parents[1]


def _write(root: Path, rel: str, data: bytes = b"x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_system_filesystem_plan_hard_blocks_local_private_and_runtime_artifacts(tmp_path: Path) -> None:
    allowed = [
        "run.py", "main.py", "latka_jazn/version.py", "latka_jazn/core/ok.py",
        "AGENTS.md", "README.md", "pyproject.toml", "requirements.txt",
    ]
    blocked = [
        ".codex/test.json", ".venv/pyvenv.cfg",
        "latka_jazn/local_resources/python/environments/e/python.exe",
        "latka_jazn/local_resources/python/wheelhouse/core/demo.whl",
        "latka_jazn/core/canon/local_private_canon_extension.py",
        "memory/private.json", "workspace_runtime/JAZN_ACTIVE_RUNTIME.json",
        ".env", "secret.sqlite3", "nested.zip",
    ]
    for rel in allowed + blocked:
        _write(tmp_path, rel)
    # Copy the canonical profile resource so this is a true filesystem-mode fixture.
    source_profiles = ROOT / "latka_jazn/resources/zip_package_profiles.json"
    target_profiles = tmp_path / "latka_jazn/resources/zip_package_profiles.json"
    target_profiles.parent.mkdir(parents=True, exist_ok=True)
    target_profiles.write_bytes(source_profiles.read_bytes())
    plan = PackagePlanBuilder(tmp_path, "system").build()
    assert set(allowed).issubset(set(plan.paths))
    assert set(blocked).isdisjoint(set(plan.paths))
    for rel in blocked:
        assert package_safety_reason(rel, "system") is not None or rel not in plan.paths


@pytest.mark.security
@pytest.mark.parametrize("value", [
    "../memory/x.jsonl", "C:/memory/x.jsonl", "//server/share/file", "file:ads",
    "CON.txt", "aux", "safe/trailing.", "safe/trailing ",
])
def test_path_boundary_rejects_cross_platform_ambiguous_names(value: str) -> None:
    with pytest.raises(UnsafeRelativePathError):
        validate_safe_relative_path(value)


@pytest.mark.security
def test_path_inventory_rejects_casefold_collision() -> None:
    with pytest.raises(UnsafeRelativePathError):
        validate_safe_path_set(["Safe/File.txt", "safe/file.TXT"])


def test_memory_promotion_rolls_back_after_new_tree_promoted(tmp_path: Path) -> None:
    source = tmp_path / "source-memory"; source.mkdir(); _write(source, "new.txt", b"new")
    target = tmp_path / "host" / "memory"; target.mkdir(parents=True); _write(target, "old.txt", b"old")
    workspace = tmp_path / "host" / "workspace_runtime"; workspace.mkdir(parents=True)
    def fail(stage: str) -> None:
        if stage == "after_new_promoted":
            raise RuntimeError("controlled-failure")
    with pytest.raises(RuntimeError, match="controlled-failure"):
        promote_memory_tree(source_memory=source, target_memory=target, workspace=workspace, fault_injector=fail)
    assert (target / "old.txt").read_bytes() == b"old"
    assert not (target / "new.txt").exists()


def test_generator_bundle_is_generated_from_current_sources() -> None:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "tools/build_jazn_pack_generator_bundle.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    import tools.jazn_pack_generator as generator
    assert generator.GENERATOR_VERSION == "8.8"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.8"
    manifest = generator._CANONICAL_PACKAGE_BUNDLE_MANIFEST
    for row in manifest.values():
        source = ROOT / row["source_path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]


def test_package_set_v3_validates_its_plan_and_output_hashes(tmp_path: Path) -> None:
    artifact = tmp_path / "system.zip"; artifact.write_bytes(b"zipbytes")
    out_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    entries = [{"path": "run.py", "size_bytes": 3, "sha256": hashlib.sha256(b"run").hexdigest(), "classification": "static_project_file"}]
    from latka_jazn.packaging.package_set_contract import build_single_zip_sidecar
    payload = build_single_zip_sidecar(package_name=artifact.name, profile="system", package_version="test", zip_path=artifact, entries=entries)
    assert payload["schema_version"] == CURRENT_SCHEMA
    assert validate_package_set(payload, require_current=True)["outputs"][0]["sha256"] == out_sha
