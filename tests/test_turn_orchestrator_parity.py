from pathlib import Path
from textwrap import dedent
from typing import Any
import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_composition import RuntimeCompositionRoot
from latka_jazn.core.turn_execution import TurnExecutionContext
import latka_jazn.core.engine as engine_module
import latka_jazn.core.dialogue_router as router_module


def _contracts(envelope):
    result = envelope.to_dict()
    decision = result["conversation_decision"]
    turn = result["runtime_turn_contract"]
    handler = decision.get("handler_result") or {}
    frame = result["cognitive_frame"]
    return {
        "intent": turn["detected_intent"], "route": turn["route"],
        "handler": turn["handler_name"], "required": handler.get("required_components"),
        "satisfied": handler.get("satisfied_components"), "missing": handler.get("missing_components"),
        "validation": turn["validation"], "requires_host": turn["requires_host_model"],
        "fallback": decision["fallback_classification"],
        "origin_truth": decision["origin_truth_valid"],
        "source": decision["source_origin_detail"],
        "memory_gate": (frame.get("memory_context") or {}).get("gate"),
        "model_retry_count": decision.get("model_guided_retry_count"),
    }


@pytest.mark.parametrize("text", ["Hej.", "Jak działa pamięć?", "Przypomnij sobie spacer nad rzeką."])
def test_deterministic_pipeline_contract_parity_without_external_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str):
    for name in ("JAZN_NETWORK_TIME_FIRST", "JAZN_NETWORK_TIME_IN_TURN", "JAZN_ALLOW_NETWORK", "JAZN_DICTIONARY_ALLOW_NETWORK"):
        monkeypatch.setenv(name, "0")
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "null")
    monkeypatch.setenv("JAZN_LLM_ROUTE_SKIP_LOCAL_PROBE", "1")
    fixture = Path(__file__).parent / "fixtures/v109_process_turn.txt"
    namespace = dict(vars(engine_module))
    exec(compile(dedent(fixture.read_text(encoding="utf-8")), str(fixture), "exec"), namespace)
    baseline = namespace["process_turn"]
    router_fixture = Path(__file__).parent / "fixtures/v110_dialogue_resolve.txt"
    router_namespace = dict(vars(router_module))
    exec(compile(dedent(router_fixture.read_text(encoding="utf-8")), str(router_fixture), "exec"), router_namespace)
    monkeypatch.setattr(router_module.DialogueRouter, "resolve", router_namespace["resolve"])

    outcomes = []
    for mode in ("baseline", "canonical"):
        root = RuntimeCompositionRoot(JaznConfig(root=tmp_path / mode / "runtime"))
        engine: Any = root.create_engine()
        context = TurnExecutionContext.create(request_id="parity-request", turn_id="parity-turn", trace_id="parity-trace", timeout_seconds=90)
        client = {"client": "chatgpt", "lifecycle": "persistent_session", "_turn_context": context, "no_carryover": True}
        try:
            envelope = baseline(engine, text, client_context=client) if mode == "baseline" else engine.process_turn(text, client_context=client)
            assert envelope.trace.turn_id == "parity-turn"
            assert envelope.trace.trace_id == "parity-request"
            assert not context._canonical_committed
            outcomes.append(_contracts(envelope))
        finally:
            root.close()
    assert outcomes[0] == outcomes[1]
