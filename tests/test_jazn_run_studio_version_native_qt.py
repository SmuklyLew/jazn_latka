"""Version Studio native read-only inspections must never imply writes."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.version_view import VersionPanel


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    instance = QApplication.instance() or QApplication([])
    assert isinstance(instance, QApplication)
    yield instance
    instance.processEvents()


def test_readonly_version_panel_dispatches_canonical_worker_without_writes(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text("# fixture", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    controller = Controller(tmp_path, Settings())
    calls: list[str] = []
    monkeypatch.setattr(controller, "studio_helper", lambda mode: calls.append(mode))
    panel = VersionPanel(controller)
    panel.inspect()
    assert calls == ["version-inspect"]
    panel.receive({"schema": "jazn_version_readonly_inspection/v1",
                   "package": "16.3.25.5.116.0.34.88", "name": "native-configuration-qt-parity",
                   "full": "16.3.25.5.116.0.34.88-native-configuration-qt-parity",
                   "read_only": True})
    assert "16.3.25.5.116.0.34.88" in panel.output.toPlainText()
    assert panel.inspect_button.isEnabled()
    assert not (tmp_path / "workspace_runtime").exists()
    panel.close()
    panel.deleteLater()
    qapp.processEvents()
