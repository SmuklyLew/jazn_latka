from __future__ import annotations

"""Standalone, stdlib-only bootstrap for a Jaźń system ZIP.

This file is intentionally independent from ``latka_jazn``. It exists for the
one state in which a ChatGPT host has a verified system ZIP but no unpacked
``run.py`` operator yet. It performs only bounded package verification and
materialization; runtime lifecycle remains owned by the extracted ``run.py``.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile


BOOTSTRAP_SCHEMA_VERSION = "chatgpt_system_zip_bootstrap/v1"
CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_MAX_ENTRIES = 20_000
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 1_000.0
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_ROOT_FILES = frozenset(
    {
        "run.py",
        "AGENTS.md",
        "latka_jazn/version.py",
        "PACKAGE_INTEGRITY_MANIFEST.json",
        "SOURCE_PROVENANCE.json",
    }
)


class BootstrapError(RuntimeError):
    """Fail-closed bootstrap error with a stable diagnostic code."""

    def __init__(self, message: str, *, code: str = "bootstrap_failed") -> None:
        super().__init__(message)
        self.code = str(code or "bootstrap_failed")


def _identity_from_stat(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
    )


def sha256_stable_file(
    path: Path,
    *,
    expected_size_bytes: int | None = None,
) -> tuple[str, int]:
    """Hash one already-materialized file and reject concurrent replacement/write.

    This is intentionally local and stdlib-only so it can be used before the
    Jaźń package itself is importable. Size is checked before hashing when an
    expected value is available, and the opened descriptor plus final path are
    compared after the read to avoid accepting a moving attachment target.
    """

    if expected_size_bytes is not None and int(expected_size_bytes) < 0:
        raise BootstrapError(
            "expected ZIP size must be >= 0",
            code="invalid_expected_size",
        )

    try:
        path_before = path.stat()
        with path.open("rb") as handle:
            fd_before = os.fstat(handle.fileno())
            if _identity_from_stat(path_before) != _identity_from_stat(fd_before):
                raise BootstrapError(
                    "system ZIP changed between path lookup and open",
                    code="source_changed_before_hash",
                )

            observed_size = int(fd_before.st_size)
            if expected_size_bytes is not None and observed_size != int(expected_size_bytes):
                raise BootstrapError(
                    "system ZIP size mismatch: "
                    f"expected={int(expected_size_bytes)}, actual={observed_size}",
                    code="source_size_mismatch",
                )

            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
            fd_after = os.fstat(handle.fileno())

        path_after = path.stat()
    except OSError as exc:
        raise BootstrapError(
            f"cannot read system ZIP: {path}",
            code="source_read_failed",
        ) from exc

    identity_before = _identity_from_stat(fd_before)
    if identity_before != _identity_from_stat(fd_after):
        raise BootstrapError(
            "system ZIP changed while SHA-256 was being calculated",
            code="source_changed_during_hash",
        )
    if identity_before != _identity_from_stat(path_after):
        raise BootstrapError(
            "system ZIP path changed during SHA-256 verification",
            code="source_replaced_during_hash",
        )
    return digest.hexdigest(), observed_size


def sha256_file(path: Path) -> str:
    """Compatibility helper returning the stable SHA-256 digest only."""

    digest, _ = sha256_stable_file(path)
    return digest


def _expected_sha256(*, sidecar: Path | None, explicit: str | None) -> str:
    candidate = str(explicit or "").strip()
    if sidecar is not None:
        if candidate:
            raise BootstrapError(
                "pass either --sha256-file or --expected-sha256, not both",
                code="ambiguous_sha256_source",
            )
        try:
            text = sidecar.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise BootstrapError(
                f"cannot read SHA-256 sidecar: {sidecar}",
                code="sha256_sidecar_read_failed",
            ) from exc
        tokens = text.strip().split()
        candidate = tokens[0] if tokens else ""
    if not _SHA256_RE.fullmatch(candidate):
        raise BootstrapError(
            "a valid 64-hex SHA-256 is required before ZIP inspection",
            code="invalid_expected_sha256",
        )
    return candidate.lower()


def _normalized_member_name(info: zipfile.ZipInfo) -> str:
    raw = info.filename
    if not raw or "\x00" in raw:
        raise BootstrapError(
            "ZIP contains an empty or NUL-bearing member name",
            code="unsafe_zip_member",
        )
    if "\\" in raw:
        raise BootstrapError(
            f"ZIP member uses non-canonical backslashes: {raw!r}",
            code="unsafe_zip_member",
        )
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise BootstrapError(
            f"unsafe ZIP member path: {raw!r}",
            code="unsafe_zip_member",
        )
    if path.parts and re.fullmatch(r"[A-Za-z]:", path.parts[0]):
        raise BootstrapError(
            f"drive-qualified ZIP member path: {raw!r}",
            code="unsafe_zip_member",
        )
    normalized = path.as_posix().rstrip("/")
    if normalized in {"", "."}:
        raise BootstrapError(
            f"invalid ZIP member path: {raw!r}",
            code="unsafe_zip_member",
        )
    if info.flag_bits & 0x1:
        raise BootstrapError(
            f"encrypted ZIP member rejected: {raw!r}",
            code="encrypted_zip_member",
        )

    if info.create_system == 3:
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise BootstrapError(
                f"ZIP symlink rejected: {raw!r}",
                code="zip_symlink_rejected",
            )
        file_type = stat.S_IFMT(mode) if mode else 0
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise BootstrapError(
                f"special ZIP filesystem entry rejected: {raw!r}",
                code="zip_special_entry_rejected",
            )
        if file_type == stat.S_IFDIR and not info.is_dir():
            raise BootstrapError(
                f"ZIP directory type/name mismatch: {raw!r}",
                code="zip_type_mismatch",
            )
        if file_type == stat.S_IFREG and info.is_dir():
            raise BootstrapError(
                f"ZIP regular-file type/name mismatch: {raw!r}",
                code="zip_type_mismatch",
            )
    return normalized


def _resolve_root_prefix(names: set[str]) -> str:
    if _REQUIRED_ROOT_FILES.issubset(names):
        return ""

    top_levels = {
        name.split("/", 1)[0]
        for name in names
        if "/" in name and name.split("/", 1)[0]
    }
    candidates = []
    for top in sorted(top_levels):
        prefix = f"{top}/"
        if all(f"{prefix}{required}" in names for required in _REQUIRED_ROOT_FILES):
            candidates.append(prefix)
    if len(candidates) != 1:
        raise BootstrapError(
            "system ZIP must expose exactly one canonical Jaźń root at archive root or one top-level directory",
            code="ambiguous_system_root",
        )
    return candidates[0]


def inspect_system_zip(
    zf: zipfile.ZipFile,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> tuple[str, int, int]:
    infos = zf.infolist()
    if not infos:
        raise BootstrapError("system ZIP is empty", code="empty_system_zip")
    if len(infos) > int(max_entries):
        raise BootstrapError(
            f"ZIP entry limit exceeded: {len(infos)} > {max_entries}",
            code="zip_entry_limit_exceeded",
        )

    names: set[str] = set()
    total_bytes = 0
    for info in infos:
        normalized = _normalized_member_name(info)
        if normalized in names:
            raise BootstrapError(
                f"duplicate ZIP member rejected: {normalized!r}",
                code="duplicate_zip_member",
            )
        names.add(normalized)

        size = int(info.file_size)
        compressed = int(info.compress_size)
        if size < 0:
            raise BootstrapError(
                f"ZIP member has negative uncompressed size: {normalized!r}",
                code="invalid_zip_size",
            )
        if compressed < 0:
            raise BootstrapError(
                f"ZIP member has negative compressed size: {normalized!r}",
                code="invalid_zip_size",
            )
        if size > int(max_member_bytes):
            raise BootstrapError(
                f"ZIP member size limit exceeded: {normalized!r}",
                code="zip_member_limit_exceeded",
            )

        total_bytes += size
        if total_bytes > int(max_total_bytes):
            raise BootstrapError(
                f"ZIP uncompressed-size limit exceeded: {total_bytes} > {max_total_bytes}",
                code="zip_total_limit_exceeded",
            )

        if size:
            ratio = float("inf") if compressed == 0 else size / compressed
            if ratio > float(max_compression_ratio):
                raise BootstrapError(
                    "ZIP compression-ratio limit exceeded: "
                    f"{normalized!r}: {ratio:.2f} > {float(max_compression_ratio):.2f}",
                    code="zip_compression_ratio_exceeded",
                )

    root_prefix = _resolve_root_prefix(names)
    bad_member = zf.testzip()
    if bad_member is not None:
        raise BootstrapError(
            f"ZIP CRC verification failed for: {bad_member}",
            code="zip_crc_failed",
        )
    return root_prefix, len(infos), total_bytes


def _safe_extract_validated_zip(
    zf: zipfile.ZipFile,
    destination: Path,
    *,
    max_total_bytes: int,
    max_member_bytes: int,
) -> int:
    """Stream validated members without delegating path decisions to extractall()."""

    destination_real = destination.resolve()
    total_written = 0
    for info in zf.infolist():
        normalized = _normalized_member_name(info)
        target = destination.joinpath(*PurePosixPath(normalized).parts)
        target_real = target.resolve(strict=False)
        try:
            common = os.path.commonpath((str(destination_real), str(target_real)))
        except ValueError as exc:
            raise BootstrapError(
                f"ZIP member cannot be resolved inside destination: {normalized!r}",
                code="unsafe_zip_member",
            ) from exc
        if common != str(destination_real):
            raise BootstrapError(
                f"ZIP member escapes destination: {normalized!r}",
                code="unsafe_zip_member",
            )

        if info.is_dir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue

        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        member_written = 0
        with zf.open(info, "r") as source, target.open("xb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                member_written += len(chunk)
                total_written += len(chunk)
                if member_written > int(max_member_bytes) or member_written > int(info.file_size):
                    raise BootstrapError(
                        f"ZIP member expanded beyond declared/allowed size: {normalized!r}",
                        code="zip_member_limit_exceeded",
                    )
                if total_written > int(max_total_bytes):
                    raise BootstrapError(
                        "ZIP extraction exceeded total uncompressed-size limit",
                        code="zip_total_limit_exceeded",
                    )
                output.write(chunk)

        if member_written != int(info.file_size):
            raise BootstrapError(
                f"ZIP member size changed during extraction: {normalized!r}",
                code="zip_member_size_inconsistent",
            )
        os.chmod(target, 0o600)
    return total_written


def bootstrap_system_zip(
    *,
    zip_path: Path,
    destination: Path,
    sha256_file_path: Path | None = None,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> dict[str, object]:
    zip_path = Path(zip_path).resolve()
    destination = Path(destination).resolve()
    sidecar = Path(sha256_file_path).resolve() if sha256_file_path is not None else None

    if not zip_path.is_file():
        raise BootstrapError(
            f"system ZIP not found: {zip_path}",
            code="source_not_found",
        )
    if destination.exists():
        raise BootstrapError(
            f"destination already exists; refusing overwrite: {destination}",
            code="destination_exists",
        )

    expected = _expected_sha256(sidecar=sidecar, explicit=expected_sha256)
    actual, observed_size = sha256_stable_file(
        zip_path,
        expected_size_bytes=expected_size_bytes,
    )
    if actual != expected:
        raise BootstrapError(
            f"SHA-256 mismatch: expected={expected}, actual={actual}",
            code="sha256_mismatch",
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".jazn-chatgpt-bootstrap-", dir=str(destination.parent)))
    moved = False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            root_prefix, entry_count, total_bytes = inspect_system_zip(
                zf,
                max_entries=max_entries,
                max_total_bytes=max_total_bytes,
                max_member_bytes=max_member_bytes,
                max_compression_ratio=max_compression_ratio,
            )
            extracted_bytes = _safe_extract_validated_zip(
                zf,
                staging,
                max_total_bytes=max_total_bytes,
                max_member_bytes=max_member_bytes,
            )

        if extracted_bytes != total_bytes:
            raise BootstrapError(
                "extracted byte count differs from validated ZIP metadata",
                code="zip_total_size_inconsistent",
            )

        root = staging if not root_prefix else staging / root_prefix.rstrip("/")
        if not root.is_dir():
            raise BootstrapError(
                "validated archive root was not materialized as a directory",
                code="materialized_root_missing",
            )
        missing = sorted(
            required for required in _REQUIRED_ROOT_FILES if not (root / required).is_file()
        )
        if missing:
            raise BootstrapError(
                f"materialized system root is incomplete: {missing}",
                code="materialized_operator_incomplete",
            )

        if root == staging:
            os.replace(staging, destination)
        else:
            os.replace(root, destination)
            shutil.rmtree(staging, ignore_errors=True)
        moved = True
        return {
            "ok": True,
            "schema_version": BOOTSTRAP_SCHEMA_VERSION,
            "state": "materialized_operator_ready",
            "zip_path": str(zip_path),
            "destination": str(destination),
            "sha256": actual,
            "source_size_bytes": observed_size,
            "stable_during_hash": True,
            "entry_count": entry_count,
            "uncompressed_size_bytes": total_bytes,
            "root_prefix": root_prefix or None,
            "operator_entrypoint": "run.py",
            "next_step": "Read AGENTS.md, then invoke the extracted run.py for host-preflight/doctor/start/status.",
        }
    except BootstrapError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise BootstrapError(
            f"system ZIP bootstrap failed: {type(exc).__name__}: {exc}",
            code="zip_bootstrap_io_failed",
        ) from exc
    finally:
        if not moved:
            shutil.rmtree(staging, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="CHATGPT_BOOTSTRAP.py",
        description="Fail-closed stdlib-only materialization of a Jaźń system ZIP.",
        allow_abbrev=False,
    )
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True)
    digest = parser.add_mutually_exclusive_group(required=True)
    digest.add_argument("--sha256-file", type=Path)
    digest.add_argument("--expected-sha256")
    parser.add_argument("--expected-size-bytes", type=int)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-member-bytes", type=int, default=DEFAULT_MAX_MEMBER_BYTES)
    parser.add_argument(
        "--max-compression-ratio",
        type=float,
        default=DEFAULT_MAX_COMPRESSION_RATIO,
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    try:
        payload = bootstrap_system_zip(
            zip_path=ns.zip_path,
            destination=ns.destination,
            sha256_file_path=ns.sha256_file,
            expected_sha256=ns.expected_sha256,
            expected_size_bytes=ns.expected_size_bytes,
            max_entries=ns.max_entries,
            max_total_bytes=ns.max_total_bytes,
            max_member_bytes=ns.max_member_bytes,
            max_compression_ratio=ns.max_compression_ratio,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except BootstrapError as exc:
        payload = {
            "ok": False,
            "schema_version": BOOTSTRAP_SCHEMA_VERSION,
            "state": "bootstrap_failed",
            "error_code": exc.code,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
