from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from .core import EVENT_MARKER, UI_STATUS


class PytestRun:
    """Run pytest outside the UI event loop and emit structured progress events."""

    def __init__(
        self,
        root: Path,
        nodeids: list[str] | None = None,
        *,
        timeout: int = 1800,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.nodeids = list(nodeids or [])
        self.timeout = max(1, int(timeout))
        self.on_event = on_event or (lambda event: None)
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.started = 0.0
        self.cancelled = False
        self.timed_out = False
        self.done = threading.Event()
        self.result: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._output: list[str] = []
        self._output_chars = 0
        self._total = 0
        self._completed = 0
        self._counts = {key: 0 for key in ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS")}

    def command(self) -> list[str]:
        cmd = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "-q",
            "-p",
            "jazn_tests_studio.progress_plugin",
            "--tb=short",
            "-ra",
            "--color=no",
        ]
        cmd.extend(self.nodeids or ["tests", "--ignore=tests/archive"])
        return cmd

    def start(self) -> "PytestRun":
        if self.thread is not None:
            raise RuntimeError("run already started")
        self.thread = threading.Thread(target=self._worker, name="jazn-tests-studio-pytest", daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.cancelled = True
        with self._lock:
            proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def wait(self, timeout: float | None = None) -> dict[str, Any]:
        if not self.done.wait(timeout):
            raise TimeoutError("pytest run did not finish")
        assert self.result is not None
        return self.result

    def _emit(self, event: dict[str, Any]) -> None:
        try:
            self.on_event(event)
        except Exception:
            pass

    def _parse_line(self, line: str) -> bool:
        marker_at = line.find(EVENT_MARKER)
        if marker_at < 0:
            return False
        raw = line[marker_at + len(EVENT_MARKER) :].strip()
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return False
        kind = event.get("type")
        if kind == "collection":
            self._total = int(event.get("total") or 0)
        elif kind == "result":
            status = str(event.get("status") or "ERROR")
            self._completed += 1
            if status not in self._counts:
                status = "ERROR"
                event["status"] = status
            self._counts[status] += 1
            event["completed"] = self._completed
            event["total"] = self._total
            event["percent"] = round((self._completed / self._total * 100.0), 1) if self._total else 0.0
        self._emit(event)
        return True

    def _timeout_process(self) -> None:
        if self.done.is_set():
            return
        self.timed_out = True
        self.stop()

    def _append_output(self, line: str) -> None:
        self._output.append(line)
        self._output_chars += len(line)
        if self._output_chars > 500_000:
            self._output = self._output[-2500:]
            self._output_chars = sum(map(len, self._output))

    def _worker(self) -> None:
        self.started = time.monotonic()
        cmd = self.command()
        env = os.environ.copy()
        tools_path = str(self.root / "tools")
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = tools_path + (os.pathsep + previous if previous else "")
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform.startswith("win") else 0
        timer = threading.Timer(self.timeout, self._timeout_process)
        timer.daemon = True
        returncode: int | None = None
        launch_error: str | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
                creationflags=creationflags,
            )
            with self._lock:
                self.process = proc
            self._emit({"type": "process_start", "pid": proc.pid, "command": cmd})
            timer.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                if not self._parse_line(line):
                    self._append_output(line)
                    self._emit({"type": "output", "text": line})
            returncode = proc.wait()
        except Exception as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
            self._emit({"type": "output", "text": launch_error + "\n"})
        finally:
            timer.cancel()
            with self._lock:
                self.process = None

        duration = round(time.monotonic() - self.started, 3)
        if self.timed_out:
            outcome = "timeout"
        elif self.cancelled:
            outcome = "cancelled"
        elif launch_error is not None:
            outcome = "error"
        elif returncode == 0:
            outcome = "passed"
        elif returncode == 1:
            outcome = "failed"
        else:
            outcome = "error"
        self.result = {
            "ok": returncode == 0 and not self.timed_out and not self.cancelled,
            "outcome": outcome,
            "returncode": returncode,
            "duration_seconds": duration,
            "command": cmd,
            "total": self._total,
            "completed": self._completed,
            "counts": dict(self._counts),
            "output": "".join(self._output)[-250000:],
        }
        if launch_error:
            self.result["error"] = launch_error
        self._emit({"type": "finished", **self.result})
        self.done.set()


def run_pytest(
    root: Path,
    nodeids: list[str] | None = None,
    *,
    timeout: int = 1800,
    live: bool = False,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def console_event(event: dict[str, Any]) -> None:
        if on_event is not None:
            on_event(event)
        if not live:
            return
        kind = event.get("type")
        if kind == "collection":
            print(f"[COLLECTED] {event.get('total', 0)} testów", flush=True)
        elif kind == "start":
            print(f"[RUN] {event.get('nodeid', '')}", flush=True)
        elif kind == "result":
            status = UI_STATUS.get(str(event.get("status")), str(event.get("status")))
            print(
                f"[{status}] {event.get('nodeid', '')} "
                f"({event.get('completed', 0)}/{event.get('total', 0)}; {event.get('percent', 0)}%)",
                flush=True,
            )
        elif kind == "output":
            text = str(event.get("text") or "")
            if "FAILURES" in text or "ERRORS" in text or text.startswith("FAILED ") or text.startswith("ERROR "):
                print(text, end="", flush=True)

    run = PytestRun(root, nodeids, timeout=timeout, on_event=console_event).start()
    try:
        return run.wait(timeout + 30)
    except KeyboardInterrupt:
        run.stop()
        try:
            run.wait(10)
        except TimeoutError:
            pass
        raise
