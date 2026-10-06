from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from zoneinfo import ZoneInfo

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    build_chatgpt_host_bridge_turn_contract,
    persist_chatgpt_host_visible_reply,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    host_request_lifecycle_state,
    persist_pending_host_request,
)
from latka_jazn.core.epistemic_claim_guard import (
    EpistemicClaimGuard,
    EpistemicClaimStatus,
    EpistemicClaimViolation,
    EpistemicSourceKind,
)
from latka_jazn.core.host_action_evidence import (
    host_action_attestations_to_epistemic_evidence,
    host_action_evidence_scope,
    validate_host_action_evidence,
)
from latka_jazn.core.host_response_candidate_guard import (
    build_host_generation_context,
    evaluate_host_response_candidate,
)
from latka_jazn.tools.chatgpt_host_bridge_helper import build_chatgpt_host_visible_reply_payload


SAMPLE = datetime(2026, 9, 7, 21, 0, 0, tzinfo=timezone.utc)
HEADER = f"🕒 {SAMPLE.astimezone(ZoneInfo('Europe/Warsaw')):%Y-%m-%d %H:%M:%S}"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_host_generation_payload() -> dict[str, object]:
    return {
        "runtime_version": "test-version",
        "trace": {
            "turn_id": "turn-host-action",
            "trace_id": "trace-host-action",
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
        },
        "conversation_decision": {
            "handler_name": "RuntimeTurnTruthGate",
            "route": "ordinary_dialogue",
            "requires_host_model": True,
            "timestamp_contract": {
                "timezone": "Europe/Warsaw",
                "sample_iso": SAMPLE.isoformat(),
                "source": "test_clock",
                "trusted": True,
            },
        },
        "runtime_turn_contract": {
            "turn_id": "turn-host-action",
            "trace_id": "trace-host-action",
            "handler_name": "RuntimeTurnTruthGate",
            "requires_host_model": True,
            "fallback_classification": "cannot_answer_directly",
            "validation": {"accepted": True},
        },
        "final_response_contract": {
            "turn_id": "turn-host-action",
            "trace_id": "trace-host-action",
            "runtime_version": "test-version",
            "requires_host_model": True,
            "timestamp_header": HEADER,
            "timezone": "Europe/Warsaw",
            "timestamp_sample_iso": SAMPLE.isoformat(),
            "timestamp_source": "test_clock",
            "timestamp_trusted": True,
            "author_id": "latka_runtime",
            "author_label": "Łatka",
            "author_source": "jazn_runtime",
            "state_emoticon": "🌿",
        },
        "runtime_truth_gate": {
            "ok": True,
            "normal_response_allowed": False,
            "errors": ["model_guided_speech_required"],
            "degradations": [],
        },
    }


def _bound_host_action(bridge: dict[str, object], *, operation: str = "test") -> dict[str, object]:
    return {
        "turn_id": bridge["turn_id"],
        "trace_id": bridge["trace_id"],
        "host_request_contract_hash": bridge["host_request_contract_hash"],
        "surface": "container",
        "operation": operation,
        "process_created": True,
        "process_pid": 12345,
        "process_exit_code": 0,
        "error_type": None,
        "command_sha256": _sha("python -m pytest -q"),
        "result_sha256": _sha("24 passed"),
    }


def test_meta_examples_and_code_do_not_become_epistemic_self_claims() -> None:
    guard = EpistemicClaimGuard()
    examples = (
        'Prawdziwe zdanie w odpowiedzi, np. „uruchomiłam testy”, może zostać odrzucone.',
        "Przykład: `Wykonałam test Pyright.`",
        "```text\nUruchomiłam runtime.\n```",
        "Nie mogę twierdzić, że uruchomiłam runtime.",
    )
    for text in examples:
        assert guard.assess(text) == []

    with pytest.raises(EpistemicClaimViolation, match="missing_semantically_matching_action_evidence"):
        guard.enforce("Uruchomiłam runtime.")
    with pytest.raises(EpistemicClaimViolation, match="missing_semantically_matching_action_evidence"):
        guard.enforce("Wykonałam test Pyright.")


def test_bound_host_action_evidence_is_fail_closed_and_semantically_scoped() -> None:
    bridge = build_chatgpt_host_bridge_turn_contract(
        _runtime_host_generation_payload(),
        user_text="Sprawdź testy.",
        chat_bridge_meta={},
    )
    raw = _bound_host_action(bridge)
    validation = validate_host_action_evidence(
        [raw],
        expected_turn_id=str(bridge["turn_id"]),
        expected_trace_id=str(bridge["trace_id"]),
        expected_request_contract_hash=str(bridge["host_request_contract_hash"]),
    )
    assert validation["ok"] is True
    evidence = host_action_attestations_to_epistemic_evidence(validation["evidence"])
    assessment = EpistemicClaimGuard().enforce("Wykonałam test Pyright.", evidence=evidence)[0]
    assert assessment.status is EpistemicClaimStatus.SUPPORTED
    assert assessment.source_kind is EpistemicSourceKind.HOST_ACTION
    assert assessment.reason == "bound_host_action_evidence"

    stale = dict(raw)
    stale["trace_id"] = "trace-from-another-turn"
    rejected = validate_host_action_evidence(
        [stale],
        expected_turn_id=str(bridge["turn_id"]),
        expected_trace_id=str(bridge["trace_id"]),
        expected_request_contract_hash=str(bridge["host_request_contract_hash"]),
    )
    assert rejected["ok"] is False
    assert "host_action_trace_id_mismatch:0" in rejected["errors"]

    runtime_start = dict(raw)
    runtime_start["operation"] = "runtime_start"
    runtime_validation = validate_host_action_evidence(
        [runtime_start],
        expected_turn_id=str(bridge["turn_id"]),
        expected_trace_id=str(bridge["trace_id"]),
        expected_request_contract_hash=str(bridge["host_request_contract_hash"]),
    )
    runtime_evidence = host_action_attestations_to_epistemic_evidence(runtime_validation["evidence"])
    supported = EpistemicClaimGuard().enforce("Uruchomiłam runtime.", evidence=runtime_evidence)[0]
    assert supported.source_kind is EpistemicSourceKind.HOST_ACTION

    with pytest.raises(EpistemicClaimViolation):
        EpistemicClaimGuard().enforce("Uruchomiłam runtime.", evidence=evidence)


def test_candidate_guard_runs_epistemic_preflight_before_persistence() -> None:
    context = build_host_generation_context(
        {
            "user_text": "Opisz problem finalizacji.",
            "nlg_plan": {"answer_kind": "natural_dialogue"},
            "allowed_memory_items": [],
        },
        detected_intent="ordinary_conversation",
        route="ordinary_dialogue",
    )
    unsupported = evaluate_host_response_candidate(
        final_text="Uruchomiłam runtime.",
        host_generation_context=context,
        used_memory_item_ids=[],
    )
    assert unsupported["accepted"] is False
    assert (
        "epistemic_claim:runtime_action:missing_semantically_matching_action_evidence"
        in unsupported["violations"]
    )

    quoted = evaluate_host_response_candidate(
        final_text='To był przykład: „uruchomiłam runtime”.',
        host_generation_context=context,
        used_memory_item_ids=[],
    )
    assert not any(item.startswith("epistemic_claim:") for item in quoted["violations"])


def test_deterministic_epistemic_rejection_never_enters_indeterminate_state(tmp_path) -> None:
    runtime = _runtime_host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Co zrobiłaś?", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Uruchomiłam runtime.")
    assert missing == [] and reply is not None

    result, errors = persist_chatgpt_host_visible_reply(
        config=JaznConfig(root=tmp_path),
        payload=reply,
        chat_bridge_meta={},
        contract={},
    )

    assert result is None
    assert any(
        error == "host_candidate:epistemic_claim:runtime_action:missing_semantically_matching_action_evidence"
        for error in errors
    )
    lifecycle = host_request_lifecycle_state(tmp_path, turn_id=str(bridge["turn_id"]))
    assert lifecycle["state"] == "pending"


def test_phase2_passes_bound_host_action_to_persistence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime_host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Co zrobiłaś?", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)
    reply, missing = build_chatgpt_host_visible_reply_payload(runtime, final_text="Wykonałam test Pyright.")
    assert missing == [] and reply is not None
    host_action = [_bound_host_action(bridge, operation="test")]
    captured: dict[str, object] = {}

    class FakeEngine:
        def __init__(self, config) -> None:
            self.config = config

        def shutdown(self) -> None:
            pass

        def persist_final_visible_reply(self, **kwargs):
            captured.update(kwargs)
            return {
                "final_visible_text": kwargs["final_text"],
                "turn_id": kwargs["turn_id"],
                "trace_id": kwargs["trace_id"],
            }

    import latka_jazn.core.engine as engine_module

    monkeypatch.setattr(engine_module, "JaznEngine", FakeEngine)
    with host_action_evidence_scope(
        host_action,
        expected_turn_id=str(bridge["turn_id"]),
        expected_trace_id=str(bridge["trace_id"]),
        expected_request_contract_hash=str(bridge["host_request_contract_hash"]),
    ):
        result, errors = persist_chatgpt_host_visible_reply(
            config=JaznConfig(root=tmp_path),
            payload=reply,
            chat_bridge_meta={},
            contract={},
        )
    assert errors == []
    assert result is not None
    external = captured.get("external_evidence")
    assert isinstance(external, dict)
    assert external.get("host_action_count") == 1
    assert external.get("host_successful_actions") == ["container:test"]



def test_host_action_scope_resets_after_phase2_binding() -> None:
    runtime = _runtime_host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Co zrobiłaś?", chat_bridge_meta={})
    evidence = [_bound_host_action(bridge, operation="test")]
    from latka_jazn.core.host_action_evidence import current_host_action_evidence_context

    assert current_host_action_evidence_context()["evidence"] == []
    with host_action_evidence_scope(
        evidence,
        expected_turn_id=str(bridge["turn_id"]),
        expected_trace_id=str(bridge["trace_id"]),
        expected_request_contract_hash=str(bridge["host_request_contract_hash"]),
    ):
        assert len(current_host_action_evidence_context()["evidence"]) == 1
    assert current_host_action_evidence_context()["evidence"] == []

def test_indeterminate_persistence_defers_daemon_ack_to_durable_reconciliation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    import latka_jazn.cli_commands.host as host_commands

    runtime = _runtime_host_generation_payload()
    bridge = build_chatgpt_host_bridge_turn_contract(runtime, user_text="Witaj", chat_bridge_meta={})
    runtime["chatgpt_host_bridge"] = bridge
    persist_pending_host_request(tmp_path, bridge)

    class FailingEngine:
        def __init__(self, config) -> None:
            self.config = config

        def shutdown(self) -> None:
            pass

        def persist_final_visible_reply(self, **_kwargs):
            raise RuntimeError("append outcome unknown")

    import latka_jazn.core.engine as engine_module

    monkeypatch.setattr(engine_module, "JaznEngine", FailingEngine)

    def forbidden_notification(**_kwargs):
        pytest.fail("indeterminate persistence must defer direct daemon notification")

    monkeypatch.setattr(host_commands, "_notify_daemon", forbidden_notification)
    text = "Witaj."
    args = SimpleNamespace(
        root=tmp_path,
        host_request_contract_hash=bridge["host_request_contract_hash"],
        text=text,
        text_file=None,
        used_memory_item_id=[],
        external_tool_evidence_file=None,
        host_action_evidence_file=None,
        turn_id=bridge["turn_id"],
        trace_id=bridge["trace_id"],
        timestamp_header=bridge["timestamp_header"],
        timezone=bridge["timezone"],
        timestamp_sample_iso=bridge["timestamp_sample_iso"],
        timestamp_source=bridge["timestamp_source"],
        timestamp_trusted=bridge["timestamp_trusted"],
        author_id=bridge["author_id"],
        author_label=bridge["author_label"],
        author_source=bridge["author_source"],
        state_emoticon=bridge["state_emoticon"],
        text_sha256=_sha(text),
        daemon_host="127.0.0.1",
        daemon_port=8787,
    )

    result = host_commands.finalize_payload(args)
    assert result["accepted"] is False
    assert result["host_request_lifecycle"]["state"] == "indeterminate"
    assert result["daemon_job_lifecycle"]["deferred_to_durable_reconciliation"] is True
    assert result["daemon_job_lifecycle"]["reason"] == "host_request_persistence_indeterminate"
