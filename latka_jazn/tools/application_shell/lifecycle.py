from __future__ import annotations

import sys
from typing import Callable

from .diagnostics import DiagnosticsHub


def normalize_ui_mode(value: str | None, *, default: str = "window") -> str:
    mode = str(value or default).strip().lower()
    if mode in {"studio", "gui", "windows", "win"}:
        mode = "window"
    if mode not in {"text", "tui", "window"}:
        raise ValueError(f"Nieobsługiwany tryb interfejsu: {value!r}")
    return mode


def run_guarded(action: Callable[[], int | None], diagnostics: DiagnosticsHub, *, app_name: str) -> int:
    try:
        result = action()
        return int(result or 0)
    except KeyboardInterrupt:
        diagnostics.record("WARNING", "Przerwano przez Ctrl+C", exit_code=130)
        print(f"{app_name}: przerwano przez Ctrl+C.", file=sys.stderr)
        return 130
    except Exception as exc:
        diagnostics.exception(exc, context=f"Nieobsłużony błąd aplikacji {app_name}")
        print(f"{app_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Szczegóły diagnostyczne: {diagnostics.log_path}", file=sys.stderr)
        return 1
