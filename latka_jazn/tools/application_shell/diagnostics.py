from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import traceback
from typing import Any


class DiagnosticsHub:
    """Thread-safe application diagnostics with a bounded in-memory view and JSONL log."""

    def __init__(
        self,
        app_id: str,
        state_dir: Path,
        *,
        enabled: bool = True,
        limit: int = 500,
        minimum_level: str = "INFO",
    ) -> None:
        self.app_id = app_id
        self.state_dir = Path(state_dir)
        self.enabled = bool(enabled)
        self.limit = max(50, int(limit))
        self.minimum_level = str(minimum_level or "INFO").upper()
        self._records: deque[dict[str, Any]] = deque(maxlen=self.limit)
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self.log_path = self.state_dir / "runtime" / f"{self.app_id}.jsonl"

    def reconfigure(
        self,
        *,
        enabled: bool | None = None,
        limit: int | None = None,
        minimum_level: str | None = None,
    ) -> None:
        """Apply live diagnostic settings without losing the newest records."""
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)
            if minimum_level is not None:
                level = str(minimum_level or "INFO").upper()
                self.minimum_level = level if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"
            if limit is not None:
                try:
                    normalized = max(50, min(5000, int(limit)))
                except (TypeError, ValueError, OverflowError):
                    normalized = self.limit
                if normalized != self.limit:
                    rows = list(self._records)[-normalized:]
                    self.limit = normalized
                    self._records = deque(rows, maxlen=normalized)

    def record(self, level: str, message: str, **details: Any) -> dict[str, Any]:
        level_name = str(level).upper()
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": level_name,
            "message": str(message),
            "details": details,
        }
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        with self._lock:
            threshold = levels.get(self.minimum_level, 20)
            enabled = self.enabled
            if levels.get(level_name, 20) < threshold:
                return record
            self._records.append(record)
        if enabled:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
                with self._write_lock:
                    with self.log_path.open("a", encoding="utf-8") as handle:
                        handle.write(line)
            except OSError:
                pass
        return record

    def exception(self, exc: BaseException, *, context: str = "") -> dict[str, Any]:
        return self.record(
            "ERROR",
            context or f"{type(exc).__name__}: {exc}",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def text(self, *, limit: int | None = None) -> str:
        rows = self.snapshot()
        if limit is not None:
            rows = rows[-max(1, int(limit)) :]
        if not rows:
            return "Brak zdarzeń diagnostycznych."
        rendered: list[str] = []
        for row in rows:
            rendered.append(f"{row['time']} [{row['level']}] {row['message']}")
            details = row.get("details") or {}
            if details:
                rendered.append(json.dumps(details, ensure_ascii=False, indent=2, default=str))
        return "\n".join(rendered)
