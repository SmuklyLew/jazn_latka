from __future__ import annotations

"""Standalone, stdlib-only bootstrap for a Jaźń system ZIP.

This file is intentionally independent from ``latka_jazn``.  It exists for the
one state in which a ChatGPT host has a verified system ZIP but no unpacked
``run.py`` operator yet.  It performs only bounded package verification and
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
DEFAULT_MAX_ENTRIES = 100_000
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
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
    """Fail-closed bootstrap error with no runtime side effects."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_sha256(*, sidecar: Path | None, explicit: str | None) -> str:
    candidate = str(explicit or "").strip()
    if sidecar is not None:
        if candidate:
            raise BootstrapError("pass either --sha256-file or --expected-sha256, not both")
        try:
            text = sidecar.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise BootstrapError(f"cannot read SHA-256 sidecar: {sidecar}") from exc
        tokens = text.strip().split()
        candidate = tokens[0] if tokens else ""
    if not _SHA256_RE.fullmatch(candidate):
        raise BootstrapError("a valid 64-hex SHA-256 is required before ZIP inspection")
    return candidate.lower()


def _normalized_member_name(info: zipfile.ZipInfo) -> str:
    raw = info.filename
    if not raw or "\x00" in raw:
        raise BootstrapError("ZIP contains an empty or NUL-bearing member name")
    if "\\" in raw:
        raise BootstrapError(f"ZIP member uses non-canonical backslashes: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise BootstrapError(f"unsafe ZIP member path: {raw!r}")
    if path.parts and re.fullmatch(r"[A-Za-z]:", path.parts[0]):
        raise BootstrapError(f"drive-qualified ZIP member path: {raw!r}")
    normalized = path.as_posix().rstrip("/")
    if normalized in {"", "."}:
        raise BootstrapError(f"invalid ZIP member path: {raw!r}")

    if info.create_system == 3:
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_ISLNK(mode):
            raise BootstrapError(f"ZIP symlink rejected: {raw!r}")
        file_type = stat.S_IFMT(mode) if mode else 0
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise BootstrapError(f"special ZIP filesystem entry rejected: {raw!r}")
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
            "system ZIP must expose exactly one canonical Jaźń root at archive root or one top-level directory"
        )
    return candidates[0]


def inspect_system_zip(
    zf: zipfile.ZipFile,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> tuple[str, int, int]:
    infos = zf.infolist()
    if not infos:
        raise BootstrapError("system ZIP is empty")
    if len(infos) > int(max_entries):
        raise BootstrapError(f"ZIP entry limit exceeded: {len(infos)} > {max_entries}")

    names: set[str] = set()
    total_bytes = 0
    for info in infos:
        normalized = _normalized_member_name(info)
        if normalized in names:
            raise BootstrapError(f"duplicate ZIP member rejected: {normalized!r}")
        names.add(normalized)
        size = int(info.file_size)
        if size < 0 or size > int(max_member_bytes):
            raise BootstrapError(f"ZIP member size limit exceeded: {normalized!r}")
        total_bytes += size
        if total_bytes > int(max_total_bytes):
            raise BootstrapError(
                f"ZIP uncompressed-size limit exceeded: {total_bytes} > {max_total_bytes}"
            )

    root_prefix = _resolve_root_prefix(names)
    bad_member = zf.testzip()
    if bad_member is not None:
        raise BootstrapError(f"ZIP CRC verification failed for: {bad_member}")
    return root_prefix, len(infos), total_bytes


def bootstrap_system_zip(
    *,
    zip_path: Path,
    destination: Path,
    sha256_file_path: Path | None = None,
    expected_sha256: str | None = None,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> dict[str, object]:
    zip_path = Path(zip_path).resolve()
    destination = Path(destination).resolve()
    sidecar = Path(sha256_file_path).resolve() if sha256_file_path is not None else None

    if not zip_path.is_file():
        raise BootstrapError(f"system ZIP not found: {zip_path}")
    if destination.exists():
        raise BootstrapError(f"destination already exists; refusing overwrite: {destination}")

    expected = _expected_sha256(sidecar=sidecar, explicit=expected_sha256)
    actual = sha256_file(zip_path)
    if actual != expected:
        raise BootstrapError(f"SHA-256 mismatch: expected={expected}, actual={actual}")

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
            )
            zf.extractall(staging)

        root = staging if not root_prefix else staging / root_prefix.rstrip("/")
        if not root.is_dir():
            raise BootstrapError("validated archive root was not materialized as a directory")
        missing = sorted(
            required for required in _REQUIRED_ROOT_FILES if not (root / required).is_file()
        )
        if missing:
            raise BootstrapError(f"materialized system root is incomplete: {missing}")

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
            "entry_count": entry_count,
            "uncompressed_size_bytes": total_bytes,
            "root_prefix": root_prefix or None,
            "next_step": "Read AGENTS.md, then invoke the extracted run.py for host-preflight/doctor/start/status.",
        }
    except (OSError, zipfile.BadZipFile) as exc:
        raise BootstrapError(f"system ZIP bootstrap failed: {type(exc).__name__}: {exc}") from exc
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
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-member-bytes", type=int, default=DEFAULT_MAX_MEMBER_BYTES)
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
            max_entries=ns.max_entries,
            max_total_bytes=ns.max_total_bytes,
            max_member_bytes=ns.max_member_bytes,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except BootstrapError as exc:
        payload = {
            "ok": False,
            "schema_version": BOOTSTRAP_SCHEMA_VERSION,
            "state": "bootstrap_failed",
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
