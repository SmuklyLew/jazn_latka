from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

import CHATGPT_BOOTSTRAP as bootstrap


_REQUIRED_MEMBERS = {
    "run.py": "print('ok')\n",
    "AGENTS.md": "# test\n",
    "latka_jazn/version.py": "PACKAGE_VERSION='test'\n",
    "PACKAGE_INTEGRITY_MANIFEST.json": "{}\n",
    "SOURCE_PROVENANCE.json": "{}\n",
}


def _write_zip(path: Path, members: dict[str, str], *, prefix: str = "") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(f"{prefix}{name}", content)


def _sidecar(zip_path: Path, *, digest: str | None = None) -> Path:
    actual = digest or hashlib.sha256(zip_path.read_bytes()).hexdigest()
    path = zip_path.with_name(f"{zip_path.name}.sha256")
    path.write_text(f"{actual}  {zip_path.name}\n", encoding="ascii")
    return path


def test_bootstrap_materializes_verified_root(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    _write_zip(package, _REQUIRED_MEMBERS)
    sidecar = _sidecar(package)
    destination = tmp_path / "runtime"

    result = bootstrap.bootstrap_system_zip(
        zip_path=package,
        sha256_file_path=sidecar,
        destination=destination,
    )

    assert result["ok"] is True
    assert result["state"] == "materialized_operator_ready"
    assert result["root_prefix"] is None
    assert (destination / "run.py").is_file()
    assert (destination / "AGENTS.md").is_file()


def test_bootstrap_accepts_one_top_level_wrapper(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    _write_zip(package, _REQUIRED_MEMBERS, prefix="jazn-system/")
    sidecar = _sidecar(package)
    destination = tmp_path / "runtime"

    result = bootstrap.bootstrap_system_zip(
        zip_path=package,
        sha256_file_path=sidecar,
        destination=destination,
    )

    assert result["ok"] is True
    assert result["root_prefix"] == "jazn-system/"
    assert (destination / "latka_jazn" / "version.py").is_file()


def test_bootstrap_rejects_sha_mismatch_before_extraction(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    _write_zip(package, _REQUIRED_MEMBERS)
    sidecar = _sidecar(package, digest="0" * 64)
    destination = tmp_path / "runtime"

    with pytest.raises(bootstrap.BootstrapError, match="SHA-256 mismatch"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=destination,
        )

    assert not destination.exists()


def test_bootstrap_rejects_path_traversal(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    members = dict(_REQUIRED_MEMBERS)
    members["../escape.txt"] = "nope"
    _write_zip(package, members)
    sidecar = _sidecar(package)
    destination = tmp_path / "runtime"

    with pytest.raises(bootstrap.BootstrapError, match="unsafe ZIP member path"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=destination,
        )

    assert not destination.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_bootstrap_rejects_symlink(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in _REQUIRED_MEMBERS.items():
            zf.writestr(name, content)
        info = zipfile.ZipInfo("runtime-link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "run.py")
    sidecar = _sidecar(package)

    with pytest.raises(bootstrap.BootstrapError, match="symlink rejected"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=tmp_path / "runtime",
        )


def test_bootstrap_rejects_duplicate_member(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in _REQUIRED_MEMBERS.items():
            zf.writestr(name, content)
        with pytest.warns(UserWarning):
            zf.writestr("run.py", "print('duplicate')\n")
    sidecar = _sidecar(package)

    with pytest.raises(bootstrap.BootstrapError, match="duplicate ZIP member"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=tmp_path / "runtime",
        )


def test_bootstrap_refuses_existing_destination(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    _write_zip(package, _REQUIRED_MEMBERS)
    sidecar = _sidecar(package)
    destination = tmp_path / "runtime"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapError, match="refusing overwrite"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=destination,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_bootstrap_enforces_uncompressed_size_budget(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    members = dict(_REQUIRED_MEMBERS)
    members["large.bin"] = "x" * 4096
    _write_zip(package, members)
    sidecar = _sidecar(package)

    with pytest.raises(bootstrap.BootstrapError, match="uncompressed-size limit exceeded"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=tmp_path / "runtime",
            max_total_bytes=1024,
        )
