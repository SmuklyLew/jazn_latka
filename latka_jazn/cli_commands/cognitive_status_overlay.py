from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from latka_jazn.core.cognitive_integration_readiness import probe_cognitive_integration
from latka_jazn.core.readiness import evaluate_system_readiness_profile


def apply_cognitive_status_overlay(payload: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    """Replace the legacy unknown cognitive placeholder with a measured tri-state probe."""

    result = dict(payload)
    profile_value = result.get("system_readiness_profile")
    profile = deepcopy(profile_value) if isinstance(profile_value, dict) else {}
    capabilities_value = profile.get("capabilities")
    capabilities = deepcopy(capabilities_value) if isinstance(capabilities_value, dict) else {}
    capabilities["cognitive_integration"] = {
        "classification": "required",
        "ready": probe.get("ready"),
        "status": str(probe.get("status") or "probe_unknown"),
    }
    rebuilt = evaluate_system_readiness_profile(
        profile=str(profile.get("profile") or "interactive_live_voice"),
        capabilities=capabilities,
    )

    capability_value = result.get("capability_readiness")
    capability = dict(capability_value) if isinstance(capability_value, dict) else {}
    capability.update(
        {
            "cognitive_integration_ready": probe.get("ready"),
            "cognitive_integration_status": str(probe.get("status") or "probe_unknown"),
            "cognitive_integration_probe": dict(probe),
            "system_fully_ready": rebuilt["system_fully_ready"],
            "system_readiness_profile": rebuilt,
        }
    )
    result["capability_readiness"] = capability
    result["system_fully_ready"] = rebuilt["system_fully_ready"]
    result["system_readiness_profile"] = rebuilt
    return result


def install_cognitive_status_overlay() -> None:
    """Patch canonical status/doctor dispatch without duplicating diagnostics implementation."""

    from latka_jazn.cli_commands import diagnostics

    current = diagnostics.status_payload
    if bool(getattr(current, "_jazn_cognitive_status_overlay", False)):
        return

    def wrapped_status_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = current(*args, **kwargs)
        return apply_cognitive_status_overlay(payload, probe_cognitive_integration())

    setattr(wrapped_status_payload, "_jazn_cognitive_status_overlay", True)
    setattr(wrapped_status_payload, "_jazn_cognitive_status_original", current)
    diagnostics.status_payload = wrapped_status_payload
