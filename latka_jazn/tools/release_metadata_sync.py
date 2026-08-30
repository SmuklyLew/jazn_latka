from __future__ import annotations

"""v16 release-metadata compatibility adapter.

The adapter keeps ``PACKAGE_VERSION`` as the release/runtime identity while
separating it from serialized contract-schema versions. It also preserves the
historical monkeypatchable public hooks and the metadata-only dirty-tree rule.

Release provenance now carries three distinct identities:

* stable contract schema (format semantics),
* runtime/release identity (PACKAGE_VERSION / PACKAGE_VERSION_FULL),
* source/lineage identity (immutable source commit plus merge-base lineage).

Legacy fields remain present as documented aliases so existing readers can
migrate without a flag-day break.
"""

import ast
from collections.abc import Iterable
from pathlib import Path
import re
from typing import Any

from latka_jazn.tools import _release_metadata_sync_impl as _impl

_impl._PACKAGE_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+$")

from latka_jazn.tools._release_metadata_sync_impl import *  # noqa: F401,F403,E402
from latka_jazn.version import (  # noqa: E402
    contract_schema_version,
    schema_contract_metadata,
)

_ORIGINAL_BUILD_RELEASE_PROVENANCE_DOCUMENT = _impl.build_release_provenance_document
_ORIGINAL_BUILD_CANONICAL_PACKAGE_MANIFEST = _impl.build_canonical_package_manifest
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_VERSION_PATH = "latka_jazn/version.py"


def _literal_runtime_version(version_py_text: str) -> str | None:
    """Read literal release identity from version.py text without importing it."""

    try:
        tree = ast.parse(version_py_text, filename=_VERSION_PATH)
    except SyntaxError:
        return None
    values: dict[str, str] = {}
    for node in tree.body:
        targets: list[str] = []
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value_node = node.value
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            continue
        value = value_node.value.strip()
        for target in targets:
            values[target] = value

    package = (values.get("PACKAGE_VERSION") or "").strip()
    distribution = (values.get("DISTRIBUTION_VERSION") or "").strip()
    release = (values.get("PACKAGE_RELEASE_NAME") or "").strip()
    if not package and distribution:
        package = f"v{distribution}"
    if not package:
        return None
    return f"{package}-{release}" if release else package


def _version_at_commit(root: Path, commit: str | None) -> str | None:
    value = str(commit or "").strip().lower()
    if not _SHA_RE.fullmatch(value):
        return None
    raw = str(_impl._git(root, "show", f"{value}:{_VERSION_PATH}", check=False))
    if not raw.strip():
        return None
    return _literal_runtime_version(raw)


def _resolve_ref(root: Path, base_branch: str | None) -> str | None:
    branch = str(base_branch or "").strip()
    if not branch:
        return None
    for candidate in (
        f"refs/remotes/origin/{branch}",
        f"refs/heads/{branch}",
        branch,
    ):
        resolved = str(
            _impl._git(root, "rev-parse", "--verify", "--quiet", candidate, check=False)
        ).strip().lower()
        if _SHA_RE.fullmatch(resolved):
            return resolved
    return None


def _lineage_base_commit(root: Path, source_commit: str, base_branch: str | None) -> str | None:
    base_ref = _resolve_ref(root, base_branch)
    if base_ref is None:
        return None
    merge_base = str(
        _impl._git(root, "merge-base", source_commit, base_ref, check=False)
    ).strip().lower()
    return merge_base if _SHA_RE.fullmatch(merge_base) else None


def _decorate_release_provenance(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    runtime_version = str(result.get("runtime_version") or "") or None
    source_commit = str(result.get("base_merge_commit") or "").strip().lower() or None
    source_version = _version_at_commit(root, source_commit) or runtime_version
    base_branch = str(result.get("base_branch") or "") or None
    lineage_base_commit = (
        _lineage_base_commit(root, source_commit, base_branch)
        if source_commit is not None
        else None
    )
    lineage_base_version = _version_at_commit(root, lineage_base_commit)

    result["schema_version"] = contract_schema_version("source_provenance")
    result["schema_contract"] = schema_contract_metadata("source_provenance")
    result["release_version"] = runtime_version
    result["source_commit"] = source_commit
    result["source_version"] = source_version
    result["lineage"] = {
        "base_branch": base_branch,
        "base_commit": lineage_base_commit,
        "base_version": lineage_base_version,
        "source_commit": source_commit,
        "source_version": source_version,
        "relationship": "merge_base_to_immutable_source_commit",
        "resolution": "resolved" if lineage_base_commit else "base_ref_unavailable",
    }
    # Preserve old field meanings for readers shipped before v16.3.25.3.
    result["base_merge_commit"] = source_commit
    result["base_version"] = source_version
    result["update_version"] = runtime_version
    result["legacy_aliases"] = {
        "base_merge_commit": "source_commit",
        "base_version": "source_version",
        "update_version": "release_version",
    }
    result["truth_boundary"] = (
        str(result.get("truth_boundary") or "").strip()
        + " Contract schema identity is independent from runtime/release identity. "
        "source_commit/source_version identify the immutable code-content source; "
        "lineage.base_* identifies the resolved merge-base when available; legacy aliases "
        "remain for migration compatibility only."
    ).strip()
    return result


def build_release_provenance_document(
    root: Path | str,
    *,
    source_commit: str | None = None,
    base_branch: str | None = None,
    allow_metadata_only_dirty: bool = False,
) -> dict[str, Any]:
    resolved_root = Path(root).resolve()
    payload = _ORIGINAL_BUILD_RELEASE_PROVENANCE_DOCUMENT(
        resolved_root,
        source_commit=source_commit,
        base_branch=base_branch,
        allow_metadata_only_dirty=allow_metadata_only_dirty,
    )
    return _decorate_release_provenance(resolved_root, payload)


def _decorate_package_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    runtime_version = str(result.get("runtime_version") or result.get("package_version") or "") or None
    result["schema_version"] = contract_schema_version("package_integrity_manifest")
    result["schema_contract"] = schema_contract_metadata("package_integrity_manifest")
    result["release_version"] = runtime_version
    result["artifact_identity"] = {
        "runtime_version": result.get("runtime_version"),
        "package_version": result.get("package_version"),
        "release_version": runtime_version,
    }
    result["legacy_aliases"] = {
        "version": "release_version",
    }
    return result


def build_canonical_package_manifest(
    root: Path | str,
    *,
    source_commit: str,
    overrides: Any = None,
    generated_at_utc: str | None = None,
    progress: Any = None,
    progress_start: int = 20,
    progress_end: int = 90,
) -> dict[str, Any]:
    payload = _ORIGINAL_BUILD_CANONICAL_PACKAGE_MANIFEST(
        root,
        source_commit=source_commit,
        overrides=overrides,
        generated_at_utc=generated_at_utc,
        progress=progress,
        progress_start=progress_start,
        progress_end=progress_end,
    )
    return _decorate_package_manifest(payload)


# The implementation functions resolve their module globals at call time. Patch
# the canonical builders once so write/check/main all use the same semantics.
_impl.build_release_provenance_document = build_release_provenance_document
_impl.build_canonical_package_manifest = build_canonical_package_manifest


def check_release_metadata(
    root: Path | str,
    *,
    base_branch: str | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """Verify canonical metadata while allowing only the metadata written just before it."""

    resolved_root = Path(root).resolve()
    _impl._report_progress(progress, 0, 100, "Sprawdzanie repozytorium i kontrolowanych metadanych")
    source_commit = _impl.resolve_release_source_commit(resolved_root)
    _impl._report_progress(progress, 8, 100, "Commit źródłowy wydania rozwiązany")
    provenance = _impl.build_release_provenance_document(
        resolved_root,
        source_commit=source_commit,
        base_branch=base_branch,
        allow_metadata_only_dirty=True,
    )
    _impl._report_progress(progress, 16, 100, "Proweniencja Git zbudowana")
    provenance_bytes = _impl._json_bytes(provenance)
    manifest = _impl.build_canonical_package_manifest(
        resolved_root,
        source_commit=source_commit,
        overrides={_impl.PROVENANCE_NAME: provenance_bytes},
        generated_at_utc=str(provenance["generated_at_utc"]),
        progress=progress,
        progress_start=20,
        progress_end=90,
    )
    _impl._report_progress(progress, 94, 100, "Serializacja manifestu integralności")
    manifest_bytes = _impl.serialize_package_integrity_manifest(manifest)
    current_provenance = (
        (resolved_root / _impl.PROVENANCE_NAME).read_bytes()
        if (resolved_root / _impl.PROVENANCE_NAME).is_file()
        else None
    )
    current_manifest = (
        (resolved_root / _impl.MANIFEST_NAME).read_bytes()
        if (resolved_root / _impl.MANIFEST_NAME).is_file()
        else None
    )
    _impl._report_progress(progress, 97, 100, "Porównywanie proweniencji")
    synchronized = current_provenance == provenance_bytes and current_manifest == manifest_bytes
    _impl._report_progress(progress, 100, 100, "Porównanie metadanych zakończone")
    return {
        "schema_version": contract_schema_version("release_metadata_sync_check"),
        "ok": synchronized,
        "synchronized": synchronized,
        "source_commit": source_commit,
        "source_tree": provenance["git_tree_sha"],
        "base_branch": provenance["base_branch"],
        "provenance_matches": current_provenance == provenance_bytes,
        "manifest_matches": current_manifest == manifest_bytes,
        "file_count": manifest["file_count"],
        "metadata_only_dirty_allowed": True,
    }


def main(argv: Iterable[str] | None = None) -> int:
    """Run the implementation while preserving monkeypatchable public hooks."""

    _impl.check_release_metadata = check_release_metadata
    _impl.write_release_metadata = write_release_metadata
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
