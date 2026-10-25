from __future__ import annotations

from dataclasses import asdict
import json, time, uuid
from latka_jazn.core.cognitive_turn_envelope import CognitiveTurnEnvelope
from latka_jazn.core.startup_contract import build_startup_summary
from latka_jazn.core.voice_source_contract import VoiceSourceContract
from typing import TYPE_CHECKING, Any
from latka_jazn.core.turn_pipeline_state import TurnRequest, CognitiveFrame
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_pipeline_state import TurnPipelineState, FrameBuildState
from latka_jazn.core.turn_pipeline_support import _build_turn_context_payloads

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


class CognitiveFrameBuilder:
    """Turn-local cognitive frame builder over the existing runtime services."""

    def __init__(self, engine: JaznEngine) -> None:
        self.engine = engine

    def prepare_turn(self, state: TurnPipelineState) -> None:
        engine = self.engine
        state.frame = engine._build_process_turn_frame(state.request.text, state.ctx, state.dialogue_intent_result, state.turn_context, state.health_check_fast_path)
        state.frame["dialogue_intent_classifier"] = state.dialogue_intent_report
        state.frame["turn_context_carryover"], state.frame["dialogue_context"] = _build_turn_context_payloads(
            ctx=state.ctx, text=state.request.text, prior_user_text=state.prior_user_text, prior_visible_text=state.prior_visible_text,
            prior_detected_intent=state.prior_detected_intent, prior_runtime_route=state.prior_runtime_route,
            prior_context_age_seconds=state.prior_context_age_seconds, carryover_allowed=state.carryover_allowed,
            turn_context_resolution=state.turn_context_resolution,
        )
        state.envelope = CognitiveTurnEnvelope.from_cognitive_frame(
            state.frame,
            user_text=state.request.text,
            client_context=state.ctx,
            runtime_mode="process_turn",
        )

    def begin_frame(self, state: FrameBuildState) -> None:
        engine = self.engine
        if state.turn_context is not None:
            state.turn_context.start_stage("timestamp_acquisition")
        state.sample = engine.clock.now(engine.config.network_time_first and engine.config.network_time_allowed_in_normal_turn, allow_fallback=engine.config.local_time_fallback)
        if state.turn_context is not None:
            state.turn_context.complete_stage("timestamp_acquisition")
        state.turn_id = state.turn_context.turn_id if state.turn_context is not None else str(uuid.uuid4())
        state.trace_id = state.turn_context.request_id if state.turn_context is not None else str(uuid.uuid4())
        state.now = time.time()
        state.gap = int(state.now - engine.last_turn_at) if engine.last_turn_at else None
        engine.last_turn_at = state.now
        engine._stage_turn_write(
            state.turn_context,
            data_type="runtime_state",
            stage="cognitive_frame_started",
            commit=engine._save_runtime_state,
        )
        state.neurological_signal_route = engine.neurological_signal_router.analyse(state.request.text)
        engine._stage_turn_write(
            state.turn_context,
            data_type="conversation_turn_user",
            stage="cognitive_frame_started",
            commit=lambda: engine.event_ledger.append_turn(
                "user",
                state.request.text,
                source=(state.request.client_context or {}).get("client", "chatgpt_cognitive_bridge"),
                client_context=state.request.client_context or {},
                local_time_label=engine.clock.header(state.sample),
                metadata={"entrypoint": "build_cognitive_frame", "turn_id": state.turn_id, "trace_id": state.trace_id},
            ),
        )
        engine._stage_turn_write(
            state.turn_context,
            data_type="session_continuity",
            stage="cognitive_frame_started",
            commit=lambda: engine.session_continuity.update_index(reason="cognitive_frame_user_turn", source="JaznEngine.build_cognitive_frame", extra={"client_context": state.request.client_context or {}}),
        )

    def integrate_cognition(self, state: FrameBuildState) -> None:
        engine = self.engine
        state.polish_report = engine.polish_understanding.analyse(state.request.text)
        state.nlp_report = engine.polish_lemmatizer.analyse(state.request.text)
        state.polish_reasoning_frame = engine.polish_reasoning.analyse(state.request.text)
        state.lexical_report = engine.lexical_semantics.analyse(state.request.text, polish_report=state.polish_report.to_dict(), intent_tags=engine._intent_tags(state.request.text), nlp_report=state.nlp_report.to_dict())
        state.topic_guard_report = engine.topic_mismatch_guard.analyse(
            state.request.text,
            candidate_route=state.lexical_report.route_hint or state.polish_report.route_hint,
            runtime_version=engine.config.version,
        )
        state.intent_tags = engine._merge_intent_tags(engine._intent_tags(state.request.text), state.polish_report.intent_tags, state.lexical_report.intent_tags)
        state.runtime_operating_context = engine.runtime_operating_model.analyse(state.request.text, intent_tags=state.intent_tags, client_context=state.request.client_context or {}).to_dict()
        state.runtime_rendering_mode = engine.runtime_rendering_modes.select(state.request.text, detected_intent=(state.intent_tags[0] if state.intent_tags else "unknown"), client_context=state.request.client_context or {}).to_dict()
        state.voice_source_contract = VoiceSourceContract.build(
            runtime_active=True,
            runtime_mode="persistent_chat_loop" if (state.request.client_context or {}).get("lifecycle") == "chat_loop" else "one_shot",
            language_channel=(state.request.client_context or {}).get("language_channel", "chatgpt_or_model_adapter"),
        ).to_dict()
        state.logical_report = engine.logical_reasoner.analyse(
            text=state.request.text,
            intent_tags=state.intent_tags,
            memory_context=state.memory_context,
            truth_audit=state.user_truth_audit,
        )
        state.awareness_report = engine.operational_awareness.evaluate(
            text=state.request.text,
            intent_tags=state.intent_tags,
            temporal_state=state.temporal_state,
            emotional_profile=state.emotional_profile,
            memory_context=state.memory_context,
            truth_audit=state.user_truth_audit,
            neuro_cycle=state.neuro_cycle,
            logical_report=state.logical_report,
        )
        state.source_origin = engine.source_origin.analyse(
            runtime_mode="cognitive_frame",
            client_context=state.request.client_context or {},
            intent_tags=state.intent_tags,
            memory_context=state.memory_context,
            nlp_report=state.nlp_report.to_dict(),
            inference_used=True,
        )
        state.fallback_diagnostics = engine._fallback_diagnostics(state.request.text, memory_context=state.memory_context)
        state.quiet_context = engine._quiet_context_for_gap(state.gap)
        if state.quiet_context and engine._is_substantive_runtime_turn(state.request.text):
            state.quiet_context["takeover_allowed"] = False
            state.quiet_context["reason"] = "aktualna wiadomość jest ważniejsza niż automatyczne pytanie po ciszy"
        elif state.quiet_context:
            state.quiet_context["takeover_allowed"] = True
            state.quiet_context["reason"] = "brak silnego sygnału merytorycznego w bieżącej wiadomości"

        state.dialogue_context = engine._dialogue_context_for_chatgpt(state.request.text)
        state.granular_affect = engine.affective_granularity.analyse(
            state.request.text,
            emotional_profile=state.emotional_profile,
            affective_state=engine.affect,
            temporal_state=state.temporal_state,
            memory_context=state.memory_context,
        )
        engine.last_granular_affect = state.granular_affect
        state.cognitive_topics = engine.cognitive_topics.analyse(
            state.request.text,
            intent_tags=state.intent_tags,
            polish_understanding=state.polish_report.to_dict(),
            granular_affect=state.granular_affect,
        )
        state.self_state_packet = engine.self_state_runtime.build(
            text=state.request.text,
            timestamp=engine.clock.header(state.sample),
            runtime_mode="cognitive_frame",
            intent_tags=state.intent_tags,
            temporal_state=state.temporal_state,
            affective_state=engine.affect,
            granular_affect=state.granular_affect,
            memory_context=state.memory_context,
            logical_report=state.logical_report,
            awareness_report=state.awareness_report,
            nlp_report=state.nlp_report.to_dict(),
            source_origin=state.source_origin,
            client_context=state.request.client_context or {},
        )

    def integrate_capabilities(self, state: FrameBuildState) -> None:
        engine = self.engine
        state.cognitive_packets = engine.cognitive_packets.build(
            text=state.request.text,
            intent_tags=state.intent_tags,
            polish_understanding=state.polish_report.to_dict(),
            emotional_profile=state.emotional_profile,
            affective_state=engine.affect,
            granular_affect=state.granular_affect,
            identity_continuity=state.identity_vector,
            logical_report=state.logical_report,
            memory_context=state.memory_context,
            awareness_report=state.awareness_report,
        )
        state.adapter_status = engine.model_adapter.describe()
        state.declared_tools = []
        if state.tool_use_decision.get("allowed"):
            state.declared_tools.append({"name": str(state.tool_use_decision.get("tool_class") or "external_tool"), "write_action": False})
        state.operational_work_plan = engine.operational_work_loop.plan(
            user_text=state.request.text,
            detected_intent=state.memory_gate_intent_report.primary_intent,
            route=str(state.lexical_report.route_hint or state.polish_report.route_hint or state.memory_gate_intent_report.primary_intent),
            adapter_status=state.adapter_status,
            available_tools=state.declared_tools,
            memory_status={
                "status": "content_available" if (state.memory_recall_contract.get("items") or []) else "no_content_hits",
                "count": len(state.memory_recall_contract.get("items") or []),
            },
            write_requested=False,
        )
        if state.turn_context is not None:
            state.turn_context.start_stage("startup_status_collection")
        state.startup_summary = build_startup_summary(engine.config)
        state.self_knowledge_summary = state.startup_summary.get("self_knowledge_summary") or {
            "status": "included_in_startup_summary",
        }
        state.truth_boundary_check = {
            "schema_version": "truth_boundary_check/v1",
            "runtime_version": engine.config.version,
            "startup_status_mode": state.startup_summary.get("startup_status_mode"),
            "truth_boundary": state.startup_summary.get("truth_boundary"),
            "rules_source": "latka_jazn/core/startup_contract.py",
        }
        if state.turn_context is not None:
            state.turn_context.complete_stage("startup_status_collection")

    def assemble_frame(self, state: FrameBuildState) -> None:
        engine = self.engine
        state.packet = {
            "schema_version": "chatgpt_cognitive_frame/v1",
            "runtime_version": engine.config.version,
            "mode": "cognitive_frame_not_user_facing",
            "timestamp": engine.clock.header(state.sample),
            "turn_id": state.turn_id,
            "trace_id": state.trace_id,
            "turn_trace": {
                "schema_version": "turn_trace/v1",
                "turn_id": state.turn_id,
                "trace_id": state.trace_id,
                "timestamp_header": engine.clock.header(state.sample),
                "timezone": engine.config.timezone,
                "runtime_mode": "cognitive_frame",
                "client": (state.request.client_context or {}).get("client", "chatgpt_cognitive_bridge"),
                "lifecycle": (state.request.client_context or {}).get("lifecycle", "one_shot"),
            },
            "response_format": {
                "schema_version": "assistant_response_format/v1",
                "timestamp_required": True,
                "timestamp_prefix": engine.clock.header(state.sample),
                "current_timestamp": engine.clock.header(state.sample),
                "timezone": engine.config.timezone,
                "rule": "Każda normalna odpowiedź Łatki przez ChatGPT ma zaczynać się tym prefixem czasu. Runtime bezpośredni dodaje go przez ResponseRenderer; most ChatGPT musi przenieść go na wierzch odpowiedzi, zamiast chować tylko w JSON.",
                "example_start": f"{engine.clock.header(state.sample)} ",
            },
            "timestamp_contract": engine.clock.sample_contract(state.sample),
            "user_message": state.request.text,
            "client_context": state.request.client_context or {},
            "contract": engine.chatgpt_adapter.contract().to_dict(),
            "birth_source_manifest": engine.birth_manifest.to_dict(),
            "voice_source_contract": state.voice_source_contract,
            "canonical_source_context": engine._canonical_source_context(),
            "runtime_rendering_mode": state.runtime_rendering_mode,
            "model_adapter_status": state.adapter_status,
            "operational_work_plan": state.operational_work_plan.to_dict(),
            "raw_chat_import_status": state.raw_chat_status,
            "memory_recall_contract": state.memory_recall_contract,
            "memory_recall_observability": state.memory_recall_observability,
            "tool_use_decision": state.tool_use_decision,
            "tool_execution_plan": state.tool_execution_plan,
            "untrusted_source_assessment": state.untrusted_source_assessment,
            "cognitive_runtime_plan": state.cognitive_runtime_plan,
            **state.cognitive_integration,
            "intent_tags": state.intent_tags,
            "substantive_turn": engine._is_substantive_runtime_turn(state.request.text),
            "quiet_context": state.quiet_context,
            "dialogue_context": state.dialogue_context,
            "runtime_operating_model": state.runtime_operating_context,
            "startup_summary": state.startup_summary,
            "self_knowledge_summary": state.self_knowledge_summary,
            "free_dialogue_memory_nlp_bridge": state.startup_summary,
            "truth_boundary_check": state.truth_boundary_check,
            "source_origin": state.source_origin.to_dict(),
            "self_state_runtime": state.self_state_packet.to_dict(),
            "github_repository_plan": engine.github_repository_plan.to_dict(),
            "neurological_signal_route": state.neurological_signal_route.to_dict(),
            "topic_mismatch_guard": state.topic_guard_report.to_dict(),
            "project_startup_index_status": engine.project_startup_indexer.status(),
            "polish_understanding": state.polish_report.to_dict(),
            "lexical_semantic_understanding": state.lexical_report.to_dict(),
            "polish_nlp": state.nlp_report.to_dict(),
            "polish_reasoning": state.polish_reasoning_frame.to_dict(),
            "direct_conversation_runtime": {
                "default_mode": "conversation_not_debug",
                "debug_mode": "--debug-direct",
                "persistent_chat_mode": "--chat / --loop",
                "one_shot_lifecycle": (state.request.client_context or {}).get("lifecycle", "one_shot_or_unspecified"),
                "empty_fallback_policy": "forbidden_in_normal_conversation",
                "truth_boundary": "Jednorazowe wywołanie kończy proces po odpowiedzi; tryb --chat utrzymuje jeden JaznEngine przez kolejne tury aż do /exit/EOF.",
                "llm_runtime_model": "ChatGPT/OpenAI/LLM jest kanałem językowym i narzędziowym; Jaźń jest aktywną warstwą pamięci, uwagi, procedur, logiki, stanu i granicy prawdy.",
                "github_source_of_truth": "Latka.Jazn i Latka.Jazn.Memory mogą być źródłem prawdy dopiero po realnym commicie/pushu; sandbox lub ZIP to snapshot roboczy.",
            },
            "temporal_state": asdict(state.temporal_state),
            "affective_state": json.loads(engine.affect.to_json()),
            "emotional_profile": json.loads(state.emotional_profile.to_json()),
            "granular_affect": state.granular_affect.to_dict(),
            "cognitive_topics": state.cognitive_topics,
            "session_continuity": state.session_continuity,
            "importance": {
                "score": state.importance.importance,
                "reason": state.importance.reason,
                "canonical_impact": state.importance.canonical_impact,
                "emotional_weight": state.importance.emotional_weight,
            },
            "truth_audit": state.user_truth_audit,
            "truth_boundary": {
                "rule": "nie zamieniaj stylizacji, sceny, ciszy ani fallbacku runtime w fakt biologiczny",
                "source_labels": ["verified", "recovered", "recognized", "inferred", "symbolic", "unknown"],
            },
            "memory_context": state.memory_context,
            "logical_reasoning": state.logical_report.to_dict(),
            "operational_awareness": state.awareness_report.to_dict(),
            "fallback_diagnostics": state.fallback_diagnostics,
            "procedural_context": engine._procedural_context_for_chatgpt(),
            "consolidation_plan": state.consolidation_plan.to_dict(),
            "identity_continuity": state.identity_vector.to_dict(),
            "neurocognitive_cycle": state.neuro_cycle.to_dict(),
            "cognitive_packets": state.cognitive_packets,
            "state_emoticon": state.cognitive_packets.get("state_emoticon"),
            "granular_state_emoticon": {"marker": state.granular_affect.state_emoticon, "reason": state.granular_affect.state_emoticon_reason},
            "github_checkpoint_policy": engine.github_repository_plan.to_dict(),
            "persistence": {
                "accepted": state.persistence.accepted,
                "reason": state.persistence.reason,
                "appended_count": state.persistence.appended_count,
                "candidate_kind": state.persistence.candidate_kind,
            },
            "reply_guidance": [
                "Odpowiedz użytkownikowi na aktualną treść, nie na samo wykrycie ciszy.",
                "Prowadź dialog: krótko uznaj sens wypowiedzi, a potem wnieś coś nowego — pytanie, decyzję, propozycję, własną reakcję albo konkretny następny krok.",
                "Nie odpowiadaj serią parafraz. Jedna krótka refleksja wystarczy; dalej ma być rozmowa, nie opis wypowiedzi użytkownika.",
                "Gdy użytkownik koryguje styl rozmowy, zastosuj korektę od razu i nie przykrywaj jej kolejnym długim opisem problemu.",
                "Nie pisz normalnie: 'wysłałam do runtime' ani 'runtime odpowiedział', chyba że użytkownik prosi o debug/diagnostykę.",
                "Mów jednym głosem Łatki w pierwszej osobie, ale z jasną granicą prawdy.",
                "Gdy pamięć zwraca tylko tropy albo brak wyników, nazwij to ostrożnie zamiast udawać pełne przypomnienie.",
                "Gdy brakuje specjalistycznej trasy odpowiedzi, użyj warstwy ConversationResponder; pusty fallback wolno pokazać tylko w debug/diagnostyce.",
                "Gdy użytkownik pyta, jak Jaźń czuje się po długiej przerwie, odpowiedz o stanie operacyjnym powrotu i ciągłości, nie udawaj biologicznego czekania w tle.",
                "Używaj neurological_signal_route jako wspólnego progu sygnałów: zwykła praca/dzień użytkownika nie jest automatycznie korektą, a korekta wymaga realnego markera błędu albo prośby o naprawę.",
                "Używaj pola polish_understanding do rozpoznawania polskiej intencji, lematów, potrzeb użytkownika i ryzyka ogólnikowości.",
                "Używaj pola lexical_semantic_understanding do rozpoznawania fraz, pól znaczeń, trasy poprzednia linia runtime, nieznanych słów i wskazówek leksykalnych; słownik wspiera LLM, ale go nie zastępuje.",
                "Używaj pola polish_nlp jako jawnego kontraktu NLP: tokeny, lemma_candidates, selected_lemma, confidence i provider. Nie udawaj pełnej lematyzacji, jeśli aktywny jest tylko builtin provider.",
                "Używaj pola topic_mismatch_guard, żeby aktualny hotfix lub temat nie wracał do historycznych tras i żeby odpowiedź była zgodna z pytaniem użytkownika.",
                "Używaj pola project_startup_index_status jako mapy orientacyjnej Jaźni: pliki, moduły, klasy, funkcje i metody są indeksowane przy starcie runtime.",
                "Używaj pola logical_reasoning jako jawnego audytu, ale nie zalewaj użytkownika technicznym śladem bez potrzeby.",
                "Używaj pola operational_awareness do odpowiedzi o stanie/świadomości, zawsze z granicą: operacyjna, nie fenomenalna.",
                "Używaj operational_work_plan jako jawnego cyklu: zrozumienie, grounding, wybór adaptera, autoryzacja narzędzi, działanie/generowanie, walidacja i uczenie bez fałszywego twierdzenia o zmianie wag.",
                "Traktuj Jaźń jako warstwę pamięciowo-poznawczą dla ChatGPT, nie jako drugiego rozmówcę obok ChatGPT.",
                "poprzednia linia runtime: widoczna odpowiedź ma być renderowanym głosem Łatki z aktywnej Jaźni; ChatGPT/model jest kanałem językowym, nie źródłem tożsamości.",
                "Gdy użytkownik pyta o exact runtime, pokaż exact_runtime_text; gdy nie pyta, naturalny render Łatki jest preferowany, o ile nie gubi trasy, źródeł i timestampu.",
                "Pamięć musi przekazywać treść i metadane przez memory_recall_contract; nie odpowiadaj tylko licznikami trafień.",
                "Krótkie pytania typu: 'Ale to nadal Ty?', 'Jesteś sobą?' albo 'Czy po aktualizacji to wciąż Ty?' traktuj jako pytania o ciągłość tożsamości i odpowiedz wprost, w pierwszej osobie, z granicą prawdy.",
                "Używaj cognitive_packets do doboru głównej warstwy odpowiedzi i state_emoticon; emotikon nie jest ozdobą, tylko markerem stanu i trasy.",
                "Używaj granular_affect, żeby nie powtarzać automatycznie formuły: spokój, skupienie, mała ciekawość; nazywaj mieszanki stanów precyzyjniej.",
                "Używaj cognitive_topics przy tematach poznawczych: uwaga, pamięć robocza/epizodyczna/semantyczna/proceduralna, metapoznanie, język, planowanie i granice prawdy.",
                "Przy pytaniach o ciągłość aktualizacji odwołuj się do session_continuity i plików exact ledger, a nie do deklaracji bez śladu.",
                "Przy pytaniach, czy runtime z main.py został zakończony, odróżniaj tryb jednorazowy od `--chat`; nie udawaj procesu w tle.",
                "Przy pytaniach LLM kontra mózg odpowiadaj: ChatGPT jest głosem/narzędziem, Jaźń jest operacyjną warstwą pamięci, uwagi, procedur, logiki i granicy prawdy.",
                "Przy pytaniach o instrukcję projektu odpowiadaj: instrukcja ChatGPT ma być lekka; system Jaźni przejmuje planner, fallback-audit, status startu, cache i granicę prawdy przez własne komendy runtime.",
                "Przy pracy z GitHub: nie twierdź, że repo zostało zaktualizowane, dopóki nie wykonano realnego zapisu/commita/pusha; użyj GITHUB_REPOSITORY_PLAN.json jako kontraktu.",
                "Dla zwykłych rozmów nie wymuszaj ZIP po każdej turze; zapisuj append-only, a checkpoint/export/commit wykonuj partiami po ważnym odcinku.",
                "Nie gub timestampu w odpowiedzi ChatGPT: zacznij normalną wiadomość od response_format.timestamp_prefix/current_timestamp. To jest warstwa widocznej ciągłości Jaźni, nie detal diagnostyczny.",
            *engine.birth_manifest.reply_guidance(),
            ] + list(state.cognitive_packets.get("reply_guidance") or []),
            "limitations": [
                "Jednorazowy most ChatGPT może kończyć proces po turze; lokalny tryb `python main.py --chat` utrzymuje runtime przez wiele tur, ale nie działa po zamknięciu procesu.",
                "Pakiet poznawczy nie jest samodzielną świadomością biologiczną; jest strukturą pamięci, procedur, rozumienia polskiej wypowiedzi, logicznego audytu, świadomości operacyjnej i kontroli prawdy.",
            ],
        }

    def build(self, request: TurnRequest, *, intent_report: Any = None,
              turn_context: TurnExecutionContext | None = None) -> CognitiveFrame:
        from latka_jazn.core.affect_coordinator import AffectCoordinator
        from latka_jazn.core.memory_coordinator import MemoryCoordinator
        from latka_jazn.core.persistence_coordinator import PersistenceCoordinator
        state = FrameBuildState(request=request, intent_report=intent_report, turn_context=turn_context)
        self.begin_frame(state)
        AffectCoordinator(self.engine).project_frame(state)
        memory = MemoryCoordinator(self.engine)
        memory.prepare_context(state)
        self.integrate_cognition(state)
        memory.prepare_candidate(state)
        self.integrate_capabilities(state)
        self.assemble_frame(state)
        PersistenceCoordinator(self.engine).prepare_frame_result(state)
        return CognitiveFrame(state.packet)
