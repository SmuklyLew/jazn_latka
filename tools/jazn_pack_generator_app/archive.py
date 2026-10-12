from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from threading import Event
from typing import Callable
import zipfile

from .constants import WINDOWS_RESERVED_NAMES
from .errors import PackCancelled, PackIntegrityError, PackSafetyError
from .models import PackPlan, ProgressEvent

ProgressCallback = Callable[[ProgressEvent], None]
_CHUNK_SIZE = 4 * 1024 * 1024


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PackCancelled("Operacja została anulowana.")


def validate_archive_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if "\x00" in normalized:
        raise PackSafetyError("Nazwa wpisu ZIP zawiera znak NUL.")
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized.startswith("/"):
        raise PackSafetyError(f"Bezwzględna ścieżka w archiwum: {name}")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise PackSafetyError(f"Niebezpieczna ścieżka w archiwum: {name}")
    first = path.parts[0]
    if len(first) >= 2 and first[1] == ":" and first[0].isalpha():
        raise PackSafetyError(f"Bezwzględna ścieżka Windows w archiwum: {name}")
    for part in path.parts:
        stem = part.rstrip(" .").split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise PackSafetyError(f"Nazwa zarezerwowana w Windows: {name}")
        if ":" in part:
            raise PackSafetyError(f"Niedozwolony ':' / ADS w nazwie archiwum: {name}")
    return path.as_posix()


def zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def sha256_file(path: Path, *, callback: ProgressCallback | None = None, cancel_event: Event | None = None) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    current = 0
    with path.open("rb") as handle:
        while True:
            _check_cancel(cancel_event)
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            current += len(chunk)
            _emit(callback, ProgressEvent("hash", "Obliczanie SHA-256", current, total, path.name))
    return digest.hexdigest()


def create_zip(
    plan: PackPlan,
    target: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    total = max(1, plan.source_total_size_bytes)
    written = 0
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=plan.request.compression_level,
        allowZip64=True,
        strict_timestamps=False,
    ) as archive:
        for entry in plan.entries:
            _check_cancel(cancel_event)
            arcname = validate_archive_member_name(entry.archive_path.rstrip("/"))
            if entry.is_dir:
                archive.writestr(arcname.rstrip("/") + "/", b"")
                continue
            info = zipfile.ZipInfo.from_file(entry.source, arcname=arcname)
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = plan.request.compression_level  # type: ignore[attr-defined]
            with entry.source.open("rb") as source, archive.open(info, "w", force_zip64=True) as dest:
                while True:
                    _check_cancel(cancel_event)
                    chunk = source.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    dest.write(chunk)
                    written += len(chunk)
                    _emit(
                        callback,
                        ProgressEvent(
                            "archive",
                            "Pakowanie ZIP",
                            min(written, total),
                            total,
                            entry.archive_path,
                        ),
                    )
    verify_zip(target, callback=callback, cancel_event=cancel_event)
    return target


def verify_zip(
    path: Path,
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> dict[str, object]:
    _check_cancel(cancel_event)
    with zipfile.ZipFile(path, "r") as archive:
        seen: dict[str, str] = {}
        infos = archive.infolist()
        for index, info in enumerate(infos, start=1):
            _check_cancel(cancel_event)
            name = validate_archive_member_name(info.filename.rstrip("/"))
            if zipinfo_is_symlink(info):
                raise PackSafetyError(f"ZIP zawiera symlink: {info.filename}")
            key = name.rstrip("/").casefold()
            previous = seen.get(key)
            if previous is not None:
                if previous == name:
                    raise PackSafetyError(f"Duplikat wpisu ZIP: {name!r}")
                raise PackSafetyError(f"Kolizja nazw ZIP: {previous!r} vs {name!r}")
            seen[key] = name
            _emit(callback, ProgressEvent("verify", "Preflight ZIP", index, len(infos), info.filename))
        bad = archive.testzip()
    if bad is not None:
        raise PackIntegrityError(f"CRC ZIP nie zgadza się dla: {bad}")
    return {"ok": True, "member_count": len(infos), "crc": "ok"}


def verify_zip_member_hashes(
    path: Path,
    expected_sha256: dict[str, str],
    *,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> dict[str, object]:
    _check_cancel(cancel_event)
    with zipfile.ZipFile(path, "r") as archive:
        actual_files = {
            info.filename: info
            for info in archive.infolist()
            if not info.is_dir()
        }
        expected_names = set(expected_sha256)
        actual_names = set(actual_files)
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        if missing or unexpected:
            raise PackIntegrityError(
                "Niezgodny zestaw plików ZIP względem manifestu byte-exact: "
                f"missing={missing[:10]}, unexpected={unexpected[:10]}"
            )
        total = len(expected_names)
        for index, name in enumerate(sorted(expected_names), start=1):
            _check_cancel(cancel_event)
            digest = hashlib.sha256()
            with archive.open(actual_files[name], "r") as handle:
                while True:
                    _check_cancel(cancel_event)
                    chunk = handle.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
            observed = digest.hexdigest()
            expected = expected_sha256[name]
            if observed != expected:
                raise PackIntegrityError(
                    f"SHA-256 wpisu ZIP nie zgadza się dla {name}: expected={expected}, observed={observed}"
                )
            _emit(callback, ProgressEvent("verify-hash", "Weryfikacja SHA-256 wpisów ZIP", index, total, name))
    return {
        "ok": True,
        "member_sha256": "ok",
        "member_count": total,
        "byte_exact": True,
    }


def safe_extract_zip(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path:
    verify_zip(source, callback=callback, cancel_event=cancel_event)
    destination = destination.resolve()
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.jazn-extract-", dir=str(parent)))
    committed = False
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            for index, info in enumerate(infos, start=1):
                _check_cancel(cancel_event)
                normalized = validate_archive_member_name(info.filename.rstrip("/"))
                target = (staging / Path(*PurePosixPath(normalized).parts)).resolve()
                try:
                    target.relative_to(staging.resolve())
                except ValueError as exc:
                    raise PackSafetyError(f"Wpis ZIP wychodzi poza katalog docelowy: {info.filename}") from exc
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as src, target.open("wb") as dst:
                        while True:
                            _check_cancel(cancel_event)
                            chunk = src.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            dst.write(chunk)
                _emit(callback, ProgressEvent("extract", "Rozpakowywanie", index, len(infos), info.filename))
        if destination.exists():
            if not overwrite:
                raise PackSafetyError(f"Katalog docelowy już istnieje: {destination}")
            shutil.rmtree(destination)
        staging.replace(destination)
        committed = True
        return destination
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
