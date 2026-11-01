"""One serialized lane for owned report I/O; no runtime/process authority."""
from collections import deque
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    finished = Signal(object)


class _Work(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    def run(self) -> None:
        # Boundary of a worker: every programming/I/O failure is delivered as
        # failure, never a missing completion signal or fabricated success.
        try:
            payload = {"value": self.operation()}
        except Exception as exc:
            payload = {"error": type(exc).__name__}
        self.signals.finished.emit(payload)


class SerialIO(QObject):
    """Execute ordered immutable work inputs; callbacks stay on the Qt thread."""
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.queue: deque = deque()
        self.job: _Work | None = None
        self.callback: Callable | None = None
        self.failure: Callable | None = None
        self.abort_error: str | None = None

    @property
    def pending(self) -> bool:
        return self.job is not None or bool(self.queue)

    def submit(self, operation: Callable, done: Callable, failed: Callable) -> None:
        if len(self.queue) >= 64:
            self.queue.clear()
            self.abort_error = "EvidenceQueueLimit"
            return
        if self.abort_error is not None:
            return
        self.queue.append((operation, done, failed))
        self._pump()

    def _pump(self) -> None:
        if self.job is not None or not self.queue:
            return
        operation, self.callback, self.failure = self.queue.popleft()
        self.job = _Work(operation)
        self.job.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self.job)

    @Slot(object)
    def _finished(self, payload: dict) -> None:
        done, failed = self.callback, self.failure
        self.job = self.callback = self.failure = None
        if self.abort_error is not None:
            payload = {"error": self.abort_error}
            self.abort_error = None
        if "error" in payload:
            self.queue.clear()  # No dependent process may launch after failure.
            assert failed is not None
            failed(payload["error"])
        else:
            assert done is not None
            done(payload["value"])
        self._pump()
