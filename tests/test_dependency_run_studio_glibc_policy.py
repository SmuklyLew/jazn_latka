"""Profile-aware manylinux floors: core remains 2.17, Qt/JSS requires 2.34.

No live daemon, network access, runtime marker mutation or model execution.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from latka_jazn.dependencies import common
from latka_jazn.dependencies.wheelhouse import download_bundle

ROOT = Path(__file__).resolve().parents[1]


def _linux_host(monkeypatch: pytest.MonkeyPatch, version: str = "2.39") -> None:
    monkeypatch.setattr(common, "current_platform_alias", lambda: "linux-x64")
    monkeypatch.setattr(common, "current_libc_family", lambda: "glibc")
    monkeypatch.setattr(common.platform_module, "libc_ver", lambda: ("glibc", version))


def test_core_target_preserves_release_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    _linux_host(monkeypatch)
    target = common.target_spec("linux-x64", "3.14")
    assert target.minimum_libc_version == "2.17"
    assert target.pip_platforms == common.LINUX_X64_PIP_PLATFORMS
    assert "manylinux_2_34_x86_64" not in target.pip_platforms
    assert "cp314-cp314-manylinux_2_17_x86_64" in target.compatible_tags


@pytest.mark.parametrize("python_version", ["3.12", "3.13", "3.14"])
def test_qt_target_supports_pyside6_abi3_wheel(
    monkeypatch: pytest.MonkeyPatch, python_version: str
) -> None:
    _linux_host(monkeypatch)
    target = common.target_spec("linux-x64", python_version, requires_run_studio=True)
    assert target.minimum_libc_version == "2.34"
    assert target.pip_platforms[0] == "manylinux_2_34_x86_64"
    assert "manylinux_2_17_x86_64" in target.pip_platforms
    # PySide6-Essentials 6.12.0 is distributed as cp310-abi3-manylinux_2_34.
    assert "cp310-abi3-manylinux_2_34_x86_64" in target.compatible_tags


def test_old_linux_host_rejects_qt_even_when_core_supported(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_host(monkeypatch, "2.31")
    current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert common.target_spec("linux-x64", current_python).minimum_libc_version == "2.17"
    with pytest.raises(common.DependencyStudioError, match="JSS/Qt requires glibc"):
        common.target_spec("linux-x64", current_python, requires_run_studio=True)


@pytest.mark.parametrize("actual,minimum,allowed", [
    ("2.17", "2.17", True),
    ("2.34", "2.34", True),
    ("2.39", "2.34", True),
    ("2.31", "2.34", False),
    ("", "2.34", False),
    ("garbage", "2.34", False),
])
def test_version_floor_comparison_fail_closed(actual: str, minimum: str, allowed: bool) -> None:
    assert common.glibc_version_at_least(actual, minimum) is allowed


def test_target_host_compatibility_checks_glibc_version(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_host(monkeypatch, "2.39")
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    target = common.target_spec("linux-x64", py, requires_run_studio=True)
    assert common.target_is_current_host(target)
    monkeypatch.setattr(common.platform_module, "libc_ver", lambda: ("glibc", "2.31"))
    assert not common.target_is_current_host(target)


def test_download_dry_run_resolves_profile_before_wheelhouse_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_host(monkeypatch)
    lock = tmp_path / "synthetic-lock.txt"
    lock.write_text("example==1 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    jss = download_bundle(
        ROOT, profile_names=("core", "run-studio"), python_version="3.14",
        platform_alias="linux-x64", lock_file=lock,
        wheelhouse_root=tmp_path / "jss", dry_run=True,
    )
    core = download_bundle(
        ROOT, profile_names=("core",), python_version="3.14",
        platform_alias="linux-x64", lock_file=lock,
        wheelhouse_root=tmp_path / "core", dry_run=True,
    )
    assert jss["target"]["minimum_libc_version"] == "2.34"
    assert core["target"]["minimum_libc_version"] == "2.17"
    assert jss["target"]["compatible_pip_platforms"][0] == "manylinux_2_34_x86_64"
    assert core["target"]["compatible_pip_platforms"][0] == "manylinux_2_17_x86_64"
    assert not (tmp_path / "jss").exists()
    assert not (tmp_path / "core").exists()
