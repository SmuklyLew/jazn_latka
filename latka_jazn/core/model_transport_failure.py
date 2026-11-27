"""Bounded evidence of a failed model transport, not a host-generation request.

Observed local Ollama failures and a verified unavailable auto/null executor
are distinguished here. No provider text, endpoint URL, prompt, credentials,
or guessed cause crosses this boundary.
"""
from __future__ import annotations

import re
from typing import Any

from latka_jazn.core.json_types import json_object


_OLLAMA_FAILURE_CODES = frozenset({
    "local_provider_unavailable", "model_request_timeout", "model_circuit_open",
    "ollama_chat_response_truncated", "ollama_chat_json_invalid",
    "ollama_chat_response_not_object", "ollama_chat_provider_error",
    "ollama_chat_response_not_complete", "ollama_chat_message_invalid",
    "ollama_chat_role_invalid", "ollama_chat_content_invalid",
    "ollama_model_metadata_unavailable", "ollama_tags_response_invalid",
})


def ollama_transport_failure(response: object) -> dict[str, Any] | None:
    """Read the actual last adapter attempt, never configuration or prose."""
    value = json_object(response)
    if (
        value.get("adapter_id") != "local_llm_adapter"
        or value.get("provider") != "ollama"
        or value.get("generated") is not False
        or value.get("status") in (None, "", "completed")
    ):
        return None
    transport = json_object(value.get("transport"))
    attempts = transport.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return None
    last = json_object(attempts[-1])
    code = last.get("error_code")
    if not (
        isinstance(code, str) and code == transport.get("error_code")
        and (code in _OLLAMA_FAILURE_CODES or re.fullmatch(r"http_error_[45][0-9]{2}", code))
        and last.get("status") not in (None, "", "completed")
        and isinstance(last.get("request_dispatched"), bool)
    ):
        return None
    circuit = json_object(last.get("model_transport_circuit"))
    circuit_state = circuit.get("state")
    return {
        "provider": "ollama",
        "adapter_id": "local_llm_adapter",
        "endpoint": "/api/chat",
        "error_code": code,
        "failure_kind": "transport",
        "request_dispatched": last["request_dispatched"],
        "circuit_state": circuit_state if circuit_state in ("closed", "open", "half_open") else None,
        "automatic_retry_allowed": False,
        "host_generation_authorized": False,
    }


def ollama_terminal_attempt_failure(response: object) -> dict[str, Any] | None:
    """Distinguish a known transport failure from a completed, limited output."""
    transport_failure = ollama_transport_failure(response)
    if transport_failure is not None:
        return transport_failure
    value = json_object(response)
    if (
        value.get("adapter_id") != "local_llm_adapter"
        or value.get("provider") != "ollama"
        or value.get("generated") is not False
        or value.get("status") != "output_limit_reached"
    ):
        return None
    transport = json_object(value.get("transport"))
    attempts = transport.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return None
    last = json_object(attempts[-1])
    if not (
        transport.get("error_code") == last.get("error_code") == "model_output_limit_reached"
        and last.get("status") == "output_limit_reached"
        and last.get("request_dispatched") is True
        and last.get("done") is True and last.get("done_reason") == "length"
    ):
        return None
    return {
        "provider": "ollama", "adapter_id": "local_llm_adapter",
        "endpoint": "/api/chat", "error_code": "model_output_limit_reached",
        "failure_kind": "generation_limit", "request_dispatched": True,
        "done_reason": "length", "automatic_retry_allowed": False,
        "host_generation_authorized": False,
    }


def terminal_local_model_failure(decision: object) -> dict[str, Any] | None:
    """Identify a failed selected local executor, not a valid accepted candidate.

    A later semantic retry, when present, supersedes the earlier candidate.
    This does not classify an unavailable/null route or invent a transport error
    from the absence of a generation result.
    """
    value = json_object(decision)
    preflight = json_object(value.get("model_executor_preflight"))
    if preflight.get("executor") != "local_model" or value.get("model_generated") is True:
        return None
    synthesis = json_object(value.get("model_guided_retry_synthesis"))
    if not synthesis:
        synthesis = json_object(value.get("model_guided_synthesis"))
    if synthesis.get("used") is True:
        return None
    return ollama_terminal_attempt_failure(synthesis.get("adapter_response"))



def terminal_model_failure(decision: object) -> dict[str, Any] | None:
    """Distinguish a known transport failure from no selected generator.

    A missing or unprobed endpoint is not evidence of a failed HTTP request.
    Only the runtime's selected auto/null route and its actual no-generation
    synthesis qualify here. An explicit host route or runtime-exact answer
    must remain governed by the existing finalization contract.
    """
    local_failure = terminal_local_model_failure(decision)
    if local_failure is not None:
        return local_failure
    value = json_object(decision)
    preflight = json_object(value.get("model_executor_preflight"))
    speech = json_object(value.get("model_guided_speech_status"))
    route = json_object(speech.get("llm_route_status"))
    host = json_object(route.get("chatgpt_bridge"))
    synthesis = json_object(value.get("model_guided_synthesis"))
    if not (
        value.get("model_generated") is False
        and value.get("requires_host_model") is True
        and value.get("fallback_classification") == "cannot_answer_directly"
        and preflight.get("executor") == "unavailable"
        and preflight.get("available") is False
        and preflight.get("retry_allowed") is False
        and preflight.get("adapter_id") == "null_model_adapter"
        and preflight.get("provider") == "none"
        and preflight.get("reason") == "external_model_not_configured"
        and speech.get("selected_route") == "null_fallback"
        and speech.get("selected_adapter") == "null_model_adapter"
        and speech.get("reason") == "null_fallback_no_model_guided_speech"
        and speech.get("can_attempt_model_guided_speech") is False
        and speech.get("can_generate_model_guided_speech") is False
        and speech.get("can_complete_model_guided_speech_via_host") is False
        and speech.get("requires_host_model") is False
        and route.get("route_mode") == "auto"
        and route.get("selected_route") == "null_fallback"
        and route.get("paid_route") is False
        and host.get("declared") is False
        and host.get("available") is False
        and synthesis.get("used") is False
        and synthesis.get("provider") == "none"
        and synthesis.get("reason") == "external_model_not_configured"
        and not synthesis.get("host_generation_context")
        and not synthesis.get("adapter_response")
        and not value.get("model_guided_retry_synthesis")
    ):
        return None
    return {
        "provider": "none",
        "adapter_id": "null_model_adapter",
        "selected_route": "null_fallback",
        "error_code": "external_model_not_configured",
        "failure_kind": "executor_unavailable",
        "request_dispatched": False,
        "automatic_retry_allowed": False,
        "host_generation_authorized": False,
    }


def model_failure_projection(failure: dict[str, Any]) -> tuple[str, str]:
    """Use the same diagnostic field and bridge status in both projections."""
    if failure.get("failure_kind") == "executor_unavailable":
        return "model_executor_unavailable", "model_executor_unavailable"
    if failure.get("failure_kind") == "generation_limit":
        return "model_generation_limit", "local_model_output_limit_reached"
    return "model_transport_failure", "local_model_transport_failed"
