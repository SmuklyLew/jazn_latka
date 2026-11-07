"""Nonblocking first-run provisioning controls are explicit and never auto-install."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox
from tests.test_jazn_run_studio_layout import window  # noqa: F401
from tools.jazn_run_studio.first_run import SetupWizard


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
