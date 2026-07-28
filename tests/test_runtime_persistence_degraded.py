from __future__ import annotations

from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_session import JaznRuntimeSession
from latka_jazn.core.turn_execution import TurnExecutionContext


def _session(tmp_path: Path, monkeypatch) -> JaznRuntimeSession:
    for name, value in {
        "JAZN_NETWORK_TIME_FIRST": "0",
        "JAZN_NETWORK_TIME_IN_TURN": "0",
        "JAZN_ALLOW_NETWORK": "0",
        "JAZN_DICTIONARY_ALLOW_NETWORK": "0",
        "JAZN_MODEL_ADAPTER": "null",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "main.py").write_text("# isolated runtime root\n", encoding="utf-8")
    return JaznRuntimeSession(
        JaznConfig(root=tmp_path),
        session_id="persistence-degraded",
        no_carryover=True,
        source_client="test",
    )


def test_canonical_persistence_failure_preserves_valid_final(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    context = TurnExecutionContext.create(
        request_id="degraded-write",
        turn_id="degraded-turn",
        session_id=session.state.session_id,
        timeout_seconds=30,
        audit_db_path=session.config.audit_db_path,
    )
    original = context.commit_if_allowed

    def degraded(result, *, job_status):
        status = original(result, job_status=job_status)
        if status.get("committed"):
            return {
                **status,
                "committed": False,
                "reason": "canonical_commit_failed",
                "error_code": "OSError",
                "persistence_degraded": True,
            }
        return status

    monkeypatch.setattr(context, "commit_if_allowed", degraded)
    try:
        result = session.process_user_text("Jaka jest godzina?", _turn_context=context)
        assert result["answer_ok"] is True
        assert result["ok"] is True
        assert result["canonical_persistence_ok"] is False
        assert result["persistence_degraded"] is True
        assert result["persistence_state"] == "degraded"
        assert result["final_visible_text"]
    finally:
        session.close()


def test_checkpoint_failure_preserves_valid_final(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    monkeypatch.setattr(session.state_store, "save", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    try:
        result = session.process_user_text("Jaka jest godzina?")
        assert result["answer_ok"] is True
        assert result["ok"] is True
        assert result["session_persistence_ok"] is False
        assert result["persistence_degraded"] is True
        assert result["session_persistence"]["error_code"] == "OSError"
    finally:
        session.close()
