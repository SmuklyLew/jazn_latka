from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import json

from latka_jazn.tools.memory_restore import confirmation_token

from .baseline_registry import discover_baseline_roots
from .controller import MemoryRebuildAppController, MemoryRebuildAppError
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
from .source_inventory import inspect_source

try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import (
        checkboxlist_dialog,
        input_dialog,
        message_dialog,
        radiolist_dialog,
        yes_no_dialog,
    )
    from prompt_toolkit.styles import Style

    HAS_CURSOR_UI = True
    DIALOG_STYLE = Style.from_dict(
        {
            "dialog": "bg:#e8e8e8 #000000",
            "dialog frame.label": "bg:#e8e8e8 #000000 bold",
            "dialog.body": "bg:#ffffff #000000",
            "dialog shadow": "bg:#666666",
            "button": "bg:#d0d0d0 #000000",
            "button.focused": "bg:#005faf #ffffff bold",
            "radio": "#000000",
            "radio-selected": "#005faf bold",
            "checkbox": "#000000",
            "checkbox-selected": "#005faf bold",
            "text-area": "bg:#ffffff #000000",
        }
    )
except Exception:  # pragma: no cover
    checkboxlist_dialog = None  # type: ignore[assignment]
    input_dialog = None  # type: ignore[assignment]
    message_dialog = None  # type: ignore[assignment]
    radiolist_dialog = None  # type: ignore[assignment]
    yes_no_dialog = None  # type: ignore[assignment]
    Style = None  # type: ignore[assignment]
    DIALOG_STYLE = None
    HAS_CURSOR_UI = False


class StudioExit(Exception):
    pass


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _short(value: str, width: int = 72) -> str:
    if len(value) <= width:
        return value
    keep = max(8, (width - 3) // 2)
    return value[:keep] + "..." + value[-keep:]


def _text_choice(title: str, text: str, values: Sequence[tuple[Any, str]]) -> Any:
    print(f"\n=== {title} ===")
    if text:
        print(text)
    for index, (_value, label) in enumerate(values, 1):
        print(f"{index:>2}. {label}")
    raw = input("Wybór [Enter=powrót]: ").strip()
    if not raw:
        return None
    try:
        index = int(raw) - 1
    except ValueError:
        return None
    return values[index][0] if 0 <= index < len(values) else None


def choose_or_create_project(store: ProjectStore, *, cursor: bool = True) -> RebuildProject:
    while True:
        projects = store.list()
        choices = [
            (item.project_id, f"{item.name}\n    Cel: {_short(item.target_root)}")
            for item in projects
        ]
        choices.extend((("__new__", "Utwórz nowy projekt"), ("__exit__", "Wyjdź")))
        if cursor and HAS_CURSOR_UI:
            assert radiolist_dialog is not None
            selected = radiolist_dialog(
                title="ODBUDOWA PAMIĘCI JAŹNI",
                text=(
                    "Wybierz projekt. Projekty przechowują tylko ustawienia i decyzje operatora.\n"
                    "Bazy testowe oraz pliki źródłowe pozostają bez zmian."
                ),
                values=choices,
                default=projects[0].project_id if projects else "__new__",
                style=DIALOG_STYLE,
            ).run()
        else:
            selected = _text_choice("PROJEKTY ODBUDOWY", "", choices)
        if selected in {None, "__exit__"}:
            raise StudioExit()
        if selected != "__new__":
            return store.load(str(selected))

        if cursor and HAS_CURSOR_UI:
            assert input_dialog is not None
            name = input_dialog(
                title="NOWY PROJEKT — KROK 1/3",
                text="Nazwa projektu:",
                default="Pełna odbudowa pamięci Łatki",
                style=DIALOG_STYLE,
            ).run()
            target = input_dialog(
                title="NOWY PROJEKT — KROK 2/3",
                text="Nowy katalog docelowy baz (może jeszcze nie istnieć):",
                default=r"D:\PRIVATE\jazn_memory_test_05",
                style=DIALOG_STYLE,
            ).run()
            source_folder = choose_directory(
                title="NOWY PROJEKT — KROK 3/3: wybierz folder źródeł",
                initial_directory=r"D:\.AI\work\memory_to_restore",
            )
            source = str(source_folder) if source_folder else ""
        else:
            name = input("Nazwa projektu: ").strip() or "Pełna odbudowa pamięci Łatki"
            target = input("Nowy katalog docelowy: ").strip()
            source = input("Katalog źródeł (opcjonalnie): ").strip()
        if not target:
            continue
        project = RebuildProject.create(name or "Pełna odbudowa pamięci Łatki", target, source_directory=source)
        store.create(project)
        return project


class MemoryRebuildStudio:
    def __init__(
        self,
        project: RebuildProject,
        *,
        store: ProjectStore,
        tool_root: str | Path | None = None,
        cursor: bool = True,
    ):
        self.project = project
        self.store = store
        self.cursor = bool(cursor and HAS_CURSOR_UI)
        self.events: list[dict[str, Any]] = []
        self.controller = MemoryRebuildAppController(
            project,
            store=store,
            tool_root=tool_root,
            callback=self._event,
        )

    def _event(self, payload: dict[str, Any]) -> None:
        self.events.append(dict(payload))
        self.events = self.events[-500:]
        if not self.cursor:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), flush=True)

    def show(self, title: str, value: Any) -> None:
        text = value if isinstance(value, str) else _json_text(value)
        if self.cursor:
            assert message_dialog is not None
            message_dialog(title=title, text=text, ok_text="OK", style=DIALOG_STYLE).run()
        else:
            print(f"\n=== {title} ===\n{text}")

    def input(self, title: str, prompt: str, default: str = "") -> str | None:
        if self.cursor:
            assert input_dialog is not None
            return input_dialog(title=title, text=prompt, default=default, style=DIALOG_STYLE).run()
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw or default

    def choose(
        self,
        title: str,
        text: str,
        values: Sequence[tuple[Any, str]],
        default: Any = None,
    ) -> Any:
        if self.cursor:
            assert radiolist_dialog is not None
            return radiolist_dialog(
                title=title,
                text=text,
                values=list(values),
                default=default,
                style=DIALOG_STYLE,
            ).run()
        return _text_choice(title, text, values)

    def confirm(self, title: str, text: str) -> bool:
        if self.cursor:
            assert yes_no_dialog is not None
            return bool(
                yes_no_dialog(
                    title=title,
                    text=text,
                    yes_text="Tak",
                    no_text="Nie",
                    style=DIALOG_STYLE,
                ).run()
            )
        return input(f"{text} [t/N]: ").strip().casefold() in {"t", "tak", "y", "yes"}

    def project_stage(self) -> str:
        enabled = self.project.enabled_sources()
        rebuild = self.project.enabled_sources(pipeline="memory_rebuild")
        if not self.project.target_root:
            return "1/5 — ustaw katalog docelowy"
        if not enabled:
            return "1/5 — dodaj lub przeskanuj źródła"
        if not rebuild:
            return "2/5 — wskaż źródła, które mają wejść do odbudowy"
        if not self.project.last_plan:
            return "3/5 — sprawdź gotowość i zbuduj plan bez zapisu"
        if not self.project.last_run:
            return "4/5 — przejrzyj plan i uruchom odbudowę"
        return "5/5 — przejrzyj wynik i porównaj z bazami testowymi"

    def status(self) -> str:
        return (
            f"Projekt: {self.project.name}\n"
            f"Etap: {self.project_stage()}\n"
            f"Cel: {self.project.target_root}\n"
            f"Folder źródeł: {self.project.source_directory or 'nie ustawiono'}\n"
            f"Źródła: {len(self.project.enabled_sources())}/{len(self.project.sources)}\n"
            f"Bazy porównawcze: {len(self.project.enabled_baselines())}/{len(self.project.baselines)}\n"
            "Automatyczne zatwierdzanie experience/L2/L3: WYŁĄCZONE"
        )

    def run(self) -> int:
        actions = (
            ("sources", "1. Źródła pamięci — pliki i foldery"),
            ("baselines", "2. Bazy testowe do porównania — tylko odczyt"),
            ("settings", "3. Ustawienia projektu — cel i folder źródeł"),
            ("preflight", "4. Sprawdź gotowość projektu"),
            ("plan", "5. Zbuduj plan bez zapisu"),
            ("execute", "6. Uruchom kontrolowaną odbudowę"),
            ("compare", "7. Porównaj wynik z bazami testowymi"),
            ("export", "Eksport manifestu"),
            ("events", "Szczegóły techniczne sesji"),
            ("save", "Zapisz projekt"),
            ("switch", "Przełącz projekt"),
            ("exit", "Zapisz i wyjdź"),
        )
        while True:
            try:
                action = self.choose("MEMORY REBUILD STUDIO", self.status(), actions, default="sources")
                if action == "sources":
                    self.sources_menu()
                elif action == "baselines":
                    self.baselines_menu()
                elif action == "settings":
                    self.settings_menu()
                elif action == "preflight":
                    self.preflight_menu()
                elif action == "plan":
                    self.plan_menu()
                elif action == "compare":
                    self.compare_menu()
                elif action == "export":
                    self.export_menu()
                elif action == "execute":
                    self.execute()
                elif action == "events":
                    self.show("SZCZEGÓŁY TECHNICZNE SESJI", self.events)
                elif action == "save":
                    self.show("ZAPISANO", f"Projekt zapisano w:\n{self.controller.save()}")
                elif action == "switch":
                    self.controller.save()
                    self.project = choose_or_create_project(self.store, cursor=self.cursor)
                    self.controller = MemoryRebuildAppController(
                        self.project,
                        store=self.store,
                        tool_root=self.controller.tool_root,
                        callback=self._event,
                    )
                elif action in {None, "exit"}:
                    self.controller.save()
                    return 0
            except (MemoryRebuildAppError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self.show(
                    "NIE UDAŁO SIĘ WYKONAĆ OPERACJI",
                    f"{exc}\n\nNic nie zostało zapisane do baz pamięci. Wróć do listy źródeł lub ustawień projektu.",
                )

    def sources_menu(self) -> None:
        while True:
            rebuild_count = len(self.project.enabled_sources(pipeline="memory_rebuild"))
            action = self.choose(
                "ŹRÓDŁA PAMIĘCI",
                (
                    f"W projekcie: {len(self.project.sources)} wpisów, w odbudowie: {rebuild_count}.\n"
                    "Foldery skanujemy; do listy źródeł trafiają wyłącznie konkretne pliki.\n"
                    "Podfoldery zaczynające się kropką, np. .BardzoStareCos, są uwzględniane."
                ),
                [
                    ("scan", "Przeskanuj folder źródeł (zalecane)"),
                    ("files", "Dodaj jeden lub wiele plików — okno systemowe"),
                    ("manual", "Wklej ścieżkę pliku lub folderu"),
                    ("list", "Lista źródeł — podgląd, edycja, wyłączenie, usunięcie"),
                    ("clean", "Usuń z projektu wpisy nieistniejące lub będące folderami"),
                    ("back", "Wróć"),
                ],
                default="scan",
            )
            if action in {None, "back"}:
                return
            if action == "scan":
                self.scan_source_folder()
            elif action == "files":
                self.add_source_files()
            elif action == "manual":
                self.add_manual_source()
            elif action == "list":
                self.source_list_menu()
            elif action == "clean":
                self.clean_invalid_source_entries()

    def _add_paths(self, paths: Sequence[str | Path]) -> dict[str, int]:
        added = 0
        existing = 0
        blocked = 0
        for path in paths:
            before = len(self.project.sources)
            source = self.controller.inspect_and_add_source(path)
            if len(self.project.sources) == before:
                existing += 1
            else:
                added += 1
            if source.status != "ready" or any(item.startswith("blocking:") for item in source.warnings):
                blocked += 1
        self.project.normalized()
        self.controller.save()
        return {"added": added, "existing": existing, "blocked": blocked}

    def add_source_files(self) -> None:
        selected = choose_files(
            title="Wybierz źródła pamięci — można zaznaczyć wiele plików",
            initial_directory=self.project.source_directory or Path.cwd(),
            multiple=True,
        )
        if not selected:
            value = self.input("DODAJ PLIK", "Wklej pełną ścieżkę pliku:", "")
            selected = [Path(value)] if value else []
        if not selected:
            return
        result = self._add_paths(selected)
        self.show(
            "DODANO ŹRÓDŁA",
            (
                f"Nowe wpisy: {result['added']}\n"
                f"Już istniejące: {result['existing']}\n"
                f"Wymagające uwagi: {result['blocked']}\n\n"
                "Otwórz listę źródeł, aby zobaczyć rolę i sposób użycia każdego pliku."
            ),
        )

    def add_manual_source(self) -> None:
        value = self.input(
            "DODAJ ŚCIEŻKĘ",
            "Wklej pełną ścieżkę pliku albo folderu:",
            self.project.source_directory,
        )
        if not value:
            return
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            self.scan_source_folder(path)
            return
        result = self._add_paths([path])
        self.show("WYNIK", f"Dodano: {result['added']}\nWymaga uwagi: {result['blocked']}")

    def scan_source_folder(self, preset: str | Path | None = None) -> None:
        folder = Path(preset).expanduser().resolve() if preset else choose_directory(
            title="Wybierz folder z ZIP-ami i innymi źródłami pamięci",
            initial_directory=self.project.source_directory or r"D:\.AI\work\memory_to_restore",
        )
        if folder is None:
            value = self.input(
                "FOLDER ŹRÓDEŁ",
                "Wklej ścieżkę folderu:",
                self.project.source_directory or r"D:\.AI\work\memory_to_restore",
            )
            folder = Path(value).expanduser().resolve() if value else None
        if folder is None:
            return
        if not folder.is_dir():
            self.show("NIEPRAWIDŁOWY FOLDER", f"Folder nie istnieje:\n{folder}")
            return
        recursive = self.confirm(
            "SKANOWANIE PODFOLDERÓW",
            "Przeskanować również wszystkie podfoldery?\n\nTak obejmie także .BardzoStareCos.",
        )
        files = discover_source_files(folder, recursive=recursive)
        if not files:
            self.show("BRAK PLIKÓW", f"Nie znaleziono obsługiwanych plików w:\n{folder}")
            return
        preview = format_discovered_files(folder, files)
        decision = self.choose(
            "PODGLĄD ZNALEZIONYCH PLIKÓW",
            preview,
            [
                ("all", f"Dodaj wszystkie ({len(files)})"),
                ("choose", "Wybierz konkretne pliki z listy"),
                ("cancel", "Anuluj"),
            ],
            default="all",
        )
        if decision in {None, "cancel"}:
            return
        selected = files
        if decision == "choose":
            selected = self.select_discovered_files(folder, files)
        if not selected:
            return
        self.project.source_directory = str(folder)
        result = self._add_paths(selected)
        self.project.touch()
        self.controller.save()
        self.show(
            "SKANOWANIE ZAKOŃCZONE",
            (
                f"Folder: {folder}\n"
                f"Znaleziono: {len(files)}\n"
                f"Dodano: {result['added']}\n"
                f"Już było w projekcie: {result['existing']}\n"
                f"Wymaga uwagi: {result['blocked']}"
            ),
        )

    def select_discovered_files(self, root: Path, files: Sequence[Path]) -> list[Path]:
        if self.cursor and HAS_CURSOR_UI and checkboxlist_dialog is not None and len(files) <= 400:
            values = []
            for path in files:
                try:
                    label = str(path.relative_to(root))
                except ValueError:
                    label = str(path)
                values.append((str(path), label))
            selected = checkboxlist_dialog(
                title="WYBIERZ PLIKI",
                text="Spacja zaznacza/odznacza. Enter zatwierdza.",
                values=values,
                default_values=[str(path) for path in files],
                style=DIALOG_STYLE,
            ).run()
            return [Path(item).resolve() for item in (selected or [])]
        self.show(
            "WYBÓR PLIKÓW",
            "Dla tej liczby plików użyj opcji „Dodaj pliki — okno systemowe” albo dodaj wszystkie i usuń zbędne wpisy z czytelnej listy.",
        )
        return []

    def clean_invalid_source_entries(self) -> None:
        invalid = [item for item in self.project.sources if not Path(item.path).is_file()]
        if not invalid:
            self.show("PORZĄDKOWANIE", "Nie ma nieistniejących plików ani folderów dodanych jako pliki.")
            return
        text = "\n".join(f"• {item.path}" for item in invalid)
        if not self.confirm("USUŃ BŁĘDNE WPISY", f"Z projektu zostaną usunięte tylko wpisy:\n\n{text}\n\nPliki na dysku nie będą usuwane."):
            return
        for item in list(invalid):
            self.project.remove_source(item.source_id)
        self.controller.save()
        self.show("PORZĄDKOWANIE", f"Usunięto {len(invalid)} błędnych wpisów z projektu.")

    def source_list_menu(self) -> None:
        while True:
            rows = [(item.source_id, source_title(item)) for item in self.project.sources]
            if not rows:
                self.show("LISTA ŹRÓDEŁ", "Lista jest pusta. Najpierw przeskanuj folder lub dodaj pliki.")
                return
            source_id = self.choose(
                "LISTA ŹRÓDEŁ",
                "Wybierz wpis. Usunięcie wpisu nie usuwa pliku z dysku.",
                rows + [("__back__", "Wróć")],
                default=rows[0][0],
            )
            if source_id in {None, "__back__"}:
                return
            self.source_entry_menu(str(source_id))

    def source_entry_menu(self, source_id: str) -> None:
        while True:
            source = self.project.source_by_id(source_id)
            operation = self.choose(
                "ŹRÓDŁO — PODGLĄD I EDYCJA",
                format_source(source),
                [
                    ("technical", "Pokaż pełne szczegóły techniczne JSON"),
                    ("refresh", "Odśwież SHA i rozpoznanie pliku"),
                    ("path", "Zmień plik / ścieżkę"),
                    ("role", "Zmień rolę źródła"),
                    ("truth", "Zmień rodzaj treści"),
                    ("pipeline", "Zmień sposób użycia"),
                    ("toggle", "Włącz/wyłącz wpis"),
                    ("approve", "Zatwierdź/cofnij zatwierdzenie"),
                    ("notes", "Edytuj notatkę operatora"),
                    ("up", "Przesuń wyżej"),
                    ("down", "Przesuń niżej"),
                    ("remove", "Usuń wpis z projektu"),
                    ("back", "Wróć"),
                ],
                default="refresh",
            )
            if operation in {None, "back"}:
                return
            if operation == "technical":
                self.show("SZCZEGÓŁY TECHNICZNE", source.to_dict())
            elif operation == "refresh":
                self.controller.refresh_source(source.source_id)
            elif operation == "path":
                self.replace_source_path(source)
            elif operation == "role":
                values = [(item, ROLE_LABELS.get(item, item)) for item in SOURCE_ROLES]
                value = self.choose("ROLA ŹRÓDŁA", "", values, default=source.role)
                if value:
                    source.role = value
            elif operation == "truth":
                values = [(item, TRUTH_LABELS.get(item, item)) for item in TRUTH_DOMAINS]
                value = self.choose("RODZAJ TREŚCI", "", values, default=source.truth_domain)
                if value:
                    source.truth_domain = value
            elif operation == "pipeline":
                values = [(item, PIPELINE_LABELS.get(item, item)) for item in PIPELINES]
                value = self.choose("SPOSÓB UŻYCIA", "", values, default=source.pipeline)
                if value:
                    source.pipeline = value
            elif operation == "toggle":
                source.enabled = not source.enabled
            elif operation == "approve":
                source.approved = not source.approved
            elif operation == "notes":
                value = self.input("NOTATKA OPERATORA", "Notatka:", source.notes)
                if value is not None:
                    source.notes = value
            elif operation == "up":
                self.project.move_source(source.source_id, -1)
            elif operation == "down":
                self.project.move_source(source.source_id, 1)
            elif operation == "remove":
                if self.confirm(
                    "USUŃ WPIS",
                    f"Usunąć z projektu:\n{source.path}\n\nPlik na dysku pozostanie bez zmian.",
                ):
                    self.project.remove_source(source.source_id)
                    self.controller.save()
                    return
            self.project.normalized()
            self.project.touch()
            self.controller.save()

    def replace_source_path(self, source: Any) -> None:
        selected = choose_files(
            title="Wybierz nowy plik dla wpisu",
            initial_directory=Path(source.path).parent,
            multiple=False,
        )
        value = str(selected[0]) if selected else self.input("ZMIEŃ PLIK", "Nowa pełna ścieżka:", source.path)
        if not value:
            return
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            self.show("TO JEST FOLDER", "W tym miejscu należy wskazać konkretny plik. Folder przeskanuj z menu źródeł.")
            return
        for other in self.project.sources:
            if other.source_id != source.source_id and Path(other.path) == path:
                self.show("DUPLIKAT", "Ten plik już znajduje się w projekcie.")
                return
        inspection = inspect_source(
            path,
            calculate_sha256=bool(self.project.settings.get("hash_sources_during_scan", True)),
            verify_zip_crc=bool(self.project.settings.get("verify_zip_crc_during_scan", False)),
        )
        source.path = inspection.path
        source.size_bytes = inspection.size_bytes
        source.sha256 = inspection.sha256
        source.role = inspection.role
        source.source_family = inspection.source_family
        source.truth_domain = inspection.truth_domain
        source.pipeline = inspection.pipeline
        source.status = inspection.status
        source.warnings = inspection.warnings
        source.metadata = inspection.metadata

    def baselines_menu(self) -> None:
        while True:
            action = self.choose(
                "BAZY TESTOWE — TYLKO ODCZYT",
                (
                    f"W projekcie: {len(self.project.baselines)}.\n"
                    "Aplikacja nie zapisuje do tych baz i nie usuwa ich z dysku."
                ),
                [
                    ("add", "Dodaj folder jednego testu — okno systemowe"),
                    ("discover", "Znajdź wszystkie zestawy baz pod wybranym folderem"),
                    ("list", "Lista baz testowych — podgląd, edycja, usunięcie wpisu"),
                    ("refresh", "Odśwież kontrolę wszystkich baz"),
                    ("back", "Wróć"),
                ],
                default="discover",
            )
            if action in {None, "back"}:
                return
            if action == "add":
                self.add_baseline_folder()
            elif action == "discover":
                self.discover_baseline_folders()
            elif action == "list":
                self.baseline_list_menu()
            elif action == "refresh":
                self.controller.refresh_baselines()
                self.controller.save()
                self.show("ODŚWIEŻONO", f"Sprawdzono {len(self.project.baselines)} zestawów baz.")

    def add_baseline_folder(self, preset: str | Path | None = None) -> None:
        folder = Path(preset).resolve() if preset else choose_directory(
            title="Wybierz folder Testu 01–04 albo folder memory/sqlite",
            initial_directory=r"D:\PRIVATE",
        )
        if folder is None:
            value = self.input("DODAJ BAZĘ TESTOWĄ", "Ścieżka folderu:", r"D:\PRIVATE")
            folder = Path(value).expanduser().resolve() if value else None
        if folder is None:
            return
        label = self.input("NAZWA BAZY TESTOWEJ", "Czytelna nazwa:", folder.name)
        baseline = self.controller.add_baseline(folder, label=label)
        self.controller.save()
        self.show("DODANO BAZĘ TESTOWĄ", format_baseline(baseline))

    def discover_baseline_folders(self) -> None:
        root = choose_directory(title="Wybierz folder zawierający Testy 01–04", initial_directory=r"D:\PRIVATE")
        if root is None:
            return
        found = discover_baseline_roots([root], max_depth=6)
        if not found:
            self.show("BRAK ZESTAWÓW BAZ", f"Nie znaleziono zestawu co najmniej trzech baz SQLite pod:\n{root}")
            return
        text = "\n".join(f"• {path}" for path in found)
        if not self.confirm("ZNALEZIONE BAZY TESTOWE", f"Znaleziono {len(found)} zestawów:\n\n{text}\n\nDodać wszystkie do projektu?"):
            return
        for path in found:
            self.controller.add_baseline(path, label=path.parent.name or path.name)
        self.controller.save()
        self.show("DODANO", f"Dodano {len(found)} zestawów baz tylko do odczytu.")

    def baseline_list_menu(self) -> None:
        while True:
            rows = [(item.baseline_id, baseline_title(item)) for item in self.project.baselines]
            if not rows:
                self.show("LISTA BAZ TESTOWYCH", "Lista jest pusta.")
                return
            baseline_id = self.choose(
                "LISTA BAZ TESTOWYCH",
                "Wybierz zestaw do podglądu lub edycji wpisu.",
                rows + [("__back__", "Wróć")],
                default=rows[0][0],
            )
            if baseline_id in {None, "__back__"}:
                return
            self.baseline_entry_menu(str(baseline_id))

    def baseline_entry_menu(self, baseline_id: str) -> None:
        while True:
            baseline = self.project.baseline_by_id(baseline_id)
            operation = self.choose(
                "BAZA TESTOWA",
                format_baseline(baseline),
                [
                    ("technical", "Pokaż szczegóły techniczne JSON"),
                    ("refresh", "Odśwież szybką kontrolę"),
                    ("full", "Uruchom pełny integrity_check"),
                    ("label", "Zmień nazwę wyświetlaną"),
                    ("path", "Zmień folder zestawu baz"),
                    ("toggle", "Włącz/wyłącz w porównaniach"),
                    ("remove", "Usuń wpis z projektu"),
                    ("back", "Wróć"),
                ],
                default="refresh",
            )
            if operation in {None, "back"}:
                return
            if operation == "technical":
                self.show("SZCZEGÓŁY TECHNICZNE", baseline.to_dict())
            elif operation in {"refresh", "full"}:
                from .baseline_registry import refresh_baseline

                refresh_baseline(baseline, full_integrity=operation == "full", calculate_sha256=True)
            elif operation == "label":
                value = self.input("NAZWA", "Nazwa wyświetlana:", baseline.label)
                if value:
                    baseline.label = value
            elif operation == "path":
                folder = choose_directory(title="Wybierz nowy folder zestawu baz", initial_directory=baseline.path)
                if folder:
                    replacement = self.controller.add_baseline(folder, label=baseline.label)
                    if replacement.baseline_id != baseline.baseline_id:
                        self.project.remove_baseline(baseline.baseline_id)
                        self.controller.save()
                        return
            elif operation == "toggle":
                baseline.enabled = not baseline.enabled
            elif operation == "remove":
                if self.confirm(
                    "USUŃ WPIS",
                    f"Usunąć z projektu bazę „{baseline.label}”?\n\nPliki SQLite pozostaną na dysku.",
                ):
                    self.project.remove_baseline(baseline.baseline_id)
                    self.controller.save()
                    return
            self.project.touch()
            self.controller.save()

    def settings_menu(self) -> None:
        while True:
            action = self.choose(
                "USTAWIENIA PROJEKTU",
                self.status(),
                [
                    ("target_browse", "Wybierz istniejący katalog docelowy"),
                    ("target_type", "Wpisz nową ścieżkę katalogu docelowego"),
                    ("source", "Wybierz główny folder źródeł"),
                    ("recursive", "Przełącz domyślne skanowanie podfolderów"),
                    ("mode", "Tryb developer/system"),
                    ("safe", "Przywróć bezpieczne ustawienia"),
                    ("back", "Wróć"),
                ],
                default="source",
            )
            if action in {None, "back"}:
                return
            if action == "target_browse":
                folder = choose_directory(title="Wybierz katalog docelowy", initial_directory=self.project.target_root)
                if folder:
                    self.project.target_root = str(folder)
            elif action == "target_type":
                value = self.input("KATALOG DOCELOWY", "Pełna ścieżka:", self.project.target_root)
                if value:
                    self.project.target_root = str(Path(value).expanduser().resolve())
            elif action == "source":
                folder = choose_directory(
                    title="Wybierz główny folder źródeł",
                    initial_directory=self.project.source_directory or r"D:\.AI\work\memory_to_restore",
                )
                if folder:
                    self.project.source_directory = str(folder)
            elif action == "recursive":
                current = bool(self.project.settings.get("recursive_scan", False))
                self.project.settings["recursive_scan"] = not current
            elif action == "mode":
                value = self.choose(
                    "TRYB",
                    "Developer zapisuje do prywatnego katalogu poza repo. System wymaga zatrzymanego, poprawnego runtime.",
                    [("developer", "Developer — zalecany do testów"), ("system", "System — finalne bazy runtime")],
                    default=self.project.mode,
                )
                if value:
                    self.project.mode = value
            elif action == "safe":
                self.project.settings.update(
                    {
                        "verify_after_each": True,
                        "full_validation": True,
                        "continue_on_error": False,
                        "create_backup": True,
                        "audit_classifiers": True,
                        "candidate_limit": 0,
                        "automatic_experience_approval": False,
                        "automatic_l2": False,
                        "automatic_l3": False,
                    }
                )
            self.project.normalized()
            self.project.touch()
            self.controller.save()

    def preflight_menu(self) -> None:
        report = self.controller.preflight()
        action = self.choose(
            "SPRAWDZENIE GOTOWOŚCI",
            format_preflight(report),
            [
                ("sources", "Przejdź do źródeł"),
                ("settings", "Przejdź do ustawień"),
                ("technical", "Pokaż szczegóły techniczne JSON"),
                ("back", "Wróć"),
            ],
            default="back" if report.get("ok") else "sources",
        )
        if action == "sources":
            self.sources_menu()
        elif action == "settings":
            self.settings_menu()
        elif action == "technical":
            self.show("SZCZEGÓŁY TECHNICZNE", report)

    def plan_menu(self) -> None:
        preflight = self.controller.preflight()
        if not preflight.get("ok"):
            self.show("PLAN JESZCZE NIEDOSTĘPNY", format_preflight(preflight))
            return
        payload = self.controller.plan()
        action = self.choose(
            "PLAN BEZ ZAPISU",
            format_plan(payload),
            [("technical", "Pokaż pełny plan techniczny JSON"), ("back", "Wróć")],
            default="back",
        )
        if action == "technical":
            self.show("PLAN TECHNICZNY", payload)

    def compare_menu(self) -> None:
        if not Path(self.project.target_root).exists():
            self.show("BRAK WYNIKU", "Katalog docelowy jeszcze nie istnieje. Porównanie wykonaj po odbudowie.")
            return
        payload = self.controller.compare_target_to_baselines()
        lines = [
            "PORÓWNANIE Z BAZAMI TESTOWYMI",
            "",
            f"Wynik poprawny: {'Tak' if payload.get('ok') else 'Nie'}",
            f"Liczba baseline’ów: {len(payload.get('comparisons') or [])}",
        ]
        for item in payload.get("comparisons") or []:
            comparison = item.get("comparison") or {}
            lines.append(
                f"• {item.get('label')}: {'OK' if comparison.get('ok') else 'wymaga uwagi'}, "
                f"spadki={len(comparison.get('declines') or [])}"
            )
        action = self.choose(
            "PORÓWNANIE",
            "\n".join(lines),
            [("technical", "Pokaż pełne szczegóły JSON"), ("back", "Wróć")],
            default="back",
        )
        if action == "technical":
            self.show("PORÓWNANIE TECHNICZNE", payload)

    def export_menu(self) -> None:
        kind = self.choose(
            "EKSPORT",
            "Manifest zawiera konfigurację projektu, nie kopiuje danych źródłowych.",
            [("project", "Pełny manifest projektu"), ("test04", "Manifest Testu 04 v1"), ("back", "Wróć")],
            default="project",
        )
        if kind in {None, "back"}:
            return
        root = Path(self.project.target_root).parent if self.project.target_root else Path.cwd()
        default = root / ("memory-rebuild-project.json" if kind == "project" else "source-manifest-test04.private.json")
        output = self.input("EKSPORT", "Plik docelowy:", str(default))
        if not output:
            return
        if kind == "project":
            path = self.controller.export_project_manifest(output)
        else:
            baseline = self.input("TEST 04", "Baseline Test 03:", self.project.baselines[0].path if self.project.baselines else "")
            legacy = self.input("TEST 04", "Legacy memory root:", "")
            path = self.controller.export_test04_manifest(
                output,
                baseline_test03_root=baseline or None,
                legacy_memory_root=legacy or None,
            )
        self.show("ZAPISANO", str(path))

    def execute(self) -> None:
        preflight = self.controller.preflight()
        if not preflight.get("ok"):
            self.show("ODBUDOWA JESZCZE ZABLOKOWANA", format_preflight(preflight))
            return
        expected = confirmation_token(self.controller.settings())
        token = self.input(
            "POTWIERDZENIE ZAPISU",
            f"Plan jest gotowy. Aby rozpocząć zapis do nowych baz, wpisz dokładnie:\n\n{expected}",
            "",
        )
        if token is None or token != expected:
            self.show("ANULOWANO", "Token nie jest zgodny. Nie wykonano zapisu.")
            return
        if not self.confirm(
            "OSTATNIA KONTROLA",
            f"Uruchomić odbudowę do:\n{self.project.target_root}\n\nAutomatyczne L2/L3 pozostają wyłączone.",
        ):
            return
        result = self.controller.run(confirmation=token)
        self.show("ODBUDOWA ZAKOŃCZONA", "Operacja się zakończyła. Szczegóły techniczne są dostępne w projekcie i raportach przebiegu.")
        self.events.append({"type": "run_result", "result": result})


def run_studio(
    *,
    project_root: str | Path | None = None,
    project: str | Path | None = None,
    tool_root: str | Path | None = None,
    text_ui: bool = False,
) -> int:
    store = ProjectStore(project_root)
    try:
        selected = store.load(project) if project else choose_or_create_project(store, cursor=not text_ui)
        return MemoryRebuildStudio(selected, store=store, tool_root=tool_root, cursor=not text_ui).run()
    except (StudioExit, KeyboardInterrupt, EOFError):
        return 0


__all__ = ["HAS_CURSOR_UI", "MemoryRebuildStudio", "StudioExit", "choose_or_create_project", "run_studio"]
