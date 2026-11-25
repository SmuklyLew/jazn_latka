"""Stage 05: terminal failure ACK is not a blocking GUI/network operation."""
from __future__ import annotations

from threading import Event, Thread, get_ident
from time import monotonic, sleep
from typing import Any

import pytest
from PySide6.QtWidgets import QMessageBox

from tools.jazn_run_studio.chat import ChatClient
from tools.jazn_run_studio.core import StudioError
from tests.test_jazn_run_studio_layout import window


@pytest.mark.parametrize("valid", [True, False])
def test_terminal_failure_validation_runs_off_gui_and_releases_client_lock(window: Any, monkeypatch: pytest.MonkeyPatch, valid: bool) -> None:
    client = ChatClient(window.core)
    window.core.chat = client
    request_id = "studio-turn-terminal"
    client.pending = request_id
    proof = {"request_id": request_id, "session_id": client.session_id,
             "daemon_url": client.daemon_url, "daemon_instance_id": "test-instance",
             "error_code": "synthetic_failure"}
    client._confirmed_failed = proof
    client._save()
    entered, release = Event(), Event()
    gui_thread_id = get_ident()
    observed: list[int] = []

    def verify(*_a: Any, **_k: Any) -> dict[str, str] | None:
        observed.append(get_ident())
        entered.set()
        if not release.wait(5):
            raise TimeoutError("synthetic test watchdog")
        return dict(proof) if valid else None

    monkeypatch.setattr(client, "_verify_terminal_failure", verify)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    try:
        window.close_failed_chat()
        assert entered.wait(2)
        assert observed and observed[0] != gui_thread_id
        assert client.pending == request_id
        assert not window.close_failed_chat_button.isEnabled()
        # GUI's status poll must still be able to acquire the client lock
        # while the worker awaits the network.
        lock_observed = Event()

        def check_lock() -> None:
            if client.can_resolve_terminal_failure():
                lock_observed.set()

        observer = Thread(target=check_lock, daemon=True)
        observer.start()
        assert lock_observed.wait(1)
        observer.join(1)
        with pytest.raises(StudioError):
            window.close_failed_chat()
        with pytest.raises(StudioError):
            window.send_chat()
        assert not client.checkpoint.with_name("chat-terminal-failure-" + request_id + ".json").exists()
    finally:
        release.set()
    deadline = monotonic() + 5
    while window._terminal_failure_inflight is not None and monotonic() < deadline:
        window._poll_terminal_failure_resolution()
        sleep(0.01)
    assert window._terminal_failure_inflight is None
    assert window.close_failed_chat_button.isEnabled()
    archive = client.checkpoint.with_name("chat-terminal-failure-" + request_id + ".json")
    assert archive.exists() is valid
    assert client.pending == (None if valid else request_id)
