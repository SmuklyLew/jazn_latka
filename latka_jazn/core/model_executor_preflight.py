from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit


from latka_jazn.core.json_types import json_object


@dataclass(frozen=True, slots=True)
class ModelExecutorPreflight:
    executor: str
    available: bool
    retry_allowed: bool
    adapter_id: str
    provider: str
    model: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _endpoint_location(value: object) -> str:
    """Conservative inference location: a URL, provider name or 'local' label is not proof."""
    raw = str(value or "").strip()
    if not raw:
        return "unknown"
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").strip().lower()
    except ValueError:
        return "unknown"
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return "unknown"
    if host == "localhost" or host.endswith(".localhost") or host == "127.0.0.1" or host == "::1":
        return "loopback"
    # Arbitrary LAN IPs, DNS names and proxies are NOT known to be local.
    return "external_or_unverified"


def _known_external_adapter(adapter_id: str, kind: str, provider: str) -> bool:
    return (
        adapter_id in {"openai_responses_adapter", "siwc_plan_usage_adapter"}
        or kind in {"remote_responses_api", "optional_oauth_plan_usage_stream"}
        or provider == "openai_siwc"
    )


def resolve_model_executor(adapter: Any) -> ModelExecutorPreflight:
    described_status = adapter.describe() if hasattr(adapter, "describe") else {}
    status = json_object(described_status)
    contract = json_object(status.get("adapter_contract"))
    adapter_id = str(status.get("adapter_id") or status.get("name") or contract.get("adapter_id") or "unknown")
    provider = str(status.get("provider") or contract.get("provider") or adapter_id)
    model = str(status.get("model") or status.get("model_name") or contract.get("model_name") or "none")
    kind = str(status.get("kind") or contract.get("kind") or "")
    endpoint = status.get("api_base") or status.get("endpoint") or contract.get("endpoint")

    if adapter_id == "chatgpt_runtime_adapter" or bool(status.get("host_visible_generation_required")):
        return ModelExecutorPreflight(
            executor="host_bridge",
            available=True,
            retry_allowed=False,
            adapter_id=adapter_id,
            provider=provider,
            model=model,
            reason="host_visible_generation_requires_external_handoff",
        )

    can_generate = bool(
        status.get("can_generate_model_guided_speech")
        or contract.get("can_generate_model_guided_speech")
    )
    can_attempt = bool(
        status.get("can_attempt_model_guided_speech")
        or contract.get("can_attempt_model_guided_speech")
    )
    configured = bool(status.get("configured") or contract.get("configured"))
    if configured and (can_generate or can_attempt) and adapter_id not in {"null_model_adapter", "voice_model_adapter", "none"}:
        # Configuration is permission to consider a first attempt, NOT proof
        # that the target endpoint or remote service is reachable.
        location = _endpoint_location(endpoint)
        is_external = _known_external_adapter(adapter_id, kind, provider)
        ambiguous_compatible = kind == "openai_compatible_local_or_external_api"
        if ambiguous_compatible:
            if location == "loopback":
                return ModelExecutorPreflight(
                    executor="local_model", available=True, retry_allowed=True,
                    adapter_id=adapter_id, provider=provider, model=model,
                    reason="configured_loopback_compatible_adapter_unprobed",
                )
            # No implicit export from a backend called 'local' to LAN/Internet.
            return ModelExecutorPreflight(
                executor="unavailable", available=False, retry_allowed=False,
                adapter_id=adapter_id, provider=provider, model=model,
                reason="compatible_endpoint_location_unverified_requires_explicit_authorization",
            )
        if is_external:
            return ModelExecutorPreflight(
                executor="external_model", available=True, retry_allowed=False,
                adapter_id=adapter_id, provider=provider, model=model,
                reason="configured_external_adapter_requires_separate_authorization_and_live_probe",
            )
        if kind == "local_generate_api" and location != "loopback":
            return ModelExecutorPreflight(
                executor="unavailable", available=False, retry_allowed=False,
                adapter_id=adapter_id, provider=provider, model=model,
                reason="local_endpoint_not_loopback_requires_explicit_authorization",
            )
        return ModelExecutorPreflight(
            executor="local_model",
            available=True,
            retry_allowed=True,
            adapter_id=adapter_id,
            provider=provider,
            model=model,
            reason=(
                "configured_local_generative_adapter"
                if can_generate
                else "configured_local_adapter_ready_for_first_attempt"
            ),
        )

    return ModelExecutorPreflight(
        executor="unavailable",
        available=False,
        retry_allowed=False,
        adapter_id=adapter_id,
        provider=provider,
        model=model,
        reason=str(
            status.get("failure_reason")
            or contract.get("failure_reason")
            or "no_configured_generative_executor"
        ),
    )
