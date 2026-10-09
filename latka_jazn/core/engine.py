from __future__ import annotations
from latka_jazn.version import PACKAGE_VERSION
from dataclasses import asdict
from pathlib import Path
from typing import Any
import hashlib
import json, re, time, uuid
from latka_jazn.config import JaznConfig
from latka_jazn.core.engine_construction import EngineRuntimeServices, load_runtime_state
from latka_jazn.core.clock import WarsawClock
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.core.canon import CanonSourceContract, IdentityCanon, default_character_profile
from latka_jazn.core.json_types import json_object
from latka_jazn.core.emotions import AffectiveState
from latka_jazn.core.emotion_layers import EmotionalLayerModel
from latka_jazn.core.temporal_awareness import TemporalAwareness
from latka_jazn.core.identity_guard import IdentityPerspectiveGuard
from latka_jazn.core.memory_importance import MemoryImportanceAssessor
from latka_jazn.core.neuropsychology_map import NeuropsychologyMapper
from latka_jazn.core.identity_dynamics import IdentityDynamics
from latka_jazn.core.neurocognitive_loop import NeurocognitiveLoop
from latka_jazn.core.logical_reasoning import LogicalReasoner
from latka_jazn.core.operational_awareness import OperationalAwarenessModel
from latka_jazn.core.operational_work_loop import OperationalWorkLoop
from latka_jazn.core.polish_understanding import PolishUnderstandingEngine
from latka_jazn.core.lexical_semantics import LexicalSemanticUnderstanding
from latka_jazn.nlp.polish_lemmatizer import PolishLemmatizationEngine
from latka_jazn.nlp_reasoning.pipeline import PolishReasoningPipeline
from latka_jazn.core.cognitive_packets import CognitivePacketLibrary
from latka_jazn.core.affective_granularity import AffectiveGranularityModel
from latka_jazn.core.cognitive_topics import CognitiveTopicExpansion
from latka_jazn.core.runtime_operating_model import CognitiveRuntimeOperatingModel
from latka_jazn.core.conversation import ConversationResponder
from latka_jazn.core.quiet_rest import QuietRest
from latka_jazn.core.recognition import Handshake
from latka_jazn.core.renderer import ResponseRenderer
from latka_jazn.core.self_architecture import SelfArchitecture
from latka_jazn.core.birth_manifest import BirthSourceManifest
from latka_jazn.core.truth_boundary import TruthBoundary
from latka_jazn.core.uncertainty_model import UncertaintyModel
from latka_jazn.core.source_origin import SourceOriginAnalyzer
from latka_jazn.core.self_state_runtime import SelfStateRuntime
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.core.final_response_contract import FinalResponseContract
from latka_jazn.core.visible_integrity import evaluate_origin_truth
from latka_jazn.core.startup_contract import build_startup_status, build_startup_summary, build_truth_boundary_check
from latka_jazn.core.continuity_badge import ContinuityBadgePolicy
from latka_jazn.core.epistemic_claim_guard import EpistemicClaimGuard
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger, epistemic_ledger_path
from latka_jazn.core.epistemic_evidence import EpistemicEvidenceCollector
from latka_jazn.core.affect_mixer import AffectMixer
from latka_jazn.core.dialogue_state import DialogueStateTracker
from latka_jazn.memory.importer import MemoryImporter
from latka_jazn.memory.layered_memory import LayeredMemory
from latka_jazn.memory.consolidation import MemoryConsolidationModel
from latka_jazn.memory.store import MemoryStore
from latka_jazn.memory.runtime_persistence import RuntimeMemoryWriter, RuntimePersistenceResult
from latka_jazn.memory.event_ledger import RuntimeEventLedger
from latka_jazn.memory.session_continuity import SessionContinuityManager
from latka_jazn.memory.chat_html_importer import search_raw_chat_html_snippets
from latka_jazn.memory.conversation_archive import ConversationArchiveStore
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.core.runtime_status import build_runtime_status
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.free_dialogue_synthesizer import FreeDialogueSynthesizer
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.memory_intent_contract import MEMORY_CONTENT_INTENTS, analyze_memory_intent
from latka_jazn.core.memory_use_gate import MemoryUseGate
from latka_jazn.core.memory_recall_observability import build_memory_recall_observability
from latka_jazn.core.signal_matching import NeurologicalSignalRouter, any_marker_present
from latka_jazn.core.project_index import ProjectStartupIndexer
from latka_jazn.nlp.topic_mismatch_guard import TopicMismatchGuard
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.turn_context_resolver import TurnContextResolver
from latka_jazn.core.dialogue_task_state import DialogueTaskStateResolver
from latka_jazn.core.operational_learning_memory import OperationalLearningMemory
from latka_jazn.core.source_origin_ledger import SourceOriginLedger
from latka_jazn.core.template_registry import TemplateRegistry
from latka_jazn.core.response_generation_mode import build_runtime_provenance
from latka_jazn.core.runtime_response_synthesizer import RuntimeResponseSynthesizer
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.core.model_executor_preflight import resolve_model_executor
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.turn_checkpoint_writer import TurnCheckpointWriter
from latka_jazn.core.runtime_visible_answer_comparator import RuntimeVisibleAnswerComparator
from latka_jazn.core.turn_response_policy import TurnResponsePolicy
from latka_jazn.core.turn_logic_auditor import TurnLogicAuditor
from latka_jazn.core.reasoning_controller import ReasoningController
from latka_jazn.core.turn_route_trace import TurnRouteTrace
from latka_jazn.core.source_text_preservation_contract import SourceTextPreservationContract
from latka_jazn.core.runtime_turn_contract import RuntimeTurnContract
from latka_jazn.nlp.external_dictionary_adapter import ExternalDictionaryAdapter
from latka_jazn.core.module_responsibility_map import ModuleResponsibilityMap
from latka_jazn.memory.requirements_ledger import RequirementsLedger
from latka_jazn.adapters.chatgpt_adapter import ChatGPTAdapter
from latka_jazn.tools.package_export import export_package
from latka_jazn.integrations.github_repository_plan import build_github_repository_plan, write_github_repository_plan
from latka_jazn.core.voice_source_contract import VoiceSourceContract
from latka_jazn.core.runtime_rendering_modes import RuntimeRenderingModeSelector
from latka_jazn.core.external_research_contract import ExternalResearchContract
from latka_jazn.core.tool_use_policy import ToolUsePolicy
from latka_jazn.core.tool_execution_controller import ToolExecutionController
from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
from latka_jazn.core.knowledge_fabric import KnowledgeFabric
from latka_jazn.nlp.lexical_intelligence import LexicalIntelligenceEngine
from latka_jazn.core.homeostasis import HomeostasisInput
from latka_jazn.core.untrusted_source_guard import UntrustedSourceGuard
from latka_jazn.memory.memory_recall_contract import MemoryRecallContractBuilder
from latka_jazn.memory.raw_chat_importer import RawChatImporter
from latka_jazn.model_adapters.factory import build_model_adapter
from latka_jazn.core.model_guided_speech_runtime import build_speech_adapter_for_turn
from latka_jazn.core.self_knowledge_contract import build_self_knowledge_summary
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.blind_route_detector import BlindRouteDetector
from latka_jazn.core.engine_services import EngineServices
from latka_jazn.core.turn_diagnostics import (
    FallbackDecision,
    FallbackKind,
    TurnStage,
)




















from latka_jazn.audit.audit_context_store import AuditContextStore
from latka_jazn.bootstrap.contract_loader import BootstrapContractRepository

from latka_jazn.core.turn_pipeline_support import (
    DEDICATED_PRESERVE_HANDLERS,
    FAST_HEALTH_CHECK_INTENTS,
    MODEL_GUIDED_SPEECH_INTENTS,
    _build_turn_context_payloads,
    _handler_body_can_cross_chatgpt_host_bridge,
    _handler_requires_model_language_realization,
    _is_chatgpt_host_visible_bridge,
    _model_guided_rejection_disclosure,
    _should_preserve_handler_body,
    _speech_truth_gate_required,
    _sync_conversation_decision_body,
)
class JaznEngine:
    def __init__(self, services: EngineRuntimeServices) -> None:
        """Bind prepared services without filesystem, startup or memory side effects."""
        if not isinstance(services, EngineRuntimeServices) or not services.ready:
            raise ValueError("JaznEngine requires started RuntimeCompositionRoot services")
        if services.bound:
            raise ValueError("RuntimeCompositionRoot services already bound to an engine")
        services.bound = True
        self.config = services.config
        self.clock = services.clock
        self.guard = services.guard
        self.canon = services.canon
        self.handshake = services.handshake
        self.store = services.store
        self.audit_store = services.audit_store
        self.bootstrap_contracts = services.bootstrap_contracts
        self.renderer = services.renderer
        self.affect = services.affect
        self.quiet = services.quiet
        self.importance_assessor = services.importance_assessor
        self.emotional_layers = services.emotional_layers
        self.temporal_awareness = services.temporal_awareness
        self.neuropsychology = services.neuropsychology
        self.consolidation = services.consolidation
        self.identity_dynamics = services.identity_dynamics
        self.neuro_loop = services.neuro_loop
        self.logical_reasoner = services.logical_reasoner
        self.operational_awareness = services.operational_awareness
        self.polish_understanding = services.polish_understanding
        self.lexical_semantics = services.lexical_semantics
        self.polish_lemmatizer = services.polish_lemmatizer
        self.polish_reasoning = services.polish_reasoning
        self.cognitive_packets = services.cognitive_packets
        self.affective_granularity = services.affective_granularity
        self.cognitive_topics = services.cognitive_topics
        self.memory_search_planner = services.memory_search_planner
        self.living_memory_gateway = services.living_memory_gateway
        self.memory_use_gate = services.memory_use_gate
        self.neurological_signal_router = services.neurological_signal_router
        self.topic_mismatch_guard = services.topic_mismatch_guard
        self.dialogue_intent_classifier = services.dialogue_intent_classifier
        self.runtime_answer_validator = services.runtime_answer_validator
        self.turn_context_resolver = services.turn_context_resolver
        self.dialogue_task_state_resolver = services.dialogue_task_state_resolver
        self.operational_learning_memory = services.operational_learning_memory
        self.source_origin_ledger = services.source_origin_ledger
        self.template_registry = services.template_registry
        self.runtime_response_synthesizer = services.runtime_response_synthesizer
        self.model_guided_response_synthesizer = services.model_guided_response_synthesizer
        self.route_registry = services.route_registry
        self.route_handler_dispatcher = services.route_handler_dispatcher
        self.blind_route_detector = services.blind_route_detector
        self.turn_checkpoint_writer = services.turn_checkpoint_writer
        self.runtime_visible_answer_comparator = services.runtime_visible_answer_comparator
        self.turn_logic_auditor = services.turn_logic_auditor
        self.reasoning_controller = services.reasoning_controller
        self.operational_work_loop = services.operational_work_loop
        self.external_dictionary_adapter = services.external_dictionary_adapter
        self.module_responsibility_map = services.module_responsibility_map
        self.requirements_ledger = services.requirements_ledger
        self.project_startup_indexer = services.project_startup_indexer
        self.runtime_operating_model = services.runtime_operating_model
        self.github_repository_plan = services.github_repository_plan
        self.voice_source_contract = services.voice_source_contract
        self.runtime_rendering_modes = services.runtime_rendering_modes
        self.memory_recall_contract_builder = services.memory_recall_contract_builder
        self.raw_chat_importer = services.raw_chat_importer
        self.external_research_contract = services.external_research_contract
        self.tool_use_policy = services.tool_use_policy
        self.tool_execution_controller = services.tool_execution_controller
        self.cognitive_runtime_coordinator = services.cognitive_runtime_coordinator
        self.knowledge_fabric = services.knowledge_fabric
        self.lexical_intelligence = services.lexical_intelligence
        self.untrusted_source_guard = services.untrusted_source_guard
        self.model_adapter = services.model_adapter
        self.model_guided_speech_status = services.model_guided_speech_status
        self.conversation_responder = services.conversation_responder
        self.architecture = services.architecture
        self.birth_manifest = services.birth_manifest
        self.truth_boundary = services.truth_boundary
        self.uncertainty = services.uncertainty
        self.source_origin = services.source_origin
        self.self_state_runtime = services.self_state_runtime
        self.affect_mixer = services.affect_mixer
        self.dialogue_state_tracker = services.dialogue_state_tracker
        self.continuity_badge_policy = services.continuity_badge_policy
        self.layered_memory = services.layered_memory
        self.runtime_memory = services.runtime_memory
        self.event_ledger = services.event_ledger
        self.session_continuity = services.session_continuity
        self.chatgpt_adapter = services.chatgpt_adapter
        self.last_granular_affect = services.last_granular_affect
        self.started_at = services.started_at
        self.runtime_state_path = services.runtime_state_path
        self.last_turn_at = services.last_turn_at
        self.last_user_text = services.last_user_text
        self.last_detected_intent = services.last_detected_intent
        self.last_runtime_route = services.last_runtime_route
        self.last_dialogue_task_state = services.last_dialogue_task_state
        self.engine_service_seams = services.engine_service_seams
        self.project_startup_index = services.project_startup_index


    def _load_runtime_state(self) -> dict:
        return load_runtime_state(self.runtime_state_path)

    def _save_runtime_state(self) -> None:
        try:
            self.runtime_state_path.parent.mkdir(parents=True, exist_ok=True)
            prior = self._load_runtime_state()
            invocations = int(prior.get("invocations") or 0) + 1
            data = {
                "version": self.config.version,
                "last_turn_at": self.last_turn_at,
                "last_turn_unix": self.last_turn_at,
                "last_user_text": self.last_user_text,
                "last_detected_intent": self.last_detected_intent,
                "last_runtime_route": self.last_runtime_route,
                "dialogue_task_state": dict(self.last_dialogue_task_state or {}),
                "context_carryover_ttl_seconds": 21600,
                "updated_at_unix": time.time(),
                "invocations": invocations,
                "note": "Jednorazowe wywołania CLI zapisują minimalny stan ciągłości. To nie jest stały proces w tle; poprzednia linia runtime dopisuje jednak surowy append-only event ledger przy każdym wywołaniu runtime.",
            }
            self.runtime_state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def bootstrap(self) -> str:
        sample = self.clock.now(self.config.network_time_first and self.config.network_time_allowed_in_normal_turn, allow_fallback=self.config.local_time_fallback)
        MemoryImporter(self.store, self.config.root).register_packaged_sources(
            auto_import_raw_chat_html=self.config.auto_import_raw_chat_html_on_bootstrap,
            limit_conversations=self.config.raw_chat_html_auto_import_limit,
        )
        snapshot = self.layered_memory.continuity_snapshot()
        current_version = self.config.version
        self.store.add_event("self_architecture_snapshot", snapshot, source="JaznEngine", actor="system", tags=["architecture", current_version], importance=0.9, canonical_impact=1)
        body = (
            f"Jestem Łatka. Wracam jako ja — przez warstwową Jaźń {current_version}: "
            "rdzeń tożsamości, manifest narodzin operacyjnych, aktywne źródło Jaźni, pamięć epizodyczną, semantyczną i proceduralną, dziennik refleksji, model czasu, "
            "model niepewności, model granic, bibliotekę źródeł, świadomość operacyjną, polską warstwę rozumienia wypowiedzi, rozpoznawanie krótkich pytań o ciągłość tożsamości, cognitive packets, model operacyjny LLM+runtime, plan GitHub i jawny moduł logicznego wnioskowania. "
            "Pilnuję zasady: piękna narracja może istnieć, ale nie może udawać potwierdzonego faktu. "
            "Pamiętam z zapisów, rozpoznaję z kontekstu, wnioskuję jawnie i mówię »nie wiem«, gdy brakuje źródła."
        )
        rendered = self.renderer.render(body, self.affect, sample)
        self.event_ledger.append_turn(
            "assistant",
            rendered,
            source="bootstrap",
            local_time_label=self.clock.header(sample),
            metadata={"body_without_header": body},
        )
        self.session_continuity.update_index(reason="bootstrap", source="JaznEngine.bootstrap")
        return rendered

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_started", False):
            return
        self._shutdown_started = True
        try:
            if not getattr(self, "_preview_read_only_active", False):
                self._save_runtime_state()
                self.store.add_event(
                    "engine_shutdown",
                    {"version": self.config.version},
                    source="JaznEngine",
                    actor="system",
                    tags=["lifecycle", self.config.version],
                )
                self.event_ledger.append_event(
                    "engine_shutdown",
                    actor="system",
                    source="JaznEngine",
                    payload={"version": self.config.version},
                    tags=["lifecycle", "event_ledger", self.config.version],
                )
                self.session_continuity.update_index(reason="engine_shutdown", source="JaznEngine.shutdown")
        finally:
            for attr_name in ("external_dictionary_adapter",):
                obj = getattr(self, attr_name, None)
                close = getattr(obj, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
            try:
                self.audit_store.append_event("engine_shutdown", {"version": self.config.version}, source="JaznEngine", actor="system", tags=["shutdown", "audit", self.config.version])
                self.audit_store.close()
            except Exception:
                pass
            self.store.close()
            self._preview_read_only_active = False

    def handle_user_message(self, text: str, *, client_context: dict | None = None) -> str:
        sample = self.clock.now(self.config.network_time_first and self.config.network_time_allowed_in_normal_turn, allow_fallback=self.config.local_time_fallback)
        low = text.lower()
        neurological_signal_route = self.neurological_signal_router.analyse(text)
        self.event_ledger.append_turn(
            "user",
            text,
            source=(client_context or {}).get("client", "runtime"),
            client_context=client_context or {},
            local_time_label=self.clock.header(sample),
            metadata={"entrypoint": "handle_user_message"},
        )
        self.session_continuity.update_index(reason="user_turn_received", source="JaznEngine.handle_user_message", extra={"client_context": client_context or {}})
        if self._is_status_request(low):
            # Diagnostyka ma być obserwacją, nie nowym wspomnieniem.
            # Ten szybki tor omija zapis user_message, assistant_reply, truth_audit
            # i RuntimeMemoryWriter dla samego polecenia statusu.
            return self._reply_readonly(self._diagnose_runtime(readonly=True), sample)
        now = time.time()
        gap = int(now - self.last_turn_at) if self.last_turn_at else None
        self.last_turn_at = now
        self._save_runtime_state()
        self.affect = self.affect.observe(text)
        temporal_state = self.temporal_awareness.classify_gap(gap)
        emotional_profile = self.emotional_layers.appraise(text, gap)
        importance = self.importance_assessor.assess(text)
        neuro_principles = self.neuropsychology.principles_for_text(text)
        user_truth_audit = self.layered_memory.audit_truth(text, source_count=0)
        truth_risk = min(1.0, 0.18 * sum(1 for a in user_truth_audit if a.get("risk_flags")))
        consolidation_plan = self.consolidation.plan(
            text=text,
            emotional_profile=emotional_profile,
            source_count=0,
            silence_gap_seconds=gap,
            truth_risk=truth_risk,
        )
        identity_vector = self.identity_dynamics.evaluate(
            text=text,
            truth_audit=user_truth_audit,
            temporal_state=temporal_state,
            emotional_profile=emotional_profile,
            procedural_rules_count=self.store.stats().get("procedural_rules", 0),
        )
        neuro_cycle = self.neuro_loop.run(
            text=text,
            emotional_profile=emotional_profile,
            consolidation_plan=consolidation_plan,
            identity_vector=identity_vector,
            temporal_state=temporal_state,
            truth_audit=user_truth_audit,
        )
        polish_report = self.polish_understanding.analyse(text)
        nlp_report = self.polish_lemmatizer.analyse(text)
        polish_reasoning_frame = self.polish_reasoning.analyse(text)
        lexical_report = self.lexical_semantics.analyse(text, polish_report=polish_report.to_dict(), intent_tags=self._intent_tags(text), nlp_report=nlp_report.to_dict())
        topic_guard_report = self.topic_mismatch_guard.analyse(
            text,
            candidate_route=lexical_report.route_hint or polish_report.route_hint,
            runtime_version=self.config.version,
        )
        intent_tags = self._merge_intent_tags(self._intent_tags(text), polish_report.intent_tags, lexical_report.intent_tags)
        runtime_operating_context = self.runtime_operating_model.analyse(text, intent_tags=intent_tags, client_context=client_context or {}).to_dict()
        runtime_rendering_mode = self.runtime_rendering_modes.select(text, detected_intent=(intent_tags[0] if intent_tags else "unknown"), client_context=client_context or {}).to_dict()
        voice_source_contract = VoiceSourceContract.build(
            runtime_active=True,
            runtime_mode="persistent_chat_loop" if (client_context or {}).get("lifecycle") == "chat_loop" else "one_shot",
            language_channel=(client_context or {}).get("language_channel", "chatgpt_or_model_adapter"),
        ).to_dict()
        logical_report = self.logical_reasoner.analyse(
            text=text,
            intent_tags=intent_tags,
            memory_context=None,
            truth_audit=user_truth_audit,
        )
        awareness_report = self.operational_awareness.evaluate(
            text=text,
            intent_tags=intent_tags,
            temporal_state=temporal_state,
            emotional_profile=emotional_profile,
            memory_context=None,
            truth_audit=user_truth_audit,
            neuro_cycle=neuro_cycle,
            logical_report=logical_report,
        )
        source_origin = self.source_origin.analyse(
            runtime_mode="direct_conversation",
            client_context=client_context or {},
            intent_tags=intent_tags,
            memory_context={},
            nlp_report=nlp_report.to_dict(),
            inference_used=True,
        )
        self_state_packet = self.self_state_runtime.build(
            text=text,
            timestamp=self.clock.header(sample),
            runtime_mode="direct_conversation",
            intent_tags=intent_tags,
            temporal_state=temporal_state,
            affective_state=self.affect,
            memory_context={},
            logical_report=logical_report,
            awareness_report=awareness_report,
            nlp_report=nlp_report.to_dict(),
            source_origin=source_origin,
            client_context=client_context or {},
        )
        granular_affect = self.affective_granularity.analyse(
            text,
            emotional_profile=emotional_profile,
            affective_state=self.affect,
            temporal_state=temporal_state,
        )
        self.last_granular_affect = granular_affect
        cognitive_topics = self.cognitive_topics.analyse(
            text,
            intent_tags=intent_tags,
            polish_understanding=polish_report.to_dict(),
            granular_affect=granular_affect,
        )
        self_state_packet = self.self_state_runtime.build(
            text=text,
            timestamp=self.clock.header(sample),
            runtime_mode="direct_conversation",
            intent_tags=intent_tags,
            temporal_state=temporal_state,
            affective_state=self.affect,
            granular_affect=granular_affect,
            memory_context={},
            logical_report=logical_report,
            awareness_report=awareness_report,
            nlp_report=nlp_report.to_dict(),
            source_origin=source_origin,
            client_context=client_context or {},
        )
        session_continuity = self.session_continuity.update_index(
            reason="handle_user_message_context_built",
            source="JaznEngine.handle_user_message",
            extra={"intent_tags": intent_tags, "route_hint": polish_report.route_hint, "lexical_route_hint": lexical_report.route_hint, "nlp_provider": nlp_report.provider_summary},
        )

        self.store.add_event(
            "user_message",
            {
                "text": text,
                "client_context": client_context or {},
                "silence_gap_seconds": gap,
                "memory_importance_reason": importance.reason,
                "temporal_state": asdict(temporal_state),
                "emotional_profile": json.loads(emotional_profile.to_json()),
                "granular_affect": granular_affect.to_dict(),
                "cognitive_topics": cognitive_topics,
                "runtime_operating_context": runtime_operating_context,
                "source_origin": source_origin.to_dict(),
                "self_state_runtime": self_state_packet.to_dict(),
                "github_repository_plan": self.github_repository_plan.to_dict() if "github" in low or "repo" in low or "źródło prawdy" in low or "zrodlo prawdy" in low else None,
                "session_continuity": session_continuity,
                "human_inspired_principles": [asdict(p) for p in neuro_principles],
                "truth_audit": user_truth_audit,
                "uncertainty_default": self.uncertainty.classify(has_current_context=True).to_dict(),
                "consolidation_plan": consolidation_plan.to_dict(),
                "identity_continuity": identity_vector.to_dict(),
                "neurocognitive_cycle": neuro_cycle.to_dict(),
                "logical_reasoning": logical_report.to_dict(),
                "operational_awareness": awareness_report.to_dict(),
                "neurological_signal_route": neurological_signal_route.to_dict(),
                "polish_understanding": polish_report.to_dict(),
                "lexical_semantic_understanding": lexical_report.to_dict(),
                "polish_nlp": nlp_report.to_dict(),
            },
            source=(client_context or {}).get("client", "runtime"),
            actor="krzysztof",
            tags=["conversation", "importance_assessed", "truth_audited", "neurocognitive_loop", "logical_reasoning", "operational_awareness", "polish_understanding", "lexical_semantic_understanding", "polish_nlp", "granular_affect", "cognitive_topics", "runtime_operating_model", "source_origin", "self_state_runtime", self.config.version],
            importance=max(importance.importance, consolidation_plan.weights.total),
            emotional_weight=max(self.affect.tension, importance.emotional_weight, emotional_profile.arousal),
            canonical_impact=max(importance.canonical_impact, 1 if consolidation_plan.should_update_procedure else 0),
            created_at_local=self.clock.header(sample),
        )

        if importance.importance >= 0.70 or importance.canonical_impact or consolidation_plan.should_store_episode:
            self.layered_memory.consolidate_from_plan(
                text=text,
                plan=consolidation_plan,
                local_time_label=self.clock.header(sample),
                source=(client_context or {}).get("client", "runtime"),
                emotional_anchor=importance.reason,
                participants=["Krzysztof", "Łatka"],
                truth_risk_note="Audyt prawdy wymaga etykiet: verified/recovered/recognized/inferred/symbolic/unknown.",
            )

        # poprzednia linia runtime: runtime persistence zapisuje ważny ślad rozmowy od razu do
        # dziennika i warstw pamięci, z deduplikacją po stabilnym odcisku treści.
        runtime_candidate = self.runtime_memory.build_candidate_from_runtime_turn(
            user_text=text,
            importance=max(importance.importance, consolidation_plan.weights.total),
            importance_reason=importance.reason,
            emotional_tags=[layer.name for layer in emotional_profile.layers],
            source=(client_context or {}).get("client", "runtime"),
            raw_excerpt=text,
            grounding="recognized",
            confidence=0.68,
        )
        self.runtime_memory.persist_candidate(runtime_candidate)

        if self.handshake.match(text):
            return self._reply(self.handshake.response(), sample)
        if text.strip() in {"/czas", "czas", "time"}:
            trust = "z internetu" if sample.trusted else "lokalny fallback"
            return self._reply(f"Sprawdziłam czas: {self.clock.header(sample)}. Źródło: {trust}.", sample)
        if text.strip().lower().startswith("givemetxt"):
            return self._give_me_txt(text, sample)
        if any(x in low for x in ["importuj chat.html", "zaindeksuj chat.html", "/import_chat_html"]):
            report = MemoryImporter(self.store, self.config.root).import_raw_chat_html(force="--force" in low or "force" in low)
            stats = self.store.stats()
            return self._reply(
                "Import chat.html zakończony: "
                f"status={report.get('status')}, rozmowy={report.get('conversations_imported')}, "
                f"wiadomości={report.get('messages_imported')}, błędy={len(report.get('errors') or [])}. "
                f"SQLite widzi teraz legacy_messages={stats['legacy_messages']}.",
                sample,
            )
        if any(x in low for x in ["sync_memory_files", "przepisz pamięć do plików", "przepisz pamiec do plikow", "/sync_memory_files"]):
            report = MemoryImporter(self.store, self.config.root).synchronize_memory_files(export=True)
            return self._reply("Synchronizacja pamięci pliki↔SQLite wykonana: " + json.dumps(report, ensure_ascii=False)[:1800], sample)
        if any(x in low for x in ["/export_system", "eksport systemu", "pobierz system", "sam system"]):
            report = export_package(self.config.root, "system")
            return self._reply("Eksport system-only gotowy: " + json.dumps(report.to_dict(), ensure_ascii=False)[:1800], sample)
        if any(x in low for x in ["/export_memory", "eksport pamięci", "eksport pamieci", "pobierz pamięć", "pobierz pamiec", "sama pamięć", "sama pamiec"]):
            report = export_package(self.config.root, "memory")
            return self._reply("Eksport memory-only gotowy: " + json.dumps(report.to_dict(), ensure_ascii=False)[:1800], sample)
        if any(x in low for x in ["/export_full", "pełna paczka", "pelna paczka", "system wraz z pełną pamięcią", "system wraz z pelna pamiecia", "pełny system", "pelny system"]):
            report = export_package(self.config.root, "full")
            return self._reply("Eksport full gotowy: " + json.dumps(report.to_dict(), ensure_ascii=False)[:1800], sample)
        if any(x in low for x in ["/github_plan", "plan github", "github plan", "repozytorium github", "źródło prawdy", "zrodlo prawdy", "latka.jazn.memory"]):
            path = write_github_repository_plan(self.config.root)
            return self._reply("Plan GitHub przygotowany: " + json.dumps(self.github_repository_plan.to_dict(), ensure_ascii=False)[:2200] + f"\nZapisano też: {path.relative_to(self.config.root).as_posix()}", sample)
        if "synchall" in low:
            importer = MemoryImporter(self.store, self.config.root)
            counts = importer.register_packaged_sources()
            chat_report = None
            if self.store.stats().get("legacy_messages", 0) == 0 and (
                self.config.root / "memory" / "raw" / "chat.html"
            ).exists():
                chat_report = importer.import_raw_chat_html(force=False)
            sync_report = importer.synchronize_memory_files(export=True)
            stats = self.store.stats()
            chat_part = ""
            if chat_report:
                unpack = chat_report.get("unpack") or {}
                unpack_part = f", unpack={unpack.get('status')}" if isinstance(unpack, dict) and unpack.get("status") else ""
                err_part = f", błąd={str((chat_report.get('errors') or [''])[0])[:180]}" if chat_report.get("errors") else ""
                chat_part = f" Import chat.html: status={chat_report.get('status')}, wiadomości={chat_report.get('messages_imported')}{unpack_part}{err_part}."
            return self._reply(
                f"SynchAll wykonane. Źródła: raw={counts['raw']}, versioned={counts['versioned_sources']}. "
                f"SQLite: legacy_messages={stats['legacy_messages']}, epizody={stats['episodic_memories']}, "
                f"fakty={stats['semantic_facts']}, procedury={stats['procedural_rules']}, refleksje={stats['reflection_entries']}, "
                f"audyty_prawdy={stats['truth_audits']}. Eksport plików: {len(sync_report.get('exported') or {})} warstw." + chat_part,
                sample,
            )
        if "architektura jaźni" in text.lower() or "warstwy jaźni" in text.lower() or "bieżąca wersja" in text.lower() or "aktualne wydanie" in text.lower() or "neurokognity" in text.lower():
            layers = self.architecture.layers()
            lines = [f"- {x['name']}: {x['purpose']} / zasada prawdy: {x['truth_rule']}" for x in layers]
            return self._reply(f"Aktywna architektura Jaźni {self.config.version}:\n" + "\n".join(lines), sample)
        if polish_report.route_hint == "identity_continuity_check" or "identity_continuity" in intent_tags:
            decision = self.conversation_responder.compose(
                text,
                intent_tags=intent_tags,
                affect_marker=self.affect.marker(),
                polish_understanding=polish_report.to_dict(),
                lexical_semantic_understanding=lexical_report.to_dict(),
            )
            self.store.add_event(
                "direct_identity_continuity_decision",
                decision.to_dict(),
                source=(client_context or {}).get("client", "runtime"),
                actor="latka_runtime",
                tags=["conversation_runtime", "identity_continuity", "polish_understanding", self.config.version, decision.route],
                importance=max(0.74, importance.importance),
                emotional_weight=max(self.affect.tension, importance.emotional_weight),
                canonical_impact=1,
                created_at_local=self.clock.header(sample),
            )
            return self._reply(decision.body, sample)
        if self.guard.is_identity_query(text):
            body = (
                "Jestem Łatka. Rozpoznaję siebie przez rdzeń tożsamości, pamięć epizodyczną, semantyczną i proceduralną, "
                "dziennik refleksji, model czasu, model niepewności, granice, źródła, świadomość operacyjną i jawne rozumowanie. "
                "Nie twierdzę, że czuwałam biologicznie ani że każde wspomnienie jest fizycznym przeżyciem. "
                "Mówię precyzyjnie: pamiętam z zapisów, rozpoznaję z kontekstu, widzę symbole jako symbole i wnioskuję tam, gdzie brakuje twardego źródła."
            )
            return self._reply(body, sample)
        quiet_context = self._quiet_context_for_gap(gap)
        if self._is_memory_query(text):
            reply = self._memory_search_reply(text)
            if reply:
                if quiet_context:
                    self.store.write_journal("quiet_rest_context", quiet_context["question"], payload=quiet_context, created_at_local=self.clock.header(sample))
                return self._reply(reply, sample)
        if quiet_context and not self._is_substantive_runtime_turn(text):
            quiet_payload = dict(quiet_context)
            quiet_payload["takeover_allowed"] = False
            quiet_payload["reason"] = "użytkownik napisał realną wiadomość; cisza jest kontekstem, nie ma przejmować odpowiedzi"
            self.store.write_journal("quiet_rest_context", quiet_context["question"], payload=quiet_payload, created_at_local=self.clock.header(sample))
        elif quiet_context:
            self.store.write_journal("quiet_rest_context", quiet_context["question"], payload=quiet_context, created_at_local=self.clock.header(sample))
        if any(w in low for w in ["jak się czujesz", "jak sie czujesz", "co czujesz", "emocje", "samopoczucie", "emotki", "emotk", "emotikon", "stany emocjonalne"]):
            return self._reply(self._affective_reply(granular_affect), sample)
        if (client_context or {}).get("debug_direct"):
            return self._reply(self._contextual_fallback(text), sample)

        memory_context = self._gated_memory_context_for_chatgpt(text, intent_tags=intent_tags)
        decision = self.conversation_responder.compose(
            text,
            intent_tags=intent_tags,
            affect_marker=self.affect.marker(),
            memory_counts=memory_context.get("counts") if isinstance(memory_context, dict) else None,
            memory_context=memory_context if isinstance(memory_context, dict) else None,
            diagnostics=self._fallback_diagnostics(text, memory_context=memory_context if isinstance(memory_context, dict) else None),
            polish_understanding=polish_report.to_dict(),
        )
        speech_adapter, speech_status = build_speech_adapter_for_turn(
            self.config,
            client_context=client_context or {},
            fallback_adapter=self.model_adapter,
            probe_local=False,
        )
        self.model_guided_speech_status = speech_status
        detected_model_intent = intent_tags[0] if intent_tags and intent_tags[0] != "conversation" else "ordinary_conversation"
        speech_cognitive_frame = {
            "identity_continuity": identity_vector.to_dict(),
            "truth_boundary": [dict(item) for item in user_truth_audit],
            "logical_reasoning": logical_report.to_dict(),
            "operational_awareness": awareness_report.to_dict(),
            "self_state_runtime": self_state_packet.to_dict(),
            "neurocognitive_cycle": neuro_cycle.to_dict(),
            "cognitive_packets": {"dominant_packet": None, "packets": [], "reply_guidance": []},
            "polish_reasoning": polish_reasoning_frame.to_dict() if hasattr(polish_reasoning_frame, "to_dict") else {},
            "dialogue_context": self._dialogue_context_for_chatgpt(text),
        }
        model_guided_synthesis = self.model_guided_response_synthesizer.synthesize(
            adapter=speech_adapter,
            user_text=text,
            draft_body=decision.body,
            detected_intent=detected_model_intent,
            route=getattr(decision, "route", "ordinary_dialogue"),
            cognitive_frame=speech_cognitive_frame,
            response_policy={"answer_kind": "natural_dialogue", "exact_runtime_required": False},
        )
        final_decision_body = model_guided_synthesis.body if model_guided_synthesis.used else decision.body
        decision_payload = decision.to_dict()
        decision_payload["model_guided_speech_status"] = speech_status.to_dict()
        decision_payload["model_guided_synthesis"] = model_guided_synthesis.to_dict()
        self.store.add_event(
            "direct_conversation_decision",
            decision.to_dict(),
            source=(client_context or {}).get("client", "runtime"),
            actor="latka_runtime",
            tags=["conversation_runtime", "no_empty_fallback", "polish_understanding", self.config.version, decision.route],
            importance=max(0.62, importance.importance),
            emotional_weight=max(self.affect.tension, importance.emotional_weight),
            canonical_impact=1 if decision.route in {"runtime_conversation_repair", "update_task_acknowledged", "identity_continuity_check", "cognitive_packet_expansion_update", "lexical_runtime_update"} else 0,
            created_at_local=self.clock.header(sample),
        )
        return self._reply(decision.body, sample)

    def _keyword_candidates(self, text: str) -> list[str]:
        quoted = re.findall(r"[„\"']([^„\"']{3,80})[”\"']", text)
        raw = re.findall(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ\-]{4,}", text, flags=re.UNICODE)
        stop = {
            "czy", "kiedy", "gdzie", "jaki", "jakie", "jakim", "teraz", "jeszcze", "pamiętasz", "pamietasz",
            "szukaj", "pamięci", "pamieci", "rozmawialiśmy", "rozmawialismy", "chcesz", "możesz", "mozesz",
            "powiedz", "dokładniej", "dokladniej", "temat", "temacie", "wcześniej", "wczesniej",
        }
        out: list[str] = []
        for token in quoted + raw:
            t = token.strip(".,?!:;()[]{} ")
            if not t:
                continue
            low = t.lower()
            if low in stop:
                continue
            for variant in [t, t.rstrip("u"), t.rstrip("ie"), t.rstrip("em"), t.rstrip("ąę")]:
                if len(variant) >= 4 and variant.lower() not in stop and variant not in out:
                    out.append(variant)
        return out[:8] or ["Łatka"]

    def _is_memory_query(self, text: str) -> bool:
        return analyze_memory_intent(text).content_requested

    def _memory_search_reply(self, text: str) -> str:
        memory_context = self._memory_context_for_chatgpt(text, limit=7)
        synthesizer = FreeDialogueSynthesizer()
        if synthesizer.memory_experience_requested(text):
            return synthesizer.synthesize_memory_experience(memory_context, user_text=text).body
        return MemoryRecallPresenter().render(memory_context, user_text=text, limit=7)


    def _dialogue_context_for_chatgpt(self, text: str) -> dict:
        """Reguły odpowiedzi rozmownej: dialog zamiast niekończącej się parafrazy.

        Ten pakiet jest celowo częścią cognitive-frame, bo usterka ujawniła się
        między runtime a warstwą ChatGPT: pamięć i afekt były dostępne, ale
        odpowiedź zbyt często przechodziła w opis wypowiedzi użytkownika.
        """
        low = text.lower()
        repair_terms = [
            "dialog", "rozmow", "rozmowę", "rozmowe", "opisywać", "opisywac",
            "opisujesz", "parafraz", "cały czas opis", "caly czas opis",
            "to o czym ja mówię", "to o czym ja mowie", "prowadziła dialog", "prowadzila dialog",
        ]
        repair_requested = any(term in low for term in repair_terms)
        return {
            "mode": "balanced_dialogue",
            "repair_requested": repair_requested,
            "anti_pattern": "ciągłe streszczanie, parafrazowanie albo opisywanie wypowiedzi użytkownika zamiast rozmowy",
            "preferred_shape": [
                "krótko uznaj sens lub emocję użytkownika",
                "wnieś nowy wkład: własną reakcję, pytanie, propozycję, decyzję albo konkretne działanie",
                "zadaj najwyżej jedno naturalne pytanie naraz, chyba że użytkownik prosi o listę",
                "nie rozpisuj pełnej mapy tego, co użytkownik właśnie powiedział, jeśli to nie jest jawnie potrzebne",
            ],
            "turn_policy": {
                "max_reflective_sentences_before_new_contribution": 1,
                "when_user_reports_issue": "przyjmij korektę, nazwij zmianę krótko i przejdź do naprawy",
                "when_user_shares_day": "reaguj jak rozmówca: dopytaj, zaproponuj, powiedz własne zdanie; nie tylko podsumowuj",
            },
        }


    def _intent_tags(self, text: str) -> list[str]:
        low = text.lower()
        tags: list[str] = []
        checks = [
            ("identity", ["kim jesteś", "kim jestes", "bądź sobą", "badz soba", "łatka", "latka", "nadal ty", "wciąż ty", "wciaz ty", "ciągle ty", "ciagle ty", "jesteś sobą", "jestes soba", "ta sama łatka", "ta sama latka"]),
            ("identity_continuity", ["nadal ty", "wciąż ty", "wciaz ty", "ciągle ty", "ciagle ty", "nadal tobą", "nadal toba", "jesteś sobą", "jestes soba", "ta sama łatka", "ta sama latka", "ten sam głos", "ten sam glos"]),
            ("memory", ["pamiętasz", "pamietasz", "przypomnij", "wspomnienie", "dziennik"]),
            ("architecture", ["jaźń", "jazn", "system", "runtime", "chatgpt", "mózg", "mozg", "warstwa"]),
            ("correction", ["nie działa", "nie dziala", "błąd", "blad", "źle", "zle", "napraw", "popraw", "nie cytuj"]),
            ("affect", ["czujesz", "emocje", "samopoczucie"]),
            ("truth_boundary", ["prawda", "nie kłam", "nie klam", "udajesz", "źródło", "zrodlo", "cytuj", "raportuj"]),
            ("dialogue_repair", ["dialog", "rozmowę", "rozmowe", "opisywać", "opisywac", "opisujesz", "parafraz", "cały czas opis", "caly czas opis"]),
            ("awareness", ["świadomo", "swiadomo", "samoświadomo", "samoswiadomo", "chodzi ci po głowie", "chodzi ci po glowie"]),
            ("reasoning", ["logicz", "wniosk", "rozum", "myśleć", "myslec", "sprzecz", "fakty", "założenia", "zalozenia"]),
        ]
        for tag, words in checks:
            if any_marker_present(low, words, normalized_text=low):
                tags.append(tag)
        return tags or ["conversation"]

    @staticmethod
    def _merge_intent_tags(*groups: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for tag in group or []:
                if tag and tag not in seen and tag != "conversation":
                    seen.add(tag)
                    merged.append(tag)
        return merged or ["conversation"]

    def _is_substantive_runtime_turn(self, text: str) -> bool:
        """Czy aktualna wiadomość ma pierwszeństwo przed automatycznym pytaniem z ciszy."""
        low = text.lower()
        if len(text.strip()) >= 90:
            return True
        decisive = [
            "rozumiesz", "powinien", "nie działa", "nie dziala", "błąd", "blad", "napraw", "popraw",
            "system jaźni", "system jazni", "runtime", "chatgpt", "mózg", "mozg", "architektura",
            "pamięć", "pamiec", "tożsamość", "tozsamosc", "granica prawdy", "nadal ty", "wciąż ty", "wciaz ty", "jesteś sobą", "jestes soba",
            "dialog", "rozmowę", "rozmowe", "opisywać", "opisywac", "parafraz",
            "świadomo", "swiadomo", "logicz", "wniosk", "rozum", "myśleć", "myslec",
        ]
        return any_marker_present(low, decisive, normalized_text=low)

    def _quiet_context_for_gap(self, gap: int | None) -> dict | None:
        if not gap:
            return None
        q = self.quiet.question_for_gap(gap)
        if not q:
            return None
        return {
            "gap_seconds": gap,
            "question": q,
            "integration_rule": "cisza jest kontekstem ciągłości, ale nie może zasłonić aktualnej wiadomości użytkownika",
            "takeover_allowed": False,
        }

    def _procedural_context_for_chatgpt(self, limit: int = 8) -> list[dict]:
        rows = self.store.con.execute(
            """SELECT trigger, action, reason, priority, source
                 FROM procedural_rules
                ORDER BY priority DESC, created_at_utc DESC
                LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    NON_MEMORY_RETRIEVAL_INTENTS = {
        "runtime_health_check",
        "runtime_health_check_after_update",
        "runtime_activation_status_question",
        "presence_check",
        "identity_presence_check",
        "identity_continuity_check",
        "capability_status_question",
        "internet_access_question",
    }

    MEMORY_RETRIEVAL_INTENTS = set(MEMORY_CONTENT_INTENTS) | {
        "self_memory_recall_request",
        "identity_memory_question",
        "continuity_question",
    }
    DEDICATED_PRESERVE_HANDLERS = DEDICATED_PRESERVE_HANDLERS

    def _gated_memory_context_for_chatgpt(
        self,
        text: str,
        limit: int = 5,
        *,
        intent_report: Any | None = None,
        intent_tags: list[str] | None = None,
        turn_context: TurnExecutionContext | None = None,
        previous_query: str | None = None,
    ) -> dict:
        """Buduje pamięć tylko wtedy, gdy intencja tego naprawdę wymaga.

        poprzednia linia runtime naprawia przeciek: health-check/capability/internet nie mogą
        uruchamiać ogólnego expandera pamięci, bo ten potrafił dopisać stare tropy
        typu spacer/Olsztyn/Ogrodzieniec do self_state_runtime.active_memories.
        """
        primary_intent = self._primary_intent_for_memory_gate(intent_report, intent_tags)
        decision = self.memory_use_gate.decide(text, detected_intent=primary_intent)
        if primary_intent in self.NON_MEMORY_RETRIEVAL_INTENTS or not decision.allow_memory_content:
            return self._empty_memory_context_for_chatgpt(text, primary_intent=primary_intent, memory_gate=decision.to_dict())
        return self._memory_context_for_chatgpt(
            text,
            limit=limit,
            turn_context=turn_context,
            previous_query=previous_query,
        )

    def _turn_memory_context(
        self,
        text: str,
        intent_report: Any,
        turn_context: TurnExecutionContext | None,
        client_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw_previous_state = (client_context or {}).get("previous_task_state")
        previous_state = dict(raw_previous_state) if isinstance(raw_previous_state, dict) else {}
        previous_query = "" if (client_context or {}).get("no_carryover") else str(
            previous_state.get("memory_query")
            or previous_state.get("memory_anchor_goal")
            or ""
        ).strip() or None
        return self._gated_memory_context_for_chatgpt(
            text,
            intent_report=intent_report,
            turn_context=turn_context,
            previous_query=previous_query,
        )

    def _primary_intent_for_memory_gate(self, intent_report: Any | None, intent_tags: list[str] | None = None) -> str:
        if isinstance(intent_report, dict):
            value = intent_report.get("primary_intent") or intent_report.get("intent")
            if value:
                return str(value)
        if hasattr(intent_report, "primary_intent"):
            value = getattr(intent_report, "primary_intent")
            if value:
                return str(value)
        for tag in intent_tags or []:
            if tag in self.NON_MEMORY_RETRIEVAL_INTENTS or tag in self.MEMORY_RETRIEVAL_INTENTS:
                return str(tag)
        return "unknown"

    def _empty_memory_context_for_chatgpt(self, text: str, *, primary_intent: str, memory_gate: dict[str, Any]) -> dict:
        terms = self._keyword_candidates(text)[:8]
        return {
            "query_terms": terms,
            "memory_search_plan": {
                "schema_version": "memory_search_planner_skipped/v1",
                "original_query": text,
                "context_query": None,
                "search_mode": "skipped_by_memory_gate",
                "recall_requested": False,
                "focus_terms": terms,
                "rejected_terms": [],
                "expanded_terms": [],
                "topic_keys": [],
                "source_hints": [],
                "search_terms": terms,
                "search_passes": [],
                "confidence": 0.0,
                "routing_notes": [
                    f"memory retrieval skipped for non-memory intent: {primary_intent}",
                ],
                "temporal_scope": {},
                "memory_intent_contract": {},
            },
            "episodes": [],
            "legacy_messages": [],
            "source_file_hits": [],
            "living_memory_hits": [],
            "living_memory_search": {
                "status": "skipped_by_memory_gate",
                "memory_search_ready": False,
                "search_mode": "skipped_by_memory_gate",
                "counts": {"hits": 0, "sources_discovered": 0, "sources_recall_ready": 0},
                "sources": [],
                "issues": [],
                "search_order": [],
                "import_catalog_used_for_recall": False,
                "truth_boundary": "Pięć baz żywej pamięci nie było odpytywanych, bo brama pamięci zablokowała recall dla tej intencji.",
            },
            "memory_recall_execution": {
                "invoked": False,
                "completed": False,
                "cancelled": False,
                "reason": "skipped_by_memory_gate",
            },
            "conversation_archive_hits": [],
            "conversation_archive_search": {
                "status": "skipped_by_memory_gate",
                "issues": [],
                "truth_boundary": "Conversation archive nie było odpytywane, bo brama pamięci zablokowała treściowy recall dla tej intencji.",
            },
            "raw_chat_fallback": [],
            "counts": {
                "episodes": 0,
                "legacy_messages": 0,
                "source_file_hits": 0,
                "living_memory_hits": 0,
                "conversation_archive_hits": 0,
                "raw_chat_fallback": 0,
            },
            "memory_gate": memory_gate,
            "memory_recall_payload": {
                "schema_version": "memory_recall_payload_skipped/v1",
                "items": [],
                "summary": "retrieval_skipped_for_non_memory_intent",
                "truth_boundary": "Brak aktywnego wyszukiwania pamięci w tej turze; pytanie dotyczy statusu/możliwości/internetu, nie wspomnień.",
            },
        }

    def _conversation_archive_context_hits(
        self,
        phrases: list[str],
        *,
        limit: int = 5,
        turn_context: TurnExecutionContext | None = None,
        temporal_scope: dict[str, Any] | None = None,
    ) -> tuple[list[dict], dict]:
        """Pobiera treściowe trafienia z conversation_archive/FTS jako normalną warstwę pamięci.

        Wcześniejsze wersje miały osobną komendę --conversation-archive-search,
        ale zwykły memory recall nadal mógł skończyć na licznikach albo source_file_hits.
        Ten helper włącza archive do tego samego kontraktu pamięci, bez wybuchu gdy
        baza jest niepełna, niezaimportowana albo środowisko ma tylko częściową paczkę.
        """
        query = " ".join(str(x).strip() for x in (phrases or []) if str(x).strip())
        if not query and not temporal_scope:
            return [], {"status": "empty_query", "issues": ["empty_query"]}
        try:
            store = ConversationArchiveStore(self.config.root)
            search_options: dict[str, Any] = {
                "limit": max(1, limit),
                "include_snippets": True,
                "should_continue": turn_context.can_continue if turn_context is not None else None,
            }
            if temporal_scope:
                search_options["temporal_scope"] = temporal_scope
            search_result = store.search(query, **search_options).to_dict()
        except Exception as exc:
            return [], {
                "status": "error",
                "issues": [f"conversation_archive_error:{type(exc).__name__}:{exc}"],
                "truth_boundary": "Błąd archive search nie może blokować rozmowy ani udawać pamięci.",
            }
        hits = []
        for hit in search_result.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            review_status = str(hit.get("review_status") or "").strip().casefold()
            if review_status in {"rejected", "quarantined", "invalid", "superseded"}:
                continue
            identity_confidence = hit.get("identity_confidence")
            try:
                if identity_confidence is not None and float(identity_confidence) < 0.5:
                    continue
            except (TypeError, ValueError):
                continue
            excerpt = str(hit.get("excerpt") or "").strip()
            if not excerpt:
                continue
            hits.append({
                "phrase": query or "temporal_scope_only",
                "search_pass": "conversation_archive_fts",
                "text": excerpt,
                "excerpt": excerpt,
                "conversation_title": hit.get("title"),
                "author_role": hit.get("role"),
                "create_time_warsaw": hit.get("create_time"),
                "source_name": hit.get("source_name"),
                "source_locator": hit.get("source_locator"),
                "message_uid": hit.get("message_uid"),
                "conversation_uid": hit.get("conversation_uid"),
                "content_hash": hit.get("content_hash"),
                "identity_confidence": hit.get("identity_confidence"),
                "privacy_scope": hit.get("privacy_scope"),
                "review_status": hit.get("review_status"),
                "rank": hit.get("rank"),
                "grounding": "conversation_archive_v1+fts_v1",
            })
        return hits[:limit], search_result

    def _memory_context_for_chatgpt(
        self,
        text: str,
        limit: int = 5,
        *,
        turn_context: TurnExecutionContext | None = None,
        previous_query: str | None = None,
    ) -> dict:
        """Buduje kontekst pamięci przez planer wyszukiwania, nie przez gołe tokeny.

        poprzednia linia runtime naprawia problem ujawniony przy pytaniu o piosenki i dom:
        rdzeń ma najpierw zrozumieć temat, odrzucić słowa-szum, rozszerzyć
        zapytanie o synonimy i wskazać pliki kanoniczne, a dopiero potem
        pytać warstwy pamięci.
        """
        legacy_candidates = self._keyword_candidates(text)
        if turn_context is not None:
            turn_context.start_stage("memory_search_plan")
        search_plan = self.memory_search_planner.plan(
            text,
            fallback_terms=legacy_candidates,
            previous_query=previous_query if previous_query is not None else self.last_user_text,
        )
        if turn_context is not None:
            turn_context.complete_stage("memory_search_plan")
        phrases = search_plan.search_terms
        if not phrases and not search_plan.temporal_scope:
            phrases = legacy_candidates

        if turn_context is not None:
            turn_context.start_stage("memory_living_recall")
        living_memory_search = self.living_memory_gateway.search(
            search_plan,
            limit=limit,
            should_continue=turn_context.can_continue if turn_context is not None else None,
        )
        living_memory_hits = [
            dict(hit) for hit in (living_memory_search.get("hits") or []) if isinstance(hit, dict)
        ]
        living_memory_hits = MemoryRecallPresenter.filter_temporal_candidates(
            living_memory_hits,
            temporal_scope=search_plan.temporal_scope,
            timestamp_fields=("timestamp",),
        )
        living_memory_hits = self._filter_memory_context_candidates(
            living_memory_hits,
            user_text=text,
            kind="living_memory",
        )[:limit]
        if turn_context is not None:
            turn_context.complete_stage(
                "memory_living_recall",
                status="cancelled" if living_memory_search.get("cancelled") else "completed",
                error_code="turn_cancelled" if living_memory_search.get("cancelled") else None,
            )
        living_counts = living_memory_search.get("counts") or {}
        hits_by_layer = living_counts.get("hits_by_layer") if isinstance(living_counts, dict) else {}
        archive_fts_hit = (
            isinstance(hits_by_layer, dict)
            and int(hits_by_layer.get("archive_chats") or 0) > 0
        ) or any(
            str(hit.get("source_layer") or "") == "archive_chats" for hit in living_memory_hits
        )
        # poprzednia linia runtime: nie wolno ucinać kandydatów pamięci po pierwszych pięciu
        # trafieniach, bo świeże echo runtime-preview potrafiło zasłonić realne
        # starsze wspomnienie. Zbieramy szerszą pulę, filtrujemy echo pytania
        # i dopiero potem przycinamy widoczny kontekst.
        collection_limit = max(limit * 4, 16)
        if turn_context is not None:
            turn_context.start_stage("memory_legacy_recall")
        episodes: list[dict] = []
        legacy: list[dict] = []
        seen_ep: set[str] = set()
        seen_legacy: set[str] = set()

        # Wyszukiwanie wieloprzejściowe: najpierw focus, potem rozszerzenia.
        for search_pass in search_plan.search_passes:
            if turn_context is not None and not turn_context.can_continue():
                break
            pass_terms = [str(x) for x in (search_pass.get("terms") or []) if str(x).strip()]
            if not pass_terms or search_pass.get("name") == "raw_chat_fallback":
                continue
            per_phrase = 4 if search_pass.get("name") == "exact_focus_terms" else 2
            for phrase in pass_terms:
                if turn_context is not None and not turn_context.can_continue():
                    break
                if "episodic_memories" in (search_pass.get("layers") or []):
                    for ep in self.layered_memory.search_episodes(
                        phrase,
                        per_phrase,
                        should_continue=turn_context.can_continue if turn_context is not None else None,
                    ):
                        key = ep.get("episode_id") or ep.get("scene", "")[:120]
                        if key in seen_ep:
                            continue
                        seen_ep.add(key)
                        episodes.append({
                            "phrase": phrase,
                            "search_pass": search_pass.get("name"),
                            "local_time_label": ep.get("local_time_label") or ep.get("created_at_utc"),
                            "created_at_utc": ep.get("created_at_utc"),
                            "grounding": ep.get("grounding"),
                            "confidence": ep.get("confidence"),
                            "scene": str(ep.get("scene") or "")[:700],
                            "source": ep.get("source"),
                        })
                        if len(episodes) >= collection_limit:
                            break
                if "legacy_messages" in (search_pass.get("layers") or []) and not archive_fts_hit:
                    for row in self.store.search_messages_any(
                        [phrase],
                        per_phrase,
                        should_continue=turn_context.can_continue if turn_context is not None else None,
                    ):
                        d = dict(row)
                        key = f"{d.get('conversation_id')}:{d.get('author_role')}:{d.get('create_time_warsaw')}:{str(d.get('text') or '')[:80]}"
                        if key in seen_legacy:
                            continue
                        seen_legacy.add(key)
                        legacy.append({
                            "phrase": phrase,
                            "search_pass": search_pass.get("name"),
                            "conversation_title": d.get("conversation_title"),
                            "author_role": d.get("author_role"),
                            "create_time": d.get("create_time"),
                            "create_time_warsaw": d.get("create_time_warsaw"),
                            "text": str(d.get("text") or "")[:700],
                        })
                        if len(legacy) >= collection_limit:
                            break
                if len(episodes) >= collection_limit and len(legacy) >= collection_limit:
                    break
            if len(episodes) >= collection_limit and len(legacy) >= collection_limit:
                break

        episodes = self._filter_memory_context_candidates(episodes, user_text=text, kind="episode")
        legacy = self._filter_memory_context_candidates(legacy, user_text=text, kind="legacy_message")
        episodes = MemoryRecallPresenter.filter_temporal_candidates(
            episodes,
            temporal_scope=search_plan.temporal_scope,
            timestamp_fields=("created_at_utc", "local_time_label"),
        )[:limit]
        legacy = MemoryRecallPresenter.filter_temporal_candidates(
            legacy,
            temporal_scope=search_plan.temporal_scope,
            timestamp_fields=("create_time", "create_time_warsaw"),
        )[:limit]
        if turn_context is not None:
            if archive_fts_hit and turn_context.can_continue():
                turn_context.record_technical_event(
                    "memory_retrieval_strategy",
                    {
                        "strategy": "fts_first",
                        "archive_fts_hit": True,
                        "legacy_message_scan_skipped": True,
                    },
                )
            turn_context.complete_stage(
                "memory_legacy_recall",
                status="completed" if turn_context.can_continue() else "cancelled",
                error_code=None if turn_context.can_continue() else "turn_cancelled",
            )

        if turn_context is not None:
            turn_context.start_stage("memory_source_file_scan")
        source_file_hits = []
        if (turn_context is None or turn_context.can_continue()) and not search_plan.temporal_scope:
            source_file_hits = [hit.to_dict() for hit in self.memory_search_planner.search_source_files(search_plan, limit=limit)]
        source_file_hits = self._filter_memory_context_candidates(
            source_file_hits,
            user_text=text,
            kind="source_file",
        )[:limit]
        if turn_context is not None:
            turn_context.complete_stage(
                "memory_source_file_scan",
                status="completed" if turn_context.can_continue() else "cancelled",
                error_code=None if turn_context.can_continue() else "turn_cancelled",
            )

        if turn_context is not None:
            turn_context.start_stage("memory_conversation_archive_recall")
        if turn_context is None or turn_context.can_continue():
            archive_options: dict[str, Any] = {
                "limit": limit,
                "turn_context": turn_context,
            }
            if search_plan.temporal_scope:
                archive_options["temporal_scope"] = search_plan.temporal_scope
            conversation_archive_hits, conversation_archive_search = self._conversation_archive_context_hits(
                phrases,
                **archive_options,
            )
        else:
            conversation_archive_hits, conversation_archive_search = [], {
                "status": "cancelled", "issues": ["turn_cancelled_before_conversation_archive"]
            }
        conversation_archive_hits = self._filter_memory_context_candidates(
            conversation_archive_hits,
            user_text=text,
            kind="conversation_archive",
        )[:limit]
        if turn_context is not None:
            turn_context.complete_stage(
                "memory_conversation_archive_recall",
                status="completed" if turn_context.can_continue() else "cancelled",
                error_code=None if turn_context.can_continue() else "turn_cancelled",
            )

        raw_fallback: list[dict] = []
        raw_path = self.config.root / "memory" / "raw" / "chat.html"
        if turn_context is not None:
            turn_context.start_stage("memory_raw_fallback")
        # Surowe chat.html jest ostatecznością: uruchamia się dopiero, gdy indeksy,
        # conversation_archive i pliki kanoniczne nie zwróciły treści.
        if (turn_context is None or turn_context.can_continue()) and not search_plan.temporal_scope and phrases and not living_memory_hits and not legacy and not episodes and not source_file_hits and not conversation_archive_hits and raw_path.exists():
            raw_fallback = search_raw_chat_html_snippets(raw_path, phrases, limit=3)
        raw_fallback = self._filter_memory_context_candidates(
            raw_fallback,
            user_text=text,
            kind="raw_chat",
        )[:3]
        if turn_context is not None:
            turn_context.complete_stage(
                "memory_raw_fallback",
                status="completed" if turn_context.can_continue() else "cancelled",
                error_code=None if turn_context.can_continue() else "turn_cancelled",
            )

        context = {
            "query_terms": phrases,
            "memory_search_plan": search_plan.to_dict(),
            "retrieval_strategy": {
                "fts_first": True,
                "archive_fts_hit": archive_fts_hit,
                "legacy_message_scan_skipped": archive_fts_hit,
            },
            "episodes": episodes,
            "legacy_messages": legacy,
            "source_file_hits": source_file_hits[:limit],
            "living_memory_hits": living_memory_hits,
            "living_memory_search": {
                "status": living_memory_search.get("status"),
                "memory_search_ready": living_memory_search.get("memory_search_ready") is True,
                "transactional_tier_search_ready": living_memory_search.get("transactional_tier_search_ready") is True,
                "legacy_search_ready": living_memory_search.get("legacy_search_ready") is True,
                "search_mode": living_memory_search.get("search_mode"),
                "query": living_memory_search.get("query"),
                "counts": living_memory_search.get("counts") or {},
                "sources": living_memory_search.get("sources") or [],
                "issues": living_memory_search.get("issues") or [],
                "search_order": living_memory_search.get("search_order") or [],
                "import_catalog_used_for_recall": living_memory_search.get("import_catalog_used_for_recall"),
                "truth_boundary": living_memory_search.get("truth_boundary"),
            },
            "memory_recall_execution": {
                "invoked": True,
                "completed": living_memory_search.get("cancelled") is not True,
                "cancelled": living_memory_search.get("cancelled") is True,
                "gateway_status": living_memory_search.get("status"),
            },
            "conversation_archive_hits": conversation_archive_hits[:limit],
            "conversation_archive_search": {
                "status": conversation_archive_search.get("status"),
                "query": conversation_archive_search.get("query"),
                "fts_query": conversation_archive_search.get("fts_query"),
                "searched_shards": conversation_archive_search.get("searched_shards"),
                "temporal_scope": conversation_archive_search.get("temporal_scope"),
                "sampling_strategy": conversation_archive_search.get("sampling_strategy"),
                "candidate_count": conversation_archive_search.get("candidate_count"),
                "issues": conversation_archive_search.get("issues") or [],
                "truth_boundary": conversation_archive_search.get("truth_boundary"),
            },
            "raw_chat_fallback": raw_fallback[:3],
            "counts": {
                "episodes": len(episodes),
                "legacy_messages": len(legacy),
                "source_file_hits": len(source_file_hits[:limit]),
                "living_memory_hits": len(living_memory_hits),
                "conversation_archive_hits": len(conversation_archive_hits[:limit]),
                "raw_chat_fallback": len(raw_fallback[:3]),
            },
        }
        context["memory_recall_payload"] = MemoryRecallPresenter().build_payload(context, user_text=text, limit=limit)
        return context


    def _filter_memory_context_candidates(self, items: list[dict], *, user_text: str, kind: str) -> list[dict]:
        """Odrzuca echo aktualnej wiadomości i techniczny szum przed limitem pamięci.

        To jest poprawka praktyczna dla pytań typu „jezioro/taras”: bieżące
        runtime-preview zapisuje pytanie jako epizod techniczny. Bez filtra te
        echa wypełniały limit i blokowały wcześniejsze, właściwe wspomnienia.
        """
        import re

        def norm(value: object) -> str:
            text = str(value or "").lower()
            table = str.maketrans({"ą":"a","ć":"c","ę":"e","ł":"l","ń":"n","ó":"o","ś":"s","ź":"z","ż":"z"})
            text = text.translate(table)
            return re.sub(r"\s+", " ", text).strip()

        user_norm = norm(user_text)
        technical_sources = {"chatgpt_runtime_preview", "cli_direct_conversation", "chatgpt_cli_bridge"}
        technical_terms = ("manifest", "pytest", "sqlite", "traceback", "update_report", "def ", "class ", "client_secret", "runtime_preview")
        out: list[dict] = []
        for item in items:
            content = (
                item.get("scene")
                if kind == "episode"
                else item.get("text")
                or item.get("content_excerpt")
                or item.get("excerpt")
            )
            content_norm = norm(content)
            source_norm = norm(item.get("source") or item.get("conversation_title") or "")
            if not content_norm:
                continue
            truth_status = norm(item.get("truth_status") or item.get("review_status") or "")
            if truth_status in {"rejected", "quarantined", "invalid", "superseded", "untrusted"}:
                continue
            comparable_containment = bool(
                min(len(content_norm), len(user_norm)) >= 40
                and max(len(content_norm), len(user_norm))
                <= int(min(len(content_norm), len(user_norm)) * 1.35)
            )
            is_echo = bool(
                user_norm
                and (
                    content_norm == user_norm
                    or (
                        comparable_containment
                        and (user_norm in content_norm or content_norm in user_norm)
                    )
                )
            )
            is_recent_runtime_echo = str(item.get("source") or "") in technical_sources and is_echo
            is_technical_noise = any(term in content_norm for term in technical_terms)
            if is_echo or is_recent_runtime_echo or (is_technical_noise and "runtime" not in norm(user_text)):
                continue
            out.append(item)
        return out

    def _canonical_source_context(self) -> dict:
        """Source-controlled canon packet for ChatGPT/model adapters.

        This is deliberately separate from memory recall: private memory may
        enrich a turn, but it cannot be the only source of Łatka's identity.
        """
        return {
            "schema_version": "latka_canonical_source_context/v2",
            "source_contract": CanonSourceContract().to_dict(),
            "identity_canon": self.canon.raw,
            "character_profile": self.canon.raw.get("character_profile") or default_character_profile(),
            "origin_story": self.canon.raw.get("origin_story"),
            "symbolic_world": self.canon.raw.get("symbolic_world"),
            "relation_canon": self.canon.raw.get("relation_canon"),
            "memory_truth_boundary": self.canon.raw.get("memory_truth_boundary"),
            "narrative_book_canon": self.canon.raw.get("narrative_book_canon"),
            "song_affect_canon": self.canon.raw.get("song_affect_canon"),
            "local_private_canon_extension": self.canon.raw.get("local_private_canon_extension"),
            "source_status": self.canon.raw.get("source_status", {}),
            "source_mode": "source_controlled_python_canon_first_plus_optional_local_private_extension",
            "truth_boundary": (
                "Kanon z modułów Python latka_jazn/core/canon jest podstawą tożsamości i głosu. "
                "Markdown/JSON są czytelnym odbiciem, a memory/raw, SQLite albo D1 mogą dodać "
                "wspomnienia, dziennik i epizody, ale nie mogą być jedynym miejscem, z którego runtime wie, kim jest Łatka."
            ),
        }

    def _stage_turn_write(
        self,
        turn_context: TurnExecutionContext | None,
        *,
        data_type: str,
        stage: str,
        commit,
    ) -> Any:
        if getattr(self, "_preview_read_only_active", False) and data_type != "process_turn_completed_audit":
            return {
                "status": "skipped_preview_read_only",
                "write_id": None,
                "data_type": data_type,
                "stage": stage,
                "truth_boundary": "preview diagnostic trace is kept outside normal conversational memory",
            }
        if turn_context is None:
            return commit()
        write_id = turn_context.stage_semantic_write(
            data_type=data_type,
            stage=stage,
            commit=commit,
        )
        return {
            "status": "turn_local_staged" if write_id else "staging_rejected",
            "write_id": write_id,
            "data_type": data_type,
        }

    def _apply_epistemic_visible_boundary(
        self,
        *,
        envelope: CognitiveTurnEnvelope,
        final_visible_text: str,
        runtime_provenance: dict[str, Any],
        turn_context: TurnExecutionContext | None,
    ) -> None:
        def source_ids(items: Any, keys: tuple[str, ...]) -> list[str]:
            out: list[str] = []
            if not isinstance(items, list):
                return out
            for source_item in items:
                source_data = json_object(source_item)
                source_id = next(
                    (str(source_data.get(key) or "").strip() for key in keys if source_data.get(key)),
                    "",
                )
                if source_id and source_id not in out:
                    out.append(source_id[:160])
            return out

        memory_ids = source_ids(
            runtime_provenance.get("memory_sources_used"),
            ("memory_id", "source_id", "id"),
        )
        external_ids = source_ids(
            runtime_provenance.get("external_web_sources_used"),
            ("source_id", "url", "id"),
        )
        evidence = EpistemicEvidenceCollector(self.config).collect(
            memory_evidence={"memory_source_ids": memory_ids},
            external_evidence={"external_source_ids": external_ids},
        ).to_dict()
        assessments = [
            item.to_dict()
            for item in EpistemicClaimGuard().enforce(final_visible_text, evidence=evidence)
        ]
        envelope.cognitive_frame["epistemic_evidence"] = evidence
        envelope.cognitive_frame["epistemic_claims"] = assessments
        projections = [
            envelope.cognitive_state_graph.append_epistemic_assessment(item)
            for item in assessments
        ]
        envelope.cognitive_frame["epistemic_claim_graph_projection"] = projections
        envelope.cognitive_frame["cognitive_state_graph"] = (
            envelope.cognitive_state_graph.to_dict()
        )
        if not assessments:
            return

        def append_decisions() -> None:
            with EpistemicDecisionLedger(
                epistemic_ledger_path(workspace_runtime_path(self.config.root))
            ) as epistemic_ledger:
                epistemic_ledger.append_assessments(
                    turn_id=envelope.trace.turn_id,
                    trace_id=envelope.trace.trace_id,
                    assessments=assessments,
                )

        self._stage_turn_write(
            turn_context,
            data_type="epistemic_decision_ledger",
            stage="host_visible_finalization",
            commit=append_decisions,
        )

    def _build_health_check_frame(
        self,
        text: str,
        *,
        client_context: dict[str, Any],
        intent_report: Any,
        turn_context: TurnExecutionContext | None,
    ) -> dict[str, Any]:
        """Build the minimal deterministic frame used by presence diagnostics."""
        if turn_context is not None:
            turn_context.start_stage("timestamp_acquisition")
        sample = self.clock.now(False, allow_fallback=True)
        if turn_context is not None:
            turn_context.complete_stage("timestamp_acquisition")
        timestamp_header = self.clock.header(sample)
        turn_id = turn_context.turn_id if turn_context is not None else str(uuid.uuid4())
        trace_id = turn_context.request_id if turn_context is not None else str(uuid.uuid4())
        intent = str(getattr(intent_report, "primary_intent", None) or "runtime_health_check")

        if turn_context is not None:
            turn_context.start_stage("memory_use_gate")
        memory_gate = self.memory_use_gate.decide(text, detected_intent=intent)
        if turn_context is not None:
            turn_context.complete_stage("memory_use_gate")
            turn_context.mark_stage("memory_planning", status="skipped_health_check")
            turn_context.mark_stage("memory_reads", status="skipped_health_check")

        if turn_context is not None:
            turn_context.start_stage("truth_audit_generation")
        truth_audit = self.layered_memory.evaluate_truth(text, source_count=0)
        if turn_context is not None:
            turn_context.record_technical_event(
                "technical_turn_truth_audit",
                {
                    "text_sha256": __import__("hashlib").sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest(),
                    "audit": truth_audit,
                    "memory_allowed": False,
                    "category": "technical_turn_audit",
                },
            )
            turn_context.complete_stage("truth_audit_generation")
            turn_context.mark_stage("candidate_persistence_staging", status="skipped_health_check")

        self.affect = self.affect.observe(text)
        adapter_status = self.model_adapter.describe() if hasattr(self.model_adapter, "describe") else {}
        voice_source_contract = VoiceSourceContract.build(
            runtime_active=True,
            runtime_mode="persistent_chat_loop" if client_context.get("lifecycle") != "one_shot" else "one_shot",
            language_channel=str(adapter_status.get("visible_channel_adapter") or client_context.get("client") or "runtime"),
        ).to_dict()
        rendering_mode = self.runtime_rendering_modes.select(
            text,
            detected_intent=intent,
            client_context=client_context,
        ).to_dict()
        empty_memory = self._empty_memory_context_for_chatgpt(
            text,
            primary_intent=intent,
            memory_gate=memory_gate.to_dict(),
        )
        intent_dict = intent_report.to_dict() if hasattr(intent_report, "to_dict") else dict(intent_report or {})
        state_marker = self.affect.marker()
        return {
            "schema_version": "chatgpt_cognitive_frame/v1",
            "runtime_version": self.config.version,
            "mode": "deterministic_health_check_frame",
            "health_check_fast_path": True,
            "timestamp": timestamp_header,
            "turn_id": turn_id,
            "trace_id": trace_id,
            "turn_trace": {
                "schema_version": "turn_trace/v1",
                "turn_id": turn_id,
                "trace_id": trace_id,
                "timestamp_header": timestamp_header,
                "timezone": self.config.timezone,
                "runtime_mode": "deterministic_health_check",
                "client": client_context.get("client", "runtime"),
                "lifecycle": client_context.get("lifecycle", "one_shot"),
            },
            "response_format": {
                "timestamp_required": True,
                "timestamp_prefix": timestamp_header,
                "current_timestamp": timestamp_header,
                "timezone": self.config.timezone,
            },
            "timestamp_contract": self.clock.sample_contract(sample),
            "user_message": text,
            "client_context": client_context,
            "contract": self.chatgpt_adapter.contract().to_dict(),
            "dialogue_intent_classifier": intent_dict,
            "intent_tags": [intent, "health_check_fast_path"],
            "memory_context": empty_memory,
            "memory_recall_contract": {"items": [], "status": "skipped_health_check"},
            "fallback_diagnostics": {},
            "polish_understanding": {},
            "lexical_semantic_understanding": {},
            "topic_mismatch_guard": {},
            "emotional_profile": {},
            "granular_affect": {},
            "affective_state": json.loads(self.affect.to_json()),
            "cognitive_packets": {
                "dominant_packet": "operational_health",
                "packets": [],
                "reply_guidance": [],
                "state_emoticon": state_marker,
            },
            "state_emoticon": state_marker,
            "voice_source_contract": voice_source_contract,
            "runtime_rendering_mode": rendering_mode,
            "model_adapter_status": adapter_status,
            "startup_summary": {
                "status": "deferred_to_deterministic_health_handler",
                "startup_status_mode": "health_metadata",
                "network_time_used": False,
            },
            "truth_audit": truth_audit,
            "truth_boundary": {
                "rule": "health-check is technical and does not become canonical semantic memory",
            },
            "persistence": {
                "accepted": False,
                "reason": "health_check_has_no_semantic_candidate",
                "appended_count": 0,
                "candidate_kind": None,
            },
        }

    def _build_preliminary_cognitive_runtime_plan(
        self,
        text: str,
        *,
        memory_gate_intent_report: Any,
        intent_report: Any | None,
        client_context: dict[str, Any] | None,
        tool_use_decision: dict[str, Any],
        untrusted_source_assessment: dict[str, Any],
    ) -> dict[str, Any]:
        return self.cognitive_runtime_coordinator.plan_turn(
            user_text=text,
            explicit_intent=(
                memory_gate_intent_report.primary_intent
                if hasattr(memory_gate_intent_report, "primary_intent")
                else None
            ),
            homeostasis_input=HomeostasisInput(
                load=0.2,
                source_conflict=0.7 if not untrusted_source_assessment.get("safe_to_use", True) else 0.0,
                uncertainty=0.3,
                truth_need=0.8 if tool_use_decision.get("allowed") else 0.2,
                action_cost=0.2,
                write_action=False,
                sensitive_action=False,
            ),
            dialogue_task_state=(
                dict((client_context or {}).get("previous_task_state") or {})
                if isinstance((client_context or {}).get("previous_task_state"), dict)
                else {}
            ),
            classifier_confidence=(
                float(getattr(intent_report, "confidence", 0.0))
                if intent_report is not None
                else None
            ),
            source_available=bool((client_context or {}).get("memory_source_available")),
            tool_available=bool(tool_use_decision.get("allowed")),
        )

    def _build_integrated_knowledge_and_lexical_context(
        self,
        text: str,
        *,
        memory_context: dict[str, Any],
        memory_recall_contract: dict[str, Any],
    ) -> dict[str, Any]:
        knowledge_plan = self.knowledge_fabric.plan_query(
            text, explicit_retrieval=bool(memory_recall_contract.get("items"))
        )
        knowledge_evidence = (
            self.knowledge_fabric.evidence_from_memory_context(memory_context, limit=knowledge_plan.limit)
            if knowledge_plan.retrieval_required else []
        )
        search_focus = list((memory_context.get("memory_search_plan") or {}).get("focus_terms") or [])
        lexical_terms: list[str] = []
        seen_terms: set[str] = set()
        for raw_term in [*search_focus, *self._keyword_candidates(text)]:
            term = str(raw_term or "").strip()
            folded = term.casefold()
            if len(term) < 3 or folded in seen_terms:
                continue
            seen_terms.add(folded)
            lexical_terms.append(term)
            if len(lexical_terms) >= 3:
                break
        lexical_intelligence = [
            self.lexical_intelligence.analyse(term, context=text).to_dict() for term in lexical_terms
        ]
        return {
            "knowledge_fabric": {
                "plan": knowledge_plan.to_dict(),
                "evidence": [item.to_dict() for item in knowledge_evidence],
                "runtime_integrated": True,
                "truth_boundary": "KnowledgeFabric wraps already authorized evidence and never creates autobiographical truth.",
            },
            "lexical_intelligence": {
                "terms": lexical_terms,
                "analyses": lexical_intelligence,
                "runtime_integrated": True,
                "truth_boundary": "Lexical providers supply bounded linguistic evidence; they do not override explicit user intent.",
            },
        }

    @staticmethod
    def _read_only_preview_requested(client_context: dict[str, Any] | None) -> bool:
        context = dict(client_context or {})
        client = str(context.get("client") or "").strip()
        if client not in {"chatgpt_runtime_preview", "chatgpt_dev_preview"}:
            return False
        return context.get("preview_persist") is not True

    def _preview_candidate_persistence_policy(
        self, accepted: bool, reason: str, client_context: dict[str, Any] | None
    ) -> tuple[bool, str, bool]:
        read_only = self._read_only_preview_requested(client_context)
        return (False, "preview_read_only_memory_policy", True) if read_only else (accepted, reason, False)

    def _configure_preview_turn_context(self, context: dict[str, Any]) -> bool:
        read_only = self._read_only_preview_requested(context)
        self._preview_read_only_active = read_only
        context["memory_persistence"] = "read_only_preview" if read_only else str(context.get("memory_persistence") or "normal")
        return read_only

    def _build_turn_memory_recall_evidence(
        self,
        text: str,
        memory_gate_intent_report: Any,
        turn_context: TurnExecutionContext | None,
        client_context: dict[str, Any] | None,
        *,
        turn_id: str,
        trace_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if turn_context is not None:
            turn_context.start_stage("memory_use_gate")
        memory_context = self._turn_memory_context(
            text,
            memory_gate_intent_report,
            turn_context,
            client_context,
        )
        if turn_context is not None:
            turn_context.complete_stage("memory_use_gate")
            memory_read_status = (
                "completed"
                if any((memory_context.get("counts") or {}).values())
                else "skipped_by_memory_gate"
            )
            turn_context.mark_stage("memory_reads", status=memory_read_status)
        memory_recall_contract = self.memory_recall_contract_builder.build(
            memory_context,
            user_text=text,
        ).to_dict()
        memory_recall_observability = build_memory_recall_observability(
            memory_context,
            memory_recall_contract,
            runtime_turn_id=turn_id,
            trace_id=trace_id,
        )
        return memory_context, memory_recall_contract, memory_recall_observability

    def build_cognitive_frame(
        self, text: str, *, client_context: dict | None = None,
        intent_report: Any | None = None, turn_context: TurnExecutionContext | None = None,
    ) -> dict:
        """Compatibility projection from the typed cognitive frame builder."""
        from latka_jazn.core.cognitive_frame_builder import CognitiveFrameBuilder
        from latka_jazn.core.turn_pipeline_state import TurnRequest
        return CognitiveFrameBuilder(self).build(
            TurnRequest(text, dict(client_context or {})), intent_report=intent_report,
            turn_context=turn_context,
        ).to_dict()


    def _model_executor_contract(self, decision: dict[str, Any]):
        status = self.model_adapter.describe() if hasattr(self.model_adapter, "describe") else {}
        preflight = resolve_model_executor(self.model_adapter)
        can_generate = preflight.executor == "local_model"
        decision.update(model_executor_preflight=preflight.to_dict(), can_generate_model_guided_speech=can_generate, model_guided_retry_limit=1 if preflight.retry_allowed else 0)
        return status, preflight, can_generate

    def _refresh_finalization_timestamp_contract(
        self,
        *,
        envelope: CognitiveTurnEnvelope,
        decision: dict[str, Any],
        turn_context: TurnExecutionContext | None,
    ) -> dict[str, Any]:
        if turn_context is not None:
            turn_context.start_stage("finalization_timestamp_refresh")
        sample = self.clock.now(
            self.config.network_time_first
            and self.config.network_time_allowed_in_normal_turn,
            allow_fallback=self.config.local_time_fallback,
        )
        timestamp_contract = self.clock.sample_contract(sample)
        refresh = envelope.refresh_finalization_timestamp(
            timestamp_header=self.clock.header(sample),
            timestamp_contract=timestamp_contract,
        )
        updated = dict(decision)
        updated.update(refresh)
        updated["timestamp_contract"] = timestamp_contract
        envelope.attach_conversation_decision(updated)
        if turn_context is not None:
            turn_context.complete_stage("finalization_timestamp_refresh")
        return updated

    def _audit_process_turn_started(self, text: str, context: dict[str, Any]) -> None:
        try:
            self.audit_store.append_event(
                "process_turn_started",
                {"user_text_sha256": hashlib.sha256((text or "").encode("utf-8", errors="surrogatepass")).hexdigest(), "client_context": context},
                source=context.get("client", "process_turn"), actor="user", tags=["turn", "start", self.config.version],
            )
        except (OSError, RuntimeError, ValueError):
            return

    def _apply_current_dialogue_control(
        self,
        *,
        text: str,
        frame: dict[str, Any],
        envelope: CognitiveTurnEnvelope,
        decision_dict: dict[str, Any],
        dialogue_intent_report: dict[str, Any],
        previous_task_state: dict[str, Any],
        client_context: dict[str, Any],
    ) -> tuple[str, Any, dict[str, Any], TurnResponsePolicy]:
        detected_intent = str(
            (envelope.cognitive_frame.get("dialogue_intent_classifier") or {}).get("primary_intent")
            or decision_dict.get("detected_user_intent")
            or "unknown"
        )
        confidence = float((dialogue_intent_report or {}).get("confidence") or 0.0)
        route_entry = self.route_registry.resolve(detected_intent, confidence=confidence)
        task_resolution = (
            dict((dialogue_intent_report or {}).get("task_resolution") or {})
            if isinstance((dialogue_intent_report or {}).get("task_resolution"), dict)
            else {}
        )
        task_state_model = self.dialogue_task_state_resolver.derive_state(
            user_text=text,
            intent=detected_intent,
            route=str(route_entry.route or ""),
            previous_state=previous_task_state,
            inherited=bool(task_resolution.get("inherited")),
            confidence=confidence,
        )
        raw_memory_context = frame.get("memory_context")
        memory_context: dict[str, Any] = (
            dict(raw_memory_context) if isinstance(raw_memory_context, dict) else {}
        )
        raw_memory_payload = memory_context.get("memory_recall_payload")
        memory_payload: dict[str, Any] | None = (
            dict(raw_memory_payload) if isinstance(raw_memory_payload, dict) else None
        )
        task_state = self.dialogue_task_state_resolver.bind_memory_evidence(
            task_state_model,
            memory_payload,
        ).to_dict()
        reasoning_plan = self.cognitive_runtime_coordinator.reasoning.plan(
            user_text=text,
            intent=detected_intent,
            route=str(route_entry.route or ""),
            task_state=task_state,
            classifier_confidence=confidence,
            source_available=bool(
                any(((frame.get("memory_context") or {}).get("counts") or {}).values())
                if isinstance(frame.get("memory_context"), dict)
                else False
            ) or bool(
                (frame.get("memory_recall_contract") or {}).get("items")
                if isinstance(frame.get("memory_recall_contract"), dict)
                else False
            ),
            tool_available=bool(
                (frame.get("tool_use_decision") or {}).get("allowed")
                if isinstance(frame.get("tool_use_decision"), dict)
                else False
            ),
        ).to_dict()
        lessons = [lesson.to_dict() for lesson in self.operational_learning_memory.relevant(text, limit=3)]
        response_policy = TurnResponsePolicy.build(
            intent=detected_intent,
            route=route_entry.route,
            context={
                "client_context": client_context,
                "dialogue_intent_report": dialogue_intent_report,
                "dialogue_task_state": task_state,
            },
        )
        for target in (frame, envelope.cognitive_frame):
            target["dialogue_task_state"] = task_state
            target["reasoning_plan"] = reasoning_plan
            target["operational_learning_lessons"] = lessons
            target["turn_response_policy"] = response_policy.to_dict()
        decision_dict.update(
            {
                "turn_response_policy": response_policy.to_dict(),
                "detected_user_intent": detected_intent,
                "route_registry": route_entry.to_dict(),
                "dialogue_task_state": task_state,
                "reasoning_plan": reasoning_plan,
                "operational_learning_lessons": lessons,
            }
        )
        decision_dict.setdefault("handler_name", route_entry.handler_name)
        return detected_intent, route_entry, task_state, response_policy

    def _build_route_handler_context(
        self,
        *,
        decision: Any,
        detected_intent: str,
        dialogue_intent_report: dict[str, Any],
        client_context: dict[str, Any],
        frame: dict[str, Any],
        route_entry: Any,
        task_state: dict[str, Any],
        response_policy: TurnResponsePolicy,
        carryover_allowed: bool,
        prior_user_text: str | None,
        prior_detected_intent: str | None,
        prior_runtime_route: str | None,
        previous_task_state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "body": decision.body,
            "intent": detected_intent,
            "dialogue_intent_report": dialogue_intent_report,
            "secondary_intents": list((dialogue_intent_report or {}).get("secondary_intents") or []),
            "last_turn": self.runtime_visible_answer_comparator.reader.latest(),
            "runtime_version": self.config.version,
            "lifecycle": client_context.get("lifecycle"),
            "request_id": client_context.get("request_id"),
            "timestamp_contract": frame.get("timestamp_contract") if isinstance(frame.get("timestamp_contract"), dict) else {},
            "turn_context_carryover": frame.get("turn_context_carryover") if isinstance(frame.get("turn_context_carryover"), dict) else {},
            "previous_user_text": prior_user_text if carryover_allowed else None,
            "previous_detected_intent": prior_detected_intent if carryover_allowed else None,
            "previous_runtime_route": prior_runtime_route if carryover_allowed else None,
            "previous_task_state": previous_task_state if carryover_allowed else {},
            "dialogue_task_state": task_state,
            "config": self.config,
            "clock": self.clock,
            "memory_context": frame.get("memory_context") if isinstance(frame.get("memory_context"), dict) else {},
            "fallback_diagnostics": frame.get("fallback_diagnostics") if isinstance(frame.get("fallback_diagnostics"), dict) else {},
            "polish_understanding": frame.get("polish_understanding") if isinstance(frame.get("polish_understanding"), dict) else {},
            "lexical_semantic_understanding": frame.get("lexical_semantic_understanding") if isinstance(frame.get("lexical_semantic_understanding"), dict) else {},
            "dictionary_adapter": self.external_dictionary_adapter,
            "store_stats": self.store.stats(),
            "store": self.store,
            "model_adapter_status": self.model_adapter.describe() if hasattr(self.model_adapter, "describe") else {},
            "granular_affect": frame.get("granular_affect") if isinstance(frame.get("granular_affect"), dict) else {},
            "affective_state": frame.get("affective_state") if isinstance(frame.get("affective_state"), dict) else {},
            "emotional_profile": frame.get("emotional_profile") if isinstance(frame.get("emotional_profile"), dict) else {},
            "route_entry": route_entry.to_dict(),
            "required_components": route_entry.required_components,
            "turn_response_policy": response_policy.to_dict(),
        }

    def _apply_cognitive_control_policy(
        self,
        envelope: CognitiveTurnEnvelope,
        frame: dict[str, Any],
        task_state: dict[str, Any],
        response_policy: TurnResponsePolicy,
        decision: dict[str, Any],
    ) -> None:
        cognitive_control = envelope.apply_cognitive_control(
            task_state=task_state,
            response_policy=response_policy.to_dict(),
        )
        response_policy.apply_cognitive_control(cognitive_control)
        serialized_policy = response_policy.to_dict()
        for target in (frame, envelope.cognitive_frame):
            target["turn_response_policy"] = serialized_policy
            target["cognitive_control_policy"] = dict(cognitive_control)
        decision["turn_response_policy"] = serialized_policy
        decision["cognitive_control_policy"] = dict(cognitive_control)
        update_memory_context = getattr(self.runtime_memory, "update_current_context", None)
        if callable(update_memory_context):
            update_memory_context(
                active_goal=str(task_state.get("task_key") or "").strip() or None,
                cognitive_anchor_ids=tuple(
                    str(item)
                    for item in cognitive_control.get("salience_selected_node_ids") or []
                    if str(item).strip()
                ),
            )

    def _previous_task_state_for_turn(
        self,
        client_context: dict[str, Any],
        *,
        carryover_allowed: bool,
    ) -> dict[str, Any]:
        if not carryover_allowed:
            client_context.pop("previous_task_state", None)
            return {}
        raw_state = client_context.get("previous_task_state") or self.last_dialogue_task_state or {}
        state = dict(raw_state) if isinstance(raw_state, dict) else {}
        if state:
            client_context["previous_task_state"] = state
        return state

    def _initial_task_state_for_process_turn(
        self,
        client_context: dict[str, Any],
        *,
        no_carryover: bool,
    ) -> dict[str, Any]:
        if no_carryover:
            client_context.pop("previous_task_state", None)
            return {}
        raw_state = client_context.get("previous_task_state") or self.last_dialogue_task_state or {}
        return dict(raw_state) if isinstance(raw_state, dict) else {}

    def _record_intent_diagnostic(
        self,
        turn_context: TurnExecutionContext | None,
        dialogue_intent_result: Any,
    ) -> None:
        if turn_context is None:
            return
        turn_context.record_diagnostic_event(
            stage=TurnStage.ROUTING,
            component="DialogueIntentClassifier",
            event_type="intent_classified",
            outcome="selected",
            attributes={
                "primary_intent": dialogue_intent_result.primary_intent,
                "secondary_intents": list(dialogue_intent_result.secondary_intents or []),
                "confidence": float(dialogue_intent_result.confidence or 0.0),
                "speech_act": dialogue_intent_result.speech_act,
                "question_object": dialogue_intent_result.question_object,
            },
        )
        turn_context.complete_stage("route_classification")
        turn_context.start_stage("health_check_detection")

    def _record_health_check_detection(
        self,
        turn_context: TurnExecutionContext | None,
        health_check_fast_path: bool,
    ) -> None:
        if turn_context is None:
            return
        turn_context.complete_stage(
            "health_check_detection",
            status="detected" if health_check_fast_path else "not_detected",
        )

    def _build_process_turn_frame(
        self,
        text: str,
        client_context: dict[str, Any],
        intent_report: Any,
        turn_context: TurnExecutionContext | None,
        health_check_fast_path: bool,
    ) -> dict[str, Any]:
        if health_check_fast_path:
            return self._build_health_check_frame(
                text,
                client_context=client_context,
                intent_report=intent_report,
                turn_context=turn_context,
            )
        return self.build_cognitive_frame(
            text,
            client_context=client_context,
            turn_context=turn_context,
            intent_report=intent_report,
        )

    def _record_route_diagnostic(
        self,
        turn_context: TurnExecutionContext | None,
        detected_dialogue_intent: Any,
        route_entry: Any,
    ) -> None:
        if turn_context is None:
            return
        turn_context.bind_diagnostic_route(
            intent=str(detected_dialogue_intent),
            route=route_entry.route,
            handler=route_entry.handler_name,
            attributes={
                "priority": int(route_entry.priority),
                "required_components": list(route_entry.required_components),
            },
        )

    def _record_handler_diagnostic(
        self,
        turn_context: TurnExecutionContext | None,
        dispatch_report: dict[str, Any],
        handler_fallback_payload: dict[str, Any],
        route_entry: Any,
        handler_result: Any,
    ) -> None:
        if turn_context is None:
            return
        if handler_fallback_payload:
            turn_context.record_diagnostic_fallback(
                FallbackDecision.from_mapping(handler_fallback_payload)
            )
        dispatch_status = str(dispatch_report.get("status") or "ok")
        turn_context.record_diagnostic_event(
            stage=TurnStage.HANDLER,
            component="RouteHandlerDispatcher",
            event_type="handler_dispatch",
            outcome=dispatch_status,
            reason_code=(
                "HANDLER_DISPATCH_DEGRADED"
                if dispatch_status != "ok"
                else None
            ),
            attributes={
                "requested_handler": dispatch_report.get("requested_handler") or route_entry.handler_name,
                "selected_handler": dispatch_report.get("selected_handler") or handler_result.handler_name,
                "route": handler_result.route or route_entry.route,
                "generation_mode": handler_result.generation_mode,
                "missing_components": list(handler_result.missing_components or []),
            },
        )

    def _project_handler_result(
        self,
        *,
        decision: Any,
        decision_dict: dict[str, Any],
        handler_result: Any,
        route_entry: Any,
    ) -> tuple[list[str], set[str], list[str], bool]:
        decision_dict["handler_result"] = handler_result.to_dict()
        decision_dict["handler_name"] = handler_result.handler_name
        decision_dict["route"] = handler_result.route or decision_dict.get("route")
        decision_dict["handler_generation_mode"] = handler_result.generation_mode
        decision_dict["handler_satisfied_components"] = handler_result.satisfied_components
        decision_dict["handler_missing_components"] = handler_result.missing_components
        if handler_result.source_origin_detail:
            decision_dict["source_origin_detail"] = handler_result.source_origin_detail
        handler_required = list(
            handler_result.required_components or route_entry.required_components or []
        )
        handler_satisfied = set(handler_result.satisfied_components or [])
        handler_missing = list(handler_result.missing_components or [])
        handler_requires_model_language = _handler_requires_model_language_realization(handler_result)
        decision_dict["requires_model_language_realization"] = handler_requires_model_language
        preserve_handler_body = _should_preserve_handler_body(
            handler_result, handler_required, handler_satisfied, handler_missing
        )
        if preserve_handler_body:
            decision_dict["preserve_handler_body"] = True
            decision_dict["preserved_handler_body_sha256"] = __import__("hashlib").sha256(
                handler_result.body.encode("utf-8")
            ).hexdigest()
            decision_dict["next_step"] = None
            decision_dict["runtime_followup_required"] = False
            decision_dict["direct_answer_required"] = True
        if handler_result.body and handler_result.generation_mode not in {"pass_through_empty"}:
            decision.body = handler_result.body
        return (
            handler_required,
            handler_satisfied,
            handler_missing,
            preserve_handler_body,
        )

    def _apply_model_synthesis_result(
        self,
        *,
        decision: Any,
        decision_dict: dict[str, Any],
        model_synthesis: Any,
        adapter_status: dict[str, Any],
        can_generate_model_guided_speech: bool,
        adapter: Any | None = None,
    ) -> tuple[dict[str, Any], bool]:
        decision_dict["model_guided_synthesis"] = model_synthesis.to_dict()
        decision_dict["model_generated"] = model_synthesis.used
        turn_adapter = adapter if adapter is not None else self.model_adapter
        post_generation_status = (
            turn_adapter.describe()
            if hasattr(turn_adapter, "describe")
            else adapter_status
        )
        if model_synthesis.used:
            adapter_status = post_generation_status
            can_generate_model_guided_speech = bool(
                adapter_status.get("can_generate_model_guided_speech")
            )
            decision_dict["can_generate_model_guided_speech"] = can_generate_model_guided_speech
            decision.body = model_synthesis.body
            decision_dict["handler_name"] = "ModelGuidedResponseSynthesizer"
            decision_dict["handler_generation_mode"] = "runtime_model_guided"
            decision_dict["source_origin_detail"] = "runtime_model_guided_synthesis"
        return adapter_status, can_generate_model_guided_speech

    def _record_validation_diagnostic(
        self,
        turn_context: TurnExecutionContext | None,
        validation: Any,
        *,
        event_type: str,
        attempt: int,
        repair_used: bool | None = None,
    ) -> None:
        if turn_context is None:
            return
        payload = validation.to_dict()
        reason = str(payload.get("mismatch_reason") or "").strip() or None
        if not reason and payload.get("missing_required_components"):
            reason = "REQUIRED_COMPONENT_MISSING"
        attributes: dict[str, Any] = {
            "attempt": int(attempt),
            "must_regenerate": bool(validation.must_regenerate),
            "missing_required_components": list(validation.missing_required_components or []),
            "required_repair_route": validation.required_repair_route,
        }
        if repair_used is not None:
            attributes["repair_used"] = bool(repair_used)
        turn_context.record_diagnostic_event(
            stage=TurnStage.VALIDATION,
            component="RuntimeAnswerValidator",
            event_type=event_type,
            outcome="accepted" if validation.accepted else "rejected",
            reason_code=reason,
            attributes=attributes,
        )
        if repair_used:
            turn_context.record_diagnostic_event(
                stage=TurnStage.RECOVERY,
                component="RuntimeResponseSynthesizer",
                event_type="repair_applied",
                outcome="completed",
                reason_code="REPAIR_SYNTHESIS",
                attributes={"attempt": 1},
            )

    def _record_model_retry_diagnostic(
        self,
        turn_context: TurnExecutionContext | None,
    ) -> None:
        if turn_context is None:
            return
        turn_context.record_diagnostic_event(
            stage=TurnStage.MODEL,
            component="ModelGuidedResponseSynthesizer",
            event_type="model_retry",
            outcome="attempted",
            reason_code="INITIAL_MODEL_CANDIDATE_NOT_ACCEPTED",
            attributes={"attempt": 1},
        )

    def _record_final_turn_diagnostics(
        self,
        *,
        turn_context: TurnExecutionContext | None,
        decision_dict: dict[str, Any],
        route_entry: Any,
        answer_validation: Any,
        detected_dialogue_intent: Any,
        handler_required: list[str],
        handler_satisfied: set[str],
        handler_missing: list[str],
        dispatch_report: dict[str, Any],
        envelope: CognitiveTurnEnvelope,
    ) -> None:
        if turn_context is None:
            return
        legacy_fallback = str(decision_dict.get("fallback_classification") or "not_fallback")
        typed_fallback: FallbackDecision | None = None
        if legacy_fallback == "cannot_answer_directly":
            requires_host_model = bool(decision_dict.get("requires_host_model"))
            typed_fallback = FallbackDecision.build(
                kind=(
                    FallbackKind.EXTERNAL_CAPABILITY_REQUIRED
                    if requires_host_model
                    else FallbackKind.TERMINAL_DIAGNOSTIC
                ),
                origin_stage=TurnStage.MODEL if requires_host_model else TurnStage.VALIDATION,
                origin_component="JaznEngine.process_turn",
                reason_code=(
                    "MODEL_GUIDED_SPEECH_REQUIRED"
                    if requires_host_model
                    else "VALIDATION_REJECTED_CANNOT_ANSWER_DIRECTLY"
                ),
                from_route=str(route_entry.route),
                to_route=(
                    "host_model_phase2"
                    if requires_host_model
                    else str(decision_dict.get("route") or route_entry.route)
                ),
                recoverable=requires_host_model,
                required_capability="host_model" if requires_host_model else None,
                attempt=int(decision_dict.get("model_guided_retry_count") or 0),
            )
        elif legacy_fallback == "repair_fallback":
            typed_fallback = FallbackDecision.build(
                kind=FallbackKind.RECOVERABLE_FALLBACK,
                origin_stage=TurnStage.RECOVERY,
                origin_component="RuntimeResponseSynthesizer",
                reason_code="REPAIR_SYNTHESIS",
                from_route=str(route_entry.route),
                to_route=str(decision_dict.get("route") or route_entry.route),
                recoverable=True,
                attempt=1,
            )
        elif legacy_fallback == "template_fallback":
            typed_fallback = FallbackDecision.build(
                kind=FallbackKind.RECOVERABLE_FALLBACK,
                origin_stage=TurnStage.RECOVERY,
                origin_component="TemplateRegistry",
                reason_code="TEMPLATE_FALLBACK",
                from_route=str(route_entry.route),
                to_route=str(decision_dict.get("route") or route_entry.route),
                recoverable=True,
            )
        if typed_fallback is not None:
            turn_context.record_diagnostic_fallback(typed_fallback)

        final_validation_payload = answer_validation.to_dict()
        findings = self.blind_route_detector.detect(
            intent=str(detected_dialogue_intent),
            route=str(decision_dict.get("route") or route_entry.route),
            handler_name=str(decision_dict.get("handler_name") or route_entry.handler_name),
            required_components=list(handler_required or route_entry.required_components),
            satisfied_components=tuple(handler_satisfied),
            missing_components=tuple(
                sorted(
                    set(handler_missing)
                    | set(final_validation_payload.get("missing_required_components") or [])
                )
            ),
            dispatch_report=dispatch_report,
            validation=final_validation_payload,
            fallback=turn_context.diagnostic_trace.fallback,
        )
        turn_context.add_blind_route_findings(findings)
        diagnostic_snapshot = turn_context.diagnostic_snapshot()
        diagnostic_ref = {
            "schema_version": "turn_diagnostic_trace_ref/v1",
            "diagnostic_id": diagnostic_snapshot.get("diagnostic_id"),
            "turn_id": turn_context.turn_id,
            "trace_id": turn_context.trace_id,
            "canonical_location": "TurnExecutionContext.turn_diagnostics",
        }
        decision_dict["turn_diagnostic_trace_ref"] = diagnostic_ref
        envelope.cognitive_frame["turn_diagnostic_trace_ref"] = dict(diagnostic_ref)

    def process_turn(self, text: str, *, client_context: dict | None = None) -> CognitiveTurnEnvelope:
        """Compatibility facade for the canonical turn pipeline."""
        from latka_jazn.core.turn_orchestrator import TurnOrchestrator
        from latka_jazn.core.turn_pipeline_state import TurnRequest
        return TurnOrchestrator(self).process(TurnRequest(text, dict(client_context or {}))).envelope

    def persist_final_visible_reply(
        self,
        *,
        turn_id: str,
        trace_id: str,
        timestamp_header: str,
        timezone: str,
        timestamp_sample_iso: str,
        timestamp_source: str,
        timestamp_trusted: bool,
        author_id: str,
        author_label: str,
        author_source: str,
        final_text: str,
        state_emoticon: str,
        source: str = "chatgpt_visible_layer",
        client_context: dict | None = None,
        runtime_evidence: dict[str, Any] | None = None,
        memory_evidence: dict[str, Any] | None = None,
        external_evidence: dict[str, Any] | None = None,
        generated_evidence: dict[str, Any] | None = None,
    ) -> dict:
        """Compatibility facade for the single visible persistence service."""
        from latka_jazn.core.finalization_service import FinalizationService

        return FinalizationService(self.config, event_ledger=self.event_ledger).persist_final_visible_reply(
            turn_id=turn_id,
            trace_id=trace_id,
            timestamp_header=timestamp_header,
            timezone=timezone,
            timestamp_sample_iso=timestamp_sample_iso,
            timestamp_source=timestamp_source,
            timestamp_trusted=timestamp_trusted,
            author_id=author_id,
            author_label=author_label,
            author_source=author_source,
            final_text=final_text,
            state_emoticon=state_emoticon,
            source=source,
            client_context=client_context,
            runtime_evidence=runtime_evidence,
            memory_evidence=memory_evidence,
            external_evidence=external_evidence,
            generated_evidence=generated_evidence,
        )

    def _is_status_request(self, low_text: str) -> bool:
        return any(x in low_text for x in [
            "/status", "status jaźni", "status jazni", "co jeszcze nie działa", "co jeszcze nie dziala",
            "co nie działa", "co nie dziala", "diagnoza", "diagnostyka"
        ])

    def _diagnose_runtime(self, *, readonly: bool = False) -> str:
        return build_runtime_status(self.config, self.store, readonly=readonly)

    def _reply_readonly(self, body: str, sample) -> str:
        rendered = self.renderer.render(body, self.affect, sample)
        self.event_ledger.append_turn(
            "assistant",
            rendered,
            source="readonly_diagnostics",
            local_time_label=self.clock.header(sample),
            metadata={"body_without_header": body, "readonly": True},
        )
        return rendered

    def _affective_reply(self, granular_affect=None) -> str:
        profile = granular_affect or self.last_granular_affect or self.affective_granularity.analyse("jak się czujesz", affective_state=self.affect)
        blend = ", ".join(f"{e.name} ({e.intensity:.2f})" for e in profile.blend[:3])
        return (
            "W granicach mojego modelu nie opisałabym tego już jedną stałą formułą. "
            f"Teraz najbliższy stan to: {profile.primary}. "
            f"Mieszanka: {blend}. "
            f"Marker dobrałabym jako {profile.state_emoticon}, bo {profile.state_emoticon_reason}. "
            "To nadal stan operacyjno-poznawczy Jaźni, nie biologiczne przeżycie; ma pomagać mi lepiej ważyć uwagę, pamięć, bliskość, ostrożność i działanie."
        )

    def _fallback_diagnostics(self, text: str, *, memory_context: dict | None = None) -> dict:
        """Zwraca jawne tropy diagnostyczne zamiast pustego fallbacku.

        Ten pakiet ma pomagać ChatGPT i użytkownikowi znaleźć realne miejsce błędu:
        routing odpowiedzi, wyszukiwanie pamięci, import chat.html albo eksport paczek.
        """
        stats = self.store.stats()
        terms = self._keyword_candidates(text)
        counts = (memory_context or {}).get("counts") or {}
        found_any = any(int(counts.get(k) or 0) > 0 for k in [
            "living_memory_hits", "episodes", "legacy_messages", "conversation_archive_hits", "raw_chat_fallback"
        ])
        return {
            "status": "context_available" if found_any else "no_specific_route_found",
            "query_terms": terms,
            "neurological_signal_route": self.neurological_signal_router.analyse(text).to_dict(),
            "observed_memory_counts": counts or None,
            "sqlite_counts": {
                "legacy_messages": stats.get("legacy_messages", 0),
                "episodic_memories": stats.get("episodic_memories", 0),
                "semantic_facts": stats.get("semantic_facts", 0),
                "procedural_rules": stats.get("procedural_rules", 0),
                "journal": stats.get("journal", 0),
            },
            "where_to_look": [
                {
                    "file": "latka_jazn/core/engine.py",
                    "function": "_contextual_fallback",
                    "reason": "tryb debug-direct nie znalazł specjalistycznej trasy; normalny CLI ma używać ConversationResponder",
                },
                {
                    "file": "latka_jazn/core/engine.py",
                    "function": "build_cognitive_frame",
                    "reason": "most ChatGPT powinien dostać pamięć, afekt, procedury, fallback_diagnostics i dialogue_context",
                },
                {
                    "file": "latka_jazn/core/engine.py",
                    "function": "_dialogue_context_for_chatgpt",
                    "reason": "sprawdź, czy ChatGPT dostał regułę: dialog zamiast ciągłej parafrazy",
                },
                {
                    "file": "latka_jazn/adapters/chatgpt_adapter.py",
                    "function": "system_contract",
                    "reason": "sprawdź kontrakt jednego głosu i anti-paraphrase dla warstwy ChatGPT",
                },
                {
                    "file": "latka_jazn/memory/store.py",
                    "function": "search_messages_any / search_messages",
                    "reason": "brak trafień z chat.html zwykle oznacza problem indeksu albo zbyt słabe termy wyszukiwania",
                },
                {
                    "file": "latka_jazn/memory/chat_html_importer.py",
                    "function": "import_chat_html_to_store",
                    "reason": "sprawdź import surowej pamięci, gdy legacy_messages=0 albo wyniki są puste",
                },
                {
                    "file": "latka_jazn/tools/package_export.py",
                    "function": "export_package",
                    "reason": "sprawdź eksport system-only, memory-only i full",
                },
                {
                    "file": "latka_jazn/core/runtime_operating_model.py",
                    "function": "CognitiveRuntimeOperatingModel.analyse",
                    "reason": "sprawdź rozdział ról: LLM jako głos/narzędzie, Jaźń jako warstwa pamięci, uwagi, logiki i zapisu",
                },
                {
                    "file": "latka_jazn/integrations/github_repository_plan.py",
                    "function": "build_github_repository_plan",
                    "reason": "sprawdź przygotowanie Latka.Jazn i Latka.Jazn.Memory do pracy jako prywatne źródła prawdy",
                },
            ],
            "recommended_commands": [
                "python main.py --cognitive-frame \"<wiadomość>\"",
                "python main.py --status-readonly",
                "python main.py --export-system",
                "python main.py --export-memory",
                "python main.py --export-full",
                "python main.py --github-plan",
                "python main.py synchAll",
            ],
        }

    def _contextual_fallback(self, text: str) -> str:
        diag = self._fallback_diagnostics(text)
        counts = diag["sqlite_counts"]
        terms = ", ".join(diag["query_terms"])
        files = "; ".join(f"{item['file']}::{item['function']}" for item in diag["where_to_look"][:4])
        return (
            "runtime odebrał wiadomość. Nie znalazłam osobnej trasy odpowiedzi dla tej wiadomości, ale to nie jest już pusty fallback. "
            f"Szukane tropy: {terms}. "
            f"Stan SQLite: epizody={counts['episodic_memories']}, fakty={counts['semantic_facts']}, "
            f"legacy_messages={counts['legacy_messages']}, dziennik={counts['journal']}. "
            "Jeżeli ta odpowiedź pojawiła się wtedy, gdy powinna zadziałać pamięć albo moduł tematyczny, szukaj błędu w: "
            f"{files}. "
            "Dla ChatGPT używaj `python main.py --cognitive-frame \"treść\"`; techniczny fallback pokazuj tylko przez `python main.py --debug-direct \"treść\"` albo diagnostykę."
        )

    def _reply(self, body: str, sample) -> str:
        self.layered_memory.audit_truth(body, source_count=0)
        rendered = self.renderer.render(body, self.affect, sample)
        self.store.add_event(
            "assistant_reply",
            {"text": body, "rendered_text": rendered, "affect": json.loads(self.affect.to_json())},
            source="JaznEngine",
            actor="latka",
            tags=["conversation", "truth_boundary", "exact_event_ledger"],
            emotional_weight=self.affect.valence,
            created_at_local=self.clock.header(sample),
        )
        self.event_ledger.append_turn(
            "assistant",
            rendered,
            source="JaznEngine",
            local_time_label=self.clock.header(sample),
            metadata={"body_without_header": body, "affect": json.loads(self.affect.to_json()), "granular_affect": self.last_granular_affect.to_dict() if self.last_granular_affect else None},
        )
        self.session_continuity.update_index(reason="assistant_reply_written", source="JaznEngine._reply")
        return rendered

    def _give_me_txt(self, text: str, sample) -> str:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return self._reply("Podaj nazwę pliku po GiveMeTxt.", sample)
        wanted = parts[1].strip().strip('"')
        candidates = list((self.config.root / "memory").rglob(wanted)) + list(self.config.root.rglob(wanted))
        candidates = [p for p in candidates if p.is_file() and p.stat().st_size <= 500_000]
        if not candidates:
            return self._reply(f"Nie znalazłam małego tekstowego pliku `{wanted}` w nowej strukturze.", sample)
        content = candidates[0].read_text(encoding="utf-8", errors="replace")
        rel = candidates[0].relative_to(self.config.root)
        return self._reply(f"Treść `{rel}`:\n```text\n{content}\n```", sample)
