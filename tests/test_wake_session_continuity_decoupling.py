from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
from latka_jazn.memory.wake_state_runtime import WakeStateRuntimeBridge


def _wake(snapshot: str = "wake-1", digest: str = "a" * 64) -> dict[str, object]:
    return {
        "status": "hydrated",
        "ok": True,
        "snapshot_id": snapshot,
        "snapshot_sha256": digest,
        "source_run_id": "run-1",
        "validation_status": "valid",
    }


def _wake_missing() -> dict[str, object]:
    return {
        "status": "sidecar_missing",
        "ok": False,
        "snapshot_id": None,
        "snapshot_sha256": None,
        "source_run_id": None,
        "validation_status": None,
    }


def _source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE messages(
              message_id TEXT, conversation_id TEXT, conversation_title TEXT, role TEXT,
              timestamp TEXT, content_text TEXT, content_hash TEXT, first_source_file TEXT,
              first_source_sha256 TEXT, source_refs_json TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta(key,value) VALUES('created_by','wake-session-continuity-test');
            """
        )
        text = "verified local recovery source"
        con.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "m1",
                "c1",
                "Continuity",
                "user",
                "2026-08-20T10:00:00+00:00",
                text,
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source.json",
                "a" * 64,
                "[]",
                "2026-08-20T10:00:00+00:00",
                "2026-08-20T10:00:00+00:00",
            ),
        )
        con.commit()


def test_hash_verified_dialogue_checkpoint_survives_when_wake_was_never_available(tmp_path: Path) -> None:
    first = RuntimeSessionStateStore(tmp_path)
    state = first.load_or_create(source_client="chatgpt_host")
    state.update(
        user_text="co dalej?",
        intent="task_continuation",
        route="ordinary_dialogue",
        task_state={"status": "active", "active_goal": "finish memory rebuild"},
    )
    saved = first.save(state, continuity_context=_wake_missing(), turn_count=4)
    assert saved["session_state_saved"] is True

    second = RuntimeSessionStateStore(tmp_path)
    restored = second.load_or_create(source_client="chatgpt_host")
    status = second.verify_loaded_continuity(restored, _wake_missing())

    assert status["status"] == "checkpoint_verified_wake_unavailable"
    assert status["carryover_allowed"] is True
    assert status["session_checkpoint_verified"] is True
    assert status["wake_binding_verified"] is False
    assert status["memory_continuity_claim_allowed"] is False
    assert restored.last_user_text == "co dalej?"
    assert restored.last_intent == "task_continuation"
    assert restored.task_state["active_goal"] == "finish memory rebuild"
    assert second.last_load_metadata["session_carryover_blocked"] is False


def test_hash_verified_dialogue_checkpoint_survives_temporary_wake_unavailability(tmp_path: Path) -> None:
    first = RuntimeSessionStateStore(tmp_path)
    state = first.load_or_create(source_client="chatgpt_host")
    state.update(
        user_text="napraw ścieżkę",
        intent="system_update_execution_request",
        route="system_update_repair",
        task_state={"status": "active", "expected_next_action": "execute_update"},
    )
    first.save(state, continuity_context=_wake("wake-a", "b" * 64), turn_count=2)

    second = RuntimeSessionStateStore(tmp_path)
    restored = second.load_or_create(source_client="chatgpt_host")
    status = second.verify_loaded_continuity(restored, _wake_missing())

    assert status["status"] == "checkpoint_verified_wake_unavailable"
    assert status["carryover_allowed"] is True
    assert status["memory_continuity_claim_allowed"] is False
    assert restored.last_user_text == "napraw ścieżkę"
    assert restored.task_state["expected_next_action"] == "execute_update"


def test_verified_wake_mismatch_still_clears_dialogue_and_task_state(tmp_path: Path) -> None:
    first = RuntimeSessionStateStore(tmp_path)
    state = first.load_or_create(source_client="chatgpt_host")
    state.update(
        user_text="private previous turn",
        intent="private",
        route="memory",
        task_state={"status": "active", "active_goal": "private task"},
    )
    first.save(state, continuity_context=_wake("wake-old", "b" * 64), turn_count=2)

    second = RuntimeSessionStateStore(tmp_path)
    restored = second.load_or_create(source_client="chatgpt_host")
    status = second.verify_loaded_continuity(restored, _wake("wake-new", "c" * 64))

    assert status["status"] == "wake_state_binding_mismatch"
    assert status["carryover_allowed"] is False
    assert status["memory_continuity_claim_allowed"] is False
    assert restored.last_user_text is None
    assert restored.last_intent is None
    assert restored.last_route is None
    assert restored.task_state == {}


def test_hydrate_l1_rebuilds_missing_sidecar_only_from_existing_canonical_source(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    cfg = JaznConfig(root=root)
    _source(cfg.normalization_source_db_path)
    assert not cfg.normalization_sidecar_db_path.exists()

    status = WakeStateRuntimeBridge(cfg).hydrate_l1(session_id="session-test")

    assert status.status == "hydrated", status.errors
    assert status.ok is True
    assert status.continuity_claim_allowed is True
    assert cfg.normalization_sidecar_db_path.is_file()


def test_hydrate_l1_does_not_synthesize_sidecar_without_canonical_source(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    cfg = JaznConfig(root=root)
    assert not cfg.normalization_source_db_path.exists()
    assert not cfg.normalization_sidecar_db_path.exists()

    status = WakeStateRuntimeBridge(cfg).hydrate_l1(session_id="session-test")

    assert status.status == "sidecar_missing"
    assert status.ok is False
    assert status.continuity_claim_allowed is False
    assert not cfg.normalization_sidecar_db_path.exists()
