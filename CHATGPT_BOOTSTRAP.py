from __future__ import annotations

"""Standalone, stdlib-only bootstrap for a Jaźń system ZIP.

This file is intentionally independent from ``latka_jazn``. It exists for the
one state in which a ChatGPT host has a verified system ZIP but no unpacked
``run.py`` operator yet. It performs only bounded package verification and
materialization; runtime lifecycle remains owned by the extracted ``run.py``.
"""

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import sys
import tempfile
from typing import Callable
import zipfile


BOOTSTRAP_SCHEMA_VERSION = "chatgpt_system_zip_bootstrap/v1"
MATERIALIZATION_STAMP_SCHEMA_VERSION = "chatgpt_materialization_stamp/v1"
MATERIALIZATION_STAMP_SUFFIX = ".jazn-materialization.json"
PACKAGE_INTEGRITY_MANIFEST_NAME = "PACKAGE_INTEGRITY_MANIFEST.json"
POST_MATERIALIZATION_ACTIVATION_SCHEMA_VERSION = "chatgpt_post_materialization_activation/v1"
BOOTSTRAP_PROGRESS_SCHEMA_VERSION = "chatgpt_bootstrap_progress/v1"
CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_MAX_ENTRIES = 20_000
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 1_000.0
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_CHATGPT_TURN_TOOLS = (
    "jazn_status",
    "jazn_generate_visible_reply",
    "jazn_resume_visible_reply",
    "jazn_finalize_reply",
)
_REQUIRED_ROOT_FILES = frozenset(
    {
        "run.py",
        "AGENTS.md",
        "latka_jazn/version.py",
        "PACKAGE_INTEGRITY_MANIFEST.json",
        "SOURCE_PROVENANCE.json",
    }
)

_BOOTSTRAP_PROGRESS_MILESTONES = (
    ("executor_probe", 5),
    ("system_package_verified", 15),
    ("zip_validated", 30),
    ("operator_materialized", 55),
    ("host_preflight", 65),
    ("contracts_loaded", 72),
    ("daemon_started", 82),
    ("live_readiness", 95),
    ("turn_channel_bound", 100),
)


def build_bootstrap_progress_contract() -> dict[str, object]:
    return {
        "schema_version": BOOTSTRAP_PROGRESS_SCHEMA_VERSION,
        "milestones": [
            {"gate": gate, "wake_percent": percent}
            for gate, percent in _BOOTSTRAP_PROGRESS_MILESTONES
        ],
        "percent_semantics": "completed_verified_gates_only",
        "optional_memory_blocks_core_wake": False,
        "required_memory_is_separate_readiness_dimension": True,
        "live_status_is_activation_authority": True,
        "snapshot_status_is_diagnostic_only": True,
        "truth_boundary": (
            "Wake percent is milestone-derived and may advance only after evidence-backed "
            "gates complete. Optional MEMORY must not hold a ready SYSTEM at 99 percent. "
            "Host-side upload/materialization progress that the bootstrap cannot observe "
            "must remain unknown rather than estimated."
        ),
    }


def _bootstrap_progress_event(
    *,
    phase: str,
    status: str,
    wake_percent: int,
    detail: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "event": "jazn_bootstrap_progress",
        "schema_version": BOOTSTRAP_PROGRESS_SCHEMA_VERSION,
        "phase": str(phase),
        "status": str(status),
        "wake_percent": max(0, min(100, int(wake_percent))),
        "detail": dict(detail or {}),
    }


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



def _materialization_stamp_path(destination: Path) -> Path:
    root = Path(destination).resolve()
    return root.parent / f".{root.name}{MATERIALIZATION_STAMP_SUFFIX}"


def _read_json_object(path: Path, *, code: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError(
            f"cannot read valid JSON object: {path}",
            code=code,
        ) from exc
    if not isinstance(value, dict):
        raise BootstrapError(
            f"JSON root must be an object: {path}",
            code=code,
        )
    return value


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _materialized_manifest_member(root: Path, raw_name: str) -> Path:
    if not raw_name or "\x00" in raw_name or "\\" in raw_name:
        raise BootstrapError(
            f"unsafe package manifest path: {raw_name!r}",
            code="unsafe_materialized_manifest_path",
        )
    relative = PurePosixPath(raw_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise BootstrapError(
            f"unsafe package manifest path: {raw_name!r}",
            code="unsafe_materialized_manifest_path",
        )
    if relative.parts and re.fullmatch(r"[A-Za-z]:", relative.parts[0]):
        raise BootstrapError(
            f"drive-qualified package manifest path: {raw_name!r}",
            code="unsafe_materialized_manifest_path",
        )

    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        common = os.path.commonpath((str(root.resolve()), str(resolved)))
    except (OSError, RuntimeError, ValueError) as exc:
        raise BootstrapError(
            f"materialized manifest member is missing or cannot be resolved: {raw_name!r}",
            code="materialized_manifest_member_missing",
        ) from exc
    if common != str(root.resolve()):
        raise BootstrapError(
            f"materialized manifest member escapes active root: {raw_name!r}",
            code="unsafe_materialized_manifest_path",
        )
    if candidate.is_symlink() or not resolved.is_file():
        raise BootstrapError(
            f"materialized manifest member is not a regular file: {raw_name!r}",
            code="materialized_manifest_member_invalid",
        )
    return resolved


def verify_materialized_integrity_manifest(destination: Path) -> dict[str, object]:
    """Cryptographically verify a reused active root without reopening the ZIP."""
    root = Path(destination).resolve()
    manifest_path = root / PACKAGE_INTEGRITY_MANIFEST_NAME
    if not manifest_path.is_file():
        raise BootstrapError(
            "reused active root has no PACKAGE_INTEGRITY_MANIFEST.json",
            code="materialized_manifest_missing",
        )
    manifest_sha256, manifest_size = sha256_stable_file(manifest_path)
    manifest = _read_json_object(manifest_path, code="materialized_manifest_invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BootstrapError(
            "PACKAGE_INTEGRITY_MANIFEST.json has no static file plan",
            code="materialized_manifest_invalid",
        )

    verified_count = 0
    verified_bytes = 0
    for index, raw_entry in enumerate(files):
        if not isinstance(raw_entry, dict):
            raise BootstrapError(
                f"invalid package manifest entry at index {index}",
                code="materialized_manifest_invalid",
            )
        raw_path = str(raw_entry.get("path") or "").strip()
        expected_sha256 = str(raw_entry.get("sha256") or "").strip().lower()
        raw_size = raw_entry.get("size_bytes")
        if (
            not raw_path
            or not _SHA256_RE.fullmatch(expected_sha256)
            or isinstance(raw_size, bool)
            or not isinstance(raw_size, int)
            or raw_size < 0
        ):
            raise BootstrapError(
                f"invalid package manifest metadata for entry {index}",
                code="materialized_manifest_invalid",
            )
        member = _materialized_manifest_member(root, raw_path)
        actual_sha256, actual_size = sha256_stable_file(
            member,
            expected_size_bytes=raw_size,
        )
        if actual_sha256 != expected_sha256:
            raise BootstrapError(
                f"materialized file SHA-256 mismatch: {raw_path}",
                code="materialized_file_sha256_mismatch",
            )
        verified_count += 1
        verified_bytes += actual_size

    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "manifest_size_bytes": manifest_size,
        "verified_static_file_count": verified_count,
        "verified_static_bytes": verified_bytes,
        "package_version": manifest.get("package_version") or manifest.get("version"),
    }


def _write_materialization_stamp(
    destination: Path,
    *,
    source_zip_sha256: str,
    source_size_bytes: int,
    root_prefix: str,
    entry_count: int,
    uncompressed_size_bytes: int,
) -> dict[str, object]:
    root = Path(destination).resolve()
    manifest_path = root / PACKAGE_INTEGRITY_MANIFEST_NAME
    manifest_sha256, manifest_size = sha256_stable_file(manifest_path)
    stamp_path = _materialization_stamp_path(root)
    payload: dict[str, object] = {
        "schema_version": MATERIALIZATION_STAMP_SCHEMA_VERSION,
        "destination": str(root),
        "source_zip_sha256": str(source_zip_sha256).lower(),
        "source_size_bytes": int(source_size_bytes),
        "package_integrity_manifest_sha256": manifest_sha256,
        "package_integrity_manifest_size_bytes": manifest_size,
        "root_prefix": root_prefix or None,
        "entry_count": int(entry_count),
        "uncompressed_size_bytes": int(uncompressed_size_bytes),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "reuse_requires_full_static_manifest_verification": True,
    }
    try:
        _write_json_atomic(stamp_path, payload)
    except OSError as exc:
        raise BootstrapError(
            f"cannot write materialization stamp: {stamp_path}",
            code="materialization_stamp_write_failed",
        ) from exc
    return {"written": True, "path": str(stamp_path), **payload}


def _reuse_existing_materialization(
    *,
    zip_path: Path,
    destination: Path,
    expected_sha256: str,
    expected_size_bytes: int | None,
) -> dict[str, object]:
    root = Path(destination).resolve()
    if not root.is_dir():
        raise BootstrapError(
            f"existing destination is not a directory: {root}",
            code="existing_destination_not_directory",
        )
    try:
        source_size = int(Path(zip_path).stat().st_size)
    except OSError as exc:
        raise BootstrapError(
            f"cannot stat system ZIP for reuse: {zip_path}",
            code="source_read_failed",
        ) from exc
    if expected_size_bytes is not None and source_size != int(expected_size_bytes):
        raise BootstrapError(
            "system ZIP size mismatch during verified reuse: "
            f"expected={int(expected_size_bytes)}, actual={source_size}",
            code="source_size_mismatch",
        )

    stamp_path = _materialization_stamp_path(root)
    stamp = _read_json_object(
        stamp_path,
        code="materialization_stamp_missing_or_invalid",
    )
    if stamp.get("schema_version") != MATERIALIZATION_STAMP_SCHEMA_VERSION:
        raise BootstrapError("materialization stamp schema mismatch", code="materialization_stamp_mismatch")
    try:
        stamped_root = Path(str(stamp.get("destination") or "")).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise BootstrapError(
            "materialization stamp destination is invalid",
            code="materialization_stamp_mismatch",
        ) from exc
    if stamped_root != root:
        raise BootstrapError(
            "materialization stamp belongs to another destination",
            code="materialization_stamp_mismatch",
        )
    if str(stamp.get("source_zip_sha256") or "").lower() != expected_sha256.lower():
        raise BootstrapError(
            "materialization stamp source SHA-256 differs from trusted package identity",
            code="materialization_stamp_mismatch",
        )
    raw_stamped_size = stamp.get("source_size_bytes")
    if (
        isinstance(raw_stamped_size, bool)
        or not isinstance(raw_stamped_size, int)
        or raw_stamped_size < 0
    ):
        raise BootstrapError(
            "materialization stamp source size is invalid",
            code="materialization_stamp_mismatch",
        )
    stamped_size = raw_stamped_size
    if stamped_size != source_size:
        raise BootstrapError(
            "materialization stamp source size differs from current ZIP size",
            code="materialization_stamp_mismatch",
        )

    integrity = verify_materialized_integrity_manifest(root)
    if (
        str(stamp.get("package_integrity_manifest_sha256") or "").lower()
        != str(integrity["manifest_sha256"]).lower()
    ):
        raise BootstrapError(
            "materialization stamp manifest identity differs from active root",
            code="materialization_stamp_mismatch",
        )
    missing = sorted(required for required in _REQUIRED_ROOT_FILES if not (root / required).is_file())
    if missing:
        raise BootstrapError(
            f"reused system root is incomplete: {missing}",
            code="materialized_operator_incomplete",
        )
    raw_entry_count = stamp.get("entry_count")
    raw_uncompressed_size = stamp.get("uncompressed_size_bytes")
    if (
        isinstance(raw_entry_count, bool)
        or not isinstance(raw_entry_count, int)
        or raw_entry_count < 0
        or isinstance(raw_uncompressed_size, bool)
        or not isinstance(raw_uncompressed_size, int)
        or raw_uncompressed_size < 0
    ):
        raise BootstrapError(
            "materialization stamp extraction counters are invalid",
            code="materialization_stamp_mismatch",
        )
    return {
        "reused": True,
        "materialization_mode": "verified_reuse",
        "source_zip_rehashed": False,
        "source_size_bytes": source_size,
        "sha256": expected_sha256.lower(),
        "root_prefix": stamp.get("root_prefix"),
        "entry_count": raw_entry_count,
        "uncompressed_size_bytes": raw_uncompressed_size,
        "materialization_stamp": {
            "path": str(stamp_path),
            "schema_version": stamp.get("schema_version"),
            "verified": True,
        },
        **integrity,
    }


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
    progress_callback: Callable[[int, int], None] | None = None,
    progress_total_bytes: int | None = None,
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
                if progress_callback is not None:
                    progress_callback(
                        total_written,
                        int(progress_total_bytes or max(total_written, 1)),
                    )

        if member_written != int(info.file_size):
            raise BootstrapError(
                f"ZIP member size changed during extraction: {normalized!r}",
                code="zip_member_size_inconsistent",
            )
        os.chmod(target, 0o600)
    return total_written


def build_chatgpt_local_launch_contract(destination: Path) -> dict[str, object]:
    """Return the canonical local ChatGPT bridge launch contract.

    The contract is intentionally declarative.  It tells a capable host exactly
    which control-plane command to execute after verified materialization while
    keeping process creation outside the ZIP/package trust boundary.
    """

    root = Path(destination).resolve()
    return {
        "schema_version": "chatgpt_local_launch/v1",
        "cwd": str(root),
        "requires_host_process_execution": True,
        "package_can_create_host_executor": False,
        "canonical_mode": "chat-gpt",
        "language_model_channel": "chatgpt_host",
        "model_cli_argument_required": False,
        "paid_openai_api_required": False,
        "openai_api_key_required": False,
        "persistent_stdio_preferred": True,
        "one_process_multiple_turns_preferred": True,
        "session_id_must_be_stable": True,
        "public_starter_argv": [
            "<python>",
            "-X",
            "utf8",
            "run.py",
            "chat-gpt",
            "--session-id",
            "<stable-session-id>",
        ],
        "control_plane_argv": [
            "<python>",
            "-X",
            "utf8",
            "main.py",
            "chat-gpt",
            "--session-id",
            "<stable-session-id>",
        ],
        "daemon_start_control_plane_argv": [
            "<python>",
            "-X",
            "utf8",
            "main.py",
            "start",
        ],
        "runtime_status_control_plane_argv": [
            "<python>",
            "-X",
            "utf8",
            "main.py",
            "status",
            "--json",
        ],
        "runtime_snapshot_diagnostic_control_plane_argv": [
            "<python>",
            "-X",
            "utf8",
            "main.py",
            "status",
            "--snapshot",
            "--json",
        ],
        "runtime_readiness_source": "live_status",
        "progress_contract": build_bootstrap_progress_contract(),
        "nonstreaming_turn_contract": {
            "transport": "daemon_bound_transactional_turns",
            "preallocate_request_id_before_process_spawn": True,
            "submit_argv_suffix": [
                "--daemon-request-id",
                "<unique-turn-request-id>",
                "--",
                "<exact-user-message>",
            ],
            "resume_argv_suffix": [
                "--daemon-result",
                "<same-request-id>",
            ],
            "message_replay_allowed": False,
        },
        "visible_reply_acceptance": {
            "required_action": "display_exact",
            "valid_lineage_required": True,
            "message_envelope_required": True,
            "accepted_finalization_required": True,
        },
        "truth_boundary": (
            "This contract is launch intent, not proof of process creation. The ChatGPT "
            "bridge uses the surrounding ChatGPT host as the language-model channel and "
            "does not require OPENAI_API_KEY or a --model flag. Canonical exported argv uses main.py subcommands; legacy --chat-gpt/--daemon-* flags remain internal compatibility only. A host without process "
            "execution cannot satisfy this local contract; it must use a separately "
            "verified callable Jaźń remote app/connector."
        ),
    }


def build_post_materialization_activation_contract(destination: Path) -> dict[str, object]:
    """Describe valid next steps after a verified SYSTEM ZIP is materialized."""

    root = Path(destination).resolve()
    chatgpt_launch = build_chatgpt_local_launch_contract(root)
    return {
        "schema_version": POST_MATERIALIZATION_ACTIVATION_SCHEMA_VERSION,
        "active_root_candidate": str(root),
        "operator_entrypoint": "run.py",
        "control_plane": "main.py",
        "local": {
            "requires_host_python_execution": True,
            "package_can_create_host_executor": False,
            "same_interpreter_preflight_supported": True,
            "preflight_requires_child_process": False,
            "preflight_flag": "--post-materialization-preflight",
            "preflight_argv": ["host-preflight", "--json"],
            "runtime_activation_requires_additional_host_capabilities": True,
            "runtime_start_entrypoint": "run.py start",
            "runtime_status_entrypoint": "run.py status --json",
            "runtime_snapshot_diagnostic_entrypoint": "run.py status --snapshot --json",
            "runtime_start_argv": ["start"],
            "runtime_status_argv": ["status", "--json"],
            "runtime_snapshot_diagnostic_argv": ["status", "--snapshot", "--json"],
            "control_plane_start_entrypoint": "main.py start",
            "control_plane_status_entrypoint": "main.py status --json",
            "control_plane_snapshot_diagnostic_entrypoint": "main.py status --snapshot --json",
            "activation_readiness_source": "live_status",
            "snapshot_is_activation_authority": False,
            "progress_contract": build_bootstrap_progress_contract(),
            "chatgpt_bridge_entrypoint": "main.py chat-gpt --session-id <stable-session-id>",
            "chatgpt_bridge": chatgpt_launch,
            "activation_success_requires_verified_status": True,
        },
        "remote": {
            "preferred_transport": "public_streamable_http",
            "endpoint_path": "/mcp",
            "status_tool": "jazn_status",
            "turn_tool": "jazn_generate_visible_reply",
            "requires_authenticated_https": True,
            "requires_current_host_connector_invocation": True,
            "fresh_conversation_reverification_required": True,
            "current_message_toolset_observation_required": True,
            "catalog_or_installed_state_sufficient": False,
            "required_chatgpt_turn_tools": list(_REQUIRED_CHATGPT_TURN_TOOLS),
            "plan_name_is_runtime_predicate": False,
            "secure_tunnel_fallback": "openai_secure_mcp_tunnel",
        },
        "truth_boundary": (
            "Materialization proves only that a verified operator exists on disk. "
            "Same-interpreter preflight can reuse the Python process already executing "
            "CHATGPT_BOOTSTRAP.py and does not create a child process, but it does not "
            "create a daemon, connector, accepted turn, or display_exact. If the host "
            "cannot execute Python at all, the ZIP cannot repair that host capability; "
            "use only an actually callable, authenticated Jaźń MCP route."
        ),
    }


def run_materialized_host_preflight_in_process(destination: Path) -> dict[str, object]:
    """Run extracted run.py host-preflight in the current interpreter only."""

    root = Path(destination).resolve()
    run_path = root / "run.py"
    main_path = root / "main.py"
    if not run_path.is_file() or not main_path.is_file():
        raise BootstrapError(
            "materialized operator does not contain run.py/main.py",
            code="post_materialization_operator_missing",
        )

    stdout = io.StringIO()
    stderr = io.StringIO()
    previous_argv = list(sys.argv)
    previous_cwd = Path.cwd()
    previous_path = list(sys.path)
    previous_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "latka_jazn" or name.startswith("latka_jazn.")
    }
    exit_code = 0

    try:
        for name in previous_modules:
            sys.modules.pop(name, None)
        os.chdir(root)
        sys.path.insert(0, str(root))
        sys.argv = [str(run_path), "host-preflight", "--json"]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(run_path), run_name="__main__")
            except SystemExit as exc:
                if exc.code is None:
                    exit_code = 0
                elif isinstance(exc.code, int):
                    exit_code = int(exc.code)
                else:
                    exit_code = 1
    finally:
        for name in [
            name
            for name in list(sys.modules)
            if name == "latka_jazn" or name.startswith("latka_jazn.")
        ]:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)
        sys.argv = previous_argv
        sys.path[:] = previous_path
        os.chdir(previous_cwd)

    raw = stdout.getvalue().strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BootstrapError(
            "post-materialization host-preflight did not return one JSON object",
            code="post_materialization_preflight_invalid_output",
        ) from exc
    if not isinstance(parsed, dict):
        raise BootstrapError(
            "post-materialization host-preflight JSON must be an object",
            code="post_materialization_preflight_invalid_output",
        )

    return {
        "attempted": True,
        "mode": "same_interpreter_no_child_process",
        "exit_code": exit_code,
        "ok": parsed.get("ok") is True,
        "gate_passed": parsed.get("gate_passed") is True,
        "preflight": parsed,
        "stderr_present": bool(stderr.getvalue().strip()),
    }


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
    run_post_materialization_preflight: bool = False,
    reuse_existing_verified: bool = False,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    zip_path = Path(zip_path).resolve()
    destination = Path(destination).resolve()
    sidecar = Path(sha256_file_path).resolve() if sha256_file_path is not None else None
    progress_events: list[dict[str, object]] = []

    def record_progress(
        phase: str,
        wake_percent: int,
        *,
        status: str = "completed",
        detail: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event = _bootstrap_progress_event(
            phase=phase,
            status=status,
            wake_percent=wake_percent,
            detail=detail,
        )
        if (
            progress_events
            and progress_events[-1].get("phase") == event.get("phase")
            and progress_events[-1].get("wake_percent") == event.get("wake_percent")
        ):
            return progress_events[-1]
        progress_events.append(event)
        if progress_callback is not None:
            progress_callback(event)
        return event

    record_progress(
        "executor_probe",
        5,
        detail={
            "evidence": "CHATGPT_BOOTSTRAP.py is executing in the current Python process",
            "external_no_file_probe": "host_responsibility",
        },
    )

    if not zip_path.is_file():
        raise BootstrapError(
            f"system ZIP not found: {zip_path}",
            code="source_not_found",
        )

    expected = _expected_sha256(sidecar=sidecar, explicit=expected_sha256)
    if destination.exists():
        if not reuse_existing_verified:
            raise BootstrapError(
                f"destination already exists; refusing overwrite: {destination}",
                code="destination_exists",
            )
        reuse = _reuse_existing_materialization(
            zip_path=zip_path,
            destination=destination,
            expected_sha256=expected,
            expected_size_bytes=expected_size_bytes,
        )
        record_progress(
            "system_package_verified",
            15,
            detail={
                "sha256": expected,
                "source_size_bytes": reuse["source_size_bytes"],
                "verification_mode": "materialization_stamp_plus_static_manifest",
                "source_zip_rehashed": False,
            },
        )
        record_progress(
            "operator_materialized",
            55,
            detail={
                "destination": str(destination),
                "materialization_mode": "verified_reuse",
                "verified_static_file_count": reuse["verified_static_file_count"],
                "verified_static_bytes": reuse["verified_static_bytes"],
            },
        )
        payload: dict[str, object] = {
            "ok": True,
            "schema_version": BOOTSTRAP_SCHEMA_VERSION,
            "state": "materialized_operator_ready",
            "zip_path": str(zip_path),
            "destination": str(destination),
            "sha256": expected,
            "source_size_bytes": reuse["source_size_bytes"],
            "stable_during_hash": None,
            "source_zip_rehashed": False,
            "reused_existing": True,
            "materialization_mode": "verified_reuse",
            "entry_count": reuse["entry_count"],
            "uncompressed_size_bytes": reuse["uncompressed_size_bytes"],
            "root_prefix": reuse["root_prefix"],
            "operator_entrypoint": "run.py",
            "materialization_stamp": reuse["materialization_stamp"],
            "package_integrity_manifest_sha256": reuse["manifest_sha256"],
            "verified_static_file_count": reuse["verified_static_file_count"],
            "verified_static_bytes": reuse["verified_static_bytes"],
            "progress": progress_events[-1],
            "progress_events": list(progress_events),
            "progress_contract": build_bootstrap_progress_contract(),
            "activation_contract": build_post_materialization_activation_contract(destination),
            "next_step": (
                "Verified existing materialization was reused without reopening, CRC-testing or "
                "decompressing the SYSTEM ZIP. Continue with AGENTS.md / AGENTS.chatgpt.md and "
                "live runtime discovery; a live matching daemon is the warm path, otherwise "
                "the canonical lifecycle owns resume/start integrity and provenance gates."
            ),
        }
        if run_post_materialization_preflight:
            preflight = run_materialized_host_preflight_in_process(destination)
            payload["post_materialization_preflight"] = preflight
            preflight_payload = preflight.get("preflight")
            execution_route = (
                preflight_payload.get("execution_route")
                if isinstance(preflight_payload, dict)
                else None
            )
            record_progress(
                "host_preflight",
                65 if preflight.get("gate_passed") is True else 55,
                status="completed" if preflight.get("gate_passed") is True else "blocked",
                detail={
                    "gate_passed": preflight.get("gate_passed") is True,
                    "execution_route": execution_route,
                    "materialization_mode": "verified_reuse",
                },
            )
            payload["progress"] = progress_events[-1]
            payload["progress_events"] = list(progress_events)
        return payload

    actual, observed_size = sha256_stable_file(
        zip_path,
        expected_size_bytes=expected_size_bytes,
    )
    if actual != expected:
        raise BootstrapError(
            f"SHA-256 mismatch: expected={expected}, actual={actual}",
            code="sha256_mismatch",
        )
    record_progress(
        "system_package_verified",
        15,
        detail={"sha256": actual, "source_size_bytes": observed_size},
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
            record_progress(
                "zip_validated",
                30,
                detail={
                    "entry_count": entry_count,
                    "uncompressed_size_bytes": total_bytes,
                    "root_prefix": root_prefix or None,
                },
            )
            last_extract_bucket = -1

            def on_extract_progress(written: int, total: int) -> None:
                nonlocal last_extract_bucket
                if total <= 0:
                    return
                fraction = min(1.0, max(0.0, written / total))
                bucket = min(100, int(fraction * 100))
                if bucket < 100 and bucket < last_extract_bucket + 5:
                    return
                last_extract_bucket = bucket
                wake_percent = 30 + round(fraction * 25)
                record_progress(
                    "operator_materializing",
                    wake_percent,
                    status="in_progress" if bucket < 100 else "completed",
                    detail={
                        "bytes_written": written,
                        "bytes_total": total,
                        "extract_percent": bucket,
                    },
                )

            extracted_bytes = _safe_extract_validated_zip(
                zf,
                staging,
                max_total_bytes=max_total_bytes,
                max_member_bytes=max_member_bytes,
                progress_callback=on_extract_progress,
                progress_total_bytes=total_bytes,
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
        try:
            materialization_stamp = _write_materialization_stamp(
                destination,
                source_zip_sha256=actual,
                source_size_bytes=observed_size,
                root_prefix=root_prefix,
                entry_count=entry_count,
                uncompressed_size_bytes=total_bytes,
            )
        except BootstrapError as exc:
            materialization_stamp = {
                "written": False,
                "path": str(_materialization_stamp_path(destination)),
                "error_code": exc.code,
                "error": str(exc),
            }
        record_progress(
            "operator_materialized",
            55,
            detail={"destination": str(destination)},
        )
        payload: dict[str, object] = {
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
            "reused_existing": False,
            "materialization_mode": "cold_extract",
            "source_zip_rehashed": True,
            "materialization_stamp": materialization_stamp,
            "progress": progress_events[-1],
            "progress_events": list(progress_events),
            "progress_contract": build_bootstrap_progress_contract(),
            "activation_contract": build_post_materialization_activation_contract(destination),
            "next_step": (
                "Read AGENTS.md and AGENTS.chatgpt.md. If this bootstrap is already executing "
                "in a usable Python host, prefer --post-materialization-preflight. After a positive "
                "local gate, start and verify the daemon through the central control-plane subcommands, then "
                "open the chatgpt_bridge control_plane_argv as one persistent stdin/stdout bridge "
                "when the host can retain it. Do not add --model and do not require OPENAI_API_KEY "
                "for chat-gpt. If process execution is unavailable, use only a verified callable "
                "remote Jaźń MCP route or an explicitly accepted host handoff."
            ),
        }
        if run_post_materialization_preflight:
            preflight = run_materialized_host_preflight_in_process(destination)
            payload["post_materialization_preflight"] = preflight
            preflight_payload = preflight.get("preflight")
            execution_route = (
                preflight_payload.get("execution_route")
                if isinstance(preflight_payload, dict)
                else None
            )
            record_progress(
                "host_preflight",
                65 if preflight.get("gate_passed") is True else 55,
                status="completed" if preflight.get("gate_passed") is True else "blocked",
                detail={
                    "gate_passed": preflight.get("gate_passed") is True,
                    "execution_route": execution_route,
                },
            )
            payload["progress"] = progress_events[-1]
            payload["progress_events"] = list(progress_events)
        return payload
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
    parser.add_argument(
        "--reuse-existing-verified",
        action="store_true",
        help=(
            "When destination already exists, reuse it only after the external "
            "materialization stamp and every static PACKAGE_INTEGRITY_MANIFEST.json "
            "member pass verification. The SYSTEM ZIP is not rehashed, CRC-tested "
            "or decompressed on this fast path."
        ),
    )
    parser.add_argument(
        "--post-materialization-preflight",
        action="store_true",
        help=(
            "After verified extraction, run only run.py host-preflight --json in the same "
            "Python interpreter. This does not spawn a child process or claim runtime activation."
        ),
    )
    parser.add_argument(
        "--progress-jsonl",
        action="store_true",
        help=(
            "Emit evidence-backed bootstrap progress events as JSONL on stderr while "
            "keeping the final result as one JSON object on stdout."
        ),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    captured_progress: list[dict[str, object]] = []

    def capture_progress(event: dict[str, object]) -> None:
        captured_progress.append(dict(event))
        if ns.progress_jsonl:
            print(
                json.dumps(event, ensure_ascii=False, sort_keys=True),
                file=sys.stderr,
                flush=True,
            )

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
            run_post_materialization_preflight=ns.post_materialization_preflight,
            reuse_existing_verified=ns.reuse_existing_verified,
            progress_callback=capture_progress,
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
            "progress": captured_progress[-1] if captured_progress else None,
            "progress_events": captured_progress,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
