"""Immutable, self-contained TPA evidence snapshots; reading never starts services.

RunStore remains the owner of TPA runs. This module adds its missing manifest,
per-scenario artifacts and integrity envelope, including unselected scenarios.
Only a committed snapshot marker makes a directory visible to history readers.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import struct
import sys
from typing import Any
from uuid import uuid4
import zipfile

from .tpa_catalog import LIVE_CASES
from .tpa_reports import MAX_REPORT, STATES, Redactor, redact, safe_child, utc

SCHEMA = "jazn_test_evidence/v1"
MAX_FILES = 20000
MAX_TOTAL = 64 * 1024 * 1024
MAX_DOCUMENT = 16 * 1024 * 1024  # A complete SYSTEM inventory can exceed a single TPA report.


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write(path: Path, value: bytes) -> None:
    if len(value) > MAX_DOCUMENT:
        raise ValueError("Dowód przekracza limit rozmiaru")
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _read(path: Path) -> bytes:
    # Validate both the leaf and every ancestor before opening external history.
    safe_child(path.parent, path.name)
    if not path.is_file() or path.stat().st_size > MAX_DOCUMENT:
        raise ValueError("Brak lub zbyt duży plik dowodu")
    with path.open("rb") as stream:
        value = stream.read(MAX_DOCUMENT + 1)
    if len(value) > MAX_DOCUMENT:
        raise ValueError("Dowód przekracza limit rozmiaru")
    return value


def manifest(report: dict) -> dict:
    """Freeze the full TPA contract, not just a successful selected subset."""
    return {
        "schema": SCHEMA, "run_id": report["run_id"], "redaction_policy": "canonical-before-freeze/v1",
        "created_utc": report["started_utc"], "selected": list(report["selected"]),
        "scope": "Registered tests and gates; execution alone does not certify a SYSTEM release",
        "scenarios": [{
            "scenario_id": row["id"], "name": row["title"],
            "description": row["steps"], "functionality": row["category"],
            "test_class": row.get("test_class", "regression_and_operator_acceptance"),
            "required_os": row.get("required_os", ["Windows", "Linux"]),
            "python": ">=3.12", "dependencies": row["requirements"],
            "requires_real_runtime": row.get("requires_real_runtime", row["id"] in LIVE_CASES),
            "executor": row["executor"], "files": row["files"],
            "pass_criteria": row["expected"],
            "fail_criteria": "Any unmet criterion, missing or mismatching evidence",
            "evidence_criteria": ["scenario TXT", "scenario JSON", "JUnit/log for regression", "separate full gate evidence"],
            "manual_confirmation": row["mode"] != "automatic",
            "contract_version": row.get("contract_version", "tpa-22/v1"), "required": True,
        } for row in report["coverage_map"]],
    }


def initialize(folder: Path, report: dict) -> None:
    """Create-only contract before preflight or any selected test can run."""
    path = safe_child(folder, "manifest.json")
    expected = _json(manifest(report))
    if path.exists():
        raise FileExistsError("Manifest przebiegu już istnieje")
    temporary = safe_child(folder, "manifest-" + uuid4().hex + ".tmp")
    _write(temporary, expected)
    os.rename(temporary, path)
    report["evidence_manifest_sha256"] = sha256(expected).hexdigest()


def _member(folder: Path, name: str) -> Path:
    if (not isinstance(name, str) or "\\" in name or name.startswith("/")
            or len(name.split("/")) > 3):
        raise ValueError("Nieprawidłowa ścieżka archiwum")
    target = folder
    for part in name.split("/"):
        target = safe_child(target, part)
    return target


def scenario_text(row: dict) -> str:
    return "\n".join([
        "JAŹŃ / JSS — RAPORT SCENARIUSZA", "",
        "SCENARIO_ID: " + row["scenario_id"], "RUN_ID: " + row["run_id"],
        *(["NAME: " + row["name"]] if "name" in row else []),
        "VERSION: " + str(row["source"].get("version")),
        "SOURCE_SHA: " + str(row["source"].get("git_sha") or "UNKNOWN"),
        "STATUS: " + row["execution_status"], "FULL_GATE: " + row["full_gate_status"],
        "START: " + str(row.get("started_utc")), "END: " + str(row.get("finished_utc")),
        "EXIT_CODE: " + str(row.get("exit_code")),
        "EXPECTED: " + row["expected"], "OBSERVED: " + row["reason"],
        "EVIDENCE: " + ", ".join(row["artifacts"]), "",
    ])


def _writer_platform() -> dict:
    # Python 3.14's platform.system/platform can synchronously query WMI on
    # Windows. Kernel version is available directly, without inventory or a
    # warm-up. Keep writer identity distinct from the selected test Python.
    if sys.platform == "win32":
        version = sys.getwindowsversion().platform_version
        identity = {"os": "Windows", "platform": "Windows-" + ".".join(map(str, version))}
    else:
        identity = {"os": platform.system(), "platform": platform.platform()}
    return {**identity, "writer_python_version": list(sys.version_info[:3]),
            "writer_pointer_bits": struct.calcsize("P") * 8}


def save_snapshot(folder: Path, report: dict, redactor: Any) -> str:
    """Publish a new immutable revision; a crash leaves older revisions readable."""
    contract_raw = _read(safe_child(folder, "manifest.json"))
    if sha256(contract_raw).hexdigest() != report.get("evidence_manifest_sha256"):
        raise ValueError("Zmieniono niezmienny manifest przebiegu")
    contract = json.loads(contract_raw)
    definitions = contract["scenarios"]
    ids = [row["scenario_id"] for row in definitions]
    rows = {row["case_id"]: row for row in report["results"]}
    if (contract.get("schema") != SCHEMA or contract.get("run_id") != report["run_id"]
            or contract.get("selected") != report["selected"]
            or len(ids) != len(set(ids)) or set(rows) != set(report["selected"])
            or len(rows) != len(report["results"]) or set(rows) - set(ids)):
        raise ValueError("Niezgodny katalog lub zakres przebiegu")
    # Preflight may resolve an unknown source or materialize the requested
    # source copy. Once execution starts, changing source cannot relabel PASS.
    binding_path = safe_child(folder, "execution-source.json")
    source_binding = _json(report["source"])
    if binding_path.exists():
        if _read(binding_path) != source_binding:
            raise ValueError("Źródło zmieniło się po rozpoczęciu wykonania")
    elif any(row["status"] in {"RUNNING", "PASS", "FAIL", "ERROR", "TIMEOUT"} for row in rows.values()):
        _write(binding_path, source_binding)
    key = "snapshot-" + uuid4().hex
    snapshot = safe_child(folder, key)
    snapshot.mkdir(exist_ok=False)
    content: dict[str, bytes] = {"manifest.json": _json(contract)}
    environment = redact({**report.get("environment", {}), "python": report["python"],
                          **_writer_platform()}, redactor)
    content["environment.json"] = _json(environment)
    # Copy only the explicitly owned, redacted text artifacts. Never walk live
    # staging, runtime, MEMORY, SQLite, claims or arbitrary neighboring files.
    artifact_names = list(dict.fromkeys(report.get("artifacts", [])))
    for name in artifact_names:
        source = safe_child(folder, name)
        if source.suffix.lower() not in {".json", ".txt", ".xml", ".log"}:
            raise ValueError("Niedozwolony typ dowodu")
        raw = _read(source)
        if source.suffix.lower() == ".json":
            raw = _json(redact(json.loads(raw), redactor))
        elif source.suffix.lower() == ".xml":
            # Reuse the canonical parsed-tree XML redaction/validation.
            from .tpa_reports import junit_result
            _, raw = junit_result(source, 0, redactor)
            if not raw:
                raise ValueError("Niepoprawny JUnit")
        else:
            raw = redactor.text(raw.decode("utf-8")).encode("utf-8")
        content["evidence/" + name] = raw
    records = []
    for definition in definitions:
        case_id = definition["scenario_id"]
        original = rows.get(case_id, {})
        status = original.get("status", "NOT_RUN")
        full = original.get("full_gate", "NOT_RUN")
        if status not in STATES or full not in STATES:
            raise ValueError("Nieznany status scenariusza")
        record = redact({
            "schema": SCHEMA, "scenario_id": case_id, "run_id": report["run_id"], "name": definition["name"],
            "source": deepcopy(report["source"]), "environment": environment,
            "execution": report.get("execution", "regression"),
            "execution_status": status, "full_gate_status": full,
            "expected": definition["pass_criteria"],
            "reason": original.get("reason", "Scenariusz nie został wybrany do wykonania."),
            "started_utc": original.get("started_utc"),
            "finished_utc": original.get("finished_utc"),
            "duration_seconds": original.get("duration_seconds"),
            "exit_code": original.get("exit_code"),
            "artifacts": ["evidence/" + name for name in artifact_names
                          if name in {original.get("log"), original.get("junit"), original.get("operator_observation"), case_id + ".live.json"}],
        }, redactor)
        records.append(record)
        content["results/" + case_id + ".json"] = _json(record)
        content["scenarios/" + case_id + ".txt"] = scenario_text(record).encode("utf-8")
    overview = {"schema": SCHEMA, "run_id": report["run_id"], "snapshot": key,
                "saved_utc": utc(), "source": redact(report["source"], redactor),
                "finished_utc": report.get("finished_utc"),
                "counts": dict(Counter(row["execution_status"] for row in records)),
                "required_count": len(definitions), "release_status": "RELEASE_NOT_ACCEPTED",
                "release_reason": "Execution evidence alone does not certify the complete SYSTEM release matrix"}
    content["summary.json"] = _json(overview)
    content["summary.txt"] = ("TPA — " + report["run_id"] + "\n" +
                              json.dumps(overview, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(content) > MAX_FILES or sum(map(len, content.values())) > MAX_TOTAL:
        raise ValueError("Archiwum przekracza limit")
    hashes = {}
    for name, raw in content.items():
        path = _member(snapshot, name)
        path.parent.mkdir(exist_ok=True)
        _write(path, raw)
        hashes[name] = {"sha256": sha256(raw).hexdigest(), "size": len(raw)}
    integrity = _json({"schema": SCHEMA, "files": hashes})
    _write(safe_child(snapshot, "integrity.json"), integrity)
    seal = {"schema": SCHEMA, "snapshot": key, "run_id": report["run_id"],
            "integrity_sha256": sha256(integrity).hexdigest()}
    temporary = safe_child(folder, key + ".tmp")
    _write(temporary, _json(seal))
    os.rename(temporary, safe_child(folder, key + ".json"))
    return key


def read_snapshot(folder: Path, key: str) -> dict:
    """Validate an imported/external snapshot without creating or repairing files."""
    if not re.fullmatch(r"snapshot-[0-9a-f]{32}", key):
        raise ValueError("Nieprawidłowy identyfikator rewizji")
    seal = json.loads(_read(safe_child(folder, key + ".json")))
    snapshot = safe_child(folder, key)
    integrity_raw = _read(safe_child(snapshot, "integrity.json"))
    return _validate_snapshot(key, seal, integrity_raw, lambda name: _read(_member(snapshot, name)))


def _validate_snapshot(key: str, seal: dict, integrity_raw: bytes, read_member: Any) -> dict:
    """The same verifier handles directories and ZIPs before materialization."""
    if (seal.get("schema") != SCHEMA or seal.get("snapshot") != key
            or seal.get("integrity_sha256") != sha256(integrity_raw).hexdigest()):
        raise ValueError("Niezgodna pieczęć integralności")
    integrity = json.loads(integrity_raw)
    files = integrity.get("files")
    if integrity.get("schema") != SCHEMA or not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("Nieprawidłowy manifest integralności")
    data = {}
    total = 0
    for name, expected in files.items():
        # Check syntax even for in-memory ZIP members.
        _member(Path.cwd(), name)
        raw = read_member(name)
        total += len(raw)
        if total > MAX_TOTAL or expected != {"sha256": sha256(raw).hexdigest(), "size": len(raw)}:
            raise ValueError("Brak lub niezgodny SHA256 dowodu: " + name)
        data[name] = raw
    contract = json.loads(data["manifest.json"])
    if contract.get("redaction_policy") not in {None, "canonical-before-freeze/v1"}:
        raise ValueError("Nieznana polityka redakcji manifestu")
    overview = json.loads(data["summary.json"])
    ids = [row["scenario_id"] for row in contract["scenarios"]]
    if (not ids or len(ids) != len(set(ids)) or contract.get("schema") != SCHEMA
            or contract.get("run_id") != seal.get("run_id") or overview.get("run_id") != seal.get("run_id")
            or overview.get("snapshot") != key):
        raise ValueError("Niezgodny manifest przebiegu")
    results = []
    definitions = {row["scenario_id"]: row for row in contract["scenarios"]}
    redactor = Redactor({})
    legacy = contract.get("redaction_policy") is None
    for case_id in ids:
        row = json.loads(data["results/" + case_id + ".json"])
        if (row.get("schema") != SCHEMA or row.get("scenario_id") != case_id
                or ("name" in row and row["name"] != (
                    redactor.text(definitions[case_id]["name"]) if legacy else definitions[case_id]["name"]))
                or row.get("run_id") != seal["run_id"] or row.get("source") != overview["source"]
                or row.get("execution_status") not in STATES or row.get("full_gate_status") not in STATES
                or scenario_text(row).encode("utf-8") != data["scenarios/" + case_id + ".txt"]
                or any(name not in data for name in row["artifacts"])):
            raise ValueError("Niezgodny wynik scenariusza")
        results.append(row)
    if overview.get("counts") != dict(Counter(row["execution_status"] for row in results)):
        raise ValueError("Niezgodne liczniki przebiegu")
    return {"manifest": contract, "summary": overview, "results": results, "files": data}


def history(base: Path, *, limit: int = 100) -> tuple[list[dict], list[str]]:
    """Bounded, read-only discovery; malformed/latest evidence remains an error."""
    if not 1 <= limit <= 100:
        raise ValueError("Nieprawidłowy limit historii")
    safe_child(base.parent, base.name)
    found, errors = [], []
    history_bytes = 0
    if not base.exists():
        return found, errors
    folders = sorted(base.glob("run-*"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for folder in folders:
        if not re.fullmatch(r"run-[0-9a-f]{32}", folder.name):
            continue
        try:
            safe_child(base, folder.name)
            # The mtime only orders discovery. No status is inferred from it.
            markers = sorted(folder.glob("snapshot-*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            if not markers:
                continue  # Legacy runs remain accessible through the existing reader.
            run = read_snapshot(folder, markers[0].stem)
            from .test_evidence_receipts import recover_receipts
            run = recover_receipts(folder, run)
            size = sum(map(len, run["files"].values()))
            if history_bytes + size > MAX_TOTAL:
                errors.append("Limit pamięci historii; wybierz katalog z mniejszym zakresem przebiegów")
                break
            history_bytes += size
            found.append(run)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(folder.name + ": " + type(exc).__name__ + "; brak potwierdzonego wyniku")
        if len(found) + len(errors) >= limit:
            break
    return sorted(found, key=lambda run: run["summary"]["saved_utc"], reverse=True), errors


def export_snapshot(folder: Path, key: str, destination: Path, system_root: Path) -> Path:
    """Export verified, self-contained evidence only; never overwrite a ZIP."""
    from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
    if destination.suffix.lower() != ".zip":
        raise ValueError("Wybierz plik ZIP")
    safe_child(destination.parent, destination.name)
    validate_operator_path(destination, system_root)
    snapshot = read_snapshot(folder, key)
    if _json(redact(snapshot["manifest"], Redactor({}))) != snapshot["files"]["manifest.json"]:
        raise ValueError("Historyczny manifest zawiera niezredagowane dane; eksport zablokowany")
    prefix = snapshot["summary"]["run_id"] + "/"
    with destination.open("xb") as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in snapshot["files"].items():
                archive.writestr(prefix + key + "/" + name, raw)
            archive.writestr(prefix + key + "/integrity.json", _read(safe_child(safe_child(folder, key), "integrity.json")))
            archive.writestr(prefix + key + ".json", _read(safe_child(folder, key + ".json")))
        output.flush()
        os.fsync(output.fileno())
    return destination


def import_snapshot(archive_path: Path, destination: Path, system_root: Path) -> Path:
    """Verify an entire bounded ZIP before creating a new, owned history folder.

    No extractall, service startup, executable data, overwrite or retention
    cleanup. A partial destination after an I/O failure remains diagnostic data.
    """
    from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
    import stat
    safe_child(archive_path.parent, archive_path.name)
    safe_child(destination.parent, destination.name)
    validate_operator_path(destination, system_root, directory=True)
    if destination.exists():
        raise FileExistsError("Katalog importu już istnieje")
    content = {}
    total = 0
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES + 2:
            raise ValueError("Zbyt wiele plików w archiwum")
        for entry in entries:
            mode = entry.external_attr >> 16
            if (entry.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                    or entry.flag_bits & 1 or entry.file_size > MAX_DOCUMENT
                    or entry.filename in content):
                raise ValueError("Niedozwolony element archiwum")
            # Syntax only; this does not create a destination or follow a ZIP path.
            parts = entry.filename.split("/")
            if (len(parts) < 2 or len(parts) > 4
                    or not re.fullmatch(r"run-[0-9a-f]{32}", parts[0])):
                raise ValueError("Nieprawidłowa ścieżka ZIP")
            for part in parts:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", part) or part in {".", ".."}:
                    raise ValueError("Nieprawidłowa ścieżka ZIP")
            with archive.open(entry) as stream:
                raw = stream.read(MAX_DOCUMENT + 1)
            total += len(raw)
            if len(raw) != entry.file_size or total > MAX_TOTAL:
                raise ValueError("Przekroczony limit importu")
            content[entry.filename] = raw
    markers = [name for name in content if re.fullmatch(r"run-[0-9a-f]{32}/snapshot-[0-9a-f]{32}\.json", name)]
    if len(markers) != 1:
        raise ValueError("Archiwum wymaga jednej kompletnej rewizji")
    marker = markers[0]
    run_id, leaf = marker.split("/")
    key = leaf[:-5]
    prefix = run_id + "/" + key + "/"
    integrity_name = prefix + "integrity.json"
    validated = _validate_snapshot(key, json.loads(content[marker]), content[integrity_name], lambda name: content[prefix + name])
    if (validated["summary"]["run_id"] != run_id
            or set(content) != {marker, integrity_name, *(prefix + name for name in validated["files"])}):
        raise ValueError("Archiwum zawiera obce lub niezgodne elementy")
    destination.mkdir(exist_ok=False)
    # Commit marker last: interruption cannot expose an incomplete PASS.
    for name in [*(name for name in content if name != marker), marker]:
        path = destination
        for part in name.split("/"):
            path = safe_child(path, part)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, content[name])
    return destination
