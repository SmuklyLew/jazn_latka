"""One asynchronous TPA queue; isolated subprocesses and durable run evidence."""
from __future__ import annotations

import codecs
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from latka_jazn.core.acceptance_layout import resolve_acceptance_layout
from .core import Redactor
from .external import environment
from .tpa_catalog import LIVE_CASES, execution_map, scenario
from .tpa_reports import RunStore, junit_result, redact, safe_child, utc
from .tpa_paths import TOKEN_ENV, issue_staging

TIMEOUT_MS = 180_000
MAX_OUTPUT = 4 * 1024 * 1024
PROBE_SCRIPT = '''import importlib, json, sys, subprocess, os
result = {"python": sys.executable, "version": list(sys.version_info[:3]), "imports": {}, "source": {}}
for name in ("pytest", "PySide6", "tkinter", "prompt_toolkit", "pydantic"):
    try:
        importlib.import_module(name)
        result["imports"][name] = {"ok": True}
    except Exception as exc:
        result["imports"][name] = {"ok": False, "error": type(exc).__name__}
root = os.path.abspath(sys.argv[1])
if os.path.exists(os.path.join(root, ".git")):
    for name, args in (("git_sha", ["rev-parse", "HEAD"]), ("git_dirty", ["status", "--porcelain"])):
        try:
            p = subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            result["source"][name] = (bool(p.stdout) if name == "git_dirty" else p.stdout.decode().strip()) if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            result["source"][name] = None
elif os.path.isfile(os.path.join(root, "PACKAGE_INTEGRITY_MANIFEST.json")):
    # This runs only in the isolated preflight process, never on the Qt thread.
    try:
        sys.path.insert(0, root)
        from tools.jazn_run_studio.tpa_release_identity import verified_release_source
        result["source"].update(verified_release_source(root))
    except Exception as exc:
        result["source"]["release_verified"] = False
        result["source"]["release_reason"] = type(exc).__name__
print(json.dumps(result))
'''


def isolated_environment(folder: Path, root: Path) -> QProcessEnvironment:
    layout = resolve_acceptance_layout(root, base=folder)
    values = environment()
    for key in list(values):
        upper = key.upper()
        if upper.startswith(("JAZN_", "PYTHONPATH", "PYTEST_")) or any(s in upper for s in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")):
            values.pop(key)
    values.update(JAZN_RUNTIME_WORKSPACE_DIR=str(layout.runtime), JAZN_OPERATOR_STATE_ROOT=str(layout.operator),
                  JAZN_MEMORY_ROOT=str(layout.memory), JAZN_MEMORY_MODE="off",
                  JAZN_NETWORK_TIME_FIRST="0", JAZN_NETWORK_TIME_IN_TURN="0",
                  PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
                  PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", QT_QPA_PLATFORM="offscreen")
    env = QProcessEnvironment()
    for key, value in values.items():
        env.insert(key, value)
    return env


def checked_files(root: Path, case_id: str) -> tuple[str, ...]:
    names = tuple(scenario(case_id)["files"])
    for name in names:
        raw = root / name
        if not raw.is_file() or not raw.resolve().is_relative_to(root.resolve()):
            raise ValueError("Brak wymaganego pliku testu: " + name)
        for part in (raw, *raw.parents):
            if part == root.parent:
                break
            if part.is_symlink() or part.is_junction():
                raise ValueError("Niezaufana ścieżka testu: " + name)
    return names


def readiness(root: Path, probe: dict) -> dict[str, dict]:
    checks = {}
    for case in execution_map():
        reasons = []
        if not probe.get("ok"):
            reasons.append(probe.get("reason", "Nie udało się uruchomić wybranego Pythona."))
        elif tuple(probe.get("version", [])) < (3, 12):
            reasons.append("Wymagany Python 3.12 lub nowszy.")
        for name in case["requirements"]:
            if probe.get("ok") and probe.get("imports", {}).get(name, {}).get("ok") is not True:
                reasons.append("Wybrany Python nie importuje " + name + ". Wybierz interpreter lub przygotuj profil w Studio Zależności.")
        try:
            checked_files(root, case["id"])
        except ValueError as exc:
            reasons.append(str(exc))
        checks[case["id"]] = {"ready": not reasons, "reason": " ".join(reasons) or "Gotowy podtest regresyjny; usługi nie są wymagane."}
    return checks


class TPARunner(QObject):
    progress = Signal(str)
    completed = Signal(object)
    changed = Signal()
    prepared = Signal(object)

    def __init__(self, root: Path, python: str, parent: QObject | None = None):
        super().__init__(parent)
        self.root, self.python = root.resolve(), python
        self.store = RunStore(self.root)
        self.active = False
        self.phase = ""
        self.report: dict[str, Any] | None = None
        self.probe: dict = {}
        self.availability: dict[str, dict] = {}
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.timeout_ms = TIMEOUT_MS
        self.temp: tempfile.TemporaryDirectory[str] | None = None
        self.index = -1
        self.reason = ""
        self.buffer = ""
        self.pending_line = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.started = 0.0
        self.redactor = Redactor()
        self.persistence_error = ""
        self._next_after_probe = False
        self.execution = "regression"
        self.model = ""
        self.live_result: dict = {}

    def _save(self) -> bool:
        if self.report is None:
            return True
        try:
            self.store.save(self.report)
            return True
        except (OSError, ValueError) as exc:
            self.persistence_error = "Nie zapisano raportu: " + self.redactor.text(type(exc).__name__)
            self.report["persistence_error"] = self.persistence_error
            self.progress.emit(self.persistence_error)
            self.changed.emit()
            return False

    def check_ready(self) -> None:
        if self.active:
            raise ValueError("Poprzednia kontrola lub przebieg nadal trwa")
        self.active = True
        self._next_after_probe = False
        self._probe()

    def start_selection(self, case_ids: tuple[str, ...], *, execution: str = "regression", model: str = "") -> None:
        if self.active:
            raise ValueError("Poprzedni przebieg nadal trwa")
        if execution not in {"regression", "live", "sandbox"} or (execution == "live" and set(case_ids) - LIVE_CASES):
            raise ValueError("Wybierz obsługiwany odbiór izolowany")
        self.execution, self.model = execution, model
        # The run exists even when preflight blocks every selected test.
        self.report = self.store.create(case_ids, self.python, {"memory_mode": "off", "qt_platform": "offscreen"})
        self.report["execution"] = execution
        self.persistence_error = ""
        self.index = -1
        self.active = True
        self._next_after_probe = True
        self._probe()

    def _probe(self) -> None:
        self.phase, self.reason, self.buffer = "preflight", "", ""
        self.pending_line = ""
        self.decoder.reset()
        self.probe = {}
        self.availability = {}
        selected = Path(self.python)
        if not selected.is_absolute() or not selected.is_file():
            self._probe_done({"ok": False, "reason": "Wybierz istniejący interpreter Python przez ścieżkę absolutną."})
            return
        try:
            self.temp = tempfile.TemporaryDirectory(prefix="jazn-tpa-")
            self.process.setProcessEnvironment(isolated_environment(Path(self.temp.name), self.root))
        except (OSError, ValueError) as exc:
            self._probe_done({"ok": False, "reason": "Niepoprawna izolacja ścieżek: " + type(exc).__name__})
            return
        self.process.setWorkingDirectory(str(self.root))
        self.progress.emit("Sprawdzam rzeczywiste importy w wybranym interpreterze…")
        self.timer.start(180_000 if not (self.root / ".git").exists() else 20_000)
        self.process.start(self.python, ["-I", "-X", "utf8", "-c", PROBE_SCRIPT, str(self.root)])
        self.changed.emit()

    def _probe_done(self, probe: dict) -> None:
        self.timer.stop()
        self.probe = probe
        self.availability = readiness(self.root, probe)
        if self.report is not None and self._next_after_probe:
            self.report["environment"].update(probe)
            self.report["source"].update(probe.get("source", {}))
            if not self._save():
                self.stop()
        self.prepared.emit(probe)
        if self._next_after_probe:
            QTimer.singleShot(0, self._next)
        else:
            self.active = False
            self._cleanup()
            self.changed.emit()

    def _next(self) -> None:
        if not self.active or self.report is None:
            return
        self.index += 1
        if self.index >= len(self.report["results"]):
            self._complete()
            return
        row = self.report["results"][self.index]
        if self.reason == "cancelled" or self.persistence_error:
            row.update(status="CANCELLED", reason="Anulowano przed uruchomieniem.")
            self._save()
            QTimer.singleShot(0, self._next)
            return
        available = self.availability[row["case_id"]]
        if self.execution in {"live", "sandbox"}:
            available = {"ready": self.probe.get("ok") is True, "reason": self.probe.get("reason", "Wybrany interpreter jest niedostępny.")}
            if self.execution == "sandbox" and self.probe.get("imports", {}).get("PySide6", {}).get("ok") is not True:
                available = {"ready": False, "reason": "Wybrany Python nie importuje PySide6; przygotuj profil run-studio."}
            if self.execution == "live" and not self.model and row["case_id"] != "gui-daemon":
                available = {"ready": False, "reason": "Wybierz lokalny model Ollama do rzeczywistego odbioru; niczego nie pobrano."}
        if not available["ready"]:
            row.update(status="BLOCKED", reason=available["reason"], next_step="Wybierz interpreter, przygotuj zależności lub przywróć wymagane pliki; ponów gotowość.")
            self._save()
            self.changed.emit()
            QTimer.singleShot(0, self._next)
            return
        self.phase, self.reason, self.buffer, self.pending_line = "tests", "", "", ""
        self.decoder.reset()
        self.started = time.monotonic()
        assert self.temp is not None
        if self.execution in {"live", "sandbox"}:
            self.phase, self.live_result = "live", {}
            try:
                self.live_folder, token = issue_staging(self.root, self.store.folder(self.report["run_id"]), row["case_id"])
            except (OSError, ValueError) as exc:
                row.update(status="BLOCKED", reason="Odmowa przygotowania katalogu TPA: " + self.redactor.text(str(exc)))
                self._save()
                self.changed.emit()
                QTimer.singleShot(0, self._next)
                return
            child_env = self.process.processEnvironment()
            child_env.insert(TOKEN_ENV, token)
            self.process.setProcessEnvironment(child_env)
            self.log_name = row["case_id"] + ".log"
            args = ["-X", "utf8", "-m", "tools.jazn_run_studio.tpa_live", "--root", str(self.root),
                    "--folder", str(self.live_folder), "--run-id", self.report["run_id"],
                    "--case", row["case_id"], "--model", self.model]
            if self.execution == "sandbox":
                args.append("--sandbox")
            row.update(status="RUNNING", reason="Rzeczywisty odbiór w nowym stagingu; nie dotyka aktywnego daemona.",
                       started_utc=utc(), command=[self.python, *args],
                       coverage="isolated_studio_workflow" if self.execution == "sandbox" else "real_runtime_acceptance")
            if not self._save():
                self.stop()
                QTimer.singleShot(0, self._next)
                return
            self.timer.start(900_000 if self.execution == "sandbox" else 480_000)
            self.process.start(self.python, args)
            self.changed.emit()
            return
        self.junit = Path(self.temp.name) / (str(self.index) + ".xml")
        self.log_name = row["case_id"] + ".log"
        files = checked_files(self.root, row["case_id"])
        args = ["-X", "utf8", "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", "--tb=short",
                "--junitxml", str(self.junit), "--basetemp", str(Path(self.temp.name) / ("pytest-" + str(self.index))), *files]
        row.update(status="RUNNING", reason="Testy pracują; wynik nie jest jeszcze znany.", started_utc=utc(), command=[self.python, *args])
        if not self._save():
            self.stop()
            QTimer.singleShot(0, self._next)
            return
        self.progress.emit("Uruchamiam: " + row["title"])
        self.timer.start(self.timeout_ms)
        self.process.start(self.python, args)
        self.changed.emit()

    def _read(self) -> None:
        text = self.decoder.decode(bytes(self.process.readAllStandardOutput().data()))
        self.pending_line += text
        if len(self.pending_line) + len(self.buffer) > MAX_OUTPUT:
            self.reason = "output_limit"
            self.stop()
            return
        # Redact complete lines, so split token assignments cannot leak to disk/UI.
        while "\n" in self.pending_line:
            line, self.pending_line = self.pending_line.split("\n", 1)
            clean = self.redactor.text(line.rstrip("\r")) + "\n"
            self.buffer += clean
            if self.phase in {"live", "cleanup"}:
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict) and payload.get("event") == "result":
                        if self.phase == "cleanup":
                            self.cleanup_result = redact(payload, self.redactor)
                        else:
                            self.live_result = redact(payload, self.redactor)
                    elif isinstance(payload, dict) and payload.get("event") == "accepted_final":
                        original = str(payload.get("text", ""))
                        displayed = self.redactor.text(original)
                        self.progress.emit("Zaakceptowana odpowiedź testowa:\n" + displayed)
                        # A redacted display cannot acknowledge display_exact of the original.
                        ack = json.dumps({"displayed_request_id": payload.get("request_id") if displayed == original else None}) + "\n"
                        self.process.write(ack.encode("utf-8"))
                except ValueError:
                    pass  # Ordinary progress lines are retained as redacted logs.
            if self.phase != "preflight":
                self.progress.emit(clean.rstrip())

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if not self.active:
            return
        self.timer.stop()
        self._read()
        if self.pending_line:
            self.buffer += self.redactor.text(self.pending_line)
            self.pending_line = ""
        if self.phase == "preflight":
            try:
                probe = json.loads(self.buffer)
                if code != 0 or not isinstance(probe, dict) or not isinstance(probe.get("imports"), dict):
                    raise ValueError("probe")
                probe["ok"] = True
            except (ValueError, TypeError):
                probe = {"ok": False, "reason": "Kontrola Pythona nie dała poprawnej odpowiedzi: " + (self.reason or "błąd importu/startu")}
            self._probe_done(probe)
            return
        if self.phase == "live":
            assert self.report is not None
            self.live_exit_code = code
            if self.live_result.get("pre_start_rejected") is True:
                self.cleanup_result = {"ok": True, "reason": "daemon_not_started"}
                self._live_done(0)
                return
            self.phase, self.cleanup_result = "cleanup", {}
            self.progress.emit("Weryfikuję sprzątnięcie wyłącznie własnego daemona testowego…")
            self.timer.start(100_000)
            self.process.start(self.python, ["-X", "utf8", "-m", "tools.jazn_run_studio.tpa_live", "--root", str(self.root),
                                             "--folder", str(self.live_folder), "--run-id", self.report["run_id"],
                                             "--case", self.report["results"][self.index]["case_id"], "--cleanup"])
            return
        if self.phase == "cleanup":
            self._live_done(code)
            return
        self._test_done(code, status == QProcess.ExitStatus.NormalExit)

    def _live_done(self, code: int) -> None:
        assert self.report is not None
        row = self.report["results"][self.index]
        result = self.live_result
        status = result.get("status", "INTERRUPTED")
        if status not in {"PASS", "FAIL", "BLOCKED", "TIMEOUT", "CANCELLED", "INTERRUPTED"}:
            status = "FAIL"
        if self.reason in {"cancelled", "timeout"}:
            status = "CANCELLED" if self.reason == "cancelled" else "TIMEOUT"
        reason = result.get("reason", "Proces odbioru zakończył się bez poprawnego dowodu.")
        if status == "PASS" and getattr(self, "live_exit_code", -1) != 0:
            status, reason = "FAIL", "Proces odbioru zakończył się niezerowym kodem wyjścia; wynik PASS nie jest wiarygodny."
        if code or self.cleanup_result.get("ok") is not True:
            status = "BLOCKED"
            reason += " Nie potwierdzono bezpiecznego sprzątnięcia. Zachowano własny staging i dowód właściciela."
        row.update(status=status, reason=reason, exit_code=getattr(self, "live_exit_code", -1), cleanup_exit_code=code,
                   duration_seconds=round(time.monotonic() - self.started, 3),
                   finished_utc=utc(), full_gate="NOT_RUN", log=self.log_name)
        folder = self.store.folder(self.report["run_id"])
        try:
            safe_child(folder, self.log_name).write_text(self.buffer, encoding="utf-8")
            name = row["case_id"] + ".live.json"
            safe_child(folder, name).write_text(json.dumps({"result": result, "cleanup": self.cleanup_result}, ensure_ascii=False, indent=2), encoding="utf-8")
            self.report["artifacts"].extend([name, self.log_name])
        except (OSError, ValueError):
            self.persistence_error = "Nie zapisano dowodów odbioru izolowanego."
            row.update(status="BLOCKED", full_gate="NOT_RUN", reason=self.persistence_error)
        self._save()
        self.changed.emit()
        QTimer.singleShot(0, self._next)

    def _test_done(self, code: int, normal: bool) -> None:
        assert self.report is not None
        row = self.report["results"][self.index]
        try:
            result, xml = junit_result(self.junit, code, self.redactor)
        except (OSError, ValueError) as exc:
            result, xml = {"status": "FAIL", "reason": "Niepoprawny JUnit: " + type(exc).__name__}, b""
        if self.reason or not normal:
            result.update(status={"cancelled": "CANCELLED", "timeout": "TIMEOUT", "process_start_failed": "BLOCKED"}.get(self.reason, "INTERRUPTED"),
                          reason={"cancelled": "Anulowano własny proces testowy.", "timeout": "Przekroczono limit czasu.",
                                  "process_start_failed": "Nie udało się uruchomić procesu."}.get(self.reason, "Proces przerwany lub przekroczony limit wyjścia; brak pełnego dowodu."))
        row.update(result, exit_code=code, duration_seconds=round(time.monotonic() - self.started, 3), finished_utc=utc(), log=self.log_name)
        try:
            folder = self.store.folder(self.report["run_id"])
            safe_child(folder, self.log_name).write_text(self.buffer, encoding="utf-8")
            self.report["artifacts"].append(self.log_name)
            if xml:
                name = row["case_id"] + ".xml"
                safe_child(folder, name).write_bytes(xml)
                row["junit"] = name
                self.report["artifacts"].append(name)
        except (OSError, ValueError):
            self.persistence_error = "Nie zapisano logu/JUnit tego przebiegu. Wynik nie jest trwałym dowodem."
            row.update(status="BLOCKED", reason=self.persistence_error)
        self._save()
        self.changed.emit()
        QTimer.singleShot(0, self._next)

    def _error(self, error: QProcess.ProcessError) -> None:
        if self.active and error == QProcess.ProcessError.FailedToStart:
            self.reason = "process_start_failed"
            if self.phase == "preflight":
                self._probe_done({"ok": False, "reason": "Nie można uruchomić wybranego Pythona."})
            elif self.phase in {"live", "cleanup"}:
                self.cleanup_result = {}
                self._live_done(-1)
            else:
                self._test_done(-1, False)

    def _timeout(self) -> None:
        if self.phase == "cleanup":
            self.reason = "cleanup_timeout"
            self.process.kill()
            return
        self.reason = self.reason or "timeout"
        self.stop()

    def stop(self) -> None:
        if not self.active:
            return
        self.reason = self.reason or "cancelled"
        if self.phase == "cleanup":
            return
        self.timer.stop()
        if self.phase == "live":
            safe_child(self.live_folder, "cancel.flag").write_text("cancel", encoding="utf-8")
            process_pid = self.process.processId()
            QTimer.singleShot(15_000, lambda: self.process.kill() if self.active and self.phase == "live" and self.process.processId() == process_pid else None)
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            process_pid = self.process.processId()
            QTimer.singleShot(2000, lambda: self.process.kill() if self.active and self.process.processId() == process_pid and self.process.state() != QProcess.ProcessState.NotRunning else None)
        elif self.phase != "preflight":
            QTimer.singleShot(0, self._next)

    def _cleanup(self) -> None:
        if self.temp is not None:
            self.temp.cleanup()
            self.temp = None

    def _complete(self) -> None:
        assert self.report is not None
        self.active = False
        self.timer.stop()
        self.report["finished_utc"] = utc()
        self._save()
        self._cleanup()
        self.changed.emit()
        self.completed.emit(self.report)
