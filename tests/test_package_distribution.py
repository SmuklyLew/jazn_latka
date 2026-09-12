from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

import pytest

from latka_jazn.archive.resource_policy import (
    ArchiveResourcePolicy,
    ArchiveResourcePolicyError,
    normalize_member_path,
    validate_member_inventory,
)
from latka_jazn.dependencies.common import (
    DEPENDENCY_SET_NAME,
    DEPENDENCY_SET_SCHEMA,
    LOCK_NAME,
    MANIFEST_NAME,
    WHEELHOUSE_SCHEMA,
    current_platform_alias,
    target_spec,
)
from latka_jazn.dependencies.release_artifact import materialize_compatible_dependency_artifact
from latka_jazn.dependencies.wheelhouse import (
    build_locked_download_command,
    render_hash_lock,
    sha256_file,
    verify_bundle,
    wheel_metadata,
)
from latka_jazn.packaging.dependency_package_contract import build_dependency_sidecar, verify_dependency_sidecar
from latka_jazn.packaging.package_plan import build_distribution_package_plan
from latka_jazn.packaging.package_set_contract import (
    PACKAGE_SET_SCHEMA,
    build_v3_package_set,
    verify_package_set,
)


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")


def _valid_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    name, version = "demo", "1.0"
    dist = f"{name}-{version}.dist-info"
    members = {
        f"{name}/__init__.py": b"VALUE=1\n",
        f"{dist}/METADATA": b"Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nRequires-Python: >=3.12\nLicense-Expression: MIT\n\n",
        f"{dist}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = f"{dist}/RECORD"
    rows = [f"{path},{_digest(data)},{len(data)}" for path, data in members.items()]
    rows.append(f"{record},,")
    members[record] = ("\n".join(rows) + "\n").encode()
    wheel = bundle / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    metadata = wheel_metadata(wheel)
    row = {"filename": wheel.name, "size_bytes": wheel.stat().st_size, "sha256": sha256_file(wheel), "metadata": metadata}
    resolved = [{
        "name": "demo", "version": "1.0", "filename": wheel.name,
        "sha256": row["sha256"], "size_bytes": row["size_bytes"],
        "requires_python": metadata["requires_python"], "license_expression": metadata["license_expression"],
        "license": metadata["license"], "license_files": [],
        "tags": list(metadata["filename"]["tags"]), "record_verified": True,
    }]
    lock = bundle / LOCK_NAME
    lock.write_bytes(render_hash_lock(resolved).encode("utf-8"))
    target = target_spec("current", f"{sys.version_info.major}.{sys.version_info.minor}")
    manifest = {
        "schema_version": WHEELHOUSE_SCHEMA,
        "runtime_version": "16.3.25.5-package-distribution-convergence",
        "profiles": ["core", "archive"], "resolved_profiles": ["core", "archive"],
        "requirements": ["demo==1.0"], "direct_requirements": ["demo==1.0"],
        "dependency_contract_fingerprint": "f" * 64,
        "target": target.to_dict(), "files": [row], "resolved_distributions": resolved,
        "wheel_count": 1, "total_size_bytes": wheel.stat().st_size,
        "hash_lock_sha256": sha256_file(lock),
    }
    (bundle / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def test_wheelhouse_v2_verifies_record_tags_and_hash_lock(tmp_path: Path) -> None:
    bundle = _valid_bundle(tmp_path)
    result = verify_bundle(bundle)
    assert result["ok"] is True
    assert result["record_verified_wheel_count"] == 1
    assert result["target"]["compatible_platform_tags"]


def test_wheelhouse_v2_fails_closed_on_record_tamper(tmp_path: Path) -> None:
    bundle = _valid_bundle(tmp_path)
    wheel = next(bundle.glob("*.whl"))
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("demo/__init__.py", b"TAMPER=1\n")
    # Repair outer manifest SHA/size so only inner wheel integrity remains the blocker.
    manifest_path = bundle / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["size_bytes"] = wheel.stat().st_size
    manifest["files"][0]["sha256"] = sha256_file(wheel)
    manifest["resolved_distributions"][0]["size_bytes"] = wheel.stat().st_size
    manifest["resolved_distributions"][0]["sha256"] = sha256_file(wheel)
    lock = bundle / LOCK_NAME
    lock.write_bytes(render_hash_lock(manifest["resolved_distributions"]).encode("utf-8"))
    manifest["hash_lock_sha256"] = sha256_file(lock)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_bundle(bundle)
    assert result["ok"] is False
    assert any(error["code"] == "wheel_structure_invalid" for error in result["errors"])


def test_dependency_sidecar_is_deterministic_and_target_verified(tmp_path: Path) -> None:
    bundle = _valid_bundle(tmp_path)
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    one = build_dependency_sidecar(bundle, first)
    two = build_dependency_sidecar(bundle, second)
    assert one["sha256"] == two["sha256"]
    assert verify_dependency_sidecar(first)["ok"] is True
    rejected = verify_dependency_sidecar(first, expected_target={"alias": "windows-arm64"})
    assert rejected["ok"] is False
    assert any(error["code"] == "sidecar_target_mismatch" for error in rejected["errors"])


def test_package_set_v3_has_explicit_dependency_role() -> None:
    payload = build_v3_package_set(
        package_name="fixture", package_version="1", profile="system",
        roles=["system", "dependencies"],
        outputs=[{"filename": "system.zip", "size_bytes": 1, "sha256": "a" * 64}],
        dependency_artifacts=[{"filename": "deps.zip", "sha256": "b" * 64}],
        generator="test", generator_version="8.8",
    )
    assert payload["schema_version"] == PACKAGE_SET_SCHEMA
    assert payload["roles"] == ["system", "dependencies"]
    assert payload["dependency_artifacts"][0]["filename"] == "deps.zip"


def test_pack_generator_clean_source_layout_is_valid() -> None:
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "tools" / "build_jazn_pack_generator_bundle.py"), "--check"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "source_layout_valid=true" in result.stdout


def test_distribution_modes_require_target_only_when_dependencies_present() -> None:
    assert build_distribution_package_plan("system-thin").include_dependencies is False
    with pytest.raises(ValueError, match="target_alias"):
        build_distribution_package_plan("system-portable")
    plan = build_distribution_package_plan("system+memory+dependencies", target_alias="linux-x64", python_version="3.14")
    assert plan.include_system and plan.include_memory and plan.include_dependencies


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/evil", "CON.txt", "file.txt:stream"])
def test_archive_common_policy_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ArchiveResourcePolicyError):
        normalize_member_path(name)


def test_archive_common_policy_rejects_casefold_collision_and_zip_bomb_ratio() -> None:
    a = zipfile.ZipInfo("Folder/File.txt")
    a.file_size, a.compress_size = 10, 10
    b = zipfile.ZipInfo("folder/file.TXT")
    b.file_size, b.compress_size = 10, 10
    with pytest.raises(ArchiveResourcePolicyError, match="collision"):
        validate_member_inventory([a, b])

    bomb = zipfile.ZipInfo("bomb.bin")
    bomb.file_size, bomb.compress_size = 10_000, 1
    with pytest.raises(ArchiveResourcePolicyError, match="compression_ratio"):
        validate_member_inventory([bomb], policy=ArchiveResourcePolicy(max_compression_ratio=100.0))


def test_archive_common_policy_rejects_symlink() -> None:
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    info.file_size, info.compress_size = 1, 1
    with pytest.raises(ArchiveResourcePolicyError, match="symlink"):
        validate_member_inventory([info])

def test_current_target_exposes_runtime_implementation_abi_and_tags() -> None:
    target = target_spec("current", f"{sys.version_info.major}.{sys.version_info.minor}")
    assert target.implementation
    assert target.abi
    assert target.compatible_tags
    assert target.to_dict()["compatible_platform_tags"]


def test_locked_download_plan_uses_require_hashes(tmp_path: Path) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text("demo==1.0 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    target = target_spec("windows-x64", "3.12")
    command = build_locked_download_command(
        python_executable="python", destination=tmp_path / "wheels", lock_file=lock, target=target
    )
    assert "--require-hashes" in command
    assert "--only-binary=:all:" in command
    assert command[command.index("--platform") + 1] == "win_amd64"
    assert command[command.index("--abi") + 1] == "cp312"


def test_dependency_sidecar_rejects_abi_mismatch(tmp_path: Path) -> None:
    bundle = _valid_bundle(tmp_path)
    sidecar = tmp_path / "deps.zip"
    build_dependency_sidecar(bundle, sidecar)
    result = verify_dependency_sidecar(sidecar, expected_target={"abi": "cp999"})
    assert result["ok"] is False
    assert any(error["code"] == "sidecar_target_mismatch" and error.get("field") == "abi" for error in result["errors"])


def test_package_set_v3_self_hash_and_dependency_projection_are_verified(tmp_path: Path) -> None:
    system = tmp_path / "system.zip"
    dependency = tmp_path / "deps.zip"
    system.write_bytes(b"system")
    dependency.write_bytes(b"dependency")
    dep_sha = hashlib.sha256(dependency.read_bytes()).hexdigest()
    payload = build_v3_package_set(
        package_name="fixture",
        package_version="1",
        profile="system",
        roles=["system", "dependencies"],
        outputs=[
            {"filename": system.name, "size_bytes": system.stat().st_size, "sha256": hashlib.sha256(system.read_bytes()).hexdigest(), "role": "system"},
            {"filename": dependency.name, "size_bytes": dependency.stat().st_size, "sha256": dep_sha, "role": "dependencies"},
        ],
        dependency_artifacts=[{"filename": dependency.name, "size_bytes": dependency.stat().st_size, "sha256": dep_sha}],
    )
    assert verify_package_set(tmp_path, payload) == []
    tampered = dict(payload)
    tampered["package_version"] = "2"
    assert "package_set_sha256_mismatch" in verify_package_set(tmp_path, tampered)


def _dependency_public_entry(artifact: dict[str, object]) -> dict[str, object]:
    descriptor = artifact["descriptor"]
    assert isinstance(descriptor, dict)
    return {
        "role": "dependencies",
        "filename": artifact["filename"],
        "size_bytes": artifact["size_bytes"],
        "sha256": artifact["sha256"],
        "bundle_name": descriptor.get("bundle_name"),
        "profiles": descriptor.get("profiles") or [],
        "target": descriptor.get("target") or {},
        "dependency_contract_fingerprint": descriptor.get("dependency_contract_fingerprint"),
        "wheelhouse_manifest_sha256": descriptor.get("wheelhouse_manifest_sha256"),
        "hash_lock_sha256": descriptor.get("hash_lock_sha256"),
    }


def test_runtime_sidecar_discovery_requires_verified_package_set_v3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _valid_bundle(tmp_path)
    source = tmp_path / "release"
    source.mkdir()
    sidecar = source / "dependencies.zip"
    artifact = build_dependency_sidecar(bundle, sidecar)
    public = _dependency_public_entry(artifact)
    dependency_set = {
        "schema_version": DEPENDENCY_SET_SCHEMA,
        "runtime_version": "16.3.25.5-package-distribution-convergence",
        "artifacts": [public],
        "network_fallback_allowed": False,
    }
    (source / DEPENDENCY_SET_NAME).write_text(json.dumps(dependency_set), encoding="utf-8")
    package_set = build_v3_package_set(
        package_name="fixture",
        package_version="16.3.25.5-package-distribution-convergence",
        profile="dependencies",
        roles=["dependencies"],
        outputs=[{
            "filename": sidecar.name,
            "size_bytes": sidecar.stat().st_size,
            "sha256": sha256_file(sidecar),
            "role": "dependencies",
            "is_complete_zip": True,
        }],
        dependency_artifacts=[public],
        generator="test",
        generator_version="8.8",
    )
    package_path = source / "fixture.package.json"
    package_path.write_text(json.dumps(package_set), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("JAZN_PACKAGE_SOURCE_DIR", str(source))

    result = materialize_compatible_dependency_artifact(project)
    assert result["ok"] is True
    assert result["package_set_path"] == str(package_path)
    assert Path(result["bundle_dir"]).is_dir()


def test_runtime_sidecar_discovery_fails_closed_without_package_set_v3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _valid_bundle(tmp_path)
    source = tmp_path / "release"
    source.mkdir()
    sidecar = source / "dependencies.zip"
    artifact = build_dependency_sidecar(bundle, sidecar)
    dependency_set = {
        "schema_version": DEPENDENCY_SET_SCHEMA,
        "runtime_version": "16.3.25.5-package-distribution-convergence",
        "artifacts": [_dependency_public_entry(artifact)],
        "network_fallback_allowed": False,
    }
    (source / DEPENDENCY_SET_NAME).write_text(json.dumps(dependency_set), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("JAZN_PACKAGE_SOURCE_DIR", str(source))

    result = materialize_compatible_dependency_artifact(project)
    assert result["ok"] is False
    assert result["state"] == "dependency_package_set_unverified"
