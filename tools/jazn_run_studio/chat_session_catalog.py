"""Small operator-owned index of local chat session IDs, never message text.

Actual accepted transcript content remains exclusively in canonical SYSTEM
conversation_state; this index does not become MEMORY or settlement authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .core import StudioError, _path_without_links, settings_path

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def catalog_path(root: Path) -> Path:
    return _path_without_links(settings_path(root).with_name("chat-session-catalog.json"))


def load_sessions(root: Path) -> list[dict[str, str]]:
    path = catalog_path(root)
    if not path.exists():
        return []
    if path.stat().st_size > 32768:
        raise StudioError("Katalog sesji przekracza bezpieczny limit")
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "jss_chat_sessions/v1":
        raise StudioError("Nieprawidłowy katalog sesji czatu")
    rows = payload.get("sessions")
    if not isinstance(rows, list) or len(rows) > 100:
        raise StudioError("Nieprawidłowa liczba sesji czatu")
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            raise StudioError("Nieprawidłowy rekord sesji")
        sid, created = item.get("session_id"), item.get("created_at_utc")
        if (not isinstance(sid, str) or SESSION_ID.fullmatch(sid) is None
                or not isinstance(created, str) or len(created) > 48):
            raise StudioError("Nieprawidłowe metadane sesji")
        try:
            parsed = datetime.fromisoformat(created)
            if parsed.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise StudioError("Nieprawidłowy czas utworzenia sesji") from exc
        if sid in seen:
            raise StudioError("Zduplikowana tożsamość sesji")
        seen.add(sid)
        result.append({"session_id": sid, "created_at_utc": created})
    return result


def remember_session(root: Path, session_id: str) -> list[dict[str, str]]:
    if SESSION_ID.fullmatch(session_id) is None:
        raise StudioError("Nieprawidłowy identyfikator sesji")
    path = catalog_path(root)
    current = load_sessions(root)
    if not any(row["session_id"] == session_id for row in current):
        current.insert(0, {
            "session_id": session_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    if len(current) > 100:
        # Keep the oldest metadata rather than silently losing a session.
        raise StudioError("Katalog sesji jest pełny; nie usuwam starszych sesji")
    path.parent.mkdir(parents=True, exist_ok=True)
    _path_without_links(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".chat-session-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"schema": "jss_chat_sessions/v1", "sessions": current},
                      handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return current
