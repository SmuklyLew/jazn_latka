from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Literal, TextIO

from latka_jazn.config import JaznConfig
from latka_jazn.core.json_types import json_object
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
from latka_jazn.core.host_visible_finalization import (
    HostVisibleFinalizationContract,
    finalize_host_visible_text,
    sha256_host_visible_text,
)
from latka_jazn.core.chatgpt_host_pending_store import (
    HostRequestStoreError,
    calculate_host_request_contract_hash,
    claim_pending_host_request,
    consume_claimed_host_request,
    continuation_ttl_for_bridge,
    mark_claimed_host_request_indeterminate,
    persist_pending_host_request,
    release_claimed_host_request,
    request_host_regeneration,
)
from latka_jazn.core.runtime_ownership_contract import build_runtime_ownership_contract
from latka_jazn.core.host_regeneration_policy import decide_host_regeneration
from latka_jazn.core.epistemic_evidence import host_tool_attestations_to_external_evidence
from latka_jazn.core.host_response_candidate_guard import (
    build_host_generation_context_from_runtime,
    evaluate_host_response_candidate,
    validate_host_generation_context,
)
from latka_jazn.core.chatgpt_host_pre_response_gate import (
    build_host_pre_response_gate_telemetry,
)
from latka_jazn.core.memory_recall_observability import (
    correlate_memory_recall_transport,
    memory_recall_truth_boundary_violation,
)
from latka_jazn.core.turn_timeout import RuntimeSessionWorker, RuntimeTurnTimeoutError, runtime_turn_timeout_seconds
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

ACCEPTED_CHATGPT_INPUT_FIELDS = ("message", "text", "user_text", "content", "prompt")
CHATGPT_BRIDGE_PROTOCOL = schema_version("chatgpt_bridge_jsonl")
CHAT_OPENAI_PROTOCOL = schema_version("chat_open_ai_jsonl")
OLLAMA_PROTOCOL = schema_version("chat_ollama_jsonl")
CHAT_BRIDGE_OUTPUT_MODES = ("jsonl", "host_packet", "final_visible_text")
KNOWN_CLI_FLAG_VALUE_POLICY = {
    "--session-id": True,
    "--no-carryover": False,
    "--trusted-time-iso": True,
    "--final-only": False,
}


def guard_cli_flags_in_user_text(user_text: str) -> tuple[str, dict[str, Any] | None]:
    """Remove leaked CLI arguments only from runtime classification input.

    The original message remains available in the warning and is copied into
    the turn trace by ``attach_cli_flag_warning``.
    """
    original = str(user_text or "")
    classification_text = original
    detected: list[str] = []
    for flag, consumes_value in KNOWN_CLI_FLAG_VALUE_POLICY.items():
        pattern = rf"(?<!\S){re.escape(flag)}(?:\s+[^\s]+)?" if consumes_value else rf"(?<!\S){re.escape(flag)}(?!\S)"
        classification_text, count = re.subn(pattern, " ", classification_text, flags=re.IGNORECASE)
        if count:
            detected.append(flag)
    classification_text = re.sub(r"\s+", " ", classification_text).strip()
    if not detected:
        return original, None
    warning = {
        "schema_version": schema_version("chat_bridge_input_warning"),
        "code": "cli_flag_after_separator",
        "message": "Flagi po -- są częścią wiadomości. Przenieś je przed --.",
        "detected_flags": detected,
        "classification_text": classification_text,
        "original_user_text": original,
        "truth_boundary": "Oryginał pozostaje w trace; tylko routing i wykonanie tej tury używają tekstu bez znanych flag CLI.",
    }
    return classification_text, warning


def attach_cli_flag_warning(result: dict[str, Any], warning: dict[str, Any] | None) -> None:
    if warning is None:
        return
    result["chat_bridge_input_warning"] = warning
    trace = json_object(result.get("trace"))
    trace["chat_bridge_original_user_text"] = warning["original_user_text"]
    trace["chat_bridge_classification_text"] = warning["classification_text"]
    trace["chat_bridge_input_warning_code"] = warning["code"]
    result["trace"] = trace
BridgeOutputMode = Literal["jsonl", "host_packet", "final_visible_text"]

CHATGPT_HOST_VISIBLE_REPLY_TYPES = (
    "host_visible_reply",
    "chatgpt_host_visible_reply",
    "chatgpt_visible_layer_reply",
)
CHATGPT_HOST_VISIBLE_REPLY_TEXT_FIELDS = (
    "final_text",
    "host_visible_text",
    "visible_text",
    "assistant_text",
    "final_visible_text",
)


@dataclass(slots=True)
class ChatCommandContract:
    command: str
    mode: str
    requires_api_key: bool
    uses_openai_api: bool
    keeps_process_alive: bool
    engine_reused_between_turns: bool
    accepted_input_fields: tuple[str, ...] = ACCEPTED_CHATGPT_INPUT_FIELDS
    accepted_input_shapes: tuple[str, ...] = (
        "plain_text_line",
        "json_object.message",
        "json_object.text",
        "json_object.user_text",
        "json_object.content",
        "json_object.prompt",
        "json_object.messages[].content",
    )
    output_modes: tuple[str, ...] = CHAT_BRIDGE_OUTPUT_MODES
    truth_boundary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chat_gpt_contract(*, process_lifecycle: str = "one_shot") -> ChatCommandContract:
    process_persistent = process_lifecycle == "jsonl_bridge"
    return ChatCommandContract(
        command="--chat-gpt",
        mode="chatgpt_bridge_without_api_key",
        requires_api_key=False,
        uses_openai_api=False,
        keeps_process_alive=process_persistent,
        engine_reused_between_turns=process_persistent,
        truth_boundary=(
            "--chat-gpt jest jedyną kanoniczną flagą mostu dla aplikacji ChatGPT/copy-paste/JSONL. "
            "Nie wymaga OPENAI_API_KEY i nie wykonuje żądań do OpenAI API. "
            "Użycie z wiadomością po `--` zwraca zwarty pakiet hosta z jednoznaczną akcją: display_exact, generate_then_finalize albo host_diagnostic. "
            "Pełny stdin JSONL zachowuje audyt techniczny. Tylko jawne `--final-only` prosi o tekst, a brama nadal odmawia jego pokazania, gdy integralność nie jest potwierdzona."
        ),
    )


def chat_open_ai_contract() -> ChatCommandContract:
    return ChatCommandContract(
        command="--chat-open-ai",
        mode="openai_api_model_adapter_bridge",
        requires_api_key=True,
        uses_openai_api=True,
        keeps_process_alive=True,
        engine_reused_between_turns=True,
        truth_boundary=(
            "--chat-open-ai uruchamia ten sam runtime Jaźni, ale językową warstwę model_adapter kieruje przez OpenAI Responses API. "
            "OPENAI_API_KEY jest wymagany. Model jest kanałem języka, nie źródłem tożsamości ani pamięci Jaźni."
        ),
    )


def local_llm_contract() -> ChatCommandContract:
    return ChatCommandContract(
        command="--chat-ollama",
        mode="ollama_native_local_backend",
        requires_api_key=False,
        uses_openai_api=False,
        keeps_process_alive=True,
        engine_reused_between_turns=True,
        truth_boundary=(
            "--chat-ollama używa natywnego lokalnego API Ollamy jako generatora kandydata. "
            "Ollama nie jest tożsamością ani pamięcią; runtime zachowuje routing, walidację, provenance, ledger i final_visible_text."
        ),
    )


def command_contract(command: str, *, process_lifecycle: str | None = None) -> dict[str, Any]:
    if command == "--chat-open-ai":
        return chat_open_ai_contract().to_dict()
    if command in {"--chat-ollama", "--local-llm", "--ollama"}:
        return local_llm_contract().to_dict()
    if command == "--chat-gpt":
        return chat_gpt_contract(process_lifecycle=process_lifecycle or "one_shot").to_dict()
    raise ValueError(f"unknown chat command contract: {command}")


def extract_user_text_from_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    for candidate in ACCEPTED_CHATGPT_INPUT_FIELDS:
        value = payload.get(candidate)
        if value is not None and str(value).strip():
            return str(value).strip(), "json", candidate

    messages = payload.get("messages")
    if isinstance(messages, list):
        fallback_content = ""
        fallback_field = "messages[].content"
        for item in messages:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if content is None:
                continue
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        text_part = part.get("text")
                        if text_part is not None:
                            parts.append(str(text_part))
                    elif part is not None:
                        parts.append(str(part))
                content_text = "".join(parts).strip()
            else:
                content_text = str(content).strip()
            if not content_text:
                continue
            fallback_content = content_text
            if str(item.get("role") or "").lower() == "user":
                return content_text, "json_chat_messages", "messages[user].content"
        if fallback_content:
            return fallback_content, "json_chat_messages", fallback_field

    return "", "json", "<missing>"



def apply_chatgpt_cli_settings(config: JaznConfig) -> JaznConfig:
    """Select the truthful ChatGPT host adapter for the --chat-gpt bridge."""
    config.model_adapter = "chatgpt_runtime_adapter"
    if not os.environ.get("JAZN_MODEL_NAME"):
        config.model_name = os.environ.get("JAZN_CHATGPT_MODEL_NAME", "chatgpt_host_model").strip() or "chatgpt_host_model"
    return config


def apply_chat_cli_settings(
    config: JaznConfig,
    *,
    infer_host_environment: bool = True,
    probe_local: bool = True,
) -> JaznConfig:
    """Resolve the universal ``--chat`` language route for this environment."""
    from latka_jazn.core.llm_route_resolver import apply_llm_route_to_config, build_llm_route_status

    route_status = build_llm_route_status(
        config,
        command="--chat",
        infer_host_environment=infer_host_environment,
        probe_local=probe_local,
    )
    apply_llm_route_to_config(config, route_status)
    if not os.environ.get("JAZN_TERMINAL_MODEL_NAME"):
        config.terminal_model_name = "terminal_visible_layer"
    return config


def apply_openai_cli_settings(
    config: JaznConfig,
    *,
    model: str | None = None,
    api_base: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
) -> JaznConfig:
    config.model_adapter = "openai_responses_adapter"
    if model:
        config.model_name = model
    if api_base:
        config.model_api_base = api_base.rstrip("/")
    if timeout_seconds is not None:
        config.model_timeout_seconds = float(timeout_seconds)
    if max_output_tokens is not None:
        config.model_max_output_tokens = int(max_output_tokens)
    return config


def apply_ollama_cli_settings(
    config: JaznConfig,
    *,
    model: str | None = None,
    api_base: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    provider: str | None = None,
) -> JaznConfig:
    """Apply explicit Ollama CLI values without performing network I/O.

    Model discovery is intentionally separate in ``resolve_ollama_cli_settings``
    so status builders and unit tests do not unexpectedly contact localhost.
    """
    config.model_adapter = "ollama"
    normalized_model = str(model or "").strip()
    if normalized_model:
        config.local_model_name = normalized_model
        os.environ["JAZN_OLLAMA_MODEL"] = normalized_model
        os.environ["JAZN_LOCAL_LLM_MODEL"] = normalized_model
    if api_base:
        normalized_api_base = str(api_base).strip().rstrip("/")
        config.local_model_api_base = normalized_api_base
        os.environ["JAZN_OLLAMA_BASE_URL"] = normalized_api_base
        os.environ["JAZN_LOCAL_LLM_BASE_URL"] = normalized_api_base
    if timeout_seconds is not None:
        config.model_timeout_seconds = float(timeout_seconds)
    if max_output_tokens is not None:
        config.model_max_output_tokens = int(max_output_tokens)
    return config


def resolve_ollama_cli_settings(
    config: JaznConfig,
    *,
    model: str | None = None,
    api_base: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
) -> tuple[JaznConfig, dict[str, Any]]:
    """Apply CLI settings and verify/select a usable Ollama model.

    An explicitly configured model is verified against ``GET /api/tags``.  When
    no model was configured, exactly one running or installed model may be
    selected by the existing canonical ``probe_ollama`` policy.  Multiple
    models remain ambiguous and require ``--ollama-model`` instead of an
    arbitrary choice.
    """
    apply_ollama_cli_settings(
        config,
        model=model,
        api_base=api_base,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )

    from latka_jazn.core.llm_route_resolver import probe_ollama

    probe_timeout = min(max(float(getattr(config, "model_timeout_seconds", 45.0)), 0.1), 2.0)
    probe = probe_ollama(config, os.environ, timeout_seconds=probe_timeout)
    selected_model = str(probe.get("model") or "").strip()
    if selected_model:
        config.local_model_name = selected_model
    return config, probe


def _nonempty_text_from_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, str]:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        text = str(value)
        if text.strip():
            return text, field
    return "", "<missing>"


def is_chatgpt_host_visible_reply_payload(payload: dict[str, Any]) -> bool:
    """Return True when a JSONL line is the host->runtime reply phase.

    This keeps --chat-gpt a single public bridge while making the truth boundary
    explicit: local Python emits the runtime packet; the surrounding ChatGPT host
    may send back the visible wording in a second JSONL line for persistence.
    """
    payload_type = str(payload.get("type") or payload.get("kind") or "").strip().lower()
    phase = str(payload.get("phase") or payload.get("chatgpt_bridge_phase") or "").strip().lower()
    if payload_type in CHATGPT_HOST_VISIBLE_REPLY_TYPES:
        return True
    return phase in {"host_visible_reply", "chatgpt_host_visible_reply", "host_visible_reply_record"}


def extract_chatgpt_host_visible_reply_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Extract a fail-closed ChatGPT-host visible reply JSONL payload."""
    trace = json_object(payload.get("trace"))
    final_text, final_text_field = _nonempty_text_from_fields(payload, CHATGPT_HOST_VISIBLE_REPLY_TEXT_FIELDS)
    used_memory_value = payload.get("used_memory_item_ids")
    external_tool_evidence_value = payload.get("external_tool_evidence")
    values: dict[str, Any] = {
        "final_text": final_text,
        "final_text_field": final_text_field,
        "turn_id": str(payload.get("turn_id") or trace.get("turn_id") or "").strip(),
        "trace_id": str(payload.get("trace_id") or trace.get("trace_id") or "").strip(),
        "timestamp_header": str(payload.get("timestamp_header") or trace.get("timestamp_header") or "").strip(),
        "timezone": str(payload.get("timezone") or trace.get("timezone") or "").strip(),
        "timestamp_sample_iso": str(payload.get("timestamp_sample_iso") or "").strip(),
        "timestamp_source": str(payload.get("timestamp_source") or "").strip(),
        "timestamp_trusted": payload.get("timestamp_trusted"),
        "author_id": str(payload.get("author_id") or "").strip(),
        "author_label": str(payload.get("author_label") or "").strip(),
        "author_source": str(payload.get("author_source") or "").strip(),
        "state_emoticon": str(payload.get("state_emoticon") or payload.get("emoticon") or "").strip(),
        "final_text_sha256": str(payload.get("final_text_sha256") or "").strip().lower(),
        "host_request_contract_hash": str(payload.get("host_request_contract_hash") or "").strip().lower(),
        "used_memory_item_ids": (
            [str(item) for item in used_memory_value[:8]]
            if isinstance(used_memory_value, list)
            else []
        ),
        "external_tool_evidence": (
            list(external_tool_evidence_value[:8])
            if isinstance(external_tool_evidence_value, list)
            else []
        ),
    }
    missing: list[str] = []
    if not final_text:
        missing.append("final_text|host_visible_text|visible_text|assistant_text")
    for field in (
        "turn_id", "trace_id", "timestamp_header", "timezone", "timestamp_sample_iso",
        "timestamp_source", "author_id", "author_label", "author_source", "state_emoticon",
    ):
        if not values[field]:
            missing.append(field)
    if not isinstance(values["timestamp_trusted"], bool):
        missing.append("timestamp_trusted")
    if not re.fullmatch(r"[0-9a-f]{64}", str(values["final_text_sha256"])):
        missing.append("final_text_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(values["host_request_contract_hash"])):
        missing.append("host_request_contract_hash")
    return values, missing

def _runtime_validation(result: dict[str, Any]) -> dict[str, Any]:
    runtime_turn = json_object(result.get("runtime_turn_contract"))
    return json_object(runtime_turn.get("validation") or result.get("runtime_answer_validation"))


def _runtime_integrity(result: dict[str, Any]) -> dict[str, Any]:
    final_contract = json_object(result.get("final_response_contract"))
    return json_object(result.get("final_visible_integrity") or final_contract.get("final_visible_integrity"))


def _runtime_integrity_consensus(result: dict[str, Any]) -> dict[str, Any]:
    return json_object(result.get("final_visible_integrity_consensus"))


def _runtime_truth_gate(result: dict[str, Any]) -> dict[str, Any]:
    return json_object(result.get("runtime_truth_gate"))


def chatgpt_result_has_accepted_runtime_final(result: dict[str, Any]) -> bool:
    """Return true only for an accepted handler final that needs no host speech."""
    decision = json_object(result.get("conversation_decision"))
    runtime_turn = json_object(result.get("runtime_turn_contract"))
    final_contract = json_object(result.get("final_response_contract"))
    validation = _runtime_validation(result)
    handler_name = str(decision.get("handler_name") or runtime_turn.get("handler_name") or "")
    return bool(
        validation.get("accepted") is True
        and runtime_turn.get("requires_host_model") is False
        and final_contract.get("requires_host_model") is False
        and handler_name
        and handler_name != "RuntimeTurnTruthGate"
        and extract_final_visible_text_from_result(result)
    )


def chatgpt_result_has_displayable_runtime_final(result: dict[str, Any]) -> bool:
    """Fail closed unless every runtime-owned presentation gate accepts one exact envelope."""
    if not chatgpt_result_has_accepted_runtime_final(result):
        return False
    final_text = extract_final_visible_text_from_result(result)
    trace = json_object(result.get("trace"))
    final_contract = json_object(result.get("final_response_contract"))
    contract_text = final_contract.get("final_visible_text")
    integrity = _runtime_integrity(result)
    consensus = _runtime_integrity_consensus(result)
    truth_gate = _runtime_truth_gate(result)
    if not final_text or integrity.get("valid") is not True:
        return False
    # Brak konsensusu nie jest sukcesem. Host nie może sam uznać, że jedna z
    # kilku kopii kontraktu jest wystarczająca.
    if consensus.get("valid") is not True or consensus.get("mismatch") is not False:
        return False
    if truth_gate.get("ok") is not True or truth_gate.get("normal_response_allowed") is not True:
        return False
    if contract_text is None or str(contract_text) != final_text:
        return False
    expected_hash = str(integrity.get("text_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        return False
    if expected_hash != sha256_host_visible_text(final_text):
        return False
    timestamp_header = str(
        integrity.get("timestamp_header")
        or trace.get("timestamp_header")
        or final_contract.get("timestamp_header")
        or ""
    ).strip()
    author_line = str(integrity.get("author_line") or "").strip()
    if not author_line:
        emoticon = str(final_contract.get("state_emoticon") or "").strip()
        author_label = str(final_contract.get("author_label") or "").strip()
        author_line = f"{emoticon} {author_label}".strip()
    if not timestamp_header or not author_line:
        return False
    if not final_text.startswith(f"{timestamp_header}\n{author_line}\n\n"):
        return False
    return True


def chatgpt_result_has_displayable_host_final(result: dict[str, Any]) -> bool:
    """Validate a phase-2 final without trusting the phase label by itself."""
    bridge = json_object(result.get("chatgpt_host_bridge"))
    finalization = json_object(result.get("host_visible_finalization"))
    final_text = extract_final_visible_text_from_result(result)
    if finalization.get("accepted") is not True or not final_text:
        return False
    if str(finalization.get("final_visible_text") or "") != final_text:
        return False
    expected_hash = str(finalization.get("final_text_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        return False
    if expected_hash != sha256_host_visible_text(final_text):
        return False
    if str(finalization.get("turn_id") or "") != str(bridge.get("turn_id") or ""):
        return False
    if str(finalization.get("trace_id") or "") != str(bridge.get("trace_id") or ""):
        return False
    return True


def chatgpt_result_requires_host_visible_reply(result: dict[str, Any]) -> bool:
    """Detect when runtime explicitly delegates model-guided wording to the host."""
    decision = json_object(result.get("conversation_decision"))
    runtime_turn = json_object(result.get("runtime_turn_contract"))
    final_contract = json_object(result.get("final_response_contract"))
    validation = _runtime_validation(result)
    if chatgpt_result_has_displayable_runtime_final(result):
        decision["requires_host_model"] = False
        result["requires_host_model"] = False
        return False
    return bool(
        runtime_turn.get("requires_host_model")
        or decision.get("requires_host_model")
        or final_contract.get("requires_host_model")
        or validation.get("requires_host_model")
        or str(runtime_turn.get("fallback_classification") or final_contract.get("fallback_classification") or "") == "cannot_answer_directly"
    )


def chatgpt_result_requires_host_diagnostic(result: dict[str, Any]) -> bool:
    return not (
        chatgpt_result_has_displayable_runtime_final(result)
        or chatgpt_result_requires_host_visible_reply(result)
    )


def _canonical_mapping_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _build_session_continuity_commit(
    result: dict[str, Any],
    *,
    user_text: str,
    detected_intent: str,
    runtime_route: str,
) -> dict[str, Any]:
    """Bind the accepted phase-2 reply back to the phase-1 conversation state.

    The payload is local runtime bookkeeping, not autobiographical memory.  It
    lets host-finalized turns advance the durable dialogue/task checkpoint only
    when the pre-finalization session state still matches exactly.
    """
    session_snapshot = json_object(result.get("session"))
    session_id = str(session_snapshot.get("session_id") or "").strip()
    if not session_id:
        return {}
    decision = json_object(result.get("conversation_decision"))
    task_state = json_object(decision.get("dialogue_task_state"))
    provenance = json_object(result.get("session_provenance"))
    try:
        turn_count_before = max(0, int(provenance.get("continuity_turn_count") or 0))
    except (TypeError, ValueError):
        turn_count_before = 0
    return {
        "schema_version": schema_version("host_finalized_session_continuity_commit"),
        "session_id": session_id,
        "source_client": str(session_snapshot.get("source_client") or "chatgpt_host"),
        "user_text": str(user_text or ""),
        "detected_intent": str(detected_intent or "unknown"),
        "runtime_route": str(runtime_route or "unknown"),
        "dialogue_task_state": task_state,
        "session_state_before_sha256": _canonical_mapping_sha256(session_snapshot),
        "turn_count_before": turn_count_before,
        "wake_state_runtime": json_object(result.get("wake_state_runtime")),
        "truth_boundary": (
            "This record advances only durable dialogue/task continuity after an accepted host-visible reply; "
            "it is not an autobiographical memory and cannot create L3 memory."
        ),
    }


def _commit_host_finalized_session_continuity(
    *,
    config: JaznConfig,
    pending: dict[str, Any],
    binding: dict[str, Any],
    final_visible_text: str,
) -> dict[str, Any]:
    generation_context = json_object(pending.get("generation_context"))
    commit = json_object(generation_context.get("session_continuity_commit"))
    expected_commit_hash = str(binding.get("session_continuity_commit_sha256") or "").strip().lower()
    if not commit or not expected_commit_hash:
        return {
            "saved": False,
            "status": "not_bound_by_phase_one",
            "backward_compatible": True,
        }
    calculated_commit_hash = _canonical_mapping_sha256(commit)
    if calculated_commit_hash != expected_commit_hash:
        return {
            "saved": False,
            "status": "continuity_commit_hash_mismatch",
            "expected_sha256": expected_commit_hash,
            "calculated_sha256": calculated_commit_hash,
        }
    session_id = str(commit.get("session_id") or "").strip()
    if not session_id:
        return {"saved": False, "status": "continuity_session_id_missing"}
    store = RuntimeSessionStateStore(config.root)
    state = store.load_or_create(
        session_id=session_id,
        source_client=str(commit.get("source_client") or "chatgpt_host"),
        no_carryover=False,
    )
    current_hash = _canonical_mapping_sha256(state.to_dict())
    expected_before = str(commit.get("session_state_before_sha256") or "").strip().lower()
    if not expected_before or current_hash != expected_before:
        return {
            "saved": False,
            "status": "session_advanced_or_phase_one_checkpoint_missing",
            "current_state_sha256": current_hash,
            "expected_state_sha256": expected_before or None,
            "truth_boundary": (
                "A newer or non-matching durable session state was preserved instead of being overwritten by a delayed finalizer."
            ),
        }
    task_state = json_object(commit.get("dialogue_task_state"))
    state.update(
        user_text=str(commit.get("user_text") or ""),
        visible_text=final_visible_text,
        intent=str(commit.get("detected_intent") or "unknown"),
        route=str(commit.get("runtime_route") or "unknown"),
        task_state=task_state,
    )
    try:
        before_count = max(0, int(commit.get("turn_count_before") or 0))
    except (TypeError, ValueError):
        before_count = 0
    save_status = store.save(
        state,
        continuity_context=json_object(commit.get("wake_state_runtime")),
        turn_count=before_count + 1,
    )
    return {
        "saved": bool(save_status.get("session_state_saved")),
        "status": "saved" if save_status.get("session_state_saved") else "save_degraded",
        "session_id": session_id,
        "task_state_persisted": bool(task_state),
        "save_status": save_status,
    }


def build_chatgpt_host_bridge_turn_contract(
    result: dict[str, Any],
    *,
    user_text: str,
    chat_bridge_meta: dict[str, Any],
) -> dict[str, Any]:
    """Attach one authoritative presentation action to --chat-gpt output."""
    trace = json_object(result.get("trace"))
    decision = json_object(result.get("conversation_decision"))
    runtime_turn = json_object(result.get("runtime_turn_contract"))
    final_contract = json_object(result.get("final_response_contract"))
    displayable_runtime_final = chatgpt_result_has_displayable_runtime_final(result)
    requires_host = bool(not displayable_runtime_final and chatgpt_result_requires_host_visible_reply(result))
    detected_intent = str(
        decision.get("detected_user_intent")
        or decision.get("intent")
        or runtime_turn.get("detected_user_intent")
        or runtime_turn.get("intent")
        or ""
    )
    runtime_route = str(decision.get("route") or runtime_turn.get("runtime_route") or runtime_turn.get("route") or "")
    model_synthesis = json_object(decision.get("model_guided_synthesis"))
    host_generation_context = json_object(model_synthesis.get("host_generation_context"))
    if not validate_host_generation_context(host_generation_context):
        host_generation_context = build_host_generation_context_from_runtime(
            result,
            user_text=user_text,
            detected_intent=detected_intent,
            route=runtime_route,
        )
    host_generation_context_valid = validate_host_generation_context(host_generation_context)
    ownership = build_runtime_ownership_contract(detected_intent=detected_intent, route=runtime_route)
    host_policy = json_object(ownership.get("host_visible_generation_contract"))
    host_policy_rules = [str(item) for item in host_policy.get("rules", []) if str(item).strip()]
    turn_id = str(trace.get("turn_id") or runtime_turn.get("turn_id") or final_contract.get("turn_id") or "")
    trace_id = str(trace.get("trace_id") or runtime_turn.get("trace_id") or final_contract.get("trace_id") or "")
    timestamp_header = str(trace.get("timestamp_header") or runtime_turn.get("timestamp_header") or final_contract.get("timestamp_header") or "")
    timestamp_contract = json_object(decision.get("timestamp_contract"))
    timezone = str(final_contract.get("timezone") or trace.get("timezone") or timestamp_contract.get("timezone") or timestamp_contract.get("timezone_key") or "")
    timestamp_sample_iso = str(final_contract.get("timestamp_sample_iso") or timestamp_contract.get("sample_iso") or "")
    timestamp_source = str(final_contract.get("timestamp_source") or timestamp_contract.get("source") or "")
    timestamp_trusted = final_contract.get("timestamp_trusted") if isinstance(final_contract.get("timestamp_trusted"), bool) else timestamp_contract.get("trusted")
    author_id = str(final_contract.get("author_id") or "")
    author_label = str(final_contract.get("author_label") or "")
    author_source = str(final_contract.get("author_source") or "")
    state_emoticon = str(final_contract.get("state_emoticon") or decision.get("state_emoticon") or "")
    runtime_version = str(final_contract.get("runtime_version") or result.get("runtime_version") or PACKAGE_VERSION_FULL)
    daemon = json_object(result.get("daemon"))
    daemon_job = json_object(result.get("daemon_job"))
    daemon_request_id = str(daemon.get("request_id") or daemon_job.get("request_id") or "").strip()
    runtime_summary = {
        "route": runtime_route,
        "detected_intent": detected_intent,
        "handler_name": decision.get("handler_name") or runtime_turn.get("handler_name"),
        "fallback_classification": runtime_turn.get("fallback_classification") or final_contract.get("fallback_classification"),
        "runtime_answer_quality": runtime_turn.get("runtime_answer_quality") or final_contract.get("runtime_answer_quality"),
        "response_generation_mode": runtime_turn.get("response_generation_mode") or decision.get("response_generation_mode"),
        "source_origin_detail": runtime_turn.get("source_origin_detail") or decision.get("source_origin_detail"),
        "can_generate_model_guided_speech": True if requires_host else runtime_turn.get("can_generate_model_guided_speech"),
        "can_generate_model_guided_speech_locally": False if requires_host else runtime_turn.get("can_generate_model_guided_speech"),
        "can_complete_model_guided_speech_via_host": bool(requires_host),
        "generation_executor": "chatgpt_host" if requires_host else "runtime",
        "requires_host_model": requires_host,
    }
    session_continuity_commit = _build_session_continuity_commit(
        result,
        user_text=user_text,
        detected_intent=detected_intent,
        runtime_route=runtime_route,
    )
    session_continuity_commit_sha256 = (
        _canonical_mapping_sha256(session_continuity_commit) if session_continuity_commit else ""
    )
    context_for_hash = {
        "runtime_summary": runtime_summary,
        "runtime_ownership_contract": ownership,
        "host_generation_policy": host_policy,
        "host_generation_context": host_generation_context,
    }
    runtime_context_sha256 = hashlib.sha256(
        json.dumps(context_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    phase = "host_visible_generation_requested" if requires_host else (
        "runtime_final_available" if displayable_runtime_final else "host_diagnostic_required"
    )
    status = {
        "host_visible_generation_requested": "requires_host_chatgpt_visible_response",
        "runtime_final_available": "runtime_final_visible_text_available",
        "host_diagnostic_required": "runtime_final_not_displayable",
    }[phase]
    bridge: dict[str, Any] = {
        "schema_version": schema_version("chatgpt_host_bridge_turn_contract"),
        "runtime_version": runtime_version,
        "phase": phase,
        "host_must_generate_visible_reply": requires_host,
        "status": status,
        "command": "--chat-gpt",
        "turn_id": turn_id,
        "trace_id": trace_id,
        "timestamp_header": timestamp_header,
        "timezone": timezone,
        "timestamp_sample_iso": timestamp_sample_iso,
        "timestamp_source": timestamp_source,
        "timestamp_trusted": timestamp_trusted,
        "author_id": author_id,
        "author_label": author_label,
        "author_source": author_source,
        "state_emoticon": state_emoticon,
        "timestamp_required": bool(timestamp_header),
        "required_visible_prefix": timestamp_header,
        "host_reply_finalization_required": requires_host,
        "user_text_sha256": hashlib.sha256((user_text or "").encode("utf-8")).hexdigest(),
        "runtime_context_sha256": runtime_context_sha256,
        "session_continuity_commit": session_continuity_commit,
        "session_continuity_commit_sha256": session_continuity_commit_sha256,
        "daemon_request_id": daemon_request_id,
        "runtime_summary": runtime_summary,
        "runtime_ownership_contract": ownership,
        "host_generation_policy": host_policy,
        "host_generation_context": host_generation_context,
        "host_generation_context_sha256": str(host_generation_context.get("context_sha256") or ""),
        "accepted_host_reply_text_fields": list(CHATGPT_HOST_VISIBLE_REPLY_TEXT_FIELDS),
        "chat_bridge": chat_bridge_meta,
        "display_exact_runtime_final": displayable_runtime_final,
        "truth_boundary": (
            "Host wykonuje wyłącznie akcję wskazaną w phase. runtime_final_available oznacza dosłowne wyświetlenie tekstu; "
            "host_visible_generation_requested wymaga związanej z turą drugiej fazy; host_diagnostic_required zabrania imitowania Łatki."
        ),
    }
    if requires_host:
        try:
            finalization_contract = HostVisibleFinalizationContract(
                required_timestamp_header=timestamp_header,
                timezone=timezone,
                timestamp_sample_iso=timestamp_sample_iso,
                timestamp_source=timestamp_source,
                timestamp_trusted=bool(timestamp_trusted),
                author_id=author_id,
                author_label=author_label,
                author_source=author_source,
                state_emoticon=state_emoticon,
                turn_id=turn_id,
                trace_id=trace_id,
            )
            bridge["finalization_contract_hash"] = finalization_contract.contract_hash
            bridge["host_request_contract_hash"] = calculate_host_request_contract_hash(bridge)
            bridge["host_reply_jsonl_shape"] = {
                "type": "host_visible_reply",
                "turn_id": turn_id,
                "trace_id": trace_id,
                "host_request_contract_hash": bridge["host_request_contract_hash"],
                "timestamp_header": timestamp_header,
                "timezone": timezone,
                "timestamp_sample_iso": timestamp_sample_iso,
                "timestamp_source": timestamp_source,
                "timestamp_trusted": timestamp_trusted,
                "author_id": author_id,
                "author_label": author_label,
                "author_source": author_source,
                "state_emoticon": state_emoticon,
                "final_text": "<body albo kompletna widoczna koperta zgodna z runtime_ownership_contract>",
                "final_text_sha256": "<sha256 kanonicznego UTF-8/LF pola final_text>",
                "used_memory_item_ids": "<identyfikatory faktycznie użytych allowed_memory_items>",
                "external_tool_evidence": "<bounded host-attested evidence only for tools actually executed outside runtime>",
            }
        except (TypeError, ValueError) as exc:
            bridge.update({
                "phase": "host_diagnostic_required",
                "host_must_generate_visible_reply": False,
                "status": "host_finalization_contract_invalid",
                "host_reply_finalization_required": False,
                "diagnostic_reason": f"host_finalization_contract_invalid:{type(exc).__name__}",
            })
            requires_host = False
    bridge["host_generation_rules"] = [
        *host_policy_rules,
        "Nie twierdź, że lokalny Python wywołał ChatGPT jako funkcję.",
        "Nie zmieniaj turn_id, trace_id, timestampu, autora ani host_request_contract_hash.",
        "Hash tekstu licz po kanonizacji UTF-8 z końcami linii LF i bez BOM.",
        "Zadeklaruj każdy użyty identyfikator pamięci i nie używaj identyfikatorów spoza host_generation_context.allowed_memory_item_ids.",
        "Jeżeli host rzeczywiście wykonał web.run lub GitHub, przekaż ograniczone external_tool_evidence; nigdy nie wymyślaj dowodu wykonania narzędzia.",
        "Jeżeli phase=host_diagnostic_required, pokaż diagnozę hosta zamiast imitować wypowiedź Łatki.",
    ]
    if requires_host and not host_generation_context_valid:
        bridge.update({
            "phase": "host_diagnostic_required",
            "status": "host_generation_context_missing_or_invalid",
            "host_must_generate_visible_reply": False,
            "host_reply_finalization_required": False,
            "diagnostic_reason": "host_generation_context_missing_or_invalid",
        })
    return bridge


def build_chatgpt_host_presentation_packet(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compact action packet after re-validating the requested phase."""
    bridge = json_object(payload.get("chatgpt_host_bridge"))
    phase = str(bridge.get("phase") or "host_diagnostic_required")
    if phase == "runtime_final_available" and chatgpt_result_has_displayable_runtime_final(payload):
        action = "display_exact"
    elif phase == "host_visible_reply_recorded" and chatgpt_result_has_displayable_host_final(payload):
        action = "display_exact"
    elif (
        phase == "host_visible_generation_requested"
        and bridge.get("host_must_generate_visible_reply") is True
        and bridge.get("pending_request_persisted") is True
        and re.fullmatch(r"[0-9a-f]{64}", str(bridge.get("host_request_contract_hash") or ""))
    ):
        action = "generate_then_finalize"
    elif (
        phase == "runtime_result_pending"
        and str(bridge.get("daemon_request_id") or "").strip()
        and str(bridge.get("poll_command") or "").strip()
    ):
        action = "poll_runtime"
    else:
        action = "host_diagnostic"
    transport_observability = json_object(payload.get("transport_observability"))
    if not transport_observability:
        transport_observability = json_object(
            json_object(payload.get("chat_bridge")).get("transport_observability")
        )
    memory_recall_observability = correlate_memory_recall_transport(
        json_object(payload.get("memory_recall_observability")),
        transport_observability,
    )
    memory_violation = memory_recall_truth_boundary_violation(
        memory_recall_observability,
        recall_required=memory_recall_observability.get("memory_recall_requested") is True,
        expected_turn_id=str(bridge.get("turn_id") or "") or None,
        expected_trace_id=str(bridge.get("trace_id") or "") or None,
    )
    if memory_violation is not None:
        action = "host_diagnostic"
        phase = "host_diagnostic_required"
    final_text = extract_final_visible_text_from_result(payload) if action == "display_exact" else ""
    validation = _runtime_validation(payload)
    integrity = _runtime_integrity(payload)
    consensus = _runtime_integrity_consensus(payload)
    truth_gate = _runtime_truth_gate(payload)
    final_contract = json_object(payload.get("final_response_contract"))
    host_policy = json_object(bridge.get("host_generation_policy"))
    voice_policy = json_object(host_policy.get("voice_continuity_policy"))
    packet: dict[str, Any] = {
        "schema_version": schema_version("chatgpt_host_presentation_packet"),
        "type": "chatgpt_host_presentation",
        "action": action,
        "phase": phase,
        "turn_id": bridge.get("turn_id"),
        "trace_id": bridge.get("trace_id"),
        "author_source": (
            final_contract.get("author_source")
            or bridge.get("author_source")
        ),
        "must_display_exactly": action == "display_exact",
        "must_not_paraphrase": action == "display_exact",
        "must_not_claim_latka_voice": action in {"host_diagnostic", "poll_runtime"},
        "must_preserve_latka_voice": bool(action == "generate_then_finalize" and voice_policy.get("active_runtime_first_person_voice_required")),
        "external_tools_do_not_transfer_voice": bool(voice_policy.get("external_tools_do_not_transfer_voice")),
        "forbidden_visible_prefixes": list(voice_policy.get("forbidden_visible_prefixes") or []),
        "required_visible_prefix": bridge.get("required_visible_prefix"),
        "final_visible_text": final_text,
        "final_text_sha256": sha256_host_visible_text(final_text) if final_text else None,
        "chatgpt_host_bridge": bridge,
        "daemon_request_id": bridge.get("daemon_request_id"),
        "poll_command": bridge.get("poll_command"),
        "diagnostic_reason": memory_violation,
        "runtime_checks": {
            "validation_accepted": validation.get("accepted"),
            "final_visible_integrity_valid": integrity.get("valid"),
            "integrity_consensus_valid": consensus.get("valid") if consensus else None,
            "integrity_consensus_mismatch": consensus.get("mismatch") if consensus else None,
            "runtime_truth_gate_ok": truth_gate.get("ok"),
            "normal_response_allowed": truth_gate.get("normal_response_allowed"),
            "runtime_truth_gate_errors": list(truth_gate.get("errors") or []),
            "runtime_truth_gate_degradations": list(truth_gate.get("degradations") or []),
            "timestamp_degraded": bool(truth_gate.get("timestamp_degraded")),
        },
        "host_instruction": {
            "display_exact": "Pokaż wyłącznie final_visible_text znak w znak.",
            "generate_then_finalize": "Wygeneruj tekst wyłącznie z host_generation_policy, odeślij host_visible_reply i pokaż dopiero final zaakceptowany przez runtime. Degradacja do świeżego czasu OS jest informacją, nie powodem zmiany action na host_diagnostic.",
            "poll_runtime": "Nie uruchamiaj ponownie wiadomości. Pobierz wynik istniejącej tury przez poll_command/request_id.",
            "host_diagnostic": "Nie imituj Łatki; pokaż krótką diagnozę jako Host ChatGPT.",
        }[action],
    }
    if transport_observability:
        packet["transport_observability"] = transport_observability
    if memory_recall_observability:
        packet["memory_recall_observability"] = memory_recall_observability
    gate_context = json_object(payload.get("host_pre_response_gate_context"))
    runtime_turn_invoked = bool(
        gate_context.get("runtime_turn_invoked") is True
        or bridge
    )
    gate_telemetry = build_host_pre_response_gate_telemetry(
        presentation=packet,
        response=payload,
        user_text_sha256=str(bridge.get("user_text_sha256") or ""),
        requested_runtime_root=(
            gate_context.get("requested_runtime_root")
            or transport_observability.get("requested_runtime_root")
        ),
        runtime_turn_invoked=runtime_turn_invoked,
    )
    packet["host_pre_response_gate"] = gate_telemetry
    packet["visible_output_source"] = gate_telemetry.get("visible_output_source")
    return packet


def attach_chatgpt_host_contract(
    result: dict[str, Any],
    *,
    config: JaznConfig,
    user_text: str,
    chat_bridge_meta: dict[str, Any],
) -> dict[str, Any]:
    """Attach and persist one idempotent ChatGPT host presentation contract."""

    result["chat_bridge"] = dict(chat_bridge_meta)
    result["chatgpt_bridge"] = dict(chat_bridge_meta)
    bridge_value = result.get("chatgpt_host_bridge")
    bridge = bridge_value if isinstance(bridge_value, dict) else {}
    if not bridge:
        bridge = build_chatgpt_host_bridge_turn_contract(
            result,
            user_text=user_text,
            chat_bridge_meta=chat_bridge_meta,
        )
        result["chatgpt_host_bridge"] = bridge
    if (
        bridge.get("phase") == "host_visible_generation_requested"
        and bridge.get("pending_request_persisted") is not True
    ):
        try:
            ttl_seconds = continuation_ttl_for_bridge(bridge)
            pending = persist_pending_host_request(config.root, bridge, ttl_seconds=ttl_seconds)
            bridge["pending_request_persisted"] = True
            bridge["pending_request_state"] = pending.get("state")
            bridge["pending_request_ttl_seconds"] = ttl_seconds
            bridge["pending_request_expires_at_utc"] = pending.get("expires_at_utc")
        except HostRequestStoreError as exc:
            bridge.update({
                "phase": "host_diagnostic_required",
                "status": "pending_host_request_persistence_failed",
                "host_must_generate_visible_reply": False,
                "host_reply_finalization_required": False,
                "diagnostic_reason": f"pending_host_request:{exc}",
            })
    result["chatgpt_host_presentation"] = build_chatgpt_host_presentation_packet(result)
    return result


def persist_chatgpt_host_visible_reply(
    *,
    config: JaznConfig,
    payload: dict[str, Any],
    chat_bridge_meta: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Persist phase-2 text only when it matches one unconsumed phase-1 request."""
    reply, missing = extract_chatgpt_host_visible_reply_payload(payload)
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
    semantic_validation = evaluate_host_response_candidate(
        final_text=reply["final_text"],
        host_generation_context=host_generation_context,
        used_memory_item_ids=list(reply.get("used_memory_item_ids") or []),
        external_tool_evidence=list(reply.get("external_tool_evidence") or []),
    )
    if semantic_validation.get("accepted") is not True:
        release_claimed_host_request(config.root, turn_id=reply["turn_id"])
        violations = [str(item) for item in semantic_validation.get("violations") or []]
        return None, [f"host_candidate:{item}" for item in violations or ["rejected"]]
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
        violation_codes = [item.code for item in finalization.violations]
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
                return None, [f'host_regeneration:{exc}', *[f'finalization:{code}' for code in violation_codes]]
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
                'host_visible_finalization': finalization.to_dict(),
                'host_regeneration': regeneration.to_dict(),
            }
            retry_result['chatgpt_host_presentation'] = build_chatgpt_host_presentation_packet(retry_result)
            return retry_result, []
        release_claimed_host_request(config.root, turn_id=reply['turn_id'])
        terminal_errors = [f'finalization:{item.code}' for item in finalization.violations]
        if regeneration.reason == 'regeneration_budget_exhausted':
            terminal_errors.insert(0, 'host_regeneration:host_regeneration_budget_exhausted')
        return None, terminal_errors
    reply["final_text"] = finalization.final_visible_text

    from latka_jazn.core.engine import JaznEngine

    try:
        engine = JaznEngine(config)
        try:
            capture = engine.persist_final_visible_reply(
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
            engine.shutdown()
        try:
            session_continuity = _commit_host_finalized_session_continuity(
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
        consumed = consume_claimed_host_request(
            config.root,
            turn_id=reply["turn_id"],
            request_contract_hash=reply["host_request_contract_hash"],
        )
    except Exception as exc:
        # Once persistence begins, a failure may have happened after one append-only
        # write succeeded.  Releasing the claim would permit a duplicate visible
        # reply.  Keep it fail-closed and expose an auditable indeterminate state.
        try:
            mark_claimed_host_request_indeterminate(
                config.root,
                turn_id=reply["turn_id"],
                error=f"{type(exc).__name__}:{exc}",
            )
        except Exception:
            pass
        return None, [f"host_persistence_indeterminate:{type(exc).__name__}"]
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
        "session_continuity_persistence": session_continuity,
    }
    return result, []


def extract_final_visible_text_from_result(payload: dict[str, Any]) -> str:
    """Return the visible Łatka reply from a chat bridge payload.

    The JSONL protocol remains the default source of truth. This helper is only
    for the human-readable --chat-gpt rendering mode.
    """
    final: Any = payload.get("final_visible_text")
    final_contract = payload.get("final_response_contract")
    if final is None and isinstance(final_contract, dict):
        final = final_contract.get("final_visible_text")
    provenance = payload.get("runtime_provenance")
    if final is None and isinstance(provenance, dict):
        final = provenance.get("visible_answer_text")
    if final is None:
        final = payload.get("exact_runtime_text")
    if final is None and payload.get("error"):
        error_code = str(payload.get("error_code") or "chat_bridge_error")
        final = f"[{error_code}] {payload.get('error')}"
    return str(final or "")


def write_chat_bridge_payload(stdout: TextIO, payload: dict[str, Any], *, output_mode: BridgeOutputMode = "jsonl") -> None:
    presentation = build_chatgpt_host_presentation_packet(payload)
    action = str(presentation.get("action") or "host_diagnostic")
    if output_mode == "final_visible_text" and action == "display_exact":
        # Dosłowny tryb nie może nawet dopisać końcowego LF.
        stdout.write(str(presentation.get("final_visible_text") or ""))
    elif output_mode == "host_packet" or output_mode == "final_visible_text":
        if output_mode == "final_visible_text" and action != "display_exact":
            presentation["requested_mode"] = "final_visible_text"
            presentation["effective_mode"] = "host_packet"
            presentation["reason"] = "plain_text_blocked_by_host_presentation_gate"
        stdout.write(json.dumps(presentation, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    stdout.flush()


def _mark_verified_one_shot_transport(turn_transport: dict[str, Any]) -> None:
    previous_transport = str(turn_transport.get("selected_transport") or "")
    previous_reason = str(turn_transport.get("fallback_reason") or "")
    turn_transport.update({
        "selected_transport": "verified_one_shot_fallback",
        "one_shot_allowed": True,
        "one_shot_verified": True,
    })
    if (
        previous_transport == "persistent_daemon"
        and previous_reason in {"daemon_reused", "daemon_started"}
    ):
        turn_transport["fallback_reason"] = "jsonl_bridge_uses_verified_one_shot"
    elif not previous_reason or previous_reason == "transport_not_classified":
        turn_transport["fallback_reason"] = "verified_one_shot_fallback_allowed"


def run_jsonl_chat_bridge(
    *,
    config: JaznConfig,
    session_id: str | None,
    no_carryover: bool,
    command: str,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    require_openai_api_key: bool = False,
    output_mode: BridgeOutputMode = "jsonl",
    one_shot_degraded: bool = False,
    transport_observability: dict[str, Any] | None = None,
) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if stdin is None:
        raise RuntimeError("chat_bridge_stdin_unavailable")
    if stdout is None:
        raise RuntimeError("chat_bridge_stdout_unavailable")
    if output_mode not in CHAT_BRIDGE_OUTPUT_MODES:
        raise ValueError(f"unsupported chat bridge output_mode: {output_mode}")
    if command == "--chat-gpt":
        apply_chatgpt_cli_settings(config)
    elif command == "--chat-open-ai":
        apply_openai_cli_settings(config)
    elif command in {"--chat-ollama", "--local-llm", "--ollama"}:
        apply_ollama_cli_settings(config)
    contract = command_contract(
        command,
        process_lifecycle="one_shot" if output_mode == "final_visible_text" else "jsonl_bridge",
    )
    protocol_version = CHATGPT_BRIDGE_PROTOCOL
    default_client = "chatgpt_bridge"
    default_lifecycle = "chatgpt_bridge_jsonl"
    turn_transport = dict(transport_observability or {})
    if command == "--chat-open-ai":
        protocol_version = CHAT_OPENAI_PROTOCOL
        default_client = "openai_api_bridge"
        default_lifecycle = "openai_api_jsonl"
    elif command in {"--chat-ollama", "--local-llm", "--ollama"}:
        protocol_version = OLLAMA_PROTOCOL
        default_client = "ollama_local_bridge"
        default_lifecycle = "ollama_jsonl_contract"

    if require_openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        payload = {
            "schema_version": schema_version("chat_command_startup_error"),
            "ok": False,
            "error_code": "missing_openai_api_key",
            "error": "--chat-open-ai wymaga zmiennej środowiskowej OPENAI_API_KEY. Nie uruchamiam modelu i nie udaję połączenia z OpenAI API.",
            "chat_command_contract": contract,
        }
        write_chat_bridge_payload(stdout, payload, output_mode=output_mode)
        return 3

    sessions: dict[str, RuntimeSessionWorker] = {}
    generated_session: RuntimeSessionWorker | None = None

    def bridge_meta(
        *,
        client: str = default_client,
        input_kind: str | None = None,
        input_field: str | None = None,
        line_index: int | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "protocol_version": protocol_version,
            "accepted_input_fields": list(ACCEPTED_CHATGPT_INPUT_FIELDS),
            "accepted_input_shapes": list(contract["accepted_input_shapes"]),
            "preferred_input_field": "message",
            "client": client,
            "lifecycle": default_lifecycle,
            "mode": contract["mode"],
            "command": command,
            "requires_api_key": contract["requires_api_key"],
            "uses_openai_api": contract["uses_openai_api"],
            "canonical_command": "--chat-gpt" if command == "--chat-gpt" else command,
            "legacy_aliases": ["--chat-gpt-final-only", "--chat-gpt --final-only"] if command == "--chat-gpt" else [],
            "canonicalization_policy": (
                "Use --chat-gpt as the single public ChatGPT bridge; aliases are backwards-compatible only."
                if command == "--chat-gpt" else "canonical command"
            ),
            "deprecated_flag_removed": "--chat-jsonl",
        }
        if input_kind is not None:
            meta["input_kind"] = input_kind
        if input_field is not None:
            meta["input_field"] = input_field
        if line_index is not None:
            meta["line_index"] = line_index
        if turn_transport:
            meta["transport_observability"] = dict(turn_transport)
        return meta

    def error_payload(
        *,
        error_code: str,
        error: str,
        client: str = default_client,
        input_kind: str | None = None,
        input_field: str | None = None,
        line_index: int | None = None,
        runtime_turn_invoked: bool = False,
    ) -> dict[str, Any]:
        return {
            "schema_version": schema_version("chat_bridge_error"),
            "chat_bridge": bridge_meta(client=client, input_kind=input_kind, input_field=input_field, line_index=line_index),
            "chat_command_contract": contract,
            "host_pre_response_gate_context": {
                "runtime_turn_invoked": runtime_turn_invoked,
                "requested_runtime_root": str(
                    turn_transport.get("requested_runtime_root")
                    or config.root
                ),
            },
            "ok": False,
            "error_code": error_code,
            "error": error,
        }

    def get_session(payload_session_id: str | None, *, client: str) -> tuple[RuntimeSessionWorker, str]:
        nonlocal generated_session
        if payload_session_id:
            if payload_session_id not in sessions:
                sessions[payload_session_id] = RuntimeSessionWorker(session_factory=JaznRuntimeSession, config=config, session_id=payload_session_id, no_carryover=no_carryover, source_client=client, command=command, timeout_seconds=runtime_turn_timeout_seconds(config))
            return sessions[payload_session_id], "payload"
        if session_id:
            if session_id not in sessions:
                sessions[session_id] = RuntimeSessionWorker(session_factory=JaznRuntimeSession, config=config, session_id=session_id, no_carryover=no_carryover, source_client=client, command=command, timeout_seconds=runtime_turn_timeout_seconds(config))
            return sessions[session_id], "cli_arg"
        if generated_session is None:
            generated_session = RuntimeSessionWorker(session_factory=JaznRuntimeSession, config=config, session_id=None, no_carryover=no_carryover, source_client=client, command=command, timeout_seconds=runtime_turn_timeout_seconds(config))
            sessions[generated_session.state.session_id] = generated_session
        return generated_session, "generated"

    try:
        for line_index, line in enumerate(stdin, 1):
            line = line.strip()
            if not line:
                continue
            if line in {"/exit", "exit"}:
                break

            input_kind = "plain_text"
            input_field = "plain_text"
            payload_session_id = None
            client = default_client

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                if line[:1] in {"{", "["}:
                    write_chat_bridge_payload(stdout, error_payload(
                        error_code="malformed_json",
                        error=f"Niepoprawna linia JSONL: {exc.msg}",
                        input_kind="malformed_json",
                        input_field="<parse_error>",
                        line_index=line_index,
                    ), output_mode=output_mode)
                    continue
                user_text = line
            else:
                input_kind = "json"
                if not isinstance(payload, dict):
                    write_chat_bridge_payload(stdout, error_payload(
                        error_code="invalid_jsonl_payload",
                        error="Każda linia mostu chat musi być obiektem JSON albo zwykłym tekstem.",
                        input_kind="json_non_object",
                        input_field="<non_object>",
                        line_index=line_index,
                    ), output_mode=output_mode)
                    continue
                client = str(payload.get("client") or default_client)
                if command == "--chat-gpt" and is_chatgpt_host_visible_reply_payload(payload):
                    meta = bridge_meta(client=client, input_kind="json_host_visible_reply", input_field="type", line_index=line_index)
                    persisted, missing = persist_chatgpt_host_visible_reply(
                        config=config,
                        payload=payload,
                        chat_bridge_meta=meta,
                        contract=contract,
                    )
                    if missing:
                        write_chat_bridge_payload(stdout, error_payload(
                            error_code="invalid_host_visible_reply",
                            error="Brakuje pól dla host_visible_reply: " + ", ".join(missing),
                            client=client,
                            input_kind="json_host_visible_reply",
                            input_field="type",
                            line_index=line_index,
                        ), output_mode=output_mode)
                    else:
                        write_chat_bridge_payload(stdout, persisted or {}, output_mode=output_mode)
                    continue
                payload_session_id = str(payload.get("session_id") or "").strip() or None
                user_text, input_kind, input_field = extract_user_text_from_payload(payload)

            if not user_text.strip():
                write_chat_bridge_payload(stdout, error_payload(
                    error_code="empty_message",
                    error="Pusta wiadomość nie została przekazana do runtime Jaźni.",
                    client=client,
                    input_kind=input_kind,
                    input_field=input_field,
                    line_index=line_index,
                ), output_mode=output_mode)
                continue

            classification_text, input_warning = guard_cli_flags_in_user_text(user_text)
            if not classification_text:
                classification_text = user_text

            try:
                session, session_id_source = get_session(payload_session_id, client=client)
                result = session.process_user_text(
                    classification_text,
                    client=client,
                    lifecycle=default_lifecycle,
                    session_id_source=session_id_source,
                    process_reused=True,
                )
            except RuntimeTurnTimeoutError as exc:
                write_chat_bridge_payload(stdout, error_payload(
                    error_code="runtime_turn_timeout",
                    error=(
                        f"Runtime Jaźni nie zakończył etapu {getattr(exc, 'phase', 'runtime_turn')} w limicie {exc.timeout_seconds:.3g}s. "
                        "Zwracam kontrolowany błąd zamiast wiszącego mostu; sprawdź start sesji, timestamp/memory/engine.process_turn."
                    ),
                    client=client,
                    input_kind=input_kind,
                    input_field=input_field,
                    line_index=line_index,
                    runtime_turn_invoked=True,
                ), output_mode=output_mode)
                continue
            except Exception as exc:
                write_chat_bridge_payload(stdout, error_payload(
                    error_code="runtime_turn_failed",
                    error=f"Runtime Jaźni przerwał turę: {type(exc).__name__}: {exc}",
                    client=client,
                    input_kind=input_kind,
                    input_field=input_field,
                    line_index=line_index,
                    runtime_turn_invoked=True,
                ), output_mode=output_mode)
                continue
            attach_cli_flag_warning(result, input_warning)
            if one_shot_degraded:
                _mark_verified_one_shot_transport(turn_transport)
                result["one_shot_degraded"] = True
                result["process_lifecycle"] = "one_shot"
                result["daemon_confirmed"] = False
                result["background_claim_allowed"] = False
                result["host_transport_diagnostic"] = {
                    "code": "one_shot_degraded",
                    "message": "Daemon nie został potwierdzony; wykonano zweryfikowaną turę jednorazową.",
                    "must_not_modify_final_visible_text": True,
                }
            if turn_transport:
                result["transport_observability"] = dict(turn_transport)
            result["chat_bridge"] = bridge_meta(client=client, input_kind=input_kind, input_field=input_field, line_index=line_index)
            result["host_pre_response_gate_context"] = {
                "runtime_turn_invoked": True,
                "requested_runtime_root": str(
                    turn_transport.get("requested_runtime_root")
                    or config.root
                ),
            }
            # Zachowujemy stary klucz dla zgodności z narzędziami, które już czytają --chat-gpt.
            if command == "--chat-gpt":
                attach_chatgpt_host_contract(
                    result,
                    config=config,
                    user_text=user_text,
                    chat_bridge_meta=result["chat_bridge"],
                )
            result["chat_command_contract"] = contract
            # poprzednia linia runtime: most nie może nadpisać blokady runtime truth gate przez ok=True.
            result["ok"] = bool(result.get("ok", True))
            write_chat_bridge_payload(stdout, result, output_mode=output_mode)
    finally:
        for session in sessions.values():
            session.close()
    return 0
