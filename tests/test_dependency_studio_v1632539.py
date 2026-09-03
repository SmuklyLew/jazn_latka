from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from latka_jazn.dependencies.runtime import (
    ENVIRONMENT_MARKER_NAME,
    LOCK_NAME,
    MANIFEST_NAME,
    WHEELHOUSE_SCHEMA,
    ENVIRONMENT_SCHEMA,
    activation_profile_names,
    audit_project_dependencies,
    build_download_command,
    current_abi_tag,
    current_implementation_tag,
    current_platform_alias,
    current_libc_family,
    default_environments_root,
    default_wheelhouse_root,
    dependency_contract_fingerprint,
    environment_marker_path,
    dependency_activation_status,
    install_bundle,
    managed_environment_status,
    prepare_entrypoint_environment,
    render_hash_lock,
    resolve_profile_requirements,
    sha256_file,
    target_spec,
    verify_bundle,
    wheel_metadata,
)
from latka_jazn.tools.dependency_studio import build_parser, execute


PROFILE_JSON = Path(__file__).parents[1] / "latka_jazn" / "resources" / "dependencies" / "profiles.json"


def _project(tmp_path: Path, *, dependencies: list[str] | None = None) -> Path:
    root = tmp_path / "repo"
    (root / "latka_jazn" / "resources" / "dependencies").mkdir(parents=True)
    (root / "latka_jazn" / "__init__.py").write_text("", encoding="utf-8")
    (root / "latka_jazn" / "resources" / "dependencies" / "profiles.json").write_text(
        PROFILE_JSON.read_text(encoding="utf-8"), encoding="utf-8"
    )
    deps = dependencies or [
        "pypdf>=5.0.0",
        "tzdata>=2024.1",
        "packaging>=24.2,<27",
        "py7zr>=1.1.3,<2",
        "pyzipper>=0.4.0,<1",
    ]
    pyproject = "[project]\nname='fixture'\nversion='1.0'\nrequires-python='>=3.12'\ndependencies=[\n"
    pyproject += "".join(f"  {item!r},\n" for item in deps)
    pyproject += "]\n[project.optional-dependencies]\n"
    pyproject += "memory-rebuild-ui=['prompt-toolkit>=3.0.52,<4']\n"
    pyproject += "memory-cloud=['PyNaCl>=1.5,<2']\n"
    pyproject += "memory-cloud-server=['PyNaCl>=1.5,<2','psycopg[binary]>=3.2,<4','boto3>=1.35,<2']\n"
    pyproject += "polish-nlp=['requests>=2.31']\n"
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return root


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"sha256={encoded}"


def _fake_wheel(directory: Path, name: str = "demo", version: str = "1.0") -> Path:
    wheel = directory / f"{name}-{version}-py3-none-any.whl"
    dist_info = f"{name}-{version}.dist-info"
    members = {
        f"{name}/__init__.py": b"__version__='1.0'\n",
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
            "Requires-Python: >=3.12\nLicense-Expression: MIT\n\n"
        ).encode("utf-8"),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode("utf-8"),
    }
    record_name = f"{dist_info}/RECORD"
    rows = [f"{path},{_record_hash(data)},{len(data)}" for path, data in members.items()]
    rows.append(f"{record_name},,")
    members[record_name] = ("\n".join(rows) + "\n").encode("utf-8")
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in members.items():
            archive.writestr(path, data)
    return wheel


def _bundle(root: Path, bundle_dir: Path, *, profiles: list[str] | None = None) -> Path:
    bundle_dir.mkdir(parents=True)
    wheel = _fake_wheel(bundle_dir)
    metadata = wheel_metadata(wheel)
    row = {
        "filename": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": sha256_file(wheel),
        "metadata": metadata,
    }
    resolved = [{
        "name": "demo",
        "version": "1.0",
        "filename": wheel.name,
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "requires_python": metadata.get("requires_python"),
        "license_expression": metadata.get("license_expression"),
        "license": metadata.get("license"),
        "license_files": list(metadata.get("license_files") or []),
        "tags": list((metadata.get("filename") or {}).get("tags") or []),
        "record_verified": True,
    }]
    lock_text = render_hash_lock(resolved)
    lock_path = bundle_dir / LOCK_NAME
    lock_path.write_text(lock_text, encoding="utf-8")
    target = target_spec("current", f"{sys.version_info.major}.{sys.version_info.minor}")
    manifest = {
        "schema_version": WHEELHOUSE_SCHEMA,
        "runtime_version": "fixture",
        "created_at_utc": "2026-09-01T00:00:00+00:00",
        "profiles": profiles or ["core", "archive"],
        "resolved_profiles": profiles or ["core", "archive"],
        "requirements": ["demo==1.0"],
        "direct_requirements": ["demo==1.0"],
        "dependency_contract_fingerprint": "fixture-dependency-contract",
        "target": target.to_dict(),
        "resolved_distributions": resolved,
        "files": [row],
        "wheel_count": 1,
        "total_size_bytes": wheel.stat().st_size,
        "hash_lock_sha256": sha256_file(lock_path),
    }
    (bundle_dir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return bundle_dir


def test_core_archive_resolves_all_required_base_dependencies(tmp_path: Path) -> None:
    root = _project(tmp_path)
    requirements = resolve_profile_requirements(root, ["core", "archive"])
    assert requirements == [
        "pypdf>=5.0.0",
        "tzdata>=2024.1",
        "packaging>=24.2,<27",
        "py7zr>=1.1.3,<2",
        "pyzipper>=0.4.0,<1",
    ]
    assert activation_profile_names(root) == ("core", "archive")


def test_windows_x64_download_plan_is_wheel_only_and_targeted(tmp_path: Path) -> None:
    target = target_spec("windows-x64", "3.12")
    command = build_download_command(
        python_executable="python",
        destination=tmp_path / "wheels",
        requirements=["py7zr>=1.1.3,<2"],
        target=target,
    )
    assert "--only-binary=:all:" in command
    assert command[command.index("--platform") + 1] == "win_amd64"
    assert command[command.index("--python-version") + 1] == "3.12"
    assert command[command.index("--abi") + 1] == "cp312"


def test_explicit_current_platform_alias_is_accepted_for_current_python() -> None:
    target = target_spec(
        current_platform_alias(),
        f"{sys.version_info.major}.{sys.version_info.minor}",
    )
    assert target.alias == current_platform_alias()
    assert target.python_version == f"{sys.version_info.major}.{sys.version_info.minor}"


def test_verify_bundle_checks_sha_and_wheel_structure(tmp_path: Path) -> None:
    root = _project(tmp_path)
    bundle = _bundle(root, tmp_path / "bundle")
    verified = verify_bundle(bundle)
    assert verified["ok"] is True
    assert verified["verified_wheel_count"] == 1

    wheel = next(bundle.glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tamper")
    failed = verify_bundle(bundle)
    assert failed["ok"] is False
    assert any(item["code"] == "wheel_size_mismatch" for item in failed["errors"])


def test_install_dry_run_is_offline_and_uses_managed_environment(tmp_path: Path) -> None:
    root = _project(tmp_path, dependencies=["demo==1.0", "py7zr>=1.1.3,<2", "pyzipper>=0.4.0,<1"])
    # Adjust the fixture registry so core resolves demo, while archive remains canonical.
    bundle = _bundle(root, tmp_path / "bundle")
    result = install_bundle(root, bundle, offline=True, dry_run=True)
    assert result["ok"] is True
    assert result["offline"] is True
    install_command = result["commands"]["install"]
    assert "--no-index" in install_command
    assert "--find-links" in install_command
    assert "local_resources" in result["environment_root"]


def test_download_dry_run_does_not_create_wheelhouse(tmp_path: Path) -> None:
    root = _project(tmp_path)
    parser = build_parser()
    ns = parser.parse_args([
        "--root", str(root),
        "download",
        "--profile", "core,archive",
        "--python-version", "3.12",
        "--platform", "windows-x64",
        "--dry-run",
    ])
    exit_code, payload = execute(ns)
    assert exit_code == 0
    assert payload["dry_run"] is True
    assert not default_wheelhouse_root(root).exists()
    assert payload["pip_command"][0]


def test_audit_reports_undeclared_external_import(tmp_path: Path) -> None:
    root = _project(tmp_path, dependencies=["requests>=2.31", "py7zr>=1.1.3,<2", "pyzipper>=0.4.0,<1"])
    (root / "latka_jazn" / "sample.py").write_text(
        "import requests\nimport fictional_dependency\n", encoding="utf-8"
    )
    payload = audit_project_dependencies(root)
    assert "requests" in payload["mapped_external_imports"]
    assert "fictional_dependency" in payload["undeclared_or_unmapped_external_imports"]


def test_activation_status_fails_closed_when_required_packages_missing(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        dependencies=[
            "definitely-not-installed-jazn-fixture>=1",
            "py7zr>=1.1.3,<2",
            "pyzipper>=0.4.0,<1",
        ],
    )
    status = dependency_activation_status(root)
    assert status["required_ready"] is False
    assert "definitely-not-installed-jazn-fixture" in status["missing_or_incompatible_distributions"]


def test_entrypoint_bootstrap_does_not_use_network_without_verified_bundle(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        dependencies=[
            "definitely-not-installed-jazn-fixture>=1",
            "py7zr>=1.1.3,<2",
            "pyzipper>=0.4.0,<1",
        ],
    )
    result = prepare_entrypoint_environment(root, auto_install=True)
    assert result["ok"] is False
    assert result["state"] == "dependencies_missing_no_verified_wheelhouse"
    assert result["reexec_python"] is None


def test_entrypoint_bootstrap_honors_canonical_wheelhouse_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(
        tmp_path,
        dependencies=[
            "definitely-not-installed-jazn-fixture>=1",
            "py7zr>=1.1.3,<2",
            "pyzipper>=0.4.0,<1",
        ],
    )
    external_wheelhouse = tmp_path / "external-wheelhouse"
    monkeypatch.setenv("JAZN_DEPENDENCY_WHEELHOUSE", str(external_wheelhouse))
    result = prepare_entrypoint_environment(root, auto_install=True)
    assert result["ok"] is False
    assert result["state"] == "dependencies_missing_no_verified_wheelhouse"
    assert result["wheelhouse_root"] == str(external_wheelhouse.resolve())
    assert result["reexec_python"] is None


def test_install_requires_explicit_offline_flag_in_cli(tmp_path: Path) -> None:
    root = _project(tmp_path)
    parser = build_parser()
    ns = parser.parse_args(["--root", str(root), "install"])
    with pytest.raises(Exception, match="offline"):
        execute(ns)


def test_all_profile_expands_to_activation_and_optional_profiles(tmp_path: Path) -> None:
    from latka_jazn.dependencies.runtime import expand_profile_names

    root = _project(tmp_path)
    expanded = expand_profile_names(root, ["all"])
    assert "core" in expanded
    assert "archive" in expanded
    assert "polish-nlp" in expanded
    assert expanded[-1] == "all"


def test_runtime_readiness_is_gated_by_required_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from latka_jazn.core.readiness import evaluate_runtime_readiness
    import latka_jazn.dependencies.runtime as dependency_runtime

    base_kwargs = {
        "required_checks": {"files": True},
        "package_integrity_checks": {
            "present": True,
            "parse_ok": True,
            "version_matches": True,
            "primary_present": True,
            "legacy_alias_absent": True,
            "canonical_source_name": True,
            "verification_ok": True,
        },
        "provenance": {
            "version_matches_runtime": True,
            "generation_mode": "git",
            "status": "clean_checkout_verified",
        },
        "daemon": {
            "active_state": "active_trusted",
            "pid_alive": True,
            "endpoint_reachable": True,
            "heartbeat_fresh": True,
        },
        "transactional_memory": {"ready": True, "exists": True},
        "dependency_root": tmp_path,
    }

    monkeypatch.setattr(
        dependency_runtime,
        "dependency_activation_status",
        lambda _root: {
            "required_ready": False,
            "selected_source": "missing",
            "missing_or_incompatible_distributions": ["py7zr"],
        },
    )
    blocked = evaluate_runtime_readiness(**base_kwargs)
    assert blocked.installation_ok is False
    assert blocked.activation_ready is False
    assert blocked.required_dependencies_ready is False
    assert blocked.dependency_missing == ("py7zr",)

    monkeypatch.setattr(
        dependency_runtime,
        "dependency_activation_status",
        lambda _root: {
            "required_ready": True,
            "selected_source": "managed_environment",
            "missing_or_incompatible_distributions": [],
        },
    )
    ready = evaluate_runtime_readiness(**base_kwargs)
    assert ready.installation_ok is True
    assert ready.activation_ready is True
    assert ready.required_dependencies_ready is True
    assert ready.summary()["dependencies"] == "ready"


def test_run_entrypoint_blocks_activation_when_required_dependencies_missing(tmp_path: Path) -> None:
    import shutil
    import subprocess

    root = _project(
        tmp_path,
        dependencies=[
            "definitely-not-installed-jazn-fixture>=1",
            "py7zr>=1.1.3,<2",
            "pyzipper>=0.4.0,<1",
        ],
    )
    (root / "latka_jazn" / "dependencies").mkdir(exist_ok=True)
    source_dependencies = Path(__file__).parents[1] / "latka_jazn" / "dependencies"
    for source in source_dependencies.glob("*.py"):
        shutil.copy2(source, root / "latka_jazn" / "dependencies" / source.name)
    (root / "latka_jazn" / "cli.py").write_text(
        "def main(argv=None):\n    return 0\n", encoding="utf-8"
    )
    shutil.copy2(Path(__file__).parents[1] / "run.py", root / "run.py")

    completed = subprocess.run(
        [sys.executable, str(root / "run.py"), "chat"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(root)},
    )
    assert completed.returncode == 78
    assert "required_python_dependencies_not_ready" in completed.stderr
    assert "no_verified_wheelhouse" in completed.stderr


def test_managed_environment_v2_reuses_dependency_contract_but_rejects_target_drift(tmp_path: Path) -> None:
    root = _project(tmp_path)
    bundle = _bundle(root, tmp_path / "bundle-target-drift")
    environments_root = default_environments_root(root)
    environment_root = environments_root / "fixture"
    python_path = environment_root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_bytes(b"fixture")

    marker_path = environment_marker_path(root)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "schema_version": ENVIRONMENT_SCHEMA,
        "ready": True,
        "environment_root": str(environment_root),
        "managed_environments_root": str(environments_root),
        "python_executable": str(python_path),
        "python_version": "0.0",
        "platform": current_platform_alias(),
        "implementation": current_implementation_tag(),
        "abi": current_abi_tag(),
        "libc_family": current_libc_family(),
        "profiles": ["core", "archive"],
        "resolved_profiles": ["core", "archive"],
        "wheelhouse_bundle": str(bundle),
        "wheelhouse_manifest_sha256": sha256_file(bundle / MANIFEST_NAME),
        "hash_lock_sha256": sha256_file(bundle / LOCK_NAME),
        "dependency_contract_fingerprint": dependency_contract_fingerprint(root, ["core", "archive"]),
        "created_for_runtime_version": "16.3.25.4-memory-rebuild-v4-consolidation",
        "import_smoke": {},
    }
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    status = managed_environment_status(root)
    assert status["ready"] is False
    assert "environment_python_target_changed_reinstall_required" in status["errors"]
    assert not any("runtime_version" in error for error in status["errors"])
