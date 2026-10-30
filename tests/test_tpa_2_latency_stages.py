"""Opt-in health diagnostics record only stage durations, not dialogue content."""
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_orchestrator import TurnOrchestrator
from latka_jazn.core.turn_pipeline_state import TurnRequest


NAMES = ("pipeline_prepare", "pipeline_route", "pipeline_response",
         "pipeline_validation", "pipeline_settlement")


class FakeStep:
    def __getattr__(self, name):
        def execute(state):
            if name == "prepare_result":
                state.envelope = {"ok": True}
        return execute


def _orchestrator():
    instance = object.__new__(TurnOrchestrator)
    for key in ("context", "dialogue", "frame", "affect", "response",
                "validation", "recovery", "persistence"):
        setattr(instance, key, FakeStep())
    return instance


def test_opt_in_stage_timing_is_numeric_and_complete(monkeypatch):
    monkeypatch.setenv("JAZN_TURN_LATENCY_DIAGNOSTICS", "1")
    turn = TurnExecutionContext.create(timeout_seconds=30, audit_db_path=None)
    result = _orchestrator().process(TurnRequest("synthetic-probe"), turn)
    assert result.envelope == {"ok": True}
    stages = turn.snapshot()["stages"]
    for name in NAMES:
        assert stages[name]["status"] == "completed"
        assert isinstance(stages[name]["duration_ms"], (int, float))
        assert stages[name]["duration_ms"] >= 0


def test_diagnostics_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("JAZN_TURN_LATENCY_DIAGNOSTICS", raising=False)
    turn = TurnExecutionContext.create(timeout_seconds=30, audit_db_path=None)
    _orchestrator().process(TurnRequest("synthetic-probe"), turn)
    stages = turn.snapshot()["stages"]
    assert all(stages[name]["status"] == "not_started" for name in NAMES)
