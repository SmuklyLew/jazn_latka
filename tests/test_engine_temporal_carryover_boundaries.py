from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, cast

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.memory_intent_contract import parse_temporal_scope
from latka_jazn.core.memory_recall_presenter import MemoryRecallPresenter
from latka_jazn.core.memory_search_planner import MemorySearchPlanner


def _scope_2025() -> dict[str, Any]:
    scope = parse_temporal_scope("2025 rok")
    assert scope is not None
    return scope.to_dict()


def _epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def test_presenter_enforces_half_open_temporal_scope_fail_closed() -> None:
    scope = _scope_2025()
    context = {
        "query_terms": ["projekt"],
        "memory_search_plan": {"temporal_scope": scope},
        "episodes": [
            {
                "scene": "EP START 2025",
                "created_at_utc": scope["start_utc"],
                "local_time_label": "2025-01-01T00:00:00+01:00",
                "source": "episodic",
            },
            {
                "scene": "EP END EXCLUSIVE",
                "created_at_utc": scope["end_utc_exclusive"],
                "source": "episodic",
            },
            {
                "scene": "EP 2022",
                "created_at_utc": "2022-07-01T12:00:00+00:00",
                "source": "episodic",
            },
            {"scene": "EP BEZ DATY", "source": "episodic"},
        ],
        "legacy_messages": [
            {
                "text": "LEGACY 2025",
                "create_time": _epoch("2025-06-15T10:00:00Z"),
                "create_time_warsaw": "2025-06-15T12:00:00+02:00",
            },
            {
                "text": "LEGACY 2023",
                "create_time": _epoch("2023-06-15T10:00:00Z"),
                "create_time_warsaw": "2023-06-15T12:00:00+02:00",
            },
            {"text": "LEGACY BEZ DATY"},
        ],
        "source_file_hits": [
            {
                "path": "memory/raw/timeless.txt",
                "content_excerpt": "SOURCE FILE BEZ DATY",
                "source_label": "canonical_source_file",
            }
        ],
        "counts": {},
    }

    payload = MemoryRecallPresenter().build_payload(
        context,
        user_text="Co pamiętasz z projektu w 2025 roku?",
        limit=20,
    )

    excerpts = {str(item["content_excerpt"]) for item in payload["items"]}
    assert excerpts == {"EP START 2025", "LEGACY 2025"}


def test_engine_filters_legacy_layers_before_final_memory_payload(tmp_path: Path) -> None:
    engine = object.__new__(JaznEngine)
    engine.last_user_text = None
    engine.config = JaznConfig(root=tmp_path)
    engine.memory_search_planner = MemorySearchPlanner(tmp_path)

    class FakeLivingGateway:
        def search(self, plan, *, limit, should_continue=None):
            del plan, limit, should_continue
            return {
                "status": "ready",
                "search_mode": "semantic_query",
                "query": "projekt",
                "hits": [
                    {
                        "record_id": "living-2025",
                        "source_layer": "experience",
                        "content_excerpt": "LIVING 2025",
                        "timestamp": "2025-03-01T10:00:00+00:00",
                        "truth_status": "source_recorded",
                    },
                    {
                        "record_id": "living-2022",
                        "source_layer": "experience",
                        "content_excerpt": "LIVING 2022",
                        "timestamp": "2022-03-01T10:00:00+00:00",
                        "truth_status": "source_recorded",
                    },
                ],
                "counts": {"hits": 2},
                "sources": [],
                "issues": [],
                "search_order": [],
                "import_catalog_used_for_recall": False,
                "truth_boundary": "source evidence only",
                "cancelled": False,
            }

    class FakeLayeredMemory:
        def search_episodes(self, phrase, limit, should_continue=None):
            del phrase, limit, should_continue
            return [
                {
                    "episode_id": "ep-2025",
                    "scene": "ENGINE EP 2025",
                    "created_at_utc": "2025-04-01T10:00:00+00:00",
                    "source": "episodic",
                },
                {
                    "episode_id": "ep-2022",
                    "scene": "ENGINE EP 2022",
                    "created_at_utc": "2022-04-01T10:00:00+00:00",
                    "source": "episodic",
                },
                {
                    "episode_id": "ep-undated",
                    "scene": "ENGINE EP BEZ DATY",
                    "source": "episodic",
                },
            ]

    class FakeLegacyStore:
        def search_messages_any(self, phrases, limit, should_continue=None):
            del phrases, limit, should_continue
            return [
                {
                    "conversation_id": "legacy-2025",
                    "author_role": "assistant",
                    "text": "ENGINE LEGACY 2025",
                    "create_time": _epoch("2025-05-01T10:00:00Z"),
                    "create_time_warsaw": "2025-05-01T12:00:00+02:00",
                },
                {
                    "conversation_id": "legacy-2023",
                    "author_role": "assistant",
                    "text": "ENGINE LEGACY 2023",
                    "create_time": _epoch("2023-05-01T10:00:00Z"),
                    "create_time_warsaw": "2023-05-01T12:00:00+02:00",
                },
                {
                    "conversation_id": "legacy-undated",
                    "author_role": "assistant",
                    "text": "ENGINE LEGACY BEZ DATY",
                },
            ]

    def fail_source_file_scan(self, plan, *, limit=6, per_file=2):
        del self, plan, limit, per_file
        raise AssertionError("timeless source-file scan must be skipped for temporal recall")

    def empty_archive(self, phrases, *, limit=5, turn_context=None, temporal_scope=None):
        del self, phrases, limit, turn_context
        expected_scope = _scope_2025()
        assert temporal_scope is not None
        assert temporal_scope["start_epoch"] == expected_scope["start_epoch"]
        assert temporal_scope["end_epoch_exclusive"] == expected_scope["end_epoch_exclusive"]
        return [], {
            "status": "no_hits",
            "query": "projekt",
            "fts_query": "projekt",
            "searched_shards": 1,
            "temporal_scope": temporal_scope,
            "issues": [],
        }

    test_engine = cast(Any, engine)
    test_engine.living_memory_gateway = FakeLivingGateway()
    test_engine.layered_memory = FakeLayeredMemory()
    test_engine.store = FakeLegacyStore()
    test_engine.memory_search_planner.search_source_files = MethodType(
        fail_source_file_scan,
        test_engine.memory_search_planner,
    )
    test_engine._conversation_archive_context_hits = MethodType(empty_archive, engine)

    result = engine._memory_context_for_chatgpt(
        "Co pamiętasz z naszych rozmów o projekcie w 2025 roku?",
        limit=20,
    )

    assert [item["scene"] for item in result["episodes"]] == ["ENGINE EP 2025"]
    assert [item["text"] for item in result["legacy_messages"]] == ["ENGINE LEGACY 2025"]
    assert [item["content_excerpt"] for item in result["living_memory_hits"]] == ["LIVING 2025"]
    assert result["source_file_hits"] == []
    payload_excerpts = {
        str(item["content_excerpt"])
        for item in result["memory_recall_payload"]["items"]
    }
    assert payload_excerpts == {"ENGINE EP 2025", "ENGINE LEGACY 2025", "LIVING 2025"}


def test_process_turn_no_carryover_scrubs_previous_task_before_frame() -> None:
    class StopAfterFrame(RuntimeError):
        pass

    captured: dict[str, Any] = {}
    engine = object.__new__(JaznEngine)
    engine.last_turn_at = None
    engine.last_user_text = "Powspominaj 2025 rok."
    engine.last_detected_intent = "memory_experience_question"
    engine.last_runtime_route = "memory_experience_recall"
    engine.last_dialogue_task_state = {
        "active": True,
        "memory_query": "Powspominaj 2025 rok.",
    }

    def audit_started(self, text, ctx):
        del self, text
        captured["audit_context"] = dict(ctx)

    class FakeTurnContextResolver:
        def resolve(self, **kwargs):
            captured["resolver_previous_task_state"] = kwargs["previous_task_state"]
            return SimpleNamespace(carryover_allowed=False)

    class FakeClassifier:
        def classify(self, text, **kwargs):
            del text
            captured["classifier_previous_task_state"] = kwargs["previous_task_state"]
            return SimpleNamespace(
                primary_intent="ordinary_conversation",
                to_dict=lambda: {
                    "primary_intent": "ordinary_conversation",
                    "confidence": 0.9,
                },
            )

    def previous_state_must_not_be_resolved(self, client_context, *, carryover_allowed):
        del self, client_context, carryover_allowed
        raise AssertionError("no_carryover must bypass previous task state resolution")

    def gated_memory_context(
        self,
        text,
        limit=5,
        *,
        intent_report=None,
        intent_tags=None,
        turn_context=None,
        previous_query=None,
    ):
        del self, text, limit, intent_report, intent_tags, turn_context
        captured["memory_previous_query"] = previous_query
        return {"counts": {}}

    def stop_at_frame(self, text, *, client_context, turn_context, intent_report):
        captured["frame_context"] = dict(client_context)
        self._turn_memory_context(text, intent_report, turn_context, client_context)
        raise StopAfterFrame

    test_engine = cast(Any, engine)
    test_engine._audit_process_turn_started = MethodType(audit_started, engine)
    test_engine.turn_context_resolver = FakeTurnContextResolver()
    test_engine.dialogue_intent_classifier = FakeClassifier()
    test_engine._previous_task_state_for_turn = MethodType(
        previous_state_must_not_be_resolved,
        engine,
    )
    test_engine._gated_memory_context_for_chatgpt = MethodType(gated_memory_context, engine)
    test_engine.build_cognitive_frame = MethodType(stop_at_frame, engine)

    with pytest.raises(StopAfterFrame):
        engine.process_turn(
            "Porozmawiajmy o czymś nowym.",
            client_context={
                "no_carryover": True,
                "previous_task_state": {
                    "active": True,
                    "memory_query": "Powspominaj 2025 rok.",
                },
            },
        )

    assert "previous_task_state" not in captured["audit_context"]
    assert captured["resolver_previous_task_state"] == {}
    assert captured["classifier_previous_task_state"] is None
    assert "previous_task_state" not in captured["frame_context"]
    assert captured["memory_previous_query"] == ""


def test_disallowed_carryover_removes_previous_task_state_from_context() -> None:
    engine = object.__new__(JaznEngine)
    engine.last_dialogue_task_state = {"active": True, "memory_query": "stary fallback"}
    context = {"previous_task_state": {"active": True, "memory_query": "stary stan"}}

    state = engine._previous_task_state_for_turn(context, carryover_allowed=False)

    assert state == {}
    assert "previous_task_state" not in context
