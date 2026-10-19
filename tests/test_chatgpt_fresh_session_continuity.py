from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import (
    _build_session_continuity_commit,
    _canonical_mapping_sha256,
    _commit_host_finalized_session_continuity,
)
from latka_jazn.core.runtime_session_state import (
    RuntimeSessionState,
    RuntimeSessionStateStore,
)


def _phase_one(session: RuntimeSessionState, root: Path) -> dict:
    return _build_session_continuity_commit(
        {
            "session": session.to_dict(),
            "session_provenance": {"continuity_turn_count": 0},
            "trace": {"turn_id": "fresh-turn", "trace_id": "fresh-trace"},
            "conversation_decision": {
                "dialogue_task_state": {"active_intent": "ordinary_dialogue"},
            },
        },
        user_text="Pierwsza wiadomość",
        detected_intent="ordinary_dialogue",
        runtime_route="ordinary_dialogue",
        config=JaznConfig(root=root),
    )


def test_first_host_turn_persists_phase_one_baseline_before_cas(tmp_path: Path) -> None:
    runtime_session = RuntimeSessionState.create(
        session_id="fresh-chatgpt-session", source_client="chatgpt_host"
    )
    assert not RuntimeSessionStateStore(tmp_path)._path_for_session(
        runtime_session.session_id
    ).exists()

    commit = _phase_one(runtime_session, tmp_path)
    assert commit["session_id"] == runtime_session.session_id
    store = RuntimeSessionStateStore(tmp_path)
    baseline = store.load_or_create(
        session_id=runtime_session.session_id, source_client="chatgpt_host"
    )
    assert store.last_load_metadata["session_resurrected_from_disk"] is True
    assert commit["session_state_before_sha256"] == _canonical_mapping_sha256(
        baseline.to_dict()
    )

    result = _commit_host_finalized_session_continuity(
        config=JaznConfig(root=tmp_path),
        pending={"generation_context": {"session_continuity_commit": commit}},
        binding={"session_continuity_commit_sha256": _canonical_mapping_sha256(commit)},
        final_visible_text="Odpowiedź zatwierdzona",
    )
    assert result["saved"] is True
    updated = RuntimeSessionStateStore(tmp_path).load_or_create(
        session_id=runtime_session.session_id, source_client="chatgpt_host"
    )
    assert updated.last_user_text == "Pierwsza wiadomość"
    assert updated.last_visible_text == "Odpowiedź zatwierdzona"


def test_phase_one_binds_disk_checkpoint_not_stale_daemon_projection(
    tmp_path: Path,
) -> None:
    durable = RuntimeSessionState.create(
        session_id="existing-chatgpt-session", source_client="chatgpt_host"
    )
    durable.update(
        user_text="Wcześniejsza wiadomość",
        visible_text="Wcześniejsza odpowiedź",
    )
    assert RuntimeSessionStateStore(tmp_path).save(
        durable, turn_count=1
    )["session_state_saved"]

    stale_daemon = RuntimeSessionState.create(
        session_id=durable.session_id, source_client="chatgpt_host"
    )
    commit = _phase_one(stale_daemon, tmp_path)
    assert commit["session_state_before_sha256"] == _canonical_mapping_sha256(
        durable.to_dict()
    )
    assert commit["turn_count_before"] == 1
    current = RuntimeSessionStateStore(tmp_path).load_or_create(
        session_id=durable.session_id, source_client="chatgpt_host"
    )
    assert current.last_user_text == "Wcześniejsza wiadomość"
