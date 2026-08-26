from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from latka_jazn.archive import (
    ArchiveError,
    ArchiveExtractionService,
    ArchiveSecurityLimits,
    ArchiveWriteEntry,
    normalize_archive_format,
)


def _service(**kwargs) -> ArchiveExtractionService:
    return ArchiveExtractionService(
        ArchiveSecurityLimits(require_free_space=False, **kwargs)
    )


def test_pyzip_and_pyzipfile_are_zip_aliases() -> None:
    assert normalize_archive_format("pyzip") == "zip"
    assert normalize_archive_format("PyZipFile") == "zip"
    assert normalize_archive_format("zip64") == "zip"


def test_zip64_roundtrip_and_atomic_extract(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Łatka archive roundtrip\n", encoding="utf-8")
    archive = tmp_path / "roundtrip.zip"
    service = _service()
    inspection = service.create_archive(
        [ArchiveWriteEntry("memory/raw/source.txt", source=source)],
        archive,
        archive_format="zip",
    )
    assert inspection.archive_format == "zip"
    destination = tmp_path / "out"
    result = service.extract_source(archive, destination)
    assert result["ok"] is True
    assert (destination / "memory/raw/source.txt").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_zip_traversal_and_casefold_collisions_fail_closed(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", b"x")
    with pytest.raises(ArchiveError, match="unsafe_archive_member"):
        _service().inspect(traversal)

    collision = tmp_path / "collision.zip"
    with zipfile.ZipFile(collision, "w") as archive:
        archive.writestr("A.txt", b"a")
        archive.writestr("a.TXT", b"b")
    with pytest.raises(ArchiveError, match="casefold"):
        _service().inspect(collision)


def test_compression_ratio_limit_rejects_zip_bomb_shape(tmp_path: Path) -> None:
    archive = tmp_path / "ratio.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as value:
        value.writestr("zeros.bin", b"0" * (1024 * 1024))
    with pytest.raises(ArchiveError, match="compression_ratio"):
        _service(max_compression_ratio=5.0).inspect(archive, verify_crc=False)


def _package_set_hash(outputs: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in outputs:
        digest.update(
            f"{item['part_no']}\0{item['filename']}\0{item['size_bytes']}\0{item['sha256']}\n".encode("utf-8")
        )
    return digest.hexdigest()


def test_verified_binary_split_sidecar_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(bytes(range(256)) * 40)
    service = _service()
    logical = tmp_path / "payload.zip"
    service.create_archive([ArchiveWriteEntry("memory/payload.bin", source=source)], logical, archive_format="zip")
    logical_sha = hashlib.sha256(logical.read_bytes()).hexdigest()
    outputs, split_sha = service.split_file(logical, tmp_path, logical.name, 256)
    assert split_sha == logical_sha
    logical.unlink()
    sidecar = {
        "schema_version": "jazn_package_set/v2",
        "package_name": "payload.zip",
        "profile": "memory",
        "archive_format": "binary",
        "container_format": "zip",
        "logical_zip_sha256": logical_sha,
        "logical_archive_sha256": logical_sha,
        "outputs": outputs,
        "package_set_sha256": _package_set_hash(outputs),
        "entries": [
            {
                "path": "memory/payload.bin",
                "size_bytes": source.stat().st_size,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "classification": "memory_file",
            }
        ],
    }
    sidecar_path = tmp_path / "payload.zip.package.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    destination = tmp_path / "extracted"
    result = service.extract_package_sidecar(sidecar_path, destination)
    assert result["ok"] is True
    assert (destination / "memory/payload.bin").read_bytes() == source.read_bytes()


def test_aes_zip_roundtrip_and_auto_detection(tmp_path: Path) -> None:
    service = _service()
    archive = tmp_path / "secret.zip"
    service.create_archive(
        [ArchiveWriteEntry("secret.txt", data=b"classified fixture")],
        archive,
        archive_format="aes_zip",
        password="correct horse battery staple",
        aes_bits=256,
    )
    inspection = service.inspect(archive, password="correct horse battery staple")
    assert inspection.archive_format == "aes_zip"
    assert inspection.encrypted is True
    with pytest.raises(ArchiveError, match="password"):
        service.extract_source(archive, tmp_path / "missing-password")
    service.extract_source(archive, tmp_path / "aes-out", password="correct horse battery staple")
    assert (tmp_path / "aes-out/secret.txt").read_bytes() == b"classified fixture"


def test_7z_roundtrip(tmp_path: Path) -> None:
    service = _service()
    archive = tmp_path / "sample.7z"
    service.create_archive(
        [ArchiveWriteEntry("nested/data.txt", data="zażółć gęślą jaźń".encode("utf-8"))],
        archive,
        archive_format="7z",
        compression_level=6,
    )
    inspection = service.inspect(archive)
    assert inspection.archive_format == "7z"
    service.extract_source(archive, tmp_path / "seven-out")
    assert (tmp_path / "seven-out/nested/data.txt").read_text(encoding="utf-8") == "zażółć gęślą jaźń"
