from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .constants import GENERATOR_VERSION, PACKAGE_MANIFEST_SCHEMA
from .models import PackPlan


def build_manifest(
    plan: PackPlan,
    *,
    logical_filename: str,
    logical_sha256: str,
    logical_size_bytes: int,
    split_enabled: bool,
    parts: list[dict[str, Any]],
    verification: dict[str, Any],
    source_sha256: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": PACKAGE_MANIFEST_SCHEMA,
        "generator": "tools/jazn_pack_generator.py",
        "generator_version": GENERATOR_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": plan.package_version,
        "content": plan.request.content.value,
        "source_root": str(plan.request.source_root),
        "memory_root": str(plan.request.memory_root) if plan.request.memory_root else None,
        "archive": {
            "logical_filename": logical_filename,
            "logical_sha256": logical_sha256,
            "logical_size_bytes": logical_size_bytes,
            "compression": "ZIP_DEFLATED",
            "compression_level": plan.request.compression_level,
            "zip64": True,
        },
        "split": {
            "enabled": split_enabled,
            "requested": plan.request.transport.value == "split",
            "part_size_bytes": plan.request.part_size_mib * 1024 * 1024,
            "parts": parts,
        },
        "source": {
            "file_count": plan.file_count,
            "directory_count": plan.directory_count,
            "total_size_bytes": plan.source_total_size_bytes,
            "byte_exact": True,
            "source_basis": (
                "canonical_release"
                if verification.get("canonical_release_bytes") is True
                else "selected_folder"
            ),
            "staging_mode": str(verification.get("staging_mode") or "source-folder-byte-copy"),
            "entries": [
                {
                    "path": item.archive_path,
                    "size_bytes": item.size_bytes,
                    "kind": "directory" if item.is_dir else "file",
                    **(
                        {"sha256": source_sha256[item.archive_path]}
                        if not item.is_dir
                        else {}
                    ),
                }
                for item in plan.entries
            ],
        },
        "excluded": list(plan.excluded),
        "verification": verification,
        "truth_boundary": (
            (
                "SYSTEM bytes are materialized from canonical Git blobs by create_release_staging, or from an already "
                "verified export without Git. Checkout EOL conversion is therefore not a release source. The completed "
                "ZIP is safely extracted to a fresh clean-room and its embedded PACKAGE_INTEGRITY_MANIFEST.json and "
                "SOURCE_PROVENANCE.json are reverified before publication. MEMORY content, when requested, remains a "
                "byte-exact filesystem snapshot outside the protected static SYSTEM inventory. Split mode cuts one "
                "already-verified logical ZIP into binary transport parts."
            )
            if plan.request.content.value != "memory"
            else (
                "MEMORY packages preserve the actual selected memory bytes. .gitattributes is diagnostic only for "
                "folder snapshots. Per-file SHA-256 is rechecked against ZIP members; split mode cuts one logical ZIP "
                "into binary transport parts."
            )
        ),
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
