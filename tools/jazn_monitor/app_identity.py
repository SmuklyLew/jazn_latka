"""Read-only Qt application identity for the *development* Monitor.

This changes Qt/taskbar grouping metadata, not the Windows image name: a
script launched via pythonw.exe remains pythonw.exe in Task Manager.
No daemon/process lifecycle, registry writes, or dependency installation.
"""
from __future__ import annotations

import os
from typing import Any, Callable

QT_APPLICATION_NAME = "JaznMonitor"
QT_APPLICATION_DISPLAY_NAME = "Jaźń Monitor"
WINDOWS_APP_USER_MODEL_ID = "Jazn.Monitor.Dev"


def _set_windows_app_user_model_id(app_id: str) -> int:
    """Call the documented process-scoped Windows shell API."""
    import ctypes

    # windll is Windows-only; dynamic access keeps Linux type checking valid.
    method = getattr(ctypes, "windll").shell32.SetCurrentProcessExplicitAppUserModelID
    method.argtypes = [ctypes.c_wchar_p]
    method.restype = ctypes.c_long  # HRESULT (32-bit LONG on Windows)
    return int(method(app_id))


def configure_monitor_app_identity(
    app: Any,
    *,
    platform: str | None = None,
    windows_app_id_setter: Callable[[str], int] | None = None,
) -> dict[str, str | int | None]:
    """Set display identity before showing Qt windows; never change daemon state.

    The Windows AppUserModelID groups taskbar windows, *not* executable names.
    On Ubuntu no Windows shell API is loaded or invoked.
    """
    app.setApplicationName(QT_APPLICATION_NAME)
    app.setApplicationDisplayName(QT_APPLICATION_DISPLAY_NAME)

    if (os.name if platform is None else platform) != "nt":
        return {"qt_name": QT_APPLICATION_NAME, "display_name": QT_APPLICATION_DISPLAY_NAME,
                "windows_app_id_status": "not_applicable", "windows_app_id": None}

    setter = windows_app_id_setter or _set_windows_app_user_model_id
    try:
        hresult = setter(WINDOWS_APP_USER_MODEL_ID)
    except (AttributeError, OSError) as exc:
        # A shell integration failure must not prevent the read-only observer.
        return {"qt_name": QT_APPLICATION_NAME, "display_name": QT_APPLICATION_DISPLAY_NAME,
                "windows_app_id_status": type(exc).__name__, "windows_app_id": None}
    if hresult != 0:
        return {"qt_name": QT_APPLICATION_NAME, "display_name": QT_APPLICATION_DISPLAY_NAME,
                "windows_app_id_status": "rejected", "windows_app_id": None,
                "hresult": hresult}
    return {"qt_name": QT_APPLICATION_NAME, "display_name": QT_APPLICATION_DISPLAY_NAME,
            "windows_app_id_status": "applied", "windows_app_id": WINDOWS_APP_USER_MODEL_ID}
