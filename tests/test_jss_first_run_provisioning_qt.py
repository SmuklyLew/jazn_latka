"""First-run JSS offers only official Ollama download and explicit model pull.

The original v127.23.1 installer tests are preserved in tests/archive.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from tools.jazn_run_studio import first_run
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
    widget = Window(core, smoke=True)
    widget.show()
    yield widget
    widget.close()
    app.processEvents()


def _wizard(window) -> SetupWizard:
    wizard = SetupWizard(window.core, lambda _settings: None, lambda _scope: None, window)
    wizard.timer.stop()
    return wizard


def test_wizard_has_no_python_package_or_duplicate_ollama_server_installers(window) -> None:
    wizard = _wizard(window)
    labels = {button.text() for button in wizard.findChildren(QPushButton)}
    assert wizard.table.columnCount() == 4
    assert wizard.models_to_download.text() == "gemma3:latest"
    assert wizard.provision_process is None
    assert wizard.ollama_official.text() == "Pobierz Ollamę — oficjalna strona"
    assert "Pobierz wybrane modele Ollama" in labels
    assert not any(
        label in labels for label in (
            "Zainstaluj Python 3.14 (WinGet)",
            "Utwórz lub sprawdź ROOT/.venv",
            "Pobierz biblioteki terminala + JSS (online)",
            "Zainstaluj zweryfikowane biblioteki (offline)",
            "Zainstaluj Ollamę (WinGet)",
            "Uruchom Ollamę jako usługę CLI",
            "Uruchom aplikację Ollama",
        )
    )
    wizard.close()


def test_official_vendor_link_never_executes_installer(window, monkeypatch) -> None:
    wizard = _wizard(window)
    opened = []
    monkeypatch.setattr(
        first_run, "QDesktopServices",
        SimpleNamespace(openUrl=lambda url: opened.append(url.toString()) or True),
    )
    monkeypatch.setattr(first_run.sys, "platform", "win32")
    wizard.open_official_ollama_download()
    assert opened == ["https://ollama.com/download/windows"]
    assert wizard.provision_process is None
    wizard.close()


def test_legacy_provisioning_paths_refuse_before_consent_or_process(window, monkeypatch) -> None:
    wizard = _wizard(window)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_args, **_kw: pytest.fail("Legacy installer must not request consent"),
    )
    monkeypatch.setattr(
        wizard, "_start_provision_process",
        lambda *_args: pytest.fail("Legacy installer must not start"),
    )
    for legacy in (
        "inspect", "install-python", "prepare-venv", "download-deps",
        "install-offline", "install-ollama", "start-ollama", "start-ollama-app",
    ):
        wizard.provision(legacy)
    assert "Studio Zależności" in wizard.provision_result.text()
    assert wizard.provision_process is None
    with pytest.raises(ValueError, match="nie należą do kreatora"):
        # Legacy bypass cannot spawn via the private process wrapper either.
        first_run.SetupWizard._start_provision_process(wizard, "start-ollama", [])
    wizard.close()


def test_model_pull_queue_validated_and_requires_explicit_approval(window, monkeypatch) -> None:
    wizard = _wizard(window)
    commands = []
    monkeypatch.setattr(wizard, "_start_provision_process",
                        lambda key, args: commands.append((key, args)))
    wizard.models_to_download.setText("gemma3:latest, gemma3:1b")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_args, **_kw: QMessageBox.StandardButton.No)
    wizard.provision("pull-model")
    assert commands == []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_args, **_kw: QMessageBox.StandardButton.Yes)
    wizard.provision("pull-model")
    assert commands == [("pull-model", ["--model", "gemma3:latest"])]
    assert wizard.provision_remaining_models == ["gemma3:1b"]
    wizard.models_to_download.setText("gemma3:latest, ../bad")
    wizard.provision_remaining_models.clear()
    wizard.provision("pull-model")
    assert len(commands) == 1
    wizard.close()
