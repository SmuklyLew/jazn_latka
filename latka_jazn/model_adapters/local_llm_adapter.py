from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapter_contract import AdapterContract, describe_with_contract
from .base import AdapterStatusSnapshot, ModelAdapterRequest, ModelAdapterResponse
from latka_jazn.nlp.response_language_guard import assess_response_language, user_explicitly_requested_non_polish



MODEL_CONTEXT_MAX_CHARS_DEFAULT = 24000


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _clip_context_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return str(value)[:1200]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_clip_context_value(item, depth=depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        return {str(key): _clip_context_value(item, depth=depth + 1) for key, item in list(value.items())[:40]}
    return str(value)[:1200]


def _compact_model_context(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _as_dict(value)
    selected_keys = (
        "schema_version", "user_message", "detected_intent", "route", "nlg_plan",
        "operational_thought_frame", "voice_source_contract", "allowed_memory_items",
        "forbidden_claims", "required_truth_boundaries", "output_instructions",
        "token_budget_hint", "dialogue_context", "self_state_runtime", "turn_response_policy",
    )
    compact = {
        key: _clip_context_value(raw.get(key))
        for key in selected_keys
        if raw.get(key) not in (None, "", [], {})
    }
    full_canon = _as_dict(raw.get("full_canon_model_context"))
    if full_canon:
        immutable = _as_dict(full_canon.get("immutable_canon"))
        compact["full_canon_model_context"] = {
            "schema_version": full_canon.get("schema_version"),
            "read_only": full_canon.get("read_only"),
            "immutable_canon_sha256": full_canon.get("immutable_canon_sha256"),
            "voice_source_contract": _clip_context_value(full_canon.get("voice_source_contract")),
            "canon_presence": _clip_context_value(full_canon.get("canon_presence")),
            "immutable_canon": {
                key: _clip_context_value(immutable.get(key))
                for key in ("identity_core", "character_profile", "relation_canon", "memory_truth_boundary", "symbolic_world")
                if immutable.get(key) not in (None, "", [], {})
            },
        }
    try:
        max_chars = max(8000, int(os.environ.get("JAZN_MODEL_CONTEXT_MAX_CHARS", MODEL_CONTEXT_MAX_CHARS_DEFAULT)))
    except (TypeError, ValueError):
        max_chars = MODEL_CONTEXT_MAX_CHARS_DEFAULT
    original_chars = len(json.dumps(raw, ensure_ascii=False, default=str))

    def encoded() -> str:
        return json.dumps(compact, ensure_ascii=False, default=str)

    serialized = encoded()
    for removable in ("operational_thought_frame", "self_state_runtime", "forbidden_claims", "required_truth_boundaries"):
        if len(serialized) <= max_chars:
            break
        compact.pop(removable, None)
        serialized = encoded()
    if len(serialized) > max_chars:
        compact["allowed_memory_items"] = list(compact.get("allowed_memory_items") or [])[:3]
        compact["context_budget_notice"] = "model context reduced to fit JAZN_MODEL_CONTEXT_MAX_CHARS"
        serialized = encoded()
    if len(serialized) > max_chars:
        compact = {
            key: compact.get(key)
            for key in ("user_message", "detected_intent", "route", "nlg_plan", "dialogue_context", "output_instructions", "full_canon_model_context")
            if compact.get(key) not in (None, "", [], {})
        }
        serialized = encoded()
    if len(serialized) > max_chars:
        canon = _as_dict(compact.get("full_canon_model_context"))
        compact["full_canon_model_context"] = {
            key: canon.get(key)
            for key in ("schema_version", "read_only", "immutable_canon_sha256", "voice_source_contract", "canon_presence")
            if canon.get(key) not in (None, "", [], {})
        }
        serialized = encoded()
    if len(serialized) > max_chars:
        compact = {
            "user_message": str(compact.get("user_message") or "")[:2000],
            "detected_intent": compact.get("detected_intent"),
            "route": compact.get("route"),
            "dialogue_context": _clip_context_value(compact.get("dialogue_context") or {}),
            "output_instructions": list(compact.get("output_instructions") or [])[:8],
            "full_canon_model_context": {
                "immutable_canon_sha256": _as_dict(compact.get("full_canon_model_context")).get("immutable_canon_sha256"),
                "canon_presence": _as_dict(compact.get("full_canon_model_context")).get("canon_presence"),
            },
            "context_budget_notice": "hard-reduced to fit JAZN_MODEL_CONTEXT_MAX_CHARS",
        }
        serialized = encoded()
    if len(serialized) > max_chars:
        compact["dialogue_context"] = {}
        compact["output_instructions"] = []
        serialized = encoded()
    if len(serialized) > max_chars:
        compact = {
            "user_message": str(compact.get("user_message") or "")[:1000],
            "detected_intent": str(compact.get("detected_intent") or "")[:120],
            "route": str(compact.get("route") or "")[:120],
            "full_canon_model_context": {
                "immutable_canon_sha256": _as_dict(compact.get("full_canon_model_context")).get("immutable_canon_sha256"),
            },
            "context_budget_notice": "minimal context after hard budget enforcement",
        }
        serialized = encoded()
    return compact, {
        "original_context_chars": original_chars,
        "compacted_context_chars": len(serialized),
        "context_max_chars": max_chars,
        "context_compacted": original_chars > len(serialized),
    }


class LocalLlmAdapter:
    name = "local_llm_adapter"

    def __init__(
        self,
        *,
        model: str = "",
        api_base: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 45.0,
        max_output_tokens: int = 800,
        root: object | None = None,
    ) -> None:
        self.model = str(model or "").strip()
        self.api_base = str(api_base or "http://127.0.0.1:11434").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._endpoint_reachable: bool | None = None
        self._probe_state = "not_probed" if self.model else "not_configured"
        self._last_probe_error: str | None = None
        self._last_generation_succeeded = False
        self._last_generation: dict[str, Any] = {}

    def describe(self) -> dict:
        configured = bool(self.model)
        contract = AdapterContract(
            adapter_id=self.name,
            provider="ollama",
            kind="local_generate_api",
            available=configured,
            model_name=self.model or None,
            endpoint=self.api_base,
            can_generate_model_guided_speech=bool(configured and self._last_generation_succeeded),
            configured=configured,
            endpoint_reachable=self._endpoint_reachable,
            probe_state=self._probe_state,
            last_probe_error=self._last_probe_error,
            can_attempt_model_guided_speech=configured,
            failure_reason=None if configured else "local_model_name_missing",
            truth_boundary=(
                "Ollama jest lokalnym backendem językowym. Dostępność oznacza kompletną konfigurację, "
                "nie wynik live probe; Jaźń zachowuje tożsamość, pamięć, routing i walidację."
            ),
        )
        return describe_with_contract(
            contract=contract,
            legacy={
                "name": self.name,
                "status": "configured" if configured else "not_configured",
                "model": self.model or "not_configured",
                "api_base": self.api_base,
                "last_generation": dict(self._last_generation),
            },
        )

    def probe(self) -> dict:
        if not self.model:
            self._endpoint_reachable = None
            self._probe_state = "not_configured"
            self._last_probe_error = "local_model_name_missing"
            return self.describe()
        try:
            req = Request(f"{self.api_base}/api/tags", method="GET")
            with urlopen(req, timeout=min(self.timeout_seconds, 8.0)) as response:
                data = json.loads(response.read().decode("utf-8"))
            models = data.get("models") if isinstance(data, dict) else []
            names = sorted({
                str(item.get("name") or item.get("model") or "").strip()
                for item in (models if isinstance(models, list) else [])
                if isinstance(item, dict)
            } - {""})
            installed = self.model in names or any(name.split(":", 1)[0] == self.model.split(":", 1)[0] for name in names)
            self._endpoint_reachable = True
            self._probe_state = "probed_ok" if installed else "model_missing"
            self._last_probe_error = None if installed else "configured_model_not_installed"
            payload = self.describe()
            payload.update({
                "probe_ok": installed,
                "configured_model_installed": installed,
                "installed_models": names,
                "probe_endpoint": "/api/tags",
            })
            return payload
        except HTTPError as exc:
            self._endpoint_reachable = False
            self._probe_state = "probed_fail"
            self._last_probe_error = f"http_error_{exc.code}"
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            self._endpoint_reachable = False
            self._probe_state = "probed_fail"
            self._last_probe_error = f"{type(exc).__name__}: local_provider_unavailable"
        payload = self.describe()
        payload.update({
            "probe_ok": False,
            "configured_model_installed": False,
            "installed_models": [],
            "probe_endpoint": "/api/tags",
        })
        return payload

    def _system_text(self, request: ModelAdapterRequest, *, strict_retry: bool = False, model_context: dict[str, Any] | None = None) -> str:
        text = (
            "Jesteś wyłącznie językową warstwą wykonawczą Jaźni Łatki. "
            "Odpowiadaj naturalnie po polsku, bez listy przypadkowych dalszych opcji. "
            "Nie wymyślaj pamięci ani faktów poza przekazanym kontekstem. "
            "Nie wspominaj o ChatGPT ani o zewnętrznym hoście, chyba że użytkownik pyta o nie wprost. "
            "Odpowiedz bezpośrednio na ostatnią wiadomość użytkownika; gdy dialogue_context zawiera poprzednią parę, uwzględnij ją. "
            "Nie kończ generycznym pytaniem w rodzaju „W czym mogę pomóc?”, jeśli użytkownik już podał temat. "
            f"Bieżący backend językowy: provider=ollama, adapter={self.name}, model={self.model}, endpoint={self.api_base}. "
            "Gdy użytkownik pyta o dostępny model lub adapter, podaj dokładnie te fakty."
        )
        if strict_retry:
            text += " POPRZEDNI KANDYDAT MIAŁ ZŁY JĘZYK. Odpowiedz wyłącznie po polsku i bez metakomentarza."
        return text + "\n\nKONTEKST_JAZNI_JSON:\n" + json.dumps(model_context if model_context is not None else request.system_context or {}, ensure_ascii=False)

    @staticmethod
    def _timed_out(exc: BaseException) -> bool:
        reason = getattr(exc, "reason", None)
        return bool(
            isinstance(exc, TimeoutError)
            or isinstance(reason, TimeoutError)
            or "timed out" in str(exc).casefold()
            or "timeout" in str(exc).casefold()
        )

    def _chat_once(
        self,
        request: ModelAdapterRequest,
        *,
        strict_retry: bool,
    ) -> tuple[str, dict[str, Any], BaseException | None]:
        model_context, context_diagnostics = _compact_model_context(request.system_context or {})
        system_text = self._system_text(request, strict_retry=strict_retry, model_context=model_context)
        dialogue_context = _as_dict(model_context.get("dialogue_context"))
        messages = [{"role": "system", "content": system_text}]
        previous_user = str(dialogue_context.get("previous_user_text") or "").strip()
        previous_assistant = str(dialogue_context.get("previous_assistant_text") or "").strip()
        if previous_user:
            messages.append({"role": "user", "content": previous_user})
        if previous_assistant:
            messages.append({"role": "assistant", "content": previous_assistant})
        messages.append({"role": "user", "content": request.prompt})
        try:
            num_ctx = max(4096, int(os.environ.get("JAZN_OLLAMA_NUM_CTX", "8192")))
        except (TypeError, ValueError):
            num_ctx = 8192
        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": "5m",
            "messages": messages,
            "options": {"num_predict": self.max_output_tokens, "num_ctx": num_ctx},
        }
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        metadata: dict[str, Any] = {
            "requested_model": self.model,
            "strict_retry": strict_retry,
            "timeout_seconds": self.timeout_seconds,
            "system_prompt_chars": len(system_text),
            "user_prompt_chars": len(request.prompt),
            "message_count": len(messages),
            "ollama_num_ctx": num_ctx,
            "request_bytes": len(encoded),
            **context_diagnostics,
        }
        req = Request(
            f"{self.api_base}/api/chat",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = perf_counter()
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            text = str(message.get("content") or data.get("response") or "").strip()
            metadata.update(
                {
                    "status": "completed",
                    "actual_model": str(data.get("model") or self.model),
                    "done": data.get("done"),
                    "done_reason": data.get("done_reason"),
                    "total_duration": data.get("total_duration"),
                    "load_duration": data.get("load_duration"),
                    "prompt_eval_duration": data.get("prompt_eval_duration"),
                    "eval_duration": data.get("eval_duration"),
                    "prompt_eval_count": data.get("prompt_eval_count"),
                    "eval_count": data.get("eval_count"),
                    "timed_out": False,
                }
            )
            return text, metadata, None
        except HTTPError as exc:
            metadata.update(
                {
                    "status": f"http_error_{exc.code}",
                    "error_code": f"http_error_{exc.code}",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "timed_out": False,
                }
            )
            return "", metadata, exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            timed_out = self._timed_out(exc)
            metadata.update(
                {
                    "status": (
                        "timeout"
                        if timed_out
                        else "local_provider_unavailable"
                    ),
                    "error_code": (
                        "model_request_timeout"
                        if timed_out
                        else "local_provider_unavailable"
                    ),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "timed_out": timed_out,
                }
            )
            return "", metadata, exc
        finally:
            metadata["wall_clock_duration_ms"] = round(
                max(0.0, perf_counter() - started) * 1000.0,
                3,
            )

    def _failure_response(
        self,
        *,
        error: BaseException,
        attempts: list[dict[str, Any]],
    ) -> ModelAdapterResponse:
        last = attempts[-1] if attempts else {}
        if isinstance(error, HTTPError):
            status = f"http_error_{error.code}"
            self._last_probe_error = status
        else:
            status = str(last.get("status") or "local_provider_unavailable")
            self._last_probe_error = str(
                last.get("error_code") or "local_provider_unavailable"
            )
        self._endpoint_reachable = False
        self._probe_state = "probed_fail"
        self._last_generation_succeeded = False
        self._last_generation = {
            "status": status,
            "error_type": type(error).__name__,
            "attempt_count": len(attempts),
            "timed_out": bool(last.get("timed_out")),
            "wall_clock_duration_ms": last.get("wall_clock_duration_ms"),
        }
        return ModelAdapterResponse(
            text="",
            provider="ollama",
            model=self.model,
            status=status,
            adapter_id=self.name,
            endpoint_used="/api/chat",
            status_snapshot=self._status_snapshot(),
            transport={
                "attempts": attempts,
                "retry_count": max(0, len(attempts) - 1),
                "error_type": type(error).__name__,
                "error_code": last.get("error_code"),
            },
        )

    def generate(self, request: ModelAdapterRequest) -> ModelAdapterResponse:
        if not self.model:
            return ModelAdapterResponse(
                text="",
                provider="ollama",
                model="not_configured",
                status="not_configured",
                adapter_id=self.name,
            )
        allow_non_polish = bool(
            request.metadata.get("allow_non_polish")
        ) or user_explicitly_requested_non_polish(request.prompt)
        attempts: list[dict[str, Any]] = []

        text, metadata, error = self._chat_once(
            request,
            strict_retry=False,
        )
        attempts.append(metadata)
        if error is not None:
            return self._failure_response(error=error, attempts=attempts)

        assessment = assess_response_language(text)
        metadata["language_guard"] = assessment.to_dict()
        if text and not allow_non_polish and not assessment.accepted_for_polish:
            text, metadata, error = self._chat_once(
                request,
                strict_retry=True,
            )
            attempts.append(metadata)
            if error is not None:
                return self._failure_response(error=error, attempts=attempts)
            assessment = assess_response_language(text)
            metadata["language_guard"] = assessment.to_dict()

        actual_model = str(
            (attempts[-1] if attempts else {}).get("actual_model")
            or self.model
        )
        accepted = bool(text) and (
            allow_non_polish or assessment.accepted_for_polish
        )
        self._last_generation = {
            "status": (
                "completed"
                if accepted
                else ("language_mismatch" if text else "empty_output")
            ),
            "actual_model": actual_model,
            "attempt_count": len(attempts),
            "done_reason": (
                attempts[-1] if attempts else {}
            ).get("done_reason"),
            "language": assessment.language,
            "wall_clock_duration_ms": sum(
                float(item.get("wall_clock_duration_ms") or 0.0)
                for item in attempts
            ),
        }
        if accepted:
            self._endpoint_reachable = True
            self._probe_state = "probed_ok"
            self._last_generation_succeeded = True
            self._last_probe_error = None
        else:
            self._last_generation_succeeded = False
            self._last_probe_error = (
                "response_language_mismatch"
                if text
                else "empty_output"
            )
        return ModelAdapterResponse(
            text=text if accepted else "",
            provider="ollama",
            model=actual_model,
            status=(
                "completed"
                if accepted
                else ("language_mismatch" if text else "empty_output")
            ),
            adapter_id=self.name,
            endpoint_used="/api/chat",
            status_snapshot=self._status_snapshot(),
            transport={
                "attempts": attempts,
                "retry_count": max(0, len(attempts) - 1),
                "language_guard_enforced": not allow_non_polish,
            },
        )

    def _status_snapshot(self) -> AdapterStatusSnapshot:
        configured = bool(self.model)
        return AdapterStatusSnapshot(
            adapter_id=self.name,
            provider="ollama",
            configured=configured,
            endpoint_reachable=self._endpoint_reachable,
            probe_state=self._probe_state if configured else "not_configured",
            last_probe_error=self._last_probe_error,
            can_attempt_model_guided_speech=configured,
            can_generate_model_guided_speech=bool(configured and self._last_generation_succeeded),
            capabilities={"last_generation": dict(self._last_generation)},
        )
