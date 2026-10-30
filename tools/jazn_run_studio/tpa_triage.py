"""Read-only TPA acceptance triage. Never promotes a subtest to full_gate PASS."""
from __future__ import annotations

from collections import Counter
from typing import Any

NOWE = "NOWE"
DO_POWTORZENIA = "DO_POWTORZENIA"
NIEAKTUALNE = "NIEAKTUALNE"
ZALICZONE = "ZALICZONE"
TRIAGE_LABELS = {
    NOWE: "Nowe",
    DO_POWTORZENIA: "Do powtórzenia",
    NIEAKTUALNE: "Nieaktualne dowody",
    ZALICZONE: "Odebrane",
}

# Manual operator gates are guidance, not executable pytest scenarios.
# They intentionally do not alter the canonical 22-case TPA coverage map.
LOCAL_GATES = (
    (NOWE, "P2 · PTY Windows / ConPTY", "Windows PC: rzeczywisty interaktywny PowerShell, wejście, resize, Ctrl+C, zamknięcie własnej sesji; bez ingerencji w daemon."),
    (NOWE, "P2 · PTY Linux", "PTY Bash: start, terminal echo, zmiana wielkości, EOF, ponowne uruchomienie; test kontrolowany."),
    (NOWE, "P3 · Panel usług", "Na Windows sprawdź wykrywanie Ollama/MCP/cloudflared oraz Start/Stop/Restart tylko procesów należących do JSS; PID nie dowodzi readiness."),
    (NOWE, "P4 · 12 natywnych Studiów", "Porównaj każdą operację Qt z klasycznym Studio, w tym błędy, anulowanie i bezpieczne ścieżki. Brak funkcji = BLOCKED."),
    (NOWE, "P5 · EXE offline i AV", "Oddzielna Windows VM bez sieci: manifest, źródłowy SHA, onedir, uruchomienie, kwarantanna AV, log, zrzuty i raport."),
    (NOWE, "P5 · Fizyczne DPI i dostępność", "Windows 100/150/200%, wszystkie motywy i dialogi, Tab/fokus, kontrast, min. 860×580."),
    (DO_POWTORZENIA, "P5 · chat-resume", "Ponów rzeczywistą turę Ollama na aktualnym SHA; ACK po wyświetleniu, jedna finalizacja, cleanup.ok=true."),
    (DO_POWTORZENIA, "P5 · daemon-restart", "Ponów odbiór z rzeczywistym lokalnym daemonem, zachowaniem session_id i nową tożsamością instancji."),
    (NIEAKTUALNE, "Historyczne dowody poprzednich wydań", "Stare SHA/wersje i zrzuty nie stanowią odbioru aktualnej gałęzi. Zachowaj historię; nie przepisuj PASS."),
)


def _source_relation(prior: dict[str, Any], current: dict[str, Any]) -> str:
    """same / stale / uncertain, based only on positive source evidence."""
    if prior.get("version") != current.get("version"):
        return "stale"
    for field in ("version_sha256", "git_sha"):
        left, right = prior.get(field), current.get(field)
        if isinstance(left, str) and left and isinstance(right, str) and right and left != right:
            return "stale"
    old_sha, new_sha = prior.get("git_sha"), current.get("git_sha")
    if old_sha and not new_sha:
        return "uncertain"
    old_file, current_file = prior.get("version_sha256"), current.get("version_sha256")
    if not old_file or not current_file:
        return "uncertain"
    if prior.get("git_dirty") is True or current.get("git_dirty") is True:
        return "uncertain"
    return "same"


def triage_cases(cases: list[dict[str, Any]], history: list[dict[str, Any]],
                 current: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Derive operator actions from evidence, without modifying historical reports."""
    output: dict[str, dict[str, str]] = {}
    for case in cases:
        key = case["id"]
        matching = [
            (run, row) for run in history if isinstance(run, dict)
            for row in run.get("results", []) if isinstance(row, dict) and row.get("case_id") == key
        ]
        matching.sort(key=lambda pair: str(pair[0].get("started_utc", "")), reverse=True)
        if not matching:
            output[key] = {"state": NOWE, "reason": "Brak zapisanego odbioru tego scenariusza."}
            continue
        run, row = matching[0]
        relation = _source_relation(run.get("source", {}), current)
        if relation == "stale":
            output[key] = {"state": NIEAKTUALNE, "reason": "Dowód pochodzi z wcześniejszej wersji lub SHA; wykonaj ponownie na obecnym źródle."}
        elif (relation == "same" and row.get("status") == "PASS"
              and row.get("full_gate") == "PASS"):
            output[key] = {"state": ZALICZONE, "reason": "Podtest i odbiór operatorski potwierdzone dla bieżącego źródła."}
        else:
            explanation = ("Nie można potwierdzić tożsamości źródła; odśwież kontrolę Git/SYSTEM."
                           if relation == "uncertain" else
                           "Wynik: " + str(row.get("status", "NOT_RUN")) +
                           ", pełny odbiór: " + str(row.get("full_gate", "NOT_RUN")) + ".")
            output[key] = {"state": DO_POWTORZENIA, "reason": explanation + " Wymagany aktualny odbiór."}
    return output


def triage_summary(triage: dict[str, dict[str, str]]) -> dict[str, int]:
    return dict(Counter(row["state"] for row in triage.values()))


def local_queue_text(triage: dict[str, dict[str, str]]) -> str:
    lines = [
        "TPA — odbiory lokalne (instrukcje, nie automatyczne PASS)",
        "Nie uruchamiaj na aktywnej MEMORY, obcym PID ani produkcyjnym daemonie.",
        "Podtest PASS ≠ full_gate PASS. Starszy dowód pozostaje zachowany.",
        "",
        "STAN 22 SCENARIUSZY",
    ]
    for key, count in sorted(triage_summary(triage).items()):
        lines.append(f"{TRIAGE_LABELS.get(key, key)}: {count}")
    lines.append("")
    lines.append("P2–P5 — NOWE / DO POWTÓRZENIA / NIEAKTUALNE")
    for state, title, instructions in LOCAL_GATES:
        lines.append(f"\n[{TRIAGE_LABELS[state]}] {title}\n{instructions}")
    return "\n".join(lines)
