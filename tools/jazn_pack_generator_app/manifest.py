from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .constants import (
    GENERATOR_VERSION,
    HOST_BOOTSTRAP_CONTRACT_SCHEMA,
    MEMORY_ATTACHMENT_CONTRACT_SCHEMA,
    PACKAGE_MANIFEST_SCHEMA,
    SYSTEM_BOOTSTRAP_REQUIRED_FILES,
)
from .errors import PackValidationError
from .models import PackPlan


SECURE_MCP_SERVER_MEMBER = "latka_jazn/mcp/server.py"
SECURE_MCP_TUNNEL_BOOTSTRAP_MEMBER = "latka_jazn/mcp/tunnel_bootstrap.py"
SECURE_MCP_TUNNEL_CONTRACT_MEMBER = "latka_jazn/mcp/secure_tunnel.py"
PUBLIC_MCP_HTTP_GATEWAY_MEMBER = "latka_jazn/mcp/http_gateway.py"
PUBLIC_MCP_HTTP_TASKS_BRIDGE_MEMBER = "latka_jazn/mcp/http_tasks_bridge.py"
PUBLIC_MCP_REMOTE_RUNTIME_MEMBER = "latka_jazn/mcp/remote_runtime.py"
PUBLIC_MCP_TASK_RESUME_MEMBER = "latka_jazn/mcp/task_resume.py"
MEMORY_ATTACHMENT_CONTRACT_MEMBER = "MEMORY_ATTACHMENT_CONTRACT.json"


def build_memory_attachment_contract(plan: PackPlan) -> dict[str, Any]:
    """Describe MEMORY as a separable runtime capability, never an implicit dependency."""

    content = plan.request.content.value
    carries_system = content in {"system", "system+memory"}
    carries_memory = content in {"memory", "system+memory"}
    return {
        "schema_version": MEMORY_ATTACHMENT_CONTRACT_SCHEMA,
        "package_content": content,
        "system_present": carries_system,
        "memory_present_in_this_package": carries_memory,
        "persistent_memory_required_for_core_runtime": False,
        "ordinary_dialogue_without_persistent_memory": True,
        "recall_without_verified_persistent_memory": False,
        "external_memory_attach_supported": carries_system,
        "memory_package_profile": "memory",
        "memory_package_is_active_root": False,
        "canonical_memory_root": "workspace_runtime/memory",
        "operational_core_state_root": "workspace_runtime/core_state",
        "memory_root_env": "JAZN_MEMORY_ROOT",
        "memory_mode_env": "JAZN_MEMORY_MODE",
        "default_memory_mode": "optional",
        "supported_memory_modes": ["optional", "required", "off"],
        "attach_requires_inactive_daemon": True,
        "attach_entrypoint": "run.py memory-attach",
        "auto_attach_entrypoint": "run.py runtime-bootstrap",
        "post_attach_restart_required": True,
        "legacy_transport_repack_supported": True,
        "bootstrap_contract_member": (
            MEMORY_ATTACHMENT_CONTRACT_MEMBER if carries_system else None
        ),
        "truth_boundary": (
            "The SYSTEM/MEMORY package boundary prevents private mutable data from becoming a release dependency. "
            "A SYSTEM-only package remains a complete core runtime. MEMORY may be absent, attached later from a "
            "separate verified package, or explicitly required by operator policy. Core operational SQLite under "
            "workspace_runtime/core_state is not recall evidence."
        ),
    }


def build_host_bootstrap_contract(plan: PackPlan) -> dict[str, Any]:
    """Describe what the package can prove about host bootstrap capability.

    The contract deliberately separates package completeness from host execution
    privileges. A SYSTEM ZIP can contain a complete bootstrap operator and a
    verified local Secure MCP Tunnel target without being able to create a
    process in ChatGPT or supply OpenAI's external tunnel control plane.
    """

    memory_attachment = build_memory_attachment_contract(plan)
    if plan.request.content.value == "memory":
        return {
            "schema_version": HOST_BOOTSTRAP_CONTRACT_SCHEMA,
            "applicable": False,
            "content_role": "memory_data_only",
            "active_system_root_eligible": False,
            "package_can_create_host_executor": False,
            "memory_attachment": memory_attachment,
            "truth_boundary": (
                "MEMORY is data only and never becomes the system active_root or an execution capability. "
                "It is consumed only through a separately verified SYSTEM memory-attach pipeline."
            ),
        }

    packaged_files = {
        item.archive_path.rstrip("/")
        for item in plan.entries
        if not item.is_dir
    }
    required = list(SYSTEM_BOOTSTRAP_REQUIRED_FILES)
    missing = [path for path in required if path not in packaged_files]
    secure_mcp_members = [
        SECURE_MCP_SERVER_MEMBER,
        SECURE_MCP_TUNNEL_BOOTSTRAP_MEMBER,
        SECURE_MCP_TUNNEL_CONTRACT_MEMBER,
    ]
    secure_mcp_target_bundled = all(path in packaged_files for path in secure_mcp_members)
    public_mcp_members = [
        SECURE_MCP_SERVER_MEMBER,
        PUBLIC_MCP_HTTP_GATEWAY_MEMBER,
        PUBLIC_MCP_HTTP_TASKS_BRIDGE_MEMBER,
        PUBLIC_MCP_REMOTE_RUNTIME_MEMBER,
        PUBLIC_MCP_TASK_RESUME_MEMBER,
    ]
    public_streamable_http_ingress_bundled = all(
        path in packaged_files for path in public_mcp_members
    )
    return {
        "schema_version": HOST_BOOTSTRAP_CONTRACT_SCHEMA,
        "applicable": True,
        "content_role": "system_operator",
        "active_system_root_eligible": not missing,
        "bootstrap_member": "CHATGPT_BOOTSTRAP.py",
        "entrypoint": "run.py",
        "control_plane": "main.py",
        "memory_attachment_contract_member": MEMORY_ATTACHMENT_CONTRACT_MEMBER,
        "memory_attachment": memory_attachment,
        "required_members": required,
        "missing_required_members": missing,
        "local_bootstrap_requires_process_creation": True,
        "package_can_create_host_executor": False,
        # The OpenAI tunnel client/control plane is deliberately external.  The
        # SYSTEM package only carries the local stdio target that the tunnel may
        # launch after host capability/authentication has been established.
        "remote_runtime_transport_bundled": False,
        "remote_runtime_route_ready_from_package_alone": False,
        "public_streamable_http_ingress_bundled": public_streamable_http_ingress_bundled,
        "public_streamable_http_ingress_members": public_mcp_members,
        "public_streamable_http_protocol_revision": "2026-07-28",
        "public_streamable_http_tasks_extension": "io.modelcontextprotocol/tasks",
        "public_streamable_http_requires_https_deployment": True,
        "public_streamable_http_requires_oauth_or_equivalent_verified_auth": True,
        "secure_mcp_tunnel_target_bundled": secure_mcp_target_bundled,
        "secure_mcp_tunnel_target_members": secure_mcp_members,
        "remote_runtime_transport_external": "openai_secure_mcp_tunnel",
        "remote_runtime_readiness_requires": [
            "one_verified_remote_transport",
            "authenticated_remote_ingress",
            "runtime_health_and_readiness",
            "explicit_chatgpt_connector_or_app_capability",
        ],
        "remote_runtime_readiness_requires_any_route": {
            "public_streamable_http": [
                "public_https_endpoint",
                "verified_oauth_or_equivalent_auth",
                "mcp_2026_07_28_protocol_compatibility",
                "gateway_healthz_live",
                "runtime_readyz_ready",
                "explicit_chatgpt_connector_or_app_capability",
            ],
            "openai_secure_mcp_tunnel": [
                "external_tunnel_client",
                "authenticated_tunnel_control_plane",
                "process_running_healthy_ready",
                "explicit_chatgpt_connector_or_app_capability",
            ],
        },
        "host_capability_negotiation_required": True,
        "supported_execution_routes": [
            "local_executor",
            "remote_runtime_external",
            "host_handoff",
        ],
        "truth_boundary": (
            "Package completeness proves that a local operator can be materialized after a host has supplied "
            "filesystem/process execution. When present, the Secure MCP files prove only that the package contains "
            "the local stdio target for OpenAI Secure MCP Tunnel. The public Streamable HTTP implementation, when "
            "present, proves only that the code for an MCP 2026-07-28 HTTPS ingress is bundled; it does not prove that "
            "a public endpoint is deployed, authenticated, healthy, reachable, or registered with the current ChatGPT "
            "host. The ZIP cannot grant ChatGPT a local executor, authenticate an external control plane, publish an "
            "app/connector, or prove a usable remote runtime route. "
            "Private MEMORY is an independent optional capability and is not required for core runtime readiness. "
            "Remote transport or execution handoff must be explicitly supplied and verified by the host."
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
    memory_attachment = build_memory_attachment_contract(plan)
    return {
        "schema_version": PACKAGE_MANIFEST_SCHEMA,
        "generator": "tools/jazn_pack_generator.py",
        "generator_version": GENERATOR_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": plan.package_version,
        "content": plan.request.content.value,
        "source_root": str(plan.request.source_root),
        # This field describes the source selected while generating this package.
        # A null value on SYSTEM never means that runtime memory is forbidden.
        "memory_root": str(plan.request.memory_root) if plan.request.memory_root else None,
        "memory_attachment": memory_attachment,
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
                "host execution capability and from private MEMORY readiness. A SYSTEM-only package is a complete core "
                "runtime; a verified MEMORY package may be attached separately later. A packaged Secure MCP target does "
                "not bundle or authenticate the external OpenAI tunnel control plane. MEMORY content, when requested, "
                "remains a byte-exact filesystem snapshot outside the protected static SYSTEM inventory. Split mode cuts "
                "one already-verified logical ZIP into binary transport parts."
            )
            if plan.request.content.value != "memory"
            else (
                "MEMORY packages preserve the actual selected memory bytes. .gitattributes is diagnostic only for "
                "folder snapshots. Per-file SHA-256 is rechecked against ZIP members; split mode cuts one logical ZIP "
                "into binary transport parts. MEMORY is data only, never grants execution capability, and is attached "
                "to a separately verified SYSTEM through the canonical memory-attach pipeline."
            )
        ),
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
