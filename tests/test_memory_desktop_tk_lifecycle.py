"""Native Memory Studio teardown must not leak scheduled Tcl callbacks."""
from __future__ import annotations

from threading import Event
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("tkinter")
import tkinter as tk

from latka_jazn.tools.memory_rebuild_app.ui_desktop import (
    DesktopWorkspace,
    TkStudioDialogs,
)


class FakeTk:
    def __init__(self) -> None:
        self.callbacks: dict[str, Any] = {}
        self.cancelled: list[str] = []
        self.destroyed = False

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def after(self, _ms: int, fn: Any) -> str:
        handle = f"timer-{len(self.callbacks) + len(self.cancelled) + 1}"
        self.callbacks[handle] = fn
        return handle

    def after_cancel(self, handle: str) -> None:
        assert handle in self.callbacks
        self.callbacks.pop(handle)
        self.cancelled.append(handle)

    def destroy(self) -> None:
        self.destroyed = True


def test_dialog_poll_cancel_and_waiting_worker_released() -> None:
    fake = FakeTk()
    dialog = TkStudioDialogs(cast(tk.Tk, fake))
    first_handle = dialog._drain_after_id
    assert first_handle in fake.callbacks

    # A pending worker must not hang after the GUI is closed.
    completed = Event()
    response: dict[str, Any] = {}
    dialog._requests.put((lambda: None, completed, response))
    dialog.close()
    assert dialog._closed
    assert not fake.callbacks
    assert fake.cancelled == [first_handle]
    assert completed.is_set()
    assert isinstance(response["exception"], RuntimeError)

    dialog.close()  # Idempotent and no duplicate Tcl cancellation.
    assert fake.cancelled == [first_handle]
    with pytest.raises(RuntimeError, match="zamknięte"):
        dialog._on_ui(lambda: None)


def test_dialog_poll_reschedules_only_before_shutdown() -> None:
    fake = FakeTk()
    dialog = TkStudioDialogs(cast(tk.Tk, fake))
    scheduled = dialog._drain_after_id
    assert scheduled is not None
    fake.callbacks.pop(scheduled)()  # Simulate the Tk event firing.
    assert dialog._drain_after_id in fake.callbacks
    dialog.close()
    assert not fake.callbacks
    dialog._drain()
    assert not fake.callbacks


def test_workspace_root_destroy_cancels_owned_timer_exactly_once() -> None:
    fake = FakeTk()
    closed: list[str] = []
    workspace = object.__new__(DesktopWorkspace)
    workspace.root = cast(tk.Tk, fake)
    workspace._closed = False
    workspace._busy = False
    workspace._updates_after_id = fake.after(80, lambda: None)
    workspace.dialogs = cast(Any, SimpleNamespace(close=lambda: closed.append("dialogs")))

    workspace._on_root_destroy(SimpleNamespace(widget=object()))
    assert fake.callbacks
    workspace._on_root_destroy(SimpleNamespace(widget=fake))
    assert workspace._closed
    assert workspace._updates_after_id is None
    assert not fake.callbacks
    assert len(fake.cancelled) == 1
    assert closed == ["dialogs"]
    workspace._on_root_destroy(SimpleNamespace(widget=fake))
    assert closed == ["dialogs"]
    workspace._poll_updates()
    assert not fake.callbacks


def test_workspace_busy_close_does_not_interrupt_memory_operation() -> None:
    fake = FakeTk()
    messages: list[str] = []
    workspace = object.__new__(DesktopWorkspace)
    workspace.root = cast(tk.Tk, fake)
    workspace._busy = True
    workspace._closed = False
    workspace._updates_after_id = fake.after(80, lambda: None)
    workspace.dialogs = cast(
        Any,
        SimpleNamespace(
            message=lambda _title, msg: messages.append(msg),
            close=lambda: pytest.fail("busy memory write must not shut down"),
        ),
    )

    workspace.close()
    assert not workspace._closed
    assert not fake.destroyed
    assert fake.callbacks
    assert "Zamykanie jest zablokowane" in messages[0]
