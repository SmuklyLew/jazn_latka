"""Schedule existing asynchronous read-only probes with bounded CLI cadence."""
from __future__ import annotations

import time
from typing import Callable

from .core import Controller


class ServiceMonitor:
    """No process ownership: closing a view stops scheduling, not shared jobs."""

    def __init__(self, core: Controller, clock: Callable[[], float] = time.monotonic):
        self.core = core
        self.clock = clock
        self.last_status = float("-inf")

    def poll(self) -> None:
        if self.core.closed:
            return
        now = self.clock()
        operations = []
        if now - self.last_status >= max(10, int(self.core.settings.service_refresh_seconds)):
            self.last_status = now
            operations.extend((key, lambda key=key: self.core.start_action(key))
                              for key in ("status", "supervisor"))
        operations.extend((key, lambda key=key: self.core.probe(key, observe_only=True))
                          for key in ("ollama_process", "ollama", "gateway"))
        if self.core.settings.cloudflare_url:
            operations.append(("cloudflare", lambda: self.core.probe("cloudflare", observe_only=True)))
        for key, operation in operations:
            try:
                operation()
            except (OSError, ValueError, RuntimeError) as exc:
                self.core.emit("service-monitor", "log",
                               "Monitor: odczyt " + key + " niedostępny (" + type(exc).__name__ + ").")
