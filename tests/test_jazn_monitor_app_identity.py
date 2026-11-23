"""Dev-mode monitor app labels; tests never start the daemon or write MEMORY."""
from __future__ import annotations

import pytest

from tools.jazn_monitor import app_identity


class FakeQtApp:
    def __init__(self) -> None:
        self.name = None
        self.display_name = None

    def setApplicationName(self, name: str) -> None:
        self.name = name

    def setApplicationDisplayName(self, name: str) -> None:
        self.display_name = name


def test_linux_sets_qt_identity_without_calling_windows_shell() -> None:
    app = FakeQtApp()

    def forbidden(_value: str) -> int:
        pytest.fail("Windows AppUserModelID must not be called on Linux")

    result = app_identity.configure_monitor_app_identity(
        app, platform="posix", windows_app_id_setter=forbidden,
    )
    assert app.name == "JaznMonitor"
    assert app.display_name == "Jaźń Monitor"
    assert result["windows_app_id_status"] == "not_applicable"
    assert result["windows_app_id"] is None


def test_windows_sets_taskbar_app_id_without_changing_python_image_name() -> None:
    app = FakeQtApp()
    calls: list[str] = []
    result = app_identity.configure_monitor_app_identity(
        app,
        platform="nt",
        windows_app_id_setter=lambda app_id: calls.append(app_id) or 0,
    )

    assert calls == ["Jazn.Monitor.Dev"]
    assert result["windows_app_id_status"] == "applied"
    assert app.name == "JaznMonitor"
    assert app.display_name == "Jaźń Monitor"
    # No executable rename, service install, daemon signal or runtime startup.


def test_windows_shell_rejection_remains_truthful_and_nonfatal() -> None:
    app = FakeQtApp()
    result = app_identity.configure_monitor_app_identity(
        app, platform="nt", windows_app_id_setter=lambda _id: -2147467259,
    )
    assert result["windows_app_id_status"] == "rejected"
    assert result["windows_app_id"] is None
    assert result["hresult"] == -2147467259
    assert app.display_name == "Jaźń Monitor"


@pytest.mark.parametrize("error", [AttributeError("shell32"), OSError("unavailable")])
def test_windows_shell_unavailable_keeps_qt_monitor(error: Exception) -> None:
    app = FakeQtApp()

    def unavailable(_app_id: str) -> int:
        raise error

    result = app_identity.configure_monitor_app_identity(
        app, platform="nt", windows_app_id_setter=unavailable,
    )
    assert result["windows_app_id_status"] == type(error).__name__
    assert result["windows_app_id"] is None
    assert app.display_name == "Jaźń Monitor"
