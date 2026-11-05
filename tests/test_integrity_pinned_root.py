"""Batch verification pins ROOT without caching member trust or file contents."""
import os

import pytest

from latka_jazn.tools.package_integrity import (
    build_package_integrity_manifest, serialize_package_integrity_manifest,
    verify_package_integrity_manifest,
)
from latka_jazn.tools.safe_paths import SafePathRoot, UnsafeRelativePathError


@pytest.mark.parametrize("unsafe", ["../outside", "/outside", "C:/outside", "a\\outside", "a:stream", "NUL"])
def test_batch_member_does_not_inherit_trust_from_an_earlier_valid_path(tmp_path, unsafe):
    (tmp_path / "valid.txt").write_text("safe", encoding="utf-8")
    resolver = SafePathRoot(tmp_path)
    assert resolver.resolve("valid.txt") == ("valid.txt", tmp_path / "valid.txt")
    with pytest.raises(UnsafeRelativePathError):
        resolver.resolve(unsafe)


@pytest.mark.parametrize("replace_root", [False, True])
def test_batch_detects_a_link_escape_introduced_after_an_earlier_member(tmp_path, replace_root):
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "nested").mkdir(parents=True)
    (outside / "nested").mkdir(parents=True)
    (root / "nested/payload.txt").write_text("inside", encoding="utf-8")
    (outside / "nested/payload.txt").write_text("outside", encoding="utf-8")
    resolver = SafePathRoot(root)
    assert resolver.resolve("nested/payload.txt")[1].read_text(encoding="utf-8") == "inside"
    replaced = root if replace_root else root / "nested"
    target = outside if replace_root else outside / "nested"
    retained = tmp_path / "retained"
    assert replaced.resolve().is_relative_to(tmp_path.resolve())
    assert retained.parent == tmp_path
    replaced.rename(retained)
    try:
        os.symlink(target, replaced, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("Host cannot create a directory symlink: " + str(exc))
    with pytest.raises(UnsafeRelativePathError, match="escapes root"):
        resolver.resolve("nested/payload.txt")
    assert (outside / "nested/payload.txt").read_text(encoding="utf-8") == "outside"


def test_repeated_verification_rehashes_contents_and_checks_new_static_members(tmp_path):
    root = tmp_path / "SYSTEM"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    for name in ("SOURCE_PROVENANCE.json", "run.py", "main.py", "payload.txt"):
        (root / name).write_text("original", encoding="utf-8")
    manifest = build_package_integrity_manifest(root)
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_bytes(serialize_package_integrity_manifest(manifest))
    assert verify_package_integrity_manifest(root)["ok"] is True
    (root / "payload.txt").write_text("modified", encoding="utf-8")  # Same byte length.
    (root / "unexpected.txt").write_text("new static file", encoding="utf-8")
    report = verify_package_integrity_manifest(root)
    assert report["ok"] is False
    assert {"sha256_mismatch", "unexpected_static_file"} <= {item["code"] for item in report["errors"]}
