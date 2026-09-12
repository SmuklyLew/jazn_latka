from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from latka_jazn.packaging.split_zip_package import (
    PackagePartExpectation,
    resolve_renamed_package_parts,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_host_renamed_part_006_is_resolved_by_manifest_identity_and_frozen(tmp_path: Path) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    base = "jazn_memory.zip"
    expected: list[PackagePartExpectation] = []
    payloads: dict[int, bytes] = {}
    for part_no in range(1, 7):
        payload = (f"part-{part_no:03d}|".encode("ascii") * 41) + bytes([part_no])
        payloads[part_no] = payload
        canonical_name = f"{base}.{part_no:03d}"
        source_name = canonical_name if part_no < 6 else f"{base}(1).006"
        (parts_dir / source_name).write_bytes(payload)
        expected.append(
            PackagePartExpectation(
                part_no=part_no,
                filename=canonical_name,
                size_bytes=len(payload),
                sha256=_sha(payload),
            )
        )

    canonical_dir = tmp_path / "canonical"
    result = resolve_renamed_package_parts(parts_dir, expected, canonical_dir=canonical_dir)

    assert result["ok"] is True
    assert result["parts_count"] == 6
    assert result["renamed_parts_count"] == 1
    part6 = next(item for item in result["resolved_parts"] if item["part_no"] == 6)
    assert part6["expected_name"] == f"{base}.006"
    assert part6["source_name"] == f"{base}(1).006"
    assert part6["renamed_by_host"] is True
    assert (canonical_dir / f"{base}.006").read_bytes() == payloads[6]


def test_part006_resolution_fails_closed_when_two_noncanonical_candidates_match(tmp_path: Path) -> None:
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    payload = b"same verified bytes for ambiguous candidates"
    (parts_dir / "jazn_memory.zip(1).006").write_bytes(payload)
    (parts_dir / "jazn_memory.zip(2).006").write_bytes(payload)
    expected = [
        PackagePartExpectation(
            part_no=6,
            filename="jazn_memory.zip.006",
            size_bytes=len(payload),
            sha256=_sha(payload),
        )
    ]

    with pytest.raises(ValueError, match="Niejednoznaczne części"):
        resolve_renamed_package_parts(
            parts_dir,
            expected,
            canonical_dir=tmp_path / "canonical",
        )
