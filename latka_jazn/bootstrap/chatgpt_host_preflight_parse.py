from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

from latka_jazn.core.chatgpt_host_executor_contract import HostExecutorObservation
from latka_jazn.core.chatgpt_host_handoff_state import normalize_handoff_state


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


def executor_observation_from_mapping(item: Mapping[str, Any]) -> HostExecutorObservation:
    process_created = optional_bool(item, "process_created", None)
    if process_created is None:
        raise ValueError("process_created_is_required")
    handoff_state = normalize_handoff_state(str(item.get("execution_handoff_state") or "unknown"))
    return HostExecutorObservation(
        process_created=process_created,
        command_completed=bool(optional_bool(item, "command_completed", False)),
        returncode=optional_int(item, "returncode", None),
        error_class=(str(item["error_class"]).strip() if item.get("error_class") is not None else None),
        alternative_surface_available=bool(optional_bool(item, "alternative_surface_available", False)),
        alternative_probe_count=int(optional_int(item, "alternative_probe_count", 0) or 0),
        filesystem_probe_succeeded=optional_bool(item, "filesystem_probe_succeeded", None),
        surface=str(item.get("surface") or "default"),
        remote_runtime_transport_available=bool(optional_bool(item, "remote_runtime_transport_available", False)),
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
