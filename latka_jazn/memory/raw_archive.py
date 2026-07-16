from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import tempfile
from typing import Any, Iterable
import uuid

from latka_jazn.tools.safe_paths import (
    UnsafeRelativePathError,
    resolve_safe_destination,
    validate_safe_relative_path,
)


@dataclass(slots=True, frozen=True)
class RawArchiveSafetyPolicy:
    max_entries: int = 10_000
    max_file_bytes: int = 2 * 1024 * 1024 * 1024
    max_total_bytes: int = 4 * 1024 * 1024 * 1024
    max_compression_ratio: float = 500.0


@dataclass(slots=True, frozen=True)
class RawArchiveEntry:
    filename: str
    compressed_bytes: int | None
    uncompressed_bytes: int
    is_directory: bool
    is_file: bool
    is_symlink: bool = False
    is_hardlink: bool = False
    is_special: bool = False


@dataclass(slots=True)
class RawArchiveReport:
    status: str
    archive: str | None = None
    output: str | None = None
    error: str | None = None
    extractor: str | None = None
    entry_count: int = 0
    total_uncompressed_bytes: int = 0
    selected_html: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RawArchiveSafetyError(ValueError):
    pass


def find_chat_archive(root: Path) -> Path | None:
    root = Path(root)
    candidates = [
        root / "chat.html.7z",
        root / "memory" / "raw" / "chat.html.7z",
        root.parent / "chat.html.7z",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def py7zr_available() -> bool:
    return importlib.util.find_spec("py7zr") is not None


def system_7z_executable() -> str | None:
    for executable in ("7z", "7za", "7zr"):
        found = shutil.which(executable)
        if found:
            return found
    return None


def chat_archive_diagnostics(root: Path) -> dict[str, Any]:
    root = Path(root)
    chat = root / "memory" / "raw" / "chat.html"
    archive = find_chat_archive(root)
    seven_zip = system_7z_executable()
    return {
        "chat_html_present": chat.exists(),
        "chat_html_path": str(chat),
        "chat_html_size_bytes": chat.stat().st_size if chat.exists() else 0,
        "archive_present": archive is not None,
        "archive_path": str(archive) if archive else None,
        "archive_size_bytes": archive.stat().st_size if archive else 0,
        "py7zr_available": py7zr_available(),
        "system_7z": seven_zip,
        "can_unpack": bool(chat.exists() or (archive and (py7zr_available() or seven_zip))),
    }


def _canonical_entry_name(filename: str, *, is_directory: bool) -> str:
    value = str(filename or "")
    if is_directory and value.endswith("/"):
        value = value[:-1]
    try:
        return validate_safe_relative_path(value)
    except UnsafeRelativePathError as exc:
        raise RawArchiveSafetyError(f"unsafe archive path {filename!r}: {exc}") from exc


def _list_py7zr(archive: Path) -> list[RawArchiveEntry]:
    import py7zr  # type: ignore

    with py7zr.SevenZipFile(archive, "r") as handle:
        return [
            RawArchiveEntry(
                filename=str(item.filename),
                compressed_bytes=(int(item.compressed) if item.compressed is not None else None),
                uncompressed_bytes=int(item.uncompressed),
                is_directory=bool(item.is_directory),
                is_file=bool(item.is_file),
                is_symlink=bool(item.is_symlink),
                is_special=not bool(item.is_directory or item.is_file or item.is_symlink),
            )
            for item in handle.list()
        ]


def _parse_7z_slt(text: str) -> list[RawArchiveEntry]:
    records: list[dict[str, str]] = []
    record: dict[str, str] = {}
    in_entries = False
    for line in text.splitlines():
        if line.startswith("----------"):
            if record:
                records.append(record)
                record = {}
            in_entries = True
            continue
        if not in_entries:
            continue
        if not line.strip():
            if record:
                records.append(record)
                record = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            record[key.strip()] = value.strip()
    if record:
        records.append(record)

    entries: list[RawArchiveEntry] = []
    for item in records:
        filename = item.get("Path", "")
        attributes = item.get("Attributes", "")
        is_directory = attributes.startswith("D") or item.get("Folder") == "+"
        symlink = bool(item.get("Symbolic Link")) or "L" in attributes
        hardlink = bool(item.get("Hard Link"))
        size = int(item.get("Size") or 0)
        packed = int(item["Packed Size"]) if item.get("Packed Size", "").isdigit() else None
        entries.append(RawArchiveEntry(
            filename=filename,
            compressed_bytes=packed,
            uncompressed_bytes=size,
            is_directory=is_directory,
            is_file=not is_directory and not symlink and not hardlink,
            is_symlink=symlink,
            is_hardlink=hardlink,
            is_special=not is_directory and not symlink and not hardlink and "A" not in attributes,
        ))
    return entries


def _list_cli(archive: Path, executable: str) -> list[RawArchiveEntry]:
    completed = subprocess.run(
        [executable, "l", "-slt", str(archive)],
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RawArchiveSafetyError(f"7z listing failed ({completed.returncode}): {completed.stderr[-1000:]}")
    entries = _parse_7z_slt(completed.stdout)
    if not entries:
        raise RawArchiveSafetyError("7z listing returned no archive entries")
    return entries


def _validate_entries(
    archive: Path,
    entries: Iterable[RawArchiveEntry],
    policy: RawArchiveSafetyPolicy,
) -> tuple[list[RawArchiveEntry], str, int]:
    listed = list(entries)
    if not listed:
        raise RawArchiveSafetyError("archive is empty")
    if len(listed) > policy.max_entries:
        raise RawArchiveSafetyError("archive entry count exceeds limit")

    total = 0
    html: list[str] = []
    seen: set[str] = set()
    for entry in listed:
        canonical = _canonical_entry_name(entry.filename, is_directory=entry.is_directory)
        if canonical in seen:
            raise RawArchiveSafetyError(f"duplicate archive entry: {canonical}")
        seen.add(canonical)
        if entry.is_symlink or entry.is_hardlink or entry.is_special:
            raise RawArchiveSafetyError(f"links and special entries are forbidden: {canonical}")
        if not entry.is_directory and not entry.is_file:
            raise RawArchiveSafetyError(f"unknown archive entry type: {canonical}")
        if entry.uncompressed_bytes < 0 or entry.uncompressed_bytes > policy.max_file_bytes:
            raise RawArchiveSafetyError(f"archive entry exceeds file size limit: {canonical}")
        total += entry.uncompressed_bytes
        if total > policy.max_total_bytes:
            raise RawArchiveSafetyError("archive total uncompressed size exceeds limit")
        if entry.uncompressed_bytes and entry.compressed_bytes is not None:
            if entry.compressed_bytes <= 0:
                raise RawArchiveSafetyError(f"archive entry compression ratio is unbounded: {canonical}")
            if entry.uncompressed_bytes / entry.compressed_bytes > policy.max_compression_ratio:
                raise RawArchiveSafetyError(f"archive entry compression ratio exceeds limit: {canonical}")
        if entry.is_file and canonical.lower().endswith(".html"):
            html.append(canonical)

    archive_bytes = max(1, archive.stat().st_size)
    if total / archive_bytes > policy.max_compression_ratio:
        raise RawArchiveSafetyError("archive aggregate compression ratio exceeds limit")
    if len(html) != 1:
        raise RawArchiveSafetyError(
            "archive must contain exactly one HTML file" if html else "archive contains no HTML file"
        )
    return listed, html[0], total


def _extract_selected_py7zr(archive: Path, staging: Path, selected: str) -> None:
    import py7zr  # type: ignore

    with py7zr.SevenZipFile(archive, "r") as handle:
        handle.extract(path=staging, targets=[selected])


def _extract_selected_cli(archive: Path, staging: Path, selected: str, executable: str) -> None:
    completed = subprocess.run(
        [executable, "x", str(archive), f"-o{staging}", "-y", "--", selected],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RawArchiveSafetyError(f"7z extraction failed ({completed.returncode})")


def _validate_staging(staging: Path, selected: str, expected_size: int) -> Path:
    staging_root = staging.resolve()
    selected_path = resolve_safe_destination(staging_root, selected)
    for path in staging.rglob("*"):
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(staging_root)
        except ValueError as exc:
            raise RawArchiveSafetyError(f"extracted path escapes staging: {path}") from exc
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or (callable(is_junction) and is_junction()):
            raise RawArchiveSafetyError(f"extracted link is forbidden: {path}")
        if path.is_file() and resolved != selected_path:
            raise RawArchiveSafetyError(f"unexpected extracted file: {path}")
    if not selected_path.is_file():
        raise RawArchiveSafetyError("selected HTML was not extracted")
    if selected_path.stat().st_size != expected_size:
        raise RawArchiveSafetyError("extracted HTML size differs from archive listing")
    return selected_path


def unpack_chat_html_archive(
    root: Path,
    *,
    overwrite: bool = False,
    policy: RawArchiveSafetyPolicy | None = None,
) -> RawArchiveReport:
    root = Path(root)
    out_dir = root / "memory" / "raw"
    out_path = out_dir / "chat.html"
    if out_path.exists() and not overwrite:
        return RawArchiveReport("already_present", output=str(out_path))
    archive = find_chat_archive(root)
    if archive is None:
        return RawArchiveReport(
            "missing_archive",
            output=str(out_path),
            error="Nie znaleziono chat.html.7z w root, memory/raw ani katalogu nadrzędnym root.",
        )

    active_policy = policy or RawArchiveSafetyPolicy()
    extractor: str | None = None
    try:
        if py7zr_available():
            entries = _list_py7zr(archive)
            extractor = "python:py7zr"
        else:
            executable = system_7z_executable()
            if executable is None:
                return RawArchiveReport(
                    "missing_safe_extractor",
                    archive=str(archive),
                    output=str(out_path),
                    error="Brak py7zr i systemowego 7z/7za/7zr potrzebnego do bezpiecznego listowania archiwum.",
                )
            entries = _list_cli(archive, executable)
            extractor = f"cli:{Path(executable).name}"
        listed, selected, total = _validate_entries(archive, entries, active_policy)
        expected = next(
            item.uncompressed_bytes
            for item in listed
            if _canonical_entry_name(item.filename, is_directory=item.is_directory) == selected
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        final_temp = out_dir / f".chat.html.{uuid.uuid4().hex}.tmp"
        try:
            with tempfile.TemporaryDirectory(prefix=".chat-html-staging-", dir=out_dir) as temp_name:
                staging = Path(temp_name)
                if extractor == "python:py7zr":
                    _extract_selected_py7zr(archive, staging, selected)
                else:
                    executable = system_7z_executable()
                    if executable is None:
                        raise RawArchiveSafetyError("validated 7z executable became unavailable")
                    _extract_selected_cli(archive, staging, selected, executable)
                extracted = _validate_staging(staging, selected, expected)
                with extracted.open("rb") as source, final_temp.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                if final_temp.stat().st_size != expected:
                    raise RawArchiveSafetyError("staged HTML size changed before atomic move")
                os.replace(final_temp, out_path)
        finally:
            final_temp.unlink(missing_ok=True)
        return RawArchiveReport(
            "unpacked",
            archive=str(archive),
            output=str(out_path),
            extractor=extractor,
            entry_count=len(listed),
            total_uncompressed_bytes=total,
            selected_html=selected,
        )
    except Exception as exc:
        return RawArchiveReport(
            "validation_failed",
            archive=str(archive),
            output=str(out_path),
            extractor=extractor,
            error=f"{type(exc).__name__}: {exc}",
        )
