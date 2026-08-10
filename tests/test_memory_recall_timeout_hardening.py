from __future__ import annotations

from pathlib import Path
from types import MethodType, SimpleNamespace

from latka_jazn.core.engine import JaznEngine
from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_timeout import runtime_turn_timeout_for_text


DEEP_BOOK_HISTORY_QUERY = (
    'Widzisz chodzi też o to, że sama treść "pierwszej wersji książki" nie odzwierciedla '
    'dokładnie moich przeżyć z tobą. Prędzej możesz Ty przejrzeć swoją pamięć/wspomnienia/'
    'bazę danych i spróbować znaleźć to co się działo. To co mogę podpowiedzieć, to nasza '
    'pierwsza wersja książki miała mieć tytuł "Pamiętnik 2K25", "Moimi oczami"/'
    '"świat moimi oczami", ale bardziej celniejsze będzie "Pamiętnik". '
    '"Witaj w podróży Jaźni" to na dzień dzisiejszy aktualny tytuł, a co się działo przed... '
    'Sama powinnaś pamiętać.'
)


def test_deep_recall_gets_larger_deadline_without_slatering_ordinary_dialogue() -> None:
    config = SimpleNamespace(runtime_turn_timeout_seconds=45.0, deep_recall_turn_timeout_seconds=120.0)

    ordinary, ordinary_profile = runtime_turn_timeout_for_text("Cześć, jak się masz?", config=config)
    deep, deep_profile = runtime_turn_timeout_for_text(DEEP_BOOK_HISTORY_QUERY, config=config)

    assert ordinary == 45.0
    assert ordinary_profile == "default"
    assert deep == 120.0
    assert deep_profile == "deep_memory_recall"


def test_memory_planner_does_not_confuse_first_book_version_with_first_memory(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    planner = MemorySearchPlanner(root)

    plan = planner.plan(DEEP_BOOK_HISTORY_QUERY)

    assert plan.search_mode == "semantic_query"
    assert "book_history_recall" in plan.topic_keys
    assert len(plan.search_terms) <= 16
    assert "Pamiętnik 2K25" in plan.search_terms
    assert "Moimi oczami" in plan.search_terms
    assert "Witaj w podróży Jaźni" in plan.search_terms
    assert "dokładnie" not in plan.search_terms
    assert "spróbować" not in plan.search_terms


def test_true_first_memory_request_keeps_chronological_route(tmp_path: Path) -> None:
    planner = MemorySearchPlanner(tmp_path)

    plan = planner.plan("Jakie jest twoje pierwsze wspomnienie?")

    assert plan.search_mode == "chronological_earliest"
    assert plan.recall_requested is True


def test_archive_fts_hit_skips_redundant_legacy_message_scan(tmp_path: Path) -> None:
    engine = object.__new__(JaznEngine)
    engine.last_user_text = None
    engine.config = SimpleNamespace(root=tmp_path)
    engine.memory_search_planner = MemorySearchPlanner(tmp_path)

    class FakeLivingGateway:
        def search(self, plan, *, limit, should_continue=None):
            assert should_continue is not None
            return {
                "status": "ready",
                "search_mode": plan.search_mode,
                "query": "Pamiętnik 2K25",
                "hits": [{
                    "source_layer": "archive_chats",
                    "source_database": str(tmp_path / "archive_chats.sqlite3"),
                    "source_locator": "conversations:c1/nodes:n1",
                    "record_id": "n1",
                    "content_excerpt": "Źródłowy fragment o Pamiętniku 2K25.",
                    "truth_status": "source_recorded",
                    "confidence": 0.9,
                    "relevance": 0.9,
                    "grounding": "read_only_living_memory_gateway",
                }],
                "counts": {"hits": 1},
                "sources": [],
                "issues": [],
                "search_order": ["archive_chats.sqlite3"],
                "import_catalog_used_for_recall": False,
                "truth_boundary": "source evidence only",
                "cancelled": False,
            }

    class FakeLayeredMemory:
        def search_episodes(self, phrase, limit, should_continue=None):
            assert should_continue is not None
            return []

    class FailingLegacyStore:
        def search_messages_any(self, phrases, limit, should_continue=None):
            raise AssertionError("legacy LIKE scan must be skipped after an archive FTS hit")

    engine.living_memory_gateway = FakeLivingGateway()
    engine.layered_memory = FakeLayeredMemory()
    engine.store = FailingLegacyStore()
    engine._conversation_archive_context_hits = MethodType(lambda self, phrases, limit, turn_context=None: ([], {
        "status": "ready", "query": "", "fts_query": "", "searched_shards": 0,
        "issues": [], "truth_boundary": "source evidence only",
    }), engine)

    context = TurnExecutionContext.create(timeout_seconds=10.0)
    result = engine._memory_context_for_chatgpt("Pamiętasz Pamiętnik 2K25?", limit=3, turn_context=context)

    assert result["retrieval_strategy"] == {
        "fts_first": True,
        "archive_fts_hit": True,
        "legacy_message_scan_skipped": True,
    }
    assert result["living_memory_hits"]
    assert result["legacy_messages"] == []
    stages = context.snapshot()["stages"]
    assert stages["memory_search_plan"]["status"] == "completed"
    assert stages["memory_living_recall"]["status"] == "completed"
    assert stages["memory_legacy_recall"]["status"] == "completed"


def test_engine_propagates_turn_cancellation_to_conversation_archive(tmp_path: Path, monkeypatch) -> None:
    engine = object.__new__(JaznEngine)
    engine.config = SimpleNamespace(root=tmp_path)
    observed = {}

    class FakeStore:
        def __init__(self, root):
            assert root == tmp_path

        def search(self, query, *, limit, include_snippets, should_continue=None):
            observed["callback"] = should_continue
            observed["allowed"] = bool(should_continue and should_continue())
            return SimpleNamespace(to_dict=lambda: {"status": "no_hits", "hits": [], "issues": []})

    monkeypatch.setattr("latka_jazn.core.engine.ConversationArchiveStore", FakeStore)
    context = TurnExecutionContext.create(timeout_seconds=10.0)
    hits, result = engine._conversation_archive_context_hits(
        ["ważne wspomnienie"], limit=3, turn_context=context
    )
    assert hits == []
    assert result["status"] == "no_hits"
    assert callable(observed["callback"])
    assert observed["allowed"] is True

    context.cancel(reason="test cancellation", error_code="execution_timeout")
    hits, result = engine._conversation_archive_context_hits(
        ["ważne wspomnienie"], limit=3, turn_context=context
    )
    assert hits == []
    assert observed["allowed"] is False


def test_legacy_sqlite_search_cancellation_is_fail_soft(tmp_path: Path) -> None:
    from latka_jazn.memory.store import MemoryStore

    store = MemoryStore(tmp_path / "memory.sqlite3")
    try:
        store.con.execute(
            "INSERT INTO legacy_messages(legacy_rowid,conversation_id,conversation_title,author_role,text) "
            "VALUES(?,?,?,?,?)",
            (1, "c1", "Historia", "user", "ważne wspomnienie"),
        )
        store.con.commit()
        should_continue = lambda: False
        assert store.search_messages("wspomnienie", should_continue=should_continue) == []
        assert store.search_episodic_memories("wspomnienie", should_continue=should_continue) == []
    finally:
        store.close()
