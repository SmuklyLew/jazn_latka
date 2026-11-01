"""Run-owned, redacted evidence outside SYSTEM. No imports from private MEMORY."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid
import xml.etree.ElementTree as ET
import zipfile

from latka_jazn.tools.application_shell.operator_paths import operator_state_dir, validate_operator_path
from .core import Redactor
from .local_acceptance import scope_version
from .tpa_catalog import execution_map

STATES = ("NOT_RUN", "QUEUED", "RUNNING", "PASS", "FAIL", "SKIPPED", "BLOCKED", "CANCELLED", "TIMEOUT", "INTERRUPTED", "ERROR")
TERMINAL = frozenset(STATES) - {"NOT_RUN", "QUEUED", "RUNNING"}
SCHEMA = "jazn_tpa_run/v2"
MAX_REPORT = 4 * 1024 * 1024
MAX_REGISTERED_INDEX = 16 * 1024 * 1024


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_child(folder: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name) or name in {".", ".."}:
        raise ValueError("Nieprawidłowa nazwa dowodu")
    raw = folder / name
    for part in (raw, *raw.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Dowiązanie w ścieżce dowodu TPA")
    if raw.resolve().parent != folder.resolve():
        raise ValueError("Dowód poza katalogiem przebiegu")
    return raw


def redact(value: Any, redactor: Redactor) -> Any:
    if isinstance(value, str):
        return redactor.text(value)
    if isinstance(value, list):
        return [redact(v, redactor) for v in value]
    if isinstance(value, dict):
        return {redactor.text(str(k)): "[UKRYTO]" if re.search(
                    r"(?i)(?:^|[_-])(?:token|secret|password|api[_-]?key|authorization|cookie|credential)(?:$|[_-])", str(k))
                else redact(v, redactor) for k, v in value.items()}
    return value


def source_identity(root: Path) -> dict:
    version = root / "latka_jazn/version.py"
    # Git is observed by the asynchronous preflight, never on the Qt thread.
    return {"version": scope_version(root), "git_sha": None, "git_dirty": None,
            "version_sha256": sha256(version.read_bytes()).hexdigest() if version.is_file() else None}


def process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION only.
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied is not proof of death.
        try:
            code = wintypes.DWORD()
            return not api.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def junit_result(path: Path, exit_code: int, redactor: Redactor) -> tuple[dict, bytes]:
    """Parse actual testcase nodes, not just exit 0 or pytest's console text."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_REPORT:
        return {"status": "FAIL", "reason": "Brak poprawnego raportu JUnit; nie ustalono wyniku testów.",
                "counts": {}}, b""
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Niedozwolona deklaracja XML")
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Niepoprawny XML raportu JUnit") from exc
    tests = list(tree.iter("testcase"))
    counts = Counter({"passed": 0, "failed": 0, "errors": 0, "skipped": 0})
    details = []
    for test in tests:
        outcome = "failed" if test.find("failure") is not None else "errors" if test.find("error") is not None else "skipped" if test.find("skipped") is not None else "passed"
        counts[outcome] += 1
        if outcome != "passed":
            node = test.find("failure") if outcome == "failed" else test.find("error") if outcome == "errors" else test.find("skipped")
            details.append({"test": test.get("name"), "outcome": outcome,
                            "message": redactor.text(str(node.get("message", "")) if node is not None else "")[:2000]})
    if counts["failed"] or counts["errors"] or exit_code not in {0, 5}:
        status, reason = "FAIL", "Testy zgłosiły niepowodzenie. Sprawdź JUnit i log tego przebiegu."
    elif not tests:
        status, reason = "SKIPPED", "Nie zebrano żadnego testu. Sprawdź pliki i warunki kolekcji."
    elif counts["skipped"]:
        status, reason = "SKIPPED", "Część lub wszystkie testy pominięto; zakres nie został w pełni sprawdzony."
    else:
        status, reason = "PASS", "Wszystkie zebrane testy podtestu przeszły. Pełny odbiór pozostaje oddzielny."
    if details:
        reason += " " + " | ".join(d["test"] + ": " + (d["message"] or "nie ustalono; otwórz log") for d in details[:2])
    # Redact values through the parsed tree so replacement cannot corrupt XML.
    for node in tree.iter():
        node.text = redactor.text(node.text) if node.text else node.text
        node.tail = redactor.text(node.tail) if node.tail else node.tail
        for key, value in list(node.attrib.items()):
            node.set(key, redactor.text(value))
    return {"status": status, "reason": reason, "counts": dict(counts), "details": details}, ET.tostring(tree, encoding="utf-8", xml_declaration=True)


def summary(report: dict) -> dict:
    counts = dict(Counter(row["status"] for row in report["results"]))
    good = [r["title"] for r in report["results"] if r.get("full_gate") == "PASS"]
    subsets = [r["title"] for r in report["results"] if r["status"] == "PASS" and r.get("full_gate") != "PASS"]
    bad = [r["title"] for r in report["results"] if r["status"] in {"FAIL", "TIMEOUT"}]
    unknown = [r["title"] + ": " + r.get("reason", "nie ustalono") for r in report["results"]
               if r["status"] not in {"PASS", "FAIL", "TIMEOUT"}]
    return {"counts": counts, "full_gate_counts": dict(Counter(r.get("full_gate", "NOT_RUN") for r in report["results"])),
            "dziala": good, "zaliczony_zakres_bez_pelnego_odbioru": subsets,
            "nie_dziala": bad, "nie_sprawdzono": unknown,
            "co_dalej": "Otwórz szczegóły blokad, przygotuj wskazane zasoby i uruchom ponownie wybrane pozycje. Podtest PASS nie zalicza pełnego odbioru."}


def readable_report(report: dict) -> str:
    lines = ["TPA — raport przebiegu " + report["run_id"],
             "Wersja: " + report["source"]["version"],
             "Źródło: " + str(report["source"].get("git_sha") or "nie ustalono"),
             "Interpreter: " + str(report.get("python", "nie ustalono")),
             "Początek: " + report["started_utc"], "Koniec: " + str(report.get("finished_utc") or "w toku"), ""]
    for result in report["results"]:
        lines += [result["status"] + " • " + result["title"],
                  "Co uruchomiono: " + " ".join(result.get("command", [])),
                  "Oczekiwano: " + result["expected"],
                  "Zaobserwowano: " + result.get("reason", "nie ustalono"),
                  "Czas / kod: " + str(result.get("duration_seconds")) + " s / " + str(result.get("exit_code")),
                  "Pełna bramka: " + result.get("full_gate", "NOT_RUN")
                  + (" — osobny odbiór operatorski do wykonania; wynik podtestu pozostaje ważny"
                     if result.get("full_gate", "NOT_RUN") == "NOT_RUN" else ""),
                  "Dalej: " + result.get("next_step", "Otwórz log i raport JUnit."), ""]
    lines += ["POKRYCIE SCENARIUSZY: " + str(len(report["coverage_map"]))]
    for item in report["coverage_map"]:
        lines += [item["id"] + " • " + item["title"],
                  "Wykonanie: " + item.get("execution_status", "NOT_RUN") + " • pełny odbiór: " + item.get("full_gate", "NOT_RUN")
                  + (" (do potwierdzenia przez operatora)" if item.get("full_gate", "NOT_RUN") == "NOT_RUN" else ""), item["limitations"]]
    lines += ["", "Podsumowanie:", json.dumps(summary(report), ensure_ascii=False, indent=2)]
    return "\n".join(lines)


class RunStore:
    def __init__(self, root: Path, *, evidence_base: Path | None = None):
        self.root = root.resolve()
        self.base = (operator_state_dir("jazn_studio_tpa", root, per_system=True)
                     if evidence_base is None else validate_operator_path(
                         evidence_base, root, directory=True,
                         allow_acceptance_operator=os.environ.get("JAZN_STUDIO_ACCEPTANCE_PROFILE") == "isolated"))
        self.redactor = Redactor()
        self.history_errors: list[str] = []

    def folder(self, run_id: str) -> Path:
        if not re.fullmatch(r"run-[0-9a-f]{32}", run_id):
            raise ValueError("Nieprawidłowy identyfikator przebiegu")
        target = safe_child(self.base, run_id)
        validate_operator_path(target, self.root, directory=True,
                               allow_acceptance_operator=os.environ.get("JAZN_STUDIO_ACCEPTANCE_PROFILE") == "isolated")
        return target

    def create(self, case_ids: tuple[str, ...], python: str, environment: dict, *,
               catalogue: list[dict] | None = None, source: dict | None = None,
               execution: str = "regression") -> dict:
        report = self.prepare(case_ids, python, environment, catalogue=catalogue, source=source, execution=execution)
        self.begin(report)
        return report

    def prepare(self, case_ids: tuple[str, ...], python: str, environment: dict, *,
                catalogue: list[dict] | None = None, source: dict | None = None,
                execution: str = "regression") -> dict:
        """Build the existing run contract without creating/writing evidence."""
        if execution not in {"regression", "pytest", "live", "sandbox"}:
            raise ValueError("Nieprawidłowy wykonawca przebiegu")
        definitions = execution_map() if catalogue is None else catalogue
        mapping = {c["id"]: c for c in definitions}
        if (len(mapping) != len(definitions) or any(
                not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", key)
                or not all(isinstance(row.get(field), str) for field in ("title", "expected", "steps", "category", "executor", "mode", "limitations"))
                or not all(isinstance(row.get(field), list) and all(isinstance(item, str) for item in row[field]) for field in ("files", "requirements"))
                for key, row in mapping.items())):
            raise ValueError("Nieprawidłowy katalog wymaganego zakresu")
        if not case_ids or len(case_ids) != len(set(case_ids)) or set(case_ids) - mapping.keys():
            raise ValueError("Wybierz znane, niepowtarzające się scenariusze")
        run_id = "run-" + uuid.uuid4().hex
        report = {"schema_version": SCHEMA, "run_id": run_id, "source": source_identity(self.root) if source is None else source,
                  "python": python, "environment": environment, "selected": list(case_ids), "execution": execution,
                  "owner_pid": os.getpid(), "started_utc": utc(), "finished_utc": None,
                  "coverage_map": definitions, "artifacts": [], "results": [
                      {"case_id": key, "title": mapping[key]["title"], "expected": mapping[key]["expected"],
                       "status": "QUEUED", "reason": "Oczekuje na wykonanie.", "full_gate": "NOT_RUN",
                       "coverage": "regression_subset", "exit_code": None, "duration_seconds": None,
                       "next_step": "Uruchom podtest; potem wykonaj kroki odbioru wspomaganego."} for key in case_ids]}
        # Freeze only the same redacted contract that later snapshots/receipts
        # use. Parametrized pytest nodeids can themselves contain credentials.
        report = redact(report, self.redactor)
        return report

    def begin(self, report: dict) -> None:
        """Persist the initial manifest and snapshot before any execution."""
        self._validate(report, report["run_id"])
        self.base.mkdir(parents=True, exist_ok=True)
        self.folder(report["run_id"]).mkdir(exist_ok=False)
        from .test_evidence_archive import initialize
        initialize(self.folder(report["run_id"]), report)
        report["evidence_schema"] = "jazn_test_evidence/v1"
        self.save(report)

    def save(self, report: dict) -> None:
        folder = self.folder(report["run_id"])
        results = {r["case_id"]: r for r in report["results"]}
        for case in report["coverage_map"]:
            row = results.get(case["id"], {})
            case.update(execution_status=row.get("status", "NOT_RUN"),
                        full_gate=row.get("full_gate", "NOT_RUN"),
                        executed_scope=row.get("coverage", "NOT_RUN"))
        clean = redact(report, self.redactor)
        clean["summary"] = summary(clean)
        if report.get("evidence_schema") == "jazn_test_evidence/v1":
            from .test_evidence_archive import save_snapshot
            key = save_snapshot(folder, clean, self.redactor)
            report["evidence_snapshot"] = clean["evidence_snapshot"] = key
        # Commit an immutable complete revision BEFORE replacing the compatibility
        # files. A crash can leave an orphan temp file, never erase a revision.
        revision = safe_child(folder, "revision-" + uuid.uuid4().hex + ".json")
        temporary = safe_child(folder, revision.name + ".tmp")
        payload = json.dumps({"schema": "jazn_tpa_revision/v1", "saved_utc": utc(),
                              "report": clean}, ensure_ascii=False, indent=2) + "\n"
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, revision)
        for name, content in (("report.json", json.dumps(clean, ensure_ascii=False, indent=2)),
                              ("report.txt", readable_report(clean))):
            target = safe_child(folder, name)
            temp = safe_child(folder, name + ".tmp-" + uuid.uuid4().hex)
            try:
                with temp.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)

    def load(self, run_id: str) -> dict:
        path = safe_child(self.folder(run_id), "report.json")
        if path.stat().st_size > MAX_REGISTERED_INDEX:
            raise ValueError("Raport przekracza limit")
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        if path.stat().st_size > MAX_REPORT and report.get("execution") != "pytest":
            raise ValueError("Raport TPA przekracza limit")
        return self._validate(report, run_id)

    @staticmethod
    def _validate(report: Any, run_id: str) -> dict:
        if (not isinstance(report, dict) or report.get("schema_version") != SCHEMA
                or report.get("run_id") != run_id or not isinstance(report.get("results"), list)
                or not isinstance(report.get("source"), dict) or not isinstance(report["source"].get("version"), str)
                or not isinstance(report.get("started_utc"), str) or not isinstance(report.get("artifacts"), list)
                or any(not isinstance(n, str) for n in report["artifacts"])
                or not isinstance(report.get("coverage_map"), list)
                or any(not isinstance(c, dict) or not all(isinstance(c.get(k), str) for k in ("id", "title", "limitations")) for c in report["coverage_map"])
                or any(not isinstance(r, dict) or r.get("status") not in STATES
                       or not all(isinstance(r.get(k), str) for k in ("case_id", "title", "expected", "reason"))
                       or not isinstance(r.get("command", []), list) or any(not isinstance(a, str) for a in r.get("command", [])) for r in report["results"])):
            raise ValueError("Nieprawidłowy raport TPA")
        return report

    def revisions(self, run_id: str) -> list[dict]:
        """Read committed revisions only. Incomplete .tmp files are not evidence."""
        result = []
        for path in self.folder(run_id).glob("revision-*.json"):
            path = safe_child(path.parent, path.name)
            if path.stat().st_size > MAX_REGISTERED_INDEX:
                raise ValueError("Rewizja przekracza limit")
            value = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("schema") != "jazn_tpa_revision/v1"
                    or not isinstance(value.get("saved_utc"), str)):
                raise ValueError("Nieprawidłowa rewizja TPA")
            self._validate(value.get("report"), run_id)
            result.append(value)
        return sorted(result, key=lambda v: v["saved_utc"], reverse=True)

    def recover_report(self, run_id: str) -> dict:
        """Explicit repair, preserving corrupt compatibility files byte-for-byte.

        Does not replay a request or touch runtime processes. The caller can then
        use recover_interrupted to classify work whose owner is known dead.
        """
        revisions = self.revisions(run_id)
        if not revisions:
            raise ValueError("Brak kompletnej rewizji do odzyskania")
        folder = self.folder(run_id)
        for name in ("report.json", "report.txt"):
            path = safe_child(folder, name)
            if path.exists():
                backup = safe_child(folder, "recovered-" + uuid.uuid4().hex + "-" + name)
                with backup.open("xb") as stream:
                    stream.write(path.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
        report = revisions[0]["report"]
        self.save(report)
        return report

    def history(self) -> list[dict]:
        self.history_errors = []
        if not self.base.exists():
            return []
        result = []
        for path in sorted(self.base.glob("run-*"), reverse=True):
            if path.is_dir() and not path.is_symlink() and not path.is_junction():
                try:
                    result.append(self.load(path.name))
                except (OSError, ValueError, TypeError) as exc:
                    self.history_errors.append(path.name + ": " + type(exc).__name__ + "; zachowano plik, nie ustalono wyniku.")
        return sorted(result, key=lambda r: r["started_utc"], reverse=True)

    def recover_interrupted(self) -> None:
        for report in self.history():
            if report.get("finished_utc"):
                continue
            pid = report.get("owner_pid")
            try:
                if not isinstance(pid, int) or pid <= 0:
                    raise ProcessLookupError()
                if not process_alive(pid):
                    raise ProcessLookupError()
            except ProcessLookupError:
                for row in report["results"]:
                    if row["status"] in {"QUEUED", "RUNNING"}:
                        row.update(status="INTERRUPTED", reason="Aplikacja zakończyła się przed zapisaniem wyniku. Uruchom ponownie.")
                report["finished_utc"] = utc()
                self.save(report)
            except PermissionError:
                continue  # Insufficient evidence that the owning process ended.

    def export_zip(self, report: dict, destination: Path) -> Path:
        destination = Path(destination)
        if not destination.is_absolute() or destination.suffix.lower() != ".zip":
            raise ValueError("Wybierz nowy plik ZIP przez ścieżkę absolutną")
        for part in (destination, *destination.parents):
            if part.is_symlink() or part.is_junction():
                raise ValueError("Eksport nie dopuszcza dowiązań")
        validate_operator_path(destination, self.root)
        folder = self.folder(report["run_id"])
        # Only explicitly owned text evidence, never rglob/runtime/SQLite/MEMORY.
        names = {"report.json", "report.txt", *report.get("artifacts", [])}
        content = {}
        for name in sorted(names):
            path = safe_child(folder, name)
            if path.suffix.lower() not in {".json", ".txt", ".xml", ".log"} or not path.is_file():
                raise ValueError("Brak lub niedozwolony plik dowodu: " + name)
            if path.stat().st_size > MAX_REPORT:
                raise ValueError("Dowód przekracza limit eksportu")
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                content[name] = json.dumps(redact(json.loads(text), self.redactor), ensure_ascii=False, indent=2)
            elif path.suffix.lower() == ".xml":
                try:
                    tree = ET.fromstring(text)
                except ET.ParseError as exc:
                    raise ValueError("Uszkodzony XML dowodu; eksport nie został wykonany") from exc
                for node in tree.iter():
                    node.text = self.redactor.text(node.text) if node.text else node.text
                    node.tail = self.redactor.text(node.tail) if node.tail else node.tail
                    for key, value in list(node.attrib.items()):
                        node.set(key, self.redactor.text(value))
                content[name] = ET.tostring(tree, encoding="unicode")
            else:
                content[name] = self.redactor.text(text)
        try:
            with destination.open("xb") as output:
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, text in content.items():
                        archive.writestr(name, text)
        except Exception:
            # No removal of pre-existing destinations or resources owned by another run.
            raise
        return destination
