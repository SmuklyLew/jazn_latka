"""Nonblocking first-run provisioning controls are explicit and never auto-install."""
from __future__ import annotations

from pathlib import Path
import json
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox
from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.window import Window
from tools.jazn_run_studio.first_run import SetupWizard


@pytest.fixture
def window(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "run.py").touch()
    (tmp_path / "main.py").touch()
    core = Controller(tmp_path, Settings(theme="dark"))
    result = Window(core, smoke=True)
    result.show()
    yield result
    result.close()
    app.processEvents()


def test_wizard_offers_root_local_setup_and_gemma3_default(window) -> None:
    wizard = SetupWizard(window.core, lambda _settings: None, lambda _scope: None, window)
    wizard.timer.stop()
    assert wizard.models_to_download.text() == "gemma3:latest"
    assert wizard.provision_result is not None
    assert wizard.provision_process is None


def test_inspect_does_not_request_mutation_approval(window, monkeypatch) -> None:
    wizard = SetupWizard(window.core, lambda _settings: None, lambda _scope: None, window)
    wizard.timer.stop()
    commands: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(wizard, "_start_provision_process",
                        lambda key, args: commands.append((key, args)))
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: pytest.fail("read-only inspection must not request approval"),
    )
    wizard.provision("inspect")
    assert commands == [("inspect", [])]
    from tools.jazn_run_studio.first_run import _provision_result_ok

    report = {
        "schema_version": "jazn_jss_prerequisites/v1",
        "ready": False, "python_314_ready": False,
        "ollama_api_ready": False, "models": [],
    }
    assert _provision_result_ok("inspect", report, exit_code=0, native_winget=False)
    assert not _provision_result_ok("inspect", report, exit_code=1, native_winget=False)
    assert not _provision_result_ok("prepare-venv", report, exit_code=0, native_winget=False)
    assert not _provision_result_ok(
        "inspect", {"schema_version": "unknown"}, exit_code=0, native_winget=False
    )
    wizard.provision_command = "inspect"
    wizard.provision_native = False
    wizard.provision_buffer = json.dumps(report)
    wizard._provision_finished(0, None)
    assert "Sprawdzono ROOT/.venv/Ollama" in wizard.provision_result.text()
    assert "wymaga przygotowania" in wizard.provision_result.text()
    with window.core.lock:
        events = list(window.core.events.queue)
    assert any(
        key == "setup:provision" and kind == "state"
        and value.get("state") == "succeeded"
        for key, kind, value in events
    )


def test_venv_provision_requires_explicit_confirmation(window, monkeypatch) -> None:
    wizard = SetupWizard(window.core, lambda _settings: None, lambda _scope: None, window)
    wizard.timer.stop()
    commands: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(wizard, "_setup_python", lambda: "C:/Python314/python.exe")
    monkeypatch.setattr(wizard, "_start_provision_process",
                        lambda key, args: commands.append((key, args)))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.No)
    wizard.provision("prepare-venv")
    assert commands == []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    wizard.provision("prepare-venv")
    assert commands == [("prepare-venv", [])]


def test_multi_model_queue_is_validated_before_any_download(window, monkeypatch) -> None:
    wizard = SetupWizard(window.core, lambda _settings: None, lambda _scope: None, window)
    wizard.timer.stop()
    commands: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(wizard, "_start_provision_process",
                        lambda key, args: commands.append((key, args)))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    wizard.models_to_download.setText("gemma3:latest, gemma3:1b")
    wizard.provision("pull-model")
    assert commands == [("pull-model", ["--model", "gemma3:latest"])]
    assert wizard.provision_remaining_models == ["gemma3:1b"]
    wizard.models_to_download.setText("gemma3:latest, ../bad")
    wizard.provision_remaining_models.clear()
    wizard.provision("pull-model")
    assert len(commands) == 1
