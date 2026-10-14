from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.memory.memory_tiers import MemoryTier


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
    # Full transactional-memory acceptance requires a synthetic explicit
    # MEMORY attachment. Bare operational SQLite is never evidence of recall.
    memory_root = tmp_path / "memory"
    legacy_source = memory_root / "raw" / "dziennik.json"
    legacy_source.parent.mkdir(parents=True, exist_ok=True)
    legacy_source.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    assert JaznConfig(root=tmp_path).memory_availability.persistent_memory_enabled

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
            # Three records: a provenance-verified wake-state L1, a turn L1
            # and one turn L2. The wake record is intentionally retained by
            # ConversationRunner; do not disguise it as a duplicate turn write.
            assert stats["memory_records"] == 3
            assert stats["working_memory_index"] == 2
            assert stats["short_term_memory_index"] == 1

            wake_status = session.wake_state_runtime_status
            assert wake_status.status == "hydrated"
            assert wake_status.l1_memory_id is not None
            working_records = store.list_records(tier=MemoryTier.WORKING)
            assert len(working_records) == 2
            wake_records = [record for record in working_records if record.mode == "wake_state"]
            turn_records = [record for record in working_records if record.mode != "wake_state"]
            assert len(wake_records) == 1
            assert len(turn_records) == 1
            wake_record, turn_record = wake_records[0], turn_records[0]
            assert wake_record.memory_id == wake_status.l1_memory_id
            assert wake_record.domain == "runtime_continuity"
            assert wake_record.session_id == session.state.session_id
            assert wake_record.turn_id is None
            assert any(e.source_type == "wake_state_snapshot" for e in wake_record.evidence)
            assert turn_record.session_id == session.state.session_id
            assert turn_record.turn_id is not None
            assert turn_record.memory_id != wake_record.memory_id
            assert all(e.source_type != "wake_state_snapshot" for e in turn_record.evidence)
            assert stats["long_term_memory_index"] == 0
            assert stats["promotion_requests"] == 0
            assert stats["promotion_decisions"] == 0
            assert stats["promotion_ledger"] == 0
            assert stats["memory_outbox"] == 1
            assert store.validate(full=True)["ok"] is True
    finally:
        session.close()
