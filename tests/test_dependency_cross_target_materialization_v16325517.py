from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.dependencies.common import (
    DependencyStudioError,
    LINUX_GLIBC_MINIMUM,
    LINUX_X64_PIP_PLATFORMS,
    current_platform_alias,
    target_spec,
)
from latka_jazn.dependencies.wheelhouse import (
    build_locked_download_command,
    download_bundle,
)

ROOT = Path(__file__).resolve().parents[1]


def test_linux_x64_descriptor_is_deterministic_off_target() -> None:
    target = target_spec("linux-x64", "3.13")

    assert target.platform_family == "linux"
    assert target.architecture == "x86_64"
    assert target.libc_family == "glibc"
    assert target.minimum_libc_version == LINUX_GLIBC_MINIMUM == "2.17"
    assert target.pip_platforms == LINUX_X64_PIP_PLATFORMS
    assert "cp313-cp313-manylinux_2_17_x86_64" in target.compatible_tags
    assert "py3-none-any" in target.compatible_tags


def test_locked_cross_target_download_is_exact_wheel_only_replay(tmp_path: Path) -> None:
    lock = tmp_path / "linux-x64-py313.txt"
    lock.write_text("example==1 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")
    target = target_spec("linux-x64", "3.13")

    command = build_locked_download_command(
        python_executable="python",
        destination=tmp_path / "wheelhouse",
        lock_file=lock,
        target=target,
    )

    assert "--require-hashes" in command
    assert "--no-deps" in command
    assert "--only-binary=:all:" in command
    assert command.count("--platform") == len(LINUX_X64_PIP_PLATFORMS)
    for platform in LINUX_X64_PIP_PLATFORMS:
        assert platform in command
    assert command[command.index("--python-version") + 1] == "3.13"
    assert command[command.index("--implementation") + 1] == "cp"
    assert command[command.index("--abi") + 1] == "cp313"


def test_cross_target_without_lock_fails_before_wheelhouse_write(tmp_path: Path) -> None:
    other = "linux-x64" if current_platform_alias() != "linux-x64" else "windows-x64"
    wheelhouse = tmp_path / "wheelhouse"

    with pytest.raises(DependencyStudioError, match="requires a canonical"):
        download_bundle(
            tmp_path,
            profile_names=("core", "archive"),
            python_version="3.13",
            platform_alias=other,
            wheelhouse_root=wheelhouse,
            dry_run=True,
        )

    assert not wheelhouse.exists()


def test_cross_target_locked_dry_run_reports_materialization_mode(tmp_path: Path) -> None:
    other = "linux-x64" if current_platform_alias() != "linux-x64" else "windows-x64"
    lock = tmp_path / "target-lock.txt"
    lock.write_text("example==1 --hash=sha256:" + "0" * 64 + "\n", encoding="utf-8")

    result = download_bundle(
        ROOT,
        profile_names=("core", "archive"),
        python_version="3.13",
        platform_alias=other,
        wheelhouse_root=tmp_path / "wheelhouse",
        lock_file=lock,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["materialization_mode"] == "cross-target-locked"
    assert result["release_lock_path"] == str(lock.resolve())
