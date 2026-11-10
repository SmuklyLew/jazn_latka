"""Deterministic disposal of Tk Studio timers and outstanding dialog requests."""
from __future__ import annotations

from queue import Queue
from threading import Event
import tkinter as tk
from typing import cast

import pytest

from latka_jazn.tools.memory_rebuild_app.ui_desktop import DesktopWorkspace, TkStudioDialogs


class StubRoot:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.scheduled: list[str] = []

    def after(self, _delay: int, _callback: object) -> str:
        token = f"after-{len(self.scheduled) + 1}"
        self.scheduled.append(token)
        return token

    def after_cancel(self, token: str) -> None:
        self.cancelled.append(token)

    def winfo_exists(self) -> int:
        return 1


def test_dialog_shutdown_cancels_timer_and_releases_waiting_worker() -> None:
    root = StubRoot()
    dialogs = TkStudioDialogs(cast(tk.Tk, root))
    done = Event()
    result: dict[str, object] = {}
    dialogs._requests.put((lambda: "unwanted", done, result))

    dialogs.close()
    dialogs.close()

    assert dialogs._closed
    assert dialogs._drain_after_id is None
    assert root.cancelled == ["after-1"]
    assert done.is_set()
    assert isinstance(result["exception"], RuntimeError)
    with pytest.raises(RuntimeError, match="zamknięte"):
        dialogs._on_ui(lambda: "should not be dispatched")


def test_workspace_shutdown_is_idempotent_and_cancels_both_timers() -> None:
    root = StubRoot()
    dialogs = TkStudioDialogs(cast(tk.Tk, root))
    workspace = DesktopWorkspace.__new__(DesktopWorkspace)
    workspace.root = cast(tk.Tk, root)
    workspace.dialogs = dialogs
    workspace._closed = False
    workspace._updates_after_id = "updates-1"

    workspace.close()
    workspace.close()

    assert workspace._closed
    assert workspace._updates_after_id is None
    assert dialogs._closed
    assert root.cancelled == ["updates-1", "after-1"]
