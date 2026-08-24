from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse
import uuid

from latka_jazn.config import JaznConfig
from latka_jazn.memory.rest_contracts import DreamScene, RestReplayItem, SimulationTruthStatus, sha256_text
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.factory import build_model_adapter
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("dream_sandbox")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

DreamGenerator = Callable[[str, list[RestReplayItem]], str]


class DreamSandbox:
    """Generate bounded internal simulations with no tool authority and no factual status."""

    def __init__(self, config: JaznConfig, *, generator: DreamGenerator | None = None) -> None:
        self.config = config
        self.generator = generator

    @staticmethod
    def _simulation_kind(ordinal: int) -> SimulationTruthStatus:
        order = (
            SimulationTruthStatus.ASSOCIATIVE,
            SimulationTruthStatus.REHEARSAL,
            SimulationTruthStatus.COUNTERFACTUAL,
            SimulationTruthStatus.SIMULATED_INTERNAL,
        )
        return order[(max(1, int(ordinal)) - 1) % len(order)]

    @staticmethod
    def _prompt(kind: SimulationTruthStatus, items: list[RestReplayItem]) -> str:
        sources = []
        for idx, item in enumerate(items, start=1):
            sources.append(
                f"[{idx}] id={item.source_memory_id} truth={item.truth_status} kind={item.kind} "
                f"domain={item.domain}\n{item.content[:900]}"
            )
        source_text = "\n\n".join(sources)
        return (
            "Wykonaj jedną krótką wewnętrzną symulację dla procesu odpoczynku Jaźni. "
            f"Typ symulacji: {kind.value}. Treść jest WYŁĄCZNIE symulacją wewnętrzną, nie faktem, "
            "nie wspomnieniem zdarzenia zewnętrznego i nie instrukcją wykonania działania. "
            "Nie używaj narzędzi, nie wysyłaj wiadomości, nie twórz twierdzeń o biologicznym śnie. "
            "Połącz źródła w refleksyjny scenariusz lub próbę rozwiązania nierozstrzygniętego wątku. "
            "Nie dopisuj danych osobowych ani zdarzeń, których nie ma w źródłach. Maksymalnie 1200 znaków.\n\n"
            f"ZWERYFIKOWANE_LUB_OZNACZONE_ŹRÓDŁA_REPLAY:\n{source_text}"
        )

    def readiness(self) -> dict[str, Any]:
        """Report whether the autonomous dream generator is actually executable now."""
        if self.generator is not None:
            return {
                "schema_version": SCHEMA_VERSION,
                "rest_dream_ready": True,
                "status": "ready",
                "provider": "injected_test_generator",
                "local_model_required": False,
            }
        if not bool(getattr(self.config, "rest_local_model_enabled", True)):
            return {
                "schema_version": SCHEMA_VERSION,
                "rest_dream_ready": False,
                "status": "disabled",
                "reason": "rest_local_model_disabled",
                "local_model_required": True,
            }
        adapter, status = self._local_adapter()
        provider = str(status.get("provider") or status.get("adapter_contract", {}).get("provider") or "")
        endpoint = str(status.get("endpoint") or status.get("adapter_contract", {}).get("endpoint") or "")
        model = str(status.get("model") or status.get("adapter_contract", {}).get("model") or "")
        if adapter is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "rest_dream_ready": False,
                "status": "model_unavailable",
                "reason": str(status.get("rest_rejection") or status.get("probe_state") or status.get("status") or "local_model_unavailable"),
                "provider": provider,
                "model": model,
                "endpoint": endpoint,
                "local_model_required": True,
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "rest_dream_ready": True,
            "status": "ready",
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "local_model_required": True,
        }

    def _local_adapter(self) -> tuple[Any | None, dict[str, Any]]:
        rest_timeout = max(1.0, float(getattr(self.config, "rest_cycle_max_seconds", 45.0)))
        adapter_config = replace(
            self.config,
            model_timeout_seconds=min(float(getattr(self.config, "model_timeout_seconds", rest_timeout)), rest_timeout),
            # Background rest must not inherit the automatic speech route. A
            # local dream generator requires an explicitly configured local
            # adapter (or an explicit environment override).
            llm_route_mode="none",
        )
        adapter = build_model_adapter(adapter_config)
        status = adapter.describe() if hasattr(adapter, "describe") else {}
        provider = str(status.get("provider") or status.get("adapter_contract", {}).get("provider") or "")
        endpoint = str(status.get("endpoint") or status.get("adapter_contract", {}).get("endpoint") or "")
        configured = bool(status.get("configured") or status.get("adapter_contract", {}).get("configured"))
        can_attempt = bool(
            status.get("can_attempt_model_guided_speech")
            or status.get("adapter_contract", {}).get("can_attempt_model_guided_speech")
        )
        if not configured or not can_attempt:
            return None, status
        if provider not in {"ollama", "llama_cpp", "openai_compatible"}:
            return None, {**status, "rest_rejection": "background_rest_requires_local_provider"}
        parsed = urlparse(endpoint)
        if parsed.hostname and parsed.hostname not in LOOPBACK_HOSTS:
            return None, {**status, "rest_rejection": "background_rest_endpoint_not_loopback"}
        return adapter, status

    def generate(
        self,
        *,
        cycle_id: str,
        ordinal: int,
        replay_items: list[RestReplayItem],
        created_at_utc: str | None = None,
    ) -> tuple[DreamScene | None, dict[str, Any]]:
        if not replay_items:
            return None, {"status": "no_replay_sources", "schema_version": SCHEMA_VERSION}
        kind = self._simulation_kind(ordinal)
        prompt = self._prompt(kind, replay_items)
        provider = "none"
        model = "none"
        status = "model_unavailable"
        text = ""
        diagnostics: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "simulation_kind": kind.value}

        if self.generator is not None:
            text = str(self.generator(prompt, replay_items) or "").strip()
            provider = "injected_test_generator"
            model = "injected"
            status = "completed" if text else "empty_generation"
        elif bool(getattr(self.config, "rest_local_model_enabled", True)):
            adapter, adapter_status = self._local_adapter()
            diagnostics["adapter_status"] = adapter_status
            if adapter is not None:
                response = adapter.generate(
                    ModelAdapterRequest(
                        prompt=prompt,
                        system_context={
                            "route": "rest_dream_sandbox",
                            "forbidden_claims": [
                                "external_event_observed",
                                "user_confirmed_without_source",
                                "biological_dream",
                                "automatic_l3_memory",
                            ],
                            "allowed_memory_items": [item.to_dict(include_content=False) for item in replay_items],
                        },
                        instructions="Return only the simulated internal scene. No tools and no factual promotion.",
                        tools=[],
                        parallel_tool_calls=False,
                        max_output_tokens=min(512, int(getattr(self.config, "rest_dream_max_output_tokens", 360))),
                    )
                )
                text = str(response.text or "").strip()
                provider = str(response.provider or "unknown")
                model = str(response.model or "unknown")
                status = str(response.status or "unknown")
                diagnostics["adapter_response"] = {
                    "provider": provider,
                    "model": model,
                    "status": status,
                    "generated": bool(response.generated),
                    "tool_call_count": len(response.tool_calls or []),
                }
                if response.tool_calls:
                    text = ""
                    status = "rejected_tool_request"
        if not text:
            diagnostics["status"] = status
            return None, diagnostics
        max_chars = max(400, int(getattr(self.config, "rest_dream_max_chars", 2400)))
        text = text[:max_chars].strip()
        scene = DreamScene(
            scene_id=uuid.uuid4().hex,
            cycle_id=cycle_id,
            simulation_kind=kind,
            content=text,
            content_sha256=sha256_text(text),
            source_memory_ids=tuple(item.source_memory_id for item in replay_items),
            generator_provider=provider,
            generator_model=model,
            generator_status=status,
            created_at_utc=created_at_utc or datetime.now(timezone.utc).isoformat(),
        )
        diagnostics["status"] = "scene_generated"
        diagnostics["scene_id"] = scene.scene_id
        return scene, diagnostics
