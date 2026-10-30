"""Qt orchestration of the existing TPARunner; no second runtime lifecycle."""
from __future__ import annotations

from pathlib import Path
import os
from PySide6.QtCore import QObject, QTimer, Signal

from .tpa_engine import TPARunner
from .tpa_execution_plan import PlanStore, blocked_dependencies, build_plan
from .tpa_reports import process_alive, utc
from .tpa_current_state import evidence_errors


class TPAPlanRunner(QObject):
    changed = Signal()
    completed = Signal(object)
    error = Signal(str)

    def __init__(self, runner: TPARunner, parent: QObject | None = None):
        super().__init__(parent)
        self.runner = runner
        self.store = PlanStore(runner.store)
        self.plan: dict | None = None
        self.active = False
        self.cancelled = False
        self.runner.completed.connect(self._completed)

    def start(self, case_ids: tuple[str, ...], *, source: dict, model: str = "",
              regression_only: bool = False) -> None:
        if self.active or self.runner.active:
            raise ValueError("Poprzedni przebieg lub plan nadal trwa")
        self.plan = build_plan(case_ids, source, model, include_live=not regression_only)
        self.plan["status"] = "RUNNING"
        self.store.save(self.plan)  # No test starts if checkpoint persistence fails.
        self.active, self.cancelled = True, False
        self._advance()

    def checkpoint(self) -> None:
        if self.plan is None:
            raise ValueError("Najpierw rozpocznij lub wybierz plan")
        self.store.save(self.plan)

    def resume(self, plan_id: str) -> None:
        if self.active or self.runner.active:
            raise ValueError("Poprzedni przebieg lub plan nadal trwa")
        plan = self.store.load(plan_id)
        if plan.get("finished_utc"):
            raise ValueError("Plan jest zakończony; nowe próby wymagają nowego planu")
        pid = plan.get("owner_pid")
        if isinstance(pid, int) and pid > 0 and pid != os.getpid() and process_alive(pid):
            raise ValueError("Nie potwierdzono zakończenia poprzedniego właściciela planu")
        # Never send a fresh request to replace an unresolved live turn.
        for node in plan["tasks"]:
            if node["status"] == "PASS":
                prior = self.runner.store.load(node["run_id"]) if node.get("run_id") else None
                row = next((r for r in prior["results"] if r["case_id"] == node["case_id"]), {}) if prior else {}
                if not prior or row.get("status") != "PASS" or prior.get("execution", "regression") != node["execution"] or evidence_errors(self.runner.store, prior, row):
                    node.update(status="BLOCKED", reason="Checkpoint PASS nie ma kompletnego potwierdzenia w zapisanym przebiegu.")
            if node["status"] == "RUNNING":
                prior = self.runner.store.load(node["run_id"]) if node.get("run_id") else None
                row = next((r for r in prior["results"] if r["case_id"] == node["case_id"]), {}) if prior else {}
                if prior and prior.get("finished_utc") and row.get("status") not in {"RUNNING", "QUEUED"}:
                    node.update(status=row.get("status", "INTERRUPTED"), reason=row.get("reason", ""))
                else:
                    node.update(status="INTERRUPTED", reason="Brak rozstrzygniętego dowodu; nie wysłano nowej tury. Sprawdź zapisany run_id i oryginalny request_id.")
                if prior and prior.get("environment", {}).get("execution_root"):
                    plan["source_copy"] = prior["environment"]["execution_root"]
                    plan["source_identity"] = prior["source"]
        plan.update(owner_pid=os.getpid(), status="RUNNING")
        self.plan, self.active, self.cancelled = plan, True, False
        self.store.save(plan)
        self._advance()

    def stop(self) -> None:
        self.cancelled = True
        if self.runner.active:
            self.runner.stop()
        elif self.active:
            self._advance()

    def _advance(self) -> None:
        try:
            self._advance_checked()
        except (OSError, ValueError, RuntimeError) as exc:
            self.active = False
            self.runner.stop()
            self.error.emit("Plan zatrzymany; zachowano checkpoint: " + self.runner.redactor.text(str(exc)))
            self.changed.emit()

    def _advance_checked(self) -> None:
        if not self.active or self.plan is None:
            return
        plan = self.plan
        blocked_dependencies(plan)
        if self.cancelled:
            for node in plan["tasks"]:
                if node["status"] == "QUEUED":
                    node.update(status="CANCELLED", reason="Operator zatrzymał plan przed wykonaniem.")
        queued = [n for n in plan["tasks"] if n["status"] == "QUEUED"]
        if not queued:
            plan.update(status="COMPLETED", finished_utc=utc())
            self.store.save(plan)
            self.active = False
            self.changed.emit()
            self.completed.emit(plan)
            return
        node = queued[0]
        if node["execution"] == "live" and not plan["model"]:
            node.update(status="BLOCKED", reason="Brak wybranego lokalnego modelu Ollama; nie uruchomiono daemona.")
            self.store.save(plan)
            QTimer.singleShot(0, self._advance)
            return
        batch = [n for n in queued if n["execution"] == "regression"] if node["execution"] == "regression" else [node]
        if node["execution"] == "live":
            statuses = {n["id"]: n["status"] for n in plan["tasks"]}
            if any(statuses[key] != "PASS" for key in node["depends_on"]):
                raise ValueError("Zależności kroku nie zostały rozstrzygnięte")
        for task in batch:
            task.update(status="RUNNING", started_utc=utc())
        self.store.save(plan)
        source = plan["source_request"]
        if plan.get("source_copy"):
            pinned = Path(plan["source_copy"])
            if not pinned.is_absolute() or not pinned.resolve().is_relative_to(self.runner.store.base.resolve()):
                raise ValueError("Przypięte źródło nie należy do zapisanych przebiegów")
            # The existing resolver verifies and copies the immutable pinned HEAD
            # again. A moving remote branch cannot change a later live step.
            source = {"kind": "local", "value": str(pinned)}
        self.runner.start_selection(tuple(n["case_id"] for n in batch), execution=node["execution"], model=plan["model"],
                                    source_kind=source.get("kind", "master"), source_value=source.get("value", ""))
        assert self.runner.report is not None
        for task in batch:
            task["run_id"] = self.runner.report["run_id"]
        self.store.save(plan)
        self.changed.emit()

    def _completed(self, report: object) -> None:
        if not self.active or self.plan is None or not isinstance(report, dict):
            return
        try:
            for node in self.plan["tasks"]:
                if node.get("run_id") == report["run_id"] and node["status"] == "RUNNING":
                    row = next(r for r in report["results"] if r["case_id"] == node["case_id"])
                    node.update(status=row["status"], reason=row.get("reason", ""), finished_utc=utc())
                    if node["status"] == "PASS" and evidence_errors(self.runner.store, report, row):
                        node.update(status="BLOCKED", reason="Brak kompletnego dowodu wykonania wymaganego kroku.")
            if report.get("environment", {}).get("execution_root"):
                if self.plan.get("source_identity") and report["source"].get("git_sha") != self.plan["source_identity"].get("git_sha"):
                    raise ValueError("Źródło zmieniło SHA w trakcie planu")
                self.plan["source_copy"] = report["environment"]["execution_root"]
                self.plan["source_identity"] = report["source"]
            self.store.save(self.plan)
            QTimer.singleShot(0, self._advance)
        except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as exc:
            self.active = False
            self.error.emit("Nie zapisano rozstrzygnięcia planu: " + type(exc).__name__)
            self.changed.emit()
