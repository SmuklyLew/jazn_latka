from __future__ import annotations

import json
from pathlib import Path
import sys
import zipfile

import pytest

from latka_jazn.dependencies.runtime import (
    ENVIRONMENT_MARKER_NAME,
    MANIFEST_NAME,
    WHEELHOUSE_SCHEMA,
    activation_profile_names,
    audit_project_dependencies,
    build_download_command,
    current_platform_alias,
    default_wheelhouse_root,
    dependency_activation_status,
    install_bundle,
    prepare_entrypoint_environment,
    resolve_profile_requirements,
    sha256_file,
    target_spec,
    verify_bundle,
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
        "py7zr>=1.1.3,<2",
        "pyzipper>=0.4.0,<1",
    ]
    pyproject = "[project]\nname='fixture'\nversion='1.0'\nrequires-python='>=3.12'\ndependencies=[\n"
    pyproject += "".join(f"  {item!r},\n" for item in deps)
    pyproject += "]\n[project.optional-dependencies]\n"
    pyproject += "memory-rebuild-ui=['prompt-toolkit>=3.0.52,<4']\n"
    pyproject += "memory-cloud=['PyNaCl>=1.5,<2']\n"
    pyproject += "memory-cloud-server=['PyNaCl>=1.5,<2','psycopg[binary]>=3.2,<4','boto3>=1.35,<2']\n"
    pyproject += "polish-nlp=['requests>=2.31#]\n"
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return root


def _fake_wheel(directory: Path, name: str = "demo", version: str = "1.0") -> Path:
    wheel = directory / f"{name}-{version}-py3-none-any.whl"
    dist_info = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) archive:
        archive.writestr(f"{name}/__init__.py", "__version__='1.0'\n")
        archive.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nLicense: MIT\n\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel


def _bundle(root: Path, bundle_dir: Path, *, profiles: list[str] | None = None) -> Path:
    bundle_dir.mkdir(parents=True)
    wheel = _fake_wheel(bundle_dir)
    manifest = {
        "schema_version": WHEELHOUSE_SCHEMA,
        "runtime_version": "fixture",
        "created_at_utc": "2026-09-01T00:00:00+00:00",
        "profiles": profiles or ["core", "archive"],
        "requirements": ["demo==1.0"],
        "target": {
            "alias": current_platform_alias(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "implementation": "cp",
            "abi": None,
            "pip_platform": None,
        },
        "files": [
            {
                "filename": wheel.name,
                "size_bytes": wheel.stat().st_size,
                "sha256": sha256_file(wheel),
                "metadata": {"name": "demo", "version": "1.0"},
            }
        ],
        "wheel_count": 1,
        "total_size_bytes": wheel.stat().st_size,
    }
    (bundle_dir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return bundle_dir


def test_core_archive_resolves_all_required_base_dependencies(tmp_path: Path) -> None:
    root = _project(tmp_path)
    requirements = resolve_profile_requirements(root, ["core", "archive"])
    assert requirements == [
        "pypdf>=5.0.0",
        "tzdata>=2024.1",
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
    assert any(item["code"] == "wheel_sha256_mismatch" for item in failed["errors"])


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
