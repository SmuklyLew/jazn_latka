from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .tui_common import HAS_PROMPT_TOOLKIT, ask_text, message, run_dialog
from .unified_memory import UnifiedMemoryDatabase

radiolist_dialog = None
if HAS_PROMPT_TOOLKIT:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import radiolist_dialog


def _radio_dialog(*, title: str, text: str, values: list[tuple[str, str]]) -> Any:
    if radiolist_dialog is None:
        raise RuntimeError("prompt_toolkit_radiolist_unavailable")
    return radiolist_dialog(title=title, text=text, values=values)


def _candidate_label(item: dict) -> str:
    status = str(item.get("status") or "?")
    truth = str(item.get("truth_status") or "?")
    title = str(item.get("title") or "(bez tytułu)").replace("\n", " ")[:80]
    return f"[{status}] [{truth}] {title} | ważność={float(item.get('importance') or 0):.2f} pewność={float(item.get('confidence') or 0):.2f}"


def _candidate_text(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _edit_candidate(store: UnifiedMemoryDatabase, candidate_id: str) -> None:
    current = store.get_candidate(candidate_id)
    title = ask_text("Edycja kandydata", "Tytuł:", str(current.get("title") or ""))
    if title is None:
        return
    summary = ask_text("Edycja kandydata", "Treść / podsumowanie:", str(current.get("summary") or ""))
    if summary is None:
        return
    truth = ask_text("Edycja kandydata", "Rodzaj prawdy:", str(current.get("truth_status") or "inferred"))
    confidence = ask_text("Edycja kandydata", "Pewność 0–1:", str(current.get("confidence") or 0.5))
    importance = ask_text("Edycja kandydata", "Ważność 0–1:", str(current.get("importance") or 0.5))
    domains = ask_text("Edycja kandydata", "Domeny oddzielone przecinkami:", ", ".join(current.get("domains") or []))
    edited_by = ask_text("Edycja kandydata", "Kto edytuje:", "Krzysztof")
    reason = ask_text("Edycja kandydata", "Powód zmiany:", "Ręczna korekta w Memory Rebuild v2.4")
    if not edited_by or not reason:
        message("Edycja kandydata", "Edycja anulowana: wymagane są osoba i powód.")
        return
    changes = {
        "title": title,
        "summary": summary,
        "truth_status": truth,
        "confidence": float(confidence or 0.5),
        "importance": float(importance or 0.5),
        "domains_json": [part.strip() for part in (domains or "").split(",") if part.strip()],
    }
    updated = store.edit_candidate(candidate_id, changes, edited_by=edited_by, reason=reason)
    message("Kandydat zapisany", _candidate_text(updated))


def _review_candidate(store: UnifiedMemoryDatabase, candidate_id: str) -> None:
    decision = run_dialog(_radio_dialog(
        title="Decyzja o kandydacie",
        text="Zatwierdzenie tworzy doświadczenie L1. Nie promuje automatycznie do L2 ani L3.",
        values=[
            ("approve", "Zatwierdź jako doświadczenie L1"),
            ("reject", "Odrzuć"),
            ("pending", "Pozostaw / przywróć do przeglądu"),
            ("cancel", "Anuluj"),
        ],
    ))
    if decision in {None, "cancel"}:
        return
    reviewed_by = ask_text("Decyzja", "Kto podejmuje decyzję:", "Krzysztof")
    reason = ask_text("Decyzja", "Uzasadnienie:", "Ręczny przegląd źródeł")
    if not reviewed_by or not reason:
        message("Decyzja", "Operacja anulowana: wymagane są osoba i uzasadnienie.")
        return
    result = store.review_candidate(candidate_id, decision=decision, reviewed_by=reviewed_by, reason=reason)
    message("Decyzja zapisana", json.dumps(result, ensure_ascii=False, indent=2, default=str))


def candidate_menu(database: Path) -> None:
    store = UnifiedMemoryDatabase(database)
    while True:
        status = run_dialog(_radio_dialog(
            title="Kandydaci pamięci",
            text="Wybierz listę. Surowe rozmowy i dzienniki pozostają niezmienne; edycja zapisuje rewizję.",
            values=[
                ("pending_review", "Do przeglądu"),
                ("approved", "Zatwierdzone"),
                ("rejected_operator", "Odrzucone ręcznie"),
                ("merged", "Połączone"),
                ("all", "Wszystkie"),
                ("generate", "Wygeneruj / odśwież kandydatów"),
                ("back", "Wróć"),
            ],
        ))
        if status in {None, "back"}:
            return
        if status == "generate":
            result = store.generate_candidates(chats=True, journal=True)
            message("Generowanie kandydatów", json.dumps(result, ensure_ascii=False, indent=2, default=str))
            continue
        items = store.list_candidates(status=status, limit=500)
        if not items:
            message("Kandydaci", "Brak kandydatów w tej grupie.")
            continue
        selected = run_dialog(_radio_dialog(
            title="Lista kandydatów",
            text="Enter: otwórz wpis. Esc: wróć.",
            values=[(str(item["candidate_id"]), _candidate_label(item)) for item in items],
        ))
        if not selected:
            continue
        while True:
            item = store.get_candidate(selected)
            action = run_dialog(_radio_dialog(
                title=str(item.get("title") or "Kandydat"),
                text=(str(item.get("summary") or "")[:1200] + "\n\n"
                      f"Status: {item.get('status')} | Prawda: {item.get('truth_status')}\n"
                      f"Dowody: {len(item.get('evidence') or [])} | Rewizje: {len(item.get('revisions') or [])}"),
                values=[
                    ("preview", "Pełny podgląd techniczny"),
                    ("edit", "Edytuj treść i klasyfikację"),
                    ("review", "Zatwierdź / odrzuć / przywróć"),
                    ("back", "Wróć do listy"),
                ],
            ))
            if action in {None, "back"}:
                break
            if action == "preview":
                message("Szczegóły kandydata", _candidate_text(item))
            elif action == "edit":
                _edit_candidate(store, selected)
            elif action == "review":
                _review_candidate(store, selected)


__all__ = ["candidate_menu"]
