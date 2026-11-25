"""The client lock and stale failure proof checks do not require Qt."""
from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest

from tools.jazn_run_studio.core import StudioError
from test_jazn_chat_terminal_recovery import _client, _failed_result, _live_validation


@pytest.mark.parametrize("changed", ["proof", "gui_ack", "endpoint"])
def test_terminal_failure_recheck_never_archives_a_changed_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    from dataclasses import replace

    client, core = _client(tmp_path, monkeypatch)
    _live_validation(client, monkeypatch)
    client.receive(_failed_result(client))
    assert client.can_resolve_terminal_failure()
    entered, release, mutated = Event(), Event(), Event()
    failures: list[Exception] = []

    def verify(*_a: Any, **kwargs: Any) -> dict[str, str] | None:
        entered.set()
        if not release.wait(5):
            raise TimeoutError("synthetic watchdog")
        return kwargs["expected_proof"]

    def resolve() -> None:
        try:
            client.resolve_terminal_failure("studio-turn-1")
        except (StudioError, OSError, ValueError) as exc:
            failures.append(exc)

    def change() -> None:
        with client.lock:
            if changed == "proof":
                client._confirmed_failed = None
            elif changed == "gui_ack":
                client._awaiting_gui_ack = "studio-turn-1"
            else:
                core.settings = replace(core.settings, daemon_url="http://127.0.0.1:8879")
            mutated.set()

    monkeypatch.setattr(client, "_verify_terminal_failure", verify)
    worker = Thread(target=resolve, daemon=True)
    changer = Thread(target=change, daemon=True)
    worker.start()
    try:
        assert entered.wait(2)
        changer.start()
        assert mutated.wait(2), "network verification held the client lock"
    finally:
        release.set()
        worker.join(5)
        if changer.ident is not None:
            changer.join(5)
    assert not worker.is_alive()
    assert not changer.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], StudioError)
    assert client.pending == "studio-turn-1"
    assert not list(tmp_path.glob("chat-terminal-failure-*.json"))
