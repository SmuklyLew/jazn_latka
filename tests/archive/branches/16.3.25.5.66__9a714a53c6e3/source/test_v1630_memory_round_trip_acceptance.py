from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.core.dialogue_task_state import (
    DialogueTaskState,
    DialogueTaskStateResolver,
)
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.route_handler_dispatcher import RouteHandlerDispatcher
from latka_jazn.core.route_registry import RouteRegistry
from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
from latka_jazn.memory.conversation_archive import (
    ConversationArchiveHit,
    ConversationArchiveStore,
)
from latka_jazn.nlp.dialogue_intent_classifier import DialogueIntentClassifier


INITIAL_RECALL = "Powspominaj wszystko co możesz z 2025 roku."
SOURCE_EXCERPT = (
    "W czerwcu rozmawiałyśmy o spokojnym spacerze nad rzeką; "
    "czułam wtedy spokój i bliskość."
)


def _wake() -> dict[str, Any]:
    return {
        "status": "hydrated",
        "ok": True,
        "snapshot_id": "synthetic-wake-v1630",
        "snapshot_sha256": "a" * 64,
        "source_run_id": "synthetic-run-v1630",
        "validation_status": "valid",
    }


def _build_synthetic_fts(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE fts_docs(
                fts_doc_uid TEXT,
                archive_message_uid TEXT,
                archive_occurrence_uid TEXT,
                staging_uid TEXT,
                conversation_uid TEXT,
                source_uid TEXT,
                content_hash TEXT,
                role TEXT,
                title TEXT,
                create_time
            )
            """
        )
        connection.execute("CREATE VIRTUAL TABLE message_fts USING fts5(content)")
        rows = [
            ("outside-2024", "2024-10-01T12:00:00Z", "Ślad spoza zakresu czasu."),
            ("grounded-2025", "2025-06-17T18:00:00Z", SOURCE_EXCERPT),
            ("current-turn-echo", "2025-08-01T12:00:00Z", INITIAL_RECALL),
        ]
        for uid, timestamp, content in rows:
            cursor = connection.execute(
                "INSERT INTO fts_docs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    f"message-{uid}",
                    f"occurrence-{uid}",
                    f"staging-{uid}",
                    f"conversation-{uid}",
                    "synthetic-source",
                    f"hash-{uid}",
                    "assistant",
                    "Syntetyczna rozmowa",
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO message_fts(rowid, content) VALUES(?, ?)",
                (cursor.lastrowid, content),
            )


def _synthetic_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ConversationArchiveStore:
    fts_path = tmp_path / "synthetic-conversation-fts.sqlite3"
    _build_synthetic_fts(fts_path)
    store = ConversationArchiveStore(tmp_path / "synthetic-memory-root")
    store.fts_dir = tmp_path
    monkeypatch.setattr(
        store,
        "status",
        lambda **_: SimpleNamespace(ready_for_search=True, issues=[]),
    )
    monkeypatch.setattr(
        store,
        "_manifest_rows",
        lambda *_args, **_kwargs: [
            {"family": "fts", "relative_path": fts_path.name, "shard_id": "synthetic-fts"}
        ],
    )

    def hydrate(
        row: dict[str, Any],
        *,
        rank: float,
        terms: list[str],
        include_snippets: bool,
    ) -> ConversationArchiveHit:
        del terms, include_snippets
        uid = str(row["fts_doc_uid"])
        with sqlite3.connect(fts_path) as connection:
            excerpt = str(
                connection.execute(
                    """
                    SELECT message_fts.content
                    FROM fts_docs
                    JOIN message_fts ON message_fts.rowid = fts_docs.rowid
                    WHERE fts_docs.fts_doc_uid = ?
                    """,
                    (uid,),
                ).fetchone()[0]
            )
        return ConversationArchiveHit(
            fts_doc_uid=uid,
            rank=rank,
            message_uid=str(row["archive_message_uid"]),
            occurrence_uid=str(row["archive_occurrence_uid"]),
            staging_uid=str(row["staging_uid"]),
            conversation_uid=str(row["conversation_uid"]),
            source_uid=str(row["source_uid"]),
            source_name="synthetic-conversation-archive",
            source_locator=f"synthetic/{uid}",
            role=str(row["role"]),
            title=str(row["title"]),
            create_time=str(row["create_time"]),
            content_hash=str(row["content_hash"]),
            memory_namespace="latka-synthetic",
            privacy_scope="synthetic",
            identity_confidence=1.0,
            review_status="accepted",
            excerpt=excerpt,
        )

    monkeypatch.setattr(store, "_hydrate_hit", hydrate)
    return store


def _archive_context(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "phrase": "temporal_scope_only",
            "search_pass": "conversation_archive_fts",
            "text": hit["excerpt"],
            "excerpt": hit["excerpt"],
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
        }
        for hit in hits
    ]


def _anchor_snapshot(state: DialogueTaskState) -> dict[str, Any]:
    return {
        "memory_query": state.memory_query,
        "memory_query_sha256": state.memory_query_sha256,
        "memory_temporal_scope": state.memory_temporal_scope,
        "memory_source_ids": state.memory_source_ids,
        "memory_item_ids": state.memory_item_ids,
        "memory_excerpt_hashes": state.memory_excerpt_hashes,
        "memory_evidence_bound": state.memory_evidence_bound,
    }


def test_v1630_source_backed_temporal_recall_survives_dialogue_and_restart_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier = DialogueIntentClassifier()
    registry = RouteRegistry()
    dispatcher = RouteHandlerDispatcher()
    resolver = DialogueTaskStateResolver()

    initial_report = classifier.classify(INITIAL_RECALL)
    initial_entry = registry.resolve(initial_report.primary_intent)
    plan = MemorySearchPlanner(tmp_path).plan(
        INITIAL_RECALL,
        now=datetime.fromisoformat("2026-08-25T12:00:00+02:00"),
    )

    assert initial_report.primary_intent == "memory_experience_question"
    assert initial_entry.handler_name == "MemoryExperienceRecallHandler"
    assert plan.temporal_scope["precision"] == "year"
    assert plan.search_terms == []

    archive_result = _synthetic_archive(tmp_path, monkeypatch).search(
        "",
        temporal_scope=plan.temporal_scope,
        limit=8,
        include_snippets=True,
    )
    assert archive_result.fts_query is None
    assert {hit["fts_doc_uid"] for hit in archive_result.hits} == {
        "grounded-2025",
        "current-turn-echo",
    }

    memory_context: dict[str, Any] = {
        "query_terms": plan.search_terms,
        "memory_search_plan": plan.to_dict(),
        "conversation_archive_hits": _archive_context(archive_result.hits),
        "counts": {"conversation_archive_hits": len(archive_result.hits)},
    }
    memory_context["memory_recall_payload"] = MemoryRecallPresenter().build_payload(
        memory_context,
        user_text=INITIAL_RECALL,
        limit=6,
    )
    payload = memory_context["memory_recall_payload"]

    assert len(payload["items"]) == 1
    assert payload["items"][0]["content_excerpt"] == SOURCE_EXCERPT
    assert INITIAL_RECALL not in str(payload["items"])

    initial_result = dispatcher.dispatch(
        initial_entry,
        INITIAL_RECALL,
        {"memory_context": memory_context},
    )
    assert initial_result.handler_name == "MemoryExperienceRecallHandler"
    assert SOURCE_EXCERPT in initial_result.body
    assert "synthetic-conversation-archive" in initial_result.body
    assert "memory_recall_payload" not in initial_result.body

    state = DialogueTaskStateResolver.derive_state(
        user_text=INITIAL_RECALL,
        intent=initial_report.primary_intent,
        route=initial_entry.route,
        confidence=initial_report.confidence,
    )
    state = DialogueTaskStateResolver.bind_memory_evidence(state, payload)
    original_anchor = _anchor_snapshot(state)

    follow_up = "A co wtedy czułaś?"
    follow_report = classifier.classify(
        follow_up,
        previous_text=INITIAL_RECALL,
        previous_intent=initial_report.primary_intent,
        previous_route=initial_entry.route,
        previous_task_state=state.to_dict(),
    )
    follow_resolution = resolver.resolve(
        current_text=follow_up,
        previous_task_state=state,
    )
    follow_result = dispatcher.dispatch(
        registry.resolve(follow_report.primary_intent),
        follow_up,
        {"memory_context": memory_context},
    )

    assert follow_report.primary_intent == "memory_experience_question"
    assert follow_resolution.inherited is True
    assert _anchor_snapshot(follow_resolution.task_state) == original_anchor
    assert "czułam wtedy spokój i bliskość" in follow_result.body

    correction = "Nie tak — właściwie spacer był nad jeziorem, nie nad rzeką."
    corrected = DialogueTaskStateResolver.derive_state(
        user_text=correction,
        intent="memory_experience_question",
        route="memory_experience_recall",
        previous_state=follow_resolution.task_state,
        confidence=0.97,
    )
    assert _anchor_snapshot(corrected) == original_anchor
    assert corrected.memory_corrections[-1]["text"] == correction
    assert corrected.memory_corrections[-1]["truth_status"] == "user_asserted_overlay"
    assert corrected.memory_corrections[-1]["historical_source_unchanged"] is True
    assert "nad rzeką" in payload["items"][0]["content_excerpt"]
    assert "nad jeziorem" not in payload["items"][0]["content_excerpt"]

    switched = DialogueTaskStateResolver.derive_state(
        user_text="A teraz porozmawiajmy o jazzie.",
        intent="ordinary_conversation",
        route="ordinary_dialogue",
        previous_state=corrected,
    )
    assert switched.memory_anchor_status == "suspended"
    assert _anchor_snapshot(switched) == original_anchor

    isolated_runtime_root = tmp_path / "isolated-runtime-fixture"
    isolated_workspace = isolated_runtime_root / "workspace_runtime"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(isolated_workspace))
    first_store = RuntimeSessionStateStore(isolated_runtime_root)
    session = first_store.load_or_create(
        session_id="v1630-synthetic-round-trip",
        source_client="pytest",
    )
    session.update(
        user_text="A teraz porozmawiajmy o jazzie.",
        visible_text="Porozmawiajmy o jazzie.",
        intent="ordinary_conversation",
        route="ordinary_dialogue",
        task_state=switched.to_dict(),
    )
    saved = first_store.save(session, continuity_context=_wake(), turn_count=4)
    assert saved["session_state_saved"] is True
    assert Path(saved["session_state_path"]).is_relative_to(isolated_workspace)

    restarted_store = RuntimeSessionStateStore(isolated_runtime_root)
    restored_session = restarted_store.load_or_create(
        session_id=session.session_id,
        source_client="pytest",
    )
    continuity = restarted_store.verify_loaded_continuity(restored_session, _wake())
    restored_anchor = DialogueTaskState.from_mapping(restored_session.task_state)

    assert continuity["status"] == "verified"
    assert continuity["carryover_allowed"] is True
    assert _anchor_snapshot(restored_anchor) == original_anchor
    assert restored_anchor.memory_corrections == corrected.memory_corrections

    return_text = "Wróćmy do tamtego wspomnienia."
    returned = resolver.resolve(
        current_text=return_text,
        previous_task_state=restored_anchor,
        carryover_allowed=bool(continuity["carryover_allowed"]),
    )
    return_result = dispatcher.dispatch(
        registry.resolve(returned.resolved_intent or "ordinary_conversation"),
        return_text,
        {"memory_context": memory_context},
    )

    assert returned.inherited is True
    assert returned.resolution_type == "memory_return_inherits_anchor"
    assert _anchor_snapshot(returned.task_state) == original_anchor
    assert SOURCE_EXCERPT in return_result.body
    assert correction not in return_result.body

    echo_only = dispatcher.dispatch(
        initial_entry,
        "To jest wyłącznie bieżąca wiadomość, nie historyczny ślad.",
        {
            "memory_context": {
                "memory_recall_payload": {
                    "items": [
                        {
                            "content_excerpt": "To jest wyłącznie bieżąca wiadomość, nie historyczny ślad.",
                            "source": "current_turn",
                        }
                    ]
                }
            }
        },
    )
    assert echo_only.data["status"] == "grounded_payload_empty"
    assert echo_only.memory_sources == []
    assert "nie mogę uczciwie wygenerować wspomnienia" in echo_only.body
    assert "To jest wyłącznie bieżąca wiadomość" not in echo_only.body
