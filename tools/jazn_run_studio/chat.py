"""Persistent public CLI transport, one outstanding request, no automatic replay."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .core import StudioError, _path_without_links, daemon_cli_options, python_executable, settings_path
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
        # The pending request is bound to this endpoint for its entire life.
        # Switching ports during resume could otherwise poll the wrong daemon.
        self.daemon_url = core.settings.daemon_url
        self.daemon_options = daemon_cli_options(core.settings)
        # A final stays pending until the GUI confirms its presentation.
        self._awaiting_gui_ack: str | None = None
        self._confirmed_failed: dict[str, str] | None = None
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
            if saved.get("daemon_url") != self.daemon_url:
                if saved.get("request_id"):
                    raise StudioError("Checkpoint pochodzi z innego albo niezweryfikowanego endpointu; nie wznawiaj na obcym daemonie")
                # A completed conversation from a different endpoint must not
                # silently become the local history of a newly chosen daemon.
            else:
                self.session_id = saved["session_id"]
                self.pending = saved.get("request_id")

    def _save(self) -> None:
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        _path_without_links(self.checkpoint)
        data = {"session_id": self.session_id, "request_id": self.pending,
                "daemon_url": self.daemon_url}
        fd, name = tempfile.mkstemp(dir=self.checkpoint.parent, prefix=".chat-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.checkpoint)
        finally:
            Path(name).unlink(missing_ok=True)

    def select_session(self, session_id: str) -> None:
        """Change the selected conversation only with no live or pending turn.

        The daemon is never asked to replay or move a request. A session may
        be reselected only while its transport is disconnected.
        """
        from .chat_session_catalog import SESSION_ID
        if not isinstance(session_id, str) or SESSION_ID.fullmatch(session_id) is None:
            raise StudioError("Nieprawidłowy identyfikator rozmowy")
        with self.lock:
            if (self.pending or self._awaiting_gui_ack
                    or (self.job is not None and not self.job.done.is_set())):
                raise StudioError(
                    "Najpierw rozstrzygnij turę i rozłącz transport; sesja nie zostanie zmieniona")
            if session_id == self.session_id:
                return
            previous = self.session_id
            self.session_id = session_id
            self.job = None
            self._confirmed_failed = None
            try:
                self._save()
            except OSError:
                self.session_id = previous
                raise

    def _require_same_endpoint(self) -> None:
        if self.core.settings.daemon_url != self.daemon_url:
            raise StudioError("Zmieniono endpoint daemona; rozłącz klienta i rozstrzygnij poprzednią turę przed ponownym połączeniem")
        if daemon_cli_options(self.core.settings) != self.daemon_options:
            raise StudioError("Niezgodność zweryfikowanego endpointu daemona")

    def connection_command(self) -> list[str]:
        self._require_same_endpoint()
        return [python_executable(self.core.settings), "-X", "utf8", str(self.core.root / "run.py"),
                "--chat-ollama", *self.daemon_options,
                "--ollama-model", self.core.settings.model, "--session-id", self.session_id]

    def resume_command(self, request: str) -> list[str]:
        self._require_same_endpoint()
        return [python_executable(self.core.settings), "-X", "utf8", str(self.core.root / "run.py"),
                "--daemon-result", request, *self.daemon_options]

    def connect(self) -> None:
        if not self.core.settings.model:
            raise StudioError("Wybierz model Ollama w ustawieniach")
        # Validate endpoint/model before reserving a long-lived job. Otherwise
        # changing the selected daemon leaves an unfinished "chat" reservation
        # and blocks the next connection attempt even though no process spawned.
        argv = self.connection_command()
        job = self.core._reserve("chat")
        self.job = job
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
                        job.error = "chat_protocol_error"
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
                if not job.cancel.is_set() and job.error is None:
                    job.error = "chat_transport_exit:" + str(proc.returncode)
                job.state = "failed" if job.error else "stopped" if job.cancel.is_set() else "failed"
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
        self._require_same_endpoint()
        with self.lock:
            if self.pending:
                raise StudioError("Najpierw odbierz wynik poprzedniego request_id; wiadomość nie zostanie powtórzona")
            if not message.strip() or len(message.encode("utf-8")) > 65536:
                raise StudioError("Wiadomość musi zawierać od 1 do 65536 bajtów")
            job = self.job
            if job is None or job.proc is None or job.proc.poll() is not None or job.proc.stdin is None:
                raise StudioError("Najpierw połącz lokalny czat")
            self.pending = "studio-turn-" + uuid4().hex
            self._confirmed_failed = None
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
        nested = payload.get("result")
        candidate = nested if isinstance(nested, dict) else payload
        code_value = payload.get("error_code") or candidate.get("error_code")
        if (payload.get("ok") is False or candidate.get("ok") is False) and code_value:
            code = str(code_value)
            if not code.isascii() or not code.replace("_", "").isalnum() or len(code) > 100:
                code = "runtime_error"
            job_value = payload.get("daemon_job")
            job = job_value if isinstance(job_value, dict) else payload
            job_result = job.get("result")
            result = job_result if isinstance(job_result, dict) else {}
            confirmed = bool(
                job.get("request_id") == request
                and job.get("session_id") == self.session_id
                and job.get("job_status") == "failed"
                and job.get("done") is True
                and job.get("ok") is False
                and result.get("ok") is False
                and result.get("error_code") == code
                and job.get("completed_at_utc")
                and not job.get("awaiting_host_finalization")
                and not job.get("phase_result_ready")
                and not any(job.get(key) for key in (
                    "host_turn_id", "host_trace_id", "host_request_contract_hash"
                ))
            )
            with self.lock:
                if self.pending == request:
                    self._confirmed_failed = (
                        {"request_id": request, "session_id": self.session_id,
                         "error_code": code, "daemon_url": self.daemon_url,
                         "completed_at_utc": str(job["completed_at_utc"])}
                        if confirmed else None
                    )
            message = (
                "Potwierdzona nieudana tura: " + code +
                ". Bez ponawiania wiadomości możesz wybrać Zamknij nieudaną turę."
                if confirmed else
                "Runtime zgłosił błąd: " + code +
                ". Brak potwierdzenia terminalnego wyniku; zachowano request_id."
            )
            self.core.emit("chat", "chat_state", message)
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

    def can_resolve_terminal_failure(self) -> bool:
        with self.lock:
            return bool(self.pending and self._awaiting_gui_ack is None
                        and self._confirmed_failed is not None
                        and self._confirmed_failed.get("request_id") == self.pending)

    def resolve_terminal_failure(self, request_id: str) -> None:
        """Operator-only archive of an authenticated terminal failure, not a final ACK."""
        from re import fullmatch

        with self.lock:
            proof = self._confirmed_failed
            if (not request_id or fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id) is None
                    or self.pending != request_id or self._awaiting_gui_ack is not None
                    or proof is None or proof.get("request_id") != request_id
                    or proof.get("session_id") != self.session_id
                    or proof.get("daemon_url") != self.daemon_url):
                raise StudioError("Brak potwierdzonej terminalnej porażki dla tej tury")
            archive = _path_without_links(
                self.checkpoint.with_name("chat-terminal-failure-" + request_id + ".json")
            )
            if archive.is_file():
                try:
                    existing = json.loads(archive.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeError) as exc:
                    raise StudioError("Nie można zweryfikować archiwum błędu") from exc
                if any(existing.get(key) != value for key, value in proof.items()):
                    raise StudioError("Archiwum nie odpowiada bieżącej turze")
            else:
                data = {"schema_version": "jss_chat_failed_ack/v1", **proof,
                        "operator_acknowledged_at_utc": datetime.now(timezone.utc).isoformat(),
                        "automatic_replay_performed": False,
                        "accepted_finalization_claimed": False,
                        "contains_user_text": False}
                fd, name = tempfile.mkstemp(dir=archive.parent, prefix=".chat-failed-")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        json.dump(data, stream, ensure_ascii=False)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, archive)
                finally:
                    Path(name).unlink(missing_ok=True)
            old_started = self.started_at
            self.pending, self.started_at = None, 0.0
            try:
                self._save()
            except OSError:
                self.pending, self.started_at = request_id, old_started
                raise
            self._confirmed_failed = None

    def resume(self) -> None:
        request = self.pending
        if not request:
            raise StudioError("Brak oczekującego request_id")
        argv = self.resume_command(request)
        job = self.core._reserve("chat:resume")
        def worker() -> None:
            try:
                job.state = "running"
                done = run(argv, cwd=self.core.root, timeout=30)
                if len(done.stdout) > 2097152:
                    raise ValueError("poll_output_limit")
                payload = json.loads(done.stdout)
                if not isinstance(payload, dict):
                    raise ValueError("invalid_resume_payload")
                self.receive(payload)
                job.returncode = done.returncode
                if done.returncode:
                    code = payload.get("error_code")
                    label = str(code or "")
                    if not (label.isascii() and 1 <= len(label) <= 100
                            and label.replace("_", "").isalnum()):
                        label = ""
                    suffix = ":" + label if label else ""
                    job.state, job.error = "failed", f"resume_exit:{done.returncode}{suffix}"
                elif self.pending is None or self._awaiting_gui_ack == request:
                    job.state = "succeeded"
                elif payload.get("done") is False or payload.get("phase_result_ready") is False:
                    job.state = "succeeded"  # Successful poll; pending request is not a failure.
                    self.core.emit("chat:resume", "chat_state", "Wynik nadal oczekuje. Zachowano request_id; wznów tę samą turę.")
                else:
                    job.state, job.error = "failed", "resume_result_unaccepted"
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                job.state, job.error = "failed", type(exc).__name__
            finally:
                job.finished = time.time()
                job.done.set()
                self.core.emit("chat:resume", "state", job.snapshot())
        threading.Thread(target=worker, daemon=True).start()
