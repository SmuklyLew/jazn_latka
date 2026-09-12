from __future__ import annotations

from io import StringIO
import pytest

from latka_jazn.tools.chat_export_ui import CursorMenu, ScriptedKeySource, TerminalKeySource, explicit_confirmation


def test_cursor_menu_navigation_and_multi_selection() -> None:
    output = StringIO()
    selected = CursorMenu("Tematy", ["a", "b", "c"], multi=True).choose(
        key_source=ScriptedKeySource(["down", "space", "down", "space", "enter"]),
        output=output,
    )
    assert selected == {1, 2}


def test_cursor_menu_typed_single_and_multi_entrypoints() -> None:
    output = StringIO()
    selected_one = CursorMenu("Menu", ["a", "b"]).choose_one(
        key_source=ScriptedKeySource(["down", "enter"]),
        output=output,
    )
    selected_many = CursorMenu("Menu", ["a", "b"], multi=True).choose_many(
        key_source=ScriptedKeySource(["space", "enter"]),
        output=output,
    )

    assert selected_one == 1
    assert selected_many == {0}


def test_cursor_menu_escape_and_ctrl_x() -> None:
    output = StringIO()
    assert CursorMenu("Menu", ["a"]).choose(
        key_source=ScriptedKeySource(["escape"]), output=output,
    ) is None
    try:
        CursorMenu("Menu", ["a"]).choose(
            key_source=ScriptedKeySource(["ctrl_x"]), output=output,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("Ctrl+X must stop the UI")


def test_write_confirmation_requires_exact_nonempty_token() -> None:
    assert explicit_confirmation(lambda _: "", "", token="IMPORTUJ") is False
    assert explicit_confirmation(lambda _: "tak", "", token="IMPORTUJ") is False
    assert explicit_confirmation(lambda _: "IMPORTUJ", "", token="IMPORTUJ") is True


def test_terminal_key_source_uses_concrete_posix_file_descriptor(monkeypatch) -> None:
    termios = pytest.importorskip("termios")
    tty = pytest.importorskip("tty")

    calls: list[tuple[str, int]] = []

    class FakeInput(StringIO):
        def fileno(self) -> int:
            return 17

    monkeypatch.setattr(termios, "tcgetattr", lambda fd: calls.append(("tcgetattr", fd)) or [1, 2, 3])
    monkeypatch.setattr(tty, "setraw", lambda fd: calls.append(("setraw", fd)))
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, _when, _state: calls.append(("tcsetattr", fd)))

    with TerminalKeySource(FakeInput()):
        pass

    assert calls == [("tcgetattr", 17), ("setraw", 17), ("tcsetattr", 17)]
