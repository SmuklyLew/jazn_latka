from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from latka_jazn.tools.safe_paths import validate_safe_relative_path, UnsafeRelativePathError
import hashlib
import os
import uuid

from latka_jazn.memory.storage_limits import DEFAULT_RAW_SEGMENT_MAX_BYTES, DEFAULT_RAW_SEGMENT_TARGET_BYTES


class RawMemorySegmentationError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class RawMemorySegmentationPolicy:
    target_segment_bytes: int = DEFAULT_RAW_SEGMENT_TARGET_BYTES
    max_segment_bytes: int = DEFAULT_RAW_SEGMENT_MAX_BYTES

    def __post_init__(self) -> None:
        if self.target_segment_bytes < 1024 * 1024:
            raise RawMemorySegmentationError("target segment size must be at least 1 MiB")
        if self.max_segment_bytes < self.target_segment_bytes:
            raise RawMemorySegmentationError("max segment size cannot be smaller than target segment size")


@dataclass(slots=True, frozen=True)
class RawMemorySegment:
    package_path: str
    segment_index: int
    line_count: int
    size_bytes: int
    sha256: str
    first_line_number: int
    last_line_number: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RawMemorySegmentationResult:
    source_path: str
    source_size_bytes: int
    source_sha256: str
    source_line_count: int
    segments: tuple[RawMemorySegment, ...]
    format: str = "jsonl_exact_line_segments/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "source_path": self.source_path,
            "source_size_bytes": self.source_size_bytes,
            "source_sha256": self.source_sha256,
            "source_line_count": self.source_line_count,
            "segments": [segment.to_dict() for segment in self.segments],
        }


class RawJsonlSegmenter:
    """Exact streaming segmentation for oversized raw JSONL transport.

    Segmentation preserves every source byte and every line boundary. It is a
    sandbox/package transport transform only; it does not change the local runtime
    representation. A single JSONL line larger than ``max_segment_bytes`` fails
    closed instead of allocating an unbounded buffer or producing an oversized ZIP
    member.
    """

    def __init__(self, policy: RawMemorySegmentationPolicy | None = None) -> None:
        self.policy = policy or RawMemorySegmentationPolicy()

    def segment(
        self,
        source: str | Path,
        *,
        source_relative: str,
        staging_root: str | Path,
    ) -> RawMemorySegmentationResult:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        relative = self._safe_memory_path(source_relative)
        if not relative.lower().endswith(".jsonl"):
            raise RawMemorySegmentationError("only JSONL files may use exact-line raw segmentation")
        staging = Path(staging_root).expanduser().resolve()
        segment_dir_relative = f"{relative}.segments"
        segment_dir = (staging / Path(*PurePosixPath(segment_dir_relative).parts)).resolve()
        segment_dir.relative_to(staging)
        if segment_dir.exists():
            raise FileExistsError(segment_dir)
        segment_dir.mkdir(parents=True, exist_ok=False)

        source_hash = hashlib.sha256()
        source_size = 0
        source_lines = 0
        segment_rows: list[RawMemorySegment] = []
        current_handle = None
        current_path: Path | None = None
        current_hash = hashlib.sha256()
        current_size = 0
        current_lines = 0
        current_first_line = 0
        segment_index = 0

        def close_segment() -> None:
            nonlocal current_handle, current_path, current_hash, current_size, current_lines
            nonlocal current_first_line, segment_index
            if current_handle is None or current_path is None:
                return
            current_handle.flush()
            os.fsync(current_handle.fileno())
            current_handle.close()
            package_path = current_path.relative_to(staging).as_posix()
            segment_rows.append(
                RawMemorySegment(
                    package_path=package_path,
                    segment_index=segment_index,
                    line_count=current_lines,
                    size_bytes=current_size,
                    sha256=current_hash.hexdigest(),
                    first_line_number=current_first_line,
                    last_line_number=current_first_line + current_lines - 1,
                )
            )
            current_handle = None
            current_path = None
            current_hash = hashlib.sha256()
            current_size = 0
            current_lines = 0
            current_first_line = 0

        try:
            with source_path.open("rb") as source_handle:
                while True:
                    line = source_handle.readline(self.policy.max_segment_bytes + 1)
                    if not line:
                        break
                    if len(line) > self.policy.max_segment_bytes:
                        raise RawMemorySegmentationError(
                            f"single JSONL line exceeds hard segment limit ({len(line)} > {self.policy.max_segment_bytes})"
                        )
                    # A bounded readline that fills the limit without a newline means
                    # the physical line continues and would exceed the hard limit.
                    if len(line) == self.policy.max_segment_bytes + 1 or (
                        len(line) >= self.policy.max_segment_bytes and not line.endswith(b"\n")
                    ):
                        probe = source_handle.peek(1)[:1] if hasattr(source_handle, "peek") else b""
                        if probe:
                            raise RawMemorySegmentationError("single JSONL line exceeds hard segment limit")
                    if current_handle is not None and current_size + len(line) > self.policy.target_segment_bytes:
                        close_segment()
                    if current_handle is None:
                        segment_index += 1
                        current_first_line = source_lines + 1
                        current_path = segment_dir / f"segment-{segment_index:06d}.jsonl"
                        current_handle = current_path.open("xb")
                    current_handle.write(line)
                    current_hash.update(line)
                    current_size += len(line)
                    current_lines += 1
                    source_hash.update(line)
                    source_size += len(line)
                    source_lines += 1
                    if current_size > self.policy.max_segment_bytes:
                        raise RawMemorySegmentationError("segment exceeded hard size limit")
            close_segment()
        except Exception:
            if current_handle is not None:
                current_handle.close()
            self._remove_tree(segment_dir)
            raise

        if source_size != source_path.stat().st_size:
            self._remove_tree(segment_dir)
            raise RawMemorySegmentationError("segmentation source size changed while reading")
        if not segment_rows and source_size:
            self._remove_tree(segment_dir)
            raise RawMemorySegmentationError("non-empty JSONL source produced no segments")
        return RawMemorySegmentationResult(
            source_path=relative,
            source_size_bytes=source_size,
            source_sha256=source_hash.hexdigest(),
            source_line_count=source_lines,
            segments=tuple(segment_rows),
        )

    @classmethod
    def verify_descriptor(
        cls,
        package_root: str | Path,
        descriptor: Mapping[str, Any],
    ) -> dict[str, Any]:
        root = Path(package_root).expanduser().resolve()
        source_path = cls._safe_memory_path(str(descriptor.get("source_path") or ""))
        source_hash = hashlib.sha256()
        source_size = 0
        source_lines = 0
        raw_segments = descriptor.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise RawMemorySegmentationError("raw segment descriptor requires a non-empty segments list")
        expected_index = 1
        for item in raw_segments:
            if not isinstance(item, Mapping):
                raise RawMemorySegmentationError("raw segment entry must be an object")
            index = int(item.get("segment_index") or 0)
            if index != expected_index:
                raise RawMemorySegmentationError(
                    f"raw segment sequence gap: expected {expected_index}, got {index}"
                )
            relative = cls._safe_memory_path(str(item.get("package_path") or ""))
            target = (root / Path(*PurePosixPath(relative).parts)).resolve()
            target.relative_to(root)
            if not target.is_file():
                raise RawMemorySegmentationError(f"raw segment missing: {relative}")
            segment_hash = hashlib.sha256()
            segment_size = 0
            newline_count = 0
            last_byte = b""
            with target.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    segment_hash.update(block)
                    source_hash.update(block)
                    segment_size += len(block)
                    source_size += len(block)
                    newline_count += block.count(b"\n")
                    if block:
                        last_byte = block[-1:]
            segment_lines = newline_count + (1 if segment_size and last_byte != b"\n" else 0)
            source_lines += segment_lines
            if segment_hash.hexdigest() != str(item.get("sha256") or ""):
                raise RawMemorySegmentationError(f"raw segment SHA-256 mismatch: {relative}")
            if segment_size != int(item.get("size_bytes") or -1):
                raise RawMemorySegmentationError(f"raw segment size mismatch: {relative}")
            declared_lines = int(item.get("line_count") or 0)
            if declared_lines != segment_lines:
                raise RawMemorySegmentationError(f"raw segment line-count mismatch: {relative}")
            first_line = int(item.get("first_line_number") or 0)
            last_line = int(item.get("last_line_number") or 0)
            if first_line != source_lines - segment_lines + 1 or last_line != source_lines:
                raise RawMemorySegmentationError(f"raw segment line-range mismatch: {relative}")
            expected_index += 1
        expected_size = int(descriptor.get("source_size_bytes") or -1)
        expected_sha = str(descriptor.get("source_sha256") or "")
        if source_size != expected_size:
            raise RawMemorySegmentationError("reconstructed raw source size mismatch")
        if source_hash.hexdigest() != expected_sha:
            raise RawMemorySegmentationError("reconstructed raw source SHA-256 mismatch")
        if source_lines != int(descriptor.get("source_line_count") or -1):
            raise RawMemorySegmentationError("reconstructed raw source line-count mismatch")
        return {
            "ok": True,
            "source_path": source_path,
            "source_size_bytes": source_size,
            "source_sha256": expected_sha,
            "segment_count": len(raw_segments),
        }

    @classmethod
    def materialize_descriptor(
        cls,
        package_root: str | Path,
        descriptor: Mapping[str, Any],
        *,
        remove_segments: bool = False,
    ) -> Path:
        root = Path(package_root).expanduser().resolve()
        report = cls.verify_descriptor(root, descriptor)
        relative = cls._safe_memory_path(str(report["source_path"]))
        target = (root / Path(*PurePosixPath(relative).parts)).resolve()
        target.relative_to(root)
        if target.exists():
            raise FileExistsError(f"segmented raw source target already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f".materializing-{uuid.uuid4().hex}.tmp")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as out:
                for item in descriptor["segments"]:
                    segment_relative = cls._safe_memory_path(str(item["package_path"]))
                    segment = (root / Path(*PurePosixPath(segment_relative).parts)).resolve()
                    with segment.open("rb") as inp:
                        for block in iter(lambda: inp.read(1024 * 1024), b""):
                            out.write(block)
                            digest.update(block)
                            size += len(block)
                out.flush()
                os.fsync(out.fileno())
            if size != int(descriptor["source_size_bytes"]) or digest.hexdigest() != str(descriptor["source_sha256"]):
                raise RawMemorySegmentationError("materialized raw source failed final size/SHA verification")
            os.replace(temporary, target)
            if remove_segments:
                parents = {
                    (root / Path(*PurePosixPath(str(item["package_path"])).parts)).resolve().parent
                    for item in descriptor["segments"]
                }
                for parent in sorted(parents, key=lambda item: len(item.parts), reverse=True):
                    cls._remove_tree(parent)
            return target
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _safe_memory_path(value: str) -> str:
        try:
            canonical = validate_safe_relative_path(str(value))
        except UnsafeRelativePathError as exc:
            raise RawMemorySegmentationError(f"unsafe memory path: {value!r}: {exc}") from exc
        if not canonical.startswith("memory/"):
            raise RawMemorySegmentationError(f"unsafe memory path outside memory/: {value!r}")
        return canonical

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()


__all__ = [
    "RawJsonlSegmenter",
    "RawMemorySegment",
    "RawMemorySegmentationError",
    "RawMemorySegmentationPolicy",
    "RawMemorySegmentationResult",
]
