from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

from latka_jazn.archive.service import (
    ArchiveExtractionService as _BaseArchiveExtractionService,
    ArchiveWriteEntry,
    _import_py7zr,
    _password_text,
)


class ArchiveExtractionService(_BaseArchiveExtractionService):
    """v16.3.8 backend hardening layered over the shared archive service."""

    @staticmethod
    def _create_7z(
        entries: Sequence[ArchiveWriteEntry],
        output: Path,
        level: int,
        password: str | bytes | None,
    ) -> None:
        py7zr = _import_py7zr()
        text_password = _password_text(password)
        filters = [{"id": py7zr.FILTER_LZMA2, "preset": int(level)}]
        if text_password:
            # An explicit LZMA2 filter suppresses py7zr's implicit encrypted
            # default filter chain. Add the crypto coder explicitly so both
            # file payload and (below) header are protected.
            filters.append({"id": py7zr.FILTER_CRYPTO_AES256_SHA256})

        with tempfile.TemporaryDirectory(prefix="jazn-7z-virtual-") as temp_raw:
            temp = Path(temp_raw)
            with py7zr.SevenZipFile(
                output,
                mode="x",
                filters=filters,
                password=text_password,
                header_encryption=bool(text_password),
            ) as archive:
                for index, entry in enumerate(entries):
                    source = entry.source
                    if source is None:
                        source = temp / f"virtual-{index:08d}.bin"
                        source.write_bytes(entry.data or b"")
                    archive.write(source, arcname=entry.arcname)
