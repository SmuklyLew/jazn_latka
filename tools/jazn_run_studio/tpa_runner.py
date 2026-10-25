"""Bounded, operator-triggered TPA *subchecks* for Studio Jaźni.

No check here is a full local acceptance gate. In particular, an automated
PASS does not mark a manual acceptance record as passed. The allowlist covers
isolated regression tests only; real daemons, model turns, EXE and MEMORY remain
separate operator gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from latka_jazn.tools.application_shell.operator_paths import operator_file
from .core import Redactor
from .local_acceptance import scope_version

# Keep test filenames literal: never accept arbitrary shell commands or node IDs.
AUTOMATED_CASES: dict[str, tuple[str, ...]] = {
    "smoke-isolation": ("tests/test_package_smoke_workspace_isolation.py",),
    "config-persistence": ("tests/test_jazn_system_root_config.py",),
    "ui-accessibility": ("tests/test_jazn_run_studio_workbench_qt.py",),
}
BASELINE_FILES = (
    "tests/test_jazn_run_studio_local_acceptance.py",
    "tests/test_jazn_run_studio_12_manual_studio_gates.py",
)
MAX_OUTPUT = 48_000
TIMEOUT_MS = 120_000


def allowed_files(root: Path, case_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve only reviewed regression files within the SYSTEM checkout."""
    if not case_ids or any(case_id not in AUTOMATED_CASES for case_id in case_ids):
        raise ValueError("TPA: wybrany scenariusz wymaga ręcznego odbioru")
    files = tuple(dict.fromkeys(path for case_id in case_ids for path in AUTOMATED_CASES[case_id]))
    canonical = root.resolve()
    for name in files:
        candidate = root / name
        if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(canonical):
            raise ValueError("TPA: plik testu nie jest dostępny w zweryfikowanym SYSTEM")
    return files


def isolated_environment(folder: Path) -> QProcessEnvironment:
    """Never inherit Jaźń runtime/memory bindings into a TPA subprocess."""
    env = QProcessEnvironment.systemEnvironment()
    for key in env.keys():
        upper = key.upper()
        if (upper.startswith("JAZN_")
                or any(term in upper for term in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL"))):
            env.remove(key)
    env.insert("JAZN_RUNTIME_WORKSPACE_DIR", str(folder / "runtime"))
    env.insert("JAZN_OPERATOR_STATE_ROOT", str(folder / "operator"))
    env.insert("JAZN_MEMORY_MODE", "off")
    env.insert("PYTHONUTF8", "1")
    env.insert("PYTHONDONTWRITEBYTECODE", "1")
    env.insert("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        env.insert("QT_QPA_PLATFORM", "offscreen")
    return env


class SafeTPARunner(QObject):
    """Runs curated pytest subchecks asynchronously; never manipulates a daemon."""

    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, root: Path, python: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.root = root
        self.python = python
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timed_out)
        self.active = False
        self.reason = ""
        self.started = ""
        self.case_ids: tuple[str, ...] = ()
        self.files: tuple[str, ...] = ()
        self.output = ""
        self.tmp: tempfile.TemporaryDirectory[str] | None = None
        self.redactor = Redactor()

    def start_cases(self, case_ids: tuple[str, ...]) -> None:
        if self.active:
            raise ValueError("TPA: poprzedni przebieg jeszcze trwa")
        self.files = allowed_files(self.root, case_ids)
        selected = Path(self.python)
        if not selected.is_absolute() or not selected.is_file():
            raise ValueError("TPA: skonfiguruj istniejący interpreter Python")
        self.case_ids = case_ids
        self.reason = ""
        self.output = ""
        self.started = datetime.now(timezone.utc).isoformat()
        self.tmp = tempfile.TemporaryDirectory(prefix="jazn_tpa_")
        isolated = Path(self.tmp.name)
        self.process.setWorkingDirectory(str(self.root.resolve()))
        self.process.setProcessEnvironment(isolated_environment(isolated))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.active = True
        self.progress.emit("TPA: uruchamianie izolowanych testów regresyjnych…")
        self.timer.start(TIMEOUT_MS)
        self.process.start(str(selected), [
            "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--tb=short", "--basetemp", str(isolated / "pytest"),
            *self.files,
        ])

    def stop(self) -> None:
        if not self.active:
            return
        self.reason = self.reason or "cancelled"
        self.progress.emit("TPA: anulowanie własnego procesu testowego")
        self.timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            QTimer.singleShot(2_000, self._force_stop)

    def _force_stop(self) -> None:
        if self.active and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _timed_out(self) -> None:
        self.reason = "timeout"
        self.stop()

    def _append(self, data: bytes) -> None:
        if not data:
            return
        line = self.redactor.text(data.decode("utf-8", "replace"))
        if len(self.output) < MAX_OUTPUT:
            self.output += line[:MAX_OUTPUT - len(self.output)]
        self.progress.emit(line[-1200:])

    def _read_stdout(self) -> None:
        self._append(self.process.readAllStandardOutput().data())

    def _read_stderr(self) -> None:
        self._append(self.process.readAllStandardError().data())

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self.active and error == QProcess.ProcessError.FailedToStart:
            self.reason = "process_start_failed"
            self._complete(-1, False)

    def _finished(self, code: int, exit_status: QProcess.ExitStatus) -> None:
        if not self.active:
            return
        self._read_stdout()
        self._read_stderr()
        normal = exit_status == QProcess.ExitStatus.NormalExit
        self._complete(code, normal)

    def _complete(self, code: int, normal: bool) -> None:
        if not self.active:
            return
        self.active = False
        self.timer.stop()
        status = ("BLOCKED" if self.reason in {"timeout", "cancelled", "process_start_failed"}
                  else "PASS" if normal and code == 0 else "FAIL")
        report: dict[str, Any] = {
            "schema_version": "jazn_tpa_automatic_subcheck/v1",
            "version_scope": scope_version(self.root),
            "started_utc": self.started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "case_ids": list(self.case_ids),
            "test_files": list(self.files),
            "status": status,
            "exit_code": code,
            "reason": self.reason or ("tests_failed" if status == "FAIL" else "completed"),
            "manual_gate_automatically_passed": False,
            "production_resources_intentionally_touched": False,
            "output_redacted_excerpt": self.output[:MAX_OUTPUT],
        }
        try:
            path = operator_file("jazn_studio_tpa", self.root, "run-" + uuid.uuid4().hex + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            report["evidence_path"] = str(path)
        except (OSError, ValueError):
            report["evidence_path"] = ""
            report["persistence_error"] = "operator_evidence_write_failed"
        finally:
            if self.tmp is not None:
                self.tmp.cleanup()
                self.tmp = None
        self.completed.emit(report)
