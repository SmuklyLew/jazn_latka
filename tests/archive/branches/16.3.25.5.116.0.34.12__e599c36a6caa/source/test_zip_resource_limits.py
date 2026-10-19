from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from latka_jazn.packaging.zip_resource_limits import (
    ZipResourceLimitError,
    ZipResourceLimits,
    validate_zip_resources,
)
from latka_jazn.tools.package_export import _extract_zip_safely


def _archive(entries: list[tuple[str, bytes]], compression=zipfile.ZIP_DEFLATED) -> zipfile.ZipFile:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    buffer.seek(0)
    archive = zipfile.ZipFile(buffer, "r")
    archive._test_buffer = buffer  # type: ignore[attr-defined]
    return archive


def test_normal_zip_passes_resource_validation() -> None:
    with _archive([("a.txt", b"hello"), ("b.txt", b"world")]) as archive:
        report = validate_zip_resources(archive, limits=ZipResourceLimits(max_members=3))
    assert report["member_count"] == 2
    assert report["total_uncompressed_bytes"] == 10


def test_member_count_limit_is_fail_closed() -> None:
    with _archive([("a", b"1"), ("b", b"2")]) as archive:
        with pytest.raises(ZipResourceLimitError, match="zip_member_limit_exceeded"):
            validate_zip_resources(archive, limits=ZipResourceLimits(max_members=1))


def test_single_member_size_limit_is_fail_closed() -> None:
    with _archive([("large.bin", b"12345")], compression=zipfile.ZIP_STORED) as archive:
        with pytest.raises(ZipResourceLimitError, match="zip_member_size_limit_exceeded"):
            validate_zip_resources(
                archive,
                limits=ZipResourceLimits(max_member_uncompressed_bytes=4),
            )


def test_total_size_limit_is_fail_closed() -> None:
    with _archive([("a", b"123"), ("b", b"456")], compression=zipfile.ZIP_STORED) as archive:
        with pytest.raises(ZipResourceLimitError, match="zip_total_size_limit_exceeded"):
            validate_zip_resources(
                archive,
                limits=ZipResourceLimits(max_total_uncompressed_bytes=5),
            )


def test_compression_ratio_limit_is_fail_closed() -> None:
    with _archive([("bomb.txt", b"0" * 50_000)]) as archive:
        with pytest.raises(ZipResourceLimitError, match="zip_compression_ratio_limit_exceeded"):
            validate_zip_resources(
                archive,
                limits=ZipResourceLimits(max_compression_ratio=2.0),
            )


def test_safe_extraction_checks_resources_before_writing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JAZN_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES", "4")
    with _archive([("large.bin", b"12345")], compression=zipfile.ZIP_STORED) as archive:
        with pytest.raises(ZipResourceLimitError):
            _extract_zip_safely(archive, tmp_path)
    assert not (tmp_path / "large.bin").exists()
