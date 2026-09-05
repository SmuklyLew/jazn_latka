from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from latka_jazn.python_runtime import (
    HostTarget,
    PythonRuntimeContractError,
    build_runtime_bundle,
    build_runtime_launch_command,
    build_runtime_set,
    materialize_runtime_bundle,
    render_runtime_index,
    runtime_target,
    runtime_target_from_mapping,
    sanitized_runtime_environment,
    select_runtime_artifact,
    verify_runtime_bundle,
    verify_runtime_set,
)
from latka_jazn.tools.package_distribution import _parser as package_distribution_parser


ROOT = Path(__file__).resolve().parents[1]


def _runtime_tree(root: Path, interpreter: str) -> Path:
    runtime = root
    target = runtime / interpreter
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake-python-runtime")
    packages = runtime / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    (packages / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    return runtime


def _bundle(tmp_path: Path, name: str, *, alias: str, py: str, libc: str | None = None) -> Path:
    interpreter = "python.exe" if alias.startswith("windows-") else "bin/python3"
    runtime = _runtime_tree(tmp_path / f"runtime-{name}", interpreter)
    output = tmp_path / f"{name}.zip"
    build_runtime_bundle(
        runtime,
        output,
        target=runtime_target(alias, py, libc_family=libc),
        provider="test-fixture",
        source_reference="fixture://runtime",
        interpreter_relative_path=interpreter,
    )
    return output


def _pack_generator_module():
    path = ROOT / "tools" / "jazn_pack_generator.py"
    name = "jazn_pack_generator_runtime_bundle_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_target_ids_keep_linux_libc_explicit() -> None:
    windows = runtime_target("windows-x64", "3.14")
    linux = runtime_target("linux-x64", "3.14", libc_family="glibc")
    assert windows.target_id == "windows-x64-py314"
    assert linux.target_id == "linux-x64-glibc-py314"
    with pytest.raises(PythonRuntimeContractError):
        runtime_target("linux-x64", "3.14")


@pytest.mark.parametrize("value", [None, [], "windows-x64"])
def test_runtime_target_from_mapping_rejects_non_mapping(value: object) -> None:
    with pytest.raises(PythonRuntimeContractError, match="runtime_target_not_mapping"):
        runtime_target_from_mapping(value)


def test_runtime_bundle_roundtrip_is_hash_verified_and_materialized(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, "win314", alias="windows-x64", py="3.14")
    verification = verify_runtime_bundle(bundle)
    assert verification["ok"] is True
    assert verification["target"]["target_id"] == "windows-x64-py314"

    result = materialize_runtime_bundle(bundle, tmp_path / "materialized")
    assert result["ok"] is True
    runtime_root = Path(result["runtime_root"])
    assert (runtime_root / "python.exe").read_bytes() == b"fake-python-runtime"
    assert (runtime_root / "packages" / "demo.py").is_file()
    assert (runtime_root / "JAZN_PYTHON_RUNTIME_READY.json").is_file()

    reused = materialize_runtime_bundle(bundle, tmp_path / "materialized")
    assert reused["state"] == "runtime_reused"


def test_runtime_bundle_rejects_parent_traversal_before_manifest_use(tmp_path: Path) -> None:
    malicious = tmp_path / "bad.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.txt", b"no")
        archive.writestr("JAZN_PYTHON_RUNTIME_MANIFEST.json", json.dumps({"schema_version": "jazn_python_runtime_manifest/v1"}))
    report = verify_runtime_bundle(malicious)
    assert report["ok"] is False
    assert any("unsafe_runtime_member" in item for item in report["errors"])


def test_runtime_set_selects_highest_preferred_compatible_target(tmp_path: Path) -> None:
    win312 = _bundle(tmp_path, "win312", alias="windows-x64", py="3.12")
    win314 = _bundle(tmp_path, "win314", alias="windows-x64", py="3.14")
    linux = _bundle(tmp_path, "linux314", alias="linux-x64", py="3.14", libc="glibc")
    runtime_set = build_runtime_set([win312, win314, linux])
    host = HostTarget("windows-x64", "x86_64", "not-applicable", "windows")

    selected = select_runtime_artifact(runtime_set, host=host)
    assert selected["target"]["python_version"] == "3.14"
    requested = select_runtime_artifact(runtime_set, host=host, requested_python="3.12")
    assert requested["target"]["python_version"] == "3.12"

    index = render_runtime_index(runtime_set)
    assert "windows-x64-py314" in index
    assert "linux-x64-glibc-py314" in index


def test_runtime_set_rejects_linux_libc_mismatch(tmp_path: Path) -> None:
    linux = _bundle(tmp_path, "linux314", alias="linux-x64", py="3.14", libc="glibc")
    runtime_set = build_runtime_set([linux])
    host = HostTarget("linux-x64", "x86_64", "musl", "linux")
    with pytest.raises(PythonRuntimeContractError, match="no_compatible_python_runtime"):
        select_runtime_artifact(runtime_set, host=host)


def test_runtime_set_verification_checks_outer_sha(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, "win314", alias="windows-x64", py="3.14")
    runtime_set = build_runtime_set([bundle])
    assert verify_runtime_set(tmp_path, runtime_set)["ok"] is True
    bundle.write_bytes(bundle.read_bytes() + b"tamper")
    report = verify_runtime_set(tmp_path, runtime_set, verify_bundles=False)
    assert report["ok"] is False
    assert any("sha256_mismatch" in item for item in report["errors"])


def test_runtime_launcher_is_isolated_and_sanitizes_host_python_environment(tmp_path: Path) -> None:
    app = tmp_path / "app"
    runtime = tmp_path / "runtime"
    app.mkdir()
    runtime.mkdir()
    (app / "jazn_runtime_bootstrap.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    python = runtime / "python.exe"
    python.write_bytes(b"x")

    command = build_runtime_launch_command(python, app, runtime, ["status"])
    assert command[1:4] == ["-I", "-X", "utf8"]
    assert command[-2:] == ["--", "status"]

    environment = sanitized_runtime_environment(
        runtime,
        base={"PYTHONPATH": "foreign", "PYTHONHOME": "foreign", "VIRTUAL_ENV": "foreign", "KEEP": "1"},
    )
    assert "PYTHONPATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert environment["KEEP"] == "1"
    assert environment["JAZN_PYTHON_RUNTIME_ACTIVE"] == "1"


def test_package_distribution_cli_accepts_verified_python_runtime_sidecars() -> None:
    parsed = package_distribution_parser().parse_args(
        [
            "--output-dir", "dist",
            "--mode", "system-portable",
            "--dependency-bundle", "wheelhouse",
            "--python-runtime-bundle", "python-runtime.zip",
            "--target", "windows-x64",
            "--python-version", "3.14",
        ]
    )
    assert parsed.python_runtime_bundle == ["python-runtime.zip"]


def test_clean_pack_generator_does_not_route_python_runtime_sidecars() -> None:
    generator = _pack_generator_module()
    assert generator.GENERATOR_VERSION == "10.1.86.0.111"
    assert not hasattr(generator, "run_distribution_pack")
    report = generator.config_report()
    assert "python-runtime" in report["not_in_scope"]
    assert "target-platform" in report["not_in_scope"]



def test_windows_launcher_prefers_private_runtime_contract_before_host_python() -> None:
    text = (ROOT / "JAZN.cmd").read_text(encoding="utf-8")
    assert "JAZN_PYTHON_RUNTIME_SET.json" in text
    assert "Start-JaznPythonRuntime.ps1" in text
    assert text.index("JAZN_PYTHON_RUNTIME_SET.json") < text.index("where py.exe")


def test_windows_runtime_launcher_powershell_parses_when_shell_is_available() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    if shell is None:
        pytest.skip("PowerShell is not available on this runner")
    script = ROOT / "tools" / "Start-JaznPythonRuntime.ps1"
    environment = dict(os.environ)
    environment["JAZN_POWERSHELL_PARSE_FILE"] = str(script)
    command = (
        "$ErrorActionPreference='Stop';"
        "$tokens=$null;$errors=$null;"
        "$null=[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:JAZN_POWERSHELL_PARSE_FILE,[ref]$tokens,[ref]$errors);"
        "if(@($errors).Count -gt 0){"
        "$errors | ForEach-Object { [Console]::Error.WriteLine($_.ToString()) };"
        "exit 1"
        "}"
    )
    completed = subprocess.run(
        [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_posix_runtime_launcher_shell_syntax_when_sh_is_available() -> None:
    shell = shutil.which("sh")
    if shell is None:
        pytest.skip("POSIX sh is not available on this runner")
    completed = subprocess.run(
        [shell, "-n", str(ROOT / "jazn")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
