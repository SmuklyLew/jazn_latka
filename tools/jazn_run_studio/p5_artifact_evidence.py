"""Read-only P5 frozen artifact inspection; not a release or malware verdict."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

_MAX_EXE_BYTES = 256 * 1024 * 1024
_MAX_INFO_BYTES = 1024 * 1024


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
    return result
