"""Evidence-backed human observations, separate from automated test outcomes."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import uuid
from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
from .local_acceptance import scope_version
from .tpa_catalog import LIVE_CASES, scenario
from .tpa_reports import RunStore, redact, safe_child, utc


def _write_artifact(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def _adopt_report(original: dict, committed: dict) -> None:
    # Existing clients retain references to result rows. Publish their new
    # values after commit without invalidating those public references.
    for field in ("results", "coverage_map"):
        if len(original[field]) != len(committed[field]):
            raise ValueError("Zmieniono zakres raportu podczas zapisu obserwacji")
    for field in ("results", "coverage_map"):
        for previous, current in zip(original[field], committed[field], strict=True):
            previous.update(current)
        committed[field] = original[field]
    original.update(committed)


def attach_evidence(store: RunStore, report: dict, source: Path) -> str:
    original, report = report, deepcopy(report)
    if re.search(r"(?i)(?:credential|secret|password|token|auth|\.env|\.ssh|\.aws)", source.name):
        raise ValueError("Nie dołączaj plików uwierzytelnienia ani sekretów")
    if source.suffix.lower() not in {".txt", ".log", ".json", ".xml"}:
        raise ValueError("Dołącz tekstowy raport lub log testowy; bazy i pliki uwierzytelnienia są niedozwolone.")
    for part in (source, *source.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Dowód nie może być dowiązaniem")
    validate_operator_path(source, store.root)
    if not source.is_file() or source.stat().st_size > 1024 * 1024:
        raise ValueError("Brak pliku dowodu lub przekroczony limit 1 MiB")
    text = source.read_text(encoding="utf-8")
    text = json.dumps(redact(json.loads(text), store.redactor), ensure_ascii=False, indent=2) if source.suffix.lower() == ".json" else store.redactor.text(text)
    name = "proof-" + uuid.uuid4().hex + ".txt"
    _write_artifact(safe_child(store.folder(report["run_id"]), name), text)
    report["artifacts"].append(name)
    store.save(report)
    _adopt_report(original, report)
    return name


def record_observation(store: RunStore, report: dict, case_id: str, checked: list[int], note: str, evidence_names: list[str], outcome: str,
                       *, verified_source: dict | None = None) -> dict:
    original, report = report, deepcopy(report)
    case = scenario(case_id)
    execution_root = Path(report.get("environment", {}).get("execution_root") or store.root)
    if execution_root != store.root and (not execution_root.is_absolute() or not execution_root.resolve().is_relative_to(store.base.resolve())
            or any(p.is_symlink() or p.is_junction() for p in (execution_root, *execution_root.parents))):
        raise ValueError("Źródło odbioru nie należy do zapisanego przebiegu")
    if not report.get("finished_utc") or report["source"]["version"] != scope_version(execution_root):
        raise ValueError("Odbiór wymaga zakończonego przebiegu bieżącej wersji. Historyczny wynik pozostaje bez zmian.")
    if (execution_root / ".git").exists() or (execution_root / "PACKAGE_INTEGRITY_MANIFEST.json").is_file():
        from .tpa_triage import _source_relation
        if verified_source is None or _source_relation(report["source"], verified_source) != "same":
            raise ValueError("Przed zapisem sprawdź bieżące SHA i integralność źródła odbioru")
    if outcome not in {"PASS", "FAIL", "BLOCKED"} or not note.strip() or len(note) > 3000:
        raise ValueError("Wpisz konkretną obserwację i wybierz wynik odbioru")
    row = next((r for r in report["results"] if r["case_id"] == case_id), None)
    if row is None:
        raise ValueError("Scenariusz nie należy do otwartego przebiegu")
    proof = []
    for name in evidence_names:
        if name not in report["artifacts"]:
            raise ValueError("Dowód nie należy do tego przebiegu")
        path = safe_child(store.folder(report["run_id"]), name)
        if not path.is_file() or not 0 < path.stat().st_size <= 4 * 1024 * 1024:
            raise ValueError("Brak kompletnego pliku dowodu")
        proof.append({"artifact": name, "sha256": sha256(path.read_bytes()).hexdigest()})
    if outcome == "PASS":
        if sorted(set(checked)) != list(range(len(case["guide"]))) or not proof or row["status"] != "PASS":
            raise ValueError("PASS wymaga całej checklisty, dowodu i zaliczonego wykonania z tego przebiegu")
        if case_id in LIVE_CASES and report.get("execution") != "live":
            raise ValueError("Ten odbiór wymaga rzeczywistych tur/tożsamości; podtest regresyjny nie wystarcza")
        if case_id.startswith("studio-") and report.get("execution") != "sandbox":
            raise ValueError("Odbiór Studio wymaga wykonania przepływu w izolowanym Studio, nie samego podtestu")
        if (case_id.startswith("studio-") or case_id in {"offline-exe", "ui-accessibility"}) and not any(
                p["artifact"].startswith("proof-") for p in proof):
            raise ValueError("Dołącz osobny raport obserwacji człowieka; JUnit nie potwierdza EXE, DPI ani pełnych przepływów")
        if case_id == "studios-parity":
            if not report["source"].get("git_sha"):
                raise ValueError("Nie ustalono SHA źródeł; wymagane 12 odrębnych odbiorów tych samych źródeł")
            from .tpa_current_state import current_state
            accepted = {key for key, state in current_state(store, report["source"]).items()
                        if key.startswith("studio-") and state["full"] and state["full"]["status"] == "PASS"
                        and state["full"]["source_relation"] == "same"}
            if len(accepted) != 12:
                raise ValueError("Brak 12 odrębnych odbiorów studiów dla tego źródła i wersji")
        from .tpa_current_state import evidence_errors
        if evidence_errors(store, report, row):
            raise ValueError("Dowody wykonania nie potwierdzają wyniku PASS")
    observation = {"case_id": case_id, "run_id": report["run_id"], "source": report["source"], "observed_utc": utc(), "kind": "operator_attestation", "status": outcome,
                   "checked_steps": sorted(set(checked)), "note": store.redactor.text(note.strip()), "evidence": proof,
                   "scope": "Human observation; not CI and not an automatic migration claim"}
    name = "observation-" + uuid.uuid4().hex + ".json"
    observation["artifact"] = name
    _write_artifact(safe_child(store.folder(report["run_id"]), name), json.dumps(observation, ensure_ascii=False, indent=2))
    report["artifacts"].append(name)
    report.setdefault("observations", []).append(observation)
    row.update(full_gate=outcome, operator_observation=name)
    store.save(report)
    _adopt_report(original, report)
    return observation
