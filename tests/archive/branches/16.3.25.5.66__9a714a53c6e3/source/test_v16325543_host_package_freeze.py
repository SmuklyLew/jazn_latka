from __future__ import annotations

import hashlib
from pathlib import Path

from latka_jazn.packaging.split_zip_package import (
    PackagePartExpectation,
    resolve_renamed_package_parts,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_resolved_package_part_is_frozen_independently_from_host_upload(tmp_path: Path) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    source = parts_dir / "jazn-system.zip(1).001"
    original = (b"verified-package-part\n" * 128) + b"tail"
    source.write_bytes(original)

    expected = [
        PackagePartExpectation(
            part_no=1,
            filename="jazn-system.zip.001",
            size_bytes=len(original),
            sha256=_sha256_bytes(original),
        )
    ]
    canonical_dir = tmp_path / "canonical"

    result = resolve_renamed_package_parts(
        parts_dir,
        expected,
        canonical_dir=canonical_dir,
        skip_part_hash=False,
    )

    target = canonical_dir / "jazn-system.zip.001"
    assert result["ok"] is True
    assert result["renamed_parts_count"] == 1
    assert result["resolved_parts"][0]["materialization"] == "verified_atomic_copy"
    assert target.read_bytes() == original
    assert _sha256_bytes(target.read_bytes()) == expected[0].sha256

    # Simulate a host rewriting the original upload after canonicalization.
    replacement = b"X" * len(original)
    source.write_bytes(replacement)

    assert source.read_bytes() == replacement
    assert target.read_bytes() == original
    assert _sha256_bytes(target.read_bytes()) == expected[0].sha256
