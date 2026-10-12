from __future__ import annotations

from pathlib import Path
from latka_jazn.config import JaznConfig

from typing import Any
import json
import time
from latka_jazn.core.clock import WarsawClock
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.core.canon import IdentityCanon
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
from latka_jazn.core.continuity_badge import ContinuityBadgePolicy
from latka_jazn.core.affect_mixer import AffectMixer
from latka_jazn.core.dialogue_state import DialogueStateTracker
from latka_jazn.memory.layered_memory import LayeredMemory
from latka_jazn.memory.consolidation import MemoryConsolidationModel
from latka_jazn.memory.store import MemoryStore
from latka_jazn.memory.runtime_persistence import RuntimeMemoryWriter
from latka_jazn.memory.event_ledger import RuntimeEventLedger
from latka_jazn.memory.session_continuity import SessionContinuityManager
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.memory_use_gate import MemoryUseGate
from latka_jazn.core.signal_matching import NeurologicalSignalRouter
from latka_jazn.core.project_index import ProjectStartupIndexer
from latka_jazn.nlp.topic_mismatch_guard import TopicMismatchGuard
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.core.runtime_answer_validator import RuntimeAnswerValidator
from latka_jazn.core.turn_context_resolver import TurnContextResolver
from latka_jazn.core.dialogue_task_state import DialogueTaskStateResolver
from latka_jazn.core.operational_learning_memory import OperationalLearningMemory
from latka_jazn.core.source_origin_ledger import SourceOriginLedger
from latka_jazn.core.template_registry import TemplateRegistry
from latka_jazn.core.runtime_response_synthesizer import RuntimeResponseSynthesizer
from latka_jazn.core.model_guided_response_synthesizer import ModelGuidedResponseSynthesizer
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.turn_checkpoint_writer import TurnCheckpointWriter
from latka_jazn.core.runtime_visible_answer_comparator import RuntimeVisibleAnswerComparator
from latka_jazn.core.turn_logic_auditor import TurnLogicAuditor
from latka_jazn.core.reasoning_controller import ReasoningController
from latka_jazn.nlp.external_dictionary_adapter import ExternalDictionaryAdapter
from latka_jazn.core.module_responsibility_map import ModuleResponsibilityMap
from latka_jazn.memory.requirements_ledger import RequirementsLedger
from latka_jazn.adapters.chatgpt_adapter import ChatGPTAdapter
from latka_jazn.integrations.github_repository_plan import build_github_repository_plan
from latka_jazn.core.voice_source_contract import VoiceSourceContract
from latka_jazn.core.runtime_rendering_modes import RuntimeRenderingModeSelector
from latka_jazn.core.external_research_contract import ExternalResearchContract
from latka_jazn.core.tool_use_policy import ToolUsePolicy
from latka_jazn.core.tool_execution_controller import ToolExecutionController
from latka_jazn.core.cognitive_runtime_coordinator import CognitiveRuntimeCoordinator
from latka_jazn.core.knowledge_fabric import KnowledgeFabric
from latka_jazn.nlp.lexical_intelligence import LexicalIntelligenceEngine
from latka_jazn.core.untrusted_source_guard import UntrustedSourceGuard
from latka_jazn.memory.memory_recall_contract import MemoryRecallContractBuilder
from latka_jazn.memory.raw_chat_importer import RawChatImporter
from latka_jazn.model_adapters.factory import build_model_adapter
from latka_jazn.core.blind_route_detector import BlindRouteDetector
from latka_jazn.audit.audit_context_store import AuditContextStore
from latka_jazn.bootstrap.contract_loader import BootstrapContractRepository
from latka_jazn.core.engine_services import EngineServices
from latka_jazn.core.procedural_bootstrap import seed_core_procedures


def load_runtime_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


class EngineRuntimeServices:
    """Typed engine dependencies; only explicit lifecycle methods perform I/O."""

    def __init__(self, config: JaznConfig) -> None:
        self.config = config
        self.ready = False
        self.bound = False

    def build_dependencies(self) -> None:
        self.clock = WarsawClock(self.config.timezone)
        self.guard = IdentityPerspectiveGuard()
        self.canon = IdentityCanon.load(self.config.resolve(self.config.canon_path))
        self.handshake = Handshake(self.canon.recognition.user_sign, self.canon.recognition.latka_sign)
        self.store = MemoryStore(self.config.memory_db_path)
        self.audit_store = AuditContextStore(self.config.audit_db_path)
        self.bootstrap_contracts = BootstrapContractRepository(self.config.root)
        self.renderer = ResponseRenderer(self.clock, self.guard)
        self.affect = AffectiveState()
        self.quiet = QuietRest(self.config.idle_reflection_thresholds)
        self.importance_assessor = MemoryImportanceAssessor()
        self.emotional_layers = EmotionalLayerModel()
        self.temporal_awareness = TemporalAwareness()
        self.neuropsychology = NeuropsychologyMapper()
        self.consolidation = MemoryConsolidationModel()
        self.identity_dynamics = IdentityDynamics()
        self.neuro_loop = NeurocognitiveLoop()
        self.logical_reasoner = LogicalReasoner()
        self.operational_awareness = OperationalAwarenessModel()
        self.polish_understanding = PolishUnderstandingEngine(self.config.root)
        self.lexical_semantics = LexicalSemanticUnderstanding(self.config.root)
        self.polish_lemmatizer = PolishLemmatizationEngine(self.config.root)
        self.polish_reasoning = PolishReasoningPipeline(self.config.root)
        self.cognitive_packets = CognitivePacketLibrary(self.config.root)
        self.affective_granularity = AffectiveGranularityModel()
        self.cognitive_topics = CognitiveTopicExpansion(self.config.root)
        self.memory_search_planner = MemorySearchPlanner(self.config.root)
        self.living_memory_gateway = LivingMemoryGateway(self.config.root)
        self.memory_use_gate = MemoryUseGate()
        self.neurological_signal_router = NeurologicalSignalRouter()
        self.topic_mismatch_guard = TopicMismatchGuard()
        self.dialogue_intent_classifier = DialogueIntentClassifier()
        self.runtime_answer_validator = RuntimeAnswerValidator()
        self.turn_context_resolver = TurnContextResolver()
        self.dialogue_task_state_resolver = DialogueTaskStateResolver()
        self.operational_learning_memory = OperationalLearningMemory.from_json_file(
            self.config.root / "latka_jazn" / "resources" / "cognition" / "v154_operational_lessons.json"
        )
        self.source_origin_ledger = SourceOriginLedger(self.config.root)
        self.template_registry = TemplateRegistry(self.config.root)
        self.runtime_response_synthesizer = RuntimeResponseSynthesizer()
        self.model_guided_response_synthesizer = ModelGuidedResponseSynthesizer()
        self.route_registry = RouteRegistry()
        self.route_handler_dispatcher = RouteHandlerDispatcher()
        self.blind_route_detector = BlindRouteDetector()
        self.turn_checkpoint_writer = TurnCheckpointWriter(self.config.root)
        self.runtime_visible_answer_comparator = RuntimeVisibleAnswerComparator(self.config.root)
        self.turn_logic_auditor = TurnLogicAuditor(self.config.root)
        self.reasoning_controller = ReasoningController()
        self.operational_work_loop = OperationalWorkLoop()
        self.external_dictionary_adapter = ExternalDictionaryAdapter(self.config.root, allow_network=self.config.dictionary_allow_network, user_agent=self.config.network_user_agent, timeout_seconds=self.config.dictionary_online_lookup_timeout_seconds, max_retries=self.config.network_max_retries, cache_ttl_seconds=self.config.network_cache_ttl_seconds)
        self.module_responsibility_map = ModuleResponsibilityMap(self.config.root)
        self.requirements_ledger = RequirementsLedger(self.config.root)
        self.project_startup_indexer = ProjectStartupIndexer(self.config.root)
        self.project_startup_index: dict[str, Any] = {}
        self.runtime_operating_model = CognitiveRuntimeOperatingModel()
        self.github_repository_plan = build_github_repository_plan(self.config.root)
        self.voice_source_contract = VoiceSourceContract.build(runtime_active=True, runtime_mode="one_shot_or_chat_loop")
        self.runtime_rendering_modes = RuntimeRenderingModeSelector()
        self.memory_recall_contract_builder = MemoryRecallContractBuilder()
        self.raw_chat_importer = RawChatImporter(self.config.root)
        self.external_research_contract = ExternalResearchContract()
        self.tool_use_policy = ToolUsePolicy()
        self.tool_execution_controller = ToolExecutionController()
        self.cognitive_runtime_coordinator = CognitiveRuntimeCoordinator()
        self.knowledge_fabric = KnowledgeFabric()
        self.lexical_intelligence = LexicalIntelligenceEngine(
            root=self.config.root,
            cache_path=self.config.runtime_workspace_dir / "lexical_intelligence.sqlite3",
        )
        self.untrusted_source_guard = UntrustedSourceGuard()
        self.model_adapter = build_model_adapter(self.config)
        self.model_guided_speech_status = None
        self.conversation_responder = ConversationResponder()
        self.architecture = SelfArchitecture()
        self.birth_manifest = BirthSourceManifest(self.config.version)
        self.truth_boundary = TruthBoundary()
        self.uncertainty = UncertaintyModel()
        self.source_origin = SourceOriginAnalyzer()
        self.self_state_runtime = SelfStateRuntime()
        self.affect_mixer = AffectMixer()
        self.dialogue_state_tracker = DialogueStateTracker()
        self.continuity_badge_policy = ContinuityBadgePolicy(self.config.root)
        self.layered_memory = LayeredMemory(self.store, self.config.root)
        self.runtime_memory = RuntimeMemoryWriter(self.config.root, version=self.config.version, store=self.store, timezone_name=self.config.timezone)
        self.event_ledger = RuntimeEventLedger(self.config.root, version=self.config.version, timezone_name=self.config.timezone)
        self.session_continuity = SessionContinuityManager(self.config.root, version=self.config.version, timezone_name=self.config.timezone)
        self.chatgpt_adapter = ChatGPTAdapter(self.config)
        self.last_granular_affect = None
        self.started_at = time.time()
        self.runtime_state_path = workspace_runtime_path(self.config.root) / "runtime_state.json"
        self.last_turn_at: float | None = None
        self.last_user_text: str | None = None
        self.last_detected_intent: str | None = None
        self.last_runtime_route: str | None = None
        self.last_dialogue_task_state: dict[str, Any] = {}

    def hydrate(self) -> None:
        state = load_runtime_state(self.runtime_state_path)
        self.last_turn_at: float | None = state.get("last_turn_at") if isinstance(state.get("last_turn_at"), (int, float)) else None
        self.last_user_text: str | None = state.get("last_user_text") if isinstance(state.get("last_user_text"), str) else None
        self.last_detected_intent: str | None = state.get("last_detected_intent") if isinstance(state.get("last_detected_intent"), str) else None
        self.last_runtime_route: str | None = state.get("last_runtime_route") if isinstance(state.get("last_runtime_route"), str) else None
        self.last_dialogue_task_state: dict[str, Any] = dict(state.get("dialogue_task_state") or {}) if isinstance(state.get("dialogue_task_state"), dict) else {}

    def start(self) -> None:
        reason = "cache_absent"
        if self.project_startup_indexer.output_path.exists():
            try:
                cached = json.loads(self.project_startup_indexer.output_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("active_root") == str(self.config.root.resolve()):
                    self.project_startup_index = cached
                    reason = "cache_reused_same_root"
                else:
                    reason = "cache_root_mismatch"
            except (OSError, UnicodeError, json.JSONDecodeError):
                reason = "cache_unreadable"
        if reason != "cache_reused_same_root":
            try:
                self.project_startup_index = self.project_startup_indexer.build(write=True)
            except (OSError, ValueError) as exc:
                raise RuntimeError("DEPENDENCY_NOT_READY:project_startup_index:" + reason) from exc
        self.project_index_startup_report = {"reason": reason, "ready": True}
        self.store.add_event(
            "engine_started",
            {
                "version": self.config.version,
                "identity": self.canon.display_name,
                "self_architecture": self.architecture.to_dict(),
                "operational_awareness": "enabled",
                "logical_reasoning": "enabled",
                "conversation_runtime": "enabled",
                "polish_understanding": "enabled",
                "lexical_semantic_understanding": "enabled",
                "polish_nlp_adapter": "enabled_builtin_optional_providers",
                "identity_continuity_understanding": "enabled",
                "cognitive_packets": "enabled",
                "affective_granularity": "enabled",
                "cognitive_topics": "enabled",
                "session_continuity_index": "enabled",
                "runtime_operating_model": "enabled",
                "github_repository_plan": "prepared",
                "zip_package_profiles": "system_memory_nlp_full_github_safe",
                "runtime_preview": "enabled",
                "source_origin": "enabled",
                "self_state_runtime": "enabled",
                "memory_search_planner": "enabled",
                "living_memory_gateway": "enabled_read_only_five_database_recall",
                "free_dialogue_memory_nlp_bridge": "enabled",
                "neurological_signal_router": "enabled",
                "topic_mismatch_guard": "enabled",
                "dialogue_intent_classifier": "enabled_behavioral_intent_router",
                "dialogue_task_state": "enabled_structured_goal_and_continuation_state",
                "reasoning_orchestrator": "enabled_selective_fast_standard_deliberative",
                "operational_learning": "verified_resource_loaded",
                "runtime_answer_validator": "enabled_topic_alignment_guard",
                "source_origin_ledger": "enabled",
                "module_responsibility_map": "enabled",
                "requirements_ledger": "enabled",
                "project_startup_index": "enabled_startup_scan",
                "voice_source_contract": "enabled_model_independent_latka_voice",
                "runtime_rendering_modes": "enabled_natural_vs_diagnostic_runtime_visibility",
                "memory_recall_content_contract": "enabled_content_not_counts_only",
                "model_adapter_contract": "enabled_null_truthful_adapter_plus_future_adapters",
            },
            source="JaznEngine",
            actor="system",
            tags=["startup", "layered_self", "truth_boundary", "memory_search_planner", "free_dialogue_memory_nlp_bridge", "neurological_signal_router", "topic_mismatch_guard", "dialogue_intent_classifier", "runtime_answer_validator", "project_startup_index", self.config.version],
             importance=0.95,
            canonical_impact=1,
        )
        self.audit_store.append_event("engine_started", {"version": self.config.version, "memory_db_path": str(self.config.memory_db_path), "audit_db_path": str(self.config.audit_db_path), "bootstrap_contracts": self.bootstrap_contracts.status()}, source="JaznEngine", actor="system", tags=["startup", "audit", self.config.version])
        self.event_ledger.append_event(
            "engine_started",
            actor="system",
            source="JaznEngine",
            payload={"version": self.config.version, "identity": self.canon.display_name, "project_startup_index": self.project_startup_indexer.status()},
            tags=["startup", "event_ledger", "project_startup_index", self.config.version],
            importance=0.95,
            canonical_impact=1,
        )
        self.procedural_seed_report = seed_core_procedures(self.layered_memory, revision=self.config.version)
        self.engine_service_seams = EngineServices.from_legacy_engine(self)
        self.ready = True
