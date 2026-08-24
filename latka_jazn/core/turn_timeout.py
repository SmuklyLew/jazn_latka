from __future__ import annotations

import os
import multiprocessing
import queue
import threading
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, TypeVar

from latka_jazn.core.turn_execution import TurnExecutionContext

T = TypeVar("T")

DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS = 45.0
DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS = 600.0

_DEEP_RECALL_MEMORY_MARKERS = (
    "pamiet", "wspomn", "archiw", "baza danych", "dziennik", "rozmow", "histori",
)
_DEEP_RECALL_SCOPE_MARKERS = (
    "przeszuk", "przejrz", "odtworz", "rekonstruk", "znajdz", "wszystk",
    "co sie dzialo", "pierwsz wers", "ksiazk", "pamietnik", "moimi oczami",
    "swiat moimi oczami", "witaj w podrozy jazni",
)


class RuntimeTurnTimeoutError(TimeoutError):
    """Raised when a chat-facing runtime turn does not finish in bounded time."""

    def __init__(self, *, command: str, timeout_seconds: float, phase: str = "runtime_turn") -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.phase = phase
        super().__init__(
            f"{command} {phase} exceeded {timeout_seconds:.3g}s; returning a controlled timeout instead of hanging"
        )


class RuntimeWorkerProcessError(RuntimeError):
    """Raised when a hard-isolated runtime worker exits without a valid result."""

    def __init__(self, *, error_code: str, message: str, remote_type: str | None = None) -> None:
        self.error_code = str(error_code or "runtime_worker_process_failed")
        self.remote_type = str(remote_type or "") or None
        super().__init__(str(message or self.error_code))


def runtime_turn_timeout_seconds(config: object | None = None) -> float:
    raw = os.environ.get("JAZN_RUNTIME_TURN_TIMEOUT_SECONDS") or os.environ.get("JAZN_TURN_TIMEOUT")
    if raw is not None:
        try:
            value = float(raw)
            return value if value > 0 else DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS
        except Exception:
            return DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS
    configured = getattr(config, "runtime_turn_timeout_seconds", None)
    try:
        value = float(configured) if configured is not None else DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS
        return value if value > 0 else DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS
    except Exception:
        return DEFAULT_RUNTIME_TURN_TIMEOUT_SECONDS


def _timeout_normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.replace("ł", "l").split())


def runtime_turn_timeout_for_text(
    user_text: str,
    *,
    config: object | None = None,
    base_timeout_seconds: float | None = None,
) -> tuple[float, str]:
    """Return a bounded per-turn budget without turning every turn into a long wait.

    Deep autobiographical/archive recall is the known expensive class.  It gets a
    larger hard deadline, while ordinary dialogue keeps the existing default.
    This is deliberately a conservative pre-routing classifier: it only extends
    the deadline when both a memory signal and a broad/deep retrieval signal are
    present.
    """

    base = float(base_timeout_seconds or runtime_turn_timeout_seconds(config))
    normalized = _timeout_normalize(user_text)
    memory_signal = any(marker in normalized for marker in _DEEP_RECALL_MEMORY_MARKERS)
    scope_signal = any(marker in normalized for marker in _DEEP_RECALL_SCOPE_MARKERS)
    if not (memory_signal and scope_signal):
        return max(0.001, base), "default"

    raw = os.environ.get("JAZN_DEEP_RECALL_TURN_TIMEOUT_SECONDS")
    configured = getattr(config, "deep_recall_turn_timeout_seconds", None)
    candidate = raw if raw is not None else configured
    try:
        deep = float(candidate) if candidate is not None else DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        deep = DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS
    if deep <= 0:
        deep = DEFAULT_DEEP_RECALL_TURN_TIMEOUT_SECONDS
    return max(base, deep), "deep_memory_recall"


def _persist_turn_audit_async(turn_context: TurnExecutionContext, *, event_type: str) -> None:
    """Persist fail-soft timeout telemetry without delaying the terminal result."""

    threading.Thread(
        target=turn_context.persist_audit,
        kwargs={"event_type": event_type},
        name="jazn-turn-audit-persist",
        daemon=True,
    ).start()


def run_with_runtime_turn_timeout(func: Callable[[], T], *, command: str, timeout_seconds: float) -> T:
    """Run a stateless call with a daemon-thread watchdog.

    Do not use this around an object that already owns thread-bound resources
    such as sqlite3 connections.  For JaznRuntimeSession use
    RuntimeSessionWorker instead, which creates and uses the session inside one
    dedicated worker thread.
    """

    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put(("ok", func()))
        except BaseException as exc:  # noqa: BLE001 - propagated to caller as-is
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_target, name=f"jazn-{command}-turn-watchdog", daemon=True)
    worker.start()
    try:
        status, payload = result_queue.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        raise RuntimeTurnTimeoutError(command=command, timeout_seconds=timeout_seconds) from exc
    if status == "error":
        raise payload  # type: ignore[misc]
    return payload  # type: ignore[return-value]


class RuntimeSessionWorker:
    """Own one JaznRuntimeSession in the same daemon thread for all turns.

    sqlite3 objects are thread-bound by default.  This worker prevents the chat
    watchdog from calling a session that was created in a different thread while
    still letting --chat and --chat-gpt return controlled timeout errors.
    """

    runtime_turn_timeout_managed = True

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any],
        config: Any,
        session_id: str | None,
        no_carryover: bool,
        source_client: str,
        command: str,
        timeout_seconds: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._session_id = session_id
        self._no_carryover = no_carryover
        self._source_client = source_client
        self._command = command
        self._timeout_seconds = timeout_seconds or runtime_turn_timeout_seconds(config)
        self._requests: queue.Queue[tuple[str, Any, queue.Queue[tuple[str, object]] | None]] = queue.Queue()
        self._ready: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
        self._closed = False
        self._timed_out = False
        self._startup_cancelled = threading.Event()
        self.state: Any = None
        self.config = config
        self.last_turn_context: TurnExecutionContext | None = None
        self._thread = threading.Thread(target=self._run, name=f"jazn-{command}-session-worker", daemon=True)
        self._thread.start()
        ready_timeout = min(max(self._timeout_seconds, 1.0), 10.0)
        try:
            status, payload = self._ready.get(timeout=ready_timeout)
        except queue.Empty as exc:
            self._startup_cancelled.set()
            raise RuntimeTurnTimeoutError(
                command=self._command,
                timeout_seconds=ready_timeout,
                phase="session_startup",
            ) from exc
        if status == "error":
            raise payload  # type: ignore[misc]
        self.state = payload

    def _run(self) -> None:
        session: Any | None = None
        try:
            session = self._session_factory(
                self._config,
                session_id=self._session_id,
                no_carryover=self._no_carryover,
                source_client=self._source_client,
            )
            if self._startup_cancelled.is_set():
                close = getattr(session, "close", None)
                if callable(close):
                    close()
                return
            self._ready.put(("ok", getattr(session, "state", None)))
        except BaseException as exc:  # noqa: BLE001
            self._ready.put(("error", exc))
            return

        while True:
            op, payload, response_queue = self._requests.get()
            if op == "close":
                try:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
                    if response_queue is not None:
                        response_queue.put(("ok", True))
                except BaseException as exc:  # noqa: BLE001
                    if response_queue is not None:
                        response_queue.put(("error", exc))
                return
            if op == "process_user_text":
                kwargs = dict(payload)
                turn_context = kwargs.get("_turn_context")
                try:
                    assert session is not None
                    result = session.process_user_text(**kwargs)
                    if isinstance(turn_context, TurnExecutionContext) and turn_context.cancelled:
                        turn_context.mark_stage(
                            "final_result_serialization",
                            status="late_completion_ignored",
                            error_code="execution_timeout",
                        )
                        turn_context.finalize_total(status="late_completion_ignored", error_code="execution_timeout")
                        _persist_turn_audit_async(
                            turn_context, event_type="runtime_turn_late_completion"
                        )
                    if response_queue is not None:
                        response_queue.put(("ok", result))
                except BaseException as exc:  # noqa: BLE001
                    if isinstance(turn_context, TurnExecutionContext) and turn_context.cancelled:
                        turn_context.record_technical_event(
                            "runtime_turn_late_exception",
                            {"error_code": type(exc).__name__, "error": str(exc)},
                        )
                        turn_context.finalize_total(status="late_exception_ignored", error_code=type(exc).__name__)
                        _persist_turn_audit_async(
                            turn_context, event_type="runtime_turn_late_exception"
                        )
                    if response_queue is not None:
                        response_queue.put(("error", exc))

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    @property
    def usable(self) -> bool:
        return not self._closed and not self._timed_out and self._thread.is_alive()

    def _call(
        self,
        op: str,
        payload: Any,
        *,
        heartbeat_callback: Callable[[], None] | None = None,
        turn_context: TurnExecutionContext | None = None,
        timeout_seconds: float | None = None,
        timeout_profile: str = "default",
    ) -> Any:
        if self._closed:
            raise RuntimeError("RuntimeSessionWorker is closed")
        if self._timed_out:
            raise RuntimeError("RuntimeSessionWorker is retired after an execution timeout")
        response_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
        self._requests.put((op, payload, response_queue))
        effective_timeout = max(0.001, float(timeout_seconds or self._timeout_seconds))
        deadline = time.monotonic() + effective_timeout
        while True:
            if heartbeat_callback is not None:
                heartbeat_callback()

            # Prefer a result that is already available at the deadline boundary.
            # This avoids reporting a timeout merely because the scheduler woke the
            # caller a fraction late after the worker had already completed.
            try:
                status, value = response_queue.get_nowait()
                break
            except queue.Empty:
                pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._timed_out = True
                if turn_context is not None:
                    turn_context.cancel(
                        reason=f"{self._command} execution deadline exceeded",
                        error_code="execution_timeout",
                    )
                    turn_context.record_technical_event(
                        "runtime_turn_execution_timeout",
                        {
                            "command": self._command,
                            "timeout_seconds": effective_timeout,
                            "timeout_profile": timeout_profile,
                            "phase": "runtime_turn",
                        },
                    )
                    _persist_turn_audit_async(
                        turn_context,
                        event_type="runtime_turn_execution_timeout",
                    )
                raise RuntimeTurnTimeoutError(command=self._command, timeout_seconds=effective_timeout)
            try:
                status, value = response_queue.get(timeout=min(0.25, remaining))
                break
            except queue.Empty:
                continue
        if status == "error":
            raise value  # type: ignore[misc]
        return value

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        heartbeat_callback = kwargs.pop("_heartbeat_callback", None)
        request_id = str(kwargs.pop("request_id", "") or kwargs.pop("_request_id", "") or "") or None
        timeout_override = kwargs.pop("_timeout_seconds_override", None)
        timeout_profile_override = str(kwargs.pop("_timeout_profile", "") or "").strip() or None
        effective_timeout, timeout_profile = runtime_turn_timeout_for_text(
            user_text,
            config=self._config,
            base_timeout_seconds=float(timeout_override or self._timeout_seconds),
        )
        if timeout_profile_override is not None:
            timeout_profile = timeout_profile_override
        turn_context = kwargs.pop("_turn_context", None)
        if not isinstance(turn_context, TurnExecutionContext):
            turn_context = TurnExecutionContext.create(
                request_id=request_id,
                session_id=str(getattr(self.state, "session_id", None) or self._session_id or "runtime-session"),
                timeout_seconds=effective_timeout,
                audit_db_path=getattr(self._config, "audit_db_path", None),
            )
        else:
            # The daemon creates the shared context with the same adaptive budget.
            # Never extend an already-created context here; only respect its bound.
            effective_timeout = min(effective_timeout, max(0.001, turn_context.remaining_seconds()))
        turn_context.mark_stage("session_initialization", status="reused")
        turn_context.record_technical_event(
            "runtime_turn_timeout_budget",
            {
                "timeout_seconds": round(float(effective_timeout), 6),
                "timeout_profile": timeout_profile,
                "base_timeout_seconds": self._timeout_seconds,
            },
        )
        self.last_turn_context = turn_context
        payload = {"user_text": user_text, "_turn_context": turn_context, **kwargs}
        return self._call(
            "process_user_text",
            payload,
            heartbeat_callback=heartbeat_callback,
            turn_context=turn_context,
            timeout_seconds=effective_timeout,
            timeout_profile=timeout_profile,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._thread.is_alive():
            return
        response_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
        self._requests.put(("close", None, response_queue))
        wait_seconds = min(max(self._timeout_seconds, 1.0), 5.0)
        try:
            response_queue.get(timeout=wait_seconds)
        except queue.Empty:
            pass
        self._thread.join(timeout=wait_seconds)


def _hard_worker_state_payload(state: Any) -> dict[str, Any]:
    to_dict = getattr(state, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return dict(value)
    session_id = getattr(state, "session_id", None)
    return {"session_id": str(session_id or "runtime-session")}


def _hard_worker_child_main(
    connection: Any,
    cancel_event: Any,
    session_factory: Callable[..., Any],
    config: Any,
    session_id: str | None,
    no_carryover: bool,
    source_client: str,
) -> None:
    """Own the runtime session inside a spawn-safe child process.

    Only bounded, structured messages cross the process boundary.  In
    particular, TurnExecutionContext is rebuilt in the child because its locks
    and staged write callbacks are intentionally process-local.
    """

    session: Any | None = None
    try:
        session = session_factory(
            config,
            session_id=session_id,
            no_carryover=no_carryover,
            source_client=source_client,
        )
        connection.send(
            {
                "kind": "ready",
                "pid": os.getpid(),
                "state": _hard_worker_state_payload(getattr(session, "state", None)),
            }
        )
    except BaseException as exc:  # noqa: BLE001 - child must report startup failure
        try:
            connection.send(
                {
                    "kind": "error",
                    "error_code": "runtime_worker_process_startup_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
        connection.close()
        return

    try:
        while True:
            try:
                message = connection.recv()
            except (EOFError, OSError):
                return
            if not isinstance(message, dict):
                continue
            operation = str(message.get("op") or "")
            if operation == "close":
                close = getattr(session, "close", None)
                if callable(close):
                    close()
                try:
                    connection.send({"kind": "closed", "pid": os.getpid()})
                except (BrokenPipeError, EOFError, OSError):
                    pass
                return
            if operation != "process_user_text":
                continue

            cancel_event.clear()
            timeout_seconds = max(0.001, float(message.get("timeout_seconds") or 0.001))
            audit_db_raw = str(message.get("audit_db_path") or "").strip()
            turn_context = TurnExecutionContext.create(
                request_id=str(message.get("request_id") or "") or None,
                turn_id=str(message.get("turn_id") or "") or None,
                session_id=str(message.get("session_id") or session_id or "runtime-session"),
                timeout_seconds=timeout_seconds,
                audit_db_path=Path(audit_db_raw) if audit_db_raw else None,
            )
            turn_context.mark_stage("session_initialization", status="reused_in_worker_process")
            turn_context.record_technical_event(
                "runtime_worker_process_boundary",
                {
                    "worker_pid": os.getpid(),
                    "parent_pid": os.getppid(),
                    "start_method": "spawn",
                    "hard_process_isolation": True,
                },
            )
            watcher_stop = threading.Event()

            def _watch_cancel() -> None:
                while not watcher_stop.is_set():
                    if cancel_event.wait(0.025):
                        turn_context.cancel(
                            reason="parent requested cooperative cancellation before process termination",
                            error_code="execution_timeout",
                        )
                        return

            watcher = threading.Thread(
                target=_watch_cancel,
                name="jazn-worker-process-cancellation-watch",
                daemon=True,
            )
            watcher.start()
            try:
                kwargs = dict(message.get("kwargs") or {})
                assert session is not None
                result = session.process_user_text(
                    str(message.get("user_text") or ""),
                    _turn_context=turn_context,
                    **kwargs,
                )
                connection.send(
                    {
                        "kind": "result",
                        "pid": os.getpid(),
                        "result": result,
                        "turn_telemetry": turn_context.snapshot(),
                    }
                )
            except BaseException as exc:  # noqa: BLE001 - serialized for the parent
                try:
                    connection.send(
                        {
                            "kind": "error",
                            "error_code": "runtime_worker_process_turn_failed",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "pid": os.getpid(),
                            "turn_telemetry": turn_context.snapshot(),
                        }
                    )
                except (BrokenPipeError, EOFError, OSError):
                    return
            finally:
                watcher_stop.set()
                watcher.join(timeout=0.1)
    finally:
        try:
            close = getattr(session, "close", None)
            if callable(close):
                close()
        except BaseException:  # noqa: BLE001 - process is already shutting down
            pass
        connection.close()


class HardIsolatedRuntimeSessionWorker:
    """Run a persistent runtime session in a replaceable spawned process.

    The daemon remains in the parent process.  A deadline first requests
    cooperative cancellation, waits a short bounded grace period, then
    terminates (and, if needed, kills) only the child.  A timed-out child is
    never reused, so the next turn receives a fresh process boundary.
    """

    runtime_turn_timeout_managed = True
    hard_worker_process_isolation = True
    process_start_method = "spawn"

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any],
        config: Any,
        session_id: str | None,
        no_carryover: bool,
        source_client: str,
        command: str,
        timeout_seconds: float | None = None,
        cancel_grace_seconds: float = 0.5,
        startup_timeout_seconds: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._session_id = session_id
        self._no_carryover = no_carryover
        self._source_client = source_client
        self._command = command
        self._timeout_seconds = timeout_seconds or runtime_turn_timeout_seconds(config)
        self._cancel_grace_seconds = max(0.05, float(cancel_grace_seconds))
        self._startup_timeout_seconds = max(1.0, float(startup_timeout_seconds))
        self._closed = False
        self._timed_out = False
        self._turn_lock = threading.Lock()
        self._termination_lock = threading.Lock()
        self.last_turn_context: TurnExecutionContext | None = None
        self.last_termination: dict[str, Any] | None = None
        self.hard_termination_count = 0
        context = multiprocessing.get_context(self.process_start_method)
        parent_connection, child_connection = context.Pipe(duplex=True)
        self._connection = parent_connection
        self._cancel_event = context.Event()
        process_factory: Callable[..., multiprocessing.Process] = getattr(context, "Process")
        self._process = process_factory(
            target=_hard_worker_child_main,
            args=(
                child_connection,
                self._cancel_event,
                session_factory,
                config,
                session_id,
                no_carryover,
                source_client,
            ),
            name=f"jazn-{command}-session-process",
            daemon=False,
        )
        self._process.start()
        child_connection.close()
        if not self._connection.poll(self._startup_timeout_seconds):
            self._timed_out = True
            self._cancel_event.set()
            self._terminate_child(reason="session_startup_timeout")
            raise RuntimeTurnTimeoutError(
                command=self._command,
                timeout_seconds=self._startup_timeout_seconds,
                phase="session_process_startup",
            )
        startup = self._recv_message(error_code="runtime_worker_process_startup_failed")
        if startup.get("kind") != "ready":
            self._closed = True
            self._terminate_child(reason="session_startup_failed")
            raise RuntimeWorkerProcessError(
                error_code=str(startup.get("error_code") or "runtime_worker_process_startup_failed"),
                message=str(startup.get("error") or "runtime worker process failed during startup"),
                remote_type=str(startup.get("error_type") or "") or None,
            )
        self.worker_pid = int(startup.get("pid") or self._process.pid or 0)
        state_value = startup.get("state")
        state_payload: dict[str, Any] = (
            {str(key): value for key, value in state_value.items()}
            if isinstance(state_value, dict)
            else {}
        )
        self.state = SimpleNamespace(**state_payload)
        self.config = config

    def _recv_message(self, *, error_code: str) -> dict[str, Any]:
        try:
            value = self._connection.recv()
        except (EOFError, OSError) as exc:
            raise RuntimeWorkerProcessError(
                error_code=error_code,
                message=(
                    f"runtime worker process exited without a response "
                    f"(pid={self._process.pid}, exitcode={self._process.exitcode})"
                ),
                remote_type=type(exc).__name__,
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeWorkerProcessError(
                error_code=error_code,
                message="runtime worker process returned an invalid message",
            )
        return value

    def _terminate_child(self, *, reason: str) -> dict[str, Any]:
        with self._termination_lock:
            pid = self._process.pid
            cooperative_requested = False
            terminated = False
            killed = False
            try:
                self._cancel_event.set()
                cooperative_requested = True
            except (OSError, ValueError):
                pass
            if self._process.is_alive():
                self._process.join(timeout=self._cancel_grace_seconds)
            if self._process.is_alive():
                self._process.terminate()
                terminated = True
                self._process.join(timeout=self._cancel_grace_seconds)
            if self._process.is_alive():
                self._process.kill()
                killed = True
                self._process.join(timeout=self._cancel_grace_seconds)
            if terminated or killed:
                self.hard_termination_count += 1
            outcome = {
                "reason": reason,
                "worker_pid": pid,
                "parent_pid": os.getpid(),
                "cooperative_cancel_requested": cooperative_requested,
                "cancel_grace_seconds": self._cancel_grace_seconds,
                "terminated": terminated,
                "killed": killed,
                "exitcode": self._process.exitcode,
                "parent_process_alive": True,
                "worker_reusable": False,
            }
            self.last_termination = outcome
            return outcome

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    @property
    def usable(self) -> bool:
        return not self._closed and not self._timed_out and self._process.is_alive()

    def process_user_text(self, user_text: str, **kwargs: Any) -> dict[str, Any]:
        heartbeat_callback = kwargs.pop("_heartbeat_callback", None)
        request_id = str(kwargs.pop("request_id", "") or kwargs.pop("_request_id", "") or "") or None
        timeout_override = kwargs.pop("_timeout_seconds_override", None)
        timeout_profile_override = str(kwargs.pop("_timeout_profile", "") or "").strip() or None
        effective_timeout, timeout_profile = runtime_turn_timeout_for_text(
            user_text,
            config=self._config,
            base_timeout_seconds=float(timeout_override or self._timeout_seconds),
        )
        if timeout_profile_override is not None:
            timeout_profile = timeout_profile_override
        parent_context = kwargs.pop("_turn_context", None)
        if not isinstance(parent_context, TurnExecutionContext):
            parent_context = TurnExecutionContext.create(
                request_id=request_id,
                session_id=str(getattr(self.state, "session_id", None) or self._session_id or "runtime-session"),
                timeout_seconds=effective_timeout,
                audit_db_path=getattr(self._config, "audit_db_path", None),
            )
        else:
            effective_timeout = min(
                effective_timeout,
                max(0.001, parent_context.remaining_seconds()),
            )
        parent_context.mark_stage("session_initialization", status="hard_process_ready")
        parent_context.record_technical_event(
            "runtime_worker_process_dispatch",
            {
                "worker_pid": self.worker_pid,
                "parent_pid": os.getpid(),
                "timeout_seconds": round(float(effective_timeout), 6),
                "timeout_profile": timeout_profile,
                "cancel_grace_seconds": self._cancel_grace_seconds,
            },
        )
        self.last_turn_context = parent_context
        # Reserve a small finalization margin inside the parent's hard budget.
        # For very short test/diagnostic deadlines the reserve scales down so a
        # healthy fast turn still has useful execution time.
        finalization_reserve = min(
            self._cancel_grace_seconds,
            max(0.001, effective_timeout * 0.10),
        )
        child_context_budget = max(0.001, effective_timeout - finalization_reserve)
        message = {
            "op": "process_user_text",
            "user_text": user_text,
            "kwargs": kwargs,
            "request_id": parent_context.request_id,
            "turn_id": parent_context.turn_id,
            "session_id": parent_context.session_id,
            "timeout_seconds": child_context_budget,
            "timeout_profile": timeout_profile,
            "audit_db_path": str(parent_context.audit_db_path or ""),
        }
        with self._turn_lock:
            if self._closed:
                raise RuntimeError("HardIsolatedRuntimeSessionWorker is closed")
            if self._timed_out:
                raise RuntimeError("HardIsolatedRuntimeSessionWorker is retired after an execution timeout")
            if not self._process.is_alive():
                self._closed = True
                raise RuntimeWorkerProcessError(
                    error_code="runtime_worker_process_not_alive",
                    message=f"runtime worker process is not alive (exitcode={self._process.exitcode})",
                )
            self._cancel_event.clear()
            try:
                self._connection.send(message)
            except (BrokenPipeError, EOFError, OSError) as exc:
                self._closed = True
                raise RuntimeWorkerProcessError(
                    error_code="runtime_worker_process_dispatch_failed",
                    message=str(exc),
                    remote_type=type(exc).__name__,
                ) from exc

            deadline = time.monotonic() + effective_timeout
            while True:
                if heartbeat_callback is not None:
                    heartbeat_callback()
                if self._connection.poll(0):
                    response = self._recv_message(error_code="runtime_worker_process_response_failed")
                    break
                if not self._process.is_alive():
                    self._closed = True
                    raise RuntimeWorkerProcessError(
                        error_code="runtime_worker_process_exited",
                        message=(
                            f"runtime worker process exited during turn "
                            f"(pid={self.worker_pid}, exitcode={self._process.exitcode})"
                        ),
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._timed_out = True
                    parent_context.cancel(
                        reason=f"{self._command} execution deadline exceeded",
                        error_code="execution_timeout",
                    )
                    parent_context.record_technical_event(
                        "runtime_turn_hard_process_timeout",
                        {
                            "command": self._command,
                            "timeout_seconds": effective_timeout,
                            "timeout_profile": timeout_profile,
                            "worker_pid": self.worker_pid,
                            "cooperative_cancel_first": True,
                        },
                    )
                    termination = self._terminate_child(reason="runtime_turn_execution_timeout")
                    parent_context.record_technical_event(
                        "runtime_worker_process_terminated",
                        termination,
                    )
                    _persist_turn_audit_async(
                        parent_context,
                        event_type="runtime_turn_hard_process_timeout",
                    )
                    raise RuntimeTurnTimeoutError(
                        command=self._command,
                        timeout_seconds=effective_timeout,
                    )
                time.sleep(min(0.025, max(0.001, remaining)))

        if response.get("kind") == "error":
            self._closed = True
            self._terminate_child(reason="runtime_turn_failed")
            raise RuntimeWorkerProcessError(
                error_code=str(response.get("error_code") or "runtime_worker_process_turn_failed"),
                message=str(response.get("error") or "runtime worker process turn failed"),
                remote_type=str(response.get("error_type") or "") or None,
            )
        if response.get("kind") != "result" or not isinstance(response.get("result"), dict):
            self._closed = True
            self._terminate_child(reason="invalid_runtime_result")
            raise RuntimeWorkerProcessError(
                error_code="runtime_worker_process_invalid_result",
                message="runtime worker process returned an invalid result envelope",
            )
        result = dict(response["result"])
        result["hard_worker_process"] = {
            "active": True,
            "worker_pid": int(response.get("pid") or self.worker_pid),
            "parent_pid": os.getpid(),
            "start_method": self.process_start_method,
            "replaceable": True,
            "cancel_grace_seconds": self._cancel_grace_seconds,
        }
        return result

    def close(self) -> None:
        if self._closed and not self._process.is_alive():
            return
        self._closed = True
        self._cancel_event.set()
        if self._process.is_alive():
            try:
                self._connection.send({"op": "close"})
            except (BrokenPipeError, EOFError, OSError):
                pass
            if self._connection.poll(self._cancel_grace_seconds):
                try:
                    self._recv_message(error_code="runtime_worker_process_close_failed")
                except RuntimeWorkerProcessError:
                    pass
                self._process.join(timeout=self._cancel_grace_seconds)
        if self._process.is_alive():
            self._terminate_child(reason="worker_close")
        try:
            self._connection.close()
        except OSError:
            pass
