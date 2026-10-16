from __future__ import annotations

"""Opt-in ChatGPT plan inference; never a substitute for the ChatGPT host bridge.

The host/operator must complete and verify SIWC OAuth before supplying an access
token and scope. No OAuth credentials are persisted by this adapter. A completed
remote Responses stream is only a language-model result, not an accepted Jaźń turn.
"""

import json
import re
from collections.abc import Callable, Iterable, Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapter_contract import AdapterContract, describe_with_contract
from .base import AdapterStatusSnapshot, ModelAdapterRequest, ModelAdapterResponse

SIWC_RESPONSES_URL = "https://api.openai.com/v1/responses"
SIWC_REQUIRED_SCOPE = "chatgpt.tokens.use.direct"
_MODEL_SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$")
_MAX_EVENT_COUNT = 100_000
_MAX_STREAM_BYTES = 8 * 1024 * 1024
_MAX_TEXT_CHARS = 256 * 1024
StreamTransport = Callable[[dict[str, Any], str, float], Iterable[dict[str, Any]]]


def _sse_events(lines: Iterable[bytes]) -> Iterator[dict[str, Any]]:
    """Decode JSON SSE data frames, including multiline frames, without logging."""
    parts: list[str] = []
    size = 0
    for raw in lines:
        size += len(raw)
        if size > _MAX_STREAM_BYTES:
            raise ValueError("siwc_stream_too_large")
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if parts:
                data = "\n".join(parts)
                parts.clear()
                if data == "[DONE]":
                    return
                event = json.loads(data)
                if not isinstance(event, dict):
                    raise ValueError("siwc_non_object_event")
                yield event
            continue
        if line.startswith("data:"):
            parts.append(line[5:].lstrip(" "))
    if parts:
        data = "\n".join(parts)
        if data != "[DONE]":
            event = json.loads(data)
            if not isinstance(event, dict):
                raise ValueError("siwc_non_object_event")
            yield event


def _https_stream(payload: dict[str, Any], token: str, timeout: float) -> Iterator[dict[str, Any]]:
    req = Request(
        SIWC_RESPONSES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    # Exact official HTTPS endpoint; no configurable destination for an OAuth token.
    with urlopen(req, timeout=timeout) as response:
        yield from _sse_events(response)


def _completed_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct
    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "".join(parts)


class SiwcPlanUsageAdapter:
    """Explicit-only OSS/localhost SIWC channel; no implicit paid API fallback."""

    name = "siwc_plan_usage_adapter"

    def __init__(
        self,
        *,
        model: str = "",
        access_token: str = "",
        granted_scopes: str | Iterable[str] = (),
        operator_opt_in: bool = False,
        network_permitted: bool = True,
        timeout_seconds: float = 45.0,
        stream_transport: StreamTransport | None = None,
    ) -> None:
        self.model = str(model or "").strip()
        self._access_token = str(access_token or "")
        if isinstance(granted_scopes, str):
            self._scopes = frozenset(granted_scopes.split())
        else:
            self._scopes = frozenset(str(scope).strip() for scope in granted_scopes)
        self._operator_opt_in = bool(operator_opt_in)
        self._network_permitted = bool(network_permitted)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._transport = stream_transport or _https_stream
        self._last_error: str | None = None
        self._completed = False

    def _failure_reason(self) -> str | None:
        if not self._operator_opt_in:
            return "siwc_explicit_opt_in_required"
        if not self._network_permitted:
            return "siwc_network_permission_missing"
        if not self._access_token:
            return "siwc_oauth_access_token_missing"
        if SIWC_REQUIRED_SCOPE not in self._scopes:
            return "siwc_plan_scope_missing"
        if not _MODEL_SLUG.fullmatch(self.model):
            return "siwc_catalog_model_required"
        return None

    def describe(self) -> dict[str, Any]:
        reason = self._failure_reason()
        configured = reason is None
        contract = AdapterContract(
            adapter_id=self.name,
            provider="openai_siwc",
            kind="optional_oauth_plan_usage_stream",
            available=configured,
            configured=configured,
            model_name=self.model or None,
            endpoint=SIWC_RESPONSES_URL,
            can_generate_model_guided_speech=self._completed,
            can_attempt_model_guided_speech=configured,
            endpoint_reachable=True if self._completed else None,
            probe_state="probed_ok" if self._completed else "not_probed",
            last_probe_error=self._last_error,
            failure_reason=reason,
            requires_api_key=False,
            availability_basis="explicit_siwc_configuration_not_verified_live_oauth",
            truth_boundary=(
                "SIWC requires operator-owned, validated user OAuth and an explicit model "
                "selected from the signed-in account catalog. Configuration alone is not OAuth "
                "proof. Responses output is an untrusted language candidate, never an accepted "
                "Jaźń memory, identity, host turn or finalized visible reply."
            ),
        )
        return describe_with_contract(
            contract=contract,
            legacy={
                "name": self.name,
                "status": "configured_not_probed" if configured else "not_configured",
                "model": self.model or "not_configured",
                "api_base": "https://api.openai.com/v1",
                "requires_openai_api_key": False,
                "requires_siwc_oauth_and_consent": True,
                "token_material_exposed": False,
                "stream": True,
                "store": False,
                "automatic_route_selection": False,
            },
        )

    def _response(self, *, status: str, text: str = "", model: str | None = None,
                  usage: dict[str, Any] | None = None) -> ModelAdapterResponse:
        ready = self._failure_reason() is None
        snapshot = AdapterStatusSnapshot(
            adapter_id=self.name,
            provider="openai_siwc",
            configured=ready,
            endpoint_reachable=True if self._completed else None,
            probe_state="probed_ok" if self._completed else ("not_probed" if ready else "not_configured"),
            last_probe_error=self._last_error,
            can_attempt_model_guided_speech=ready,
            can_generate_model_guided_speech=self._completed,
            validated=self._completed,
            capabilities={"responses_sse": True, "oauth_provider": "external", "store": False},
        )
        return ModelAdapterResponse(
            text=text,
            provider="openai_siwc",
            adapter_id=self.name,
            model=model or self.model or "not_configured",
            status=status,
            generated=status == "completed" and bool(text),
            validated=status == "completed" and bool(text),
            status_snapshot=snapshot,
            endpoint_used=SIWC_RESPONSES_URL if ready else None,
            transport={"provider": "siwc_oauth", "store": False, "stream": True, "retry_safe": False},
            usage=usage,
            truth_boundary=(
                "Completed model inference is not an accepted/finalized Jaźń reply. "
                "Host/runtime truth, source lineage and finalization remain mandatory."
            ),
        )

    def _build_payload(self, request: ModelAdapterRequest) -> dict[str, Any]:
        # Preview does not support tools/search, previous_response_id, metadata,
        # max_output_tokens, prompt_cache_key or explicit system message items.
        if request.tools or request.allowed_tool_names or request.tool_choice is not None:
            raise ValueError("siwc_tools_not_supported_by_this_adapter")
        if request.previous_response_id:
            raise ValueError("siwc_http_previous_response_id_forbidden")
        if request.response_schema:
            raise ValueError("siwc_structured_output_not_implemented")
        if not request.prompt.strip():
            raise ValueError("siwc_empty_prompt")
        context = json.dumps(request.system_context, ensure_ascii=False, sort_keys=True)
        return {
            "model": self.model,
            "instructions": request.instructions or (
                "You are the language backend of Jaźń. Runtime supplies identity, source-aware "
                "context and authorization. Do not invent memories, actions or tools. "
                "Respond naturally in Polish. Never claim accepted Jaźń finalization."
            ),
            "input": [{
                "role": "user",
                "content": "DYNAMICZNY_KONTEKST_TURY_JSON:\n" + context
                + "\n\nAKTUALNA_WIADOMOSC_UZYTKOWNIKA:\n" + request.prompt,
            }],
            "store": False,
            "stream": True,
        }

    def generate(self, request: ModelAdapterRequest) -> ModelAdapterResponse:
        reason = self._failure_reason()
        if reason:
            return self._response(status=reason)
        try:
            payload = self._build_payload(request)
        except (TypeError, ValueError):
            return self._response(status="siwc_request_unsupported")

        chunks: list[str] = []
        text_size = 0
        self._completed = False
        try:
            for index, event in enumerate(self._transport(payload, self._access_token, self.timeout_seconds)):
                if index >= _MAX_EVENT_COUNT:
                    raise ValueError("siwc_event_limit")
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise ValueError("siwc_invalid_delta")
                    text_size += len(delta)
                    if text_size > _MAX_TEXT_CHARS:
                        raise ValueError("siwc_text_too_large")
                    chunks.append(delta)
                elif kind in {"response.failed", "response.incomplete", "error"}:
                    self._last_error = "siwc_response_not_completed"
                    return self._response(status="siwc_response_not_completed")
                elif kind == "response.completed":
                    remote = event.get("response")
                    if not isinstance(remote, dict) or remote.get("status") != "completed":
                        raise ValueError("siwc_invalid_completion")
                    final_text = _completed_text(remote) or "".join(chunks)
                    if len(final_text) > _MAX_TEXT_CHARS:
                        raise ValueError("siwc_text_too_large")
                    if not final_text.strip():
                        self._last_error = "siwc_empty_completion"
                        return self._response(status="siwc_empty_completion")
                    self._completed = True
                    self._last_error = None
                    return self._response(
                        status="completed",
                        text=final_text,
                        model=str(remote.get("model") or self.model),
                        usage=remote.get("usage") if isinstance(remote.get("usage"), dict) else None,
                    )
            self._last_error = "siwc_stream_missing_completion"
            return self._response(status=self._last_error)
        except HTTPError as exc:
            self._last_error = "siwc_http_" + str(exc.code)
        except (OSError, URLError, TimeoutError, ValueError, UnicodeError, json.JSONDecodeError):
            self._last_error = "siwc_stream_transport_error"
        # Do not log exceptions, URLs with tokens, SSE frames, or input context.
        return self._response(status=self._last_error or "siwc_stream_transport_error")


__all__ = ["SiwcPlanUsageAdapter", "SIWC_RESPONSES_URL", "SIWC_REQUIRED_SCOPE"]
