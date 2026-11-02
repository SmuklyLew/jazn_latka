"""Canonical TPA result validation/artifact persistence, away from GUI handlers."""
import json
import time

from .tpa_reports import RunStore, junit_result, safe_child, utc


def finish_test(store: RunStore, report: dict, index: int, context: dict, redactor) -> dict:
    row = report["results"][index]
    code, reason = context["code"], context["reason"]
    try:
        result, xml = junit_result(context["junit"], code, redactor)
    except (OSError, ValueError) as exc:
        result, xml = {"status": "FAIL", "reason": "Niepoprawny JUnit: " + type(exc).__name__}, b""
    if reason or not context["normal"]:
        result.update(status={"cancelled": "CANCELLED", "timeout": "TIMEOUT", "process_start_failed": "BLOCKED"}.get(reason, "INTERRUPTED"),
                      reason={"cancelled": "Anulowano własny proces testowy.", "timeout": "Przekroczono limit czasu.",
                              "process_start_failed": "Nie udało się uruchomić procesu."}.get(reason, "Proces przerwany lub przekroczony limit wyjścia; brak pełnego dowodu."))
    row.update(result, exit_code=code, duration_seconds=round(time.monotonic() - context["started"], 3),
               finished_utc=utc(), log=context["log_name"])
    try:
        folder = store.folder(report["run_id"])
        safe_child(folder, context["log_name"]).write_text(context["buffer"], encoding="utf-8")
        report["artifacts"].append(context["log_name"])
        if xml:
            name = row["case_id"] + ".xml"
            safe_child(folder, name).write_bytes(xml)
            row["junit"] = name
            report["artifacts"].append(name)
    except (OSError, ValueError):
        report["persistence_error"] = "Nie zapisano logu/JUnit tego przebiegu. Wynik nie jest trwałym dowodem."
        row.update(status="BLOCKED", reason=report["persistence_error"])
    store.save(report)
    return report


def finish_live(store: RunStore, report: dict, index: int, context: dict) -> dict:
    row, result = report["results"][index], context["result"]
    status = result.get("status", "INTERRUPTED")
    if status not in {"PASS", "FAIL", "BLOCKED", "TIMEOUT", "CANCELLED", "INTERRUPTED"}:
        status = "FAIL"
    if context["reason"] in {"cancelled", "timeout"}:
        status = "CANCELLED" if context["reason"] == "cancelled" else "TIMEOUT"
    reason = result.get("reason", "Proces odbioru zakończył się bez poprawnego dowodu.")
    if status == "PASS" and context["live_exit_code"] != 0:
        status, reason = "FAIL", "Proces odbioru zakończył się niezerowym kodem wyjścia; wynik PASS nie jest wiarygodny."
    if context["code"] or context["cleanup"].get("ok") is not True:
        status = "BLOCKED"
        reason += " Nie potwierdzono bezpiecznego sprzątnięcia. Zachowano własny staging i dowód właściciela."
    row.update(status=status, reason=reason, exit_code=context["live_exit_code"], cleanup_exit_code=context["code"],
               duration_seconds=round(time.monotonic() - context["started"], 3), finished_utc=utc(),
               full_gate="NOT_RUN", log=context["log_name"])
    try:
        folder = store.folder(report["run_id"])
        safe_child(folder, context["log_name"]).write_text(context["buffer"], encoding="utf-8")
        name = row["case_id"] + ".live.json"
        safe_child(folder, name).write_text(json.dumps({"result": result, "cleanup": context["cleanup"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        report["artifacts"].extend([name, context["log_name"]])
        if row["status"] == "PASS":
            from .tpa_current_state import evidence_errors
            errors = evidence_errors(store, report, row)
            if errors:
                row.update(status="BLOCKED", reason=" ".join(errors))
    except (OSError, ValueError):
        report["persistence_error"] = "Nie zapisano dowodów odbioru izolowanego."
        row.update(status="BLOCKED", full_gate="NOT_RUN", reason=report["persistence_error"])
    store.save(report)
    return report
