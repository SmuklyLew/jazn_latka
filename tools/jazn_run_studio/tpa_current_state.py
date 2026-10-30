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
                if row["case_id"] in LIVE_CASES:
                    evidence = live["result"].get("evidence", {})
                    identity = evidence.get("identity", {})
                    required_identity = ("root_matches", "version_matches", "process_identity_confirmed", "endpoint_identity_matches", "heartbeat_fresh")
                    if (not all(identity.get(k) is True for k in required_identity)
                            or not isinstance(identity.get("instance_id"), str) or not identity["instance_id"]):
                        raise ValueError("Brak pełnej tożsamości instancji live")
                    if row["case_id"] == "gui-daemon":
                        if identity.get("conversation_ready") is not True:
                            raise ValueError("Niepotwierdzona gotowość rozmowy")
                    else:
                        turns = evidence.get("turns", [])
                        count = 1 if row["case_id"] == "chat-resume" else 2
                        if (not isinstance(turns, list) or len(turns) != count
                                or not evidence.get("session_id")
                                or any(not isinstance(t, dict) or t.get("accepted") is not True
                                       or any(not isinstance(t.get(k), str) or not t[k] for k in ("request_id", "turn_id", "trace_id", "text")) for t in turns)
                                or any(len({t[k] for t in turns}) != count for k in ("request_id", "turn_id", "trace_id"))
                                or evidence.get("displayed_request_ids") != [t["request_id"] for t in turns]):
                            raise ValueError("Brak kompletnych zaakceptowanych tur i ACK wyświetlenia")
                        if row["case_id"] == "chat-resume" and (evidence.get("admission", {}).get("confirmed") is not True
                                or evidence["admission"].get("request_id") != turns[0]["request_id"]):
                            raise ValueError("Brak trwałego przyjęcia oryginalnego request_id")
                        if row["case_id"] == "daemon-restart":
                            restarted = evidence.get("restarted_identity", {})
                            if (not all(restarted.get(k) is True for k in required_identity)
                                    or not restarted.get("instance_id") or restarted["instance_id"] == identity["instance_id"]):
                                raise ValueError("Niepotwierdzona nowa własna instancja po restarcie")
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
        full_candidates: list[dict] = []
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
                observations = [o for o in run.get("observations", []) if isinstance(o, dict) and o.get("case_id") == case["id"]]
                latest_observation = next((o for o in reversed(observations) if o.get("status") == row["full_gate"]), {})
                full["time"] = latest_observation.get("observed_utc", entry["time"])
                full_candidates.append(full)
                for observation in observations:
                    if observation.get("status") != "PASS" or not isinstance(observation.get("observed_utc"), str):
                        continue
                    name = observation.get("artifact")
                    if not name:
                        # Known v2 observations predate the explicit artifact field.
                        # Locate their immutable file by case and observation time.
                        for candidate in run.get("artifacts", []):
                            if not candidate.startswith("observation-") or not candidate.endswith(".json"):
                                continue
                            try:
                                path = safe_child(store.folder(run["run_id"]), candidate)
                                if path.stat().st_size > MAX_REPORT:
                                    continue
                                value = json.loads(path.read_text(encoding="utf-8"))
                                if value == observation:
                                    name = candidate
                                    break
                            except (OSError, ValueError):
                                continue  # Invalid historical material never becomes PASS.
                    if not name or name == row.get("operator_observation"):
                        continue
                    prior_errors = evidence_errors(store, run, {**row, "operator_observation": name}, full=True)
                    full_candidates.append({**entry, "status": "BLOCKED" if errors or prior_errors else "PASS",
                                            "time": observation["observed_utc"], "evidence_errors": errors + prior_errors})
                if state["full"] is None:
                    state["full"] = full
                if state["last_full_success"] is None and full["status"] == "PASS":
                    state["last_full_success"] = full
        if full_candidates:
            full_candidates.sort(key=lambda item: (str(item["time"]), item["run_id"]), reverse=True)
            state["full"] = full_candidates[0]
            state["last_full_success"] = next((item for item in full_candidates if item["status"] == "PASS"), None)
        output[case["id"]] = state
    parity = output["studios-parity"]
    if parity["full"] and parity["full"]["status"] == "PASS":
        accepted = [s for key, s in output.items() if key.startswith("studio-") and s["full"]
                    and s["full"]["status"] == "PASS" and s["full"]["source_relation"] == "same"]
        if len(accepted) != 12:
            parity["full"] = {**parity["full"], "status": "BLOCKED", "evidence_errors": ["Brak 12 zweryfikowanych odbiorów studiów tego źródła."]}
            parity["last_full_success"] = None
    return output
