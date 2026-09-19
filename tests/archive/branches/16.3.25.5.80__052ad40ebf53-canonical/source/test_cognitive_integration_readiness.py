from __future__ import annotations

import latka_jazn.core.cognitive_integration_readiness as readiness
from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
from latka_jazn.core.readiness import evaluate_system_readiness_profile


def test_cognitive_integration_probe_measures_coordinator_to_envelope_path() -> None:
    report = readiness.probe_cognitive_integration()
    assert report["outcome"] == "success"
    assert report["ready"] is True
    assert report["status"] == "ready"
    assert all(report["checks"].values())
    assert report["checks"]["prediction_cannot_override_user_intent"] is True
    assert report["checks"]["host_generation_contract_compiled"] is True
    assert "consciousness" in report["truth_boundary"]


def test_cognitive_probe_reports_failure_for_broken_measured_invariant(monkeypatch) -> None:
    real = CognitiveRuntimeCoordinator()

    class BrokenCoordinator:
        def plan_turn(self, **kwargs):
            plan = real.plan_turn(**kwargs)
            plan["prediction_may_override_user_intent"] = True
            return plan

    monkeypatch.setattr(readiness, "CognitiveRuntimeCoordinator", BrokenCoordinator)
    report = readiness.probe_cognitive_integration()
    assert report["outcome"] == "failure"
    assert report["ready"] is False
    assert report["status"] == "integration_invariant_failed"
    assert report["checks"]["prediction_cannot_override_user_intent"] is False


def test_cognitive_probe_preserves_unknown_when_diagnostic_cannot_complete(monkeypatch) -> None:
    class UnavailableCoordinator:
        def plan_turn(self, **_kwargs):
            raise OSError("diagnostic surface unavailable")

    monkeypatch.setattr(readiness, "CognitiveRuntimeCoordinator", UnavailableCoordinator)
    report = readiness.probe_cognitive_integration()
    assert report["outcome"] == "unknown"
    assert report["ready"] is None
    assert report["status"] == "probe_unknown"
    assert report["error_type"] == "OSError"


def test_required_cognitive_probe_blocks_full_readiness_on_failure_or_unknown() -> None:
    ready = evaluate_system_readiness_profile(
        profile="test",
        capabilities={"cognitive_integration": {"classification": "required", "ready": True, "status": "ready"}},
    )
    failed = evaluate_system_readiness_profile(
        profile="test",
        capabilities={"cognitive_integration": {"classification": "required", "ready": False, "status": "failed"}},
    )
    unknown = evaluate_system_readiness_profile(
        profile="test",
        capabilities={"cognitive_integration": {"classification": "required", "ready": None, "status": "probe_unknown"}},
    )
    assert ready["system_fully_ready"] is True
    assert failed["system_fully_ready"] is False
    assert unknown["system_fully_ready"] is False


def test_status_overlay_replaces_legacy_unknown_and_recomputes_system_gate() -> None:
    from latka_jazn.cli_commands.cognitive_status_overlay import apply_cognitive_status_overlay

    base_profile = evaluate_system_readiness_profile(
        profile="interactive_live_voice",
        capabilities={
            "runtime_core": {"classification": "required", "ready": True, "status": "ready"},
            "live_voice": {"classification": "required", "ready": True, "status": "ready"},
            "cognitive_integration": {
                "classification": "unknown",
                "ready": None,
                "status": "requires_cognitive_architecture_audit_or_live_effect_probe",
            },
        },
    )
    payload = {
        "system_fully_ready": base_profile["system_fully_ready"],
        "system_readiness_profile": base_profile,
        "capability_readiness": {
            "cognitive_integration_ready": None,
            "cognitive_integration_status": "requires_cognitive_architecture_audit_or_live_effect_probe",
        },
    }
    result = apply_cognitive_status_overlay(
        payload,
        {"ready": True, "status": "ready", "outcome": "success", "checks": {"coordinator": True}},
    )
    assert result["capability_readiness"]["cognitive_integration_ready"] is True
    assert result["capability_readiness"]["cognitive_integration_status"] == "ready"
    assert result["capability_readiness"]["cognitive_integration_probe"]["outcome"] == "success"
    assert result["system_readiness_profile"]["capabilities"]["cognitive_integration"]["classification"] == "required"
    assert result["system_fully_ready"] is True
