"""Rebuild the 22-case projection from reports; never write or promote evidence."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from .tpa_catalog import LIVE_CASES, execution_map, scenario
from .tpa_reports import MAX_REPORT, RunStore, junit_result, safe_child
from .tpa_triage import _source_relation


def evidence_errors(store: RunStore, report: dict, row: dict, *, full: bool = False) -> list[str]:
    """A historical PASS is a claim until its owned material is checked."""
    errors: list[str] = []
    try:
        folder = store.folder(report["run_id"])
        names = report.get("artifacts", [])
        required = [row[k] for k in ("log", "junit") if row.get(k)]
        if row.get("status") == "PASS":
            if report.get("execution", "regression") == "regression" and not row.get("junit"):
                errors.append("Brak JUnit potwierdzającego regresję.")
            if report.get("execution") == "live":
                required.append(row["case_id"] + ".live.json")
        if full:
            if row.get("status") != "PASS":
                errors.append("Pełny odbiór nie ma zaliczonego wykonania.")
            key = row["case_id"]
            if key in LIVE_CASES and report.get("execution") != "live":
                errors.append("Wymagane wykonanie live.")
            if key.startswith("studio-") and report.get("execution") != "sandbox":
                errors.append("Wymagany przepływ izolowanego Studio.")
            name = row.get("operator_observation")
            if not name:
                errors.append("Brak zapisu odbioru operatora.")
            else:
                required.append(name)
        for name in required:
            if name not in names:
                raise ValueError("Dowód nie należy do przebiegu")
            path = safe_child(folder, name)
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_REPORT:
                raise ValueError("Brak lub niekompletny dowód")
            if name == row.get("junit") and row.get("status") == "PASS":
                result, _ = junit_result(path, row.get("exit_code", -1), store.redactor)
                if result["status"] != "PASS":
                    raise ValueError("JUnit nie potwierdza PASS")
            if name.endswith(".live.json") and row.get("status") == "PASS":
                live = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(live, dict) or not isinstance(live.get("result"), dict)
                        or live["result"].get("status") != "PASS"
                        or not isinstance(live.get("cleanup"), dict)
                        or live["cleanup"].get("ok") is not True):
                    raise ValueError("Dowód live lub cleanup nie potwierdza PASS")
        if full and row.get("operator_observation"):
            observation = json.loads(safe_child(folder, row["operator_observation"]).read_text(encoding="utf-8"))
            if (not isinstance(observation, dict) or observation.get("status") != "PASS"
                    or observation.get("case_id") != row["case_id"]
                    or observation.get("kind") != "operator_attestation"
                    or not observation.get("note", "").strip()
                    or observation.get("checked_steps") != list(range(len(scenario(row["case_id"])["guide"])))
                    or not isinstance(observation.get("evidence"), list) or not observation["evidence"]):
                raise ValueError("Niekompletna obserwacja operatora")
            for proof in observation["evidence"]:
                if not isinstance(proof, dict) or proof.get("artifact") not in names:
                    raise ValueError("Brak dowodu obserwacji")
                path = safe_child(folder, proof["artifact"])
                if (not path.is_file() or not 0 < path.stat().st_size <= MAX_REPORT
                        or sha256(path.read_bytes()).hexdigest() != proof.get("sha256")):
                    raise ValueError("Niezgodny SHA256 dowodu obserwacji")
            if (row["case_id"].startswith("studio-") or row["case_id"] in {"offline-exe", "ui-accessibility"}) and not any(
                    p["artifact"].startswith("proof-") for p in observation["evidence"]):
                errors.append("Brak osobnego dowodu operatora GUI/EXE.")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        errors.append("Brak, uszkodzenie lub niezgodność dowodu; zachowano historyczne twierdzenie.")
    return errors


def current_state(store: RunStore, current: dict, history: list[dict] | None = None) -> dict[str, dict[str, Any]]:
    """Latest attempted result per channel, plus last verified successes, across runs.

    NOT_RUN is absence of an attempt and never hides an older result. Missing
    source identity stays uncertain. Stale successful evidence remains visible.
    """
    runs = store.history() if history is None else history
    output: dict[str, dict[str, Any]] = {}
    for case in execution_map():
        attempts = [(run, row) for run in runs for row in run.get("results", [])
                    if row.get("case_id") == case["id"] and row.get("status") != "NOT_RUN"]
        attempts.sort(key=lambda pair: (str(pair[1].get("finished_utc") or pair[1].get("started_utc")
                                           or pair[0].get("started_utc", "")), pair[0]["run_id"]), reverse=True)
        state: dict[str, Any] = {"case_id": case["id"], "regression": None, "live": None,
                                 "sandbox": None, "full": None, "last_attempt": None,
                                 "last_success": None, "last_full_success": None}
        for run, row in attempts:
            relation = _source_relation(run.get("source", {}), current)
            errors = evidence_errors(store, run, row) if row.get("status") == "PASS" else []
            entry = {"run_id": run["run_id"], "source": deepcopy(run.get("source", {})),
                     "row": deepcopy(row), "status": "BLOCKED" if errors else row["status"],
                     "source_relation": relation, "evidence_errors": errors,
                     "time": row.get("finished_utc") or row.get("started_utc") or run["started_utc"]}
            if state["last_attempt"] is None:
                state["last_attempt"] = entry
            channel = run.get("execution", "regression")
            if channel in {"regression", "live", "sandbox"} and state[channel] is None:
                state[channel] = entry
            if state["last_success"] is None and entry["status"] == "PASS":
                state["last_success"] = entry
            if row.get("full_gate", "NOT_RUN") != "NOT_RUN":
                full_errors = evidence_errors(store, run, row, full=True) if row["full_gate"] == "PASS" else []
                full = {**entry, "status": "BLOCKED" if errors or full_errors else row["full_gate"],
                        "evidence_errors": errors + full_errors}
                if state["full"] is None:
                    state["full"] = full
                if state["last_full_success"] is None and full["status"] == "PASS":
                    state["last_full_success"] = full
        output[case["id"]] = state
    return output
