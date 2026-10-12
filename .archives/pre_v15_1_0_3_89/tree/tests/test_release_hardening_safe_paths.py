from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import zipfile

import pytest

from latka_jazn.tools.package_export import build_package_manifest, build_packing_audit
from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
from latka_jazn.tools.release_readiness import _copy_static_package
from latka_jazn.tools.safe_paths import (
    UnsafeRelativePathError,
    resolve_safe_destination,
    resolve_safe_source,
    validate_safe_relative_path,
)


@pytest.mark.security
@pytest.mark.parametrize(
    "value",
    [
        "../secret.txt",
        "..\\secret.txt",
        "/etc/passwd",
        "C:\\Windows\\system.ini",
        "\\\\server\\share\\file",
        "",
        "bad\x00name",
    ],
)
def test_canonical_relative_path_rejects_cross_platform_escape(value: str) -> None:
    with pytest.raises(UnsafeRelativePathError):
        validate_safe_relative_path(value)


@pytest.mark.security
def test_safe_nested_source_and_destination_remain_under_roots(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    nested = source_root / "safe" / "nested" / "file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("safe", encoding="utf-8")
    assert resolve_safe_source(source_root, "safe/nested/file.txt") == nested.resolve()
    assert resolve_safe_destination(destination_root, "safe/nested/file.txt").is_relative_to(destination_root.resolve())


def _symlink_or_skip(link: Path, target: Path, *, directory: bool) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this Windows runner: {exc}")


@pytest.mark.security
def test_source_symlink_outside_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    _symlink_or_skip(root / "linked.txt", outside, directory=False)
    with pytest.raises(UnsafeRelativePathError, match="escapes root"):
        resolve_safe_source(root, "linked.txt")


@pytest.mark.security
def test_manifest_copy_rejects_destination_symlink_escape_before_copy(tmp_path: Path) -> None:
    root = tmp_path / "root"
    destination = tmp_path / "destination"
    outside = tmp_path / "outside"
    (root / "escape").mkdir(parents=True)
    destination.mkdir()
    outside.mkdir()
    source = root / "escape" / "file.txt"
    source.write_text("safe source", encoding="utf-8")
    _symlink_or_skip(destination / "escape", outside, directory=True)
    manifest = {
        "files": [{
            "path": "escape/file.txt",
            "size_bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }],
    }
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(UnsafeRelativePathError, match="escapes root"):
        _copy_static_package(root, destination)
    assert not (outside / "file.txt").exists()


@pytest.mark.security
def test_malicious_package_integrity_manifest_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text(
        'DISTRIBUTION_VERSION="15.0.3.2"\nPACKAGE_VERSION="v15.0.3.2"\nPACKAGE_RELEASE_NAME=""\n',
        encoding="utf-8",
    )
    payload = {
        "version": "v15.0.3.2",
        "runtime_version": "v15.0.3.2",
        "files": [{"path": "../secret.txt", "size_bytes": 0, "sha256": "0" * 64}],
    }
    (tmp_path / "PACKAGE_INTEGRITY_MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")
    report = verify_package_integrity_manifest(tmp_path)
    assert report["ok"] is False
    assert any(item["code"] == "unsafe_manifest_path" for item in report["errors"])


@pytest.mark.security
def test_zip_audit_uses_same_path_boundary(tmp_path: Path) -> None:
    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../secret.txt", "secret")
    manifest = build_package_manifest(archive, mode="system")
    audit = build_packing_audit(archive, manifest)
    assert audit["ok"] is False
    assert "unsafe_paths" in audit["errors"]
    assert "../secret.txt" in audit["unsafe_paths"]
