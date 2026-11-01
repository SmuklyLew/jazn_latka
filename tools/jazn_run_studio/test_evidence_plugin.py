"""Opt-in pytest evidence adapter over the existing RunStore, not another runner.

Enable with -p tools.jazn_run_studio.test_evidence_plugin and an explicit
JAZN_TEST_EVIDENCE_DIR. Collection freezes the complete inventory before tests.
Per-phase create-only receipts survive a killed pytest process; final snapshots
are published only after completion. No lifecycle/model/MEMORY operations.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any
from uuid import uuid4

import pytest

from .tpa_catalog import execution_map
from .tpa_reports import RunStore, junit_result, redact, safe_child, source_identity, utc
from .test_evidence_archive import _json, _write


def _definition(nodeid: str, record: dict | None = None) -> dict:
    record = record or {}
    return {"id": "pytest-" + sha256(nodeid.encode("utf-8")).hexdigest()[:32],
            "title": nodeid, "steps": str(record.get("purpose") or "Execute the registered pytest test"),
            "expected": str(record.get("expected") or "All assertions and setup/teardown succeed"),
            "category": str(record.get("category") or "pytest"), "executor": "pytest",
            "mode": "automatic", "files": [nodeid.split("::", 1)[0]], "requirements": ["pytest"],
            "test_class": "pytest", "required_os": [platform.system()],
            "limitations": "Execution evidence; separate platform, live and operator gates remain required",
            "contract_version": "pytest-evidence/v1"}


def modernization_gates() -> list[dict]:
    """Required non-pytest gates remain visible even when no executor exists."""
    gates = []
    for profile, operating_system in (("powershell", "Windows"), ("pwsh", "Windows"), ("cmd", "Windows"),
                                      ("git-bash", "Windows"), ("wsl-bash", "Windows"),
                                      ("bash", "Linux"), ("sh", "Linux")):
        for check in ("start", "command", "unicode", "python", "interrupt", "child-exit", "exit-reopen",
                      "resize", "ansi", "alternate-buffer", "long-output", "crash", "parallel-tabs", "gui-close", "cleanup"):
            gates.append({"id": "terminal-" + profile + "-" + check, "title": profile + ": " + check,
                          "required_os": [operating_system], "category": "Terminal live",
                          "expected": "Real interactive PTY/ConPTY: " + check + "; own processes only"})
    for key, title in (
        ("release-hardening", "Final SHA metadata identity and repeated idempotence"),
        ("system-windows", "Complete required Windows SYSTEM suite"),
        ("system-linux", "Complete required Linux SYSTEM suite"),
        ("evidence-windows", "Evidence integrity, crash and read-only history on Windows"),
        ("evidence-linux", "Evidence integrity, crash and read-only history on Linux"),
        ("accepted-finalization", "Accepted lineage, display_exact, hash, persistence and deduplication"),
        ("chat-multisession", "Concurrent session identity, switch, restart and same-request recovery"),
        ("ci-final-sha", "All required CI workflows terminal on exact final SHA"),
    ):
        gates.append({"id": key, "title": title, "expected": title,
                      "category": "Release", "required_os": ["Windows", "Linux"]})
    for width, height in ((860, 580), (1240, 840), (1920, 1080)):
        for dpi in (100, 150, 200):
            gates.append({"id": f"gui-{width}-{height}-{dpi}", "title": f"GUI {width}×{height}, DPI {dpi}%",
                          "expected": "Reachable controls, keyboard focus, themes, screenshots and operator review",
                          "category": "GUI live", "required_os": ["Windows", "Linux"]})
    return [{"steps": row["expected"], "executor": "compatible real host and operator",
             "requirements": [], "files": [], "mode": "manual",
             "requires_real_runtime": row["id"] == "accepted-finalization",
             "limitations": "No automatic acceptance from pytest or screenshots",
             "test_class": "live_or_release_gate", "contract_version": "jss-modernization/v1", **row}
            for row in gates]


class EvidenceRecorder:
    def __init__(self, config: Any, output: Path):
        self.config = config
        self.root = Path(config.rootpath)
        self.store = RunStore(self.root, evidence_base=output)
        self.report: dict | None = None
        self.rows: dict[str, dict] = {}
        self.inventory_error = ""
        self.collection_errors: list[str] = []

    def _inventory(self) -> dict:
        from tools.jazn_tests_studio.sync_contract_catalog import build_current_catalog
        try:
            records = build_current_catalog(self.root).get("contracts", {})
            if not isinstance(records, dict):
                raise ValueError("Invalid canonical test inventory")
            return records
        except (OSError, ValueError, SyntaxError, TypeError) as exc:
            self.inventory_error = type(exc).__name__
            return {}

    def _create(self, items: list) -> None:
        inventory = self._inventory()
        base_nodeids = {item.nodeid.split("[", 1)[0] for item in items}
        definitions = [_definition(item.nodeid, inventory.get(item.nodeid.split("[", 1)[0])) for item in items]
        definitions += [_definition(nodeid, record) for nodeid, record in sorted(inventory.items())
                        if nodeid not in base_nodeids]
        collection = {"id": "pytest-collection", "title": "pytest collection and inventory", "steps": "Collect the requested scope",
                      "expected": "Collection completes and canonical inventory is readable", "category": "pytest",
                      "executor": "pytest", "mode": "automatic", "files": [], "requirements": ["pytest"],
                      "limitations": "Does not certify complete SYSTEM acceptance", "test_class": "collection"}
        definitions += [collection, *execution_map(), *modernization_gates()]
        source = source_identity(self.root)
        for key, args in (("git_sha", ["rev-parse", "HEAD"]), ("git_dirty", ["status", "--porcelain"])):
            try:
                result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                                        timeout=5, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode == 0:
                    source[key] = bool(result.stdout) if key == "git_dirty" else result.stdout.decode("ascii").strip()
            except (OSError, subprocess.SubprocessError, UnicodeError):
                pass
        selected = tuple([_definition(item.nodeid)["id"] for item in items] + ["pytest-collection"])
        self.report = self.store.create(selected, sys.executable,
            {"os": platform.system(), "python_version": platform.python_version(),
             "pytest_version": pytest.__version__, "collected_count": len(items),
             "inventory_definition_count": len(inventory), "inventory_error": self.inventory_error},
            catalogue=definitions, source=source)
        self.report["execution"] = "pytest"
        self.rows = {row["case_id"]: row for row in self.report["results"]}
        self.rows["pytest-collection"].update(status="ERROR" if self.inventory_error or self.collection_errors else "PASS",
            reason=("Canonical inventory unavailable" if self.inventory_error else
                    "Collection failed: " + "\n".join(self.collection_errors) if self.collection_errors else
                    "Collection finished; other gates remain separate"),
            finished_utc=utc())

    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.collection_errors.append(self.store.redactor.text(str(report.longrepr))[:8000])

    def pytest_collection_finish(self, session: Any) -> None:
        self._create(list(session.items))

    def pytest_runtest_logreport(self, report: Any) -> None:
        if self.report is None:
            raise RuntimeError("Evidence manifest was not committed before execution")
        key = _definition(report.nodeid)["id"]
        row = self.rows[key]
        row.setdefault("started_utc", utc())
        row["duration_seconds"] = float(row.get("duration_seconds") or 0) + report.duration
        already_failed = row["status"] in {"FAIL", "ERROR"}
        if not already_failed:
            if report.failed:
                row["status"] = "FAIL" if report.when == "call" else "ERROR"
            elif report.skipped:
                row["status"] = "SKIPPED"
            elif report.when == "call":
                row["status"] = "FAIL" if hasattr(report, "wasxfail") else "PASS"
            elif row["status"] == "QUEUED":
                row["status"] = "RUNNING"
        if not already_failed or report.failed:
            row["reason"] = self.store.redactor.text(report.when + ": " + report.outcome +
                             ("\n" + str(report.longrepr)[:8000] if report.failed or report.skipped else ""))
        if report.when == "teardown":
            row["finished_utc"] = utc()
        # A killed process retains create-only receipts instead of losing the
        # complete in-memory result. No historical receipt is overwritten.
        event = redact({"schema": "jazn_pytest_receipt/v1", "run_id": self.report["run_id"],
                        "source": self.report["source"], "phase": report.when, "saved_utc": utc(),
                        "result": row}, self.store.redactor)
        raw = _json(event)
        envelope = _json({"sha256": sha256(raw).hexdigest(), "event": event})
        name = key + "-" + uuid4().hex
        folder = self.store.folder(self.report["run_id"])
        _write(safe_child(folder, name + ".json"), envelope)
        result = event["result"]
        _write(safe_child(folder, name + ".txt"),
               (result["title"] + "\n" + result["status"] + "\n" + result["reason"] + "\n").encode("utf-8"))

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        if self.report is None:
            self._create([])
        assert self.report is not None
        if int(exitstatus) != 0 and not session.items:
            self.rows["pytest-collection"].update(status="ERROR", reason="Collection failed or no tests were collected")
        for row in self.rows.values():
            if row["status"] in {"QUEUED", "RUNNING"}:
                row.update(status="INTERRUPTED", reason="Test did not complete before the pytest session ended")
        xml_path = getattr(self.config.option, "xmlpath", None)
        if xml_path and Path(xml_path).is_file():
            _, xml = junit_result(Path(xml_path), int(exitstatus), self.store.redactor)
            if xml:
                _write(safe_child(self.store.folder(self.report["run_id"]), "pytest.xml"), xml)
                self.report["artifacts"].append("pytest.xml")
                for row in self.rows.values():
                    row["junit"] = "pytest.xml"
        self.report["finished_utc"] = utc()
        self.report["pytest_exit_code"] = int(exitstatus)
        self.store.save(self.report)


def pytest_configure(config: Any) -> None:
    raw = os.environ.get("JAZN_TEST_EVIDENCE_DIR", "").strip()
    if raw:
        config.pluginmanager.register(EvidenceRecorder(config, Path(raw)), "jazn-durable-test-evidence")
