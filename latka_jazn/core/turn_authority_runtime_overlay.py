from __future__ import annotations

"""Install turn-authority and canonical conversation-runtime invariants.

The overlay wraps stable public contracts instead of forking the large
bridge/engine/control-plane modules.  Besides authority, identity and
host-tool-evidence gates it installs the single ConversationRunner and preserves
one transport invariant: after a daemon submit may have crossed the process
boundary, the host must poll the preallocated request id instead of replaying the
user message.
"""

from typing import Any, Mapping

from latka_jazn.core.full_canon_model_context import build_full_canon_model_context
from latka_jazn.core.host_tool_turn_policy import (
    build_host_tool_turn_policy,
    validate_tool_evidence_against_policy,
)
from latka_jazn.core.identity_response_evaluator import evaluate_identity_response
from latka_jazn.core.turn_authority import (
    build_turn_authority_receipt,
    validate_turn_authority_receipt,
)
from latka_jazn.core.turn_pipeline_contract import (
    build_turn_pipeline_contract,
    finalize_turn_pipeline_contract,
    validate_turn_pipeline_contract,
)
from latka_jazn.version import schema_version

_OVERLAY_VERSION = schema_version("turn_authority_runtime_overlay")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _identity_hash_from_context(value: Any) -> str:
    contract = _mapping(value)
    model_context = _mapping(contract.get("model_context"))
    full_canon = _mapping(model_context.get("full_canon_model_context"))
    digest = str(full_canon.get("immutable_canon_sha256") or "").lower()
    if len(digest) == 64:
        return digest
    return str(build_full_canon_model_context({}).get("immutable_canon_sha256") or "").lower()


def install_turn_authority_runtime_overlay() -> dict[str, Any]:
    # runtime_daemon is already imported by the lifecycle hotfix in main.py.
    # Install the canonical runner before chat_command_contract is imported so
    # every worker/finalization path observes the same session class.
    from latka_jazn.core import runtime_daemon
    from latka_jazn.core.conversation_runtime_convergence import (
        ConversationTurnLedger,
        build_host_finalized_turn_state,
        build_linguistic_turn_frame,
        build_runtime_result_turn_state,
        install_conversation_runner_class,
        validate_linguistic_turn_frame,
        validate_turn_state_contract,
    )

    runner_install = install_conversation_runner_class(runtime_daemon_module=runtime_daemon)

    from latka_jazn.core import chat_command_contract as bridge
    from latka_jazn.core import chatgpt_host_pending_store as pending_store
    from latka_jazn.core import host_response_candidate_guard as candidate_guard

    if getattr(bridge, "_turn_authority_runtime_overlay_installed", False):
        return {
            "installed": True,
            "already_installed": True,
            "schema_version": _OVERLAY_VERSION,
            "conversation_runner": runner_install,
        }

    original_daemon_submit = runtime_daemon.chat_daemon_submit
    original_chat_daemon = runtime_daemon.chat_daemon

    def daemon_submit_with_authority(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            request_id = runtime_daemon.normalize_daemon_request_id(kwargs.get("request_id"))
        except ValueError:
            raise
        kwargs["request_id"] = request_id
        try:
            payload = original_daemon_submit(*args, **kwargs)
        except Exception as exc:
            payload = {
                "ok": False,
                "accepted": False,
                "done": False,
                "error_code": "daemon_chat_submit_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "request_id": request_id,
            }
        if isinstance(payload, dict) and payload.get("error_code") == "daemon_chat_submit_failed":
            payload = dict(payload)
            payload["request_id"] = str(payload.get("request_id") or request_id)
            payload["submit_outcome_authoritative"] = False
            payload["safe_recovery"] = "poll_same_request_id_before_any_retry"
        return payload

    def chat_daemon_with_authority(*args: Any, **kwargs: Any) -> dict[str, Any]:
        request_id = runtime_daemon.normalize_daemon_request_id(kwargs.get("request_id"))
        kwargs["request_id"] = request_id
        try:
            payload = original_chat_daemon(*args, **kwargs)
        except Exception as exc:
            payload = {
                "ok": False,
                "accepted": None,
                "done": False,
                "error_code": "daemon_chat_pending",
                "error": f"{type(exc).__name__}: {exc}",
                "request_id": request_id,
                "client_wait_status": "submit_outcome_unknown",
            }
        if isinstance(payload, dict) and payload.get("error_code") == "daemon_chat_submit_failed":
            payload = dict(payload)
            payload.update({
                "accepted": None,
                "done": False,
                "error_code": "daemon_chat_pending",
                "request_id": str(payload.get("request_id") or request_id),
                "client_wait_status": "submit_outcome_unknown",
                "submit_outcome_authoritative": False,
                "safe_recovery": "poll_same_request_id_before_any_retry",
            })
        return payload

    runtime_daemon.chat_daemon_submit = daemon_submit_with_authority
    runtime_daemon.chat_daemon = chat_daemon_with_authority

    original_binding = pending_store.canonical_host_request_binding
    original_build_context = candidate_guard.build_host_generation_context
    original_evaluate_host_candidate = candidate_guard.evaluate_host_response_candidate
    original_build_bridge = bridge.build_chatgpt_host_bridge_turn_contract
    original_presentation = bridge.build_chatgpt_host_presentation_packet
    original_persist = bridge.persist_chatgpt_host_visible_reply
    original_gate = bridge.build_host_pre_response_gate_telemetry

    def canonical_binding_with_identity(value: Mapping[str, Any]) -> dict[str, Any]:
        result = original_binding(value)
        digest = str(value.get("identity_canon_sha256") or "").strip().lower()
        if len(digest) == 64:
            result["identity_canon_sha256"] = digest
        state = _mapping(value.get("conversation_turn_state"))
        state_digest = str(state.get("contract_sha256") or "").strip().lower()
        if len(state_digest) == 64:
            result["conversation_turn_state_sha256"] = state_digest
        return result

    pending_store.canonical_host_request_binding = canonical_binding_with_identity

    def build_context_with_tool_policy(
        model_context: dict[str, Any],
        *,
        detected_intent: str,
        route: str,
        context_origin: str = "runtime_model_synthesis",
    ) -> dict[str, Any]:
        payload = original_build_context(
            model_context,
            detected_intent=detected_intent,
            route=route,
            context_origin=context_origin,
        )
        plan = _mapping(_mapping(payload.get("model_context")).get("nlg_plan"))
        policy = build_host_tool_turn_policy(
            user_text=str(_mapping(payload.get("model_context")).get("user_text") or ""),
            detected_intent=detected_intent,
            route=route,
            nlg_plan=plan,
        )
        linguistic_frame = build_linguistic_turn_frame(
            _mapping(payload.get("model_context")),
            detected_intent=detected_intent,
            route=route,
        )
        linguistic_validation = validate_linguistic_turn_frame(linguistic_frame)
        payload["host_tool_turn_policy"] = policy
        payload["linguistic_turn_frame"] = linguistic_frame
        payload["linguistic_turn_frame_validation"] = linguistic_validation
        generation = _mapping(payload.get("generation_contract"))
        generation.update({
            "all_host_tools_are_subordinate_to_runtime_turn": True,
            "tool_results_cannot_become_identity_or_voice_source": True,
            "runtime_finalization_required_after_host_tool_use": True,
            "host_tool_turn_policy_path": "host_tool_turn_policy",
            "conversation_runner_required": True,
            "runtime_turn_state_machine_required": True,
            "linguistic_turn_frame_path": "linguistic_turn_frame",
        })
        payload["generation_contract"] = generation
        unsigned = dict(payload)
        unsigned.pop("context_sha256", None)
        payload["context_sha256"] = candidate_guard._sha256(unsigned)
        return payload

    candidate_guard.build_host_generation_context = build_context_with_tool_policy

    def evaluate_host_candidate_with_authority(**kwargs: Any) -> dict[str, Any]:
        result = original_evaluate_host_candidate(**kwargs)
        context = _mapping(kwargs.get("host_generation_context"))
        tool_policy = _mapping(context.get("host_tool_turn_policy"))
        linguistic_validation = _mapping(context.get("linguistic_turn_frame_validation"))
        evidence = kwargs.get("external_tool_evidence")
        evidence_list = list(evidence) if isinstance(evidence, list) else []
        violations = [str(item) for item in result.get("violations") or []]
        violations.extend(
            item for item in validate_tool_evidence_against_policy(evidence_list, tool_policy)
            if item not in violations
        )
        if linguistic_validation.get("ok") is not True:
            violations.append("linguistic_turn_frame_invalid")
        model_context = _mapping(context.get("model_context"))
        full_canon = _mapping(model_context.get("full_canon_model_context"))
        identity = evaluate_identity_response(
            text=str(kwargs.get("final_text") or ""),
            full_canon_model_context=full_canon,
            answer_kind=str(_mapping(model_context.get("nlg_plan")).get("answer_kind") or "natural_dialogue"),
            user_text=str(model_context.get("user_text") or ""),
        )
        for item in identity.violations:
            if item not in violations:
                violations.append(item)
        result["identity_response_evaluation"] = identity.to_dict()
        result["host_tool_turn_policy"] = tool_policy
        result["linguistic_turn_frame_validation"] = linguistic_validation
        result["violations"] = violations
        result["accepted"] = bool(result.get("accepted") is True and identity.accepted and not violations)
        return result

    candidate_guard.evaluate_host_response_candidate = evaluate_host_candidate_with_authority
    bridge.evaluate_host_response_candidate = evaluate_host_candidate_with_authority

    def build_bridge_with_authority(
        result: dict[str, Any],
        *,
        user_text: str,
        chat_bridge_meta: dict[str, Any],
    ) -> dict[str, Any]:
        value = original_build_bridge(result, user_text=user_text, chat_bridge_meta=chat_bridge_meta)
        host_context = _mapping(value.get("host_generation_context"))
        identity_hash = _identity_hash_from_context(host_context)
        value["identity_canon_sha256"] = identity_hash
        value["turn_authority_required"] = True
        requires_host = value.get("phase") == "host_visible_generation_requested"
        runtime_final = value.get("phase") == "runtime_final_available"

        state = _mapping(result.get("conversation_turn_state"))
        if not state:
            session = _mapping(result.get("session"))
            state = build_runtime_result_turn_state(
                result,
                user_text=user_text,
                session_id=str(
                    session.get("session_id")
                    or chat_bridge_meta.get("session_id")
                    or value.get("session_id")
                    or "compat-session"
                ),
                request_id=str(
                    chat_bridge_meta.get("daemon_request_id")
                    or chat_bridge_meta.get("request_id")
                    or value.get("daemon_request_id")
                    or value.get("turn_id")
                    or ""
                ) or None,
            )
        state_validation = validate_turn_state_contract(state)
        value["conversation_turn_state"] = state
        value["conversation_turn_state_validation"] = state_validation
        expected_state = "host_generation_pending" if requires_host else "visible_committed" if runtime_final else None
        if (
            state_validation.get("ok") is not True
            or (expected_state is not None and str(state.get("state") or "") != expected_state)
        ):
            value.update({
                "phase": "host_diagnostic_required",
                "status": "conversation_turn_state_invalid",
                "host_must_generate_visible_reply": False,
                "host_reply_finalization_required": False,
                "diagnostic_reason": "conversation_turn_state_invalid",
            })
            return value

        value["turn_pipeline_contract"] = build_turn_pipeline_contract(
            turn_id=str(value.get("turn_id") or ""),
            trace_id=str(value.get("trace_id") or ""),
            user_text_sha256=str(value.get("user_text_sha256") or ""),
            identity_canon_sha256=identity_hash,
            host_generation_context=host_context,
            requires_host_generation=requires_host,
            runtime_final_available=runtime_final,
        )
        value["turn_pipeline_validation"] = validate_turn_pipeline_contract(value["turn_pipeline_contract"])
        if value["turn_pipeline_validation"].get("ok") is not True:
            value.update({
                "phase": "host_diagnostic_required",
                "status": "turn_pipeline_contract_invalid",
                "host_must_generate_visible_reply": False,
                "host_reply_finalization_required": False,
                "diagnostic_reason": "turn_pipeline_contract_invalid",
            })
            return value
        if requires_host:
            value["host_request_contract_hash"] = bridge.calculate_host_request_contract_hash(value)
            shape = _mapping(value.get("host_reply_jsonl_shape"))
            if shape:
                shape["host_request_contract_hash"] = value["host_request_contract_hash"]
                value["host_reply_jsonl_shape"] = shape
        elif runtime_final:
            final_text = bridge.extract_final_visible_text_from_result(result)
            receipt = build_turn_authority_receipt(
                turn_id=str(value.get("turn_id") or ""),
                trace_id=str(value.get("trace_id") or ""),
                user_text_sha256=str(value.get("user_text_sha256") or ""),
                final_visible_text=final_text,
                identity_canon_sha256=identity_hash,
                visible_output_source="runtime_exact",
                author_id=str(value.get("author_id") or ""),
                author_label=str(value.get("author_label") or ""),
                author_source=str(value.get("author_source") or ""),
            )
            validation = validate_turn_authority_receipt(
                receipt,
                expected_user_text_sha256=str(value.get("user_text_sha256") or ""),
                expected_final_visible_text=final_text,
                expected_identity_canon_sha256=identity_hash,
                expected_visible_output_source="runtime_exact",
            )
            value["turn_authority_receipt"] = receipt
            value["turn_authority_validation"] = validation
            if validation.get("ok") is not True:
                value.update({
                    "phase": "host_diagnostic_required",
                    "status": "turn_authority_receipt_invalid",
                    "diagnostic_reason": "turn_authority_receipt_invalid",
                })
        return value

    bridge.build_chatgpt_host_bridge_turn_contract = build_bridge_with_authority

    def gate_with_authority(**kwargs: Any) -> dict[str, Any]:
        telemetry = original_gate(**kwargs)
        response = _mapping(kwargs.get("response"))
        presentation = _mapping(kwargs.get("presentation"))
        host_bridge = _mapping(response.get("chatgpt_host_bridge"))
        validation = _mapping(presentation.get("turn_authority_validation")) or _mapping(host_bridge.get("turn_authority_validation"))
        receipt = _mapping(presentation.get("turn_authority_receipt")) or _mapping(host_bridge.get("turn_authority_receipt"))
        state_validation = _mapping(presentation.get("conversation_turn_state_validation")) or _mapping(host_bridge.get("conversation_turn_state_validation"))
        telemetry["authorship_verified"] = bool(
            presentation.get("action") == "display_exact"
            and validation.get("ok") is True
            and state_validation.get("visible_commit_ready") is True
            and str(telemetry.get("visible_output_source") or "") in {"runtime_exact", "runtime_finalized"}
        )
        telemetry["turn_authority_receipt_sha256"] = receipt.get("receipt_sha256")
        telemetry["turn_authority_validation"] = validation or None
        telemetry["conversation_turn_state_validation"] = state_validation or None
        return telemetry

    bridge.build_host_pre_response_gate_telemetry = gate_with_authority

    def presentation_with_authority(payload: dict[str, Any]) -> dict[str, Any]:
        packet = original_presentation(payload)
        host_bridge = _mapping(payload.get("chatgpt_host_bridge"))
        receipt = _mapping(host_bridge.get("turn_authority_receipt")) or _mapping(payload.get("turn_authority_receipt"))
        cached_validation = _mapping(host_bridge.get("turn_authority_validation")) or _mapping(payload.get("turn_authority_validation"))
        validation = cached_validation
        if receipt:
            source = str(receipt.get("visible_output_source") or "")
            validation = validate_turn_authority_receipt(
                receipt,
                expected_user_text_sha256=str(host_bridge.get("user_text_sha256") or receipt.get("user_text_sha256") or ""),
                expected_final_visible_text=str(packet.get("final_visible_text") or ""),
                expected_identity_canon_sha256=str(host_bridge.get("identity_canon_sha256") or receipt.get("identity_canon_sha256") or ""),
                expected_visible_output_source=source or None,
            )
        state = _mapping(host_bridge.get("conversation_turn_state")) or _mapping(payload.get("conversation_turn_state"))
        state_validation = validate_turn_state_contract(state) if state else {}
        required = bool(host_bridge.get("turn_authority_required"))
        if packet.get("action") == "display_exact" and required and (
            validation.get("ok") is not True
            or state_validation.get("visible_commit_ready") is not True
        ):
            packet.update({
                "action": "host_diagnostic",
                "final_visible_text": None,
                "diagnostic_reason": "accepted_visible_turn_lineage_invalid_or_missing",
                "must_not_claim_runtime_voice": True,
            })
        packet["turn_authority_receipt"] = receipt or None
        packet["turn_authority_validation"] = validation or None
        packet["conversation_turn_state"] = state or None
        packet["conversation_turn_state_validation"] = state_validation or None
        packet["authorship_verified"] = bool(
            packet.get("action") == "display_exact"
            and validation.get("ok") is True
            and state_validation.get("visible_commit_ready") is True
        )
        return packet

    bridge.build_chatgpt_host_presentation_packet = presentation_with_authority

    def persist_with_authority(**kwargs: Any) -> tuple[dict[str, Any] | None, list[str]]:
        result, errors = original_persist(**kwargs)
        if result is None or errors:
            return result, errors
        payload = _mapping(kwargs.get("payload"))
        config = kwargs.get("config")
        turn_id = str(payload.get("turn_id") or "")
        lifecycle = pending_store.host_request_lifecycle_state(config.root, turn_id=turn_id) if config is not None else {}
        binding = _mapping(lifecycle.get("binding"))
        host_bridge = _mapping(result.get("chatgpt_host_bridge"))
        identity_hash = str(binding.get("identity_canon_sha256") or "").lower()
        if len(identity_hash) != 64:
            identity_hash = str(build_full_canon_model_context({}).get("immutable_canon_sha256") or "").lower()
        final_text = str(result.get("final_visible_text") or "")
        tool_policy = _mapping(_mapping(result.get("host_response_candidate_validation")).get("host_tool_turn_policy"))
        pipeline = build_turn_pipeline_contract(
            turn_id=str(binding.get("turn_id") or turn_id),
            trace_id=str(binding.get("trace_id") or host_bridge.get("trace_id") or ""),
            user_text_sha256=str(binding.get("user_text_sha256") or ""),
            identity_canon_sha256=identity_hash,
            host_generation_context={"host_tool_turn_policy": tool_policy},
            requires_host_generation=False,
            runtime_final_available=True,
        )
        pipeline = finalize_turn_pipeline_contract(pipeline)
        pipeline_validation = validate_turn_pipeline_contract(pipeline)
        receipt = build_turn_authority_receipt(
            turn_id=str(binding.get("turn_id") or turn_id),
            trace_id=str(binding.get("trace_id") or host_bridge.get("trace_id") or ""),
            user_text_sha256=str(binding.get("user_text_sha256") or ""),
            final_visible_text=final_text,
            identity_canon_sha256=identity_hash,
            visible_output_source="runtime_finalized",
            author_id=str(binding.get("author_id") or ""),
            author_label=str(binding.get("author_label") or ""),
            author_source=str(binding.get("author_source") or ""),
            host_request_contract_hash=str(payload.get("host_request_contract_hash") or ""),
        )
        validation = validate_turn_authority_receipt(
            receipt,
            expected_user_text_sha256=str(binding.get("user_text_sha256") or ""),
            expected_final_visible_text=final_text,
            expected_identity_canon_sha256=identity_hash,
            expected_visible_output_source="runtime_finalized",
        )
        result_session = _mapping(result.get("session"))
        payload_session = _mapping(payload.get("session"))
        session_id = str(
            result_session.get("session_id")
            or payload_session.get("session_id")
            or payload.get("session_id")
            or host_bridge.get("session_id")
            or "host-finalized-session"
        )
        request_id = str(
            binding.get("daemon_request_id")
            or payload.get("daemon_request_id")
            or payload.get("request_id")
            or binding.get("turn_id")
            or turn_id
        )
        final_state = build_host_finalized_turn_state(
            session_id=session_id,
            request_id=request_id,
            turn_id=str(binding.get("turn_id") or turn_id),
            trace_id=str(binding.get("trace_id") or host_bridge.get("trace_id") or ""),
            user_text_sha256=str(binding.get("user_text_sha256") or ""),
        )
        state_validation = validate_turn_state_contract(final_state)
        if (
            validation.get("ok") is not True
            or pipeline_validation.get("ok") is not True
            or state_validation.get("visible_commit_ready") is not True
        ):
            return None, ["turn_authority:post_finalize_binding_invalid"]
        ledger = (
            ConversationTurnLedger(config.root).append(final_state)
            if config is not None
            else {"ok": False, "written": False, "error_code": "runtime_root_unavailable"}
        )
        host_bridge.update({
            "identity_canon_sha256": identity_hash,
            "turn_authority_required": True,
            "turn_authority_receipt": receipt,
            "turn_authority_validation": validation,
            "turn_pipeline_contract": pipeline,
            "turn_pipeline_validation": pipeline_validation,
            "conversation_turn_state": final_state,
            "conversation_turn_state_validation": state_validation,
        })
        result["chatgpt_host_bridge"] = host_bridge
        result["turn_authority_receipt"] = receipt
        result["turn_authority_validation"] = validation
        result["turn_pipeline_contract"] = pipeline
        result["turn_pipeline_validation"] = pipeline_validation
        result["conversation_turn_state"] = final_state
        result["conversation_turn_state_validation"] = state_validation
        result["conversation_turn_ledger"] = ledger
        return result, []

    bridge.persist_chatgpt_host_visible_reply = persist_with_authority
    setattr(bridge, "_turn_authority_runtime_overlay_installed", True)
    setattr(bridge, "_turn_authority_runtime_overlay_version", _OVERLAY_VERSION)
    return {
        "installed": True,
        "already_installed": False,
        "schema_version": _OVERLAY_VERSION,
        "conversation_runner": runner_install,
    }
