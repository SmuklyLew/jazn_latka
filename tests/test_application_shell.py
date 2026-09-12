from __future__ import annotations

from pathlib import Path

from latka_jazn.tools.application_shell import DiagnosticsHub, ShellSettings, TerminalSplash, normalize_ui_mode
from latka_jazn.tools.application_shell.settings import load_shell_settings, save_shell_settings


def test_normalize_ui_mode_uses_three_canonical_modes() -> None:
    assert normalize_ui_mode("text") == "text"
    assert normalize_ui_mode("tui") == "tui"
    assert normalize_ui_mode("window") == "window"
    assert normalize_ui_mode("studio") == "window"
    assert normalize_ui_mode(None, default="tui") == "tui"


def test_shell_settings_round_trip_and_normalization(tmp_path: Path) -> None:
    path = tmp_path / "ui.json"
    saved = save_shell_settings(
        path,
        ShellSettings(
            ui_mode="window",
            splash_enabled=False,
            diagnostics_enabled=True,
            diagnostics_limit=10,
            log_level="debug",
        ),
    )
    assert saved.diagnostics_limit == 50
    assert saved.log_level == "DEBUG"
    loaded = load_shell_settings(path)
    assert loaded == saved


def test_diagnostics_reconfigure_is_live_and_bounded(tmp_path: Path) -> None:
    hub = DiagnosticsHub("demo", tmp_path, enabled=False, limit=50, minimum_level="INFO")
    hub.record("DEBUG", "hidden")
    hub.record("INFO", "visible")
    assert [row["message"] for row in hub.snapshot()] == ["visible"]
    hub.reconfigure(enabled=True, minimum_level="DEBUG", limit=50)
    hub.record("DEBUG", "now-visible", key="value")
    assert hub.snapshot()[-1]["message"] == "now-visible"
    assert hub.log_path.is_file()
    assert "now-visible" in hub.log_path.read_text(encoding="utf-8")


def test_terminal_splash_context_is_safe_without_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    splash = TerminalSplash("Demo", enabled=True)
    with splash:
        splash.step("start")
        splash.done()
    assert splash.enabled is False
