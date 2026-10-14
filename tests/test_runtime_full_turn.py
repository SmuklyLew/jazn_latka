from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.memory.memory_tier_store import MemoryTierStore


def _legacy_semantic_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    con = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        return {
            table: int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (
                "episodic_memories",
                "semantic_facts",
                "procedural_rules",
                "reflection_entries",
                "truth_audits",
            )
            if table in tables
        }
    finally:
        con.close()


def _safe_failure_diagnostic(result: dict) -> str:
    payload = {
        "ok": result.get("ok"),
        "normal_response_blocked": result.get("normal_response_blocked"),
        "canonical_persistence": result.get("canonical_persistence"),
        "runtime_truth_gate": result.get("runtime_truth_gate"),
        "final_visible_integrity": result.get("final_visible_integrity"),
        "final_visible_integrity_consensus": result.get("final_visible_integrity_consensus"),
        "transactional_memory": result.get("transactional_memory"),
        "conversation_route": (result.get("conversation_decision") or {}).get("route"),
        "conversation_intent": (result.get("conversation_decision") or {}).get("detected_user_intent"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def test_full_runtime_turn_commits_transactionally_without_legacy_fanout(tmp_path: Path, monkeypatch) -> None:
    # Isolated integration is CPU/CI-speed sensitive (Windows runner can take
    # longer than the 45s production default while validating memory).
    # Bound this test explicitly; do not disable or change runtime deadlines.
    monkeypatch.setenv("JAZN_RUNTIME_TURN_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("JAZN_NETWORK_TIME_FIRST", "0")
    monkeypatch.setenv("JAZN_NETWORK_TIME_IN_TURN", "0")
    monkeypatch.setenv("JAZN_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_DICTIONARY_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "null")
    (tmp_path / "main.py").write_text("# isolated runtime root\n", encoding="utf-8")
    memory_source = tmp_path / "memory" / "sqlite" / "memory_jazn.sqlite3"
    memory_source.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(memory_source) as con:
        con.execute("CREATE TABLE fixture_metadata(note TEXT)")

    session = JaznRuntimeSession(
        JaznConfig(root=tmp_path),
        session_id="transactional-full-turn",
        no_carryover=True,
        source_client="isolated-transactional-test",
    )
    try:
        # The integration test targets persistence wiring, not threshold tuning.
        # Routing, answer validation, staging and commit remain the real runtime path.
        monkeypatch.setattr(
            session.engine.runtime_memory,
            "should_persist",
            lambda _candidate: (True, "forced_for_full_turn_integration_test"),
        )
        legacy_path = session.config.memory_db_path
        before_legacy = _legacy_semantic_counts(legacy_path)

        # Health-checks intentionally skip semantic persistence, while ordinary and
        # static fallback routes require model-guided speech. The time route is both
        # deterministic and dynamic, and it truthfully discloses degraded local time.
        result = session.process_user_text(
            "Jaka jest godzina?",
            client="isolated-transactional-test",
            lifecycle="persistent_daemon_async_job",
            process_reused=True,
        )

        after_legacy = _legacy_semantic_counts(legacy_path)
        assert result["ok"] is True, _safe_failure_diagnostic(result)
        assert result["canonical_persistence"]["committed"] is True, _safe_failure_diagnostic(result)
        assert result["transactional_memory"]["available"] is True
        assert result["transactional_memory"]["store"]["ready"] is True
        assert result["session_provenance"]["transactional_memory_ready"] is True
        assert before_legacy == after_legacy

        database = Path(result["transactional_memory"]["install"]["database_path"])
        with MemoryTierStore(database) as store:
            stats = store.stats()
            # An explicit legacy MEMORY fixture activates transactional L1/L2.
            # The runtime-created wake snapshot is source-recorded and must
            # never be counted as an autobiographical recollection or L3 promotion.
            assert stats["memory_records"] == 3
            assert stats["working_memory_index"] == 2
            assert stats["short_term_memory_index"] == 1
            assert stats["long_term_memory_index"] == 0
            assert stats["promotion_requests"] == 0
            assert stats["promotion_decisions"] == 0
            assert stats["promotion_ledger"] == 0
            assert stats["memory_outbox"] == 1
            assert store.validate(full=True)["ok"] is True
            with sqlite3.connect(database) as con:
                sources = [row[0] for row in con.execute("SELECT source_type FROM memory_evidence")]
            assert sources.count("wake_state_snapshot") == 1
            assert sources.count("runtime_turn") == 2
    finally:
        session.close()


def test_system_only_full_turn_keeps_core_operational_without_false_autobiographical_memory(tmp_path: Path, monkeypatch) -> None:
    # Keep SYSTEM-only separate from the explicitly attached-memory integration.
    monkeypatch.setenv("JAZN_RUNTIME_TURN_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("JAZN_NETWORK_TIME_FIRST", "0")
    monkeypatch.setenv("JAZN_NETWORK_TIME_IN_TURN", "0")
    monkeypatch.setenv("JAZN_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_DICTIONARY_ALLOW_NETWORK", "0")
    monkeypatch.setenv("JAZN_MODEL_ADAPTER", "null")
    (tmp_path / "main.py").write_text("# isolated runtime root\n", encoding="utf-8")
    config = JaznConfig(root=tmp_path)
    session = JaznRuntimeSession(config, session_id="system-only-no-private-recall", no_carryover=True,
        source_client="system-only-no-private-recall")
    try:
        result = session.process_user_text("Jaka jest godzina?", client="system-only-no-private-recall",
            lifecycle="persistent_daemon_async_job", process_reused=True)
        assert result["ok"] is True, _safe_failure_diagnostic(result)
        assert result["canonical_persistence"]["committed"] is True
        assert result["transactional_memory"]["install"]["persistent_memory_enabled"] is False
        assert result["transactional_memory"]["store"]["ready"] is False
        assert result["session_provenance"]["transactional_memory_ready"] is False
        assert not Path(result["transactional_memory"]["install"]["database_path"]).is_file()
    finally:
        session.close()
