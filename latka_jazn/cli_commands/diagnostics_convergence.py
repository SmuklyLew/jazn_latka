from __future__ import annotations

"""Converge legacy diagnostics onto the optional-MEMORY readiness contract.

The historical diagnostics module exposed ``transactional_memory_ready`` and
then accidentally used it as a prerequisite for ``runtime_core_ready``. That
made a valid SYSTEM-only installation look broken. This module keeps the
transactional-memory diagnostic intact while projecting the canonical v16.3
contract: persistent MEMORY is an optional capability unless the operator
explicitly selects ``JAZN_MEMORY_MODE=required``.
"""

from copy import deepcopy
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.readiness import evaluate_system_readiness_profile
from latka_jazn.runtime.capability_matrix import build_capability_matrix
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("diagnostics_convergence")
_INSTALL_MARKER = "_optional_memory_diagnostics_convergence_installed"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _canonical_raw_memory_status(cfg: JaznConfig) -> dict[str, Any]:
    raw = cfg.memory_root / "raw"
    chat = raw / "chat.html"
    enabled = cfg.memory_availability.persistent_memory_enabled
    return {
        "schema_version": schema_version("raw_memory_startup_status"),
        "memory_root": str(cfg.memory_root),
        "persistent_memory_enabled": enabled,
        "chat_html_present": bool(enabled and chat.is_file()),
        "chat_html_size_bytes": chat.stat().st_size if enabled and chat.is_file() else None,
        "status": (
            "raw_available"
            if enabled and chat.is_file()
            else "memory_disabled_by_policy"
            if cfg.memory_mode == "off"
            else "raw_missing"
        ),
        "truth_boundary": (
            "Raw-memory startup status is resolved from the canonical external MEMORY root. "
            "SYSTEM core_state is never treated as autobiographical raw memory."
        ),
    }


def apply_status_convergence(
    payload: dict[str, Any],
    *,
    root: Path | str,
) -> dict[str, Any]:
    """Return one diagnostics payload with optional MEMORY treated correctly."""

    result = deepcopy(payload)
    runtime_root = Path(root).expanduser().resolve()
    cfg = JaznConfig(root=runtime_root)
    memory = cfg.memory_availability
    memory_dict = memory.to_dict()
    daemon = _mapping(result.get("daemon"))
    active_state = str(
        daemon.get("active_state")
        or daemon.get("runtime_active_state")
        or "inactive"
    )
    process_ok = bool(
        result.get("process_ok")
        if isinstance(result.get("process_ok"), bool)
        else active_state in {"active_trusted", "active_degraded"}
    )
    runtime_write_ready = result.get("runtime_write_ready") is True
    transactional = _mapping(result.get("transactional_memory"))
    transactional_ready = transactional.get("ready") is True

    runtime_core_ready = bool(
        process_ok
        and runtime_write_ready
        and memory.required_satisfied
        and memory.core_runtime_allowed
    )

    result["runtime_core_ready"] = runtime_core_ready
    result["fully_ready"] = runtime_core_ready
    result["fully_ready_compatibility_alias_of"] = "runtime_core_ready"
    result["memory_availability"] = memory_dict
    result["transactional_memory_required_for_core_runtime"] = False
    result["persistent_memory_required_for_core_runtime"] = memory.persistent_memory_required

    startup = _mapping(result.get("startup"))
    startup["raw_memory_status"] = _canonical_raw_memory_status(cfg)
    startup["memory_availability"] = memory_dict
    result["startup"] = startup

    blocking_reasons: list[str] = []
    if not process_ok:
        blocking_reasons.append("daemon_not_confirmed")
    if not runtime_write_ready:
        blocking_reasons.append("runtime_write_not_ready")
    if not memory.required_satisfied:
        blocking_reasons.append("persistent_memory_required_missing")
    result["operational_reasons"] = blocking_reasons

    degradations: list[str] = []
    if not memory.persistent_memory_enabled:
        degradations.append(
            "persistent_memory_disabled_by_policy"
            if memory.mode == "off"
            else "persistent_memory_optional_absent"
        )
    elif not transactional_ready:
        degradations.append("transactional_memory_not_ready_nonblocking")
    result["operational_degradations"] = degradations

    if not process_ok:
        operational_state = "inactive_or_untrusted"
    elif not memory.required_satisfied:
        operational_state = "active_required_memory_missing"
    elif not runtime_write_ready:
        operational_state = "active_runtime_write_degraded"
    elif memory.persistent_memory_enabled and not transactional_ready:
        operational_state = "active_ready_memory_degraded"
    elif memory.mode == "off":
        operational_state = "active_ready_memory_off"
    elif not memory.persistent_memory_enabled:
        operational_state = "active_ready_system_only"
    elif active_state == "active_trusted":
        operational_state = "active_ready"
    else:
        operational_state = "active_process_degraded"
    result["operational_state"] = operational_state

    capability = _mapping(result.get("capability_readiness"))
    capability.update(
        {
            "runtime_core_ready": runtime_core_ready,
            "runtime_ready": runtime_core_ready,
            "persistent_memory_mode": memory.mode,
            "persistent_memory_present": memory.persistent_memory_present,
            "persistent_memory_enabled": memory.persistent_memory_enabled,
            "persistent_memory_required": memory.persistent_memory_required,
            "persistent_memory_required_satisfied": memory.required_satisfied,
            "transactional_memory_ready": transactional_ready,
            "transactional_memory_required_for_core_runtime": False,
            "memory_availability": memory_dict,
        }
    )

    old_profile = _mapping(result.get("system_readiness_profile"))
    old_capabilities = _mapping(old_profile.get("capabilities"))
    old_capabilities["runtime_core"] = {
        "classification": "required",
        "ready": runtime_core_ready,
        "status": "ready" if runtime_core_ready else "not_ready",
    }
    old_capabilities["persistent_memory"] = {
        "classification": (
            "required" if memory.persistent_memory_required else "degraded_allowed"
        ),
        "ready": memory.persistent_memory_enabled,
        "status": memory.status,
    }
    old_capabilities["transactional_memory"] = {
        "classification": "degraded_allowed",
        "ready": transactional_ready,
        "status": str(transactional.get("status") or ("ready" if transactional_ready else "not_ready")),
    }
    profile_name = str(old_profile.get("profile") or "interactive_live_voice")
    corrected_profile = evaluate_system_readiness_profile(
        profile=profile_name,
        capabilities=old_capabilities,
    )
    result["system_readiness_profile"] = corrected_profile
    result["system_fully_ready"] = corrected_profile["system_fully_ready"]
    capability["system_fully_ready"] = corrected_profile["system_fully_ready"]
    capability["system_readiness_profile"] = corrected_profile
    capability["truth_boundary"] = (
        "Runtime core readiness is independent from optional persistent MEMORY and transactional L1/L2/L3. "
        "Memory capabilities remain separately observable and fail closed for recall claims."
    )
    result["capability_readiness"] = capability

    gateway_status = {
        "gateway_ok": bool(daemon.get("endpoint_reachable") or process_ok),
        "daemon_reachable": bool(daemon.get("endpoint_reachable") or process_ok),
        "daemon_auth_configured": bool(daemon.get("auth_required", True)),
        "transport": "canonical_runtime_daemon_status",
        "daemon": {
            **daemon,
            "runtime_core_ready": runtime_core_ready,
        },
    }
    try:
        result["capability_matrix"] = build_capability_matrix(
            runtime_root,
            gateway_status=gateway_status,
            mcp_tasks_supported=True,
        )
    except Exception as exc:
        result["capability_matrix"] = {
            "schema_version": SCHEMA_VERSION,
            "conversation_ready": runtime_core_ready,
            "ordinary_dialogue_allowed": bool(
                runtime_core_ready and memory.ordinary_dialogue_allowed
            ),
            "error": f"capability_matrix_probe_failed:{type(exc).__name__}:{exc}",
        }

    result["status_exit_contract"] = (
        "zero_only_for_confirmed_active_process; runtime_core_ready requires process, operational runtime-write, "
        "and explicit memory-mode policy satisfaction; optional persistent MEMORY, recall and transactional L1/L2/L3 "
        "are reported separately and do not block SYSTEM-only dialogue"
    )
    result["diagnostics_convergence"] = {
        "schema_version": SCHEMA_VERSION,
        "optional_memory_contract_applied": True,
    }
    return result


def install(module: ModuleType) -> None:
    """Install once on the canonical diagnostics module."""

    if getattr(module, _INSTALL_MARKER, False):
        return
    original = getattr(module, "status_payload")
    if not callable(original):
        raise TypeError("diagnostics_status_payload_missing")

    @wraps(original)
    def converged(root: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raw_value = original(root, *args, **kwargs)
        raw = _mapping(raw_value)
        return apply_status_convergence(raw, root=root)

    setattr(module, "status_payload", converged)
    setattr(module, _INSTALL_MARKER, True)
    setattr(module, "_status_payload_before_optional_memory_convergence", original)


__all__ = ["apply_status_convergence", "install"]
