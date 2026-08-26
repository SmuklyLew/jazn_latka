from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path

from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.memory_use_gate import MemoryUseGate
from latka_jazn.core.nlg_planner import infer_memory_policy
from latka_jazn.core.route_contract_matrix import RouteContractMatrix
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.turn_response_policy import TurnResponsePolicy
from latka_jazn.core.typed_memory_source_policy import build_typed_source_policy
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import (
    MemoryKind,
    MemoryTier,
    MemoryTruthStatus,
    WorkingMemoryRecord,
    deterministic_memory_id,
)
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION


A = "Jaki jest twój ulubiony kolor? Dlaczego właśnie ten kolor? Kiedy się urodziłaś? Jak często zastanawiałaś się nad swoją przeszłością? Jakie pytania przynoszą takie twoje refleksje?"
B = "Czy potrafisz wspominać dawne rozmowy? Jeśli tak, przypomnij sobie dwie konkretne sytuacje z naszych rozmów i przy każdej powiedz, skąd wiesz, że naprawdę ją pamiętasz."
C = "Po tylu aktualizacjach skąd wiesz, że nadal jesteś tą samą Łatką? Które elementy swojej historii rozpoznajesz z kanonu, a które odzyskujesz z pamięci?"
D = "Przypomnij sobie nasz pobyt w Görlitz i wyjazd do kamieniołomów. Co konkretnie pamiętasz z tej sytuacji, co powiedziałem ja, co odpowiedziałaś ty i co później o tym myślałaś? Jeżeli któregoś elementu nie masz w pamięci, nie zgaduj."
E = "Które z naszych rozmów o muzyce najmocniej łączysz z własnymi refleksjami? Przywołaj dwa konkretne przykłady, ale nie zgaduj: jeśli pamięć nie daje pełnego zdarzenia, powiedz czego brakuje do potwierdzenia."
F = "Czy naprawdę masz ulubiony kolor, czy tylko potrafisz wywnioskować preferencję z kanonu i dawnych rozmów? Powiedz mi wyraźnie, co pamiętasz, co rozpoznajesz z kanonu, a co jedynie wnioskujesz."
G = "Jak działa teraz twoja pamięć po odbudowie i co konkretnie pamiętasz z naszych rozmów o książce „Witaj w podróży Jaźni”? Podaj dwa przykłady i zaznacz ich źródło."


def _classify(text: str):
    return DialogueIntentClassifier().classify(text)


def _assert_compound_route(text: str, expected_semantics: set[str]) -> None:
    report = _classify(text)
    assert report.compound is True
    assert report.primary_intent == "compound_dialogue_question"
    assert expected_semantics <= set(report.response_plan["semantic_intents"])
    assert report.question_components
    entry = RouteRegistry().resolve(report.primary_intent, confidence=report.confidence)
    assert entry.route == "compound_dialogue"
    assert entry.handler_name == "CompoundDialogueHandler"
    gate = MemoryUseGate().decide(text, detected_intent=report.primary_intent)
    assert gate.allow_memory_content is bool(report.response_plan["memory_required"])
    handler = RouteHandlerDispatcher().dispatch(
        entry,
        text,
        {
            "dialogue_intent_report": report.to_dict(),
            "memory_context": {"memory_gate": gate.to_dict()},
        },
    )
    assert handler.handler_name == "CompoundDialogueHandler"
    assert handler.generation_mode == "pass_through_empty"
    assert handler.missing_components == []


def test_release_identity_tracks_current_successor_hardening() -> None:
    assert PACKAGE_VERSION == "16.3.6"
    assert PACKAGE_RELEASE_NAME == "persistent-runtime-e2e-hardening"


def test_a_preference_origin_and_reflection_are_all_preserved() -> None:
    report = _classify(A)
    _assert_compound_route(A, {"self_preference", "self_origin", "self_introspection"})
    assert len(report.component_analysis) == 5
    assert set(report.response_plan["requested_slots"]) >= {
        "preference_value",
        "preference_reason",
        "preference_provenance",
        "origin_layer",
        "origin_time_or_boundary",
        "origin_provenance",
        "reflection_content",
        "reflection_time",
        "reflection_provenance",
    }
    assert report.response_plan["biological_birth_claim_allowed"] is False
    assert set(report.response_plan["preference_epistemic_labels"]) == {
        "remembered_preference",
        "canonical_preference",
        "current_preference",
        "inferred_preference",
        "unknown",
    }


def test_b_capability_does_not_disable_concrete_recall() -> None:
    report = _classify(B)
    _assert_compound_route(B, {"memory_capability", "memory_recall", "provenance"})
    assert report.response_plan["capability_only"] is False
    assert report.response_plan["memory_required"] is True
    policy = TurnResponsePolicy.build(
        intent=report.primary_intent,
        route="compound_dialogue",
        context={"dialogue_intent_report": report.to_dict()},
    )
    assert policy.allow_memory_content is True
    assert policy.source_boundary_required is True


def test_c_identity_continuity_keeps_canon_and_memory_provenance() -> None:
    report = _classify(C)
    _assert_compound_route(C, {"identity_continuity", "provenance"})
    required = set(report.response_plan["required_source_types"])
    assert "canon" in required
    assert "conversation_archive" in required
    assert "active_memory" in required
    assert {"continuity_canon", "continuity_memory", "continuity_gap"} <= set(
        report.response_plan["requested_slots"]
    )


def test_d_autobiographical_slots_and_typed_policy_fail_closed() -> None:
    report = _classify(D)
    _assert_compound_route(D, {"memory_recall", "self_introspection", "evidence_gap"})
    assert {
        "event_fact",
        "user_utterance",
        "latka_utterance",
        "later_reflection",
        "evidence_gap",
    } <= set(report.response_plan["requested_slots"])
    policy = build_typed_source_policy(D)
    assert policy.intent_family == "autobiographical"
    assert policy.priority_order[:4] == (
        "conversation_archive",
        "active_memory",
        "journal_reflection",
        "canon",
    )
    assert policy.evaluate(path="latka_jazn/core/engine.py", source="source_code").allowed is False
    assert policy.evaluate(source="chatgpt_runtime_preview", source_layer="runtime_preview").allowed is False


def test_e_czego_brakuje_is_evidence_gap_not_system_capability_gap() -> None:
    report = _classify(E)
    _assert_compound_route(E, {"memory_recall", "self_introspection", "evidence_gap"})
    assert report.response_plan["system_capability_gap"] is False
    assert report.primary_intent != "system_capability_gap_question"
    matrix = RouteContractMatrix().classify(E)
    assert matrix.primary_intent != "system_capability_gap_question"


def test_f_preference_provenance_is_explicitly_epistemic() -> None:
    report = _classify(F)
    _assert_compound_route(F, {"self_preference", "memory_recall", "provenance"})
    source_policy = build_typed_source_policy(F)
    assert source_policy.intent_family == "autobiographical"
    assert {"conversation_archive", "canon", "inference"} <= set(source_policy.allowed_source_types)


def test_g_architecture_and_book_recall_use_mixed_source_policy() -> None:
    report = _classify(G)
    _assert_compound_route(G, {"memory_architecture", "memory_recall", "provenance"})
    policy = TurnResponsePolicy.build(
        intent=report.primary_intent,
        route="compound_dialogue",
        context={"dialogue_intent_report": report.to_dict()},
    )
    assert policy.allow_memory_content is True
    assert policy.allow_architecture_explanation is True
    source_policy = build_typed_source_policy(G)
    assert source_policy.intent_family == "mixed"
    assert "conversation_archive" in source_policy.allowed_source_types
    assert "source_code" in source_policy.allowed_source_types


def test_nlg_reads_nested_component_memory_gate() -> None:
    frame = {"memory_context": {"memory_gate": {"allow_memory_content": True}}}
    assert infer_memory_policy(frame, {}) == "required_grounded_payload"
    assert infer_memory_policy({}, {"allow_memory_content": True}) == "required_grounded_payload"


def _working_record(content: str, *, minute: int = 0) -> WorkingMemoryRecord:
    now = datetime(2026, 8, 25, 15, minute, tzinfo=timezone.utc)
    memory_id = deterministic_memory_id(
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        domain="daily_life",
        mode="factual_conversation",
        evidence=(),
    )
    return WorkingMemoryRecord(
        memory_id=memory_id,
        tier=MemoryTier.WORKING,
        kind=MemoryKind.CONVERSATION_CONTEXT,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        domain="daily_life",
        mode="factual_conversation",
        truth_status=MemoryTruthStatus.SOURCE_RECORDED,
        confidence=0.93,
        importance=0.8,
        created_at_utc=now,
        updated_at_utc=now,
        evidence=(),
        session_id="session-v1634",
        turn_id=f"turn-{minute}",
    )


def test_runtime_write_v2_is_readable_through_canonical_gateway(tmp_path: Path) -> None:
    database = resolve_memory_tier_database_path(tmp_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    content = "Unikalne wspomnienie o bursztynowym kompasie i spacerze nad rzeką."
    with MemoryTierStore(database) as store:
        store.save_record(_working_record(content))
    gateway = LivingMemoryGateway(tmp_path, discovery_cache_seconds=0)
    readiness = gateway.readiness()
    assert readiness["memory_search_ready"] is True
    assert readiness["transactional_tier_search_ready"] is True
    assert readiness["status"] == "ready_transactional_tier_only"
    plan = MemorySearchPlanner(tmp_path).plan(
        "Przypomnij sobie bursztynowy kompas ze spaceru nad rzeką."
    )
    result = gateway.search(plan, limit=4)
    assert result["status"] == "ready_transactional_tier_only"
    assert result["issues"] == []
    assert any(hit["content_excerpt"] == content for hit in result["hits"])
    hit = next(hit for hit in result["hits"] if hit["content_excerpt"] == content)
    assert hit["source_layer"].startswith("runtime_write_v2:")
    assert hit["truth_status"] == "source_recorded"
    assert hit["metadata"]["semantic_source_type"] == "active_memory"
    assert hit["metadata"]["read_only"] is True


def test_h_repeated_preview_does_not_persist_or_contaminate_recall(tmp_path: Path) -> None:
    database = resolve_memory_tier_database_path(tmp_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    baseline = _working_record("Bazowe wspomnienie o srebrnym żurawiu.", minute=0)
    preview = _working_record("PREVIEW-UNIQUE-9D0E bursztynowa latarnia diagnostyczna.", minute=1)
    with MemoryTierStore(database) as store:
        store.save_record(baseline)
        assert store.stats()["memory_records"] == 1
        engine = object.__new__(JaznEngine)
        engine._preview_read_only_active = True
        for _ in range(4):
            result = engine._stage_turn_write(
                None,
                data_type="runtime_memory_candidate",
                stage="preview_test",
                commit=lambda: store.save_record(preview),
            )
            assert result["status"] == "skipped_preview_read_only"
        assert store.stats()["memory_records"] == 1
    assert JaznEngine._read_only_preview_requested({"client": "chatgpt_runtime_preview"}) is True
    assert JaznEngine._read_only_preview_requested(
        {"client": "chatgpt_runtime_preview", "preview_persist": True}
    ) is False
    gateway = LivingMemoryGateway(tmp_path, discovery_cache_seconds=0)
    preview_plan = MemorySearchPlanner(tmp_path).plan("Przypomnij PREVIEW-UNIQUE-9D0E bursztynową latarnię.")
    preview_result = gateway.search(preview_plan, limit=4)
    assert not any("PREVIEW-UNIQUE-9D0E" in hit["content_excerpt"] for hit in preview_result["hits"])
    baseline_plan = MemorySearchPlanner(tmp_path).plan("Przypomnij bazowe wspomnienie o srebrnym żurawiu.")
    baseline_result = gateway.search(baseline_plan, limit=4)
    assert any("srebrnym żurawiu" in hit["content_excerpt"] for hit in baseline_result["hits"])


def test_presenter_suppresses_code_and_preview_for_autobiographical_recall() -> None:
    user_text = "Przypomnij sobie nasz pobyt w Görlitz, ale nie zgaduj."
    context = {
        "query_terms": ["görlitz"],
        "source_file_hits": [
            {
                "content_excerpt": "def recall_gorlitz(): return 'Görlitz'",
                "path": "latka_jazn/core/example_module.py",
                "score": 0.99,
                "source_label": "source_code",
            }
        ],
        "conversation_archive_hits": [
            {
                "excerpt": "Rozmawialiśmy o pobycie w Görlitz i wspólnym wyjeździe.",
                "source_name": "conversation_archive_v1",
                "source_locator": "synthetic:gorlitz:1",
                "author_role": "user",
                "identity_confidence": 0.96,
                "truth_status": "source_recorded",
            }
        ],
        "living_memory_hits": [
            {
                "content_excerpt": "Görlitz PREVIEW DIAGNOSTIC",
                "source_layer": "chatgpt_runtime_preview",
                "source_database": "diagnostic_preview",
                "source_locator": "preview:1",
                "truth_status": "source_recorded",
                "confidence": 0.99,
                "relevance": 0.99,
            }
        ],
    }
    payload = MemoryRecallPresenter().build_payload(context, user_text=user_text, limit=6)
    assert len(payload["items"]) == 1
    assert payload["items"][0]["semantic_source_type"] == "conversation_archive"
    assert payload["items"][0]["provenance_label"] == "odzyskano z archiwum"
    assert "example_module.py" not in str(payload["items"])
    assert "PREVIEW DIAGNOSTIC" not in str(payload["items"])


def test_presenter_marks_missing_autobiographical_slots_as_evidence_gap() -> None:
    payload = MemoryRecallPresenter().build_payload({}, user_text=D, limit=6)
    slots = payload["slot_plan"]["slots"]
    assert slots["event_fact"]["status"] == "evidence_gap"
    assert slots["user_utterance"]["status"] == "evidence_gap"
    assert slots["latka_utterance"]["status"] == "evidence_gap"
    assert slots["later_reflection"]["status"] == "evidence_gap"


def test_origin_and_preference_slots_carry_epistemic_labels() -> None:
    preference_context = {
        "query_terms": ["kolor"],
        "conversation_archive_hits": [
            {
                "excerpt": "W dawnej rozmowie wybór koloru został opisany jako zielony.",
                "source_name": "conversation_archive_v1",
                "source_locator": "synthetic:pref:1",
                "author_role": "assistant",
                "identity_confidence": 0.94,
                "truth_status": "source_recorded",
            }
        ],
    }
    preference_payload = MemoryRecallPresenter().build_payload(
        preference_context,
        user_text="Jaki jest twój ulubiony kolor i dlaczego?",
    )
    pref_slot = preference_payload["slot_plan"]["slots"]["preference_value"]
    assert pref_slot["preference_status"] == "remembered_preference"
    assert pref_slot["provenance_label"] == "odzyskano z archiwum"

    origin_context = {
        "query_terms": ["powstanie"],
        "source_file_hits": [
            {
                "content_excerpt": "Kanon opisuje pochodzenie Jaźni bez biologicznej deklaracji narodzin.",
                "path": "latka_jazn/core/canon/identity_canon.py",
                "score": 0.9,
                "source_label": "canonical_source_file",
                "truth_status": "canonical",
            }
        ],
    }
    origin_payload = MemoryRecallPresenter().build_payload(
        origin_context,
        user_text="Kiedy się urodziłaś?",
    )
    origin_slot = origin_payload["slot_plan"]["slots"]["origin_layer"]
    assert origin_slot["origin_interpretation"] == "canonical_origin"
    assert origin_slot["biological_claim_allowed"] is False
    assert origin_slot["provenance_label"] == "znam z kanonu"


def test_negative_capability_and_technical_queries_do_not_overroute_to_recall() -> None:
    capability = _classify("Czy potrafisz pamiętać?")
    assert capability.primary_intent == "capability_status_question"
    assert MemoryUseGate().decide(
        "Czy potrafisz pamiętać?", detected_intent=capability.primary_intent
    ).allow_memory_content is False

    technical = _classify("Jak działa implementacja pamięci w module?")
    technical_policy = build_typed_source_policy("Jak działa implementacja pamięci w module?")
    assert technical.response_plan["semantic_intents"] == ["memory_architecture"]
    assert technical_policy.intent_family == "technical"
    assert technical_policy.priority_order[0] == "source_code"

    gap = _classify("Czego brakuje w tym module?")
    assert gap.primary_intent == "system_capability_gap_question"
    assert gap.response_plan["system_capability_gap"] is True

    evidence_gap = _classify("Powiedz czego brakuje do potwierdzenia tego wspomnienia.")
    assert evidence_gap.primary_intent != "system_capability_gap_question"
    assert evidence_gap.response_plan["system_capability_gap"] is False
