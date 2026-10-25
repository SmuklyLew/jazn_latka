"""Native Configuration Qt ROOT migration: fail-closed CAS and user consent."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox

from latka_jazn.core import system_config
from latka_jazn.tools import configuration_studio
from tools.jazn_run_studio import studio_worker
from tools.jazn_run_studio.configuration_view import ConfigurationPanel
from tools.jazn_run_studio.core import Controller, Settings


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    obj = QApplication.instance() or QApplication([])
    assert isinstance(obj, QApplication)
    yield obj
    obj.processEvents()


def test_worker_migration_guards_source_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[Path, str | None]] = []
    monkeypatch.setattr(configuration_studio, "profile_snapshot",
                        lambda _root: ({"JAZN_MEMORY_MODE": "optional"}, "a" * 64))
    monkeypatch.setattr(system_config, "migrate_operator_profile",
                        lambda root, *, expected_sha256=None:
                        calls.append((root, expected_sha256)))
    monkeypatch.setattr(system_config, "config_path",
                        lambda root: Path(root) / "system_config.json")
    with pytest.raises(ValueError, match="zmieniono"):
        studio_worker.profile("profile-migrate", {"digest": "b" * 64})
    assert not calls
    result = studio_worker.profile("profile-migrate", {"digest": "a" * 64})
    assert calls == [(tmp_path, "a" * 64)]
    assert result["schema"] == "jazn_config_root_migration/v1"
    assert result["saved"] is True
    assert result["runtime_activated"] is False
    assert result["profile_sha256"] == "a" * 64


@pytest.fixture
def panel(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ConfigurationPanel]:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    controller = Controller(tmp_path, Settings())
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(controller, "studio_helper",
                        lambda mode, **kwargs: calls.append((mode, kwargs)))
    item = ConfigurationPanel(controller)
    setattr(item, "test_calls", calls)
    item.reload()
    item.receive("helper:profile-read:", {
        "schema": "jazn_config_snapshot/v1",
        "values": {"JAZN_MEMORY_MODE": "optional"}, "digest": "a" * 64,
        "profile_path": str(tmp_path / "operator.json"),
        "fields": [{"key": "JAZN_MEMORY_MODE", "title": "Tryb pamięci",
                    "kind": "memory_mode", "choices": ["off", "optional", "required"]}],
    })
    yield item
    item.close()
    item.deleteLater()
    qapp.processEvents()


def test_gui_migration_requires_explicit_consent(
    panel: ConfigurationPanel, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = getattr(panel, "test_calls")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_args, **_kwargs: QMessageBox.StandardButton.No)
    panel.migrate()
    assert [x[0] for x in calls] == ["profile-read"]

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    panel.migrate()
    assert calls[-1] == ("profile-migrate", {"data": {"digest": "a" * 64}})
    panel.receive("helper:profile-migrate:", {
        "schema": "jazn_config_root_migration/v1",
        "saved": True, "runtime_activated": False,
        "profile_sha256": "a" * 64,
        "config_path": str(panel.core.root / "system_config.json"),
    })
    assert "Runtime niezmieniony" in panel.status.text()


def test_unsaved_gui_draft_blocks_root_migration(
    panel: ConfigurationPanel, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = getattr(panel, "test_calls")
    choice = panel.widgets["JAZN_MEMORY_MODE"]
    assert isinstance(choice, QComboBox)
    choice.setCurrentText("off")
    assert panel.dirty
    before = len(calls)
    panel.migrate()
    assert len(calls) == before
    assert not panel.migrate_button.isEnabled()
