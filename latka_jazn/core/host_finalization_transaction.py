from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from latka_jazn.core.json_types import json_object
from latka_jazn.core.host_visible_finalization import finalize_host_visible_text
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError, claim_pending_host_request, consume_claimed_host_request,
    release_claimed_host_request, request_host_regeneration,
    mark_claimed_host_request_indeterminate,
)
from latka_jazn.core.host_regeneration_policy import decide_host_regeneration
from latka_jazn.core.epistemic_evidence import host_tool_attestations_to_external_evidence
from latka_jazn.core.host_response_candidate_guard import evaluate_host_response_candidate
from latka_jazn.core.finalization_service import FinalizationState
from latka_jazn.version import schema_version

if TYPE_CHECKING:
    from latka_jazn.core.finalization_service import FinalizationService


@dataclass(frozen=True)
class HostFinalizationPorts:
    extract_payload: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str]]]
    presentation: Callable[[dict[str, Any]], dict[str, Any]]
    commit_conversation: Callable[..., dict[str, Any]]
    commit_session: Callable[..., dict[str, Any]]



# Fixed repair hints are derived exclusively from codes; no private text or
# untrusted candidate excerpt leaves the finalization layer.
_REPAIR_GUIDANCE: dict[str, str] = {
    "memory_claim_without_allowed_memory_payload":
        "Avoid positive recollection without allowed source items; state uncertainty.",
    "memory_claim_without_grounded_items":
        "Replace ungrounded positive memory with an explicit evidence gap.",
    "self_state_question_missing_operational_state":
        "Describe current conversational state, without biological claims.",
    "missing_required_components_for_intent":
        "Cover each required component naturally and make the truth boundary explicit.",
    "compound_component_coverage_incomplete":
        "Cover each independent user-question component or declare its evidence gap.",
    "forbidden_host_voice_prefix":
        "Return only the body; runtime supplies the MessageEnvelope.",
    "malformed_message_envelope":
        "Return only the body, without host-generated timestamp or author headers.",
}


def _repair_guidance_for_codes(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(
        _REPAIR_GUIDANCE[code] for code in codes if code in _REPAIR_GUIDANCE
    ))

def _request_repair_or_reject(
    *,
    config: Any,
    ports: HostFinalizationPorts,
    pending: dict[str, Any],
    reply: dict[str, Any],
    binding: dict[str, Any],
    chat_bridge_meta: dict[str, Any],
    contract: dict[str, Any],
    violation_codes: list[str],
    error_prefix: str,
    finalization_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """One fail-closed regeneration owner for semantic and envelope rejection.

    A retry consumes the existing request budget and keeps the same turn/binding.
    It does not accept or persist a rejected candidate.
    """
    attempts_used = int(pending.get('regeneration_attempts') or 0)
    maximum = int(pending.get('max_regeneration_attempts') or 1)
    regeneration = decide_host_regeneration(
        violation_codes, attempts_used=attempts_used, max_attempts=maximum
    )
    if regeneration.regenerate:
        try:
            retry_record = request_host_regeneration(
                config.root, turn_id=reply['turn_id'], reason=regeneration.reason
            )
        except HostRequestStoreError as exc:
            return None, [f'host_regeneration:{exc}', *[f'{error_prefix}:{code}' for code in violation_codes]]
        binding_retry = json_object(retry_record.get('binding'))
        generation_context = json_object(retry_record.get('generation_context'))
        retry_host_generation_context = json_object(
            generation_context.get('host_generation_context')
        )
        retry_bridge = {
            'schema_version': schema_version('chatgpt_host_bridge_turn'),
            'phase': 'host_visible_generation_requested',
            'status': 'host_regeneration_requested',
            'host_must_generate_visible_reply': True,
            'host_reply_finalization_required': True,
            'pending_request_persisted': True,
            'turn_id': binding_retry.get('turn_id'),
            'trace_id': binding_retry.get('trace_id'),
            'runtime_version': binding_retry.get('runtime_version'),
            'timestamp_header': binding_retry.get('timestamp_header'),
            'timezone': binding_retry.get('timezone'),
            'timestamp_sample_iso': binding_retry.get('timestamp_sample_iso'),
            'timestamp_source': binding_retry.get('timestamp_source'),
            'timestamp_trusted': binding_retry.get('timestamp_trusted'),
            'author_id': binding_retry.get('author_id'),
            'author_label': binding_retry.get('author_label'),
            'author_source': binding_retry.get('author_source'),
            'state_emoticon': binding_retry.get('state_emoticon'),
            'host_request_contract_hash': retry_record.get('request_contract_hash'),
            'user_text_sha256': binding_retry.get('user_text_sha256'),
            'finalization_contract_hash': binding_retry.get('finalization_contract_hash'),
            'runtime_context_sha256': binding_retry.get('runtime_context_sha256'),
            'session_continuity_commit_sha256': binding_retry.get(
                'session_continuity_commit_sha256'
            ),
            'host_generation_context_sha256': binding_retry.get(
                'host_generation_context_sha256'
            ),
            'daemon_request_id': binding_retry.get('daemon_request_id')
            or generation_context.get('daemon_request_id'),
            'required_visible_prefix': generation_context.get('required_visible_prefix'),
            'host_generation_policy': generation_context.get('host_generation_policy') or {},
            'host_generation_rules': generation_context.get('host_generation_rules') or [],
            'host_generation_context': retry_host_generation_context,
            'runtime_summary': generation_context.get('runtime_summary') or {},
            'session_continuity_commit': generation_context.get(
                'session_continuity_commit'
            ) or {},
            'regeneration_attempt': retry_record.get('regeneration_attempts'),
            'max_regeneration_attempts': retry_record.get('max_regeneration_attempts'),
            'regeneration_reason': regeneration.reason,
            'regeneration_violations': list(violation_codes),
            'repair_guidance': _repair_guidance_for_codes(violation_codes),
        }
        retry_result = {
            'schema_version': schema_version('chatgpt_host_regeneration_requested'),
            'ok': True,
            'runtime_version': binding_retry.get('runtime_version'),
            'chat_bridge': chat_bridge_meta,
            'chatgpt_bridge': chat_bridge_meta,
            'chat_command_contract': contract,
            'chatgpt_host_bridge': retry_bridge,
            'host_must_generate_visible_reply': True,
            'runtime_truth_gate': {
                'ok': True, 'normal_response_allowed': False,
                'errors': ['model_guided_speech_required'], 'degradations': [],
            },
            'host_visible_finalization': finalization_payload or {'accepted': False, 'violations': list(violation_codes)},
            'host_regeneration': regeneration.to_dict(),
        }
        retry_result['chatgpt_host_presentation'] = ports.presentation(retry_result)
        return retry_result, []
    release_claimed_host_request(config.root, turn_id=reply['turn_id'])
    terminal_errors = [f'{error_prefix}:{code}' for code in violation_codes]
    if regeneration.reason == 'regeneration_budget_exhausted':
        terminal_errors.insert(0, 'host_regeneration:host_regeneration_budget_exhausted')
    return None, terminal_errors


def finalize_host_candidate(
    *,
    service: FinalizationService,
    ports: HostFinalizationPorts,
    payload: dict[str, Any],
    chat_bridge_meta: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Persist phase-2 text only when it matches one unconsumed phase-1 request."""
    config = service.config
    service.transition(FinalizationState.CANDIDATE_RECEIVED)
    reply, missing = ports.extract_payload(payload)
    if missing:
        return None, missing
    try:
        pending = claim_pending_host_request(
            config.root,
            turn_id=reply["turn_id"],
            request_contract_hash=reply["host_request_contract_hash"],
        )
    except HostRequestStoreError as exc:
        return None, [f"host_request:{exc}"]
    binding = json_object(pending.get("binding"))
    immutable_fields = (
        "turn_id", "trace_id", "timestamp_header", "timezone", "timestamp_sample_iso",
        "timestamp_source", "timestamp_trusted", "author_id", "author_label",
        "author_source", "state_emoticon",
    )
    mismatches = [
        field for field in immutable_fields
        if reply.get(field) != binding.get(field)
    ]
    if mismatches:
        release_claimed_host_request(config.root, turn_id=reply["turn_id"])
        return None, [f"host_request_binding_mismatch:{field}" for field in mismatches]
    generation_context = json_object(pending.get("generation_context"))
    host_generation_context = json_object(generation_context.get("host_generation_context"))
    bound_host_generation_context_sha256 = str(
        binding.get("host_generation_context_sha256") or ""
    ).strip()
    actual_host_generation_context_sha256 = str(
        host_generation_context.get("context_sha256") or ""
    ).strip()
    if (
        bound_host_generation_context_sha256
        and actual_host_generation_context_sha256
        != bound_host_generation_context_sha256
    ):
        release_claimed_host_request(config.root, turn_id=reply["turn_id"])
        return None, ["host_candidate:host_generation_context_binding_mismatch"]
    service.transition(FinalizationState.BINDING_VERIFIED)
    semantic_validation = evaluate_host_response_candidate(
        final_text=reply["final_text"],
        host_generation_context=host_generation_context,
        used_memory_item_ids=list(reply.get("used_memory_item_ids") or []),
        external_tool_evidence=list(reply.get("external_tool_evidence") or []),
    )
    if semantic_validation.get("accepted") is not True:
        violations = [str(item) for item in semantic_validation.get("violations") or []]
        return _request_repair_or_reject(
            config=config, ports=ports, pending=pending, reply=reply,
            binding=binding, chat_bridge_meta=chat_bridge_meta, contract=contract,
            violation_codes=violations or ["rejected"], error_prefix="host_candidate",
            finalization_payload=None,
        )
    service.transition(FinalizationState.CANDIDATE_VALIDATED)
    finalization = finalize_host_visible_text(
        required_timestamp_header=str(binding["timestamp_header"]),
        timezone=str(binding["timezone"]),
        timestamp_sample_iso=str(binding["timestamp_sample_iso"]),
        timestamp_source=str(binding["timestamp_source"]),
        timestamp_trusted=bool(binding["timestamp_trusted"]),
        author_id=str(binding["author_id"]),
        author_label=str(binding["author_label"]),
        author_source=str(binding["author_source"]),
        state_emoticon=str(binding["state_emoticon"]),
        turn_id=str(binding["turn_id"]),
        trace_id=str(binding["trace_id"]),
        text=reply["final_text"],
        supplied_turn_id=reply["turn_id"],
        supplied_trace_id=reply["trace_id"],
        supplied_text_sha256=reply["final_text_sha256"],
    )
    if not finalization.accepted:
        return _request_repair_or_reject(
            config=config, ports=ports, pending=pending, reply=reply,
            binding=binding, chat_bridge_meta=chat_bridge_meta, contract=contract,
            violation_codes=[item.code for item in finalization.violations],
            error_prefix="finalization", finalization_payload=finalization.to_dict(),
        )
    reply["final_text"] = finalization.final_visible_text

    service.transition(FinalizationState.FINAL_CONTRACT_BUILT)

    try:
        finalizer = service
        try:
            capture = finalizer.persist_final_visible_reply(
                prepared_only=True,
                turn_id=str(binding["turn_id"]),
                trace_id=str(binding["trace_id"]),
                timestamp_header=str(binding["timestamp_header"]),
                timezone=str(binding["timezone"]),
                timestamp_sample_iso=str(binding["timestamp_sample_iso"]),
                timestamp_source=str(binding["timestamp_source"]),
                timestamp_trusted=bool(binding["timestamp_trusted"]),
                author_id=str(binding["author_id"]),
                author_label=str(binding["author_label"]),
                author_source=str(binding["author_source"]),
                final_text=reply["final_text"],
                state_emoticon=str(binding["state_emoticon"]),
                source="chatgpt_visible_layer_jsonl",
                client_context={
                    "client": "chatgpt_visible_layer_jsonl",
                    "lifecycle": "chatgpt_host_visible_reply_record",
                    "chat_bridge": chat_bridge_meta,
                    "final_text_field": reply["final_text_field"],
                    "host_request_contract_hash": reply["host_request_contract_hash"],
                    "generation_executor": "chatgpt_host",
                    "used_memory_item_ids": list(reply.get("used_memory_item_ids") or []),
                    "external_tool_evidence": list(semantic_validation.get("external_tool_evidence") or []),
                    "host_candidate_validation": semantic_validation,
                },
                memory_evidence={
                    "memory_source_ids": list(reply.get("used_memory_item_ids") or []),
                },
                external_evidence=host_tool_attestations_to_external_evidence(
                    semantic_validation.get("external_tool_evidence") or []
                ),
            )
        finally:
            finalizer.shutdown()
        service.transition(FinalizationState.PERSISTENCE_PREPARED)
        consumed = consume_claimed_host_request(
            config.root, turn_id=reply["turn_id"],
            request_contract_hash=reply["host_request_contract_hash"],
            final_visible_capture=capture,
        )
        service.transition(FinalizationState.COMMIT_ACCEPTED)
    except Exception as exc:
        try:
            mark_claimed_host_request_indeterminate(config.root, turn_id=reply["turn_id"], error=str(exc))
        except HostRequestStoreError:
            pass
        return None, [f"host_persistence_indeterminate:{type(exc).__name__}"]
    # Durable consumed record is the sole acceptance authority. All following
    # writes are projections and cannot turn a committed candidate into a replay.
    capture = service.publish_committed_capture(capture)
    try:
        try:
            conversation_state = ports.commit_conversation(
                config=config,
                pending=pending,
                binding=binding,
                final_visible_text=reply["final_text"],
            )
        except Exception as conversation_exc:
            conversation_state = {
                "ok": False,
                "status": "conversation_commit_exception",
                "error_type": type(conversation_exc).__name__,
                "error": str(conversation_exc),
            }
        try:
            session_continuity = ports.commit_session(
                config=config,
                pending=pending,
                binding=binding,
                final_visible_text=reply["final_text"],
            )
        except Exception as continuity_exc:
            # Final visible persistence is already authoritative.  Conversation
            # continuity is reported as degraded instead of pretending that the
            # final reply itself failed or replaying the append-only write.
            session_continuity = {
                "saved": False,
                "status": "continuity_commit_exception",
                "error_type": type(continuity_exc).__name__,
                "error": str(continuity_exc),
            }
    finally:
        service.transition(FinalizationState.VISIBLE_ACCEPTED)
    result = {
        "schema_version": schema_version("chatgpt_host_visible_reply_recorded"),
        "ok": True,
        "chat_bridge": chat_bridge_meta,
        "chatgpt_bridge": chat_bridge_meta,
        "chat_command_contract": contract,
        "chatgpt_host_bridge": {
            "schema_version": schema_version("chatgpt_host_visible_reply_recorded"),
            "phase": "host_visible_reply_recorded",
            "status": "host_visible_reply_finalized",
            "host_must_generate_visible_reply": False,
            "turn_id": binding["turn_id"],
            "trace_id": binding["trace_id"],
            "host_request_contract_hash": reply["host_request_contract_hash"],
            "user_text_sha256": binding.get("user_text_sha256"),
            "timestamp_header": binding["timestamp_header"],
            "timezone": binding["timezone"],
            "timestamp_sample_iso": binding["timestamp_sample_iso"],
            "timestamp_source": binding["timestamp_source"],
            "timestamp_trusted": binding["timestamp_trusted"],
            "author_id": binding["author_id"],
            "author_label": binding["author_label"],
            "author_source": binding["author_source"],
            "state_emoticon": binding["state_emoticon"],
            "timestamp_required": True,
            "timestamp_enforced": True,
            "final_text_field": reply["final_text_field"],
            "can_generate_model_guided_speech": True,
            "can_generate_model_guided_speech_locally": False,
            "can_complete_model_guided_speech_via_host": True,
            "generation_executor": "chatgpt_host",
            "replay_protected": True,
            "daemon_request_id": binding.get("daemon_request_id") or None,
            "semantic_validation_accepted": True,
            "truth_boundary": "Odpowiedź hosta została związana z jednym niezużytym kontraktem phase-1, sfinalizowana i dopiero wtedy zapisana.",
        },
        "host_must_generate_visible_reply": False,
        "can_generate_model_guided_speech": True,
        "final_visible_text": capture.get("final_visible_text"),
        "host_visible_finalization": finalization.to_dict(),
        "host_visible_reply_capture": capture,
        "host_response_candidate_validation": semantic_validation,
        "host_request_consumption": consumed,
        "finalization_state": service.state.value,
        "finalization_history": [stage.value for stage in service.history],
        "conversation_state_persistence": conversation_state,
        "session_continuity_persistence": session_continuity,
    }
    return result, []
