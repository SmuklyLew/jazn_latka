from __future__ import annotations

"""Bounded compatibility for current pack-generator v2 transports.

The adapter translates transport metadata only. It never trusts package bytes
without rechecking declared sizes/SHA-256, and it never changes SYSTEM/MEMORY
semantics. Consumers still pass the adapted transport through the mature
package verification/extraction pipeline.
"""

from collections.abc import Collection
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from latka_jazn.packaging.zip_resource_limits import ZipResourceLimits


PACK_GENERATOR_V2 = "jazn_pack_generator_package/v2"
LEGACY_COMPAT_SCHEMA = "jazn_package_set/v3"
CHUNK_SIZE = 8 * 1024 * 1024


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified(
    source: Path,
    destination: Path,
    expected_sha: str | None,
    expected_size: int | None,
) -> None:
    source = Path(source).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected_size is not None and source.stat().st_size != int(expected_size):
        raise ValueError(f"package transport size mismatch for {source.name}")
    if expected_sha and sha256_file(source) != expected_sha.lower():
        raise ValueError(f"package transport sha256 mismatch for {source.name}")
    tmp = destination.with_name(f".{destination.name}.copying.tmp")
    try:
        shutil.copy2(source, tmp)
        if expected_size is not None and tmp.stat().st_size != int(expected_size):
            raise ValueError(f"copied package transport size mismatch for {source.name}")
        if expected_sha and sha256_file(tmp) != expected_sha.lower():
            raise ValueError(f"copied package transport sha256 mismatch for {source.name}")
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)


def discover_generator_sidecar(
    parts_dir: Path,
    zip_name: str | None = None,
    *,
    allowed_contents: Collection[str] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    """Discover one generator-v2 sidecar after semantic content filtering.

    Filtering happens before ambiguity detection, so a colocated SYSTEM and
    MEMORY transport do not make each other ambiguous.
    """

    directory = Path(parts_dir).expanduser().resolve()
    allowed = (
        {str(item).strip().lower() for item in allowed_contents}
        if allowed_contents is not None
        else None
    )
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        if ".package" not in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != PACK_GENERATOR_V2:
            continue
        content = str(payload.get("content") or "").strip().lower()
        if allowed is not None and content not in allowed:
            continue
        archive = _mapping(payload.get("archive"))
        logical = str(archive.get("logical_filename") or "").strip()
        if not logical.lower().endswith(".zip"):
            continue
        if zip_name and logical != str(zip_name).strip():
            continue
        candidates.append((path, payload))
    if len(candidates) > 1:
        names = [
            str(_mapping(item[1].get("archive")).get("logical_filename") or item[0].name)
            for item in candidates
        ]
        raise ValueError(
            "more than one jazn_pack_generator_package/v2 package matched "
            f"content filter; pass an explicit ZIP name: {names}"
        )
    return candidates[0] if candidates else None


def _find_transport_file(
    parts_dir: Path,
    canonical_name: str,
    sha256: str | None,
    size_bytes: int | None,
) -> Path:
    exact = Path(parts_dir) / canonical_name
    if exact.is_file():
        return exact
    matches: list[Path] = []
    for candidate in Path(parts_dir).iterdir():
        if not candidate.is_file():
            continue
        if size_bytes is not None and candidate.stat().st_size != int(size_bytes):
            continue
        if sha256 and sha256_file(candidate) != sha256.lower():
            continue
        matches.append(candidate)
    if len(matches) != 1:
        raise FileNotFoundError(f"cannot uniquely resolve transport file {canonical_name!r}")
    return matches[0]


def _compat_entries(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = _mapping(payload.get("source"))
    raw_entries = source.get("entries")
    result: list[dict[str, Any]] = []
    for raw in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("kind") or "file").strip().lower() == "directory":
            continue
        path = str(raw.get("path") or "").replace("\\", "/").strip()
        if not path:
            continue
        item: dict[str, Any] = {
            "path": path,
            "size_bytes": int(raw.get("size_bytes") or 0),
        }
        digest = str(raw.get("sha256") or "").strip().lower()
        if digest:
            item["sha256"] = digest
        result.append(item)
    return result



def normalize_generator_v2_compat(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Translate generator-v2 metadata without copying package bytes.

    Runtime attach uses this view directly against the already uploaded source
    files. The older materializing adapter remains available for explicit
    tooling/migration workflows, but normal MEMORY convergence must not create
    a second transport copy merely to normalize sidecar metadata.
    """

    archive = _mapping(payload.get("archive"))
    logical_name = str(archive.get("logical_filename") or "").strip()
    if (
        not logical_name.lower().endswith(".zip")
        or Path(logical_name).name != logical_name
        or "/" in logical_name
        or "\\" in logical_name
    ):
        raise ValueError("generator-v2 logical archive filename must be a simple .zip filename")
    logical_sha = str(archive.get("logical_sha256") or "").strip().lower() or None
    logical_size = (
        int(archive["logical_size_bytes"])
        if archive.get("logical_size_bytes") is not None
        else None
    )
    content = str(payload.get("content") or "").strip().lower()
    profile = {
        "system": "system",
        "memory": "memory",
        "system+memory": "combined",
    }.get(content)
    if profile is None:
        raise ValueError(f"unsupported generator package content: {content!r}")

    split = _mapping(payload.get("split"))
    raw_parts = split.get("parts")
    split_parts = raw_parts if isinstance(raw_parts, list) else []
    outputs: list[dict[str, Any]] = []
    if split_parts:
        for index, raw in enumerate(split_parts, start=1):
            if not isinstance(raw, Mapping):
                raise ValueError("invalid split.parts record")
            filename = str(raw.get("filename") or "").strip()
            if (
                not filename
                or Path(filename).name != filename
                or "/" in filename
                or "\\" in filename
            ):
                raise ValueError(f"invalid generator-v2 transport filename: {filename!r}")
            outputs.append(
                {
                    "part_no": int(raw.get("part_no") or index),
                    "filename": filename,
                    "size_bytes": (
                        int(raw["size_bytes"])
                        if raw.get("size_bytes") is not None
                        else None
                    ),
                    "sha256": str(raw.get("sha256") or "").strip().lower() or None,
                    "is_complete_zip": False,
                }
            )
    else:
        outputs.append(
            {
                "part_no": 1,
                "filename": logical_name,
                "size_bytes": logical_size,
                "sha256": logical_sha,
                "is_complete_zip": True,
            }
        )

    return {
        "schema_version": LEGACY_COMPAT_SCHEMA,
        "package_name": logical_name,
        "profile": profile,
        "archive_format": "binary",
        "package_version": str(payload.get("package_version") or "").strip() or None,
        "logical_zip_sha256": logical_sha,
        "logical_zip_size_bytes": logical_size,
        "outputs": outputs,
        "entries": _compat_entries(payload),
        "compatibility_source_schema": PACK_GENERATOR_V2,
        "compatibility_source_content": content,
        "runtime_metadata_only_adapter": True,
        "truth_boundary": (
            "This sidecar is an in-memory transport compatibility projection. "
            "No package bytes were copied; source bytes remain subject to the "
            "same size/SHA/member verification during streaming MEMORY attach."
        ),
    }

def materialize_generator_v2_compat(
    parts_dir: Path,
    payload: Mapping[str, Any],
    compat_dir: Path,
) -> str:
    """Materialize a verified legacy-shaped sidecar/transport view."""

    source_dir = Path(parts_dir).expanduser().resolve()
    destination = Path(compat_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    archive = _mapping(payload.get("archive"))
    logical_name = str(archive.get("logical_filename") or "").strip()
    if not logical_name.lower().endswith(".zip"):
        raise ValueError("generator-v2 logical archive filename must end with .zip")
    logical_sha = str(archive.get("logical_sha256") or "").strip().lower() or None
    logical_size = (
        int(archive["logical_size_bytes"])
        if archive.get("logical_size_bytes") is not None
        else None
    )
    content = str(payload.get("content") or "").strip().lower()
    profile = {
        "system": "system",
        "memory": "memory",
        "system+memory": "combined",
    }.get(content)
    if profile is None:
        raise ValueError(f"unsupported generator package content: {content!r}")

    split = _mapping(payload.get("split"))
    raw_parts = split.get("parts")
    split_parts = raw_parts if isinstance(raw_parts, list) else []
    outputs: list[dict[str, Any]] = []
    if split_parts:
        for index, raw in enumerate(split_parts, start=1):
            if not isinstance(raw, Mapping):
                raise ValueError("invalid split.parts record")
            filename = str(raw.get("filename") or "").strip()
            sha = str(raw.get("sha256") or "").strip().lower() or None
            size = int(raw["size_bytes"]) if raw.get("size_bytes") is not None else None
            source = _find_transport_file(source_dir, filename, sha, size)
            _copy_verified(source, destination / filename, sha, size)
            outputs.append(
                {
                    "part_no": int(raw.get("part_no") or index),
                    "filename": filename,
                    "size_bytes": size,
                    "sha256": sha,
                    "is_complete_zip": False,
                }
            )
    else:
        source = _find_transport_file(source_dir, logical_name, logical_sha, logical_size)
        _copy_verified(source, destination / logical_name, logical_sha, logical_size)
        outputs.append(
            {
                "part_no": 1,
                "filename": logical_name,
                "size_bytes": logical_size,
                "sha256": logical_sha,
                "is_complete_zip": True,
            }
        )

    compat = {
        "schema_version": LEGACY_COMPAT_SCHEMA,
        "package_name": logical_name,
        "profile": profile,
        "archive_format": "binary",
        "package_version": str(payload.get("package_version") or "").strip() or None,
        "logical_zip_sha256": logical_sha,
        "outputs": outputs,
        "entries": _compat_entries(payload),
        "compatibility_source_schema": PACK_GENERATOR_V2,
        "compatibility_source_content": content,
        "truth_boundary": (
            "This sidecar is a verified transport compatibility projection only. "
            "Package bytes remain subject to canonical SYSTEM/MEMORY verification."
        ),
    }
    (destination / f"{logical_name}.package.json").write_text(
        json.dumps(compat, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if logical_sha:
        (destination / f"{logical_name}.sha256").write_text(
            f"{logical_sha}  {logical_name}\n",
            encoding="ascii",
        )
    return logical_name


def memory_package_requires_v3_repack(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    """Decide whether a legacy/generator-compat MEMORY needs safe v3 transport."""

    if (
        str(sidecar.get("memory_manifest_schema") or "").strip()
        == "jazn_memory_package_manifest/v3"
    ):
        return {"required": False, "reason": "memory_transport_v3"}

    limits = ZipResourceLimits.from_env()
    entries = [item for item in sidecar.get("entries") or [] if isinstance(item, Mapping)]
    total = sum(max(0, int(item.get("size_bytes") or 0)) for item in entries)
    oversized = [
        str(item.get("path") or "")
        for item in entries
        if int(item.get("size_bytes") or 0) > limits.max_member_uncompressed_bytes
    ]
    archive_format = str(sidecar.get("archive_format") or "").strip().lower()
    required = bool(
        oversized
        or (archive_format == "binary" and total > limits.max_total_uncompressed_bytes)
    )
    return {
        "required": required,
        "reason": (
            "legacy_transport_exceeds_safe_zip_limits"
            if required
            else "legacy_transport_within_safe_zip_limits"
        ),
        "archive_format": archive_format,
        "declared_total_uncompressed_bytes": total,
        "oversized_members": oversized[:16],
        "limits": limits.to_dict(),
    }


__all__ = [
    "LEGACY_COMPAT_SCHEMA",
    "PACK_GENERATOR_V2",
    "discover_generator_sidecar",
    "materialize_generator_v2_compat",
    "normalize_generator_v2_compat",
    "memory_package_requires_v3_repack",
    "sha256_file",
]
