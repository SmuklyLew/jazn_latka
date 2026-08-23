from __future__ import annotations

"""v16 release-metadata compatibility adapter.

v16 deliberately uses an unprefixed semantic ``PACKAGE_VERSION``.  The underlying
release implementation remains canonical; this adapter widens the version validator
and preserves the historical monkeypatchable public hooks.

The check path also has one deliberate v16 contract: after ``--write`` the worktree
may contain changes to *only* SOURCE_PROVENANCE.json and
PACKAGE_INTEGRITY_MANIFEST.json.  Requiring a completely clean tree there makes the
canonical ``write -> check`` sequence impossible.  The check therefore rebuilds the
same deterministic documents with ``allow_metadata_only_dirty=True``.  Any other
tracked or untracked change still fails closed in the underlying provenance builder.
"""

from pathlib import Path
import re
from collections.abc import Iterable
from typing import Any

from latka_jazn.tools import _release_metadata_sync_impl as _impl

_impl._PACKAGE_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+$")

from latka_jazn.tools._release_metadata_sync_impl import *  # noqa: F401,F403,E402


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
        "schema_version": _impl.schema_version("release_metadata_sync_check"),
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
