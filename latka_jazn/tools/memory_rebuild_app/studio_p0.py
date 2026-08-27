from __future__ import annotations

"""Memory Rebuild Studio P0 full-screen terminal UI.

P0 reorganizes the existing v2.4 workflows into three operator-facing pages:
TESTY, PROJEKTOWANIE, and USTAWIENIA.  It deliberately reuses the proven
project/import/candidate/export controllers instead of introducing a second
memory engine.  The full-screen shell exits temporarily when an existing
workflow/dialog is opened, then restores the same studio state afterwards.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import json

from .controller import MemoryRebuildAppController
from .models import DEFAULT_SETTINGS
from .project_store import ProjectStore
from .read_only_validation import validate_existing_database
from .settings import MemoryRebuildSettings, load_settings
from .test_profiles import PROFILE_NAMES, run_test_profile
from .themes import DEFAULT_STUDIO_THEME_NAME, cycle_theme_name, get_theme, prompt_toolkit_style
from .layout import build_studio_layout
from .tui import run_studio as run_project_studio
from .tui_candidates import candidate_menu
from .tui_common import database_from_project, format_stats, message
from .tui_export import final_export_menu
from .tui_import import source_import_menu
from .tui_paths import choose_database

STUDIO_P0_VERSION = "memory-rebuild-studio/v16.3.13"
PAGE_IDS = ("tests", "design", "settings")
PAGE_LABELS = {
    "tests": "TESTY",
    "design": "PROJEKTOWANIE",
    "settings": "USTAWIENIA",
}


@dataclass(frozen=True, slots=True)
class PageItem:
    key: str
    label: str
    hint: str = ""


@dataclass(frozen=True, slots=True)
class TestProfilePresentation:
    profile: str
    label: str
    goal: str
    requirements: tuple[str, ...]
    checks: tuple[str, ...]


TEST_PRESENTATIONS: tuple[TestProfilePresentation, ...] = (
    TestProfilePresentation(
        profile="test01",
        label="Test 01 — fundament rozmów",
        goal="Potwierdza minimalną, spójną bazę L0 rozmów i indeks wyszukiwania.",
        requirements=("Istniejąca memory_jazn.sqlite3",),
        checks=(
            "SQLite integrity + foreign keys",
            "jedna fizyczna baza pamięci",
            "FTS5 integrity + smoke query",
            "co najmniej 1 rozmowa, 1 węzeł i 1 dokument FTS",
            "walidacja tylko do odczytu nie zmienia bazy",
        ),
    ),
    TestProfilePresentation(
        profile="test02",
        label="Test 02 — rozmowy + dziennik",
        goal="Rozszerza Test 01 o obecność dziennika w tej samej bazie.",
        requirements=("Wymagania Testu 01", "Zaimportowany dziennik"),
        checks=(
            "wszystkie kontrole Testu 01",
            "journal_entries > 0",
            "brak zapisu podczas walidacji",
        ),
    ),
    TestProfilePresentation(
        profile="test03",
        label="Test 03 — proweniencja i konflikty",
        goal="Sprawdza źródła importu oraz brak nierozwiązanych konfliktów.",
        requirements=("Wymagania Testu 02", "Zarejestrowane źródła importu"),
        checks=(
            "wszystkie kontrole Testu 02",
            "import_sources > 0",
            "0 nierozwiązanych konfliktów import/migration/runtime-sync",
            "walidacja tylko do odczytu",
        ),
    ),
    TestProfilePresentation(
        profile="test04",
        label="Test 04 — pełna akceptacja odbudowy",
        goal="Porównuje wynik z baseline'ami i wymaga pełnego raportu akceptacyjnego.",
        requirements=(
            "Wymagania Testu 03",
            "Baseline Testów 01–03",
            "Raport pełnej akceptacji Testu 04",
        ),
        checks=(
            "record-level reconciliation bez brakujących stabilnych kluczy",
            "source completeness",
            "same-target idempotence",
            "fresh rebuild reproducibility",
            "Test03 reconciliation",
            "recall + multi-turn review",
            "HTML dry-run, jeśli dotyczy",
            "restart continuity dodatkowo dla system acceptance",
        ),
    ),
    TestProfilePresentation(
        profile="final",
        label="Final — gotowość pamięci",
        goal="Nadzbiór Testu 04 z kontrolą ręcznie zatwierdzanych L2/L3.",
        requirements=("Zaliczony Test 04", "Ledger decyzji/promocji L2/L3"),
        checks=(
            "wszystkie kontrole Testu 04",
            "brak automatycznych decyzji commit/promocji",
            "każde aktywne L3 ma decyzję i ledger",
            "candidate scores mieszczą się w 0..1",
            "zatwierdzone doświadczenia mają źródłowych kandydatów",
        ),
    ),
)

DESIGN_ITEMS: tuple[PageItem, ...] = (
    PageItem("project", "Projekt i źródła", "Lista źródeł, baseline'y, role, pipeline'y i notatki."),
    PageItem("database", "Baza docelowa", "Wybór jednej kanonicznej memory_jazn.sqlite3."),
    PageItem("import", "Import źródeł", "Rozmowy, HTML, dzienniki i nowe wątki."),
    PageItem("candidates", "Kandydaci pamięci", "Podgląd, edycja i jawne decyzje bez auto-L2/L3."),
    PageItem("plan", "Plan bez zapisu", "Preflight i plan odbudowy bez modyfikowania celu."),
    PageItem("compare", "Porównanie z baseline", "Porównanie celu z zachowanymi Testami 01–04."),
    PageItem("export", "Finalny eksport", "Kontrolowany staging finalnej pamięci."),
)

SETTINGS_ITEMS: tuple[PageItem, ...] = (
    PageItem("all", "Wszystkie ustawienia", "Pełny przegląd opcji projektu i silnika."),
    PageItem("project-settings", "Ustawienia projektu", "Skanowanie, walidacja, backup i klasyfikacja."),
    PageItem("retrieval", "FTS / retrieval / embeddings", "Parametry wyszukiwania i opcjonalnych embeddingów."),
    PageItem("safety", "Granice bezpieczeństwa", "Wymuszone blokady automatycznej promocji i aktywacji."),
    PageItem("paths", "Ścieżki i środowisko", "Projekt, baza, settings JSON i katalog narzędzia."),
    PageItem("theme", "Wygląd / theme", "Paleta terminalowa i informacje o układzie."),
)


def test_presentation(profile: str) -> TestProfilePresentation:
    for item in TEST_PRESENTATIONS:
        if item.profile == profile:
            return item
    raise KeyError(profile)


def _yes_no(value: Any) -> str:
    return "TAK" if bool(value) else "NIE"


def _value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return _yes_no(value)
    return str(value)


def _project_setting_lines(settings: dict[str, Any]) -> list[str]:
    keys = tuple(DEFAULT_SETTINGS)
    return [f"{key}: {_value(settings.get(key, DEFAULT_SETTINGS[key]))}" for key in keys]


def _runtime_setting_lines(settings: MemoryRebuildSettings) -> list[str]:
    return [
        f"require_fts5: {_yes_no(settings.require_fts5)}",
        f"require_provenance: {_yes_no(settings.require_provenance)}",
        f"retrieval_limit: {settings.retrieval_limit}",
        f"min_lexical_score: {settings.min_lexical_score}",
        f"embeddings_enabled: {_yes_no(settings.embeddings_enabled)}",
        f"embedding_model: {_value(settings.embedding_model)}",
        f"automatic_l2: {_yes_no(settings.automatic_l2)} [ZABLOKOWANE]",
        f"automatic_l3: {_yes_no(settings.automatic_l3)} [ZABLOKOWANE]",
        f"automatic_activation: {_yes_no(settings.automatic_activation)} [ZABLOKOWANE]",
    ]


@dataclass(slots=True)
class StudioAction:
    kind: str
    value: str | None = None


@dataclass(slots=True)
class StudioState:
    database: Path
    project_root: str | Path | None
    project: str | None
    tool_root: Path
    settings_path: str | Path | None = None
    active_page: str = "tests"
    selected: dict[str, int] = field(default_factory=lambda: {page: 0 for page in PAGE_IDS})
    theme_name: str = DEFAULT_STUDIO_THEME_NAME
    status: str = "Gotowe. Wybierz stronę i operację."
    status_kind: str = "ok"
    project_snapshot: dict[str, Any] | None = None
    project_error: str | None = None
    runtime_settings: MemoryRebuildSettings = field(default_factory=MemoryRebuildSettings)

    def __post_init__(self) -> None:
        self.database = Path(self.database).expanduser().resolve()
        self.tool_root = Path(self.tool_root).expanduser().resolve()
        self.refresh()

    def refresh(self) -> None:
        self.project_snapshot = None
        self.project_error = None
        try:
            self.runtime_settings = load_settings(self.settings_path)
        except Exception as exc:
            self.runtime_settings = MemoryRebuildSettings()
            self.project_error = f"settings: {type(exc).__name__}: {exc}"
        if not self.project:
            return
        try:
            loaded = ProjectStore(self.project_root).load(self.project)
            self.project_snapshot = loaded.to_dict()
        except Exception as exc:
            self.project_error = f"project: {type(exc).__name__}: {exc}"

    def set_page(self, page: str) -> None:
        if page not in PAGE_IDS:
            raise ValueError(page)
        self.active_page = page

    def cycle_page(self, delta: int) -> None:
        index = PAGE_IDS.index(self.active_page)
        self.active_page = PAGE_IDS[(index + delta) % len(PAGE_IDS)]

    def items(self) -> Sequence[PageItem]:
        if self.active_page == "tests":
            return tuple(PageItem(item.profile, item.label, item.goal) for item in TEST_PRESENTATIONS)
        if self.active_page == "design":
            return DESIGN_ITEMS
        return SETTINGS_ITEMS

    def move_selection(self, delta: int) -> None:
        items = self.items()
        if not items:
            return
        current = self.selected.get(self.active_page, 0)
        self.selected[self.active_page] = (current + delta) % len(items)

    def current_item(self) -> PageItem:
        items = self.items()
        index = min(self.selected.get(self.active_page, 0), max(0, len(items) - 1))
        return items[index]

    def cycle_theme(self) -> None:
        self.theme_name = cycle_theme_name(self.theme_name)
        self.status = f"Theme sesji: {self.theme_name}"
        self.status_kind = "ok"

    def header_fragments(self):
        theme = get_theme(self.theme_name)
        project_name = (self.project_snapshot or {}).get("name") or self.project or "bez projektu"
        return [
            ("class:header-title", f"  {theme.title}  "),
            ("class:header-version", f"{STUDIO_P0_VERSION}   "),
            ("class:muted", f"projekt: {project_name}"),
            ("", "\n"),
            ("class:muted", f"  baza: {self.database}"),
        ]

    def tab_fragments(self):
        fragments: list[tuple[str, str]] = [("", "  ")]
        for page in PAGE_IDS:
            style = "class:tab-active" if page == self.active_page else "class:tab"
            fragments.append((style, f" {PAGE_LABELS[page]} "))
            fragments.append(("class:tabs", "  "))
        return fragments

    def sidebar_fragments(self):
        fragments: list[tuple[str, str]] = []
        selected = self.selected.get(self.active_page, 0)
        for index, item in enumerate(self.items()):
            style = "class:selected" if index == selected else "class:sidebar"
            marker = "›" if index == selected else " "
            fragments.append((style, f" {marker} {item.label}\n"))
        return fragments

    def _project_lines(self) -> list[str]:
        project = self.project_snapshot
        if project is None:
            lines = ["Projekt: nie wybrano lub nie można odczytać."]
            if self.project_error:
                lines.append(self.project_error)
            lines.append("Otwórz „Projekt i źródła”, aby utworzyć albo wybrać konfigurację.")
            return lines
        return [
            f"Nazwa: {project.get('name')}",
            f"Tryb: {project.get('mode')}",
            f"Target root: {project.get('target_root')}",
            f"Folder źródeł: {project.get('source_directory') or '—'}",
            f"Źródła: {len(project.get('sources') or [])}",
            f"Baseline'y: {len(project.get('baselines') or [])}",
            f"Revision: {project.get('revision')}",
        ]

    def _test_detail(self, profile: str) -> list[str]:
        item = test_presentation(profile)
        lines = [item.label, "", item.goal, "", "Wymagania:"]
        lines.extend(f"  • {value}" for value in item.requirements)
        lines.extend(("", "Kontrole:"))
        lines.extend(f"  ✓ {value}" for value in item.checks)
        lines.extend(("", "Uruchomienie jest read-only. Klawisz R lub Enter uruchamia wybrany profil."))
        return lines

    def _design_detail(self, key: str) -> list[str]:
        item = next(value for value in DESIGN_ITEMS if value.key == key)
        lines = [item.label, "", item.hint, "", "Stan projektu:"]
        lines.extend(f"  {value}" for value in self._project_lines())
        lines.extend(("", f"Kanoniczna baza: {self.database}", f"Istnieje: {_yes_no(self.database.is_file())}"))
        if key == "plan":
            lines.extend(("", "Plan bez zapisu wykorzystuje istniejący preflight i nie uruchamia odbudowy."))
        elif key == "compare":
            lines.extend(("", "Baseline'y pozostają tylko do odczytu."))
        elif key == "candidates":
            lines.extend(("", "Brak automatycznej akceptacji doświadczeń i promocji L2/L3."))
        return lines

    def _settings_detail(self, key: str) -> list[str]:
        project_settings = dict(DEFAULT_SETTINGS)
        if self.project_snapshot:
            project_settings.update(dict(self.project_snapshot.get("settings") or {}))
        if key == "project-settings":
            return ["Ustawienia projektu", ""] + _project_setting_lines(project_settings) + [
                "",
                "Enter otwiera istniejący edytor projektu.",
            ]
        if key == "retrieval":
            return ["FTS / retrieval / embeddings", ""] + _runtime_setting_lines(self.runtime_settings)
        if key == "safety":
            return [
                "Granice bezpieczeństwa",
                "",
                "FTS5 wymagane: TAK",
                "Proweniencja wymagana: TAK",
                "Automatyczna akceptacja doświadczeń: NIE [ZABLOKOWANE]",
                "Automatyczne L2: NIE [ZABLOKOWANE]",
                "Automatyczne L3: NIE [ZABLOKOWANE]",
                "Automatyczna aktywacja: NIE [ZABLOKOWANE]",
                "Surowe L0 i baseline'y nie są edytowane przez walidację.",
            ]
        if key == "paths":
            return [
                "Ścieżki i środowisko",
                "",
                f"Project root: {_value(self.project_root)}",
                f"Project: {_value(self.project)}",
                f"Database: {self.database}",
                f"Settings JSON: {_value(self.settings_path)}",
                f"Tool root: {self.tool_root}",
                f"Database exists: {_yes_no(self.database.is_file())}",
            ]
        if key == "theme":
            theme = get_theme(self.theme_name)
            return [
                "Wygląd / theme",
                "",
                f"Theme: {theme.name}",
                f"Tło: {theme.background}",
                f"Panel: {theme.panel}",
                f"Obramowanie: {theme.border}",
                f"Akcent: {theme.accent}",
                "",
                "T przełącza paletę podczas bieżącej sesji.",
                "Kod jest rozdzielony: theme.py / themes.py / layout.py.",
            ]
        return (
            ["Wszystkie ustawienia", "", "[projekt]"]
            + _project_setting_lines(project_settings)
            + ["", "[silnik / retrieval]"]
            + _runtime_setting_lines(self.runtime_settings)
            + [
                "",
                "[informacje]",
                f"theme: {self.theme_name}",
                f"database: {self.database}",
                f"project: {_value(self.project)}",
                f"settings_json: {_value(self.settings_path)}",
            ]
        )

    def content_fragments(self):
        key = self.current_item().key
        if self.active_page == "tests":
            lines = self._test_detail(key)
        elif self.active_page == "design":
            lines = self._design_detail(key)
        else:
            lines = self._settings_detail(key)
        fragments: list[tuple[str, str]] = []
        for index, line in enumerate(lines):
            if index == 0:
                style = "class:section"
            elif "ZABLOKOWANE" in line:
                style = "class:warning"
            elif line.startswith("  ✓"):
                style = "class:success"
            elif line.startswith("[") and line.endswith("]"):
                style = "class:accent"
            else:
                style = "class:content"
            fragments.append((style, f" {line}\n"))
        return fragments

    def status_fragments(self):
        style = "class:status-error" if self.status_kind == "error" else "class:status-ok"
        return [(style, f" {self.status}")]

    def footer_fragments(self):
        return [
            ("class:footer-key", " 1 "), ("class:footer", "Testy  "),
            ("class:footer-key", " 2 "), ("class:footer", "Projektowanie  "),
            ("class:footer-key", " 3 "), ("class:footer", "Ustawienia  "),
            ("class:footer-key", " ↑↓ "), ("class:footer", "Wybór  "),
            ("class:footer-key", " Enter "), ("class:footer", "Otwórz  "),
            ("class:footer-key", " R "), ("class:footer", "Test  "),
            ("class:footer-key", " T "), ("class:footer", "Theme  "),
            ("class:footer-key", " Q "), ("class:footer", "Wyjście"),
        ]


def _action_for_state(state: StudioState) -> StudioAction | None:
    item = state.current_item().key
    if state.active_page == "tests":
        return StudioAction("run-test", item)
    if state.active_page == "design":
        return StudioAction(item)
    if item == "project-settings":
        return StudioAction("project")
    return None


def _run_shell(state: StudioState) -> StudioAction:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings

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
        state.cycle_theme()
        event.app.style = prompt_toolkit_style(get_theme(state.theme_name))
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
        action = _action_for_state(state)
        if action is None:
            state.status = "Ta sekcja jest informacyjna. Użyj T dla theme lub wybierz Ustawienia projektu."
            state.status_kind = "ok"
            invalidate(event)
            return
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


def _project_object(state: StudioState):
    if not state.project:
        return None
    return ProjectStore(state.project_root).load(state.project)


def _remember_database(state: StudioState) -> None:
    if not state.project:
        return
    store = ProjectStore(state.project_root)
    loaded = store.load(state.project)
    loaded.settings["unified_database_path"] = str(state.database)
    store.save(loaded)


def _format_test_report(report: dict[str, Any]) -> str:
    lines = [
        f"Profil: {report.get('profile')}",
        f"Wynik: {'ZALICZONY' if report.get('ok') else 'NIEZALICZONY'}",
        f"Baza: {report.get('database')}",
        "",
    ]
    for check in report.get("checks") or []:
        passed = bool(check.get("passed"))
        blocking = bool(check.get("blocking", True))
        mark = "✓" if passed else ("!" if not blocking else "✗")
        lines.append(f"{mark} {check.get('name')}: {check.get('actual')}")
    return "\n".join(lines)


def _run_test_action(state: StudioState, profile: str) -> None:
    if profile not in PROFILE_NAMES:
        raise ValueError(profile)
    project = _project_object(state)
    baselines = [item.path for item in project.enabled_baselines()] if project else []
    settings = dict(project.settings) if project else {}
    acceptance_report = settings.get("test04_acceptance_report")
    system_acceptance = bool(settings.get("system_acceptance", False))
    report = run_test_profile(
        state.database,
        profile,
        baselines=baselines,
        full_validation=True,
        acceptance_report=acceptance_report,
        system_acceptance=system_acceptance,
    )
    state.status = f"{profile.upper()}: {'ZALICZONY' if report.get('ok') else 'NIEZALICZONY'}"
    state.status_kind = "ok" if report.get("ok") else "error"
    message("Wynik testu pamięci", _format_test_report(report))


def _run_project_action(state: StudioState) -> None:
    run_project_studio(
        project_root=state.project_root,
        project=state.project,
        tool_root=state.tool_root,
        text_ui=False,
    )
    configured = database_from_project(state.project_root, state.project)
    if configured is not None:
        state.database = configured
    state.status = "Wrócono z edytora projektu."
    state.status_kind = "ok"


def _run_plan_action(state: StudioState, *, compare: bool = False) -> None:
    project = _project_object(state)
    if project is None:
        raise ValueError("Plan i porównanie wymagają wybranego projektu.")
    controller = MemoryRebuildAppController(project, store=ProjectStore(state.project_root), tool_root=state.tool_root)
    payload = controller.compare_target_to_baselines(full_integrity=False) if compare else controller.plan()
    ok = bool(payload.get("ok", payload.get("engine_plan", {}).get("ok")))
    state.status = f"{'Porównanie' if compare else 'Plan bez zapisu'}: {'OK' if ok else 'wymaga uwagi'}"
    state.status_kind = "ok" if ok else "error"
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if len(body) > 7000:
        body = body[:7000] + "\n… [pełny wynik dostępny w CLI/JSON]"
    message("Porównanie baseline" if compare else "Plan bez zapisu", body)


def _handle_action(state: StudioState, action: StudioAction) -> int | None:
    if action.kind == "quit":
        return 0
    if action.kind == "run-test":
        _run_test_action(state, str(action.value))
    elif action.kind == "project":
        _run_project_action(state)
    elif action.kind == "database":
        selected = choose_database(state.database)
        if selected:
            state.database = Path(selected).expanduser().resolve()
            _remember_database(state)
            state.status = f"Baza: {state.database}"
            state.status_kind = "ok"
    elif action.kind == "import":
        source_import_menu(state.database)
        state.status = "Zakończono menu importu."
        state.status_kind = "ok"
    elif action.kind == "candidates":
        candidate_menu(state.database)
        state.status = "Zakończono menu kandydatów."
        state.status_kind = "ok"
    elif action.kind == "export":
        final_export_menu(state.database)
        state.status = "Zakończono menu finalnego eksportu."
        state.status_kind = "ok"
    elif action.kind == "plan":
        _run_plan_action(state, compare=False)
    elif action.kind == "compare":
        _run_plan_action(state, compare=True)
    else:
        state.status = f"Nieobsługiwana akcja: {action.kind}"
        state.status_kind = "error"
    state.refresh()
    return None


def run_studio_p0(
    *,
    database: str | Path,
    project_root: str | Path | None = None,
    project: str | None = None,
    tool_root: str | Path | None = None,
    settings_path: str | Path | None = None,
) -> int:
    """Run the P0 studio shell and reuse existing workflows for actions."""

    state = StudioState(
        database=Path(database),
        project_root=project_root,
        project=project,
        tool_root=Path(tool_root or Path.cwd()),
        settings_path=settings_path,
    )
    while True:
        action = _run_shell(state)
        try:
            result = _handle_action(state, action)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            state.status = f"{type(exc).__name__}: {exc}"
            state.status_kind = "error"
            message("Memory Rebuild Studio", state.status)
            state.refresh()
            continue
        if result is not None:
            return result


__all__ = [
    "DESIGN_ITEMS",
    "PAGE_IDS",
    "PAGE_LABELS",
    "SETTINGS_ITEMS",
    "STUDIO_P0_VERSION",
    "StudioAction",
    "StudioState",
    "TEST_PRESENTATIONS",
    "TestProfilePresentation",
    "run_studio_p0",
    "test_presentation",
]
