from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import json

from latka_jazn.tools.memory_restore import confirmation_token

from .controller import MemoryRebuildAppController, MemoryRebuildAppError
from .models import PIPELINES, SOURCE_ROLES, TRUTH_DOMAINS, RebuildProject
from .project_store import ProjectStore

try:  # pragma: no cover - terminal dependent
    from prompt_toolkit.shortcuts import input_dialog, message_dialog, radiolist_dialog, yes_no_dialog

    HAS_CURSOR_UI = True
except Exception:  # pragma: no cover
    input_dialog = None  # type: ignore[assignment]
    message_dialog = None  # type: ignore[assignment]
    radiolist_dialog = None  # type: ignore[assignment]
    yes_no_dialog = None  # type: ignore[assignment]
    HAS_CURSOR_UI = False


class StudioExit(Exception):
    pass


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _short(value: str, width: int = 64) -> str:
    if len(value) <= width:
        return value
    keep = max(8, (width - 3) // 2)
    return value[:keep] + "..." + value[-keep:]


def _text_choice(title: str, values: Sequence[tuple[Any, str]]) -> Any:
    print(f"\n=== {title} ===")
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
        choices = [(item.project_id, f"{item.name} — {_short(item.target_root)}") for item in projects]
        choices.extend((("__new__", "Utwórz nowy projekt"), ("__exit__", "Wyjdź")))
        if cursor and HAS_CURSOR_UI:
            assert radiolist_dialog is not None
            selected = radiolist_dialog(
                title="ODBUDOWA PAMIĘCI JAŹNI",
                text="Wybierz projekt. Bazy testowe pozostają tylko do odczytu.",
                values=choices,
                default=projects[0].project_id if projects else "__new__",
            ).run()
        else:
            selected = _text_choice("PROJEKTY ODBUDOWY", choices)
        if selected in {None, "__exit__"}:
            raise StudioExit()
        if selected != "__new__":
            return store.load(str(selected))
        if cursor and HAS_CURSOR_UI:
            assert input_dialog is not None
            name = input_dialog(title="NOWY PROJEKT", text="Nazwa:", default="Pełna pamięć Łatki").run()
            target = input_dialog(title="NOWY PROJEKT", text="Nowy katalog docelowy:", default=r"D:\PRIVATE\jazn_memory_test_05").run()
            source = input_dialog(title="NOWY PROJEKT", text="Katalog źródeł (opcjonalnie):", default="").run()
        else:
            name = input("Nazwa projektu: ").strip() or "Pełna pamięć Łatki"
            target = input("Nowy katalog docelowy: ").strip()
            source = input("Katalog źródeł (opcjonalnie): ").strip()
        if not target:
            continue
        project = RebuildProject.create(name or "Pełna pamięć Łatki", target, source_directory=source or "")
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
            message_dialog(title=title, text=text).run()
        else:
            print(f"\n=== {title} ===\n{text}")

    def input(self, title: str, prompt: str, default: str = "") -> str | None:
        if self.cursor:
            assert input_dialog is not None
            return input_dialog(title=title, text=prompt, default=default).run()
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw or default

    def choose(self, title: str, text: str, values: Sequence[tuple[Any, str]], default: Any = None) -> Any:
        if self.cursor:
            assert radiolist_dialog is not None
            return radiolist_dialog(title=title, text=text, values=list(values), default=default).run()
        return _text_choice(title, values)

    def confirm(self, title: str, text: str) -> bool:
        if self.cursor:
            assert yes_no_dialog is not None
            return bool(yes_no_dialog(title=title, text=text).run())
        return input(f"{text} [t/N]: ").strip().casefold() in {"t", "tak", "y", "yes"}

    def status(self) -> str:
        return (
            f"Projekt: {self.project.name}\n"
            f"Cel: {self.project.target_root}\n"
            f"Tryb: {self.project.mode}\n"
            f"Źródła: {len(self.project.enabled_sources())}/{len(self.project.sources)}\n"
            f"Baseline’y: {len(self.project.enabled_baselines())}/{len(self.project.baselines)}\n"
            f"Rewizja: {self.project.revision}\n"
            "Automatyczne experience/L2/L3: OFF/OFF/OFF"
        )

    def run(self) -> int:
        actions = (
            ("sources", "Źródła — dodaj, obejrzyj i ustaw metadane"),
            ("baselines", "Bazy testowe — dodaj i porównuj tylko do odczytu"),
            ("settings", "Ustawienia projektu"),
            ("preflight", "Preflight bez zapisu"),
            ("plan", "Plan silnika bez zapisu"),
            ("compare", "Porównanie celu z baseline’ami"),
            ("export", "Eksport manifestu projektu lub Testu 04"),
            ("execute", "Uruchom kontrolowaną odbudowę"),
            ("events", "Pokaż zdarzenia sesji"),
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
                    self.show("PREFLIGHT", self.controller.preflight())
                elif action == "plan":
                    self.show("PLAN BEZ ZAPISU", self.controller.plan())
                elif action == "compare":
                    self.show("PORÓWNANIE", self.controller.compare_target_to_baselines())
                elif action == "export":
                    self.export_menu()
                elif action == "execute":
                    self.execute()
                elif action == "events":
                    self.show("ZDARZENIA", self.events)
                elif action == "save":
                    self.show("ZAPISANO", str(self.controller.save()))
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
                self.show("BŁĄD KONTROLOWANY", f"{type(exc).__name__}: {exc}")

    def sources_menu(self) -> None:
        while True:
            rows = [
                (
                    item.source_id,
                    f"{item.order:02d} {'✓' if item.enabled else '–'} {item.role:<20} {Path(item.path).name}",
                )
                for item in self.project.sources
            ]
            action = self.choose(
                "ŹRÓDŁA",
                "Surowa treść źródeł nie jest edytowana. Zmieniane są tylko metadane projektu.",
                [("add", "Dodaj plik"), ("inspect", "Wybierz źródło do podglądu/edycji"), ("back", "Wróć")],
                default="add",
            )
            if action in {None, "back"}:
                return
            if action == "add":
                path = self.input("DODAJ ŹRÓDŁO", "Pełna ścieżka pliku:")
                if path:
                    self.show("WYNIK INSPEKCJI", self.controller.inspect_and_add_source(path).to_dict())
                    self.controller.save()
                continue
            if not rows:
                self.show("ŹRÓDŁA", "Brak źródeł.")
                continue
            source_id = self.choose("WYBIERZ ŹRÓDŁO", "", rows, default=rows[0][0])
            if not source_id:
                continue
            source = self.project.source_by_id(source_id)
            operation = self.choose(
                "ŹRÓDŁO",
                _json_text(source.to_dict()),
                [
                    ("refresh", "Odśwież SHA i inspekcję"),
                    ("role", "Zmień rolę"),
                    ("truth", "Zmień domenę prawdy"),
                    ("pipeline", "Zmień pipeline"),
                    ("toggle", "Włącz/wyłącz"),
                    ("approve", "Przełącz approved"),
                    ("up", "Przesuń w górę"),
                    ("down", "Przesuń w dół"),
                    ("remove", "Usuń z projektu"),
                    ("back", "Wróć"),
                ],
                default="refresh",
            )
            if operation == "refresh":
                self.controller.refresh_source(source.source_id)
            elif operation == "role":
                value = self.choose("ROLA", "", [(item, item) for item in SOURCE_ROLES], default=source.role)
                if value:
                    source.role = value
            elif operation == "truth":
                value = self.choose("DOMENA PRAWDY", "", [(item, item) for item in TRUTH_DOMAINS], default=source.truth_domain)
                if value:
                    source.truth_domain = value
            elif operation == "pipeline":
                value = self.choose("PIPELINE", "", [(item, item) for item in PIPELINES], default=source.pipeline)
                if value:
                    source.pipeline = value
            elif operation == "toggle":
                source.enabled = not source.enabled
            elif operation == "approve":
                source.approved = not source.approved
            elif operation == "up":
                self.project.move_source(source.source_id, -1)
            elif operation == "down":
                self.project.move_source(source.source_id, 1)
            elif operation == "remove" and self.confirm("USUŃ", "Usunąć tylko wpis z projektu?"):
                self.project.remove_source(source.source_id)
            self.project.normalized()
            self.project.touch()
            self.controller.save()

    def baselines_menu(self) -> None:
        while True:
            values = [(item.baseline_id, f"{'✓' if item.enabled else '–'} {item.label} [{item.status}]") for item in self.project.baselines]
            action = self.choose(
                "BASELINE’Y",
                "Program nigdy nie zapisuje do tych baz.",
                [("add", "Dodaj katalog bazy testowej"), ("select", "Wybierz istniejący baseline"), ("refresh", "Odśwież wszystkie"), ("back", "Wróć")],
                default="add",
            )
            if action in {None, "back"}:
                return
            if action == "add":
                path = self.input("DODAJ BASELINE", "Katalog testu lub memory/sqlite:")
                if path:
                    label = self.input("DODAJ BASELINE", "Nazwa:", Path(path).name)
                    self.show("BASELINE", self.controller.add_baseline(path, label=label).to_dict())
                    self.controller.save()
            elif action == "refresh":
                self.controller.refresh_baselines()
                self.controller.save()
            elif action == "select":
                if not values:
                    continue
                baseline_id = self.choose("WYBIERZ", "", values, default=values[0][0])
                if not baseline_id:
                    continue
                baseline = self.project.baseline_by_id(baseline_id)
                operation = self.choose(
                    "BASELINE",
                    _json_text(baseline.to_dict()),
                    [("toggle", "Włącz/wyłącz"), ("remove", "Usuń z projektu"), ("back", "Wróć")],
                    default="toggle",
                )
                if operation == "toggle":
                    baseline.enabled = not baseline.enabled
                    self.project.touch()
                elif operation == "remove" and self.confirm("USUŃ", "Usunąć wpis? Pliki baz pozostaną bez zmian."):
                    self.project.remove_baseline(baseline.baseline_id)
                self.controller.save()

    def settings_menu(self) -> None:
        action = self.choose(
            "USTAWIENIA",
            self.status(),
            [("target", "Katalog docelowy"), ("source", "Katalog źródeł"), ("mode", "Tryb developer/system"), ("safe", "Przywróć bezpieczne granice"), ("back", "Wróć")],
            default="target",
        )
        if action == "target":
            value = self.input("CEL", "Katalog docelowy:", self.project.target_root)
            if value:
                self.project.target_root = str(Path(value).expanduser().resolve())
        elif action == "source":
            value = self.input("ŹRÓDŁA", "Katalog źródeł:", self.project.source_directory)
            if value is not None:
                self.project.source_directory = str(Path(value).expanduser().resolve()) if value else ""
        elif action == "mode":
            value = self.choose("TRYB", "", [("developer", "developer"), ("system", "system")], default=self.project.mode)
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
        if action not in {None, "back"}:
            self.project.normalized()
            self.project.touch()
            self.controller.save()

    def export_menu(self) -> None:
        kind = self.choose("EKSPORT", "", [("project", "Pełny manifest projektu"), ("test04", "Manifest Testu 04 v1"), ("back", "Wróć")], default="project")
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
            path = self.controller.export_test04_manifest(output, baseline_test03_root=baseline or None, legacy_memory_root=legacy or None)
        self.show("ZAPISANO", str(path))

    def execute(self) -> None:
        preflight = self.controller.preflight()
        if not preflight.get("ok"):
            self.show("ODBUDOWA ZABLOKOWANA", preflight)
            return
        expected = confirmation_token(self.controller.settings())
        token = self.input("POTWIERDZENIE", f"Wpisz dokładnie:\n{expected}", "")
        if token != expected:
            self.show("ANULOWANO", "Token nie jest zgodny. Nie wykonano zapisu.")
            return
        if not self.confirm("OSTATNIA KONTROLA", f"Uruchomić odbudowę do {self.project.target_root}?\nL2/L3 pozostają OFF/OFF."):
            return
        self.show("WYNIK", self.controller.run(confirmation=token))


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
