from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_tool_capability_snapshot")
MANIFEST_SCHEMA_VERSION = schema_version("host_tool_capability_manifest")
CATALOG_SCHEMA_VERSION = schema_version("host_tool_catalog")
MAX_HOST_TOOLS = 128
MAX_MANIFEST_BYTES = 256 * 1024
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class HostToolAvailability(str, Enum):
    UNKNOWN = "unknown"
    ADVERTISED = "advertised"
    VERIFIED = "verified"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HostToolDescriptor:
    name: str
    family: str
    aliases: tuple[str, ...]
    read_only_hint: bool
    destructive_hint: bool
    idempotent_hint: bool
    open_world_hint: bool
    automatic_probe: str
    probe_operation_hint: str | None
    evidence_kind: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


HOST_TOOL_CATALOG: tuple[HostToolDescriptor, ...] = (
    HostToolDescriptor(
        name="web.run",
        family="external_research",
        aliases=("web", "browser", "search", "internet"),
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
        automatic_probe="read_only",
        probe_operation_hint=(
            "perform one bounded public search/open operation without authentication, purchase, booking, "
            "submission, or any other external mutation"
        ),
        evidence_kind="source_citation_or_structured_web_result",
        description="Public web research and current external information.",
    ),
    HostToolDescriptor(
        name="GitHub",
        family="repository_connector",
        aliases=("github", "repo", "repository"),
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
        automatic_probe="read_only_suboperation_only",
        probe_operation_hint=(
            "read repository metadata or fetch a known public file only; never create, update, delete, merge, "
            "or move refs during automatic capability probing"
        ),
        evidence_kind="repository_read_or_action_receipt",
        description="Repository reads plus explicitly authorized repository mutations.",
    ),
    HostToolDescriptor(
        name="file_search",
        family="user_file_retrieval",
        aliases=("files", "file-library", "file library"),
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
        automatic_probe="deferred",
        probe_operation_hint=(
            "defer probing until a real user file request exists; do not enumerate private files merely to prove capability"
        ),
        evidence_kind="file_reference_evidence",
        description="Read-only retrieval from files that the host has actually made available to the conversation.",
    ),
    HostToolDescriptor(
        name="image_gen",
        family="image_generation",
        aliases=("image", "image-gen", "image_gen.text2im"),
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
        automatic_probe="forbidden",
        probe_operation_hint="never generate an image only to test whether the tool exists",
        evidence_kind="host_action_receipt",
        description="Image generation or image editing when the user request actually requires it.",
    ),
    HostToolDescriptor(
        name="automations",
        family="scheduled_actions",
        aliases=("automation", "reminder", "schedule"),
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
        automatic_probe="forbidden",
        probe_operation_hint="never create a reminder or scheduled task merely as a capability probe",
        evidence_kind="host_action_receipt",
        description="Future reminders, recurring delivery, or condition watches explicitly requested by the user.",
    ),
    HostToolDescriptor(
        name="genui",
        family="host_ui",
        aliases=("widget", "ui-widget"),
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
        automatic_probe="deferred",
        probe_operation_hint="use only when the real turn benefits from a supported host widget",
        evidence_kind="host_ui_result",
        description="Host-managed interactive widgets and utility presentation.",
    ),
    HostToolDescriptor(
        name="python_user_visible",
        family="host_compute",
        aliases=("python-visible", "python_user_visible.exec"),
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
        automatic_probe="forbidden",
        probe_operation_hint="never execute user-visible code or create files merely to test capability availability",
        evidence_kind="host_execution_receipt",
        description="User-visible computation, tables, plots, or artifact generation performed by the host.",
    ),
)

_CATALOG_BY_NAME = {item.name: item for item in HOST_TOOL_CATALOG}
_ALIAS_TO_NAME = {
    alias.casefold(): item.name
    for item in HOST_TOOL_CATALOG
    for alias in (item.name, *item.aliases)
}


def canonical_host_tool_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("empty_host_tool_name")
    canonical = _ALIAS_TO_NAME.get(raw.casefold(), raw)
    if not _TOOL_NAME_RE.fullmatch(canonical):
        raise ValueError(f"invalid_host_tool_name:{raw!r}")
    return canonical


def supported_host_tool_names() -> frozenset[str]:
    return frozenset(_CATALOG_BY_NAME)


def _generic_descriptor(name: str) -> HostToolDescriptor:
    return HostToolDescriptor(
        name=name,
        family="host_declared_extension",
        aliases=(),
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
        automatic_probe="forbidden",
        probe_operation_hint="unknown host tool: require explicit user/host context and real-turn evidence before use",
        evidence_kind="host_supplied_evidence",
        description="Host-declared tool not yet described by the trusted Jaźń catalog.",
    )


def _decode_manifest_text(text: str, *, source: str) -> tuple[dict[str, Any] | None, list[str]]:
    encoded = text.encode("utf-8", errors="strict")
    if len(encoded) > MAX_MANIFEST_BYTES:
        return None, [f"host_tool_manifest_too_large:{source}"]
    try:
        value = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, [f"host_tool_manifest_invalid_json:{source}:{type(exc).__name__}"]
    if not isinstance(value, dict):
        return None, [f"host_tool_manifest_root_not_object:{source}"]
    return value, []


def load_host_tool_capability_manifest(
    manifest: Mapping[str, Any] | str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str, list[str], bool]:
    """Load a host-declared capability manifest without pretending local introspection.

    Built-in ChatGPT tools live outside the Jaźń Python process.  The runtime can
    therefore validate a host declaration and later bind observed tool evidence,
    but it cannot discover the host tool namespace by inspecting local modules.
    """

    if isinstance(manifest, Mapping):
        return dict(manifest), "explicit_mapping", [], True
    if isinstance(manifest, str) and manifest.strip():
        value, errors = _decode_manifest_text(manifest, source="explicit_json")
        return value, "explicit_json", errors, True

    env_map = env if env is not None else os.environ
    inline = str(env_map.get("JAZN_HOST_TOOL_CAPABILITIES_JSON") or "").strip()
    if inline:
        value, errors = _decode_manifest_text(inline, source="env_json")
        return value, "env:JAZN_HOST_TOOL_CAPABILITIES_JSON", errors, True

    path_value = str(env_map.get("JAZN_HOST_TOOL_CAPABILITIES_FILE") or "").strip()
    if path_value:
        path = Path(path_value).expanduser()
        try:
            if path.is_symlink():
                return None, "env:JAZN_HOST_TOOL_CAPABILITIES_FILE", ["host_tool_manifest_symlink_rejected"], True
            stat = path.stat()
            if not path.is_file():
                return None, "env:JAZN_HOST_TOOL_CAPABILITIES_FILE", ["host_tool_manifest_not_regular_file"], True
            if stat.st_size > MAX_MANIFEST_BYTES:
                return None, "env:JAZN_HOST_TOOL_CAPABILITIES_FILE", ["host_tool_manifest_file_too_large"], True
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return None, "env:JAZN_HOST_TOOL_CAPABILITIES_FILE", [f"host_tool_manifest_file_unreadable:{type(exc).__name__}"], True
        value, errors = _decode_manifest_text(text, source="env_file")
        return value, "env:JAZN_HOST_TOOL_CAPABILITIES_FILE", errors, True

    return None, "none", [], False


def _manifest_tool_entries(manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    raw_tools = manifest.get("tools")
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    if raw_tools is None:
        return entries, ["host_tool_manifest_tools_missing"]

    if isinstance(raw_tools, Mapping):
        iterable: list[Any] = []
        for name, value in raw_tools.items():
            if isinstance(value, Mapping):
                iterable.append({"name": str(name), **dict(value)})
            else:
                iterable.append({"name": str(name), "available": bool(value)})
    elif isinstance(raw_tools, list):
        iterable = list(raw_tools)
    else:
        return entries, ["host_tool_manifest_tools_invalid_type"]

    if len(iterable) > MAX_HOST_TOOLS:
        return entries, ["host_tool_manifest_tool_limit_exceeded"]

    seen: set[str] = set()
    for raw in iterable:
        if isinstance(raw, str):
            item: dict[str, Any] = {"name": raw, "available": True}
        elif isinstance(raw, Mapping):
            item = dict(raw)
        else:
            errors.append("host_tool_manifest_entry_invalid_type")
            continue
        try:
            name = canonical_host_tool_name(str(item.get("name") or ""))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if name in seen:
            errors.append(f"duplicate_host_tool:{name}")
            continue
        seen.add(name)
        operations_raw = item.get("operations")
        if isinstance(operations_raw, str):
            operations = [operations_raw]
        elif isinstance(operations_raw, list):
            operations = [str(value) for value in operations_raw if str(value).strip()]
        else:
            operations = []
        annotations = dict(item.get("annotations")) if isinstance(item.get("annotations"), Mapping) else {}
        entries.append(
            {
                "name": name,
                "available": item.get("available") is not False,
                "operations": operations[:64],
                "annotations": annotations,
                "provider": str(item.get("provider") or "host").strip() or "host",
            }
        )
    return entries, errors


def _observation_index(
    observations: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for raw in observations or ():
        if not isinstance(raw, Mapping):
            errors.append("host_tool_observation_invalid_type")
            continue
        try:
            name = canonical_host_tool_name(str(raw.get("tool") or raw.get("name") or ""))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        indexed[name] = {
            "tool": name,
            "operation": str(raw.get("operation") or "").strip() or None,
            "ok": raw.get("ok") is True or raw.get("success") is True,
            "availability_confirmed": raw.get("availability_confirmed"),
            "error_code": str(raw.get("error_code") or "").strip() or None,
            "source": str(raw.get("source") or "runtime_tool_evidence").strip() or "runtime_tool_evidence",
        }
    return indexed, errors


def build_host_tool_capability_snapshot(
    manifest: Mapping[str, Any] | str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    observations: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest_value, manifest_source, manifest_errors, manifest_supplied = load_host_tool_capability_manifest(
        manifest,
        env=env,
    )
    manifest_entries: list[dict[str, Any]] = []
    errors = list(manifest_errors)
    if manifest_value is not None:
        manifest_entries, entry_errors = _manifest_tool_entries(manifest_value)
        errors.extend(entry_errors)

    observation_map, observation_errors = _observation_index(observations)
    errors.extend(observation_errors)

    descriptors: dict[str, HostToolDescriptor] = dict(_CATALOG_BY_NAME)
    states: dict[str, HostToolAvailability] = {
        name: HostToolAvailability.UNKNOWN for name in descriptors
    }
    metadata: dict[str, dict[str, Any]] = {name: {} for name in descriptors}

    for item in manifest_entries:
        name = str(item["name"])
        descriptors.setdefault(name, _generic_descriptor(name))
        metadata[name] = {
            "operations": list(item.get("operations") or []),
            "reported_annotations": dict(item.get("annotations") or {}),
            "provider": item.get("provider"),
        }
        states[name] = (
            HostToolAvailability.ADVERTISED
            if item.get("available") is True
            else HostToolAvailability.UNAVAILABLE
        )

    unavailable_codes = {"tool_unavailable", "tool_missing", "host_tool_not_found"}
    for name, observation in observation_map.items():
        descriptors.setdefault(name, _generic_descriptor(name))
        metadata.setdefault(name, {})["last_observation"] = dict(observation)
        if observation.get("ok") is True:
            states[name] = HostToolAvailability.VERIFIED
        elif (
            observation.get("availability_confirmed") is False
            and observation.get("error_code") in unavailable_codes
        ):
            states[name] = HostToolAvailability.UNAVAILABLE
        elif states.get(name) is HostToolAvailability.ADVERTISED:
            states[name] = HostToolAvailability.DEGRADED
        else:
            states.setdefault(name, HostToolAvailability.UNKNOWN)

    explicit_manifest_invalid = bool(manifest_supplied and errors and manifest_value is None)
    strict_availability = bool(manifest_supplied)
    if explicit_manifest_invalid:
        policy_candidates: list[str] = []
    elif strict_availability:
        policy_candidates = sorted(
            name
            for name, state in states.items()
            if state in {HostToolAvailability.ADVERTISED, HostToolAvailability.VERIFIED}
        )
    else:
        policy_candidates = sorted(_CATALOG_BY_NAME)

    verified = sorted(name for name, state in states.items() if state is HostToolAvailability.VERIFIED)
    advertised = sorted(name for name, state in states.items() if state is HostToolAvailability.ADVERTISED)
    degraded = sorted(name for name, state in states.items() if state is HostToolAvailability.DEGRADED)
    unavailable = sorted(name for name, state in states.items() if state is HostToolAvailability.UNAVAILABLE)
    unknown = sorted(name for name, state in states.items() if state is HostToolAvailability.UNKNOWN)

    tools: list[dict[str, Any]] = []
    probe_plan: list[dict[str, Any]] = []
    for name in sorted(descriptors):
        descriptor = descriptors[name]
        item = {
            **descriptor.to_dict(),
            "availability": states.get(name, HostToolAvailability.UNKNOWN).value,
            "catalog_known": name in _CATALOG_BY_NAME,
            "manifest_metadata": dict(metadata.get(name) or {}),
            "reported_annotations_trusted_for_authorization": False,
        }
        tools.append(item)
        if name not in policy_candidates and not (not strict_availability and name in _CATALOG_BY_NAME):
            continue
        probe_mode = descriptor.automatic_probe
        probe_plan.append(
            {
                "tool": name,
                "probe_mode": probe_mode,
                "host_execution_required": True,
                "runtime_executes_host_tool_directly": False,
                "automatic_probe_allowed": probe_mode in {"read_only", "read_only_suboperation_only"},
                "operation_hint": descriptor.probe_operation_hint,
                "evidence_kind": descriptor.evidence_kind,
            }
        )

    if errors:
        status = "manifest_or_observation_invalid"
    elif not manifest_supplied:
        status = "host_manifest_missing"
    elif verified and len(verified) == len(policy_candidates):
        status = "verified"
    elif verified:
        status = "verified_partial"
    else:
        status = "advertised_unverified"

    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "status": status,
        "manifest_present": bool(manifest_supplied and manifest_value is not None),
        "manifest_source": manifest_source,
        "strict_availability": strict_availability,
        "policy_candidate_tools": policy_candidates,
        "verified_tools": verified,
        "advertised_tools": advertised,
        "degraded_tools": degraded,
        "unavailable_tools": unavailable,
        "unknown_tools": unknown,
        "capability_confirmation_required_for_tools": sorted(
            name for name in policy_candidates if name not in verified
        ),
        "tools": tools,
        "probe_plan": probe_plan,
        "errors": errors,
        "discovery_contract": {
            "host_inventory_is_authoritative_for_presence": True,
            "runtime_local_module_introspection_is_not_host_tool_discovery": True,
            "successful_real_tool_evidence_can_upgrade_to_verified": True,
            "tool_annotations_are_hints_not_authorization": True,
            "automatic_probe_must_be_read_only": True,
            "mutating_or_private_data_probe_for_capability_only": False,
            "host_environment_variables": [
                "JAZN_HOST_TOOL_CAPABILITIES_JSON",
                "JAZN_HOST_TOOL_CAPABILITIES_FILE",
            ],
        },
        "truth_boundary": (
            "Narzędzia hosta istnieją poza procesem Python Jaźni. Runtime może zweryfikować hostowy manifest i "
            "evidence z rzeczywistych wywołań, ale nie może dowieść dostępności web/GitHub/image/file przez "
            "sam import lokalnego modułu, TTY ani PID. Brak manifestu pozostawia availability niezweryfikowane."
        ),
    }


def resolve_policy_tool_availability(
    requested_tools: Iterable[str],
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    capabilities = dict(snapshot or build_host_tool_capability_snapshot())
    requested: list[str] = []
    invalid: list[str] = []
    for value in requested_tools:
        try:
            name = canonical_host_tool_name(str(value))
        except ValueError as exc:
            invalid.append(str(exc))
            continue
        if name not in requested:
            requested.append(name)

    candidates = {str(value) for value in capabilities.get("policy_candidate_tools") or []}
    verified = {str(value) for value in capabilities.get("verified_tools") or []}
    strict = capabilities.get("strict_availability") is True
    if strict:
        allowed = [name for name in requested if name in candidates]
    else:
        catalog = supported_host_tool_names()
        allowed = [name for name in requested if name in candidates or name in catalog]
    unavailable = [name for name in requested if name not in allowed]
    confirmation = [name for name in allowed if name not in verified]
    return {
        "requested_tools": requested,
        "allowed_tools": allowed,
        "unavailable_requested_tools": unavailable,
        "capability_confirmation_required_for_tools": confirmation,
        "availability_basis": (
            "strict_host_manifest" if strict else "catalog_compatibility_requires_host_confirmation"
        ),
        "snapshot_status": capabilities.get("status"),
        "manifest_source": capabilities.get("manifest_source"),
        "invalid_requests": invalid,
    }
