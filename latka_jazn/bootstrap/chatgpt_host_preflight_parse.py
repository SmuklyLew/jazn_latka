from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

from latka_jazn.core.chatgpt_host_executor_contract import HostExecutorObservation
from latka_jazn.core.chatgpt_host_handoff_state import normalize_handoff_state
from latka_jazn.mcp.remote_runtime import classify_public_streamable_http_failover
from latka_jazn.mcp.secure_tunnel import classify_remote_runtime_failover


def json_object_from_file(path_value: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path_value == "-" else Path(path_value).expanduser().read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("host_preflight_input_must_be_json_object")
    return value


def optional_bool(mapping: Mapping[str, Any], key: str, default: bool | None) -> bool | None:
    if key not in mapping:
        return default
    value = mapping[key]
    if value is None and default is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key}_must_be_boolean")
    return value


def optional_int(mapping: Mapping[str, Any], key: str, default: int | None) -> int | None:
    if key not in mapping:
        return default
    value = mapping[key]
    if value is None and default is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key}_must_be_integer")
    return int(value)


def _mapping(value: Any, *, error_code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(error_code)
    return value


def _remote_runtime_evidence(
    item: Mapping[str, Any],
) -> tuple[bool, str, str | None]:
    """Derive positive remote-route capability from concrete route evidence.

    The host-preflight JSON surface is untrusted integration input. A caller
    cannot promote itself to remote_runtime by setting one boolean. The positive
    bit is derived from the same fail-closed transport classifiers used by the
    runtime and is then checked against an optional legacy declaration.
    """

    declared = optional_bool(item, "remote_runtime_transport_available", None)
    raw = item.get("remote_runtime_evidence")
    if raw is None:
        if declared is True:
            raise ValueError(
                "remote_runtime_transport_available_requires_verified_evidence"
            )
        return False, "none", None

    evidence = _mapping(
        raw,
        error_code="remote_runtime_evidence_must_be_object",
    )
    transport = str(evidence.get("transport") or "").strip().lower()
    if transport == "public_streamable_http":
        health = evidence.get("health")
        readiness = evidence.get("readiness")
        result = classify_public_streamable_http_failover(
            endpoint_configured=bool(
                optional_bool(evidence, "endpoint_configured", False)
            ),
            auth_ready=bool(optional_bool(evidence, "auth_ready", False)),
            protocol_compatible=bool(
                optional_bool(evidence, "protocol_compatible", False)
            ),
            health_payload=(
                _mapping(health, error_code="remote_runtime_health_must_be_object")
                if health is not None
                else None
            ),
            readiness_payload=(
                _mapping(
                    readiness,
                    error_code="remote_runtime_readiness_must_be_object",
                )
                if readiness is not None
                else None
            ),
            host_connector_capability_available=optional_bool(
                evidence,
                "host_connector_capability_available",
                None,
            ),
        )
    elif transport == "openai_secure_mcp_tunnel":
        runtime_status = evidence.get("runtime_status")
        result = classify_remote_runtime_failover(
            (
                _mapping(
                    runtime_status,
                    error_code="remote_runtime_status_must_be_object",
                )
                if runtime_status is not None
                else None
            ),
            host_connector_capability_available=optional_bool(
                evidence,
                "host_connector_capability_available",
                None,
            ),
        )
    else:
        raise ValueError(
            "remote_runtime_evidence_transport_must_be_public_streamable_http_or_openai_secure_mcp_tunnel"
        )

    available = result.get("remote_runtime_transport_available") is True
    if declared is not None and declared is not available:
        raise ValueError(
            "remote_runtime_transport_declaration_conflicts_with_verified_evidence"
        )
    return available, transport, str(result.get("reason_code") or "").strip() or None


def executor_observation_from_mapping(item: Mapping[str, Any]) -> HostExecutorObservation:
    process_created = optional_bool(item, "process_created", None)
    if process_created is None:
        raise ValueError("process_created_is_required")
    handoff_state = normalize_handoff_state(str(item.get("execution_handoff_state") or "unknown"))
    remote_available, remote_transport, remote_reason = _remote_runtime_evidence(item)
    return HostExecutorObservation(
        process_created=process_created,
        command_completed=bool(optional_bool(item, "command_completed", False)),
        returncode=optional_int(item, "returncode", None),
        error_class=(str(item["error_class"]).strip() if item.get("error_class") is not None else None),
        alternative_surface_available=bool(optional_bool(item, "alternative_surface_available", False)),
        alternative_probe_count=int(optional_int(item, "alternative_probe_count", 0) or 0),
        filesystem_probe_succeeded=optional_bool(item, "filesystem_probe_succeeded", None),
        surface=str(item.get("surface") or "default"),
        remote_runtime_transport_available=remote_available,
        remote_runtime_transport=remote_transport,
        remote_runtime_reason_code=remote_reason,
        execution_handoff_available=bool(optional_bool(item, "execution_handoff_available", False)),
        execution_handoff_state=handoff_state,
        observation_generation=int(optional_int(item, "observation_generation", 0) or 0),
    )


def executor_observations_from_payload(payload: Mapping[str, Any]) -> tuple[HostExecutorObservation, ...]:
    raw = payload.get("executor_observations", [])
    if not isinstance(raw, list):
        raise ValueError("executor_observations_must_be_array")
    observations: list[HostExecutorObservation] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("executor_observation_must_be_object")
        observations.append(executor_observation_from_mapping(item))
    return tuple(observations)
