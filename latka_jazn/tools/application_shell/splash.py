from __future__ import annotations

import sys
import time


class TerminalSplash:
    """Small startup indicator that remains friendly to redirected/non-interactive output."""

    def __init__(self, title: str, *, enabled: bool = True) -> None:
        self.title = title
        self.enabled = bool(enabled and getattr(sys.stdout, "isatty", lambda: False)())
        self.started = time.monotonic()
        self._shown = False
        self._closed = False

    def __enter__(self) -> "TerminalSplash":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def step(self, message: str) -> None:
        self.update(message)

    def update(self, message: str) -> None:
        if not self.enabled:
            return
        prefix = "Uruchamianie" if not self._shown else "Wczytywanie"
        print(f"{prefix} {self.title} — {message}…", flush=True)
        self._shown = True

    def done(self) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.enabled and self._shown:
            elapsed = time.monotonic() - self.started
            print(f"{self.title} gotowe ({elapsed:.2f}s).", flush=True)
