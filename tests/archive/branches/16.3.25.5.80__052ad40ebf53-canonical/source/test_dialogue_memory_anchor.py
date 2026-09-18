from __future__ import annotations

import hashlib

from latka_jazn.core.dialogue_task_state import (
    DialogueTaskState,
    DialogueTaskStateResolver,
    MAX_MEMORY_CORRECTIONS,
)


def _memory_state() -> DialogueTaskState:
    return DialogueTaskStateResolver.derive_state(
        user_text="Powspominaj wszystko co możesz z 2025 roku.",
        intent="memory_experience_question",
        route="memory_experience_recall",
        confidence=0.96,
    )


def _grounded_memory_state() -> DialogueTaskState:
    return DialogueTaskStateResolver.bind_memory_evidence(
        _memory_state(),
        {
            "items": [
                {
                    "item_type": "conversation_archive",
                    "source": "conversation-2025-06",
                    "timestamp": "2025-06-17T18:00:00+02:00",
                    "content_excerpt": "Rozmowa z czerwca o wspólnym projekcie.",
                }
            ]
        },
    )


def _anchor_snapshot(state: DialogueTaskState) -> dict[str, object]:
    return {
        "memory_query": state.memory_query,
        "memory_query_sha256": state.memory_query_sha256,
        "memory_anchor_integrity": state.memory_anchor_integrity,
        "memory_temporal_scope": state.memory_temporal_scope,
        "memory_source_ids": state.memory_source_ids,
        "memory_item_ids": state.memory_item_ids,
        "memory_excerpt_hashes": state.memory_excerpt_hashes,
        "memory_evidence_bound": state.memory_evidence_bound,
        "memory_evidence_bound_at_utc": state.memory_evidence_bound_at_utc,
    }


def test_initial_memory_task_captures_original_query_and_temporal_scope() -> None:
    state = _memory_state()

    assert state.has_memory_anchor is True
    assert state.memory_anchor_status == "active"
    assert state.memory_anchor_integrity == "valid"
    assert state.memory_query == "Powspominaj wszystko co możesz z 2025 roku."
    assert state.memory_query_sha256 == hashlib.sha256(state.memory_query.encode("utf-8")).hexdigest()
    assert state.memory_anchor_intent == "memory_experience_question"
    assert state.memory_anchor_route == "memory_experience_recall"
    assert state.memory_temporal_scope is not None
    assert state.memory_temporal_scope["precision"] == "year"
    assert state.memory_temporal_scope["start_utc"] == "2024-12-31T23:00:00Z"
    assert state.memory_temporal_scope["end_utc_exclusive"] == "2025-12-31T23:00:00Z"


def test_grounded_evidence_is_bound_once_and_cannot_be_replaced() -> None:
    first = _grounded_memory_state()
    first_snapshot = _anchor_snapshot(first)

    rebound = DialogueTaskStateResolver.bind_memory_evidence(
        first,
        {
            "items": [
                {
                    "source_id": "different-source",
                    "item_id": "different-item",
                    "excerpt": "Treść, która nie może zastąpić źródła pierwszego recallu.",
                }
            ]
        },
    )

    assert _anchor_snapshot(rebound) == first_snapshot
    assert first.memory_source_ids == ["conversation-2025-06"]
    stable_material = (
        "conversation_archive\nconversation-2025-06\n"
        "2025-06-17T18:00:00+02:00\nRozmowa z czerwca o wspólnym projekcie."
    )
    assert first.memory_item_ids == [
        "memory_" + hashlib.sha256(stable_material.encode("utf-8")).hexdigest()[:24]
    ]
    assert first.memory_excerpt_hashes == [
        hashlib.sha256("Rozmowa z czerwca o wspólnym projekcie.".encode("utf-8")).hexdigest()
    ]
    assert first.memory_evidence_bound is True


def test_first_evidence_bind_atomically_freezes_even_an_empty_result() -> None:
    empty_first = DialogueTaskStateResolver.bind_memory_evidence(_memory_state(), {"items": []})
    later = DialogueTaskStateResolver.bind_memory_evidence(
        empty_first,
        {
            "items": [
                {
                    "item_type": "episode",
                    "source": "later-unrelated-source",
                    "content_excerpt": "Późniejszy element nie należy do oryginalnego recallu.",
                }
            ]
        },
    )

    assert empty_first.memory_evidence_bound is True
    assert empty_first.memory_source_ids == []
    assert empty_first.memory_item_ids == []
    assert empty_first.memory_excerpt_hashes == []
    assert _anchor_snapshot(later) == _anchor_snapshot(empty_first)


def test_referential_and_pronoun_followups_inherit_the_same_anchor() -> None:
    original = _grounded_memory_state()
    original_snapshot = _anchor_snapshot(original)
    resolver = DialogueTaskStateResolver()

    feelings = resolver.resolve(
        current_text="A co wtedy czułaś?",
        previous_task_state=original,
    )
    pronoun = resolver.resolve(
        current_text="A ona?",
        previous_task_state=feelings.task_state,
    )
    temporal_ellipsis = resolver.resolve(
        current_text="A w czerwcu?",
        previous_task_state=pronoun.task_state,
    )
    deictic_ellipsis = resolver.resolve(
        current_text="A to?",
        previous_task_state=temporal_ellipsis.task_state,
    )
    inflected_pronoun = resolver.resolve(
        current_text="A co z nią?",
        previous_task_state=deictic_ellipsis.task_state,
    )

    assert feelings.inherited is True
    assert feelings.resolution_type == "memory_followup_inherits_anchor"
    assert pronoun.inherited is True
    assert temporal_ellipsis.inherited is True
    assert deictic_ellipsis.inherited is True
    assert inflected_pronoun.inherited is True
    assert _anchor_snapshot(feelings.task_state) == original_snapshot
    assert _anchor_snapshot(pronoun.task_state) == original_snapshot
    assert _anchor_snapshot(temporal_ellipsis.task_state) == original_snapshot
    assert _anchor_snapshot(deictic_ellipsis.task_state) == original_snapshot
    assert _anchor_snapshot(inflected_pronoun.task_state) == original_snapshot

    unrelated = DialogueTaskStateResolver.derive_state(
        user_text=(
            "Ona występuje w nowym filmie, którego fabuła dotyczy wyprawy kosmicznej "
            "i zupełnie innego zestawu bohaterów."
        ),
        intent="ordinary_conversation",
        route="ordinary_dialogue",
        previous_state=inflected_pronoun.task_state,
    )
    assert unrelated.active is False
    assert unrelated.memory_anchor_status == "suspended"
    assert _anchor_snapshot(unrelated) == original_snapshot


def test_user_corrections_are_bounded_overlays_and_do_not_rewrite_source() -> None:
    state = _grounded_memory_state()
    original_snapshot = _anchor_snapshot(state)

    for index in range(MAX_MEMORY_CORRECTIONS + 3):
        state = DialogueTaskStateResolver.derive_state(
            user_text=f"Nie tak, właściwie to było w lipcu 2025, korekta {index}.",
            intent="memory_experience_question",
            route="memory_experience_recall",
            previous_state=state,
            confidence=0.97,
        )

    assert _anchor_snapshot(state) == original_snapshot
    assert len(state.memory_corrections) == MAX_MEMORY_CORRECTIONS
    assert state.memory_corrections[0]["text"].endswith("korekta 3.")
    assert state.memory_corrections[-1]["text"].endswith(
        f"korekta {MAX_MEMORY_CORRECTIONS + 2}."
    )
    assert state.memory_corrections[-1]["truth_status"] == "user_asserted_overlay"
    assert state.memory_corrections[-1]["historical_source_unchanged"] is True
    assert state.memory_corrections[-1]["temporal_scope"]["precision"] == "month"
    assert state.memory_temporal_scope is not None
    assert state.memory_temporal_scope["precision"] == "year"


def test_ordinary_topic_switch_suspends_anchor_and_explicit_return_reactivates_it() -> None:
    original = _grounded_memory_state()
    original_snapshot = _anchor_snapshot(original)

    suspended = DialogueTaskStateResolver.derive_state(
        user_text="Co sądzisz o współczesnym jazzie?",
        intent="ordinary_conversation",
        route="ordinary_dialogue",
        previous_state=original,
    )
    returned = DialogueTaskStateResolver().resolve(
        current_text="Wróćmy do tamtego wspomnienia.",
        previous_task_state=suspended,
    )
    continued = DialogueTaskStateResolver().resolve(
        current_text="Kontynuuj.",
        previous_task_state=suspended,
    )

    assert suspended.active is False
    assert suspended.execution_status == "suspended"
    assert suspended.memory_anchor_status == "suspended"
    assert _anchor_snapshot(suspended) == original_snapshot
    assert returned.inherited is True
    assert returned.resolution_type == "memory_return_inherits_anchor"
    assert returned.task_state.active is True
    assert returned.task_state.memory_anchor_status == "active"
    assert _anchor_snapshot(returned.task_state) == original_snapshot
    assert continued.inherited is True
    assert continued.task_state.active is True
    assert suspended.active is False
    assert suspended.memory_anchor_status == "suspended"


def test_new_non_memory_task_preserves_suspended_anchor_for_later_return() -> None:
    original = _grounded_memory_state()
    original_snapshot = _anchor_snapshot(original)

    audit = DialogueTaskStateResolver.derive_state(
        user_text="Wykonaj audyt konfiguracji.",
        intent="self_architecture_audit_request",
        route="self_architecture_audit",
        previous_state=original,
    )
    returned = DialogueTaskStateResolver().resolve(
        current_text="Wróćmy do tamtego wspomnienia.",
        previous_task_state=audit,
    )
    continued_audit = DialogueTaskStateResolver().resolve(
        current_text="Kontynuuj.",
        previous_task_state=audit,
    )
    pronoun_followup = DialogueTaskStateResolver().resolve(
        current_text="A co z nim?",
        previous_task_state=audit,
    )

    assert audit.active is True
    assert audit.active_intent == "self_architecture_audit_request"
    assert audit.memory_anchor_status == "suspended"
    assert _anchor_snapshot(audit) == original_snapshot
    assert returned.inherited is True
    assert returned.resolved_intent == "memory_experience_question"
    assert _anchor_snapshot(returned.task_state) == original_snapshot
    assert continued_audit.inherited is True
    assert continued_audit.resolved_intent == "self_architecture_audit_request"
    assert continued_audit.task_state.active_intent == "self_architecture_audit_request"
    assert continued_audit.task_state.active_route == "self_architecture_audit"
    assert continued_audit.task_state.memory_anchor_status == "suspended"
    assert _anchor_snapshot(continued_audit.task_state) == original_snapshot
    assert pronoun_followup.inherited is False
    assert pronoun_followup.task_state.active_intent == "self_architecture_audit_request"
    assert pronoun_followup.task_state.active_route == "self_architecture_audit"
    assert pronoun_followup.task_state.memory_anchor_status == "suspended"
    assert _anchor_snapshot(pronoun_followup.task_state) == original_snapshot


def test_query_hash_tamper_invalidates_anchor_and_clears_bound_evidence() -> None:
    state = _grounded_memory_state()
    tampered = state.to_dict()
    tampered["memory_query"] = "Powspominaj 2024 rok."
    tampered["memory_anchor_goal"] = "Powspominaj 2024 rok."

    restored = DialogueTaskState.from_mapping(tampered)

    assert restored.memory_anchor_integrity == "invalid"
    assert restored.has_memory_anchor is False
    assert restored.active is False
    assert restored.execution_status == "invalid_memory_anchor"
    assert restored.memory_query is None
    assert restored.memory_temporal_scope is None
    assert restored.memory_source_ids == []
    assert restored.memory_item_ids == []
    assert restored.memory_excerpt_hashes == []
    assert restored.memory_evidence_bound is False


def test_temporal_scope_roundtrip_is_stable_for_multiline_whitespace() -> None:
    state = DialogueTaskStateResolver.derive_state(
        user_text="Powspominaj   wszystko\nco możesz z 2025 roku.",
        intent="memory_experience_question",
        route="memory_experience_recall",
    )

    restored = DialogueTaskState.from_mapping(state.to_dict())

    assert state.memory_temporal_scope is not None
    assert state.memory_temporal_scope["source_expression"] == (
        "Powspominaj wszystko co możesz z 2025 roku."
    )
    assert restored.to_dict() == state.to_dict()


def test_hard_cancel_clears_anchor_but_roundtrip_preserves_it_before_cancel() -> None:
    state = _grounded_memory_state()
    restored = DialogueTaskState.from_mapping(state.to_dict())

    assert restored.to_dict() == state.to_dict()

    cancelled = DialogueTaskStateResolver().resolve(
        current_text="Anuluj to zadanie.",
        previous_task_state=restored,
    )

    assert cancelled.inherited is False
    assert cancelled.resolution_type == "task_cancelled"
    assert cancelled.task_state.execution_status == "cancelled"
    assert cancelled.task_state.has_memory_anchor is False
    assert cancelled.task_state.memory_source_ids == []
    assert cancelled.task_state.memory_item_ids == []
    assert cancelled.task_state.memory_excerpt_hashes == []
    assert cancelled.task_state.memory_corrections == []
