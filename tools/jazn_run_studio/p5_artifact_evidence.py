"""Read-only P5 frozen artifact inspection; not a release or malware verdict."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

_MAX_EXE_BYTES = 256 * 1024 * 1024
_MAX_INFO_BYTES = 1024 * 1024
_BUNDLE_MANIFEST = "STUDIO_BUNDLE_MANIFEST.json"
_MAX_BUNDLE_MANIFEST_BYTES = 2 * 1024 * 1024
_MAX_BUNDLE_FILES = 20000
_MAX_BUNDLE_BYTES = 4 * 1024 * 1024 * 1024


def _bundle_inventory(bundle: Path) -> list[dict[str, Any]]:
    """Read-only, bounded, case-insensitive inventory; rejects symlink entries."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("bundle_not_directory")
    entries: list[dict[str, Any]] = []
    keys: set[str] = set()
    total = 0
    for file in bundle.rglob("*"):
        if file.is_symlink():
            raise ValueError("bundle_link_forbidden")
        if not file.is_file():
            continue
        relative = file.relative_to(bundle).as_posix()
        if relative == _BUNDLE_MANIFEST:
            continue
        key = relative.casefold()
        if key in keys:
            raise ValueError("bundle_path_collision")
        keys.add(key)
        if len(entries) >= _MAX_BUNDLE_FILES:
            raise ValueError("bundle_file_limit")
        size = file.stat().st_size
        total += size
        if size < 0 or total > _MAX_BUNDLE_BYTES:
            raise ValueError("bundle_size_limit")
        digest = sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append({"path": relative, "size": size, "sha256": digest.hexdigest()})
    return sorted(entries, key=lambda e: e["path"])


def write_frozen_bundle_manifest(bundle: Path) -> None:
    """Build-time inventory of all onedir files; excludes only this manifest."""
    target = bundle / _BUNDLE_MANIFEST
    if target.exists() or target.is_symlink():
        raise ValueError("bundle_manifest_exists")
    inventory = _bundle_inventory(bundle)
    target.write_text(json.dumps(
        {"schema": "jazn_studio_bundle_inventory/v1", "files": inventory},
        ensure_ascii=False, indent=2,
    ) + "\n", encoding="utf-8")


def verify_frozen_bundle_manifest(bundle: Path) -> tuple[bool, int]:
    """Integrity is never treated as proof of malware clearance."""
    target = bundle / _BUNDLE_MANIFEST
    try:
        if target.is_symlink() or not target.is_file():
            return False, 0
        if target.stat().st_size > _MAX_BUNDLE_MANIFEST_BYTES:
            return False, 0
        content = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or content.get("schema") != "jazn_studio_bundle_inventory/v1":
            return False, 0
        expected = content.get("files")
        if not isinstance(expected, list) or len(expected) > _MAX_BUNDLE_FILES:
            return False, 0
        observed = _bundle_inventory(bundle)
        return observed == expected and bool(observed), len(observed)
    except (OSError, UnicodeError, ValueError):
        return False, 0



def inspect_frozen_artifact(
    exe_path: Path,
    build_info_path: Path,
    *,
    expected_sha256: str,
    expected_source_commit: str,
) -> dict[str, Any]:
    """Observe current file bytes, never historical hashes or private paths.

    A checksum alone does not establish software safety or offline acceptance.
    This helper does not execute or restore a quarantined file.
    """
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("invalid_expected_sha256")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", expected_source_commit):
        raise ValueError("invalid_source_commit")

    result: dict[str, Any] = {
        "schema": "jazn_studio_p5_artifact_readonly/v1",
        "source_commit_expected": expected_source_commit.lower(),
        "exe_exists": False,
        "observed_exe_sha256": None,
        "exe_sha256_matches": False,
        "build_info_exists": False,
        "build_info_commit_matches": False,
        "build_info_onedir": False,
        "current_integrity_match": False,
        "bundle_manifest_exists": False,
        "whole_bundle_integrity_match": False,
        "bundle_file_count": 0,
        "security_review": "HOLD",
        "antivirus_false_positive_confirmed": False,
        "offline_acceptance": "NOT_RUN",
        "independent_system_acceptance": "NOT_RUN",
    }
    try:
        if exe_path.is_symlink() or not exe_path.is_file():
            return result
        size = exe_path.stat().st_size
        if size <= 0 or size > _MAX_EXE_BYTES:
            return result
        result["exe_exists"] = True
        digest = sha256()
        with exe_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        observed = digest.hexdigest()
        result["observed_exe_sha256"] = observed
        result["exe_sha256_matches"] = observed == expected_sha256.lower()
    except OSError:
        return result

    try:
        if build_info_path.is_symlink() or not build_info_path.is_file():
            return result
        if build_info_path.stat().st_size > _MAX_INFO_BYTES:
            return result
        metadata = json.loads(build_info_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return result
        result["build_info_exists"] = True
        result["build_info_commit_matches"] = (
            metadata.get("source_commit") == expected_source_commit.lower()
        )
        result["build_info_onedir"] = metadata.get("layout") == "onedir"
    except (OSError, UnicodeError, ValueError):
        return result

    result["current_integrity_match"] = bool(
        result["exe_sha256_matches"]
        and result["build_info_commit_matches"]
        and result["build_info_onedir"]
    )
    manifest = exe_path.parent / _BUNDLE_MANIFEST
    result["bundle_manifest_exists"] = manifest.is_file() and not manifest.is_symlink()
    bundle_ok, file_count = verify_frozen_bundle_manifest(exe_path.parent)
    result["bundle_file_count"] = file_count
    result["whole_bundle_integrity_match"] = bool(result["current_integrity_match"] and bundle_ok)
    # security_review remains HOLD independently of both hash checks.
    return result
