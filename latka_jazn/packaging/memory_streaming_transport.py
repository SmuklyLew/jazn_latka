from __future__ import annotations

"""Low-amplification MEMORY transport verification and extraction.

This module is deliberately limited to package transport/install concerns. It
keeps the existing fail-closed integrity model, but avoids creating a second
copy of uploaded parts, a joined logical ZIP, or a runtime v3 repack merely to
attach MEMORY.

The install form may differ from the transport form for v3 raw JSONL segments:
segments are verified while being streamed directly into the original logical
JSONL file. No segment files need to be materialized on disk.
"""

import bisect
import hashlib
import io
import json
import os
import re
import shutil
import stat
import time
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationState,
    probe_attachment_materialization,
)
from latka_jazn.packaging.memory_package_types import (
    MEMORY_MANIFEST_SCHEMA_V3,
    MEMORY_PACKAGE_MANIFEST_PATH,
)
from latka_jazn.packaging.split_zip_package import (
    CHUNK_SIZE,
    PackagePartExpectation,
    load_package_expectations,
    load_package_set_metadata,
    unsafe_zip_member_name,
)

_PROGRESS_SCHEMA = "jazn_memory_streaming_extract_progress/v1"
_MIN_FREE_RESERVE = 64 * 1024 * 1024
_MAX_FREE_RESERVE = 512 * 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MemoryStreamingTransportError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedTransportPart:
    part_no: int
    expected_name: str
    source_path: Path
    size_bytes: int
    sha256: str
    mtime_ns: int


class SplitZipReader(io.RawIOBase):
    """Seekable read-only logical view over binary split ZIP parts."""

    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        if not paths:
            raise ValueError("split ZIP reader requires at least one part")
        self._paths = [Path(path).expanduser().resolve() for path in paths]
        self._handles = [path.open("rb") for path in self._paths]
        self._sizes: list[int] = []
        self._mtimes: list[int] = []
        self._ends: list[int] = []
        total = 0
        for handle in self._handles:
            state = os.fstat(handle.fileno())
            size = int(state.st_size)
            self._sizes.append(size)
            self._mtimes.append(int(state.st_mtime_ns))
            total += size
            self._ends.append(total)
        self._length = total
        self._position = 0

    @property
    def length(self) -> int:
        return self._length

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = int(offset)
        elif whence == io.SEEK_CUR:
            position = self._position + int(offset)
        elif whence == io.SEEK_END:
            position = self._length + int(offset)
        else:
            raise ValueError(f"unsupported whence: {whence}")
        if position < 0:
            raise ValueError("negative seek position")
        self._position = min(position, self._length)
        return self._position

    def readinto(self, buffer: bytearray | memoryview) -> int:
        if self._position >= self._length:
            return 0
        view = memoryview(buffer).cast("B")
        written = 0
        while written < len(view) and self._position < self._length:
            index = bisect.bisect_right(self._ends, self._position)
            part_start = 0 if index == 0 else self._ends[index - 1]
            local_offset = self._position - part_start
            available = self._sizes[index] - local_offset
            wanted = min(len(view) - written, available)
            handle = self._handles[index]
            handle.seek(local_offset)
            chunk = handle.read(wanted)
            if not chunk:
                break
            view[written : written + len(chunk)] = chunk
            written += len(chunk)
            self._position += len(chunk)
        return written

    def assert_stable(self) -> None:
        for path, handle, size, mtime_ns in zip(
            self._paths,
            self._handles,
            self._sizes,
            self._mtimes,
            strict=True,
        ):
            state = os.fstat(handle.fileno())
            if int(state.st_size) != size or int(state.st_mtime_ns) != mtime_ns:
                raise MemoryStreamingTransportError(
                    f"verified transport changed during read: {path.name}"
                )

    def close(self) -> None:
        if not self.closed:
            for handle in self._handles:
                try:
                    handle.close()
                except OSError:
                    pass
        super().close()


def _safe_flat_filename(value: str) -> str:
    raw = str(value or "").strip()
    if (
        not raw
        or raw in {".", ".."}
        or "\x00" in raw
        or "/" in raw
        or "\\" in raw
        or Path(raw).name != raw
    ):
        raise MemoryStreamingTransportError(f"unsafe package part filename: {value!r}")
    return raw


def _safe_memory_path(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    reason = unsafe_zip_member_name(text)
    if reason:
        raise MemoryStreamingTransportError(f"unsafe MEMORY member {value!r}: {reason}")
    path = PurePosixPath(text)
    if not text or text.endswith("/") or not path.parts or path.parts[0] != "memory":
        raise MemoryStreamingTransportError(f"MEMORY member outside memory/: {value!r}")
    return path.as_posix()


def _part_suffix_number(path: Path) -> int | None:
    match = re.search(r"\.(\d{3})$", path.name)
    return int(match.group(1)) if match else None


def _expectations_from_sidecar(
    sidecar: Mapping[str, Any],
) -> tuple[list[PackagePartExpectation], str | None]:
    rows = sidecar.get("outputs")
    if not isinstance(rows, list) or not rows:
        raise MemoryStreamingTransportError("MEMORY sidecar has no outputs")
    expected: list[PackagePartExpectation] = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, Mapping):
            raise MemoryStreamingTransportError("invalid MEMORY sidecar output record")
        filename = _safe_flat_filename(str(raw.get("filename") or ""))
        expected.append(
            PackagePartExpectation(
                part_no=int(raw.get("part_no") or index),
                filename=filename,
                size_bytes=(
                    int(raw["size_bytes"])
                    if raw.get("size_bytes") is not None
                    else None
                ),
                sha256=str(raw.get("sha256") or "").strip().lower() or None,
            )
        )
    expected.sort(key=lambda item: item.part_no)
    full_sha = str(sidecar.get("logical_zip_sha256") or "").strip().lower() or None
    return expected, full_sha


def resolve_verified_parts_in_place(
    parts_dir: Path,
    expected: list[PackagePartExpectation],
) -> tuple[list[VerifiedTransportPart], dict[str, Any]]:
    """Resolve host-renamed parts after a stable full read, without copying."""

    directory = Path(parts_dir).expanduser().resolve()
    all_files = [path for path in directory.iterdir() if path.is_file()]
    numbered = [path for path in all_files if _part_suffix_number(path) is not None]
    used: set[Path] = set()
    resolved: list[VerifiedTransportPart] = []
    rows: list[dict[str, Any]] = []

    for part in expected:
        filename = _safe_flat_filename(part.filename)
        exact = directory / filename
        candidates = [exact] if exact.is_file() else []
        candidates.extend(
            path
            for path in numbered
            if path != exact and _part_suffix_number(path) == int(part.part_no)
        )
        if not exact.is_file() and part.size_bytes is not None and part.sha256:
            candidates.extend(
                path
                for path in all_files
                if path != exact
                and path not in candidates
                and path.suffix.lower() in {".zip", f".{int(part.part_no):03d}"}
            )

        matches: list[tuple[Path, Any]] = []
        rejected: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate in used:
                continue
            probe = probe_attachment_materialization(
                candidate,
                expected_size_bytes=part.size_bytes,
                expected_sha256=part.sha256,
                chunk_size=CHUNK_SIZE,
            )
            if probe.state is not AttachmentMaterializationState.READY:
                rejected.append(probe.to_dict())
                continue
            matches.append((candidate.resolve(), probe))

        if not matches:
            raise FileNotFoundError(
                f"no stable verified MEMORY part {part.part_no:03d} ({filename}); "
                f"rejected={rejected}"
            )
        if len(matches) > 1:
            exact_matches = [item for item in matches if item[0] == exact.resolve()]
            if len(exact_matches) == 1:
                matches = exact_matches
            else:
                raise MemoryStreamingTransportError(
                    f"ambiguous MEMORY part {part.part_no:03d}: "
                    + ", ".join(str(path) for path, _probe in matches)
                )

        source, probe = matches[0]
        used.add(source)
        state = source.stat()
        digest = str(probe.observed_sha256 or "").lower()
        if not _SHA256_RE.fullmatch(digest):
            raise MemoryStreamingTransportError(
                f"verified MEMORY part has no valid SHA-256: {source.name}"
            )
        item = VerifiedTransportPart(
            part_no=int(part.part_no),
            expected_name=filename,
            source_path=source,
            size_bytes=int(state.st_size),
            sha256=digest,
            mtime_ns=int(state.st_mtime_ns),
        )
        resolved.append(item)
        rows.append(
            {
                "part_no": item.part_no,
                "expected_name": item.expected_name,
                "source_name": source.name,
                "source_path": str(source),
                "renamed_by_host": source.name != item.expected_name,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "source_mtime_ns": item.mtime_ns,
                "materialization": "in_place_verified_no_copy",
                "stable_during_read": True,
            }
        )

    return resolved, {
        "ok": True,
        "parts_dir": str(directory),
        "parts_count": len(rows),
        "renamed_parts_count": sum(1 for row in rows if row["renamed_by_host"]),
        "bytes_copied": 0,
        "resolved_parts": rows,
        "truth_boundary": (
            "Each upload part was accepted only after a stable full size/SHA read. "
            "The runtime consumes those verified files in place and never creates "
            "a second canonical_parts copy."
        ),
    }


def _logical_sha256(parts: list[VerifiedTransportPart]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        with part.source_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _entry_inventory(sidecar: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = sidecar.get("entries")
    if not isinstance(rows, list) or not rows:
        raise MemoryStreamingTransportError("MEMORY sidecar has no file entry inventory")
    inventory: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise MemoryStreamingTransportError("invalid MEMORY sidecar entry")
        relative = _safe_memory_path(str(raw.get("path") or ""))
        if relative in inventory:
            raise MemoryStreamingTransportError(f"duplicate MEMORY sidecar entry: {relative}")
        size = int(raw.get("size_bytes", -1))
        digest = str(raw.get("sha256") or "").strip().lower()
        if size < 0 or not _SHA256_RE.fullmatch(digest):
            raise MemoryStreamingTransportError(
                f"MEMORY sidecar entry requires exact size/SHA-256: {relative}"
            )
        inventory[relative] = {
            **dict(raw),
            "path": relative,
            "size_bytes": size,
            "sha256": digest,
        }
    return inventory


class _ArchiveSet:
    def __init__(self, parts: list[VerifiedTransportPart], archive_format: str) -> None:
        self.parts = parts
        self.archive_format = archive_format
        self._raw: SplitZipReader | None = None
        self._buffered: io.BufferedReader | None = None
        self._handles: list[io.BufferedReader] = []
        self.archives: list[zipfile.ZipFile] = []

    def __enter__(self) -> "_ArchiveSet":
        if self.archive_format == "binary":
            self._raw = SplitZipReader([part.source_path for part in self.parts])
            self._buffered = io.BufferedReader(self._raw, buffer_size=CHUNK_SIZE)
            self.archives = [zipfile.ZipFile(self._buffered, "r")]
        elif self.archive_format == "independent":
            for part in self.parts:
                handle = part.source_path.open("rb")
                self._handles.append(handle)
                self.archives.append(zipfile.ZipFile(handle, "r"))
        else:
            raise MemoryStreamingTransportError(
                f"unsupported MEMORY archive_format: {self.archive_format!r}"
            )
        return self

    def assert_stable(self) -> None:
        if self._raw is not None:
            self._raw.assert_stable()
        for part, handle in zip(self.parts, self._handles, strict=False):
            state = os.fstat(handle.fileno())
            if (
                int(state.st_size) != part.size_bytes
                or int(state.st_mtime_ns) != part.mtime_ns
            ):
                raise MemoryStreamingTransportError(
                    f"verified transport changed during read: {part.source_path.name}"
                )

    def close(self) -> None:
        for archive in self.archives:
            try:
                archive.close()
            except Exception:
                pass
        self.archives = []
        if self._buffered is not None:
            try:
                self._buffered.close()
            except OSError:
                pass
            self._buffered = None
        elif self._raw is not None:
            self._raw.close()
        self._raw = None
        for handle in self._handles:
            try:
                handle.close()
            except OSError:
                pass
        self._handles = []

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if exc_type is None:
                self.assert_stable()
        finally:
            self.close()


def _member_map(
    archives: list[zipfile.ZipFile],
    inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[zipfile.ZipFile, zipfile.ZipInfo]]:
    members: dict[str, tuple[zipfile.ZipFile, zipfile.ZipInfo]] = {}
    files: set[str] = set()
    directories: set[str] = set()

    for archive in archives:
        for info in archive.infolist():
            reason = unsafe_zip_member_name(info.filename)
            if reason:
                raise MemoryStreamingTransportError(
                    f"unsafe ZIP member {info.filename!r}: {reason}"
                )
            relative = info.filename.rstrip("/")
            if not relative:
                continue
            unix_type = (int(info.external_attr) >> 16) & 0o170000
            if unix_type == stat.S_IFLNK:
                raise MemoryStreamingTransportError(
                    f"MEMORY ZIP symbolic link rejected: {relative}"
                )
            if info.is_dir():
                directories.add(relative)
                continue
            relative = _safe_memory_path(relative)
            if relative in members:
                raise MemoryStreamingTransportError(
                    f"duplicate MEMORY ZIP member across volumes: {relative}"
                )
            expected = inventory.get(relative)
            if expected is None:
                raise MemoryStreamingTransportError(
                    f"MEMORY ZIP member missing from sidecar inventory: {relative}"
                )
            if int(info.file_size) != int(expected["size_bytes"]):
                raise MemoryStreamingTransportError(
                    f"MEMORY ZIP central-directory size mismatch: {relative}"
                )
            members[relative] = (archive, info)
            files.add(relative)

    missing = sorted(set(inventory) - set(members))
    if missing:
        raise MemoryStreamingTransportError(
            f"MEMORY sidecar entries missing from ZIP: {missing[:20]}"
        )

    for file_name in sorted(files):
        if file_name in directories:
            raise MemoryStreamingTransportError(
                f"MEMORY ZIP file-directory collision: {file_name}"
            )
        parts = PurePosixPath(file_name).parts
        for index in range(1, len(parts)):
            parent = PurePosixPath(*parts[:index]).as_posix()
            if parent in files:
                raise MemoryStreamingTransportError(
                    f"MEMORY ZIP parent path is a file: {file_name} -> {parent}"
                )
    return members


def _crc_and_sha_stream(
    source: Any,
    target: Any | None,
) -> tuple[int, str, int, int, bytes]:
    crc = 0
    digest = hashlib.sha256()
    size = 0
    newline_count = 0
    last_byte = b""
    while True:
        chunk = source.read(CHUNK_SIZE)
        if not chunk:
            break
        if target is not None:
            target.write(chunk)
        crc = zlib.crc32(chunk, crc)
        digest.update(chunk)
        size += len(chunk)
        newline_count += chunk.count(b"\n")
        last_byte = chunk[-1:]
    return crc & 0xFFFFFFFF, digest.hexdigest(), size, newline_count, last_byte


def _verify_member_result(
    relative: str,
    info: zipfile.ZipInfo,
    expected: Mapping[str, Any],
    *,
    crc: int,
    digest: str,
    size: int,
) -> None:
    if size != int(info.file_size) or size != int(expected["size_bytes"]):
        raise MemoryStreamingTransportError(f"MEMORY member size mismatch: {relative}")
    if digest != str(expected["sha256"]):
        raise MemoryStreamingTransportError(f"MEMORY member SHA-256 mismatch: {relative}")
    if crc != int(info.CRC):
        raise MemoryStreamingTransportError(f"MEMORY member CRC mismatch: {relative}")


def _read_manifest(
    members: Mapping[str, tuple[zipfile.ZipFile, zipfile.ZipInfo]],
    inventory: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    member = members.get(MEMORY_PACKAGE_MANIFEST_PATH)
    if member is None:
        raise MemoryStreamingTransportError("MEMORY package manifest is missing")
    archive, info = member
    if int(info.file_size) > _MAX_MANIFEST_BYTES:
        raise MemoryStreamingTransportError("MEMORY package manifest exceeds metadata limit")
    with archive.open(info, "r") as source:
        payload = source.read(_MAX_MANIFEST_BYTES + 1)
    if len(payload) > _MAX_MANIFEST_BYTES:
        raise MemoryStreamingTransportError("MEMORY package manifest exceeds metadata limit")
    expected = inventory[MEMORY_PACKAGE_MANIFEST_PATH]
    digest = hashlib.sha256(payload).hexdigest()
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    _verify_member_result(
        MEMORY_PACKAGE_MANIFEST_PATH,
        info,
        expected,
        crc=crc,
        digest=digest,
        size=len(payload),
    )
    try:
        decoded = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MemoryStreamingTransportError(
            f"invalid MEMORY package manifest JSON: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise MemoryStreamingTransportError("MEMORY package manifest must be an object")
    return decoded


def _raw_descriptor_maps(
    manifest: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if str(manifest.get("schema_version") or "") != MEMORY_MANIFEST_SCHEMA_V3:
        return {}, set()
    raw = manifest.get("raw_segments")
    if not isinstance(raw, list):
        raise MemoryStreamingTransportError("v3 MEMORY manifest raw_segments must be a list")
    by_source: dict[str, dict[str, Any]] = {}
    segment_paths: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise MemoryStreamingTransportError("invalid v3 raw segment descriptor")
        descriptor = dict(item)
        source_path = _safe_memory_path(str(descriptor.get("source_path") or ""))
        if source_path in by_source:
            raise MemoryStreamingTransportError(
                f"duplicate v3 raw segment source: {source_path}"
            )
        segments = descriptor.get("segments")
        if not isinstance(segments, list) or not segments:
            raise MemoryStreamingTransportError(
                f"v3 raw segment descriptor has no segments: {source_path}"
            )
        expected_index = 1
        for raw_segment in segments:
            if not isinstance(raw_segment, Mapping):
                raise MemoryStreamingTransportError(
                    f"invalid v3 raw segment record: {source_path}"
                )
            index = int(raw_segment.get("segment_index") or 0)
            if index != expected_index:
                raise MemoryStreamingTransportError(
                    f"v3 raw segment sequence gap for {source_path}: "
                    f"expected {expected_index}, got {index}"
                )
            segment_path = _safe_memory_path(
                str(raw_segment.get("package_path") or "")
            )
            if segment_path in segment_paths:
                raise MemoryStreamingTransportError(
                    f"duplicate v3 raw segment path: {segment_path}"
                )
            segment_paths.add(segment_path)
            expected_index += 1
        if source_path in segment_paths:
            raise MemoryStreamingTransportError(
                f"v3 raw source collides with transport segment: {source_path}"
            )
        by_source[source_path] = descriptor
    return by_source, segment_paths


def _target_for(staging: Path, relative: str) -> Path:
    root = staging.resolve()
    target = (root / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MemoryStreamingTransportError(
            f"MEMORY target escapes staging root: {relative}"
        ) from exc
    return target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _existing_matches(path: Path, *, size: int, sha256: str) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(size)
        and _sha256_file(path) == str(sha256).lower()
    )


def _write_member(
    relative: str,
    member: tuple[zipfile.ZipFile, zipfile.ZipInfo],
    expected: Mapping[str, Any],
    staging: Path,
) -> None:
    archive, info = member
    target = _target_for(staging, relative)
    if _existing_matches(
        target,
        size=int(expected["size_bytes"]),
        sha256=str(expected["sha256"]),
    ):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        with archive.open(info, "r") as source, partial.open("xb") as output:
            crc, digest, size, _newlines, _last = _crc_and_sha_stream(source, output)
            output.flush()
            os.fsync(output.fileno())
        _verify_member_result(
            relative,
            info,
            expected,
            crc=crc,
            digest=digest,
            size=size,
        )
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _stream_raw_descriptor(
    descriptor: Mapping[str, Any],
    members: Mapping[str, tuple[zipfile.ZipFile, zipfile.ZipInfo]],
    inventory: Mapping[str, Mapping[str, Any]],
    staging: Path,
) -> None:
    source_path = _safe_memory_path(str(descriptor.get("source_path") or ""))
    source_size_expected = int(descriptor.get("source_size_bytes", -1))
    source_sha_expected = str(descriptor.get("source_sha256") or "").strip().lower()
    source_lines_expected = int(descriptor.get("source_line_count", -1))
    if (
        source_size_expected < 0
        or source_lines_expected < 0
        or not _SHA256_RE.fullmatch(source_sha_expected)
    ):
        raise MemoryStreamingTransportError(
            f"invalid v3 raw source metadata: {source_path}"
        )
    target = _target_for(staging, source_path)
    if _existing_matches(
        target,
        size=source_size_expected,
        sha256=source_sha_expected,
    ):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)

    source_digest = hashlib.sha256()
    source_size = 0
    source_lines = 0
    expected_index = 1
    try:
        with partial.open("xb") as output:
            for raw_segment in descriptor.get("segments") or []:
                if not isinstance(raw_segment, Mapping):
                    raise MemoryStreamingTransportError(
                        f"invalid v3 raw segment record: {source_path}"
                    )
                index = int(raw_segment.get("segment_index") or 0)
                if index != expected_index:
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment sequence gap for {source_path}"
                    )
                segment_path = _safe_memory_path(
                    str(raw_segment.get("package_path") or "")
                )
                member = members.get(segment_path)
                expected = inventory.get(segment_path)
                if member is None or expected is None:
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment missing: {segment_path}"
                    )
                archive, info = member
                segment_digest = hashlib.sha256()
                segment_crc = 0
                segment_size = 0
                newline_count = 0
                last_byte = b""
                with archive.open(info, "r") as source:
                    while True:
                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        source_digest.update(chunk)
                        segment_digest.update(chunk)
                        segment_crc = zlib.crc32(chunk, segment_crc)
                        segment_size += len(chunk)
                        source_size += len(chunk)
                        newline_count += chunk.count(b"\n")
                        if chunk:
                            last_byte = chunk[-1:]
                segment_crc &= 0xFFFFFFFF
                segment_lines = newline_count + (
                    1 if segment_size and last_byte != b"\n" else 0
                )
                source_lines += segment_lines
                _verify_member_result(
                    segment_path,
                    info,
                    expected,
                    crc=segment_crc,
                    digest=segment_digest.hexdigest(),
                    size=segment_size,
                )
                if segment_size != int(raw_segment.get("size_bytes", -1)):
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment descriptor size mismatch: {segment_path}"
                    )
                if segment_digest.hexdigest() != str(
                    raw_segment.get("sha256") or ""
                ).strip().lower():
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment descriptor SHA mismatch: {segment_path}"
                    )
                if segment_lines != int(raw_segment.get("line_count", -1)):
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment line-count mismatch: {segment_path}"
                    )
                first_line = int(raw_segment.get("first_line_number", -1))
                last_line = int(raw_segment.get("last_line_number", -1))
                if (
                    first_line != source_lines - segment_lines + 1
                    or last_line != source_lines
                ):
                    raise MemoryStreamingTransportError(
                        f"v3 raw segment line-range mismatch: {segment_path}"
                    )
                expected_index += 1
            output.flush()
            os.fsync(output.fileno())

        if source_size != source_size_expected:
            raise MemoryStreamingTransportError(
                f"v3 raw source size mismatch: {source_path}"
            )
        if source_digest.hexdigest() != source_sha_expected:
            raise MemoryStreamingTransportError(
                f"v3 raw source SHA mismatch: {source_path}"
            )
        if source_lines != source_lines_expected:
            raise MemoryStreamingTransportError(
                f"v3 raw source line-count mismatch: {source_path}"
            )
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _load_progress(path: Path, package_key: str) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("package_key") != package_key:
        return {}
    raw = payload.get("completed")
    return dict(raw) if isinstance(raw, dict) else {}


def _write_progress(
    path: Path,
    *,
    package_key: str,
    state: str,
    completed: Mapping[str, Any],
    staging: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _PROGRESS_SCHEMA,
        "package_key": package_key,
        "state": state,
        "staging": str(staging),
        "completed": dict(completed),
        "completed_count": len(completed),
        "updated_at_epoch": time.time(),
    }
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _directory_payload_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.name.endswith(".partial"):
            try:
                total += int(path.stat().st_size)
            except FileNotFoundError:
                continue
    return total


def _disk_preflight(
    parent: Path,
    staging: Path,
    *,
    expected_payload_bytes: int,
) -> dict[str, Any]:
    parent.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(parent)
    existing = min(
        max(0, _directory_payload_bytes(staging)),
        max(0, expected_payload_bytes),
    )
    remaining = max(0, expected_payload_bytes - existing)
    reserve = max(
        _MIN_FREE_RESERVE,
        min(_MAX_FREE_RESERVE, max(0, expected_payload_bytes // 50)),
    )
    required_free = remaining + reserve
    report = {
        "ok": int(usage.free) >= required_free,
        "filesystem_path": str(parent),
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "expected_payload_bytes": int(expected_payload_bytes),
        "existing_payload_bytes": int(existing),
        "remaining_payload_bytes": int(remaining),
        "reserve_bytes": int(reserve),
        "required_free_bytes": int(required_free),
    }
    if not report["ok"]:
        raise MemoryStreamingTransportError(
            "insufficient_disk_space:"
            f"free={usage.free},required={required_free},payload={expected_payload_bytes}"
        )
    return report


def _package_key(
    zip_name: str,
    sidecar: Mapping[str, Any],
    expected_full_sha: str | None,
) -> str:
    seed = (
        expected_full_sha
        or str(sidecar.get("package_set_sha256") or "").strip().lower()
        or hashlib.sha256(
            json.dumps(
                {
                    "package_name": zip_name,
                    "outputs": sidecar.get("outputs"),
                    "entries": sidecar.get("entries"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    safe_seed = re.sub(r"[^0-9a-zA-Z_-]", "", seed)[:32]
    return safe_seed or hashlib.sha256(zip_name.encode("utf-8")).hexdigest()[:32]


def stream_extract_verified_memory_package(
    runtime_root: Path,
    parts_dir: Path,
    *,
    target_memory_root: Path,
    base_zip_name: str,
    package_sidecar: Mapping[str, Any] | None = None,
    time_budget_seconds: float | None = None,
    force_reextract: bool = False,
) -> dict[str, Any]:
    """Verify and extract MEMORY with one payload copy on the target filesystem."""

    runtime_root = Path(runtime_root).expanduser().resolve()
    parts_dir = Path(parts_dir).expanduser().resolve()
    target_memory_root = Path(target_memory_root).expanduser().resolve()
    zip_name = _safe_flat_filename(base_zip_name)

    if package_sidecar is None:
        package_set = load_package_set_metadata(parts_dir, zip_name)
        if (
            package_set.get("source") != "package.json"
            or str(package_set.get("profile") or "").strip().lower() != "memory"
        ):
            raise MemoryStreamingTransportError("MEMORY package profile rejected")
        expected, expected_full_sha, expectations_source = load_package_expectations(
            parts_dir,
            zip_name,
        )
        sidecar_path = Path(str(package_set.get("path") or ""))
        try:
            sidecar_value = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MemoryStreamingTransportError(
                f"invalid MEMORY package sidecar: {exc}"
            ) from exc
        if not isinstance(sidecar_value, dict):
            raise MemoryStreamingTransportError("MEMORY package sidecar must be an object")
        sidecar = sidecar_value
    else:
        sidecar = dict(package_sidecar)
        if str(sidecar.get("profile") or "").strip().lower() != "memory":
            raise MemoryStreamingTransportError("MEMORY package profile rejected")
        declared = _safe_flat_filename(str(sidecar.get("package_name") or ""))
        if declared != zip_name:
            raise MemoryStreamingTransportError(
                f"MEMORY sidecar package name mismatch: {declared!r}!={zip_name!r}"
            )
        expected, expected_full_sha = _expectations_from_sidecar(sidecar)
        expectations_source = "in_memory_sidecar"
        package_set = {
            "source": "in_memory_sidecar",
            "path": None,
            "profile": "memory",
            "archive_format": str(sidecar.get("archive_format") or "binary")
            .strip()
            .lower(),
            "package_version": str(sidecar.get("package_version") or "").strip() or None,
            "schema_version": sidecar.get("schema_version"),
        }

    archive_format = str(package_set.get("archive_format") or "binary").strip().lower()
    if archive_format not in {"binary", "independent"}:
        raise MemoryStreamingTransportError(
            f"unsupported MEMORY archive_format: {archive_format!r}"
        )

    parts, part_report = resolve_verified_parts_in_place(parts_dir, expected)
    if expected_full_sha and archive_format == "binary":
        actual_full_sha = _logical_sha256(parts)
        if actual_full_sha != expected_full_sha:
            raise MemoryStreamingTransportError(
                f"MEMORY logical ZIP SHA-256 mismatch: "
                f"{actual_full_sha}!={expected_full_sha}"
            )
    else:
        actual_full_sha = None

    inventory = _entry_inventory(sidecar)
    package_key = _package_key(zip_name, sidecar, expected_full_sha)
    staging_parent = target_memory_root.parent / ".memory-incoming"
    staging = staging_parent / package_key
    progress_path = staging_parent / f".{package_key}.progress.json"
    if force_reextract:
        shutil.rmtree(staging, ignore_errors=True)
        progress_path.unlink(missing_ok=True)
    staging.mkdir(parents=True, exist_ok=True)

    expected_payload_bytes = sum(int(item["size_bytes"]) for item in inventory.values())
    disk = _disk_preflight(
        staging_parent,
        staging,
        expected_payload_bytes=expected_payload_bytes,
    )
    completed = _load_progress(progress_path, package_key)
    started = time.monotonic()
    completed_now = 0

    with _ArchiveSet(parts, archive_format) as archive_set:
        members = _member_map(archive_set.archives, inventory)
        manifest = _read_manifest(members, inventory)
        raw_by_source, segment_paths = _raw_descriptor_maps(manifest)

        regular_paths = [
            relative for relative in sorted(inventory) if relative not in segment_paths
        ]
        total_operations = len(regular_paths) + len(raw_by_source)

        def budget_reached() -> bool:
            return bool(
                time_budget_seconds is not None
                and completed_now > 0
                and (time.monotonic() - started) >= float(time_budget_seconds)
            )

        for relative in regular_paths:
            if budget_reached():
                _write_progress(
                    progress_path,
                    package_key=package_key,
                    state="pending",
                    completed=completed,
                    staging=staging,
                )
                return {
                    "ok": False,
                    "pending": True,
                    "state": "memory_streaming_extract_pending",
                    "zip_name": zip_name,
                    "staging": str(staging),
                    "progress_path": str(progress_path),
                    "package_set": package_set,
                    "part_resolution": part_report,
                    "disk_preflight": disk,
                    "expected_full_sha256": expected_full_sha,
                    "observed_full_sha256": actual_full_sha,
                    "completed_count": len(completed),
                    "total_operations": total_operations,
                    "raw_segments_materialized": bool(raw_by_source),
                    "bytes_copied_for_transport_normalization": 0,
                    "joined_zip_materialized": False,
                    "runtime_repack_performed": False,
                }
            expected_entry = inventory[relative]
            _write_member(relative, members[relative], expected_entry, staging)
            completed[relative] = {
                "size_bytes": int(expected_entry["size_bytes"]),
                "sha256": str(expected_entry["sha256"]),
                "form": "transport_member",
            }
            completed_now += 1
            _write_progress(
                progress_path,
                package_key=package_key,
                state="extracting",
                completed=completed,
                staging=staging,
            )

        for source_path in sorted(raw_by_source):
            if budget_reached():
                _write_progress(
                    progress_path,
                    package_key=package_key,
                    state="pending",
                    completed=completed,
                    staging=staging,
                )
                return {
                    "ok": False,
                    "pending": True,
                    "state": "memory_streaming_extract_pending",
                    "zip_name": zip_name,
                    "staging": str(staging),
                    "progress_path": str(progress_path),
                    "package_set": package_set,
                    "part_resolution": part_report,
                    "disk_preflight": disk,
                    "expected_full_sha256": expected_full_sha,
                    "observed_full_sha256": actual_full_sha,
                    "completed_count": len(completed),
                    "total_operations": total_operations,
                    "raw_segments_materialized": True,
                    "bytes_copied_for_transport_normalization": 0,
                    "joined_zip_materialized": False,
                    "runtime_repack_performed": False,
                }
            descriptor = raw_by_source[source_path]
            _stream_raw_descriptor(descriptor, members, inventory, staging)
            completed[source_path] = {
                "size_bytes": int(descriptor.get("source_size_bytes") or 0),
                "sha256": str(descriptor.get("source_sha256") or ""),
                "form": "materialized_raw_source",
            }
            completed_now += 1
            _write_progress(
                progress_path,
                package_key=package_key,
                state="extracting",
                completed=completed,
                staging=staging,
            )

        allowed_paths = (set(inventory) - segment_paths) | set(raw_by_source)
        actual_paths = {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file() and not path.name.endswith(".partial")
        }
        extras = sorted(actual_paths - allowed_paths)
        missing_installed = sorted(
            path for path in allowed_paths if not _target_for(staging, path).is_file()
        )
        if extras or missing_installed:
            raise MemoryStreamingTransportError(
                "installed MEMORY tree mismatch:"
                f"extras={extras[:20]},missing={missing_installed[:20]}"
            )

        archive_set.assert_stable()

    _write_progress(
        progress_path,
        package_key=package_key,
        state="complete",
        completed=completed,
        staging=staging,
    )
    return {
        "ok": True,
        "pending": False,
        "state": "memory_streaming_extract_complete",
        "zip_name": zip_name,
        "staging": str(staging),
        "progress_path": str(progress_path),
        "package_set": package_set,
        "expectations_source": expectations_source,
        "part_resolution": part_report,
        "disk_preflight": disk,
        "expected_full_sha256": expected_full_sha,
        "observed_full_sha256": actual_full_sha,
        "transport_member_count": len(inventory),
        "installed_file_count": len(allowed_paths),
        "raw_segments_materialized": bool(raw_by_source),
        "raw_segment_source_count": len(raw_by_source),
        "raw_transport_segment_count": len(segment_paths),
        "bytes_copied_for_transport_normalization": 0,
        "joined_zip_materialized": False,
        "runtime_repack_performed": False,
        "truth_boundary": (
            "The source transport remains immutable input. Uploaded parts are "
            "verified in place; the runtime writes exactly one candidate MEMORY "
            "tree on the target filesystem, validates it, and only then may the "
            "caller atomically activate that tree."
        ),
    }


__all__ = [
    "MemoryStreamingTransportError",
    "SplitZipReader",
    "VerifiedTransportPart",
    "resolve_verified_parts_in_place",
    "stream_extract_verified_memory_package",
]
