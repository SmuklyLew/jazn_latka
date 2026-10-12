from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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


def resolve_model_executor(adapter: Any) -> ModelExecutorPreflight:
    described_status = adapter.describe() if hasattr(adapter, "describe") else {}
    status = json_object(described_status)
    contract = json_object(status.get("adapter_contract"))
    adapter_id = str(status.get("adapter_id") or status.get("name") or contract.get("adapter_id") or "unknown")
    provider = str(status.get("provider") or contract.get("provider") or adapter_id)
    model = str(status.get("model") or status.get("model_name") or contract.get("model_name") or "none")

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
