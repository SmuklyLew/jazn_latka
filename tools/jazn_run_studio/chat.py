"""Persistent public CLI transport, one outstanding request, no automatic replay."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .core import StudioError, _path_without_links, python_executable, settings_path
from .external import run, spawn
from .chat_protocol import frames

if TYPE_CHECKING:
    from .core import Controller, Job


class ChatClient:
    def __init__(self, core: Controller):
        self.core = core
        self.lock = threading.RLock()
        self.session_id = "studio-" + uuid4().hex
        self.pending: str | None = None
        # A final stays pending until the GUI confirms its presentation.
        self._awaiting_gui_ack: str | None = None
        self.started_at = 0.0
        self.job: Job | None = None
        self.checkpoint = _path_without_links(settings_path(core.root).with_name("chat-checkpoint.json"))
        if self.checkpoint.is_file():
            if self.checkpoint.stat().st_size > 4096:
                raise StudioError("Nieprawidłowy checkpoint rozmowy")
            saved = json.loads(self.checkpoint.read_bytes())
            from re import fullmatch
            for key in ("session_id", "request_id"):
                if saved.get(key) is not None and not fullmatch(r"[A-Za-z0-9_-]{1,128}", saved[key]):
                    raise StudioError("Nieprawidłowy identyfikator checkpointu")
            self.session_id = saved["session_id"]
            self.pending = saved.get("request_id")

    def _save(self) -> None:
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        _path_without_links(self.checkpoint)
        data = {"session_id": self.session_id, "request_id": self.pending}
        fd, name = tempfile.mkstemp(dir=self.checkpoint.parent, prefix=".chat-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.checkpoint)
        finally:
            Path(name).unlink(missing_ok=True)

    def connect(self) -> None:
        if not self.core.settings.model:
            raise StudioError("Wybierz model Ollama w ustawieniach")
        job = self.core._reserve("chat")
        self.job = job
        argv = [python_executable(self.core.settings), "-X", "utf8", str(self.core.root / "run.py"),
                "chat-ollama", "--ollama-model", self.core.settings.model, "--session-id", self.session_id]
        def worker() -> None:
            try:
                proc = spawn(argv, cwd=self.core.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=self.core.child_environment(profile=True))
                job.proc, job.pid, job.state = proc, proc.pid, "running"
                self.core.emit("chat", "state", job.snapshot())
                assert proc.stdout is not None and proc.stderr is not None
                output = proc.stdout
                # stderr is redacted and bounded by the shared reader; stdout is private protocol.
                stderr = threading.Thread(target=self.core._read, args=(job, proc.stderr), daemon=True)
                stderr.start()
                def reader() -> None:
                    try:
                        for payload in frames(output):
                            self.receive(payload)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        self.core.emit("chat", "chat_state", "Błąd transportu. Zachowano request_id; użyj Wznów wynik.")
                        job.cancel.set()
                thread = threading.Thread(target=reader, daemon=True)
                thread.start()
                while proc.poll() is None:
                    if job.cancel.wait(0.1):
                        proc.terminate()
                        try:
                            proc.wait(3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(3)
                        break
                    if self.pending and self.started_at and time.monotonic() - self.started_at > 180:
                        self.core.emit("chat", "chat_state", "Oczekiwanie przekroczyło 180 s. Nie wysłano ponownie wiadomości; wznów ten sam wynik.")
                        self.started_at = 0
                thread.join(3)
                stderr.join(3)
                job.returncode = proc.returncode
                job.state = "stopped" if job.cancel.is_set() else "failed"
            except (OSError, ValueError) as exc:
                job.state, job.error = "failed", type(exc).__name__
            finally:
                job.output.clear()
                job.finished = time.time()
                job.done.set()
                self.core.emit("chat", "state", job.snapshot())
                self.core.emit("chat", "chat_state", "Transport zamknięty. Nierozstrzygnięte żądanie zachowano do wznowienia.")
        threading.Thread(target=worker, daemon=True).start()

    def send(self, message: str) -> str:
        with self.lock:
            if self.pending:
                raise StudioError("Najpierw odbierz wynik poprzedniego request_id; wiadomość nie zostanie powtórzona")
            if not message.strip() or len(message.encode("utf-8")) > 65536:
                raise StudioError("Wiadomość musi zawierać od 1 do 65536 bajtów")
            job = self.job
            if job is None or job.proc is None or job.proc.poll() is not None or job.proc.stdin is None:
                raise StudioError("Najpierw połącz lokalny czat")
            self.pending = "studio-turn-" + uuid4().hex
            self._save()  # Durable identity before any bytes can reach runtime.
            payload = {"message": message, "session_id": self.session_id, "request_id": self.pending}
            try:
                job.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                job.proc.stdin.flush()
            except OSError:
                raise StudioError("Niepewny transport. Zachowano request_id; użyj Wznów wynik, bez ponownego wysyłania") from None
            self.started_at = time.monotonic()
            return self.pending

    def receive(self, payload: dict[str, Any]) -> None:
        with self.lock:
            request = self.pending
        if not request:
            self.core.emit("chat", "chat_state", "Odebrano diagnostykę transportu bez aktywnego żądania.")
            return
        if payload.get("error_code") and payload.get("ok") is False:
            code = str(payload["error_code"])
            if not code.isascii() or not code.replace("_", "").isalnum() or len(code) > 100:
                code = "runtime_error"
            self.core.emit("chat", "chat_state", "Runtime zgłosił błąd: " + code + ". Zachowano request_id; użyj Wznów wynik.")
            return
        # No unaccepted candidate or user prompt is sent into the shared log registry.
        checked = run([python_executable(self.core.settings), "-X", "utf8", "-m",
                       "tools.jazn_run_studio.validation_worker"], cwd=self.core.root,
                      data=json.dumps({"payload": payload, "request_id": request,
                                       "session_id": self.session_id}, ensure_ascii=False).encode("utf-8"), timeout=30)
        if checked.returncode or len(checked.stdout) > 2097152:
            raise ValueError("Final validator failed")
        result = json.loads(checked.stdout)
        if result.get("accepted") is True:
            with self.lock:
                if self.pending != request:
                    raise ValueError("Request changed during validation")
                if self._awaiting_gui_ack == request:
                    return  # Duplicate transport completion, not a second visible turn.
                self._awaiting_gui_ack = request
            # No durable checkpoint is cleared here: a GUI/crash interruption
            # must retain the exact request_id for daemon-result recovery.
            self.core.emit("chat", "chat_final", result)
        else:
            self.core.emit("chat", "chat_state", "Brak zaakceptowanej wypowiedzi. Zachowano request_id: " + request)

    def acknowledge_final(self, request_id: str) -> None:
        """Clear a pending turn only after the accepted final reaches the GUI."""
        with self.lock:
            if not request_id or self.pending != request_id or self._awaiting_gui_ack != request_id:
                raise StudioError("Brak zaakceptowanego wyniku do potwierdzenia")
            previous_started = self.started_at
            self.pending = None
            self.started_at = 0.0
            try:
                self._save()
            except OSError:
                # An unsuccessful checkpoint update may never unlock another send.
                self.pending = request_id
                self.started_at = previous_started
                raise
            self._awaiting_gui_ack = None

    def resume(self) -> None:
        request = self.pending
        if not request:
            raise StudioError("Brak oczekującego request_id")
        job = self.core._reserve("chat:resume")
        def worker() -> None:
            try:
                job.state = "running"
                done = run([python_executable(self.core.settings), "-X", "utf8", str(self.core.root / "run.py"),
                            "--daemon-result", request], cwd=self.core.root, timeout=30)
                if len(done.stdout) > 2097152:
                    raise ValueError("poll_output_limit")
                self.receive(json.loads(done.stdout))
                job.state = "succeeded" if (self.pending is None or self._awaiting_gui_ack == request) else "failed"
                job.returncode = done.returncode
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                job.state, job.error = "failed", type(exc).__name__
            finally:
                job.finished = time.time()
                job.done.set()
                self.core.emit("chat:resume", "state", job.snapshot())
        threading.Thread(target=worker, daemon=True).start()
