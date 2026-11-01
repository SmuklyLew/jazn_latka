"""Focused chat layout keeps trusted runtime boundaries and accessible controls."""
from __future__ import annotations
import pytest
pytest.importorskip("PySide6")
from tests.test_jazn_run_studio_layout import window


def test_local_chat_transcript_and_composer_are_primary_surfaces(window) -> None:
    window.navigate("Czat lokalny")
    assert window.conversation.isReadOnly()
    assert window.message.isReadOnly() is False
    assert window.conversation.objectName() == "workbenchChatTranscript"
    assert window.message.objectName() == "workbenchChatComposer"
    assert window.send_button.objectName() == "jssPrimaryAction"
    assert window.chat_controls.isHidden()
    window.chat_controls_toggle.setChecked(True)
    assert not window.chat_controls.isHidden()
    assert window.chat_model_selector.count() >= 1
    window.chat_controls_toggle.setChecked(False)
    assert window.chat_controls.isHidden()
    assert window.core.chat is None  # Appearance alone cannot connect or send.
