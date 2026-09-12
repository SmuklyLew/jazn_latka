from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.archive import (
    ArchiveError,
    ArchiveExtractionService,
    ArchiveSecurityLimits,
    ArchiveWriteEntry,
)


def test_encrypted_7z_requires_password_and_roundtrips(tmp_path: Path) -> None:
    service = ArchiveExtractionService(ArchiveSecurityLimits(require_free_space=False))
    archive = tmp_path / "encrypted.7z"
    password = "fixture-7z-password"

    service.create_archive(
        [ArchiveWriteEntry("memory/private.txt", data=b"private archive fixture")],
        archive,
        archive_format="7z",
        password=password,
        compression_level=6,
    )

    with pytest.raises(ArchiveError, match="password|7z_read_failed"):
        service.inspect(archive)

    inspection = service.inspect(archive, password=password)
    assert inspection.archive_format == "7z"
    assert inspection.encrypted is True

    destination = tmp_path / "out"
    service.extract_source(archive, destination, password=password)
    assert (destination / "memory/private.txt").read_bytes() == b"private archive fixture"
