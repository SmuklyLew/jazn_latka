"""Fail-closed immutable RC evidence used only by isolated TPA preflight.

Never trusts a JSON field alone: canonical verifier hashes the entire static
package plan, then the provenance is validated with export_without_git profile.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def verified_release_source(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    if (root / ".git").exists():
        raise ValueError("Git checkout must use Git preflight instead")
    from latka_jazn.tools.package_integrity import verify_package_integrity_manifest
    from latka_jazn.core.source_provenance import read_source_provenance
    integrity = verify_package_integrity_manifest(root)
    provenance = read_source_provenance(root, profile="export_without_git")
    sha = integrity.get("manifest_sha256")
    commit = provenance.base_merge_commit
    valid = (
        integrity.get("ok") is True
        and provenance.status == "verified_export_without_git_history"
        and provenance.manifest_protected is True
        and provenance.version_matches_runtime is True
        and isinstance(sha, str) and len(sha) == 64
        and isinstance(commit, str) and len(commit) == 40
    )
    if not valid:
        return {"release_verified": False, "release_reason": "manifest_or_provenance_unverified"}
    return {
        "release_verified": True,
        "release_manifest_sha256": sha,
        "release_source_commit": commit,
        "release_runtime_version": provenance.runtime_version,
    }
