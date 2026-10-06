from __future__ import annotations

from latka_jazn.core.engine_services import EngineServices


class _FakeEngine:
    living_memory_gateway = object()
    cognitive_runtime_coordinator = object()
    route_registry = object()
    route_handler_dispatcher = object()
    affective_granularity = object()
    runtime_response_synthesizer = object()
    runtime_answer_validator = object()


def test_engine_services_exposes_legacy_components_without_taking_ownership() -> None:
    diagnostics = object()
    services = EngineServices.from_legacy_engine(
        _FakeEngine(),
        diagnostics=diagnostics,
    )

    readiness = services.readiness()
    assert readiness["memory"] is True
    assert readiness["cognition"] is True
    assert readiness["route_registry"] is True
    assert readiness["route_dispatcher"] is True
    assert readiness["affect"] is True
    assert readiness["generation"] is True
    assert readiness["validation"] is True
    assert readiness["diagnostics"] is True
    assert readiness["recovery"] is False
    assert readiness["finalization"] is False
    assert readiness["persistence"] is False
