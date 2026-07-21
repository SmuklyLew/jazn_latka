from __future__ import annotations

from pathlib import Path
import threading
import time

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.turn_execution import TurnExecutionContext
from latka_jazn.core.turn_timeout import RuntimeSessionWorker, RuntimeTurnTimeoutError


class _SlowSession:
    started = threading.Event()
    release = threading.Event()

    def __init__(self, _config, **kwargs) -> None:
        self.state = type("State", (), {"session_id": kwargs.get("session_id")})()

    def process_user_text(self, user_text: str, *, _turn_context: TurnExecutionContext, **_kwargs) -> dict:
        assert user_text == "slow"
        self.started.set()
        self.release.wait(2.0)
        return {"ok": True, "final_visible_text": "late"}

    def close(self) -> None:
        return


def test_execution_timeout_does_not_wait_for_slow_technical_audit(tmp_path: Path, monkeypatch) -> None:
    audit_started = threading.Event()
    release_audit = threading.Event()

    def slow_persist_audit(self, *, event_type: str = "runtime_turn_telemetry") -> dict:
        audit_started.set()
        release_audit.wait(2.0)
        return {
            "ok": True,
            "available": True,
            "event_type": event_type,
            "technical_event_count": 1,
            "error_code": None,
            "error": None,
        }

    monkeypatch.setattr(TurnExecutionContext, "persist_audit", slow_persist_audit)
    _SlowSession.started = threading.Event()
    _SlowSession.release = threading.Event()
    worker = RuntimeSessionWorker(
        session_factory=_SlowSession,
        config=JaznConfig(root=tmp_path),
        session_id="slow-audit-timeout",
        no_carryover=False,
        source_client="isolated-test",
        command="isolated-test",
        timeout_seconds=0.03,
    )
    started = time.perf_counter()
    try:
        with pytest.raises(RuntimeTurnTimeoutError):
            worker.process_user_text("slow", request_id="slow-audit-timeout-request")
        elapsed = time.perf_counter() - started
        assert _SlowSession.started.is_set()
        assert elapsed < 0.5
        assert audit_started.wait(1.0)
        assert worker.timed_out is True
        assert worker.usable is False
    finally:
        release_audit.set()
        _SlowSession.release.set()
        worker.close()
