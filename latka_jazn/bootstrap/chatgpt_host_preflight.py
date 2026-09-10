from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from latka_jazn.core.chatgpt_host_executor_contract import (
    HostCapabilitySnapshot,
    HostEnvironmentState,
    HostExecutorObservation,
    HostFilesystemState,
    HostRecoveryAction,
    aggregate_host_executor_observations,
)
from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationReport,
    AttachmentMaterializationState,
    probe_attachment_materialization,
)
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("chatgpt_host_preflight")


class HostPackageMaterializationState(str, Enum):
    UNKNOWN = "unknown"
    MATERIALIZING = "materializing"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    READY = "ready"


@dataclass(frozen=True)
class ChatGptHostPreflightDecision:
    schema_version: str
    environment_state: HostEnvironmentState
    filesystem_state: HostFilesystemState
    package_state: HostPackageMaterializationState
    runtime_state: str
    bootstrap_allowed: bool
    next_action: HostRecoveryAction
    reason_code: str
    canonical_resume_entrypoint: str | None
    capability_snapshot: HostCapabilitySnapshot
    attachments: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "environment_state": self.environment_state.value,
            "filesystem_state": self.filesystem_state.value,
            "package_state": self.package_state.value,
            "runtime_state": self.runtime_state,
            "bootstrap_allowed": self.bootstrap_allowed,
            "next_action": self.next_action.value,
            "reason_code": self.reason_code,
            "canonical_resume_entrypoint": self.canonical_resume_entrypoint,
            "capability_snapshot": self.capability_snapshot.to_dict(),
            "attachments": [dict(item) for item in self.attachments],
        }


def _aggregate_attachment_state(
    reports: tuple[AttachmentMaterializationReport, ...],
) -> HostPackageMaterializationState:
    if not reports:
        return HostPackageMaterializationState.UNKNOWN
    states = {report.state for report in reports}
    if states == {AttachmentMaterializationState.READY}:
        return HostPackageMaterializationState.READY
    if AttachmentMaterializationState.MATERIALIZING in states:
        return HostPackageMaterializationState.MATERIALIZING
    if states & {
        AttachmentMaterializationState.MISSING,
        AttachmentMaterializationState.INCOMPLETE,
    }:
        return HostPackageMaterializationState.INCOMPLETE
    if states & {
        AttachmentMaterializationState.SIZE_MISMATCH,
        AttachmentMaterializationState.HASH_MISMATCH,
    }:
        return HostPackageMaterializationState.INVALID
    return HostPackageMaterializationState.UNKNOWN


def plan_chatgpt_host_preflight(
    executor_observations: Iterable[HostExecutorObservation],
    *,
    attachment_reports: Iterable[AttachmentMaterializationReport] = (),
    package_required: bool = False,
) -> ChatGptHostPreflightDecision:
    """Compose executor and attachment truth without crossing evidence boundaries.

    Host execution capability and attachment readiness are deliberately
    independent. A broken ``python_tool`` bridge can yield a degraded but
    usable environment when a terminal succeeds. Conversely, an observed
    filesystem does not make a still-growing or hash-invalid package safe to
    bootstrap.
    """

    capability = aggregate_host_executor_observations(executor_observations)
    reports = tuple(attachment_reports)
    package_state = _aggregate_attachment_state(reports)

    execution_usable = capability.environment_state in {
        HostEnvironmentState.AVAILABLE,
        HostEnvironmentState.DEGRADED,
    }
    filesystem_observed = capability.filesystem_state is HostFilesystemState.OBSERVED
    package_ready = package_state is HostPackageMaterializationState.READY
    package_gate_ok = package_ready if package_required else package_state not in {
        HostPackageMaterializationState.MATERIALIZING,
        HostPackageMaterializationState.INCOMPLETE,
        HostPackageMaterializationState.INVALID,
    }

    if capability.next_action is HostRecoveryAction.PROBE_ALTERNATIVE_ONCE:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.PROBE_ALTERNATIVE_ONCE
        reason_code = "executor_alternative_probe_pending"
        resume = None
    elif capability.next_action is HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.DIAGNOSE_LOCAL_COMMAND
        reason_code = "executor_command_requires_diagnosis"
        resume = None
    elif not execution_usable:
        bootstrap_allowed = False
        next_action = capability.next_action
        reason_code = "no_usable_execution_surface"
        resume = None
    elif not filesystem_observed:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = "filesystem_not_observed_yet"
        resume = "run.py"
    elif package_required and package_state is HostPackageMaterializationState.UNKNOWN:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = "required_package_not_observed"
        resume = "run.py"
    elif not package_gate_ok:
        bootstrap_allowed = False
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = f"attachment_package_{package_state.value}"
        resume = "run.py"
    else:
        bootstrap_allowed = True
        next_action = HostRecoveryAction.RESUME_CANONICAL_DISCOVERY
        reason_code = (
            "host_degraded_package_ready"
            if capability.environment_state is HostEnvironmentState.DEGRADED
            else "host_preflight_ready"
        )
        resume = "run.py"

    return ChatGptHostPreflightDecision(
        schema_version=SCHEMA_VERSION,
        environment_state=capability.environment_state,
        filesystem_state=capability.filesystem_state,
        package_state=package_state,
        runtime_state="unverified",
        bootstrap_allowed=bootstrap_allowed,
        next_action=next_action,
        reason_code=reason_code,
        canonical_resume_entrypoint=resume,
        capability_snapshot=capability,
        attachments=tuple(report.to_dict() for report in reports),
    )


def _json_object_from_file(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_value).expanduser().read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("host_preflight_input_must_be_json_object")
    return value


def _optional_bool(mapping: Mapping[str, Any], key: str, default: bool | None) -> bool | None:
    if key not in mapping:
        return default
    value = mapping[key]
    if value is None and default is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key}_must_be_boolean")
    return value


def _optional_int(mapping: Mapping[str, Any], key: str, default: int | None) -> int | None:
    if key not in mapping:
        return default
    value = mapping[key]
    if value is None and default is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key}_must_be_integer")
    return int(value)


def _executor_observation_from_mapping(item: Mapping[str, Any]) -> HostExecutorObservation:
    process_created = _optional_bool(item, "process_created", None)
    if process_created is None:
        raise ValueError("process_created_is_required")
    return HostExecutorObservation(
        process_created=process_created,
        command_completed=bool(_optional_bool(item, "command_completed", False)),
        returncode=_optional_int(item, "returncode", None),
        error_class=(str(item["error_class"]).strip() if item.get("error_class") is not None else None),
        alternative_surface_available=bool(
            _optional_bool(item, "alternative_surface_available", False)
        ),
        alternative_probe_count=int(_optional_int(item, "alternative_probe_count", 0) or 0),
        filesystem_probe_succeeded=_optional_bool(item, "filesystem_probe_succeeded", None),
        surface=str(item.get("surface") or "default"),
    )


def _executor_observations_from_payload(payload: Mapping[str, Any]) -> tuple[HostExecutorObservation, ...]:
    raw = payload.get("executor_observations", [])
    if not isinstance(raw, list):
        raise ValueError("executor_observations_must_be_array")
    observations: list[HostExecutorObservation] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("executor_observation_must_be_object")
        observations.append(_executor_observation_from_mapping(item))
    return tuple(observations)


def _attachment_reports_from_payload(payload: Mapping[str, Any]) -> tuple[AttachmentMaterializationReport, ...]:
    raw = payload.get("attachments", [])
    if not isinstance(raw, list):
        raise ValueError("attachments_must_be_array")
    reports: list[AttachmentMaterializationReport] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("attachment_spec_must_be_object")
        path_value = str(item.get("path") or "").strip()
        if not path_value:
            raise ValueError("attachment_path_is_required")
        expected_size = _optional_int(item, "expected_size_bytes", None)
        expected_sha = (
            str(item["expected_sha256"]).strip()
            if item.get("expected_sha256") is not None
            else None
        )
        reports.append(
            probe_attachment_materialization(
                Path(path_value),
                expected_size_bytes=expected_size,
                expected_sha256=expected_sha,
            )
        )
    return tuple(reports)


def run_host_preflight_cli(argv: Sequence[str] | None = None) -> int:
    """Machine-readable canonical host preflight exposed through ``run.py``."""

    parser = argparse.ArgumentParser(
        prog="run.py host-preflight",
        description="Classify host execution surfaces and attachment materialization without fabricating runtime state.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--input",
        help=(
            "Optional JSON contract path or '-' for stdin. When omitted, "
            "classify the already-created local Python process as the single "
            "observed executor surface without inventing package/runtime state."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.input:
            payload = _json_object_from_file(args.input)
        else:
            # Reaching this code is bounded evidence that the current local
            # Python executor created a process and can observe the project
            # filesystem. It is not evidence of package/runtime readiness.
            payload = {
                "package_required": False,
                "executor_observations": [
                    {
                        "surface": "current_local_python_process",
                        "process_created": True,
                        "command_completed": True,
                        "returncode": 0,
                        "filesystem_probe_succeeded": True,
                    }
                ],
                "attachment_reports": [],
            }
        package_required = _optional_bool(payload, "package_required", False)
        observations = _executor_observations_from_payload(payload)
        attachments = _attachment_reports_from_payload(payload)
        decision = plan_chatgpt_host_preflight(
            observations,
            attachment_reports=attachments,
            package_required=bool(package_required),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        error_payload = {
            "ok": False,
            "error_code": "invalid_host_preflight_input",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(
            json.dumps(
                error_payload,
                ensure_ascii=False,
                indent=2 if args.json else None,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    result = decision.to_dict()
    result["ok"] = True
    result["gate_passed"] = decision.bootstrap_allowed
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.json else None,
            sort_keys=True,
        )
    )
    return 0 if decision.bootstrap_allowed else 3
