from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .project_store import ProjectStore
from .unified_memory import CANONICAL_DATABASE_NAME

input_dialog = message_dialog = radiolist_dialog = None
try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import input_dialog, message_dialog, radiolist_dialog
    HAS_PROMPT_TOOLKIT = True
except Exception:  # pragma: no cover
    HAS_PROMPT_TOOLKIT = False


def run_dialog(dialog: Any) -> Any:
    return dialog.run()


def message(title: str, text: str) -> None:
    if HAS_PROMPT_TOOLKIT and message_dialog is not None:
        run_dialog(message_dialog(title=title, text=text))
    else:
        print(f"\n=== {title} ===\n{text}\n")


def ask_text(title: str, label: str, default: str = "") -> str | None:
    if HAS_PROMPT_TOOLKIT and input_dialog is not None:
        value = run_dialog(input_dialog(title=title, text=label, default=default))
        return str(value) if value is not None else None
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def database_from_project(project_root: str | Path | None, project: str | None) -> Path | None:
    if not project:
        env = os.getenv("JAZN_MEMORY_DATABASE", "").strip()
        return Path(env).expanduser().resolve() if env else None
    try:
        loaded = ProjectStore(project_root).load(project)
    except Exception:
        return None
    configured = str(loaded.settings.get("unified_database_path") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if loaded.target_root:
        return Path(loaded.target_root).expanduser().resolve() / CANONICAL_DATABASE_NAME
    return None


def format_stats(payload: dict[str, Any]) -> str:
    lines = [
        f"Baza: {payload.get('database')}", f"Integralność: {'OK' if payload.get('ok') else 'BŁĄD'}",
        f"Schemat: {payload.get('schema_version')}", f"Rozmiar: {payload.get('size_bytes', 0)} bajtów", "",
        "Najważniejsze liczniki:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in (payload.get("stats") or {}).items())
    if payload.get("foreign_key_error_count"):
        lines.append(f"\nBłędy kluczy obcych: {payload['foreign_key_error_count']}")
    return "\n".join(lines)


__all__ = ["HAS_PROMPT_TOOLKIT", "ask_text", "database_from_project", "format_stats", "message", "run_dialog"]
