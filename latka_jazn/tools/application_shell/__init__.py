"""Shared lifecycle, settings and diagnostics primitives for interactive Jaźń tools."""
from .diagnostics import DiagnosticsHub
from .command_studio import CommandItem, CommandStudioSpec, build_diagnostics, load_command_studio_settings, run_text_studio, run_tui_studio, run_window_studio
from .lifecycle import normalize_ui_mode, run_guarded
from .settings import ShellSettings, load_shell_settings, save_shell_settings
from .splash import TerminalSplash

__all__ = [
    "DiagnosticsHub",
    "CommandItem",
    "CommandStudioSpec",
    "build_diagnostics",
    "load_command_studio_settings",
    "run_text_studio",
    "run_tui_studio",
    "run_window_studio",
    "ShellSettings",
    "TerminalSplash",
    "load_shell_settings",
    "normalize_ui_mode",
    "run_guarded",
    "save_shell_settings",
]
