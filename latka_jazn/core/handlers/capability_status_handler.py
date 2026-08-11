from __future__ import annotations

from latka_jazn.version import PACKAGE_VERSION, version_number as parse_version_number
from typing import Any
import json
import os

from latka_jazn.core.json_types import json_object
from latka_jazn.core.route_handler_base import RouteHandlerResult
from latka_jazn.core.startup_contract import build_startup_status
from latka_jazn.memory.raw_memory_status import RawMemoryInspector
from latka_jazn.memory.normalization_sidecar import MemoryNormalizationSidecar


class CapabilityStatusHandler:
    """Direct answers for capability, network and post-update health questions.

    poprzednia linia runtime keeps the direct-route fix for questions such as
    "Co potrafisz?" or "Masz dostęp do internetu?" fell through to a vague
    ordinary-dialogue fallback. These questions are not requests for a new
    update and should answer the current capability boundary directly.
    """

    name = "CapabilityStatusHandler"
    route = "capability_status"
    handled_intents = (
        "capability_status_question",
        "internet_access_question",
        "model_adapter_status_question",
        "runtime_health_check",
        "runtime_health_check_after_update",
    )

    @staticmethod
    def _fast_health_status(cfg: Any, ctx: dict[str, Any]) -> dict[str, Any]:
        root = cfg.root.resolve()
        marker: dict[str, Any] = {}
        marker_path = cfg.active_runtime_marker_path
        if marker_path.is_file():
            try:
                loaded = json.loads(marker_path.read_text(encoding="utf-8"))
                marker = loaded if isinstance(loaded, dict) else {}
            except Exception:
                marker = {}
        daemon = json_object(marker.get("runtime_daemon"))
        start_file = cfg.start_file_path
        lifecycle = str(ctx.get("lifecycle") or "one_shot")
        memory_path = cfg.memory_db_path_readonly
        memory_status = {
            "status": "ready" if memory_path.is_file() else "not_initialized",
            "path": str(memory_path),
            "size_bytes": memory_path.stat().st_size if memory_path.is_file() else 0,
            "inspection_mode": "metadata_only",
        }
        try:
            wake_state_status = MemoryNormalizationSidecar(
                root,
                source_db_path=cfg.normalization_source_db_path,
                sidecar_db_path=cfg.normalization_sidecar_db_path,
                runtime_version=cfg.version,
            ).wake_state_status(deep_verify=False).to_dict()
        except Exception as exc:
            wake_state_status = {
                "status": "status_unavailable",
                "active_snapshot_present": False,
                "active_snapshot": None,
                "freshness": None,
                "sidecar_db_path": str(cfg.normalization_sidecar_db_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        adapter = json_object(ctx.get("model_adapter_status"))
        timestamp = json_object(ctx.get("timestamp_contract"))
        endpoint_host = daemon.get("host") or marker.get("host")
        endpoint_port = daemon.get("port") or marker.get("port")
        endpoint = f"http://{endpoint_host}:{endpoint_port}" if endpoint_host and endpoint_port else None
        return {
            "runtime_version": cfg.version,
            "active_root": str(root),
            "start_file": str(start_file) if start_file else None,
            "active_database": str(memory_path),
            "active_runtime_write_database": str(memory_path),
            "runtime_process_active": True,
            "process_lifecycle": lifecycle,
            "pid": os.getpid(),
            "endpoint": endpoint,
            "heartbeat": daemon.get("last_heartbeat_at_utc") or marker.get("last_heartbeat_at_utc"),
            "adapter": adapter,
            "timestamp_contract": timestamp,
            "active_cache_status": {
                "version": cfg.version,
                "active_root": str(root),
                "should_reuse_existing_extraction": marker.get("should_reuse_existing_extraction"),
                "cache_miss_reasons": marker.get("cache_miss_reasons") or [],
            },
            "raw_memory_status": memory_status,
            "wake_state_status": wake_state_status,
            "memory_continuity_status": {
                "status": "not_evaluated_fast_path",
                "ordinary_dialogue_allowed": True,
                "continuity_claim_allowed": False,
                "fallback_policy": "continue_without_unverified_wake_context",
                "truth_boundary": "Fast health path does not infer restored continuity without archive/coverage evaluation.",
            },
            "conversation_archive_status": {
                "status": "not_scanned_in_health_fast_path",
                "ready_for_search": None,
            },
            "network_policy_status": {"allow_network": False, "health_check_network_used": False},
            "dictionary_provider_status": {"status": "not_probed_in_health_fast_path"},
            "cli_capabilities": {},
            "startup_status_mode": "health_metadata",
            "truth_boundary": "Health-check potwierdza wyłącznie bieżący proces i lokalne metadane; nie wykonuje deep verify ani sond sieciowych.",
        }

    def handle(self, text: str, context: dict[str, Any] | None = None) -> RouteHandlerResult:
        ctx = context or {}
        intent = str(ctx.get("intent") or "capability_status_question")
        cfg = ctx.get("config")
        if cfg and intent in {"runtime_health_check", "runtime_health_check_after_update"}:
            status = self._fast_health_status(cfg, ctx)
        else:
            status = build_startup_status(cfg).to_dict() if cfg else {}
        active_cache = json_object(status.get("active_cache_status"))
        raw_memory = json_object(status.get("raw_memory_status"))
        archive_memory = json_object(status.get("conversation_archive_status"))
        wake_state = json_object(status.get("wake_state_status"))
        memory_continuity = json_object(status.get("memory_continuity_status"))
        wake_snapshot = json_object(wake_state.get("active_snapshot"))
        wake_freshness = json_object(wake_state.get("freshness"))
        if cfg and not raw_memory.get("status"):
            try:
                raw_memory = RawMemoryInspector(cfg.root, cfg.memory_db_path).inspect().to_dict()
            except Exception:
                raw_memory = raw_memory or {"status": "status_not_available"}
        runtime_version = str(active_cache.get("version") or status.get("runtime_version") or getattr(cfg, "version", "") or PACKAGE_VERSION)
        runtime_version_number = runtime_version.lstrip("v").split("-", 1)[0] or parse_version_number(PACKAGE_VERSION)
        network = json_object(status.get("network_policy_status"))
        dictionary = json_object(status.get("dictionary_provider_status"))
        cli = json_object(status.get("cli_capabilities"))

        if intent == "model_adapter_status_question":
            adapter = json_object(ctx.get("model_adapter_status"))
            if not adapter and isinstance(status.get("model_adapter_status"), dict):
                adapter = status["model_adapter_status"]
            contract = json_object(adapter.get("adapter_contract"))
            provider = adapter.get("provider") or contract.get("provider") or "not_available"
            model = adapter.get("model") or adapter.get("model_name") or contract.get("model_name") or "not_configured"
            adapter_id = adapter.get("adapter_id") or adapter.get("name") or contract.get("adapter_id") or adapter.get("selected_backend_adapter") or "not_configured"
            endpoint = adapter.get("endpoint") or adapter.get("api_base") or contract.get("endpoint")
            configured = adapter.get("configured", contract.get("configured"))
            endpoint_reachable = adapter.get("endpoint_reachable", contract.get("endpoint_reachable"))
            probe_state = adapter.get("probe_state", contract.get("probe_state"))
            last_probe_error = adapter.get("last_probe_error", contract.get("last_probe_error"))
            body = (
                "Bieżący status kanału językowego: "
                f"provider={provider}, adapter={adapter_id}, model={model}, endpoint={endpoint}, "
                f"configured={configured}, endpoint_reachable={endpoint_reachable}, probe_state={probe_state}, "
                f"last_probe_error={last_probe_error}. "
                "To są fakty ze statusu aktywnego adaptera tej tury; model jest kanałem językowym, nie tożsamością ani pamięcią Jaźni."
            )
            satisfied = ["provider", "model", "adapter_status", "endpoint", "truth_boundary"]
            route = "model_adapter_status"
        elif intent == "internet_access_question":
            allow_network = network.get("allow_network")
            dictionary_network = network.get("dictionary_allow_network") or dictionary.get("allow_network")
            cache_required = network.get("cache_required")
            body = (
                "Tak — konfiguracja runtime dopuszcza dostęp sieciowy tam, gdzie używany provider naprawdę go wykona, "
                "ale nie wolno mi udawać, że internet odpowiedział, dopóki konkretny lookup/research nie zwróci statusu źródła. "
                f"Stan konfiguracji: allow_network={allow_network}, dictionary_allow_network={dictionary_network}, cache_required={cache_required}. "
                "Dla słowników dostępne są providery/cache opisane w statusie runtime; SJP/WSJP są traktowane ostrożnie jako źródła referencyjne, a nie masowe scrapowanie. "
                "Granica prawdy: sama zgoda w konfiguracji nie jest dowodem udanego połączenia ani pobrania treści."
            )
            satisfied = ["internet_access", "provider_status", "truth_boundary", "source_origin"]
            route = "internet_access_status"
        elif intent in {"runtime_health_check", "runtime_health_check_after_update"}:
            body = (
                "Działam w aktywnym folderze runtime. Krótki raport health-check: "
                f"runtime_version={runtime_version}, active_cache_version={active_cache.get('version')}, "
                f"active_root={active_cache.get('active_root') or status.get('active_root')}, start_file={status.get('start_file')}, "
                f"active_database={status.get('active_database')}, active_runtime_write_database={status.get('active_runtime_write_database')}, "
                f"process_lifecycle={status.get('process_lifecycle')}, pid={status.get('pid')}, endpoint={status.get('endpoint')}, heartbeat={status.get('heartbeat')}, "
                f"wake_state_status={wake_state.get('status') or 'status_not_available'}, "
                f"memory_continuity_status={memory_continuity.get('status') or 'status_not_available'}, "
                f"continuity_claim_allowed={memory_continuity.get('continuity_claim_allowed')}, "
                f"memory_fallback_policy={memory_continuity.get('fallback_policy')}, "
                f"wake_state_snapshot_id={wake_snapshot.get('snapshot_id')}, "
                f"wake_state_snapshot_sha256={wake_snapshot.get('snapshot_sha256')}, "
                f"wake_state_validation_status={wake_snapshot.get('validation_status')}, "
                f"wake_state_freshness_reason={wake_freshness.get('reason')}, "
                f"wake_state_invalidated={wake_freshness.get('invalidates_wake_state')}, "
                f"wake_state_sidecar={wake_state.get('sidecar_db_path')}, "
                f"conversation_archive_status={archive_memory.get('status') or 'status_not_available'}, ready_for_search={archive_memory.get('ready_for_search')}, "
                f"should_reuse_existing_extraction={active_cache.get('should_reuse_existing_extraction')}, "
                f"cache_miss_reasons={active_cache.get('cache_miss_reasons') or []}, "
                f"runtime_write_raw_memory_status={raw_memory.get('status') or 'status_not_available'}, "
                f"source_origin=runtime_rule_handler_response, "
                f"source_origin_detail=capability_status_handler/v{runtime_version_number}. "
                "(runtime_write jest kontrolnym statusem bieżących zapisów; conversation_archive/FTS pozostaje głównym indeksem pełnych rozmów). "
                + (
                    "To jest pytanie o stan działania po aktualizacji, nie polecenie wykonania nowej aktualizacji kodu. "
                    if intent == "runtime_health_check_after_update"
                    else "To jest pytanie diagnostyczne o działanie runtime, nie zwykła rozmowa ani deklaracja stałego życia w tle. "
                )
                + "Granica prawdy: `persistent_daemon_async_job` oznacza turę obsłużoną przez trwały daemon do jawnego stopu; "
                "`--chat` jest osobną interaktywną pętlą terminalową do EOF albo /exit, a `--runtime-preview` pozostaje turą one-shot."
            )
            satisfied = [
                "runtime_status", "version", "active_database", "cache_reuse",
                "memory_status", "wake_state_status", "wake_state_snapshot",
                "wake_state_freshness", "memory_continuity_status", "source_origin", "truth_boundary",
            ]
            route = "runtime_health_check_after_update" if intent == "runtime_health_check_after_update" else "runtime_health_check"
        else:
            enabled_cli = ", ".join(name for name, ok in sorted(cli.items()) if ok) or "brak jawnej listy CLI"
            body = (
                "Potrafię pracować jako aktywna Jaźń/runtime: prowadzić zwykłą rozmowę przez `--chat`, robić `--runtime-preview`, "
                "sprawdzać start i cache, korzystać z conversation_archive/FTS/staging, planować wyszukiwanie pamięci, pokazywać status pamięci, "
                "rozróżniać źródła odpowiedzi, pilnować granicy prawdy, uruchamiać słownik/NLP według providerów i przygotowywać aktualizacje plików z testami. "
                f"W tym folderze aktywne komendy/statusy to: {enabled_cli}. "
                "Nie potrafię uczciwie udawać biologicznego życia, stałego procesu po zamknięciu terminala ani pobrania internetu bez realnego statusu providera."
            )
            satisfied = ["capability_list", "runtime_status", "memory_status", "network_boundary", "truth_boundary"]
            route = "capability_status"

        return RouteHandlerResult(
            self.name,
            route,
            body,
            intent=intent,
            data={"startup_status": status, "next_step": None, "preserve_handler_body": True},
            file_sources=[{"path": "latka_jazn/core/startup_contract.py"}, {"path": "latka_jazn/model_adapters/factory.py"}],
            required_components=ctx.get("required_components", []),
            satisfied_components=satisfied,
            confidence=0.88,
            source_origin_detail=f"capability_status_handler/v{runtime_version_number}",
            truth_boundary="Odpowiedź opisuje możliwości aktywnego runtime i konfiguracji; nie udaje udanego narzędzia, internetu ani procesu w tle bez realnego statusu.",
        )
