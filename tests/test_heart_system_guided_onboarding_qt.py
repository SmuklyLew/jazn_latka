"""First-run settings and three-step chat unlock remain evidence-based."""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import sys

import pytest

pytest.importorskip("PySide6")

from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.core import Settings, StudioError
from tools.jazn_run_studio.first_run import SetupWizard
from tools.jazn_run_studio.requirements_worker import setup_scope


def test_first_run_has_all_studio_settings_and_saves_validated_draft(window, monkeypatch) -> None:
    # Synthetic fixture roots do not carry a .venv. Mock only the verified
    # interpreter for this positive form-save case; private_python_status
    # ownership checks have independent real-filesystem regression coverage.
    from latka_jazn.dependencies import private_python
    expected_python = Path(sys.executable).resolve()
    monkeypatch.setattr(private_python, "private_python_status", lambda _root: {"ready": True})
    monkeypatch.setattr(private_python, "private_python_path", lambda _root: expected_python)
    saved: list[Settings] = []
    finished: list[str] = []
    wizard = SetupWizard(window.core, saved.append, finished.append, window)
    wizard.timer.stop()
    assert set(wizard.setting_fields) | {"theme", "runtime_profile"} == set(asdict(Settings()))
    assert wizard.model is wizard.setting_fields["model"]
    wizard.report = {
        "required_ok": True,
        "scope": setup_scope(window.core.root, str(expected_python)),
    }
    wizard.setting_fields["python"].setText(str(expected_python))
    wizard.setting_fields["mcp_python"].setText(str(expected_python))
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


def test_first_run_missing_private_python_is_nonblocking_and_denied(window) -> None:
    saved: list[Settings] = []
    finished: list[str] = []
    wizard = SetupWizard(window.core, saved.append, finished.append, window)
    wizard.timer.stop()
    wizard.report = {"required_ok": True, "scope": "synthetic"}
    wizard.consent.setChecked(True)
    wizard.accept()
    assert not saved
    assert not finished
    assert not wizard.finished_setup
    assert "ROOT/.venv" in wizard.notice.text()


def test_chat_step_requires_trusted_runtime_and_explicit_generation(window) -> None:
    window.core.settings = replace(window.core.settings, model="gemma3:latest")
    assert not (window.quick_runtime_ready and window.quick_generation_ready)
    window.core.emit("status", "evidence", {
        "endpoint_reachable": True,
        "process_identity_confirmed": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "conversation_ready": True,
        "active_state": "active_degraded",
        "root_matches": True, "version_matches": True,
    })
    window.poll()
    assert not (window.quick_runtime_ready and window.quick_generation_ready)
    window.core.emit("status", "evidence", {
        "endpoint_reachable": True,
        "process_identity_confirmed": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "conversation_ready": True,
        "active_state": "active_trusted",
        "root_matches": True, "version_matches": True,
    })
    window.poll()
    assert not (window.quick_runtime_ready and window.quick_generation_ready)
    window.core.emit("probe:ollama_generate", "probe", {
        "service": "ollama", "endpoint_reachable": True, "models": ["gemma3:latest"],
        "selected_model_present": True, "generation_verified": True,
        "accepted_visible_turn": False,
    })
    window.poll()
    assert window.quick_runtime_ready and window.quick_generation_ready
    assert "możesz połączyć" in window.quick_start_status.text()
    window.core.emit("status", "evidence", {})
    window.poll()
    assert not (window.quick_runtime_ready and window.quick_generation_ready)


def test_memory_continuity_label_does_not_unlock_chat(window) -> None:
    window.core.emit("status", "status_summary", {
        "memory": "dostępna technicznie",
        "continuity": "ciągłość niepotwierdzona • normalization_stale",
    })
    window.poll()
    assert "normalization_stale" in window.quick_memory_status.text()
    assert not (window.quick_runtime_ready and window.quick_generation_ready)


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
