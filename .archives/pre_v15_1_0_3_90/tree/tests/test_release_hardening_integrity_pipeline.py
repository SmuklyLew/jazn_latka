from __future__ import annotations

from datetime import datetime, timezone
import copy
import hashlib

from latka_jazn.core.final_response_contract import FinalResponseContract
from latka_jazn.core.host_visible_finalization import finalize_host_visible_text
from latka_jazn.core.runtime_session import JaznRuntimeSession

HEADER = "[🕒 2026-07-16 12:00:00 GMT+2, czwartek, Europe/Warsaw]"
BODY = "Działam uczciwie."
VISIBLE = f"{HEADER} 🌿\n{BODY}"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decision() -> dict:
    return {
        "fallback_classification": "rule_handler_response",
        "route": "presence",
        "handler_name": "presence_handler",
        "handler_result": {
            "handler_name": "presence_handler",
            "body": BODY,
            "required_components": ["presence"],
            "satisfied_components": ["presence"],
            "missing_components": [],
        },
        "final_answer_validation": {"accepted": True, "must_regenerate": False},
        "template_origin": {},
        "runtime_provenance": {
            "handler_name": "presence_handler",
            "source_origin_detail": "presence_handler",
            "response_generation_mode": "runtime_dynamic",
            "exact_runtime_text": BODY,
            "runtime_text_hash": _sha(BODY),
            "visible_answer_text": VISIBLE,
            "visible_answer_hash": _sha(VISIBLE),
        },
        "visible_answer_hash": _sha(VISIBLE),
        "runtime_text_hash": _sha(BODY),
        "timestamp_contract": {
            "trusted": False,
            "source": "local_machine",
            "sample_iso": datetime.now(timezone.utc).isoformat(),
            "require_trusted_in_final_visible": False,
            "allow_degraded_local_visible": True,
        },
    }


def _envelope(*, final_text: str = VISIBLE, mutate_contract: bool = False) -> dict:
    decision = _decision()
    contract = FinalResponseContract.build(
        turn_id="turn-1",
        trace_id="trace-1",
        runtime_version="v15.1.0.3.89",
        timestamp_header=HEADER,
        timezone="Europe/Warsaw",
        state_emoticon="🌿",
        body=BODY,
        conversation_decision=decision,
    ).to_dict()
    if mutate_contract:
        contract["final_visible_text"] = final_text
    return {
        "trace": {"timestamp_header": HEADER, "turn_id": "turn-1", "trace_id": "trace-1"},
        "cognitive_frame": {"conversation_decision": decision},
        "runtime_turn_contract": {
            "turn_id": "turn-1", "trace_id": "trace-1",
            "validation": {"accepted": True, "must_regenerate": False},
            "requires_host_model": False,
        },
        "final_response_contract": contract,
        "final_visible_text": final_text,
    }


class _Envelope:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def to_dict(self) -> dict:
        return copy.deepcopy(self.payload)


class _Engine:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def process_turn(self, _text: str, *, client_context: dict) -> _Envelope:
        assert client_context["session_id"] == "session-1"
        return _Envelope(self.payload)


class _State:
    session_id = "session-1"
    last_user_text = ""
    last_intent = ""
    last_route = ""

    def update(self, *, user_text: str, intent: str, route: str) -> None:
        self.last_user_text = user_text
        self.last_intent = intent
        self.last_route = route

    def to_dict(self) -> dict:
        return {"session_id": self.session_id}


class _StateStore:
    last_load_metadata: dict = {}

    def save(self, _state: _State) -> dict:
        return {"session_state_saved": True}


def _session(payload: dict) -> JaznRuntimeSession:
    session = object.__new__(JaznRuntimeSession)
    session.engine = _Engine(payload)
    session.state_store = _StateStore()
    session.state = _State()
    session.no_carryover = True
    session._turn_count = 0
    return session


def test_process_user_text_restores_only_missing_timestamp_from_verified_contract() -> None:
    result = _session(_envelope(final_text=BODY)).process_user_text("test")
    assert result["final_visible_text"] == VISIBLE
    assert result["runtime_provenance"]["visible_answer_hash"] == _sha(VISIBLE)
    audit = result["final_visible_integrity_repair_audit"][0]
    assert audit["applied"] is True
    assert audit["body_unchanged"] is True
    assert audit["provenance_hash_preserved"] is True
    assert audit["original_visible_text_sha256"] == _sha(BODY)
    assert audit["repaired_visible_text_sha256"] == _sha(VISIBLE)
    assert result["final_visible_integrity"]["valid"] is True


def test_process_user_text_rejects_changed_text_without_laundering_hash() -> None:
    changed = f"{HEADER} 🌿\nTekst zmieniony po obliczeniu hasha."
    result = _session(_envelope(final_text=changed)).process_user_text("test")
    assert result["final_visible_text"] != changed
    assert result["normal_response_blocked"] is True
    assert result["runtime_provenance"]["visible_answer_hash"] == _sha(VISIBLE)
    assert result["final_visible_integrity"]["valid"] is False
    assert result["final_visible_integrity_consensus"]["mismatch"] is True
    assert result["final_visible_integrity_consensus"]["values"]["pre_repair_contract"] is True
    assert result["error_code"] == "integrity_consensus_mismatch"
    assert "visible_text_hash_mismatch" in result["final_visible_integrity"]["errors"]
    assert result["runtime_truth_gate"]["normal_response_allowed"] is False


def test_process_user_text_rejects_body_change_disguised_as_timestamp_repair() -> None:
    result = _session(_envelope(final_text="Niedozwolona zmiana body.")).process_user_text("test")
    audit = result["final_visible_integrity_repair_audit"][0]
    assert audit["applied"] is False
    assert audit["body_unchanged"] is False
    assert audit["provenance_hash_preserved"] is True
    assert result["final_visible_integrity"]["valid"] is False


def test_process_user_text_does_not_ignore_changed_first_body_line() -> None:
    changed = f"Niedozwolona pierwsza linia body.\n{BODY}"
    result = _session(_envelope(final_text=changed)).process_user_text("test")
    audit = result["final_visible_integrity_repair_audit"][0]
    assert audit["applied"] is False
    assert audit["body_unchanged"] is False
    assert result["runtime_provenance"]["visible_answer_hash"] == _sha(VISIBLE)
    assert result["final_visible_integrity"]["valid"] is False


def test_process_user_text_rejects_changed_contract_after_provenance_hash() -> None:
    changed = f"{HEADER} 🌿\nZmieniony kontrakt."
    result = _session(_envelope(final_text=changed, mutate_contract=True)).process_user_text("test")
    audit = result["final_visible_integrity_repair_audit"][0] if result.get("final_visible_integrity_repair_audit") else None
    assert audit is None or audit["applied"] is False
    assert result["runtime_provenance"]["visible_answer_hash"] == _sha(VISIBLE)
    assert result["final_visible_integrity"]["valid"] is False


def test_valid_process_user_text_has_consensus_across_public_layers() -> None:
    result = _session(_envelope()).process_user_text("test")
    assert result["final_visible_integrity_consensus"]["valid"] is True
    assert result["final_visible_integrity_consensus"]["mismatch"] is False
    assert result["final_visible_integrity"]["valid"] is True
    assert result["final_response_contract"]["final_visible_integrity"]["valid"] is True
    assert result["runtime_truth_gate"]["final_visible_integrity_valid"] is True
    assert result["session_provenance"]["final_visible_integrity_valid"] is True


def test_host_finalize_has_separate_hash_approval_stage() -> None:
    accepted = finalize_host_visible_text(
        required_timestamp_header=HEADER,
        turn_id="turn-1",
        trace_id="trace-1",
        text=BODY,
        supplied_turn_id="turn-1",
        supplied_trace_id="trace-1",
        supplied_text_sha256=_sha(BODY),
    )
    assert accepted.accepted is True
    assert accepted.approval_stage == "host_finalize_hash_approval"
    assert accepted.state == "approved_envelope_completion"
    assert accepted.hash_valid is True
    assert accepted.repaired is False

    rejected = finalize_host_visible_text(
        required_timestamp_header=HEADER,
        turn_id="turn-1",
        trace_id="trace-1",
        text=BODY,
        supplied_text_sha256="0" * 64,
    )
    assert rejected.accepted is False
    assert rejected.hash_valid is False
    assert any(item.code == "text_hash_mismatch" for item in rejected.violations)
