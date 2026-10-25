"""Native configuration Qt covers canonical CAS and unsaved-draft behavior."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QComboBox

from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.configuration_view import (
    ConfigurationPanel, launch_command, profile_fingerprint,
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    instance = QApplication.instance() or QApplication([])
    assert isinstance(instance, QApplication)
    yield instance
    instance.processEvents()


@pytest.fixture
def panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> Iterator[ConfigurationPanel]:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn" / "version.py").write_text("# fixture", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    backend = Controller(tmp_path, Settings(model="local-test"))
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(backend, "studio_helper", lambda mode, **kw: requests.append((mode, kw)))
    widget = ConfigurationPanel(backend)
    yield widget
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def mode_choice(panel: ConfigurationPanel) -> QComboBox:
    item = panel.widgets["JAZN_MEMORY_MODE"]
    assert isinstance(item, QComboBox)
    return item


def sample_snapshot() -> dict:
    return {
        "schema": "jazn_config_snapshot/v1",
        "values": {"JAZN_MEMORY_MODE": "optional"},
        "digest": "a" * 64,
        "profile_path": "/tmp/profile.json",
        "fields": [
            {"key": "JAZN_MEMORY_MODE", "title": "MEMORY",
             "choices": ["optional", "required", "off"], "kind": "memory_mode"},
        ],
    }


def test_profile_draft_does_not_save_before_preview(panel: ConfigurationPanel) -> None:
    panel.reload()
    assert panel.busy == "profile-read"
    assert not panel.save_button.isEnabled()
    panel.receive("helper:profile-read:", sample_snapshot())
    assert panel.loaded_once and not panel.dirty
    mode_choice(panel).setCurrentText("off")
    assert panel.dirty
    assert not panel.save_button.isEnabled()
    panel.preview()
    assert panel.busy == "profile-preview"
    preview = {"schema": "jazn_config_profile_preview/v1", "read_only": True,
               "profile_sha256": "a" * 64, "changes_count": 1,
               "changed_keys": ["JAZN_MEMORY_MODE"],
               "rows": [{"changed": True, "key": "JAZN_MEMORY_MODE",
                         "title": "MEMORY", "saved": "optional", "proposed": "off"}]}
    panel.receive("helper:profile-preview:", preview)
    assert panel.save_button.isEnabled()
    mode_choice(panel).setCurrentText("required")
    assert not panel.save_button.isEnabled()
    assert panel.preview_hash == ""


def test_stale_async_preview_cannot_approve_new_draft(panel: ConfigurationPanel) -> None:
    panel.reload()
    panel.receive("helper:profile-read:", sample_snapshot())
    mode_choice(panel).setCurrentText("off")
    panel.preview()
    mode_choice(panel).setCurrentText("required")
    panel.receive("helper:profile-preview:", {
        "schema": "jazn_config_profile_preview/v1", "read_only": True,
        "profile_sha256": "a" * 64, "changes_count": 1,
        "changed_keys": ["JAZN_MEMORY_MODE"], "rows": [],
    })
    assert panel.preview_hash == ""
    assert not panel.save_button.isEnabled()


def test_failed_write_never_marks_draft_saved(panel: ConfigurationPanel) -> None:
    panel.reload()
    panel.receive("helper:profile-read:", sample_snapshot())
    mode_choice(panel).setCurrentText("off")
    panel.preview()
    panel.receive("helper:profile-preview:", {
        "schema": "jazn_config_profile_preview/v1", "read_only": True,
        "profile_sha256": "a" * 64, "changes_count": 1,
        "changed_keys": ["JAZN_MEMORY_MODE"], "rows": [],
    })
    assert panel.dirty
    panel._run("profile-save", {"values": panel.values(), "digest": panel.digest})
    panel.receive_state("helper:profile-save:", {"state": "failed", "error": "CAS conflict"})
    assert panel.dirty and panel.digest == "a" * 64
    assert not panel.save_button.isEnabled()


def test_copy_command_requires_absolute_verified_profile_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="zweryfikowanej"):
        launch_command(tmp_path, "../profile.json")
    text = launch_command(tmp_path, str(tmp_path / "operator.json"))
    assert "Start-JaznWithConfig.ps1" in text
    assert str(tmp_path / "operator.json") in text
    assert profile_fingerprint({"a": "b"}, None) != profile_fingerprint({"a": "c"}, None)
