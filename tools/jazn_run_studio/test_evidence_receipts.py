"""Read-only projection of immutable pytest receipts after an unsealed run.

No process liveness is inferred: an unfinished phase may still be executing.
Only complete setup/call/teardown evidence can establish a scenario PASS.
This projection is never a sealed snapshot or release acceptance.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from .test_evidence_archive import MAX_DOCUMENT, MAX_FILES, MAX_TOTAL, _json, _read, scenario_text
from .tpa_reports import Redactor, safe_child

_NAME = re.compile(r"(pytest-[0-9a-f]{32})-[0-9a-f]{32}\.json")
_PHASES = ("setup", "call", "teardown")
_STATUSES = {"RUNNING", "PASS", "FAIL", "ERROR", "SKIPPED"}


def recover_receipts(folder: Path, sealed: dict) -> dict:
    """Verify bounded receipts against an already verified immutable snapshot.

    The returned view is memory-only; no source report, receipt, index or seal
    is repaired. Finalized snapshots remain authoritative and untouched.
    """
    if sealed["summary"].get("finished_utc"):
        return sealed
    names = []
    for path in folder.glob("pytest-*.json"):
        if len(names) >= MAX_FILES:
            raise ValueError("Zbyt wiele potwierdzeń pytest")
        if not _NAME.fullmatch(path.name):
            raise ValueError("Nieprawidłowa nazwa potwierdzenia pytest")
        names.append(path.name)
    if not names:
        return sealed
    definitions = {row["scenario_id"]: row for row in sealed["manifest"]["scenarios"]}
    # Older manifests predate pre-freeze redaction. Apply only the stable
    # canonical syntax rules, never today's environment-secret values.
    redactor = Redactor({})
    policy = sealed["manifest"].get("redaction_policy")
    if policy not in {None, "canonical-before-freeze/v1"}:
        raise ValueError("Nieznana polityka redakcji potwierdzeń")
    legacy = policy is None
    selected = set(sealed["manifest"]["selected"])
    run_id = sealed["summary"]["run_id"]
    source = sealed["summary"]["source"]
    binding = safe_child(folder, "execution-source.json")
    if binding.exists() and json.loads(_read(binding)) != source:
        raise ValueError("Źródło wykonania niezgodne z rewizją")
    groups: dict[str, dict[str, tuple[dict, str]]] = {}
    proof = {}
    total = sum(map(len, sealed["files"].values()))
    for name in sorted(names):
        raw = _read(safe_child(folder, name))
        txt = _read(safe_child(folder, name[:-5] + ".txt"))
        total += len(raw) + len(txt)
        if total > MAX_TOTAL:
            raise ValueError("Potwierdzenia przekraczają limit odczytu")
        envelope = json.loads(raw)
        event = envelope.get("event")
        if not isinstance(event, dict) or envelope.get("sha256") != sha256(_json(event)).hexdigest():
            raise ValueError("Niezgodny SHA256 potwierdzenia pytest")
        result = event.get("result")
        match = _NAME.fullmatch(name)
        assert match is not None
        case_id = match.group(1)
        phase = event.get("phase")
        definition = definitions.get(case_id, {})
        if (event.get("schema") != "jazn_pytest_receipt/v1" or event.get("run_id") != run_id
                or event.get("source") != source or case_id not in selected
                or definition.get("executor") != "pytest" or phase not in _PHASES
                or not isinstance(result, dict) or result.get("case_id") != case_id
                or result.get("title") != (redactor.text(definition.get("name", "")) if legacy else definition.get("name"))
                or result.get("expected") != (redactor.text(definition.get("pass_criteria", "")) if legacy else definition.get("pass_criteria"))
                or result.get("status") not in _STATUSES or result.get("full_gate") != "NOT_RUN"
                or not isinstance(result.get("reason"), str)
                or not isinstance(event.get("saved_utc"), str)
                or not isinstance(result.get("started_utc"), str)):
            raise ValueError("Potwierdzenie niezgodne z kontraktem przebiegu")
        duration = result.get("duration_seconds")
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or duration < 0 or duration > 10 * 366 * 86400 or not math.isfinite(duration)):
            raise ValueError("Nieprawidłowy czas wykonania")
        if phase == "teardown" and not isinstance(result.get("finished_utc"), str):
            raise ValueError("Brak potwierdzenia końca teardown")
        expected_txt = (result["title"] + "\n" + result["status"] + "\n" + result["reason"] + "\n").encode("utf-8")
        comparable_txt = redactor.text(txt.decode("utf-8")).encode("utf-8") if legacy else txt
        if comparable_txt != expected_txt:
            raise ValueError("Niezgodna para TXT/JSON potwierdzenia")
        phases = groups.setdefault(case_id, {})
        if phase in phases:
            raise ValueError("Niejednoznaczne powtórzenie fazy pytest")
        phases[phase] = (event, name)
        proof["receipts/" + name] = raw
    view = deepcopy(sealed)
    files = view["files"]
    files.update(proof)
    latest_saved = []
    for row in view["results"]:
        case_id = row["scenario_id"]
        row["name"] = redactor.text(definitions[case_id]["name"])
        phases = groups.get(case_id)
        if phases is None:
            if case_id in selected and row["execution_status"] in {"QUEUED", "RUNNING"}:
                row.update(execution_status="NOT_RUN", reason="Brak potwierdzenia wykonania w niezamkniętym przebiegu")
        else:
            ordered = [phases[phase] for phase in _PHASES if phase in phases]
            times = [event["saved_utc"] for event, _ in ordered]
            starts = {event["result"]["started_utc"] for event, _ in ordered}
            if times != sorted(times) or len(starts) != 1:
                raise ValueError("Niezgodna kolejność lub tożsamość faz pytest")
            latest_saved.extend(times)
            last = ordered[-1][0]["result"]
            statuses = [event["result"]["status"] for event, _ in ordered]
            failed = [event["result"] for event, _ in ordered if event["result"]["status"] in {"FAIL", "ERROR"}]
            complete = set(phases) == set(_PHASES) and bool(last.get("finished_utc"))
            if failed:
                outcome = failed[-1]
                status, reason = outcome["status"], outcome["reason"]
            elif "SKIPPED" in statuses:
                status, reason = "SKIPPED", last["reason"]
            elif complete and statuses == ["RUNNING", "PASS", "PASS"]:
                status, reason = "PASS", last["reason"]
            else:
                status, reason = "RUNNING", "Niepotwierdzone zakończenie setup/call/teardown; przebieg może nadal działać"
            row.update(execution_status=status, full_gate_status="NOT_RUN", reason=reason,
                       started_utc=last["started_utc"], finished_utc=last.get("finished_utc") if complete else None,
                       duration_seconds=last["duration_seconds"], exit_code=last.get("exit_code"),
                       artifacts=["receipts/" + name for _, name in ordered])
        files["results/" + case_id + ".json"] = _json(row)
        files["scenarios/" + case_id + ".txt"] = scenario_text(row).encode("utf-8")
    summary = view["summary"]
    summary.update(receipt_recovery="UNSEALED", receipt_count=len(names),
                   saved_utc=max(latest_saved), counts=dict(Counter(row["execution_status"] for row in view["results"])),
                   release_status="RELEASE_NOT_ACCEPTED")
    files["summary.json"] = _json(summary)
    files["summary.txt"] = ("NIEZAMKNIĘTY PRZEBIEG — odczyt potwierdzeń, bez naprawy źródeł\n" + _json(summary).decode()).encode("utf-8")
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_TOTAL or any(len(raw) > MAX_DOCUMENT for raw in files.values()):
        raise ValueError("Odzyskany widok przekracza limit historii")
    return view
