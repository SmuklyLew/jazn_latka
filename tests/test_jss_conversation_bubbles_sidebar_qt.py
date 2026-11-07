"""Native chat bubbles and safe, metadata-only session sidebar.

All tests use a temporary operator root. No daemon, Ollama or MEMORY is started.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtTest import QTest

from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.chat_bubbles import ChatTranscript, visible_time
from tools.jazn_run_studio.chat_session_catalog import (
    load_sessions, remember_session,
)
from tools.jazn_run_studio.core import StudioError


def test_warsaw_header_converts_utc_without_renaming_history() -> None:
    assert visible_time(datetime(2026, 11, 6, 18, 26, tzinfo=timezone.utc)) == "06.11.2026, 19:26"
    assert visible_time("2026-07-06T18:26:00+00:00") == "06.07.2026, 20:26"
    assert visible_time(None) == "czas nieznany"
    assert visible_time("invalid") == "czas nieznany"
    assert visible_time(datetime(2026, 11, 6, 19, 26)) == "czas nieznany"


def test_native_bubbles_have_own_alignment_role_and_timestamp(window) -> None:
    transcript = window.conversation
    assert isinstance(transcript, ChatTranscript)
    assert transcript.isReadOnly()
    timestamp = datetime(2026, 11, 6, 18, 26, tzinfo=timezone.utc)
    transcript.append_message("user", "Cześć <tag>.", timestamp=timestamp,
                              timestamp_kind="wysłano")
    transcript.append_message("assistant", "Witaj!", timestamp=timestamp,
                              timestamp_kind="odebrano")
    assert len(transcript.bubbles) == 2
    user_row, assistant_row = transcript.bubbles
    assert user_row.objectName() == "jssUserBubbleRow"
    assert assistant_row.objectName() == "jssAssistantBubbleRow"
    user_layout, assistant_layout = user_row.layout(), assistant_row.layout()
    assert user_layout is not None and assistant_layout is not None
    user_first = user_layout.itemAt(0)
    assistant_last = assistant_layout.itemAt(1)
    assert user_first is not None and user_first.spacerItem() is not None
    assert assistant_last is not None and assistant_last.spacerItem() is not None
    user_header = user_row.findChild(QLabel, "jssBubbleHeader")
    assistant_header = assistant_row.findChild(QLabel, "jssBubbleHeader")
    assert user_header is not None and assistant_header is not None
    assert user_header.text() == "Ty  •  06.11.2026, 19:26"
    assert assistant_header.text() == "Łatka  •  06.11.2026, 19:26"
    user_content = user_row.findChild(QLabel, "jssBubbleContent")
    assert user_content is not None and user_content.text() == "Cześć <tag>."
    assert user_content.textFormat() == Qt.TextFormat.PlainText
    assert user_content.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert "Cześć <tag>." in transcript.toPlainText()
    assert "Witaj!" in transcript.toPlainText()


def test_chat_activity_group_replaces_module_links_with_sessions(window) -> None:
    window.workbench.activate_group("Czat")
    assert not window.chat_sidebar.isHidden()
    assert window.nav.isHidden()
    assert window.sidebar_heading.text() == "ROZMOWY"
    assert window.new_chat_button.text() == "＋ Nowa rozmowa"
    assert window.workbench.group_for_section("Modele AI") == "Ustawienia"
    assert window.workbench.group_for_section("Połączenie z ChatGPT") == "Usługi"
    window.workbench.activate_group("Ustawienia")
    assert not window.nav.isHidden()
    assert window.chat_sidebar.isHidden()


def test_new_session_is_real_and_cannot_discard_pending_request(window) -> None:
    window.new_local_conversation()
    chat = window.core.chat
    assert chat is not None
    current_id = chat.session_id
    assert current_id.startswith("studio-")
    catalog = load_sessions(window.core.root)
    assert catalog[0]["session_id"] == current_id
    assert catalog[0]["daemon_url"] == window.core.settings.daemon_url
    assert window.chat_session_list.count() == 1
    assert window.chat_session_list.item(0).data(Qt.ItemDataRole.UserRole) == current_id

    chat.pending = "studio-turn-unsettled"
    with pytest.raises(StudioError, match="rozstrzygnij"):
        window.new_local_conversation()
    assert chat.pending == "studio-turn-unsettled"
    assert chat.session_id == current_id
    assert len(load_sessions(window.core.root)) == 1


def test_session_index_rejects_cross_daemon_reassociation(tmp_path: Path) -> None:
    first = "studio-example"
    remember_session(tmp_path, first, "http://127.0.0.1:8787")
    assert load_sessions(tmp_path)[0]["session_id"] == first
    with pytest.raises(StudioError, match="innego endpointu"):
        remember_session(tmp_path, first, "http://127.0.0.1:8794")
    assert load_sessions(tmp_path)[0]["daemon_url"] == "http://127.0.0.1:8787"


def test_historical_accepted_turn_does_not_forge_original_send_time(window) -> None:
    sid = "studio-historical-test"
    window._selected_chat_session_id = sid
    window._chat_history_generation = 7
    projection = {
        "session_id": sid, "turns": [{
            "user_text": "Historyczna wiadomość",
            "assistant_text": "Potwierdzona odpowiedź.",
            "accepted_at_utc": "2026-11-06T18:09:41+00:00",
        }],
    }
    window._present_chat_history(sid, 7, projection)
    assert len(window.conversation.bubbles) == 2
    user_header = window.conversation.bubbles[0].findChild(QLabel, "jssBubbleHeader")
    assistant_header = window.conversation.bubbles[1].findChild(QLabel, "jssBubbleHeader")
    assert user_header is not None and "czas nieznany" in user_header.text()
    assert assistant_header is not None and "06.11.2026, 19:09" in assistant_header.text()
    assert "Potwierdzona odpowiedź." in window.conversation.toPlainText()
    window._present_chat_history("studio-other", 7, {"session_id": "studio-other", "turns": []})
    assert len(window.conversation.bubbles) == 2


def test_sidebar_conversation_index_has_no_user_message_content(tmp_path: Path) -> None:
    remember_session(tmp_path, "studio-private", "http://127.0.0.1:8787")
    from tools.jazn_run_studio.chat_session_catalog import catalog_path
    raw = catalog_path(tmp_path).read_text(encoding="utf-8")
    assert "user_text" not in raw
    assert "assistant_text" not in raw
    assert "studio-private" in raw
