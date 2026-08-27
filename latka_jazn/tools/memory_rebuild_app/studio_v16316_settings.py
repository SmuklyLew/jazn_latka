from __future__ import annotations

"""Editable, persistent Memory Rebuild Studio settings for package v16.3.16."""

from pathlib import Path
from typing import Any, Sequence
import json
import os

from .models import DEFAULT_SETTINGS
from .project_store import ProjectStore
from .settings import (
    MemoryRebuildSettings,
    MemoryRebuildStudioPreferences,
    load_tool_settings,
    resolve_settings_path,
    save_tool_settings,
)
from .studio_p0 import StudioAction
from .studio_v16314 import StudioV16314State, _handle_action_v16314
from .themes import THEMES, get_theme, prompt_toolkit_style
from .tui import DIALOG_STYLE
from .tui_common import message


STUDIO_VERSION = "memory-rebuild-studio/v16.3.16"

PROJECT_LOCKED_SETTINGS = frozenset(
    {"automatic_experience_approval", "automatic_l2", "automatic_l3"}
)
PROJECT_RISKY_TRUE = frozenset(
    {"continue_on_error", "apply_reclassification", "force_topics", "system_acceptance"}
)
PROJECT_RISKY_FALSE = frozenset(
    {
        "verify_after_each",
        "full_validation",
        "create_backup",
        "audit_classifiers",
        "hash_sources_during_scan",
        "preserve_all_chat_branches",
        "preserve_exact_source_text",
    }
)

PROJECT_SETTING_LABELS: dict[str, str] = {
    "recursive_scan": "Skanuj podfoldery",
    "verify_after_each": "Weryfikuj po każdym etapie",
    "full_validation": "Pełna walidacja",
    "continue_on_error": "Kontynuuj po błędzie",
    "create_backup": "Twórz backup",
    "audit_classifiers": "Audyt klasyfikatorów",
    "reclassify_journal_dry_run": "Reklasyfikacja dziennika — dry-run",
    "apply_reclassification": "Zastosuj reklasyfikację",
    "analyse_topics": "Analizuj tematy",
    "force_topics": "Wymuś analizę tematów",
    "candidate_limit": "Limit kandydatów (0 = bez limitu)",
    "progress_every_conversations": "Raport postępu co N rozmów",
    "hash_sources_during_scan": "SHA-256 źródeł podczas skanu",
    "verify_zip_crc_during_scan": "CRC ZIP podczas skanu",
    "preserve_all_chat_branches": "Zachowaj wszystkie gałęzie rozmów",
    "preserve_exact_source_text": "Zachowaj dokładny tekst źródłowy",
    "automatic_experience_approval": "Automatyczna akceptacja experience",
    "automatic_l2": "Automatyczne L2",
    "automatic_l3": "Automatyczne L3",
}


def _yes_no(value: Any) -> str:
    return "TAK" if bool(value) else "NIE"


def _value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return _yes_no(value)
    return str(value)


def _dialog_choice(
    title: str,
    text: str,
    values: Sequence[tuple[Any, str]],
    *,
    default: Any = None,
) -> Any:
    from prompt_toolkit.shortcuts import radiolist_dialog

    return radiolist_dialog(
        title=title,
        text=text,
        values=list(values),
        default=default,
        style=DIALOG_STYLE,
    ).run()


def _dialog_input(title: str, text: str, default: str = "") -> str | None:
    from prompt_toolkit.shortcuts import input_dialog

    return input_dialog(
        title=title,
        text=text,
        default=default,
        style=DIALOG_STYLE,
    ).run()


def _dialog_confirm(title: str, text: str) -> bool:
    from prompt_toolkit.shortcuts import yes_no_dialog

    return bool(
        yes_no_dialog(
            title=title,
            text=text,
            yes_text="Tak",
            no_text="Nie",
            style=DIALOG_STYLE,
        ).run()
    )


def _runtime_lines(settings: MemoryRebuildSettings) -> list[str]:
    return [
        f"retrieval_limit: {settings.retrieval_limit}  [EDYTOWALNE 1..500]",
        f"min_lexical_score: {settings.min_lexical_score}  [EDYTOWALNE 0..1]",
        f"embeddings_enabled: {_yes_no(settings.embeddings_enabled)}  [EDYTOWALNE]",
        f"embedding_model: {_value(settings.embedding_model)}  [EDYTOWALNE]",
        f"require_fts5: {_yes_no(settings.require_fts5)}  [READ-ONLY — wymagane]",
        f"require_provenance: {_yes_no(settings.require_provenance)}  [READ-ONLY — wymagane]",
        f"automatic_l2: {_yes_no(settings.automatic_l2)}  [READ-ONLY / ZABLOKOWANE]",
        f"automatic_l3: {_yes_no(settings.automatic_l3)}  [READ-ONLY / ZABLOKOWANE]",
        f"automatic_activation: {_yes_no(settings.automatic_activation)}  [READ-ONLY / ZABLOKOWANE]",
    ]


def _project_lines(project: dict[str, Any] | None) -> list[str]:
    values = dict(DEFAULT_SETTINGS)
    extras: dict[str, Any] = {}
    if project:
        raw = dict(project.get("settings") or {})
        values.update({key: raw[key] for key in DEFAULT_SETTINGS if key in raw})
        extras = {
            key: value
            for key, value in raw.items()
            if key not in DEFAULT_SETTINGS and not key.startswith("_")
        }
    result: list[str] = []
    for key, default in DEFAULT_SETTINGS.items():
        value = values.get(key, default)
        marker = "[READ-ONLY / ZABLOKOWANE]" if key in PROJECT_LOCKED_SETTINGS else "[EDYTOWALNE]"
        if key in PROJECT_RISKY_TRUE or key in PROJECT_RISKY_FALSE:
            marker = "[EDYTOWALNE — wymaga potwierdzenia przy mniej bezpiecznej wartości]"
        result.append(f"{key}: {_value(value)}  {marker}")
    for key, value in sorted(extras.items()):
        if key == "unified_database_path":
            result.append(f"{key}: {_value(value)}  [READ-ONLY tutaj — zmień w „Baza docelowa”]")
        elif key in {"test04_acceptance_report", "system_acceptance"}:
            result.append(f"{key}: {_value(value)}  [EDYTOWALNE]")
        else:
            result.append(f"{key}: {_value(value)}  [READ-ONLY — rozszerzenie projektu]")
    return result


class StudioV16316State(StudioV16314State):
    """v16.3.14 Studio plus persistent settings and editing policy."""

    def __init__(
        self,
        *,
        database: str | Path,
        project_root: str | Path | None = None,
        project: str | None = None,
        tool_root: str | Path | None = None,
        settings_path: str | Path | None = None,
    ) -> None:
        root = Path(tool_root or Path.cwd()).expanduser().resolve()
        super(StudioV16316State, self).__init__(
            database=Path(database),
            project_root=project_root,
            project=project,
            tool_root=root,
            settings_path=settings_path,
        )
        self.settings_file = resolve_settings_path(settings_path, tool_root=root)
        self.tool_settings = load_tool_settings(self.settings_file, tool_root=root, create=True)
        if self.tool_settings.studio.theme_name not in THEMES:
            raise ValueError(
                f"Nieznany theme w {self.settings_file}: {self.tool_settings.studio.theme_name!r}"
            )
        self.settings_path = self.settings_file
        self.runtime_settings = self.tool_settings.runtime
        self.theme_name = self.tool_settings.studio.theme_name
        self.status = f"Ustawienia: {self.settings_file}"
        self.status_kind = "ok"

    def reload_tool_settings(self) -> None:
        self.tool_settings = load_tool_settings(self.settings_file, tool_root=self.tool_root, create=True)
        if self.tool_settings.studio.theme_name not in THEMES:
            raise ValueError(f"Nieznany theme: {self.tool_settings.studio.theme_name!r}")
        self.runtime_settings = self.tool_settings.runtime
        self.theme_name = self.tool_settings.studio.theme_name

    def save_tool_settings(self) -> Path:
        path = save_tool_settings(self.tool_settings, self.settings_file, tool_root=self.tool_root)
        self.settings_path = path
        self.runtime_settings = self.tool_settings.runtime
        return path

    def set_runtime(self, runtime: MemoryRebuildSettings) -> Path:
        self.tool_settings = self.tool_settings.with_runtime(runtime)
        return self.save_tool_settings()

    def set_theme(self, name: str) -> Path:
        if name not in THEMES:
            raise ValueError(f"Nieznany theme: {name}")
        self.tool_settings = self.tool_settings.with_studio(
            MemoryRebuildStudioPreferences(theme_name=name)
        )
        self.theme_name = name
        return self.save_tool_settings()

    def cycle_theme_persistent(self) -> Path:
        names = tuple(THEMES)
        try:
            index = names.index(self.theme_name)
        except ValueError:
            index = -1
        return self.set_theme(names[(index + 1) % len(names)])

    def header_fragments(self):
        fragments = list(super(StudioV16316State, self).header_fragments())
        if len(fragments) > 1:
            fragments[1] = ("class:header-version", f"{STUDIO_VERSION}   ")
        return fragments

    def _settings_detail(self, key: str) -> list[str]:
        if key == "project-settings":
            project = self.project_snapshot
            lines = [
                "Ustawienia projektu",
                "",
                "Projekt ma własny plik *.memory-rebuild.json. Enter otwiera pełny edytor tej sekcji.",
                "Pola bezpieczeństwa oznaczone READ-ONLY pozostają wymuszone przez model projektu.",
                "",
            ]
            if project:
                lines.extend(
                    [
                        f"name: {_value(project.get('name'))}  [EDYTOWALNE]",
                        f"mode: {_value(project.get('mode'))}  [EDYTOWALNE]",
                        f"target_root: {_value(project.get('target_root'))}  [EDYTOWALNE]",
                        f"source_directory: {_value(project.get('source_directory'))}  [EDYTOWALNE]",
                        "",
                    ]
                )
            lines.extend(_project_lines(project))
            return lines

        if key == "retrieval":
            return [
                "FTS / retrieval / embeddings",
                "",
                "Enter otwiera edytor ustawień narzędzia. Zmiany są walidowane i zapisywane od razu.",
                "",
                *_runtime_lines(self.runtime_settings),
                "",
                "[Recall benchmark]",
                "baseline: fts5-bm25/v1  [READ-ONLY]",
                "query_rewrite: NIEIMPLEMENTOWANE  [READ-ONLY]",
                "dense_retrieval: NIEIMPLEMENTOWANE  [READ-ONLY]",
                "reranker: NIEIMPLEMENTOWANE  [READ-ONLY]",
                "model_training: NIE  [READ-ONLY / ZABLOKOWANE]",
            ]

        if key == "safety":
            return [
                "Granice bezpieczeństwa",
                "",
                "Ta sekcja jest tylko do odczytu. Enter pokazuje wyjaśnienie blokad.",
                "",
                "require_fts5: TAK  [READ-ONLY — baseline wymagany]",
                "require_provenance: TAK  [READ-ONLY — dowód źródłowy wymagany]",
                "automatic_experience_approval: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_l2: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_l3: NIE  [READ-ONLY / ZABLOKOWANE]",
                "automatic_activation: NIE  [READ-ONLY / ZABLOKOWANE]",
                "Walidacja i baseline'y nie uzyskują prawa zapisu do źródłowego L0.",
            ]

        if key == "paths":
            workspace = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR", "").strip()
            return [
                "Ścieżki i środowisko",
                "",
                "Ta sekcja opisuje kontekst. Bazę zmieniaj na stronie PROJEKTOWANIE → Baza docelowa.",
                "",
                f"Project root: {_value(self.project_root)}  [READ-ONLY tutaj]",
                f"Project: {_value(self.project)}  [READ-ONLY tutaj]",
                f"Database: {self.database}  [READ-ONLY tutaj]",
                f"Settings JSON: {self.settings_file}  [PLIK USTAWIEŃ NARZĘDZIA]",
                f"Tool root: {self.tool_root}  [READ-ONLY]",
                f"JAZN_RUNTIME_WORKSPACE_DIR: {_value(workspace)}  [READ-ONLY / ENV]",
                f"Database exists: {_yes_no(self.database.is_file())}",
            ]

        if key == "theme":
            theme = get_theme(self.theme_name)
            return [
                "Wygląd / theme",
                "",
                "Enter wybiera theme; T przełącza theme. Obie operacje zapisują wybór.",
                "",
                f"Theme: {theme.name}  [EDYTOWALNE]",
                f"Tło: {theme.background}  [READ-ONLY — składnik theme]",
                f"Panel: {theme.panel}  [READ-ONLY — składnik theme]",
                f"Obramowanie: {theme.border}  [READ-ONLY — składnik theme]",
                f"Akcent: {theme.accent}  [READ-ONLY — składnik theme]",
            ]

        project = self.project_snapshot
        return [
            "Wszystkie ustawienia",
            "",
            f"Plik narzędzia: {self.settings_file}",
            "Enter otwiera centrum edycji. S zapisuje pełny plik ustawień ponownie.",
            "",
            "[narzędzie / retrieval]",
            *_runtime_lines(self.runtime_settings),
            "",
            "[studio]",
            f"theme_name: {self.theme_name}  [EDYTOWALNE]",
            "",
            "[projekt]",
            *_project_lines(project),
            "",
            "[informacje tylko do odczytu]",
            f"database: {self.database}",
            f"project: {_value(self.project)}",
            f"tool_root: {self.tool_root}",
        ]

    def footer_fragments(self):
        return [
            ("class:footer-key", " 1 "), ("class:footer", "Testy  "),
            ("class:footer-key", " 2 "), ("class:footer", "Projektowanie  "),
            ("class:footer-key", " 3 "), ("class:footer", "Ustawienia  "),
            ("class:footer-key", " ↑↓ "), ("class:footer", "Wybór  "),
            ("class:footer-key", " Enter "), ("class:footer", "Otwórz/Edytuj  "),
            ("class:footer-key", " S "), ("class:footer", "Zapisz settings  "),
            ("class:footer-key", " T "), ("class:footer", "Theme + zapis  "),
            ("class:footer-key", " Q "), ("class:footer", "Wyjście"),
        ]


def _settings_action_for_state(state: StudioV16316State) -> StudioAction | None:
    item = state.current_item().key
    if state.active_page == "tests":
        return StudioAction("run-test", item)
    if state.active_page == "design":
        return StudioAction(item)
    return StudioAction(
        {
            "all": "settings-hub",
            "project-settings": "settings-project",
            "retrieval": "settings-runtime",
            "safety": "settings-safety",
            "paths": "settings-paths",
            "theme": "settings-theme",
        }[item]
    )


def _run_shell_v16316(state: StudioV16316State) -> StudioAction:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from .layout import build_studio_layout

    bindings = KeyBindings()

    def invalidate(event) -> None:
        event.app.invalidate()

    @bindings.add("1")
    def _tests(event) -> None:
        state.set_page("tests")
        invalidate(event)

    @bindings.add("2")
    def _design(event) -> None:
        state.set_page("design")
        invalidate(event)

    @bindings.add("3")
    def _settings(event) -> None:
        state.set_page("settings")
        invalidate(event)

    @bindings.add("left")
    @bindings.add("s-tab")
    def _previous_page(event) -> None:
        state.cycle_page(-1)
        invalidate(event)

    @bindings.add("right")
    @bindings.add("tab")
    def _next_page(event) -> None:
        state.cycle_page(1)
        invalidate(event)

    @bindings.add("up")
    def _up(event) -> None:
        state.move_selection(-1)
        invalidate(event)

    @bindings.add("down")
    def _down(event) -> None:
        state.move_selection(1)
        invalidate(event)

    @bindings.add("t")
    def _theme(event) -> None:
        try:
            state.cycle_theme_persistent()
            state.status = f"Theme zapisany: {state.theme_name}"
            state.status_kind = "ok"
            event.app.style = prompt_toolkit_style(get_theme(state.theme_name))
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
        invalidate(event)

    @bindings.add("s")
    def _save_settings(event) -> None:
        try:
            path = state.save_tool_settings()
            state.status = f"Zapisano pełne ustawienia: {path}"
            state.status_kind = "ok"
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
        invalidate(event)

    @bindings.add("r")
    def _run_test(event) -> None:
        if state.active_page == "tests":
            event.app.exit(result=StudioAction("run-test", state.current_item().key))
        else:
            state.status = "R uruchamia profil tylko na stronie TESTY."
            state.status_kind = "error"
            invalidate(event)

    @bindings.add("enter")
    def _activate(event) -> None:
        action = _settings_action_for_state(state)
        if action is not None:
            event.app.exit(result=action)

    @bindings.add("q")
    @bindings.add("c-c")
    def _quit(event) -> None:
        event.app.exit(result=StudioAction("quit"))

    application = Application(
        layout=build_studio_layout(state),
        key_bindings=bindings,
        style=prompt_toolkit_style(get_theme(state.theme_name)),
        full_screen=True,
        mouse_support=False,
    )
    result = application.run()
    return result if isinstance(result, StudioAction) else StudioAction("quit")


def _edit_runtime_settings(state: StudioV16316State) -> None:
    while True:
        current = state.tool_settings.runtime
        action = _dialog_choice(
            "USTAWIENIA NARZĘDZIA — RETRIEVAL",
            "\n".join(_runtime_lines(current)),
            [
                ("limit", f"retrieval_limit — teraz {current.retrieval_limit}"),
                ("score", f"min_lexical_score — teraz {current.min_lexical_score}"),
                ("embeddings", f"embeddings_enabled — teraz {_yes_no(current.embeddings_enabled)}"),
                ("model", f"embedding_model — teraz {_value(current.embedding_model)}"),
                ("reset", "Przywróć bezpieczne ustawienia narzędzia"),
                ("json", "Pokaż pełny memory_rebuild_settings.json"),
                ("back", "Wróć"),
            ],
            default="limit",
        )
        if action in {None, "back"}:
            return
        if action == "limit":
            raw = _dialog_input("RETRIEVAL LIMIT", "Zakres 1..500:", str(current.retrieval_limit))
            if raw is None:
                continue
            try:
                runtime = current.with_overrides(retrieval_limit=int(raw.strip()))
            except (TypeError, ValueError) as exc:
                message("Nieprawidłowa wartość", str(exc))
                continue
            state.set_runtime(runtime)
        elif action == "score":
            raw = _dialog_input("MIN LEXICAL SCORE", "Zakres 0..1:", str(current.min_lexical_score))
            if raw is None:
                continue
            try:
                runtime = current.with_overrides(min_lexical_score=float(raw.strip().replace(",", ".")))
            except (TypeError, ValueError) as exc:
                message("Nieprawidłowa wartość", str(exc))
                continue
            state.set_runtime(runtime)
        elif action == "embeddings":
            enable = not current.embeddings_enabled
            model = current.embedding_model
            if enable and not (model or "").strip():
                model = _dialog_input(
                    "MODEL EMBEDDINGÓW",
                    "Włączenie embeddingów wymaga jawnego modelu:",
                    "",
                )
                if model is None or not model.strip():
                    message("Nie zmieniono", "Embeddingi pozostają wyłączone bez jawnego modelu.")
                    continue
            state.set_runtime(
                current.with_overrides(
                    embeddings_enabled=enable,
                    embedding_model=model.strip() if isinstance(model, str) and model.strip() else None,
                )
            )
        elif action == "model":
            raw = _dialog_input(
                "MODEL EMBEDDINGÓW",
                "Identyfikator modelu; pusty tylko gdy embeddingi są wyłączone:",
                current.embedding_model or "",
            )
            if raw is None:
                continue
            model = raw.strip() or None
            try:
                state.set_runtime(current.with_overrides(embedding_model=model))
            except ValueError as exc:
                message("Nieprawidłowa wartość", str(exc))
        elif action == "reset":
            if _dialog_confirm(
                "PRZYWRÓĆ USTAWIENIA",
                "Przywrócić domyślne, bezpieczne ustawienia retrieval i embeddingów?",
            ):
                state.set_runtime(MemoryRebuildSettings())
        elif action == "json":
            message(
                "memory_rebuild_settings.json",
                json.dumps(state.tool_settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            )


def _project_save(store: ProjectStore, project) -> None:
    project.normalized()
    project.touch()
    store.save(project)


def _confirm_risk(key: str, new_value: bool) -> bool:
    less_safe = (key in PROJECT_RISKY_TRUE and new_value) or (
        key in PROJECT_RISKY_FALSE and not new_value
    )
    if not less_safe:
        return True
    return _dialog_confirm(
        "POTWIERDŹ MNIEJ BEZPIECZNE USTAWIENIE",
        (
            f"{key} = {_yes_no(new_value)} zmniejsza ochronę lub zwiększa zakres zapisu/automatyzacji.\n\n"
            "Zmiana dotyczy tylko konfiguracji projektu. Kontynuować?"
        ),
    )


def _edit_project_settings(state: StudioV16316State) -> None:
    if not state.project:
        message("Ustawienia projektu", "Najpierw wybierz lub utwórz projekt na stronie PROJEKTOWANIE.")
        return
    store = ProjectStore(state.project_root)
    project = store.load(state.project)
    # Keep a stable identifier even if the operator renames the project.
    state.project = project.project_id

    while True:
        project.normalized()
        rows: list[tuple[str, str]] = [
            ("name", f"Nazwa projektu: {project.name}"),
            ("mode", f"Tryb: {project.mode}"),
            ("target_root", f"Katalog docelowy: {project.target_root}"),
            ("source_directory", f"Główny folder źródeł: {project.source_directory or '—'}"),
            ("test04_acceptance_report", f"Raport Test04: {project.settings.get('test04_acceptance_report') or '—'}"),
            ("system_acceptance", f"System acceptance: {_yes_no(project.settings.get('system_acceptance', False))}"),
        ]
        for key, default in DEFAULT_SETTINGS.items():
            value = project.settings.get(key, default)
            label = PROJECT_SETTING_LABELS.get(key, key)
            if key in PROJECT_LOCKED_SETTINGS:
                rows.append((f"locked:{key}", f"{label}: {_value(value)}  [READ-ONLY]"))
            else:
                rows.append((f"setting:{key}", f"{label}: {_value(value)}"))
        rows.extend(
            [
                ("safe", "Przywróć bezpieczne ustawienia projektu"),
                ("json", "Pokaż pełne ustawienia projektu JSON"),
                ("back", "Wróć"),
            ]
        )
        action = _dialog_choice(
            "PEŁNE USTAWIENIA PROJEKTU",
            "Zmiany są zapisywane od razu do pliku projektu. Pola READ-ONLY są wymuszone przez bezpieczeństwo.",
            rows,
            default="name",
        )
        if action in {None, "back"}:
            state.refresh()
            return
        if action == "name":
            raw = _dialog_input("NAZWA PROJEKTU", "Nazwa:", project.name)
            if raw is not None and raw.strip():
                project.name = raw.strip()
                _project_save(store, project)
        elif action == "mode":
            value = _dialog_choice(
                "TRYB PROJEKTU",
                "Developer jest przeznaczony do odbudów testowych. System dotyczy finalnych operacji runtime.",
                [("developer", "developer"), ("system", "system")],
                default=project.mode,
            )
            if value:
                project.mode = str(value)
                _project_save(store, project)
        elif action in {"target_root", "source_directory"}:
            current = project.target_root if action == "target_root" else project.source_directory
            raw = _dialog_input("ŚCIEŻKA", "Pełna ścieżka:", current or "")
            if raw is not None:
                value = raw.strip()
                if action == "target_root" and not value:
                    message("Nieprawidłowa wartość", "Katalog docelowy nie może być pusty.")
                    continue
                resolved = str(Path(value).expanduser().resolve()) if value else ""
                if action == "target_root":
                    project.target_root = resolved
                else:
                    project.source_directory = resolved
                _project_save(store, project)
        elif action == "test04_acceptance_report":
            raw = _dialog_input(
                "RAPORT TEST04",
                "Ścieżka prywatnego raportu akceptacyjnego; puste = nie ustawiono:",
                str(project.settings.get("test04_acceptance_report") or ""),
            )
            if raw is not None:
                value = raw.strip()
                if value:
                    project.settings["test04_acceptance_report"] = str(Path(value).expanduser().resolve())
                else:
                    project.settings.pop("test04_acceptance_report", None)
                _project_save(store, project)
        elif action == "system_acceptance":
            current = bool(project.settings.get("system_acceptance", False))
            new_value = not current
            if _confirm_risk("system_acceptance", new_value):
                project.settings["system_acceptance"] = new_value
                _project_save(store, project)
        elif isinstance(action, str) and action.startswith("locked:"):
            key = action.split(":", 1)[1]
            message(
                "Ustawienie tylko do odczytu",
                f"{key} jest wymuszone na NIE i nie może zostać włączone przez Memory Rebuild.",
            )
        elif isinstance(action, str) and action.startswith("setting:"):
            key = action.split(":", 1)[1]
            current = project.settings.get(key, DEFAULT_SETTINGS[key])
            if isinstance(DEFAULT_SETTINGS[key], bool):
                new_value = not bool(current)
                if not _confirm_risk(key, new_value):
                    continue
                project.settings[key] = new_value
            elif key == "candidate_limit":
                raw = _dialog_input(
                    "LIMIT KANDYDATÓW",
                    "0 = bez limitu; wartość >= 0:",
                    str(current),
                )
                if raw is None:
                    continue
                try:
                    value = int(raw.strip())
                    if value < 0:
                        raise ValueError
                except ValueError:
                    message("Nieprawidłowa wartość", "candidate_limit musi być liczbą całkowitą >= 0.")
                    continue
                project.settings[key] = value
            elif key == "progress_every_conversations":
                raw = _dialog_input(
                    "POSTĘP",
                    "Raportuj co N rozmów; zakres 1..100000:",
                    str(current),
                )
                if raw is None:
                    continue
                try:
                    value = int(raw.strip())
                    if value < 1 or value > 100000:
                        raise ValueError
                except ValueError:
                    message("Nieprawidłowa wartość", "progress_every_conversations: zakres 1..100000.")
                    continue
                project.settings[key] = value
            _project_save(store, project)
        elif action == "safe":
            if _dialog_confirm(
                "PRZYWRÓĆ BEZPIECZNE USTAWIENIA",
                "Przywrócić wszystkie standardowe ustawienia projektu do wartości domyślnych?",
            ):
                extras = {
                    key: value
                    for key, value in project.settings.items()
                    if key not in DEFAULT_SETTINGS
                }
                project.settings = dict(DEFAULT_SETTINGS)
                project.settings.update(extras)
                _project_save(store, project)
        elif action == "json":
            payload = project.to_dict()
            message(
                "Pełne ustawienia projektu",
                json.dumps(payload.get("settings") or {}, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            )


def _choose_theme(state: StudioV16316State) -> None:
    selected = _dialog_choice(
        "THEME MEMORY REBUILD STUDIO",
        "Wybór jest zapisywany w memory_rebuild_settings.json.",
        [(name, name) for name in THEMES],
        default=state.theme_name,
    )
    if selected:
        state.set_theme(str(selected))


def _show_safety() -> None:
    message(
        "Granice bezpieczeństwa — tylko do odczytu",
        (
            "FTS5 i proweniencja są obowiązkowe.\n"
            "Automatyczne experience/L2/L3 oraz automatyczna aktywacja pozostają wyłączone.\n\n"
            "Te ustawienia nie są przełącznikami UI: są invariantami Memory Rebuild i próba "
            "ich zmiany w JSON kończy się błędem walidacji."
        ),
    )


def _show_paths(state: StudioV16316State) -> None:
    message("Ścieżki Memory Rebuild", "\n".join(state._settings_detail("paths")))


def _settings_hub(state: StudioV16316State) -> None:
    while True:
        action = _dialog_choice(
            "CENTRUM USTAWIEŃ MEMORY REBUILD",
            f"Plik narzędzia:\n{state.settings_file}\n\nZmiany są zapisywane atomowo.",
            [
                ("runtime", "Retrieval / embeddingi"),
                ("project", "Pełne ustawienia bieżącego projektu"),
                ("theme", "Wygląd / theme"),
                ("safety", "Granice bezpieczeństwa — tylko odczyt"),
                ("paths", "Ścieżki i środowisko — informacje"),
                ("json", "Pokaż pełny memory_rebuild_settings.json"),
                ("save", "Zapisz pełny plik ustawień ponownie"),
                ("back", "Wróć"),
            ],
            default="runtime",
        )
        if action in {None, "back"}:
            return
        if action == "runtime":
            _edit_runtime_settings(state)
        elif action == "project":
            _edit_project_settings(state)
        elif action == "theme":
            _choose_theme(state)
        elif action == "safety":
            _show_safety()
        elif action == "paths":
            _show_paths(state)
        elif action == "json":
            message(
                "memory_rebuild_settings.json",
                json.dumps(state.tool_settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            )
        elif action == "save":
            path = state.save_tool_settings()
            message("Zapisano", str(path))


def _handle_action_v16316(state: StudioV16316State, action: StudioAction) -> int | None:
    if action.kind == "settings-hub":
        _settings_hub(state)
    elif action.kind == "settings-project":
        _edit_project_settings(state)
    elif action.kind == "settings-runtime":
        _edit_runtime_settings(state)
    elif action.kind == "settings-theme":
        _choose_theme(state)
    elif action.kind == "settings-safety":
        _show_safety()
    elif action.kind == "settings-paths":
        _show_paths(state)
    else:
        return _handle_action_v16314(state, action)

    state.reload_tool_settings()
    state.refresh()
    state.reload_tool_settings()
    state.status = f"Ustawienia zapisane: {state.settings_file}"
    state.status_kind = "ok"
    return None


def edit_tool_settings_text(path: Path, *, tool_root: Path) -> None:
    """Small non-prompt_toolkit fallback editor for the global tool settings."""
    while True:
        settings = load_tool_settings(path, tool_root=tool_root, create=True)
        runtime = settings.runtime
        print("\n=== USTAWIENIA NARZĘDZIA MEMORY REBUILD ===")
        print(f"Plik: {path}")
        print(f"1. retrieval_limit: {runtime.retrieval_limit}")
        print(f"2. min_lexical_score: {runtime.min_lexical_score}")
        print(f"3. embeddings_enabled: {_yes_no(runtime.embeddings_enabled)}")
        print(f"4. embedding_model: {_value(runtime.embedding_model)}")
        print(f"5. theme_name: {settings.studio.theme_name}")
        print("6. Pokaż pełny JSON")
        print("7. Wróć")
        raw = input("> ").strip()
        try:
            if raw == "1":
                value = input("retrieval_limit [1..500]: ").strip()
                if value:
                    save_tool_settings(settings.with_runtime(runtime.with_overrides(retrieval_limit=int(value))), path)
            elif raw == "2":
                value = input("min_lexical_score [0..1]: ").strip().replace(",", ".")
                if value:
                    save_tool_settings(settings.with_runtime(runtime.with_overrides(min_lexical_score=float(value))), path)
            elif raw == "3":
                enable = not runtime.embeddings_enabled
                model = runtime.embedding_model
                if enable and not (model or "").strip():
                    model = input("embedding_model (wymagany): ").strip()
                    if not model:
                        continue
                save_tool_settings(
                    settings.with_runtime(
                        runtime.with_overrides(embeddings_enabled=enable, embedding_model=model)
                    ),
                    path,
                )
            elif raw == "4":
                model = input(f"embedding_model [{runtime.embedding_model or ''}]: ").strip()
                save_tool_settings(
                    settings.with_runtime(runtime.with_overrides(embedding_model=model or None)),
                    path,
                )
            elif raw == "5":
                names = tuple(THEMES)
                for index, name in enumerate(names, 1):
                    print(f"{index}. {name}")
                selected = input("Wybór: ").strip()
                if selected.isdigit() and 1 <= int(selected) <= len(names):
                    name = names[int(selected) - 1]
                    save_tool_settings(
                        settings.with_studio(MemoryRebuildStudioPreferences(theme_name=name)),
                        path,
                    )
            elif raw == "6":
                print(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            elif raw in {"", "7"}:
                return
        except (OSError, TypeError, ValueError) as exc:
            print(f"Błąd ustawień: {exc}")


def run_studio_v16316(
    *,
    database: str | Path,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    settings_path: str | Path | None = None,
) -> int:
    state = StudioV16316State(
        database=database,
        project_root=project_root,
        project=project,
        tool_root=tool_root,
        settings_path=settings_path,
    )
    while True:
        action = _run_shell_v16316(state)
        try:
            result = _handle_action_v16316(state, action)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
            message("Memory Rebuild Studio", state.status)
            state.refresh()
            state.reload_tool_settings()
            continue
        if result is not None:
            return result


__all__ = [
    "PROJECT_LOCKED_SETTINGS",
    "PROJECT_RISKY_FALSE",
    "PROJECT_RISKY_TRUE",
    "STUDIO_VERSION",
    "StudioV16316State",
    "edit_tool_settings_text",
    "run_studio_v16316",
]
