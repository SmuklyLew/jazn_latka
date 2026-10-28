"""First-run settings and three-step chat unlock remain evidence-based."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.core import Settings, StudioError
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.requirements_worker import setup_scope
from tools.jazn_run_studio.core import python_executable


def test_first_run_has_all_studio_settings_and_saves_validated_draft(window) -> None:
    saved: list[Settings] = []
    finished: list[str] = []
    wizard = SetupWizard(window.core, saved.append, finished.append, window)
    wizard.timer.stop()
    assert set(wizard.setting_fields) | {"theme", "runtime_profile"} == set(asdict(Settings()))
    assert wizard.model is wizard.setting_fields["model"]
    wizard.report = {
        "required_ok": True,
        "scope": setup_scope(window.core.root, python_executable(window.core.settings)),
    }
    wizard.setting_fields["model"].setText("gemma3:latest")
    wizard.setting_fields["daemon_url"].setText("http://127.0.0.1:8787")
    wizard.setting_fields["mcp_port"].setText("18086")
    wizard.theme_choice.setCurrentText("light")
    wizard.runtime_profile_choice.setCurrentIndex(1)
    wizard.consent.setChecked(True)
    wizard.accept()
    assert len(saved) == 1
    assert saved[0].model == "gemma3:latest"
    assert saved[0].mcp_port == "18086"
    assert saved[0].theme == "light"
    assert saved[0].runtime_profile == "operator"
    assert len(finished) == 1


def test_chat_step_requires_trusted_runtime_and_explicit_generation(window) -> None:
    window.core.settings = replace(window.core.settings, model="gemma3:latest")
    assert window.quick_chat_button.isEnabled() is False
    window.core.emit("status", "evidence", {
        "endpoint_reachable": True,
        "process_identity_confirmed": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "conversation_ready": True,
        "active_state": "active_degraded",
    })
    window.poll()
    assert window.quick_chat_button.isEnabled() is False
    window.core.emit("status", "evidence", {
        "endpoint_reachable": True,
        "process_identity_confirmed": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "conversation_ready": True,
        "active_state": "active_trusted",
    })
    window.poll()
    assert window.quick_chat_button.isEnabled() is False
    window.core.emit("probe:ollama_generate", "probe", {
        "service": "ollama", "endpoint_reachable": True, "models": ["gemma3:latest"],
        "selected_model_present": True, "generation_verified": True,
        "accepted_visible_turn": False,
    })
    window.poll()
    assert window.quick_chat_button.isEnabled() is True
    window.core.emit("status", "evidence", {})
    window.poll()
    assert window.quick_chat_button.isEnabled() is False


def test_memory_continuity_label_does_not_unlock_chat(window) -> None:
    window.core.emit("status", "status_summary", {
        "memory": "dostępna technicznie",
        "continuity": "ciągłość niepotwierdzona • normalization_stale",
    })
    window.poll()
    assert "normalization_stale" in window.quick_memory_status.text()
    assert window.quick_chat_button.isEnabled() is False


def test_sidebar_chat_connect_cannot_bypass_guided_readiness(window, monkeypatch) -> None:
    with pytest.raises(StudioError, match="test generacji"):
        window.connect_local_chat()
    window.core.settings = replace(window.core.settings, model="gemma3:latest")
    window.quick_runtime_ready = True
    window.quick_generation_ready = True
    calls: list[bool] = []
    monkeypatch.setattr(window.core, "connect_chat", lambda: calls.append(True))
    window.connect_local_chat()
    assert calls == [True]
    window.core.emit("service:ollama", "state", {
        "key": "service:ollama", "state": "stopped", "error": None, "pid": None,
    })
    window.poll()
    assert window.quick_generation_ready is False
    with pytest.raises(StudioError):
        window.connect_local_chat()
