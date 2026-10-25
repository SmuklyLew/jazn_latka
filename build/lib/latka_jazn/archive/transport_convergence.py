from __future__ import annotations

"""Transport/materialization hardening for archive package sets."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Sequence
import unicodedata

from latka_jazn.archive.service import (
    CHUNK_SIZE,
    SUPPORTED_PACKAGE_SCHEMAS,
    ArchiveError,
    ArchiveSecurityLimits,
    _check_free_space,
)

MAX_TRANSPORT_SIDECAR_CANDIDATES = 256
MAX_TRANSPORT_OUTPUT_CANDIDATES = 1024
_SPLIT_SUFFIX = re.compile(r"\.\d{3,4}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
    )


def sha256_stable_file(path: Path, *, expected_size_bytes: int | None = None) -> tuple[str, int]:
    """Hash one materialized file and reject concurrent replace/write races."""

    path = Path(path).resolve()
    try:
        path_before = path.stat()
        with path.open("rb") as handle:
            fd_before = os.fstat(handle.fileno())
            if _file_identity(path_before) != _file_identity(fd_before):
                raise ArchiveError(f"package_input_not_ready:{path.name}")
            observed_size = int(fd_before.st_size)
            if expected_size_bytes is not None and observed_size != int(expected_size_bytes):
                raise ArchiveError(
                    f"package_input_size_mismatch:{path.name}:{observed_size}!={int(expected_size_bytes)}"
                )
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
            fd_after = os.fstat(handle.fileno())
        path_after = path.stat()
    except ArchiveError:
        raise
    except OSError as exc:
        raise ArchiveError(f"package_input_read_failed:{path}:{exc}") from exc
    identity = _file_identity(fd_before)
    if identity != _file_identity(fd_after) or identity != _file_identity(path_after):
        raise ArchiveError(f"package_input_not_ready:{path.name}")
    return digest.hexdigest(), observed_size


def transport_name_key(name: str) -> str:
    """Remove host copy suffixes like ``(1)`` without treating the name as proof."""

    value = unicodedata.normalize("NFC", str(name or "")).casefold()
    previous = None
    while value != previous:
        previous = value
        value = re.sub(r"\s*\(\d+\)(?=(?:\.[^./\\]+)+$)", "", value)
    return value


def _resolve_output(
    parent: Path,
    *,
    logical_filename: str,
    expected_size: int,
    expected_sha256: str,
    used_paths: set[Path],
) -> tuple[Path, bool]:
    parent = parent.resolve()
    exact = (parent / logical_filename).resolve()
    try:
        exact.relative_to(parent)
    except ValueError as exc:
        raise ArchiveError(f"package_output_escapes_directory:{logical_filename}") from exc

    expected_sha256 = str(expected_sha256).lower()
    if exact.exists():
        if exact.is_symlink() or not exact.is_file():
            raise ArchiveError(f"package_output_not_regular_file:{logical_filename}")
        try:
            if int(exact.stat().st_size) != int(expected_size):
                raise ArchiveError(f"package_output_size_mismatch:{logical_filename}")
        except OSError as exc:
            raise ArchiveError(f"package_input_read_failed:{exact}:{exc}") from exc
        try:
            digest, observed = sha256_stable_file(exact, expected_size_bytes=int(expected_size))
        except ArchiveError as exc:
            if str(exc).startswith("package_input_size_mismatch:"):
                raise ArchiveError(f"package_input_not_ready:{exact.name}") from exc
            raise
        if observed != int(expected_size):
            raise ArchiveError(f"package_input_not_ready:{exact.name}")
        if digest != expected_sha256:
            raise ArchiveError(f"package_output_sha256_mismatch:{logical_filename}")
        if exact in used_paths:
            raise ArchiveError(f"package_output_physical_reuse:{logical_filename}")
        used_paths.add(exact)
        return exact, False

    logical_key = transport_name_key(logical_filename)
    suffix_hint = Path(logical_filename).suffix.casefold()
    preferred: list[Path] = []
    fallback: list[Path] = []
    scanned = 0
    try:
        siblings = sorted(parent.iterdir(), key=lambda item: item.name.casefold())
    except OSError as exc:
        raise ArchiveError(f"package_output_directory_unreadable:{parent}:{exc}") from exc
    for candidate in siblings:
        if candidate in used_paths or candidate.is_symlink() or not candidate.is_file():
            continue
        scanned += 1
        if scanned > MAX_TRANSPORT_OUTPUT_CANDIDATES:
            raise ArchiveError(f"package_transport_candidate_limit_exceeded:{MAX_TRANSPORT_OUTPUT_CANDIDATES}")
        try:
            if int(candidate.stat().st_size) != int(expected_size):
                continue
        except OSError:
            continue
        if transport_name_key(candidate.name) == logical_key:
            preferred.append(candidate.resolve())
        elif suffix_hint and candidate.suffix.casefold() == suffix_hint:
            fallback.append(candidate.resolve())

    matches: list[Path] = []
    for candidate in preferred or fallback:
        digest, observed = sha256_stable_file(candidate, expected_size_bytes=int(expected_size))
        if observed == int(expected_size) and digest == expected_sha256:
            matches.append(candidate)
    if not matches:
        raise ArchiveError(f"package_output_missing:{logical_filename}")
    if len(matches) != 1:
        names = ",".join(item.name for item in matches[:8])
        raise ArchiveError(f"package_output_transport_alias_ambiguous:{logical_filename}:{names}")
    resolved = matches[0]
    used_paths.add(resolved)
    return resolved, True


class ArchiveTransportConvergenceMixin:
    """Add transport-renamed sidecar/output resolution to the stable service."""

    limits: ArchiveSecurityLimits

    @staticmethod
    def _try_load_supported_sidecar(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if str(payload.get("schema_version") or "") not in SUPPORTED_PACKAGE_SCHEMAS:
            return None
        if not isinstance(payload.get("outputs"), list):
            return None
        return payload

    @classmethod
    def _discover_package_sidecar(cls, source: Path) -> Path | None:
        source = Path(source).expanduser()
        if source.is_file() and cls._try_load_supported_sidecar(source) is not None:
            return source.resolve()

        exact_candidates = [source.parent / f"{source.name}.package.json"] if source.is_file() else [Path(str(source) + ".package.json")]
        if _SPLIT_SUFFIX.search(source.name):
            exact_candidates.append(Path(_SPLIT_SUFFIX.sub("", str(source)) + ".package.json"))
        for candidate in exact_candidates:
            if candidate.is_file() and cls._try_load_supported_sidecar(candidate) is not None:
                return candidate.resolve()
        if not source.is_file():
            return None

        parent = source.parent.resolve()
        normalized_source = transport_name_key(source.name)
        expected_sidecar_key = (
            _SPLIT_SUFFIX.sub("", normalized_source) + ".package.json"
            if _SPLIT_SUFFIX.search(normalized_source)
            else None
        )
        sidecars: list[tuple[Path, dict[str, Any]]] = []
        scanned = 0
        try:
            siblings = sorted(parent.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ArchiveError(f"package_sidecar_directory_unreadable:{parent}:{exc}") from exc
        for candidate in siblings:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.suffix.casefold() != ".json" or "package" not in candidate.name.casefold():
                continue
            scanned += 1
            if scanned > MAX_TRANSPORT_SIDECAR_CANDIDATES:
                raise ArchiveError(f"package_sidecar_candidate_limit_exceeded:{MAX_TRANSPORT_SIDECAR_CANDIDATES}")
            payload = cls._try_load_supported_sidecar(candidate)
            if payload is not None:
                sidecars.append((candidate.resolve(), payload))

        if expected_sidecar_key is not None:
            by_name = [path for path, _ in sidecars if transport_name_key(path.name) == expected_sidecar_key]
            if len(by_name) == 1:
                return by_name[0]
            if len(by_name) > 1:
                raise ArchiveError("package_sidecar_discovery_ambiguous")

        try:
            source_size = int(source.stat().st_size)
        except OSError as exc:
            raise ArchiveError(f"package_input_read_failed:{source}:{exc}") from exc
        source_digest: str | None = None
        matches: list[Path] = []
        for path, payload in sidecars:
            rows = payload.get("outputs")
            if not isinstance(rows, list):
                continue
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                try:
                    expected_size = int(raw.get("size_bytes"))
                    expected_sha = str(raw.get("sha256") or "").lower()
                except (TypeError, ValueError):
                    continue
                if expected_size != source_size or _SHA256.fullmatch(expected_sha) is None:
                    continue
                if source_digest is None:
                    source_digest, observed = sha256_stable_file(source, expected_size_bytes=source_size)
                    if observed != source_size:
                        raise ArchiveError(f"package_input_not_ready:{source.name}")
                if source_digest == expected_sha:
                    matches.append(path)
                    break
        unique = sorted(set(matches), key=lambda item: item.name.casefold())
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            raise ArchiveError("package_sidecar_discovery_ambiguous")
        if _SPLIT_SUFFIX.search(source.name):
            raise ArchiveError("split_archive_requires_verified_package_sidecar")
        return None

    def extract_source(
        self,
        source: Path,
        destination: Path,
        *,
        archive_format: str | None = None,
        password: str | bytes | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        source = Path(source).expanduser()
        destination = Path(destination).expanduser().resolve()
        sidecar = self._discover_package_sidecar(source)
        if sidecar is not None:
            return self.extract_package_sidecar(  # type: ignore[attr-defined]
                sidecar,
                destination,
                password=password,
                replace_existing=replace_existing,
            )
        source = source.resolve()
        inspection = self.inspect(source, archive_format=archive_format, password=password, verify_crc=True)  # type: ignore[attr-defined]
        _check_free_space(destination.parent, inspection.total_uncompressed_bytes, self.limits)
        staging = self._new_staging(destination)  # type: ignore[attr-defined]
        try:
            self._extract_archive_to(source, staging, inspection.archive_format, password=password)  # type: ignore[attr-defined]
            self._verify_extracted_tree(staging, inspection.entries, expected=None)  # type: ignore[attr-defined]
            self._commit_staging(staging, destination, replace_existing=replace_existing)  # type: ignore[attr-defined]
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return {
            "ok": True,
            "source": str(source),
            "destination": str(destination),
            "container_format": inspection.archive_format,
            "entry_count": len(inspection.entries),
            "total_uncompressed_bytes": inspection.total_uncompressed_bytes,
            "encrypted": inspection.encrypted,
            "security_limits": self.limits.to_dict(),
        }

    @staticmethod
    def _verified_outputs(parent: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("outputs")
        if not isinstance(rows, list) or not rows:
            raise ArchiveError("package_sidecar_outputs_missing")
        outputs: list[dict[str, Any]] = []
        used_paths: set[Path] = set()
        for raw in rows:
            if not isinstance(raw, dict):
                raise ArchiveError("package_sidecar_output_invalid")
            item = {
                "part_no": int(raw["part_no"]),
                "filename": str(raw["filename"]),
                "size_bytes": int(raw["size_bytes"]),
                "sha256": str(raw["sha256"]).lower(),
            }
            if _SHA256.fullmatch(str(item["sha256"])) is None:
                raise ArchiveError(f"package_output_sha256_invalid:{item['filename']}")
            logical = str(item["filename"])
            path, aliased = _resolve_output(
                parent,
                logical_filename=logical,
                expected_size=int(item["size_bytes"]),
                expected_sha256=str(item["sha256"]),
                used_paths=used_paths,
            )
            item["logical_filename"] = logical
            item["filename"] = path.name
            item["transport_alias_used"] = aliased
            outputs.append(item)
        outputs.sort(key=lambda item: int(item["part_no"]))
        numbers = [int(item["part_no"]) for item in outputs]
        if numbers != list(range(1, len(outputs) + 1)):
            raise ArchiveError(f"package_output_part_sequence_invalid:{numbers}")
        expected_set_hash = str(payload.get("package_set_sha256") or "").strip().lower()
        if expected_set_hash:
            digest = hashlib.sha256()
            for item in outputs:
                digest.update(
                    f"{item['part_no']}\0{item['logical_filename']}\0{item['size_bytes']}\0{item['sha256']}\n".encode("utf-8")
                )
            if digest.hexdigest() != expected_set_hash:
                raise ArchiveError("package_set_sha256_mismatch")
        return outputs

    @staticmethod
    def join_parts(
        parts: Sequence[Path],
        output: Path,
        *,
        expected_sha256: Sequence[str] | None = None,
        logical_sha256: str | None = None,
    ) -> str:
        if not parts:
            raise ArchiveError("split_parts_missing")
        if expected_sha256 is not None and len(expected_sha256) != len(parts):
            raise ArchiveError("split_part_hash_count_mismatch")
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ArchiveError(f"join_output_exists:{output}")
        logical = hashlib.sha256()
        try:
            with output.open("xb") as target:
                for index, raw in enumerate(parts):
                    part = Path(raw).resolve()
                    if part.is_symlink() or not part.is_file():
                        raise ArchiveError(f"split_part_missing:{part}")
                    try:
                        path_before = part.stat()
                        with part.open("rb") as source:
                            fd_before = os.fstat(source.fileno())
                            if _file_identity(path_before) != _file_identity(fd_before):
                                raise ArchiveError(f"package_input_not_ready:{part.name}")
                            digest = hashlib.sha256()
                            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                                digest.update(chunk)
                                logical.update(chunk)
                                target.write(chunk)
                            fd_after = os.fstat(source.fileno())
                        path_after = part.stat()
                    except ArchiveError:
                        raise
                    except OSError as exc:
                        raise ArchiveError(f"package_input_read_failed:{part}:{exc}") from exc
                    identity = _file_identity(fd_before)
                    if identity != _file_identity(fd_after) or identity != _file_identity(path_after):
                        raise ArchiveError(f"package_input_not_ready:{part.name}")
                    if expected_sha256 is not None and digest.hexdigest() != str(expected_sha256[index]).lower():
                        raise ArchiveError(f"split_part_sha256_mismatch:{part.name}")
            actual = logical.hexdigest()
            if logical_sha256 and actual != str(logical_sha256).lower():
                raise ArchiveError("logical_archive_sha256_mismatch")
            return actual
        except Exception:
            output.unlink(missing_ok=True)
            raise
