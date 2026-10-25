from __future__ import annotations

from typing import Any

from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version


SCHEMA_VERSION = schema_version("cognitive_integration_probe")


def _is_nonempty_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def probe_cognitive_integration() -> dict[str, Any]:
    """Run a bounded, side-effect-free integration probe for the live cognitive path.

    The probe exercises the same coordinator and turn-envelope types used by
    ``JaznEngine``.  It reports a tri-state result: ``True`` when all measured
    invariants are observed, ``False`` when the integration executes but violates
    an invariant, and ``None`` when the diagnostic itself cannot complete.
    """

    try:
        coordinator = CognitiveRuntimeCoordinator()
        plan = coordinator.plan_turn(
            user_text="Zweryfikuj spójność integracji poznawczej.",
            explicit_intent="runtime_diagnostic",
            classifier_confidence=1.0,
            source_available=True,
            tool_available=True,
        )
        frame = {
            "runtime_version": PACKAGE_VERSION_FULL,
            "turn_trace": {
                "turn_id": "cognitive-readiness-probe-turn",
                "trace_id": "cognitive-readiness-probe-trace",
                "timestamp_header": "",
                "timezone": "Europe/Warsaw",
                "runtime_mode": "diagnostic_probe",
                "client": "runtime_diagnostics",
                "lifecycle": "one_shot",
            },
            "response_format": {"timezone": "Europe/Warsaw"},
            **plan,
        }
        envelope = CognitiveTurnEnvelope.from_cognitive_frame(
            frame,
            user_text="Zweryfikuj spójność integracji poznawczej.",
            client_context={"client": "runtime_diagnostics", "lifecycle": "one_shot"},
            runtime_mode="diagnostic_probe",
        )
    except (OSError, TimeoutError) as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": PACKAGE_VERSION_FULL,
            "outcome": "unknown",
            "ready": None,
            "status": "probe_unknown",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "checks": {},
            "truth_boundary": (
                "Unknown means the diagnostic itself could not complete; it is not success or proof of failure."
            ),
        }
    except Exception as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": PACKAGE_VERSION_FULL,
            "outcome": "failure",
            "ready": False,
            "status": "integration_execution_failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "checks": {},
            "truth_boundary": (
                "Failure means the measured cognitive integration path raised during the bounded probe; "
                "it does not assert anything about consciousness or biological cognition."
            ),
        }

    control_effects = plan.get("control_effects")
    control = control_effects if isinstance(control_effects, dict) else {}
    lineage = envelope.cognitive_lineage.summary()
    state_graph = envelope.cognitive_state_graph.summary()
    host_generation_contract = envelope.cognitive_frame.get("host_generation_contract")
    full_canon = envelope.cognitive_frame.get("full_canon_model_context")
    checks = {
        "coordinator_plan_present": _is_nonempty_mapping(plan),
        "control_effects_present": _is_nonempty_mapping(control),
        "control_max_tool_calls_typed": isinstance(control.get("max_tool_calls"), int)
        and not isinstance(control.get("max_tool_calls"), bool)
        and int(control.get("max_tool_calls", -1)) >= 0,
        "control_prediction_advisory_only": control.get("prediction_is_advisory_only") is True,
        "prediction_cannot_override_user_intent": plan.get("prediction_may_override_user_intent") is False,
        "reasoning_plan_present": _is_nonempty_mapping(plan.get("reasoning_plan")),
        "turn_binding_preserved": (
            envelope.trace.turn_id == "cognitive-readiness-probe-turn"
            and envelope.trace.trace_id == "cognitive-readiness-probe-trace"
        ),
        "lineage_initialized": int(lineage.get("lineage_observation_count") or 0) >= 1
        and int(lineage.get("lineage_break_count") or 0) == 0,
        "state_graph_initialized": int(state_graph.get("state_graph_node_count") or 0) >= 1
        and int(state_graph.get("state_graph_break_count") or 0) == 0,
        "full_canon_compiled": _is_nonempty_mapping(full_canon),
        "host_generation_contract_compiled": _is_nonempty_mapping(host_generation_contract),
    }
    ready = all(checks.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_version": PACKAGE_VERSION_FULL,
        "outcome": "success" if ready else "failure",
        "ready": ready,
        "status": "ready" if ready else "integration_invariant_failed",
        "checks": checks,
        "control_effects": {
            "max_tool_calls": control.get("max_tool_calls"),
            "requires_verification": control.get("requires_verification"),
            "prediction_is_advisory_only": control.get("prediction_is_advisory_only"),
        },
        "lineage_summary": lineage,
        "state_graph_summary": state_graph,
        "truth_boundary": (
            "This is a bounded operational probe of coordinator→turn-envelope integration. "
            "It measures software invariants only and does not prove general intelligence, subjective experience, or consciousness."
        ),
    }
