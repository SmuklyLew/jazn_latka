from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .constants import (
    GENERATOR_VERSION,
    HOST_BOOTSTRAP_CONTRACT_SCHEMA,
    PACKAGE_MANIFEST_SCHEMA,
    SYSTEM_BOOTSTRAP_REQUIRED_FILES,
)
from .errors import PackValidationError
from .models import PackPlan


def build_host_bootstrap_contract(plan: PackPlan) -> dict[str, Any]:
    """Describe what the package can prove about host bootstrap capability.

    The contract deliberately separates package completeness from host execution
    privileges. A SYSTEM ZIP can contain a complete bootstrap operator without
    being able to create a process in ChatGPT. Remote runtime access and host
    handoff are external capabilities and are never inferred from package bytes.
    """

    if plan.request.content.value == "memory":
        return {
            "schema_version": HOST_BOOTSTRAP_CONTRACT_SCHEMA,
            "applicable": False,
            "content_role": "memory_data_only",
            "active_system_root_eligible": False,
            "package_can_create_host_executor": False,
            "truth_boundary": (
                "MEMORY is data only and never becomes the system active_root or an execution capability."
            ),
        }

    packaged_files = {
        item.archive_path.rstrip("/")
        for item in plan.entries
        if not item.is_dir
    }
    required = list(SYSTEM_BOOTSTRAP_REQUIRED_FILES)
    missing = [path for path in required if path not in packaged_files]
    return {
        "schema_version": HOST_BOOTSTRAP_CONTRACT_SCHEMA,
        "applicable": True,
        "content_role": "system_operator",
        "active_system_root_eligible": not missing,
        "bootstrap_member": "CHATGPT_BOOTSTRAP.py",
        "entrypoint": "run.py",
        "control_plane": "main.py",
        "required_members": required,
        "missing_required_members": missing,
        "local_bootstrap_requires_process_creation": True,
        "package_can_create_host_executor": False,
        "remote_runtime_transport_bundled": False,
        "host_capability_negotiation_required": True,
        "supported_execution_routes": [
            "local_executor",
            "remote_runtime_external",
            "host_handoff",
        ],
        "truth_boundary": (
            "Package completeness proves only that a local operator can be materialized after a host has supplied "
            "filesystem and process execution. The ZIP cannot grant ChatGPT a local executor. A remote runtime "
            "transport or execution handoff must be explicitly supplied and verified by the host."
        ),
    }


def validate_system_bootstrap_contract(plan: PackPlan) -> dict[str, Any]:
    contract = build_host_bootstrap_contract(plan)
    if contract.get("applicable") is not True:
        return contract
    missing = [str(value) for value in contract.get("missing_required_members") or []]
    if missing:
        raise PackValidationError(
            "SYSTEM package is not bootstrap-complete; missing required members: "
            + ", ".join(missing)
        )
    return contract


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
    host_bootstrap = validate_system_bootstrap_contract(plan)
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
        "host_bootstrap": host_bootstrap,
        "excluded": list(plan.excluded),
        "verification": verification,
        "truth_boundary": (
            (
                "SYSTEM bytes are materialized from canonical Git blobs by create_release_staging, or from an already "
                "verified export without Git. Checkout EOL conversion is therefore not a release source. The completed "
                "ZIP is safely extracted to a fresh clean-room and its embedded PACKAGE_INTEGRITY_MANIFEST.json and "
                "SOURCE_PROVENANCE.json are reverified before publication. Package completeness is independent from "
                "host execution capability: the ZIP cannot grant ChatGPT a local executor. MEMORY content, when "
                "requested, remains a byte-exact filesystem snapshot outside the protected static SYSTEM inventory. "
                "Split mode cuts one already-verified logical ZIP into binary transport parts."
            )
            if plan.request.content.value != "memory"
            else (
                "MEMORY packages preserve the actual selected memory bytes. .gitattributes is diagnostic only for "
                "folder snapshots. Per-file SHA-256 is rechecked against ZIP members; split mode cuts one logical ZIP "
                "into binary transport parts. MEMORY is data only and never grants execution capability."
            )
        ),
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
