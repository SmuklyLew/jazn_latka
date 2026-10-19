from __future__ import annotations

from types import SimpleNamespace
import pytest

from latka_jazn.core.turn_orchestrator import TurnOrchestrator
from latka_jazn.core.turn_pipeline_state import TurnRequest


STAGES = [
    ("context", "build"), ("dialogue", "classify"), ("frame", "prepare_turn"),
    ("affect", "project"), ("dialogue", "resolve_and_execute"),
    ("response", "produce"), ("validation", "validate_candidate"),
    ("recovery", "resolve"), ("validation", "assess_reasoning"),
    ("recovery", "resolve_reasoning"), ("validation", "record_final_validation"),
    ("recovery", "classify_result"),
    ("validation", "complete_validation"), ("response", "build_provenance"),
    ("response", "build_contract"), ("persistence", "checkpoint"),
    ("persistence", "prepare_result"),
]


def _pipeline(fail: str | None = None):
    orchestrator = object.__new__(TurnOrchestrator)
    calls = []
    for component, method in STAGES:
        if not hasattr(orchestrator, component):
            setattr(orchestrator, component, SimpleNamespace())
        def run(state, name=method):
            calls.append((name, state))
            if name == fail:
                raise RuntimeError("injected-stage-failure")
            if name == "prepare_result":
                state.envelope = SimpleNamespace(trace=SimpleNamespace(turn_id="same-turn"))
        setattr(getattr(orchestrator, component), method, run)
    return orchestrator, calls


def test_orchestration_uses_one_request_and_one_turn_local_state():
    pipeline, calls = _pipeline()
    request = TurnRequest("synthetic current turn", {"session_id": "existing-owner"})
    result = pipeline.process(request)
    assert [name for name, state in calls] == [method for component, method in STAGES]
    assert len({id(state) for name, state in calls}) == 1
    assert all(state.request is request for name, state in calls)
    assert result.envelope.trace.turn_id == "same-turn"


def test_validation_failure_cannot_reach_persistence_or_fallback():
    pipeline, calls = _pipeline("complete_validation")
    with pytest.raises(RuntimeError, match="injected-stage-failure"):
        pipeline.process(TurnRequest("synthetic candidate"))
    assert [name for name, state in calls][-1] == "complete_validation"
    assert not {"build_contract", "checkpoint", "prepare_result"}.intersection(name for name, state in calls)


def test_next_turn_does_not_reuse_previous_pipeline_state():
    pipeline, calls = _pipeline()
    pipeline.process(TurnRequest("first"))
    first = calls[0][1]
    calls.clear()
    pipeline.process(TurnRequest("second"))
    assert calls[0][1] is not first
    assert first.request.text == "first"
