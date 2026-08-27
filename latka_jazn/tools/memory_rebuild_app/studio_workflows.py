from __future__ import annotations

"""Direct workflows for the canonical Memory Rebuild Studio.

Every operation calls the current engine/controller directly. No workflow
starts another Memory Rebuild UI or imports any retired ``tui_*`` module.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol
import json

from latka_jazn.tools.memory_restore import confirmation_token

from .baseline_registry import discover_baseline_roots
from .controller import MemoryRebuildAppController
from .final_export import export_final_memory
from .models import PIPELINES, SOURCE_ROLES, TRUTH_DOMAINS, RebuildProject
from .path_picker import choose_directory, choose_files
from .presentation import (
    PIPELINE_LABELS,
    ROLE_LABELS,
    TRUTH_LABELS,
    baseline_title,
    format_baseline,
    format_plan,
    format_preflight,
    format_source,
    source_title,
)
from .project_store import ProjectStore
from .source_browser import discover_source_files, format_discovered_files
from .unified_memory import UnifiedMemoryDatabase
from .studio_dialogs import DialogBackend


class StudioContext(Protocol):
    database: Path
    project_root: str | Path | None
    project: str | None
    tool_root: Path

    def refresh(self) -> None: ...
    def select_project(self, identifier: str | None) -> None: ...
    def set_database(self, path: str | Path, *, remember: bool = True) -> None: ...
    def edit_project_settings(self) -> None: ...


def _json_text(value: Any, *, limit: int = 12000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… [wynik skrócony; pełne dane są dostępne w CLI/JSON]"


def _short(value: str, width: int = 82) -> str:
    value = str(value).replace("\n", " ")
    if len(value) <= width:
        return value
    keep = max(12, (width - 3) // 2)
    return value[:keep] + "..." + value[-keep:]


class StudioWorkflows:
    def __init__(self, state: StudioContext, dialogs: DialogBackend):
        self.state = state
        self.dialogs = dialogs

    def _store(self) -> ProjectStore:
        return ProjectStore(self.state.project_root)

    def _project(self) -> RebuildProject:
        if not self.state.project:
            raise ValueError("Ta operacja wymaga wybranego projektu.")
        return self._store().load(self.state.project)

    def _controller(self, project: RebuildProject | None = None) -> MemoryRebuildAppController:
        return MemoryRebuildAppController(
            project or self._project(),
            store=self._store(),
            tool_root=self.state.tool_root,
        )

    def project_stage(self, project: RebuildProject | None = None) -> str:
        project = project or self._project()
        enabled = project.enabled_sources()
        rebuild = project.enabled_sources(pipeline="memory_rebuild")
        if not project.target_root:
            return "1/5 — ustaw katalog docelowy"
        if not enabled:
            return "1/5 — dodaj lub przeskanuj źródła"
        if not rebuild:
            return "2/5 — wskaż źródła przeznaczone do odbudowy"
        if not project.last_plan:
            return "3/5 — wykonaj preflight i plan bez zapisu"
        if not project.last_run:
            return "4/5 — przejrzyj plan i uruchom odbudowę"
        return "5/5 — przejrzyj wynik, testy i porównanie baseline"

    def project_hub(self) -> None:
        while True:
            current = None
            if self.state.project:
                try:
                    current = self._project()
                except Exception:
                    current = None
            status = (
                f"Bieżący projekt: {current.name if current else '—'}\n"
                f"Etap: {self.project_stage(current) if current else 'wybierz lub utwórz projekt'}"
            )
            action = self.dialogs.choice(
                "PROJEKT I ŹRÓDŁA",
                status,
                [
                    ("switch", "Wybierz / przełącz projekt"),
                    ("new", "Utwórz nowy projekt"),
                    ("sources", "Źródła pamięci"),
                    ("baselines", "Baseline’y Testów 01–04 — tylko odczyt"),
                    ("settings", "Ustawienia projektu"),
                    ("preflight", "Sprawdź gotowość projektu"),
                    ("json", "Pokaż pełny projekt JSON"),
                    ("back", "Wróć"),
                ],
                default="sources" if current else "switch",
            )
            if action in {None, "back"}:
                return
            if action == "switch":
                self._choose_project()
            elif action == "new":
                self._create_project()
            elif action == "sources":
                if self.state.project:
                    self.sources_hub()
                else:
                    self.dialogs.message("Projekt", "Najpierw wybierz lub utwórz projekt.")
            elif action == "baselines":
                if self.state.project:
                    self.baselines_hub()
                else:
                    self.dialogs.message("Projekt", "Najpierw wybierz lub utwórz projekt.")
            elif action == "settings":
                self.state.edit_project_settings()
            elif action == "preflight":
                report = self._controller().preflight()
                self.dialogs.message("GOTOWOŚĆ PROJEKTU", format_preflight(report))
            elif action == "json":
                self.dialogs.message("PROJEKT JSON", _json_text(self._project().to_dict()))
            self.state.refresh()

    def _choose_project(self) -> None:
        store = self._store()
        projects = store.list()
        if not projects:
            self.dialogs.message("Projekty", "Brak zapisanych projektów. Utwórz pierwszy projekt.")
            return
        selected = self.dialogs.choice(
            "WYBIERZ PROJEKT",
            "Projekt zapisuje konfigurację operatora, nie dane pamięci.",
            [(item.project_id, f"{item.name} — {_short(item.target_root)}") for item in projects]
            + [("__back__", "Wróć")],
            default=projects[0].project_id,
        )
        if selected not in {None, "__back__"}:
            self.state.select_project(str(selected))

    def _create_project(self) -> None:
        name = self.dialogs.input("NOWY PROJEKT", "Nazwa projektu:", "Pełna odbudowa pamięci Łatki")
        if not name or not name.strip():
            return
        target_dir = choose_directory(
            title="Wybierz nowy katalog docelowy pamięci",
            initial_directory=Path.cwd(),
        )
        target_raw = str(target_dir) if target_dir else self.dialogs.input(
            "NOWY PROJEKT",
            "Katalog docelowy:",
            "",
        )
        if not target_raw or not str(target_raw).strip():
            return
        source_dir = choose_directory(
            title="Wybierz główny folder źródeł (opcjonalnie)",
            initial_directory=Path.cwd(),
        )
        project = RebuildProject.create(
            name.strip(),
            Path(str(target_raw)).expanduser().resolve(),
            source_directory=str(source_dir) if source_dir else "",
        )
        store = self._store()
        store.create(project)
        self.state.select_project(project.project_id)

    def sources_hub(self) -> None:
        while True:
            project = self._project()
            action = self.dialogs.choice(
                "ŹRÓDŁA PAMIĘCI",
                (
                    f"Projekt: {project.name}\n"
                    f"Źródła: {len(project.enabled_sources())}/{len(project.sources)}\n"
                    "Usunięcie wpisu nie usuwa pliku z dysku."
                ),
                [
                    ("scan", "Przeskanuj folder źródeł"),
                    ("files", "Dodaj pliki"),
                    ("manual", "Dodaj ścieżkę ręcznie"),
                    ("list", "Lista źródeł — podgląd i edycja"),
                    ("clean", "Usuń z projektu nieistniejące wpisy"),
                    ("back", "Wróć"),
                ],
                default="scan",
            )
            if action in {None, "back"}:
                return
            if action == "scan":
                self._scan_sources()
            elif action == "files":
                files = choose_files(
                    title="Wybierz źródła pamięci",
                    initial_directory=project.source_directory or Path.cwd(),
                    multiple=True,
                )
                self._add_source_paths(files)
            elif action == "manual":
                raw = self.dialogs.input(
                    "DODAJ ŹRÓDŁO",
                    "Pełna ścieżka pliku lub folderu:",
                    project.source_directory,
                )
                if raw:
                    path = Path(raw).expanduser().resolve()
                    if path.is_dir():
                        self._scan_sources(path)
                    else:
                        self._add_source_paths([path])
            elif action == "list":
                self._source_list()
            elif action == "clean":
                invalid = [item for item in project.sources if not Path(item.path).is_file()]
                if not invalid:
                    self.dialogs.message("Porządkowanie", "Nie ma błędnych wpisów źródeł.")
                    continue
                if self.dialogs.confirm(
                    "USUŃ BŁĘDNE WPISY",
                    f"Usunąć z projektu {len(invalid)} wpisów? Pliki na dysku nie będą usuwane.",
                ):
                    for item in invalid:
                        project.remove_source(item.source_id)
                    self._store().save(project)
            self.state.refresh()

    def _add_source_paths(self, paths: Sequence[str | Path]) -> None:
        if not paths:
            return
        project = self._project()
        controller = self._controller(project)
        added = 0
        existing = 0
        blocked = 0
        for value in paths:
            before = len(project.sources)
            source = controller.inspect_and_add_source(value)
            if len(project.sources) == before:
                existing += 1
            else:
                added += 1
            if source.status != "ready" or any(str(item).startswith("blocking:") for item in source.warnings):
                blocked += 1
        controller.save()
        self.dialogs.message(
            "ŹRÓDŁA ZAKTUALIZOWANE",
            f"Dodano: {added}\nJuż istniało: {existing}\nWymaga uwagi: {blocked}",
        )

    def _scan_sources(self, preset: str | Path | None = None) -> None:
        project = self._project()
        folder = Path(preset).expanduser().resolve() if preset else choose_directory(
            title="Wybierz folder ze źródłami pamięci",
            initial_directory=project.source_directory or Path.cwd(),
        )
        if folder is None:
            raw = self.dialogs.input(
                "FOLDER ŹRÓDEŁ",
                "Pełna ścieżka folderu:",
                project.source_directory,
            )
            folder = Path(raw).expanduser().resolve() if raw else None
        if folder is None or not folder.is_dir():
            return
        recursive = self.dialogs.confirm("SKANOWANIE", "Skanować również podfoldery?")
        files = discover_source_files(folder, recursive=recursive)
        if not files:
            self.dialogs.message("Skanowanie", "Nie znaleziono obsługiwanych plików.")
            return
        selected = self.dialogs.checklist(
            "WYBIERZ ŹRÓDŁA",
            format_discovered_files(folder, files),
            [(str(path), str(path.relative_to(folder))) for path in files],
            default_values=[str(path) for path in files],
        )
        if selected is None:
            return
        project.source_directory = str(folder)
        self._store().save(project)
        self._add_source_paths([Path(item) for item in selected])

    def _source_list(self) -> None:
        while True:
            project = self._project()
            if not project.sources:
                self.dialogs.message("Źródła", "Lista źródeł jest pusta.")
                return
            selected = self.dialogs.choice(
                "LISTA ŹRÓDEŁ",
                "Wybierz wpis do podglądu lub edycji.",
                [(item.source_id, source_title(item)) for item in project.sources]
                + [("__back__", "Wróć")],
                default=project.sources[0].source_id,
            )
            if selected in {None, "__back__"}:
                return
            self._source_entry(str(selected))

    def _source_entry(self, source_id: str) -> None:
        while True:
            project = self._project()
            source = project.source_by_id(source_id)
            action = self.dialogs.choice(
                "ŹRÓDŁO",
                format_source(source),
                [
                    ("refresh", "Odśwież rozpoznanie i SHA"),
                    ("role", "Zmień rolę"),
                    ("truth", "Zmień rodzaj treści"),
                    ("pipeline", "Zmień sposób użycia"),
                    ("toggle", "Włącz / wyłącz"),
                    ("approve", "Zatwierdź / cofnij zatwierdzenie"),
                    ("notes", "Edytuj notatkę"),
                    ("up", "Przesuń wyżej"),
                    ("down", "Przesuń niżej"),
                    ("remove", "Usuń wpis z projektu"),
                    ("json", "Pełny JSON"),
                    ("back", "Wróć"),
                ],
                default="refresh",
            )
            if action in {None, "back"}:
                return
            controller = self._controller(project)
            if action == "refresh":
                controller.refresh_source(source.source_id)
            elif action == "role":
                value = self.dialogs.choice(
                    "ROLA ŹRÓDŁA",
                    "",
                    [(item, ROLE_LABELS.get(item, item)) for item in SOURCE_ROLES],
                    default=source.role,
                )
                if value:
                    source.role = str(value)
            elif action == "truth":
                value = self.dialogs.choice(
                    "RODZAJ TREŚCI",
                    "",
                    [(item, TRUTH_LABELS.get(item, item)) for item in TRUTH_DOMAINS],
                    default=source.truth_domain,
                )
                if value:
                    source.truth_domain = str(value)
            elif action == "pipeline":
                value = self.dialogs.choice(
                    "SPOSÓB UŻYCIA",
                    "",
                    [(item, PIPELINE_LABELS.get(item, item)) for item in PIPELINES],
                    default=source.pipeline,
                )
                if value:
                    source.pipeline = str(value)
            elif action == "toggle":
                source.enabled = not source.enabled
            elif action == "approve":
                source.approved = not source.approved
            elif action == "notes":
                value = self.dialogs.input("NOTATKA", "Notatka operatora:", source.notes)
                if value is not None:
                    source.notes = value
            elif action == "up":
                project.move_source(source.source_id, -1)
            elif action == "down":
                project.move_source(source.source_id, 1)
            elif action == "remove":
                if self.dialogs.confirm(
                    "USUŃ WPIS",
                    f"Usunąć z projektu {source.path}?\nPlik na dysku pozostanie bez zmian.",
                ):
                    project.remove_source(source.source_id)
                    self._store().save(project)
                    return
            elif action == "json":
                self.dialogs.message("ŹRÓDŁO JSON", _json_text(source.to_dict()))
                continue
            project.normalized()
            self._store().save(project)

    def baselines_hub(self) -> None:
        while True:
            project = self._project()
            action = self.dialogs.choice(
                "BASELINE’Y — TYLKO ODCZYT",
                f"Projekt: {project.name}\nBaseline’y: {len(project.enabled_baselines())}/{len(project.baselines)}",
                [
                    ("discover", "Znajdź baseline’y w folderze"),
                    ("list", "Lista baseline’ów"),
                    ("refresh", "Odśwież wszystkie baseline’y"),
                    ("back", "Wróć"),
                ],
                default="discover",
            )
            if action in {None, "back"}:
                return
            if action == "discover":
                folder = choose_directory(
                    title="Wybierz folder zawierający stare bazy Testów 01–04",
                    initial_directory=Path.cwd(),
                )
                if not folder:
                    continue
                found = discover_baseline_roots([folder])
                if not found:
                    self.dialogs.message("Baseline’y", "Nie znaleziono kompatybilnego zestawu baz.")
                    continue
                selected = self.dialogs.checklist(
                    "DODAJ BASELINE’Y",
                    "Wszystkie wpisy są tylko do odczytu.",
                    [(str(path), str(path)) for path in found],
                    default_values=[str(path) for path in found],
                )
                if selected:
                    controller = self._controller(project)
                    known = {Path(item.path).resolve() for item in project.baselines}
                    for raw in selected:
                        path = Path(raw).resolve()
                        if path not in known:
                            controller.add_baseline(path, full_integrity=False)
                            known.add(path)
                    controller.save()
            elif action == "list":
                self._baseline_list()
            elif action == "refresh":
                controller = self._controller(project)
                controller.refresh_baselines(full_integrity=False)
                controller.save()
            self.state.refresh()

    def _baseline_list(self) -> None:
        while True:
            project = self._project()
            if not project.baselines:
                self.dialogs.message("Baseline’y", "Lista baseline’ów jest pusta.")
                return
            selected = self.dialogs.choice(
                "LISTA BASELINE’ÓW",
                "Baseline’y nie są modyfikowane przez Memory Rebuild.",
                [(item.baseline_id, baseline_title(item)) for item in project.baselines]
                + [("__back__", "Wróć")],
                default=project.baselines[0].baseline_id,
            )
            if selected in {None, "__back__"}:
                return
            baseline = project.baseline_by_id(str(selected))
            action = self.dialogs.choice(
                "BASELINE",
                format_baseline(baseline),
                [
                    ("toggle", "Włącz / wyłącz w porównaniach"),
                    ("refresh", "Odśwież podsumowanie"),
                    ("remove", "Usuń wpis z projektu"),
                    ("json", "Pełny JSON"),
                    ("back", "Wróć"),
                ],
                default="back",
            )
            if action == "toggle":
                baseline.enabled = not baseline.enabled
                self._store().save(project)
            elif action == "refresh":
                controller = self._controller(project)
                controller.refresh_baselines(full_integrity=False)
                controller.save()
            elif action == "remove":
                if self.dialogs.confirm(
                    "USUŃ BASELINE Z PROJEKTU",
                    "Usunąć tylko wpis projektu? Pliki SQLite pozostaną bez zmian.",
                ):
                    project.remove_baseline(baseline.baseline_id)
                    self._store().save(project)
            elif action == "json":
                self.dialogs.message("BASELINE JSON", _json_text(baseline.to_dict()))

    def database_hub(self) -> None:
        while True:
            action = self.dialogs.choice(
                "BAZA DOCELOWA",
                f"Kanoniczna baza:\n{self.state.database}",
                [
                    ("existing", "Wybierz istniejący memory_jazn.sqlite3"),
                    ("new", "Utwórz nową bazę w wybranym folderze"),
                    ("manual", "Wpisz ścieżkę ręcznie"),
                    ("validate", "Pełna walidacja bieżącej bazy"),
                    ("back", "Wróć"),
                ],
                default="existing",
            )
            if action in {None, "back"}:
                return
            if action == "existing":
                files = choose_files(
                    title="Wybierz memory_jazn.sqlite3",
                    initial_directory=self.state.database.parent,
                    multiple=False,
                )
                if files:
                    self.state.set_database(files[0])
            elif action == "new":
                folder = choose_directory(
                    title="Wybierz folder dla nowej memory_jazn.sqlite3",
                    initial_directory=self.state.database.parent,
                )
                if folder:
                    path = Path(folder) / "memory_jazn.sqlite3"
                    if path.exists() or self.dialogs.confirm(
                        "UTWÓRZ BAZĘ",
                        f"Utworzyć i zainicjalizować:\n{path}?",
                    ):
                        UnifiedMemoryDatabase(path).initialize()
                        self.state.set_database(path)
            elif action == "manual":
                raw = self.dialogs.input(
                    "ŚCIEŻKA BAZY",
                    "Pełna ścieżka memory_jazn.sqlite3:",
                    str(self.state.database),
                )
                if raw:
                    self.state.set_database(Path(raw).expanduser().resolve())
            elif action == "validate":
                report = UnifiedMemoryDatabase(self.state.database).validate(full=True)
                self.dialogs.message("WALIDACJA BAZY", _json_text(report))

    def import_hub(self) -> None:
        store = UnifiedMemoryDatabase(self.state.database)
        while True:
            action = self.dialogs.choice(
                "IMPORT ŹRÓDEŁ",
                (
                    f"Baza: {self.state.database}\n"
                    "Import jest przyrostowy i zachowuje proweniencję. "
                    "Stare bazy można najpierw sprawdzić w trybie dry-run."
                ),
                [
                    ("project", "Importuj włączone źródła projektu"),
                    ("files", "Wybierz pliki do importu"),
                    ("folder", "Przeskanuj folder i wybierz pliki"),
                    ("legacy-plan", "Plan migracji starych baz — bez zapisu"),
                    ("legacy-run", "Wykonaj migrację starych baz"),
                    ("back", "Wróć"),
                ],
                default="project" if self.state.project else "files",
            )
            if action in {None, "back"}:
                return
            paths: list[Path] = []
            if action == "project":
                project = self._project()
                paths = [Path(item.path) for item in project.enabled_sources()]
            elif action == "files":
                paths = choose_files(title="Wybierz źródła do importu", multiple=True)
            elif action == "folder":
                folder = choose_directory(title="Wybierz folder ze źródłami")
                if folder:
                    recursive = self.dialogs.confirm("PODFOLDERY", "Skanować podfoldery?")
                    files = discover_source_files(folder, recursive=recursive)
                    selected = self.dialogs.checklist(
                        "WYBIERZ PLIKI",
                        format_discovered_files(folder, files),
                        [(str(path), str(path.relative_to(folder))) for path in files],
                        default_values=[str(path) for path in files],
                    )
                    paths = [Path(item) for item in (selected or [])]
            elif action in {"legacy-plan", "legacy-run"}:
                folder = choose_directory(title="Wybierz folder starych baz Testów 01–04")
                if not folder:
                    continue
                dry_run = action == "legacy-plan"
                if not dry_run and not self.dialogs.confirm(
                    "MIGRACJA STARYCH BAZ",
                    "Ta operacja zapisze kompatybilne rekordy do bieżącej bazy. Kontynuować?",
                ):
                    continue
                result = store.migrate_legacy_root(folder, dry_run=dry_run)
                self.dialogs.message("MIGRACJA", _json_text(result))
                continue
            if paths:
                result = store.import_sources(paths, full_validation=True)
                self.dialogs.message("WYNIK IMPORTU", _json_text(result))

    def candidates_hub(self) -> None:
        store = UnifiedMemoryDatabase(self.state.database)
        while True:
            status = self.dialogs.choice(
                "KANDYDACI PAMIĘCI",
                "Edycja zapisuje rewizję. Zatwierdzenie tworzy L1; nie ma auto-L2/L3.",
                [
                    ("pending_review", "Do przeglądu"),
                    ("approved", "Zatwierdzone"),
                    ("rejected_operator", "Odrzucone ręcznie"),
                    ("merged", "Połączone"),
                    ("all", "Wszystkie"),
                    ("generate", "Wygeneruj / odśwież kandydatów"),
                    ("back", "Wróć"),
                ],
                default="pending_review",
            )
            if status in {None, "back"}:
                return
            if status == "generate":
                if self.dialogs.confirm(
                    "GENEROWANIE KANDYDATÓW",
                    "Wygenerować kandydatów z rozmów i dziennika? Nie zatwierdza to L1/L2/L3.",
                ):
                    self.dialogs.message(
                        "GENEROWANIE KANDYDATÓW",
                        _json_text(store.generate_candidates(chats=True, journal=True)),
                    )
                continue
            items = store.list_candidates(status=str(status), limit=500)
            if not items:
                self.dialogs.message("Kandydaci", "Brak kandydatów w tej grupie.")
                continue
            selected = self.dialogs.choice(
                "LISTA KANDYDATÓW",
                "",
                [
                    (
                        str(item["candidate_id"]),
                        f"[{item.get('status')}] {str(item.get('title') or '(bez tytułu)')[:90]}",
                    )
                    for item in items
                ],
                default=str(items[0]["candidate_id"]),
            )
            if selected:
                self._candidate_entry(store, str(selected))

    def _candidate_entry(self, store: UnifiedMemoryDatabase, candidate_id: str) -> None:
        while True:
            item = store.get_candidate(candidate_id)
            action = self.dialogs.choice(
                "KANDYDAT",
                (
                    f"{str(item.get('summary') or '')[:1600]}\n\n"
                    f"Status: {item.get('status')} | Prawda: {item.get('truth_status')}\n"
                    f"Dowody: {len(item.get('evidence') or [])} | Rewizje: {len(item.get('revisions') or [])}"
                ),
                [
                    ("preview", "Pełny podgląd techniczny"),
                    ("edit", "Edytuj treść i klasyfikację"),
                    ("review", "Zatwierdź / odrzuć / przywróć"),
                    ("back", "Wróć"),
                ],
                default="preview",
            )
            if action in {None, "back"}:
                return
            if action == "preview":
                self.dialogs.message("KANDYDAT JSON", _json_text(item))
            elif action == "edit":
                self._edit_candidate(store, candidate_id, item)
            elif action == "review":
                self._review_candidate(store, candidate_id)

    def _edit_candidate(
        self,
        store: UnifiedMemoryDatabase,
        candidate_id: str,
        current: dict[str, Any],
    ) -> None:
        title = self.dialogs.input("EDYCJA KANDYDATA", "Tytuł:", str(current.get("title") or ""))
        if title is None:
            return
        summary = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Treść / podsumowanie:",
            str(current.get("summary") or ""),
        )
        if summary is None:
            return
        truth = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Rodzaj prawdy:",
            str(current.get("truth_status") or "inferred"),
        )
        confidence = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Pewność 0–1:",
            str(current.get("confidence") or 0.5),
        )
        importance = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Ważność 0–1:",
            str(current.get("importance") or 0.5),
        )
        domains = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Domeny oddzielone przecinkami:",
            ", ".join(current.get("domains") or []),
        )
        edited_by = self.dialogs.input("EDYCJA KANDYDATA", "Kto edytuje:", "Krzysztof")
        reason = self.dialogs.input(
            "EDYCJA KANDYDATA",
            "Powód zmiany:",
            "Ręczna korekta w Memory Rebuild Studio",
        )
        if not edited_by or not reason:
            return
        changes = {
            "title": title,
            "summary": summary,
            "truth_status": truth,
            "confidence": float(confidence or 0.5),
            "importance": float(importance or 0.5),
            "domains_json": [part.strip() for part in (domains or "").split(",") if part.strip()],
        }
        updated = store.edit_candidate(
            candidate_id,
            changes,
            edited_by=edited_by,
            reason=reason,
        )
        self.dialogs.message("KANDYDAT ZAPISANY", _json_text(updated))

    def _review_candidate(self, store: UnifiedMemoryDatabase, candidate_id: str) -> None:
        decision = self.dialogs.choice(
            "DECYZJA O KANDYDACIE",
            "Zatwierdzenie tworzy doświadczenie L1. Nie promuje automatycznie do L2 ani L3.",
            [
                ("approve", "Zatwierdź jako L1"),
                ("reject", "Odrzuć"),
                ("pending", "Przywróć / pozostaw do przeglądu"),
                ("cancel", "Anuluj"),
            ],
            default="cancel",
        )
        if decision in {None, "cancel"}:
            return
        reviewed_by = self.dialogs.input("DECYZJA", "Kto podejmuje decyzję:", "Krzysztof")
        reason = self.dialogs.input("DECYZJA", "Uzasadnienie:", "Ręczny przegląd źródeł")
        if not reviewed_by or not reason:
            return
        result = store.review_candidate(
            candidate_id,
            decision=str(decision),
            reviewed_by=reviewed_by,
            reason=reason,
        )
        self.dialogs.message("DECYZJA ZAPISANA", _json_text(result))

    def plan(self, *, compare: bool = False) -> None:
        controller = self._controller()
        payload = (
            controller.compare_target_to_baselines(full_integrity=False)
            if compare
            else controller.plan()
        )
        title = "PORÓWNANIE Z BASELINE" if compare else "PLAN BEZ ZAPISU"
        body = _json_text(payload) if compare else format_plan(payload)
        self.dialogs.message(title, body)

    def rebuild(self) -> None:
        project = self._project()
        controller = self._controller(project)
        preflight = controller.preflight()
        if not preflight.get("ok"):
            self.dialogs.message("ODBUDOWA ZABLOKOWANA", format_preflight(preflight))
            return
        plan = controller.plan()
        self.dialogs.message("PLAN PRZED ODBUDOWĄ", format_plan(plan))
        expected = confirmation_token(controller.settings())
        typed = self.dialogs.input(
            "POTWIERDŹ ODBUDOWĘ",
            (
                "Ta operacja zapisuje do katalogu docelowego projektu.\n"
                "Wpisz dokładny token potwierdzenia:"
            ),
            "",
        )
        if typed != expected:
            self.dialogs.message(
                "ODBUDOWA ANULOWANA",
                "Token nie zgadza się. Nie uruchomiono zapisu.",
            )
            return
        result = controller.run(confirmation=typed)
        self.dialogs.message("WYNIK ODBUDOWY", _json_text(result))

    def export(self) -> None:
        project = self._project() if self.state.project else None
        default_output = (
            Path(project.target_root).expanduser().resolve().parent / "memory_final"
            if project and project.target_root
            else self.state.database.parent / "memory_final"
        )
        raw = self.dialogs.input(
            "FINALNY EKSPORT",
            "Nowy katalog finalnego eksportu:",
            str(default_output),
        )
        if not raw:
            return
        output = Path(raw).expanduser().resolve()
        overwrite = output.exists() and self.dialogs.confirm(
            "NADPISAĆ EKSPORT",
            "Cel już istnieje. Przenieść stary katalog do backupu i opublikować nowy?",
        )
        if output.exists() and not overwrite:
            return
        baselines = [item.path for item in project.enabled_baselines()] if project else []
        sources = [item.path for item in project.enabled_sources()] if project else []
        settings = dict(project.settings) if project else {}
        result = export_final_memory(
            self.state.database,
            output,
            baselines=baselines,
            sources=sources,
            overwrite=overwrite,
            acceptance_report=settings.get("test04_acceptance_report"),
            system_acceptance=bool(settings.get("system_acceptance", False)),
        )
        self.dialogs.message("FINALNY EKSPORT", _json_text(result))


__all__ = ["StudioContext", "StudioWorkflows"]
