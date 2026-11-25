"""Synthetic pipe-backpressure regressions; no Ollama, daemon or real MEMORY."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import cast

import pytest

from tools.jazn_run_studio.chat import ChatClient
from tools.jazn_run_studio.core import Controller, Job, Settings, StudioError


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text("# synthetic", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return tmp_path


class BlockedStdin:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.frames: list[bytes] = []

    def write(self, payload: bytes) -> int:
        self.entered.set()
        if not self.release.wait(5):
            raise OSError("synthetic pipe did not unblock")
        self.frames.append(payload)
        return len(payload)

    def flush(self) -> None:
        pass


def _client(root: Path) -> tuple[ChatClient, Job, BlockedStdin]:
    core = Controller(root, Settings(model="synthetic-model"))
    client = ChatClient(core)
    pipe = BlockedStdin()
    job = Job("chat")
    # Test-only synthetic Popen contract; no child process or runtime is launched.
    job.proc = cast(subprocess.Popen[bytes], SimpleNamespace(stdin=pipe, poll=lambda: None))
    client.job = job
    return client, job, pipe


def test_chat_stalled_stdin_does_not_block_qt_event_loop(synthetic_root: Path) -> None:
    """Timer must fire while the child pipe is still refusing to read stdin."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    client, _job, pipe = _client(synthetic_root)
    loop = QEventLoop()
    observed: dict[str, object] = {}
    started = time.monotonic()
    release = threading.Timer(1.0, pipe.release.set)
    release.daemon = True
    release.start()

    def submit() -> None:
        observed["request"] = client.send("Syntetyczna wiadomość")
        observed["send_returned"] = time.monotonic()

    def qt_heartbeat() -> None:
        observed["heartbeat"] = time.monotonic()
        loop.quit()

    QTimer.singleShot(0, submit)
    QTimer.singleShot(120, qt_heartbeat)
    QTimer.singleShot(2000, loop.quit)
    try:
        loop.exec()
        assert "request" in observed
        assert "heartbeat" in observed
        assert cast(float, observed["send_returned"]) - started < 0.7
        assert cast(float, observed["heartbeat"]) - started < 0.7
        assert pipe.entered.wait(1.0)
        assert client.pending == observed["request"]
        assert json.loads(client.checkpoint.read_text(encoding="utf-8"))["request_id"] == client.pending
    finally:
        pipe.release.set()
        release.cancel()
        assert pipe.release.is_set()


def test_chat_stdin_write_watchdog_preserves_identity_without_replay(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.jazn_run_studio.chat as chat_module

    monkeypatch.setattr(chat_module, "CHAT_STDIN_WRITE_TIMEOUT_SECONDS", 0.05)
    client, job, pipe = _client(synthetic_root)
    try:
        request = client.send("Nie ponawiaj wiadomości")
        assert pipe.entered.wait(1.0)
        assert job.cancel.wait(2.0)  # Own transport cancellation only.
        assert client.pending == request
        assert json.loads(client.checkpoint.read_text(encoding="utf-8"))["request_id"] == request
        with pytest.raises(StudioError, match="Najpierw odbierz"):
            client.send("Nie wolno ponowić")
    finally:
        pipe.release.set()


def test_helper_stalled_stdin_is_bounded_by_single_execution_deadline(
    synthetic_root: Path,
) -> None:
    """Real synthetic child deliberately never reads from its input pipe."""
    core = Controller(synthetic_root)
    job = core._reserve("helper:synthetic:blocking-stdin")
    # Much larger than a Windows/Linux pipe buffer, with no production data.
    job.input_data = b"x" * (4 * 1024 * 1024)
    try:
        core._launch(job, [sys.executable, "-u", "-c", "import time; time.sleep(30)"], 1)
        assert job.done.wait(9), "Job stalled before its timeout watchdog"
        assert job.state == "failed"
        assert job.error == "timeout"
        assert job.proc is not None and job.proc.poll() is not None
        assert job.input_data is None
    finally:
        core.close()
